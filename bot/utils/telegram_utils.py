"""
Telegram Bot utility functions.
"""
import logging
import time
from asyncio import Semaphore, sleep
from typing import Any
from telegram import CallbackQuery
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def safe_answer_callback_query(query: CallbackQuery, text: str = "", show_alert: bool = False):
    """
    Safely answer a callback query, ignoring timeout errors.

    When a callback query is too old (> ~30 seconds), Telegram will reject the answer.
    This is not a critical error, so we catch and log it.
    """
    try:
        await query.answer(text, show_alert=show_alert)
    except BadRequest as e:
        if "query is too old" in str(e).lower() or "timeout expired" in str(e).lower():
            # Query expired, not a problem
            logger.debug(f"Callback query expired (expected for slow operations)")
        else:
            # Other BadRequest, re-raise
            raise


class TelegramRateLimiter:
    """
    Lightweight rate limiter for Telegram API.
    Prevents hitting 30 messages/second global limit.
    """

    def __init__(self, max_rate: int = 25):
        """
        Args:
            max_rate: Maximum messages per second (default 25,留5条缓冲)
        """
        self.max_rate = max_rate
        self.semaphore = Semaphore(max_rate)  # Limit concurrent sends
        self.sent_times = []  # Sliding window: recent send timestamps

    async def acquire(self):
        """Acquire permission to send a message."""
        async with self.semaphore:
            now = time.time()

            # Clean up old entries (>1 second ago)
            self.sent_times = [t for t in self.sent_times if now - t < 1.0]

            # If we've sent max_rate messages in the last second
            if len(self.sent_times) >= self.max_rate:
                # Calculate wait time
                oldest = self.sent_times[0]
                wait_time = 1.0 - (now - oldest) + 0.05  # Add 50ms buffer
                if wait_time > 0:
                    await sleep(wait_time)
                    now = time.time()

            # Record this send time
            self.sent_times.append(now)


# Global rate limiter instance
_tg_rate_limiter = TelegramRateLimiter(max_rate=25)


async def send_message_safe(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    **kwargs: Any
):
    """
    Rate-limited wrapper for context.bot.send_message.

    Automatically throttles to avoid Telegram API flood limits (30 msg/s).

    Args:
        context: Telegram context
        chat_id: Chat ID to send to
        text: Message text
        **kwargs: Additional arguments passed to send_message

    Returns:
        Message object from send_message
    """
    await _tg_rate_limiter.acquire()
    return await context.bot.send_message(chat_id, text, **kwargs)
