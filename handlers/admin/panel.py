"""Admin panel main menu, stats, backup, and maintenance handlers."""

from __future__ import annotations

import contextlib
import datetime
import logging
import os
import shutil
import tempfile

from pyrogram import Client
from pyrogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from config import is_admin
from handlers.states import clear_state, get_user_data, set_state
from models import AdminState
from services import get_cache, get_db
from utils.helpers import bytes_to_human, server_uptime_string, uptime_string
from utils.keyboards import (
    admin_main_keyboard,
    back_reply_keyboard,
    main_keyboard,
)

logger = logging.getLogger(__name__)

DEFAULT_JOIN_MSG = "سلام خوش اومدی🌹\n✨ برای استفاده از ربات، لطفاً ابتدا در کانال‌ها عضو شوید:"


async def _safe_edit(
    callback_query: CallbackQuery,
    text: str,
    markup=None,
) -> None:
    try:
        await callback_query.message.edit_text(
            text,
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.warning("edit_text failed: %s", exc)


async def _check_back(client: Client, message: Message) -> int | None:
    if message and message.text and message.text.strip() == "🔙 بازگشت":
        user_id = message.from_user.id
        get_user_data(user_id)["on_admin_main"] = True
        await message.reply_text(
            "🗽 **پنل مدیریت ربات**",
            reply_markup=admin_main_keyboard(),
        )
        return AdminState.ADMIN_CHOOSE
    return None


async def admin_start_handler(client: Client, message: Message) -> int:
    """Open the admin panel from the /admin command."""
    if not is_admin(message.from_user.id):
        await message.reply_text("❌ دسترسی ندارید.")
        clear_state(message.from_user.id)
        return -1  # END
    user_id = message.from_user.id
    set_state(user_id, AdminState.ADMIN_CHOOSE)
    get_user_data(user_id)["on_admin_main"] = True
    await message.reply_text(
        "🗽 **پنل مدیریت ربات**",
        reply_markup=admin_main_keyboard(),
    )
    await message.reply_text(
        "برای بازگشت دکمه زیر را بزنید:",
        reply_markup=back_reply_keyboard(),
    )
    logger.info("Admin %d opened admin panel", user_id)
    return AdminState.ADMIN_CHOOSE


async def admin_open_callback_handler(client: Client, callback_query: CallbackQuery) -> int:
    """Open the admin panel from the inline button callback."""
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        await callback_query.answer("❌ دسترسی ندارید.", show_alert=True)
        clear_state(user_id)
        return -1
    await callback_query.answer()
    set_state(user_id, AdminState.ADMIN_CHOOSE)
    get_user_data(user_id)["on_admin_main"] = True
    await callback_query.message.edit_text(
        "🗽 **پنل مدیریت ربات**",
        reply_markup=admin_main_keyboard(),
    )
    await callback_query.message.reply_text(
        "برای بازگشت دکمه زیر را بزنید:",
        reply_markup=back_reply_keyboard(),
    )
    logger.info(
        "Admin %d opened admin panel via button",
        user_id,
    )
    return AdminState.ADMIN_CHOOSE


async def _handle_open_admin(callback_query: CallbackQuery) -> int:
    """Refresh the admin panel main menu."""
    await callback_query.answer()
    await _safe_edit(callback_query, "🗽 **پنل مدیریت ربات**", admin_main_keyboard())
    return AdminState.ADMIN_CHOOSE


async def _handle_maintenance_toggle(callback_query: CallbackQuery, db) -> int:
    """Toggle maintenance mode on or off."""
    current = await db.get_setting("maintenance_mode", "0")
    new_value = "0" if current == "1" else "1"
    await db.set_setting("maintenance_mode", new_value)
    status = "حالت تعمیر فعال شد" if new_value == "1" else "حالت تعمیر غیرفعال شد"
    await callback_query.answer(status, show_alert=True)
    await _safe_edit(callback_query, "🗽 **پنل مدیریت ربات**", admin_main_keyboard())
    logger.info("Maintenance mode toggled to %s", new_value)
    return AdminState.ADMIN_CHOOSE


async def _handle_a_back(callback_query: CallbackQuery) -> int:
    """Return to the admin panel main menu."""
    await _safe_edit(callback_query, "🗽 **پنل مدیریت ربات**", admin_main_keyboard())
    return AdminState.ADMIN_CHOOSE


async def _handle_a_back_main(callback_query: CallbackQuery, user_id: int) -> int:
    """Exit admin panel and return to the user-facing main keyboard."""
    await callback_query.answer()
    kb_text = "سلام! اینجا ربات نیکسو اسپاتیفای هست 🗽\n\nاز دکمه های زیر برای سرچ اسم خواننده، آلبوم یا آهنگ استفاده کن 👇"
    await callback_query.message.reply_text(
        text="🏠",
        reply_markup=ReplyKeyboardRemove(),
    )
    await callback_query.message.reply_text(
        text=kb_text,
        reply_markup=main_keyboard(is_admin(user_id)),
    )
    with contextlib.suppress(Exception):
        await callback_query.message.delete()
    clear_state(user_id)
    return -1  # END


async def _build_stats_text() -> str:
    """Build the admin statistics summary text."""
    db = get_db()
    downloads_today = await db.get_today_download_count()
    cache_stats = await get_cache().get_stats()
    return (
        "📊 **آمار ربات**\n\n"
        f"👥 کل کاربران: `{await db.get_users_count():,}`\n"
        f"📥 کل دانلودها: `{await db.get_download_count():,}`\n"
        f"📥 دانلودهای امروز: `{downloads_today}`\n\n"
        f"🖥 آپتایم سرور: `{server_uptime_string()}`\n"
        f"⏱ آپتایم ربات: `{uptime_string()}`\n\n"
        f"📦 کش: `{cache_stats['total_files']} فایل` — "
        f"`{bytes_to_human(cache_stats['total_size_bytes'])}`\n"
        f"🗄 حجم دیتابیس: `{bytes_to_human(await db.get_size_bytes())}`"
    )


async def _handle_a_stats(
    callback_query: CallbackQuery,
) -> int:
    """Display bot statistics to the admin."""
    get_user_data(callback_query.from_user.id).pop("on_admin_main", None)
    text = await _build_stats_text()
    await _safe_edit(callback_query, text)
    return AdminState.ADMIN_CHOOSE


async def _handle_a_recent_dl(
    callback_query: CallbackQuery,
) -> int:
    """Display the 10 most recent downloads."""
    get_user_data(callback_query.from_user.id).pop("on_admin_main", None)
    db = get_db()
    rows = await db.get_recent_downloads(10)
    if not rows:
        text = "📥 هیچ دانلودی ثبت نشده."
    else:
        lines = ["📥 **۱۰ دانلود اخیر:**\n"]
        for r in rows:
            lines.append(f"• {r['track_name']}")
        text = "\n".join(lines)
    await _safe_edit(callback_query, text)
    return AdminState.ADMIN_CHOOSE


async def _handle_a_backup(
    callback_query: CallbackQuery,
) -> int:
    """Send the database file as a backup document."""
    get_user_data(callback_query.from_user.id).pop("on_admin_main", None)
    db = get_db()
    with contextlib.suppress(Exception):
        await callback_query.message.reply_text("💾 در حال آمادهسازی بکاپ...")
    backup_path = None
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d")
        backup_path = os.path.join(tempfile.gettempdir(), f"database ({timestamp}).db")
        shutil.copy2(db.get_path(), backup_path)
        with open(backup_path, "rb") as f:
            await callback_query.message.reply_document(
                document=f,
                file_name=os.path.basename(backup_path),
                caption="✅ بکاپ دیتابیس",
            )
        logger.info("Database backup created: %s", backup_path)
    except Exception as exc:
        logger.error("Backup failed: %s", exc)
        with contextlib.suppress(Exception):
            await callback_query.message.reply_text(f"❌ خطا در بکاپ: {exc}")
    finally:
        if backup_path and os.path.exists(backup_path):
            with contextlib.suppress(OSError):
                os.remove(backup_path)
    return AdminState.ADMIN_CHOOSE


async def _handle_a_logs(
    callback_query: CallbackQuery,
) -> int:
    """Display recent log entries or send the log file."""
    get_user_data(callback_query.from_user.id).pop("on_admin_main", None)
    from config import cfg

    try:
        with open(cfg.LOG_FILE, encoding="utf-8") as f:
            lines = f.readlines()
        last = "".join(lines[-30:]) if lines else "لاگی موجود نیست."
        if len(last) > 3500:
            with open(cfg.LOG_FILE, "rb") as f:
                try:
                    await callback_query.message.reply_document(
                        f, file_name="bot.log", caption="📋 فایل لاگ کامل"
                    )
                except Exception as exc:
                    logger.warning("Failed to send log file: %s", exc)
                    await callback_query.message.reply_text("❌ خطا در ارسال فایل لاگ.")
        else:
            try:
                await callback_query.message.reply_text(f"```\n{last}\n```")
            except Exception as exc:
                logger.warning("Failed to send log text: %s", exc)
    except FileNotFoundError:
        with contextlib.suppress(Exception):
            await callback_query.message.reply_text("لاگی یافت نشد.")
    except Exception as exc:
        logger.error("Failed to read log file: %s", exc)
        with contextlib.suppress(Exception):
            await callback_query.message.reply_text("❌ خطا در خواندن فایل لاگ.")
    return AdminState.ADMIN_CHOOSE


async def _handle_a_edit_start(
    callback_query: CallbackQuery,
) -> int:
    """Prompt the admin to send a new /start message."""
    get_user_data(callback_query.from_user.id).pop("on_admin_main", None)
    await _safe_edit(callback_query, "متن جدید را بفرستید:")
    return AdminState.WAIT_START_MSG


async def h_start_msg_handler(client: Client, message: Message) -> int:
    """Save the new /start message text sent by the admin."""
    back = await _check_back(client, message)
    if back is not None:
        return back
    db = get_db()
    await db.set_setting("start_message", message.text)
    await message.reply_text(
        "✅ پیام استارت آپدیت شد.",
        reply_markup=None,
    )
    await message.reply_text(
        "🗽 **پنل مدیریت ربات**",
        reply_markup=admin_main_keyboard(),
    )
    return AdminState.ADMIN_CHOOSE


async def admin_cancel_handler(client: Client, message: Message) -> int:
    """Cancel the current admin conversation and return to the main menu."""
    user_id = message.from_user.id
    clear_state(user_id)
    await message.reply_text("❌ لغو شد.", reply_markup=admin_main_keyboard())
    return AdminState.ADMIN_CHOOSE


async def admin_back_to_main_handler(client: Client, message: Message) -> int:
    """Handle the back button — navigate up one level or exit admin panel."""
    user_id = message.from_user.id
    if message and message.text and message.text.strip() == "🔙 بازگشت":
        ud = get_user_data(user_id)
        if ud.get("on_admin_main"):
            clear_state(user_id)
            kb_text = "سلام! اینجا ربات نیکسو اسپاتیفای هست 🗽\n\nاز دکمه های زیر برای سرچ اسم خواننده، آلبوم یا آهنگ استفاده کن 👇"
            await message.reply_text(
                text="🏠",
                reply_markup=ReplyKeyboardRemove(),
            )
            await message.reply_text(
                text=kb_text,
                reply_markup=main_keyboard(is_admin(user_id)),
            )
            return -1  # END
        else:
            ud["on_admin_main"] = True
            await message.reply_text(
                "🗽 **پنل مدیریت ربات**",
                reply_markup=admin_main_keyboard(),
            )
            return AdminState.ADMIN_CHOOSE
    return -1  # END
