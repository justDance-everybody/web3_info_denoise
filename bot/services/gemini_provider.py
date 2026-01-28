"""
Gemini Provider - LLM Provider implementation for Google Gemini 3 Pro

This class implements the LLMProvider interface for Gemini API.
"""

import asyncio
import httpx
import json
import logging
from typing import Dict, Any, Optional

from .llm_provider import LLMProvider, LLMResponse, LLMAuthError, LLMRateLimitError, LLMTimeoutError
from config import GEMINI_API_KEY, GEMINI_API_URL, GEMINI_MODEL, GEMINI_THINKING_LEVEL

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


class GeminiProvider(LLMProvider):
    """Google Gemini 3 Pro Provider with thinking support."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, api_url: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY
        self.model = model or GEMINI_MODEL
        self.thinking_level = GEMINI_THINKING_LEVEL

        # Auto-construct API URL if not provided
        if api_url:
            self.api_url = api_url
        else:
            base_url = GEMINI_API_URL or "https://generativelanguage.googleapis.com/v1beta/models"
            self.api_url = f"{base_url}/{self.model}:generateContent"

        if not self.api_key:
            raise LLMAuthError("GEMINI_API_KEY not set")

        logger.info(f"Gemini Provider initialized: model={self.model}, thinking={self.thinking_level}")

    async def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: int = 8192
    ) -> LLMResponse:
        """Generate text response with Gemini."""
        headers = {"Content-Type": "application/json"}

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "thinkingConfig": {"thinkingLevel": self.thinking_level}
            }
        }

        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.api_url}?key={self.api_key}",
                        json=payload,
                        headers=headers,
                        timeout=120.0
                    )
                    response.raise_for_status()
                    result = response.json()

                    # Extract response and thoughts
                    candidate = result["candidates"][0]["content"]
                    response_text = ""
                    thoughts_text = ""

                    for part in candidate.get("parts", []):
                        if part.get("thought"):
                            thoughts_text += part.get("text", "")
                        else:
                            response_text += part.get("text", "")

                    # Extract token usage (Gemini 3 includes thinking tokens)
                    usage_metadata = result.get("usageMetadata", {})
                    usage = {
                        "prompt_tokens": usage_metadata.get("promptTokenCount", 0),
                        "completion_tokens": usage_metadata.get("candidatesTokenCount", 0),
                        "thoughts_tokens": usage_metadata.get("thoughtsTokenCount", 0),
                        "total_tokens": usage_metadata.get("totalTokenCount", 0)
                    }

                    # Log token usage
                    if usage['thoughts_tokens'] > 0:
                        logger.info(f"Gemini API usage - prompt: {usage['prompt_tokens']}, "
                                   f"completion: {usage['completion_tokens']}, "
                                   f"thinking: {usage['thoughts_tokens']}, "
                                   f"total: {usage['total_tokens']} tokens")
                    else:
                        logger.info(f"Gemini API usage - prompt: {usage['prompt_tokens']}, "
                                   f"completion: {usage['completion_tokens']}, "
                                   f"total: {usage['total_tokens']} tokens")

                    return LLMResponse(
                        content=response_text,
                        thinking=thoughts_text if thoughts_text else None,
                        usage=usage
                    )

            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Gemini network error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Gemini network error after {MAX_RETRIES} attempts: {e}")
                    raise LLMTimeoutError(f"Gemini API timeout: {e}")

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                response_text = e.response.text

                if status_code in [400, 401] and ("API key" in response_text or "authentication" in response_text.lower()):
                    raise LLMAuthError(f"Invalid Gemini API key: {response_text}")
                elif status_code == 429:
                    raise LLMRateLimitError(f"Gemini rate limit exceeded: {response_text}")
                else:
                    logger.error(f"Gemini HTTP error: {status_code} - {response_text}")
                    raise

            except httpx.TimeoutException as e:
                raise LLMTimeoutError(f"Gemini request timeout: {e}")

            except Exception as e:
                logger.error(f"Unexpected Gemini error: {e}")
                raise

        # Should not reach here, but just in case
        if last_error:
            raise last_error

    async def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.5
    ) -> Dict[str, Any]:
        """Generate structured JSON response with Gemini."""
        headers = {"Content-Type": "application/json"}

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json",  # JSON mode
                "thinkingConfig": {"thinkingLevel": self.thinking_level}
            }
        }

        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.api_url}?key={self.api_key}",
                        json=payload,
                        headers=headers,
                        timeout=120.0
                    )
                    response.raise_for_status()
                    result = response.json()

                    # Extract token usage
                    usage_metadata = result.get("usageMetadata", {})
                    usage = {
                        "prompt_tokens": usage_metadata.get("promptTokenCount", 0),
                        "completion_tokens": usage_metadata.get("candidatesTokenCount", 0),
                        "total_tokens": usage_metadata.get("totalTokenCount", 0)
                    }

                    # Log token usage for JSON generation
                    logger.info(f"Gemini JSON API usage - prompt: {usage['prompt_tokens']}, "
                               f"completion: {usage['completion_tokens']}, "
                               f"total: {usage['total_tokens']} tokens")

                    # Extract JSON content
                    candidate = result["candidates"][0]["content"]
                    response_text = ""

                    for part in candidate.get("parts", []):
                        if not part.get("thought"):  # Skip thinking parts
                            response_text += part.get("text", "")

                    # Parse JSON
                    try:
                        return json.loads(response_text)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Initial JSON parse failed: {e}")
                        # Fallback 1: extract JSON from markdown code blocks
                        try:
                            if "```json" in response_text:
                                json_str = response_text.split("```json")[1].split("```")[0].strip()
                                return json.loads(json_str)
                            elif "```" in response_text:
                                json_str = response_text.split("```")[1].split("```")[0].strip()
                                return json.loads(json_str)
                        except (json.JSONDecodeError, IndexError) as e2:
                            logger.error(f"Markdown extraction failed: {e2}")

                        # Fallback 2: Return empty structure to prevent crash
                        logger.error(f"All JSON parsing failed. Response: {response_text[:300]}")
                        return {"error": "JSON parse failed", "raw_response": response_text[:500]}

            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Gemini JSON network error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Gemini JSON network error after {MAX_RETRIES} attempts: {e}")
                    raise LLMTimeoutError(f"Gemini JSON API timeout: {e}")

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                response_text = e.response.text

                if status_code in [400, 401]:
                    raise LLMAuthError(f"Invalid Gemini API key: {response_text}")
                elif status_code == 429:
                    raise LLMRateLimitError(f"Gemini rate limit exceeded: {response_text}")
                else:
                    logger.error(f"Gemini JSON HTTP error: {status_code} - {response_text}")
                    raise

            except Exception as e:
                logger.error(f"Unexpected Gemini JSON error: {e}")
                raise

        if last_error:
            raise last_error

    async def generate_with_search(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7
    ) -> LLMResponse:
        """Generate response with Google Search grounding."""
        headers = {"Content-Type": "application/json"}

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 8192,
                "thinkingConfig": {"thinkingLevel": self.thinking_level}
            },
            "tools": [{"google_search": {}}]  # Enable Google Search
        }

        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.api_url}?key={self.api_key}",
                        json=payload,
                        headers=headers,
                        timeout=120.0
                    )
                    response.raise_for_status()
                    result = response.json()

                    # Extract response
                    candidate = result["candidates"][0]["content"]
                    response_text = ""
                    thoughts_text = ""

                    for part in candidate.get("parts", []):
                        if part.get("thought"):
                            thoughts_text += part.get("text", "")
                        else:
                            response_text += part.get("text", "")

                    # Extract token usage (Gemini 3 includes thinking tokens)
                    usage_metadata = result.get("usageMetadata", {})
                    usage = {
                        "prompt_tokens": usage_metadata.get("promptTokenCount", 0),
                        "completion_tokens": usage_metadata.get("candidatesTokenCount", 0),
                        "thoughts_tokens": usage_metadata.get("thoughtsTokenCount", 0),
                        "total_tokens": usage_metadata.get("totalTokenCount", 0)
                    }

                    # Log token usage
                    if usage['thoughts_tokens'] > 0:
                        logger.info(f"Gemini API usage - prompt: {usage['prompt_tokens']}, "
                                   f"completion: {usage['completion_tokens']}, "
                                   f"thinking: {usage['thoughts_tokens']}, "
                                   f"total: {usage['total_tokens']} tokens")
                    else:
                        logger.info(f"Gemini API usage - prompt: {usage['prompt_tokens']}, "
                                   f"completion: {usage['completion_tokens']}, "
                                   f"total: {usage['total_tokens']} tokens")

                    return LLMResponse(
                        content=response_text,
                        thinking=thoughts_text if thoughts_text else None,
                        usage=usage
                    )

            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Gemini search error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Gemini search error after {MAX_RETRIES} attempts: {e}")
                    raise LLMTimeoutError(f"Gemini search timeout: {e}")

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                response_text = e.response.text

                if status_code in [400, 401]:
                    raise LLMAuthError(f"Invalid Gemini API key: {response_text}")
                elif status_code == 429:
                    raise LLMRateLimitError(f"Gemini rate limit exceeded: {response_text}")
                else:
                    logger.error(f"Gemini search HTTP error: {status_code} - {response_text}")
                    raise

            except Exception as e:
                logger.error(f"Unexpected Gemini search error: {e}")
                raise

        if last_error:
            raise last_error
