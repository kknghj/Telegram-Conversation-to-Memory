"""Final memory persistence for the conversation flow."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app import database as db
from conversation_to_memory.bot import session
from conversation_to_memory.debug_trace import recorder as trace_recorder
from conversation_to_memory.debug_trace.store import (
    DecisionTraceStore,
    save_trace_safely,
)
from conversation_to_memory.memory import fidelity
from conversation_to_memory.storage.base import MemoryStorage
from conversation_to_memory.storage.factory import create_storage

logger = logging.getLogger(__name__)

archive_storage = create_storage()


@dataclass
class SaveDraftResult:
    saved: bool
    storage_ref: str = ""
    draft_status_warning: str = ""
    error: Exception | None = None


def _persist_decision_trace(
    user_data: dict[str, Any],
    *,
    memory_id: str | None,
    full_memory: dict[str, Any],
    source_text: str,
    saved: bool,
    save_error: Exception | None = None,
    trace_store: DecisionTraceStore | None = None,
) -> None:
    """저장 시점에 decision trace를 확정해 저장. 실패해도 메모 저장 흐름을 막지 않는다."""
    try:
        project_trace = fidelity.build_project_trace(full_memory, source_text)
        has_projects = bool(full_memory.get("projects"))
        if not saved:
            project_trace["tag_written"] = False
            if has_projects:
                project_trace["reason"] = "tag_save_failed"
        else:
            project_trace["tag_written"] = has_projects

        tag_trace = {
            "tags": list(full_memory.get("tags") or []),
            "value_tags": list(full_memory.get("value_tags") or []),
            "written": saved,
        }
        if not saved:
            tag_trace["reason"] = "tag_save_failed"

        trace = trace_recorder.build_trace(
            user_data=user_data,
            memory_id=memory_id,
            project_trace=project_trace,
            tag_trace=tag_trace,
            raw_input_preview=source_text,
            error=f"memory_save_failed: {save_error}" if save_error else None,
        )
        save_trace_safely(trace, store=trace_store)
    except Exception:
        logger.warning("Decision trace 조립 실패 — 메모 저장 흐름은 계속 진행합니다.", exc_info=True)


def save_current_draft(
    user_id: str,
    user_data: dict[str, Any],
    *,
    storage: MemoryStorage | None = None,
    trace_store: DecisionTraceStore | None = None,
) -> SaveDraftResult:
    pending = session.get_draft(user_data)
    current = session.get_session(user_data)

    if not pending:
        return SaveDraftResult(saved=False)

    full_memory = {
        **pending,
        "conversation": current.get("conversation", []) if current else [],
        "approved": True,
    }
    source_text = "\n".join(current.get("user_texts", [])) if current else ""

    try:
        storage_ref = (storage or archive_storage).save(
            full_memory,
            telegram_user_id=user_id,
        )
    except Exception as exc:
        logger.exception("저장 오류")
        _persist_decision_trace(
            user_data,
            memory_id=None,
            full_memory=full_memory,
            source_text=source_text,
            saved=False,
            save_error=exc,
            trace_store=trace_store,
        )
        return SaveDraftResult(saved=False, error=exc)

    _persist_decision_trace(
        user_data,
        memory_id=storage_ref,
        full_memory=full_memory,
        source_text=source_text,
        saved=True,
        trace_store=trace_store,
    )

    draft_status_warning = ""
    draft_id = user_data.get(session.KEY_PERSISTED_DRAFT_ID)
    try:
        db.mark_draft_saved(
            draft_id,
            user_id,
            draft=pending,
            user_texts=current.get("user_texts", []) if current else [],
            conversation=current.get("conversation", []) if current else [],
        )
    except Exception:
        logger.exception("최종 기억 저장 후 초안 상태 업데이트 실패")
        draft_status_warning = (
            "\n\n최종 기억은 저장되었지만 임시 초안 상태 업데이트에 실패했습니다. "
            "같은 초안이 다시 보이면 새 기록으로 시작해주세요."
        )

    session.reset_all(user_data)
    return SaveDraftResult(
        saved=True,
        storage_ref=storage_ref,
        draft_status_warning=draft_status_warning,
    )
