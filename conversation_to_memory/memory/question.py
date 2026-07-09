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
    if not result["needs_followup"]:
        result["followup_question"] = ""
        if not result["skip_reason"]:
            result["skip_reason"] = "information_already_complete"
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

    if should_skip_followup_after_summary(
        user_texts=user_texts,
        latest_user_text=latest_user_text,
        conversation=conversation,
    ):
        validated["needs_followup"] = False
        validated["followup_question"] = ""
        validated["skip_reason"] = "summary_with_negative_emotion"
        draft["interpretation_risk"] = "high"
        return validated

    if latest_user_text and has_fatigue_signal(latest_user_text):
        validated["needs_followup"] = False
        validated["followup_question"] = ""
        validated["skip_reason"] = "fatigue_keyword_detected"
        return validated

    question = validated.get("followup_question", "")
    if not question:
        mode, fallback = build_grounded_expansion_question(
            draft=draft,
            user_texts=user_texts,
            conversation=conversation,
        )
        if fallback and validated.get("skip_reason") in (
            "",
            "information_already_complete",
            "empty_question_generated",
        ):
            validated["needs_followup"] = True
            validated["followup_question"] = fallback
            validated["question_mode"] = mode
            validated["skip_reason"] = ""
            question = fallback
        else:
            validated["needs_followup"] = False
            if not validated.get("skip_reason"):
                validated["skip_reason"] = "no_reflective_handle"
            return validated

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
        draft["interpretation_risk"] = "high"
        return validated

    if question.count("?") > 1 or question.count("？") > 1:
        validated["needs_followup"] = False
        validated["followup_question"] = ""
        validated["skip_reason"] = "multiple_questions_in_one"
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

    return validated


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
