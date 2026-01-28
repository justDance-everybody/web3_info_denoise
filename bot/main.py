"""
Web3 Daily Digest - Telegram Bot Entry Point

Main application file that initializes the bot, sets up handlers,
and configures scheduled tasks for daily digest delivery.

Reference: python-telegram-bot v22.x with built-in JobQueue
"""
import asyncio
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import sys
import signal
import atexit
from datetime import time, datetime, timedelta
from typing import Dict, Any
from zoneinfo import ZoneInfo

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import (
    TELEGRAM_BOT_TOKEN, PUSH_HOUR, PUSH_MINUTE, DATA_DIR,
    LOG_ROTATE_DAYS, LOG_BACKUP_COUNT, MAX_DIGEST_ITEMS, CONCURRENT_USERS,
    PREFETCH_INTERVAL_HOURS, PREFETCH_START_HOUR, ADMIN_TELEGRAM_IDS
)
from services.digest_processor import process_single_user
from utils.telegram_utils import safe_answer_callback_query
from handlers.start import get_start_handler, get_start_callbacks
from handlers.feedback import get_feedback_handlers
from handlers.settings import get_settings_handler, get_settings_callbacks
from handlers.sources import get_sources_handler, get_sources_callbacks
from handlers.admin import get_admin_handlers


# ============ Logging Configuration ============

# Create logs directory
LOGS_DIR = os.path.join(DATA_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)


class HeartbeatFilter(logging.Filter):
    """Filter out noisy heartbeat/polling log messages."""

    # Patterns to filter out
    NOISE_PATTERNS = [
        "HTTP Request: POST https://api.telegram.org/bot",
        "getUpdates",
        "Got response",
        "Entering:",
        "Exiting:",
        "No updates to fetch",
        "Network loop",
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern in self.NOISE_PATTERNS:
            if pattern in msg:
                return False
        return True


log_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Console handler (with heartbeat filter)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
console_handler.addFilter(HeartbeatFilter())

# Timed rotating file handler: rotate every N days, keep 30 backups
# 按天轮转日志，LOG_ROTATE_DAYS 控制几天轮转一次，LOG_BACKUP_COUNT 控制保留数量
file_handler = TimedRotatingFileHandler(
    os.path.join(LOGS_DIR, "bot.log"),
    when="D",                        # 按天
    interval=LOG_ROTATE_DAYS,        # 每 N 天轮转
    backupCount=LOG_BACKUP_COUNT,    # 保留 N 个备份（默认30天）
    encoding="utf-8"
)
file_handler.setFormatter(log_formatter)
file_handler.addFilter(HeartbeatFilter())

logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler, file_handler]
)

# Reduce noise from third-party libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Force reload environment variables and update config
from dotenv import load_dotenv
import config

env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)
    logger.info(f"Force reloaded .env from {env_path}")

# Update config variable (support multiple admins)
_admin_ids_str = os.getenv("ADMIN_TELEGRAM_IDS", "") or os.getenv("ADMIN_TELEGRAM_ID", "")
config.ADMIN_TELEGRAM_IDS = [id.strip() for id in _admin_ids_str.split(",") if id.strip()]
config.ADMIN_TELEGRAM_ID = config.ADMIN_TELEGRAM_IDS[0] if config.ADMIN_TELEGRAM_IDS else ""
logger.info(f"Admin IDs configured: {len(config.ADMIN_TELEGRAM_IDS)} admin(s)")


