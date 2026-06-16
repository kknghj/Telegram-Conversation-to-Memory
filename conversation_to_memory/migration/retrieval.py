"""회고 retrieval 필터 — evidence_quality 기반."""

from __future__ import annotations

from conversation_to_memory.migration.evidence_quality import assess_evidence_quality
from conversation_to_memory.reflection.evidence import EvidenceItem


def _evidence_quality(memory: dict) -> str:
    return memory.get("evidence_quality") or assess_evidence_quality(memory)


def can_cite_as_evidence(memory: dict) -> bool:
    """회고 카드 근거 인용 가능 여부.

    contains_derived_text 메모는 근거 인용 전면 금지.
    """
    return _evidence_quality(memory) != "contains_derived_text"


def can_use_for_existence(memory: dict) -> bool:
    """메모 존재·표본 수 판단에는 항상 사용 가능."""
    return True


def filter_citable_memories(memories_by_id: dict[str, dict]) -> dict[str, dict]:
    """근거 인용에 사용 가능한 메모만 반환."""
    return {
        mid: mem
        for mid, mem in memories_by_id.items()
        if can_cite_as_evidence(mem)
    }


def filter_for_existence(memories_by_id: dict[str, dict]) -> dict[str, dict]:
    """존재 판단용 — 전체 반환."""
    return dict(memories_by_id)


def validate_evidence_for_memory(
    item: EvidenceItem | dict,
    memories_by_id: dict[str, dict],
) -> list[str]:
    """contains_derived_text 메모의 모든 근거 인용을 차단."""
    if isinstance(item, EvidenceItem):
        memory_id = item.memory_id
        source_field = item.source_field
    else:
        memory_id = item["memory_id"]
        source_field = item["source_field"]

    memory = memories_by_id.get(memory_id)
    if not memory:
        return []

    if not can_cite_as_evidence(memory):
        return [
            f"{memory_id}: evidence_quality=contains_derived_text — "
            f"근거 인용 금지 ({source_field})."
        ]
    return []
