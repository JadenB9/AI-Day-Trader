"""
Indicator caching for HFT mode.
Avoids recalculating indicators on every sub-second cycle.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import structlog

from config.settings import get_settings

logger = structlog.get_logger()
settings = get_settings()


@dataclass
class CachedIndicators:
    """Cached indicator values with timestamp"""
    symbol: str
    indicators: Dict[str, float]
    timestamp: datetime
    bars_hash: str  # Hash of bar data used to compute

    def is_stale(self, ttl_ms: int) -> bool:
        """Check if cache entry is expired"""
        age_ms = (datetime.now() - self.timestamp).total_seconds() * 1000
        return age_ms > ttl_ms


class IndicatorCache:
    """
    TTL-based cache for indicator calculations.
    Used in HFT mode to avoid recalculating on every cycle.
    """

    def __init__(self, ttl_ms: int = None):
        self._ttl_ms = ttl_ms or settings.hft.indicator_cache_ttl_ms
        self._cache: Dict[str, CachedIndicators] = {}
        self._hits = 0
        self._misses = 0

    def get(self, symbol: str, bars_hash: str = None) -> Optional[Dict[str, float]]:
        """
        Get cached indicators for symbol.

        Args:
            symbol: Stock/crypto symbol
            bars_hash: Hash of current bar data (invalidate if different)

        Returns:
            Indicator dict if valid cache exists, None otherwise
        """
        entry = self._cache.get(symbol)

        if entry is None:
            self._misses += 1
            return None

        # Check if stale
        if entry.is_stale(self._ttl_ms):
            self._misses += 1
            del self._cache[symbol]
            return None

        # Check if bar data changed (optional invalidation)
        if bars_hash and entry.bars_hash != bars_hash:
            self._misses += 1
            return None

        self._hits += 1
        return entry.indicators

    def set(self, symbol: str, indicators: Dict[str, float], bars_hash: str = "") -> None:
        """Store indicators in cache"""
        self._cache[symbol] = CachedIndicators(
            symbol=symbol,
            indicators=indicators,
            timestamp=datetime.now(),
            bars_hash=bars_hash
        )

    def invalidate(self, symbol: str) -> None:
        """Remove symbol from cache"""
        self._cache.pop(symbol, None)

    def clear(self) -> None:
        """Clear entire cache"""
        self._cache.clear()
        logger.debug("indicator_cache_cleared")

    def cleanup_stale(self) -> int:
        """Remove all stale entries, return count removed"""
        stale = [s for s, e in self._cache.items() if e.is_stale(self._ttl_ms)]
        for symbol in stale:
            del self._cache[symbol]
        return len(stale)

    @property
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 1),
            "ttl_ms": self._ttl_ms
        }


# Singleton
_cache: Optional[IndicatorCache] = None


def get_indicator_cache() -> IndicatorCache:
    """Get or create indicator cache singleton"""
    global _cache
    if _cache is None:
        _cache = IndicatorCache()
    return _cache


def hash_bars(bars: list) -> str:
    """Create hash of bar data for cache invalidation"""
    if not bars:
        return ""
    # Use last bar's timestamp + close as simple hash
    last = bars[-1]
    return f"{last.timestamp.isoformat()}:{last.close}"