async def daily_digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Scheduled job to generate and send daily digest to all users.
    Runs at configured time (default: 9:00 AM Beijing Time).
    Uses concurrent processing for better performance with pre-fetching optimization.
    """
    from utils.json_storage import get_users, get_user_sources
    from services.rss_fetcher import fetch_all_sources

    logger.info("Starting daily digest generation...")

    today = datetime.now().strftime("%Y-%m-%d")

    try:
        # Get all users
        users = get_users()
        if not users:
            logger.warning("No users registered, skipping digest")
            return

        # ===== Pre-fetch optimization: Collect all unique sources =====
        logger.info("Collecting all user sources...")
        all_sources = {}  # {category: {name: url}}

        for user in users:
            telegram_id = user.get("telegram_id")
            if not telegram_id:
                continue

            user_sources = get_user_sources(telegram_id)
            # Merge into global sources dict
            for category, sources in user_sources.items():
                if category not in all_sources:
                    all_sources[category] = {}
                for name, url in sources.items():
                    if url and name not in all_sources[category]:
                        all_sources[category][name] = url

        # Count unique sources
        unique_sources_count = sum(len(sources) for sources in all_sources.values())
        logger.info(f"Found {unique_sources_count} unique RSS sources across {len(users)} users")

        # Batch fetch all sources once (shared by all users)
        logger.info("Pre-fetching all RSS sources...")
        global_raw_content = await fetch_all_sources(
            hours_back=24,
            sources=all_sources
        )
        logger.info(f"Pre-fetched {len(global_raw_content)} total items")
        # ===== Pre-fetch complete =====

        logger.info(f"Processing {len(users)} users with concurrency={CONCURRENT_USERS}")

        # Concurrent processing with semaphore to limit concurrency
        semaphore = asyncio.Semaphore(CONCURRENT_USERS)

        async def process_with_limit(user):
            async with semaphore:
                # Pass global data to avoid duplicate fetching
                return await process_single_user(context, user, today, global_raw_content)

        # Process all users concurrently
        results = await asyncio.gather(
            *[process_with_limit(user) for user in users],
            return_exceptions=True  # Single user failure doesn't affect others
        )

        # Collect statistics
        success_count = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
        error_count = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "error")
        skipped_count = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "skipped")
        exception_count = sum(1 for r in results if isinstance(r, Exception))

        logger.info(
            f"Daily digest complete: {success_count} success, {error_count} errors, "
            f"{skipped_count} skipped, {exception_count} exceptions"
        )

        # Log any exceptions that occurred
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"User {users[i].get('telegram_id')} raised exception: {result}")

    except Exception as e:
        logger.error(f"Daily digest job failed: {e}", exc_info=True)


async def test_fetch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hidden /test command - manually trigger digest for the current user only."""
    from utils.json_storage import get_user, get_user_sources
    from services.rss_fetcher import fetch_all_sources
    
    user = update.effective_user
    telegram_id = str(user.id)
    today = datetime.now().strftime("%Y-%m-%d")

    await update.message.reply_text("正在为你生成简报...")

    try:
        # Get current user's data
        user_data = get_user(telegram_id)
        if not user_data:
            await update.message.reply_text("未找到你的用户数据，请先完成 /start 设置。")
            return
        
        # Fetch sources for this user only
        user_sources = get_user_sources(telegram_id)
        if not user_sources:
            await update.message.reply_text("你还没有配置信息源，请使用 /sources 添加。")
            return
        
        # Add sources to user_data for process_single_user
        user_data["sources"] = user_sources
        
        logger.info(f"Test command: Processing user {telegram_id}")
        
        # Fetch RSS content for this user
        raw_content = await fetch_all_sources(
            hours_back=24,
            sources=user_sources
        )
        logger.info(f"Test command: Fetched {len(raw_content)} items for user {telegram_id}")
        
        # Process single user
        result = await process_single_user(context, user_data, today, raw_content)
        
        if result.get("status") == "success":
            await update.message.reply_text("简报已发送！")
        elif result.get("status") == "skipped":
            await update.message.reply_text(f"跳过: {result.get('reason', '未知原因')}")
        else:
            await update.message.reply_text(f"处理失败: {result.get('error', '未知错误')[:100]}")
            
    except Exception as e:
        logger.error(f"Test fetch failed for user {telegram_id}: {e}", exc_info=True)
        await update.message.reply_text(f"抓取失败: {str(e)[:100]}")


