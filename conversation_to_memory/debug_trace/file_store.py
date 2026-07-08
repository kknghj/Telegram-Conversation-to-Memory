"""로컬 파일(JSONL) 기반 decision trace 저장소."""

from __future__ import annotations

import json
from pathlib import Path

from conversation_to_memory.debug_trace.models import DecisionTrace
from conversation_to_memory.debug_trace.store import DecisionTraceStore

DEFAULT_TRACE_PATH = Path("data/debug/decision_traces.jsonl")


class FileDecisionTraceStore(DecisionTraceStore):
    """data/debug/decision_traces.jsonl에 trace를 append."""

    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_TRACE_PATH

    def save(self, trace: DecisionTrace) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(trace.to_row(), ensure_ascii=False) + "\n")
