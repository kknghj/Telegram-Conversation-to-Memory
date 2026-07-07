"""User session state for memory archive recording."""

from __future__ import annotations

from typing import Any

KEY_CURRENT_SESSION = "current_session"
KEY_CURRENT_DRAFT = "current_draft"
KEY_CANCELLED_DRAFT = "cancelled_draft"
KEY_CANCELLATION_REASON = "cancellation_reason"
KEY_RECENT_CONTEXT = "recent_context"
KEY_FOLLOWUP_ASKED = "followup_asked"
KEY_QUESTION_SESSION = "question_session"
KEY_PERSISTED_DRAFT_ID = "persisted_draft_id"
KEY_PENDING_FAILURE = "pending_failure_recording"
KEY_DECISION_TRACE = "decision_trace"

CANCEL_MESSAGE = (
    "저장을 취소했습니다. 방금 요약은 저장하지 않았습니다.\n"
    "임시 초안으로 보관해두었습니다.\n"
    "'수정'이라고 입력하면 마지막 초안을 다시 불러올 수 있습니다."
)

RESUME_CHOICE_MESSAGE = (
    "이전에 저장하지 않은 기록이 있습니다.\n\n"
    "1. 이전 기록 이어쓰기\n"
    "2. 새 기록 시작\n\n"
    "번호를 선택해주세요."
)

NO_DRAFT_TO_EDIT_MESSAGE = "수정할 임시 초안이 없습니다."

EDIT_KEYWORDS = ("수정", "이전 기록 수정", "취소한 기록 수정")


def get_session(user_data: dict[str, Any]) -> dict[str, Any] | None:
    return user_data.get(KEY_CURRENT_SESSION)


def ensure_session(user_data: dict[str, Any]) -> dict[str, Any]:
    session = user_data.get(KEY_CURRENT_SESSION)
    if session is None:
        session = {"conversation": [], "user_texts": []}
        user_data[KEY_CURRENT_SESSION] = session
    return session


def get_draft(user_data: dict[str, Any]) -> dict[str, Any] | None:
    return user_data.get(KEY_CURRENT_DRAFT)


def get_decision_trace(user_data: dict[str, Any]):
    """Return the active decision trace collector when debug mode is enabled."""
    from conversation_to_memory.debug.decision_trace import (
        DecisionTraceCollector,
        is_decision_trace_enabled,
    )

    if not is_decision_trace_enabled():
        return None

    collector = user_data.get(KEY_DECISION_TRACE)
    if collector is None:
        collector = DecisionTraceCollector()
        user_data[KEY_DECISION_TRACE] = collector
    return collector


def clear_decision_trace(user_data: dict[str, Any]) -> None:
    user_data.pop(KEY_DECISION_TRACE, None)


def set_draft(user_data: dict[str, Any], draft: dict[str, Any]) -> None:
    user_data[KEY_CURRENT_DRAFT] = draft


def get_cancelled_draft(user_data: dict[str, Any]) -> dict[str, Any] | None:
    return user_data.get(KEY_CANCELLED_DRAFT)


def has_cancelled_draft(user_data: dict[str, Any]) -> bool:
    return KEY_CANCELLED_DRAFT in user_data


def get_recent_context(user_data: dict[str, Any]) -> list[dict[str, Any]]:
    return user_data.setdefault(KEY_RECENT_CONTEXT, [])


def ensure_question_session(user_data: dict[str, Any]) -> dict[str, Any]:
    qsession = user_data.get(KEY_QUESTION_SESSION)
    if qsession is None:
        qsession = {
            "questions_asked": 0,
            "question_modes_used": [],
            "meaning_check_count": 0,
            "last_question_mode": None,
        }
        user_data[KEY_QUESTION_SESSION] = qsession
    return qsession


def record_question(
    user_data: dict[str, Any],
    draft: dict[str, Any],
    question_result: dict[str, Any],
) -> dict[str, Any]:
    """질문 1회를 세션에 기록하고 draft.question_mode_used를 갱신."""
    qsession = ensure_question_session(user_data)
    mode = question_result.get("question_mode")
    qsession["questions_asked"] += 1
    if mode:
        qsession["question_modes_used"].append(mode)
        qsession["last_question_mode"] = mode
    if mode == "meaning_check":
        qsession["meaning_check_count"] += 1
    draft["question_mode_used"] = list(qsession["question_modes_used"])
    return qsession


