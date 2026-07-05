"""SQLite persistence for drafts, memories, and sessions."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.draft_storage import (
    DRAFT_STORAGE_BACKEND_SUPABASE,
    SupabaseDraftStore,
    get_draft_storage_backend_name,
)

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "memory_archive.db"

DRAFT_STATUS_ACTIVE = "active"
DRAFT_STATUS_CANCELLED = "cancelled"
DRAFT_STATUS_SAVED = "saved"

CANCELLED_RETENTION_DAYS = 30
ACTIVE_ABANDONED_DAYS = 7
RECENT_CANCELLED_HOURS = 24


def _use_supabase_drafts(db_path: Path | str | None = None) -> bool:
    return db_path is None and get_draft_storage_backend_name() == DRAFT_STORAGE_BACKEND_SUPABASE


def _draft_store() -> SupabaseDraftStore:
    return SupabaseDraftStore()


def _resolve_db_path(db_path: Path | str | None) -> Path:
    return Path(db_path) if db_path is not None else DEFAULT_DB_PATH


def _connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = _resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | str | None = None) -> None:
    """Create tables if they do not exist."""
    if _use_supabase_drafts(db_path):
        return

    with _connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                status TEXT NOT NULL,
                raw_text TEXT,
                summary_json TEXT,
                cancellation_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                draft_id INTEGER,
                content_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (draft_id) REFERENCES drafts(id)
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                draft_id INTEGER,
                state_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (draft_id) REFERENCES drafts(id)
            );

            CREATE INDEX IF NOT EXISTS idx_drafts_user_status
                ON drafts(user_id, status);
            CREATE INDEX IF NOT EXISTS idx_drafts_updated_at
                ON drafts(updated_at);
            """
        )
        conn.commit()


def _row_to_draft(row: sqlite3.Row) -> dict[str, Any]:
    summary = json.loads(row["summary_json"]) if row["summary_json"] else {}
    raw = json.loads(row["raw_text"]) if row["raw_text"] else {}
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "status": row["status"],
        "draft": summary,
        "user_texts": raw.get("user_texts", []),
        "conversation": raw.get("conversation", []),
        "cancellation_reason": row["cancellation_reason"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def save_cancelled_draft(
    user_id: str,
    *,
    draft: dict[str, Any],
    user_texts: list[str],
    conversation: list[dict[str, Any]] | None = None,
    cancellation_reason: str = "",
    db_path: Path | str | None = None,
) -> int:
    """Persist a cancelled draft. Returns the new row id."""
    if _use_supabase_drafts(db_path):
        return _draft_store().save_cancelled_draft(
            user_id,
            draft=draft,
            user_texts=user_texts,
            conversation=conversation,
            cancellation_reason=cancellation_reason,
        )

    raw_text = json.dumps(
        {"user_texts": user_texts, "conversation": conversation or []},
        ensure_ascii=False,
    )
    summary_json = json.dumps(draft, ensure_ascii=False)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO drafts (user_id, status, raw_text, summary_json, cancellation_reason, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, DRAFT_STATUS_CANCELLED, raw_text, summary_json, cancellation_reason, now),
        )
        conn.commit()
        return cursor.lastrowid


def get_latest_cancelled_draft(
    user_id: str,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Return the most recent cancelled draft for a user."""
    if _use_supabase_drafts(db_path):
        return _draft_store().get_latest_cancelled_draft(user_id)

    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM drafts
            WHERE user_id = ?
            AND status = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (user_id, DRAFT_STATUS_CANCELLED),
        ).fetchone()
    return _row_to_draft(row) if row else None


def has_recent_cancelled_draft(
    user_id: str,
    *,
    within_hours: int = RECENT_CANCELLED_HOURS,
    db_path: Path | str | None = None,
) -> bool:
    """True if a cancelled draft exists within the given hour window."""
    if _use_supabase_drafts(db_path):
        return _draft_store().has_recent_cancelled_draft(
            user_id,
            within_hours=within_hours,
        )

    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=within_hours)
    ).strftime("%Y-%m-%d %H:%M:%S")

    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM drafts
            WHERE user_id = ?
            AND status = ?
            AND updated_at >= ?
            LIMIT 1
            """,
            (user_id, DRAFT_STATUS_CANCELLED, cutoff),
        ).fetchone()
    return row is not None


