"""Transcript replay adapter for the existing dev chat flow."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from app import database as db
from conversation_to_memory.bot import chat_service, session, states
from conversation_to_memory.memory.fidelity import validate_draft
from conversation_to_memory.storage.local_json import DEFAULT_MEMORIES_DIR

ReplayMode = Literal["dry-run", "interactive-review", "save-final"]
InteractiveReviewChoice = Literal["save", "skip", "exit"]


@dataclass
class ReplayBlock:
    """One replayable recording unit."""

    index: int
    source_text: str
    conversation: list[dict[str, str]]
    session_id: str | None = None
    recorded_at: datetime | None = None


_BLOCK_DATETIME_PATTERNS: tuple[re.Pattern[str], ...] = (
    # YYYY MM DD HHmm (spaces), e.g. "2026 06 23 0754"
    re.compile(r"^(?P<y>20\d{2})\s+(?P<m>\d{1,2})\s+(?P<d>\d{1,2})\s+(?P<t>\d{3,4})\s*$"),
    # YYYY-MM-DD with optional HHmm, e.g. "2026-06-21" or "2026-06-21 0754"
    re.compile(r"^(?P<y>20\d{2})-(?P<m>\d{1,2})-(?P<d>\d{1,2})(?:\s+(?P<t>\d{3,4}))?\s*$"),
)


@dataclass
class ReplayBlockResult:
    index: int
    replay_hash: str
    draft: dict[str, Any] | None = None
    validation: dict[str, Any] = field(default_factory=dict)
    saved: bool = False
    skipped: bool = False
    output_path: str | None = None
    messages: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class ReplayRunResult:
    input_file: str
    mode: ReplayMode
    parsed_blocks: int
    saved: bool
    results: list[ReplayBlockResult]
    aborted: bool = False


def parse_txt_blocks(text: str) -> list[str]:
    """Split bulk memo text on --- or === lines and drop empty blocks."""
    chunks = re.split(r"(?m)^\s*(?:---|===)\s*$", text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def parse_block_header_datetime(text: str) -> tuple[datetime | None, str]:
    """Parse an optional memo timestamp from the first line and return the body."""
    stripped = text.strip()
    if not stripped:
        return None, stripped

    first_line, separator, rest = stripped.partition("\n")
    first_line = first_line.strip()
    for pattern in _BLOCK_DATETIME_PATTERNS:
        match = pattern.match(first_line)
        if not match:
            continue
        year = int(match.group("y"))
        month = int(match.group("m"))
        day = int(match.group("d"))
        hour, minute = 0, 0
        time_part = match.group("t")
        if time_part:
            padded = time_part.zfill(4)
            hour = int(padded[:2])
            minute = int(padded[2:])
        try:
            recorded_at = datetime(year, month, day, hour, minute)
        except ValueError:
            continue
        body = rest.strip() if separator else ""
        return recorded_at, body

    return None, stripped


def parse_json_blocks(data: Any) -> list[ReplayBlock]:
    """Parse supported JSON transcript formats."""
    if not isinstance(data, list):
        raise ValueError("JSON replay input must be a list.")

    if all(isinstance(item, dict) and "messages" in item for item in data):
        blocks: list[ReplayBlock] = []
        for index, item in enumerate(data, 1):
            messages = _normalize_messages(item.get("messages", []))
            blocks.append(
                ReplayBlock(
                    index=index,
                    source_text=_source_text_from_messages(messages),
                    conversation=messages,
                    session_id=item.get("session_id"),
                )
            )
        return [block for block in blocks if block.source_text.strip()]

    messages = _normalize_messages(data)
    source_text = _source_text_from_messages(messages)
    return [ReplayBlock(index=1, source_text=source_text, conversation=messages)] if source_text else []


def parse_replay_file(path: Path | str) -> list[ReplayBlock]:
    replay_path = Path(path)
    suffix = replay_path.suffix.lower()
    if suffix == ".txt":
        text = replay_path.read_text(encoding="utf-8")
        blocks: list[ReplayBlock] = []
        for index, block in enumerate(parse_txt_blocks(text), 1):
            recorded_at, body = parse_block_header_datetime(block)
            content = body if body else block
            blocks.append(
                ReplayBlock(
                    index=index,
                    source_text=block,
                    conversation=[{"role": "user", "content": content}],
                    recorded_at=recorded_at,
                )
            )
        return blocks
    if suffix == ".json":
        data = json.loads(replay_path.read_text(encoding="utf-8"))
        return parse_json_blocks(data)
    raise ValueError("Replay input must be a .txt or .json file.")


def compute_replay_hash(source_file: Path | str, block: ReplayBlock) -> str:
    """Return a deterministic hash for duplicate detection."""
    payload = {
        "source_file": str(Path(source_file).as_posix()),
        "session_id": block.session_id,
        "source_text": block.source_text,
        "conversation": block.conversation,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def format_memory_preview(draft: dict[str, Any]) -> str:
    """Return structured JSON preview for interactive review."""
    preview = {
        "topic": draft.get("topic"),
        "event_summary": draft.get("event_summary"),
        "user_emotions": draft.get("user_emotions"),
        "emotion_evidence": draft.get("emotion_evidence"),
        "people": draft.get("people"),
        "projects": draft.get("projects"),
        "tags": draft.get("tags"),
        "memory_candidate": draft.get("memory_candidate"),
        "key_phrases": draft.get("key_phrases"),
        "emerging_themes": draft.get("emerging_themes"),
        "open_questions": draft.get("open_questions"),
        "reflection_value": draft.get("reflection_value"),
        "memory_type": draft.get("memory_type"),
        "interpretation_risk": draft.get("interpretation_risk"),
        "unsupported_inferences": draft.get("unsupported_inferences"),
    }
    return json.dumps(preview, ensure_ascii=False, indent=2)


def format_interactive_review_screen(block: ReplayBlock, draft: dict[str, Any]) -> str:
    """Format one block's interactive review prompt."""
    divider = "=" * 33
    section = "-" * 33
    return (
        f"{divider}\n\n"
        "원문\n\n"
        f"{block.source_text}\n\n"
        f"{section}\n\n"
        "요약\n\n"
        f"{draft.get('event_summary', '')}\n\n"
        f"{section}\n\n"
        "Memory Preview\n\n"
        f"{format_memory_preview(draft)}\n\n"
        f"{section}\n\n"
        "저장하시겠습니까?\n\n"
        "[y] 저장\n"
        "[n] 건너뛰기\n"
        "[e] 종료\n\n"
        ">"
    )


