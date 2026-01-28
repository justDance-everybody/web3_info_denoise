"""
Automated Test Script for Web3 Daily Digest Bot

Tests all functionality against the test case document.
Run with: python -m pytest tests/test_all_modules.py -v
"""
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============ Module 1: User Registration Tests ============

class TestUserRegistration:
    """TC-1.1, TC-1.2: User registration and Telegram binding"""

    def test_create_new_user(self, tmp_data_dir):
        """TC-1.1: New user can be created"""
        from utils.json_storage import create_user, get_user

        user = create_user(
            telegram_id="123456789",
            username="testuser",
            first_name="Test"
        )

        assert user is not None
        assert user["telegram_id"] == "123456789"
        assert user["username"] == "testuser"
        assert "created" in user

        # Verify retrieval
        retrieved = get_user("123456789")
        assert retrieved is not None
        assert retrieved["telegram_id"] == "123456789"

    def test_existing_user_returns_same(self, tmp_data_dir):
        """TC-1.2: Existing user is recognized"""
        from utils.json_storage import create_user, get_user

        # Create user first time
        user1 = create_user(telegram_id="111222333")

        # Create same user again
        user2 = create_user(telegram_id="111222333")

        assert user1["id"] == user2["id"]


# ============ Module 2: AI Preference Collection Tests ============

class TestPreferenceCollection:
    """TC-2.1-2.4: AI dialogue preference collection"""

    def test_profile_storage(self, tmp_data_dir):
        """TC-2.3: Preferences are correctly stored"""
        from utils.json_storage import create_user, save_user_profile, get_user_profile

        # Create user
        create_user(telegram_id="987654321")

        # Save profile
        profile = """[User Type]
DeFi-focused trader

[Focus Areas]
- DeFi protocols (Uniswap, Aave, Compound)
- Layer 2 solutions (Arbitrum, Optimism)
- On-chain data analysis

[Content Preferences]
- News and analysis
- Whale movements
- 10-15 items per day"""

        result = save_user_profile("987654321", profile)
        assert result is True

        # Verify retrieval
        retrieved = get_user_profile("987654321")
        assert retrieved is not None
        assert "DeFi" in retrieved
        assert "Layer 2" in retrieved


# ============ Module 3: Source Management Tests ============

class TestSourceManagement:
    """TC-3.1-3.4: Information source management"""

    def test_get_source_list(self):
        """TC-3.1: View preset sources"""
        from services.rss_fetcher import get_source_list

        sources = get_source_list()

        assert "twitter" in sources
        assert "websites" in sources
        assert len(sources["twitter"]) > 0
        assert len(sources["websites"]) > 0

    def test_add_twitter_source(self):
        """TC-3.2: Add custom Twitter account"""
        from services.rss_fetcher import add_source, get_source_list, remove_source

        # Add new Twitter source
        result = add_source("twitter", "@TestAccount", "https://rss.app/feeds/test")
        assert result is True

        # Verify added
        sources = get_source_list()
        assert "@TestAccount" in sources["twitter"]

        # Cleanup
        remove_source("twitter", "@TestAccount")

    def test_add_website_source(self):
        """TC-3.3: Add custom website"""
        from services.rss_fetcher import add_source, get_source_list, remove_source

        # Add new website
        result = add_source("websites", "Test Site", "https://example.com/rss")
        assert result is True

        # Verify added
        sources = get_source_list()
        assert "Test Site" in sources["websites"]

        # Cleanup
        remove_source("websites", "Test Site")

    def test_remove_source(self):
        """TC-3.4: Remove source"""
        from services.rss_fetcher import add_source, remove_source, get_source_list

        # Add then remove
        add_source("twitter", "@TempAccount", "https://temp.url")
        result = remove_source("twitter", "@TempAccount")
        assert result is True

        sources = get_source_list()
        assert "@TempAccount" not in sources["twitter"]

    def test_validate_twitter_handle(self):
        """TC-3.2: Validate Twitter handle format"""
        import asyncio
        from services.rss_fetcher import validate_twitter_handle

        # Valid handles
        result = asyncio.run(validate_twitter_handle("@VitalikButerin"))
        assert result["valid"] is True
        assert result["handle"] == "@VitalikButerin"

        result = asyncio.run(validate_twitter_handle("lookonchain"))
        assert result["valid"] is True
        assert result["handle"] == "@lookonchain"

        # Invalid handles
        result = asyncio.run(validate_twitter_handle("@invalid handle with spaces"))
        assert result["valid"] is False

        result = asyncio.run(validate_twitter_handle("@toolonghandlethatexceedslimit"))
        assert result["valid"] is False

    def test_add_custom_twitter_source(self):
        """TC-3.2: Add custom Twitter with validation"""
        import asyncio
        from services.rss_fetcher import add_custom_source, remove_source

        # Valid addition
        result = asyncio.run(add_custom_source("twitter", "@TestUser123"))
        assert result["success"] is True

        # Cleanup
        remove_source("twitter", "@TestUser123")

        # Invalid addition
        result = asyncio.run(add_custom_source("twitter", "invalid handle!!!"))
        assert result["success"] is False

    def test_invalid_source_handling(self):
        """TC-3.4: Invalid source handling"""
        import asyncio
        from services.rss_fetcher import add_custom_source

        # Invalid Twitter handle
        result = asyncio.run(add_custom_source("twitter", "@"))
        assert result["success"] is False
        assert "Invalid" in result["message"]

        # Website without URL
        result = asyncio.run(add_custom_source("websites", "Test Site", ""))
        assert result["success"] is False
        assert "URL" in result["message"]

        # Invalid URL format
        result = asyncio.run(add_custom_source("websites", "Test", "not-a-url"))
        assert result["success"] is False


