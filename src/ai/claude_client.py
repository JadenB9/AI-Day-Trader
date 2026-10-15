"""
Anthropic Claude API client wrapper.
"""
import asyncio
from typing import Optional, Dict, Any
import time
import structlog
from anthropic import AsyncAnthropic

from config.settings import get_settings
from src.core.exceptions import AIError, AITimeoutError, AIRateLimitError

logger = structlog.get_logger()
settings = get_settings()


class ClaudeClient:
    """
    Wrapper for Anthropic Claude API.
    Supports web search tool for real-time information.
    """

    def __init__(self):
        self._client = AsyncAnthropic(api_key=settings.anthropic.api_key)
        self._model = settings.anthropic.model
        self._max_tokens = settings.anthropic.max_tokens
        self._temperature = settings.anthropic.temperature

        # Rate limiting - conservative to avoid hitting limits
        # Tier 1 limit: 50 requests/minute = ~1.2 sec between requests
        self._last_request_time = 0
        self._min_request_interval = 2.0  # 2 seconds between requests (30 req/min max)
        self._requests_this_minute = 0
        self._minute_start = time.time()

        # Stats
        self._request_count = 0
        self._total_tokens = 0

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        use_web_search: bool = False,
        max_tokens: int = None,
        temperature: float = None
    ) -> Dict[str, Any]:
        """
        Send completion request to Claude.

        Args:
            system_prompt: System message
            user_prompt: User message
            use_web_search: Enable web search tool
            max_tokens: Override default max tokens
            temperature: Override default temperature

        Returns:
            Dict with 'content', 'tokens_used', 'response_time_ms'
        """
        # Rate limiting
        await self._rate_limit()

        start_time = time.time()

        try:
            # Build request
            messages = [{"role": "user", "content": user_prompt}]

            # Build request kwargs
            request_kwargs = {
                "model": self._model,
                "max_tokens": max_tokens or self._max_tokens,
                "temperature": temperature if temperature is not None else self._temperature,
                "system": system_prompt,
                "messages": messages,
            }

            # Add tools only if web search enabled
            if use_web_search:
                request_kwargs["tools"] = [{
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 3
                }]

            # Make request
            response = await self._client.messages.create(**request_kwargs)

            # Process response
            content = self._extract_content(response)
            tokens_used = response.usage.input_tokens + response.usage.output_tokens

            response_time = int((time.time() - start_time) * 1000)

            # Update stats
            self._request_count += 1
            self._total_tokens += tokens_used

            logger.debug(
                "claude_response",
                tokens=tokens_used,
                response_time_ms=response_time
            )

            # Log to activity feed
            try:
                from api.routers.system import log_activity
                log_activity(
                    "ai",
                    "AI Response",
                    f"Claude responded in {response_time}ms using {tokens_used} tokens",
                    {
                        "tokens": tokens_used,
                        "response_time_ms": response_time,
                        "web_search": use_web_search,
                        "model": self._model
                    }
                )
            except ImportError:
                pass  # API not running

            return {
                'content': content,
                'tokens_used': tokens_used,
                'response_time_ms': response_time,
                'model': self._model,
                'web_search_used': use_web_search
            }

        except Exception as e:
            error_msg = str(e)

            if "rate_limit" in error_msg.lower() or "429" in error_msg:
                # Auto-retry with wait for rate limits
                logger.warning("rate_limit_hit_retrying", error=error_msg[:100])

                # Wait 60 seconds and retry once
                logger.info("rate_limit_wait", seconds=65)
                await asyncio.sleep(65)

                try:
                    response = await self._client.messages.create(**request_kwargs)
                    content = self._extract_content(response)
                    tokens_used = response.usage.input_tokens + response.usage.output_tokens
                    response_time = int((time.time() - start_time) * 1000)

                    self._request_count += 1
                    self._total_tokens += tokens_used

                    return {
                        'content': content,
                        'tokens_used': tokens_used,
                        'response_time_ms': response_time,
                        'model': self._model,
                        'web_search_used': use_web_search,
                        'retried': True
                    }
                except Exception as retry_error:
                    raise AIRateLimitError(f"Rate limit hit after retry: {str(retry_error)}")

            elif "timeout" in error_msg.lower():
                raise AITimeoutError(f"Request timed out: {error_msg}")
            else:
                raise AIError(f"Claude API error: {error_msg}")

    def _extract_content(self, response) -> str:
        """Extract text content from response"""
        content_parts = []

        for block in response.content:
            if hasattr(block, 'text'):
                content_parts.append(block.text)
            elif hasattr(block, 'type') and block.type == 'tool_use':
                # Tool use block - might have web search results
                pass

        return "\n".join(content_parts)

    async def _rate_limit(self) -> None:
        """
        Implement rate limiting to stay under Tier 1 limits:
        - 50 requests/minute
        - 30K input tokens/minute

        We use conservative limits to avoid hitting the rate limit.
        """
        now = time.time()

        # Reset counter every minute
        if now - self._minute_start > 60:
            self._requests_this_minute = 0
            self._minute_start = now

        # If we've made 25+ requests this minute, wait until next minute
        if self._requests_this_minute >= 25:
            wait_time = 60 - (now - self._minute_start)
            if wait_time > 0:
                logger.info("rate_limit_waiting", wait_seconds=wait_time)
                await asyncio.sleep(wait_time)
                self._requests_this_minute = 0
                self._minute_start = time.time()

        # Enforce minimum interval between requests
        elapsed = now - self._last_request_time
        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)

        self._last_request_time = time.time()
        self._requests_this_minute += 1

    async def analyze_trade(
        self,
        context: str,
        use_web_search: bool = True
    ) -> Dict[str, Any]:
        """
        Analyze a potential trade with AI.

        Args:
            context: Full context string about the trade
            use_web_search: Search for recent news

        Returns:
            Analysis result
        """
        system_prompt = """You are an expert day trader analyzing potential trades.
You make quick, decisive recommendations based on technical analysis and market conditions.
Your response must be concise and actionable.

Response format:
DECISION: [APPROVE/REJECT/MODIFY]
CONFIDENCE: [0-100]%
REASONING: [2-3 sentences max]
MODIFICATIONS: [If MODIFY, specify changes to stop/target/size]
"""

        return await self.complete(
            system_prompt=system_prompt,
            user_prompt=context,
            use_web_search=use_web_search
        )

    @property
    def stats(self) -> Dict:
        """Get client statistics"""
        return {
            'requests': self._request_count,
            'total_tokens': self._total_tokens,
            'model': self._model
        }


# Singleton
_client: Optional[ClaudeClient] = None


def get_claude_client() -> ClaudeClient:
    """Get or create Claude client singleton"""
    global _client
    if _client is None:
        _client = ClaudeClient()
    return _client
