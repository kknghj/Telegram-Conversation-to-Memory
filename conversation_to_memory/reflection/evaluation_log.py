"""회고 카드 평가 failure log (JSONL)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_EVALUATION_DIR = PROJECT_ROOT / "data" / "evaluation"

FAILURE_TYPES = frozenset(
    {
        "SEARCH_FAILURE",
        "CONNECTION_FAILURE",
        "INTERPRETATION_FAILURE",
        "OBVIOUS_INSIGHT",
        "OVER_GENERALIZATION",
        "DATA_INSUFFICIENT",
        "DUPLICATED_CARD",
    }
)


@dataclass
class EvaluationLogEntry:
    report_id: str
    card_id: str
    card_type: str
    source_memory_ids: list[str]
    sample_size: int
    evidence_tiers_used: list[str] = field(default_factory=list)
    schema_versions_used: list[int] = field(default_factory=list)
    model_confidence: str = "medium"
    failure_types: list[str] | None = None
    failure_notes: str | None = None
    user_accuracy: str | None = None
    user_interesting: str | None = None
    user_revisit: str | None = None
    user_grounding: str | None = None
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if self.failure_types is not None:
            self._validate_failure_types(self.failure_types)

    @staticmethod
    def _validate_failure_types(types: list[str]) -> None:
        invalid = [t for t in types if t not in FAILURE_TYPES]
        if invalid:
            raise ValueError(f"알 수 없는 failure_type: {invalid}")

    @property
    def failure_type(self) -> str | None:
        if not self.failure_types:
            return None
        return self.failure_types[0]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["failure_type"] = self.failure_type
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationLogEntry:
        failure_types = data.get("failure_types")
        if failure_types is None and data.get("failure_type"):
            failure_types = [data["failure_type"]]
        return cls(
            report_id=data["report_id"],
            card_id=data["card_id"],
            card_type=data["card_type"],
            source_memory_ids=list(data["source_memory_ids"]),
            sample_size=int(data["sample_size"]),
            evidence_tiers_used=list(data.get("evidence_tiers_used") or []),
            schema_versions_used=list(data.get("schema_versions_used") or []),
            model_confidence=str(data.get("model_confidence") or "medium"),
            failure_types=failure_types,
            failure_notes=data.get("failure_notes"),
            user_accuracy=data.get("user_accuracy"),
            user_interesting=data.get("user_interesting"),
            user_revisit=data.get("user_revisit"),
            user_grounding=data.get("user_grounding"),
            created_at=str(data.get("created_at") or ""),
        )


class EvaluationLogStore:
    """JSONL 기반 평가 로그 저장소."""

    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path or (DEFAULT_EVALUATION_DIR / "reflection_failures.jsonl")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: EvaluationLogEntry | dict) -> dict[str, Any]:
        record = entry.to_dict() if isinstance(entry, EvaluationLogEntry) else EvaluationLogEntry.from_dict(entry).to_dict()
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def load_all(self) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    def update_failure_types(
        self,
        *,
        report_id: str,
        card_id: str,
        failure_types: list[str] | None,
        failure_notes: str | None = None,
        **user_fields: Any,
    ) -> dict[str, Any]:
        entries = self.load_all()
        updated: dict[str, Any] | None = None
        for entry in entries:
            if entry["report_id"] == report_id and entry["card_id"] == card_id:
                if failure_types is not None:
                    EvaluationLogEntry._validate_failure_types(failure_types)
                    entry["failure_types"] = failure_types
                    entry["failure_type"] = failure_types[0] if failure_types else None
                if failure_notes is not None:
                    entry["failure_notes"] = failure_notes
                for key, value in user_fields.items():
                    if value is not None:
                        entry[key] = value
                updated = entry

        if updated is None:
            raise KeyError(f"로그를 찾을 수 없습니다: {report_id}/{card_id}")

        self._rewrite(entries)
        return updated

    def _rewrite(self, entries: list[dict[str, Any]]) -> None:
        with open(self.log_path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
