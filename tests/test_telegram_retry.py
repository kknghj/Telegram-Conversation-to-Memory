"""Tests for Telegram send retry logic."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import TimedOut

from conversation_to_memory.bot.handlers import _reply_text_with_retry


def test_reply_text_retries_on_timeout():
    message = MagicMock()
    message.reply_text = AsyncMock(side_effect=[TimedOut("timeout"), None])

    with patch("conversation_to_memory.bot.handlers.asyncio.sleep", new_callable=AsyncMock):
        asyncio.run(_reply_text_with_retry(message, "hello"))

    assert message.reply_text.await_count == 2


def test_reply_text_raises_after_max_retries():
    message = MagicMock()
    message.reply_text = AsyncMock(side_effect=TimedOut("timeout"))

    with patch("conversation_to_memory.bot.handlers.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(TimedOut):
            asyncio.run(_reply_text_with_retry(message, "hello"))

    assert message.reply_text.await_count == 3
