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
        # Tracks whether settings have been successfully loaded at least once.
        self._loaded = False
        # Guards against scheduling multiple concurrent reloads from emit().
        self._reload_pending = False
        # One-shot flag so a persistent send failure is logged to stderr once
        # (visible in `docker compose logs`) without spamming on every record.
        self._send_failed = False

    def set_client(self, client: Client) -> None:
        """Set the Pyrogram client instance."""
        self._client = client

    async def reload(self) -> bool:
        """Load (or refresh) channel ID and enabled status from the database.

        Returns True if settings were successfully loaded. Failures are logged
        to stderr (via the module logger) rather than swallowed silently, so
        misconfiguration is visible. This method is safe to call repeatedly.
        """
        from services import get_db

        try:
            db = get_db()
            channel_id = await db.get_setting("log_channel_id", "")
            enabled = await db.get_setting("log_channel_enabled", "0") == "1"
        except Exception as exc:
            # Don't mark as loaded — emit() will keep retrying.
            logging.getLogger(__name__).warning(
                "log_channel.reload_failed: %s", exc, exc_info=False
            )
            return False

        if channel_id and enabled:
            try:
                self._channel_id = int(channel_id)
                self._enabled = True
            except (TypeError, ValueError):
                self._channel_id = None
                self._enabled = False
                logging.getLogger(__name__).warning(
                    "log_channel.invalid_channel_id: %r", channel_id
                )
        else:
            self._channel_id = None
            self._enabled = False

        self._loaded = True
        # Re-arm the one-shot send-failure warning so a settings change gets
        # a fresh chance to report problems.
        self._send_failed = False
        return True

    async def ensure_resolved(self) -> None:
        """Re-resolve the log channel by username so its access_hash is cached
        in the Pyrogram session.

        Required after a fresh start (e.g. Docker container recreation) where
        the session no longer holds the channel's access_hash. Pyrogram needs
        the access_hash to send to a channel by its numeric marked ID; without
        it, `send_message(chat_id=<marked_id>)` raises PeerIdInvalidError.

        The channel username is stored at configuration time
        (see handlers/admin/log_channel.py). If absent (e.g. private channel
        or older config), this is a no-op and delivery relies on the persisted
        session instead.

        If the channel is no longer accessible (deleted, bot removed, etc.),
        the saved configuration is cleared and the admin is notified so they
        can set a new log channel.
        """
        if not self._client:
            return
        from services import get_db

        try:
            db = get_db()
            username = await db.get_setting("log_channel_username", "")
        except Exception:
            return

        if not username:
            return

        try:
            await self._client.get_chat(f"@{username}")
        except Exception as exc:
            import sys
            print(
                f"[log_channel_handler] could not re-resolve channel "
                f"@{username}: {exc}",
                file=sys.stderr,
            )
            await self._clear_and_notify_admin(
                f"⚠️ کانال لاگ @{username} دیگر در دسترس نیست.\n"
                "لطفاً یک کانال لاگ جدید از پنل مدیریت تنظیم کنید."
            )

    def _schedule_reload(self) -> None:
        """Schedule an async reload from within sync emit() if one isn't pending."""
        if self._reload_pending:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # No running loop (e.g., during shutdown / before startup)
        self._reload_pending = True

        async def _do_reload() -> None:
            try:
                await self.reload()
            finally:
                self._reload_pending = False

        asyncio.create_task(_do_reload())

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record by sending it to the configured channel."""
        if not self._client:
            return

        # If settings haven't been loaded yet, kick off a lazy reload. The
        # current record is necessarily dropped (reload is async), but once the
        # reload completes subsequent records will flow.
        if not self._loaded:
            self._schedule_reload()

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
                asyncio.create_task(self._send_message(msg))
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
                self._send_failed = False
        except Exception as exc:
            # Do NOT use stdlib logging here — a failed send logged via stdlib
            # would re-trigger this handler and loop. print() to stderr is
            # captured by Docker's json-file log driver (visible in
            # `docker compose logs`) and cannot recurse. Suppressed after the
            # first failure to avoid spam; re-armed on success or reload().
            if not self._send_failed:
                self._send_failed = True
                import sys
                print(
                    f"[log_channel_handler] send failed "
                    f"(further failures suppressed): {exc}",
                    file=sys.stderr,
                )

            # Permanent channel errors → clear config and notify admin so
            # log sending can be reconfigured rather than failing forever.
            from pyrogram.errors import (
                ChannelInvalid,
                ChannelPrivate,
                ChatWriteForbiddenError,
                PeerIdInvalidError,
            )

            if isinstance(exc, (ChannelPrivate, ChannelInvalid, PeerIdInvalidError, ChatWriteForbiddenError)):
                await self._clear_and_notify_admin(
                    "⚠️ کانال لاگ دیگر در دسترس نیست.\n"
                    "لطفاً یک کانال لاگ جدید از پنل مدیریت تنظیم کنید."
                )

    async def _clear_and_notify_admin(self, reason: str) -> None:
        """Clear saved log channel config and send a DM to the admin."""
        from config import admin_ids
        from services import get_db

        self._channel_id = None
        self._enabled = False

        try:
            db = get_db()
            await db.set_setting("log_channel_id", "")
            await db.set_setting("log_channel_enabled", "0")
            await db.set_setting("log_channel_username", "")
        except Exception:
            pass

        # DM every configured admin so they know to reconfigure.
        if self._client:
            for admin_id in admin_ids():
                try:
                    await self._client.send_message(
                        chat_id=admin_id,
                        text=reason,
                    )
                except Exception:
                    pass


# ── Module-level singleton ──────────────────────────────────────────────────
# A single handler instance is shared between main.py (which attaches it to the
# root logger) and the admin handlers (which trigger reloads after settings
# change). Using functools.cache-style access keeps the wiring centralized.

_log_channel_handler: TelegramLogHandler | None = None


def get_log_channel_handler() -> TelegramLogHandler:
    """Return the shared TelegramLogHandler singleton."""
    global _log_channel_handler
    if _log_channel_handler is None:
        _log_channel_handler = TelegramLogHandler()
    return _log_channel_handler
