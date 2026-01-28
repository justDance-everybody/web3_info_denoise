"""
Prompt Loader Utility

Loads prompt templates from the prompts/ directory.
Supports variable substitution using Python string formatting.
"""
import os
import logging
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

# Get the prompts directory path
PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")


@lru_cache(maxsize=32)
def load_prompt(filename: str) -> str:
    """
    Load a prompt template from the prompts directory.

    Args:
        filename: Name of the prompt file (e.g., "filtering.txt")

    Returns:
        The prompt template as a string

    Raises:
        FileNotFoundError: If the prompt file doesn't exist
    """
    filepath = os.path.join(PROMPTS_DIR, filename)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            logger.debug(f"Loaded prompt from {filename}")
            return content
    except FileNotFoundError:
        logger.error(f"Prompt file not found: {filepath}")
        raise
    except Exception as e:
        logger.error(f"Error loading prompt {filename}: {e}")
        raise


def get_prompt(filename: str, **kwargs) -> str:
    """
    Load a prompt template and substitute variables.

    Args:
        filename: Name of the prompt file
        **kwargs: Variables to substitute in the template

    Returns:
        The formatted prompt string

    Example:
        prompt = get_prompt("filtering.txt",
                           user_profile="DeFi enthusiast",
                           feedback_summary="Positive trend")
    """
    template = load_prompt(filename)

    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing variable in prompt {filename}: {e}")
            # Return template with partial substitution
            for key, value in kwargs.items():
                template = template.replace("{" + key + "}", str(value))
            return template

    return template


def reload_prompts() -> None:
    """Clear the prompt cache to reload all prompts from disk."""
    load_prompt.cache_clear()
    logger.info("Prompt cache cleared")
