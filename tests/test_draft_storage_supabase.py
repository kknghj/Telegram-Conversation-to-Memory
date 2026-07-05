"""Supabase draft storage tests (mocked, no network)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app import database as db
from app.draft_storage import (
    SupabaseDraftStore,
    get_draft_storage_backend_name,
    validate_draft_storage_backend,
)


def test_supabase_draft_store_inserts_cancelled_draft(monkeypatch):
    table = MagicMock()
    table.insert.return_value.execute.return_value = MagicMock(data=[{"id": "draft-1"}])
    client = MagicMock()
    client.table.return_value = table

    store = SupabaseDraftStore(client=client, table_name="drafts")
    result = store.save_cancelled_draft(
        "user-1",
        draft={"topic": "테스트"},
        user_texts=["원문"],
        conversation=[{"role": "user", "content": "원문"}],
        cancellation_reason="취소",
    )

    assert result == "draft-1"
    client.table.assert_called_with("drafts")
    inserted = table.insert.call_args[0][0]
    assert inserted["telegram_user_id"] == "user-1"
    assert inserted["status"] == "cancelled"
    assert inserted["raw_text"]["user_texts"] == ["원문"]
    assert inserted["summary_json"] == {"topic": "테스트"}


def test_supabase_draft_store_maps_latest_cancelled_draft():
    row = {
        "id": "draft-1",
        "telegram_user_id": "user-1",
        "status": "cancelled",
        "raw_text": {
            "user_texts": ["원문"],
            "conversation": [{"role": "user", "content": "원문"}],
        },
        "summary_json": {"topic": "테스트"},
        "cancellation_reason": "취소",
        "created_at": "2026-07-05T00:00:00Z",
        "updated_at": "2026-07-05T00:00:00Z",
    }
    table = MagicMock()
    table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[row]
    )
    client = MagicMock()
    client.table.return_value = table

    store = SupabaseDraftStore(client=client, table_name="drafts")
    result = store.get_latest_cancelled_draft("user-1")

    assert result["id"] == "draft-1"
    assert result["user_id"] == "user-1"
    assert result["draft"] == {"topic": "테스트"}
    assert result["user_texts"] == ["원문"]


def test_database_routes_to_supabase_when_backend_enabled(monkeypatch):
    monkeypatch.setenv("DRAFT_STORAGE_BACKEND", "supabase")
    store = MagicMock()
    store.save_active_draft.return_value = "draft-1"

    with patch("app.database._draft_store", return_value=store):
        result = db.save_active_draft(
            "user-1",
            user_texts=["원문"],
            conversation=[{"role": "user", "content": "원문"}],
            draft={"topic": "테스트"},
        )

    assert result == "draft-1"
    store.save_active_draft.assert_called_once()


def test_database_explicit_db_path_keeps_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv("DRAFT_STORAGE_BACKEND", "supabase")
    db_path = tmp_path / "memory_archive.db"
    db.init_db(db_path)

    draft_id = db.save_active_draft(
        "user-1",
        user_texts=["원문"],
        db_path=db_path,
    )

    assert isinstance(draft_id, int)


def test_draft_storage_backend_validation(monkeypatch):
    monkeypatch.setenv("DRAFT_STORAGE_BACKEND", "supabase")
    assert get_draft_storage_backend_name() == "supabase"
    validate_draft_storage_backend()
