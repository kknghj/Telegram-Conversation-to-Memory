"""승인된 기억을 로컬 JSON 파일로 저장."""

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from conversation_to_memory.reflection.schema import CURRENT_SCHEMA_VERSION

# 프로젝트 루트 기준 data/memories/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_MEMORIES_DIR = PROJECT_ROOT / "data" / "memories"


class MemoryStorage(ABC):
    """저장소 추상 인터페이스 — Supabase 전환 시 동일 시그니처 유지."""

    @abstractmethod
    def save(self, memory: dict) -> str:
        """기억 저장 후 식별자(파일 경로 또는 record id) 반환."""


class LocalJsonStorage(MemoryStorage):
    """MVP: 로컬 JSON 파일 저장."""

    def __init__(self, directory: Path | None = None):
        self.directory = directory or DEFAULT_MEMORIES_DIR
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, memory: dict) -> str:
        timestamp = datetime.now()
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
