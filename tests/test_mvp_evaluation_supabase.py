"""Supabase MVP evaluation mirror tests (mocked — no network)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.mvp_evaluation_supabase import (
    MVP_TABLE_NAME,
    MVP_UPSERT_CONFLICT_COLUMN,
    load_mvp_evaluation,
    load_mvp_pattern_card_evaluations,
    mvp_evaluation_to_supabase_row,
    mvp_pattern_card_to_reflection_row,
    sync_mvp_bundle_to_supabase,
    sync_mvp_evaluation_to_supabase,
)


def _sample_mvp_data(**overrides) -> dict:
    payload = {
        "evaluation_id": "mvp_round2-2026-06-19",
        "evaluation_type": "mvp_round",
        "round": 2,
        "evaluated_at": "2026-06-19",
        "memory_count": 50,
        "previous_memory_count": 36,
        "new_memory_count": 14,
        "final_judgment": "conditional_success",
        "score": 4.08,
        "user_validated": True,
        "user_validation_summary": {"accepted_insights": ["test"]},
        "top_insights": ["insight"],
        "main_limitation": "short period",
        "next_milestone": "100 records",
    }
    payload.update(overrides)
    return payload


class TestMvpEvaluationToSupabaseRow:
    def test_maps_columns_and_payload(self):
        data = _sample_mvp_data()
        row = mvp_evaluation_to_supabase_row(data)

        assert row["evaluation_id"] == "mvp_round2-2026-06-19"
        assert row["evaluation_type"] == "mvp_round"
        assert row["round"] == 2
        assert row["final_judgment"] == "conditional_success"
        assert row["score"] == 4.08
        assert row["user_validated"] is True
        assert row["payload"] == data


class TestMvpPatternCardMapping:
    def test_maps_to_reflection_row(self):
        row = {
            "evaluation_id": "mvp_round2-2026-06-19",
            "evaluated_at": "2026-06-19T12:00:00+00:00",
            "memory_count": 50,
            "card_id": "MVP2-PC-02",
            "card_type": "mvp_pattern_card",
            "title": "업무 자동화 역설",
            "user_judgment": "accepted",
            "evaluation_result": "correct",
            "accuracy": "correct",
            "value": {"interesting": True, "revisit": True},
            "evidence": "sufficient",
            "failure_type": None,
            "user_comment": "accepted",
            "action": "keep",
        }
        supabase_row = mvp_pattern_card_to_reflection_row(row)
        assert supabase_row["card_id"] == "MVP2-PC-02"
        assert supabase_row["accuracy"] == "correct"
        assert supabase_row["action"] == "keep"
        assert supabase_row["raw"]["title"] == "업무 자동화 역설"


class TestSyncMvpBundle:
    def test_dry_run_counts_without_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            mvp_path = Path(tmp) / "mvp.json"
            cards_path = Path(tmp) / "cards.jsonl"
            mvp_path.write_text(
                json.dumps(_sample_mvp_data(), ensure_ascii=False),
                encoding="utf-8",
            )
            cards_path.write_text(
                json.dumps(
                    {
                        "evaluation_id": "mvp_round2-2026-06-19",
                        "evaluated_at": "2026-06-19T12:00:00+00:00",
                        "memory_count": 50,
                        "card_id": "MVP2-PC-01",
                        "card_type": "mvp_pattern_card",
                        "title": "test",
                        "user_judgment": "accepted",
                        "evaluation_result": "correct",
                        "accuracy": "correct",
                        "value": {"interesting": True, "revisit": False},
                        "evidence": "sufficient",
                        "user_comment": "",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = sync_mvp_bundle_to_supabase(
                mvp_json_path=mvp_path,
                pattern_cards_path=cards_path,
                dry_run=True,
            )

        assert result["loaded_mvp_evaluations"] == 1
        assert result["upserted_mvp"] == 1
        assert result["pattern_cards"]["synced"] == 1

    def test_sync_mvp_uses_evaluation_id_conflict(self):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.upsert.return_value.execute.return_value = MagicMock(data=[])

        with patch(
            "app.mvp_evaluation_supabase.get_supabase_client",
            return_value=mock_client,
        ):
            ok = sync_mvp_evaluation_to_supabase(_sample_mvp_data())

        assert ok is True
        mock_client.table.assert_called_with(MVP_TABLE_NAME)
        mock_table.upsert.assert_called_once()
        _, kwargs = mock_table.upsert.call_args
        assert kwargs["on_conflict"] == MVP_UPSERT_CONFLICT_COLUMN

    def test_load_pattern_cards_filters_by_evaluation_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            cards_path = Path(tmp) / "cards.jsonl"
            cards_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "evaluation_id": "mvp_round2-2026-06-19",
                                "card_id": "MVP2-PC-01",
                            }
                        ),
                        json.dumps(
                            {
                                "evaluation_id": "other",
                                "card_id": "X-01",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            rows = load_mvp_pattern_card_evaluations(
                cards_path,
                evaluation_id="mvp_round2-2026-06-19",
            )
        assert len(rows) == 1
        assert rows[0]["card_id"] == "MVP2-PC-01"

    def test_load_mvp_evaluation_from_file(self, tmp_path):
        mvp_path = tmp_path / "mvp.json"
        mvp_path.write_text(
            json.dumps(_sample_mvp_data(), ensure_ascii=False),
            encoding="utf-8",
        )
        loaded = load_mvp_evaluation(mvp_path)
        assert loaded["evaluation_id"] == "mvp_round2-2026-06-19"
