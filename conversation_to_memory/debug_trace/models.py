"""Decision trace 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

RAW_INPUT_PREVIEW_MAX_LENGTH = 200


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DecisionTrace:
    """후속 질문·프로젝트 태그 판단 과정을 기록하는 trace 1건."""

    memory_id: str | None = None
    source: str = "telegram"
    environment: str = "production"
    prompt_version: str | None = None
    model: str | None = None
    question_trace: dict[str, Any] | None = None
    project_trace: dict[str, Any] | None = None
    tag_trace: dict[str, Any] | None = None
    raw_input_preview: str | None = None
    error: str | None = None
    created_at: str = field(default_factory=_utc_now_iso)

    def to_row(self) -> dict[str, Any]:
        """Supabase insert / JSONL 직렬화용 dict."""
        return {
            "memory_id": self.memory_id,
            "source": self.source,
            "environment": self.environment,
            "prompt_version": self.prompt_version,
            "model": self.model,
            "question_trace": self.question_trace,
            "project_trace": self.project_trace,
            "tag_trace": self.tag_trace,
            "raw_input_preview": self.raw_input_preview,
            "error": self.error,
            "created_at": self.created_at,
        }
