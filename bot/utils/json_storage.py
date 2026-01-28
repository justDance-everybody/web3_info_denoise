"""
JSON Storage Utilities

Handles all file-based data storage operations.
Uses JSON files for users, profiles, feedback, and content.
"""
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

from config import (
    DATA_DIR,
    USERS_FILE,
    PROFILES_DIR,
    FEEDBACK_DIR,
    DAILY_STATS_DIR,
    RAW_CONTENT_DIR,
    USER_SOURCES_DIR,
    PREFETCH_CACHE_DIR,
    DEFAULT_USER_SOURCES,
    RAW_CONTENT_RETENTION_DAYS,
    DAILY_STATS_RETENTION_DAYS,
    FEEDBACK_RETENTION_DAYS,
)

logger = logging.getLogger(__name__)


def _ensure_dir(path: str) -> None:
    """Ensure directory exists."""
    Path(path).mkdir(parents=True, exist_ok=True)


def _read_json(file_path: str) -> Dict[str, Any]:
    """
    Read JSON file with retry logic.

    No file locking needed - atomic writes guarantee consistency.
    Retries handle transient permission issues on Windows.
    """
    import time

    max_retries = 5
    retry_delay = 0.05  # 50ms

    for attempt in range(max_retries):
        try:
            if not os.path.exists(file_path):
                return {}

            # Simple read without locking (atomic writes guarantee consistency)
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in {file_path}: {e}")
            return {}
        except (PermissionError, OSError) as e:
            # Retry on Windows permission errors
            if attempt < max_retries - 1:
                logger.debug(f"File locked, retrying ({attempt+1}/{max_retries}): {file_path}")
                time.sleep(retry_delay)
                retry_delay *= 1.5  # Gentle backoff
                continue
            else:
                logger.error(f"Error reading {file_path} after {max_retries} retries: {e}")
                return {}
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            return {}

    return {}


def _write_json(file_path: str, data: Dict[str, Any]) -> bool:
    """
    Write JSON file using atomic write with retry logic.

    Uses temp file + atomic rename to avoid file lock issues on Windows.
    This is more reliable than msvcrt.locking().
    """
    import time
    import tempfile

    max_retries = 5  # Increased retries for atomic write
    retry_delay = 0.05  # 50ms

    for attempt in range(max_retries):
        temp_fd = None
        temp_path = None
        try:
            _ensure_dir(os.path.dirname(file_path))

            # Write to temporary file in same directory (same filesystem)
            dir_path = os.path.dirname(file_path) or '.'
            temp_fd, temp_path = tempfile.mkstemp(
                dir=dir_path,
                prefix='.tmp_',
                suffix='.json',
                text=True
            )

            # Write JSON to temp file
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                temp_fd = None  # Prevent double close
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Atomic replace (os.replace is atomic on both Windows and Unix)
            os.replace(temp_path, file_path)
            temp_path = None  # Prevent cleanup of successful file
            return True

        except (PermissionError, OSError) as e:
            # Retry on Windows file lock errors
            if attempt < max_retries - 1:
                logger.debug(f"File locked for write, retrying ({attempt+1}/{max_retries}): {file_path}")
                time.sleep(retry_delay)
                retry_delay *= 1.5  # Gentle backoff
                continue
            else:
                logger.error(f"Error writing {file_path} after {max_retries} retries: {e}")
                return False
        except Exception as e:
            logger.error(f"Error writing {file_path}: {e}")
            return False
        finally:
            # Cleanup on failure
            if temp_fd is not None:
                try:
                    os.close(temp_fd)
                except:
                    pass
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except:
                    pass

    return False


# ============ User Management ============

def get_users() -> List[Dict[str, Any]]:
    """Get all users."""
    data = _read_json(USERS_FILE)
    return data.get("users", [])


def get_user(telegram_id: str) -> Optional[Dict[str, Any]]:
    """Get user by Telegram ID."""
    users = get_users()
    for user in users:
        if user.get("telegram_id") == telegram_id:
            return user
    return None


