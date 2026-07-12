"""Start handler — /start, /cancel commands, and forced-join verification."""

from __future__ import annotations

import contextlib
import logging

from pyrogram import Client, enums, filters
from pyrogram.types import CallbackQuery, Message

import plugins.download_manager as download_manager
from config import is_admin
from models import ChannelRecord
from services import get_db
from strings import (
    DEFAULT_START_MESSAGE,
    MAINTENANCE,
    NO_ACTIVE_DL,
)
from utils.keyboards import join_keyboard, main_keyboard

logger = logging.getLogger(__name__)


async def _check_membership(client: Client, user_id: int) -> list[ChannelRecord]:
    """Return a list of mandatory-join channels the user has not joined."""
    db = get_db()
    not_joined: list[ChannelRecord] = []
    for channel in await db.get_channels():
        try:
            member = await client.get_chat_member(chat_id=channel.channel_id, user_id=user_id)
            if member.status not in (enums.ChatMemberStatus.MEMBER, enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER):
                not_joined.append(channel)
        except Exception:
            not_joined.append(channel)
    return not_joined


@Client.on_message(filters.command("start") & filters.private)
async def cmd_start(client: Client, message: Message) -> None:
    """Handle /start — register the user and display the main keyboard."""
    if not message.from_user:
        return
    user_id = message.from_user.id
    db = get_db()
    if not is_admin(user_id):
        if await db.get_setting("maintenance_mode") == "1":
            await message.reply_text(MAINTENANCE)
            return

    # Deep link: /start verify → show forced-join channels
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1] == "verify":
        not_joined = await _check_membership(client, user_id)
        if not_joined:
            kb = join_keyboard(not_joined)
            msg = await db.get_setting(
                "join_message",
                "سلام خوش اومدی🌹\n✨ برای استفاده از ربات، لطفاً ابتدا در کانال‌ها عضو شوید:",
            )
            await message.reply_text(msg, reply_markup=kb)
            return

    # Deep link: /start artist_trackname → search and download track
    if len(args) > 1 and args[1] != "verify":
        track_key = args[1]
        await _handle_track_deep_link(client, message, user_id, track_key)
        return

    db = get_db()
    await db.add_user(user_id, message.from_user.username)
    text = await db.get_setting("start_message") or DEFAULT_START_MESSAGE
    await message.reply_text(text=text, reply_markup=main_keyboard(is_admin(user_id)))
    logger.info("User %d started the bot", user_id)


async def _handle_track_deep_link(
    client: Client, message: Message, user_id: int, track_key: str
) -> None:
    """Search and download a track from a deep link key (artistname_trackname)."""
    import asyncio
    import contextlib

    from handlers.download import _download_single_track
    from plugins.spotdl import _ensure_spotdl_init
    from spotdl.utils.spotify import SpotifyClient
    from strings import RATE_LIMITED

    # Reconstruct search query: replace underscores with spaces
    query = track_key.replace("_", " ")

    status_msg = await message.reply_text("🔍 در حال جستجوی آهنگ...")

    try:
        _ensure_spotdl_init()
        spotify = SpotifyClient()
        loop = asyncio.get_running_loop()

        def _search_track():
            logger.info("Deep link search: q=%s", query)
            results = spotify.search(q=query, type="track", limit=5)
            items = results.get("tracks", {}).get("items", [])
            return items[0] if items else None

        track = await loop.run_in_executor(None, _search_track)

        if not track:
            logger.warning("Deep link track not found for query: %s", query)
            await status_msg.edit_text("❌ Track Not Found")
            return

        track_id = track.get("id")
        if not track_id:
            await status_msg.edit_text("❌ خطا در دریافت اطلاعات آهنگ.")
            return

        await status_msg.delete()
    except Exception as exc:
        logger.error("Deep link search failed: %s", exc)
        with contextlib.suppress(Exception):
            await status_msg.edit_text("❌ خطا در جستجوی آهنگ.")
        return

    # Enforce membership
    if not await enforce_membership(client, message):
        return

    # Rate limit
    from services import get_rate_limiter

    rate_limiter = get_rate_limiter()
    if not is_admin(user_id) and await rate_limiter.is_limited(user_id):
        window = await rate_limiter.window_seconds()
        await message.reply_text(RATE_LIMITED.format(window=window))
        return

    download_manager.clear_cancel_flag(user_id)
    task = asyncio.current_task()
    try:
        await _download_single_track(client, message, user_id, track_id, task)
    finally:
        if task:
            download_manager.unregister(user_id, task)


async def verify_join_callback(client: Client, callback_query: CallbackQuery) -> None:
    """Verify mandatory-join membership after the user presses the verify button."""
    user_id = callback_query.from_user.id
    not_joined = await _check_membership(client, user_id)
    if not_joined:
        await callback_query.answer("هنوز جوین نشدی که!")
        return
    await callback_query.answer()
    db = get_db()
    await db.add_user(user_id, callback_query.from_user.username)
    text = await db.get_setting("start_message") or DEFAULT_START_MESSAGE
    await callback_query.message.reply_text(
        text=text, reply_markup=main_keyboard(is_admin(user_id))
    )
    with contextlib.suppress(Exception):
        await callback_query.message.delete()
    logger.info("User %d verified channel membership", user_id)


async def enforce_membership(client: Client, message: Message) -> bool:
    """Block the user if mandatory-join channels are not satisfied; return True if allowed."""
    if not message.from_user:
        return True
    user_id = message.from_user.id
    if is_admin(user_id):
        return True

    db = get_db()
    if await db.get_setting("maintenance_mode") == "1":
        if message:
            await message.reply_text(MAINTENANCE)
        return False

    if await db.get_setting("force_join_enabled") != "1":
        return True

    not_joined = await _check_membership(client, user_id)
    if not_joined:
        kb = join_keyboard(not_joined)
        msg = await db.get_setting(
            "join_message",
            "سلام خوش اومدی🌹\n✨ برای استفاده از ربات، لطفاً ابتدا در کانال‌ها عضو شوید:",
        )
        await message.reply_text(msg, reply_markup=kb)
        return False
    return True


@Client.on_message(filters.command("admin") & filters.private)
async def cmd_admin(client: Client, message: Message) -> None:
    """Handle /admin command — open admin panel."""
    from handlers.admin.panel import admin_start_handler

    await admin_start_handler(client, message)


@Client.on_message(filters.command("cancel") & filters.private)
async def cmd_cancel(client: Client, message: Message) -> None:
    """Handle /cancel — cancel all active downloads and clean up temp files."""
    if not message.from_user:
        return
    user_id = message.from_user.id
    count = download_manager.cancel_all(user_id)
    download_manager.cleanup_user_files(user_id)
    from handlers.states import clear_state

    clear_state(user_id)
    if count == 0:
        await message.reply_text(NO_ACTIVE_DL)
