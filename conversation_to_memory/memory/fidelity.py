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


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def term_in_source(term: str, source_text: str) -> bool:
    return term in source_text


def detect_unsupported_inferences(draft: dict, source_text: str) -> list[str]:
    """원문에 없는 긍정적 재해석·성장 서사를 탐지."""
    source = _normalize_text(source_text)
    found: list[str] = []

    searchable_fields = [
        draft.get("event_summary", ""),
        draft.get("memory_candidate", ""),
        " ".join(draft.get("user_emotions", [])),
    ]
    combined_output = " ".join(str(v) for v in searchable_fields)

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
