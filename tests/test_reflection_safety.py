"""회고 안전장치 및 평가 로깅 테스트."""

import json
import tempfile
from pathlib import Path

import pytest

from conversation_to_memory.reflection.cards import (
    CardValidationError,
    ReflectionCard,
    build_card_observation_text,
    compute_card_confidence,
    validate_reflection_card,
)
from conversation_to_memory.reflection.evaluation_log import (
    EvaluationLogEntry,
    EvaluationLogStore,
)
from conversation_to_memory.reflection.evidence import (
    EvidenceItem,
    evidence_tier_for_field,
    extract_user_quotes,
    validate_evidence_items,
)
from conversation_to_memory.reflection.schema import (
    CURRENT_SCHEMA_VERSION,
    detect_schema_version,
    is_legacy_schema,
    legacy_schema_warning,
)
from conversation_to_memory.storage.local_json import LocalJsonStorage
from scripts.migrate_schema_version import migrate_memories


def _legacy_memory() -> dict:
    return {
        "topic": "구스키마",
        "emotion": "혼란",
        "summary": "요약",
        "memory_candidate": "후보",
        "conversation": [{"role": "user", "content": "원문 A"}],
    }


def _new_memory() -> dict:
    return {
        "topic": "신스키마",
        "event_summary": "요약",
        "user_emotions": ["불안"],
        "interpretation_risk": "low",
        "memory_candidate": "후보",
        "conversation": [{"role": "user", "content": "원문 B"}],
    }


class TestSchemaVersion:
    def test_legacy_memory_is_version_1(self):
        assert detect_schema_version(_legacy_memory()) == 1

    def test_new_memory_is_version_2(self):
        assert detect_schema_version(_new_memory()) == 2

    def test_new_save_defaults_to_schema_version_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalJsonStorage(directory=Path(tmp))
            filepath = storage.save(_new_memory())
            with open(filepath, encoding="utf-8") as f:
                saved = json.load(f)
            assert saved["schema_version"] == CURRENT_SCHEMA_VERSION


class TestEvidenceTier:
    def test_conversation_is_primary(self):
        assert evidence_tier_for_field("conversation") == "primary"

    def test_memory_candidate_and_summary_are_derived(self):
        assert evidence_tier_for_field("memory_candidate") == "derived"
        assert evidence_tier_for_field("summary") == "derived"

    def test_card_without_primary_evidence_fails(self):
        evidence = [
            EvidenceItem("derived", "memory_candidate", "m1", "후보 문장"),
        ]
        errors = validate_evidence_items(evidence)
        assert any("primary evidence" in e for e in errors)

    def test_derived_only_cannot_be_final_citation(self):
        evidence = [
            EvidenceItem("derived", "summary", "m1", "요약"),
            EvidenceItem("derived", "event_summary", "m1", "요약2"),
        ]
        errors = validate_evidence_items(evidence, for_final_citation=True)
        assert any("derived evidence만으로" in e for e in errors)

    def test_extract_user_quotes(self):
        memory = {
            "conversation": [
                {"role": "user", "content": "첫 발화"},
                {"role": "assistant", "content": "봇"},
                {"role": "user", "content": "둘째 발화"},
            ]
        }
        assert extract_user_quotes(memory) == ["첫 발화", "둘째 발화"]


class TestSampleSize:
    def _primary_evidence(self, memory_id: str, quote: str) -> EvidenceItem:
        return EvidenceItem("primary", "conversation", memory_id, quote)

    def test_sample_size_from_source_memory_ids(self):
        card = validate_reflection_card(
            ReflectionCard(
                card_id="c1",
                card_type="open_question",
                title="질문",
                observation="민원과 배고픔의 관계",
                source_memory_ids=["m1", "m2"],
                evidence=[
                    self._primary_evidence("m1", "불안"),
                    self._primary_evidence("m2", "배고픔"),
                ],
            ),
            {"m1": _new_memory(), "m2": _new_memory()},
        )
        assert card.sample_size == 2
        assert "n=2" in card.observation

    def test_sample_size_one_blocks_pattern_card(self):
        with pytest.raises(CardValidationError, match="패턴 카드"):
            validate_reflection_card(
                ReflectionCard(
                    card_id="c2",
                    card_type="repeated_pattern",
                    title="패턴",
                    observation="반복",
                    source_memory_ids=["m1"],
                    evidence=[self._primary_evidence("m1", "원문")],
                ),
                {"m1": _new_memory()},
            )

    def test_sample_size_one_low_confidence(self):
        card = validate_reflection_card(
            ReflectionCard(
                card_id="c3",
                card_type="single_observation",
                title="단일",
                observation="reflection_seed가 1건",
                source_memory_ids=["m1"],
                evidence=[self._primary_evidence("m1", "원문")],
            ),
            {"m1": _new_memory()},
        )
        assert card.sample_size == 1
        assert card.model_confidence == "low"

    def test_sample_size_under_three_limits_pattern_confidence(self):
        assert compute_card_confidence(2, card_type="repeated_pattern") == "low"

    def test_build_card_observation_text(self):
        text = build_card_observation_text("직장 맥락에서 불안 표현이 반복됩니다.", 4)
        assert text == "현재 기록(n=4)에서는 직장 맥락에서 불안 표현이 반복됩니다."


