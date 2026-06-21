"""Transcript replay adapter for the existing dev chat flow."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from app import database as db
from conversation_to_memory.bot import chat_service, session, states
from conversation_to_memory.memory.fidelity import validate_draft
from conversation_to_memory.storage.local_json import DEFAULT_MEMORIES_DIR

ReplayMode = Literal["dry-run", "save-draft", "save-final"]
FollowupMode = Literal["none", "generate-only"]

DEFAULT_DRAFT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "replay_outputs" / "drafts"


@dataclass
class ReplayBlock:
    """One replayable recording unit."""

    index: int
    source_text: str
    conversation: list[dict[str, str]]
    session_id: str | None = None


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


def parse_txt_blocks(text: str) -> list[str]:
    """Split bulk memo text on --- or === lines and drop empty blocks."""
    chunks = re.split(r"(?m)^\s*(?:---|===)\s*$", text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


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
        return [
            ReplayBlock(
                index=index,
                source_text=block,
                conversation=[{"role": "user", "content": block}],
            )
            for index, block in enumerate(parse_txt_blocks(text), 1)
        ]
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


def run_replay(
    source_file: Path | str,
    *,
    mode: ReplayMode = "dry-run",
    user_id: str = "dev-user",
    force: bool = False,
    followup_mode: FollowupMode = "none",
    draft_output_dir: Path | str = DEFAULT_DRAFT_OUTPUT_DIR,
    memories_dir: Path | str = DEFAULT_MEMORIES_DIR,
) -> ReplayRunResult:
    """Replay a file through dev_chat's session, draft, and save flow."""
    if mode not in ("dry-run", "save-draft", "save-final"):
        raise ValueError(f"Unsupported replay mode: {mode}")
    if followup_mode not in ("none", "generate-only"):
        raise ValueError(f"Unsupported followup mode: {followup_mode}")

    db.init_db()
    source_path = Path(source_file)
    blocks = parse_replay_file(source_path)
    results: list[ReplayBlockResult] = []

    for block in blocks:
        replay_hash = compute_replay_hash(source_path, block)
        result = ReplayBlockResult(index=block.index, replay_hash=replay_hash)

        if mode == "save-final" and not force and replay_hash_exists(replay_hash, memories_dir):
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
                draft = session.get_draft(user_data) or {}
                if followup_mode == "generate-only":
                    _merge_replay_metadata(
                        draft,
                        source_path,
                        block,
                        replay_hash,
                        include_suggested_followup=True,
                    )
                    result.messages.extend(summary.messages)
                state = states.REVIEW

            draft = session.get_draft(user_data)
            if not draft:
                raise RuntimeError("Replay did not produce a draft.")

            _merge_replay_metadata(
                draft,
                source_path,
                block,
                replay_hash,
                include_suggested_followup=followup_mode == "generate-only",
            )
            session.set_draft(user_data, draft)
            result.draft = draft
            result.validation = _validation_summary(draft)

            if mode == "save-draft":
                result.output_path = save_replay_draft(draft, block, draft_output_dir)
                result.saved = True
            elif mode == "save-final":
                save_result = chat_service.handle_review(user_id, user_data, chat_service.SAVE_KEYWORD)
                result.messages.extend(save_result.messages)
                result.saved = save_result.state == chat_service.IDLE
                result.output_path = _extract_saved_path(save_result.messages)

            results.append(result)
        except Exception as exc:
            result.error = str(exc)
            results.append(result)

    return ReplayRunResult(
        input_file=str(source_path),
        mode=mode,
        parsed_blocks=len(blocks),
        saved=mode != "dry-run",
        results=results,
    )


def save_replay_draft(
    draft: dict[str, Any],
    block: ReplayBlock,
    output_dir: Path | str = DEFAULT_DRAFT_OUTPUT_DIR,
) -> str:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    date_prefix = _date_prefix(block.source_text)
    filename = f"{date_prefix}_{block.index:03d}_draft.json"
    filepath = output_path / filename
    payload = {
        "created_at": datetime.now().isoformat(),
        "status": "draft",
        **draft,
        "approved": False,
    }
    filepath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(filepath)


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
        f"actual_save_requested: {str(run.saved).lower()}",
    ]
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
            preview = json.dumps(result.draft, ensure_ascii=False, indent=2)
            lines.append("json_preview:")
            lines.append(preview)
    return "\n".join(lines)


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
    *,
    include_suggested_followup: bool = False,
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
    if include_suggested_followup and draft.get("followup_question"):
        metadata["suggested_followup_questions"] = [draft["followup_question"]]
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


def _date_prefix(source_text: str) -> str:
    match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", source_text)
    return match.group(1) if match else datetime.now().strftime("%Y-%m-%d")


def _extract_saved_path(messages: list[str]) -> str | None:
    joined = "\n".join(messages)
    match = re.search(r"파일:\s*`?([^`\n]+)`?", joined)
    return match.group(1).strip() if match else None
