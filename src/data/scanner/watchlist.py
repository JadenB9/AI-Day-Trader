"""
Dynamic watchlist manager.
Combines scanner results with default symbols.
"""
from typing import List, Set, Dict, Optional
from datetime import datetime
import structlog

from config.settings import get_settings
from src.data.scanner.premarket import PremarketScanner
from src.data.scanner.criteria import ScanResult
from src.core.event_bus import get_event_bus, EventType, Event
from src.utils.helpers import is_premarket

logger = structlog.get_logger()
settings = get_settings()


class WatchlistManager:
    """
    Manages the dynamic watchlist for the trading session.
    Combines scanner results with static defaults.
    """

    def __init__(self):
        self._scanner = PremarketScanner()
        self._event_bus = get_event_bus()

        # Current watchlist
        self._symbols: Set[str] = set()
        self._scan_results: Dict[str, ScanResult] = {}

        # Priority tiers
        self._tier1: Set[str] = set()  # Top scanner picks
        self._tier2: Set[str] = set()  # Secondary picks
        self._tier3: Set[str] = set()  # Defaults

        # Tracking
        self._last_update: Optional[datetime] = None
        self._scan_count = 0

    async def initialize(self, run_scan: bool = True) -> None:
        """
        Initialize watchlist.
        Optionally runs pre-market scan if in pre-market hours.
        """
        if run_scan and is_premarket():
            await self.run_scan()
        else:
            # Use defaults
            self._load_defaults()

        logger.info(
            "watchlist_initialized",
            total_symbols=len(self._symbols),
            tier1=len(self._tier1),
            tier2=len(self._tier2),
            tier3=len(self._tier3)
        )

    def _load_defaults(self) -> None:
        """Load default symbols from settings, including crypto if enabled"""
        defaults = set(settings.default_symbols)

        # Always include all crypto symbols for comprehensive coverage
        # Crypto trades 24/7, so we want them in our watchlist
        crypto_symbols = settings.crypto.symbols if hasattr(settings, 'crypto') else []
        if crypto_symbols:
            # Convert BTC/USD format to match our internal format
            for crypto in crypto_symbols:
                defaults.add(crypto)
            logger.info("crypto_symbols_added_to_watchlist", count=len(crypto_symbols))

        self._tier3 = defaults
        self._symbols = defaults
        self._last_update = datetime.now()

    async def run_scan(self) -> List[ScanResult]:
        """Run pre-market scan and update watchlist"""
        logger.info("running_premarket_scan")

        results = await self._scanner.run_full_scan()
        self._scan_count += 1

        # Classify results into tiers
        self._tier1.clear()
        self._tier2.clear()
        self._scan_results.clear()

        for i, result in enumerate(results):
            self._scan_results[result.symbol] = result

            if i < 10:  # Top 10
                self._tier1.add(result.symbol)
            else:
                self._tier2.add(result.symbol)

        # Add defaults to tier3
        self._tier3 = set(settings.default_symbols) - self._tier1 - self._tier2

        # Combine all tiers
        self._symbols = self._tier1 | self._tier2 | self._tier3
        self._last_update = datetime.now()

        # Publish update
        await self._event_bus.publish(Event(
            type=EventType.WATCHLIST_UPDATED,
            data={
                'symbols': list(self._symbols),
                'tier1': list(self._tier1),
                'tier2': list(self._tier2),
                'tier3': list(self._tier3),
                'scan_results': [r.to_dict() for r in results]
            },
            source="watchlist_manager"
        ))

        logger.info(
            "watchlist_updated",
            total=len(self._symbols),
            from_scan=len(self._tier1) + len(self._tier2),
            from_defaults=len(self._tier3)
        )

        return results

    def add_symbol(self, symbol: str, tier: int = 2) -> None:
        """Manually add symbol to watchlist"""
        symbol = symbol.upper()
        self._symbols.add(symbol)

        if tier == 1:
            self._tier1.add(symbol)
        elif tier == 2:
            self._tier2.add(symbol)
        else:
            self._tier3.add(symbol)

        logger.info("symbol_added", symbol=symbol, tier=tier)

    def remove_symbol(self, symbol: str) -> None:
        """Remove symbol from watchlist"""
        symbol = symbol.upper()
        self._symbols.discard(symbol)
        self._tier1.discard(symbol)
        self._tier2.discard(symbol)
        self._tier3.discard(symbol)
        self._scan_results.pop(symbol, None)

        logger.info("symbol_removed", symbol=symbol)

    def get_symbols(self, tier: int = None) -> List[str]:
        """
        Get symbols from watchlist.

        Args:
            tier: Optional tier filter (1, 2, 3)

        Returns:
            List of symbols
        """
        if tier == 1:
            return list(self._tier1)
        elif tier == 2:
            return list(self._tier2)
        elif tier == 3:
            return list(self._tier3)
        return list(self._symbols)

    def get_scan_result(self, symbol: str) -> Optional[ScanResult]:
        """Get scan result for symbol"""
        return self._scan_results.get(symbol.upper())

    def is_top_pick(self, symbol: str) -> bool:
        """Check if symbol is a top-tier pick"""
        return symbol.upper() in self._tier1

    def get_priority_score(self, symbol: str) -> float:
        """
        Get priority score for symbol.
        Higher = more priority for trading.
        """
        symbol = symbol.upper()

        # Base tier scores
        if symbol in self._tier1:
            base = 100
        elif symbol in self._tier2:
            base = 50
        else:
            base = 25

        # Add scan score if available
        result = self._scan_results.get(symbol)
        if result:
            base += result.score * 0.5

        return base

    @property
    def symbols(self) -> Set[str]:
        """All symbols in watchlist"""
        return self._symbols.copy()

    @property
    def symbol_count(self) -> int:
        return len(self._symbols)

    @property
    def last_update(self) -> Optional[datetime]:
        return self._last_update

    @property
    def stats(self) -> Dict:
        """Get watchlist statistics"""
        return {
            'total_symbols': len(self._symbols),
            'tier1_count': len(self._tier1),
            'tier2_count': len(self._tier2),
            'tier3_count': len(self._tier3),
            'scan_count': self._scan_count,
            'last_update': self._last_update.isoformat() if self._last_update else None
        }


# Singleton instance
_watchlist: Optional[WatchlistManager] = None


def get_watchlist() -> WatchlistManager:
    """Get or create watchlist manager singleton"""
    global _watchlist
    if _watchlist is None:
        _watchlist = WatchlistManager()
    return _watchlist


async def initialize_watchlist(run_scan: bool = True) -> WatchlistManager:
    """Initialize watchlist manager"""
    wl = get_watchlist()
    await wl.initialize(run_scan)
    return wl
