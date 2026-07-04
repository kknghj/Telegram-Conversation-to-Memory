"""Conversation-to-Memory MVP entry point."""

import logging
import os
import signal
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


def main() -> None:
    if _is_truthy(os.getenv("TELEGRAM_OFFLINE_MODE")):
        from dev_chat import run_dev_chat

        logger.info("TELEGRAM_OFFLINE_MODE=true — 개발 모드로 실행합니다.")
        run_dev_chat()
        return

    from telegram.ext import (
        ApplicationBuilder,
        CommandHandler,
        ContextTypes,
        ConversationHandler,
        MessageHandler,
        filters,
    )

    from conversation_to_memory.bot import handlers, states
    from conversation_to_memory.startup import (
        StartupError,
        exit_on_startup_error,
        log_telegram_bot_ready,
        run_pre_build_checks,
    )

    try:
        run_pre_build_checks()
    except StartupError as exc:
        exit_on_startup_error(exc)

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

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error("Update 처리 중 오류", exc_info=context.error)

    async def on_init(application: object) -> None:
        await log_telegram_bot_ready(application)

    async def on_shutdown(_application: object) -> None:
        logger.info("Polling 종료 — Bot을 안전하게 중지합니다.")

    app = (
        ApplicationBuilder()
        .token(token)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(10.0)
        .get_updates_connect_timeout(30.0)
        .get_updates_read_timeout(30.0)
        .post_init(on_init)
        .post_shutdown(on_shutdown)
        .build()
    )
    app.add_error_handler(error_handler)
    app.add_handler(conv_handler)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.route_message)
    )

    stop_signals = (signal.SIGINT, signal.SIGTERM)
    logger.info(
        "Telegram Polling 시작 (stop_signals=%s)",
        [signal.Signals(s).name for s in stop_signals],
    )

    try:
        app.run_polling(stop_signals=stop_signals)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt 수신 — Bot을 안전하게 중지합니다.")
    except Exception as exc:
        exc_name = type(exc).__module__ + "." + type(exc).__name__
        if exc_name.startswith("telegram."):
            logger.error("Telegram Bot 시작 실패: %s", exc)
            sys.exit(1)
        raise


if __name__ == "__main__":
    main()
