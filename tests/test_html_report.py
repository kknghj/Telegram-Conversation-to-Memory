"""Tests for static HTML comparison report."""

from __future__ import annotations

from pathlib import Path

from conversation_to_memory.evaluation.html_report import generate_comparison_html
from conversation_to_memory.evaluation.model_comparison import case_blind_order


def test_html_renders_three_models_and_escapes(tmp_path: Path):
    models = ["gpt-4o-mini", "gpt-5.6-luna", "gpt-5.6-terra"]
    case = {
        "case_id": "case_001",
        "status": "saved",
        "user_texts": ["<script>alert(1)</script>원문"],
        "conversation": [{"role": "user", "content": "A&B"}],
        "categories": {"length_bucket": "short", "record_type": "work"},
        "production_summary": {"event_summary": "prod"},
    }
    order = case_blind_order("case_001", models, seed=1)
    results = []
    for model in models:
        results.append(
            {
                "case_id": "case_001",
                "model": model,
                "latency_ms": 10,
                "estimated_cost_usd": 0.001,
                "draft": {
                    "event_summary": f"summary {model}",
                    "projects": [],
                    "tags": ["t"],
                    "user_emotions": [],
                    "memory_candidate": "m",
                    "model_interpretation": "i",
                    "interpretation_risk": "low",
                    "unsupported_inferences": [],
                },
                "question_result": {
                    "needs_followup": False,
                    "followup_question": "",
                    "skip_reason": "no_reflective_handle",
                    "question_mode": "",
                    "rejected_candidates": [],
                },
                "error": None,
            }
        )
    # one error result should not break page
    results[2]["error"] = {"error_type": "model_access_error", "category": "billing", "message": "quota"}

    manifest = {
        "run_id": "run_test",
        "case_model_order": {"case_001": order},
        "blind_global_alias_to_model": {"A": order[0], "B": order[1], "C": order[2]},
    }
    out = generate_comparison_html(
        cases=[case],
        results=results,
        manifest=manifest,
        output_path=tmp_path / "comparison.html",
    )
    text = out.read_text(encoding="utf-8")
    assert "localStorage" in text
    assert "평가 JSON 내보내기" in text
    assert "평가 CSV 내보내기" in text
    assert "const DATA =" in text
    assert "모델 ${label}" in text
    # Embedded JSON must not include raw < from user text.
    assert "<script>alert(1)</script>" not in text
    assert "\\u003cscript\\u003e" in text or "\\u003c" in text
    assert "billing" in text or "model_access_error" in text
    assert "gpt-4o-mini" in text  # in DATA for reveal after evaluation
    assert "case_001" in text


def test_blind_order_seed_fixed():
    a = case_blind_order("case_009", ["a", "b", "c"], seed=42)
    b = case_blind_order("case_009", ["a", "b", "c"], seed=42)
    assert a == b
