"""
Telegram Bot Sources Handler

Handles /sources command for users to view and manage information sources.
Allows viewing current sources and suggesting new ones.

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

from services.rss_fetcher import get_user_source_list
from utils.telegram_utils import safe_answer_callback_query
from utils.json_storage import get_user, add_user_source, remove_user_source

logger = logging.getLogger(__name__)

# Conversation states
AWAITING_SOURCE_SUGGESTION, AWAITING_TWITTER_ADD, AWAITING_WEBSITE_ADD, AWAITING_BULK_IMPORT = range(4)


async def sources_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /sources command - show sources menu."""
    user = update.effective_user
    telegram_id = str(user.id)

    db_user = get_user(telegram_id)
    if not db_user:
        await update.message.reply_text(
            "你还没有注册。请使用 /start 开始。"
        )
        return

    keyboard = [
        [
            InlineKeyboardButton("Twitter", callback_data="sources_twitter"),
            InlineKeyboardButton("网站", callback_data="sources_websites"),
        ],
        [InlineKeyboardButton("批量导入", callback_data="sources_bulk_import")],
        [InlineKeyboardButton("推荐信息源", callback_data="sources_suggest")],
        [InlineKeyboardButton("返回", callback_data="back_to_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Get source counts for this user
    sources = get_user_source_list(telegram_id)
    twitter_count = len(sources.get("twitter", []))
    website_count = len(sources.get("websites", []))

    await update.message.reply_text(
        f"信息源管理\n"
        f"{'─' * 24}\n\n"
        f"当前监控：\n"
        f"  • Twitter 账号: {twitter_count}\n"
        f"  • 网站 RSS: {website_count}\n\n"
        "选择分类查看详情。",
        reply_markup=reply_markup
    )


async def view_twitter_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show list of monitored Twitter accounts."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    telegram_id = str(query.from_user.id)
    sources = get_user_source_list(telegram_id)
    twitter_sources = sources.get("twitter", [])

    if twitter_sources:
        lines = [
            f"Twitter 信息源\n"
            f"{'─' * 24}\n"
        ]
        for i, source in enumerate(twitter_sources, 1):
            lines.append(f"  {i}. {source}")
        lines.append(f"\n共 {len(twitter_sources)} 个账号")
        text = "\n".join(lines)
    else:
        text = (
            f"Twitter 信息源\n"
            f"{'─' * 24}\n\n"
            "还没有配置 Twitter 信息源。\n\n"
            "点击「添加 Twitter」添加账号。"
        )

    keyboard = [
        [InlineKeyboardButton("添加 Twitter", callback_data="sources_add_twitter")],
    ]
    if twitter_sources:
        keyboard.append([InlineKeyboardButton("删除 Twitter", callback_data="sources_del_twitter")])
    keyboard.append([InlineKeyboardButton("返回", callback_data="sources_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)


async def view_website_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show list of monitored website RSS feeds."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    telegram_id = str(query.from_user.id)
    sources = get_user_source_list(telegram_id)
    website_sources = sources.get("websites", [])

    if website_sources:
        lines = [
            f"网站信息源\n"
            f"{'─' * 24}\n"
        ]
        for i, source in enumerate(website_sources, 1):
            lines.append(f"  {i}. {source}")
        lines.append(f"\n共 {len(website_sources)} 个网站")
        text = "\n".join(lines)
    else:
        text = (
            f"网站信息源\n"
            f"{'─' * 24}\n\n"
            "还没有配置网站信息源。\n\n"
            "点击「添加网站」添加 RSS 源。"
        )

    keyboard = [
        [InlineKeyboardButton("添加网站", callback_data="sources_add_website")],
    ]
    if website_sources:
        keyboard.append([InlineKeyboardButton("删除网站", callback_data="sources_del_website")])
    keyboard.append([InlineKeyboardButton("返回", callback_data="sources_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)


async def start_source_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the source suggestion conversation."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    await query.edit_message_text(
        f"推荐信息源\n"
        f"{'─' * 24}\n\n"
        "告诉我们你想监控的信息源。\n\n"
        "示例：\n"
        "  • @DefiLlama - DeFi 分析\n"
        "  • defillama.com - TVL 追踪\n\n"
        "请输入或 /cancel 取消："
    )

    return AWAITING_SOURCE_SUGGESTION


async def start_add_twitter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start adding a Twitter account."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    await query.edit_message_text(
        f"添加 Twitter 账号\n"
        f"{'─' * 24}\n\n"
        "请输入 Twitter 账号和 RSS 地址。\n\n"
        "格式：\n"
        "  账号名 | RSS 地址\n\n"
        "示例：\n"
        "  @VitalikButerin | https://rss.app/feeds/xxx\n"
        "  lookonchain | https://nitter.net/lookonchain/rss\n\n"
        "提示：可使用 rss.app 或 nitter 获取 RSS\n\n"
        "请输入或 /cancel 取消："
    )

    return AWAITING_TWITTER_ADD


async def handle_twitter_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle Twitter account addition."""
    from services.rss_fetcher import validate_twitter_handle, validate_url

    telegram_id = str(update.effective_user.id)
    user_input = update.message.text.strip()

    # Parse input: "handle | URL" format
    if "|" in user_input:
        parts = user_input.split("|", 1)
        handle = parts[0].strip()
        url = parts[1].strip()
    else:
        # No URL provided
        handle = user_input
        url = ""

    # Validate Twitter handle
    validation = await validate_twitter_handle(handle)
    if not validation["valid"]:
        keyboard = [
            [InlineKeyboardButton("重试", callback_data="sources_add_twitter")],
            [InlineKeyboardButton("返回", callback_data="sources_twitter")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"添加失败\n"
            f"{'─' * 24}\n\n"
            f"{html.escape(validation['error'])}\n\n"
            "请重试。",
            reply_markup=reply_markup
        )
        return ConversationHandler.END

    handle = validation["handle"]

    # Validate URL if provided
    if url:
        url_validation = await validate_url(url)
        if not url_validation["valid"]:
            keyboard = [
                [InlineKeyboardButton("重试", callback_data="sources_add_twitter")],
                [InlineKeyboardButton("返回", callback_data="sources_twitter")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"添加失败\n"
                f"{'─' * 24}\n\n"
                f"RSS 地址无效：{html.escape(url_validation['error'])}\n\n"
                "请重试。",
                reply_markup=reply_markup
            )
            return ConversationHandler.END

    # Add to user's sources
    success = add_user_source(telegram_id, "twitter", handle, url)

    keyboard = [
        [InlineKeyboardButton("添加更多", callback_data="sources_add_twitter")],
        [InlineKeyboardButton("返回", callback_data="sources_twitter")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if success:
        message = f"已添加 {html.escape(handle)}。"
        if not url:
            message += "\n注意：需要配置 RSS 地址才能抓取。"
        await update.message.reply_text(
            f"添加成功\n"
            f"{'─' * 24}\n\n"
            f"{message}",
            reply_markup=reply_markup
        )
        logger.info(f"Added Twitter source for user {telegram_id}: {handle}")
    else:
        await update.message.reply_text(
            f"添加失败\n"
            f"{'─' * 24}\n\n"
            "保存失败，请重试。",
            reply_markup=reply_markup
        )
        logger.warning(f"Failed to add Twitter source for user {telegram_id}: {handle}")

    return ConversationHandler.END


async def start_add_website(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start adding a website RSS feed."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    await query.edit_message_text(
        f"添加网站 RSS\n"
        f"{'─' * 24}\n\n"
        "方式一：只输入域名（自动探测）\n"
        "  theblock.co\n"
        "  decrypt.co\n\n"
        "方式二：指定名称和地址\n"
        "  The Block | https://theblock.co/rss.xml\n\n"
        "请输入或 /cancel 取消："
    )

    return AWAITING_WEBSITE_ADD


async def handle_website_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle website RSS feed addition."""
    from services.rss_fetcher import validate_url, auto_detect_rss

    telegram_id = str(update.effective_user.id)
    user_input = update.message.text.strip()

    # Parse input: "Name | URL" or just URL/domain
    if "|" in user_input:
        parts = user_input.split("|", 1)
        name = parts[0].strip()
        url = parts[1].strip()
    else:
        # Try to extract name from URL/domain
        url = user_input
        try:
            from urllib.parse import urlparse
            if url.startswith("http"):
                parsed = urlparse(url)
                name = parsed.netloc.replace("www.", "").split(".")[0].title()
            else:
                name = url.replace("www.", "").split(".")[0].title()
        except Exception:
            name = "Custom Source"

    keyboard = [
        [InlineKeyboardButton("添加更多", callback_data="sources_add_website")],
        [InlineKeyboardButton("返回", callback_data="sources_websites")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # If URL provided, validate it directly
    if url.startswith("http"):
        validation = await validate_url(url)
        if not validation["valid"]:
            await update.message.reply_text(
                f"添加失败\n"
                f"{'─' * 24}\n\n"
                f"{html.escape(validation['error'])}\n\n"
                "请检查地址后重试。",
                reply_markup=reply_markup
            )
            return ConversationHandler.END
        final_url = url
    else:
        # No full URL - try to auto-detect RSS from domain
        detection = await auto_detect_rss(url)
        if not detection["found"]:
            await update.message.reply_text(
                f"添加失败\n"
                f"{'─' * 24}\n\n"
                f"{html.escape(detection['error'])}\n\n"
                "请检查地址后重试。",
                reply_markup=reply_markup
            )
            return ConversationHandler.END
        final_url = detection["url"]

    # Add to user's sources
    success = add_user_source(telegram_id, "websites", name, final_url)

    if success:
        await update.message.reply_text(
            f"添加成功\n"
            f"{'─' * 24}\n\n"
            f"已添加 {html.escape(name)}。\n"
            f"RSS: {html.escape(final_url)}",
            reply_markup=reply_markup
        )
        logger.info(f"Added website source for user {telegram_id}: {name} - {final_url}")
    else:
        await update.message.reply_text(
            f"添加失败\n"
            f"{'─' * 24}\n\n"
            "保存失败，请重试。",
            reply_markup=reply_markup
        )
        logger.warning(f"Failed to add website source for user {telegram_id}: {name}")

    return ConversationHandler.END


async def handle_source_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle user's source suggestion."""
    user = update.effective_user
    telegram_id = str(user.id)
    suggestion = update.message.text

    # In a real implementation, this would be saved to a review queue
    # For MVP, we just acknowledge and log

    logger.info(f"Source suggestion from {telegram_id}: {suggestion}")

    await update.message.reply_text(
        f"已收到推荐\n"
        f"{'─' * 24}\n\n"
        f"{suggestion}\n\n"
        "我们会审核这个信息源。\n"
        "如果通过审核，将添加到监控列表。\n\n"
        "使用 /sources 查看当前信息源。"
    )

    return ConversationHandler.END


async def start_bulk_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start bulk source import conversation."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    await query.edit_message_text(
        f"批量导入信息源\n"
        f"{'─' * 24}\n\n"
        "请输入多个信息源，每行一个。\n\n"
        "Twitter 格式：\n"
        "  @账号名 | RSS地址\n\n"
        "网站格式：\n"
        "  网站名 | RSS地址\n\n"
        "示例：\n"
        "  @VitalikButerin | https://rss.app/feeds/xxx\n"
        "  @lookonchain | https://nitter.net/lookonchain/rss\n"
        "  The Block | https://theblock.co/rss.xml\n"
        "  decrypt.co\n\n"
        "请输入或 /cancel 取消："
    )

    return AWAITING_BULK_IMPORT


async def handle_bulk_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle bulk source import."""
    from services.rss_fetcher import validate_twitter_handle, validate_url, auto_detect_rss

    telegram_id = str(update.effective_user.id)
    user_input = update.message.text.strip()
    lines = user_input.split("\n")

    success_count = 0
    fail_count = 0
    results = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Determine category based on @ symbol
        if line.startswith("@") or ("|" in line and line.split("|")[0].strip().startswith("@")):
            category = "twitter"
        else:
            category = "websites"

        # Parse name and URL
        if "|" in line:
            parts = line.split("|", 1)
            name = parts[0].strip()
            url = parts[1].strip()
        else:
            name = line
            url = ""

        # Process based on category
        if category == "twitter":
            validation = await validate_twitter_handle(name)
            if not validation["valid"]:
                fail_count += 1
                results.append(f"  - {name}: {validation['error'][:30]}")
                continue
            name = validation["handle"]
            if url:
                url_validation = await validate_url(url)
                if not url_validation["valid"]:
                    fail_count += 1
                    results.append(f"  - {name}: RSS无效")
                    continue
        else:
            # Website
            if url.startswith("http"):
                validation = await validate_url(url)
                if not validation["valid"]:
                    fail_count += 1
                    results.append(f"  - {name}: {validation['error'][:30]}")
                    continue
            elif not url:
                # Try auto-detect
                detection = await auto_detect_rss(name)
                if detection["found"]:
                    url = detection["url"]
                    name = name.replace("www.", "").split(".")[0].title()
                else:
                    fail_count += 1
                    results.append(f"  - {name}: 未找到RSS")
                    continue

        # Add to user's sources
        success = add_user_source(telegram_id, category, name, url)
        if success:
            success_count += 1
            results.append(f"  + {name}")
        else:
            fail_count += 1
            results.append(f"  - {name}: 保存失败")

    keyboard = [
        [InlineKeyboardButton("继续导入", callback_data="sources_bulk_import")],
        [InlineKeyboardButton("返回", callback_data="sources_back")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    status_text = "\n".join(results[:15])
    if len(results) > 15:
        status_text += f"\n  ... 还有 {len(results) - 15} 条"

    await update.message.reply_text(
        f"批量导入结果\n"
        f"{'─' * 24}\n\n"
        f"成功: {success_count}\n"
        f"失败: {fail_count}\n\n"
        f"详情：\n{status_text}",
        reply_markup=reply_markup
    )

    logger.info(f"Bulk import for user {telegram_id}: {success_count} success, {fail_count} failed")
    return ConversationHandler.END


async def show_delete_twitter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show Twitter sources with delete buttons."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    telegram_id = str(query.from_user.id)
    sources = get_user_source_list(telegram_id)
    twitter_sources = sources.get("twitter", [])

    if not twitter_sources:
        await query.edit_message_text(
            "没有可删除的 Twitter 信息源。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("返回", callback_data="sources_twitter")]
            ])
        )
        return

    lines = [
        f"删除 Twitter 信息源\n"
        f"{'─' * 24}\n\n"
        "点击要删除的账号：\n"
    ]
    text = "\n".join(lines)

    # Create a button for each source
    keyboard = []
    for source in twitter_sources:
        keyboard.append([InlineKeyboardButton(f"❌ {source}", callback_data=f"del_tw_{source}")])
    keyboard.append([InlineKeyboardButton("取消", callback_data="sources_twitter")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_delete_website(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show website sources with delete buttons."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    telegram_id = str(query.from_user.id)
    sources = get_user_source_list(telegram_id)
    website_sources = sources.get("websites", [])

    if not website_sources:
        await query.edit_message_text(
            "没有可删除的网站信息源。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("返回", callback_data="sources_websites")]
            ])
        )
        return

    lines = [
        f"删除网站信息源\n"
        f"{'─' * 24}\n\n"
        "点击要删除的网站：\n"
    ]
    text = "\n".join(lines)

    # Create a button for each source
    keyboard = []
    for source in website_sources:
        keyboard.append([InlineKeyboardButton(f"❌ {source}", callback_data=f"del_web_{source}")])
    keyboard.append([InlineKeyboardButton("取消", callback_data="sources_websites")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_delete_twitter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Twitter source deletion."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    telegram_id = str(query.from_user.id)
    source_name = query.data.replace("del_tw_", "")

    success = remove_user_source(telegram_id, "twitter", source_name)

    if success:
        logger.info(f"Deleted Twitter source for user {telegram_id}: {source_name}")
        await query.edit_message_text(
            f"已删除\n"
            f"{'─' * 24}\n\n"
            f"{source_name} 已从你的信息源中移除。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("继续删除", callback_data="sources_del_twitter")],
                [InlineKeyboardButton("返回", callback_data="sources_twitter")],
            ])
        )
    else:
        await query.edit_message_text(
            f"删除失败\n"
            f"{'─' * 24}\n\n"
            f"无法删除 {source_name}，请重试。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("返回", callback_data="sources_twitter")]
            ])
        )


async def handle_delete_website(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle website source deletion."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    telegram_id = str(query.from_user.id)
    source_name = query.data.replace("del_web_", "")

    success = remove_user_source(telegram_id, "websites", source_name)

    if success:
        logger.info(f"Deleted website source for user {telegram_id}: {source_name}")
        await query.edit_message_text(
            f"已删除\n"
            f"{'─' * 24}\n\n"
            f"{source_name} 已从你的信息源中移除。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("继续删除", callback_data="sources_del_website")],
                [InlineKeyboardButton("返回", callback_data="sources_websites")],
            ])
        )
    else:
        await query.edit_message_text(
            f"删除失败\n"
            f"{'─' * 24}\n\n"
            f"无法删除 {source_name}，请重试。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("返回", callback_data="sources_websites")]
            ])
        )


async def sources_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return to sources menu."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    # Get source counts for this user
    telegram_id = str(query.from_user.id)
    sources = get_user_source_list(telegram_id)
    twitter_count = len(sources.get("twitter", []))
    website_count = len(sources.get("websites", []))

    keyboard = [
        [
            InlineKeyboardButton("Twitter", callback_data="sources_twitter"),
            InlineKeyboardButton("网站", callback_data="sources_websites"),
        ],
        [InlineKeyboardButton("批量导入", callback_data="sources_bulk_import")],
        [InlineKeyboardButton("推荐信息源", callback_data="sources_suggest")],
        [InlineKeyboardButton("返回", callback_data="back_to_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"信息源管理\n"
        f"{'─' * 24}\n\n"
        f"当前监控：\n"
        f"  • Twitter 账号: {twitter_count}\n"
        f"  • 网站 RSS: {website_count}\n\n"
        "选择分类查看详情。",
        reply_markup=reply_markup
    )


async def cancel_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel sources conversation."""
    keyboard = [
        [
            InlineKeyboardButton("信息源", callback_data="sources_back"),
            InlineKeyboardButton("主菜单", callback_data="back_to_start"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "已取消。\n\n"
        "随时可以推荐信息源。",
        reply_markup=reply_markup
    )
    return ConversationHandler.END


def get_sources_handler() -> ConversationHandler:
    """Create and return the sources conversation handler."""
    return ConversationHandler(
        entry_points=[
            CommandHandler("sources", sources_command),
            CallbackQueryHandler(start_source_suggestion, pattern="^sources_suggest$"),
            CallbackQueryHandler(start_add_twitter, pattern="^sources_add_twitter$"),
            CallbackQueryHandler(start_add_website, pattern="^sources_add_website$"),
            CallbackQueryHandler(start_bulk_import, pattern="^sources_bulk_import$"),
        ],
        states={
            AWAITING_SOURCE_SUGGESTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_source_suggestion),
            ],
            AWAITING_TWITTER_ADD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_twitter_add),
            ],
            AWAITING_WEBSITE_ADD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_website_add),
            ],
            AWAITING_BULK_IMPORT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bulk_import),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_sources),
        ],
    )


def get_sources_callbacks():
    """Get standalone callback handlers for sources menu."""
    return [
        CallbackQueryHandler(view_twitter_sources, pattern="^sources_twitter$"),
        CallbackQueryHandler(view_website_sources, pattern="^sources_websites$"),
        CallbackQueryHandler(show_delete_twitter, pattern="^sources_del_twitter$"),
        CallbackQueryHandler(show_delete_website, pattern="^sources_del_website$"),
        CallbackQueryHandler(handle_delete_twitter, pattern="^del_tw_"),
        CallbackQueryHandler(handle_delete_website, pattern="^del_web_"),
        CallbackQueryHandler(sources_back, pattern="^sources_back$"),
    ]
