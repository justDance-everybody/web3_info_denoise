"""
Web3 Daily Digest - Configuration Management
"""
import os
import json
import logging
from dotenv import load_dotenv

# Explicitly load .env from current directory
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)
else:
    load_dotenv(override=True)

logger = logging.getLogger(__name__)

# ============ LLM Selection (Smart Auto-Config) ============
# Set LLM=gemini or openai, then configure the corresponding keys
LLM = os.getenv("LLM", "gemini").lower().strip()

# Auto-configure based on LLM selection
if LLM == "openai":
    # OpenAI (or OpenAI-compatible: Kimi, DeepSeek, etc.)
    LLM_PROVIDER = "openai"
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
    OPENAI_API_URL = os.getenv("OPENAI_API_URL", "")

    # Log provider info
    if OPENAI_API_URL:
        logger.info(f"🤖 Using OpenAI-compatible API: {OPENAI_MODEL}")
    else:
        logger.info(f"🤖 Using OpenAI: {OPENAI_MODEL}")

elif LLM == "gemini":
    # Google Gemini (default)
    LLM_PROVIDER = "gemini"
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-pro-preview")
    GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "HIGH")

    # Build Gemini API URL: supports both base URL and full URL
    _api_base = os.getenv("GEMINI_API_URL", "").rstrip("/")
    if _api_base:
        if "/v1beta/models/" in _api_base or ":generateContent" in _api_base:
            GEMINI_API_URL = _api_base
        else:
            GEMINI_API_URL = f"{_api_base}/v1beta/models/{GEMINI_MODEL}:generateContent"
    else:
        GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

    logger.info(f"✨ Using Gemini: {GEMINI_MODEL}")

else:
    logger.warning(f"⚠️ Unknown LLM: {LLM}, falling back to Gemini")
    LLM_PROVIDER = "gemini"
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-pro-preview")
    GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "HIGH")
    GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# Ensure all variables exist (for compatibility)
if LLM_PROVIDER == "gemini":
    # Set dummy OpenAI vars
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
    OPENAI_API_URL = os.getenv("OPENAI_API_URL", "")
else:
    # Set dummy Gemini vars
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-pro-preview")
    GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "HIGH")
    GEMINI_API_URL = ""

# Validate required API keys
import sys
if LLM_PROVIDER == "gemini" and not GEMINI_API_KEY:
    logger.error("❌ GEMINI_API_KEY not set! Please check your .env file.")
    logger.error("   Set GEMINI_API_KEY=your_api_key in .env")
    sys.exit(1)
elif LLM_PROVIDER == "openai" and not OPENAI_API_KEY:
    logger.error("❌ OPENAI_API_KEY not set! Please check your .env file.")
    logger.error("   Set OPENAI_API_KEY=your_api_key in .env")
    sys.exit(1)

# Telegram Bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Push Schedule (Beijing Time)
def _parse_int_env(key: str, default: int) -> int:
    """Parse an integer environment variable with fallback."""
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default

PUSH_HOUR = _parse_int_env("PUSH_HOUR", 9)
PUSH_MINUTE = _parse_int_env("PUSH_MINUTE", 0)

# Data Directory
DATA_DIR = os.getenv("DATA_DIR", "./data")

# Security Configuration
# Support multiple admins (comma-separated)
_admin_ids_str = os.getenv("ADMIN_TELEGRAM_IDS", "") or os.getenv("ADMIN_TELEGRAM_ID", "")
ADMIN_TELEGRAM_IDS = [id.strip() for id in _admin_ids_str.split(",") if id.strip()]

# Legacy single admin (for backward compatibility)
ADMIN_TELEGRAM_ID = ADMIN_TELEGRAM_IDS[0] if ADMIN_TELEGRAM_IDS else ""

# Whitelist settings
WHITELIST_FILE = os.path.join(DATA_DIR, "whitelist.json")
WHITELIST_SETTINGS_FILE = os.path.join(DATA_DIR, "whitelist_settings.json")
WHITELIST_ENABLED_DEFAULT = os.getenv("WHITELIST_ENABLED", "true").lower() == "true"

# Logging Configuration
LOG_ROTATE_DAYS = _parse_int_env("LOG_ROTATE_DAYS", 1)  # 每几天轮转一次日志
LOG_BACKUP_COUNT = _parse_int_env("LOG_BACKUP_COUNT", 30)  # 最多保留多少个备份

# Data Retention Configuration (days)
# 数据保留天数配置
RAW_CONTENT_RETENTION_DAYS = _parse_int_env("RAW_CONTENT_RETENTION_DAYS", 7)  # 原始内容保留天数
DAILY_STATS_RETENTION_DAYS = _parse_int_env("DAILY_STATS_RETENTION_DAYS", 30)  # 每日统计保留天数
FEEDBACK_RETENTION_DAYS = _parse_int_env("FEEDBACK_RETENTION_DAYS", 30)  # 反馈记录保留天数

# Digest Configuration
# 简报配置
MIN_DIGEST_ITEMS = _parse_int_env("MIN_DIGEST_ITEMS", 15)  # 每日精选最少条数
MAX_DIGEST_ITEMS = _parse_int_env("MAX_DIGEST_ITEMS", 30)  # 每日精选最多条数
MAX_AI_INPUT_ITEMS = _parse_int_env("MAX_AI_INPUT_ITEMS", 0)  # AI单次输入最大条数（0=不限制，超过则分批处理）

