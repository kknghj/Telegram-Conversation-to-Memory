"""Tests for memory archive fidelity validation."""

from conversation_to_memory.memory.fidelity import (
    contains_forbidden_growth_narrative,
    detect_future_tense,
    detect_project_entities,
    detect_reflection_seed_signals,
    detect_unsupported_inferences,
    detect_value_tags,
    draft_hides_value,
    infer_temporal_status,
    is_reflection_seed_candidate,
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


# ---------------------------------------------------------------------------
# 가치관 우선 / reflection_seed / 시제 / 프로젝트·가치 태그 (Rule 6)
# ---------------------------------------------------------------------------

TOSS_INPUT = (
    "7월 말부터 들을 지피터스 ai 강의 주제로 내가 제일 원했던 주제인 하네스 구축은 마감이 되었고, "
    "고민 끝에 cursor로 토스 미니앱 만들기를 신청했어. "
    "토스앱 상주시간을 늘리기 위한 단순하면서 무식하게 중간 광고를 집어 넣은 게임앱이 대부분이었어. "
    "제일 기발해보이는 앱이 인스타그램 언팔한 계정 찾기였는데 "
    "그마저도 관계의 차단에 대한 불안을 이용하는 거라 조금 거리낌이 들었어. "
    "난 사람들의 일을 줄이고 편의성을 주는 것을 만들고 싶은데 "
    "게임앱이나 인스타언팔앱은 결국 사용자의 시간과 마음을 낭비한다는 생각이 들었어. "
    "토스 앱 제작 강의를 들어봤자 내가 원하는 방향으론 구현하기 힘들 것 같아서 다른 강의로 수강 변경했어."
)


def _toss_base_draft(**overrides) -> dict:
    draft = {
        "topic": "토스 미니앱 제작 강의",
        "event_summary": "토스 미니앱을 확인하고 다른 강의로 수강 변경했다.",
        "user_emotions": ["거리낌"],
        "emotion_evidence": ["조금 거리낌이 들었어"],
        "people": [],
        "projects": [],
        "tags": ["토스", "강의"],
        "value_tags": [],
        "memory_candidate": "토스 미니앱을 확인하고 강의를 변경했다.",
        "model_interpretation": "",
        "key_phrases": [],
        "emerging_themes": [],
        "open_questions": [],
        "reflection_value": "medium",
        "memory_type": "event",
        "interpretation_risk": "low",
        "unsupported_inferences": [],
        "needs_followup": False,
        "followup_question": "",
    }
    draft.update(overrides)
    return draft


def test_detect_future_tense_markers():
    assert detect_future_tense("cursor로 토스 미니앱 만들기를 신청했어") == ["신청했"]
    assert "예정" in detect_future_tense("다음 달부터 강의를 들을 예정이다")
    assert detect_future_tense("어제 회의를 했다") == []


def test_infer_temporal_status_mixed_and_past():
    assert infer_temporal_status(TOSS_INPUT) == "mixed"
    assert infer_temporal_status("어제 회의를 했다") == "past"
    assert infer_temporal_status("다음 주에 강의를 들을 예정") == "future"


def test_detect_value_tags_from_source():
    tags = detect_value_tags(TOSS_INPUT)
    assert "사용자 시간 절약" in tags
    assert "다크패턴 거부" in tags
    assert "불안 마케팅 거부" in tags
    assert "편의성" in tags


def test_detect_project_entities_normalized():
    projects = detect_project_entities(TOSS_INPUT)
    assert "GPTERS" in projects
    assert "Harness" in projects
    assert "Cursor" in projects
    assert "토스 미니앱" in projects


def test_detect_reflection_seed_signals_present():
    signals = detect_reflection_seed_signals(TOSS_INPUT)
    assert any("만들고 싶" in s for s in signals)
    assert any("거리낌" in s for s in signals)


def test_draft_hides_value_detects_event_only_summary():
    bad = _toss_base_draft()
    assert draft_hides_value(bad, TOSS_INPUT) is True


def test_draft_does_not_hide_value_when_reflected():
    good = _toss_base_draft(
        event_summary=(
            "사람들의 일을 줄이고 편의성을 주는 것을 만들고 싶어, "
            "다크패턴·불안 마케팅을 쓰는 앱에 거리낌이 들어 강의를 바꿨다."
        ),
        memory_type="reflection_seed",
    )
    assert draft_hides_value(good, TOSS_INPUT) is False
    assert is_reflection_seed_candidate(good, TOSS_INPUT) is True


def test_validate_draft_promotes_value_hidden_to_reflection_seed():
    bad = _toss_base_draft()
    validated = validate_draft(bad, TOSS_INPUT)

    assert validated["memory_type"] == "reflection_seed"
    assert validated["reflection_seed_candidate"] is True
    assert validated["temporal_status"] == "mixed"
    assert "다크패턴 거부" in validated["value_tags"]
    assert "GPTERS" in validated["projects"]
    assert "토스 미니앱" in validated["projects"]


def test_validate_draft_keeps_neutral_case_unchanged():
    validated = validate_draft(GOOD_DRAFT, USER_INPUT)
    assert validated["temporal_status"] == "past"
    assert validated["reflection_seed_candidate"] is False
    assert validated["value_tags"] == []
    assert validated.get("memory_type") != "reflection_seed"
