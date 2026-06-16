"""schema_version 백필."""

from __future__ import annotations

from conversation_to_memory.reflection.schema import detect_schema_version


def backfill_schema_version(memory: dict) -> tuple[bool, int]:
    """schema_version이 없으면 판별 결과를 붙인다.

    Returns:
        (migrated, schema_version) — migrated=True면 이번 호출에서 필드를 추가했다.
    """
    if memory.get("schema_version") in (1, 2):
        return False, int(memory["schema_version"])

    version = detect_schema_version(memory)
    memory["schema_version"] = version
    memory["migration_status"] = "backfilled"
    return True, version
