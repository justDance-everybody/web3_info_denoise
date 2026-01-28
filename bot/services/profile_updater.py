"""
Profile Updater Service

Analyzes user feedback and updates user profiles using AI.
Implements the feedback learning loop for personalization.

Reference: Plan specification for profile update with Gemini 3
"""
import logging
from typing import List, Dict, Any, Optional

from services.gemini import call_gemini
from utils.prompt_loader import get_prompt
from utils.json_storage import (
    get_users,
    get_user,
    get_user_profile,
    save_user_profile,
    get_user_feedbacks,
)

logger = logging.getLogger(__name__)


def format_feedbacks_for_ai(feedbacks: List[Dict[str, Any]]) -> str:
    """Format feedback records for AI analysis."""
    if not feedbacks:
        return "No feedback records available."

    formatted = []
    for fb in feedbacks:
        date = fb.get("date", "Unknown")
        time = fb.get("time", "")
        overall = fb.get("overall", "")
        reasons = fb.get("reason_selected", [])
        reason_text = fb.get("reason_text", "")
        item_fbs = fb.get("item_feedbacks", [])

        entry = f"- {date} {time}: {overall.upper()}"
        if reasons:
            entry += f" | Reasons: {', '.join(reasons)}"
        if reason_text:
            entry += f" | Comment: {reason_text}"
        if item_fbs:
            likes = sum(1 for i in item_fbs if i.get("feedback") == "like")
            dislikes = sum(1 for i in item_fbs if i.get("feedback") == "dislike")
            stars = sum(1 for i in item_fbs if i.get("feedback") == "star")
            if likes or dislikes or stars:
                entry += f" | Items: {likes} liked, {dislikes} disliked, {stars} starred"

        formatted.append(entry)

    return "\n".join(formatted)


async def update_user_profile(telegram_id: str) -> Optional[str]:
    """
    Analyze feedback and update a user's profile.

    Args:
        telegram_id: User's Telegram ID

    Returns:
        Updated profile string, or None if update failed
    """
    user = get_user(telegram_id)
    if not user:
        logger.warning(f"Cannot update profile: user {telegram_id} not found")
        return None

    # Get current profile
    current_profile = get_user_profile(telegram_id)
    if not current_profile:
        logger.info(f"No existing profile for {telegram_id}, skipping update")
        return None

    # Get recent feedbacks
    feedbacks = get_user_feedbacks(telegram_id, days=7)
    if not feedbacks:
        logger.info(f"No feedbacks for {telegram_id}, skipping update")
        return current_profile

    # Format feedbacks for AI
    feedbacks_text = format_feedbacks_for_ai(feedbacks)

    # Load prompt from file
    system_instruction = get_prompt(
        "profile_update.txt",
        current_profile=current_profile,
        recent_feedbacks=feedbacks_text
    )

    prompt = """Based on the current profile and recent feedback history,
generate an updated user profile that better reflects their preferences.

If the feedback suggests significant changes are needed, update accordingly.
If feedback is mostly positive with minor issues, make subtle adjustments.
If there's not enough information to make changes, return the current profile with minimal modifications."""

    try:
        updated_profile = await call_gemini(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=0.5  # Lower temperature for more consistent updates
        )

        # Save the updated profile
        save_user_profile(telegram_id, updated_profile)

        logger.info(f"Updated profile for user {telegram_id}")
        return updated_profile

    except Exception as e:
        logger.error(f"Failed to update profile for {telegram_id}: {e}")
        return None


async def update_all_user_profiles() -> Dict[str, bool]:
    """
    Update profiles for all users with recent feedback.

    Returns:
        Dict mapping telegram_id to success status
    """
    users = get_users()
    results = {}

    for user in users:
        telegram_id = user.get("telegram_id")
        if not telegram_id:
            continue

        try:
            updated = await update_user_profile(telegram_id)
            results[telegram_id] = updated is not None
        except Exception as e:
            logger.error(f"Error updating profile for {telegram_id}: {e}")
            results[telegram_id] = False

    success_count = sum(1 for v in results.values() if v)
    logger.info(f"Profile update complete: {success_count}/{len(results)} successful")

    return results


