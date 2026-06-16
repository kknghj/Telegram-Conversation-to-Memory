"""회고 카드 평가 observation log 저장 및 집계."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import ValidationError

from conversation_to_memory.reflection.evaluation_models import (
    Action,
    CardEvaluation,
    EvaluationStats,
    FailureType,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_EVALUATION_PATH = PROJECT_ROOT / "data" / "evaluation" / "reflection_failures.jsonl"


def _try_sync_to_supabase(record: CardEvaluation) -> None:
    """JSONL 저장 후 optional Supabase mirror sync. 실패해도 호출자에게 전파하지 않는다."""
    try:
        from app.evaluation_supabase import is_supabase_configured, sync_evaluation_to_supabase

        if not is_supabase_configured():
            return
        if not sync_evaluation_to_supabase(record):
            logger.warning(
                "Supabase sync failed after JSONL append: %s/%s",
                record.evaluation_id,
                record.card_id,
            )
    except Exception:
        logger.warning(
            "Supabase sync error after JSONL append: %s/%s",
            record.evaluation_id,
            record.card_id,
            exc_info=True,
        )


def append_card_evaluation(
    evaluation: CardEvaluation | dict,
    *,
    path: Path | None = None,
    sync_supabase: bool = True,
) -> CardEvaluation:
    """카드 평가 1건을 JSONL에 append한다. Supabase는 optional mirror."""
    record = (
        evaluation
        if isinstance(evaluation, CardEvaluation)
        else CardEvaluation.model_validate(evaluation)
    )
    log_path = path or DEFAULT_EVALUATION_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")

    if sync_supabase:
        _try_sync_to_supabase(record)

    return record


def load_card_evaluations(*, path: Path | None = None) -> list[CardEvaluation]:
    """JSONL에서 모든 카드 평가를 로드한다. 빈·없는 파일은 [] 반환."""
    log_path = path or DEFAULT_EVALUATION_PATH
    if not log_path.exists() or log_path.stat().st_size == 0:
        return []

    evaluations: list[CardEvaluation] = []
    with open(log_path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                evaluations.append(CardEvaluation.model_validate_json(stripped))
            except ValidationError as exc:
                raise ValidationError.from_exception_data(
                    title=f"Invalid evaluation at {log_path}:{line_no}",
                    line_errors=exc.errors(),
                ) from exc
    return evaluations


def aggregate_evaluation_stats(
    evaluations: list[CardEvaluation] | None = None,
    *,
    path: Path | None = None,
) -> EvaluationStats:
    """평가 로그 집계 — acceptance, value, evidence, failure 분포."""
    records = (
        evaluations
        if evaluations is not None
        else load_card_evaluations(path=path)
    )
    total = len(records)
    if total == 0:
        return {
            "total_cards": 0,
            "acceptance_rate": 0.0,
            "value_rate": 0.0,
            "interesting_rate": 0.0,
            "revisit_rate": 0.0,
            "evidence_sufficient_rate": 0.0,
            "failure_distribution": {},
        }

    keep_count = sum(1 for r in records if r.action == Action.KEEP)
    interesting_count = sum(1 for r in records if r.value.interesting)
    revisit_count = sum(1 for r in records if r.value.revisit)
    value_count = sum(
        1 for r in records if r.value.interesting or r.value.revisit
    )
    sufficient_count = sum(
        1 for r in records if r.evidence.value == "sufficient"
    )

    failure_distribution: dict[str, int] = {}
    for record in records:
        if record.failure_type is not None:
            key = record.failure_type.value
            failure_distribution[key] = failure_distribution.get(key, 0) + 1

    return {
        "total_cards": total,
        "acceptance_rate": round(keep_count / total, 3),
        "value_rate": round(value_count / total, 3),
        "interesting_rate": round(interesting_count / total, 3),
        "revisit_rate": round(revisit_count / total, 3),
        "evidence_sufficient_rate": round(sufficient_count / total, 3),
        "failure_distribution": failure_distribution,
    }


__all__ = [
    "DEFAULT_EVALUATION_PATH",
    "append_card_evaluation",
    "load_card_evaluations",
    "aggregate_evaluation_stats",
    "FailureType",
]
