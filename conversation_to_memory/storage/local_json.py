"""승인된 기억을 로컬 JSON 파일로 저장."""

import json
from datetime import datetime
from pathlib import Path

from conversation_to_memory.reflection.schema import CURRENT_SCHEMA_VERSION
from conversation_to_memory.storage.base import MemoryStorage

# 프로젝트 루트 기준 data/memories/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_MEMORIES_DIR = PROJECT_ROOT / "data" / "memories"


class LocalJsonStorage(MemoryStorage):
    """MVP: 로컬 JSON 파일 저장."""

    def __init__(self, directory: Path | None = None):
        self.directory = directory or DEFAULT_MEMORIES_DIR
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, memory: dict, *, telegram_user_id: str | None = None) -> str:
        timestamp = _resolve_save_timestamp(memory)
        filename = timestamp.strftime("%Y-%m-%d_%H%M%S") + ".json"
        filepath = self.directory / filename

        payload = {
            "timestamp": timestamp.isoformat(),
            **memory,
            "schema_version": memory.get("schema_version", CURRENT_SCHEMA_VERSION),
            "approved": True,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        return str(filepath)


def _resolve_save_timestamp(memory: dict) -> datetime:
    for candidate in (
        memory.get("timestamp"),
        (memory.get("metadata") or {}).get("recorded_at"),
    ):
        parsed = _coerce_datetime(candidate)
        if parsed is not None:
            return parsed
    return datetime.now()


def _coerce_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        normalized = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
    return None
