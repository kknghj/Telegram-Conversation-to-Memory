"""질문 후보 품질 검증 — archive_gap과 reflective handle을 분리한다."""

from __future__ import annotations

import re
from typing import Any

ARCHIVE_GAP_LEVELS = frozenset({"none", "minor", "major"})
HANDLE_STRENGTH_LEVELS = frozenset({"none", "weak", "strong"})
SALIENCE_LEVELS = frozenset({"low", "medium", "high"})
GAIN_LEVELS = frozenset({"low", "medium", "high"})

# 원문에 이미 답이 있는 "연결/관련" 재질문 신호.
ALREADY_ANSWERED_LINK_MARKERS = (
    "연결",
    "관련해",
    "관련해서",
    "어떤 식으로",
    "어떻게 연결",
    "어떤 식으로 연결",
    "비슷한 점",
    "다른 점",
)

# 낮은 중요도 주변 예시(음식 인스턴스 등)로 쓰이기 쉬운 앵커.
LOW_SALIENCE_FOOD_RE = re.compile(
    r"(콩국수|냉면|라면|김밥|치킨|피자|햄버거|아이스크림|커피|맥주|소주)"
)

COMPARISON_MARKERS = (
    "사이",
    "중에서",
    "중 어느",
    "어느 쪽",
    "어느 쪽이",
    "더 매력",
    "더 중요",
    "와 ",
    "과 ",
    " vs ",
    "대비",
)

INSTANCE_MARKERS = (
    "콩국수",
    "냉면",
    "라면",
    "특정한 음식",
    "특정 음식",
    "가게",
    "사람 이름",
)

STRATEGY_MARKERS = (
    "감정에 따라",
    "감정 기반",
    "추천하는 방식",
    "추천 방식",
    "추천 전략",
    "프로젝트 전략",
    "가치관",
    "마감",
    "완성",
    "상금",
)

CORE_THEME_MARKERS = (
    "마감",
    "완성",
    "공모전",
    "제품",
    "프로젝트",
    "거리낌",
    "승산",
    "기준",
    "장기",
    "단기",
    "상금",
    "낭비",
    "지출",
    "판단",
)


def _norm_level(value: Any, allowed: frozenset[str], default: str) -> str:
    text = str(value or default).strip().lower()
    return text if text in allowed else default


def assess_archive_gap(
    *,
    draft: dict[str, Any],
    user_texts: list[str] | None = None,
) -> str:
    """기록을 정확히 저장하기 위해 부족한 정보 정도."""
    risk = draft.get("interpretation_risk", "low")
    unsupported = draft.get("unsupported_inferences") or []
    summary = str(draft.get("event_summary") or "").strip()
    source = " ".join(user_texts or [])

    if risk == "high" or len(unsupported) >= 2:
        return "major"
    if risk == "medium" or unsupported:
        return "major" if not summary else "minor"
    if not summary and len(source) < 40:
        return "major"
    if not summary:
        return "minor"
    return "none"


def assess_reflective_handle_strength(
    *,
    draft: dict[str, Any],
    user_texts: list[str] | None = None,
    conversation: list[dict] | None = None,
    has_expansion_signal: bool = False,
) -> str:
    """정확한 기록 너머로 새 생각을 만들 수 있는 손잡이 강도."""
    source_parts: list[str] = list(user_texts or [])
    if conversation:
        source_parts.extend(
            str(turn.get("content", ""))
            for turn in conversation
            if turn.get("role") == "user"
        )
    source = " ".join(source_parts)
    draft_bits = " ".join(
        [
            str(draft.get("topic") or ""),
            str(draft.get("event_summary") or ""),
            str(draft.get("memory_candidate") or ""),
            " ".join(str(x) for x in (draft.get("key_phrases") or [])),
            " ".join(str(x) for x in (draft.get("emerging_themes") or [])),
            " ".join(str(x) for x in (draft.get("value_tags") or [])),
        ]
    )
    combined = f"{source} {draft_bits}"

    strong_hits = 0
    if draft.get("reflection_seed_candidate"):
        strong_hits += 1
    if draft.get("reflection_value") == "high":
        strong_hits += 1
    if draft.get("key_phrases"):
        strong_hits += 1
    if any(marker in combined for marker in CORE_THEME_MARKERS):
        strong_hits += 1
    if has_expansion_signal:
        strong_hits += 1

    if strong_hits >= 2:
        return "strong"
    if strong_hits == 1 or draft.get("reflection_value") == "medium":
        return "weak"
    return "none"


