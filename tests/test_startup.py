"""Startup validation tests."""

from __future__ import annotations

from unittest.mock import patch

from conversation_to_memory import startup


def test_run_pre_build_checks_verifies_supabase_drafts(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
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
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("STORAGE_BACKEND", "local_json")
    monkeypatch.setenv("DRAFT_STORAGE_BACKEND", "supabase")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)

    try:
        startup.run_pre_build_checks()
    except startup.StartupError as exc:
        assert "SUPABASE_URL" in str(exc)
    else:
        raise AssertionError("StartupError was not raised")
