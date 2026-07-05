"""Tests for terminal dev chat flow (no Telegram API)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app import database as db
from conversation_to_memory.bot import chat_service, session, states


@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "memory_archive.db"
    db.init_db(db_path)
    return db_path


SAMPLE_DRAFT = {
    "topic": "민원 전화",
    "event_summary": "전화 대기 시간이 힘들었다",
    "user_emotions": ["힘듦"],
    "memory_candidate": "민원 전화 경험",
    "needs_followup": False,
    "followup_question": "",
}


def _dispatch(user_id: str, user_data: dict, text: str, state: int = chat_service.IDLE):
    with patch(
        "conversation_to_memory.bot.chat_service.memory_service.analyze_recording",
        return_value=SAMPLE_DRAFT,
    ):
        return chat_service.dispatch_message(user_id, user_data, text, state=state)


class TestDevChatFlow:
    def test_start_shows_welcome(self):
        user_data = {}
        result = chat_service.handle_start(user_data)

        assert result.state == chat_service.IDLE
        assert "기억 아카이브 봇" in result.messages[0]
        assert "기록 시작" in result.messages[0]

    def test_begin_recording_enters_recording_state(self, temp_db):
        user_id = "dev-user"
        user_data = {}

        with patch("conversation_to_memory.bot.chat_service.db.DEFAULT_DB_PATH", temp_db):
            result = _dispatch(user_id, user_data, "기록 시작")

        assert result.state == states.RECORDING
        assert "있는 그대로 기록해 주세요" in result.messages[0]

    def test_recording_then_summary_moves_to_review(self, temp_db):
        user_id = "dev-user"
        user_data = {}

        with patch("conversation_to_memory.bot.chat_service.db.DEFAULT_DB_PATH", temp_db):
            begin = _dispatch(user_id, user_data, "기록 시작")
            record = _dispatch(
                user_id,
                user_data,
                "오늘 회의가 길었다",
                state=begin.state,
            )
            summary = _dispatch(user_id, user_data, "요약", state=record.state)

        assert record.state == states.RECORDING
        assert summary.state == states.REVIEW
        assert SAMPLE_DRAFT["event_summary"] in summary.messages[0]

    def test_review_cancel_persists_draft(self, temp_db):
        user_id = "dev-user"
        user_data = {}
        session.set_draft(user_data, SAMPLE_DRAFT)
        session.ensure_session(user_data)

        with patch("conversation_to_memory.bot.chat_service.db.DEFAULT_DB_PATH", temp_db):
            result = chat_service.handle_review(user_id, user_data, "취소")

        assert result.state == chat_service.IDLE
        assert "저장을 취소했습니다" in result.messages[0]
        assert db.get_latest_cancelled_draft(user_id, db_path=temp_db) is not None

    def test_edit_cancelled_draft_via_dispatch(self, temp_db):
        user_id = "dev-user"
        user_data = {}

        db.save_cancelled_draft(
            user_id,
            draft=SAMPLE_DRAFT,
            user_texts=["민원 전화가 왔다"],
            db_path=temp_db,
        )

        with patch("conversation_to_memory.bot.chat_service.db.DEFAULT_DB_PATH", temp_db):
            result = _dispatch(user_id, user_data, "수정")

        assert result.state == states.REVIEW
        assert "취소했던 초안을 불러왔습니다" in result.messages[0]
        assert session.get_draft(user_data) == SAMPLE_DRAFT

    def test_save_draft_resets_session(self, temp_db, tmp_path):
        user_id = "dev-user"
        user_data = {}
        session.ensure_session(user_data)
        session.set_draft(user_data, SAMPLE_DRAFT)

        with patch("conversation_to_memory.bot.chat_service.db.DEFAULT_DB_PATH", temp_db):
            with patch(
                "conversation_to_memory.bot.chat_service.storage.save",
                return_value=str(tmp_path / "saved.json"),
            ):
                result = chat_service.handle_review(user_id, user_data, "저장")

        assert result.state == chat_service.IDLE
        assert "기억이 저장되었습니다" in result.messages[0]
        assert session.get_draft(user_data) is None

    def test_save_draft_reports_saved_when_draft_mark_fails(self, tmp_path):
        user_id = "dev-user"
        user_data = {}
        session.ensure_session(user_data)
        session.set_draft(user_data, SAMPLE_DRAFT)

        with patch(
            "conversation_to_memory.bot.chat_service.storage.save",
            return_value=str(tmp_path / "saved.json"),
        ):
            with patch(
                "conversation_to_memory.bot.chat_service.db.mark_draft_saved",
                side_effect=RuntimeError("draft backend down"),
            ):
                result = chat_service.handle_review(user_id, user_data, "저장")

        assert result.state == chat_service.IDLE
        assert "기억이 저장되었습니다" in result.messages[0]
        assert "임시 초안 상태 업데이트에 실패" in result.messages[0]
        assert session.get_draft(user_data) is None

    def test_save_draft_failure_keeps_review_state_and_draft(self):
        user_id = "dev-user"
        user_data = {}
        session.ensure_session(user_data)
        session.set_draft(user_data, SAMPLE_DRAFT)

        with patch(
            "conversation_to_memory.bot.chat_service.storage.save",
            side_effect=RuntimeError("memory backend down"),
        ):
            with patch(
                "conversation_to_memory.bot.chat_service.db.mark_draft_saved"
            ) as mark_saved:
                result = chat_service.handle_review(user_id, user_data, "저장")

        assert result.state == states.REVIEW
        assert "저장 실패: memory backend down" in result.messages[0]
        mark_saved.assert_not_called()
        assert session.get_draft(user_data) == SAMPLE_DRAFT

    def test_resume_choice_after_recent_cancel(self, temp_db):
        user_id = "dev-user"
        user_data = {}

        db.save_cancelled_draft(
            user_id,
            draft=SAMPLE_DRAFT,
            user_texts=["테스트"],
            db_path=temp_db,
        )

        with patch("conversation_to_memory.bot.chat_service.db.DEFAULT_DB_PATH", temp_db):
            begin = _dispatch(user_id, user_data, "기록 시작")

        assert begin.state == states.RESUME_CHOICE
        assert "이전에 저장하지 않은 기록이 있습니다" in begin.messages[0]
