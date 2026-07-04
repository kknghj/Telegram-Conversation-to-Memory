"""Supabase storage for approved memories."""

from __future__ import annotations

import os
from typing import Any

from conversation_to_memory.reflection.schema import CURRENT_SCHEMA_VERSION
from conversation_to_memory.storage.base import MemoryStorage

DEFAULT_MEMORIES_TABLE = "memories"


class SupabaseStorageError(Exception):
    """Raised when Supabase memory insert fails."""


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SupabaseStorageError(f"환경변수 {name}가 설정되지 않았습니다.")
    return value


def get_memories_table_name() -> str:
    return os.getenv("SUPABASE_MEMORIES_TABLE", DEFAULT_MEMORIES_TABLE).strip() or DEFAULT_MEMORIES_TABLE


def _build_row(memory: dict, *, telegram_user_id: str | None = None) -> dict[str, Any]:
    """memory dict → Supabase memories 테이블 row."""
    return {
        "source": "telegram",
        "telegram_user_id": telegram_user_id,
        "timestamp": memory.get("timestamp"),
        "topic": memory.get("topic"),
        "event_summary": memory.get("event_summary"),
        "user_emotions": memory.get("user_emotions", []),
        "emotion_evidence": memory.get("emotion_evidence", []),
        "people": memory.get("people", []),
        "projects": memory.get("projects", []),
        "tags": memory.get("tags", []),
        "memory_candidate": memory.get("memory_candidate"),
        "interpretation_risk": memory.get("interpretation_risk"),
        "unsupported_inferences": memory.get("unsupported_inferences", []),
        "needs_followup": memory.get("needs_followup"),
        "followup_question": memory.get("followup_question"),
        "conversation": memory.get("conversation", []),
        "approved": memory.get("approved", True),
        "schema_version": memory.get("schema_version", CURRENT_SCHEMA_VERSION),
        "raw_memory": memory,
    }


def verify_connection() -> None:
    """Verify Supabase credentials and table reachability at startup."""
    storage = SupabaseStorage()
    try:
        storage._get_client().table(storage.table_name).select("id").limit(1).execute()
    except SupabaseStorageError:
        raise
    except Exception as exc:
        raise SupabaseStorageError(f"Supabase connection check failed: {exc}") from exc


class SupabaseStorage(MemoryStorage):
    """승인된 기억을 Supabase memories 테이블에 저장."""

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
        self.table_name = table_name or get_memories_table_name()
        self._client = client

    def _get_client(self):
        if self._client is not None:
            return self._client

        url = self.url or _require_env("SUPABASE_URL")
        secret_key = self.secret_key or _require_env("SUPABASE_SECRET_KEY")

        from supabase import create_client

        return create_client(url, secret_key)

    def save(self, memory: dict, *, telegram_user_id: str | None = None) -> str:
        row = _build_row(memory, telegram_user_id=telegram_user_id)

        try:
            response = self._get_client().table(self.table_name).insert(row).execute()
        except SupabaseStorageError:
            raise
        except Exception as exc:
            raise SupabaseStorageError(
                f"Supabase memories insert failed: {exc}"
            ) from exc

        data = response.data or []
        if not data:
            raise SupabaseStorageError(
                "Supabase memories insert succeeded but returned no row id."
            )

        row_id = data[0].get("id")
        if not row_id:
            raise SupabaseStorageError(
                "Supabase memories insert succeeded but row id is missing."
            )

        return str(row_id)
