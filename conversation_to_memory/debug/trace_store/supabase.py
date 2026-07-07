"""Supabase storage for decision traces (future implementation)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from conversation_to_memory.debug.trace_store.base import TraceStore


class SupabaseTraceStore(TraceStore):
    """Supabase-backed decision trace store.

    Implement ``save`` when trace persistence to Supabase is required.
    Factory wiring is already in place via ``TRACE_STORAGE_BACKEND=supabase``.
    """

    def save(
        self,
        trace: dict[str, Any],
        *,
        timestamp: datetime | None = None,
        telegram_user_id: str | None = None,
    ) -> str:
        raise NotImplementedError(
            "SupabaseTraceStore is not implemented yet. "
            "Use TRACE_STORAGE_BACKEND=file for local development."
        )
