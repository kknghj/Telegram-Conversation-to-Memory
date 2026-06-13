"""메모 schema_version 판별 및 정규화."""

from __future__ import annotations

CURRENT_SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1


def detect_schema_version(memory: dict) -> int:
    """저장된 메모 dict에서 schema_version을 판별한다."""
    explicit = memory.get("schema_version")
    if explicit in (1, 2):
        return int(explicit)

    has_new = "event_summary" in memory or "user_emotions" in memory
    has_old = "summary" in memory or "emotion" in memory

    if has_new and ("interpretation_risk" in memory or "event_summary" in memory):
        return CURRENT_SCHEMA_VERSION
    if has_old and not has_new:
        return LEGACY_SCHEMA_VERSION
    if has_new:
        return CURRENT_SCHEMA_VERSION
    return LEGACY_SCHEMA_VERSION


def is_legacy_schema(memory: dict) -> bool:
    return detect_schema_version(memory) == LEGACY_SCHEMA_VERSION


def legacy_schema_warning(memory: dict) -> str | None:
    if not is_legacy_schema(memory):
        return None
    memory_id = memory.get("_id") or memory.get("timestamp") or "unknown"
    return (
        f"legacy_schema: schema_version=1 메모({memory_id})는 "
        "derived 필드 오염 가능성이 있어 신뢰도를 낮게 표시합니다."
    )


def ensure_schema_version(memory: dict) -> dict:
    """schema_version 필드가 없으면 판별 결과를 붙인다 (in-place)."""
    if memory.get("schema_version") not in (1, 2):
        memory["schema_version"] = detect_schema_version(memory)
    return memory
