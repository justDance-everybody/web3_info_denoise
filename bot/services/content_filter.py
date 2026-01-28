"""
AI Content Filter Service

Uses Gemini 3 to intelligently filter content based on user profiles.
Selects relevant items from raw content and ranks by importance.

Features:
- Automatic retry with model switching for improved reliability
- Primary model failure -> retry with lower temperature
- Primary model multiple failures -> switch to fallback model
- All AI outputs in English, translation at final stage

Reference: Plan specification for content filtering with Gemini 3
"""
import json
import logging
from typing import List, Dict, Any, Optional

from services.gemini import call_gemini_json, call_gemini
from services.llm_factory import call_llm_json, call_llm_text
from utils.json_storage import get_user_profile, get_user_feedbacks
from utils.prompt_loader import get_prompt
from config import MIN_DIGEST_ITEMS, MAX_DIGEST_ITEMS, MAX_AI_INPUT_ITEMS

logger = logging.getLogger(__name__)


DEFAULT_PROFILE = """This is a new user who hasn't set specific preferences yet.

[Focus Areas]
- General Web3 news and updates
- Major protocol and ecosystem developments
- Market-moving news and announcements

[Content Preferences]
- Balanced mix of news and analysis
- Moderate volume (10-15 items per day)

[Sources]
- No specific preferences yet"""


def summarize_feedbacks(feedbacks: List[Dict[str, Any]]) -> str:
    """Summarize recent user feedbacks for AI context."""
    if not feedbacks:
        return "No feedback history available."

    positive_count = 0
    negative_count = 0
    reasons = []

    for fb in feedbacks:
        if fb.get("overall") == "positive":
            positive_count += 1
        elif fb.get("overall") == "negative":
            negative_count += 1
            if fb.get("reason_selected"):
                reasons.extend(fb["reason_selected"])
            if fb.get("reason_text"):
                reasons.append(fb["reason_text"])

    summary_parts = [
        f"Recent 7 days: {positive_count} positive, {negative_count} negative ratings."
    ]

    if reasons:
        unique_reasons = list(set(reasons))[:5]
        summary_parts.append(f"Main concerns: {', '.join(unique_reasons)}")

    return " ".join(summary_parts)


