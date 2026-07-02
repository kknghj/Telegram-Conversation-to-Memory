"""Rule 5 — 부정 감정 직후 긍정 회상 질문 금지 테스트."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conversation_to_memory import failure_recorder
from conversation_to_memory.memory.question import validate_question

DRAFT_LOW_RISK = {
    "topic": "수면",
    "event_summary": "새벽에 일어나 자신이 한심하게 느껴졌다.",
    "interpretation_risk": "low",
    "unsupported_inferences": [],
    "open_questions": [],
}

SESSION = {
    "questions_asked": 0,
    "last_question_mode": None,
    "meaning_check_count": 0,
}


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "interpretation_failures.jsonl"


def test_summary_after_worry_skips_joy_recall_question():
    user_texts = [
        "저녁에 잠깐만 잠드려다가 새벽1시에 일어났어. 내 자신이 좀 한심하게 느껴지네",
        "걱정되니까 내가 즐거워했던 일이 손에 잡히지 않아",
    ]
    draft = dict(DRAFT_LOW_RISK)

    result = validate_question(
        {
            "question_mode": "contrast",
            "followup_question": "반대로 평소에 즐거움을 느꼈던 순간은 어떤 때였는지 기억나?",
            "needs_followup": True,
        },
        draft=draft,
        question_session=SESSION,
        latest_user_text="요약",
        user_texts=user_texts,
    )

    assert result["needs_followup"] is False
    assert result["followup_question"] == ""
    assert "즐거웠던" not in result["followup_question"]


def test_positive_reframe_question_blocked_after_negative_emotion():
    user_texts = ["걱정되니까 내가 즐거워했던 일이 손에 잡히지 않아"]
    draft = dict(DRAFT_LOW_RISK)

    result = validate_question(
        {
            "question_mode": "contrast",
            "followup_question": "반대로 좋았던 점은 무엇이었나요?",
            "needs_followup": True,
        },
        draft=draft,
        question_session=SESSION,
        latest_user_text=user_texts[-1],
        user_texts=user_texts,
    )

    assert result["needs_followup"] is False
    assert result["followup_question"] == ""
    assert draft["interpretation_risk"] == "high"


def test_inappropriate_positive_reframe_sample_in_jsonl():
    log_path = Path("data/evaluation/interpretation_failures.jsonl")
    assert log_path.exists()

    entries = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").strip().splitlines()
        if line.strip()
    ]
    matches = [
        entry
        for entry in entries
        if entry.get("failure_type") == "inappropriate_positive_reframe"
        and entry.get("conversation_id") == "telegram_20260702_sleep_worry_positive_reframe"
    ]
    assert len(matches) == 1
    sample = matches[0]
    assert sample["fixed_rule"] == "Rule 5"
    assert sample["user_correction"] == "그런건 묻지마"
    assert "반대로" in sample["assistant_after_correction"]
    assert "느꼈던" in sample["assistant_after_correction"]


def test_question_rejection_records_failure_snapshot(log_path: Path):
    conversation = [
        {
            "role": "user",
            "content": "저녁에 잠깐만 잠드려다가 새벽1시에 일어났어. 내 자신이 좀 한심하게 느껴지네",
        },
        {
            "role": "user",
            "content": "걱정되니까 내가 즐거워했던 일이 손에 잡히지 않아",
        },
        {"role": "user", "content": "요약"},
        {
            "role": "assistant",
            "content": "새벽 1시에 일어난 후 어떤 생각이나 장면이 떠올랐어?",
        },
        {
            "role": "user",
            "content": "이렇게 어영부영 시간을 보내버린 내가 한심해졌어",
        },
        {
            "role": "assistant",
            "content": "이런 기분이 드는 순간과 반대로, 평소에 즐거움을 느꼈던 순간은 어떤 때였는지 기억나?",
        },
    ]
    user_correction = "그런건 묻지마"

    pending = failure_recorder.try_prepare_question_rejection_failure(
        user_correction=user_correction,
        conversation=conversation,
        conversation_id="telegram_20260702_sleep_worry_positive_reframe-test",
    )
    assert pending is not None
    assert pending["failure_type"] == "inappropriate_positive_reframe"

    record = failure_recorder.finalize_question_rejection_failure(pending, log_path=log_path)
    assert record["failure_type"] == "inappropriate_positive_reframe"
    assert record["user_correction"] == user_correction
    assert "반대로" in record["assistant_after_correction"]
    assert record["fixed_rule"] == "Rule 5"

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    parsed = json.loads(lines[-1])
    assert parsed["failure_type"] == "inappropriate_positive_reframe"


def test_detect_inappropriate_positive_reframe_risk():
    assert failure_recorder.detect_inappropriate_positive_reframe_risk(
        user_messages="걱정되니까 손에 잡히지 않아",
        question="반대로 즐거웠던 순간은 언제인가요?",
    )
    assert not failure_recorder.detect_inappropriate_positive_reframe_risk(
        user_messages="오늘 회의가 길었다",
        question="반대로 즐거웠던 순간은 언제인가요?",
    )
