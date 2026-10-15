"""
Pre-market scanner for finding trading opportunities.
Runs daily before market open to build dynamic watchlist.
"""
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
import structlog

from config.settings import get_settings
from src.data.historical.alpaca_client import get_historical_client, AlpacaHistoricalClient
from src.data.scanner.criteria import (
    ScannerCriteria, ScanResult, ScanType
)
from src.data.models.market_snapshot import BarTimeframe
from src.core.event_bus import get_event_bus, EventType, Event

logger = structlog.get_logger()
settings = get_settings()


# Universe of symbols to scan (can be loaded from file/API)
# This is a sample - in production, fetch from screener API
DEFAULT_UNIVERSE = [
    # Large cap tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "AMD", "TSLA",
    # Popular volatile stocks
    "SPY", "QQQ", "TQQQ", "SQQQ", "SOXL",
    # Financial
    "JPM", "BAC", "GS", "MS",
    # Consumer
    "WMT", "TGT", "COST", "HD",
    # Healthcare
    "UNH", "JNJ", "PFE", "MRNA",
    # Energy
    "XOM", "CVX", "OXY",
    # Meme/volatile
    "GME", "AMC", "PLTR", "SOFI", "RIVN", "LCID",
    # ETFs
    "IWM", "DIA", "XLF", "XLE", "XLK"
]


