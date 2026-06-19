"""Supabase remote mirror for MVP round evaluation snapshots."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from conversation_to_memory.reflection.evaluation_models import CardEvaluation

from app.evaluation_supabase import (
    TABLE_NAME as REFLECTION_TABLE,
    UPSERT_CONFLICT_COLUMNS as REFLECTION_UPSERT_KEY,
    get_supabase_client,
    is_supabase_configured,
)

logger = logging.getLogger(__name__)

MVP_TABLE_NAME = "mvp_evaluations"
MVP_UPSERT_CONFLICT_COLUMN = "evaluation_id"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MVP_JSON = (
    PROJECT_ROOT / "data" / "evaluation" / "mvp_round2_2026-06-19.json"
)
DEFAULT_PATTERN_CARDS_JSONL = (
    PROJECT_ROOT / "data" / "evaluation" / "reflection_evaluations.jsonl"
)


def load_mvp_evaluation(path: str | Path | None = None) -> dict[str, Any]:
    """Load MVP evaluation JSON snapshot."""
    json_path = Path(path or DEFAULT_MVP_JSON)
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


def mvp_evaluation_to_supabase_row(data: dict[str, Any]) -> dict[str, Any]:
    """MVP evaluation dict → mvp_evaluations table row."""
    return {
        "evaluation_id": data["evaluation_id"],
        "evaluation_type": data["evaluation_type"],
        "round": data["round"],
        "evaluated_at": data["evaluated_at"],
        "memory_count": data["memory_count"],
        "previous_memory_count": data.get("previous_memory_count"),
        "new_memory_count": data.get("new_memory_count"),
        "final_judgment": data["final_judgment"],
        "score": data.get("score"),
        "user_validated": data.get("user_validated", False),
        "user_validation_summary": data.get("user_validation_summary"),
        "top_insights": data.get("top_insights"),
        "main_limitation": data.get("main_limitation"),
        "next_milestone": data.get("next_milestone"),
        "payload": data,
    }


def load_mvp_pattern_card_evaluations(
    path: str | Path | None = None,
    *,
    evaluation_id: str | None = None,
) -> list[dict[str, Any]]:
    """Load MVP pattern card rows from reflection_evaluations.jsonl."""
    jsonl_path = Path(path or DEFAULT_PATTERN_CARDS_JSONL)
    if not jsonl_path.exists() or jsonl_path.stat().st_size == 0:
        return []

    rows: list[dict[str, Any]] = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON at {jsonl_path}:{line_no}"
                ) from exc
            if evaluation_id and row.get("evaluation_id") != evaluation_id:
                continue
            rows.append(row)
    return rows


def mvp_pattern_card_to_reflection_row(row: dict[str, Any]) -> dict[str, Any]:
    """MVP pattern card JSONL row → reflection_evaluations table row."""
    card_evaluation = CardEvaluation.model_validate(
        {
            "evaluation_id": row["evaluation_id"],
            "evaluated_at": row["evaluated_at"],
            "memory_count": row["memory_count"],
            "card_id": row["card_id"],
            "card_type": row["card_type"],
            "accuracy": row["accuracy"],
            "value": row["value"],
            "evidence": row["evidence"],
            "failure_type": row.get("failure_type"),
            "user_comment": row.get("user_comment", ""),
        }
    )
    supabase_row = {
        "evaluation_id": card_evaluation.evaluation_id,
        "evaluated_at": card_evaluation.evaluated_at,
        "memory_count": card_evaluation.memory_count,
        "card_id": card_evaluation.card_id,
        "card_type": card_evaluation.card_type,
        "accuracy": card_evaluation.accuracy.value,
        "interesting": card_evaluation.value.interesting,
        "revisit": card_evaluation.value.revisit,
        "evidence": card_evaluation.evidence.value,
        "failure_type": (
            card_evaluation.failure_type.value
            if card_evaluation.failure_type
            else None
        ),
        "user_comment": card_evaluation.user_comment or None,
        "action": card_evaluation.action.value if card_evaluation.action else None,
        "raw": row,
    }
    return supabase_row


def sync_mvp_evaluation_to_supabase(
    data: dict[str, Any],
    *,
    dry_run: bool = False,
) -> bool:
    """Upsert one MVP evaluation snapshot. Returns True on success."""
    row = mvp_evaluation_to_supabase_row(data)
    if dry_run:
        return True

    try:
        client = get_supabase_client()
        if client is None:
            return False

        client.table(MVP_TABLE_NAME).upsert(
            row,
            on_conflict=MVP_UPSERT_CONFLICT_COLUMN,
        ).execute()
        return True
    except Exception:
        logger.warning(
            "Supabase MVP evaluation sync failed for %s",
            data.get("evaluation_id"),
            exc_info=True,
        )
        return False


def sync_mvp_pattern_cards_to_supabase(
    rows: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Upsert MVP pattern cards into reflection_evaluations."""
    synced = 0
    failed_items: list[dict[str, str]] = []

    for row in rows:
        supabase_row = mvp_pattern_card_to_reflection_row(row)
        if dry_run:
            synced += 1
            continue

        try:
            client = get_supabase_client()
            if client is None:
                failed_items.append(
                    {
                        "evaluation_id": row.get("evaluation_id", ""),
                        "card_id": row.get("card_id", ""),
                    }
                )
                continue

            client.table(REFLECTION_TABLE).upsert(
                supabase_row,
                on_conflict=REFLECTION_UPSERT_KEY,
            ).execute()
            synced += 1
        except Exception:
            logger.warning(
                "Supabase pattern card sync failed for %s/%s",
                row.get("evaluation_id"),
                row.get("card_id"),
                exc_info=True,
            )
            failed_items.append(
                {
                    "evaluation_id": row.get("evaluation_id", ""),
                    "card_id": row.get("card_id", ""),
                }
            )

    total = len(rows)
    return {
        "total": total,
        "synced": synced,
        "failed": total - synced,
        "failed_items": failed_items,
    }


