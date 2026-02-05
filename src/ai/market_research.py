"""
Periodic AI Market Research.
Runs hourly to gather market insights using Claude with web search.
"""
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import structlog

from config.settings import get_settings
from src.ai.claude_client import get_claude_client
from src.core.event_bus import get_event_bus, EventType, Event

logger = structlog.get_logger()
settings = get_settings()


@dataclass
class MarketResearch:
    """Result of market research"""
    symbol: str
    timestamp: datetime
    sentiment: str  # bullish, bearish, neutral
    confidence: int  # 0-100
    key_findings: List[str]
    news_summary: str
    risks: List[str]
    opportunities: List[str]
    recommendation: str
    raw_response: str = ""


@dataclass
class ResearchCache:
    """Cache for market research results"""
    data: Dict[str, MarketResearch] = field(default_factory=dict)
    last_full_scan: Optional[datetime] = None

    def get(self, symbol: str) -> Optional[MarketResearch]:
        return self.data.get(symbol)

    def set(self, symbol: str, research: MarketResearch):
        self.data[symbol] = research

    def is_stale(self, symbol: str, max_age_hours: int = 1) -> bool:
        r = self.data.get(symbol)
        if not r:
            return True
        return datetime.now() - r.timestamp > timedelta(hours=max_age_hours)


