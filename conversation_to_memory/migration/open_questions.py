"""open_questions 휴리스틱 추출 및 백필.

사용자 발화에서 미해결 질문 후보를 결정적(deterministic)으로 찾는다.
- 포함 신호: "~일까"류 어미, "궁금", "모르겠", "왜 그럴", 물음표로 끝나는 문장
- 제외 규칙: 직전 assistant 턴이 질문이면, 그에 대한 반문·되물음으로 보고 제외
- 제외 규칙: 봇에게 시키는 요청형 문장("~해줘?", "~해줄래?" 등)은 제외
"""

from __future__ import annotations

import re

# 강한 자기 질문 신호: "~일까" 어미, "궁금" (물음표 없어도 인정)
# "궁금해하는 타입" 같은 성격 서술은 제외하기 위해 "궁금해하"는 매칭하지 않는다.
STRONG_INQUIRY_PATTERN = re.compile(r"(까\?*$|궁금(?!해\s?하))")

# 자기 자신에게 던진 미해결 질문 신호 (강한 신호 + 약한 신호)
SELF_INQUIRY_PATTERN = re.compile(r"(까\?*$|궁금(?!해\s?하)|모르겠|왜 그럴)")

# 봇에게 시키는 요청형 문장 신호
BOT_DIRECTED_PATTERN = re.compile(r"(해\s?줘|해\s?줄래|해\s?주세요|알려\s?줘|요약)")

_SENTENCE_SPLIT = re.compile(r"(?<=[.?!])\s+|\n+")

MIN_CANDIDATE_LENGTH = 8


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _is_question_sentence(sentence: str) -> bool:
    if len(sentence) < MIN_CANDIDATE_LENGTH:
        return False
    if BOT_DIRECTED_PATTERN.search(sentence):
        return False
    if SELF_INQUIRY_PATTERN.search(sentence):
        return True
    return sentence.rstrip("…. ").endswith("?")


def _prev_turn_is_assistant_question(conversation: list[dict], index: int) -> bool:
    if index <= 0:
        return False
    prev = conversation[index - 1]
    if prev.get("role") != "assistant":
        return False
    return "?" in str(prev.get("content") or "")


def _is_retort_to_bot(sentence: str, *, after_assistant_question: bool) -> bool:
    """직전 봇 질문에 대한 반문·되물음·"모르겠다" 응답인지 판단.

    봇 질문 직후 턴에서는 강한 자기 질문 신호(~일까, 궁금)가 있을 때만
    스스로 던진 질문으로 보고 유지한다. "모르겠어"는 봇 질문에 대한
    답변("나도 모른다")일 가능성이 높아 제외한다.
    """
    if not after_assistant_question:
        return False
    return not STRONG_INQUIRY_PATTERN.search(sentence.rstrip("? "))


def extract_open_question_candidates(memory: dict) -> list[str]:
    """conversation의 user 턴에서 미해결 질문 후보를 원문 그대로 추출."""
    conversation = memory.get("conversation") or []
    candidates: list[str] = []
    for index, turn in enumerate(conversation):
        if turn.get("role") != "user":
            continue
        after_bot_question = _prev_turn_is_assistant_question(conversation, index)
        for sentence in _split_sentences(str(turn.get("content") or "")):
            if not _is_question_sentence(sentence):
                continue
            if _is_retort_to_bot(sentence, after_assistant_question=after_bot_question):
                continue
            if sentence not in candidates:
                candidates.append(sentence)
    return candidates


def find_noise_entries(memory: dict) -> list[str]:
    """기존 open_questions 중 봇 질문에 대한 반문으로 보이는 노이즈를 찾는다."""
    existing = memory.get("open_questions") or []
    if not existing:
        return []
    valid = set(extract_open_question_candidates(memory))
    return [q for q in existing if q not in valid]


def backfill_open_questions(
    memory: dict,
    questions: list[str],
    *,
    source: str,
    remove: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """승인된 질문 목록을 open_questions에 반영한다.

    Returns:
        (changed, open_questions) — changed=True면 이번 호출에서 필드가 바뀌었다.
    """
    current = list(memory.get("open_questions") or [])
    updated = [q for q in current if q not in set(remove or [])]
    for question in questions:
        if question not in updated:
            updated.append(question)

    if updated == current:
        return False, current

    memory["open_questions"] = updated
    memory["open_questions_source"] = source
    return True, updated
