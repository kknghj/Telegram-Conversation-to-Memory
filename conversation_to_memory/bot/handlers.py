"""Telegram bot conversation handlers — memory archive flow."""

import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from app import database as db
from conversation_to_memory.bot import session, states
from conversation_to_memory.memory import service as memory_service
from conversation_to_memory.storage.local_json import LocalJsonStorage

logger = logging.getLogger(__name__)

storage = LocalJsonStorage()

SAVE_KEYWORD = "저장"
CANCEL_KEYWORD = "취소"
EDIT_KEYWORD = "수정"
NEW_RECORD_KEYWORD = "새 기록"
RESUME_KEYWORD = "이어서"
NEW_START_KEYWORD = "새로"
BEGIN_KEYWORD = "기록 시작"


def _user_id(update: Update) -> str:
    user = update.effective_user
    return str(user.id if user else 0)


def _ensure_cancelled_draft_loaded(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """Load latest cancelled draft from SQLite if not already in memory."""
    if session.has_cancelled_draft(context):
        return True

    persisted = db.get_latest_cancelled_draft(_user_id(update))
    if persisted:
        session.load_cancelled_draft_from_db(context, persisted)
        return True
    return False


def _persist_cancelled_draft(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    reason: str = "",
) -> None:
    """Cancel current draft in memory and persist to SQLite."""
    sess = session.get_session(context)
    draft = session.get_draft(context)
    if draft is None:
        session.cancel_current_draft(context, reason=reason)
        return

    user_texts = sess.get("user_texts", []) if sess else []
    conversation = sess.get("conversation", []) if sess else []

    cancellation_reason = reason
    if not cancellation_reason and sess:
        texts = sess.get("user_texts", [])
        if texts:
            cancellation_reason = texts[-1]

    draft_id = db.save_cancelled_draft(
        _user_id(update),
        draft=draft,
        user_texts=user_texts,
        conversation=conversation,
        cancellation_reason=cancellation_reason,
    )

    session.cancel_current_draft(context, reason=cancellation_reason)
    context.user_data[session.KEY_PERSISTED_DRAFT_ID] = draft_id


def _recording_prompt() -> str:
    return (
        "있는 그대로 기록해 주세요. 오늘 있었던 일, 감정, 생각을 자유롭게 적어주세요.\n"
        "다 적으셨으면 「요약」이라고 입력하세요.\n"
        "(상담·조언·성장 서사가 아닌, 원문 기반 정리만 합니다.)"
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session.reset_recording_session(context)
    await update.message.reply_text(
        "안녕하세요. 기억 아카이브 봇입니다.\n\n"
        "상담봇이나 자기계발 일기봇이 아니라, 말한 내용을 있는 그대로 정리·보관합니다.\n\n"
        f"기록을 시작하려면 「{BEGIN_KEYWORD}」을 입력하세요.\n"
        "자유롭게 기록 → (필요 시 질문 1개) → 요약 확인 → 「저장」"
    )
    return ConversationHandler.END


async def begin_recording(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    user_id = _user_id(update)

    has_recent = db.has_recent_cancelled_draft(user_id)
    if has_recent:
        _ensure_cancelled_draft_loaded(update, context)

    if session.has_cancelled_draft(context) or has_recent:
        if session.relates_to_cancellation(text, context):
            draft = session.restore_cancelled_to_current(context)
            if draft:
                await update.message.reply_text(
                    "이전에 취소한 기록 맥락을 참고합니다.\n\n"
                    + memory_service.format_review_message(draft)
                )
                return states.REVIEW

        await update.message.reply_text(session.RESUME_CHOICE_MESSAGE)
        return states.RESUME_CHOICE

    session.reset_recording_session(context)
    session.ensure_session(context)
    db.save_active_draft(
        user_id,
        user_texts=[],
        conversation=[],
    )
    await update.message.reply_text(_recording_prompt())
    return states.RECORDING


async def handle_resume_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    if text in ("1", RESUME_KEYWORD, EDIT_KEYWORD):
        if not _ensure_cancelled_draft_loaded(update, context):
            await update.message.reply_text(session.NO_DRAFT_TO_EDIT_MESSAGE)
            return ConversationHandler.END

        draft = session.restore_cancelled_to_current(context)
        if not draft:
            await update.message.reply_text(session.NO_DRAFT_TO_EDIT_MESSAGE)
            return ConversationHandler.END

        await update.message.reply_text(
            "이전 초안을 불러왔습니다.\n\n" + memory_service.format_review_message(draft)
        )
        return states.REVIEW

    if text in ("2", NEW_START_KEYWORD, NEW_RECORD_KEYWORD):
        session.clear_cancelled_draft(context)
        session.reset_recording_session(context)
        session.ensure_session(context)
        db.save_active_draft(
            _user_id(update),
            user_texts=[],
            conversation=[],
        )
        await update.message.reply_text("새 기록을 시작합니다.\n\n" + _recording_prompt())
        return states.RECORDING

    if session.relates_to_cancellation(text, context):
        session.ensure_session(context)
        sess = session.ensure_session(context)
        sess["user_texts"].append(text)
        sess["conversation"].append({"role": "user", "content": text})

        try:
            draft = memory_service.analyze_recording(
                user_texts=sess["user_texts"],
                conversation=sess["conversation"],
                recent_context=session.get_recent_context(context),
                cancelled_draft=session.get_cancelled_draft(context),
                cancellation_reason=context.user_data.get(session.KEY_CANCELLATION_REASON, ""),
            )
            session.clear_cancelled_draft(context)
            session.set_draft(context, draft)
            return await _maybe_followup_or_review(update, context, draft)
        except Exception as e:
            logger.exception("취소 맥락 기록 처리 오류")
            await update.message.reply_text(f"오류: {e}\n「{BEGIN_KEYWORD}」으로 다시 시도하세요.")
            session.reset_recording_session(context)
            return ConversationHandler.END

    await update.message.reply_text(
        f"「1」 또는 「2」, 또는 「{RESUME_KEYWORD}」 / 「{NEW_START_KEYWORD}」를 입력해주세요."
    )
    return states.RESUME_CHOICE


async def handle_recording(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    sess = session.ensure_session(context)

    if text != states.SUMMARY_TRIGGER:
        sess["user_texts"].append(text)
        sess["conversation"].append({"role": "user", "content": text})
        db.save_active_draft(
            _user_id(update),
            user_texts=sess["user_texts"],
            conversation=sess["conversation"],
        )
        await update.message.reply_text(
            "기록했습니다. 더 적으시거나, 다 적으셨으면 「요약」을 입력하세요."
        )
        return states.RECORDING

    if not sess["user_texts"]:
        await update.message.reply_text("먼저 기록 내용을 입력해주세요.")
        return states.RECORDING

    try:
        draft = memory_service.analyze_recording(
            user_texts=sess["user_texts"],
            conversation=sess["conversation"],
            recent_context=session.get_recent_context(context),
            cancelled_draft=session.get_cancelled_draft(context),
            cancellation_reason=context.user_data.get(session.KEY_CANCELLATION_REASON, ""),
        )
        session.set_draft(context, draft)
        db.save_active_draft(
            _user_id(update),
            user_texts=sess["user_texts"],
            conversation=sess["conversation"],
            draft=draft,
        )
        return await _maybe_followup_or_review(update, context, draft)
    except Exception as e:
        logger.exception("기록 분석 오류")
        await update.message.reply_text(f"분석 중 오류: {e}\n다시 「요약」을 시도하거나 내용을 추가해주세요.")
        return states.RECORDING


async def _maybe_followup_or_review(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    draft: dict,
) -> int:
    followup_asked = context.user_data.get(session.KEY_FOLLOWUP_ASKED, False)
    needs_followup = draft.get("needs_followup") and draft.get("followup_question")

    if needs_followup and not followup_asked:
        question = draft["followup_question"]
        sess = session.ensure_session(context)
        sess["conversation"].append({"role": "assistant", "content": question})
        context.user_data[session.KEY_FOLLOWUP_ASKED] = True
        await update.message.reply_text(question)
        return states.FOLLOWUP

    review_text = memory_service.format_review_message(draft)
    await update.message.reply_text(review_text)
    return states.REVIEW


async def handle_followup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    sess = session.ensure_session(context)
    sess["user_texts"].append(text)
    sess["conversation"].append({"role": "user", "content": text})

    try:
        draft = memory_service.analyze_recording(
            user_texts=sess["user_texts"],
            conversation=sess["conversation"],
            recent_context=session.get_recent_context(context),
            followup_already_asked=True,
        )
        session.set_draft(context, draft)
        db.save_active_draft(
            _user_id(update),
            user_texts=sess["user_texts"],
            conversation=sess["conversation"],
            draft=draft,
        )
        review_text = memory_service.format_review_message(draft)
        await update.message.reply_text(review_text)
        return states.REVIEW
    except Exception as e:
        logger.exception("후속 답변 처리 오류")
        await update.message.reply_text(f"오류: {e}")
        return states.FOLLOWUP


async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    if text == SAVE_KEYWORD:
        return await _save_draft(update, context)

    if text == CANCEL_KEYWORD:
        _persist_cancelled_draft(update, context)
        await update.message.reply_text(session.CANCEL_MESSAGE)
        return ConversationHandler.END

    if text == EDIT_KEYWORD or text.startswith(EDIT_KEYWORD):
        edit_instruction = text[len(EDIT_KEYWORD) :].strip()
        if not edit_instruction:
            await update.message.reply_text(
                "어떤 부분을 고치고 싶은지 함께 적어주세요.\n"
                "예: 「수정 지나치게 긍정적으로 왜곡하지 말고 있는 그대로 받아들여줘」"
            )
            return states.EDIT
        return await _apply_edit(update, context, edit_instruction)

    await update.message.reply_text(
        f"「{SAVE_KEYWORD}」, 「{EDIT_KEYWORD}」, 「{CANCEL_KEYWORD}」 중 하나를 입력해주세요."
    )
    return states.REVIEW


async def handle_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _apply_edit(update, context, update.message.text.strip())


async def _apply_edit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    edit_instruction: str,
) -> int:
    sess = session.get_session(context)
    draft = session.get_draft(context)

    if not sess or not draft:
        if not _ensure_cancelled_draft_loaded(update, context):
            await update.message.reply_text(session.NO_DRAFT_TO_EDIT_MESSAGE)
            return ConversationHandler.END
        cancelled = session.get_cancelled_draft(context)
        if cancelled:
            session.restore_cancelled_to_current(context)
            sess = session.ensure_session(context)
            draft = session.get_draft(context)
        else:
            await update.message.reply_text(session.NO_DRAFT_TO_EDIT_MESSAGE)
            return ConversationHandler.END

    try:
        revised = memory_service.analyze_recording(
            user_texts=sess["user_texts"],
            conversation=sess["conversation"],
            recent_context=session.get_recent_context(context),
            edit_instruction=edit_instruction,
            followup_already_asked=True,
        )
        session.set_draft(context, revised)
        await update.message.reply_text(memory_service.format_review_message(revised))
        return states.REVIEW
    except Exception as e:
        logger.exception("수정 처리 오류")
        await update.message.reply_text(f"수정 중 오류: {e}")
        return states.REVIEW


async def _save_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pending = session.get_draft(context)
    sess = session.get_session(context)

    if not pending:
        await update.message.reply_text(f"저장할 기억이 없습니다. 「{BEGIN_KEYWORD}」으로 새로 시작하세요.")
        return ConversationHandler.END

    full_memory = {
        **pending,
        "conversation": sess.get("conversation", []) if sess else [],
        "approved": True,
    }

    try:
        filepath = storage.save(full_memory)
        draft_id = context.user_data.get(session.KEY_PERSISTED_DRAFT_ID)
        db.mark_draft_saved(
            draft_id,
            _user_id(update),
            draft=pending,
            user_texts=sess.get("user_texts", []) if sess else [],
            conversation=sess.get("conversation", []) if sess else [],
        )
        await update.message.reply_text(
            f"✅ 기억이 저장되었습니다.\n\n파일: `{filepath}`\n\n"
            f"다시 기록하려면 「{BEGIN_KEYWORD}」을 입력하세요.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.exception("저장 오류")
        await update.message.reply_text(f"저장 실패: {e}")
        return states.REVIEW

    session.reset_all(context)
    return ConversationHandler.END


async def edit_cancelled_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Load the latest cancelled draft and enter review."""
    if not _ensure_cancelled_draft_loaded(update, context):
        await update.message.reply_text(session.NO_DRAFT_TO_EDIT_MESSAGE)
        return ConversationHandler.END

    draft = session.restore_cancelled_to_current(context)
    if not draft:
        await update.message.reply_text(session.NO_DRAFT_TO_EDIT_MESSAGE)
        return ConversationHandler.END

    await update.message.reply_text(
        "취소했던 초안을 불러왔습니다.\n\n" + memory_service.format_review_message(draft)
    )
    return states.REVIEW


async def route_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """대화 세션 밖에서 보낸 일반 텍스트."""
    text = update.message.text.strip()

    if session.is_edit_command(text):
        if _ensure_cancelled_draft_loaded(update, context):
            draft = session.restore_cancelled_to_current(context)
            session.ensure_session(context)
            await update.message.reply_text(
                "취소했던 초안을 불러왔습니다.\n\n"
                + memory_service.format_review_message(draft)
            )
        else:
            await update.message.reply_text(session.NO_DRAFT_TO_EDIT_MESSAGE)
        return

    if text == NEW_RECORD_KEYWORD:
        session.clear_cancelled_draft(context)
        session.reset_recording_session(context)
        await update.message.reply_text(
            f"새 기록을 시작합니다. 「{BEGIN_KEYWORD}」을 입력해주세요."
        )
        return

    if text == BEGIN_KEYWORD:
        return

    await update.message.reply_text(
        f"기록을 시작하려면 「{BEGIN_KEYWORD}」을 입력하세요.\n"
        "도움말은 /start"
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = session.get_draft(context)
    if draft:
        _persist_cancelled_draft(update, context)
        await update.message.reply_text(session.CANCEL_MESSAGE)
    else:
        session.reset_recording_session(context)
        await update.message.reply_text("진행 중인 기록을 취소했습니다.")
    return ConversationHandler.END
