"""Failure-recording hooks for the conversation flow."""

from __future__ import annotations

from typing import Any

from conversation_to_memory import failure_recorder
from conversation_to_memory.bot import session


def conversation_id(user_data: dict[str, Any]) -> str:
    draft_id = user_data.get(session.KEY_PERSISTED_DRAFT_ID)
    if draft_id:
        return str(draft_id)
    current = session.get_session(user_data)
    if current and current.get("user_texts"):
        return f"session-{hash(tuple(current['user_texts'])) & 0xFFFFFFFF:08x}"
    return ""


def maybe_prepare_correction_failure(
    user_data: dict[str, Any],
    text: str,
) -> None:
    current = session.get_session(user_data)
    conversation = current.get("conversation", []) if current else []
    draft = session.get_draft(user_data)
    pending = failure_recorder.try_prepare_correction_failure(
        user_correction=text,
        conversation=conversation,
        draft=draft,
        conversation_id=conversation_id(user_data),
    )
    if pending:
        user_data[session.KEY_PENDING_FAILURE] = pending


def maybe_record_question_rejection_failure(
    user_data: dict[str, Any],
    text: str,
) -> None:
    current = session.get_session(user_data)
    conversation = current.get("conversation", []) if current else []
    pending = failure_recorder.try_prepare_question_rejection_failure(
        user_correction=text,
        conversation=conversation,
        conversation_id=conversation_id(user_data),
    )
    if pending:
        failure_recorder.finalize_question_rejection_failure(pending)


def finalize_pending_failure(user_data: dict[str, Any], assistant_output: str) -> None:
    pending = user_data.pop(session.KEY_PENDING_FAILURE, None)
    if pending:
        failure_recorder.finalize_pending_failure(pending, assistant_output)


def record_followup_violation(
    user_data: dict[str, Any],
    *,
    user_text: str,
    followup_question: str,
) -> None:
    current = session.get_session(user_data)
    conversation = current.get("conversation", []) if current else []
    failure_recorder.record_repeated_question_failure(
        user_text=user_text,
        followup_question=followup_question,
        conversation=conversation,
        conversation_id=conversation_id(user_data),
    )


def record_korean_misparse(
    user_data: dict[str, Any],
    *,
    user_text: str,
    draft: dict[str, Any],
    assistant_output: str,
) -> None:
    current = session.get_session(user_data)
    conversation = current.get("conversation", []) if current else []
    failure_recorder.record_korean_misparse_failure(
        user_text=user_text,
        assistant_output=assistant_output,
        conversation=conversation,
        draft=draft,
        conversation_id=conversation_id(user_data),
    )
