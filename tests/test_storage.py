"""Storage backend and Supabase row builder tests."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from conversation_to_memory.storage.factory import (
    DEFAULT_STORAGE_BACKEND,
    UnknownStorageBackendError,
    create_storage,
    get_storage_backend_name,
    validate_storage_backend,
)
from conversation_to_memory.storage.local_json import LocalJsonStorage
from conversation_to_memory.storage.supabase import (
    SupabaseStorage,
    SupabaseStorageError,
    _build_row,
)


def test_default_storage_backend_is_local_json(monkeypatch):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    assert get_storage_backend_name() == DEFAULT_STORAGE_BACKEND
    assert get_storage_backend_name() == "local_json"


def test_create_storage_uses_local_json_by_default(monkeypatch):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    storage = create_storage()
    assert isinstance(storage, LocalJsonStorage)


def test_create_storage_local_json_explicit(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local_json")
    storage = create_storage()
    assert isinstance(storage, LocalJsonStorage)


def test_create_storage_supabase(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "supabase")
    storage = create_storage()
    assert isinstance(storage, SupabaseStorage)


def test_unknown_storage_backend_raises(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    with pytest.raises(UnknownStorageBackendError, match="Unknown STORAGE_BACKEND"):
        validate_storage_backend()


def test_save_creates_json_file():
    with tempfile.TemporaryDirectory() as tmp:
        storage = LocalJsonStorage(directory=Path(tmp))
        memory = {
            "topic": "테스트",
            "event_summary": "요약",
            "user_emotions": ["기쁨"],
            "emotion_evidence": ["좋았다"],
            "people": ["Alice"],
            "projects": [],
            "tags": ["test"],
            "conversation": [{"role": "user", "content": "hello"}],
            "memory_candidate": "후보",
            "interpretation_risk": "low",
            "unsupported_inferences": [],
            "approved": True,
        }
        filepath = storage.save(memory)

        assert Path(filepath).exists()
        with open(filepath, encoding="utf-8") as f:
            saved = json.load(f)

        assert saved["topic"] == "테스트"
        assert saved["approved"] is True
        assert saved["schema_version"] == 2
        assert "timestamp" in saved


def test_save_uses_provided_timestamp():
    with tempfile.TemporaryDirectory() as tmp:
        storage = LocalJsonStorage(directory=Path(tmp))
        memory = {
            "timestamp": "2026-06-23T07:54:00",
            "topic": "테스트",
            "event_summary": "요약",
            "user_emotions": ["기쁨"],
            "emotion_evidence": ["좋았다"],
            "people": [],
            "projects": [],
            "tags": ["test"],
            "conversation": [{"role": "user", "content": "hello"}],
            "memory_candidate": "후보",
            "interpretation_risk": "low",
            "unsupported_inferences": [],
            "approved": True,
        }
        filepath = storage.save(memory)

        assert Path(filepath).name == "2026-06-23_075400.json"
        with open(filepath, encoding="utf-8") as f:
            saved = json.load(f)

        assert saved["timestamp"] == "2026-06-23T07:54:00"


def test_build_row_full_memory():
    memory = {
        "timestamp": "2026-06-11T17:56:09.123456",
        "topic": "부서 내 관계",
        "event_summary": "사건 요약",
        "user_emotions": ["답답함"],
        "emotion_evidence": ["원문"],
        "people": ["팀장"],
        "projects": ["프로젝트A"],
        "tags": ["업무"],
        "memory_candidate": "후보",
        "interpretation_risk": "low",
        "unsupported_inferences": [],
        "needs_followup": False,
        "followup_question": "",
        "conversation": [{"role": "user", "content": "hello"}],
        "approved": True,
        "schema_version": 2,
    }

    row = _build_row(memory, telegram_user_id="12345")

    assert row["source"] == "telegram"
    assert row["telegram_user_id"] == "12345"
    assert row["topic"] == "부서 내 관계"
    assert row["raw_memory"] == memory
    assert row["schema_version"] == 2


def test_build_row_missing_fields_use_safe_defaults():
    memory = {"topic": "최소"}

    row = _build_row(memory)

    assert row["user_emotions"] == []
    assert row["emotion_evidence"] == []
    assert row["people"] == []
    assert row["projects"] == []
    assert row["tags"] == []
    assert row["unsupported_inferences"] == []
    assert row["conversation"] == []
    assert row["approved"] is True
    assert row["schema_version"] == 2
    assert row["raw_memory"] == memory
    assert row["telegram_user_id"] is None


def test_supabase_save_inserts_row_and_returns_id():
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "abc-123"}]
    )

    storage = SupabaseStorage(
        url="https://example.supabase.co",
        secret_key="secret",
        table_name="memories",
        client=mock_client,
    )
    memory = {"topic": "테스트", "event_summary": "요약"}

    result = storage.save(memory, telegram_user_id="999")

    assert result == "abc-123"
    mock_client.table.assert_called_once_with("memories")
    inserted = mock_table.insert.call_args[0][0]
    assert inserted["topic"] == "테스트"
    assert inserted["telegram_user_id"] == "999"
    assert inserted["raw_memory"] == memory


def test_supabase_save_raises_on_insert_failure():
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.insert.return_value.execute.side_effect = RuntimeError("network down")

    storage = SupabaseStorage(client=mock_client)

    with pytest.raises(SupabaseStorageError, match="insert failed"):
        storage.save({"topic": "테스트"})


def test_supabase_save_requires_env_when_client_missing(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)

    storage = SupabaseStorage()

    with pytest.raises(SupabaseStorageError, match="SUPABASE_URL"):
        storage.save({"topic": "테스트"})