def is_question_already_answered(
    question: str,
    *,
    user_texts: list[str] | None = None,
    draft: dict[str, Any] | None = None,
) -> bool:
    """질문이 원문에 이미 설명된 내용을 다시 요구하는지 판단."""
    q = question.strip()
    if not q:
        return False
    source = " ".join(user_texts or [])
    if draft:
        source = " ".join(
            [
                source,
                str(draft.get("event_summary") or ""),
                str(draft.get("memory_candidate") or ""),
            ]
        )
    if not source:
        return False

    asks_link = any(marker in q for marker in ALREADY_ANSWERED_LINK_MARKERS)
    if asks_link:
        # 도스토옙스키 ↔ 현재 상황처럼, 질문의 고유명사가 원문에 이미 연결 서술과 함께 있음.
        named = re.findall(r"[가-힣A-Za-z]{2,}", q)
        notable = [
            token
            for token in named
            if token
            not in {
                "관련해",
                "관련해서",
                "연결",
                "느끼나요",
                "어떤",
                "식으로",
                "현재",
                "상황",
                "이야기",
                "비슷한",
                "다른",
            }
        ]
        present = [token for token in notable if token in source]
        if len(present) >= 1 and any(
            cue in source
            for cue in ("떠올", "생각", "느꼈", "연결", "닮", "비슷", "일화")
        ):
            return True

    # 질문 핵심 구절이 원문에 거의 그대로 있으면 중복.
    compact_q = re.sub(r"[?\s]+", "", q)
    compact_source = re.sub(r"\s+", "", source)
    if len(compact_q) >= 12 and compact_q[:20] in compact_source:
        return True
    return False


def is_low_salience_anchor(
    anchor: str,
    *,
    draft: dict[str, Any] | None = None,
    user_texts: list[str] | None = None,
) -> bool:
    """주변 예시를 핵심 앵커로 잡지 않았는지 검사."""
    text = (anchor or "").strip()
    if not text:
        return False
    source = " ".join(user_texts or [])
    draft_text = " ".join(
        [
            str((draft or {}).get("topic") or ""),
            str((draft or {}).get("event_summary") or ""),
            " ".join(str(x) for x in ((draft or {}).get("emerging_themes") or [])),
            " ".join(str(x) for x in ((draft or {}).get("key_phrases") or [])),
        ]
    )
    combined = f"{source} {draft_text}"

    if LOW_SALIENCE_FOOD_RE.search(text):
        # 핵심 테마가 마감·제품·프로젝트면 음식 인스턴스는 low salience.
        if any(marker in combined for marker in CORE_THEME_MARKERS):
            return True
    return False


def is_comparison_question(question: str) -> bool:
    return any(marker in question for marker in COMPARISON_MARKERS)


def has_same_abstraction_level(
    question: str,
    *,
    same_abstraction_level: bool | None = None,
    comparison_axis: str = "",
) -> tuple[bool, str]:
    """비교 질문의 추상화 수준 일치 여부. (ok, reject_reason)"""
    if same_abstraction_level is False:
        return False, "category_mismatch"
    if not is_comparison_question(question):
        return True, ""

    has_instance = any(marker in question for marker in INSTANCE_MARKERS)
    has_strategy = any(marker in question for marker in STRATEGY_MARKERS)
    if has_instance and has_strategy:
        return False, "category_mismatch"
    if same_abstraction_level is True and comparison_axis.strip():
        return True, ""
    if same_abstraction_level is True:
        return True, ""
    # 명시 필드가 없고 비교 마커만 있으면 axis 부재로 보수적 거절하지 않되,
    # instance/strategy 혼재만 막는다.
    return True, ""


def answer_adds_new_information(
    *,
    original_user_texts: list[str],
    accepted_answer: str,
) -> bool:
    """후속 답변이 원문 반복이 아니라 새 정보를 더했는지 판단."""
    answer = accepted_answer.strip()
    if not answer:
        return False
    if len(answer) < 8:
        return False
    original = " ".join(original_user_texts)
    if not original:
        return True
    # 답변의 상당 부분이 원문에 이미 있으면 반복으로 본다.
    chunks = [answer[i : i + 12] for i in range(0, min(len(answer), 60), 12)]
    overlap = sum(1 for chunk in chunks if chunk and chunk in original)
    if chunks and overlap / len(chunks) >= 0.7:
        return False
    return True


def questions_are_redundant(first: str, second: str) -> bool:
    """두 질문이 의미적으로 중복인지 단순 검사."""
    a = re.sub(r"[\s?？]+", "", first.strip())
    b = re.sub(r"[\s?？]+", "", second.strip())
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 10 and (a in b or b in a):
        return True
    shared = set(re.findall(r"[가-힣A-Za-z]{2,}", first)) & set(
        re.findall(r"[가-힣A-Za-z]{2,}", second)
    )
    stop = {"어떤", "무엇", "언제", "어디", "어떻게", "관련", "기록", "느낌", "생각"}
    shared -= stop
    return len(shared) >= 3 and len(shared) >= min(len(a), len(b)) // 20


