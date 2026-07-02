"""Admin forced-join channel management handlers."""

from __future__ import annotations

import logging
import re

from pyrogram import Client, enums
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from handlers.states import get_user_data
from models import AdminState
from services import get_db
from utils.keyboards import (
    back_reply_keyboard,
    channel_remove_keyboard,
    channels_keyboard,
    join_keyboard,
)

from .panel import DEFAULT_JOIN_MSG, _safe_edit

logger = logging.getLogger(__name__)

CHANNEL_URL_RE: re.Pattern[str] = re.compile(r"https?://t\.me/([a-zA-Z0-9_]+)")


async def _channel_text(lock: str, db) -> tuple[str, list[list[InlineKeyboardButton]]]:
    """Build the forced-join channel settings text and keyboard."""
    text = (
        "• با فعال کردن این قابلیت\n"
        "⋆ می‌توان گروه یا کانالی در ربات ثبت کرد\n"
        "⋆ ربات کاربران را اجبار به عضویت در آن می‌کند\n"
        "⋆ تا اجازه چت کردن در گروه را داشته باشند"
    )
    kb: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(f"قفل عضویت اجباری: {lock}", callback_data="c_toggle")],
    ]
    if lock == "✅":
        channels = await db.get_channels()
        dest = "تنظیم شده" if channels else "تنظیم نشده"
        kb.append([InlineKeyboardButton(f"مقصد: {dest}", callback_data="c_destination")])
        current_msg = await db.get_setting("join_message", DEFAULT_JOIN_MSG)
        msg_status = "پیش فرض" if current_msg == DEFAULT_JOIN_MSG else "دستی"
        kb.append(
            [
                InlineKeyboardButton(
                    f"• متن پیام عضویت اجباری : {msg_status}", callback_data="c_preview"
                )
            ]
        )
    return text, kb


async def _handle_c_destination(callback_query: CallbackQuery) -> int:
    """Prompt the admin to enter a channel ID."""
    await callback_query.answer("لطفا آیدی کانال مورد نظر را بدون @ ارسال کنید", show_alert=True)
    return AdminState.WAIT_CHAN_ID


async def _handle_a_channels(callback_query: CallbackQuery, db) -> int:
    """Display the forced-join channel management screen."""
    await callback_query.answer()
    get_user_data(callback_query.from_user.id).pop("on_admin_main", None)
    lock = "✅" if await db.get_setting("force_join_enabled", "0") == "1" else "❌"
    text, kb = await _channel_text(lock, db)
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb))
    return AdminState.ADMIN_CHOOSE


async def _handle_c_toggle(callback_query: CallbackQuery, db) -> int:
    """Toggle the forced-join lock on or off."""
    await callback_query.answer()
    get_user_data(callback_query.from_user.id).pop("on_admin_main", None)
    current = await db.get_setting("force_join_enabled", "0")
    new_value = "0" if current == "1" else "1"
    await db.set_setting("force_join_enabled", new_value)
    lock = "✅" if new_value == "1" else "❌"
    text, kb = await _channel_text(lock, db)
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb))
    return AdminState.ADMIN_CHOOSE


async def _handle_c_preview(callback_query: CallbackQuery, db) -> int:
    """Preview the forced-join message with the current channel list."""
    channels = await db.get_channels()
    if not channels:
        await callback_query.answer("هیچ کانالی تنظیم نشده است", show_alert=True)
        return AdminState.ADMIN_CHOOSE
    await callback_query.answer()
    msg = await db.get_setting("join_message", DEFAULT_JOIN_MSG)
    await callback_query.message.reply_text(msg, reply_markup=join_keyboard(channels))
    current_msg = msg
    msg_status = "پیش فرض" if current_msg == DEFAULT_JOIN_MSG else "دستی"
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✏️ تغییر متن پیام", callback_data="c_edit_join_msg")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="a_channels")],
        ]
    )
    await callback_query.message.reply_text(
        f"**وضعیت متن پیام:** {msg_status}\n\n**متن فعلی:**\n{msg}",
        reply_markup=kb,
    )
    return AdminState.ADMIN_CHOOSE


async def _handle_c_edit_join_msg(callback_query: CallbackQuery) -> int:
    """Prompt the admin to send a new forced-join message."""
    await callback_query.answer()
    await _safe_edit(callback_query, "متن جدید پیام عضویت اجباری را بفرستید:")
    return AdminState.WAIT_JOIN_MSG


async def _handle_c_add(
    callback_query: CallbackQuery,
) -> int:
    """Prompt the admin to add a new forced-join channel."""
    get_user_data(callback_query.from_user.id).pop("on_admin_main", None)
    text = (
        "● لطفا آیدی کانالی که مایل هستید "
        "کاربران ربات در آن عضو شوند را بدون @ ارسال کنید\n"
        "مثال: mychannel"
    )
    await _safe_edit(callback_query, text)
    return AdminState.WAIT_CHAN_ID