def create_user(
    telegram_id: str,
    username: Optional[str] = None,
    first_name: Optional[str] = None
) -> Dict[str, Any]:
    """Create a new user."""
    data = _read_json(USERS_FILE)
    if "users" not in data:
        data["users"] = []

    # Check if user already exists
    for user in data["users"]:
        if user.get("telegram_id") == telegram_id:
            return user

    # Create new user
    user = {
        "id": f"user_{len(data['users']) + 1:03d}",
        "telegram_id": telegram_id,
        "username": username,
        "first_name": first_name,
        "created": datetime.now().isoformat(),
        "last_active": datetime.now().isoformat(),
    }

    data["users"].append(user)
    _write_json(USERS_FILE, data)

    logger.info(f"Created user: {user['id']} (telegram_id: {telegram_id})")
    return user


def update_user_activity(telegram_id: str) -> None:
    """Update user's last activity timestamp."""
    data = _read_json(USERS_FILE)
    for user in data.get("users", []):
        if user.get("telegram_id") == telegram_id:
            user["last_active"] = datetime.now().isoformat()
            _write_json(USERS_FILE, data)
            break


def get_user_setting(telegram_id: str, key: str, default: Any = None) -> Any:
    """Get a user setting value."""
    user = get_user(telegram_id)
    if not user:
        return default
    return user.get("settings", {}).get(key, default)


def set_user_setting(telegram_id: str, key: str, value: Any) -> bool:
    """Set a user setting value."""
    data = _read_json(USERS_FILE)
    for user in data.get("users", []):
        if user.get("telegram_id") == telegram_id:
            if "settings" not in user:
                user["settings"] = {}
            user["settings"][key] = value
            return _write_json(USERS_FILE, data)
    return False


def get_user_last_push_time(telegram_id: str) -> Optional[str]:
    """
    获取用户上次推送时间。
    
    Returns:
        ISO 格式的时间字符串，如果没有记录则返回 None
    """
    user = get_user(telegram_id)
    if not user:
        return None
    return user.get("last_push_time")


def set_user_last_push_time(telegram_id: str, push_time: Optional[str] = None) -> bool:
    """
    记录用户本次推送时间。
    
    Args:
        telegram_id: 用户 Telegram ID
        push_time: ISO 格式的时间字符串，默认为当前时间
    
    Returns:
        是否保存成功
    """
    if not push_time:
        push_time = datetime.now().isoformat()
    
    data = _read_json(USERS_FILE)
    for user in data.get("users", []):
        if user.get("telegram_id") == telegram_id:
            user["last_push_time"] = push_time
            return _write_json(USERS_FILE, data)
    return False


# ============ User Profile Management ============

def get_user_profile(telegram_id: str) -> Optional[str]:
    """Get user's natural language profile."""
    user = get_user(telegram_id)
    if not user:
        return None

    profile_path = os.path.join(PROFILES_DIR, f"{user['id']}.txt")
    if not os.path.exists(profile_path):
        return None

    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error reading profile for {telegram_id}: {e}")
        return None


def save_user_profile(telegram_id: str, profile: str, user_id: Optional[str] = None) -> bool:
    """Save user's natural language profile.

    Args:
        telegram_id: User's Telegram ID
        profile: Profile content
        user_id: Optional user ID (avoids file lock race condition)
    """
    if not user_id:
        user = get_user(telegram_id)
        if not user:
            logger.error(f"Cannot save profile: user {telegram_id} not found")
            return False
        user_id = user['id']

    _ensure_dir(PROFILES_DIR)
    profile_path = os.path.join(PROFILES_DIR, f"{user_id}.txt")

    try:
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(profile)
        logger.info(f"Saved profile for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving profile for {telegram_id}: {e}")
        return False


# ============ Feedback Management ============

def save_feedback(
    telegram_id: str,
    overall_rating: str,
    reason_selected: Optional[List[str]] = None,
    reason_text: Optional[str] = None,
    item_feedbacks: Optional[List[Dict[str, str]]] = None
) -> bool:
    """Save user feedback for a day."""
    user = get_user(telegram_id)
    if not user:
        return False

    today = datetime.now().strftime("%Y-%m-%d")
    feedback_path = os.path.join(FEEDBACK_DIR, f"{today}.json")

    data = _read_json(feedback_path)
    if "date" not in data:
        data["date"] = today
        data["feedbacks"] = []

    feedback = {
        "user_id": user["id"],
        "telegram_id": telegram_id,
        "time": datetime.now().strftime("%H:%M"),
        "overall": overall_rating,
        "reason_selected": reason_selected or [],
        "reason_text": reason_text,
        "item_feedbacks": item_feedbacks or [],
    }

    data["feedbacks"].append(feedback)
    return _write_json(feedback_path, data)


