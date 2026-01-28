"""
LLM Factory - Provider factory for creating LLM instances

Provides a centralized factory for creating LLM provider instances
based on configuration. Supports primary and fallback providers for
improved reliability.

Includes unified retry mechanism for all LLM calls.
"""

import logging
import asyncio
from typing import Optional, Tuple, Any, Callable

from .llm_provider import LLMProvider
from .gemini_provider import GeminiProvider
from .openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

# Retry configuration
RETRY_DELAY_SECONDS = 2  # Delay between retries
MAX_ATTEMPTS = 4  # Total attempts: primary(2) + fallback(2)

# Global singleton instances
_llm_provider: Optional[LLMProvider] = None
_fallback_provider: Optional[LLMProvider] = None


class LLMFactory:
    """Factory class for creating LLM provider instances."""

    @staticmethod
    def create_provider(provider_name: str) -> LLMProvider:
        """
        Create an LLM provider based on the provider name.

        Args:
            provider_name: Provider name ('gemini' or 'openai')

        Returns:
            LLMProvider instance

        Raises:
            ValueError: If provider name is unknown
        """
        provider_name = provider_name.lower().strip()

        if provider_name == "gemini":
            from config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_API_URL
            logger.info("Creating Gemini provider")
            return GeminiProvider(
                api_key=GEMINI_API_KEY,
                model=GEMINI_MODEL,
                api_url=GEMINI_API_URL or None
            )

        elif provider_name == "openai":
            from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_API_URL
            logger.info("Creating OpenAI provider")
            return OpenAIProvider(
                api_key=OPENAI_API_KEY,
                model=OPENAI_MODEL,
                api_url=OPENAI_API_URL or None
            )

        else:
            raise ValueError(
                f"Unknown LLM provider: {provider_name}. "
                f"Supported providers: 'gemini', 'openai'"
            )

    @staticmethod
    def get_provider() -> LLMProvider:
        """
        Get the global LLM provider instance (singleton).

        Returns:
            LLMProvider instance based on LLM_PROVIDER environment variable
        """
        global _llm_provider

        if _llm_provider is None:
            from config import LLM_PROVIDER
            logger.info(f"Initializing LLM provider: {LLM_PROVIDER}")
            _llm_provider = LLMFactory.create_provider(LLM_PROVIDER)

        return _llm_provider

    @staticmethod
    def get_fallback_provider() -> Optional[LLMProvider]:
        """
        Get the fallback LLM provider instance (singleton).
        
        If primary is Gemini, fallback is OpenAI (if configured).
        If primary is OpenAI, fallback is Gemini (if configured).

        Returns:
            LLMProvider instance or None if fallback not available
        """
        global _fallback_provider

        if _fallback_provider is None:
            from config import LLM_PROVIDER, OPENAI_API_KEY, GEMINI_API_KEY
            
            primary = LLM_PROVIDER.lower().strip()
            
            # Determine fallback provider
            if primary == "gemini" and OPENAI_API_KEY:
                logger.info("Initializing fallback provider: openai")
                try:
                    _fallback_provider = LLMFactory.create_provider("openai")
                except Exception as e:
                    logger.warning(f"Failed to create fallback OpenAI provider: {e}")
                    return None
            elif primary == "openai" and GEMINI_API_KEY:
                logger.info("Initializing fallback provider: gemini")
                try:
                    _fallback_provider = LLMFactory.create_provider("gemini")
                except Exception as e:
                    logger.warning(f"Failed to create fallback Gemini provider: {e}")
                    return None
            else:
                logger.info("No fallback provider available (API key not configured)")
                return None

        return _fallback_provider

    @staticmethod
    def get_provider_name() -> str:
        """Get the name of the primary provider."""
        from config import LLM_PROVIDER
        return LLM_PROVIDER.lower().strip()

    @staticmethod
    def get_fallback_provider_name() -> Optional[str]:
        """Get the name of the fallback provider, if available."""
        from config import LLM_PROVIDER, OPENAI_API_KEY, GEMINI_API_KEY
        
        primary = LLM_PROVIDER.lower().strip()
        
        if primary == "gemini" and OPENAI_API_KEY:
            return "openai"
        elif primary == "openai" and GEMINI_API_KEY:
            return "gemini"
        return None

    @staticmethod
    def reset():
        """Reset the global provider instances (for testing)."""
        global _llm_provider, _fallback_provider
        _llm_provider = None
        _fallback_provider = None


# Convenience functions for backward compatibility
def get_llm() -> LLMProvider:
    """
    Get the global LLM provider instance.

    Returns:
        LLMProvider instance
    """
    return LLMFactory.get_provider()


def get_fallback_llm() -> Optional[LLMProvider]:
    """
    Get the fallback LLM provider instance.

    Returns:
        LLMProvider instance or None if not available
    """
    return LLMFactory.get_fallback_provider()