async def filter_content_for_user(
    telegram_id: str,
    raw_content: List[Dict[str, Any]],
    max_items: int = 20
) -> List[Dict[str, Any]]:
    """
    Filter raw content based on user profile using AI.
    
    Optimized I/O: Uses compact input format (n/src/t) and output format (n/r)
    to reduce token usage by ~40%.
    
    Supports batch processing when content exceeds MAX_AI_INPUT_ITEMS.

    Args:
        telegram_id: User's Telegram ID
        raw_content: List of raw content items to filter
        max_items: Maximum number of items to return

    Returns:
        List of filtered and ranked content items
    """
    if not raw_content:
        logger.warning(f"No content to filter for user {telegram_id}")
        return []

    # Check if batch processing is needed
    if MAX_AI_INPUT_ITEMS > 0 and len(raw_content) > MAX_AI_INPUT_ITEMS:
        logger.info(f"Content count {len(raw_content)} exceeds limit {MAX_AI_INPUT_ITEMS}, using batch processing")
        return await _filter_content_batched(telegram_id, raw_content, max_items)

    # Get user profile
    profile = get_user_profile(telegram_id)
    if not profile:
        logger.info(f"No profile found for {telegram_id}, using default")
        profile = DEFAULT_PROFILE

    # Get feedback history
    feedbacks = get_user_feedbacks(telegram_id, days=7)
    feedback_summary = summarize_feedbacks(feedbacks)

    # Build index map for later mapping (n -> original item)
    index_map: Dict[int, Dict[str, Any]] = {}
    
    # Prepare OPTIMIZED content list for AI (compact format)
    # No artificial limit - let AI see all available content for best filtering
    content_for_ai = []
    for i, item in enumerate(raw_content, 1):
        index_map[i] = item
        
        # Merge title and summary intelligently
        title = item.get("title", "")
        summary = item.get("summary", "")
        
        # If summary adds more info beyond title, include it
        if len(summary) > len(title) and summary not in title:
            content = f"{title} | {summary}"
        else:
            content = title if len(title) >= len(summary) else summary
        
        # Compact format: n (index), src (source), t (content)
        # Removed: id, link, category (not needed for AI analysis)
        content_for_ai.append({
            "n": i,
            "src": item.get("source", ""),
            "t": content
        })

    # Build prompt with optimized system instruction
    system_instruction = get_prompt(
        "filtering.txt",
        user_profile=profile,
        feedback_summary=feedback_summary,
        min_items=MIN_DIGEST_ITEMS,
        max_items=MAX_DIGEST_ITEMS
    )

    # Compact prompt format (no indent, saves tokens)
    prompt = f"""## Content to filter today ({len(content_for_ai)} items)

{json.dumps(content_for_ai, ensure_ascii=False)}

Please categorize and output {MIN_DIGEST_ITEMS}-{MAX_DIGEST_ITEMS} items."""

    # Call AI with automatic retry and model switching
    filtered_result, model_used = await call_llm_json(
        prompt=prompt,
        system_instruction=system_instruction,
        context=f"filtering-{telegram_id}"
    )
    
    # Check if all attempts failed
    if filtered_result is None:
        logger.error(f"All AI attempts failed for user {telegram_id}, using fallback")
        return _build_fallback_result(raw_content, max_items, "Fallback: AI unavailable")

    # Handle optimized format: {must_read: [{n, r}], ...}
    if isinstance(filtered_result, dict):
        all_items = []
        
        for section in ["must_read", "macro_insights", "recommended", "other"]:
            items = filtered_result.get(section, [])
            for ai_item in items:
                n = ai_item.get("n")
                if n and n in index_map:
                    # Map back to original item with full data
                    original = index_map[n]
                    mapped_item = {
                        "id": original.get("id"),
                        "title": original.get("title"),
                        "summary": original.get("summary", "")[:100],
                        "source": original.get("source"),
                        "link": original.get("link"),
                        "section": section,
                        "reason": ai_item.get("r", ""),
                        "author": original.get("author", "")  # Keep author for Twitter
                    }
                    all_items.append(mapped_item)
                else:
                    logger.warning(f"Invalid index {n} in AI response")

        total_count = len(all_items)
        section_counts = {}
        for item in all_items:
            s = item.get("section", "other")
            section_counts[s] = section_counts.get(s, 0) + 1

        logger.info(f"AI selected {total_count} items for user {telegram_id} using {model_used} "
                   f"(must_read: {section_counts.get('must_read', 0)}, "
                   f"macro: {section_counts.get('macro_insights', 0)}, "
                   f"recommended: {section_counts.get('recommended', 0)}, "
                   f"other: {section_counts.get('other', 0)})")
        return all_items[:max_items]

    logger.error(f"Unexpected response format: {type(filtered_result)}")
    return _build_fallback_result(raw_content, max_items, "Fallback: invalid AI response")


def _build_fallback_result(raw_content: List[Dict[str, Any]], max_items: int, reason: str) -> List[Dict[str, Any]]:
    """Build fallback result when AI filtering fails."""
    return [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "summary": item.get("summary", "")[:100],
            "source": item.get("source"),
            "link": item.get("link"),
            "section": "other",
            "reason": reason
        }
        for item in raw_content[:max_items]
    ]