# Concurrency Configuration
# 并发配置
CONCURRENT_USERS = _parse_int_env("CONCURRENT_USERS", 10)  # 并发处理用户数（1-50，建议10）

# Prefetch Configuration
# 预抓取配置（解决 RSS.app 只返回最近内容的问题）
PREFETCH_INTERVAL_HOURS = _parse_int_env("PREFETCH_INTERVAL_HOURS", 2)  # 预抓取间隔（小时）
PREFETCH_START_HOUR = _parse_int_env("PREFETCH_START_HOUR", 1)  # 预抓取开始时间（小时，北京时间）

# Paths
USERS_FILE = os.path.join(DATA_DIR, "users.json")
PROFILES_DIR = os.path.join(DATA_DIR, "profiles")
FEEDBACK_DIR = os.path.join(DATA_DIR, "feedback")
DAILY_STATS_DIR = os.path.join(DATA_DIR, "daily_stats")
RAW_CONTENT_DIR = os.path.join(DATA_DIR, "raw_content")
USER_SOURCES_DIR = os.path.join(DATA_DIR, "user_sources")  # Per-user source configs
PREFETCH_CACHE_DIR = os.path.join(DATA_DIR, "prefetch_cache")  # 预抓取缓存目录


# ============ Default Sources Configuration ============

# Hardcoded default sources (used if env not set)
_DEFAULT_SOURCES = {
    "twitter": {
        # These are bundled Twitter feeds from RSS.app
        # The actual feeds are aggregated through these URLs:
        # 1. https://rss.app/feeds/G6dip9YSp1NzQMls.xml
        # 2. https://rss.app/feeds/HVg722x6SI7tChWQ.xml
        "Twitter Bundle 1": "https://rss.app/feeds/G6dip9YSp1NzQMls.xml",
        "Twitter Bundle 2": "https://rss.app/feeds/HVg722x6SI7tChWQ.xml",
    },
    "websites": {
        # Web3 news sites with verified RSS feeds
        "Cointelegraph": "https://cointelegraph.com/rss",
        "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "The Block Beats": "https://api.theblockbeats.news/v1/open-api/home-xml",  # Fixed: using API endpoint
        # Additional sites from Excel with verified RSS
        "TechFlow Post": "https://techflowpost.substack.com/feed",  # Alternative: https://techflowpost.mirror.xyz/feed/atom
        "DeFi Rate": "https://defirate.com/feed",
        "Prediction News": "https://predictionnews.com/rss/",
        "Event Horizon": "https://nexteventhorizon.substack.com/feed",
        "un.Block (吴说)": "https://unblock256.substack.com/feed",  # wublock123.com's newsletter
        # Note: Sites without RSS feeds (verified by testing):
        # - Odaily: Returns HTML instead of RSS
        # - ChainFeeds: 404 error
        # - Foresight News: WAF protection page
        # - https://www.me.news/news (no RSS)
        # - https://www.chaincatcher.com/news (404 on RSS endpoint)
        # - https://www.panewslab.com/ (no RSS)
        # - Telegram channels cannot be added as RSS
    }
}


def _parse_sources_env() -> dict:
    """
    Parse default sources from environment variables.

    Supports two formats:
    1. JSON format: DEFAULT_SOURCES='{"twitter": {"@user": "url"}, "websites": {"name": "url"}}'
    2. Simple format (comma-separated):
       DEFAULT_TWITTER_SOURCES='@VitalikButerin,@lookonchain,@whale_alert'
       DEFAULT_WEBSITE_SOURCES='The Block|https://theblock.co/rss.xml,CoinDesk|https://coindesk.com/rss'

    Returns:
        Dict with twitter and websites sources
    """
    # Try JSON format first
    json_sources = os.getenv("DEFAULT_SOURCES", "")
    if json_sources:
        try:
            parsed = json.loads(json_sources)
            if isinstance(parsed, dict):
                return {
                    "twitter": parsed.get("twitter", {}),
                    "websites": parsed.get("websites", {})
                }
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse DEFAULT_SOURCES JSON: {e}")

    # Try simple format
    result = {"twitter": {}, "websites": {}}

    # Parse Twitter sources: @user1,@user2 or @user1|rss_url,@user2|rss_url
    twitter_env = os.getenv("DEFAULT_TWITTER_SOURCES", "")
    if twitter_env:
        for item in twitter_env.split(","):
            item = item.strip()
            if not item:
                continue
            if "|" in item:
                parts = item.split("|", 1)
                handle = parts[0].strip()
                url = parts[1].strip()
            else:
                handle = item
                url = ""
            # Ensure @ prefix
            if not handle.startswith("@"):
                handle = f"@{handle}"
            result["twitter"][handle] = url

    # Parse website sources: Name|url,Name2|url2
    website_env = os.getenv("DEFAULT_WEBSITE_SOURCES", "")
    if website_env:
        for item in website_env.split(","):
            item = item.strip()
            if not item:
                continue
            if "|" in item:
                parts = item.split("|", 1)
                name = parts[0].strip()
                url = parts[1].strip()
                result["websites"][name] = url

    # If nothing from env, return None to use hardcoded defaults
    if not result["twitter"] and not result["websites"]:
        return None

    return result


# Load default sources: env > hardcoded defaults
_env_sources = _parse_sources_env()
DEFAULT_USER_SOURCES = _env_sources if _env_sources else _DEFAULT_SOURCES
