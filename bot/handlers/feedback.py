"""
Telegram Bot Feedback Handler

Handles feedback collection through inline keyboard buttons.
Supports overall rating, reason selection, and item-level feedback.

Reference: python-telegram-bot v22.x (Exa verified 2025-01-12)
"""
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from utils.telegram_utils import safe_answer_callback_query
from utils.json_storage import save_feedback, get_user

logger = logging.getLogger(__name__)

# Conversation states for feedback flow
SELECTING_REASON, ENTERING_CUSTOM_REASON = range(2)


def create_feedback_keyboard(report_id: str) -> InlineKeyboardMarkup:
    """Create the main feedback buttons for a report."""
    keyboard = [
        [
            InlineKeyboardButton("有帮助", callback_data=f"fb_positive_{report_id}"),
            InlineKeyboardButton("没帮助", callback_data=f"fb_negative_{report_id}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_reason_keyboard(report_id: str) -> InlineKeyboardMarkup:
    """Create reason selection buttons for negative feedback."""
    keyboard = [
        [
            InlineKeyboardButton("内容不相关", callback_data=f"reason_not_relevant_{report_id}"),
            InlineKeyboardButton("漏掉重要信息", callback_data=f"reason_missed_{report_id}"),
        ],
        [
            InlineKeyboardButton("信息太多", callback_data=f"reason_too_much_{report_id}"),
            InlineKeyboardButton("信息太少", callback_data=f"reason_too_few_{report_id}"),
        ],
        [InlineKeyboardButton("主题不对", callback_data=f"reason_wrong_topics_{report_id}")],
        [InlineKeyboardButton("其他", callback_data=f"reason_other_{report_id}")],
        [InlineKeyboardButton("取消", callback_data="feedback_cancel")],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_item_feedback_keyboard(item_id: str, lang: str = "zh") -> InlineKeyboardMarkup:
    """
    Create feedback buttons for individual items.
    
    Buttons:
    - 👍 (Like)
    - "不感兴趣" / "Not interested" (instead of 👎)
    
    Args:
        item_id: Item identifier for callback data
        lang: Language code for button text
    
    Returns:
        InlineKeyboardMarkup with feedback buttons
    """
    # Get localized button text
    from services.report_generator import get_locale
    locale = get_locale(lang)
    
    like_text = locale.get("btn_like", "👍")
    not_interested_text = locale.get("btn_not_interested", "不感兴趣")
    
    keyboard = [
        [
            InlineKeyboardButton(like_text, callback_data=f"item_like_{item_id}"),
            InlineKeyboardButton(not_interested_text, callback_data=f"item_dislike_{item_id}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_item_feedback_status(item_id: str) -> str:
    """
    Check if an item has already received feedback.
    Returns "like", "dislike", or empty string if no feedback.
    """
    from utils.json_storage import FEEDBACK_DIR
    from datetime import datetime
    import os
    import json

    today = datetime.now().strftime("%Y-%m-%d")
    feedback_path = os.path.join(FEEDBACK_DIR, f"{today}.json")

    if not os.path.exists(feedback_path):
        return ""

    try:
        with open(feedback_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Check all feedbacks for this item_id
        for feedback in data.get("feedbacks", []):
            for item_fb in feedback.get("item_feedbacks", []):
                if item_fb.get("item_id") == item_id:
                    return item_fb.get("feedback", "")
    except Exception:
        return ""

    return ""


async def handle_feedback_positive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle positive feedback."""

    query = update.callback_query
    await safe_answer_callback_query(query)

    user = update.effective_user
    telegram_id = str(user.id)

    # Extract report ID from callback data
    callback_data = query.data
    report_id = callback_data.replace("fb_positive_", "")

    # Get accumulated item feedbacks from session
    item_feedbacks = context.user_data.get("item_feedbacks", [])

    # Save positive feedback with item feedbacks
    save_feedback(
        telegram_id=telegram_id,
        overall_rating="positive",
        item_feedbacks=item_feedbacks,
    )

    # Clear item feedbacks after saving
    context.user_data.pop("item_feedbacks", None)

    await query.edit_message_text(
        query.message.text + "\n\n---\n感谢你的反馈。"
    )

    logger.info(f"Positive feedback from {telegram_id} for report {report_id}")

    return ConversationHandler.END


async def handle_feedback_negative(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle negative feedback - show reason selection."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    callback_data = query.data
    report_id = callback_data.replace("fb_negative_", "")

    # Store report_id for later
    context.user_data["feedback_report_id"] = report_id

    reply_markup = create_reason_keyboard(report_id)

    await query.edit_message_text(
        f"反馈\n"
        f"{'─' * 24}\n\n"
        "有什么可以改进的？\n\n"
        "请选择原因：",
        reply_markup=reply_markup
    )

    return SELECTING_REASON


async def handle_reason_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle reason selection for negative feedback."""

    query = update.callback_query
    await safe_answer_callback_query(query)

    user = update.effective_user
    telegram_id = str(user.id)
    callback_data = query.data

    if callback_data == "feedback_cancel":
        await query.edit_message_text("已取消反馈。")
        return ConversationHandler.END

    # Parse reason from callback data
    reason_map = {
        "reason_not_relevant_": "内容不相关",
        "reason_missed_": "漏掉重要信息",
        "reason_too_much_": "信息太多",
        "reason_too_few_": "信息太少",
        "reason_wrong_topics_": "主题不对",
    }

    selected_reason = None
    for prefix, reason_text in reason_map.items():
        if callback_data.startswith(prefix):
            selected_reason = reason_text
            break

    if callback_data.startswith("reason_other_"):
        context.user_data["feedback_reason_selected"] = ["其他"]
        await query.edit_message_text(
            "请输入你的反馈意见："
        )
        return ENTERING_CUSTOM_REASON

    if selected_reason:
        # Get accumulated item feedbacks from session
        item_feedbacks = context.user_data.get("item_feedbacks", [])

        # Save feedback with selected reason and item feedbacks
        save_feedback(
            telegram_id=telegram_id,
            overall_rating="negative",
            reason_selected=[selected_reason],
            item_feedbacks=item_feedbacks,
        )

        # Clear item feedbacks after saving
        context.user_data.pop("item_feedbacks", None)

        await query.edit_message_text(
            f"已收到反馈\n"
            f"{'─' * 24}\n\n"
            f"问题：{selected_reason}\n\n"
            "我们会调整你的偏好设置。"
        )

        logger.info(f"Negative feedback from {telegram_id}: {selected_reason}")

    return ConversationHandler.END


async def handle_custom_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom text reason for negative feedback."""

    user = update.effective_user
    telegram_id = str(user.id)
    custom_text = update.message.text

    # Get accumulated item feedbacks from session
    item_feedbacks = context.user_data.get("item_feedbacks", [])

    # Save feedback with custom reason and item feedbacks
    save_feedback(
        telegram_id=telegram_id,
        overall_rating="negative",
        reason_selected=context.user_data.get("feedback_reason_selected", []),
        reason_text=custom_text,
        item_feedbacks=item_feedbacks,
    )

    await update.message.reply_text(
        f"已收到反馈\n"
        f"{'─' * 24}\n\n"
        "感谢你的详细反馈。\n"
        "我们会用它来改进你的简报。"
    )

    logger.info(f"Custom feedback from {telegram_id}: {custom_text[:50]}...")

    # Clear user data
    context.user_data.pop("feedback_reason_selected", None)
    context.user_data.pop("feedback_report_id", None)
    context.user_data.pop("item_feedbacks", None)

    return ConversationHandler.END


async def handle_item_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle like/dislike feedback on individual content items."""

    query = update.callback_query

    user = update.effective_user
    telegram_id = str(user.id)
    callback_data = query.data

    # Parse item feedback (only like/dislike)
    if callback_data.startswith("item_like_"):
        item_id = callback_data.replace("item_like_", "")
        feedback_type = "like"
        response = "👍 已记录"
        indicator = "👍"
    elif callback_data.startswith("item_dislike_"):
        item_id = callback_data.replace("item_dislike_", "")
        feedback_type = "dislike"
        response = "👎 已记录"
        indicator = "👎"
    else:
        await safe_answer_callback_query(query)
        return

    # Extract item content from the message for profile update
    # The message contains the news title and source
    original_text = query.message.text or ""
    # Try to extract title (first line after emoji indicator)
    lines = original_text.split("\n")
    item_title = lines[0] if lines else "Unknown"
    # Clean up the title (remove emoji indicators like 🔴 🔵 and numbering)
    import re
    item_title = re.sub(r'^[🔴🔵]\s*\d+\.\s*', '', item_title).strip()
    item_title = re.sub(r'<[^>]+>', '', item_title)  # Remove HTML tags

    # Store item feedback in memory (for later aggregation)
    item_feedbacks = context.user_data.get("item_feedbacks", [])
    item_feedbacks.append({
        "item_id": item_id,
        "feedback": feedback_type,
        "title": item_title,
    })
    context.user_data["item_feedbacks"] = item_feedbacks

    # IMPORTANT: Also save immediately to file for real-time statistics
    # Create a lightweight feedback record for this single item
    from utils.json_storage import save_feedback
    save_feedback(
        telegram_id=telegram_id,
        overall_rating="positive" if feedback_type == "like" else "neutral",
        item_feedbacks=[{
            "item_id": item_id,
            "feedback": feedback_type,
            "title": item_title,
        }]
    )

    # Show visual confirmation with indicator
    await safe_answer_callback_query(query, f"{response}", show_alert=False)

    # Remove feedback buttons but keep original message (preserves HTML links)
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass  # Message may already be edited

    logger.info(f"Item feedback from {telegram_id}: {feedback_type} on '{item_title[:30]}'")


def get_feedback_handlers():
    """Create and return all feedback-related handlers."""
    # Main feedback conversation handler
    feedback_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_feedback_positive, pattern=r"^fb_positive_"),
            CallbackQueryHandler(handle_feedback_negative, pattern=r"^fb_negative_"),
        ],
        states={
            SELECTING_REASON: [
                CallbackQueryHandler(handle_reason_selection, pattern=r"^reason_"),
                CallbackQueryHandler(handle_reason_selection, pattern=r"^feedback_cancel$"),
            ],
            ENTERING_CUSTOM_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_reason),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(handle_reason_selection, pattern=r"^feedback_cancel$"),
        ],
        per_message=True,
    )

    # Item-level feedback handler
    item_handler = CallbackQueryHandler(handle_item_feedback, pattern=r"^item_")

    return feedback_conv, item_handler
