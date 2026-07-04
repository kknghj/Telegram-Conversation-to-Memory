"""Supabase interpretation failure mirror tests (mocked — no network)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.interpretation_failures_supabase import (
    TABLE_NAME,
    UPSERT_CONFLICT_COLUMN,
    build_failure_key,
    failure_to_supabase_row,
    load_interpretation_failures,
    sync_interpretation_failure_to_supabase,
    sync_jsonl_to_supabase,
)


def _sample_failure(**overrides) -> dict:
    payload = {
        "timestamp": "2026-07-02T00:00:00+00:00",
        "conversation_id": "telegram_20260702_sleep_worry",
        "message_index": 5,
        "failure_type": "inappropriate_positive_reframe",
        "severity": "high",
        "context": [{"role": "user", "content": "걱정된다"}],
        "user_correction": "그런건 묻지마",
        "assistant_after_correction": "반대로 즐거웠던 순간은?",
        "expected_behavior": "긍정 회상 질문 금지",
        "root_cause": "부정 감정 직후 긍정 전환",
        "fixed_rule": "Rule 5",
    }
    payload.update(overrides)
    return payload


class TestFailureToSupabaseRow:
    def test_maps_columns_and_raw(self):
        record = _sample_failure()
        row = failure_to_supabase_row(record)

        assert row["failure_key"] == build_failure_key(record)
        assert row["failure_type"] == "inappropriate_positive_reframe"
        assert row["severity"] == "high"
        assert row["assistant_output"] == "반대로 즐거웠던 순간은?"
        assert row["raw"] == record


class TestSyncInterpretationFailures:
    def test_sync_uses_failure_key_conflict(self):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.upsert.return_value.execute.return_value = MagicMock(data=[])

        with patch(
            "app.interpretation_failures_supabase.get_supabase_client",
            return_value=mock_client,
        ):
            ok = sync_interpretation_failure_to_supabase(_sample_failure())

        assert ok is True
        mock_client.table.assert_called_with(TABLE_NAME)
        _, kwargs = mock_table.upsert.call_args
        assert kwargs["on_conflict"] == UPSERT_CONFLICT_COLUMN

    def test_sync_jsonl_from_temp_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "failures.jsonl"
            log_path.write_text(
                json.dumps(_sample_failure(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            with patch(
                "app.interpretation_failures_supabase.sync_interpretation_failure_to_supabase",
                return_value=True,
            ) as mock_sync:
                result = sync_jsonl_to_supabase(log_path)

            assert result["total"] == 1
            assert result["synced"] == 1
            assert result["failed"] == 0
            mock_sync.assert_called_once()

    def test_load_interpretation_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "failures.jsonl"
            log_path.write_text(
                json.dumps(_sample_failure(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            rows = load_interpretation_failures(log_path)
        assert len(rows) == 1
        assert rows[0]["failure_type"] == "inappropriate_positive_reframe"
