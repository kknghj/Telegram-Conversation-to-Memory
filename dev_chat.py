"""Terminal-based dev chat — no Telegram API required."""

from __future__ import annotations

import logging
import os
import sys
from argparse import ArgumentParser

from dotenv import load_dotenv

from app import database as db
from conversation_to_memory.bot import chat_service
from conversation_to_memory.replay import format_run_result, run_replay

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DEFAULT_DEV_USER_ID = "dev-user"
DEFAULT_REPLAY_USER_ID = "replay-user"


def _validate_env() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("필수 환경변수 누락: OPENAI_API_KEY")
        sys.exit(1)


def _print_result(result: chat_service.ChatTurnResult, user_data: dict | None = None) -> None:
    for message in result.messages:
        print(f"\n봇: {message}\n")

    if user_data is not None:
        trace_output = chat_service.format_decision_trace_output(user_data)
        if trace_output:
            print(trace_output)
            print()


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
    _print_result(start_result, user_data)
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
        _print_result(result, user_data)
        state = result.state


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Memory Archive dev chat and transcript replay")
    parser.add_argument("--user-id", default=None, help="User id for dev chat or replay persistence")
    parser.add_argument("--replay", help="Path to .txt or .json replay input")

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview replay drafts without final save")
    mode.add_argument(
        "--interactive-review",
        action="store_true",
        help="Review each memo in the terminal and choose save, skip, or exit",
    )
    mode.add_argument("--save-final", action="store_true", help="Save replay output to the normal memory store")

    parser.add_argument("--force", action="store_true", help="Allow duplicate replay_hash final saves")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.replay:
        run_dev_chat(args.user_id)
        return

    _validate_env()
    mode = "dry-run"
    if args.interactive_review:
        mode = "interactive-review"
    elif args.save_final:
        mode = "save-final"

    result = run_replay(
        args.replay,
        mode=mode,
        user_id=args.user_id or os.getenv("DEV_CHAT_REPLAY_USER_ID", DEFAULT_REPLAY_USER_ID),
        force=args.force,
    )
    print(format_run_result(result))


if __name__ == "__main__":
    main()
