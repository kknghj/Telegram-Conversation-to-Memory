"""회고 근거 evidence tier 판별 및 검증."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EvidenceTier = Literal["primary", "derived"]

PRIMARY_SOURCE_FIELDS = frozenset({"conversation"})
DERIVED_SOURCE_FIELDS = frozenset(
    {
        "user_emotions",
        "emotion_evidence",
        "event_summary",
        "memory_candidate",
        "summary",
        "emerging_themes",
        "key_phrases",
        "model_interpretation",
        "tags",
        "people",
        "projects",
    }
)
KNOWN_SOURCE_FIELDS = PRIMARY_SOURCE_FIELDS | DERIVED_SOURCE_FIELDS

PATTERN_CARD_TYPES = frozenset(
    {"repeated_pattern", "pattern", "surprising_connection", "connection"}
)


@dataclass(frozen=True)
class EvidenceItem:
    evidence_tier: EvidenceTier
    source_field: str
    memory_id: str
    quote: str = ""

    def to_dict(self) -> dict:
        payload = {
            "evidence_tier": self.evidence_tier,
            "source_field": self.source_field,
            "memory_id": self.memory_id,
        }
        if self.quote:
            payload["quote"] = self.quote
        return payload


def evidence_tier_for_field(source_field: str) -> EvidenceTier:
    if source_field in PRIMARY_SOURCE_FIELDS:
        return "primary"
    if source_field in DERIVED_SOURCE_FIELDS:
        return "derived"
    raise ValueError(f"알 수 없는 source_field: {source_field}")


def extract_user_quotes(memory: dict) -> list[str]:
    quotes: list[str] = []
    for turn in memory.get("conversation") or []:
        if turn.get("role") == "user":
            content = str(turn.get("content") or "").strip()
            if content:
                quotes.append(content)
    return quotes


def has_primary_evidence(evidence_items: list[EvidenceItem | dict]) -> bool:
    return any(
        (item.evidence_tier if isinstance(item, EvidenceItem) else item["evidence_tier"])
        == "primary"
        for item in evidence_items
    )


def _as_evidence_item(item: EvidenceItem | dict) -> EvidenceItem:
    if isinstance(item, EvidenceItem):
        return item
    return EvidenceItem(
        evidence_tier=item["evidence_tier"],
        source_field=item["source_field"],
        memory_id=item["memory_id"],
        quote=str(item.get("quote") or ""),
    )


def validate_evidence_items(
    evidence_items: list[EvidenceItem | dict],
    *,
    card_type: str = "",
    for_final_citation: bool = True,
) -> list[str]:
    """근거 목록 검증. 문제 메시지 목록을 반환한다 (비어 있으면 통과)."""
    errors: list[str] = []
    if not evidence_items:
        errors.append("근거(evidence)가 없습니다.")
        return errors

    normalized = [_as_evidence_item(item) for item in evidence_items]

    for item in normalized:
        if item.source_field not in KNOWN_SOURCE_FIELDS:
            errors.append(f"알 수 없는 source_field: {item.source_field}")
            continue
        expected = evidence_tier_for_field(item.source_field)
        if item.evidence_tier != expected:
            errors.append(
                f"{item.source_field}는 {expected}이어야 하는데 "
                f"{item.evidence_tier}로 표시되었습니다."
            )

    if for_final_citation and not has_primary_evidence(normalized):
        errors.append(
            "primary evidence(conversation 원문) 없이 회고 카드를 만들 수 없습니다."
        )

    primary_items = [i for i in normalized if i.evidence_tier == "primary"]
    derived_only = not primary_items and bool(normalized)

    if for_final_citation and derived_only:
        errors.append(
            "derived evidence만으로 최종 근거 인용을 구성할 수 없습니다."
        )

    if card_type in PATTERN_CARD_TYPES and len(primary_items) < 2:
        errors.append(
            "반복 패턴·연결 카드에는 primary evidence가 최소 2개 필요합니다."
        )

    return errors
