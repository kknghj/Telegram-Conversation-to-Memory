"""회고 카드 평가 observation log 테스트."""

import json
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from conversation_to_memory.reflection.evaluation_models import (
    Accuracy,
    Action,
    CardEvaluation,
    CardValue,
    EvidenceQuality,
    FailureType,
    derive_action,
)
from conversation_to_memory.reflection.evaluation_storage import (
    aggregate_evaluation_stats,
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
        "value": {"interesting": True, "revisit": True},
        "evidence": "sufficient",
        "failure_type": None,
        "user_comment": "테스트",
    }
    payload.update(overrides)
    return payload


class TestAppendLoadRoundTrip:
    def test_append_and_load_single_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "reflection_failures.jsonl"
            original = _sample_evaluation()
            saved = append_card_evaluation(original, path=log_path)

            assert saved.action == Action.KEEP
            loaded = load_card_evaluations(path=log_path)
            assert len(loaded) == 1
            assert loaded[0].evaluation_id == "eval-test-001"
            assert loaded[0].card_id == "SC-03"
            assert loaded[0].value.interesting is True

    def test_multiple_append_preserves_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "reflection_failures.jsonl"
            append_card_evaluation(
                _sample_evaluation(evaluation_id="a", card_id="C-1"),
                path=log_path,
            )
            append_card_evaluation(
                _sample_evaluation(evaluation_id="b", card_id="C-2"),
                path=log_path,
            )
            loaded = load_card_evaluations(path=log_path)
            assert [r.evaluation_id for r in loaded] == ["a", "b"]

    def test_jsonl_line_matches_model_dump(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "reflection_failures.jsonl"
            append_card_evaluation(_sample_evaluation(), path=log_path)
            line = log_path.read_text(encoding="utf-8").strip()
            parsed = json.loads(line)
            assert parsed["action"] == "keep"
            assert parsed["accuracy"] == "correct"


class TestInvalidEnumReject:
    def test_invalid_accuracy_rejected(self):
        with pytest.raises(ValidationError):
            CardEvaluation.model_validate(
                _sample_evaluation(accuracy="mostly_correct")
            )

    def test_invalid_failure_type_rejected(self):
        with pytest.raises(ValidationError):
            CardEvaluation.model_validate(
                _sample_evaluation(failure_type="HALLUCINATION")
            )

    def test_invalid_evidence_rejected(self):
        with pytest.raises(ValidationError):
            CardEvaluation.model_validate(
                _sample_evaluation(evidence="maybe")
            )


class TestActionDerivation:
    def test_wrong_accuracy_discards(self):
        record = CardEvaluation.model_validate(
            _sample_evaluation(accuracy="wrong", evidence="sufficient")
        )
        assert record.action == Action.DISCARD

    def test_weak_evidence_revises(self):
        record = CardEvaluation.model_validate(
            _sample_evaluation(
                accuracy="correct",
                evidence="weak",
                failure_type=None,
            )
        )
        assert record.action == Action.REVISE

    def test_failure_type_revises(self):
        record = CardEvaluation.model_validate(
            _sample_evaluation(
                accuracy="correct",
                evidence="sufficient",
                failure_type="CONNECTION_FAILURE",
            )
        )
        assert record.action == Action.REVISE

    def test_wrong_accuracy_overrides_failure_type(self):
        record = CardEvaluation.model_validate(
            _sample_evaluation(
                accuracy="wrong",
                evidence="weak",
                failure_type="CONNECTION_FAILURE",
            )
        )
        assert record.action == Action.DISCARD

    def test_derive_action_function(self):
        base = CardEvaluation.model_validate(_sample_evaluation())
        assert derive_action(base) == Action.KEEP


class TestAggregateStats:
    def _write_evaluations(self, log_path: Path, rows: list[dict]) -> None:
        for row in rows:
            append_card_evaluation(row, path=log_path)

    def test_aggregate_from_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "reflection_failures.jsonl"
            self._write_evaluations(
                log_path,
                [
                    _sample_evaluation(
                        evaluation_id="1",
                        accuracy="correct",
                        evidence="sufficient",
                        value={"interesting": True, "revisit": False},
                    ),
                    _sample_evaluation(
                        evaluation_id="2",
                        card_id="RP-01",
                        accuracy="wrong",
                        evidence="wrong",
                        value={"interesting": False, "revisit": False},
                        failure_type="INTERPRETATION_FAILURE",
                    ),
                    _sample_evaluation(
                        evaluation_id="3",
                        card_id="OQ-01",
                        accuracy="partial",
                        evidence="weak",
                        value={"interesting": True, "revisit": True},
                        failure_type="EVIDENCE_WEAK",
                    ),
                    _sample_evaluation(
                        evaluation_id="4",
                        card_id="SC-07",
                        accuracy="partial",
                        evidence="sufficient",
                        value={"interesting": False, "revisit": True},
                        failure_type="CONNECTION_FAILURE",
                    ),
                ],
            )
            stats = aggregate_evaluation_stats(path=log_path)

            assert stats["total_cards"] == 4
            assert stats["acceptance_rate"] == 0.25
            assert stats["interesting_rate"] == 0.5
            assert stats["revisit_rate"] == 0.5
            assert stats["value_rate"] == 0.75
            assert stats["evidence_sufficient_rate"] == 0.5
            assert stats["failure_distribution"] == {
                "INTERPRETATION_FAILURE": 1,
                "EVIDENCE_WEAK": 1,
                "CONNECTION_FAILURE": 1,
            }

    def test_aggregate_accepts_in_memory_list(self):
        records = [
            CardEvaluation.model_validate(_sample_evaluation()),
            CardEvaluation.model_validate(
                _sample_evaluation(
                    evaluation_id="2",
                    accuracy="wrong",
                    evidence="wrong",
                )
            ),
        ]
        stats = aggregate_evaluation_stats(records)
        assert stats["total_cards"] == 2
        assert stats["acceptance_rate"] == 0.5


class TestEmptyFileHandling:
    def test_missing_file_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "missing.jsonl"
            assert load_card_evaluations(path=log_path) == []

    def test_empty_file_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "empty.jsonl"
            log_path.touch()
            assert load_card_evaluations(path=log_path) == []

    def test_empty_aggregate_returns_zero_rates(self):
        stats = aggregate_evaluation_stats([])
        assert stats == {
            "total_cards": 0,
            "acceptance_rate": 0.0,
            "value_rate": 0.0,
            "interesting_rate": 0.0,
            "revisit_rate": 0.0,
            "evidence_sufficient_rate": 0.0,
            "failure_distribution": {},
        }

    def test_whitespace_only_lines_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "log.jsonl"
            append_card_evaluation(_sample_evaluation(), path=log_path)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("\n\n")
            loaded = load_card_evaluations(path=log_path)
            assert len(loaded) == 1
