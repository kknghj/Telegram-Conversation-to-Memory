"""Supabase decision_traces 테이블 기반 trace 저장소."""

from __future__ import annotations

import os
from typing import Any

from conversation_to_memory.debug_trace.models import DecisionTrace
from conversation_to_memory.debug_trace.store import DecisionTraceStore

DEFAULT_TRACES_TABLE = "decision_traces"


class SupabaseDecisionTraceStoreError(Exception):
    """Raised when Supabase decision trace insert fails."""


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SupabaseDecisionTraceStoreError(f"환경변수 {name}가 설정되지 않았습니다.")
    return value


def get_traces_table_name() -> str:
    return (
        os.getenv("SUPABASE_DECISION_TRACES_TABLE", DEFAULT_TRACES_TABLE).strip()
        or DEFAULT_TRACES_TABLE
    )


class SupabaseDecisionTraceStore(DecisionTraceStore):
    """decision trace를 Supabase decision_traces 테이블에 저장."""

    def __init__(
        self,
        *,
        url: str | None = None,
        secret_key: str | None = None,
        table_name: str | None = None,
        client: Any | None = None,
    ):
        self.url = (url or os.getenv("SUPABASE_URL", "")).strip()
        self.secret_key = (secret_key or os.getenv("SUPABASE_SECRET_KEY", "")).strip()
        self.table_name = table_name or get_traces_table_name()
        self._client = client

    def _get_client(self):
        if self._client is not None:
            return self._client

        url = self.url or _require_env("SUPABASE_URL")
        secret_key = self.secret_key or _require_env("SUPABASE_SECRET_KEY")

        from supabase import create_client

        return create_client(url, secret_key)

    def save(self, trace: DecisionTrace) -> None:
        row = trace.to_row()
        try:
            self._get_client().table(self.table_name).insert(row).execute()
        except SupabaseDecisionTraceStoreError:
            raise
        except Exception as exc:
            raise SupabaseDecisionTraceStoreError(
                f"Supabase decision_traces insert failed: {exc}"
            ) from exc