def sync_mvp_bundle_to_supabase(
    *,
    mvp_json_path: str | Path | None = None,
    pattern_cards_path: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Sync MVP round snapshot + related pattern card evaluations.

    Returns summary dict for CLI output.
    """
    mvp_data = load_mvp_evaluation(mvp_json_path)
    evaluation_id = mvp_data["evaluation_id"]
    pattern_rows = load_mvp_pattern_card_evaluations(
        pattern_cards_path,
        evaluation_id=evaluation_id,
    )

    mvp_ok = sync_mvp_evaluation_to_supabase(mvp_data, dry_run=dry_run)
    pattern_result = sync_mvp_pattern_cards_to_supabase(
        pattern_rows,
        dry_run=dry_run,
    )

    loaded_mvp = 1
    upserted_mvp = 1 if mvp_ok or dry_run else 0
    skipped_mvp = 0 if upserted_mvp else 1

    return {
        "loaded_mvp_evaluations": loaded_mvp,
        "upserted_mvp": upserted_mvp,
        "skipped_mvp": skipped_mvp,
        "mvp_evaluation_id": evaluation_id,
        "pattern_cards": pattern_result,
        "dry_run": dry_run,
    }


def load_mvp_evaluations_from_supabase(
    evaluation_id: str | None = None,
) -> list[dict[str, Any]]:
    """Query mvp_evaluations from Supabase."""
    try:
        client = get_supabase_client()
        if client is None:
            return []

        query = client.table(MVP_TABLE_NAME).select("*")
        if evaluation_id is not None:
            query = query.eq("evaluation_id", evaluation_id)
        response = query.order("evaluated_at", desc=True).execute()
        return list(response.data or [])
    except Exception:
        logger.warning(
            "Supabase MVP evaluation load failed (evaluation_id=%s)",
            evaluation_id,
            exc_info=True,
        )
        return []


__all__ = [
    "DEFAULT_MVP_JSON",
    "DEFAULT_PATTERN_CARDS_JSONL",
    "MVP_TABLE_NAME",
    "MVP_UPSERT_CONFLICT_COLUMN",
    "load_mvp_evaluation",
    "load_mvp_pattern_card_evaluations",
    "mvp_evaluation_to_supabase_row",
    "mvp_pattern_card_to_reflection_row",
    "sync_mvp_bundle_to_supabase",
    "sync_mvp_evaluation_to_supabase",
    "sync_mvp_pattern_cards_to_supabase",
    "load_mvp_evaluations_from_supabase",
    "is_supabase_configured",
]
