"""
Scanner filter criteria definitions.
"""
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


class ScanType(str, Enum):
    GAP = "gap"
    VOLUME = "volume"
    MOMENTUM = "momentum"
    EARNINGS = "earnings"
    NEWS = "news"
    COMBINED = "combined"


@dataclass
class GapCriteria:
    """Criteria for gap scanner"""
    min_gap_pct: float = 3.0
    max_gap_pct: float = 20.0
    min_premarket_volume: int = 100000
    require_news: bool = False
    direction: str = "both"  # up, down, both


@dataclass
class VolumeCriteria:
    """Criteria for volume scanner"""
    min_relative_volume: float = 2.0  # vs 20-day average
    min_price: float = 5.0
    max_price: float = 500.0
    min_dollar_volume: float = 1000000


@dataclass
class MomentumCriteria:
    """Criteria for momentum scanner"""
    min_5d_change_pct: float = 10.0
    min_avg_volume: int = 500000
    min_price: float = 5.0
    rsi_min: float = 50.0  # Looking for strength
    rsi_max: float = 80.0  # Not too overbought


@dataclass
class EarningsCriteria:
    """Criteria for earnings scanner"""
    days_until_earnings: List[int] = field(default_factory=lambda: [0, 1])
    min_volume: int = 500000
    min_price: float = 10.0


@dataclass
class ScannerCriteria:
    """Combined scanner criteria"""
    # General filters
    min_price: float = 5.0
    max_price: float = 500.0
    min_avg_volume: int = 500000
    max_spread_pct: float = 0.5  # Max bid-ask spread %

    # Specific criteria
    gap: GapCriteria = field(default_factory=GapCriteria)
    volume: VolumeCriteria = field(default_factory=VolumeCriteria)
    momentum: MomentumCriteria = field(default_factory=MomentumCriteria)
    earnings: EarningsCriteria = field(default_factory=EarningsCriteria)

    # Scan types to run
    enabled_scans: List[ScanType] = field(default_factory=lambda: [
        ScanType.GAP,
        ScanType.VOLUME,
        ScanType.MOMENTUM
    ])

    # Results
    max_results_per_scan: int = 20
    max_total_results: int = 30


@dataclass
class ScanResult:
    """Individual scan result"""
    symbol: str
    scan_type: ScanType
    score: float  # 0-100 composite score

    # Common metrics
    price: float
    gap_pct: float = 0.0
    relative_volume: float = 1.0
    premarket_volume: int = 0
    avg_volume: int = 0
    change_5d_pct: float = 0.0

    # Additional context
    has_news: bool = False
    news_headlines: List[str] = field(default_factory=list)
    sector: str = ""

    def to_dict(self):
        return {
            'symbol': self.symbol,
            'scan_type': self.scan_type.value,
            'score': self.score,
            'price': self.price,
            'gap_pct': self.gap_pct,
            'relative_volume': self.relative_volume,
            'premarket_volume': self.premarket_volume,
            'has_news': self.has_news
        }
