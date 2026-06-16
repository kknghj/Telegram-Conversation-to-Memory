"""Supabase evaluation mirror tests (mocked — no network)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation_supabase import (
    evaluation_to_supabase_row,
    get_supabase_client,
    is_supabase_configured,
    load_evaluations_from_supabase,
    sync_evaluation_to_supabase,
    sync_jsonl_to_supabase,
)
from conversation_to_memory.reflection.evaluation_models import CardEvaluation
from conversation_to_memory.reflection.evaluation_storage import (
    append_card_evaluation,
    load_card_evaluations,
)


def _sample_evaluation(**overrides) -> dict:
    payload = {
        "evaluation_id": "eval-test-001",
        "evaluated_at": "2026-06-13T15:00:00+00:00",
        "memory_count": 36,
        "card_id": "SC-03",
        "card_type": "surprising_connection",
        "accuracy": "correct",
        "value": {"interesting": True, "revisit": False},
        "evidence": "sufficient",
        "failure_type": None,
        "user_comment": "테스트 코멘트",
    }
    payload.update(overrides)
    return payload


class TestEvaluationToSupabaseRow:
    def test_maps_flat_columns_and_raw_json(self):
        evaluation = CardEvaluation.model_validate(_sample_evaluation())
        row = evaluation_to_supabase_row(evaluation)

        assert row["evaluation_id"] == "eval-test-001"
        assert row["evaluated_at"] == "2026-06-13T15:00:00+00:00"
        assert row["memory_count"] == 36
        assert row["card_id"] == "SC-03"
        assert row["card_type"] == "surprising_connection"
        assert row["accuracy"] == "correct"
        assert row["interesting"] is True
        assert row["revisit"] is False
        assert row["evidence"] == "sufficient"
        assert row["failure_type"] is None
        assert row["user_comment"] == "테스트 코멘트"
        assert row["action"] == "keep"
        assert row["raw"]["card_id"] == "SC-03"
        assert row["raw"]["value"]["interesting"] is True

    def test_failure_type_mapped_when_present(self):
        evaluation = CardEvaluation.model_validate(
            _sample_evaluation(failure_type="CONNECTION_FAILURE")
        )
        row = evaluation_to_supabase_row(evaluation)
        assert row["failure_type"] == "CONNECTION_FAILURE"
        assert row["action"] == "revise"


class TestSupabaseWithoutEnv:
    def test_get_supabase_client_returns_none_without_env(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
        assert get_supabase_client() is None
        assert is_supabase_configured() is False

    def test_sync_evaluation_returns_false_without_env(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
        evaluation = CardEvaluation.model_validate(_sample_evaluation())
        assert sync_evaluation_to_supabase(evaluation) is False

    def test_load_evaluations_returns_empty_without_env(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
        assert load_evaluations_from_supabase() == []


class TestSyncJsonlToSupabase:
    def test_records_partial_failures(self):
        evaluations = [
            CardEvaluation.model_validate(
                _sample_evaluation(evaluation_id="ok", card_id="C-1")
            ),
            CardEvaluation.model_validate(
                _sample_evaluation(evaluation_id="bad", card_id="C-2")
            ),
        ]

        def fake_sync(evaluation: CardEvaluation) -> bool:
            return evaluation.evaluation_id == "ok"

        with patch(
            "app.evaluation_supabase.load_card_evaluations",
            return_value=evaluations,
        ), patch(
            "app.evaluation_supabase.sync_evaluation_to_supabase",
            side_effect=fake_sync,
        ):
            result = sync_jsonl_to_supabase("dummy.jsonl")

        assert result == {
            "total": 2,
            "synced": 1,
            "failed": 1,
            "failed_items": [{"evaluation_id": "bad", "card_id": "C-2"}],
        }

    def test_sync_from_temp_jsonl_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "log.jsonl"
            append_card_evaluation(
                _sample_evaluation(evaluation_id="a", card_id="C-1"),
                path=log_path,
                sync_supabase=False,
            )
            append_card_evaluation(
                _sample_evaluation(evaluation_id="b", card_id="C-2"),
                path=log_path,
                sync_supabase=False,
            )

            with patch(
                "app.evaluation_supabase.sync_evaluation_to_supabase",
                return_value=True,
            ) as mock_sync:
                result = sync_jsonl_to_supabase(log_path)

            assert result["total"] == 2
            assert result["synced"] == 2
            assert result["failed"] == 0
            assert mock_sync.call_count == 2


class TestAppendWithOptionalSync:
    def test_append_succeeds_when_supabase_sync_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "log.jsonl"
            with patch(
                "app.evaluation_supabase.is_supabase_configured",
                return_value=True,
            ), patch(
                "app.evaluation_supabase.sync_evaluation_to_supabase",
                return_value=False,
            ):
                record = append_card_evaluation(
                    _sample_evaluation(),
                    path=log_path,
                )

            assert record.evaluation_id == "eval-test-001"
            loaded = load_card_evaluations(path=log_path)
            assert len(loaded) == 1

    def test_append_skips_sync_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "log.jsonl"
            with patch(
                "app.evaluation_supabase.sync_evaluation_to_supabase",
            ) as mock_sync:
                append_card_evaluation(
                    _sample_evaluation(),
                    path=log_path,
                    sync_supabase=False,
                )
            mock_sync.assert_not_called()

    def test_append_triggers_sync_when_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "log.jsonl"
            with patch(
                "app.evaluation_supabase.is_supabase_configured",
                return_value=True,
            ), patch(
                "app.evaluation_supabase.sync_evaluation_to_supabase",
                return_value=True,
            ) as mock_sync:
                append_card_evaluation(_sample_evaluation(), path=log_path)
            mock_sync.assert_called_once()


class TestLoadFromSupabase:
    def test_load_with_evaluation_id_filter(self):
        mock_client = MagicMock()
        mock_query = MagicMock()
        mock_client.table.return_value.select.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.execute.return_value = MagicMock(
            data=[{"evaluation_id": "eval-1", "card_id": "SC-03"}]
        )

        with patch(
            "app.evaluation_supabase.get_supabase_client",
            return_value=mock_client,
        ):
            rows = load_evaluations_from_supabase(evaluation_id="eval-1")

        assert len(rows) == 1
        mock_query.eq.assert_called_once_with("evaluation_id", "eval-1")

    def test_load_returns_empty_on_client_error(self):
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.order.return_value.execute.side_effect = RuntimeError(
            "network down"
        )

        with patch(
            "app.evaluation_supabase.get_supabase_client",
            return_value=mock_client,
        ):
            assert load_evaluations_from_supabase() == []
