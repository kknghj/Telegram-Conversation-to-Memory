"""Conversation-to-Memory MVP entry point."""

import logging
import os
import sys

from dotenv import load_dotenv

from app import database as db

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _validate_env() -> None:
    missing = []
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        missing.append("TELEGRAM_BOT_TOKEN")
    if not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if missing:
        logger.error("필수 환경변수 누락: %s", ", ".join(missing))
        sys.exit(1)


def main() -> None:
    if _is_truthy(os.getenv("TELEGRAM_OFFLINE_MODE")):
        from dev_chat import run_dev_chat

        logger.info("TELEGRAM_OFFLINE_MODE=true — 개발 모드로 실행합니다.")
        run_dev_chat()
        return

    from telegram.ext import (
        ApplicationBuilder,
        CommandHandler,
        ConversationHandler,
        MessageHandler,
        filters,
    )

    from conversation_to_memory.bot import handlers, states

    _validate_env()
    db.init_db()
    cleanup_result = db.cleanup_drafts()
    logger.info("Draft cleanup: %s", cleanup_result)

    token = os.getenv("TELEGRAM_BOT_TOKEN")

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", handlers.start_command),
            MessageHandler(filters.Regex("^기록\\s*시작$"), handlers.begin_recording),
            MessageHandler(
                filters.Regex("^(수정|이전 기록 수정|취소한 기록 수정)$"),
                handlers.edit_cancelled_draft,
            ),
        ],
        states={
            states.RESUME_CHOICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_resume_choice),
            ],
            states.RECORDING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_recording),
            ],
            states.FOLLOWUP: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_followup),
            ],
            states.REVIEW: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_review),
            ],
            states.EDIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_edit),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", handlers.cancel_command),
            MessageHandler(filters.Regex("^기록\\s*시작$"), handlers.begin_recording),
        ],
        name="memory_session",
    )

    app = ApplicationBuilder().token(token).build()
    app.add_handler(conv_handler)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.route_message)
    )

    logger.info("Memory Archive bot 시작")
    app.run_polling()


if __name__ == "__main__":
    main()
