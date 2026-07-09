"""Platform-agnostic conversation flow for memory archive bot."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app import database as db
from conversation_to_memory.bot import (
    failure_hooks,
    question_flow,
    save_service,
    session,
    states,
)
from conversation_to_memory.debug_trace import recorder as trace_recorder
from conversation_to_memory.debug_trace.store import save_trace_safely
from conversation_to_memory.memory import question as question_service
from conversation_to_memory.memory import service as memory_service

logger = logging.getLogger(__name__)

SAVE_KEYWORD = "저장"
CANCEL_KEYWORD = "취소"
EDIT_KEYWORD = "수정"
NEW_RECORD_KEYWORD = "새 기록"
RESUME_KEYWORD = "이어서"
NEW_START_KEYWORD = "새로"
BEGIN_KEYWORD = "기록 시작"

IDLE = -1

EDIT_ENTRY_PATTERN = re.compile("^(수정|이전 기록 수정|취소한 기록 수정)$")
BEGIN_PATTERN = re.compile("^기록\\s*시작$")


@dataclass
class ChatTurnResult:
    messages: list[str] = field(default_factory=list)
    state: int = IDLE
    parse_mode: str | None = None


def _recording_prompt() -> str:
    followup_note = (
        "필요하면 짧은 후속 질문이 이어질 수 있습니다."
        if question_service.is_reflection_agent_enabled()
        else "필요 시 정확도 확인 질문 1개가 있을 수 있습니다."
    )
    return (
        "있는 그대로 기록해 주세요. 오늘 있었던 일, 감정, 생각을 자유롭게 적어주세요.\n"
        f"다 적으셨으면 「요약」이라고 입력하세요.\n"
        f"({followup_note} 상담·조언·성장 서사가 아닌, 원문 기반 정리만 합니다.)"
    )


def _ensure_cancelled_draft_loaded(user_id: str, user_data: dict[str, Any]) -> bool:
    if session.has_cancelled_draft(user_data):
        return True

    persisted = db.get_latest_cancelled_draft(user_id)
    if persisted:
        session.load_cancelled_draft_from_db(user_data, persisted)
        return True
    return False


def _persist_cancelled_draft(
    user_id: str,
    user_data: dict[str, Any],
    *,
    reason: str = "",
) -> None:
    current = session.get_session(user_data)
    draft = session.get_draft(user_data)
    if draft is None:
        session.cancel_current_draft(user_data, reason=reason)
        return

    user_texts = current.get("user_texts", []) if current else []
    conversation = current.get("conversation", []) if current else []

    cancellation_reason = reason
    if not cancellation_reason and current:
        texts = current.get("user_texts", [])
        if texts:
            cancellation_reason = texts[-1]

    draft_id = db.save_cancelled_draft(
        user_id,
        draft=draft,
        user_texts=user_texts,
        conversation=conversation,
        cancellation_reason=cancellation_reason,
    )

    session.cancel_current_draft(user_data, reason=cancellation_reason)
    user_data[session.KEY_PERSISTED_DRAFT_ID] = draft_id


def _review_message(draft: dict[str, Any]) -> str:
    return memory_service.format_review_message(draft)


def _record_analysis_failure_trace(
    user_data: dict[str, Any],
    current: dict[str, Any] | None,
    exc: Exception,
) -> None:
    """요약 분석 자체가 실패하면 즉시 trace를 남긴다 (메모가 저장되지 않는 케이스)."""
    error = "json_parse_failed" if isinstance(exc, json.JSONDecodeError) else "llm_call_failed"
    user_texts = current.get("user_texts", []) if current else []
    trace = trace_recorder.build_trace(
        user_data=user_data,
        question_trace={
            "evaluated": False,
            "need_followup": None,
            "reason": "analysis_failed",
            "llm_called": False,
            "generated": False,
            "sent": False,
        },
        project_trace={
            "evaluated": False,
            "detected": False,
            "reason": "analysis_failed",
        },
        raw_input_preview="\n".join(user_texts),
        error=error,
    )
    save_trace_safely(trace)


def _maybe_followup_or_review(
    user_id: str,
    user_data: dict[str, Any],
    draft: dict[str, Any],
) -> ChatTurnResult:
    result = question_flow.maybe_followup_or_review(
        user_id,
        user_data,
        draft,
        review_message=_review_message,
    )
    return ChatTurnResult(messages=result.messages, state=result.state)


def handle_start(user_data: dict[str, Any]) -> ChatTurnResult:
    session.reset_recording_session(user_data)
    return ChatTurnResult(
        messages=[
            "안녕하세요. 기억 아카이브 봇입니다.\n\n"
            "상담봇이나 자기계발 일기봇이 아니라, 말한 내용을 있는 그대로 정리·보관합니다.\n\n"
            f"기록을 시작하려면 「{BEGIN_KEYWORD}」을 입력하세요.\n"
            "자유롭게 기록 → (필요 시 질문) → 요약 확인 → 「저장」"
        ],
        state=IDLE,
    )


def handle_begin_recording(user_id: str, user_data: dict[str, Any], text: str) -> ChatTurnResult:
    has_recent = db.has_recent_cancelled_draft(user_id)
    if has_recent:
        _ensure_cancelled_draft_loaded(user_id, user_data)

    if session.has_cancelled_draft(user_data) or has_recent:
        if session.relates_to_cancellation(text, user_data):
            draft = session.restore_cancelled_to_current(user_data)
            if draft:
                return ChatTurnResult(
                    messages=[
                        "이전에 취소한 기록 맥락을 참고합니다.\n\n" + _review_message(draft)
                    ],
                    state=states.REVIEW,
                )

        return ChatTurnResult(messages=[session.RESUME_CHOICE_MESSAGE], state=states.RESUME_CHOICE)

    session.reset_recording_session(user_data)
    session.ensure_session(user_data)
    db.save_active_draft(user_id, user_texts=[], conversation=[])
    return ChatTurnResult(messages=[_recording_prompt()], state=states.RECORDING)


def handle_resume_choice(
    user_id: str,
    user_data: dict[str, Any],
    text: str,
) -> ChatTurnResult:
    if text in ("1", RESUME_KEYWORD, EDIT_KEYWORD):
        if not _ensure_cancelled_draft_loaded(user_id, user_data):
            return ChatTurnResult(messages=[session.NO_DRAFT_TO_EDIT_MESSAGE], state=IDLE)

        draft = session.restore_cancelled_to_current(user_data)
        if not draft:
            return ChatTurnResult(messages=[session.NO_DRAFT_TO_EDIT_MESSAGE], state=IDLE)

        return ChatTurnResult(
            messages=["이전 초안을 불러왔습니다.\n\n" + _review_message(draft)],
            state=states.REVIEW,
        )

    if text in ("2", NEW_START_KEYWORD, NEW_RECORD_KEYWORD):
        session.clear_cancelled_draft(user_data)
        session.reset_recording_session(user_data)
        session.ensure_session(user_data)
        db.save_active_draft(user_id, user_texts=[], conversation=[])
        return ChatTurnResult(
            messages=["새 기록을 시작합니다.\n\n" + _recording_prompt()],
            state=states.RECORDING,
        )

    if session.relates_to_cancellation(text, user_data):
        current = session.ensure_session(user_data)
        current["user_texts"].append(text)
        current["conversation"].append({"role": "user", "content": text})

        try:
            draft = memory_service.analyze_recording(
                user_texts=current["user_texts"],
                conversation=current["conversation"],
                recent_context=session.get_recent_context(user_data),
                cancelled_draft=session.get_cancelled_draft(user_data),
                cancellation_reason=user_data.get(session.KEY_CANCELLATION_REASON, ""),
            )
            session.clear_cancelled_draft(user_data)
            session.set_draft(user_data, draft)
            return _maybe_followup_or_review(user_id, user_data, draft)
        except Exception as e:
            logger.exception("취소 맥락 기록 처리 오류")
            session.reset_recording_session(user_data)
            return ChatTurnResult(
                messages=[f"오류: {e}\n「{BEGIN_KEYWORD}」으로 다시 시도하세요."],
                state=IDLE,
            )

    return ChatTurnResult(
        messages=[
            f"「1」 또는 「2」, 또는 「{RESUME_KEYWORD}」 / 「{NEW_START_KEYWORD}」를 입력해주세요."
        ],
        state=states.RESUME_CHOICE,
    )


def handle_recording(
    user_id: str,
    user_data: dict[str, Any],
    text: str,
) -> ChatTurnResult:
    current = session.ensure_session(user_data)

    if text != states.SUMMARY_TRIGGER:
        current["user_texts"].append(text)
        current["conversation"].append({"role": "user", "content": text})
        db.save_active_draft(
            user_id,
            user_texts=current["user_texts"],
            conversation=current["conversation"],
        )
        return ChatTurnResult(
            messages=["기록했습니다. 더 적으시거나, 다 적으셨으면 「요약」을 입력하세요."],
            state=states.RECORDING,
        )

    if not current["user_texts"]:
        return ChatTurnResult(
            messages=["먼저 기록 내용을 입력해주세요."],
            state=states.RECORDING,
        )

    try:
        draft = memory_service.analyze_recording(
            user_texts=current["user_texts"],
            conversation=current["conversation"],
            recent_context=session.get_recent_context(user_data),
            cancelled_draft=session.get_cancelled_draft(user_data),
            cancellation_reason=user_data.get(session.KEY_CANCELLATION_REASON, ""),
        )
        session.set_draft(user_data, draft)
        failure_hooks.record_korean_misparse(
            user_data,
            user_text="\n".join(current["user_texts"]),
            draft=draft,
            assistant_output=_review_message(draft),
        )
        db.save_active_draft(
            user_id,
            user_texts=current["user_texts"],
            conversation=current["conversation"],
            draft=draft,
        )
        return _maybe_followup_or_review(user_id, user_data, draft)
    except Exception as e:
        logger.exception("기록 분석 오류")
        _record_analysis_failure_trace(user_data, current, e)
        return ChatTurnResult(
            messages=[f"분석 중 오류: {e}\n다시 「요약」을 시도하거나 내용을 추가해주세요."],
            state=states.RECORDING,
        )


def handle_followup(
    user_id: str,
    user_data: dict[str, Any],
    text: str,
) -> ChatTurnResult:
    failure_hooks.maybe_record_question_rejection_failure(user_data, text)
    failure_hooks.maybe_prepare_correction_failure(user_data, text)
    current = session.ensure_session(user_data)
    current["user_texts"].append(text)
    current["conversation"].append({"role": "user", "content": text})

    try:
        draft = memory_service.analyze_recording(
            user_texts=current["user_texts"],
            conversation=current["conversation"],
            recent_context=session.get_recent_context(user_data),
            followup_already_asked=True,
        )
        session.set_draft(user_data, draft)
        failure_hooks.finalize_pending_failure(user_data, _review_message(draft))
        db.save_active_draft(
            user_id,
            user_texts=current["user_texts"],
            conversation=current["conversation"],
            draft=draft,
        )
        if question_service.is_reflection_agent_enabled():
            return _maybe_followup_or_review(user_id, user_data, draft)
        return ChatTurnResult(messages=[_review_message(draft)], state=states.REVIEW)
    except Exception as e:
        logger.exception("후속 답변 처리 오류")
        return ChatTurnResult(messages=[f"오류: {e}"], state=states.FOLLOWUP)


def handle_review(
    user_id: str,
    user_data: dict[str, Any],
    text: str,
) -> ChatTurnResult:
    if text == SAVE_KEYWORD:
        return _save_draft(user_id, user_data)

    if text == CANCEL_KEYWORD:
        _persist_cancelled_draft(user_id, user_data)
        return ChatTurnResult(messages=[session.CANCEL_MESSAGE], state=IDLE)

    if text == EDIT_KEYWORD or text.startswith(EDIT_KEYWORD):
        edit_instruction = text[len(EDIT_KEYWORD) :].strip()
        if not edit_instruction:
            return ChatTurnResult(
                messages=[
                    "어떤 부분을 고치고 싶은지 함께 적어주세요.\n"
                    "예: 「수정 지나치게 긍정적으로 왜곡하지 말고 있는 그대로 받아들여줘」"
                ],
                state=states.EDIT,
            )
        return _apply_edit(user_id, user_data, edit_instruction)

    return ChatTurnResult(
        messages=[
            f"「{SAVE_KEYWORD}」, 「{EDIT_KEYWORD}」, 「{CANCEL_KEYWORD}」 중 하나를 입력해주세요."
        ],
        state=states.REVIEW,
    )


def handle_edit(
    user_id: str,
    user_data: dict[str, Any],
    text: str,
) -> ChatTurnResult:
    return _apply_edit(user_id, user_data, text.strip())


def _apply_edit(
    user_id: str,
    user_data: dict[str, Any],
    edit_instruction: str,
) -> ChatTurnResult:
    failure_hooks.maybe_prepare_correction_failure(user_data, edit_instruction)
    current = session.get_session(user_data)
    draft = session.get_draft(user_data)

    if not current or not draft:
        if not _ensure_cancelled_draft_loaded(user_id, user_data):
            return ChatTurnResult(messages=[session.NO_DRAFT_TO_EDIT_MESSAGE], state=IDLE)
        cancelled = session.get_cancelled_draft(user_data)
        if cancelled:
            session.restore_cancelled_to_current(user_data)
            current = session.ensure_session(user_data)
            draft = session.get_draft(user_data)
        else:
            return ChatTurnResult(messages=[session.NO_DRAFT_TO_EDIT_MESSAGE], state=IDLE)

    try:
        revised = memory_service.analyze_recording(
            user_texts=current["user_texts"],
            conversation=current["conversation"],
            recent_context=session.get_recent_context(user_data),
            edit_instruction=edit_instruction,
            previous_draft=draft,
            followup_already_asked=True,
        )
        session.set_draft(user_data, revised)
        failure_hooks.finalize_pending_failure(user_data, _review_message(revised))
        return ChatTurnResult(messages=[_review_message(revised)], state=states.REVIEW)
    except Exception as e:
        logger.exception("수정 처리 오류")
        return ChatTurnResult(messages=[f"수정 중 오류: {e}"], state=states.REVIEW)


def _save_draft(user_id: str, user_data: dict[str, Any]) -> ChatTurnResult:
    pending = session.get_draft(user_data)

    if not pending:
        return ChatTurnResult(
            messages=[f"저장할 기억이 없습니다. 「{BEGIN_KEYWORD}」으로 새로 시작하세요."],
            state=IDLE,
        )

    result = save_service.save_current_draft(user_id, user_data)
    if result.saved:
        return ChatTurnResult(
            messages=[
                f"✅ 기억이 저장되었습니다.\n\n파일: `{result.storage_ref}`"
                f"{result.draft_status_warning}\n\n"
                f"다시 기록하려면 「{BEGIN_KEYWORD}」을 입력하세요."
            ],
            state=IDLE,
            parse_mode="Markdown",
        )
    return ChatTurnResult(messages=[f"저장 실패: {result.error}"], state=states.REVIEW)


def handle_edit_cancelled_draft(user_id: str, user_data: dict[str, Any]) -> ChatTurnResult:
    if not _ensure_cancelled_draft_loaded(user_id, user_data):
        return ChatTurnResult(messages=[session.NO_DRAFT_TO_EDIT_MESSAGE], state=IDLE)

    draft = session.restore_cancelled_to_current(user_data)
    if not draft:
        return ChatTurnResult(messages=[session.NO_DRAFT_TO_EDIT_MESSAGE], state=IDLE)

    return ChatTurnResult(
        messages=["취소했던 초안을 불러왔습니다.\n\n" + _review_message(draft)],
        state=states.REVIEW,
    )


def handle_route_message(user_id: str, user_data: dict[str, Any], text: str) -> ChatTurnResult:
    if session.is_edit_command(text):
        if _ensure_cancelled_draft_loaded(user_id, user_data):
            draft = session.restore_cancelled_to_current(user_data)
            session.ensure_session(user_data)
            return ChatTurnResult(
                messages=[
                    "취소했던 초안을 불러왔습니다.\n\n" + _review_message(draft)
                ],
                state=states.REVIEW,
            )
        return ChatTurnResult(messages=[session.NO_DRAFT_TO_EDIT_MESSAGE], state=IDLE)

    if text == NEW_RECORD_KEYWORD:
        session.clear_cancelled_draft(user_data)
        session.reset_recording_session(user_data)
        return ChatTurnResult(
            messages=[f"새 기록을 시작합니다. 「{BEGIN_KEYWORD}」을 입력해주세요."],
            state=IDLE,
        )

    if text == BEGIN_KEYWORD:
        return ChatTurnResult(state=IDLE)

    return ChatTurnResult(
        messages=[
            f"기록을 시작하려면 「{BEGIN_KEYWORD}」을 입력하세요.\n"
            "도움말은 /start"
        ],
        state=IDLE,
    )


def handle_cancel(user_id: str, user_data: dict[str, Any]) -> ChatTurnResult:
    draft = session.get_draft(user_data)
    if draft:
        _persist_cancelled_draft(user_id, user_data)
        return ChatTurnResult(messages=[session.CANCEL_MESSAGE], state=IDLE)

    session.reset_recording_session(user_data)
    return ChatTurnResult(messages=["진행 중인 기록을 취소했습니다."], state=IDLE)


def dispatch_message(
    user_id: str,
    user_data: dict[str, Any],
    text: str,
    *,
    state: int = IDLE,
) -> ChatTurnResult:
    """Route one user message through the conversation flow."""
    stripped = text.strip()

    if stripped in ("/start", "/help"):
        return handle_start(user_data)

    if stripped in ("/cancel", "/quit", "/exit"):
        return handle_cancel(user_id, user_data)

    if state == IDLE:
        if BEGIN_PATTERN.match(stripped):
            return handle_begin_recording(user_id, user_data, stripped)
        if EDIT_ENTRY_PATTERN.match(stripped):
            return handle_edit_cancelled_draft(user_id, user_data)
        return handle_route_message(user_id, user_data, stripped)

    if state == states.RESUME_CHOICE:
        return handle_resume_choice(user_id, user_data, stripped)

    if state == states.RECORDING:
        return handle_recording(user_id, user_data, stripped)

    if state == states.FOLLOWUP:
        return handle_followup(user_id, user_data, stripped)

    if state == states.REVIEW:
        return handle_review(user_id, user_data, stripped)

    if state == states.EDIT:
        return handle_edit(user_id, user_data, stripped)

    return handle_route_message(user_id, user_data, stripped)
