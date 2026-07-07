"""Final memory persistence for the conversation flow."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app import database as db
from conversation_to_memory.bot import session
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


def save_current_draft(
    user_id: str,
    user_data: dict[str, Any],
    *,
    storage: MemoryStorage | None = None,
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

    trace_collector = session.get_decision_trace(user_data)
    if trace_collector is not None:
        trace_path = trace_collector.save(timestamp=datetime.now())
        full_memory["debug_trace_path"] = trace_path

    try:
        storage_ref = (storage or archive_storage).save(
            full_memory,
            telegram_user_id=user_id,
        )
    except Exception as exc:
        logger.exception("저장 오류")
        return SaveDraftResult(saved=False, error=exc)

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
