"""Telegram bot conversation handlers — thin adapters over chat_service."""

import asyncio
import logging

from telegram import Message, Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import ContextTypes, ConversationHandler

from conversation_to_memory.bot import chat_service, states

logger = logging.getLogger(__name__)

_SEND_MAX_RETRIES = 3
_SEND_RETRY_BACKOFF_SECONDS = 2.0


async def _reply_text_with_retry(
    message: Message,
    text: str,
    *,
    parse_mode: str | None = None,
) -> None:
    kwargs = {"parse_mode": parse_mode} if parse_mode else {}

    for attempt in range(1, _SEND_MAX_RETRIES + 1):
        try:
            await message.reply_text(text, **kwargs)
            return
        except (TimedOut, NetworkError) as exc:
            if attempt >= _SEND_MAX_RETRIES:
                logger.error(
                    "Telegram reply failed after %d attempts: %s",
                    _SEND_MAX_RETRIES,
                    exc,
                )
                raise
            wait = _SEND_RETRY_BACKOFF_SECONDS * attempt
            logger.warning(
                "Telegram reply timed out (attempt %d/%d), retrying in %.1fs",
                attempt,
                _SEND_MAX_RETRIES,
                wait,
            )
            await asyncio.sleep(wait)


def _user_id(update: Update) -> str:
    user = update.effective_user
    return str(user.id if user else 0)


async def _reply_result(
    update: Update,
    result: chat_service.ChatTurnResult,
) -> int:
    for message in result.messages:
        await _reply_text_with_retry(
            update.message,
            message,
            parse_mode=result.parse_mode,
        )
    return result.state if result.state != chat_service.IDLE else ConversationHandler.END


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    result = chat_service.handle_start(context.user_data)
    return await _reply_result(update, result)


async def begin_recording(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    result = chat_service.handle_begin_recording(_user_id(update), context.user_data, text)
    return await _reply_result(update, result)


async def handle_resume_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    result = chat_service.handle_resume_choice(_user_id(update), context.user_data, text)
    return await _reply_result(update, result)


async def handle_recording(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    result = chat_service.handle_recording(_user_id(update), context.user_data, text)
    return await _reply_result(update, result)


async def handle_followup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    result = chat_service.handle_followup(_user_id(update), context.user_data, text)
    return await _reply_result(update, result)


async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    result = chat_service.handle_review(_user_id(update), context.user_data, text)
    return await _reply_result(update, result)


async def handle_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    result = chat_service.handle_edit(_user_id(update), context.user_data, text)
    return await _reply_result(update, result)


async def edit_cancelled_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    result = chat_service.handle_edit_cancelled_draft(_user_id(update), context.user_data)
    return await _reply_result(update, result)


async def route_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    result = chat_service.handle_route_message(_user_id(update), context.user_data, text)
    for message in result.messages:
        await _reply_text_with_retry(update.message, message)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    result = chat_service.handle_cancel(_user_id(update), context.user_data)
    return await _reply_result(update, result)
