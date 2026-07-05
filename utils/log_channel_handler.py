"""Custom logging handler that forwards all logs to a Telegram channel."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyrogram import Client


class TelegramLogHandler(logging.Handler):
    """Asynchronous logging handler that queues all log messages for delivery to a Telegram channel."""

    def __init__(self, client: Client | None = None):
        super().__init__(level=logging.DEBUG)
        self._client = client
        self._channel_id: int | None = None
        self._enabled = False

    def set_client(self, client: Client) -> None:
        """Set the Pyrogram client instance."""
        self._client = client

    async def _update_settings(self) -> None:
        """Update channel ID and enabled status from database."""
        from services import get_db

        try:
            db = get_db()
            channel_id = await db.get_setting("log_channel_id", "")
            enabled = await db.get_setting("log_channel_enabled", "0") == "1"
        except Exception:
            return

        if channel_id and enabled:
            try:
                self._channel_id = int(channel_id)
                self._enabled = True
            except ValueError:
                self._channel_id = None
                self._enabled = False
        else:
            self._channel_id = None
            self._enabled = False

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record by sending it to the configured channel."""
        if not self._client:
            return

        if not self._enabled:
            try:
                loop = asyncio.get_running_loop()
                asyncio.ensure_future(self._update_settings())
            except RuntimeError:
                return

        if not self._enabled or not self._channel_id:
            return

        msg = self.format(record)

        # Skip if message is too long
        if len(msg) > 4000:
            msg = msg[:4000] + "..."

        # Schedule async send
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                asyncio.ensure_future(self._send_message(msg))
        except RuntimeError:
            pass  # No running loop (e.g., during shutdown)

    async def _send_message(self, msg: str) -> None:
        """Send message to the configured channel."""
        try:
            if self._enabled and self._channel_id:
                await self._client.send_message(
                    chat_id=self._channel_id,
                    text=msg,
                    disable_web_page_preview=True,
                )
        except Exception:
            pass  # Silently fail to avoid infinite recursion
