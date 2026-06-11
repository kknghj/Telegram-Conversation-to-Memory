"""Tests for session state management."""

from unittest.mock import MagicMock

from conversation_to_memory.bot import session


def _make_context(user_data=None):
    ctx = MagicMock()
    ctx.user_data = user_data if user_data is not None else {}
    return ctx


def test_cancel_preserves_draft_as_cancelled():
    ctx = _make_context()
    session.ensure_session(ctx)
    ctx.user_data[session.KEY_CURRENT_SESSION]["user_texts"] = ["민원 전화 힘들다"]
    draft = {"topic": "테스트", "event_summary": "요약"}
    session.set_draft(ctx, draft)

    session.cancel_current_draft(ctx)

    assert session.get_draft(ctx) is None
    assert session.get_cancelled_draft(ctx) == draft
    assert len(session.get_recent_context(ctx)) == 1
    assert session.get_recent_context(ctx)[0]["user_texts"] == ["민원 전화 힘들다"]


def test_restore_cancelled_to_current():
    ctx = _make_context({session.KEY_CANCELLED_DRAFT: {"topic": "이전"}})
    restored = session.restore_cancelled_to_current(ctx)

    assert restored == {"topic": "이전"}
    assert session.get_draft(ctx) == {"topic": "이전"}
    assert session.get_cancelled_draft(ctx) is None


def test_relates_to_cancellation_detects_keywords():
    ctx = _make_context(
        {
            session.KEY_CANCELLATION_REASON: "지나치게 긍정적으로 왜곡하지 말고",
            session.KEY_CANCELLED_DRAFT: {"topic": "x"},
        }
    )
    assert session.relates_to_cancellation("있는 그대로 받아들여줘", ctx) is True


def test_clear_cancelled_draft():
    ctx = _make_context(
        {
            session.KEY_CANCELLED_DRAFT: {"topic": "x"},
            session.KEY_CANCELLATION_REASON: "reason",
        }
    )
    session.clear_cancelled_draft(ctx)
    assert not session.has_cancelled_draft(ctx)
    assert session.KEY_CANCELLATION_REASON not in ctx.user_data