def get_user_feedbacks(telegram_id: str, days: int = 7) -> List[Dict[str, Any]]:
    """Get user's feedback history for the past N days."""
    user = get_user(telegram_id)
    if not user:
        return []

    feedbacks = []
    from datetime import timedelta

    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        feedback_path = os.path.join(FEEDBACK_DIR, f"{date}.json")

        data = _read_json(feedback_path)
        for feedback in data.get("feedbacks", []):
            if feedback.get("user_id") == user["id"]:
                feedback["date"] = date
                feedbacks.append(feedback)

    return feedbacks


# ============ Daily Stats Management ============

def save_daily_stats(
    date: str,
    sources_monitored: int,
    raw_items_scanned: int,
    user_stats: Dict[str, Dict[str, Any]]
) -> bool:
    """Save daily statistics."""
    stats_path = os.path.join(DAILY_STATS_DIR, f"{date}.json")

    data = {
        "date": date,
        "sources_monitored": sources_monitored,
        "raw_items_scanned": raw_items_scanned,
        "users": user_stats,
    }

    return _write_json(stats_path, data)


def get_daily_stats(date: Optional[str] = None) -> Dict[str, Any]:
    """Get daily statistics."""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    stats_path = os.path.join(DAILY_STATS_DIR, f"{date}.json")
    return _read_json(stats_path)


# ============ Raw Content Management ============

def save_raw_content(date: str, items: List[Dict[str, Any]]) -> bool:
    """Save raw fetched content for a day."""
    content_path = os.path.join(RAW_CONTENT_DIR, f"{date}.json")

    data = {
        "date": date,
        "fetched_at": datetime.now().isoformat(),
        "count": len(items),
        "items": items,
    }

    return _write_json(content_path, data)


def get_raw_content(date: Optional[str] = None) -> Dict[str, Any]:
    """Get raw content for a day."""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    content_path = os.path.join(RAW_CONTENT_DIR, f"{date}.json")
    return _read_json(content_path)


# ============ User Sources Management ============


def get_user_sources(telegram_id: str) -> Dict[str, Dict[str, str]]:
    """Get user's RSS source configuration."""
    user = get_user(telegram_id)
    if not user:
        return DEFAULT_USER_SOURCES.copy()

    _ensure_dir(USER_SOURCES_DIR)
    sources_path = os.path.join(USER_SOURCES_DIR, f"{user['id']}.json")

    if not os.path.exists(sources_path):
        # Initialize with default sources
        save_user_sources(telegram_id, DEFAULT_USER_SOURCES)
        return DEFAULT_USER_SOURCES.copy()

    data = _read_json(sources_path)
    return data.get("sources", DEFAULT_USER_SOURCES.copy())


def save_user_sources(telegram_id: str, sources: Dict[str, Dict[str, str]]) -> bool:
    """Save user's RSS source configuration."""
    user = get_user(telegram_id)
    if not user:
        logger.error(f"Cannot save sources: user {telegram_id} not found")
        return False

    _ensure_dir(USER_SOURCES_DIR)
    sources_path = os.path.join(USER_SOURCES_DIR, f"{user['id']}.json")

    data = {
        "user_id": user["id"],
        "telegram_id": telegram_id,
        "updated": datetime.now().isoformat(),
        "sources": sources,
    }

    result = _write_json(sources_path, data)
    if result:
        logger.info(f"Saved sources for user {user['id']}")
    return result


def add_user_source(telegram_id: str, category: str, name: str, url: str) -> bool:
    """Add a source to user's configuration."""
    sources = get_user_sources(telegram_id)

    if category not in sources:
        sources[category] = {}

    sources[category][name] = url
    return save_user_sources(telegram_id, sources)


def remove_user_source(telegram_id: str, category: str, name: str) -> bool:
    """Remove a source from user's configuration."""
    sources = get_user_sources(telegram_id)

    if category in sources and name in sources[category]:
        del sources[category][name]
        return save_user_sources(telegram_id, sources)
    return False


