"""Admin broadcast conversation flow handlers."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from pyrogram import Client
from pyrogram.types import CallbackQuery, Message

from handlers.states import get_user_data
from models import AdminState
from services import get_db
from utils.keyboards import (
    admin_main_keyboard,
    broadcast_confirm_keyboard,
)

from .panel import _check_back, _safe_edit

logger = logging.getLogger(__name__)


async def _handle_a_broadcast(
    callback_query: CallbackQuery,
) -> int:
    """Prompt the admin to compose a broadcast message."""
    get_user_data(callback_query.from_user.id).pop("on_admin_main", None)
    await _safe_edit(
        callback_query,
        "📣 پیام همگانی را بفرستید.",
    )
    return AdminState.WAIT_BROADCAST


async def h_broadcast_handler(client: Client, message: Message) -> int:
    """Receive the broadcast message and show a confirmation prompt."""
    back = await _check_back(client, message)
    if back is not None:
        return back
    user_id = message.from_user.id
    ud = get_user_data(user_id)
    ud["bc_msg_id"] = message.id
    ud["bc_chat_id"] = message.chat.id
    db = get_db()
    user_count = await db.get_users_count()
    await message.reply_text(
        f"این پیام به {user_count} نفر ارسال میشود آیا تأیید میکنید",
        reply_markup=broadcast_confirm_keyboard(user_count),
    )
    return AdminState.WAIT_BROADCAST_CONFIRM


async def h_broadcast_confirm_handler(client: Client, callback_query: CallbackQuery) -> int:
    """Execute the broadcast after admin confirmation."""
    await callback_query.answer()
    if callback_query.data != "bc_confirm":
        await _safe_edit(callback_query, "🗽 **پنل مدیریت ربات**", admin_main_keyboard())
        return AdminState.ADMIN_CHOOSE

    user_id = callback_query.from_user.id
    ud = get_user_data(user_id)
    msg_id = ud.pop("bc_msg_id", None)
    chat_id = ud.pop("bc_chat_id", None)
    if not msg_id or not chat_id:
        await callback_query.answer("❌ خطا: اطلاعات پیام یافت نشد.", show_alert=True)
        await _safe_edit(callback_query, "🗽 **پنل مدیریت ربات**", admin_main_keyboard())
        return AdminState.ADMIN_CHOOSE
    db = get_db()
    user_ids = await db.get_all_user_ids()
    status = await callback_query.message.reply_text("درحال ارسال...")
    success = failed = 0

    total = len(user_ids)
    start_time = asyncio.get_running_loop().time()

    for i, uid in enumerate(user_ids, 1):
        try:
            await client.copy_message(chat_id=uid, from_chat_id=chat_id, message_id=msg_id)
            success += 1
        except Exception as exc:
            failed += 1
            logger.warning("Broadcast to %d failed: %s", uid, exc)
        if i % 50 == 0:
            elapsed = asyncio.get_running_loop().time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            remaining = (total - i) / rate if rate > 0 else 0
            with contextlib.suppress(Exception):
                await status.edit_text(
                    f"📣 در حال ارسال... {i}/{total}\n⏱ تخمین باقیمانده: {int(remaining)} ثانیه"
                )
        await asyncio.sleep(0.05)

    with contextlib.suppress(Exception):
        await status.delete()
    await callback_query.message.reply_text(
        "✅ ارسال پیام همگانی تمام شد",
        reply_markup=admin_main_keyboard(),
    )
    logger.info(
        "Broadcast completed: success=%d, failed=%d",
        success,
        failed,
    )
    return AdminState.ADMIN_CHOOSE