async def _filter_content_batched(
    telegram_id: str,
    raw_content: List[Dict[str, Any]],
    max_items: int = 20
) -> List[Dict[str, Any]]:
    """
    Process content in batches when total count exceeds MAX_AI_INPUT_ITEMS.
    
    Strategy:
    1. Split content into batches of MAX_AI_INPUT_ITEMS
    2. Filter each batch with AI
    3. Merge results by section priority
    4. Return top max_items
    """
    batch_size = MAX_AI_INPUT_ITEMS
    total_items = len(raw_content)
    num_batches = (total_items + batch_size - 1) // batch_size
    
    logger.info(f"Batch processing: {total_items} items in {num_batches} batches of {batch_size}")
    
    # Process each batch
    all_results = []
    for batch_idx in range(num_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, total_items)
        batch = raw_content[start:end]
        
        logger.info(f"Processing batch {batch_idx + 1}/{num_batches}: items {start + 1}-{end}")
        
        # Temporarily set MAX_AI_INPUT_ITEMS to 0 to avoid recursion
        # Call the main filter function for this batch
        batch_results = await _filter_single_batch(telegram_id, batch, max_items)
        all_results.extend(batch_results)
    
    # Merge and sort by section priority
    section_priority = {"must_read": 0, "macro_insights": 1, "recommended": 2, "other": 3}
    all_results.sort(key=lambda x: section_priority.get(x.get("section", "other"), 3))
    
    # Deduplicate by title (in case same news appears in multiple batches)
    seen_titles = set()
    unique_results = []
    for item in all_results:
        title = item.get("title", "")
        if title not in seen_titles:
            seen_titles.add(title)
            unique_results.append(item)
    
    logger.info(f"Batch processing complete: {len(unique_results)} unique items from {len(all_results)} total")
    return unique_results[:max_items]


async def _filter_single_batch(
    telegram_id: str,
    batch_content: List[Dict[str, Any]],
    max_items: int
) -> List[Dict[str, Any]]:
    """Filter a single batch of content (internal helper for batch processing)."""
    # Get user profile
    profile = get_user_profile(telegram_id)
    if not profile:
        profile = DEFAULT_PROFILE
    
    feedbacks = get_user_feedbacks(telegram_id, days=7)
    feedback_summary = summarize_feedbacks(feedbacks)
    
    # Build index map
    index_map: Dict[int, Dict[str, Any]] = {}
    content_for_ai = []
    
    for i, item in enumerate(batch_content, 1):
        index_map[i] = item
        title = item.get("title", "")
        summary = item.get("summary", "")
        
        if len(summary) > len(title) and summary not in title:
            content = f"{title} | {summary}"
        else:
            content = title if len(title) >= len(summary) else summary
        
        content_for_ai.append({
            "n": i,
            "src": item.get("source", ""),
            "t": content
        })
    
    # Build prompt
    system_instruction = get_prompt(
        "filtering.txt",
        user_profile=profile,
        feedback_summary=feedback_summary,
        min_items=MIN_DIGEST_ITEMS,
        max_items=MAX_DIGEST_ITEMS
    )
    
    prompt = f"""## Content to filter (batch, {len(content_for_ai)} items)

{json.dumps(content_for_ai, ensure_ascii=False)}

Please categorize and output {MIN_DIGEST_ITEMS}-{MAX_DIGEST_ITEMS} items."""

    # Use retry logic for batch processing too
    filtered_result, model_used = await call_llm_json(
        prompt=prompt,
        system_instruction=system_instruction,
        context=f"batch-filtering-{telegram_id}"
    )
    
    if filtered_result is None:
        return _build_fallback_result(batch_content, max_items, "Batch AI failed")
    
    if isinstance(filtered_result, dict):
        all_items = []
        for section in ["must_read", "macro_insights", "recommended", "other"]:
            items = filtered_result.get(section, [])
            for ai_item in items:
                n = ai_item.get("n")
                if n and n in index_map:
                    original = index_map[n]
                    all_items.append({
                        "id": original.get("id"),
                        "title": original.get("title"),
                        "summary": original.get("summary", "")[:100],
                        "source": original.get("source"),
                        "author": original.get("author", ""),
                        "link": original.get("link"),
                        "section": section,
                        "reason": ai_item.get("r", "")
                    })
        return all_items
    
    return _build_fallback_result(batch_content, max_items, "Batch AI error")