class MarketResearcher:
    """
    AI-powered market researcher.
    Runs periodically to gather insights on watched symbols.
    Uses Claude with web search for real-time information.
    """

    # DETAILED RESEARCH PROMPTS - Spread across the hour to avoid rate limits
    RESEARCH_PROMPT = """You are a financial analyst researching {symbol} for day trading.

Search the web for the latest news about {symbol}. Check:
1. Recent news headlines (last 24 hours)
2. Price action and technical levels
3. Any catalysts (earnings, FDA, partnerships)
4. Social sentiment if relevant

Provide your analysis in this EXACT format:

SENTIMENT: [bullish/bearish/neutral]
CONFIDENCE: [0-100]%

KEY FINDINGS:
- [most important news or development]
- [price action note]
- [catalyst or risk factor]

NEWS SUMMARY:
[2-3 sentence summary of recent developments]

RISKS:
- [primary risk]
- [secondary risk]

OPPORTUNITIES:
- [trading opportunity if any]

RECOMMENDATION:
[1-2 sentence trading recommendation with direction and reasoning]
"""

    CRYPTO_RESEARCH_PROMPT = """You are a crypto analyst researching {symbol} for intraday trading.

Search the web for:
1. {symbol} news today
2. Bitcoin correlation and overall crypto sentiment
3. Any whale activity or exchange news
4. Technical setup and key levels

Provide analysis in this EXACT format:

SENTIMENT: [bullish/bearish/neutral]
CONFIDENCE: [0-100]%

KEY FINDINGS:
- [most impactful news]
- [BTC correlation / market context]
- [technical or on-chain insight]

NEWS SUMMARY:
[2-3 sentence summary of crypto-specific developments]

RISKS:
- [primary risk]
- [secondary risk]

OPPORTUNITIES:
- [specific trade setup if any]

RECOMMENDATION:
[1-2 sentence recommendation with direction and key levels]
"""

    MARKET_OVERVIEW_PROMPT = """You are a market analyst. Search for current market conditions.

Provide a comprehensive overview:

1. INDICES: SPY, QQQ, current levels and % change today
2. VOLATILITY: VIX level and what it indicates
3. ECONOMIC EVENTS: Any Fed news, economic data, or earnings today
4. SECTORS: Which sectors are leading/lagging
5. CRYPTO: Bitcoin and Ethereum trend, any major crypto news
6. BREAKING NEWS: Any market-moving headlines
7. TOP OPPORTUNITIES: 3-5 specific tickers showing unusual activity or setups

Be specific with numbers and actionable insights.
"""

    def __init__(self):
        self._client = get_claude_client()
        self._cache = ResearchCache()
        self._event_bus = get_event_bus()
        self._research_count = 0
        self._last_market_overview: Optional[str] = None
        self._last_overview_time: Optional[datetime] = None

    async def research_symbol(self, symbol: str, force: bool = False) -> MarketResearch:
        """
        Research a specific symbol using AI + web search.

        Args:
            symbol: Stock/crypto symbol
            force: Force refresh even if cached

        Returns:
            MarketResearch result
        """
        # Check cache
        if not force and not self._cache.is_stale(symbol):
            cached = self._cache.get(symbol)
            if cached:
                logger.debug("research_cache_hit", symbol=symbol)
                return cached

        logger.info("researching_symbol", symbol=symbol)

        # Use crypto-specific prompt for crypto symbols
        is_crypto = '/' in symbol or symbol.endswith('USD') or symbol in [
            'BTC', 'ETH', 'SOL', 'LTC', 'AVAX', 'LINK', 'DOGE', 'SHIB',
            'UNI', 'AAVE', 'SUSHI', 'CRV', 'DOT', 'MATIC', 'ATOM', 'ALGO',
            'XLM', 'XTZ', 'BCH', 'BAT'
        ]

        if is_crypto:
            prompt = self.CRYPTO_RESEARCH_PROMPT.format(symbol=symbol)
            system = "You are an expert crypto trading analyst with deep knowledge of on-chain metrics and DeFi."
        else:
            prompt = self.RESEARCH_PROMPT.format(symbol=symbol)
            system = "You are an expert financial analyst specializing in aggressive day trading strategies."

        try:
            response = await self._client.complete(
                system_prompt=system,
                user_prompt=prompt,
                use_web_search=True,
                max_tokens=1200  # Balanced for good detail without hitting limits
            )

            research = self._parse_research_response(symbol, response['content'])
            self._cache.set(symbol, research)
            self._research_count += 1

            # Emit event
            await self._event_bus.publish(Event(
                type=EventType.AI_DECISION_RESPONSE,
                data={
                    'type': 'market_research',
                    'symbol': symbol,
                    'sentiment': research.sentiment,
                    'confidence': research.confidence,
                    'key_findings': research.key_findings
                },
                source="market_researcher"
            ))

            logger.info(
                "research_complete",
                symbol=symbol,
                sentiment=research.sentiment,
                confidence=research.confidence
            )

            # Log to activity feed
            try:
                from api.routers.system import log_activity
                log_activity(
                    "research",
                    f"Research: {symbol}",
                    f"Sentiment: {research.sentiment.upper()}, Confidence: {research.confidence}%",
                    {
                        "symbol": symbol,
                        "sentiment": research.sentiment,
                        "confidence": research.confidence,
                        "findings": research.key_findings[:2]
                    }
                )
            except ImportError:
                pass

            return research

        except Exception as e:
            logger.error("research_failed", symbol=symbol, error=str(e))
            # Return neutral result on error
            return MarketResearch(
                symbol=symbol,
                timestamp=datetime.now(),
                sentiment="neutral",
                confidence=0,
                key_findings=["Research failed"],
                news_summary=f"Error: {str(e)}",
                risks=["Unable to assess"],
                opportunities=[],
                recommendation="Skip - research unavailable"
            )

    async def get_market_overview(self, force: bool = False) -> str:
        """
        Get overall market overview.
        Cached for 30 minutes.
        """
        if not force and self._last_overview_time:
            if datetime.now() - self._last_overview_time < timedelta(minutes=30):
                return self._last_market_overview or ""

        logger.info("getting_market_overview")

        try:
            response = await self._client.complete(
                system_prompt="You are a market analyst providing actionable trading insights.",
                user_prompt=self.MARKET_OVERVIEW_PROMPT,
                use_web_search=True,
                max_tokens=1500  # Good detail for market overview
            )

            self._last_market_overview = response['content']
            self._last_overview_time = datetime.now()

            logger.info("market_overview_complete")
            return self._last_market_overview

        except Exception as e:
            logger.error("market_overview_failed", error=str(e))
            return f"Market overview unavailable: {str(e)}"

    async def research_watchlist(self, symbols: List[str]) -> Dict[str, MarketResearch]:
        """
        Research ALL symbols in watchlist, spread across the entire hour.

        Strategy:
        - 3600 seconds in an hour
        - Divide by number of symbols to get delay between each
        - This ensures continuous research without hitting rate limits
        - Each symbol gets fresh research every hour
        """
        total_symbols = len(symbols)

        # Calculate delay to spread research across ~55 minutes (leave buffer)
        # 55 min = 3300 seconds, spread across all symbols
        delay_between_symbols = max(3300 // total_symbols, 60)  # Minimum 60 seconds

        logger.info(
            "researching_watchlist_spread",
            count=total_symbols,
            delay_seconds=delay_between_symbols,
            estimated_duration_min=round((total_symbols * delay_between_symbols) / 60, 1)
        )

        results = {}

        for i, symbol in enumerate(symbols):
            try:
                result = await self.research_symbol(symbol)
                results[symbol] = result

                logger.info(
                    "research_progress",
                    symbol=symbol,
                    progress=f"{i+1}/{total_symbols}",
                    sentiment=result.sentiment,
                    confidence=result.confidence
                )

                # Log to activity feed
                try:
                    from api.routers.system import log_activity
                    log_activity(
                        "research",
                        f"Research: {symbol} ({i+1}/{total_symbols})",
                        f"{result.sentiment.upper()} - {result.confidence}% confidence. Next in {delay_between_symbols}s",
                        {
                            "symbol": symbol,
                            "sentiment": result.sentiment,
                            "confidence": result.confidence,
                            "progress": f"{i+1}/{total_symbols}"
                        }
                    )
                except ImportError:
                    pass

            except Exception as e:
                logger.error("research_symbol_error", symbol=symbol, error=str(e))
                # Log error to activity
                try:
                    from api.routers.system import log_activity
                    log_activity(
                        "error",
                        f"Research Failed: {symbol}",
                        f"Error: {str(e)[:100]}",
                        {"symbol": symbol, "error": str(e)}
                    )
                except ImportError:
                    pass

            # Wait between symbols to spread across the hour
            if i < total_symbols - 1:
                logger.debug(
                    "research_waiting",
                    seconds=delay_between_symbols,
                    next_symbol=symbols[i+1]
                )
                await asyncio.sleep(delay_between_symbols)

        self._cache.last_full_scan = datetime.now()
        logger.info("research_watchlist_complete", total_researched=len(results))
        return results

    def _parse_research_response(self, symbol: str, content: str) -> MarketResearch:
        """Parse AI research response into structured format"""
        import re

        sentiment = "neutral"
        confidence = 50
        key_findings = []
        news_summary = ""
        risks = []
        opportunities = []
        recommendation = ""

        content_lower = content.lower()

        # Extract sentiment
        sent_match = re.search(r'\*?\*?sentiment\*?\*?[:\s]+\*?\*?(\w+)', content_lower)
        if sent_match:
            val = sent_match.group(1)
            if 'bullish' in val:
                sentiment = 'bullish'
            elif 'bearish' in val:
                sentiment = 'bearish'

        # Extract confidence
        conf_match = re.search(r'\*?\*?confidence\*?\*?[:\s]+\*?\*?(\d+)', content_lower)
        if conf_match:
            confidence = int(conf_match.group(1))

        # Split into sections using regex
        sections = {
            'findings': r'(?:\*\*)?key\s*findings?(?:\*\*)?[:\s]*(.*?)(?=(?:\*\*)?(?:news|risks?|opportunities?|recommendation|$))',
            'news': r'(?:\*\*)?news\s*summary(?:\*\*)?[:\s]*(.*?)(?=(?:\*\*)?(?:risks?|opportunities?|recommendation|$))',
            'risks': r'(?:\*\*)?risks?(?:\*\*)?[:\s]*(.*?)(?=(?:\*\*)?(?:opportunities?|recommendation|$))',
            'opportunities': r'(?:\*\*)?opportunities?(?:\*\*)?[:\s]*(.*?)(?=(?:\*\*)?(?:recommendation|$))',
            'recommendation': r'(?:\*\*)?recommendation(?:\*\*)?[:\s]*(.*?)$'
        }

        def extract_bullets(text):
            """Extract bullet points from text, handling multi-line format"""
            items = []
            # Handle both "- text" and "-\ntext" patterns
            # Split on bullet markers but keep content
            parts = re.split(r'\n-\s*\n?|\n\*\s*\n?|\n•\s*\n?', '\n' + text)
            for p in parts[1:]:  # Skip first empty part
                # Clean up
                item = re.sub(r'\*\*|\*', '', p).strip()
                item = ' '.join(item.split())  # Normalize whitespace
                if item and len(item) > 5:
                    items.append(item)
            return items

        # Extract each section
        for section_name, pattern in sections.items():
            match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if match:
                section_text = match.group(1).strip()

                if section_name == 'findings':
                    key_findings = extract_bullets(section_text)
                elif section_name == 'risks':
                    risks = extract_bullets(section_text)
                elif section_name == 'opportunities':
                    opportunities = extract_bullets(section_text)
                elif section_name == 'news':
                    # Clean up news summary
                    news_summary = re.sub(r'\*\*|\*', '', section_text)
                    news_summary = ' '.join(news_summary.split())
                elif section_name == 'recommendation':
                    recommendation = re.sub(r'\*\*|\*', '', section_text)
                    recommendation = ' '.join(recommendation.split())

        # Fallback: if no findings, try to extract sentences with the symbol
        if not key_findings:
            sentences = re.split(r'[.!?]+', content)
            for s in sentences[:15]:
                s = re.sub(r'\*\*|\*', '', s).strip()
                if 20 < len(s) < 200 and symbol.upper() in s.upper():
                    key_findings.append(s[:150])
                    if len(key_findings) >= 3:
                        break

        # Fallback for news summary
        if not news_summary:
            paragraphs = content.split('\n\n')
            for p in paragraphs:
                p = re.sub(r'\*\*|\*|#', '', p).strip()
                if len(p) > 50:
                    news_summary = p[:300]
                    break

        logger.debug(
            "research_parsed",
            symbol=symbol,
            sentiment=sentiment,
            confidence=confidence,
            findings_count=len(key_findings),
            risks_count=len(risks),
            has_news=bool(news_summary),
            has_recommendation=bool(recommendation)
        )

        return MarketResearch(
            symbol=symbol,
            timestamp=datetime.now(),
            sentiment=sentiment,
            confidence=confidence,
            key_findings=key_findings[:5],
            news_summary=news_summary.strip()[:500],
            risks=risks[:3],
            opportunities=opportunities[:3],
            recommendation=recommendation.strip()[:300],
            raw_response=content
        )

    def get_cached_research(self, symbol: str) -> Optional[MarketResearch]:
        """Get cached research if available"""
        return self._cache.get(symbol)

    @property
    def stats(self) -> Dict[str, Any]:
        """Get researcher statistics"""
        return {
            "total_researched": self._research_count,
            "cached_symbols": len(self._cache.data),
            "last_full_scan": self._cache.last_full_scan.isoformat() if self._cache.last_full_scan else None,
            "last_overview": self._last_overview_time.isoformat() if self._last_overview_time else None
        }


# Singleton
_researcher: Optional[MarketResearcher] = None


def get_researcher() -> MarketResearcher:
    """Get or create researcher singleton"""
    global _researcher
    if _researcher is None:
        _researcher = MarketResearcher()
    return _researcher


async def run_hourly_research(symbols: List[str]) -> Dict[str, Any]:
    """
    Run hourly market research job.
    Called by the trading engine or scheduler.
    """
    researcher = get_researcher()

    # Get market overview first
    overview = await researcher.get_market_overview()

    # Research all symbols
    research_results = await researcher.research_watchlist(symbols)

    # Build summary
    bullish = sum(1 for r in research_results.values() if r.sentiment == "bullish")
    bearish = sum(1 for r in research_results.values() if r.sentiment == "bearish")
    neutral = len(research_results) - bullish - bearish

    return {
        "timestamp": datetime.now().isoformat(),
        "symbols_researched": len(research_results),
        "sentiment_summary": {
            "bullish": bullish,
            "bearish": bearish,
            "neutral": neutral
        },
        "market_overview": overview[:500],  # Truncate for summary
        "high_confidence": [
            {"symbol": s, "sentiment": r.sentiment, "confidence": r.confidence}
            for s, r in research_results.items()
            if r.confidence >= 70
        ]
    }
