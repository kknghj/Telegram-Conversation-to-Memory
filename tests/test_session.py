"""Tests for session state management."""

from conversation_to_memory.bot import session


def test_cancel_preserves_draft_as_cancelled():
    user_data = {}
    session.ensure_session(user_data)
    user_data[session.KEY_CURRENT_SESSION]["user_texts"] = ["민원 전화 힘들다"]
    draft = {"topic": "테스트", "event_summary": "요약"}
    session.set_draft(user_data, draft)

    session.cancel_current_draft(user_data)

    assert session.get_draft(user_data) is None
    assert session.get_cancelled_draft(user_data) == draft
    assert len(session.get_recent_context(user_data)) == 1
    assert session.get_recent_context(user_data)[0]["user_texts"] == ["민원 전화 힘들다"]


def test_restore_cancelled_to_current():
    user_data = {session.KEY_CANCELLED_DRAFT: {"topic": "이전"}}
    restored = session.restore_cancelled_to_current(user_data)

    assert restored == {"topic": "이전"}
    assert session.get_draft(user_data) == {"topic": "이전"}
    assert session.get_cancelled_draft(user_data) is None


def test_relates_to_cancellation_detects_keywords():
    user_data = {
        session.KEY_CANCELLATION_REASON: "지나치게 긍정적으로 왜곡하지 말고",
        session.KEY_CANCELLED_DRAFT: {"topic": "x"},
    }
    assert session.relates_to_cancellation("있는 그대로 받아들여줘", user_data) is True


def test_clear_cancelled_draft():
    user_data = {
        session.KEY_CANCELLED_DRAFT: {"topic": "x"},
        session.KEY_CANCELLATION_REASON: "reason",
    }
    session.clear_cancelled_draft(user_data)
    assert not session.has_cancelled_draft(user_data)
    assert session.KEY_CANCELLATION_REASON not in user_data