def save_active_draft(
    user_id: str,
    *,
    user_texts: list[str],
    conversation: list[dict[str, Any]] | None = None,
    draft: dict[str, Any] | None = None,
    db_path: Path | str | None = None,
) -> int:
    """Create or update the user's active draft."""
    if _use_supabase_drafts(db_path):
        return _draft_store().save_active_draft(
            user_id,
            user_texts=user_texts,
            conversation=conversation,
            draft=draft,
        )

    raw_text = json.dumps(
        {"user_texts": user_texts, "conversation": conversation or []},
        ensure_ascii=False,
    )
    summary_json = json.dumps(draft, ensure_ascii=False) if draft else None
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    with _connect(db_path) as conn:
        existing = conn.execute(
            """
            SELECT id FROM drafts
            WHERE user_id = ? AND status = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (user_id, DRAFT_STATUS_ACTIVE),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE drafts
                SET raw_text = ?, summary_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (raw_text, summary_json, now, existing["id"]),
            )
            conn.commit()
            return existing["id"]

        cursor = conn.execute(
            """
            INSERT INTO drafts (user_id, status, raw_text, summary_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, DRAFT_STATUS_ACTIVE, raw_text, summary_json, now),
        )
        conn.commit()
        return cursor.lastrowid


def mark_draft_saved(
    draft_id: Any | None,
    user_id: str,
    *,
    draft: dict[str, Any],
    user_texts: list[str],
    conversation: list[dict[str, Any]] | None = None,
    db_path: Path | str | None = None,
) -> int:
    """Mark an existing draft as saved, or insert a new saved row."""
    if _use_supabase_drafts(db_path):
        return _draft_store().mark_draft_saved(
            str(draft_id) if draft_id is not None else None,
            user_id,
            draft=draft,
            user_texts=user_texts,
            conversation=conversation,
        )

    raw_text = json.dumps(
        {"user_texts": user_texts, "conversation": conversation or []},
        ensure_ascii=False,
    )
    summary_json = json.dumps(draft, ensure_ascii=False)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    with _connect(db_path) as conn:
        if draft_id is not None:
            conn.execute(
                """
                UPDATE drafts
                SET status = ?, raw_text = ?, summary_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (DRAFT_STATUS_SAVED, raw_text, summary_json, now, draft_id),
            )
            conn.commit()
            return draft_id

        cursor = conn.execute(
            """
            INSERT INTO drafts (user_id, status, raw_text, summary_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, DRAFT_STATUS_SAVED, raw_text, summary_json, now),
        )
        conn.commit()
        return cursor.lastrowid


def cleanup_drafts(db_path: Path | str | None = None) -> dict[str, int]:
    """
    Apply retention policy:
    - cancelled older than 30 days → delete
    - active abandoned 7+ days → convert to cancelled
    - saved → never deleted
    """
    if _use_supabase_drafts(db_path):
        return _draft_store().cleanup_drafts(
            cancelled_days=CANCELLED_RETENTION_DAYS,
            active_days=ACTIVE_ABANDONED_DAYS,
        )

    now = datetime.now(timezone.utc)
    cancelled_cutoff = (now - timedelta(days=CANCELLED_RETENTION_DAYS)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    active_cutoff = (now - timedelta(days=ACTIVE_ABANDONED_DAYS)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    convert_time = now.strftime("%Y-%m-%d %H:%M:%S")

    with _connect(db_path) as conn:
        deleted = conn.execute(
            """
            DELETE FROM drafts
            WHERE status = ? AND updated_at < ?
            """,
            (DRAFT_STATUS_CANCELLED, cancelled_cutoff),
        ).rowcount

        converted = conn.execute(
            """
            UPDATE drafts
            SET status = ?, updated_at = ?
            WHERE status = ? AND updated_at < ?
            """,
            (DRAFT_STATUS_CANCELLED, convert_time, DRAFT_STATUS_ACTIVE, active_cutoff),
        ).rowcount

        conn.commit()

    return {"deleted_cancelled": deleted, "converted_active": converted}