async def update_user_profile_from_feedback(
    telegram_id: str,
    feedback_type: str,
    item_id: str = None,
    item_title: str = None,
    reason: str = None
) -> Optional[str]:
    """
    Real-time profile update triggered by user feedback.
    Updates profile dynamically without accumulation.

    Args:
        telegram_id: User's Telegram ID
        feedback_type: Type of feedback (like, dislike, positive, negative)
        item_id: Optional item ID that received feedback
        item_title: Optional item title/content for context
        reason: Optional reason for negative feedback

    Returns:
        Updated profile string, or None if update failed
    """
    user = get_user(telegram_id)
    if not user:
        logger.warning(f"Cannot update profile: user {telegram_id} not found")
        return None

    # Get current profile
    current_profile = get_user_profile(telegram_id)
    if not current_profile:
        logger.info(f"No existing profile for {telegram_id}, skipping real-time update")
        return None

    # Build feedback context with actual content
    feedback_context = f"Feedback type: {feedback_type}"
    if item_title:
        feedback_context += f"\nContent: {item_title}"
    if reason:
        feedback_context += f"\nReason: {reason}"

    # Create focused prompt for real-time update
    system_instruction = f"""You are a user preference profile optimizer.

## Task
REFINE the user profile based on this feedback. Fixed length, higher precision.

## Current Profile
{current_profile}

## New Feedback Event
{feedback_context}

## ⚠️ HARD LIMIT: 800 characters max (excluding section headers)

## Update Logic

### For "like" feedback:
- This is EVIDENCE that user likes this type of content
- REFINE the related preference to be more specific
- Example: "关注DeFi" + liked Aave content → "关注DeFi借贷，尤其Aave"
- Do NOT add new lines, UPDATE existing descriptions

### For "dislike" feedback:
- User explicitly doesn't want this type
- Add to [明确不喜欢] section briefly
- OR correct a wrong assumption in [关注领域]

### For "positive" overall:
- Profile is working well, minimal changes
- Maybe slightly refine based on what was liked

### For "negative" overall:
- Something is wrong with current understanding
- Adjust based on the reason provided

## Key Rules
1. REPLACE, don't accumulate - update existing text, don't append
2. REFINE, don't expand - more precise ≠ more words
3. Preserve language preference
4. Keep same structure
5. Maximize information density

## Output
The updated profile only. Same structure, refined content."""

    prompt = "Update the profile based on this feedback event. Output only the updated profile text."

    try:
        updated_profile = await call_gemini(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=0.3  # Lower temperature for consistent updates
        )

        # Save the updated profile
        save_user_profile(telegram_id, updated_profile)

        logger.info(f"Real-time profile update for user {telegram_id}: {feedback_type}")
        return updated_profile

    except Exception as e:
        logger.error(f"Failed real-time profile update for {telegram_id}: {e}")
        return None


async def analyze_feedback_trends(telegram_id: str, days: int = 30) -> Dict[str, Any]:
    """
    Analyze long-term feedback trends for a user.

    Args:
        telegram_id: User's Telegram ID
        days: Number of days to analyze

    Returns:
        Dict with trend analysis
    """
    feedbacks = get_user_feedbacks(telegram_id, days=days)

    if not feedbacks:
        return {
            "total_feedbacks": 0,
            "positive_count": 0,
            "negative_count": 0,
            "positive_rate": 0.0,
            "common_issues": [],
            "trend": "no_data",
        }

    positive = sum(1 for fb in feedbacks if fb.get("overall") == "positive")
    negative = len(feedbacks) - positive

    # Collect all reasons
    all_reasons = []
    for fb in feedbacks:
        all_reasons.extend(fb.get("reason_selected", []))
        if fb.get("reason_text"):
            all_reasons.append(fb["reason_text"])

    # Find common issues
    reason_counts = {}
    for reason in all_reasons:
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    common_issues = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:3]

    # Determine trend (compare first half vs second half)
    mid = len(feedbacks) // 2
    if mid > 0:
        first_half_positive = sum(1 for fb in feedbacks[:mid] if fb.get("overall") == "positive")
        second_half_positive = sum(1 for fb in feedbacks[mid:] if fb.get("overall") == "positive")

        first_rate = first_half_positive / mid if mid > 0 else 0
        second_rate = second_half_positive / (len(feedbacks) - mid) if (len(feedbacks) - mid) > 0 else 0

        if second_rate > first_rate + 0.1:
            trend = "improving"
        elif second_rate < first_rate - 0.1:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "insufficient_data"

    return {
        "total_feedbacks": len(feedbacks),
        "positive_count": positive,
        "negative_count": negative,
        "positive_rate": positive / len(feedbacks) if feedbacks else 0,
        "common_issues": [issue[0] for issue in common_issues],
        "trend": trend,
    }