# ============ Module 4: RSS Fetcher Tests ============

class TestRSSFetcher:
    """TC-4.1-4.4: Information fetching engine"""

    def test_generate_item_id(self):
        """TC-4.4: Deduplication via unique IDs"""
        from services.rss_fetcher import generate_item_id

        entry = {"id": "12345", "link": "https://example.com/post"}
        id1 = generate_item_id(entry, "source1")
        id2 = generate_item_id(entry, "source1")

        # Same entry should produce same ID
        assert id1 == id2

        # Different source should produce different ID
        id3 = generate_item_id(entry, "source2")
        assert id1 != id3

    def test_parse_published_date(self):
        """Test date parsing from RSS entries"""
        from services.rss_fetcher import parse_published_date

        # RFC 2822 format
        entry1 = {"published": "Mon, 01 Jan 2024 12:00:00 GMT"}
        date1 = parse_published_date(entry1)
        assert date1 is not None

        # ISO format
        entry2 = {"updated": "2024-01-01T12:00:00Z"}
        date2 = parse_published_date(entry2)
        assert date2 is not None

    def test_extract_summary(self):
        """Test summary extraction and cleaning"""
        from services.rss_fetcher import extract_summary

        entry = {"summary": "<p>This is <b>HTML</b> content</p>"}
        summary = extract_summary(entry)

        assert "<p>" not in summary
        assert "<b>" not in summary
        assert "HTML" in summary


# ============ Module 5: AI Content Filtering Tests ============

class TestContentFiltering:
    """TC-5.1-5.3: AI intelligent filtering"""

    def test_summarize_feedbacks(self):
        """Test feedback summarization for AI context"""
        from services.content_filter import summarize_feedbacks

        feedbacks = [
            {"overall": "positive"},
            {"overall": "negative", "reason_selected": ["Too much"]},
            {"overall": "negative", "reason_text": "Missing DeFi news"},
        ]

        summary = summarize_feedbacks(feedbacks)

        assert "1 positive" in summary
        assert "2 negative" in summary

    def test_categorize_filtered_content(self):
        """TC-5.2: Content categorization"""
        import asyncio
        from services.content_filter import categorize_filtered_content

        items = [
            {"title": "DeFi protocol update", "importance": "high"},
            {"title": "NFT collection launch", "importance": "medium"},
            {"title": "Layer2 scaling news", "importance": "high"},
            {"title": "Whale trading activity", "importance": "medium"},
        ]

        categories = asyncio.run(categorize_filtered_content(items))

        assert "top_stories" in categories
        assert len(categories["top_stories"]) >= 1


# ============ Module 6: Report Generation Tests ============

class TestReportGeneration:
    """TC-6.1-6.4: AI report generation"""

    def test_report_structure(self):
        """TC-6.1: Report structure completeness"""
        from services.report_generator import (
            format_top_stories,
            format_category_section,
            format_metrics_section,
        )

        # Test top stories format
        top_stories = [
            {"title": "Test Title", "summary": "Test summary", "source": "Test", "link": "http://test.com"}
        ]
        formatted = format_top_stories(top_stories)
        assert "TOP STORIES" in formatted
        assert "Test Title" in formatted

        # Test category section
        items = [{"title": "Item 1", "source": "Source1"}]
        cat_section = format_category_section("defi", items)
        assert "DeFi" in cat_section

        # Test metrics section
        metrics = format_metrics_section(50, 200, 15)
        assert "Sources" in metrics
        assert "Scanned" in metrics
        assert "Selected" in metrics

    def test_split_report_for_telegram(self):
        """Test report splitting for Telegram limit"""
        from services.report_generator import split_report_for_telegram

        # Short report - no split
        short = "Short report"
        parts = split_report_for_telegram(short)
        assert len(parts) == 1

        # Long report - should split
        long = "Section\n\n" * 500
        parts = split_report_for_telegram(long, max_length=100)
        assert len(parts) > 1

    def test_empty_report_generation(self):
        """Test empty report when no content"""
        from services.report_generator import generate_empty_report

        report = generate_empty_report()
        assert "No updates" in report
        assert "/settings" in report