async def test_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hidden /testprofile command - manually trigger profile update from feedback."""
    from services.profile_updater import update_all_user_profiles

    await update.message.reply_text("正在更新用户画像...")

    try:
        await update_all_user_profiles()
        await update.message.reply_text("画像更新完成。")
    except Exception as e:
        logger.error(f"Test profile update failed: {e}")
        await update.message.reply_text(f"更新失败: {str(e)[:100]}")


async def test_prefetch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hidden /testprefetch command - manually trigger prefetch and show stats."""
    from services.rss_fetcher import prefetch_all_user_sources
    from utils.json_storage import get_prefetch_cache
    from datetime import datetime

    await update.message.reply_text("🔄 正在执行预抓取测试...")

    try:
        # 执行预抓取
        stats = await prefetch_all_user_sources()

        # 获取缓存状态
        today = datetime.now().strftime("%Y-%m-%d")
        cache = get_prefetch_cache(today)

        result_text = f"""✅ 预抓取测试完成

📊 本次抓取统计：
• 用户数: {stats.get('users_count', 0)}
• 信息源数: {stats.get('sources_count', 0)}
• 新增条目: {stats.get('new_items', 0)}
• 重复跳过: {stats.get('duplicates', 0)}

📦 当日缓存状态：
• 累计条目: {len(cache.get('items', []))}
• 去重 ID 数: {len(cache.get('seen_ids', []))}
• 抓取次数: {cache.get('fetch_count', 0)}
• 最后抓取: {cache.get('last_fetch', 'N/A')[:19] if cache.get('last_fetch') else 'N/A'}

💡 提示：
• 如果"新增条目"为 0 且"重复跳过"有数值，说明去重正常工作
• 多次执行此命令，观察"累计条目"是否增加（有新推文时）
• 使用 /test 命令可测试完整推送流程"""

        await update.message.reply_text(result_text)

    except Exception as e:
        logger.error(f"Test prefetch failed: {e}", exc_info=True)
        await update.message.reply_text(f"❌ 预抓取失败: {str(e)[:200]}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    keyboard = [
        [
            InlineKeyboardButton("主菜单", callback_data="back_to_start"),
            InlineKeyboardButton("设置", callback_data="update_preferences"),
        ],
        [InlineKeyboardButton("信息源", callback_data="manage_sources")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    help_text = f"""帮助
{'─' * 24}

命令：
  /start     主菜单
  /settings  偏好设置
  /sources   信息源管理
  /stats     查看统计
  /help      帮助信息

{'─' * 24}

功能说明：

每日简报
  每天 {PUSH_HOUR:02d}:{PUSH_MINUTE:02d}（北京时间）自动推送。
  内容分为「今日必看」「推荐」「其他」三个板块。
  AI 根据你的偏好智能筛选 15-30 条精选内容。

偏好设置 (/settings)
  查看或更新你的 Web3 兴趣偏好。
  AI 会根据偏好个性化筛选每日简报。

信息源管理 (/sources)
  添加/删除你关注的 Twitter 账号或网站 RSS。
  支持自定义个人信息源。

统计 (/stats)
  查看你的注册时间、反馈历史、满意度趋势。

反馈机制
  每条推送消息都有反馈按钮（👍/👎）。
  你的反馈会被收集并在每日凌晨批量更新偏好画像，
  次日推送将体现你的最新偏好。

{'─' * 24}

有问题？使用上方命令或主菜单操作。"""

    await update.message.reply_text(help_text, reply_markup=reply_markup)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats command - show user statistics."""
    from services.profile_updater import analyze_feedback_trends
    from utils.json_storage import get_user

    def _translate_trend(trend: str) -> str:
        """Translate trend text to Chinese."""
        translations = {
            "improving": "改善中",
            "declining": "下降中",
            "stable": "稳定",
            "no_data": "暂无数据",
        }
        return translations.get(trend, trend.replace('_', ' '))

    user = update.effective_user
    telegram_id = str(user.id)

    db_user = get_user(telegram_id)
    if not db_user:
        await update.message.reply_text(
            "你还没有注册。请使用 /start 开始。"
        )
        return

    # Get feedback trends
    trends = await analyze_feedback_trends(telegram_id, days=30)

    stats_text = f"""你的统计
{'─' * 24}

注册时间：{db_user.get('created', '未知')[:10]}

最近 30 天
  反馈次数         {trends['total_feedbacks']}
  正面评价         {trends['positive_count']}
  负面评价         {trends['negative_count']}
  满意度           {trends['positive_rate']:.0%}
  趋势             {_translate_trend(trends['trend'])}
{f"  主要问题         {', '.join(trends['common_issues'][:2])}" if trends['common_issues'] else ""}

{'─' * 24}

使用 /settings 调整偏好设置。"""

    keyboard = [
        [
            InlineKeyboardButton("更新偏好", callback_data="settings_update"),
            InlineKeyboardButton("主菜单", callback_data="back_to_start"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(stats_text, reply_markup=reply_markup)


async def post_init(application: Application) -> None:
    """Post-initialization callback to set up scheduled jobs and bot commands."""
    # Set bot commands menu (only show user-facing commands)
    # Debug commands (/test, /testprofile) are hidden from menu but still functional
    commands = [
        BotCommand("start", "主菜单"),
        BotCommand("help", "帮助信息"),
        BotCommand("settings", "偏好设置"),
        BotCommand("sources", "信息源管理"),
        BotCommand("stats", "查看统计"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands menu set successfully")

    # Get timezone for Beijing
    beijing_tz = ZoneInfo("Asia/Shanghai")

    # Schedule daily digest
    push_time = time(hour=PUSH_HOUR, minute=PUSH_MINUTE, tzinfo=beijing_tz)

    application.job_queue.run_daily(
        callback=daily_digest_job,
        time=push_time,
        name="daily_digest"
    )

    logger.info(f"Scheduled daily digest at {PUSH_HOUR:02d}:{PUSH_MINUTE:02d} Beijing Time")

    # Run profile updates 30 minutes before daily digest push
    # This ensures the latest feedback is incorporated into today's filtering
    profile_update_hour = PUSH_HOUR if PUSH_MINUTE >= 30 else (PUSH_HOUR - 1) % 24
    profile_update_minute = (PUSH_MINUTE - 30) % 60
    profile_update_time = time(hour=profile_update_hour, minute=profile_update_minute, tzinfo=beijing_tz)
    application.job_queue.run_daily(
        callback=profile_update_job,
        time=profile_update_time,
        name="profile_update"
    )
    logger.info(f"Scheduled profile update at {profile_update_hour:02d}:{profile_update_minute:02d} Beijing Time (30 min before push)")

    # Run data cleanup at 00:30 daily
    # 每日 00:30 清理过期数据文件
    cleanup_time = time(hour=0, minute=30, tzinfo=beijing_tz)
    application.job_queue.run_daily(
        callback=data_cleanup_job,
        time=cleanup_time,
        name="data_cleanup"
    )

    logger.info("Scheduled data cleanup at 00:30 Beijing Time")

    # Schedule prefetch jobs (if enabled)
    # 预抓取任务：每隔 PREFETCH_INTERVAL_HOURS 小时执行一次
    if PREFETCH_INTERVAL_HOURS > 0:
        # 计算预抓取时间点
        prefetch_times = []
        hour = PREFETCH_START_HOUR
        while hour < 24:
            prefetch_times.append(hour)
            hour += PREFETCH_INTERVAL_HOURS

        # 为每个时间点创建定时任务
        for i, prefetch_hour in enumerate(prefetch_times):
            prefetch_time = time(hour=prefetch_hour, minute=0, tzinfo=beijing_tz)
            application.job_queue.run_daily(
                callback=prefetch_job,
                time=prefetch_time,
                name=f"prefetch_{prefetch_hour:02d}"
            )

        # 同时在推送前 30 分钟也执行一次预抓取，确保数据最新
        pre_push_hour = (PUSH_HOUR - 1) % 24 if PUSH_HOUR > 0 else 23
        pre_push_time = time(hour=pre_push_hour, minute=30, tzinfo=beijing_tz)
        application.job_queue.run_daily(
            callback=prefetch_job,
            time=pre_push_time,
            name="prefetch_pre_push"
        )

        logger.info(
            f"Scheduled prefetch jobs at hours: {prefetch_times} + {pre_push_hour:02d}:30 (pre-push) Beijing Time"
        )

        # 启动时立即执行一次预抓取（异步）
        application.job_queue.run_once(
            callback=prefetch_job,
            when=10,  # 10 秒后执行
            name="prefetch_startup"
        )
        logger.info("Scheduled startup prefetch in 10 seconds")
    else:
        logger.info("Prefetch disabled (PREFETCH_INTERVAL_HOURS=0)")


async def profile_update_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduled job to update user profiles based on feedback."""
    from services.profile_updater import update_all_user_profiles

    logger.info("Running scheduled profile update...")
    try:
        await update_all_user_profiles()
        logger.info("Profile update complete")
    except Exception as e:
        logger.error(f"Profile update failed: {e}")


async def data_cleanup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Scheduled job to clean up old data files.

    每日定时清理过期数据：
    - raw_content: 保留 RAW_CONTENT_RETENTION_DAYS 天
    - daily_stats: 保留 DAILY_STATS_RETENTION_DAYS 天
    - feedback: 保留 FEEDBACK_RETENTION_DAYS 天
    - prefetch_cache: 保留 2 天
    """
    from utils.json_storage import cleanup_old_data, cleanup_prefetch_cache

    logger.info("Running scheduled data cleanup...")
    try:
        results = cleanup_old_data()
        # 清理预抓取缓存（保留 2 天）
        prefetch_deleted = cleanup_prefetch_cache(retention_days=2)
        results["prefetch_cache"] = prefetch_deleted

        total = sum(results.values())
        if total > 0:
            logger.info(
                f"Data cleanup complete: deleted {results['raw_content']} raw_content, "
                f"{results['daily_stats']} daily_stats, {results['feedback']} feedback, "
                f"{results['prefetch_cache']} prefetch_cache files"
            )
        else:
            logger.info("Data cleanup complete: no expired files to delete")
    except Exception as e:
        logger.error(f"Data cleanup failed: {e}")


async def prefetch_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    定时预抓取任务。

    每隔 PREFETCH_INTERVAL_HOURS 小时执行一次，
    抓取所有用户的 RSS 源并保存到缓存（自动去重）。

    解决 RSS.app 只返回最近 25 条内容的问题。
    """
    from services.rss_fetcher import prefetch_all_user_sources

    logger.info("Running scheduled prefetch job...")
    try:
        stats = await prefetch_all_user_sources()
        logger.info(
            f"Prefetch job complete: {stats.get('new_items', 0)} new items, "
            f"{stats.get('total_items', 0)} total cached from {stats.get('sources_count', 0)} sources"
        )
    except Exception as e:
        logger.error(f"Prefetch job failed: {e}", exc_info=True)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the bot."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle noop callback for already-feedback items."""
    query = update.callback_query
    await safe_answer_callback_query(query, "已经反馈过了", show_alert=False)


async def show_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle show_help callback from unknown message handler."""
    query = update.callback_query
    await safe_answer_callback_query(query)

    keyboard = [
        [
            InlineKeyboardButton("主菜单", callback_data="back_to_start"),
            InlineKeyboardButton("设置", callback_data="update_preferences"),
        ],
        [InlineKeyboardButton("信息源", callback_data="manage_sources")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    help_text = f"""帮助
{'─' * 24}

命令：
  /start     主菜单
  /settings  偏好设置
  /sources   信息源管理
  /stats     查看统计
  /help      帮助信息

{'─' * 24}

功能说明：

每日简报
  每天 {PUSH_HOUR:02d}:{PUSH_MINUTE:02d}（北京时间）自动推送。
  内容分为「今日必看」「推荐」「其他」三个板块。
  AI 根据你的偏好智能筛选 15-30 条精选内容。

偏好设置 (/settings)
  查看或更新你的 Web3 兴趣偏好。
  AI 会根据偏好个性化筛选每日简报。

信息源管理 (/sources)
  添加/删除你关注的 Twitter 账号或网站 RSS。
  支持自定义个人信息源。

统计 (/stats)
  查看你的注册时间、反馈历史、满意度趋势。

反馈机制
  每条推送消息都有反馈按钮（👍/👎）。
  你的反馈会被收集并在每日凌晨批量更新偏好画像，
  次日推送将体现你的最新偏好。

{'─' * 24}

有问题？使用上方命令或主菜单操作。"""

    await query.edit_message_text(help_text, reply_markup=reply_markup)


def main() -> None:
    """Main function to run the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set. Please check your .env file.")
        sys.exit(1)

    # Build application
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Add handlers
    
    # 1. Admin handlers (Priority: Highest - always handle admin commands first)
    for handler in get_admin_handlers():
        application.add_handler(handler)
    logger.info("Admin handlers registered")

    # 2. Start/onboarding conversation handler
    application.add_handler(get_start_handler())

    # Start menu callbacks
    for callback in get_start_callbacks():
        application.add_handler(callback)

    # Settings handler
    application.add_handler(get_settings_handler())
    for callback in get_settings_callbacks():
        application.add_handler(callback)

    # Sources handler
    application.add_handler(get_sources_handler())
    for callback in get_sources_callbacks():
        application.add_handler(callback)

    # Feedback handlers
    feedback_conv, item_handler = get_feedback_handlers()
    application.add_handler(feedback_conv)
    application.add_handler(item_handler)

    # Command handlers
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("test", test_fetch_command))
    application.add_handler(CommandHandler("testprofile", test_profile_command))
    application.add_handler(CommandHandler("testprefetch", test_prefetch_command))
    application.add_handler(CommandHandler("stats", stats_command))

    # Callback for help from unknown message
    application.add_handler(CallbackQueryHandler(show_help_callback, pattern="^show_help$"))
    application.add_handler(CallbackQueryHandler(noop_callback, pattern="^noop$"))

    # Error handler
    application.add_error_handler(error_handler)

    # Register shutdown handler to save shutdown log
    # 服务关闭时保存 shutdown 日志
    def on_shutdown():
        shutdown_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        shutdown_log_path = os.path.join(LOGS_DIR, f"bot.log.shutdown.{shutdown_time}")
        try:
            # Copy current log to shutdown file
            current_log_path = os.path.join(LOGS_DIR, "bot.log")
            if os.path.exists(current_log_path):
                import shutil
                shutil.copy2(current_log_path, shutdown_log_path)
                logger.info(f"Shutdown log saved to {shutdown_log_path}")
        except Exception as e:
            logger.error(f"Failed to save shutdown log: {e}")
        logger.info("Bot shutting down...")

    atexit.register(on_shutdown)

    # Start the bot
    logger.info(f"Admin IDs: {len(ADMIN_TELEGRAM_IDS)} configured")
    logger.info("Starting Web3 Daily Digest Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
