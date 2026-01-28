"""
LLM Provider Abstract Interface

Provides a unified interface for different LLM providers (Gemini, OpenAI, etc.)
to enable seamless switching between providers.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Unified response format from LLM providers."""
    content: str
    thinking: Optional[str] = None
    usage: Optional[Dict[str, int]] = None  # {prompt_tokens, completion_tokens, total_tokens}


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: int = 8192
    ) -> LLMResponse:
        """
        Generate text response.

        Args:
            prompt: User prompt
            system_instruction: System instruction/context
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum output tokens

        Returns:
            LLMResponse with content, thinking, and usage stats
        """
        pass

    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.5
    ) -> Dict[str, Any]:
        """
        Generate structured JSON response.

        Args:
            prompt: User prompt
            system_instruction: System instruction/context
            temperature: Sampling temperature

        Returns:
            Parsed JSON dict
        """
        pass

    async def generate_with_search(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7
    ) -> LLMResponse:
        """
        Generate response with web search (only supported by Gemini).

        Args:
            prompt: User prompt
            system_instruction: System instruction/context
            temperature: Sampling temperature

        Returns:
            LLMResponse

        Raises:
            NotImplementedError: If provider doesn't support search
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support web search")


# ============ Exception Classes ============

class LLMError(Exception):
    """Base class for LLM errors."""
    pass


class LLMAuthError(LLMError):
    """Authentication error (invalid API key)."""
    pass


class LLMRateLimitError(LLMError):
    """Rate limit exceeded."""
    pass


class LLMTimeoutError(LLMError):
    """Request timeout."""
    pass
