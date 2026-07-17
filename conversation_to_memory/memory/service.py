"""OpenAI 기반 기억 아카이브 분석 및 추출."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from conversation_to_memory.memory.fidelity import (
    apply_edit_patches,
    coerce_text_list,
    enforce_consistency,
    parse_excluded_value_tags,
    validate_draft,
    verify_edit_requests,
)
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
    "tools": [],
    "organizations": [],
    "events": [],
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

VALID_TEMPORAL_STATUS = frozenset({"past", "future", "ongoing", "mixed", "current"})


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
    return OpenAI(api_key=api_key)


def resolve_memory_model(model: str | None = None) -> str:
    """모델 선택: 함수 인자 > OPENAI_MEMORY_MODEL > OPENAI_MODEL > 기본값."""
    if model and str(model).strip():
        return str(model).strip()
    return (
        os.getenv("OPENAI_MEMORY_MODEL", "").strip()
        or os.getenv("OPENAI_MODEL", "").strip()
        or "gpt-5.6-luna"
    )


def _get_model() -> str:
    return resolve_memory_model()


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
            parts.append(
                f"{idx}. 사용자: {' '.join(coerce_text_list(ctx.get('user_texts')))}"
            )
            parts.append(f"   요약: {ctx.get('event_summary', '')}")

    if cancelled_draft:
        parts.append("## 이전 취소된 초안")
        parts.append(f"주제: {cancelled_draft.get('topic', '')}")
        parts.append(f"요약: {cancelled_draft.get('event_summary', '')}")
        if cancellation_reason:
            parts.append(f"취소 당시 사용자 발화: {cancellation_reason}")

    if followup_already_asked:
        parts.append("## 제약")
        parts.append(
            "레거시 경로: 후속 질문이 이미 사용됨. "
            "needs_followup=false, followup_question=\"\" 로 설정."
        )

    return "\n".join(parts)


_STRING_LIST_FIELDS = (
    "user_emotions",
    "emotion_evidence",
    "people",
    "projects",
    "tools",
    "organizations",
    "events",
    "tags",
    "value_tags",
    "key_phrases",
    "emerging_themes",
    "open_questions",
    "question_mode_used",
    "unsupported_inferences",
)


def normalize_draft(data: dict) -> dict:
    draft = {**DEFAULT_DRAFT}
    draft.update(data)
    for field in _STRING_LIST_FIELDS:
        draft[field] = coerce_text_list(draft.get(field))
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
    previous_draft: dict | None = None,
    model: str | None = None,
    return_meta: bool = False,
) -> dict:
    """사용자 원문을 분석해 draft JSON 생성.

    model이 주어지면 OPENAI_MODEL을 덮어쓰지 않고 해당 요청에만 사용한다.
    return_meta=True이면 {"draft", "usage", "request_config", "model", "raw_usage"}를 반환한다.
    """
    from conversation_to_memory.evaluation.openai_compat import (
        chat_completion_create,
        extract_usage,
    )

    client = _get_client()
    selected_model = resolve_memory_model(model)
    system = _load_prompt("memory_archive_system_prompt.txt")
    source_text = "\n".join(coerce_text_list(user_texts))
    last_meta: dict[str, Any] = {
        "usage": {},
        "raw_usage": None,
        "request_config": {},
        "model": selected_model,
    }

    context_block = _build_context_block(
        recent_context=recent_context,
        cancelled_draft=cancelled_draft,
        cancellation_reason=cancellation_reason,
        followup_already_asked=followup_already_asked,
    )

    def _call_model(instruction: str) -> dict:
        nonlocal last_meta
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
        if instruction and previous_draft is not None:
            user_content_parts.append(
                "## 기존 초안 (수정 기준)\n"
                f"{json.dumps(previous_draft, ensure_ascii=False)}\n\n"
                "요청된 항목만 변경하고, 요청에 없는 필드는 기존 초안 값을 "
                "그대로 유지하라. 특히 open_questions 항목 하나만 삭제하라는 "
                "요청이면 다른 open_questions와 요약·태그·유형 필드를 다시 "
                "쓰지 마라."
            )
        if instruction:
            user_content_parts.append(
                "## 수정 요청\n"
                f"{instruction}\n\n"
                "수정 요청에 나열된 모든 항목을 반영했는지 출력 직전에 체크리스트로 검증하라. "
                "하나라도 미반영이면 다시 수정하라."
            )
        if conversation:
            user_content_parts.append("## 추가 대화")
            for turn in conversation:
                role = "사용자" if turn["role"] == "user" else "봇"
                user_content_parts.append(f"{role}: {turn['content']}")

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(user_content_parts)},
        ]

        response, request_config = chat_completion_create(
            client,
            model=selected_model,
            messages=messages,
            temperature=0.2,
            max_output_tokens=1200,
            response_format={"type": "json_object"},
        )
        usage, raw_usage = extract_usage(response)
        last_meta = {
            "usage": usage,
            "raw_usage": raw_usage,
            "request_config": request_config,
            "model": selected_model,
        }

        content = response.choices[0].message.content
        if content is None or not str(content).strip():
            raise ValueError(
                "empty model response content "
                f"(model={selected_model}, finish_reason="
                f"{getattr(response.choices[0], 'finish_reason', None)}, usage={usage})"
            )
        raw = str(content).strip()
        data = json.loads(raw)
        draft = normalize_draft(data)
        draft = validate_draft(
            draft,
            source_text,
            excluded_value_tags=excluded_value_tags,
        )
        return enforce_consistency(draft, source_text)

    excluded_value_tags = parse_excluded_value_tags(edit_instruction)
    draft = _call_model(edit_instruction)

    if edit_instruction and previous_draft is not None:
        draft = apply_edit_patches(
            edit_instruction,
            draft,
            source_text,
            before=previous_draft,
        )
        unfulfilled = verify_edit_requests(
            edit_instruction, previous_draft, draft, source_text
        )
        if unfulfilled:
            reinforced = (
                f"{edit_instruction}\n\n"
                "[필수] 다음 수정사항이 아직 반영되지 않았습니다: "
                f"{'; '.join(unfulfilled)}. 모두 반영한 뒤에만 JSON을 출력하세요."
            )
            draft = _call_model(reinforced)
            draft = apply_edit_patches(
                edit_instruction,
                draft,
                source_text,
                before=previous_draft,
            )
            unfulfilled = verify_edit_requests(
                edit_instruction, previous_draft, draft, source_text
            )
            if unfulfilled:
                raise ValueError(
                    "수정 요청이 일부만 반영되었습니다: " + "; ".join(unfulfilled)
                )

    if return_meta:
        return {"draft": draft, **last_meta}
    return draft


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
    elif temporal_status == "current":
        temporal_note = (
            "\n🕒 시제: current — 현재 마음·지향·바람을 나타내는 내용입니다. "
            "과거 사실(~라고 말했다)로 기록하지 않았는지 확인하세요.\n"
        )

    seed_note = ""
    if memory.get("reflection_seed_candidate"):
        seed_note = "\n🌱 장기 패턴(가치관·판단 기준) 후보로 표시되었습니다.\n"

    unsupported = coerce_text_list(memory.get("unsupported_inferences"))
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
