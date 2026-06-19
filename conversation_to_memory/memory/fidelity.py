"""원문 충실도 검사 — GPT 출력 후처리."""

from __future__ import annotations

import re

FORBIDDEN_INFERENCE_TERMS = (
    "견뎌",
    "성장",
    "칭찬",
    "교훈",
    "깨달음",
    "배운",
    "극복",
    "의미 있는",
    "소중한",
)

GROWTH_NARRATIVE_PHRASES = (
    "힘든 순간을 견뎌",
    "자신을 칭찬",
    "성장",
    "배운 점",
    "소중한 깨달음",
)

POSITIVE_REFRAMING_TERMS = (
    "지원",
    "배려",
    "격려",
    "응원",
    "도움",
    "도와",
)

ROLE_GENERALIZATION_RE = re.compile(r"관리자.{0,12}역할")
INFERRED_EMOTION_RE = re.compile(r"복잡한\s*감정")
ACTOR_POSITIVE_RE = re.compile(r"(팀장|상사|부모|교사|관리자).{0,12}(지원|배려|도움|격려)")


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def term_in_source(term: str, source_text: str) -> bool:
    return term in source_text


def _combined_output_text(draft: dict) -> str:
    searchable_fields = [
        draft.get("topic", ""),
        draft.get("event_summary", ""),
        draft.get("memory_candidate", ""),
        draft.get("model_interpretation", ""),
        " ".join(draft.get("user_emotions", [])),
        " ".join(draft.get("emerging_themes", [])),
    ]
    return " ".join(str(v) for v in searchable_fields)


def _detect_positive_reframing(combined_output: str, source: str) -> list[str]:
    found: list[str] = []
    for term in POSITIVE_REFRAMING_TERMS:
        if term in combined_output and term not in source:
            label = f"unsupported_positive_reframing: '{term}' (원문에 없음)"
            if label not in found:
                found.append(label)
    return found


def _detect_role_generalization(combined_output: str, source: str) -> list[str]:
    found: list[str] = []
    if ROLE_GENERALIZATION_RE.search(combined_output) and "역할" not in source:
        found.append("topic_shift: 관리자의 역할 일반화")
    if INFERRED_EMOTION_RE.search(combined_output) and "복잡한" not in source:
        found.append("unsupported_motivation: 복잡한 감정 (원문에 없음)")
    return found


def _detect_actor_evaluation(combined_output: str, source: str) -> list[str]:
    found: list[str] = []
    match = ACTOR_POSITIVE_RE.search(combined_output)
    if match:
        term = match.group(2)
        if term not in source:
            found.append(f"actor_evaluation_inference: '{match.group(0)}' (원문에 없음)")
    return found


def detect_unsupported_inferences(draft: dict, source_text: str) -> list[str]:
    """원문에 없는 긍정적 재해석·성장 서사·역할 일반화를 탐지."""
    source = _normalize_text(source_text)
    found: list[str] = []
    combined_output = _combined_output_text(draft)

    for phrase in GROWTH_NARRATIVE_PHRASES:
        if phrase in combined_output and phrase not in source:
            found.append(phrase)

    for term in FORBIDDEN_INFERENCE_TERMS:
        if term in combined_output and not term_in_source(term, source):
            label = {
                "견뎌": "자기칭찬/견딤 서사",
                "성장": "성장",
                "칭찬": "자기칭찬",
                "교훈": "교훈",
                "깨달음": "깨달음",
                "배운": "교훈",
            }.get(term, term)
            if label not in found:
                found.append(label)

    for detector in (
        _detect_positive_reframing,
        _detect_role_generalization,
        _detect_actor_evaluation,
    ):
        for item in detector(combined_output, source):
            if item not in found:
                found.append(item)

    existing = draft.get("unsupported_inferences", [])
    for item in existing:
        if item not in found:
            found.append(item)

    return found


def assess_interpretation_risk(draft: dict, source_text: str) -> str:
    unsupported = detect_unsupported_inferences(draft, source_text)
    if unsupported:
        return "high" if len(unsupported) >= 2 else "medium"
    current = draft.get("interpretation_risk", "low")
    if current in ("low", "medium", "high"):
        return current
    return "low"


def validate_draft(draft: dict, source_text: str) -> dict:
    """후처리: unsupported_inferences 보강 및 interpretation_risk 재평가."""
    unsupported = detect_unsupported_inferences(draft, source_text)
    risk = assess_interpretation_risk(draft, source_text)

    validated = dict(draft)
    validated["unsupported_inferences"] = unsupported
    validated["interpretation_risk"] = risk
    return validated


def contains_forbidden_growth_narrative(draft: dict) -> bool:
    """테스트용: 금지 성장 서사 포함 여부."""
    text = " ".join(
        [
            draft.get("event_summary", ""),
            draft.get("memory_candidate", ""),
        ]
    )
    return any(phrase in text for phrase in GROWTH_NARRATIVE_PHRASES)
