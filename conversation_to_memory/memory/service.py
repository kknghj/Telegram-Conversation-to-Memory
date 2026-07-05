"""OpenAI 기반 기억 아카이브 분석 및 추출."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from conversation_to_memory.memory.fidelity import validate_draft
from conversation_to_memory.memory.question import is_reflection_agent_enabled

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

VALID_MEMORY_TYPES = frozenset(
    {"event", "observation", "relation", "pattern", "reflection_seed"}
)

DEFAULT_DRAFT: dict[str, Any] = {
    "topic": "",
    "event_summary": "",
    "user_emotions": [],
    "emotion_evidence": [],
    "people": [],
    "projects": [],
    "tags": [],
    "value_tags": [],
    "memory_candidate": "",
    "model_interpretation": "",
    "key_phrases": [],
    "emerging_themes": [],
    "open_questions": [],
    "reflection_value": "medium",
    "memory_type": "event",
    "reflection_seed_candidate": False,
    "temporal_status": "past",
    "question_mode_used": [],
    "interpretation_risk": "low",
    "unsupported_inferences": [],
    "needs_followup": False,
    "followup_question": "",
}

VALID_TEMPORAL_STATUS = frozenset({"past", "future", "ongoing", "mixed"})


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
    return OpenAI(api_key=api_key)


def _get_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _conversation_to_messages(conversation: list[dict]) -> list[dict]:
    return [{"role": turn["role"], "content": turn["content"]} for turn in conversation]


def _build_context_block(
    *,
    recent_context: list[dict] | None = None,
    cancelled_draft: dict | None = None,
    cancellation_reason: str = "",
    followup_already_asked: bool = False,
) -> str:
    parts: list[str] = []

    if recent_context:
        parts.append("## 최근 기록 맥락")
        for idx, ctx in enumerate(recent_context[-3:], 1):
            parts.append(f"{idx}. 사용자: {' '.join(ctx.get('user_texts', []))}")
            parts.append(f"   요약: {ctx.get('event_summary', '')}")

    if cancelled_draft:
        parts.append("## 이전 취소된 초안")
        parts.append(f"주제: {cancelled_draft.get('topic', '')}")
        parts.append(f"요약: {cancelled_draft.get('event_summary', '')}")
        if cancellation_reason:
            parts.append(f"취소 당시 사용자 발화: {cancellation_reason}")

    if followup_already_asked:
        parts.append("## 제약")
        parts.append("후속 질문은 이미 1회 사용됨. needs_followup=false, followup_question=\"\" 로 설정.")

    return "\n".join(parts)


def normalize_draft(data: dict) -> dict:
    draft = {**DEFAULT_DRAFT}
    draft.update(data)
    draft["user_emotions"] = list(draft.get("user_emotions") or [])
    draft["emotion_evidence"] = list(draft.get("emotion_evidence") or [])
    draft["people"] = list(draft.get("people") or [])
    draft["projects"] = list(draft.get("projects") or [])
    draft["tags"] = list(draft.get("tags") or [])
    draft["value_tags"] = list(draft.get("value_tags") or [])
    draft["key_phrases"] = list(draft.get("key_phrases") or [])
    draft["emerging_themes"] = list(draft.get("emerging_themes") or [])
    draft["open_questions"] = list(draft.get("open_questions") or [])
    draft["question_mode_used"] = list(draft.get("question_mode_used") or [])
    draft["unsupported_inferences"] = list(draft.get("unsupported_inferences") or [])
    draft["model_interpretation"] = str(draft.get("model_interpretation") or "").strip()

    reflection_value = draft.get("reflection_value", "medium")
    if reflection_value not in ("low", "medium", "high"):
        reflection_value = "medium"
    draft["reflection_value"] = reflection_value

    memory_type = draft.get("memory_type", "event")
    if memory_type not in VALID_MEMORY_TYPES:
        memory_type = "event"
    draft["memory_type"] = memory_type

    draft["reflection_seed_candidate"] = bool(draft.get("reflection_seed_candidate"))

    temporal_status = draft.get("temporal_status", "past")
    if temporal_status not in VALID_TEMPORAL_STATUS:
        temporal_status = "past"
    draft["temporal_status"] = temporal_status

    draft["needs_followup"] = bool(draft.get("needs_followup"))
    risk = draft.get("interpretation_risk", "low")
    if risk not in ("low", "medium", "high"):
        risk = "low"
    draft["interpretation_risk"] = risk

    if is_reflection_agent_enabled():
        draft["needs_followup"] = False
        draft["followup_question"] = ""
    elif not draft["needs_followup"]:
        draft["followup_question"] = ""
    return draft


def analyze_recording(
    *,
    user_texts: list[str],
    conversation: list[dict] | None = None,
    recent_context: list[dict] | None = None,
    cancelled_draft: dict | None = None,
    cancellation_reason: str = "",
    followup_already_asked: bool = False,
    edit_instruction: str = "",
) -> dict:
    """사용자 원문을 분석해 draft JSON 생성."""
    client = _get_client()
    system = _load_prompt("memory_archive_system_prompt.txt")
    source_text = "\n".join(user_texts)

    context_block = _build_context_block(
        recent_context=recent_context,
        cancelled_draft=cancelled_draft,
        cancellation_reason=cancellation_reason,
        followup_already_asked=followup_already_asked,
    )

    user_content_parts = [
        "아래 사용자 원문을 기억 아카이브 초안 JSON으로 정리하세요.",
        f"## 사용자 원문\n{source_text}",
    ]
    if is_reflection_agent_enabled():
        user_content_parts.append(
            "## 제약\n"
            "후속 질문은 별도 단계에서 생성한다. "
            "needs_followup=false, followup_question=\"\" 로 설정하라."
        )
    if context_block:
        user_content_parts.append(context_block)
    if edit_instruction:
        user_content_parts.append(f"## 수정 요청\n{edit_instruction}")
    if conversation:
        user_content_parts.append("## 추가 대화")
        for turn in conversation:
            role = "사용자" if turn["role"] == "user" else "봇"
            user_content_parts.append(f"{role}: {turn['content']}")

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(user_content_parts)},
    ]

    response = client.chat.completions.create(
        model=_get_model(),
        messages=messages,
        temperature=0.2,
        max_tokens=1200,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()
    data = json.loads(raw)
    draft = normalize_draft(data)
    return validate_draft(draft, source_text)


def extract_memory(conversation: list[dict]) -> dict:
    """하위 호환: 대화 목록에서 user 텍스트 추출 후 analyze_recording 호출."""
    user_texts = [t["content"] for t in conversation if t["role"] == "user"]
    return analyze_recording(user_texts=user_texts, conversation=conversation)


def format_review_message(memory: dict) -> str:
    """저장 전 사용자에게 보여줄 요약 + JSON 텍스트."""
    preview = {
        "topic": memory.get("topic"),
        "event_summary": memory.get("event_summary"),
        "user_emotions": memory.get("user_emotions"),
        "emotion_evidence": memory.get("emotion_evidence"),
        "people": memory.get("people"),
        "projects": memory.get("projects"),
        "tags": memory.get("tags"),
        "value_tags": memory.get("value_tags"),
        "memory_candidate": memory.get("memory_candidate"),
        "key_phrases": memory.get("key_phrases"),
        "emerging_themes": memory.get("emerging_themes"),
        "open_questions": memory.get("open_questions"),
        "reflection_value": memory.get("reflection_value"),
        "memory_type": memory.get("memory_type"),
        "reflection_seed_candidate": memory.get("reflection_seed_candidate"),
        "temporal_status": memory.get("temporal_status"),
        "interpretation_risk": memory.get("interpretation_risk"),
        "unsupported_inferences": memory.get("unsupported_inferences"),
    }
    json_str = json.dumps(preview, ensure_ascii=False, indent=2)

    risk = memory.get("interpretation_risk", "low")
    risk_note = ""
    if risk != "low":
        risk_note = f"\n⚠️ 해석 위험도: {risk}\n"

    temporal_status = memory.get("temporal_status", "past")
    temporal_note = ""
    if temporal_status in ("future", "mixed"):
        temporal_note = (
            f"\n🕒 시제: {temporal_status} — 아직 일어나지 않은/예정된 내용이 포함되어 있습니다. "
            "완료된 사실로 기록하지 않았는지 확인하세요.\n"
        )

    seed_note = ""
    if memory.get("reflection_seed_candidate"):
        seed_note = "\n🌱 장기 패턴(가치관·판단 기준) 후보로 표시되었습니다.\n"

    unsupported = memory.get("unsupported_inferences") or []
    unsupported_note = ""
    if unsupported:
        unsupported_note = (
            f"\n⚠️ 원문 근거 약한 추론: {', '.join(unsupported)}\n"
        )

    interpretation = (memory.get("model_interpretation") or "").strip()
    interpretation_note = ""
    if interpretation:
        interpretation_note = f"\n💭 에이전트 해석\n{interpretation}\n"

    return (
        "📋 기록 요약\n"
        f"{memory.get('event_summary', '')}\n"
        f"{risk_note}{temporal_note}{seed_note}{unsupported_note}{interpretation_note}\n"
        "📦 구조화 JSON\n"
        f"{json_str}\n\n"
        "저장하려면 「저장」을 입력하세요.\n"
        "수정하려면 「수정」과 함께 고칠 내용을 입력하세요.\n"
        "취소하려면 「취소」를 입력하세요."
    )
