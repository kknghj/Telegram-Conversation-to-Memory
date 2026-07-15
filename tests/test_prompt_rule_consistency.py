"""Canonical docs vs runtime prompts consistency for Phase 2 rules."""

from __future__ import annotations

from pathlib import Path

from conversation_to_memory.evaluation.prompt_hash import (
    LEGACY_DIR,
    MEMORY_PROMPT,
    QUESTION_PROMPT,
    get_prompt_hashes,
    load_prompt,
)
from conversation_to_memory.memory.question import is_reflection_agent_enabled
from conversation_to_memory.memory.service import normalize_draft

ROOT = Path(__file__).resolve().parents[1]


def test_prompt_hashes_are_stable_sha256():
    hashes = get_prompt_hashes()
    assert len(hashes["memory"]) == 64
    assert len(hashes["question"]) == 64
    assert hashes["memory"] != hashes["question"]


def test_legacy_prompts_not_loaded_by_runtime_loaders():
    # Runtime loaders only read named active files under prompts/, never legacy/.
    memory = load_prompt(MEMORY_PROMPT)
    question = load_prompt(QUESTION_PROMPT)
    assert "회고형 대화 파트너" in question or "질문" in question
    assert "기억 아카이브" in memory
    if LEGACY_DIR.exists():
        for path in LEGACY_DIR.glob("*.txt"):
            assert path.name not in (MEMORY_PROMPT, QUESTION_PROMPT)


def test_archive_prompt_defers_questions_to_reflection_agent():
    memory = load_prompt(MEMORY_PROMPT)
    assert "질문 단계" in memory or "question_generation_prompt" in memory
    assert "followup_question으로 최대 1개만 확인" not in memory
    assert "EditChecklist" in memory
    assert "ConsistencyCheck" in memory


def test_question_prompt_distinguishes_one_vs_session_max():
    question = load_prompt(QUESTION_PROMPT)
    assert "최대 2회" in question
    assert "한 번에" in question or "1개" in question
    assert "accurate_summary != no_question_needed" in question


def test_question_strategy_is_canonical_for_extension_modes():
    strategy = (ROOT / "docs" / "question_strategy.md").read_text(encoding="utf-8")
    policy = (ROOT / "docs" / "PROMPT_POLICY.md").read_text(encoding="utf-8")
    assert "association" in strategy
    assert "question_strategy.md" in policy
    assert "위임" in policy or "canonical" in policy.lower()


def test_reflection_agent_clears_draft_followup(monkeypatch):
    monkeypatch.setenv("REFLECTION_AGENT_ENABLED", "true")
    assert is_reflection_agent_enabled() is True
    draft = normalize_draft(
        {"needs_followup": True, "followup_question": "왜요?", "event_summary": "x"}
    )
    assert draft["needs_followup"] is False
    assert draft["followup_question"] == ""


def test_memory_principles_session_cap_not_conflicting():
    principles = (ROOT / "docs" / "MEMORY_ARCHIVE_PRINCIPLES.md").read_text(encoding="utf-8")
    assert "최대 2회" in principles
    assert "한 번에" in principles
