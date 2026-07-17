"""후속 질문 응답 분류 — 기억 원문과 상호작용 피드백을 분리한다."""

from __future__ import annotations

import re
from typing import Literal

FollowupResponseKind = Literal[
    "followup_answer",
    "pass",
    "fatigue_or_stop",
    "question_rejection",
    "meta_feedback",
    "correction",
]

PASS_EXACT = frozenset(
    {
        "패스",
        "pass",
        "됐어",
        "됐다",
        "모르겠어",
        "모르겠네",
        "몰라",
        "그만",
        "중단",
    }
)

PASS_PHRASES = (
    "패스할게",
    "패스할래",
    "넘어가",
    "그냥 넘어",
    "질문 패스",
)

FATIGUE_OR_STOP_PHRASES = (
    "질문 그만",
    "그만 물어",
    "질문하지 마",
    "질문 안 해도",
    "더 묻지 마",
    "여기까지",
)

QUESTION_REJECTION_PHRASES = (
    "맥락에 맞지 않은 질문",
    "맥락에 안 맞는 질문",
    "이미 앞에서 말했",
    "이미 말했잖아",
    "그 질문은 이상",
    "질문이 이상",
    "이상한 질문",
    "그런건 묻지마",
    "그런 건 묻지마",
    "묻지마",
    "그 질문 별로",
    "질문은 별로",
)

META_FEEDBACK_PHRASES = (
    "같은 격이어야",
    "같은 급이어야",
    "비교 대상이 아니",
    "비교가 안 돼",
    "비교하면 안",
    "추상화",
    "격이 다르",
    "레벨이 다르",
    "수준이 다르",
    "둘 중 무엇이 낫냐고",
    "질문 오류",
    "질문이 맥락",
    "무슨일이야",
    "무슨 일이야",
    "버그야",
    "고장났어",
)

CORRECTION_PHRASES = (
    "잘못 이해했다",
    "그 뜻이 아니다",
    "아니라고 했잖아",
    "문장이 이상하다",
    "다시 고쳐",
    "다시 요약해",
    "왜 그렇게 해석했어",
    "삭제해",
    "people이 아니",
    "people 이 아니",
    "요약에서 삭제",
)

CORRECTION_PREFIX = re.compile(r"^수정\b")


def classify_followup_response(text: str) -> FollowupResponseKind:
    """FOLLOWUP 상태의 사용자 입력을 분류한다.

    followup_answer만 기억 원문에 포함한다.
    """
    normalized = text.strip()
    if not normalized:
        return "pass"

    lowered = normalized.lower()
    if normalized in PASS_EXACT or lowered in PASS_EXACT:
        return "pass"
    if any(phrase in normalized for phrase in PASS_PHRASES):
        return "pass"
    if any(phrase in normalized for phrase in FATIGUE_OR_STOP_PHRASES):
        return "fatigue_or_stop"
    if any(phrase in normalized for phrase in QUESTION_REJECTION_PHRASES):
        return "question_rejection"
    if any(phrase in normalized for phrase in META_FEEDBACK_PHRASES):
        return "meta_feedback"
    if CORRECTION_PREFIX.match(normalized) or any(
        phrase in normalized for phrase in CORRECTION_PHRASES
    ):
        return "correction"
    return "followup_answer"


def should_include_in_memory_source(kind: FollowupResponseKind) -> bool:
    return kind == "followup_answer"


def should_go_to_review_immediately(kind: FollowupResponseKind) -> bool:
    return kind in {
        "pass",
        "fatigue_or_stop",
        "question_rejection",
        "meta_feedback",
    }


def should_record_as_failure(kind: FollowupResponseKind) -> bool:
    return kind in {"question_rejection", "meta_feedback"}
