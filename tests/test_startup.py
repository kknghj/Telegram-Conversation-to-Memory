"""Startup validation tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from conversation_to_memory import startup


def _set_required_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")


def test_check_required_env_reports_missing_values(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(startup.StartupError) as exc_info:
        startup.check_required_env()

    message = str(exc_info.value)
    assert "TELEGRAM_BOT_TOKEN" in message
    assert "OPENAI_API_KEY" in message


def test_run_pre_build_checks_skips_supabase_for_local_backends(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("STORAGE_BACKEND", "local_json")
    monkeypatch.setenv("DRAFT_STORAGE_BACKEND", "sqlite")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)

    with patch("conversation_to_memory.startup.check_supabase_connection") as memories:
        with patch("conversation_to_memory.startup.check_supabase_drafts_connection") as drafts:
            backend = startup.run_pre_build_checks()

    assert backend == "local_json"
    memories.assert_not_called()
    drafts.assert_not_called()


def test_run_pre_build_checks_verifies_supabase_drafts(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("STORAGE_BACKEND", "supabase")
    monkeypatch.setenv("DRAFT_STORAGE_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "secret")

    with patch("conversation_to_memory.startup.check_supabase_connection") as memories:
        with patch("conversation_to_memory.startup.check_supabase_drafts_connection") as drafts:
            startup.run_pre_build_checks()

    memories.assert_called_once()
    drafts.assert_called_once()


def test_run_pre_build_checks_requires_supabase_env_for_drafts(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("STORAGE_BACKEND", "local_json")
    monkeypatch.setenv("DRAFT_STORAGE_BACKEND", "supabase")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)

    with pytest.raises(startup.StartupError) as exc_info:
        startup.run_pre_build_checks()

    assert "SUPABASE_URL" in str(exc_info.value)
    assert "SUPABASE_SECRET_KEY" in str(exc_info.value)


def test_check_supabase_connection_wraps_storage_error(monkeypatch):
    from conversation_to_memory.storage.supabase import SupabaseStorageError

    monkeypatch.setenv("SUPABASE_MEMORIES_TABLE", "memories")

    with patch(
        "conversation_to_memory.storage.supabase.verify_connection",
        side_effect=SupabaseStorageError("network down"),
    ):
        with pytest.raises(startup.StartupError) as exc_info:
            startup.check_supabase_connection()

    assert "Supabase 연결 실패 (table=memories)" in str(exc_info.value)
    assert "network down" in str(exc_info.value)


def test_check_supabase_drafts_connection_wraps_storage_error(monkeypatch):
    from app.draft_storage import SupabaseDraftStorageError

    monkeypatch.setenv("SUPABASE_DRAFTS_TABLE", "drafts")

    with patch(
        "conversation_to_memory.startup.verify_supabase_drafts_connection",
        side_effect=SupabaseDraftStorageError("table missing"),
    ):
        with pytest.raises(startup.StartupError) as exc_info:
            startup.check_supabase_drafts_connection()

    assert "Supabase drafts 연결 실패 (table=drafts)" in str(exc_info.value)
    assert "table missing" in str(exc_info.value)