async def categorize_filtered_content(
    filtered_items: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Categorize filtered content into sections for the report.

    Args:
        filtered_items: List of filtered content items

    Returns:
        Dict with categories as keys and item lists as values
    """
    categories = {
        "top_stories": [],
        "defi": [],
        "nft": [],
        "layer2": [],
        "trading": [],
        "development": [],
        "other": []
    }

    # Separate high importance items as top stories
    for item in filtered_items:
        if item.get("importance") == "high" and len(categories["top_stories"]) < 3:
            categories["top_stories"].append(item)
        else:
            # Simple keyword-based categorization
            title_lower = (item.get("title", "") + " " + item.get("summary", "")).lower()

            if any(kw in title_lower for kw in ["defi", "lending", "yield", "liquidity", "swap"]):
                categories["defi"].append(item)
            elif any(kw in title_lower for kw in ["nft", "opensea", "blur", "collection"]):
                categories["nft"].append(item)
            elif any(kw in title_lower for kw in ["layer2", "l2", "arbitrum", "optimism", "zksync", "rollup"]):
                categories["layer2"].append(item)
            elif any(kw in title_lower for kw in ["trade", "trading", "long", "short", "whale"]):
                categories["trading"].append(item)
            elif any(kw in title_lower for kw in ["developer", "github", "upgrade", "fork", "code"]):
                categories["development"].append(item)
            else:
                categories["other"].append(item)

    # Remove empty categories
    return {k: v for k, v in categories.items() if v}


async def get_ai_summary(
    items: List[Dict[str, Any]],
    user_profile: str
) -> str:
    """
    Generate a brief AI summary of today's key themes.
    
    Uses unified retry mechanism with model switching.

    Args:
        items: List of filtered items
        user_profile: User's profile for context

    Returns:
        Brief summary text (2-3 sentences)
    """
    if not items:
        return "No significant updates today."

    # Use all filtered items for summary (typically 15-30 items)
    titles = [item.get("title", "") for item in items]

    # Load prompt from file
    prompt = get_prompt(
        "report.txt",
        user_profile=user_profile[:200],
        headlines=json.dumps(titles, ensure_ascii=False)
    )

    # Use unified retry mechanism
    summary, model_used = await call_llm_text(
        prompt=prompt,
        temperature=0.7,
        context="ai-summary"
    )
    
    if summary:
        return summary.strip()
    
    logger.error("Failed to generate AI summary, using fallback")
    return "Today's digest covers the latest Web3 developments across your areas of interest."


def get_user_target_language(profile: str) -> str:
    """
    Get user's target language from profile for final translation.
    
    This function determines what language the final output should be in.
    Default is Chinese as most users are Chinese-speaking.
    
    Args:
        profile: User's profile text
        
    Returns:
        Target language name (e.g., "Chinese", "English", "Japanese")
    """
    if not profile:
        return "Chinese"  # Default to Chinese
    
    profile_lower = profile.lower()
    
    # Check for explicit language markers
    # Chinese
    if any(marker in profile for marker in ["用户语言", "中文", "简体", "繁體"]):
        return "Chinese"
    if "chinese" in profile_lower:
        return "Chinese"
    
    # English
    if any(marker in profile_lower for marker in ["english", "英文", "英语"]):
        return "English"
    
    # Japanese
    if any(marker in profile for marker in ["日本語", "日语"]):
        return "Japanese"
    if "japanese" in profile_lower:
        return "Japanese"
    
    # Korean
    if any(marker in profile for marker in ["한국어", "韩语", "韓語"]):
        return "Korean"
    if "korean" in profile_lower:
        return "Korean"
    
    # Spanish
    if any(marker in profile_lower for marker in ["español", "spanish", "西班牙语"]):
        return "Spanish"
    
    # Detect by character ranges in profile
    for char in profile[:200]:  # Check first 200 chars
        # Chinese characters
        if '\u4e00' <= char <= '\u9fff':
            return "Chinese"
        # Japanese Hiragana/Katakana
        if '\u3040' <= char <= '\u30ff':
            return "Japanese"
        # Korean Hangul
        if '\uac00' <= char <= '\ud7af' or '\u1100' <= char <= '\u11ff':
            return "Korean"
    
    return "Chinese"  # Default to Chinese


# Backward compatibility alias
def _extract_user_language(profile: str) -> str:
    """Deprecated: Use get_user_target_language() instead."""
    lang = get_user_target_language(profile)
    # Map to old format for compatibility
    lang_map = {
        "Chinese": "中文",
        "Japanese": "日本語",
        "Korean": "한국어",
        "Spanish": "Español",
        "English": "English"
    }
    return lang_map.get(lang, lang)


async def translate_text(text: str, target_language: str) -> str:
    """
    Translate a plain text string to target language.
    
    Uses unified retry mechanism with model switching for reliability.
    Used for translating AI summary and other text content.
    
    Args:
        text: Text to translate
        target_language: Target language (e.g., "Chinese", "Japanese")
    
    Returns:
        Translated text
    """
    if not text or target_language.lower() == "english":
        return text
    
    prompt = f"Translate the following to {target_language}. Output only the translation, no extra text:\n\n{text}"
    
    # Use unified retry mechanism
    result, model_used = await call_llm_text(
        prompt=prompt,
        temperature=0.3,
        context="text-translation"
    )
    
    if result:
        return result.strip()
    
    logger.error("Text translation failed, returning original")
    return text


def _has_non_english_content(items: List[Dict[str, Any]]) -> bool:
    """Check if items contain non-English content (e.g., Chinese)."""
    for item in items:
        text = (item.get("title", "") + item.get("summary", ""))[:500]
        for char in text:
            # Chinese characters
            if '\u4e00' <= char <= '\u9fff':
                return True
            # Japanese Hiragana/Katakana
            if '\u3040' <= char <= '\u30ff':
                return True
            # Korean Hangul
            if '\uac00' <= char <= '\ud7af':
                return True
    return False


async def translate_content(
    items: List[Dict[str, Any]],
    target_language: str
) -> List[Dict[str, Any]]:
    """
    Translate filtered content to user's preferred language.
    
    This is the final translation step before sending to user.
    Translates: title, summary, reason fields.
    Keeps unchanged: id, source, link, section, author.
    
    Args:
        items: List of filtered content items
        target_language: Target language (e.g., "Chinese", "English", "Japanese")
    
    Returns:
        List of translated content items
    """
    if not items:
        return items
    
    # Normalize target language
    target_lower = target_language.lower()
    
    # If target is English, only translate if there's non-English content
    if target_lower == "english":
        if not _has_non_english_content(items):
            logger.info("Target is English and content is already English, skipping translation")
            return items
        logger.info(f"Target is English but content has non-English, translating {len(items)} items")
    else:
        logger.info(f"Translating {len(items)} items to {target_language}")
    
    # Prepare content for translation
    content_to_translate = []
    for item in items:
        content_to_translate.append({
            "id": item.get("id"),
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "reason": item.get("reason", ""),
            "source": item.get("source", ""),
            "link": item.get("link", ""),
            "section": item.get("section", "other"),
            "author": item.get("author", "")  # Keep author field
        })
    
    # Build translation prompt
    prompt = get_prompt(
        "translate.txt",
        target_language=target_language,
        content=json.dumps(content_to_translate, ensure_ascii=False, indent=2)
    )
    
    # Use unified retry mechanism with model switching for translation
    translated_result, model_used = await call_llm_json(
        prompt=prompt,
        system_instruction="You are a professional translator. Output valid JSON only.",
        temperature=0.3,  # Low temperature for accurate translation
        context="translation"
    )
    
    if translated_result is None:
        logger.error(f"All translation attempts failed, returning original")
        return items
    
    # Process result
    if isinstance(translated_result, list):
        logger.info(f"Translation successful using {model_used}: {len(translated_result)} items")
        return translated_result
    elif isinstance(translated_result, dict) and "error" not in translated_result:
        # May return wrapped result
        if "items" in translated_result:
            return translated_result["items"]
        logger.warning("Unexpected translation format, using original")
        return items
    else:
        logger.error(f"Translation failed: {translated_result}")
        return items


async def filter_and_translate_for_user(
    telegram_id: str,
    raw_content: List[Dict[str, Any]],
    max_items: int = 20
) -> List[Dict[str, Any]]:
    """
    Filter content for user (filtering only, no translation).
    
    Translation is handled at the final output stage, not here.
    This keeps the middle processing language-agnostic.
    
    Args:
        telegram_id: User's Telegram ID
        raw_content: List of raw content items
        max_items: Maximum number of items
    
    Returns:
        List of filtered content items (original language)
    """
    # Only filter, no translation (translation happens at final output)
    return await filter_content_for_user(telegram_id, raw_content, max_items)
