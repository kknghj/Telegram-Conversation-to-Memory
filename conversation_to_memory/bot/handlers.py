"""Telegram bot conversation handlers — thin adapters over chat_service."""

import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from conversation_to_memory.bot import chat_service, states

logger = logging.getLogger(__name__)


def _user_id(update: Update) -> str:
    user = update.effective_user
    return str(user.id if user else 0)


async def _reply_result(
    update: Update,
    result: chat_service.ChatTurnResult,
) -> int:
    for message in result.messages:
        if result.parse_mode:
            await update.message.reply_text(message, parse_mode=result.parse_mode)
        else:
            await update.message.reply_text(message)
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
        await update.message.reply_text(message)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    result = chat_service.handle_cancel(_user_id(update), context.user_data)
    return await _reply_result(update, result)
