"""
Telegram Bot Settings Handler

Handles /settings command for users to view and update their preferences.
Supports viewing current profile and re-running preference setup.

Reference: python-telegram-bot v22.x (Exa verified 2025-01-12)
"""
import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from services.gemini import call_gemini
from utils.prompt_loader import get_prompt
from utils.telegram_utils import safe_answer_callback_query
from utils.json_storage import (
    get_user,
    get_user_profile,
    save_user_profile,
)

logger = logging.getLogger(__name__)

# Conversation states
(AWAITING_PROFILE_UPDATE,) = range(1)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings command - show settings menu."""
    user = update.effective_user
    telegram_id = str(user.id)

    db_user = get_user(telegram_id)
    if not db_user:
        await update.message.reply_text(
            "你还没有注册。请使用 /start 开始。"
        )
        return

    keyboard = [
        [InlineKeyboardButton("查看偏好", callback_data="settings_view")],
        [
            InlineKeyboardButton("更新", callback_data="settings_update"),
            InlineKeyboardButton("重置", callback_data="settings_reset"),
        ],
        [InlineKeyboardButton("返回", callback_data="back_to_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"偏好设置\n"
        f"{'─' * 24}\n\n"
        "管理你的偏好设置：\n"
        "  • 查看当前偏好\n"
        "  • 更新兴趣领域\n"
        "  • 重置为默认",
        reply_markup=reply_markup
    )


async def view_current_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's current preference profile."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    user = update.effective_user
    telegram_id = str(user.id)

    profile = get_user_profile(telegram_id)

    if profile:
        text = (
            f"你的偏好设置\n"
            f"{'─' * 24}\n\n"
            f"{html.escape(profile)}\n\n"
            f"{'─' * 24}\n"
            "使用 /settings 修改偏好。"
        )
    else:
        text = (
            f"你的偏好设置\n"
            f"{'─' * 24}\n\n"
            "还没有设置偏好。\n\n"
            "使用 /start 开始设置。"
        )

    keyboard = [[InlineKeyboardButton("返回", callback_data="settings_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)


async def start_profile_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the profile update conversation."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    user = update.effective_user
    telegram_id = str(user.id)

    profile = get_user_profile(telegram_id)

    if profile:
        await query.edit_message_text(
            f"更新偏好\n"
            f"{'─' * 24}\n\n"
            "当前偏好：\n"
            f"{html.escape(profile)}\n\n"
            f"{'─' * 24}\n\n"
            "你想修改什么？\n\n"
            "示例：\n"
            "  • '增加 DeFi 内容'\n"
            "  • '减少 NFT 相关'\n"
            "  • '关注 Arbitrum'\n\n"
            "请输入或 /cancel 取消："
        )
    else:
        await query.edit_message_text(
            f"更新偏好\n"
            f"{'─' * 24}\n\n"
            "还没有设置偏好。\n\n"
            "请描述你的兴趣：\n\n"
            "示例：'我对 DeFi 感兴趣，\n"
            "主要关注 Uniswap 和 Aave。\n"
            "我关注 Solana 和以太坊。'\n\n"
            "请输入或 /cancel 取消："
        )

    return AWAITING_PROFILE_UPDATE


async def handle_profile_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle user's profile update input."""
    user = update.effective_user
    telegram_id = str(user.id)
    user_input = update.message.text

    # Get current profile
    current_profile = get_user_profile(telegram_id) or ""

    # Load prompt from file
    system_instruction = get_prompt(
        "settings_update.txt",
        current_profile=current_profile or "No existing profile",
        user_input=user_input
    )

    try:
        updated_profile = await call_gemini(
            prompt=f"Update profile with: {user_input}",
            system_instruction=system_instruction,
            temperature=0.5
        )

        # Save updated profile
        save_user_profile(telegram_id, updated_profile)

        await update.message.reply_text(
            f"偏好已更新\n"
            f"{'─' * 24}\n\n"
            f"{html.escape(updated_profile)}\n\n"
            f"{'─' * 24}\n"
            "下次简报将反映这些变化。"
        )

        logger.info(f"Updated profile for {telegram_id}")

    except Exception as e:
        logger.error(f"Failed to update profile for {telegram_id}: {e}")
        keyboard = [
            [InlineKeyboardButton("重试", callback_data="settings_update")],
            [InlineKeyboardButton("返回设置", callback_data="settings_back")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "暂时无法更新偏好。\n\n"
            "可能是临时问题，请稍后重试。",
            reply_markup=reply_markup
        )

    return ConversationHandler.END


async def confirm_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask for confirmation before resetting preferences."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    keyboard = [
        [
            InlineKeyboardButton("取消", callback_data="settings_back"),
            InlineKeyboardButton("确认重置", callback_data="settings_reset_confirm"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"重置偏好\n"
        f"{'─' * 24}\n\n"
        "这将删除你当前的偏好设置。\n"
        "你需要重新设置。\n\n"
        "确定要重置吗？",
        reply_markup=reply_markup
    )


async def execute_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Execute profile reset."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    user = update.effective_user
    telegram_id = str(user.id)

    # Reset profile to default
    default_profile = """[用户类型]
Web3 新用户，通用兴趣

[关注领域]
- Web3 综合新闻
- 主要生态系统更新
- 市场重大动态

[内容偏好]
- 新闻和分析均衡
- 适中数量 (10-15 条)

[明确不喜欢]
- 暂无"""

    save_user_profile(telegram_id, default_profile)

    await query.edit_message_text(
        f"偏好已重置\n"
        f"{'─' * 24}\n\n"
        "你的偏好已重置为默认设置。\n\n"
        "使用 /settings 自定义。"
    )

    logger.info(f"Reset profile for {telegram_id}")


async def settings_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return to settings menu."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    keyboard = [
        [InlineKeyboardButton("查看偏好", callback_data="settings_view")],
        [
            InlineKeyboardButton("更新", callback_data="settings_update"),
            InlineKeyboardButton("重置", callback_data="settings_reset"),
        ],
        [InlineKeyboardButton("返回", callback_data="back_to_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"偏好设置\n"
        f"{'─' * 24}\n\n"
        "管理你的偏好设置：\n"
        "  • 查看当前偏好\n"
        "  • 更新兴趣领域\n"
        "  • 重置为默认",
        reply_markup=reply_markup
    )


async def cancel_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel settings conversation."""
    keyboard = [
        [
            InlineKeyboardButton("设置", callback_data="settings_back"),
            InlineKeyboardButton("主菜单", callback_data="back_to_start"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "已取消。\n\n"
        "随时可以重新开始。",
        reply_markup=reply_markup
    )
    return ConversationHandler.END


def get_settings_handler() -> ConversationHandler:
    """Create and return the settings conversation handler."""
    return ConversationHandler(
        entry_points=[
            CommandHandler("settings", settings_command),
            CallbackQueryHandler(start_profile_update, pattern="^settings_update$"),
        ],
        states={
            AWAITING_PROFILE_UPDATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_profile_update),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_settings),
        ],
    )


def get_settings_callbacks():
    """Get standalone callback handlers for settings menu."""
    return [
        CallbackQueryHandler(view_current_profile, pattern="^settings_view$"),
        CallbackQueryHandler(confirm_reset, pattern="^settings_reset$"),
        CallbackQueryHandler(execute_reset, pattern="^settings_reset_confirm$"),
        CallbackQueryHandler(settings_back, pattern="^settings_back$"),
    ]
