"""
⚠️ DEPRECATED: AI Chat functionality has been DISABLED to reduce token consumption.

This file is preserved for potential future re-enablement but is NOT currently used.
The handlers in this file are NOT registered in main.py.

---

AI Chat Handler (INACTIVE)

Handles natural language conversations with users.
AI has access to:
- User's profile/preferences
- Last 3 days of daily push content
- Google Search grounding for real-time information

Context Management:
- Conversation history is stored per-date in context.user_data["chat_history_by_date"]
- CHAT_CONTEXT_DAYS controls how many days of history to include (0=today only, 1=+yesterday, etc.)
- Users can manually clear history via /clear command or button
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes

from services.gemini import call_gemini_with_search
from utils.telegram_utils import safe_answer_callback_query
from utils.json_storage import (
    get_user,
    get_user_profile,
    get_user_raw_content,
    create_user,
    update_user_activity,
    get_user_setting,
    set_user_setting,
)
from config import CHAT_CONTEXT_DAYS

logger = logging.getLogger(__name__)

# Default context days if user hasn't set
DEFAULT_CONTEXT_DAYS = CHAT_CONTEXT_DAYS


def get_last_three_days_content(telegram_id: str) -> str:
    """
    Get the last 3 days of push content for the user.

    Returns formatted string of content summaries.
    """
    content_parts = []

    for i in range(3):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        raw_content = get_user_raw_content(telegram_id, date)

        if raw_content and raw_content.get("items"):
            items = raw_content["items"]
            date_label = "今天" if i == 0 else ("昨天" if i == 1 else "前天")
            content_parts.append(f"\n【{date_label} {date}】共 {len(items)} 条")

            # Include top items with title and summary
            for idx, item in enumerate(items[:10], 1):
                title = item.get("title", "无标题")
                summary = item.get("summary", "")[:100]
                source = item.get("source", "未知来源")
                content_parts.append(f"  {idx}. [{source}] {title}")
                if summary:
                    content_parts.append(f"     {summary}")

    if not content_parts:
        return "暂无最近三天的推送内容。"

    return "\n".join(content_parts)


def get_or_init_chat_history(context: ContextTypes.DEFAULT_TYPE, telegram_id: str) -> List[Dict[str, str]]:
    """
    Get chat history from context for the user's configured date range.

    对话历史按日期存储在 chat_history_by_date 中。
    根据用户设置的 chat_context_days 决定获取多少天的历史：
    - 0: 只获取今天的对话
    - 1: 获取今天和昨天的对话
    - 2: 获取今天、昨天和前天的对话

    Returns:
        Combined chat history for the configured date range
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # Get user's context days setting
    context_days = get_user_setting(telegram_id, "chat_context_days", DEFAULT_CONTEXT_DAYS)

    # Initialize chat_history_by_date if not exists
    if "chat_history_by_date" not in context.user_data:
        context.user_data["chat_history_by_date"] = {}

    # Ensure today's history exists
    if today not in context.user_data["chat_history_by_date"]:
        context.user_data["chat_history_by_date"][today] = []

    # Clean up old dates (keep only recent days based on config + 1 buffer)
    max_days_to_keep = max(context_days + 1, 3)
    cutoff_date = (datetime.now() - timedelta(days=max_days_to_keep)).strftime("%Y-%m-%d")
    dates_to_remove = [d for d in context.user_data["chat_history_by_date"] if d < cutoff_date]
    for d in dates_to_remove:
        del context.user_data["chat_history_by_date"][d]

    # Collect history for configured date range
    combined_history = []
    for i in range(context_days + 1):  # +1 to include today
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        if date in context.user_data["chat_history_by_date"]:
            day_history = context.user_data["chat_history_by_date"][date]
            # Add date marker for context
            if day_history and i > 0:
                date_label = "昨天" if i == 1 else f"{i}天前"
                combined_history.append({
                    "role": "system",
                    "content": f"--- {date_label}的对话 ---",
                    "date": date
                })
            combined_history.extend(day_history)

    return combined_history


def get_today_chat_history(context: ContextTypes.DEFAULT_TYPE) -> List[Dict[str, str]]:
    """Get only today's chat history (for adding new messages)."""
    today = datetime.now().strftime("%Y-%m-%d")

    if "chat_history_by_date" not in context.user_data:
        context.user_data["chat_history_by_date"] = {}

    if today not in context.user_data["chat_history_by_date"]:
        context.user_data["chat_history_by_date"][today] = []

    return context.user_data["chat_history_by_date"][today]


def add_to_chat_history(
    context: ContextTypes.DEFAULT_TYPE,
    user_message: str,
    ai_response: str
) -> None:
    """Add a conversation turn to today's history."""
    today_history = get_today_chat_history(context)

    today_history.append({
        "role": "user",
        "content": user_message
    })
    today_history.append({
        "role": "assistant",
        "content": ai_response
    })