async def _handle_c_remove(callback_query: CallbackQuery, db) -> int:
    """Display channels with removal buttons."""
    get_user_data(callback_query.from_user.id).pop("on_admin_main", None)
    channels = await db.get_channels()
    if not channels:
        await callback_query.answer("هیچ کانالی ثبت نشده", show_alert=True)
        return AdminState.ADMIN_CHOOSE
    await _safe_edit(
        callback_query,
        "کانال مورد نظر را انتخاب کنید:",
        channel_remove_keyboard(channels),
    )
    return AdminState.ADMIN_CHOOSE


async def _handle_c_del(
    callback_query: CallbackQuery,
    db,
    channel_id: str,
) -> int:
    """Remove a specific forced-join channel."""
    get_user_data(callback_query.from_user.id).pop("on_admin_main", None)
    await db.remove_channel(channel_id)
    text = (
        "• با فعال کردن این قابلیت\n"
        "⋆ می‌توان گروه یا کانالی در ربات ثبت کرد\n"
        "⋆ ربات کاربران را اجبار به عضویت در آن می‌کند\n"
        "⋆ تا اجازه چت کردن در گروه را داشته باشند"
    )
    await _safe_edit(callback_query, text, await channels_keyboard())

    return AdminState.ADMIN_CHOOSE


async def h_chan_id_handler(client: Client, message: Message) -> int:
    """Validate and register a channel ID sent by the admin."""
    from .panel import _check_back

    back = await _check_back(client, message)
    if back is not None:
        return back

    text = message.text.strip()

    if text.startswith("@"):
        await message.reply_text(
            "❌ خطا کانال یافت نشد\n\n"
            "لطفاً مطمئن شوید:\n"
            "• آیدی کانال صحیح است\n"
            "• ربات در کانال عضو و ادمین است\n"
            "• ربات دسترسی خواندن پیام را دارد",
            reply_markup=back_reply_keyboard(),
        )
        return AdminState.WAIT_CHAN_ID

    channel_id = text
    if text.startswith("https://t.me/"):
        match = CHANNEL_URL_RE.search(text)
        if match:
            channel_id = f"@{match.group(1)}"
    elif not text.startswith("@") and not text.lstrip("-").isdigit():
        channel_id = f"@{text}"

    CHANNEL_ERROR = (
        "❌ خطا کانال یافت نشد\n\n"
        "لطفاً مطمئن شوید:\n"
        "• آیدی کانال صحیح است\n"
        "• ربات در کانال عضو و ادمین است\n"
        "• ربات دسترسی خواندن پیام را دارد"
    )

    try:
        chat = await client.get_chat(channel_id)
        bot_member = await client.get_chat_member(chat.id, client.me.id)

        if chat.type.value != "channel":
            await message.reply_text(CHANNEL_ERROR, reply_markup=back_reply_keyboard())
            return AdminState.WAIT_CHAN_ID

        if bot_member.status not in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER):
            await message.reply_text(CHANNEL_ERROR, reply_markup=back_reply_keyboard())
            return AdminState.WAIT_CHAN_ID

        try:
            invite_link = await client.export_chat_invite_link(chat.id)
        except Exception:
            invite_link = f"https://t.me/{chat.username}" if chat.username else ""

        db = get_db()
        await db.add_channel(str(chat.id), chat.title, invite_link)
        await db.set_setting("force_join_enabled", "1")

        channel_username = f"@{chat.username}" if chat.username else str(chat.id)
        await message.reply_text(
            f"✅ کانال اضافه شد:\n\n〽️ {chat.title}\n🆔 {channel_username}",
            reply_markup=None,
        )
        text = (
            "• با فعال کردن این قابلیت\n"
            "⋆ می‌توان گروه یا کانالی در ربات ثبت کرد\n"
            "⋆ ربات کاربران را اجبار به عضویت در آن می‌کند\n"
            "⋆ تا اجازه چت کردن در گروه را داشته باشند"
        )
        await message.reply_text(
            text,
            reply_markup=await channels_keyboard(),
        )
        logger.info("Admin added channel: %s (%s)", chat.title, chat.id)
        return AdminState.ADMIN_CHOOSE

    except Exception as exc:
        logger.warning("Channel validation failed: %s", exc)
        await message.reply_text(
            "❌ خطا کانال یافت نشد\n\n"
            "لطفاً مطمئن شوید:\n"
            "• آیدی کانال صحیح است\n"
            "• ربات در کانال عضو و ادمین است\n"
            "• ربات دسترسی خواندن پیام را دارد",
            reply_markup=back_reply_keyboard(),
        )
        return AdminState.WAIT_CHAN_ID


async def h_join_msg_handler(client: Client, message: Message) -> int:
    """Save the new forced-join message text sent by the admin."""
    from .panel import _check_back, admin_main_keyboard

    back = await _check_back(client, message)
    if back is not None:
        return back
    db = get_db()
    await db.set_setting("join_message", message.text)
    await message.reply_text(
        "✅ پیام عضویت اجباری آپدیت شد.",
        reply_markup=None,
    )
    await message.reply_text(
        "🗽 **پنل مدیریت ربات**",
        reply_markup=admin_main_keyboard(),
    )
    return AdminState.ADMIN_CHOOSE
