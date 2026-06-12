"""User session state for memory archive recording."""

from __future__ import annotations

from typing import Any

from telegram.ext import ContextTypes

KEY_CURRENT_SESSION = "current_session"
KEY_CURRENT_DRAFT = "current_draft"
KEY_CANCELLED_DRAFT = "cancelled_draft"
KEY_CANCELLATION_REASON = "cancellation_reason"
KEY_RECENT_CONTEXT = "recent_context"
KEY_FOLLOWUP_ASKED = "followup_asked"
KEY_QUESTION_SESSION = "question_session"
KEY_PERSISTED_DRAFT_ID = "persisted_draft_id"

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


def get_session(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    return context.user_data.get(KEY_CURRENT_SESSION)


def ensure_session(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    session = context.user_data.get(KEY_CURRENT_SESSION)
    if session is None:
        session = {"conversation": [], "user_texts": []}
        context.user_data[KEY_CURRENT_SESSION] = session
    return session


def get_draft(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    return context.user_data.get(KEY_CURRENT_DRAFT)


def set_draft(context: ContextTypes.DEFAULT_TYPE, draft: dict[str, Any]) -> None:
    context.user_data[KEY_CURRENT_DRAFT] = draft


def get_cancelled_draft(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    return context.user_data.get(KEY_CANCELLED_DRAFT)


def has_cancelled_draft(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return KEY_CANCELLED_DRAFT in context.user_data


def get_recent_context(context: ContextTypes.DEFAULT_TYPE) -> list[dict[str, Any]]:
    return context.user_data.setdefault(KEY_RECENT_CONTEXT, [])


def ensure_question_session(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    qsession = context.user_data.get(KEY_QUESTION_SESSION)
    if qsession is None:
        qsession = {
            "questions_asked": 0,
            "question_modes_used": [],
            "meaning_check_count": 0,
            "last_question_mode": None,
        }
        context.user_data[KEY_QUESTION_SESSION] = qsession
    return qsession


def record_question(
    context: ContextTypes.DEFAULT_TYPE,
    draft: dict[str, Any],
    question_result: dict[str, Any],
) -> dict[str, Any]:
    """질문 1회를 세션에 기록하고 draft.question_mode_used를 갱신."""
    qsession = ensure_question_session(context)
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
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_texts: list[str],
    draft: dict[str, Any],
) -> None:
    recent = get_recent_context(context)
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
    context: ContextTypes.DEFAULT_TYPE,
    *,
    reason: str = "",
) -> None:
    draft = context.user_data.pop(KEY_CURRENT_DRAFT, None)
    session = context.user_data.get(KEY_CURRENT_SESSION)

    if draft is not None:
        context.user_data[KEY_CANCELLED_DRAFT] = draft
        if reason:
            context.user_data[KEY_CANCELLATION_REASON] = reason
        elif session:
            user_texts = session.get("user_texts", [])
            if user_texts:
                context.user_data[KEY_CANCELLATION_REASON] = user_texts[-1]

        user_texts = session.get("user_texts", []) if session else []
        append_recent_context(context, user_texts=user_texts, draft=draft)

    context.user_data.pop(KEY_CURRENT_SESSION, None)
    context.user_data.pop(KEY_FOLLOWUP_ASKED, None)
    context.user_data.pop(KEY_QUESTION_SESSION, None)


def clear_cancelled_draft(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(KEY_CANCELLED_DRAFT, None)
    context.user_data.pop(KEY_CANCELLATION_REASON, None)
    context.user_data.pop(KEY_PERSISTED_DRAFT_ID, None)


def load_cancelled_draft_from_db(
    context: ContextTypes.DEFAULT_TYPE,
    persisted: dict[str, Any],
) -> None:
    """Restore cancelled draft from SQLite row into user_data."""
    context.user_data[KEY_CANCELLED_DRAFT] = persisted["draft"]
    context.user_data[KEY_PERSISTED_DRAFT_ID] = persisted["id"]
    if persisted.get("cancellation_reason"):
        context.user_data[KEY_CANCELLATION_REASON] = persisted["cancellation_reason"]

    user_texts = persisted.get("user_texts") or []
    conversation = persisted.get("conversation") or []
    if user_texts or conversation:
        context.user_data[KEY_CURRENT_SESSION] = {
            "user_texts": list(user_texts),
            "conversation": list(conversation),
        }


def is_edit_command(text: str) -> bool:
    return text in EDIT_KEYWORDS or text.startswith("수정 ")


def reset_recording_session(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in (
        KEY_CURRENT_SESSION,
        KEY_CURRENT_DRAFT,
        KEY_FOLLOWUP_ASKED,
        KEY_QUESTION_SESSION,
    ):
        context.user_data.pop(key, None)


def reset_all(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in (
        KEY_CURRENT_SESSION,
        KEY_CURRENT_DRAFT,
        KEY_CANCELLED_DRAFT,
        KEY_CANCELLATION_REASON,
        KEY_RECENT_CONTEXT,
        KEY_FOLLOWUP_ASKED,
        KEY_QUESTION_SESSION,
        KEY_PERSISTED_DRAFT_ID,
    ):
        context.user_data.pop(key, None)


def restore_cancelled_to_current(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    draft = context.user_data.pop(KEY_CANCELLED_DRAFT, None)
    if draft is None:
        return None
    context.user_data[KEY_CURRENT_DRAFT] = draft
    ensure_session(context)
    return draft


def relates_to_cancellation(text: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """취소 사유·맥락과 새 입력이 관련 있는지 간단히 판별."""
    reason = context.user_data.get(KEY_CANCELLATION_REASON, "")
    if not reason and not has_cancelled_draft(context):
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
