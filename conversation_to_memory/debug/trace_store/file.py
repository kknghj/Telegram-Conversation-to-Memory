"""Local file storage for decision traces."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from conversation_to_memory.debug.trace_store.base import TraceStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_TRACE_DIR = PROJECT_ROOT / "data" / "debug_traces"


class FileTraceStore(TraceStore):
    """MVP: decision trace를 로컬 JSON 파일로 저장."""

    def __init__(self, directory: Path | None = None):
        self.directory = directory or _resolve_trace_dir()

    def save(
        self,
        trace: dict[str, Any],
        *,
        timestamp: datetime | None = None,
        telegram_user_id: str | None = None,
    ) -> str:
        when = timestamp or datetime.now()
        self.directory.mkdir(parents=True, exist_ok=True)
        filename = when.strftime("%Y-%m-%d_%H%M%S") + ".trace.json"
        filepath = self.directory / filename

        payload = {
            "timestamp": when.isoformat(),
            **trace,
        }
        if telegram_user_id:
            payload["telegram_user_id"] = telegram_user_id

        with open(filepath, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

        return str(filepath)


def _resolve_trace_dir() -> Path:
    raw = os.getenv("DEBUG_TRACE_DIR", "").strip()
    return Path(raw) if raw else DEFAULT_TRACE_DIR
