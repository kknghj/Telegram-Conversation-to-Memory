"""파이프라인 진행 중 trace 조각을 모아 최종 DecisionTrace로 조립."""

from __future__ import annotations

import os
from typing import Any

from conversation_to_memory.debug_trace.models import (
    RAW_INPUT_PREVIEW_MAX_LENGTH,
    DecisionTrace,
)
from conversation_to_memory.debug_trace.store import get_trace_environment

KEY_PENDING_TRACE = "decision_trace_pending"


def _pending(user_data: dict[str, Any]) -> dict[str, Any]:
    return user_data.setdefault(KEY_PENDING_TRACE, {})


def record_question_trace(
    user_data: dict[str, Any],
    question_trace: dict[str, Any],
) -> None:
    """후속 질문 판단 결과를 세션에 보관 (저장 시점에 확정)."""
    _pending(user_data)["question_trace"] = dict(question_trace)


def get_question_trace(user_data: dict[str, Any]) -> dict[str, Any] | None:
    pending = user_data.get(KEY_PENDING_TRACE) or {}
    return pending.get("question_trace")


def mark_question_sent(user_data: dict[str, Any]) -> None:
    trace = get_question_trace(user_data)
    if trace is not None:
        trace["sent"] = True


def clear_pending(user_data: dict[str, Any]) -> None:
    user_data.pop(KEY_PENDING_TRACE, None)


def build_trace(
    *,
    user_data: dict[str, Any] | None = None,
    memory_id: str | None = None,
    question_trace: dict[str, Any] | None = None,
    project_trace: dict[str, Any] | None = None,
    tag_trace: dict[str, Any] | None = None,
    raw_input_preview: str | None = None,
    error: str | None = None,
) -> DecisionTrace:
    """세션에 쌓인 조각 + 저장 시점 정보로 DecisionTrace를 조립."""
    if question_trace is None and user_data is not None:
        question_trace = get_question_trace(user_data)

    preview = (raw_input_preview or "").strip()
    if len(preview) > RAW_INPUT_PREVIEW_MAX_LENGTH:
        preview = preview[:RAW_INPUT_PREVIEW_MAX_LENGTH]

    return DecisionTrace(
        memory_id=memory_id,
        environment=get_trace_environment(),
        prompt_version=os.getenv("PROMPT_VERSION") or None,
        model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
        question_trace=question_trace,
        project_trace=project_trace,
        tag_trace=tag_trace,
        raw_input_preview=preview or None,
        error=error,
    )
