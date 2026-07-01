"""Admin rate-limit and general settings handlers."""

from __future__ import annotations

import logging

from pyrogram import Client
from pyrogram.types import CallbackQuery, Message

from handlers.states import get_user_data
from models import AdminState
from services import get_db, get_rate_limiter
from utils.keyboards import settings_keyboard

from .panel import _check_back, _safe_edit, admin_main_keyboard

logger = logging.getLogger(__name__)

RATE_LIMIT_DELTAS: dict[str, int] = {
    "s_rl_m5": -5,
    "s_rl_m1": -1,
    "s_rl_p1": 1,
    "s_rl_p5": 5,
}

RATE_WINDOW_DELTAS: dict[str, int] = {
    "s_rlw_m5": -5,
    "s_rlw_m1": -1,
    "s_rlw_p1": 1,
    "s_rlw_p5": 5,
}


async def _handle_a_settings(
    callback_query: CallbackQuery,
) -> int:
    """Display the rate-limit settings screen."""
    get_user_data(callback_query.from_user.id).pop("on_admin_main", None)
    await _safe_edit(callback_query, "⚙️ **تنظیمات ربات:**", await settings_keyboard())
    return AdminState.ADMIN_CHOOSE


async def _handle_rate_limit_adjust(
    callback_query: CallbackQuery,
    data: str,
    db,
) -> int:
    """Adjust the maximum downloads per window by the given delta."""
    get_user_data(callback_query.from_user.id).pop("on_admin_main", None)
    delta = RATE_LIMIT_DELTAS.get(data, 0)
    current = int(await db.get_setting("rate_limit_max", "3"))
    new_value = max(1, current + delta)
    await db.set_setting("rate_limit_max", str(new_value))
    await _safe_edit(callback_query, "⚙️ **تنظیمات ربات:**", await settings_keyboard())
    return AdminState.ADMIN_CHOOSE


async def _handle_rate_window_adjust(
    callback_query: CallbackQuery,
    data: str,
    db,
) -> int:
    """Adjust the rate-limit window duration by the given delta."""
    get_user_data(callback_query.from_user.id).pop("on_admin_main", None)
    delta = RATE_WINDOW_DELTAS.get(data, 0)
    current = int(await db.get_setting("rate_limit_window", "60"))
    new_value = max(1, current + delta)
    await db.set_setting("rate_limit_window", str(new_value))
    await _safe_edit(callback_query, "⚙️ **تنظیمات ربات:**", await settings_keyboard())
    return AdminState.ADMIN_CHOOSE


async def h_rate_limit_handler(client: Client, message: Message) -> int:
    """Save a new max-downloads value sent by the admin."""
    back = await _check_back(client, message)
    if back is not None:
        return back
    value = message.text.strip()
    if not value.isdigit() or int(value) < 1:
        await message.reply_text("❌ عدد صحیح بزرگتر از صفر وارد کنید.")
        return AdminState.WAIT_RATE_LIMIT
    db = get_db()
    await db.set_setting("rate_limit_max", value)
    await get_rate_limiter().reset(message.from_user.id)
    await message.reply_text(
        f"✅ حداکثر دانلود به {value} تغییر یافت.",
        reply_markup=None,
    )
    await message.reply_text(
        "⚙️ **تنظیمات ربات:**",
        reply_markup=await settings_keyboard(),
    )
    return AdminState.ADMIN_CHOOSE


async def h_rate_window_handler(client: Client, message: Message) -> int:
    """Save a new rate-limit window duration sent by the admin."""
    back = await _check_back(client, message)
    if back is not None:
        return back
    value = message.text.strip()
    if not value.isdigit() or int(value) < 1:
        await message.reply_text("❌ عدد صحیح بزرگتر از صفر وارد کنید.")
        return AdminState.WAIT_RATE_WINDOW
    db = get_db()
    await db.set_setting("rate_limit_window", value)
    await get_rate_limiter().reset(message.from_user.id)
    await message.reply_text(
        f"✅ بازه زمانی به {value} ثانیه تغییر یافت.",
        reply_markup=None,
    )
    await message.reply_text(
        "⚙️ **تنظیمات ربات:**",
        reply_markup=await settings_keyboard(),
    )
    return AdminState.ADMIN_CHOOSE