# ============ Module 8: Feedback Collection Tests ============

class TestFeedbackCollection:
    """TC-8.1-8.4: User feedback collection"""

    def test_save_feedback(self, tmp_data_dir):
        """TC-8.4: Feedback data storage"""
        from utils.json_storage import create_user, save_feedback, get_user_feedbacks

        # Create user first
        create_user(telegram_id="feedback_test_user")

        # Save feedback
        result = save_feedback(
            telegram_id="feedback_test_user",
            overall_rating="negative",
            reason_selected=["Too much", "Not relevant"],
            reason_text="Need more DeFi content",
            item_feedbacks=[
                {"item_id": "item1", "feedback": "like"},
                {"item_id": "item2", "feedback": "dislike"},
            ]
        )
        assert result is True

        # Verify retrieval
        feedbacks = get_user_feedbacks("feedback_test_user", days=1)
        assert len(feedbacks) >= 1
        assert feedbacks[0]["overall"] == "negative"
        assert "Too much" in feedbacks[0]["reason_selected"]
        assert len(feedbacks[0]["item_feedbacks"]) == 2


# ============ Module 9: Feedback Learning Loop Tests ============

class TestFeedbackLearning:
    """TC-9.1-9.3: Feedback learning loop"""

    def test_format_feedbacks_for_ai(self):
        """TC-9.1: AI feedback analysis formatting"""
        from services.profile_updater import format_feedbacks_for_ai

        feedbacks = [
            {
                "date": "2024-01-01",
                "time": "10:00",
                "overall": "negative",
                "reason_selected": ["Too much"],
                "item_feedbacks": [
                    {"feedback": "like"},
                    {"feedback": "dislike"},
                ]
            }
        ]

        formatted = format_feedbacks_for_ai(feedbacks)
        assert "NEGATIVE" in formatted
        assert "Too much" in formatted
        assert "1 liked" in formatted
        assert "1 disliked" in formatted

    def test_analyze_feedback_trends(self, tmp_data_dir):
        """TC-9.1: Feedback trend analysis"""
        import asyncio
        from utils.json_storage import create_user, save_feedback
        from services.profile_updater import analyze_feedback_trends

        # Create user and add feedbacks
        create_user(telegram_id="trend_test_user")

        # Add multiple feedbacks
        for _ in range(3):
            save_feedback("trend_test_user", "positive")
        save_feedback("trend_test_user", "negative", reason_selected=["Too much"])

        trends = asyncio.run(analyze_feedback_trends("trend_test_user", days=1))

        assert trends["total_feedbacks"] == 4
        assert trends["positive_count"] == 3
        assert trends["negative_count"] == 1


# ============ Fixtures ============

@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Create temporary data directory for tests"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Create subdirectories
    (data_dir / "profiles").mkdir()
    (data_dir / "feedback").mkdir()
    (data_dir / "daily_stats").mkdir()
    (data_dir / "raw_content").mkdir()

    # Patch config
    monkeypatch.setattr("config.DATA_DIR", str(data_dir))
    monkeypatch.setattr("config.USERS_FILE", str(data_dir / "users.json"))
    monkeypatch.setattr("config.PROFILES_DIR", str(data_dir / "profiles"))
    monkeypatch.setattr("config.FEEDBACK_DIR", str(data_dir / "feedback"))
    monkeypatch.setattr("config.DAILY_STATS_DIR", str(data_dir / "daily_stats"))
    monkeypatch.setattr("config.RAW_CONTENT_DIR", str(data_dir / "raw_content"))

    # Also patch in json_storage module
    import utils.json_storage as storage
    monkeypatch.setattr(storage, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(storage, "USERS_FILE", str(data_dir / "users.json"))
    monkeypatch.setattr(storage, "PROFILES_DIR", str(data_dir / "profiles"))
    monkeypatch.setattr(storage, "FEEDBACK_DIR", str(data_dir / "feedback"))
    monkeypatch.setattr(storage, "DAILY_STATS_DIR", str(data_dir / "daily_stats"))
    monkeypatch.setattr(storage, "RAW_CONTENT_DIR", str(data_dir / "raw_content"))

    return data_dir


# ============ Run Tests ============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