# ============ Per-User Raw Content ============

def save_user_raw_content(
    telegram_id: str,
    date: str,
    items: List[Dict[str, Any]],
    user_id: Optional[str] = None
) -> bool:
    """Save raw fetched content for a user on a specific day.

    Args:
        telegram_id: User's Telegram ID
        date: Date string (YYYY-MM-DD)
        items: Raw content items
        user_id: Optional user ID (avoids file lock race condition)
    """
    if not user_id:
        user = get_user(telegram_id)
        if not user:
            return False
        user_id = user["id"]

    user_content_dir = os.path.join(RAW_CONTENT_DIR, user_id)
    _ensure_dir(user_content_dir)
    content_path = os.path.join(user_content_dir, f"{date}.json")

    data = {
        "date": date,
        "user_id": user_id,
        "fetched_at": datetime.now().isoformat(),
        "count": len(items),
        "items": items,
    }

    return _write_json(content_path, data)


def get_user_raw_content(telegram_id: str, date: Optional[str] = None) -> Dict[str, Any]:
    """Get raw content for a user on a specific day."""
    user = get_user(telegram_id)
    if not user:
        return {}

    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    user_content_dir = os.path.join(RAW_CONTENT_DIR, user["id"])
    content_path = os.path.join(user_content_dir, f"{date}.json")
    return _read_json(content_path)


# ============ Per-User Daily Stats ============

def save_user_daily_stats(
    telegram_id: str,
    date: str,
    sources_monitored: int,
    raw_items_scanned: int,
    items_sent: int,
    status: str = "success",
    filtered_items: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[str] = None
) -> bool:
    """Save daily statistics for a specific user.

    Args:
        telegram_id: User's Telegram ID
        date: Date string (YYYY-MM-DD)
        sources_monitored: Number of sources monitored
        raw_items_scanned: Number of raw items scanned
        items_sent: Number of items sent
        status: Status string (default "success")
        filtered_items: Filtered items list (optional)
        user_id: Optional user ID (avoids file lock race condition)
    """
    if not user_id:
        user = get_user(telegram_id)
        if not user:
            return False
        user_id = user["id"]

    user_stats_dir = os.path.join(DAILY_STATS_DIR, user_id)
    _ensure_dir(user_stats_dir)
    stats_path = os.path.join(user_stats_dir, f"{date}.json")

    data = {
        "date": date,
        "user_id": user_id,
        "sources_monitored": sources_monitored,
        "raw_items_scanned": raw_items_scanned,
        "items_sent": items_sent,
        "status": status,
    }

    # Save filtered items for re-viewing the digest
    if filtered_items is not None:
        data["filtered_items"] = filtered_items

    return _write_json(stats_path, data)


def get_user_daily_stats(telegram_id: str, date: Optional[str] = None) -> Dict[str, Any]:
    """Get daily statistics for a specific user."""
    user = get_user(telegram_id)
    if not user:
        return {}

    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    user_stats_dir = os.path.join(DAILY_STATS_DIR, user["id"])
    stats_path = os.path.join(user_stats_dir, f"{date}.json")
    return _read_json(stats_path)


# ============ Data Cleanup ============

def _cleanup_old_files_in_dir(directory: str, retention_days: int) -> int:
    """
    Delete files older than retention_days in a directory.

    清理指定目录中超过保留天数的文件。
    支持 {date}.json 格式的文件名。

    Returns:
        Number of files deleted
    """
    if not os.path.exists(directory):
        return 0

    deleted_count = 0
    cutoff_date = datetime.now() - timedelta(days=retention_days)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d")

    try:
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)

            # Skip directories (handle user subdirectories separately)
            if os.path.isdir(filepath):
                continue

            # Extract date from filename (format: {date}.json)
            if filename.endswith(".json"):
                date_part = filename.replace(".json", "")
                try:
                    # Validate date format
                    datetime.strptime(date_part, "%Y-%m-%d")
                    if date_part < cutoff_str:
                        os.remove(filepath)
                        deleted_count += 1
                        logger.debug(f"Deleted old file: {filepath}")
                except ValueError:
                    # Not a date-formatted file, skip
                    continue
    except Exception as e:
        logger.error(f"Error cleaning up {directory}: {e}")

    return deleted_count


