"""질문 품질·후속 응답 분류·엔티티 재분류 회귀 테스트."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from conversation_to_memory import failure_recorder
from conversation_to_memory.bot import session, states
from conversation_to_memory.bot.chat_service import handle_followup
from conversation_to_memory.bot.followup_response import classify_followup_response
from conversation_to_memory.memory.fidelity import (
    detect_event_entities,
    detect_project_entities,
    detect_tool_entities,
    reclassify_entities,
    validate_draft,
)
from conversation_to_memory.memory.question import validate_question
from conversation_to_memory.memory.question_quality import (
    assess_archive_gap,
    assess_reflective_handle_strength,
    evaluate_second_question_gate,
    has_same_abstraction_level,
    is_low_salience_anchor,
    is_question_already_answered,
    validate_question_candidate,
)


DOSTOEVSKY_SOURCE = (
    "주술회전 가챠에 총 38만 원을 썼다. "
    "관심 없는 캐릭터가 중복으로 나오면서 돈을 낭비했다고 느꼈다. "
    "돈을 쓰는 와중에 돈이 부족할 때마다 인기 작품을 썼다는 도스토옙스키의 일화를 떠올렸다. "
    "낭비한 돈을 복구하려면 7월 토스 미니앱 공모전에 참여할 수밖에 없겠다고 생각했다."
)

SUMMER_MENU_SOURCE = (
    "GPT와 아이디어 회의를 거쳐 토스 미니앱 공모전에 여름 메뉴 추천앱을 제출하기로 했다. "
    "음식이 떠오르지 않는 사람에게 몇 번의 질문으로 여름 음식을 추천하고 가게를 알려주는 앱이다. "
    "억지 광고를 유도하지 않는 제품이라는 점에 거리낌이 없다. "
    "음식 태깅과 디자인에 신경 쓰면 승산이 있다고 생각한다. "
    "7월 29일까지 완성하는 것이 가장 중요하다. "
    "다른 장기 프로젝트와 달리 단기 마감과 외부 반응이 필요한 프로젝트다. "
    "상금을 받아 가챠 지출을 만회하고 싶지만 우선 완성을 목표로 한다."
)


def _qsession(**kwargs):
    base = {
        "questions_asked": 0,
        "last_question_mode": None,
        "meaning_check_count": 0,
        "question_modes_used": [],
        "questions_text": [],
    }
    base.update(kwargs)
    return base


def test_dostoevsky_connection_already_answered():
    question = "도스토옙스키의 일화와 관련해, 그의 이야기가 현재 상황에 어떤 식으로 연결된다고 느끼나요?"
    assert is_question_already_answered(question, user_texts=[DOSTOEVSKY_SOURCE]) is True

    result = validate_question(
        {
            "question_mode": "association",
            "followup_question": question,
            "needs_followup": True,
        },
        draft={
            "topic": "가챠 지출",
            "event_summary": "가챠에 돈을 쓰고 도스토옙스키 일화를 떠올렸다.",
            "interpretation_risk": "low",
            "unsupported_inferences": [],
            "key_phrases": ["도스토옙스키의 일화"],
            "reflection_value": "medium",
        },
        question_session=_qsession(),
        user_texts=[DOSTOEVSKY_SOURCE],
    )
    assert result["needs_followup"] is False
    assert result["skip_reason"] == "answered_already"


def test_already_answered_candidate_rejected_even_with_strong_handle():
    ok, reason = validate_question_candidate(
        {
            "candidate_question": "도스토옙스키의 일화가 현재 상황에 어떻게 연결되나요?",
            "anchor": "도스토옙스키",
            "anchor_salience": "high",
            "expected_reflective_gain": "high",
            "already_answered": True,
            "question_mode": "association",
        },
        draft={"event_summary": "연결을 설명함", "key_phrases": ["도스토옙스키"]},
        user_texts=[DOSTOEVSKY_SOURCE],
    )
    assert ok is False
    assert reason == "answered_already"


def test_accurate_memory_can_still_ask_expansion_question():
    draft = {
        "topic": "가챠와 공모전",
        "event_summary": "가챠 낭비를 복구하려고 공모전 참여를 생각했다.",
        "interpretation_risk": "low",
        "unsupported_inferences": [],
        "key_phrases": ["낭비한 돈을 복구"],
        "reflection_value": "high",
        "reflection_seed_candidate": True,
        "emerging_themes": ["지출", "공모전"],
    }
    result = validate_question(
        {
            "question_mode": "archive_decision",
            "followup_question": "이번 기록의 중심이 지출 충격인가요, 그 충격이 공모전 참여 동기로 이어진 흐름인가요?",
            "needs_followup": True,
            "anchor_salience": "high",
            "expected_reflective_gain": "high",
        },
        draft=draft,
        question_session=_qsession(),
        user_texts=[DOSTOEVSKY_SOURCE],
    )
    assert result["needs_followup"] is True
    assert "도스토옙스키" not in result["followup_question"]


def test_archive_gap_none_does_not_force_global_skip():
    draft = {
        "topic": "정확한 기록",
        "event_summary": "정확한 요약",
        "interpretation_risk": "low",
        "unsupported_inferences": [],
        "key_phrases": ["열등감"],
        "reflection_value": "medium",
    }
    assert assess_archive_gap(draft=draft, user_texts=["열등감이 생겼다"]) == "none"
    strength = assess_reflective_handle_strength(
        draft=draft,
        user_texts=["열등감이 생겼다"],
        has_expansion_signal=True,
    )
    assert strength in {"weak", "strong"}

    result = validate_question(
        {
            "needs_followup": False,
            "followup_question": "",
            "skip_reason": "information_already_complete",
        },
        draft=draft,
        question_session=_qsession(),
        user_texts=["동기 승진을 보며 열등감이 생겼다."],
    )
    assert result["needs_followup"] is True


def test_key_phrase_alone_does_not_force_question():
    draft = {
        "topic": "짧은 메모",
        "event_summary": "회의가 있었다.",
        "interpretation_risk": "low",
        "unsupported_inferences": [],
        "key_phrases": ["회의"],
        "reflection_value": "low",
    }
    result = validate_question(
        {
            "needs_followup": False,
            "followup_question": "",
            "skip_reason": "no_reflective_handle",
        },
        draft=draft,
        question_session=_qsession(),
        user_texts=["회의가 있었다."],
    )
    # key_phrase만으로는 fallback 질문이 강제되지 않거나, 나와도 약한 일반론이 아님을 허용.
    # 손잡이 강도가 약하면 skip 유지.
    if result["needs_followup"]:
        assert "회의" in result["followup_question"]
    else:
        assert result["skip_reason"] in {
            "no_reflective_handle",
            "low_expected_gain",
            "question_candidate_not_generated",
        }


def test_low_salience_food_anchor_blocked():
    assert is_low_salience_anchor(
        "콩국수",
        draft={"emerging_themes": ["마감", "제품"], "event_summary": "단기 마감 프로젝트"},
        user_texts=[SUMMER_MENU_SOURCE],
    )
    ok, reason = validate_question_candidate(
        {
            "candidate_question": "여름 메뉴 추천앱을 개발하면서 어떤 특정한 음식이나 가게를 떠올렸나요?",
            "anchor": "콩국수",
            "anchor_salience": "low",
            "expected_reflective_gain": "medium",
            "question_mode": "association",
        },
        draft={"event_summary": "마감이 중요하다", "emerging_themes": ["마감"]},
        user_texts=[SUMMER_MENU_SOURCE],
    )
    assert ok is False
    assert reason == "low_salience_anchor"


def test_abstraction_mismatch_blocked():
    question = "콩국수와 감정에 따라 추천하는 방식 사이에서 어떤 점이 더 매력적으로 느껴지나요?"
    ok_level, reason = has_same_abstraction_level(question)
    assert ok_level is False
    assert reason == "category_mismatch"

    result = validate_question(
        {
            "question_mode": "contrast",
            "followup_question": question,
            "needs_followup": True,
            "same_abstraction_level": False,
        },
        draft={
            "topic": "여름 메뉴",
            "event_summary": "단기 마감 프로젝트를 진행한다.",
            "interpretation_risk": "low",
            "unsupported_inferences": [],
            "key_phrases": ["단기 마감"],
            "reflection_value": "high",
            "reflection_seed_candidate": True,
        },
        question_session=_qsession(),
        user_texts=[SUMMER_MENU_SOURCE],
    )
    assert result["needs_followup"] is False
    assert result["skip_reason"] == "category_mismatch"


def test_same_abstraction_contrast_allowed():
    ok, reason = validate_question_candidate(
        {
            "candidate_question": "음식명 기반 추천과 감정 기반 추천 중 어떤 축을 중심에 둘까요?",
            "anchor": "추천 방식",
            "anchor_salience": "high",
            "expected_reflective_gain": "high",
            "question_mode": "contrast",
            "same_abstraction_level": True,
            "comparison_axis": "추천 전략",
        },
        draft={"event_summary": "추천 전략을 고민한다", "emerging_themes": ["제품"]},
        user_texts=[SUMMER_MENU_SOURCE],
    )
    assert ok is True
    assert reason == ""


def test_classify_followup_response_kinds():
    assert classify_followup_response("돈을 복구할 생각을 하니 공모전에 참여해야겠다고 생각했다.") == "followup_answer"
    assert classify_followup_response("패스") == "pass"
    assert classify_followup_response("맥락에 맞지 않은 질문이야.") == "question_rejection"
    assert (
        classify_followup_response("둘 중 무엇이 낫냐고 물으려면 같은 격이어야 해.")
        == "meta_feedback"
    )
    assert classify_followup_response("수정 GPT는 people이 아니야.") == "correction"


def test_pass_goes_to_review_without_memory_source(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        failure_recorder,
        "_default_recorder",
        failure_recorder.FailureRecorder(tmp_path / "failures.jsonl"),
    )
    user_data = {
        session.KEY_CURRENT_SESSION: {
            "conversation": [{"role": "assistant", "content": "질문이 있습니다?"}],
            "user_texts": ["원문"],
            "original_user_texts": ["원문"],
            "accepted_followup_answers": [],
            "interaction_feedback": [],
        },
        session.KEY_CURRENT_DRAFT: {
            "topic": "t",
            "event_summary": "요약",
            "people": [],
            "projects": [],
            "tags": [],
            "key_phrases": [],
            "emerging_themes": [],
            "open_questions": [],
            "value_tags": [],
            "interpretation_risk": "low",
            "unsupported_inferences": [],
            "memory_candidate": "후보",
            "model_interpretation": "",
            "user_emotions": [],
            "emotion_evidence": [],
            "reflection_value": "medium",
            "memory_type": "event",
            "reflection_seed_candidate": False,
            "temporal_status": "past",
            "question_mode_used": [],
        },
        session.KEY_QUESTION_SESSION: _qsession(questions_asked=1, questions_text=["Q1"]),
    }
    with patch("conversation_to_memory.bot.chat_service.db.save_active_draft"):
        result = handle_followup("u1", user_data, "패스")
    assert result.state == states.REVIEW
    assert user_data[session.KEY_CURRENT_SESSION]["user_texts"] == ["원문"]
    assert user_data[session.KEY_CURRENT_SESSION]["interaction_feedback"]


def test_meta_feedback_excluded_from_memory_and_logged(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "failures.jsonl"
    monkeypatch.setattr(failure_recorder, "_default_recorder", failure_recorder.FailureRecorder(log_path))
    user_data = {
        session.KEY_CURRENT_SESSION: {
            "conversation": [
                {
                    "role": "assistant",
                    "content": "콩국수와 감정 기반 추천 중 무엇이 매력적인가요?",
                }
            ],
            "user_texts": [SUMMER_MENU_SOURCE],
            "original_user_texts": [SUMMER_MENU_SOURCE],
            "accepted_followup_answers": [],
            "interaction_feedback": [],
        },
        session.KEY_CURRENT_DRAFT: {
            "topic": "여름 메뉴",
            "event_summary": "마감이 중요하다",
            "people": [],
            "projects": [],
            "tags": [],
            "key_phrases": [],
            "emerging_themes": [],
            "open_questions": [],
            "value_tags": [],
            "interpretation_risk": "low",
            "unsupported_inferences": [],
            "memory_candidate": "후보",
            "model_interpretation": "",
            "user_emotions": [],
            "emotion_evidence": [],
            "reflection_value": "medium",
            "memory_type": "event",
            "reflection_seed_candidate": False,
            "temporal_status": "past",
            "question_mode_used": [],
        },
        session.KEY_QUESTION_SESSION: _qsession(questions_asked=1, questions_text=["Q1"]),
    }
    with patch("conversation_to_memory.bot.chat_service.db.save_active_draft"):
        result = handle_followup(
            "u1",
            user_data,
            "둘 중 무엇이 낫냐고 물으려면 같은 격이어야 해.",
        )
    assert result.state == states.REVIEW
    assert SUMMER_MENU_SOURCE in user_data[session.KEY_CURRENT_SESSION]["user_texts"]
    assert all(
        "같은 격" not in text
        for text in user_data[session.KEY_CURRENT_SESSION]["user_texts"]
    )
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines
    assert json.loads(lines[-1])["failure_type"] == "category_mismatch"


def test_question_rejection_blocks_second_question(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "failures.jsonl"
    monkeypatch.setattr(
        failure_recorder,
        "_default_recorder",
        failure_recorder.FailureRecorder(log_path),
    )
    user_data = {
        session.KEY_CURRENT_SESSION: {
            "conversation": [{"role": "assistant", "content": "질문이 이상했나요?"}],
            "user_texts": ["원문"],
            "original_user_texts": ["원문"],
            "accepted_followup_answers": [],
            "interaction_feedback": [],
        },
        session.KEY_CURRENT_DRAFT: {
            "topic": "t",
            "event_summary": "요약",
            "people": [],
            "projects": [],
            "tags": [],
            "key_phrases": [],
            "emerging_themes": [],
            "open_questions": [],
            "value_tags": [],
            "interpretation_risk": "low",
            "unsupported_inferences": [],
            "memory_candidate": "",
            "model_interpretation": "",
            "user_emotions": [],
            "emotion_evidence": [],
            "reflection_value": "medium",
            "memory_type": "event",
            "reflection_seed_candidate": False,
            "temporal_status": "past",
            "question_mode_used": [],
        },
        session.KEY_QUESTION_SESSION: _qsession(questions_asked=1, questions_text=["Q1"]),
    }
    with patch("conversation_to_memory.bot.chat_service.db.save_active_draft"):
        with patch(
            "conversation_to_memory.bot.chat_service._maybe_followup_or_review"
        ) as mock_follow:
            result = handle_followup("u1", user_data, "맥락에 맞지 않은 질문이야.")
    assert result.state == states.REVIEW
    mock_follow.assert_not_called()


def test_correction_routed_as_edit(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        failure_recorder,
        "_default_recorder",
        failure_recorder.FailureRecorder(tmp_path / "failures.jsonl"),
    )
    user_data = {
        session.KEY_CURRENT_SESSION: {
            "conversation": [],
            "user_texts": [SUMMER_MENU_SOURCE],
            "original_user_texts": [SUMMER_MENU_SOURCE],
            "accepted_followup_answers": [],
            "interaction_feedback": [],
        },
        session.KEY_CURRENT_DRAFT: {"event_summary": "요약", "people": ["GPT"]},
        session.KEY_QUESTION_SESSION: _qsession(questions_asked=1, questions_text=["Q1"]),
    }

    def _fake_analyze(**kwargs):
        assert kwargs.get("edit_instruction")
        assert "GPT는 people이 아니야" in kwargs["edit_instruction"]
        return {
            "topic": "여름 메뉴",
            "event_summary": "요약",
            "people": [],
            "projects": ["여름 메뉴 추천앱"],
            "tools": ["GPT"],
            "events": ["토스 미니앱 공모전"],
            "tags": [],
            "key_phrases": [],
            "emerging_themes": [],
            "open_questions": [],
            "value_tags": [],
            "interpretation_risk": "low",
            "unsupported_inferences": [],
            "memory_candidate": "",
            "model_interpretation": "",
            "user_emotions": [],
            "emotion_evidence": [],
            "reflection_value": "medium",
            "memory_type": "event",
            "reflection_seed_candidate": False,
            "temporal_status": "past",
            "question_mode_used": [],
        }

    with patch("conversation_to_memory.bot.chat_service.db.save_active_draft"):
        with patch(
            "conversation_to_memory.bot.chat_service.memory_service.analyze_recording",
            side_effect=_fake_analyze,
        ):
            result = handle_followup("u1", user_data, "수정 GPT는 people이 아니야.")
    assert result.state == states.REVIEW
    assert user_data[session.KEY_CURRENT_SESSION]["user_texts"] == [SUMMER_MENU_SOURCE]


def test_second_question_allowed_on_new_tradeoff():
    gate = evaluate_second_question_gate(
        question_session=_qsession(questions_asked=1, questions_text=["첫 질문"]),
        response_kind="followup_answer",
        original_user_texts=[SUMMER_MENU_SOURCE],
        accepted_answer="상금보다 우선 완성이 중요하다는 점이 더 선명해졌다.",
        previous_question="첫 질문",
        new_question="완성 우선과 상금 우선 중 어디에 더 무게를 두나요?",
        new_reflective_handle_strength="strong",
        new_unresolved_point="완성 vs 상금",
    )
    assert gate["second_question_allowed"] is True


def test_second_question_blocked_on_repeat_answer():
    gate = evaluate_second_question_gate(
        question_session=_qsession(questions_asked=1),
        response_kind="followup_answer",
        original_user_texts=[DOSTOEVSKY_SOURCE],
        accepted_answer="도스토옙스키의 일화를 떠올렸다.",
        previous_question="연결이 뭔가요?",
        new_reflective_handle_strength="strong",
        new_unresolved_point="x",
    )
    assert gate["second_question_allowed"] is False
    assert gate["second_question_gate_reason"] == "answer_repeats_source"


def test_second_question_blocked_on_pass_and_meta():
    for kind in ("pass", "question_rejection", "meta_feedback", "correction"):
        gate = evaluate_second_question_gate(
            question_session=_qsession(questions_asked=1),
            response_kind=kind,
            original_user_texts=["원문"],
            accepted_answer="패스",
            new_reflective_handle_strength="strong",
            new_unresolved_point="새 지점",
        )
        assert gate["second_question_allowed"] is False


def test_second_question_not_redundant_and_max_two():
    gate = evaluate_second_question_gate(
        question_session=_qsession(questions_asked=1, questions_text=["비슷한 점과 다른 점은?"]),
        response_kind="followup_answer",
        original_user_texts=["원문 긴 내용입니다. " * 5],
        accepted_answer="새로운 가치 충돌이 생겼다. 완성 우선이 더 중요하다.",
        previous_question="비슷한 점과 다른 점은?",
        new_question="비슷한 점과 다른 점은 무엇인가요?",
        new_reflective_handle_strength="strong",
        new_unresolved_point="완성 우선",
    )
    assert gate["second_question_allowed"] is False
    assert gate["second_question_gate_reason"] == "redundant_question"

    gate2 = evaluate_second_question_gate(
        question_session=_qsession(questions_asked=2),
        response_kind="followup_answer",
        original_user_texts=["원문"],
        accepted_answer="새 정보",
        new_reflective_handle_strength="strong",
        new_unresolved_point="x",
    )
    assert gate2["second_question_gate_reason"] == "max_questions_reached"


def test_entities_summer_menu_case():
    draft = {
        "people": ["GPT"],
        "projects": ["토스 미니앱 공모전"],
        "tools": [],
        "events": [],
        "tags": [],
    }
    result = reclassify_entities(draft, SUMMER_MENU_SOURCE)
    assert result["people"] == []
    assert "여름 메뉴 추천앱" in result["projects"]
    assert "GPT" in result["tools"]
    assert "토스 미니앱 공모전" in result["events"]
    assert "토스 미니앱 공모전" not in result["projects"]


def test_toss_contest_not_globally_mapped_to_summer_app():
    other = "토스 미니앱 공모전에 가계부 앱을 제출하기로 했다."
    projects = detect_project_entities(other)
    events = detect_event_entities(other)
    assert "여름 메뉴 추천앱" not in projects
    assert "가계부 앱" in projects
    assert "토스 미니앱 공모전" in events


def test_gpt_not_in_people_after_validate():
    validated = validate_draft(
        {
            "topic": "여름 메뉴",
            "event_summary": "GPT와 회의 후 앱을 제출하기로 했다.",
            "people": ["GPT"],
            "projects": [],
            "tags": [],
            "value_tags": [],
            "memory_type": "event",
            "interpretation_risk": "low",
            "unsupported_inferences": [],
        },
        SUMMER_MENU_SOURCE,
    )
    assert "GPT" not in validated["people"]
    assert "GPT" in validated["tools"]
    assert "여름 메뉴 추천앱" in validated["projects"]


def test_failure_records_a_and_b_appended(tmp_path: Path):
    log_path = tmp_path / "interpretation_failures.jsonl"
    a = failure_recorder.record_static_failure_case(
        failure_type="redundant_question",
        context=[
            {"role": "user", "content": DOSTOEVSKY_SOURCE},
            {
                "role": "assistant",
                "content": "도스토옙스키의 일화와 관련해, 그의 이야기가 현재 상황에 어떤 식으로 연결된다고 느끼나요?",
            },
        ],
        user_correction="이미 앞에서 말했잖아.",
        assistant_output="비슷한 점과 다른 점은 무엇인가요?",
        conversation_id="telegram_20260712_dostoevsky_redundant_question",
        notes="원문에 이미 연결이 설명됐는데 동일 내용을 재질문하고 유사 비교 질문을 추가함.",
        log_path=log_path,
    )
    b = failure_recorder.record_static_failure_case(
        failure_type="low_salience_anchor",
        context=[
            {"role": "user", "content": SUMMER_MENU_SOURCE},
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
        ],
        user_correction="맥락에 맞지 않은 질문이야. 둘 중 무엇이 낫냐고 물으려면 같은 격이어야 해.",
        assistant_output="콩국수와 감정에 따라 추천하는 방식 사이에서 어떤 점이 더 매력적으로 느껴지나요?",
        conversation_id="telegram_20260712_summer_menu_low_salience_anchor",
        notes="낮은 중요도 앵커, 추상화 수준 불일치, 메타 피드백 원문 유입, GPT people 오분류.",
        severity="high",
        log_path=log_path,
    )
    assert a["failure_type"] == "redundant_question"
    assert b["failure_type"] == "low_salience_anchor"
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
