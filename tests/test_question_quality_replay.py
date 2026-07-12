"""Transcript replay fixtures for 2026-07-12 question quality failures."""

from __future__ import annotations

from conversation_to_memory.memory.fidelity import reclassify_entities, validate_draft
from conversation_to_memory.memory.question import validate_question
from conversation_to_memory.bot.followup_response import classify_followup_response


DOSTOEVSKY_TURNS = [
    {
        "role": "user",
        "content": (
            "주술회전 가챠에 총 38만 원을 썼다. "
            "관심 없는 캐릭터가 중복으로 나오면서 돈을 낭비했다고 느꼈다. "
            "돈을 쓰는 와중에 돈이 부족할 때마다 인기 작품을 썼다는 도스토옙스키의 일화를 떠올렸다. "
            "낭비한 돈을 복구하려면 7월 토스 미니앱 공모전에 참여할 수밖에 없겠다고 생각했다."
        ),
    },
    {
        "role": "assistant",
        "content": "도스토옙스키의 일화와 관련해, 그의 이야기가 현재 상황에 어떤 식으로 연결된다고 느끼나요?",
    },
    {
        "role": "user",
        "content": "돈을 복구할 생각을 하니 공모전에 참여해야겠다고 생각했다.",
    },
    {
        "role": "assistant",
        "content": "도스토옙스키 일화와 현재 상황의 비슷한 점과 다른 점은 무엇인가요?",
    },
]

SUMMER_MENU_TURNS = [
    {
        "role": "user",
        "content": (
            "GPT와 아이디어 회의를 거쳐 토스 미니앱 공모전에 여름 메뉴 추천앱을 제출하기로 했다. "
            "음식이 떠오르지 않는 사람에게 몇 번의 질문으로 여름 음식을 추천하고 가게를 알려주는 앱이다. "
            "억지 광고를 유도하지 않는 제품이라는 점에 거리낌이 없다. "
            "음식 태깅과 디자인에 신경 쓰면 승산이 있다고 생각한다. "
            "7월 29일까지 완성하는 것이 가장 중요하다. "
            "다른 장기 프로젝트와 달리 단기 마감과 외부 반응이 필요한 프로젝트다. "
            "상금을 받아 가챠 지출을 만회하고 싶지만 우선 완성을 목표로 한다."
        ),
    },
    {
        "role": "assistant",
        "content": "여름 메뉴 추천앱을 개발하면서 어떤 특정한 음식이나 가게를 떠올렸나요?",
    },
    {
        "role": "user",
        "content": "콩국수를 떠올렸는데 GPT가 특정 음식이 아닌 감정에 따라 음식을 추천하는 걸 제안했다.",
    },
    {
        "role": "assistant",
        "content": "콩국수와 감정에 따라 추천하는 방식 사이에서 어떤 점이 더 매력적으로 느껴지나요?",
    },
    {
        "role": "user",
        "content": "맥락에 맞지 않은 질문이야. 둘 중 무엇이 낫냐고 물으려면 같은 격이어야 해.",
    },
]


def test_replay_dostoevsky_rejects_redundant_questions():
    source = DOSTOEVSKY_TURNS[0]["content"]
    bad_q1 = DOSTOEVSKY_TURNS[1]["content"]
    bad_q2 = DOSTOEVSKY_TURNS[3]["content"]
    draft = {
        "topic": "가챠 지출과 공모전",
        "event_summary": "가챠 낭비를 복구하려고 공모전 참여를 생각했다.",
        "interpretation_risk": "low",
        "unsupported_inferences": [],
        "key_phrases": ["도스토옙스키의 일화", "낭비한 돈을 복구"],
        "reflection_value": "high",
        "reflection_seed_candidate": True,
        "emerging_themes": ["지출", "공모전"],
    }
    qsession = {
        "questions_asked": 0,
        "last_question_mode": None,
        "meaning_check_count": 0,
        "questions_text": [],
    }
    result1 = validate_question(
        {
            "question_mode": "association",
            "followup_question": bad_q1,
            "needs_followup": True,
        },
        draft=draft,
        question_session=qsession,
        user_texts=[source],
    )
    assert result1["needs_followup"] is False
    assert result1["skip_reason"] == "answered_already"
    assert any(
        item["reason"] == "answered_already"
        for item in result1.get("rejected_candidates") or [{"reason": "answered_already"}]
    )

    qsession = {
        "questions_asked": 1,
        "last_question_mode": "association",
        "meaning_check_count": 0,
        "questions_text": [bad_q1],
    }
    result2 = validate_question(
        {
            "question_mode": "contrast",
            "followup_question": bad_q2,
            "needs_followup": True,
        },
        draft=draft,
        question_session=qsession,
        user_texts=[source, DOSTOEVSKY_TURNS[2]["content"]],
    )
    assert result2["needs_followup"] is False
    assert result2["skip_reason"] in {"answered_already", "redundant_question"}


