"""Admin scenario tests for cancelled draft SQLite persistence."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import database as db
from conversation_to_memory.bot import session, states
from conversation_to_memory.bot.handlers import (
    begin_recording,
    edit_cancelled_draft,
)


@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "memory_archive.db"
    db.init_db(db_path)
    return db_path


def _make_update(user_id: int = 42, text: str = "기록 시작"):
    update = MagicMock()
    update.effective_user = MagicMock(id=user_id)
    update.message = MagicMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def _make_context(user_data=None):
    ctx = MagicMock()
    ctx.user_data = user_data if user_data is not None else {}
    return ctx


def _set_draft_updated_at(db_path: Path, draft_id: int, days_ago: int) -> None:
    ts = (
        datetime.now(timezone.utc) - timedelta(days=days_ago)
    ).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE drafts SET updated_at = ? WHERE id = ?",
            (ts, draft_id),
        )
        conn.commit()


SAMPLE_DRAFT = {
    "topic": "민원 전화",
    "event_summary": "전화 대기 시간이 힘들었다",
    "user_emotions": ["힘듦"],
    "memory_candidate": "민원 전화 경험",
}
SAMPLE_TEXTS = ["민원 전화가 왔는데 기다리는 시간이 힘들었다"]
SAMPLE_CONVERSATION = [{"role": "user", "content": SAMPLE_TEXTS[0]}]


class TestScenarioA:
    """기록 시작 → 대화 → 취소 → 서버 재시작 → 수정 → 취소 초안 복구."""

    def test_cancelled_draft_survives_restart(self, temp_db):
        user_id = "user-a"

        draft_id = db.save_cancelled_draft(
            user_id,
            draft=SAMPLE_DRAFT,
            user_texts=SAMPLE_TEXTS,
            conversation=SAMPLE_CONVERSATION,
            cancellation_reason="취소",
            db_path=temp_db,
        )

        # 서버 재시작: 메모리 세션 비움
        ctx = _make_context({})

        with patch("conversation_to_memory.bot.handlers.db.DEFAULT_DB_PATH", temp_db):
            persisted = db.get_latest_cancelled_draft(user_id, db_path=temp_db)

        assert persisted is not None
        assert persisted["id"] == draft_id
        assert persisted["draft"]["event_summary"] == SAMPLE_DRAFT["event_summary"]
        assert persisted["user_texts"] == SAMPLE_TEXTS

        session.load_cancelled_draft_from_db(ctx, persisted)
        restored = session.restore_cancelled_to_current(ctx)

        assert restored == SAMPLE_DRAFT
        assert session.get_session(ctx)["user_texts"] == SAMPLE_TEXTS

    def test_edit_after_restart_loads_draft(self, temp_db):
        user_id = "user-a"

        db.save_cancelled_draft(
            user_id,
            draft=SAMPLE_DRAFT,
            user_texts=SAMPLE_TEXTS,
            conversation=SAMPLE_CONVERSATION,
            db_path=temp_db,
        )

        update = _make_update(user_id=42, text="수정")
        ctx = _make_context({})

        with patch("conversation_to_memory.bot.handlers.db.DEFAULT_DB_PATH", temp_db):
            with patch(
                "conversation_to_memory.bot.handlers._user_id",
                return_value=user_id,
            ):
                result = asyncio.run(edit_cancelled_draft(update, ctx))

        assert result == states.REVIEW
        assert session.get_draft(ctx) == SAMPLE_DRAFT
        update.message.reply_text.assert_awaited()
        reply = update.message.reply_text.await_args[0][0]
        assert "취소했던 초안을 불러왔습니다" in reply
        assert SAMPLE_DRAFT["event_summary"] in reply


class TestScenarioB:
    """기록 시작 → 취소 → 기록 시작 → 이전 기록 이어쓰기 여부 질문."""

    def test_has_recent_cancelled_draft_within_24h(self, temp_db):
        user_id = "user-b"
        db.save_cancelled_draft(
            user_id,
            draft=SAMPLE_DRAFT,
            user_texts=SAMPLE_TEXTS,
            db_path=temp_db,
        )

        assert db.has_recent_cancelled_draft(user_id, db_path=temp_db) is True

    def test_begin_recording_prompts_resume_choice(self, temp_db):
        user_id = "user-b"
        db.save_cancelled_draft(
            user_id,
            draft=SAMPLE_DRAFT,
            user_texts=SAMPLE_TEXTS,
            db_path=temp_db,
        )

        update = _make_update(user_id=99, text="기록 시작")
        ctx = _make_context({})

        with patch("conversation_to_memory.bot.handlers.db.DEFAULT_DB_PATH", temp_db):
            with patch(
                "conversation_to_memory.bot.handlers._user_id",
                return_value=user_id,
            ):
                result = asyncio.run(begin_recording(update, ctx))

        assert result == states.RESUME_CHOICE
        update.message.reply_text.assert_awaited()
        reply = update.message.reply_text.await_args[0][0]
        assert "이전에 저장하지 않은 기록이 있습니다" in reply
        assert "1. 이전 기록 이어쓰기" in reply
        assert "2. 새 기록 시작" in reply


class TestScenarioC:
    """취소 후 31일 경과 → 자동 삭제."""

    def test_old_cancelled_draft_is_deleted(self, temp_db):
        user_id = "user-c"
        draft_id = db.save_cancelled_draft(
            user_id,
            draft=SAMPLE_DRAFT,
            user_texts=SAMPLE_TEXTS,
            db_path=temp_db,
        )

        _set_draft_updated_at(temp_db, draft_id, days_ago=31)

        result = db.cleanup_drafts(db_path=temp_db)

        assert result["deleted_cancelled"] >= 1
        assert db.get_latest_cancelled_draft(user_id, db_path=temp_db) is None

    def test_active_draft_converted_after_7_days(self, temp_db):
        user_id = "user-c2"
        draft_id = db.save_active_draft(
            user_id,
            user_texts=["진행 중"],
            db_path=temp_db,
        )
        _set_draft_updated_at(temp_db, draft_id, days_ago=8)

        result = db.cleanup_drafts(db_path=temp_db)

        assert result["converted_active"] >= 1
        with sqlite3.connect(temp_db) as conn:
            row = conn.execute(
                "SELECT status FROM drafts WHERE id = ?", (draft_id,)
            ).fetchone()
        assert row[0] == db.DRAFT_STATUS_CANCELLED


class TestDatabaseInit:
    def test_init_creates_all_tables(self, temp_db):
        with sqlite3.connect(temp_db) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        assert {"drafts", "memories", "sessions"}.issubset(tables)