def normalize_candidate(raw: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(raw or {})
    return {
        "grounding_quote": str(data.get("grounding_quote") or "").strip(),
        "anchor": str(data.get("anchor") or "").strip(),
        "anchor_salience": _norm_level(data.get("anchor_salience"), SALIENCE_LEVELS, "medium"),
        "unexplored_dimension": str(data.get("unexplored_dimension") or "").strip(),
        "question_mode": str(data.get("question_mode") or "association").strip(),
        "candidate_question": str(
            data.get("candidate_question") or data.get("followup_question") or ""
        ).strip(),
        "expected_reflective_gain": _norm_level(
            data.get("expected_reflective_gain"), GAIN_LEVELS, "medium"
        ),
        "already_answered": bool(data.get("already_answered", False)),
        "same_abstraction_level": data.get("same_abstraction_level", True),
        "comparison_axis": str(data.get("comparison_axis") or "").strip(),
    }


def validate_question_candidate(
    candidate: dict[str, Any],
    *,
    draft: dict[str, Any],
    user_texts: list[str] | None = None,
) -> tuple[bool, str]:
    """후보 1건 품질 검증. (pass, reject_reason)"""
    c = normalize_candidate(candidate)
    question = c["candidate_question"]
    if not question:
        return False, "empty_question_generated"

    if c["already_answered"] or is_question_already_answered(
        question, user_texts=user_texts, draft=draft
    ):
        return False, "answered_already"

    ok_level, reason = has_same_abstraction_level(
        question,
        same_abstraction_level=(
            None
            if c["same_abstraction_level"] is True and not c["comparison_axis"]
            else bool(c["same_abstraction_level"])
        ),
        comparison_axis=c["comparison_axis"],
    )
    if not ok_level:
        return False, reason or "category_mismatch"

    if is_comparison_question(question) and c["question_mode"] in {
        "contrast",
        "value_probe",
    }:
        if c["same_abstraction_level"] is False:
            return False, "category_mismatch"

    if c["anchor_salience"] == "low" or is_low_salience_anchor(
        c["anchor"] or question,
        draft=draft,
        user_texts=user_texts,
    ):
        return False, "low_salience_anchor"

    if c["expected_reflective_gain"] == "low":
        return False, "low_expected_gain"

    return True, ""


def select_best_candidate(
    candidates: list[dict[str, Any]],
    *,
    draft: dict[str, Any],
    user_texts: list[str] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """검증을 통과한 후보 중 첫 유효 후보를 고른다."""
    rejected: list[dict[str, str]] = []
    for raw in candidates:
        c = normalize_candidate(raw)
        ok, reason = validate_question_candidate(
            c, draft=draft, user_texts=user_texts
        )
        if ok:
            return c, rejected
        rejected.append(
            {
                "question": c["candidate_question"],
                "reason": reason,
            }
        )
    return None, rejected


def evaluate_second_question_gate(
    *,
    question_session: dict[str, Any],
    response_kind: str,
    original_user_texts: list[str],
    accepted_answer: str,
    previous_question: str = "",
    new_question: str = "",
    new_reflective_handle_strength: str = "none",
    new_unresolved_point: str = "",
) -> dict[str, Any]:
    """두 번째 질문 전용 게이트."""
    asked = int(question_session.get("questions_asked") or 0)
    result = {
        "question_round": asked + 1,
        "accepted_answer_added_information": False,
        "new_unresolved_point": new_unresolved_point,
        "new_reflective_handle_strength": new_reflective_handle_strength,
        "second_question_allowed": False,
        "second_question_gate_reason": "",
    }

    if asked >= 2:
        result["second_question_gate_reason"] = "max_questions_reached"
        return result
    if asked != 1:
        result["second_question_gate_reason"] = "not_second_round"
        return result
    if response_kind != "followup_answer":
        result["second_question_gate_reason"] = f"response_kind_{response_kind}"
        return result

    added = answer_adds_new_information(
        original_user_texts=original_user_texts,
        accepted_answer=accepted_answer,
    )
    result["accepted_answer_added_information"] = added
    if not added:
        result["second_question_gate_reason"] = "answer_repeats_source"
        return result

    if new_question and previous_question and questions_are_redundant(
        previous_question, new_question
    ):
        result["second_question_gate_reason"] = "redundant_question"
        return result

    if new_unresolved_point or new_reflective_handle_strength == "strong":
        result["second_question_allowed"] = True
        result["second_question_gate_reason"] = (
            "new_value_tradeoff_emerged"
            if new_unresolved_point
            else "new_reflective_handle"
        )
        return result

    result["second_question_gate_reason"] = "no_new_unresolved_point"
    return result


def decide_question_policy(
    *,
    archive_gap: str,
    reflective_handle_strength: str,
    hard_stop: bool = False,
) -> dict[str, Any]:
    """archive_gap / reflective_handle에 따른 허용 모드 정책."""
    if hard_stop:
        return {
            "allow_question": False,
            "allow_meaning_check": False,
            "allow_expansion_modes": False,
            "reason": "hard_stop",
        }
    if archive_gap == "major":
        return {
            "allow_question": True,
            "allow_meaning_check": True,
            "allow_expansion_modes": False,
            "reason": "archive_gap_major",
        }
    if reflective_handle_strength == "strong":
        return {
            "allow_question": True,
            "allow_meaning_check": False,
            "allow_expansion_modes": True,
            "reason": "complete_but_expandable",
        }
    if reflective_handle_strength == "weak" and archive_gap == "minor":
        return {
            "allow_question": True,
            "allow_meaning_check": False,
            "allow_expansion_modes": True,
            "reason": "minor_gap_with_handle",
        }
    return {
        "allow_question": False,
        "allow_meaning_check": False,
        "allow_expansion_modes": False,
        "reason": "no_reflective_handle",
    }
