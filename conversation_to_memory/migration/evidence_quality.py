"""retrieval safety — evidence_quality 판별."""

from __future__ import annotations

import re
from typing import Literal

from conversation_to_memory.memory.fidelity import (
    GROWTH_NARRATIVE_PHRASES,
    detect_unsupported_inferences,
)

EvidenceQuality = Literal["primary_only", "contains_derived_text"]

DERIVED_INTENT_PATTERNS = (
    r"지속적으로\s+노력",
    r"앞으로도\s+",
    r"~?하고\s+싶다",
    r"해야\s*겠다",
    r"해야\s*한다",
    r"찾아야",
    r"기억하자",
    r"그러므로",
    r"깨달았",
    r"배운\s+점",
)


def _extract_user_quotes(memory: dict) -> list[str]:
    quotes: list[str] = []
    for turn in memory.get("conversation") or []:
        if turn.get("role") == "user":
            content = str(turn.get("content") or "").strip()
            if content:
                quotes.append(content)
    return quotes


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _user_source_text(memory: dict) -> str:
    return _normalize(" ".join(_extract_user_quotes(memory)))


def _candidate_text(memory: dict) -> str:
    return _normalize(
        str(memory.get("memory_candidate") or memory.get("summary") or "")
    )


def _has_derived_intent_phrases(candidate: str, source: str) -> bool:
    for pattern in DERIVED_INTENT_PATTERNS:
        if re.search(pattern, candidate) and not re.search(pattern, source):
            return True
    return False


def _has_ungrounded_sentences(candidate: str, source: str, *, min_overlap: float = 0.15) -> bool:
    """memory_candidate 문장이 원문과 겹침이 낮으면 derived로 판단."""
    if not candidate:
        return False

    sentences = [s.strip() for s in re.split(r"[.!?]\s*", candidate) if len(s.strip()) >= 8]
    if not sentences:
        return False

    source_chars = set(source.replace(" ", ""))
    ungrounded = 0
    for sentence in sentences:
        sent_chars = set(sentence.replace(" ", ""))
        if not sent_chars:
            continue
        overlap = len(sent_chars & source_chars) / len(sent_chars)
        if overlap < min_overlap:
            ungrounded += 1

    return ungrounded >= 1


def _is_legacy_schema(memory: dict) -> bool:
    explicit = memory.get("schema_version")
    if explicit == 1:
        return True
    if explicit == 2:
        return False
    has_new = "event_summary" in memory or "user_emotions" in memory
    has_old = "summary" in memory or "emotion" in memory
    return bool(has_old and not has_new)


def contains_derived_text(memory: dict) -> bool:
    """legacy schema 또는 memory_candidate 오염 여부."""
    if _is_legacy_schema(memory):
        return True

    source = _user_source_text(memory)
    candidate = _candidate_text(memory)
    if not candidate:
        return False

    draft = {
        "event_summary": memory.get("event_summary", memory.get("summary", "")),
        "memory_candidate": candidate,
        "model_interpretation": memory.get("model_interpretation", ""),
        "user_emotions": memory.get("user_emotions", []),
        "unsupported_inferences": memory.get("unsupported_inferences", []),
    }

    if detect_unsupported_inferences(draft, source):
        return True

    for phrase in GROWTH_NARRATIVE_PHRASES:
        if phrase in candidate and phrase not in source:
            return True

    if _has_derived_intent_phrases(candidate, source):
        return True

    return _has_ungrounded_sentences(candidate, source)


def assess_evidence_quality(memory: dict) -> EvidenceQuality:
    if contains_derived_text(memory):
        return "contains_derived_text"
    return "primary_only"


def backfill_evidence_quality(memory: dict) -> tuple[bool, EvidenceQuality]:
    """evidence_quality 필드를 갱신한다."""
    quality = assess_evidence_quality(memory)
    before = memory.get("evidence_quality")
    memory["evidence_quality"] = quality
    return before != quality, quality
