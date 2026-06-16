"""Supabase remote mirror for reflection evaluation observation logs."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from conversation_to_memory.reflection.evaluation_models import CardEvaluation
from conversation_to_memory.reflection.evaluation_storage import load_card_evaluations

logger = logging.getLogger(__name__)

TABLE_NAME = "reflection_evaluations"
UPSERT_CONFLICT_COLUMNS = "evaluation_id,card_id"


def get_supabase_client():
    """SUPABASE_URL + SUPABASE_SECRET_KEY가 있으면 클라이언트를 반환한다."""
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SECRET_KEY", "").strip()
    if not url or not key:
        return None

    from supabase import create_client

    return create_client(url, key)


def evaluation_to_supabase_row(evaluation: CardEvaluation) -> dict[str, Any]:
    """CardEvaluation → reflection_evaluations 행 dict."""
    return {
        "evaluation_id": evaluation.evaluation_id,
        "evaluated_at": evaluation.evaluated_at,
        "memory_count": evaluation.memory_count,
        "card_id": evaluation.card_id,
        "card_type": evaluation.card_type,
        "accuracy": evaluation.accuracy.value,
        "interesting": evaluation.value.interesting,
        "revisit": evaluation.value.revisit,
        "evidence": evaluation.evidence.value,
        "failure_type": (
            evaluation.failure_type.value if evaluation.failure_type else None
        ),
        "user_comment": evaluation.user_comment or None,
        "action": evaluation.action.value if evaluation.action else None,
        "raw": evaluation.model_dump(mode="json"),
    }


def sync_evaluation_to_supabase(evaluation: CardEvaluation) -> bool:
    """
    evaluation 1건을 reflection_evaluations에 upsert한다.
    성공하면 True. 실패하면 예외를 밖으로 던지지 말고 False 반환.
    """
    try:
        client = get_supabase_client()
        if client is None:
            return False

        row = evaluation_to_supabase_row(evaluation)
        client.table(TABLE_NAME).upsert(
            row,
            on_conflict=UPSERT_CONFLICT_COLUMNS,
        ).execute()
        return True
    except Exception:
        logger.warning(
            "Supabase evaluation sync failed for %s/%s",
            evaluation.evaluation_id,
            evaluation.card_id,
            exc_info=True,
        )
        return False


def sync_jsonl_to_supabase(jsonl_path: str | Path) -> dict[str, Any]:
    """
    JSONL 전체를 읽어 Supabase에 upsert한다.

    반환:
    {
      "total": 14,
      "synced": 14,
      "failed": 0,
      "failed_items": []
    }
    """
    path = Path(jsonl_path)
    evaluations = load_card_evaluations(path=path)
    synced = 0
    failed_items: list[dict[str, str]] = []

    for evaluation in evaluations:
        if sync_evaluation_to_supabase(evaluation):
            synced += 1
        else:
            failed_items.append(
                {
                    "evaluation_id": evaluation.evaluation_id,
                    "card_id": evaluation.card_id,
                }
            )

    total = len(evaluations)
    return {
        "total": total,
        "synced": synced,
        "failed": total - synced,
        "failed_items": failed_items,
    }


def load_evaluations_from_supabase(
    evaluation_id: str | None = None,
) -> list[dict[str, Any]]:
    """Supabase에서 평가 로그를 조회한다. 환경변수 없으면 [] 반환."""
    try:
        client = get_supabase_client()
        if client is None:
            return []

        query = client.table(TABLE_NAME).select("*")
        if evaluation_id is not None:
            query = query.eq("evaluation_id", evaluation_id)
        response = query.order("evaluated_at").execute()
        return list(response.data or [])
    except Exception:
        logger.warning(
            "Supabase evaluation load failed (evaluation_id=%s)",
            evaluation_id,
            exc_info=True,
        )
        return []


def is_supabase_configured() -> bool:
    """Supabase sync 가능 여부."""
    return get_supabase_client() is not None