class TestFailureLog:
    def test_append_with_null_failure_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvaluationLogStore(log_path=Path(tmp) / "log.jsonl")
            record = store.append(
                EvaluationLogEntry(
                    report_id="reflection-2026-06-13",
                    card_id="connection-03",
                    card_type="surprising_connection",
                    source_memory_ids=["a", "b"],
                    sample_size=2,
                    failure_types=None,
                )
            )
            assert record["failure_type"] is None
            assert record["failure_types"] is None

    def test_update_failure_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvaluationLogStore(log_path=Path(tmp) / "log.jsonl")
            store.append(
                EvaluationLogEntry(
                    report_id="r1",
                    card_id="c1",
                    card_type="pattern",
                    source_memory_ids=["a"],
                    sample_size=1,
                )
            )
            updated = store.update_failure_types(
                report_id="r1",
                card_id="c1",
                failure_types=["DATA_INSUFFICIENT", "OVER_GENERALIZATION"],
                failure_notes="표본 부족",
            )
            assert updated["failure_types"] == [
                "DATA_INSUFFICIENT",
                "OVER_GENERALIZATION",
            ]
            assert updated["failure_type"] == "DATA_INSUFFICIENT"

    def test_multiple_failure_types_allowed(self):
        entry = EvaluationLogEntry(
            report_id="r2",
            card_id="c2",
            card_type="connection",
            source_memory_ids=["a", "b"],
            sample_size=2,
            failure_types=["CONNECTION_FAILURE", "OBVIOUS_INSIGHT"],
        )
        assert len(entry.failure_types) == 2


class TestLegacySchemaWarning:
    def test_legacy_warning_message(self):
        memory = _legacy_memory()
        assert is_legacy_schema(memory)
        warning = legacy_schema_warning({**memory, "_id": "2026-06-09_223830"})
        assert warning is not None
        assert "legacy_schema" in warning

    def test_legacy_lowers_confidence_on_card(self):
        card = validate_reflection_card(
            ReflectionCard(
                card_id="c4",
                card_type="open_question",
                title="질문",
                observation="legacy 메모 기반",
                source_memory_ids=["m1", "m2"],
                evidence=[
                    EvidenceItem("primary", "conversation", "m1", "q1"),
                    EvidenceItem("primary", "conversation", "m2", "q2"),
                ],
            ),
            {"m1": _legacy_memory(), "m2": _new_memory()},
        )
        assert card.legacy_schema_warnings
        assert card.model_confidence in ("low", "medium")


class TestMigration:
    def test_migration_adds_schema_version_with_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem_dir = Path(tmp) / "memories"
            mem_dir.mkdir()
            legacy_path = mem_dir / "2026-06-09_test.json"
            with open(legacy_path, "w", encoding="utf-8") as f:
                json.dump(_legacy_memory(), f, ensure_ascii=False, indent=2)

            result = migrate_memories(mem_dir)
            assert result["updated"] == 1
            backup_dir = Path(result["backup_dir"])
            assert (backup_dir / legacy_path.name).exists()

            with open(legacy_path, encoding="utf-8") as f:
                migrated = json.load(f)
            assert migrated["schema_version"] == 1
            with open(backup_dir / legacy_path.name, encoding="utf-8") as f:
                backup = json.load(f)
            assert "schema_version" not in backup


class TestPatternCardPrimaryRequirement:
    def test_pattern_requires_two_primary_evidence(self):
        errors = validate_evidence_items(
            [
                EvidenceItem("primary", "conversation", "m1", "a"),
            ],
            card_type="repeated_pattern",
        )
        assert any("최소 2개" in e for e in errors)
