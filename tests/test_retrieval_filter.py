"""retrieval 필터 — evidence_quality 기반."""

import pytest

from conversation_to_memory.migration.evidence_quality import assess_evidence_quality
from conversation_to_memory.migration.retrieval import (
    can_cite_as_evidence,
    can_use_for_existence,
    filter_citable_memories,
    validate_evidence_for_memory,
)
from conversation_to_memory.reflection.cards import (
    CardValidationError,
    ReflectionCard,
    validate_reflection_card,
)
from conversation_to_memory.reflection.evidence import EvidenceItem


def _clean_memory() -> dict:
    return {
        "schema_version": 2,
        "evidence_quality": "primary_only",
        "event_summary": "요약",
        "memory_candidate": "원문과 동일한 후보",
        "conversation": [{"role": "user", "content": "원문과 동일한 후보"}],
    }


def _derived_memory() -> dict:
    return {
        "schema_version": 1,
        "summary": "요약",
        "memory_candidate": "앞으로도 지속적으로 노력하고 싶다.",
        "conversation": [{"role": "user", "content": "잘 모르겠어."}],
    }


class TestEvidenceQualityAssessment:
    def test_legacy_is_contains_derived_text(self):
        assert assess_evidence_quality(_derived_memory()) == "contains_derived_text"

    def test_clean_memory_is_primary_only(self):
        assert assess_evidence_quality(_clean_memory()) == "primary_only"


class TestRetrievalFilter:
    def test_cannot_cite_derived_memory(self):
        assert can_cite_as_evidence(_derived_memory()) is False

    def test_can_cite_clean_memory(self):
        assert can_cite_as_evidence(_clean_memory()) is True

    def test_existence_always_allowed(self):
        assert can_use_for_existence(_derived_memory()) is True

    def test_filter_citable_excludes_derived(self):
        memories = {"m1": _clean_memory(), "m2": _derived_memory()}
        citable = filter_citable_memories(memories)
        assert "m1" in citable
        assert "m2" not in citable

    def test_validate_evidence_blocks_derived_memory(self):
        item = EvidenceItem("primary", "conversation", "m2", "잘 모르겠어.")
        errors = validate_evidence_for_memory(item, {"m2": _derived_memory()})
        assert len(errors) == 1
        assert "contains_derived_text" in errors[0]


class TestCardValidationWithRetrievalFilter:
    def test_card_with_derived_memory_evidence_fails(self):
        derived = _derived_memory()
        derived["evidence_quality"] = "contains_derived_text"
        with pytest.raises(CardValidationError, match="contains_derived_text"):
            validate_reflection_card(
                ReflectionCard(
                    card_id="c1",
                    card_type="open_question",
                    title="질문",
                    observation="legacy 메모",
                    source_memory_ids=["m2"],
                    evidence=[
                        EvidenceItem("primary", "conversation", "m2", "잘 모르겠어."),
                    ],
                ),
                {"m2": derived},
            )

    def test_sample_size_counts_derived_for_existence(self):
        """contains_derived_text 메모도 source_memory_ids 표본 수에는 포함."""
        derived = _derived_memory()
        derived["evidence_quality"] = "contains_derived_text"
        clean = _clean_memory()

        card = validate_reflection_card(
            ReflectionCard(
                card_id="c2",
                card_type="open_question",
                title="질문",
                observation="clean 메모만 인용",
                source_memory_ids=["m1", "m2"],
                evidence=[
                    EvidenceItem("primary", "conversation", "m1", "원문"),
                ],
            ),
            {"m1": clean, "m2": derived},
        )
        assert card.sample_size == 2
