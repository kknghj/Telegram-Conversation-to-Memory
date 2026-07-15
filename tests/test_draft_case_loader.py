"""Unit tests for read-only draft case export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conversation_to_memory.evaluation.draft_case_loader import (
    ReadOnlyDraftClient,
    build_dataset,
    content_fingerprint,
    restore_raw_text,
    rows_to_candidates,
    select_balanced_cases,
    strip_sensitive_fields,
    write_dataset,
)


def _row(status: str, texts: list[str], **kwargs):
    summary = kwargs.pop("summary", {"projects": [], "interpretation_risk": "low"})
    return {
        "id": kwargs.pop("id", "uuid-should-not-leak"),
        "telegram_user_id": kwargs.pop("telegram_user_id", 12345),
        "status": status,
        "raw_text": {"user_texts": texts, "conversation": kwargs.pop("conversation", [])},
        "summary_json": summary,
        "cancellation_reason": kwargs.pop("cancellation_reason", ""),
        "created_at": "2026-07-01T00:00:00Z",
        "updated_at": "2026-07-01T00:00:00Z",
        **kwargs,
    }


def test_restore_raw_text():
    user_texts, conversation = restore_raw_text(
        {
            "user_texts": ["안녕", ""],
            "conversation": [{"role": "user", "content": "hi"}, {"role": "bot"}],
        }
    )
    assert user_texts == ["안녕"]
    assert conversation == [{"role": "user", "content": "hi"}]


def test_empty_user_texts_excluded():
    rows = [_row("saved", []), _row("saved", ["내용"])]
    candidates, exclusion = rows_to_candidates(rows)
    assert len(candidates) == 1
    assert exclusion["empty_user_texts"] == 1


def test_dedupe_by_normalized_content():
    rows = [
        _row("saved", ["Hello World"]),
        _row("cancelled", ["hello   world"]),
    ]
    candidates, exclusion = rows_to_candidates(rows)
    assert len(candidates) == 1
    assert exclusion["duplicate_content"] == 1
    assert content_fingerprint(["Hello World"], []) == content_fingerprint(["hello   world"], [])


def test_seed_reproducibility():
    rows = [
        _row("saved", [f"text-{i}" * 3], summary={"interpretation_risk": "low", "projects": []})
        for i in range(20)
    ]
    rows += [
        _row(
            "cancelled",
            [f"long-" + ("x" * 200) + str(i)],
            summary={"interpretation_risk": "high", "projects": ["Harness"]},
            cancellation_reason="취소",
        )
        for i in range(20)
    ]
    a, _ = build_dataset(rows, limit=10, seed=20260715, dataset_id="t1")
    b, _ = build_dataset(rows, limit=10, seed=20260715, dataset_id="t2")
    assert [c["source_hash"] for c in a] == [c["source_hash"] for c in b]
    assert [c["case_id"] for c in a] == [c["case_id"] for c in b]


def test_active_excluded_by_default_statuses():
    from conversation_to_memory.evaluation.draft_case_loader import DEFAULT_STATUSES

    assert "active" not in DEFAULT_STATUSES


def test_strip_sensitive_fields():
    case = {
        "case_id": "case_001",
        "id": "uuid",
        "telegram_user_id": 99,
        "user_id": "99",
        "source_hash": "abc",
        "user_texts": ["x"],
    }
    cleaned = strip_sensitive_fields(case)
    assert "id" not in cleaned
    assert "telegram_user_id" not in cleaned
    assert "user_id" not in cleaned
    assert cleaned["case_id"] == "case_001"


def test_readonly_client_forbids_writes():
    class Fake:
        def table(self, name):
            return self

        def select(self, *a, **k):
            return self

        def in_(self, *a, **k):
            return self

        def order(self, *a, **k):
            return self

        def execute(self):
            class R:
                data = []

            return R()

    client = ReadOnlyDraftClient(Fake(), "drafts")
    client.select_drafts(statuses=["saved"])
    assert client.select_calls == 1
    with pytest.raises(RuntimeError, match="insert"):
        client.insert({})
    with pytest.raises(RuntimeError, match="update"):
        client.update({})
    with pytest.raises(RuntimeError, match="delete"):
        client.delete({})


def test_write_dataset_manifest_has_no_source_text(tmp_path: Path):
    rows = [_row("saved", ["비밀 원문입니다"])]
    cases, manifest = build_dataset(rows, limit=1, seed=1, dataset_id="ds_test")
    write_dataset(cases, manifest, tmp_path)
    manifest_text = (tmp_path / "manifest.json").read_text(encoding="utf-8")
    assert "비밀 원문" not in manifest_text
    assert "case_count" in manifest
    cases_line = (tmp_path / "cases.jsonl").read_text(encoding="utf-8")
    assert "uuid-should-not-leak" not in cases_line
    assert "12345" not in cases_line
