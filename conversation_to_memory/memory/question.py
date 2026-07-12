"""회고형 후속 질문 생성 및 검증."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from conversation_to_memory.memory.fidelity import (
    FORBIDDEN_INFERENCE_TERMS,
    GROWTH_NARRATIVE_PHRASES,
)
from conversation_to_memory.failure_recorder import (
    detect_inappropriate_positive_reframe_risk,
    user_has_negative_emotion_context,
)
from conversation_to_memory.memory.question_quality import (
    assess_archive_gap,
    assess_reflective_handle_strength,
    decide_question_policy,
    evaluate_second_question_gate,
    is_question_already_answered,
    normalize_candidate,
    select_best_candidate,
    validate_question_candidate,
)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

VALID_QUESTION_MODES = frozenset(
    {
        "meaning_check",
        "emotion_probe",
        "association",
        "memory_link",
        "value_probe",
        "contrast",
        "future_reflection",
        "archive_decision",
    }
)

FATIGUE_KEYWORDS = ("됐어", "됐다", "그만", "모르겠", "싫어", "중단", "패스")

# 긴 본문에서도 명시적으로 질문 중단을 뜻하는 표현.
EXPLICIT_STOP_PHRASES = ("질문 그만", "그만 물어", "질문하지 마", "질문 안 해도")

# 피로 키워드가 짧은 답변에 있을 때만 피로 신호로 본다.
# "왜 그런지 모르겠다" 같은 긴 성찰형 문장의 "모르겠다"는 중단 신호가 아니다.
FATIGUE_SHORT_REPLY_MAX_CHARS = 25


def has_fatigue_signal(latest_user_text: str) -> bool:
    """사용자가 질문을 그만 받고 싶다는 신호인지 판단."""
    text = latest_user_text.strip()
    if not text:
        return False
    if any(phrase in text for phrase in EXPLICIT_STOP_PHRASES):
        return True
    if len(text) <= FATIGUE_SHORT_REPLY_MAX_CHARS and any(
        keyword in text for keyword in FATIGUE_KEYWORDS
    ):
        return True
    return False

FORBIDDEN_QUESTION_PHRASES = (
    "배운 점",
    "견뎌",
    "칭찬",
    "교훈",
    "깨달음",
    "극복",
    "어떻게 해결",
    "앞으로 어떻게",
)

# 정확히 요약된 기록이라도 새 생각으로 이어질 수 있는 원문 손잡이.
# 이 신호는 meaning_check가 아니라 association/contrast/value_probe 후보로만 사용한다.
EXPANSION_SIGNAL_KEYWORDS = (
    "기억이 났",
    "떠올",
    "아쉬",
    "자제해야",
    "불확실",
    "열등감",
    "거리낌",
    "원하는 방향",
    "만들고 싶",
    "중요하게",
    "판단",
    "기준",
    "새로운 관점",
    "새로운 생각",
    "만족도",
    "후속질문",
    "질문",
)

DEFAULT_QUESTION_RESULT: dict[str, Any] = {
    "topic": "",
    "emotion": {"labels": [], "evidence_strength": "none"},
    "unresolved_point": "",
    "possible_memory_value": "medium",
    "question_mode": "association",
    "followup_question": "",
    "needs_followup": False,
    "open_questions": [],
    "reasoning": "",
    "skip_reason": "",
    "archive_gap": "none",
    "reflective_handle_strength": "none",
    "candidates": [],
    "rejected_candidates": [],
    "selected_anchor": "",
    "candidate_count": 0,
    "question_outcome": "",
}


def is_reflection_agent_enabled() -> bool:
    return os.getenv("REFLECTION_AGENT_ENABLED", "false").lower() in ("true", "1", "yes")


def get_max_questions() -> int:
    raw = os.getenv("REFLECTION_MAX_QUESTIONS", "2")
    try:
        return max(1, int(raw))
    except ValueError:
        return 2


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
    return OpenAI(api_key=api_key)


def _get_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def can_use_meaning_check(
    *,
    draft: dict,
    question_session: dict,
) -> bool:
    if question_session.get("meaning_check_count", 0) >= 1:
        return False
    if question_session.get("last_question_mode") == "meaning_check":
        return False
    if draft.get("interpretation_risk", "low") == "low" and not draft.get("unsupported_inferences"):
        return False
    return True


def _build_question_user_content(
    *,
    user_texts: list[str],
    conversation: list[dict] | None,
    draft: dict,
    question_session: dict,
    recent_context: list[dict] | None = None,
) -> str:
    parts = [
        "아래 사용자 원문과 현재 초안을 바탕으로 후속 질문 1개를 생성하세요.",
        f"## 사용자 원문\n{chr(10).join(user_texts)}",
        "## 현재 초안",
        json.dumps(
            {
                "topic": draft.get("topic"),
                "event_summary": draft.get("event_summary"),
                "memory_candidate": draft.get("memory_candidate"),
                "key_phrases": draft.get("key_phrases", []),
                "emerging_themes": draft.get("emerging_themes", []),
                "reflection_value": draft.get("reflection_value"),
                "memory_type": draft.get("memory_type"),
                "interpretation_risk": draft.get("interpretation_risk"),
                "unsupported_inferences": draft.get("unsupported_inferences", []),
            },
            ensure_ascii=False,
            indent=2,
        ),
        "## 질문 세션 상태",
        json.dumps(
            {
                "questions_asked": question_session.get("questions_asked", 0),
                "question_modes_used": question_session.get("question_modes_used", []),
                "meaning_check_count": question_session.get("meaning_check_count", 0),
                "last_question_mode": question_session.get("last_question_mode"),
                "meaning_check_allowed": can_use_meaning_check(
                    draft=draft, question_session=question_session
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
    ]

    if recent_context:
        parts.append("## 최근 기록 맥락")
        for idx, ctx in enumerate(recent_context[-3:], 1):
            parts.append(f"{idx}. 요약: {ctx.get('event_summary', '')}")

    if conversation:
        parts.append("## 추가 대화")
        for turn in conversation:
            role = "사용자" if turn["role"] == "user" else "봇"
            parts.append(f"{role}: {turn['content']}")

    return "\n\n".join(parts)


def normalize_question_result(data: dict) -> dict:
    result = {**DEFAULT_QUESTION_RESULT}
    result.update(data)

    mode = result.get("question_mode", "association")
    if mode not in VALID_QUESTION_MODES:
        mode = "association"
    result["question_mode"] = mode

    emotion = result.get("emotion") or {}
    if not isinstance(emotion, dict):
        emotion = {}
    strength = emotion.get("evidence_strength", "none")
    if strength not in ("none", "weak", "medium", "strong"):
        strength = "none"
    result["emotion"] = {
        "labels": list(emotion.get("labels") or []),
        "evidence_strength": strength,
    }

    value = result.get("possible_memory_value", "medium")
    if value not in ("low", "medium", "high"):
        value = "medium"
    result["possible_memory_value"] = value

    result["open_questions"] = list(result.get("open_questions") or [])
    result["needs_followup"] = bool(result.get("needs_followup"))
    result["followup_question"] = str(result.get("followup_question") or "").strip()
    result["skip_reason"] = str(result.get("skip_reason") or "").strip()
    result["archive_gap"] = str(result.get("archive_gap") or "none").strip() or "none"
    if result["archive_gap"] not in ("none", "minor", "major"):
        result["archive_gap"] = "none"
    result["reflective_handle_strength"] = (
        str(result.get("reflective_handle_strength") or "none").strip() or "none"
    )
    if result["reflective_handle_strength"] not in ("none", "weak", "strong"):
        result["reflective_handle_strength"] = "none"
    result["candidates"] = list(result.get("candidates") or [])
    result["rejected_candidates"] = list(result.get("rejected_candidates") or [])
    result["selected_anchor"] = str(result.get("selected_anchor") or "").strip()
    result["candidate_count"] = int(result.get("candidate_count") or len(result["candidates"]))
    result["question_outcome"] = str(result.get("question_outcome") or "").strip()
    if not result["needs_followup"]:
        result["followup_question"] = ""
        if not result["skip_reason"]:
            # information_already_complete는 archive_gap=none만으로 쓰지 않는다.
            if result["reflective_handle_strength"] in ("none", ""):
                result["skip_reason"] = "no_reflective_handle"
            else:
                result["skip_reason"] = "low_expected_gain"
    return result


def _combined_user_text(
    *,
    user_texts: list[str] | None = None,
    latest_user_text: str = "",
    conversation: list[dict] | None = None,
) -> str:
    parts: list[str] = []
    if user_texts:
        parts.extend(user_texts)
    if conversation:
        parts.extend(
            turn["content"] for turn in conversation if turn.get("role") == "user"
        )
    if latest_user_text:
        parts.append(latest_user_text)
    return " ".join(parts)


def _draft_signal_text(draft: dict) -> str:
    parts: list[str] = []
    for key in ("topic", "event_summary", "memory_candidate"):
        value = draft.get(key)
        if value:
            parts.append(str(value))
    for key in ("key_phrases", "emerging_themes", "value_tags"):
        values = draft.get(key) or []
        if isinstance(values, list):
            parts.extend(str(item) for item in values if item)
    return " ".join(parts)


def has_reflective_expansion_signal(
    *,
    draft: dict,
    user_texts: list[str] | None = None,
    conversation: list[dict] | None = None,
) -> bool:
    """정확한 요약 너머로 안전하게 확장할 만한 원문 손잡이가 있는지 판단."""
    source = " ".join(
        [
            _combined_user_text(user_texts=user_texts, conversation=conversation),
            _draft_signal_text(draft),
        ]
    )
    if any(keyword in source for keyword in EXPANSION_SIGNAL_KEYWORDS):
        return True
    if draft.get("reflection_seed_candidate"):
        return True
    if draft.get("reflection_value") in ("medium", "high") and draft.get("key_phrases"):
        return True
    return False


def _first_compact_key_phrase(draft: dict) -> str:
    for phrase in draft.get("key_phrases") or []:
        text = str(phrase).strip()
        if 2 <= len(text) <= 45:
            return text
    return ""


def build_grounded_expansion_question(
    *,
    draft: dict,
    user_texts: list[str] | None = None,
    conversation: list[dict] | None = None,
) -> tuple[str, str]:
    """LLM이 complete로 스킵한 경우 사용할 보수적 확장 질문 후보."""
    source = " ".join(
        [
            _combined_user_text(user_texts=user_texts, conversation=conversation),
            _draft_signal_text(draft),
        ]
    )

    if "후속질문" in source or ("질문" in source and "새로운" in source):
        return (
            "association",
            "예전에 새로운 생각으로 이어졌던 질문은 어떤 방식이었는지 떠오르는 예가 있나요?",
        )
    if "열등감" in source:
        return (
            "association",
            "'열등감'이 자리를 차지했다는 표현에서, 비교의 기준이 가장 선명해진 순간이 있었나요?",
        )
    if "자제해야" in source or "술 마시는" in source:
        return (
            "archive_decision",
            "'자제해야 하는데'라는 말에서, 이번 기록에 남기고 싶은 건 아쉬움 쪽인가요 아니면 스트레스 푸는 방식에 대한 경계 쪽인가요?",
        )

    phrase = _first_compact_key_phrase(draft)
    if phrase:
        return (
            "association",
            f"'{phrase}'라는 표현을 나중에 다시 읽을 때, 어떤 장면이나 맥락이 같이 떠오르면 좋을까요?",
        )

    if has_reflective_expansion_signal(
        draft=draft,
        user_texts=user_texts,
        conversation=conversation,
    ):
        return (
            "contrast",
            "이 기록을 나중에 다시 읽는다면, 지금 말한 내용 중 어떤 표현이 가장 먼저 떠오르면 좋을까요?",
        )
    return "", ""


def should_skip_followup_after_summary(
    *,
    user_texts: list[str] | None = None,
    latest_user_text: str = "",
    conversation: list[dict] | None = None,
) -> bool:
    """요약 요청 + 부정 감정이 충분히 드러난 경우 추가 질문 생략."""
    if latest_user_text.strip() != "요약":
        return False
    prior_text = _combined_user_text(
        user_texts=user_texts,
        conversation=conversation,
    )
    return user_has_negative_emotion_context(prior_text)


def _extract_candidates_from_result(result: dict) -> list[dict[str, Any]]:
    """LLM 결과에서 후보 목록을 정규화한다. 단일 질문도 후보 1개로 취급."""
    raw_candidates = result.get("candidates")
    candidates: list[dict[str, Any]] = []
    if isinstance(raw_candidates, list):
        for item in raw_candidates:
            if isinstance(item, dict):
                candidates.append(normalize_candidate(item))
    question = str(result.get("followup_question") or "").strip()
    if question and not any(c.get("candidate_question") == question for c in candidates):
        candidates.insert(
            0,
            normalize_candidate(
                {
                    "candidate_question": question,
                    "question_mode": result.get("question_mode", "association"),
                    "anchor": result.get("selected_anchor") or "",
                    "anchor_salience": result.get("anchor_salience", "medium"),
                    "expected_reflective_gain": result.get(
                        "expected_reflective_gain", "medium"
                    ),
                    "already_answered": result.get("already_answered", False),
                    "same_abstraction_level": result.get("same_abstraction_level", True),
                    "comparison_axis": result.get("comparison_axis", ""),
                    "grounding_quote": result.get("grounding_quote", ""),
                    "unexplored_dimension": result.get("unresolved_point", ""),
                }
            ),
        )
    return candidates


def validate_question(
    result: dict,
    *,
    draft: dict,
    question_session: dict,
    latest_user_text: str = "",
    user_texts: list[str] | None = None,
    conversation: list[dict] | None = None,
) -> dict:
    """질문 품질 검증 및 meaning_check 제한 적용."""
    validated = normalize_question_result(result)

    expansion = has_reflective_expansion_signal(
        draft=draft,
        user_texts=user_texts,
        conversation=conversation,
    )
    archive_gap = assess_archive_gap(draft=draft, user_texts=user_texts)
    handle_strength = assess_reflective_handle_strength(
        draft=draft,
        user_texts=user_texts,
        conversation=conversation,
        has_expansion_signal=expansion,
    )
    # LLM이 준 값이 있으면 보수적으로 상향만 허용하지 않고 코드 평가를 우선한다.
    validated["archive_gap"] = archive_gap
    validated["reflective_handle_strength"] = handle_strength

    if should_skip_followup_after_summary(
        user_texts=user_texts,
        latest_user_text=latest_user_text,
        conversation=conversation,
    ):
        validated["needs_followup"] = False
        validated["followup_question"] = ""
        validated["skip_reason"] = "summary_with_negative_emotion"
        validated["question_outcome"] = "question_candidate_rejected"
        draft["interpretation_risk"] = "high"
        return validated

    if latest_user_text and has_fatigue_signal(latest_user_text):
        validated["needs_followup"] = False
        validated["followup_question"] = ""
        validated["skip_reason"] = "fatigue_keyword_detected"
        validated["question_outcome"] = "question_candidate_rejected"
        return validated

    policy = decide_question_policy(
        archive_gap=archive_gap,
        reflective_handle_strength=handle_strength,
        hard_stop=False,
    )

    candidates = _extract_candidates_from_result(validated)
    validated["candidate_count"] = len(candidates)

    # LLM이 비어 있는 complete skip을 보냈을 때 확장 손잡이가 있으면 fallback 후보 생성.
    # archive_gap=none만으로 전체 질문을 생략하지 않는다.
    if not candidates and policy.get("allow_expansion_modes"):
        mode, fallback = build_grounded_expansion_question(
            draft=draft,
            user_texts=user_texts,
            conversation=conversation,
        )
        if fallback:
            candidates = [
                normalize_candidate(
                    {
                        "candidate_question": fallback,
                        "question_mode": mode,
                        "anchor_salience": "medium",
                        "expected_reflective_gain": "medium",
                    }
                )
            ]
            validated["candidate_count"] = len(candidates)
            validated["question_outcome"] = "question_candidate_generated"

    if not candidates:
        validated["needs_followup"] = False
        validated["followup_question"] = ""
        if not policy.get("allow_question"):
            validated["skip_reason"] = policy.get("reason") or "no_reflective_handle"
        elif not validated.get("skip_reason") or validated["skip_reason"] in {
            "information_already_complete",
            "low_expected_gain",
        }:
            validated["skip_reason"] = "no_reflective_handle"
        validated["question_outcome"] = "question_candidate_not_generated"
        return validated

    selected, rejected = select_best_candidate(
        candidates,
        draft=draft,
        user_texts=user_texts,
    )
    validated["rejected_candidates"] = rejected

    if selected is None:
        validated["needs_followup"] = False
        validated["followup_question"] = ""
        reason = rejected[-1]["reason"] if rejected else "low_expected_gain"
        # archive_gap=none만으로 전체 skip하지 않음 — 거절 사유를 보존.
        if reason == "answered_already":
            validated["skip_reason"] = "answered_already"
        elif reason == "redundant_question":
            validated["skip_reason"] = "redundant_question"
        else:
            validated["skip_reason"] = reason
        validated["question_outcome"] = "question_candidate_rejected"
        return validated

    question = selected["candidate_question"]
    validated["needs_followup"] = True
    validated["followup_question"] = question
    validated["question_mode"] = selected.get("question_mode") or validated["question_mode"]
    validated["selected_anchor"] = selected.get("anchor") or ""
    validated["skip_reason"] = ""
    validated["question_outcome"] = "question_candidate_generated"

    # meaning_check는 위험도/세션 게이트로만 제한. 전체 질문 금지가 아니다.
    mode = validated.get("question_mode", "association")
    if mode == "meaning_check" and (
        not policy.get("allow_meaning_check")
        or not can_use_meaning_check(draft=draft, question_session=question_session)
    ):
        if archive_gap == "major":
            pass
        else:
            validated["question_mode"] = "association"

    user_messages = _combined_user_text(
        user_texts=user_texts,
        latest_user_text=latest_user_text,
        conversation=conversation,
    )
    if detect_inappropriate_positive_reframe_risk(
        user_messages=user_messages,
        question=question,
    ):
        validated["needs_followup"] = False
        validated["followup_question"] = ""
        validated["skip_reason"] = "positive_reframe_risk"
        validated["question_outcome"] = "question_candidate_rejected"
        draft["interpretation_risk"] = "high"
        return validated

    if question.count("?") > 1 or question.count("？") > 1:
        validated["needs_followup"] = False
        validated["followup_question"] = ""
        validated["skip_reason"] = "multiple_questions_in_one"
        validated["question_outcome"] = "question_candidate_rejected"
        return validated

    for phrase in FORBIDDEN_QUESTION_PHRASES + GROWTH_NARRATIVE_PHRASES:
        if phrase in question:
            validated["question_mode"] = "association"
            break

    for term in FORBIDDEN_INFERENCE_TERMS:
        if term in question:
            validated["needs_followup"] = False
            validated["followup_question"] = ""
            validated["skip_reason"] = "forbidden_inference_term"
            validated["question_outcome"] = "question_candidate_rejected"
            return validated

    if is_question_already_answered(
        question, user_texts=user_texts, draft=draft
    ):
        validated["needs_followup"] = False
        validated["followup_question"] = ""
        validated["skip_reason"] = "answered_already"
        validated["rejected_candidates"] = list(validated["rejected_candidates"]) + [
            {"question": question, "reason": "answered_already"}
        ]
        validated["question_outcome"] = "question_candidate_rejected"
        return validated

    mode = validated.get("question_mode", "association")
    if mode == "meaning_check" and not can_use_meaning_check(
        draft=draft, question_session=question_session
    ):
        validated["question_mode"] = "association"

    if question_session.get("last_question_mode") == validated["question_mode"]:
        if validated["question_mode"] == "meaning_check":
            validated["question_mode"] = "association"
        elif validated["question_mode"] == "association":
            validated["question_mode"] = "contrast"

    if validated["question_mode"] == "meaning_check" and not can_use_meaning_check(
        draft=draft, question_session=question_session
    ):
        validated["question_mode"] = "association"

    # 직전 질문과 의미 중복이면 거절.
    previous_questions = question_session.get("questions_text") or []
    if previous_questions:
        from conversation_to_memory.memory.question_quality import questions_are_redundant

        if questions_are_redundant(previous_questions[-1], question):
            validated["needs_followup"] = False
            validated["followup_question"] = ""
            validated["skip_reason"] = "redundant_question"
            validated["question_outcome"] = "question_candidate_rejected"
            return validated

    return validated


# 하위 호환: 외부에서 second gate 평가를 직접 호출할 수 있게 re-export.
__all_reexports__ = (
    "evaluate_second_question_gate",
    "validate_question_candidate",
    "assess_archive_gap",
    "assess_reflective_handle_strength",
)

def generate_question(
    *,
    user_texts: list[str],
    conversation: list[dict] | None = None,
    draft: dict,
    question_session: dict,
    recent_context: list[dict] | None = None,
) -> dict:
    """후속 질문 1개 생성."""
    if question_session.get("questions_asked", 0) >= get_max_questions():
        return normalize_question_result(
            {
                "needs_followup": False,
                "followup_question": "",
                "skip_reason": "max_questions_reached",
            }
        )

    client = _get_client()
    system = _load_prompt("question_generation_prompt.txt")
    user_content = _build_question_user_content(
        user_texts=user_texts,
        conversation=conversation,
        draft=draft,
        question_session=question_session,
        recent_context=recent_context,
    )

    response = client.chat.completions.create(
        model=_get_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=0.45,
        max_tokens=800,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()
    data = json.loads(raw)
    latest_user = ""
    if user_texts:
        latest_user = user_texts[-1]
    return validate_question(
        data,
        draft=draft,
        question_session=question_session,
        latest_user_text=latest_user,
        user_texts=user_texts,
        conversation=conversation,
    )


def merge_question_into_draft(draft: dict, question_result: dict) -> dict:
    """질문 결과에서 draft에 반영할 필드를 병합."""
    merged = dict(draft)
    open_q = question_result.get("open_questions") or []
    if open_q:
        existing = list(merged.get("open_questions") or [])
        for item in open_q:
            if item and item not in existing:
                existing.append(item)
        merged["open_questions"] = existing

    value = question_result.get("possible_memory_value")
    if value in ("low", "medium", "high"):
        merged["reflection_value"] = value
    return merged