def format_history_for_prompt(history: List[Dict[str, str]]) -> str:
    """Format chat history as context for the AI prompt."""
    if not history:
        return ""

    formatted = "\n## 对话历史\n"
    for msg in history:
        role = "用户" if msg["role"] == "user" else "助手"
        formatted += f"{role}: {msg['content']}\n"

    return formatted


def build_chat_system_prompt(telegram_id: str, history: List[Dict[str, str]]) -> str:
    """Build the system prompt with user context and chat history."""
    # Get user profile
    profile = get_user_profile(telegram_id) or "用户尚未设置偏好。"

    # Get recent content
    recent_content = get_last_three_days_content(telegram_id)

    # Format conversation history
    history_text = format_history_for_prompt(history)

    system_prompt = f"""你是 Web3 Daily Digest 的智能助手，帮助用户了解 Web3 和加密货币相关信息。

## 你的能力
1. 回答用户关于 Web3、加密货币、区块链的问题
2. 基于用户最近收到的推送内容回答问题
3. 使用联网搜索获取最新信息
4. 帮助用户理解市场动态

## 用户画像
{profile}

## 用户最近三天的推送内容
{recent_content}
{history_text}
## 回答准则
- 简洁明了，避免冗长
- 如果问题涉及最新信息，主动搜索验证
- 引用推送内容时注明来源
- 保持专业但友好的语气
- 使用中文回答
- 注意对话上下文的连贯性"""

    return system_prompt