def cleanup_old_data() -> Dict[str, int]:
    """
    Clean up old data files based on retention settings.

    根据配置的保留天数清理过期数据：
    - raw_content: RAW_CONTENT_RETENTION_DAYS (默认7天)
    - daily_stats: DAILY_STATS_RETENTION_DAYS (默认30天)
    - feedback: FEEDBACK_RETENTION_DAYS (默认30天)

    Returns:
        Dict with cleanup counts for each category
    """
    results = {
        "raw_content": 0,
        "daily_stats": 0,
        "feedback": 0,
    }

    # Clean feedback directory
    results["feedback"] = _cleanup_old_files_in_dir(
        FEEDBACK_DIR, FEEDBACK_RETENTION_DAYS
    )

    # Clean raw_content - handle per-user subdirectories
    if os.path.exists(RAW_CONTENT_DIR):
        root_level_cleaned = False
        for item in os.listdir(RAW_CONTENT_DIR):
            item_path = os.path.join(RAW_CONTENT_DIR, item)
            if os.path.isdir(item_path):
                # User subdirectory
                results["raw_content"] += _cleanup_old_files_in_dir(
                    item_path, RAW_CONTENT_RETENTION_DAYS
                )
            elif item.endswith(".json") and not root_level_cleaned:
                # Legacy global files - only process root level once
                results["raw_content"] += _cleanup_old_files_in_dir(
                    RAW_CONTENT_DIR, RAW_CONTENT_RETENTION_DAYS
                )
                root_level_cleaned = True

    # Clean daily_stats - handle per-user subdirectories
    if os.path.exists(DAILY_STATS_DIR):
        root_level_cleaned = False
        for item in os.listdir(DAILY_STATS_DIR):
            item_path = os.path.join(DAILY_STATS_DIR, item)
            if os.path.isdir(item_path):
                # User subdirectory
                results["daily_stats"] += _cleanup_old_files_in_dir(
                    item_path, DAILY_STATS_RETENTION_DAYS
                )
            elif item.endswith(".json") and not root_level_cleaned:
                # Legacy global files - only process root level once
                results["daily_stats"] += _cleanup_old_files_in_dir(
                    DAILY_STATS_DIR, DAILY_STATS_RETENTION_DAYS
                )
                root_level_cleaned = True

    total = sum(results.values())
    if total > 0:
        logger.info(
            f"Data cleanup complete: {results['raw_content']} raw_content, "
            f"{results['daily_stats']} daily_stats, {results['feedback']} feedback files deleted"
        )

    return results


# ============ Prefetch Cache Management ============

def get_prefetch_cache(date: Optional[str] = None) -> Dict[str, Any]:
    """
    获取指定日期的预抓取缓存。

    Args:
        date: 日期字符串 (YYYY-MM-DD)，默认为今天

    Returns:
        缓存数据字典，包含 seen_ids 和 items
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    _ensure_dir(PREFETCH_CACHE_DIR)
    cache_path = os.path.join(PREFETCH_CACHE_DIR, f"{date}.json")

    data = _read_json(cache_path)
    if not data:
        # 初始化空缓存
        data = {
            "date": date,
            "seen_ids": [],
            "items": [],
            "fetch_count": 0,
            "last_fetch": None,
        }

    return data


def save_prefetch_cache(
    items: List[Dict[str, Any]],
    date: Optional[str] = None
) -> Dict[str, int]:
    """
    保存预抓取的内容到缓存，自动去重。

    Args:
        items: 新抓取的内容列表
        date: 日期字符串 (YYYY-MM-DD)，默认为今天

    Returns:
        统计信息 {"new_items": N, "total_items": M, "duplicates": D}
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    # 读取现有缓存
    cache = get_prefetch_cache(date)
    seen_ids = set(cache.get("seen_ids", []))
    existing_items = cache.get("items", [])

    # 去重添加新内容
    new_count = 0
    duplicate_count = 0

    for item in items:
        item_id = item.get("id")
        if item_id and item_id not in seen_ids:
            seen_ids.add(item_id)
            existing_items.append(item)
            new_count += 1
        else:
            duplicate_count += 1

    # 更新缓存
    cache["seen_ids"] = list(seen_ids)
    cache["items"] = existing_items
    cache["fetch_count"] = cache.get("fetch_count", 0) + 1
    cache["last_fetch"] = datetime.now().isoformat()

    # 保存
    _ensure_dir(PREFETCH_CACHE_DIR)
    cache_path = os.path.join(PREFETCH_CACHE_DIR, f"{date}.json")
    _write_json(cache_path, cache)

    stats = {
        "new_items": new_count,
        "total_items": len(existing_items),
        "duplicates": duplicate_count,
    }

    logger.info(
        f"Prefetch cache updated: +{new_count} new, {duplicate_count} duplicates, "
        f"{len(existing_items)} total items"
    )

    return stats


