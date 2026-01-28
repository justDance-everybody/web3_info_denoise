"""
Authentication and Authorization Utilities.
"""
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
import logging

from utils.json_storage import is_whitelisted

logger = logging.getLogger(__name__)

def whitelist_required(func):
    """
    Decorator to restrict access to whitelisted users and admins only.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user:
            return await func(update, context, *args, **kwargs)
            
        if is_whitelisted(user.id):
            return await func(update, context, *args, **kwargs)
            
        # Access denied logic
        logger.warning(f"Unauthorized access attempt from user {user.id} ({user.username})")
        
        message = (
            "⛔️ <b>未获授权访问</b>\n\n"
            "抱歉，该机器人目前仅限内部使用。\n\n"
            "如果您希望使用此服务，请将下方的 ID 发送给<b>群管理员</b>申请白名单：\n\n"
            f"🆔 您的 ID: <code>{user.id}</code>"
        )
        
        if update.callback_query:
            await update.callback_query.answer("⛔️ 您未获授权使用此功能", show_alert=True)
            # Optional: edit message text or send new message if needed
        elif update.message:
            await update.message.reply_text(message, parse_mode='HTML')
            
        return # Stop execution
        
    return wrapper
