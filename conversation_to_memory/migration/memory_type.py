"""memory_type 추론 및 confidence 산출."""

from __future__ import annotations

import re
from typing import Literal

MemoryType = Literal["event", "observation", "reflection_seed"]
Confidence = Literal["high", "medium", "low"]

REFLECTION_SEED_SIGNALS = (
    "왜 ",
    "왜일까",
    "궁금",
    "고민",
    "의미",
    "철학",
    "본질",
    "자아",
    "정체",
    "삶",
    "존재",
    "?",
)
OBSERVATION_SIGNALS = (
    "느꼈",
    "느껴",
    "같아",
    "같은",
    "반복",
    "자주",
    "늘 ",
    "항상",
    "패턴",
    "인식",
    "생각",
)
EVENT_SIGNALS = (
    "오늘",
    "어제",
    "했",
    "갔",
    "만났",
    "전화",
    "회의",
    "발표",
    "신청",
    "받",
    "보냈",
    "일어났",
)


def _extract_user_quotes(memory: dict) -> list[str]:
    quotes: list[str] = []
    for turn in memory.get("conversation") or []:
        if turn.get("role") == "user":
            content = str(turn.get("content") or "").strip()
            if content:
                quotes.append(content)
    return quotes


def _user_text(memory: dict) -> str:
    return " ".join(_extract_user_quotes(memory))


def _score_signals(text: str, signals: tuple[str, ...]) -> int:
    return sum(1 for s in signals if s in text)


def _has_named_people(memory: dict) -> bool:
    people = memory.get("people") or []
    return bool(people)


def _has_open_questions(memory: dict) -> bool:
    questions = memory.get("open_questions") or []
    return bool(questions)


def _has_date_in_id(memory_id: str) -> bool:
    return bool(re.match(r"\d{4}-\d{2}-\d{2}", memory_id))


def infer_memory_type(
    memory: dict,
    *,
    memory_id: str = "",
) -> dict[str, MemoryType | Confidence]:
    """규칙 기반 memory_type 추론.

    Returns:
        {"memory_type": ..., "memory_type_confidence": ...}
    """
    existing = memory.get("memory_type")
    if existing in ("event", "observation", "reflection_seed", "relation", "pattern"):
        return {
            "memory_type": existing,
            "memory_type_confidence": "high",
        }

    text = _user_text(memory)
    topic = str(memory.get("topic") or "")
    candidate = str(memory.get("memory_candidate") or memory.get("summary") or "")
    combined = f"{topic} {text} {candidate}"

    seed_score = _score_signals(combined, REFLECTION_SEED_SIGNALS)
    obs_score = _score_signals(combined, OBSERVATION_SIGNALS)
    event_score = _score_signals(combined, EVENT_SIGNALS)

    if _has_open_questions(memory):
        seed_score += 2
    if "?" in text:
        seed_score += 1
    if _has_named_people(memory):
        event_score += 1
    if _has_date_in_id(memory_id):
        event_score += 1

    scores = {
        "reflection_seed": seed_score,
        "observation": obs_score,
        "event": event_score,
    }
    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]
    second_score = sorted(scores.values(), reverse=True)[1]

    if best_score == 0:
        return {"memory_type": "event", "memory_type_confidence": "low"}

    margin = best_score - second_score
    if margin >= 2 and best_score >= 2:
        confidence: Confidence = "high"
    elif margin >= 1 or best_score >= 1:
        confidence = "medium"
    else:
        confidence = "low"

    return {"memory_type": best_type, "memory_type_confidence": confidence}


def backfill_memory_type(
    memory: dict,
    *,
    memory_id: str = "",
    force: bool = False,
) -> tuple[bool, dict[str, MemoryType | Confidence]]:
    """memory_type·confidence가 없으면 추론 결과를 붙인다."""
    if memory.get("memory_type") and not force:
        if memory.get("memory_type_confidence"):
            return False, {
                "memory_type": memory["memory_type"],
                "memory_type_confidence": memory["memory_type_confidence"],
            }
        memory["memory_type_confidence"] = "high"
        return True, {
            "memory_type": memory["memory_type"],
            "memory_type_confidence": "high",
        }

    result = infer_memory_type(memory, memory_id=memory_id)
    memory["memory_type"] = result["memory_type"]
    memory["memory_type_confidence"] = result["memory_type_confidence"]
    return True, result