def get_prefetch_items(date: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    获取指定日期的所有预抓取内容（已去重）。

    Args:
        date: 日期字符串 (YYYY-MM-DD)，默认为今天

    Returns:
        内容列表
    """
    cache = get_prefetch_cache(date)
    return cache.get("items", [])


def clear_prefetch_cache(date: Optional[str] = None) -> bool:
    """
    清除指定日期的预抓取缓存。

    Args:
        date: 日期字符串 (YYYY-MM-DD)，默认为今天

    Returns:
        是否成功
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    cache_path = os.path.join(PREFETCH_CACHE_DIR, f"{date}.json")

    try:
        if os.path.exists(cache_path):
            os.remove(cache_path)
            logger.info(f"Cleared prefetch cache for {date}")
        return True
    except Exception as e:
        logger.error(f"Error clearing prefetch cache: {e}")
        return False


def cleanup_prefetch_cache(retention_days: int = 2) -> int:
    """
    清理过期的预抓取缓存（默认保留 2 天）。

    Args:
        retention_days: 保留天数

    Returns:
        删除的文件数
    """
    return _cleanup_old_files_in_dir(PREFETCH_CACHE_DIR, retention_days)


# ============ Whitelist Management ============

def get_whitelist() -> List[int]:
    """Get whitelisted user IDs."""
    from config import WHITELIST_FILE
    
    data = _read_json(WHITELIST_FILE)
    return data.get("whitelisted_ids", [])


def add_to_whitelist(telegram_id: int) -> bool:
    """Add user to whitelist."""
    from config import WHITELIST_FILE
    
    data = _read_json(WHITELIST_FILE)
    if "whitelisted_ids" not in data:
        data["whitelisted_ids"] = []
        
    if telegram_id not in data["whitelisted_ids"]:
        data["whitelisted_ids"].append(telegram_id)
        return _write_json(WHITELIST_FILE, data)
    
    return True


def remove_from_whitelist(telegram_id: int) -> bool:
    """Remove user from whitelist."""
    from config import WHITELIST_FILE
    
    data = _read_json(WHITELIST_FILE)
    if "whitelisted_ids" not in data:
        return False
        
    if telegram_id in data["whitelisted_ids"]:
        data["whitelisted_ids"].remove(telegram_id)
        return _write_json(WHITELIST_FILE, data)
        
    return False

# ============ Whitelist Settings ============

def get_whitelist_enabled() -> bool:
    """Get whitelist enabled status. Reads from settings file or defaults to env config."""
    from config import WHITELIST_SETTINGS_FILE, WHITELIST_ENABLED_DEFAULT
    
    data = _read_json(WHITELIST_SETTINGS_FILE)
    if "enabled" in data:
        return data["enabled"]
    return WHITELIST_ENABLED_DEFAULT


def set_whitelist_enabled(enabled: bool) -> bool:
    """Set whitelist enabled status. Saves to settings file."""
    from config import WHITELIST_SETTINGS_FILE
    
    data = _read_json(WHITELIST_SETTINGS_FILE)
    data["enabled"] = enabled
    return _write_json(WHITELIST_SETTINGS_FILE, data)


def is_whitelisted(telegram_id: int) -> bool:
    """Check if user is whitelisted (considering whitelist enabled status)."""
    from config import ADMIN_TELEGRAM_IDS
    
    # Admins are always allowed
    if str(telegram_id) in ADMIN_TELEGRAM_IDS:
        return True
    
    # If whitelist is disabled, everyone is allowed
    if not get_whitelist_enabled():
        return True
        
    # Check whitelist
    whitelist = get_whitelist()
    return telegram_id in whitelist
