"""마이그레이션 전후 통계 수집."""

from __future__ import annotations

from collections import Counter
from typing import Any


def collect_migration_stats(memories: list[dict]) -> dict[str, Any]:
    total = len(memories)

    schema = Counter(m.get("schema_version", "missing") for m in memories)
    memory_type = Counter(m.get("memory_type", "missing") for m in memories)
    mt_confidence = Counter(m.get("memory_type_confidence", "missing") for m in memories)
    evidence = Counter(m.get("evidence_quality", "missing") for m in memories)
    migration_status = Counter(m.get("migration_status", "none") for m in memories)

    derived_count = evidence.get("contains_derived_text", 0)
    derived_ratio = derived_count / total if total else 0.0

    citable = sum(
        1 for m in memories if m.get("evidence_quality") == "primary_only"
    )
    blocked = derived_count

    return {
        "total": total,
        "schema_version": dict(schema),
        "memory_type": dict(memory_type),
        "memory_type_confidence": dict(mt_confidence),
        "evidence_quality": dict(evidence),
        "migration_status": dict(migration_status),
        "derived_text_count": derived_count,
        "derived_text_ratio": round(derived_ratio, 3),
        "retrieval": {
            "citable_for_evidence": citable,
            "blocked_for_derived_citation": blocked,
            "available_for_existence": total,
        },
    }
