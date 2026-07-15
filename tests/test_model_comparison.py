"""Unit tests for multi-model comparison runner."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from conversation_to_memory.evaluation.model_comparison import (
    case_blind_order,
    load_cases,
    probe_model_access,
    result_path,
    run_comparison,
    run_single_case_model,
)
from conversation_to_memory.evaluation.openai_compat import (
    build_chat_kwargs,
    classify_api_error,
    is_reasoning_family,
)
from conversation_to_memory.evaluation.prompt_hash import get_prompt_hashes
from conversation_to_memory.memory.question import resolve_question_model
from conversation_to_memory.memory.service import resolve_memory_model


SAMPLE_CASE = {
    "case_id": "case_001",
    "source_hash": "abc",
    "status": "saved",
    "user_texts": ["회의가 길어서 지쳤다"],
    "conversation": [],
    "categories": {"length_bucket": "short", "record_type": "work"},
    "production_summary": {"event_summary": "old"},
}


def test_model_resolve_priority(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "env-default")
    monkeypatch.setenv("OPENAI_MEMORY_MODEL", "memory-env")
    monkeypatch.setenv("OPENAI_QUESTION_MODEL", "question-env")
    assert resolve_memory_model("arg-model") == "arg-model"
    assert resolve_memory_model(None) == "memory-env"
    assert resolve_question_model(None) == "question-env"
    monkeypatch.delenv("OPENAI_MEMORY_MODEL")
    monkeypatch.delenv("OPENAI_QUESTION_MODEL")
    assert resolve_memory_model(None) == "env-default"


def test_reasoning_family_uses_max_completion_tokens():
    assert is_reasoning_family("gpt-5.6-luna")
    kwargs = build_chat_kwargs(
        model="gpt-5.6-luna",
        messages=[{"role": "user", "content": "x"}],
        temperature=0.2,
        max_output_tokens=100,
    )
    assert "max_completion_tokens" in kwargs
    assert kwargs["max_completion_tokens"] >= 4096
    assert "temperature" not in kwargs
    classic = build_chat_kwargs(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "x"}],
        temperature=0.2,
        max_output_tokens=100,
    )
    assert classic["max_tokens"] == 100
    assert classic["temperature"] == 0.2


def test_same_inputs_and_prompt_hashes_across_models():
    hashes = get_prompt_hashes()
    calls = []

    def fake_analyze(**kwargs):
        calls.append(("analyze", kwargs["model"], kwargs["user_texts"], kwargs.get("conversation")))
        return {
            "draft": {
                "event_summary": f"summary-{kwargs['model']}",
                "needs_followup": False,
                "projects": [],
                "tags": [],
                "user_emotions": [],
                "interpretation_risk": "low",
                "unsupported_inferences": [],
                "memory_candidate": "m",
                "model_interpretation": "i",
            },
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            "raw_usage": {},
            "request_config": {"model": kwargs["model"]},
            "model": kwargs["model"],
        }

    def fake_question(**kwargs):
        calls.append(("question", kwargs["model"], kwargs["user_texts"]))
        return {
            "question_result": {
                "needs_followup": False,
                "followup_question": "",
                "skip_reason": "no_reflective_handle",
                "question_mode": "",
                "archive_gap": "none",
                "reflective_handle_strength": "none",
                "candidate_count": 0,
                "selected_anchor": "",
                "rejected_candidates": [],
                "question_outcome": "skipped",
            },
            "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            "raw_usage": {},
            "request_config": {"model": kwargs["model"]},
            "model": kwargs["model"],
        }

    r1 = run_single_case_model(SAMPLE_CASE, "gpt-4o-mini", analyze_fn=fake_analyze, question_fn=fake_question)
    r2 = run_single_case_model(SAMPLE_CASE, "gpt-5.6-luna", analyze_fn=fake_analyze, question_fn=fake_question)
    assert r1["prompt_hashes"] == r2["prompt_hashes"] == hashes
    assert r1["input_fingerprint"]["user_texts"] == r2["input_fingerprint"]["user_texts"]
    assert r1["question_result"]["skip_reason"] == "no_reflective_handle"
    assert ("analyze", "gpt-4o-mini", SAMPLE_CASE["user_texts"], []) in calls
    assert ("analyze", "gpt-5.6-luna", SAMPLE_CASE["user_texts"], []) in calls


def test_no_fallback_on_model_failure():
    def boom(**kwargs):
        raise RuntimeError("model_not_found: gpt-x")

    result = run_single_case_model(SAMPLE_CASE, "gpt-x", analyze_fn=boom, question_fn=boom)
    assert result["error"]["error_type"] == "model_access_error"
    assert result["error"]["category"] == "project_permission"
    assert result["draft"] == {}


def test_resume_skips_completed(tmp_path: Path):
    def analyze(**kwargs):
        return {
            "draft": {"event_summary": "ok", "needs_followup": False, "projects": []},
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            "request_config": {},
            "raw_usage": None,
            "model": kwargs["model"],
        }

    def question(**kwargs):
        return {
            "question_result": {
                "needs_followup": False,
                "followup_question": "",
                "skip_reason": "no_reflective_handle",
                "rejected_candidates": [],
            },
            "usage": {},
            "request_config": {},
            "raw_usage": None,
            "model": kwargs["model"],
        }

    calls = {"n": 0}

    def counting_analyze(**kwargs):
        calls["n"] += 1
        return analyze(**kwargs)

    out = tmp_path / "run1"
    run_comparison(
        cases=[SAMPLE_CASE],
        models=["gpt-4o-mini"],
        output_dir=out,
        probe=False,
        analyze_fn=counting_analyze,
        question_fn=question,
    )
    assert calls["n"] == 1
    run_comparison(
        cases=[SAMPLE_CASE],
        models=["gpt-4o-mini"],
        output_dir=out,
        probe=False,
        analyze_fn=counting_analyze,
        question_fn=question,
    )
    assert calls["n"] == 1  # resumed


def test_does_not_write_production_memories(tmp_path: Path, monkeypatch):
    mem = tmp_path / "data" / "memories"
    mem.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    def analyze(**kwargs):
        return {
            "draft": {"event_summary": "x", "needs_followup": False},
            "usage": {},
            "request_config": {},
            "raw_usage": None,
            "model": kwargs["model"],
        }

    def question(**kwargs):
        return {
            "question_result": {"needs_followup": False, "followup_question": "", "skip_reason": "x"},
            "usage": {},
            "request_config": {},
            "raw_usage": None,
            "model": kwargs["model"],
        }

    run_comparison(
        cases=[SAMPLE_CASE],
        models=["gpt-4o-mini"],
        output_dir=tmp_path / "out",
        probe=False,
        analyze_fn=analyze,
        question_fn=question,
    )
    assert list(mem.glob("*.json")) == []


def test_model_override_reaches_api_kwargs():
    from conversation_to_memory.evaluation.openai_compat import chat_completion_create

    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content='{"ok":true}'))]
    response.usage = None
    client.chat.completions.create.return_value = response
    chat_completion_create(
        client,
        model="gpt-5.6-terra",
        messages=[{"role": "user", "content": "x"}],
        temperature=0.2,
        max_output_tokens=50,
        response_format={"type": "json_object"},
    )
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "gpt-5.6-terra"


def test_blind_order_stable():
    a = case_blind_order("case_001", ["m1", "m2", "m3"], seed=20260715)
    b = case_blind_order("case_001", ["m1", "m2", "m3"], seed=20260715)
    assert a == b
    c = case_blind_order("case_002", ["m1", "m2", "m3"], seed=20260715)
    assert sorted(a) == sorted(c)


def test_classify_rate_limit():
    err = classify_api_error(RuntimeError("Rate limit exceeded 429"))
    assert err["category"] == "rate_limit"


@pytest.mark.model_comparison_live
def test_live_model_probe():
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY missing")
    status = probe_model_access("gpt-4o-mini")
    assert "ok" in status