class PremarketScanner:
    """
    Scans pre-market for trading opportunities.
    Runs gap, volume, and momentum scans.
    """

    def __init__(
        self,
        criteria: ScannerCriteria = None,
        universe: List[str] = None
    ):
        self.criteria = criteria or ScannerCriteria()
        self.universe = universe or DEFAULT_UNIVERSE
        self._client: AlpacaHistoricalClient = get_historical_client()
        self._event_bus = get_event_bus()
        self._last_scan: Optional[datetime] = None
        self._results: List[ScanResult] = []

    async def run_full_scan(self) -> List[ScanResult]:
        """
        Run all enabled scans and return combined results.
        """
        logger.info("scanner_starting", universe_size=len(self.universe))
        start_time = datetime.now()

        all_results: List[ScanResult] = []

        # Fetch base data for all symbols
        snapshots = await self._fetch_snapshots(self.universe)

        # Run each enabled scan type
        for scan_type in self.criteria.enabled_scans:
            try:
                if scan_type == ScanType.GAP:
                    results = await self._run_gap_scan(snapshots)
                elif scan_type == ScanType.VOLUME:
                    results = await self._run_volume_scan(snapshots)
                elif scan_type == ScanType.MOMENTUM:
                    results = await self._run_momentum_scan(snapshots)
                else:
                    continue

                all_results.extend(results)
                logger.info("scan_complete", scan_type=scan_type.value, results=len(results))

            except Exception as e:
                logger.error("scan_error", scan_type=scan_type.value, error=str(e))

        # Deduplicate and rank
        final_results = self._rank_and_dedupe(all_results)

        # Store results
        self._results = final_results
        self._last_scan = datetime.now()

        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(
            "scanner_complete",
            total_results=len(final_results),
            elapsed_seconds=elapsed
        )

        # Publish event
        await self._event_bus.publish(Event(
            type=EventType.SCANNER_RESULT,
            data=final_results,
            source="premarket_scanner"
        ))

        return final_results

    async def _fetch_snapshots(self, symbols: List[str]) -> Dict[str, Dict]:
        """Fetch market snapshots for all symbols"""
        snapshots = {}

        # Batch fetch in chunks to avoid rate limits
        chunk_size = 20
        for i in range(0, len(symbols), chunk_size):
            chunk = symbols[i:i + chunk_size]
            tasks = [self._client.get_snapshot(sym) for sym in chunk]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for sym, result in zip(chunk, results):
                if isinstance(result, Exception):
                    logger.warning("snapshot_fetch_error", symbol=sym, error=str(result))
                elif result:
                    snapshots[sym] = result

            # Small delay between batches
            if i + chunk_size < len(symbols):
                await asyncio.sleep(0.1)

        return snapshots

    async def _run_gap_scan(self, snapshots: Dict[str, Dict]) -> List[ScanResult]:
        """Scan for pre-market gaps"""
        results = []
        criteria = self.criteria.gap

        for symbol, snap in snapshots.items():
            try:
                daily = snap.get('daily_bar', {})
                prev = snap.get('prev_daily_bar', {})

                if not daily.get('open') or not prev.get('close'):
                    continue

                current_price = daily.get('close', daily.get('open'))
                prev_close = prev['close']

                # Calculate gap
                gap_pct = ((daily['open'] - prev_close) / prev_close) * 100

                # Check direction filter
                if criteria.direction == "up" and gap_pct < 0:
                    continue
                if criteria.direction == "down" and gap_pct > 0:
                    continue

                # Apply gap criteria
                abs_gap = abs(gap_pct)
                if abs_gap < criteria.min_gap_pct or abs_gap > criteria.max_gap_pct:
                    continue

                # Volume check (using daily volume as proxy for premarket)
                volume = daily.get('volume', 0)
                if volume < criteria.min_premarket_volume:
                    continue

                # Calculate score (higher gap + higher volume = better)
                gap_score = min(abs_gap / criteria.max_gap_pct * 50, 50)
                vol_score = min(volume / 1000000 * 50, 50)  # 1M volume = 50 points
                score = gap_score + vol_score

                results.append(ScanResult(
                    symbol=symbol,
                    scan_type=ScanType.GAP,
                    score=score,
                    price=current_price,
                    gap_pct=gap_pct,
                    premarket_volume=volume,
                    avg_volume=prev.get('volume', 0)
                ))

            except Exception as e:
                logger.debug("gap_scan_symbol_error", symbol=symbol, error=str(e))

        # Sort by score and limit
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:self.criteria.max_results_per_scan]

    async def _run_volume_scan(self, snapshots: Dict[str, Dict]) -> List[ScanResult]:
        """Scan for unusual volume"""
        results = []
        criteria = self.criteria.volume

        for symbol, snap in snapshots.items():
            try:
                daily = snap.get('daily_bar', {})
                prev = snap.get('prev_daily_bar', {})

                current_price = daily.get('close', 0)
                if not current_price:
                    continue

                # Price filter
                if current_price < criteria.min_price or current_price > criteria.max_price:
                    continue

                current_vol = daily.get('volume', 0)
                avg_vol = prev.get('volume', 0)

                if avg_vol == 0:
                    continue

                # Calculate relative volume
                rel_vol = current_vol / avg_vol

                if rel_vol < criteria.min_relative_volume:
                    continue

                # Dollar volume check
                dollar_vol = current_vol * current_price
                if dollar_vol < criteria.min_dollar_volume:
                    continue

                # Calculate score
                vol_score = min(rel_vol / 5 * 60, 60)  # 5x RVOL = 60 points
                price_score = min(dollar_vol / 10000000 * 40, 40)  # $10M = 40 points
                score = vol_score + price_score

                results.append(ScanResult(
                    symbol=symbol,
                    scan_type=ScanType.VOLUME,
                    score=score,
                    price=current_price,
                    relative_volume=rel_vol,
                    avg_volume=avg_vol,
                    premarket_volume=current_vol
                ))

            except Exception as e:
                logger.debug("volume_scan_symbol_error", symbol=symbol, error=str(e))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:self.criteria.max_results_per_scan]

    async def _run_momentum_scan(self, snapshots: Dict[str, Dict]) -> List[ScanResult]:
        """Scan for momentum stocks"""
        results = []
        criteria = self.criteria.momentum

        # Need historical data for momentum
        for symbol, snap in snapshots.items():
            try:
                daily = snap.get('daily_bar', {})
                prev = snap.get('prev_daily_bar', {})

                current_price = daily.get('close', 0)
                if not current_price or current_price < criteria.min_price:
                    continue

                avg_vol = prev.get('volume', 0)
                if avg_vol < criteria.min_avg_volume:
                    continue

                # Get 5-day bars for momentum calc
                bars = await self._client.get_bars(
                    symbol,
                    BarTimeframe.DAY,
                    limit=6
                )

                if len(bars) < 6:
                    continue

                # 5-day change
                old_close = bars[0].close
                new_close = bars[-1].close
                change_5d = ((new_close - old_close) / old_close) * 100

                if change_5d < criteria.min_5d_change_pct:
                    continue

                # Calculate score
                momentum_score = min(change_5d / 20 * 70, 70)  # 20% = 70 points
                vol_score = min(avg_vol / 2000000 * 30, 30)  # 2M avg vol = 30 points
                score = momentum_score + vol_score

                results.append(ScanResult(
                    symbol=symbol,
                    scan_type=ScanType.MOMENTUM,
                    score=score,
                    price=current_price,
                    change_5d_pct=change_5d,
                    avg_volume=avg_vol,
                    relative_volume=daily.get('volume', 0) / avg_vol if avg_vol else 1.0
                ))

            except Exception as e:
                logger.debug("momentum_scan_symbol_error", symbol=symbol, error=str(e))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:self.criteria.max_results_per_scan]

    def _rank_and_dedupe(self, results: List[ScanResult]) -> List[ScanResult]:
        """Remove duplicates and rank final results"""
        # Keep best result per symbol
        best_by_symbol: Dict[str, ScanResult] = {}
        for result in results:
            sym = result.symbol
            if sym not in best_by_symbol or result.score > best_by_symbol[sym].score:
                best_by_symbol[sym] = result

        # Sort by score
        final = sorted(best_by_symbol.values(), key=lambda x: x.score, reverse=True)

        # Limit total results
        return final[:self.criteria.max_total_results]

    def get_symbols(self) -> List[str]:
        """Get list of symbols from last scan"""
        return [r.symbol for r in self._results]

    def get_results(self) -> List[ScanResult]:
        """Get results from last scan"""
        return self._results

    @property
    def last_scan_time(self) -> Optional[datetime]:
        return self._last_scan


async def run_premarket_scan(
    criteria: ScannerCriteria = None,
    universe: List[str] = None
) -> List[ScanResult]:
    """Convenience function to run pre-market scan"""
    scanner = PremarketScanner(criteria, universe)
    return await scanner.run_full_scan()