async def handle_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages as AI chat."""
    user = update.effective_user
    telegram_id = str(user.id)
    message_text = update.message.text

    # Ensure user exists
    db_user = get_user(telegram_id)
    if not db_user:
        create_user(telegram_id, user.username, user.first_name)

    update_user_activity(telegram_id)

    # Get chat history (based on user's context days setting)
    history = get_or_init_chat_history(context, telegram_id)

    # Build system prompt with context and history
    system_prompt = build_chat_system_prompt(telegram_id, history)

    # Send typing indicator
    await update.message.chat.send_action("typing")

    try:
        # Call Gemini with search enabled
        response = await call_gemini_with_search(
            prompt=message_text,
            system_instruction=system_prompt,
            temperature=0.7,
        )

        # Add to history
        add_to_chat_history(context, message_text, response)

        # Navigation keyboard with clear button
        # 使用 chat_to_start 避免编辑 AI 回复内容
        keyboard = [[
            InlineKeyboardButton("清空对话", callback_data="clear_chat"),
            InlineKeyboardButton("主菜单", callback_data="chat_to_start"),
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send response
        await update.message.reply_text(
            response,
            reply_markup=reply_markup,
            parse_mode=None,  # Plain text to avoid formatting issues
        )

        logger.info(f"AI chat response sent to {telegram_id}")

    except Exception as e:
        logger.error(f"AI chat error for {telegram_id}: {e}")
        keyboard = [[
            InlineKeyboardButton("重试", callback_data="retry_chat"),
            InlineKeyboardButton("主菜单", callback_data="chat_to_start"),
        ]]
        # Store the failed message for retry
        context.user_data["last_failed_message"] = message_text
        await update.message.reply_text(
            "AI 服务暂时不可用，请稍后重试。",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def clear_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /clear command to manually clear today's chat history."""
    # 只清理当天的对话历史，保留之前的
    today = datetime.now().strftime("%Y-%m-%d")
    if "chat_history_by_date" in context.user_data:
        context.user_data["chat_history_by_date"][today] = []

    keyboard = [[
        InlineKeyboardButton("主菜单", callback_data="back_to_start"),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "今日对话已清空。\n\n"
        "你可以开始新的对话了。",
        reply_markup=reply_markup
    )

    logger.info(f"Today's chat history cleared by user: {update.effective_user.id}")


async def retry_chat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle retry_chat callback button to retry the last failed message."""
    query = update.callback_query
    await safe_answer_callback_query(query, "正在重试...")

    # Get the last failed message
    last_message = context.user_data.get("last_failed_message")
    if not last_message:
        await query.edit_message_text("没有需要重试的消息。")
        return

    telegram_id = query.from_user.id

    # Call the AI
    try:
        ai_response = await get_ai_response(telegram_id, last_message, context)

        # Clear the failed message
        context.user_data.pop("last_failed_message", None)

        # Send response
        keyboard = [[
            InlineKeyboardButton("清空对话", callback_data="clear_chat"),
            InlineKeyboardButton("主菜单", callback_data="chat_to_start"),
        ]]
        await query.edit_message_text(
            ai_response,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Retry chat error for {telegram_id}: {e}")
        keyboard = [[
            InlineKeyboardButton("重试", callback_data="retry_chat"),
            InlineKeyboardButton("主菜单", callback_data="chat_to_start"),
        ]]
        await query.edit_message_text(
            "AI 服务暂时不可用，请稍后重试。",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def clear_chat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle clear_chat callback button."""
    query = update.callback_query
    await safe_answer_callback_query(query, "今日对话已清空")

    # 只清理当天的对话历史，保留之前的
    today = datetime.now().strftime("%Y-%m-%d")
    if "chat_history_by_date" in context.user_data:
        context.user_data["chat_history_by_date"][today] = []

    keyboard = [[
        InlineKeyboardButton("主菜单", callback_data="chat_to_start"),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "今日对话已清空。\n\n"
        "你可以开始新的对话了。",
        reply_markup=reply_markup
    )

    logger.info(f"Today's chat history cleared by user: {update.effective_user.id}")


async def chat_to_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle chat_to_start callback - send new message instead of editing.

    从 AI 对话返回主菜单时，发送新消息而不是编辑 AI 回复，
    这样用户可以保留 AI 的回复内容。
    """
    query = update.callback_query
    await safe_answer_callback_query(query)

    from utils.json_storage import get_user

    user = update.effective_user
    telegram_id = str(user.id)
    existing_user = get_user(telegram_id)

    if existing_user:
        keyboard = [
            [InlineKeyboardButton("查看今日简报", callback_data="view_digest")],
            [
                InlineKeyboardButton("偏好设置", callback_data="update_preferences"),
                InlineKeyboardButton("信息源", callback_data="manage_sources"),
            ],
            [
                InlineKeyboardButton("查看统计", callback_data="view_stats"),
                InlineKeyboardButton("对话设置", callback_data="chat_context_settings"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # 发送新消息而不是编辑
        await query.message.reply_text(
            f"欢迎回来，{user.first_name}\n"
            f"{'─' * 24}\n\n"
            "你的个性化 Web3 情报简报。\n"
            "每日精选，智能推送。\n\n"
            "请选择操作：",
            reply_markup=reply_markup
        )
    else:
        keyboard = [
            [InlineKeyboardButton("开始使用", callback_data="start_onboarding")],
            [InlineKeyboardButton("了解更多", callback_data="learn_more")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_text(
            "Web3 每日简报\n"
            f"{'─' * 24}\n\n"
            "你的个性化情报助手。\n\n"
            "我们做什么：\n"
            "  • 每日扫描 50+ 信息源\n"
            "  • 过滤噪音，精选内容\n"
            "  • 推送真正重要的信息\n\n"
            "每天节省约 2 小时阅读时间",
            reply_markup=reply_markup
        )


def get_chat_handler() -> MessageHandler:
    """Get the message handler for AI chat.

    Note: This handler should be added LAST to handle messages
    that don't match any other handlers.
    """
    return MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_chat_message
    )


def get_clear_command_handler() -> CommandHandler:
    """Get the /clear command handler."""
    return CommandHandler("clear", clear_chat_command)


def get_clear_callback_handler() -> CallbackQueryHandler:
    """Get the clear_chat callback handler."""
    return CallbackQueryHandler(clear_chat_callback, pattern="^clear_chat$")


def get_chat_to_start_handler() -> CallbackQueryHandler:
    """Get the chat_to_start callback handler."""
    return CallbackQueryHandler(chat_to_start_callback, pattern="^chat_to_start$")


def get_retry_chat_handler() -> CallbackQueryHandler:
    """Get the retry_chat callback handler."""
    return CallbackQueryHandler(retry_chat_callback, pattern="^retry_chat$")


# ============ Chat Context Settings ============

async def show_context_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show chat context days settings."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    telegram_id = str(update.effective_user.id)
    current_days = get_user_setting(telegram_id, "chat_context_days", DEFAULT_CONTEXT_DAYS)

    # Build options with checkmark for current setting
    options = []
    for days in [0, 1, 2]:
        label = ["只用当天", "包含昨天", "包含前天"][days]
        if days == current_days:
            label = f"✓ {label}"
        options.append(InlineKeyboardButton(label, callback_data=f"set_context_days_{days}"))

    keyboard = [
        options,
        [InlineKeyboardButton("返回", callback_data="back_to_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "对话上下文设置\n"
        f"{'─' * 24}\n\n"
        "设置 AI 对话时获取多少天的历史上下文：\n\n"
        "  • 只用当天 - 每天从头开始\n"
        "  • 包含昨天 - AI 能记住昨天的对话\n"
        "  • 包含前天 - AI 能记住近3天对话\n\n"
        f"当前设置：{['只用当天', '包含昨天', '包含前天'][current_days]}",
        reply_markup=reply_markup
    )


async def set_context_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle setting context days."""
    query = update.callback_query

    # Extract days from callback data: set_context_days_0/1/2
    days = int(query.data.split("_")[-1])
    telegram_id = str(update.effective_user.id)

    set_user_setting(telegram_id, "chat_context_days", days)

    labels = ["只用当天", "包含昨天", "包含前天"]
    await safe_answer_callback_query(query, f"已设置为：{labels[days]}")

    # Refresh the settings view
    await show_context_settings(update, context)


def get_context_settings_handler() -> CallbackQueryHandler:
    """Get the context settings callback handler."""
    return CallbackQueryHandler(show_context_settings, pattern="^chat_context_settings$")


def get_set_context_days_handler() -> CallbackQueryHandler:
    """Get the set context days callback handler."""
    return CallbackQueryHandler(set_context_days_callback, pattern="^set_context_days_[0-2]$")
