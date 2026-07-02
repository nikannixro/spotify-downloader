"""Admin log channel management handlers."""

from __future__ import annotations

import logging
import re

from pyrogram import Client, enums
from pyrogram.types import CallbackQuery, Message

from handlers.states import get_user_data
from models import AdminState
from services import get_db
from utils.keyboards import back_reply_keyboard

from .panel import _safe_edit

logger = logging.getLogger(__name__)


async def _log_channel_text(db) -> tuple[str, list]:
    """Build log channel settings text and keyboard."""
    from utils.keyboards import log_channel_keyboard

    log_channel_enabled = await db.get_setting("log_channel_enabled", "0") == "1"
    log_channel_id = await db.get_setting("log_channel_id", "")

    text = (
        "📋 **کانال لاگ**\n\n"
        "• با فعال کردن این قابلیت، لاگهای Error و Warning به کانال تنظیم شده ارسال میشوند"
    )

    kb = await log_channel_keyboard()
    return text, kb


async def _handle_a_log_channel(callback_query: CallbackQuery, db) -> int:
    """Handle opening log channel settings."""
    await callback_query.answer()
    get_user_data(callback_query.from_user.id).pop("on_admin_main", None)
    text, kb = await _log_channel_text(db)
    await callback_query.message.edit_text(text, reply_markup=kb)
    return AdminState.ADMIN_CHOOSE


async def _handle_lc_toggle(callback_query: CallbackQuery, db) -> int:
    """Toggle log channel enabled/disabled."""
    await callback_query.answer()
    get_user_data(callback_query.from_user.id).pop("on_admin_main", None)

    current = await db.get_setting("log_channel_enabled", "0")
    new_value = "0" if current == "1" else "1"
    await db.set_setting("log_channel_enabled", new_value)

    text, kb = await _log_channel_text(db)
    await callback_query.message.edit_text(text, reply_markup=kb)
    return AdminState.ADMIN_CHOOSE


async def _handle_lc_set(callback_query: CallbackQuery) -> int:
    """Prompt admin to send log channel username."""
    await callback_query.answer(
        "لطفا آیدی کانال مورد نظر را بدون @ ارسال کنید", show_alert=True
    )
    return AdminState.WAIT_LOG_CHANNEL


async def _handle_lc_remove(callback_query: CallbackQuery, db) -> int:
    """Remove configured log channel."""
    get_user_data(callback_query.from_user.id).pop("on_admin_main", None)
    await db.set_setting("log_channel_id", "")
    await db.set_setting("log_channel_enabled", "0")

    text, kb = await _log_channel_text(db)
    await callback_query.message.edit_text(text, reply_markup=kb)
    return AdminState.ADMIN_CHOOSE


async def h_log_channel_handler(client: Client, message: Message) -> int:
    """Handle log channel username input."""
    from .panel import _check_back

    back = await _check_back(client, message)
    if back is not None:
        return back

    text = message.text.strip()

    # Reject usernames starting with @
    if text.startswith("@"):
        await message.reply_text(
            "❌ کانال یافت نشد.\n\n"
            "لطفاً مطمئن شوید:\n"
            "• آیدی کانال صحیح است\n"
            "• ربات در کانال عضو و ادمین است\n"
            "• آیدی را بدون @ ارسال کنید",
            reply_markup=back_reply_keyboard(),
        )
        return AdminState.WAIT_LOG_CHANNEL

    channel_id = text
    if text.startswith("https://t.me/"):
        match = re.search(r"https?://t\.me/([a-zA-Z0-9_]+)", text)
        if match:
            channel_id = f"@{match.group(1)}"

    try:
        chat = await client.get_chat(channel_id)
        bot_member = await client.get_chat_member(chat.id, client.me.id)

        # Validate it's a channel
        if chat.type.value != "channel":
            await message.reply_text(
                "❌ خطا کانال یافت نشد\n\n"
                "لطفاً مطمئن شوید:\n"
                "• آیدی کانال صحیح است\n"
                "• ربات در کانال عضو و ادمین است\n"
                "• ربات دسترسی ارسال پیام را دارد",
                reply_markup=back_reply_keyboard(),
            )
            return AdminState.WAIT_LOG_CHANNEL

        # Validate bot is admin
        if bot_member.status not in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER):
            await message.reply_text(
                "❌ ربات باید ادمین کانال باشد.\n"
                "لطفاً ربات را به عنوان ادمین به کانال اضافه کنید.",
                reply_markup=back_reply_keyboard(),
            )
            return AdminState.WAIT_LOG_CHANNEL

        # Save channel ID
        db = get_db()
        await db.set_setting("log_channel_id", str(chat.id))
        await db.set_setting("log_channel_enabled", "1")

        channel_username = f"@{chat.username}" if chat.username else str(chat.id)
        await message.reply_text(
            f"✅ کانال لاگ تنظیم شد:\n\n〽️ {chat.title}\n🆔 {channel_username}",
            reply_markup=None,
        )

        text, kb = await _log_channel_text(db)
        await message.reply_text(text, reply_markup=kb)
        logger.info("Admin set log channel: %s (%s)", chat.title, chat.id)
        return AdminState.ADMIN_CHOOSE

    except Exception as exc:
        logger.warning("Log channel validation failed: %s", exc)
        await message.reply_text(
            "❌ خطا کانال یافت نشد\n\n"
            "لطفاً مطمئن شوید:\n"
            "• آیدی کانال صحیح است\n"
            "• ربات در کانال عضو و ادمین است\n"
            "• ربات دسترسی ارسال پیام را دارد",
            reply_markup=back_reply_keyboard(),
        )
        return AdminState.WAIT_LOG_CHANNEL
