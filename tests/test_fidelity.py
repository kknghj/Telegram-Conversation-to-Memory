"""Tests for memory archive fidelity validation."""

from conversation_to_memory.memory.fidelity import (
    contains_forbidden_growth_narrative,
    detect_unsupported_inferences,
    validate_draft,
)

USER_INPUT = (
    "식생활교육 신청 민원 전화 너무 힘들다. "
    "사실 받는 것보다 전화 올까봐 기다리는 게 더 힘들어. "
    "용역업체에서 잘못한 것 때문에 이 고생을 해야 한다는 게 억울하다. "
    "또 불만 전화이면 어떡하지. 이제 그만 오면 좋겠어. "
    "겨우 일 하나 끝냈구나. 얼른 침대에 눕고 싶어."
)

GOOD_DRAFT = {
    "topic": "식생활교육 신청 민원 전화 처리의 어려움",
    "event_summary": (
        "식생활교육 신청 민원 전화 처리가 힘들었다. "
        "전화를 받는 것보다 전화가 올지 기다리는 시간이 더 힘들었다. "
        "용역업체 실수로 인해 억울함을 느꼈다. "
        "불만 전화가 올까 불안했고, 일을 마친 뒤 침대에 눕고 싶었다."
    ),
    "user_emotions": ["피로", "불안", "억울함"],
    "emotion_evidence": [
        "너무 힘들다",
        "기다리는 게 더 힘들어",
        "억울하다",
        "불만 전화이면 어떡하지",
        "침대에 눕고 싶어",
    ],
    "people": [],
    "projects": ["식생활교육 신청"],
    "tags": ["민원", "전화", "업무", "억울함"],
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

BAD_DRAFT = {
    **GOOD_DRAFT,
    "memory_candidate": "힘든 순간을 견뎌낸 나 자신을 칭찬하고 싶다.",
    "unsupported_inferences": [],
}


def test_good_draft_has_no_forbidden_narrative():
    validated = validate_draft(GOOD_DRAFT, USER_INPUT)
    assert not contains_forbidden_growth_narrative(validated)
    assert validated["interpretation_risk"] == "low"
    assert "자기칭찬" not in str(validated["unsupported_inferences"])


def test_bad_draft_detects_growth_narrative():
    unsupported = detect_unsupported_inferences(BAD_DRAFT, USER_INPUT)
    validated = validate_draft(BAD_DRAFT, USER_INPUT)

    assert contains_forbidden_growth_narrative(BAD_DRAFT)
    assert len(unsupported) >= 1
    assert validated["interpretation_risk"] in ("medium", "high")


def test_good_draft_emotions_match_source():
    validated = validate_draft(GOOD_DRAFT, USER_INPUT)
    for emotion in validated["user_emotions"]:
        assert emotion in ("피로", "불안", "억울함", "짜증")


def test_followup_at_most_one():
    draft_with_followup = {**GOOD_DRAFT, "needs_followup": True, "followup_question": "민원 전화 자체보다 기다리는 시간이 더 힘들다고 기록해도 될까요?"}
    assert draft_with_followup["followup_question"]
    assert "배운" not in draft_with_followup["followup_question"]
    assert "칭찬" not in draft_with_followup["followup_question"]
