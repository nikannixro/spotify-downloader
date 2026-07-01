"""Callback query handler — routes all callback queries to the appropriate handler."""

from __future__ import annotations

import contextlib
import logging

from pyrogram import Client
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
    _handle_open_admin,
    _handle_rate_limit_adjust,
    _handle_rate_window_adjust,
    admin_open_callback_handler,
    h_broadcast_confirm_handler,
)
from handlers.start import verify_join_callback
from handlers.states import clear_state, get_state, set_state
from models import AdminState
from services import get_db
from strings import CANCELLED_FA, NO_ACTIVE_DL

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
        target_user_id = int(data.split(":")[1])
        if user_id == target_user_id:
            count = download_manager.cancel_all(user_id)
            download_manager.cleanup_user_files(user_id)
            with contextlib.suppress(Exception):
                await callback_query.message.edit_text(CANCELLED_FA)
            if count == 0:
                await callback_query.answer(NO_ACTIVE_DL)
            else:
                await callback_query.answer()
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
