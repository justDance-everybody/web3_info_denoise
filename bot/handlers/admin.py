"""
Admin Handlers for Whitelist Management.
Provides both command handlers and callback button handlers.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters

from utils.json_storage import (
    get_whitelist, add_to_whitelist, remove_from_whitelist, get_users,
    get_whitelist_enabled, set_whitelist_enabled
)

logger = logging.getLogger(__name__)

# Conversation state for adding user
WAITING_FOR_USER_ID = 100


def is_admin(user_id: int) -> bool:
    """Check if user is admin. Supports multiple admins from env variable."""
    from config import ADMIN_TELEGRAM_IDS
    return str(user_id) in ADMIN_TELEGRAM_IDS


def get_user_info(telegram_id: int) -> dict:
    """Get user info from users.json by telegram_id."""
    users = get_users()
    for user in users:
        if str(user.get("telegram_id")) == str(telegram_id):
            return user
    return None


# ============ Button-based Admin Panel ============

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel with buttons (callback handler)."""
    query = update.callback_query
    if query:
        await query.answer()
        user_id = query.from_user.id
    else:
        user_id = update.effective_user.id

    if not is_admin(user_id):
        if query:
            await query.answer("🔒 无权限", show_alert=True)
        return

    # Get current whitelist status
    wl_enabled = get_whitelist_enabled()
    wl_status = "🟢 已开启" if wl_enabled else "🔴 已关闭"
    toggle_text = "关闭白名单" if wl_enabled else "开启白名单"
    toggle_emoji = "🔴" if wl_enabled else "🟢"

    keyboard = [
        [InlineKeyboardButton(f"{toggle_emoji} {toggle_text}", callback_data="admin_wl_toggle")],
        [InlineKeyboardButton("📋 查看白名单", callback_data="admin_wl_list")],
        [
            InlineKeyboardButton("➕ 添加用户", callback_data="admin_wl_add"),
            InlineKeyboardButton("➖ 删除用户", callback_data="admin_wl_del"),
        ],
        [InlineKeyboardButton("« 返回主菜单", callback_data="back_to_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    whitelist = get_whitelist()
    text = (
        "🛡️ <b>管理员控制台</b>\n"
        f"{'─' * 24}\n\n"
        f"白名单状态: {wl_status}\n"
        f"白名单人数: {len(whitelist)} 人\n\n"
        "请选择操作："
    )

    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def admin_wl_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle whitelist enabled/disabled."""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("🔒 无权限", show_alert=True)
        return

    # Toggle the status
    current = get_whitelist_enabled()
    new_status = not current
    set_whitelist_enabled(new_status)
    
    status_text = "开启" if new_status else "关闭"
    await query.answer(f"✅ 白名单已{status_text}", show_alert=True)
    logger.info(f"Admin {query.from_user.id} toggled whitelist to {new_status}")
    
    # Refresh the panel
    await admin_panel(update, context)


async def admin_wl_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show whitelist with user details (callback handler)."""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.answer("🔒 无权限", show_alert=True)
        return

    whitelist = get_whitelist()

    if not whitelist:
        text = "📋 <b>白名单为空</b>\n\n暂无授权用户。"
    else:
        text = f"📋 <b>白名单用户 ({len(whitelist)} 人)</b>\n"
        text += f"{'─' * 24}\n\n"

        for uid in whitelist:
            user_info = get_user_info(uid)
            if user_info:
                username = user_info.get("username") or "无"
                first_name = user_info.get("first_name") or "未知"
                created = user_info.get("created", "")[:10] if user_info.get("created") else "未知"
                text += f"• <b>{first_name}</b>\n"
                text += f"  ID: <code>{uid}</code>\n"
                text += f"  用户名: @{username}\n"
                text += f"  注册: {created}\n\n"
            else:
                text += f"• ID: <code>{uid}</code> (未注册)\n\n"

    keyboard = [[InlineKeyboardButton("« 返回管理面板", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def admin_wl_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt admin to enter user ID to add."""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.answer("🔒 无权限", show_alert=True)
        return

    keyboard = [[InlineKeyboardButton("取消", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "➕ <b>添加用户到白名单</b>\n\n"
        "请发送要添加的用户 Telegram ID（纯数字）：",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

    context.user_data["admin_action"] = "add"
    return WAITING_FOR_USER_ID


async def admin_wl_del_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt admin to enter user ID to remove."""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.answer("🔒 无权限", show_alert=True)
        return

    keyboard = [[InlineKeyboardButton("取消", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "➖ <b>从白名单删除用户</b>\n\n"
        "请发送要删除的用户 Telegram ID（纯数字）：",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

    context.user_data["admin_action"] = "del"
    return WAITING_FOR_USER_ID


async def handle_user_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user ID input for add/delete operations."""
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    text = update.message.text.strip()
    action = context.user_data.get("admin_action")

    try:
        target_id = int(text)
    except ValueError:
        await update.message.reply_text("❌ 请输入有效的数字 ID。")
        return WAITING_FOR_USER_ID

    keyboard = [[InlineKeyboardButton("« 返回管理面板", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if action == "add":
        if add_to_whitelist(target_id):
            user_info = get_user_info(target_id)
            if user_info:
                name = user_info.get("first_name") or "用户"
                await update.message.reply_text(
                    f"✅ 已添加 <b>{name}</b> (<code>{target_id}</code>) 到白名单。",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(
                    f"✅ 已添加 <code>{target_id}</code> 到白名单。\n（该用户尚未注册）",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            logger.info(f"Admin added {target_id} to whitelist")
        else:
            await update.message.reply_text("❌ 添加失败，请检查日志。", reply_markup=reply_markup)

    elif action == "del":
        if remove_from_whitelist(target_id):
            await update.message.reply_text(
                f"🗑️ 已从白名单移除 <code>{target_id}</code>。",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            logger.info(f"Admin removed {target_id} from whitelist")
        else:
            await update.message.reply_text("⚠️ 该用户不在白名单中。", reply_markup=reply_markup)

    context.user_data.pop("admin_action", None)
    return ConversationHandler.END


async def cancel_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel admin action and return to panel."""
    context.user_data.pop("admin_action", None)
    await admin_panel(update, context)
    return ConversationHandler.END


# ============ Legacy Command Handlers (kept for compatibility) ============

async def wl_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List whitelisted users (command version)."""
    if not is_admin(update.effective_user.id):
        return

    whitelist = get_whitelist()
    if not whitelist:
        await update.message.reply_text("📋 白名单为空。")
        return

    text = f"📋 <b>白名单用户 ({len(whitelist)} 人)</b>\n\n"
    for uid in whitelist:
        user_info = get_user_info(uid)
        if user_info:
            name = user_info.get("first_name") or "未知"
            username = user_info.get("username") or "无"
            text += f"• {name} | @{username} | <code>{uid}</code>\n"
        else:
            text += f"• <code>{uid}</code> (未注册)\n"

    await update.message.reply_text(text, parse_mode='HTML')


async def wl_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add user to whitelist (command version)."""
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("⚠️ 用法: /wl_add <用户ID>")
        return

    try:
        target_id = int(context.args[0])
        if add_to_whitelist(target_id):
            await update.message.reply_text(f"✅ 已添加 <code>{target_id}</code> 到白名单。", parse_mode='HTML')
            logger.info(f"Admin added {target_id} to whitelist")
        else:
            await update.message.reply_text("❌ 添加失败。")
    except ValueError:
        await update.message.reply_text("❌ ID 必须是数字。")


async def wl_del_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove user from whitelist (command version)."""
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("⚠️ 用法: /wl_del <用户ID>")
        return

    try:
        target_id = int(context.args[0])
        if remove_from_whitelist(target_id):
            await update.message.reply_text(f"🗑️ 已移除 <code>{target_id}</code>。", parse_mode='HTML')
            logger.info(f"Admin removed {target_id} from whitelist")
        else:
            await update.message.reply_text("⚠️ 用户不在白名单中。")
    except ValueError:
        await update.message.reply_text("❌ ID 必须是数字。")


# ============ Handler Registration ============

def get_admin_handlers():
    """Return all admin-related handlers."""
    # ConversationHandler for add/delete flow
    admin_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_wl_add_callback, pattern="^admin_wl_add$"),
            CallbackQueryHandler(admin_wl_del_callback, pattern="^admin_wl_del$"),
        ],
        states={
            WAITING_FOR_USER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_id_input),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_admin_action, pattern="^admin_panel$"),
        ],
        per_message=False,
    )

    return [
        # Button-based handlers
        CallbackQueryHandler(admin_panel, pattern="^admin_panel$"),
        CallbackQueryHandler(admin_wl_toggle_callback, pattern="^admin_wl_toggle$"),
        CallbackQueryHandler(admin_wl_list_callback, pattern="^admin_wl_list$"),
        admin_conv,
        # Command handlers (legacy, still work)
        CommandHandler("admin", admin_panel),
        CommandHandler("wl_list", wl_list_command),
        CommandHandler("wl_add", wl_add_command),
        CommandHandler("wl_del", wl_del_command),
    ]