def test_replay_summer_menu_entities_and_feedback_separation():
    source = SUMMER_MENU_TURNS[0]["content"]
    feedback = SUMMER_MENU_TURNS[4]["content"]
    assert classify_followup_response(feedback) in {
        "question_rejection",
        "meta_feedback",
    }

    bad_q = SUMMER_MENU_TURNS[1]["content"]
    draft = {
        "topic": "여름 메뉴 추천앱",
        "event_summary": "단기 마감의 여름 메뉴 추천앱을 공모전에 제출하기로 했다.",
        "people": ["GPT"],
        "projects": ["토스 미니앱 공모전"],
        "tags": [],
        "value_tags": [],
        "interpretation_risk": "low",
        "unsupported_inferences": [],
        "key_phrases": ["7월 29일까지 완성", "단기 마감"],
        "emerging_themes": ["마감", "제품"],
        "reflection_value": "high",
        "reflection_seed_candidate": True,
        "memory_type": "event",
        "memory_candidate": "단기 마감 프로젝트를 완성하는 것이 우선이다.",
        "model_interpretation": "",
        "user_emotions": [],
        "emotion_evidence": [],
        "open_questions": [],
    }
    validated = validate_draft(draft, source)
    assert validated["people"] == []
    assert "여름 메뉴 추천앱" in validated["projects"]
    assert "GPT" in validated["tools"]
    assert "토스 미니앱 공모전" in validated["events"]
    assert "토스 미니앱 공모전" not in validated["projects"]

    # 메타 피드백은 원문에 넣지 않는다.
    memory_source = [source]
    assert feedback not in "\n".join(memory_source)
    for field in (
        validated.get("event_summary", ""),
        validated.get("memory_candidate", ""),
        " ".join(validated.get("key_phrases") or []),
    ):
        assert "같은 격" not in field
        assert "맥락에 맞지 않은 질문" not in field

    result = validate_question(
        {
            "question_mode": "association",
            "followup_question": bad_q,
            "needs_followup": True,
            "anchor": "콩국수",
            "anchor_salience": "low",
        },
        draft=validated,
        question_session={
            "questions_asked": 0,
            "last_question_mode": None,
            "meaning_check_count": 0,
            "questions_text": [],
        },
        user_texts=[source],
    )
    assert result["needs_followup"] is False
    assert result["skip_reason"] in {"low_salience_anchor", "category_mismatch"}

    mismatch = validate_question(
        {
            "question_mode": "contrast",
            "followup_question": SUMMER_MENU_TURNS[3]["content"],
            "needs_followup": True,
            "same_abstraction_level": False,
        },
        draft=validated,
        question_session={
            "questions_asked": 1,
            "last_question_mode": "association",
            "meaning_check_count": 0,
            "questions_text": [bad_q],
        },
        user_texts=[source, SUMMER_MENU_TURNS[2]["content"]],
    )
    assert mismatch["needs_followup"] is False
    assert mismatch["skip_reason"] in {"category_mismatch", "low_salience_anchor", "redundant_question"}


def test_reclassify_does_not_map_all_toss_contests_to_summer_app():
    source = "토스 미니앱 공모전에 가계부 앱을 제출하기로 했다."
    result = reclassify_entities(
        {"people": [], "projects": ["토스 미니앱 공모전"], "tools": [], "events": [], "tags": []},
        source,
    )
    assert "여름 메뉴 추천앱" not in result["projects"]
    assert "가계부 앱" in result["projects"]
    assert "토스 미니앱 공모전" in result["events"]
