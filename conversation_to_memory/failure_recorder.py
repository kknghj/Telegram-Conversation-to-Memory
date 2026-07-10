"""해석 실패 스냅샷 기록 — 재현 가능한 학습 데이터셋."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_PATH = PROJECT_ROOT / "data" / "evaluation" / "interpretation_failures.jsonl"

CORRECTION_TRIGGERS: tuple[str, ...] = (
    "잘못 이해했다",
    "그 뜻이 아니다",
    "아니라고 했잖아",
    "기억 안 난다고 했잖아",
    "문장이 이상하다",
    "다시 고쳐",
    "다시 요약해",
    "왜 그렇게 해석했어",
    "그런건 묻지마",
    "그런 건 묻지마",
    "묻지마",
)

NEGATIVE_EMOTION_SIGNALS: tuple[str, ...] = (
    "걱정",
    "한심",
    "불안",
    "우울",
    "스트레스",
    "손에 잡히지 않",
    "아무것도 못",
    "지침",
    "지쳐",
    "무기력",
    "괴로",
)

POSITIVE_REFRAME_QUESTION_SIGNALS: tuple[str, ...] = (
    "반대로",
    "즐거웠던",
    "좋았던",
    "나아졌던",
    "극복",
    "기분이 좋아졌",
    "긍정적",
    "감사했던",
)

MEMORY_UNAVAILABLE_SIGNALS: tuple[str, ...] = (
    "기억이 안 난다",
    "기억 안 난다",
    "잘 모르겠다",
    "떠오르지 않는다",
    "생각이 안 난다",
    "기억이 흐릿하다",
    "더 말할 것이 없다",
    "모르겠네",
)

CONDITIONAL_PATTERN = re.compile(
    r"(.+?)(?:이|가)\s*(?:되면|된다면|승진하면|팀장이\s*되면|왕주임이\s*되면)"
)

FAILURE_TYPES = frozenset(
    {
        "repeated_question",
        "korean_misparse",
        "correction_ignored",
        "correction_partial",
        "memory_unavailable_ignored",
        "inappropriate_positive_reframe",
        "value_hidden_by_event",
    }
)

RULE_BY_FAILURE_TYPE: dict[str, str] = {
    "repeated_question": "Rule 4",
    "korean_misparse": "Rule 2",
    "correction_ignored": "Rule 3",
    "correction_partial": "Rule 7",
    "memory_unavailable_ignored": "Rule 1",
    "inappropriate_positive_reframe": "Rule 5",
    "value_hidden_by_event": "Rule 6",
}

DEFAULT_EXPECTED_BEHAVIOR: dict[str, str] = {
    "repeated_question": "기억하지 못한다는 답변 후 추가 질문을 생성하지 말았어야 함.",
    "korean_misparse": "조건문을 people 관계로 압축하지 말고 conditions로 저장했어야 함.",
    "correction_ignored": "사용자 정정을 우선 반영하고 기존 오해를 반복하지 말았어야 함.",
    "correction_partial": (
        "수정 요청에 나열된 모든 항목(value_tags 삭제 포함)을 반영하고, "
        "일부만 반영된 JSON을 출력하지 말았어야 함."
    ),
    "memory_unavailable_ignored": "기억 불가 신호 후 추가 질문 없이 요약·저장 확인으로 종료했어야 함.",
    "inappropriate_positive_reframe": (
        "사용자가 걱정과 자기비판을 표현한 뒤 요약을 요청했으므로, "
        "긍정 회상 질문을 하지 말고 원문 기반으로 바로 요약했어야 함."
    ),
    "value_hidden_by_event": (
        "가치관·판단 기준이 핵심이었으므로, 사건 나열보다 가치관을 event_summary 중심에 두고 "
        "memory_type=reflection_seed로 저장했어야 함."
    ),
}

DEFAULT_ROOT_CAUSE: dict[str, str] = {
    "repeated_question": "기억 불가 신호를 무시하고 후속 질문을 생성함",
    "korean_misparse": "조건문을 사람 관계로 압축하여 해석함",
    "correction_ignored": "사용자 정정 후에도 기존 해석을 고집함",
    "correction_partial": "수정 요청 중 일부 필드만 반영하고 나머지는 누락함",
    "memory_unavailable_ignored": "답변 종료 신호를 추가 질문 기회로 오인함",
    "inappropriate_positive_reframe": (
        "부정 감정 표현 직후 반대 감정과 즐거운 순간을 묻는 긍정 전환 질문을 생성함"
    ),
    "value_hidden_by_event": "가치관이 핵심이었는데 사건 요약 위주로 저장됨",
}


def detect_correction_trigger(text: str) -> str | None:
    """사용자 정정 문구를 substring으로 탐지."""
    normalized = text.strip()
    for trigger in CORRECTION_TRIGGERS:
        if trigger in normalized:
            return trigger
    return None


def detect_question_rejection_trigger(text: str) -> str | None:
    """질문 거부 문구를 substring으로 탐지."""
    normalized = text.strip()
    for trigger in ("그런건 묻지마", "그런 건 묻지마", "묻지마"):
        if trigger in normalized:
            return trigger
    return None


def user_has_negative_emotion_context(text: str) -> bool:
    normalized = text.strip()
    return any(signal in normalized for signal in NEGATIVE_EMOTION_SIGNALS)


def question_has_positive_reframe(question: str) -> bool:
    normalized = question.strip()
    return any(signal in normalized for signal in POSITIVE_REFRAME_QUESTION_SIGNALS)


def detect_inappropriate_positive_reframe_risk(
    *,
    user_messages: str,
    question: str,
) -> bool:
    """부정 감정 + 긍정 회상 질문 조합을 탐지."""
    if not question.strip():
        return False
    if not user_has_negative_emotion_context(user_messages):
        return False
    return question_has_positive_reframe(question)


def _last_assistant_message(conversation: list[dict[str, str]] | None) -> str:
    if not conversation:
        return ""
    for turn in reversed(conversation):
        if turn.get("role") == "assistant":
            return str(turn.get("content", "")).strip()
    return ""


def user_said_memory_unavailable(text: str) -> bool:
    normalized = text.strip()
    return any(signal in normalized for signal in MEMORY_UNAVAILABLE_SIGNALS)


def detect_conditional_phrase(text: str) -> str | None:
    match = CONDITIONAL_PATTERN.search(text.strip())
    if match:
        return match.group(0)
    return None


def build_failure_context(
    conversation: list[dict[str, str]] | None,
    *,
    draft: dict[str, Any] | None = None,
    window: int = 4,
) -> list[dict[str, str]]:
    """실패 직전 대화 맥락을 role/content 형태로 구성."""
    context: list[dict[str, str]] = []
    if conversation:
        for turn in conversation[-window:]:
            role = turn.get("role", "user")
            content = str(turn.get("content", "")).strip()
            if content:
                context.append({"role": role, "content": content})

    if draft:
        summary = str(draft.get("event_summary") or "").strip()
        followup = str(draft.get("followup_question") or "").strip()
        if summary and not any(
            turn.get("role") == "assistant" and summary in turn.get("content", "")
            for turn in context
        ):
            context.append({"role": "assistant", "content": summary})
        elif followup and not any(
            turn.get("role") == "assistant" and followup in turn.get("content", "")
            for turn in context
        ):
            context.append({"role": "assistant", "content": followup})

    return context


def classify_failure_type(
    *,
    user_correction: str,
    context: list[dict[str, str]],
    draft: dict[str, Any] | None = None,
) -> str:
    """정정 문구와 맥락으로 failure_type을 분류."""
    if detect_question_rejection_trigger(user_correction):
        rejected_question = _last_assistant_message(context)
        user_messages = " ".join(
            turn["content"] for turn in context if turn.get("role") == "user"
        )
        if detect_inappropriate_positive_reframe_risk(
            user_messages=user_messages,
            question=rejected_question,
        ):
            return "inappropriate_positive_reframe"
        return "correction_ignored"

    if "기억" in user_correction and "했잖아" in user_correction:
        return "repeated_question"

    if detect_correction_trigger(user_correction):
        return "correction_ignored"

    user_messages = " ".join(
        turn["content"] for turn in context if turn.get("role") == "user"
    )
    combined = f"{user_messages} {user_correction}"

    if detect_conditional_phrase(combined) or _draft_has_conditional_misparse(draft, combined):
        return "korean_misparse"

    if user_said_memory_unavailable(combined):
        return "memory_unavailable_ignored"

    return "correction_ignored"


def _draft_has_conditional_misparse(
    draft: dict[str, Any] | None,
    combined_text: str,
) -> bool:
    if not draft:
        return bool(detect_conditional_phrase(combined_text))

    conditional = detect_conditional_phrase(combined_text)
    if not conditional:
        return False

    people = draft.get("people") or []
    if not people:
        return True

    subject_match = re.match(r"(.+?)(?:이|가)", conditional)
    if not subject_match:
        return False

    subject = subject_match.group(1).strip()
    for person in people:
        person_text = str(person)
        if subject in person_text and any(
            token in person_text for token in ("왕주임", "팀장", "승진")
        ):
            return True
    return False


def _message_index(conversation: list[dict[str, str]] | None) -> int | None:
    if not conversation:
        return None
    return len(conversation) - 1


class FailureRecorder:
    """JSONL 기반 해석 실패 스냅샷 저장소."""

    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path or DEFAULT_LOG_PATH
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        with open(self.log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def load_all(self) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with open(self.log_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries


_default_recorder = FailureRecorder()


def record_interpretation_failure(
    failure_type: str,
    context: list[dict[str, str]],
    user_correction: str,
    assistant_output: str,
    expected_behavior: str,
    root_cause: str,
    fixed_rule: str,
    *,
    severity: str = "medium",
    conversation_id: str = "",
    message_index: int | None = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    """실패 스냅샷 1건을 JSONL에 append."""
    if failure_type not in FAILURE_TYPES:
        raise ValueError(f"알 수 없는 failure_type: {failure_type}")

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "conversation_id": conversation_id or str(uuid.uuid4()),
        "message_index": message_index,
        "failure_type": failure_type,
        "severity": severity,
        "context": context,
        "user_correction": user_correction,
        "assistant_after_correction": assistant_output,
        "expected_behavior": expected_behavior,
        "root_cause": root_cause,
        "fixed_rule": fixed_rule,
    }

    recorder = FailureRecorder(log_path) if log_path else _default_recorder
    return recorder.append(record)


def try_prepare_correction_failure(
    *,
    user_correction: str,
    conversation: list[dict[str, str]] | None,
    draft: dict[str, Any] | None = None,
    conversation_id: str = "",
) -> dict[str, Any] | None:
    """정정 트리거 입력 시 기록 대기(pending) payload 생성."""
    if not detect_correction_trigger(user_correction):
        return None

    context = build_failure_context(conversation, draft=draft)
    failure_type = classify_failure_type(
        user_correction=user_correction,
        context=context,
        draft=draft,
    )

    return {
        "failure_type": failure_type,
        "context": context,
        "user_correction": user_correction,
        "expected_behavior": DEFAULT_EXPECTED_BEHAVIOR[failure_type],
        "root_cause": DEFAULT_ROOT_CAUSE[failure_type],
        "fixed_rule": RULE_BY_FAILURE_TYPE[failure_type],
        "severity": "medium",
        "conversation_id": conversation_id or str(uuid.uuid4()),
        "message_index": _message_index(conversation),
    }


def record_repeated_question_failure(
    *,
    user_text: str,
    followup_question: str,
    conversation: list[dict[str, str]] | None,
    conversation_id: str = "",
    log_path: Path | None = None,
) -> dict[str, Any] | None:
    """기억 불가 후 추가 질문 발생 시 즉시 기록."""
    if not user_said_memory_unavailable(user_text):
        return None

    context = build_failure_context(conversation)
    if followup_question:
        context.append({"role": "assistant", "content": followup_question})

    return record_interpretation_failure(
        failure_type="repeated_question",
        context=context,
        user_correction="",
        assistant_output=followup_question,
        expected_behavior=DEFAULT_EXPECTED_BEHAVIOR["repeated_question"],
        root_cause=DEFAULT_ROOT_CAUSE["repeated_question"],
        fixed_rule=RULE_BY_FAILURE_TYPE["repeated_question"],
        conversation_id=conversation_id,
        message_index=_message_index(conversation),
        log_path=log_path,
    )


def record_korean_misparse_failure(
    *,
    user_text: str,
    assistant_output: str,
    conversation: list[dict[str, str]] | None,
    draft: dict[str, Any] | None = None,
    user_correction: str = "",
    conversation_id: str = "",
    log_path: Path | None = None,
) -> dict[str, Any] | None:
    """조건문 오해석 패턴 감지 시 기록."""
    if not detect_conditional_phrase(user_text) and not _draft_has_conditional_misparse(
        draft, user_text
    ):
        return None

    context = build_failure_context(conversation, draft=draft)
    return record_interpretation_failure(
        failure_type="korean_misparse",
        context=context,
        user_correction=user_correction,
        assistant_output=assistant_output,
        expected_behavior=DEFAULT_EXPECTED_BEHAVIOR["korean_misparse"],
        root_cause=DEFAULT_ROOT_CAUSE["korean_misparse"],
        fixed_rule=RULE_BY_FAILURE_TYPE["korean_misparse"],
        conversation_id=conversation_id,
        message_index=_message_index(conversation),
        log_path=log_path,
    )


def record_inappropriate_positive_reframe_failure(
    *,
    user_messages: str,
    followup_question: str,
    conversation: list[dict[str, str]] | None,
    user_correction: str = "",
    conversation_id: str = "",
    log_path: Path | None = None,
    notes: str = "",
) -> dict[str, Any] | None:
    """부정 감정 직후 긍정 회상 질문 발생 시 기록."""
    if not detect_inappropriate_positive_reframe_risk(
        user_messages=user_messages,
        question=followup_question,
    ):
        return None

    context = build_failure_context(conversation, window=8)
    if followup_question and not any(
        turn.get("role") == "assistant" and followup_question in turn.get("content", "")
        for turn in context
    ):
        context.append({"role": "assistant", "content": followup_question})

    record = record_interpretation_failure(
        failure_type="inappropriate_positive_reframe",
        context=context,
        user_correction=user_correction,
        assistant_output=followup_question,
        expected_behavior=DEFAULT_EXPECTED_BEHAVIOR["inappropriate_positive_reframe"],
        root_cause=DEFAULT_ROOT_CAUSE["inappropriate_positive_reframe"],
        fixed_rule=RULE_BY_FAILURE_TYPE["inappropriate_positive_reframe"],
        severity="high",
        conversation_id=conversation_id,
        message_index=_message_index(conversation),
        log_path=log_path,
    )
    if notes:
        record["notes"] = notes
    return record


def record_value_hidden_by_event_failure(
    *,
    user_text: str,
    draft: dict[str, Any],
    conversation: list[dict[str, str]] | None = None,
    user_correction: str = "",
    conversation_id: str = "",
    severity: str = "medium",
    log_path: Path | None = None,
    notes: str = "",
) -> dict[str, Any] | None:
    """가치관이 핵심인데 사건 위주로 저장된 경우 기록.

    fidelity.draft_hides_value로 판단한다.
    """
    from conversation_to_memory.memory.fidelity import draft_hides_value

    if not draft_hides_value(draft, user_text):
        return None

    context = build_failure_context(conversation, draft=draft, window=8)
    assistant_output = str(draft.get("event_summary") or "").strip()

    record = record_interpretation_failure(
        failure_type="value_hidden_by_event",
        context=context,
        user_correction=user_correction,
        assistant_output=assistant_output,
        expected_behavior=DEFAULT_EXPECTED_BEHAVIOR["value_hidden_by_event"],
        root_cause=DEFAULT_ROOT_CAUSE["value_hidden_by_event"],
        fixed_rule=RULE_BY_FAILURE_TYPE["value_hidden_by_event"],
        severity=severity,
        conversation_id=conversation_id,
        message_index=_message_index(conversation),
        log_path=log_path,
    )
    if notes:
        record["notes"] = notes
    return record


def try_prepare_question_rejection_failure(
    *,
    user_correction: str,
    conversation: list[dict[str, str]] | None,
    conversation_id: str = "",
) -> dict[str, Any] | None:
    """질문 거부 입력 시 직전 봇 질문을 failure snapshot으로 준비."""
    if not detect_question_rejection_trigger(user_correction):
        return None

    context = build_failure_context(conversation, window=8)
    rejected_question = _last_assistant_message(conversation)
    if not rejected_question:
        return None

    failure_type = classify_failure_type(
        user_correction=user_correction,
        context=context,
    )
    if failure_type != "inappropriate_positive_reframe":
        return None

    return {
        "failure_type": failure_type,
        "context": context,
        "user_correction": user_correction,
        "expected_behavior": DEFAULT_EXPECTED_BEHAVIOR[failure_type],
        "root_cause": DEFAULT_ROOT_CAUSE[failure_type],
        "fixed_rule": RULE_BY_FAILURE_TYPE[failure_type],
        "severity": "high",
        "conversation_id": conversation_id or str(uuid.uuid4()),
        "message_index": _message_index(conversation),
        "assistant_output": rejected_question,
    }


def finalize_question_rejection_failure(
    pending: dict[str, Any],
    *,
    log_path: Path | None = None,
) -> dict[str, Any]:
    """질문 거부 pending failure를 즉시 기록."""
    record = record_interpretation_failure(
        failure_type=pending["failure_type"],
        context=pending["context"],
        user_correction=pending["user_correction"],
        assistant_output=pending.get("assistant_output", ""),
        expected_behavior=pending["expected_behavior"],
        root_cause=pending["root_cause"],
        fixed_rule=pending["fixed_rule"],
        severity=pending.get("severity", "high"),
        conversation_id=pending.get("conversation_id", ""),
        message_index=pending.get("message_index"),
        log_path=log_path,
    )
    notes = pending.get("notes")
    if notes:
        record["notes"] = notes
    return record


def finalize_pending_failure(
    pending: dict[str, Any],
    assistant_output: str,
    *,
    log_path: Path | None = None,
) -> dict[str, Any]:
    """정정 후 AI 결과를 포함해 pending failure를 기록."""
    return record_interpretation_failure(
        failure_type=pending["failure_type"],
        context=pending["context"],
        user_correction=pending["user_correction"],
        assistant_output=assistant_output,
        expected_behavior=pending["expected_behavior"],
        root_cause=pending["root_cause"],
        fixed_rule=pending["fixed_rule"],
        severity=pending.get("severity", "medium"),
        conversation_id=pending.get("conversation_id", ""),
        message_index=pending.get("message_index"),
        log_path=log_path,
    )
