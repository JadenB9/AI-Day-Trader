"""
Anthropic Claude API client wrapper.
"""
import asyncio
from typing import Optional, Dict, List, Any
import time
import structlog
from anthropic import Anthropic, AsyncAnthropic

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

        # Rate limiting
        self._last_request_time = 0
        self._min_request_interval = 0.5  # 500ms between requests

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

            # Tools
            tools = []
            if use_web_search:
                tools.append({
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 3
                })

            # Make request
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens or self._max_tokens,
                temperature=temperature if temperature is not None else self._temperature,
                system=system_prompt,
                messages=messages,
                tools=tools if tools else None
            )

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

            return {
                'content': content,
                'tokens_used': tokens_used,
                'response_time_ms': response_time,
                'model': self._model,
                'web_search_used': use_web_search
            }

        except Exception as e:
            error_msg = str(e)

            if "rate_limit" in error_msg.lower():
                raise AIRateLimitError(f"Rate limit hit: {error_msg}")
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
        """Implement simple rate limiting"""
        now = time.time()
        elapsed = now - self._last_request_time

        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)

        self._last_request_time = time.time()

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
