"""Supabase remote mirror for interpretation failure snapshots."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.evaluation_supabase import get_supabase_client, is_supabase_configured

logger = logging.getLogger(__name__)

TABLE_NAME = "interpretation_failures"
UPSERT_CONFLICT_COLUMN = "failure_key"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSONL = PROJECT_ROOT / "data" / "evaluation" / "interpretation_failures.jsonl"


def build_failure_key(record: dict[str, Any]) -> str:
    """Stable upsert key for one JSONL failure row."""
    conversation_id = str(record.get("conversation_id") or "unknown")
    occurred_at = str(record.get("timestamp") or "")
    failure_type = str(record.get("failure_type") or "unknown")
    return f"{conversation_id}|{occurred_at}|{failure_type}"


def failure_to_supabase_row(record: dict[str, Any]) -> dict[str, Any]:
    """interpretation_failures.jsonl row → interpretation_failures table row."""
    return {
        "failure_key": build_failure_key(record),
        "occurred_at": record["timestamp"],
        "conversation_id": str(record.get("conversation_id") or "unknown"),
        "source_memory_file": record.get("source_memory_file"),
        "message_index": record.get("message_index"),
        "failure_type": record["failure_type"],
        "severity": record.get("severity") or "medium",
        "context": record.get("context") or [],
        "user_correction": record.get("user_correction") or "",
        "assistant_output": record.get("assistant_after_correction") or "",
        "expected_behavior": record.get("expected_behavior"),
        "root_cause": record.get("root_cause"),
        "fixed_rule": record.get("fixed_rule"),
        "rule_candidate": record.get("rule_candidate"),
        "recurrence_risk": record.get("recurrence_risk"),
        "prevented_by_rule": record.get("prevented_by_rule"),
        "raw": record,
    }


def load_interpretation_failures(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load all rows from interpretation_failures.jsonl."""
    jsonl_path = Path(path or DEFAULT_JSONL)
    if not jsonl_path.exists() or jsonl_path.stat().st_size == 0:
        return []

    rows: list[dict[str, Any]] = []
    with open(jsonl_path, encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON at {jsonl_path}:{line_no}"
                ) from exc
    return rows


def sync_interpretation_failure_to_supabase(record: dict[str, Any]) -> bool:
    """Upsert one failure snapshot. Returns True on success."""
    try:
        client = get_supabase_client()
        if client is None:
            return False

        row = failure_to_supabase_row(record)
        client.table(TABLE_NAME).upsert(
            row,
            on_conflict=UPSERT_CONFLICT_COLUMN,
        ).execute()
        return True
    except Exception:
        logger.warning(
            "Supabase interpretation failure sync failed for %s",
            record.get("conversation_id"),
            exc_info=True,
        )
        return False


def sync_jsonl_to_supabase(jsonl_path: str | Path | None = None) -> dict[str, Any]:
    """Sync interpretation_failures.jsonl → Supabase."""
    records = load_interpretation_failures(jsonl_path)
    synced = 0
    failed_items: list[dict[str, str]] = []

    for record in records:
        if sync_interpretation_failure_to_supabase(record):
            synced += 1
        else:
            failed_items.append(
                {
                    "failure_key": build_failure_key(record),
                    "conversation_id": str(record.get("conversation_id") or ""),
                }
            )

    total = len(records)
    return {
        "total": total,
        "synced": synced,
        "failed": total - synced,
        "failed_items": failed_items,
    }


def load_interpretation_failures_from_supabase(
    *,
    failure_type: str | None = None,
    conversation_id: str | None = None,
) -> list[dict[str, Any]]:
    """Query interpretation_failures from Supabase."""
    try:
        client = get_supabase_client()
        if client is None:
            return []

        query = client.table(TABLE_NAME).select("*")
        if failure_type is not None:
            query = query.eq("failure_type", failure_type)
        if conversation_id is not None:
            query = query.eq("conversation_id", conversation_id)
        response = query.order("occurred_at", desc=True).execute()
        return list(response.data or [])
    except Exception:
        logger.warning(
            "Supabase interpretation failure load failed",
            exc_info=True,
        )
        return []


__all__ = [
    "DEFAULT_JSONL",
    "TABLE_NAME",
    "UPSERT_CONFLICT_COLUMN",
    "build_failure_key",
    "failure_to_supabase_row",
    "load_interpretation_failures",
    "load_interpretation_failures_from_supabase",
    "sync_interpretation_failure_to_supabase",
    "sync_jsonl_to_supabase",
    "is_supabase_configured",
]
