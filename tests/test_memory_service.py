"""Tests for memory service normalization and mocked analysis."""

import json
from unittest.mock import MagicMock, patch

from conversation_to_memory.memory.service import analyze_recording, normalize_draft

USER_INPUT = (
    "식생활교육 신청 민원 전화 너무 힘들다. "
    "사실 받는 것보다 전화 올까봐 기다리는 게 더 힘들어. "
    "용역업체에서 잘못한 것 때문에 이 고생을 해야 한다는 게 억울하다. "
    "또 불만 전화이면 어떡하지. 이제 그만 오면 좋겠어. "
    "겨우 일 하나 끝냈구나. 얼른 침대에 눕고 싶어."
)

MOCK_GPT_RESPONSE = {
    "topic": "식생활교육 신청 민원 전화 처리의 어려움",
    "event_summary": (
        "식생활교육 신청 민원 전화 처리가 힘들었다. "
        "전화를 받는 것보다 전화가 올지 기다리는 시간이 더 힘들었다. "
        "용역업체 실수로 인해 억울함을 느꼈다."
    ),
    "user_emotions": ["피로", "불안", "억울함"],
    "emotion_evidence": ["너무 힘들다", "기다리는 게 더 힘들어", "억울하다"],
    "people": [],
    "projects": ["식생활교육 신청"],
    "tags": ["민원", "전화", "업무"],
    "memory_candidate": (
        "식생활교육 신청 민원 전화 처리 과정에서 "
        "전화가 올지 기다리는 시간이 특히 힘들었고, "
        "용역업체 실수로 인해 억울함을 느꼈다."
    ),
    "interpretation_risk": "low",
    "unsupported_inferences": [],
    "needs_followup": False,
    "followup_question": "",
}


def _mock_openai_response(data: dict):
    message = MagicMock()
    message.content = json.dumps(data, ensure_ascii=False)
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


@patch("conversation_to_memory.memory.service._get_client")
def test_analyze_recording_minwon_case(mock_get_client):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(MOCK_GPT_RESPONSE)
    mock_get_client.return_value = mock_client

    draft = analyze_recording(user_texts=[USER_INPUT])

    assert draft["topic"] == "식생활교육 신청 민원 전화 처리의 어려움"
    assert "피로" in draft["user_emotions"] or "불안" in draft["user_emotions"]
    assert "견뎌" not in draft["memory_candidate"]
    assert "칭찬" not in draft["memory_candidate"]
    assert draft["needs_followup"] is False
    assert draft["followup_question"] == ""
    assert "자기칭찬" not in draft["unsupported_inferences"]


def test_normalize_draft_clears_followup_when_not_needed():
    draft = normalize_draft({"needs_followup": False, "followup_question": "질문?"})
    assert draft["followup_question"] == ""


def test_normalize_draft_default_fields():
    draft = normalize_draft({})
    assert draft["user_emotions"] == []
    assert draft["interpretation_risk"] == "low"
    assert draft["key_phrases"] == []
    assert draft["model_interpretation"] == ""
    assert draft["memory_type"] == "event"
    assert draft["reflection_value"] == "medium"


def test_format_review_message_shows_model_interpretation():
    from conversation_to_memory.memory.service import format_review_message

    text = format_review_message(
        {
            "event_summary": "요약",
            "model_interpretation": "사용자가 기다림에 더 민감하게 반응한 것으로 읽힘",
            "topic": "t",
            "user_emotions": [],
            "emotion_evidence": [],
            "people": [],
            "projects": [],
            "tags": [],
            "memory_candidate": "본문",
            "interpretation_risk": "low",
            "unsupported_inferences": [],
        }
    )
    assert "에이전트 해석" in text
    assert "기다림" in text
    assert "본문" in text
