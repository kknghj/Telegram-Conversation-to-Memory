"""Terminal-based dev chat — no Telegram API required."""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv

from app import database as db
from conversation_to_memory.bot import chat_service

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DEFAULT_DEV_USER_ID = "dev-user"


def _validate_env() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("필수 환경변수 누락: OPENAI_API_KEY")
        sys.exit(1)


def _print_result(result: chat_service.ChatTurnResult) -> None:
    for message in result.messages:
        print(f"\n봇: {message}\n")


def run_dev_chat(user_id: str | None = None) -> None:
    """Run an interactive terminal chat loop."""
    _validate_env()
    db.init_db()
    cleanup_result = db.cleanup_drafts()
    logger.info("Draft cleanup: %s", cleanup_result)

    resolved_user_id = user_id or os.getenv("DEV_CHAT_USER_ID", DEFAULT_DEV_USER_ID)
    user_data: dict = {}
    state = chat_service.IDLE

    print("=== Memory Archive 개발 모드 (Telegram API 미사용) ===")
    print(f"사용자 ID: {resolved_user_id}")
    print("명령: /start, 기록 시작, 요약, 저장, 취소, 수정, /quit")
    print("종료: /quit 또는 Ctrl+C\n")

    start_result = chat_service.handle_start(user_data)
    _print_result(start_result)
    state = start_result.state

    while True:
        try:
            text = input("나: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n개발 모드 종료.")
            break

        if not text:
            continue

        result = chat_service.dispatch_message(
            resolved_user_id,
            user_data,
            text,
            state=state,
        )
        _print_result(result)
        state = result.state


def main() -> None:
    run_dev_chat()


if __name__ == "__main__":
    main()
