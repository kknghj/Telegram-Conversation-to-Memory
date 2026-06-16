"""회고 카드 검증, sample_size, 신뢰도 규칙."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from conversation_to_memory.reflection.evidence import (
    EvidenceItem,
    validate_evidence_items,
)
from conversation_to_memory.reflection.schema import (
    detect_schema_version,
    is_legacy_schema,
    legacy_schema_warning,
)

PATTERN_CARD_TYPES = frozenset({"repeated_pattern", "pattern"})
CONNECTION_CARD_TYPES = frozenset({"surprising_connection", "connection"})
SINGLE_OBSERVATION_TYPES = frozenset(
    {"open_question", "data_insufficient", "single_observation"}
)


class CardValidationError(ValueError):
    """회고 카드가 안전 규칙을 위반할 때."""


@dataclass
class ReflectionCard:
    card_id: str
    card_type: str
    title: str
    observation: str
    source_memory_ids: list[str]
    evidence: list[EvidenceItem | dict]
    sample_size: int = 0
    evidence_tiers_used: list[str] = field(default_factory=list)
    schema_versions_used: list[int] = field(default_factory=list)
    model_confidence: str = "medium"
    legacy_schema_warnings: list[str] = field(default_factory=list)
    hypothesis: str = ""
    counter_interpretation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "card_type": self.card_type,
            "title": self.title,
            "observation": self.observation,
            "source_memory_ids": self.source_memory_ids,
            "sample_size": self.sample_size,
            "evidence_tiers_used": self.evidence_tiers_used,
            "schema_versions_used": self.schema_versions_used,
            "model_confidence": self.model_confidence,
            "legacy_schema_warnings": self.legacy_schema_warnings,
            "evidence": [
                e.to_dict() if isinstance(e, EvidenceItem) else e for e in self.evidence
            ],
            "hypothesis": self.hypothesis,
            "counter_interpretation": self.counter_interpretation,
        }


def build_card_observation_text(observation: str, sample_size: int) -> str:
    """사용자-facing 문장에 표본 수 n을 포함한다."""
    prefix = f"현재 기록(n={sample_size})에서는 "
    if observation.startswith("현재 "):
        return observation.replace("현재 ", prefix, 1)
    return f"{prefix}{observation}"


def compute_card_confidence(
    sample_size: int,
    *,
    has_legacy_schema: bool = False,
    card_type: str = "",
) -> str:
    if sample_size <= 1:
        return "low"
    if sample_size < 3:
        base = "low" if has_legacy_schema else "medium"
        if card_type in PATTERN_CARD_TYPES | CONNECTION_CARD_TYPES:
            return "low"
        return base
    if has_legacy_schema:
        return "medium"
    return "medium"


def _collect_metadata(
    source_memory_ids: list[str],
    evidence: list[EvidenceItem | dict],
    memories_by_id: dict[str, dict],
) -> tuple[list[str], list[int], list[str]]:
    tiers: set[str] = set()
    versions: set[int] = set()
    warnings: list[str] = []

    for item in evidence:
        tier = item.evidence_tier if isinstance(item, EvidenceItem) else item["evidence_tier"]
        tiers.add(tier)

    for memory_id in source_memory_ids:
        memory = memories_by_id.get(memory_id)
        if not memory:
            continue
        versions.add(detect_schema_version(memory))
        warning = legacy_schema_warning({**memory, "_id": memory_id})
        if warning:
            warnings.append(warning)

    return sorted(tiers), sorted(versions), warnings


def validate_reflection_card(
    card: ReflectionCard | dict,
    memories_by_id: dict[str, dict],
) -> ReflectionCard:
    """카드 안전 규칙 검증. 통과 시 sample_size·신뢰도 등을 채운 ReflectionCard 반환."""
    if isinstance(card, dict):
        evidence = card.get("evidence") or []
        card_obj = ReflectionCard(
            card_id=card["card_id"],
            card_type=card["card_type"],
            title=card.get("title", ""),
            observation=card.get("observation", ""),
            source_memory_ids=list(card.get("source_memory_ids") or []),
            evidence=evidence,
            hypothesis=card.get("hypothesis", ""),
            counter_interpretation=card.get("counter_interpretation", ""),
        )
    else:
        card_obj = card

    sample_size = len(card_obj.source_memory_ids)
    if sample_size == 0:
        raise CardValidationError("source_memory_ids가 비어 있습니다.")

    card_obj.sample_size = sample_size

    if sample_size == 1 and card_obj.card_type in PATTERN_CARD_TYPES:
        raise CardValidationError(
            "sample_size=1에서는 패턴 카드를 생성할 수 없습니다. "
            "단일 관찰(single_observation) 또는 열린 질문(open_question)을 사용하세요."
        )

    if sample_size == 1 and card_obj.card_type in CONNECTION_CARD_TYPES:
        raise CardValidationError(
            "sample_size=1에서는 연결(connection) 카드를 생성할 수 없습니다."
        )

    evidence_errors = validate_evidence_items(
        card_obj.evidence,
        card_type=card_obj.card_type,
        for_final_citation=True,
    )
    from conversation_to_memory.migration.retrieval import validate_evidence_for_memory

    for item in card_obj.evidence:
        evidence_errors.extend(
            validate_evidence_for_memory(item, memories_by_id)
        )
    if evidence_errors:
        raise CardValidationError("; ".join(evidence_errors))

    tiers, versions, warnings = _collect_metadata(
        card_obj.source_memory_ids,
        card_obj.evidence,
        memories_by_id,
    )
    card_obj.evidence_tiers_used = tiers
    card_obj.schema_versions_used = versions
    card_obj.legacy_schema_warnings = warnings

    has_legacy = any(is_legacy_schema(memories_by_id[mid]) for mid in card_obj.source_memory_ids if mid in memories_by_id)
    card_obj.model_confidence = compute_card_confidence(
        sample_size,
        has_legacy_schema=has_legacy,
        card_type=card_obj.card_type,
    )

    card_obj.observation = build_card_observation_text(card_obj.observation, sample_size)
    return card_obj
