# Changelog

All notable changes to this project will be documented in this file.

## [v1.3.0] - 2026-01-22

### Summary
Major improvements to AI reliability, language consistency, and user experience.

---

### Added

#### AI Reliability (Task 1)
- **Automatic retry mechanism** for AI filtering with up to 4 attempts
- **Model switching**: Primary model failure automatically switches to fallback model
- Retry strategy: Primary(temp=1.0) → Primary(temp=0.8) → Fallback(temp=1.0) → Fallback(temp=0.8)
- New `_call_ai_with_retry()` function in `content_filter.py`
- New `get_fallback_provider()` method in `llm_factory.py`

#### Twitter Author Extraction (Task 3)
- **Extract real Twitter handle** from tweet links (e.g., `@VitalikButerin`)
- New `extract_twitter_author()` function in `rss_fetcher.py`
- Added `author` field to content items for Twitter sources
- Source display now shows actual author instead of "Twitter Bundle 1"

#### Localization (Task 2)
- New locale strings: `reason_prefix`, `source_prefix`, `btn_like`, `btn_not_interested`
- New `LANG_CODE_TO_NAME` mapping for translation API
- New `get_translation_language()` helper function

---

### Changed

#### Language Processing (Task 2) - **Breaking Change**
- **All AI processing now uses English** (prompts, outputs, intermediate data)
- Translation happens **only at final output stage**
- Improved `get_user_target_language()` function with better detection
- Default language changed to Chinese (was English for empty profiles)
- `translate_content()` now handles all cases including mixed-language content
- Updated `filtering.txt` prompt to enforce English reason output
- Updated `translate.txt` to preserve `author` field

#### Report Format (Task 4)
- **New item format** with recommendation reason display:
  ```
  🔴 1. Title (clickable)
  Summary text...
  💡 Recommendation reason
  Source: @author
  ```
- Section-based priority indicators: 🔴 (must_read), 🟠 (macro_insights), 🔵 (others)
- `format_single_item()` now displays `reason` and `author` fields

#### Feedback Buttons (Task 5)
- **Changed dislike button** from "👎" to "不感兴趣" / "Not interested"
- `create_item_feedback_keyboard()` now accepts `lang` parameter
- Feedback buttons are now localized based on user language

#### UI Consistency
- All UI elements (buttons, prompts, headers) now respect user language setting
- `helpful_prompt` now uses locale strings instead of hardcoded check

---

### Fixed

- Fixed language mixing issue where users received mixed Chinese/English content
- Fixed AI filtering instability causing "Fallback selection" on some days
- Fixed inconsistent `reason` language (sometimes Chinese, sometimes English)

---

### Technical Details

#### Files Modified

| File | Changes |
|------|---------|
| `bot/services/content_filter.py` | Added retry logic, improved language functions |
| `bot/services/llm_factory.py` | Added fallback provider support |
| `bot/services/rss_fetcher.py` | Added Twitter author extraction |
| `bot/services/report_generator.py` | Added locale strings, updated format |
| `bot/services/digest_processor.py` | Updated translation flow |
| `bot/handlers/feedback.py` | Localized feedback buttons |
| `bot/prompts/filtering.txt` | Enforced English reason output |
| `bot/prompts/translate.txt` | Updated translation rules |

#### Configuration

No new environment variables required. Existing `OPENAI_API_KEY` enables fallback model.

---

### Migration Notes

1. **No breaking changes for users** - All changes are backward compatible
2. **Fallback model**: If you have both `GEMINI_API_KEY` and `OPENAI_API_KEY` configured, the system will automatically use the other as fallback
3. **Language**: Users with empty profiles will now default to Chinese (previously defaulted to English)

---

## [v1.2.x] - Previous versions

(See git history for previous changes)
