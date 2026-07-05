"""Supabase persistence for in-progress and cancelled drafts."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

DRAFT_STORAGE_BACKEND_SQLITE = "sqlite"
DRAFT_STORAGE_BACKEND_SUPABASE = "supabase"
DEFAULT_DRAFT_STORAGE_BACKEND = DRAFT_STORAGE_BACKEND_SQLITE
SUPPORTED_DRAFT_STORAGE_BACKENDS = frozenset(
    {DRAFT_STORAGE_BACKEND_SQLITE, DRAFT_STORAGE_BACKEND_SUPABASE}
)
DEFAULT_DRAFTS_TABLE = "drafts"


class UnknownDraftStorageBackendError(ValueError):
    """Raised when DRAFT_STORAGE_BACKEND is not supported."""


class SupabaseDraftStorageError(Exception):
    """Raised when Supabase draft persistence fails."""


def get_draft_storage_backend_name() -> str:
    return (
        os.getenv("DRAFT_STORAGE_BACKEND", DEFAULT_DRAFT_STORAGE_BACKEND)
        .strip()
        .lower()
        or DEFAULT_DRAFT_STORAGE_BACKEND
    )


def validate_draft_storage_backend() -> None:
    backend = get_draft_storage_backend_name()
    if backend not in SUPPORTED_DRAFT_STORAGE_BACKENDS:
        supported = ", ".join(sorted(SUPPORTED_DRAFT_STORAGE_BACKENDS))
        raise UnknownDraftStorageBackendError(
            f"Unknown DRAFT_STORAGE_BACKEND={backend!r}. Supported values: {supported}"
        )


def get_drafts_table_name() -> str:
    return os.getenv("SUPABASE_DRAFTS_TABLE", DEFAULT_DRAFTS_TABLE).strip() or DEFAULT_DRAFTS_TABLE


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SupabaseDraftStorageError(f"환경변수 {name}가 설정되지 않았습니다.")
    return value


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_draft(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["telegram_user_id"],
        "status": row["status"],
        "draft": row.get("summary_json") or {},
        "user_texts": (row.get("raw_text") or {}).get("user_texts", []),
        "conversation": (row.get("raw_text") or {}).get("conversation", []),
        "cancellation_reason": row.get("cancellation_reason") or "",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


class SupabaseDraftStore:
    """Draft store with the same contract as app.database public helpers."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        table_name: str | None = None,
        url: str | None = None,
        secret_key: str | None = None,
    ):
        self._client = client
        self.table_name = table_name or get_drafts_table_name()
        self.url = (url or os.getenv("SUPABASE_URL", "")).strip()
        self.secret_key = (secret_key or os.getenv("SUPABASE_SECRET_KEY", "")).strip()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        from supabase import create_client

        self._client = create_client(
            self.url or _require_env("SUPABASE_URL"),
            self.secret_key or _require_env("SUPABASE_SECRET_KEY"),
        )
        return self._client

    def verify_connection(self) -> None:
        try:
            (
                self._get_client()
                .table(self.table_name)
                .select("id")
                .limit(1)
                .execute()
            )
        except SupabaseDraftStorageError:
            raise
        except Exception as exc:
            raise SupabaseDraftStorageError(
                f"Supabase drafts connection check failed: {exc}"
            ) from exc

    def save_cancelled_draft(
        self,
        user_id: str,
        *,
        draft: dict[str, Any],
        user_texts: list[str],
        conversation: list[dict[str, Any]] | None = None,
        cancellation_reason: str = "",
    ) -> str:
        row = {
            "telegram_user_id": user_id,
            "status": "cancelled",
            "raw_text": {"user_texts": user_texts, "conversation": conversation or []},
            "summary_json": draft,
            "cancellation_reason": cancellation_reason,
            "updated_at": _now_iso(),
        }
        response = self._get_client().table(self.table_name).insert(row).execute()
        data = response.data or []
        if not data or not data[0].get("id"):
            raise SupabaseDraftStorageError("Draft insert succeeded but returned no row id.")
        return str(data[0]["id"])

    def get_latest_cancelled_draft(self, user_id: str) -> dict[str, Any] | None:
        response = (
            self._get_client()
            .table(self.table_name)
            .select("*")
            .eq("telegram_user_id", user_id)
            .eq("status", "cancelled")
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return _row_to_draft(rows[0]) if rows else None

    def has_recent_cancelled_draft(self, user_id: str, *, within_hours: int) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=within_hours)).isoformat()
        response = (
            self._get_client()
            .table(self.table_name)
            .select("id")
            .eq("telegram_user_id", user_id)
            .eq("status", "cancelled")
            .gte("updated_at", cutoff)
            .limit(1)
            .execute()
        )
        return bool(response.data)

    def save_active_draft(
        self,
        user_id: str,
        *,
        user_texts: list[str],
        conversation: list[dict[str, Any]] | None = None,
        draft: dict[str, Any] | None = None,
    ) -> str:
        existing = (
            self._get_client()
            .table(self.table_name)
            .select("id")
            .eq("telegram_user_id", user_id)
            .eq("status", "active")
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = existing.data or []
        payload = {
            "raw_text": {"user_texts": user_texts, "conversation": conversation or []},
            "summary_json": draft,
            "updated_at": _now_iso(),
        }
        table = self._get_client().table(self.table_name)
        if rows:
            draft_id = str(rows[0]["id"])
            table.update(payload).eq("id", draft_id).execute()
            return draft_id

        row = {
            "telegram_user_id": user_id,
            "status": "active",
            **payload,
        }
        response = table.insert(row).execute()
        data = response.data or []
        if not data or not data[0].get("id"):
            raise SupabaseDraftStorageError("Draft insert succeeded but returned no row id.")
        return str(data[0]["id"])

    def mark_draft_saved(
        self,
        draft_id: str | None,
        user_id: str,
        *,
        draft: dict[str, Any],
        user_texts: list[str],
        conversation: list[dict[str, Any]] | None = None,
    ) -> str:
        payload = {
            "status": "saved",
            "raw_text": {"user_texts": user_texts, "conversation": conversation or []},
            "summary_json": draft,
            "updated_at": _now_iso(),
        }
        table = self._get_client().table(self.table_name)
        if draft_id is not None:
            table.update(payload).eq("id", str(draft_id)).execute()
            return str(draft_id)

        response = table.insert(
            {
                "telegram_user_id": user_id,
                **payload,
            }
        ).execute()
        data = response.data or []
        if not data or not data[0].get("id"):
            raise SupabaseDraftStorageError("Draft insert succeeded but returned no row id.")
        return str(data[0]["id"])

    def cleanup_drafts(self, *, cancelled_days: int, active_days: int) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        cancelled_cutoff = (now - timedelta(days=cancelled_days)).isoformat()
        active_cutoff = (now - timedelta(days=active_days)).isoformat()

        deleted = (
            self._get_client()
            .table(self.table_name)
            .delete()
            .eq("status", "cancelled")
            .lt("updated_at", cancelled_cutoff)
            .execute()
        )
        converted = (
            self._get_client()
            .table(self.table_name)
            .update({"status": "cancelled", "updated_at": _now_iso()})
            .eq("status", "active")
            .lt("updated_at", active_cutoff)
            .execute()
        )
        return {
            "deleted_cancelled": len(deleted.data or []),
            "converted_active": len(converted.data or []),
        }


def verify_supabase_drafts_connection() -> None:
    SupabaseDraftStore().verify_connection()
