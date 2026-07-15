"""Read-only loader for Supabase drafts → evaluation cases."""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
from datetime import datetime, timezone
from typing import Any, Callable

DEFAULT_STATUSES = ("saved", "cancelled")
DEFAULT_LIMIT = 30
DEFAULT_SEED = 20260715
SENSITIVE_KEYS = frozenset({"id", "telegram_user_id", "user_id", "source_uuid"})


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(normalize_text(v) for v in value)
    text = str(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def content_fingerprint(user_texts: list[str], conversation: list[dict] | None) -> str:
    payload = {
        "user_texts": [normalize_text(t) for t in user_texts],
        "conversation": [
            {"role": normalize_text(t.get("role")), "content": normalize_text(t.get("content"))}
            for t in (conversation or [])
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def restore_raw_text(raw_text: Any) -> tuple[list[str], list[dict]]:
    if isinstance(raw_text, str):
        try:
            raw_text = json.loads(raw_text)
        except json.JSONDecodeError:
            raw_text = {}
    if not isinstance(raw_text, dict):
        raw_text = {}
    user_texts = list(raw_text.get("user_texts") or [])
    conversation = list(raw_text.get("conversation") or [])
    user_texts = [str(t) for t in user_texts if str(t).strip()]
    cleaned_conversation: list[dict] = []
    for turn in conversation:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role") or "").strip()
        content = str(turn.get("content") or "").strip()
        if role and content:
            cleaned_conversation.append({"role": role, "content": content})
    return user_texts, cleaned_conversation


def _char_length(user_texts: list[str], conversation: list[dict]) -> int:
    n = sum(len(t) for t in user_texts)
    n += sum(len(t.get("content", "")) for t in conversation)
    return n


def _length_bucket(n: int) -> str:
    if n < 120:
        return "short"
    if n < 500:
        return "medium"
    return "long"


def _infer_record_type(user_texts: list[str], summary: dict) -> str:
    text = " ".join(user_texts)
    tags = " ".join(str(t) for t in (summary.get("tags") or []))
    projects = summary.get("projects") or []
    memory_type = str(summary.get("memory_type") or "")
    emotions = summary.get("user_emotions") or []
    lower = (text + " " + tags).lower()

    if projects or any(k in lower for k in ("프로젝트", "gpt", "cursor", "하네스", "토스", "gpters")):
        return "project"
    if emotions or any(k in lower for k in ("화나", "슬프", "불안", "기쁘", "감정", "힘들")):
        return "emotion"
    if memory_type == "relation" or any(k in lower for k in ("친구", "동료", "관계", "팀")):
        return "relation"
    if memory_type == "reflection_seed" or any(k in lower for k in ("아이디어", "생각", "떠올", "만들고 싶")):
        return "idea"
    if any(k in lower for k in ("회의", "업무", "회사", "민원", "일하")):
        return "work"
    return "other"


def _has_user_complaint(user_texts: list[str], conversation: list[dict], cancellation_reason: str) -> bool:
    blob = " ".join(user_texts) + " " + (cancellation_reason or "")
    for turn in conversation:
        if turn.get("role") == "user":
            blob += " " + turn.get("content", "")
    markers = (
        "왜 이런 질문",
        "이미 말했",
        "맞지 않",
        "틀렸",
        "이상해",
        "잘못",
        "원하지 않",
        "질문 그만",
        "과잉",
        "해석이",
    )
    return any(m in blob for m in markers)


def categorize_case(
    *,
    status: str,
    user_texts: list[str],
    conversation: list[dict],
    summary: dict,
    cancellation_reason: str,
) -> dict[str, Any]:
    length = _char_length(user_texts, conversation)
    projects = list(summary.get("projects") or [])
    text = " ".join(user_texts)
    project_mentioned = bool(projects) or any(
        k in text for k in ("프로젝트", "GPTERS", "Harness", "Cursor", "토스", "하네스")
    )
    risk = str(summary.get("interpretation_risk") or "unknown")
    had_followup = bool(summary.get("needs_followup") or summary.get("followup_question") or summary.get("question_mode_used"))
    return {
        "status": status,
        "length_bucket": _length_bucket(length),
        "char_length": length,
        "project_mentioned": project_mentioned,
        "projects_empty": len(projects) == 0,
        "interpretation_risk": risk if risk in ("low", "medium", "high") else "unknown",
        "had_followup": had_followup,
        "has_cancellation_reason": bool((cancellation_reason or "").strip()),
        "record_type": _infer_record_type(user_texts, summary),
        "user_complaint": _has_user_complaint(user_texts, conversation, cancellation_reason),
        "possible_missing_project_tag": project_mentioned and len(projects) == 0,
    }


def select_balanced_cases(
    candidates: list[dict[str, Any]],
    *,
    limit: int,
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Deterministic stratified sample; do not force ratios when data is scarce."""
    rng = random.Random(seed)
    buckets: dict[str, list[dict[str, Any]]] = {}
    for case in candidates:
        cats = case["categories"]
        key = f"{cats['status']}|{cats['length_bucket']}|{cats['record_type']}|{cats['interpretation_risk']}"
        buckets.setdefault(key, []).append(case)

    for key in buckets:
        buckets[key] = list(buckets[key])
        rng.shuffle(buckets[key])

    selected: list[dict[str, Any]] = []
    selected_hashes: set[str] = set()
    keys = sorted(buckets.keys())
    # Round-robin across strata for diversity.
    while len(selected) < limit:
        progressed = False
        for key in keys:
            if len(selected) >= limit:
                break
            while buckets[key]:
                item = buckets[key].pop()
                if item["source_hash"] in selected_hashes:
                    continue
                selected.append(item)
                selected_hashes.add(item["source_hash"])
                progressed = True
                break
        if not progressed:
            break

    # Fill remaining from leftover pool if strata exhausted early.
    if len(selected) < limit:
        leftovers = [c for c in candidates if c["source_hash"] not in selected_hashes]
        rng.shuffle(leftovers)
        for item in leftovers:
            if len(selected) >= limit:
                break
            selected.append(item)
            selected_hashes.add(item["source_hash"])

    selected.sort(key=lambda c: c["source_hash"])
    # Assign stable public case IDs after final sort for reproducibility.
    for idx, case in enumerate(selected, start=1):
        case["case_id"] = f"case_{idx:03d}"

    category_counts: dict[str, dict[str, int]] = {}
    for case in selected:
        for field, value in case["categories"].items():
            if field == "char_length":
                continue
            bucket = category_counts.setdefault(field, {})
            key = str(value)
            bucket[key] = bucket.get(key, 0) + 1

    scarcity = {
        "requested_limit": limit,
        "available_unique": len(candidates),
        "selected": len(selected),
        "shortfall": max(0, limit - len(selected)),
    }
    return selected, {"category_counts": category_counts, "scarcity": scarcity}


class ReadOnlyDraftClient:
    """Thin wrapper that only exposes select; write methods raise."""

    def __init__(self, client: Any, table_name: str):
        self._client = client
        self.table_name = table_name
        self.select_calls = 0

    def select_drafts(
        self,
        *,
        statuses: list[str],
        columns: str = "id,status,raw_text,summary_json,cancellation_reason,created_at,updated_at",
    ) -> list[dict[str, Any]]:
        self.select_calls += 1
        query = (
            self._client.table(self.table_name)
            .select(columns)
            .in_("status", statuses)
            .order("created_at", desc=True)
        )
        response = query.execute()
        return list(response.data or [])

    def insert(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("evaluation draft loader is read-only; insert forbidden")

    def update(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("evaluation draft loader is read-only; update forbidden")

    def delete(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("evaluation draft loader is read-only; delete forbidden")


def fetch_draft_rows(
    *,
    statuses: list[str] | None = None,
    client: Any | None = None,
    table_name: str | None = None,
) -> list[dict[str, Any]]:
    statuses = list(statuses or DEFAULT_STATUSES)
    table = table_name or os.getenv("SUPABASE_DRAFTS_TABLE", "drafts").strip() or "drafts"
    if client is None:
        from supabase import create_client

        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_SECRET_KEY", "").strip()
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")
        client = create_client(url, key)
    ro = ReadOnlyDraftClient(client, table)
    return ro.select_drafts(statuses=statuses)


def rows_to_candidates(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    exclusion = {
        "empty_user_texts": 0,
        "duplicate_content": 0,
        "total_rows": len(rows),
    }
    for row in rows:
        user_texts, conversation = restore_raw_text(row.get("raw_text"))
        if not user_texts:
            exclusion["empty_user_texts"] += 1
            continue
        source_hash = content_fingerprint(user_texts, conversation)
        if source_hash in seen:
            exclusion["duplicate_content"] += 1
            continue
        seen.add(source_hash)
        summary = row.get("summary_json") or {}
        if isinstance(summary, str):
            try:
                summary = json.loads(summary)
            except json.JSONDecodeError:
                summary = {}
        status = str(row.get("status") or "")
        cancellation_reason = str(row.get("cancellation_reason") or "")
        categories = categorize_case(
            status=status,
            user_texts=user_texts,
            conversation=conversation,
            summary=summary if isinstance(summary, dict) else {},
            cancellation_reason=cancellation_reason,
        )
        # Keep production summary only for reference comparison — never as model input.
        candidates.append(
            {
                "source_hash": source_hash,
                "status": status,
                "user_texts": user_texts,
                "conversation": conversation,
                "cancellation_reason": cancellation_reason,
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
                "production_summary": summary if isinstance(summary, dict) else {},
                "categories": categories,
            }
        )
    return candidates, exclusion


def strip_sensitive_fields(case: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(case)
    for key in SENSITIVE_KEYS:
        cleaned.pop(key, None)
    return cleaned


def build_dataset(
    rows: list[dict[str, Any]],
    *,
    limit: int = DEFAULT_LIMIT,
    seed: int = DEFAULT_SEED,
    statuses: list[str] | None = None,
    dataset_id: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates, exclusion = rows_to_candidates(rows)
    selected, selection_meta = select_balanced_cases(candidates, limit=limit, seed=seed)
    public_cases = [strip_sensitive_fields(c) for c in selected]

    status_counts: dict[str, int] = {}
    for case in public_cases:
        status_counts[case["status"]] = status_counts.get(case["status"], 0) + 1

    ds_id = dataset_id or datetime.now(timezone.utc).strftime("ds_%Y%m%d_%H%M%S")
    manifest = {
        "dataset_id": ds_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "case_count": len(public_cases),
        "status_counts": status_counts,
        "category_counts": selection_meta["category_counts"],
        "selection_rules": {
            "statuses": list(statuses or DEFAULT_STATUSES),
            "require_nonempty_user_texts": True,
            "dedupe_by": "normalized user_texts + conversation",
            "exclude_active_by_default": "active" not in (statuses or DEFAULT_STATUSES),
            "limit": limit,
            "seed": seed,
            "scarcity": selection_meta["scarcity"],
            "exclusions": exclusion,
        },
        "source_table": os.getenv("SUPABASE_DRAFTS_TABLE", "drafts") or "drafts",
    }
    return public_cases, manifest


def write_dataset(
    cases: list[dict[str, Any]],
    manifest: dict[str, Any],
    output_dir: str | os.PathLike[str],
) -> dict[str, str]:
    from pathlib import Path

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    cases_path = out / "cases.jsonl"
    manifest_path = out / "manifest.json"
    with cases_path.open("w", encoding="utf-8") as fh:
        for case in cases:
            fh.write(json.dumps(case, ensure_ascii=False) + "\n")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"cases": str(cases_path), "manifest": str(manifest_path)}