# =============================================================================
# Unified LLM Call with Retry and Model Switching
# =============================================================================

async def call_llm_with_retry(
    prompt: str,
    system_instruction: str = "",
    response_type: str = "json",
    temperature: float = 1.0,
    context: str = "unknown"
) -> Tuple[Any, str]:
    """
    Call LLM with automatic retry and model switching.
    
    This is the unified error handling mechanism for all LLM calls.
    
    Retry strategy:
    1. Primary model with given temperature
    2. Primary model with lower temperature (retry)
    3. Fallback model with given temperature
    4. Fallback model with lower temperature (retry)
    
    Args:
        prompt: User prompt
        system_instruction: System instruction (optional)
        response_type: "json" for JSON response, "text" for plain text
        temperature: Initial temperature (will be lowered on retry)
        context: Context string for logging (e.g., "filtering", "translation")
    
    Returns:
        Tuple of (result, model_description)
        result is None if all attempts failed
        For JSON: returns dict/list or None
        For text: returns string or None
    """
    primary_name = LLMFactory.get_provider_name()
    fallback_name = LLMFactory.get_fallback_provider_name()
    
    # Build attempt list: (provider_getter, temperature, description)
    retry_temp = max(0.3, temperature - 0.2)  # Lower temp for retry
    
    attempts = [
        (LLMFactory.get_provider, temperature, f"primary ({primary_name})"),
        (LLMFactory.get_provider, retry_temp, f"primary ({primary_name}) retry"),
    ]
    
    # Add fallback attempts if available
    if fallback_name:
        attempts.extend([
            (LLMFactory.get_fallback_provider, temperature, f"fallback ({fallback_name})"),
            (LLMFactory.get_fallback_provider, retry_temp, f"fallback ({fallback_name}) retry"),
        ])
    
    last_error = None
    
    for i, (get_provider, temp, description) in enumerate(attempts):
        try:
            provider = get_provider()
            if provider is None:
                logger.warning(f"[{context}] Attempt {i+1}/{len(attempts)}: Provider not available for {description}")
                continue
            
            logger.info(f"[{context}] Attempt {i+1}/{len(attempts)}: Calling {description} (temp={temp})")
            
            # Call appropriate method based on response type
            if response_type == "json":
                result = await provider.generate_json(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    temperature=temp
                )
            else:
                result = await provider.generate_text(
                    prompt=prompt,
                    system_instruction=system_instruction if system_instruction else None,
                    temperature=temp
                )
            
            # Check for error in response
            if response_type == "json":
                if isinstance(result, dict) and "error" in result:
                    error_msg = result.get("error", "Unknown error")
                    logger.warning(f"[{context}] Attempt {i+1}: {description} returned error: {error_msg}")
                    last_error = error_msg
                    if i < len(attempts) - 1:
                        await asyncio.sleep(RETRY_DELAY_SECONDS)
                    continue
            else:
                # For text response, extract content from LLMResponse
                if hasattr(result, 'content'):
                    result = result.content
                if not result or (isinstance(result, str) and result.startswith("Error")):
                    logger.warning(f"[{context}] Attempt {i+1}: {description} returned invalid: {str(result)[:100]}")
                    last_error = str(result)[:100] if result else "empty response"
                    if i < len(attempts) - 1:
                        await asyncio.sleep(RETRY_DELAY_SECONDS)
                    continue
            
            # Success!
            logger.info(f"[{context}] LLM call succeeded on attempt {i+1} using {description}")
            return result, description
            
        except Exception as e:
            last_error = str(e)
            logger.warning(f"[{context}] Attempt {i+1}: {description} failed with exception: {e}")
            
            # Wait before retry
            if i < len(attempts) - 1:
                await asyncio.sleep(RETRY_DELAY_SECONDS)
    
    # All attempts failed
    logger.error(f"[{context}] All {len(attempts)} LLM attempts failed. Last error: {last_error}")
    return None, "all_failed"


async def call_llm_json(
    prompt: str,
    system_instruction: str = "",
    temperature: float = 1.0,
    context: str = "unknown"
) -> Tuple[Any, str]:
    """
    Call LLM expecting JSON response with retry and model switching.
    
    Convenience wrapper for call_llm_with_retry with response_type="json".
    """
    return await call_llm_with_retry(
        prompt=prompt,
        system_instruction=system_instruction,
        response_type="json",
        temperature=temperature,
        context=context
    )


async def call_llm_text(
    prompt: str,
    system_instruction: str = "",
    temperature: float = 0.7,
    context: str = "unknown"
) -> Tuple[Optional[str], str]:
    """
    Call LLM expecting text response with retry and model switching.
    
    Convenience wrapper for call_llm_with_retry with response_type="text".
    """
    return await call_llm_with_retry(
        prompt=prompt,
        system_instruction=system_instruction,
        response_type="text",
        temperature=temperature,
        context=context
    )