def append_recent_context(
    user_data: dict[str, Any],
    *,
    user_texts: list[str],
    draft: dict[str, Any],
) -> None:
    recent = get_recent_context(user_data)
    recent.append(
        {
            "user_texts": list(user_texts),
            "event_summary": draft.get("event_summary", ""),
            "memory_candidate": draft.get("memory_candidate", ""),
        }
    )
    if len(recent) > 5:
        del recent[:-5]


def cancel_current_draft(
    user_data: dict[str, Any],
    *,
    reason: str = "",
) -> None:
    draft = user_data.pop(KEY_CURRENT_DRAFT, None)
    current_session = user_data.get(KEY_CURRENT_SESSION)

    if draft is not None:
        user_data[KEY_CANCELLED_DRAFT] = draft
        if reason:
            user_data[KEY_CANCELLATION_REASON] = reason
        elif current_session:
            user_texts = current_session.get("user_texts", [])
            if user_texts:
                user_data[KEY_CANCELLATION_REASON] = user_texts[-1]

        user_texts = current_session.get("user_texts", []) if current_session else []
        append_recent_context(user_data, user_texts=user_texts, draft=draft)

    user_data.pop(KEY_CURRENT_SESSION, None)
    user_data.pop(KEY_FOLLOWUP_ASKED, None)
    user_data.pop(KEY_QUESTION_SESSION, None)


def clear_cancelled_draft(user_data: dict[str, Any]) -> None:
    user_data.pop(KEY_CANCELLED_DRAFT, None)
    user_data.pop(KEY_CANCELLATION_REASON, None)
    user_data.pop(KEY_PERSISTED_DRAFT_ID, None)


def load_cancelled_draft_from_db(
    user_data: dict[str, Any],
    persisted: dict[str, Any],
) -> None:
    """Restore cancelled draft from SQLite row into user_data."""
    user_data[KEY_CANCELLED_DRAFT] = persisted["draft"]
    user_data[KEY_PERSISTED_DRAFT_ID] = persisted["id"]
    if persisted.get("cancellation_reason"):
        user_data[KEY_CANCELLATION_REASON] = persisted["cancellation_reason"]

    user_texts = persisted.get("user_texts") or []
    conversation = persisted.get("conversation") or []
    if user_texts or conversation:
        user_data[KEY_CURRENT_SESSION] = {
            "user_texts": list(user_texts),
            "conversation": list(conversation),
        }


def is_edit_command(text: str) -> bool:
    return text in EDIT_KEYWORDS or text.startswith("수정 ")


def reset_recording_session(user_data: dict[str, Any]) -> None:
    for key in (
        KEY_CURRENT_SESSION,
        KEY_CURRENT_DRAFT,
        KEY_FOLLOWUP_ASKED,
        KEY_QUESTION_SESSION,
        KEY_PENDING_FAILURE,
        KEY_DECISION_TRACE,
    ):
        user_data.pop(key, None)


def reset_all(user_data: dict[str, Any]) -> None:
    for key in (
        KEY_CURRENT_SESSION,
        KEY_CURRENT_DRAFT,
        KEY_CANCELLED_DRAFT,
        KEY_CANCELLATION_REASON,
        KEY_RECENT_CONTEXT,
        KEY_FOLLOWUP_ASKED,
        KEY_QUESTION_SESSION,
        KEY_PERSISTED_DRAFT_ID,
        KEY_PENDING_FAILURE,
        KEY_DECISION_TRACE,
    ):
        user_data.pop(key, None)


def restore_cancelled_to_current(user_data: dict[str, Any]) -> dict[str, Any] | None:
    draft = user_data.pop(KEY_CANCELLED_DRAFT, None)
    if draft is None:
        return None
    user_data[KEY_CURRENT_DRAFT] = draft
    ensure_session(user_data)
    return draft


def relates_to_cancellation(text: str, user_data: dict[str, Any]) -> bool:
    """취소 사유·맥락과 새 입력이 관련 있는지 간단히 판별."""
    reason = user_data.get(KEY_CANCELLATION_REASON, "")
    if not reason and not has_cancelled_draft(user_data):
        return False

    keywords = (
        "왜곡",
        "긍정",
        "있는 그대로",
        "원문",
        "취소",
        "수정",
        "이전",
        "방금",
        "요약",
    )
    if any(k in text for k in keywords):
        return True
    if reason and any(word in text for word in reason.split() if len(word) >= 2):
        return True
    return False
