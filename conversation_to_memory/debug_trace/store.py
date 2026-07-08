"""Decision trace 저장소 추상화 및 팩토리."""

from __future__ import annotations

import logging
import os

from conversation_to_memory.debug_trace.models import DecisionTrace

logger = logging.getLogger(__name__)

STORE_FILE = "file"
STORE_SUPABASE = "supabase"
STORE_NOOP = "noop"

VALID_STORES = (STORE_FILE, STORE_SUPABASE, STORE_NOOP)

DEFAULT_STORE = STORE_FILE


class DecisionTraceStore:
    def save(self, trace: DecisionTrace) -> None:
        raise NotImplementedError


class NoopDecisionTraceStore(DecisionTraceStore):
    """trace 저장을 하지 않는 구현체 (DECISION_TRACE_ENABLED=false 등)."""

    def save(self, trace: DecisionTrace) -> None:
        return None


def is_trace_enabled() -> bool:
    return os.getenv("DECISION_TRACE_ENABLED", "true").lower() in ("true", "1", "yes")


def get_trace_environment() -> str:
    return os.getenv("DECISION_TRACE_ENVIRONMENT", "production").strip() or "production"


def get_store_backend() -> str:
    raw = os.getenv("DECISION_TRACE_STORE", DEFAULT_STORE).strip().lower()
    if raw not in VALID_STORES:
        logger.warning(
            "알 수 없는 DECISION_TRACE_STORE=%r — noop으로 대체합니다. (허용값: %s)",
            raw,
            ", ".join(VALID_STORES),
        )
        return STORE_NOOP
    return raw


def create_trace_store() -> DecisionTraceStore:
    """환경변수 기반으로 trace store를 생성."""
    if not is_trace_enabled():
        return NoopDecisionTraceStore()

    backend = get_store_backend()
    if backend == STORE_SUPABASE:
        from conversation_to_memory.debug_trace.supabase_store import (
            SupabaseDecisionTraceStore,
        )

        return SupabaseDecisionTraceStore()
    if backend == STORE_FILE:
        from conversation_to_memory.debug_trace.file_store import (
            FileDecisionTraceStore,
        )

        return FileDecisionTraceStore()
    return NoopDecisionTraceStore()


def save_trace_safely(
    trace: DecisionTrace,
    *,
    store: DecisionTraceStore | None = None,
) -> bool:
    """trace 저장. 어떤 실패도 호출 흐름(메모 저장·응답)을 막지 않는다.

    Returns:
        저장 성공 여부. 실패 시 warning 로그만 남기고 False를 반환한다.
    """
    try:
        (store or create_trace_store()).save(trace)
        return True
    except Exception:
        logger.warning("Decision trace 저장 실패 — 메모 저장 흐름은 계속 진행합니다.", exc_info=True)
        return False
