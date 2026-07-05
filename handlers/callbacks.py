"""Callback query handler — routes all callback queries to the appropriate handler."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from pyrogram import Client, enums
from pyrogram.types import CallbackQuery

import plugins.download_manager as download_manager
from config import is_admin
from handlers.admin import (
    RATE_LIMIT_DELTAS,
    RATE_WINDOW_DELTAS,
    _handle_a_back,
    _handle_a_back_main,
    _handle_a_backup,
    _handle_a_broadcast,
    _handle_a_channels,
    _handle_a_edit_start,
    _handle_a_log_channel,
    _handle_a_logs,
    _handle_a_recent_dl,
    _handle_a_settings,
    _handle_a_stats,
    _handle_c_add,
    _handle_c_del,
    _handle_c_destination,
    _handle_c_edit_join_msg,
    _handle_c_preview,
    _handle_c_remove,
    _handle_c_toggle,
    _handle_lc_remove,
    _handle_lc_set,
    _handle_lc_toggle,
    _handle_maintenance_toggle,
    _handle_rate_limit_adjust,
    _handle_rate_window_adjust,
    admin_open_callback_handler,
    h_broadcast_confirm_handler,
)
from handlers.start import verify_join_callback
from handlers.states import clear_state, get_state, set_state
from models import AdminState
from services import get_db
from strings import CANCELLED, NO_ACTIVE_DL

logger = logging.getLogger(__name__)


@Client.on_callback_query()
async def handle_callback(client: Client, callback_query: CallbackQuery) -> None:
    """Main callback router — delegates to sub-modules."""
    data = callback_query.data
    user_id = callback_query.from_user.id

    # --- Verify join ---
    if data == "verify_join":
        await verify_join_callback(client, callback_query)
        return

    # --- Cancel download ---
    if data and data.startswith("cancel_dl:"):
        parts = data.split(":")
        if len(parts) == 3:
            target_user_id = int(parts[1])
            task_id = int(parts[2])
            if user_id == target_user_id:
                cancelled = download_manager.cancel_task(user_id, task_id)
                if not cancelled:
                    await callback_query.answer(NO_ACTIVE_DL)
                else:
                    download_manager.cleanup_user_files(user_id)
                    with contextlib.suppress(Exception):
                        await callback_query.message.edit_text(CANCELLED)
                    await callback_query.answer()
        return

    # --- Download artist track ---
    if data and data.startswith("download_artist_track:"):
        parts = data.split(":")
        if len(parts) == 3:
            target_user_id = int(parts[1])
            track_index = int(parts[2])
            if user_id == target_user_id:
                await _handle_download_artist_track(client, callback_query, track_index)
            else:
                await callback_query.answer("❌ این دکمه مال شما نیست!", show_alert=True)
        return

    # --- Show artist top tracks ---
    if data and data.startswith("show_artist_tracks:"):
        parts = data.split(":")
        if len(parts) == 2:
            target_user_id = int(parts[1])
            if user_id == target_user_id:
                await _handle_show_artist_tracks(client, callback_query)
            else:
                await callback_query.answer("❌ این دکمه مال شما نیست!", show_alert=True)
        return

    # --- Open admin panel ---
    if data == "open_admin":
        if not is_admin(user_id):
            await callback_query.answer("❌ دسترسی ندارید.", show_alert=True)
            return
        new_state = await admin_open_callback_handler(client, callback_query)
        if new_state is not None and new_state >= 0:
            set_state(user_id, new_state)
        return

    # --- Broadcast confirm / back ---
    if data in ("bc_confirm", "a_back"):
        if data == "bc_confirm":
            new_state = await h_broadcast_confirm_handler(client, callback_query)
        else:
            new_state = await _handle_a_back(callback_query)
        if new_state is not None and new_state >= 0:
            set_state(user_id, new_state)
        else:
            clear_state(user_id)
        return

    # --- All other admin callbacks ---
    if not is_admin(user_id):
        await callback_query.answer()
        return

    db = get_db()
    current_state = get_state(user_id)
    new_state = None

    if data == "a_maintenance":
        new_state = await _handle_maintenance_toggle(callback_query, db)
    elif data == "c_destination":
        new_state = await _handle_c_destination(callback_query)
    elif data == "a_channels":
        new_state = await _handle_a_channels(callback_query, db)
    elif data == "c_toggle":
        new_state = await _handle_c_toggle(callback_query, db)
    elif data == "c_preview":
        new_state = await _handle_c_preview(callback_query, db)
    elif data == "c_edit_join_msg":
        new_state = await _handle_c_edit_join_msg(callback_query)
    elif data == "a_back_main":
        new_state = await _handle_a_back_main(callback_query, user_id)
    elif data == "a_stats":
        await callback_query.answer()
        new_state = await _handle_a_stats(callback_query)
    elif data == "a_recent_dl":
        await callback_query.answer()
        new_state = await _handle_a_recent_dl(callback_query)
    elif data == "a_backup":
        await callback_query.answer()
        new_state = await _handle_a_backup(callback_query)
    elif data == "a_logs":
        await callback_query.answer()
        new_state = await _handle_a_logs(callback_query)
    elif data == "a_edit_start":
        new_state = await _handle_a_edit_start(callback_query)
    elif data == "a_broadcast":
        new_state = await _handle_a_broadcast(callback_query)
    elif data == "c_add":
        new_state = await _handle_c_add(callback_query)
    elif data == "c_remove":
        new_state = await _handle_c_remove(callback_query, db)
    elif data.startswith("c_del_"):
        new_state = await _handle_c_del(callback_query, db, data.removeprefix("c_del_"))
    elif data == "a_settings":
        new_state = await _handle_a_settings(callback_query)
    elif data == "a_log_channel":
        new_state = await _handle_a_log_channel(callback_query, db)
    elif data == "lc_toggle":
        new_state = await _handle_lc_toggle(callback_query, db)
    elif data == "lc_set":
        new_state = await _handle_lc_set(callback_query)
    elif data == "lc_remove":
        new_state = await _handle_lc_remove(callback_query, db)
    elif data in RATE_LIMIT_DELTAS:
        new_state = await _handle_rate_limit_adjust(callback_query, data, db)
    elif data in RATE_WINDOW_DELTAS:
        new_state = await _handle_rate_window_adjust(callback_query, data, db)
    elif data in ("s_rl_max", "s_rl_win"):
        await callback_query.answer()
        new_state = AdminState.ADMIN_CHOOSE
    else:
        await callback_query.answer()
        new_state = current_state or AdminState.ADMIN_CHOOSE

    if new_state is not None and new_state >= 0:
        set_state(user_id, new_state)
    else:
        clear_state(user_id)


async def _handle_download_artist_track(
    client: Client, callback_query: CallbackQuery, track_index: int
) -> None:
    """Handle download request for a specific artist track."""
    from handlers.download import _artist_tracks_cache, _download_single_track
    from plugins.spotdl import _ensure_spotdl_init
    from spotdl.utils.spotify import SpotifyClient

    user_id = callback_query.from_user.id

    tracks = _artist_tracks_cache.get(user_id, [])
    if track_index >= len(tracks):
        await callback_query.answer("❌ Track Not Found", show_alert=True)
        return

    track_info = tracks[track_index]
    track_title = track_info.get("title", "")
    artist_name = track_info.get("artist", "")

    await callback_query.answer()

    status_msg = await callback_query.message.reply_text("🔍 در حال جستجوی آهنگ...")

    try:
        _ensure_spotdl_init()
        spotify = SpotifyClient()
        loop = asyncio.get_running_loop()

        def _search_track():
            query = f"{track_title} {artist_name}"
            results = spotify.search(q=query, type="track", limit=1)
            found_tracks = results.get("tracks", {}).get("items", [])
            return found_tracks[0] if found_tracks else None

        track = await loop.run_in_executor(None, _search_track)

        if not track:
            await status_msg.edit_text("❌ Track Not Found")
            return

        spotify_track_id = track.get("id")
        if not spotify_track_id:
            await status_msg.edit_text("❌ خطا در دریافت اطلاعات آهنگ.")
            return

        await status_msg.delete()
    except Exception as exc:
        logger.error("Failed to search for track %s by %s: %s", track_title, artist_name, exc)
        with contextlib.suppress(Exception):
            await status_msg.edit_text("❌ خطا در جستجوی آهنگ.")
        return

    task = asyncio.current_task()

    try:
        await _download_single_track(client, callback_query.message, user_id, spotify_track_id, task)
    finally:
        if task:
            download_manager.unregister(user_id, task)


async def _handle_show_artist_tracks(
    client: Client, callback_query: CallbackQuery
) -> None:
    """Send a new message with clickable deep links for top tracks."""
    from urllib.parse import quote

    import config
    from handlers.download import _artist_tracks_cache

    user_id = callback_query.from_user.id
    tracks = _artist_tracks_cache.get(user_id, [])

    if not tracks:
        await callback_query.answer("❌ لیست آهنگ‌ها یافت نشد.", show_alert=True)
        return

    bot_username = config.cfg.BOT_USERNAME
    lines = []
    for i, track in enumerate(tracks):
        title = track.get("title", f"Track {i + 1}")
        artist = track.get("artist", "Unknown")
        key = f"{artist}_{title}".replace(" ", "_").lower()
        encoded = quote(key, safe="")
        url = f"https://t.me/{bot_username}?start={encoded}"
        lines.append(f'{artist} - {title}')
        lines.append(f'<a href="{url}">Download</a>')
        lines.append('--------------------------')

    text = "🎵Top 10 Tracks\n\n" + "\n".join(lines)
    await client.send_message(
        chat_id=user_id,
        text=text,
        parse_mode=enums.ParseMode.HTML,
    )
    await callback_query.answer()
