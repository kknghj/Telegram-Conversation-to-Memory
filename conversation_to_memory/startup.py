"""Startup validation and connection checks for production deployment."""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING

from app.draft_storage import (
    DRAFT_STORAGE_BACKEND_SUPABASE,
    get_draft_storage_backend_name,
    get_drafts_table_name,
    validate_draft_storage_backend,
    verify_supabase_drafts_connection,
)
from conversation_to_memory.storage.factory import (
    STORAGE_BACKEND_SUPABASE,
    get_storage_backend_name,
    validate_storage_backend,
)

if TYPE_CHECKING:
    from telegram.ext import Application

logger = logging.getLogger(__name__)


class StartupError(Exception):
    """Fatal startup misconfiguration or connectivity failure."""


def check_required_env() -> None:
    missing = []
    if not os.getenv("TELEGRAM_BOT_TOKEN", "").strip():
        missing.append("TELEGRAM_BOT_TOKEN")
    if not os.getenv("OPENAI_API_KEY", "").strip():
        missing.append("OPENAI_API_KEY")
    if missing:
        raise StartupError(f"필수 환경변수 누락: {', '.join(missing)}")


def check_supabase_env() -> None:
    missing = []
    if not os.getenv("SUPABASE_URL", "").strip():
        missing.append("SUPABASE_URL")
    if not os.getenv("SUPABASE_SECRET_KEY", "").strip():
        missing.append("SUPABASE_SECRET_KEY")
    if missing:
        raise StartupError(
            "STORAGE_BACKEND=supabase이지만 다음 환경변수가 누락되었습니다: "
            + ", ".join(missing)
        )


def check_supabase_connection() -> None:
    from conversation_to_memory.storage.supabase import (
        SupabaseStorageError,
        get_memories_table_name,
        verify_connection,
    )

    table = get_memories_table_name()
    try:
        verify_connection()
    except SupabaseStorageError as exc:
        raise StartupError(f"Supabase 연결 실패 (table={table}): {exc}") from exc


def check_supabase_drafts_connection() -> None:
    from app.draft_storage import SupabaseDraftStorageError

    table = get_drafts_table_name()
    try:
        verify_supabase_drafts_connection()
    except SupabaseDraftStorageError as exc:
        raise StartupError(f"Supabase drafts 연결 실패 (table={table}): {exc}") from exc


async def log_telegram_bot_ready(app: Application) -> None:
    """Log bot identity after Application.initialize() (same event loop as polling)."""
    bot = app.bot
    username = bot.username or "(username 없음)"
    logger.info("Telegram Bot 연결 성공 (@%s, id=%s)", username, bot.id)


def log_startup_banner() -> str:
    backend = get_storage_backend_name()
    draft_backend = get_draft_storage_backend_name()
    model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna").strip() or "gpt-5.6-luna"
    logger.info("Memory Archive Bot 시작")
    logger.info("Storage Backend: %s", backend)
    logger.info("Draft Storage Backend: %s", draft_backend)
    logger.info("OpenAI Model: %s", model)
    return backend


def run_pre_build_checks() -> str:
    """Validate env and storage before Application is built."""
    validate_storage_backend()
    validate_draft_storage_backend()
    check_required_env()

    backend = log_startup_banner()
    draft_backend = get_draft_storage_backend_name()

    if backend == STORAGE_BACKEND_SUPABASE or draft_backend == DRAFT_STORAGE_BACKEND_SUPABASE:
        check_supabase_env()

    if backend == STORAGE_BACKEND_SUPABASE:
        check_supabase_connection()
        from conversation_to_memory.storage.supabase import get_memories_table_name

        logger.info("Supabase 연결 성공 (table=%s)", get_memories_table_name())
    else:
        logger.info("Supabase 연결 확인 건너뜀 (STORAGE_BACKEND=%s)", backend)

    if draft_backend == DRAFT_STORAGE_BACKEND_SUPABASE:
        check_supabase_drafts_connection()
        logger.info("Supabase drafts 연결 성공 (table=%s)", get_drafts_table_name())
    else:
        logger.info("Supabase drafts 연결 확인 건너뜀 (DRAFT_STORAGE_BACKEND=%s)", draft_backend)

    return backend


def exit_on_startup_error(exc: Exception) -> None:
    logger.error("%s", exc)
    sys.exit(1)
