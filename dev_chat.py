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


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Memory Archive dev chat and transcript replay")
    parser.add_argument("--user-id", default=None, help="User id for dev chat or replay persistence")
    parser.add_argument("--replay", help="Path to .txt or .json replay input")

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview replay drafts without final save")
    mode.add_argument("--save-draft", action="store_true", help="Write replay drafts under data/replay_outputs/drafts")
    mode.add_argument("--save-final", action="store_true", help="Save replay output to the normal memory store")

    parser.add_argument("--force", action="store_true", help="Allow duplicate replay_hash final saves")
    parser.add_argument(
        "--followup-mode",
        choices=("none", "generate-only"),
        default="none",
        help="How replay handles generated follow-up questions",
    )
    parser.add_argument("--no-followup", action="store_true", help="Alias for --followup-mode none")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.replay:
        run_dev_chat(args.user_id)
        return

    _validate_env()
    mode = "dry-run"
    if args.save_draft:
        mode = "save-draft"
    elif args.save_final:
        mode = "save-final"

    followup_mode = "none" if args.no_followup else args.followup_mode
    result = run_replay(
        args.replay,
        mode=mode,
        user_id=args.user_id or os.getenv("DEV_CHAT_REPLAY_USER_ID", DEFAULT_REPLAY_USER_ID),
        force=args.force,
        followup_mode=followup_mode,
    )
    print(format_run_result(result))


if __name__ == "__main__":
    main()