def prompt_review_choice(input_fn: Callable[[], str]) -> InteractiveReviewChoice:
    """Read and validate an interactive review choice."""
    while True:
        raw = input_fn().strip().lower()
        if raw in ("y", "yes"):
            return "save"
        if raw in ("n", "no"):
            return "skip"
        if raw in ("e", "exit"):
            return "exit"


def run_replay(
    source_file: Path | str,
    *,
    mode: ReplayMode = "dry-run",
    user_id: str = "dev-user",
    force: bool = False,
    memories_dir: Path | str = DEFAULT_MEMORIES_DIR,
    input_fn: Callable[[], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> ReplayRunResult:
    """Replay a file through dev_chat's session, draft, and save flow."""
    if mode not in ("dry-run", "interactive-review", "save-final"):
        raise ValueError(f"Unsupported replay mode: {mode}")

    db.init_db()
    source_path = Path(source_file)
    blocks = parse_replay_file(source_path)
    results: list[ReplayBlockResult] = []
    aborted = False

    for block in blocks:
        if aborted:
            break

        replay_hash = compute_replay_hash(source_path, block)
        result = ReplayBlockResult(index=block.index, replay_hash=replay_hash)

        if mode in ("save-final", "interactive-review") and not force and replay_hash_exists(
            replay_hash, memories_dir
        ):
            result.skipped = True
            result.messages.append("Duplicate replay_hash found; skipped.")
            results.append(result)
            continue

        try:
            user_data: dict[str, Any] = {}
            state = chat_service.IDLE

            begin = chat_service.dispatch_message(user_id, user_data, chat_service.BEGIN_KEYWORD, state=state)
            state = begin.state
            if state == states.RESUME_CHOICE:
                choice = chat_service.dispatch_message(user_id, user_data, chat_service.NEW_START_KEYWORD, state=state)
                state = choice.state

            for message in block.conversation:
                if message["role"] == "user":
                    turn = chat_service.dispatch_message(user_id, user_data, message["content"], state=state)
                    state = turn.state
                else:
                    current = session.ensure_session(user_data)
                    current["conversation"].append(message)

            summary = chat_service.dispatch_message(user_id, user_data, states.SUMMARY_TRIGGER, state=state)
            state = summary.state

            if state == states.FOLLOWUP:
                state = states.REVIEW

            draft = session.get_draft(user_data)
            if not draft:
                raise RuntimeError("Replay did not produce a draft.")

            _merge_replay_metadata(
                draft,
                source_path,
                block,
                replay_hash,
            )
            session.set_draft(user_data, draft)
            result.draft = draft
            result.validation = _validation_summary(draft)

            if mode == "interactive-review":
                _emit(format_interactive_review_screen(block, draft), output_fn)
                reader = input_fn or input
                while True:
                    choice = prompt_review_choice(reader)
                    if choice == "save":
                        save_result = chat_service.handle_review(
                            user_id, user_data, chat_service.SAVE_KEYWORD
                        )
                        result.messages.extend(save_result.messages)
                        result.saved = save_result.state == chat_service.IDLE
                        result.output_path = _extract_saved_path(save_result.messages)
                        break
                    if choice == "skip":
                        result.skipped = True
                        break
                    aborted = True
                    result.skipped = True
                    break
            elif mode == "save-final":
                save_result = chat_service.handle_review(user_id, user_data, chat_service.SAVE_KEYWORD)
                result.messages.extend(save_result.messages)
                result.saved = save_result.state == chat_service.IDLE
                result.output_path = _extract_saved_path(save_result.messages)

            results.append(result)
            if aborted:
                break
        except Exception as exc:
            result.error = str(exc)
            results.append(result)

    return ReplayRunResult(
        input_file=str(source_path),
        mode=mode,
        parsed_blocks=len(blocks),
        saved=mode != "dry-run",
        results=results,
        aborted=aborted,
    )


def replay_hash_exists(replay_hash: str, memories_dir: Path | str = DEFAULT_MEMORIES_DIR) -> bool:
    directory = Path(memories_dir)
    if not directory.exists():
        return False
    for filepath in directory.glob("*.json"):
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        metadata = data.get("metadata") or {}
        if metadata.get("replay_hash") == replay_hash:
            return True
    return False


def format_run_result(run: ReplayRunResult) -> str:
    lines = [
        f"input_file: {run.input_file}",
        f"mode: {run.mode}",
        f"parsed_blocks: {run.parsed_blocks}",
        f"processed_blocks: {len(run.results)}",
        f"actual_save_requested: {str(run.saved).lower()}",
    ]
    if run.mode == "interactive-review":
        lines.append(f"aborted: {str(run.aborted).lower()}")
        saved_count = sum(1 for result in run.results if result.saved)
        skipped_count = sum(1 for result in run.results if result.skipped and not result.saved)
        lines.append(f"saved_blocks: {saved_count}")
        lines.append(f"skipped_blocks: {skipped_count}")

    for result in run.results:
        lines.append("")
        lines.append(f"[block {result.index}]")
        lines.append(f"replay_hash: {result.replay_hash}")
        lines.append(f"saved: {str(result.saved).lower()}")
        lines.append(f"skipped: {str(result.skipped).lower()}")
        if result.output_path:
            lines.append(f"output_path: {result.output_path}")
        if result.error:
            lines.append(f"error: {result.error}")
        if result.draft:
            lines.append(f"draft_summary: {result.draft.get('event_summary', '')}")
            lines.append(f"validation: {json.dumps(result.validation, ensure_ascii=False)}")
            if run.mode == "dry-run":
                preview = json.dumps(result.draft, ensure_ascii=False, indent=2)
                lines.append("json_preview:")
                lines.append(preview)
    return "\n".join(lines)


def _emit(text: str, output_fn: Callable[[str], None] | None) -> None:
    if output_fn is not None:
        output_fn(text)
    else:
        print(text, flush=True)


def _normalize_messages(raw_messages: Any) -> list[dict[str, str]]:
    if not isinstance(raw_messages, list):
        raise ValueError("messages must be a list.")
    messages: list[dict[str, str]] = []
    for item in raw_messages:
        if not isinstance(item, dict):
            raise ValueError("Each message must be an object.")
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role not in ("user", "assistant"):
            raise ValueError("Message role must be 'user' or 'assistant'.")
        if content:
            messages.append({"role": role, "content": content})
    return messages


def _source_text_from_messages(messages: list[dict[str, str]]) -> str:
    return "\n".join(message["content"] for message in messages if message["role"] == "user").strip()


def _merge_replay_metadata(
    draft: dict[str, Any],
    source_file: Path,
    block: ReplayBlock,
    replay_hash: str,
) -> None:
    metadata = dict(draft.get("metadata") or {})
    metadata.update(
        {
            "source": "transcript_replay",
            "source_file": str(source_file),
            "replay_mode": True,
            "replay_hash": replay_hash,
            "source_text": block.source_text,
        }
    )
    if block.session_id:
        metadata["session_id"] = block.session_id
    if block.recorded_at:
        metadata["recorded_at"] = block.recorded_at.isoformat()
        draft["timestamp"] = block.recorded_at.isoformat()
    draft["metadata"] = metadata
    draft["conversation"] = list(block.conversation)
    validated = validate_draft(draft, block.source_text)
    draft.update(validated)


def _validation_summary(draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "interpretation_risk": draft.get("interpretation_risk", "low"),
        "unsupported_inferences": draft.get("unsupported_inferences", []),
        "valid": not draft.get("unsupported_inferences"),
    }


def _extract_saved_path(messages: list[str]) -> str | None:
    joined = "\n".join(messages)
    match = re.search(r"파일:\s*`?([^`\n]+)`?", joined)
    return match.group(1).strip() if match else None
