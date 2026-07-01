"""Telegram inline keyboards — Pyrogram types."""

from __future__ import annotations

from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from models import ChannelRecord


def cancel_download_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Build an inline keyboard with a cancel download button."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_dl:{user_id}")]]
    )


def main_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Build the main search keyboard, optionally including the admin panel button."""
    kb = [
        [
            InlineKeyboardButton("Search by artist 👤", switch_inline_query_current_chat="art: "),
            InlineKeyboardButton("Search by album 💿", switch_inline_query_current_chat="alb: "),
        ],
        [
            InlineKeyboardButton("Search playlist 📁", switch_inline_query_current_chat="pla: "),
            InlineKeyboardButton("Search track 🎧", switch_inline_query_current_chat="trk: "),
        ],
        [InlineKeyboardButton("Global search 📊", switch_inline_query_current_chat="")],
    ]
    if is_admin:
        kb.append([InlineKeyboardButton("پنل مدیریت 🛠", callback_data="open_admin")])
    return InlineKeyboardMarkup(kb)


def admin_main_keyboard() -> InlineKeyboardMarkup:
    """Build the admin panel main menu keyboard."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📥 دانلودهای اخیر", callback_data="a_recent_dl"),
                InlineKeyboardButton("📊 آمار کلی", callback_data="a_stats"),
            ],
            [
                InlineKeyboardButton("🪙 عضویت اجباری", callback_data="a_channels"),
                InlineKeyboardButton("✏️ تنظیم پیام استارت", callback_data="a_edit_start"),
            ],
            [
                InlineKeyboardButton("📣 ارسال پیام همگانی", callback_data="a_broadcast"),
                InlineKeyboardButton("💾 بکاپ دیتابیس", callback_data="a_backup"),
            ],
            [InlineKeyboardButton("🛠 حالت تعمیر", callback_data="a_maintenance")],
            [InlineKeyboardButton("📋 لاگ ها", callback_data="a_log_channel")],
            [InlineKeyboardButton("⚙️ تنظیمات", callback_data="a_settings")],
        ]
    )


async def channels_keyboard() -> InlineKeyboardMarkup:
    """Build the mandatory-join channel settings keyboard."""
    from services import get_db

    db = get_db()
    force_join = await db.get_setting("force_join_enabled", "0")
    channels = await db.get_channels()
    lock_status = "✅" if force_join == "1" and channels else "❌"
    dest_status = "تنظیم شده" if channels else "تنظیم نشده"
    kb = [
        [InlineKeyboardButton(f"قفل عضویت اجباری: {lock_status}", callback_data="c_toggle")],
        [InlineKeyboardButton(f"مقصد: {dest_status}", callback_data="c_destination")],
    ]
    if force_join == "1":
        from handlers.admin.panel import DEFAULT_JOIN_MSG

        current_msg = await db.get_setting("join_message", DEFAULT_JOIN_MSG)
        msg_status = "پیشفرض" if current_msg == DEFAULT_JOIN_MSG else "دستی"
        kb.append(
            [
                InlineKeyboardButton(
                    f"• متن پیام عضویت اجباری : {msg_status}", callback_data="c_preview"
                )
            ]
        )
    return InlineKeyboardMarkup(kb)


async def settings_keyboard() -> InlineKeyboardMarkup:
    """Build the rate-limit settings keyboard."""
    from services import get_db

    db = get_db()
    rl_max = await db.get_setting("rate_limit_max", "3")
    rl_win = await db.get_setting("rate_limit_window", "60")
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"🔢 حداکثر دانلود: {rl_max}", callback_data="s_rl_max")],
            [
                InlineKeyboardButton("❮❮", callback_data="s_rl_m5"),
                InlineKeyboardButton("❮", callback_data="s_rl_m1"),
                InlineKeyboardButton("❯", callback_data="s_rl_p1"),
                InlineKeyboardButton("❯❯", callback_data="s_rl_p5"),
            ],
            [InlineKeyboardButton(f"⏱ بازه زمانی: {rl_win}s", callback_data="s_rl_win")],
            [
                InlineKeyboardButton("❮❮", callback_data="s_rlw_m5"),
                InlineKeyboardButton("❮", callback_data="s_rlw_m1"),
                InlineKeyboardButton("❯", callback_data="s_rlw_p1"),
                InlineKeyboardButton("❯❯", callback_data="s_rlw_p5"),
            ],
        ]
    )


def channel_remove_keyboard(channels: list[ChannelRecord]) -> InlineKeyboardMarkup:
    """Build a keyboard listing channels with removal buttons."""
    kb = [
        [InlineKeyboardButton(f"❌ {ch.channel_title}", callback_data=f"c_del_{ch.channel_id}")]
        for ch in channels
    ]
    return InlineKeyboardMarkup(kb)


def broadcast_confirm_keyboard(user_count: int) -> InlineKeyboardMarkup:
    """Build the broadcast confirmation keyboard."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ ارسال", callback_data="bc_confirm"),
                InlineKeyboardButton("❌ لغو", callback_data="a_back"),
            ]
        ]
    )


def join_keyboard(channels: list[ChannelRecord]) -> InlineKeyboardMarkup:
    """Build the mandatory-join channel selection keyboard."""
    kb = [[InlineKeyboardButton(f"📢 {ch.channel_title}", url=ch.invite_link)] for ch in channels]
    kb.append([InlineKeyboardButton("✅ جوین شدم", callback_data="verify_join")])
    return InlineKeyboardMarkup(kb)


def back_reply_keyboard() -> ReplyKeyboardMarkup:
    """Build a simple reply keyboard with a back button."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🔙 بازگشت")]],
        resize_keyboard=True,
    )


async def log_channel_keyboard() -> InlineKeyboardMarkup:
    """Build the log channel settings keyboard."""
    from services import get_db

    db = get_db()
    log_channel_enabled = await db.get_setting("log_channel_enabled", "0") == "1"
    log_channel_id = await db.get_setting("log_channel_id", "")

    lock_status = "✅" if log_channel_enabled else "❌"
    channel_status = "تنظیم شده" if log_channel_id else "تنظیم نشده"

    kb = [
        [InlineKeyboardButton(f"قفل لاگ کانال: {lock_status}", callback_data="lc_toggle")],
    ]

    if log_channel_enabled:
        kb.append([InlineKeyboardButton(f"مقصد: {channel_status}", callback_data="lc_set")])
        if log_channel_id:
            kb.append([InlineKeyboardButton("🗑 حذف کانال لاگ", callback_data="lc_remove")])

    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="a_back")])
    return InlineKeyboardMarkup(kb)
