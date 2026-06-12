"""Tests for reflection question generation and validation."""

import json
from unittest.mock import MagicMock, patch

from conversation_to_memory.memory.question import (
    can_use_meaning_check,
    generate_question,
    merge_question_into_draft,
    normalize_question_result,
    validate_question,
)

DRAFT_LOW_RISK = {
    "topic": "회의",
    "event_summary": "회의에서 말이 안 통하는 느낌이 들었다.",
    "interpretation_risk": "low",
    "unsupported_inferences": [],
    "open_questions": [],
}

DRAFT_MEDIUM_RISK = {
    **DRAFT_LOW_RISK,
    "interpretation_risk": "medium",
    "unsupported_inferences": ["맥락 부족"],
}


def test_can_use_meaning_check_blocked_when_already_used():
    session = {"meaning_check_count": 1, "last_question_mode": "association"}
    assert can_use_meaning_check(draft=DRAFT_MEDIUM_RISK, question_session=session) is False


def test_can_use_meaning_check_blocked_on_low_risk():
    session = {"meaning_check_count": 0, "last_question_mode": None}
    assert can_use_meaning_check(draft=DRAFT_LOW_RISK, question_session=session) is False


def test_validate_question_rejects_forbidden_coaching():
    result = validate_question(
        {
            "question_mode": "association",
            "followup_question": "이 경험에서 배운 점은 무엇인가요?",
            "needs_followup": True,
        },
        draft=DRAFT_LOW_RISK,
        question_session={"questions_asked": 0, "last_question_mode": None, "meaning_check_count": 0},
    )
    assert result["needs_followup"] is False
    assert result["followup_question"] == ""


def test_validate_question_downgrades_meaning_check_when_not_allowed():
    result = validate_question(
        {
            "question_mode": "meaning_check",
            "followup_question": "이렇게 기록해도 될까요?",
            "needs_followup": True,
        },
        draft=DRAFT_LOW_RISK,
        question_session={"questions_asked": 0, "last_question_mode": None, "meaning_check_count": 0},
    )
    assert result["question_mode"] == "association"
    assert result["needs_followup"] is True


def test_validate_question_stops_on_fatigue_signal():
    result = validate_question(
        {
            "question_mode": "association",
            "followup_question": "그때 어떤 장면이 떠올랐나요?",
            "needs_followup": True,
        },
        draft=DRAFT_LOW_RISK,
        question_session={"questions_asked": 0, "last_question_mode": None, "meaning_check_count": 0},
        latest_user_text="모르겠어. 됐어.",
    )
    assert result["needs_followup"] is False


def test_merge_question_into_draft_appends_open_questions():
    draft = {"open_questions": ["기존 질문"]}
    merged = merge_question_into_draft(
        draft,
        {"open_questions": ["새 질문"], "possible_memory_value": "high"},
    )
    assert "새 질문" in merged["open_questions"]
    assert merged["reflection_value"] == "high"


def test_normalize_question_result_defaults():
    result = normalize_question_result({})
    assert result["question_mode"] == "association"
    assert result["needs_followup"] is False


@patch("conversation_to_memory.memory.question._get_client")
def test_generate_question_respects_max_questions(mock_get_client):
    mock_get_client.return_value = MagicMock()
    result = generate_question(
        user_texts=["테스트"],
        draft=DRAFT_LOW_RISK,
        question_session={"questions_asked": 2, "question_modes_used": [], "meaning_check_count": 0, "last_question_mode": None},
    )
    assert result["needs_followup"] is False
    mock_get_client.return_value.chat.completions.create.assert_not_called()


@patch("conversation_to_memory.memory.question._get_client")
def test_generate_question_calls_openai(mock_get_client):
    payload = {
        "question_mode": "association",
        "followup_question": "그때 어떤 소리가 기억나나요?",
        "needs_followup": True,
        "open_questions": [],
        "possible_memory_value": "medium",
        "emotion": {"labels": [], "evidence_strength": "weak"},
    }
    message = MagicMock()
    message.content = json.dumps(payload, ensure_ascii=False)
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = response
    mock_get_client.return_value = mock_client

    with patch.dict("os.environ", {"REFLECTION_MAX_QUESTIONS": "2"}):
        result = generate_question(
            user_texts=["복도 형광등이 유난히 밝게 느껴졌어"],
            draft=DRAFT_LOW_RISK,
            question_session={
                "questions_asked": 0,
                "question_modes_used": [],
                "meaning_check_count": 0,
                "last_question_mode": None,
            },
        )

    assert result["needs_followup"] is True
    assert result["question_mode"] == "association"
    mock_client.chat.completions.create.assert_called_once()
