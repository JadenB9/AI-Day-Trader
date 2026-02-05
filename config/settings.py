"""
Pydantic settings for the AI Day Trading System.
All configuration centralized here - other modules import from this.
"""
import os
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from enum import Enum


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class PositionSizingMethod(str, Enum):
    FIXED_FRACTIONAL = "fixed_fractional"
    KELLY = "kelly"
    ATR_BASED = "atr_based"


class StopMethod(str, Enum):
    ATR_BASED = "atr_based"
    PERCENTAGE = "percentage"
    TRAILING = "trailing"


class AlpacaSettings(BaseSettings):
    """Alpaca API configuration"""
    model_config = SettingsConfigDict(env_prefix="ALPACA_")

    api_key: str = Field(default="")
    secret_key: str = Field(default="")
    base_url: str = Field(default="https://paper-api.alpaca.markets")
    data_url: str = Field(default="https://data.alpaca.markets")
    stream_url: str = Field(default="wss://stream.data.alpaca.markets/v2/iex")
    trading_mode: TradingMode = Field(default=TradingMode.PAPER)


class AnthropicSettings(BaseSettings):
    """Claude API configuration"""
    model_config = SettingsConfigDict(env_prefix="ANTHROPIC_")

    api_key: str = Field(default="")
    model: str = Field(default="claude-opus-4-5-20250101")
    max_tokens: int = Field(default=4096)
    temperature: float = Field(default=0.3)


class ScannerSettings(BaseSettings):
    """Pre-market scanner configuration"""
    model_config = SettingsConfigDict(env_prefix="SCANNER_")

    # Gap scan
    min_gap_percent: float = Field(default=3.0)
    max_gap_percent: float = Field(default=20.0)
    min_premarket_volume: int = Field(default=100000)
    require_news: bool = Field(default=False)

    # Volume scan
    relative_volume_min: float = Field(default=2.0)
    min_price: float = Field(default=5.0)
    max_price: float = Field(default=500.0)

    # Momentum scan
    min_5d_change: float = Field(default=10.0)
    min_avg_volume: int = Field(default=500000)

    # Watchlist
    max_watchlist_size: int = Field(default=30)

    # Scan timing
    scan_start_time: str = Field(default="04:00")  # ET
    scan_end_time: str = Field(default="09:25")


class PositionSizingSettings(BaseSettings):
    """Position sizing configuration"""
    model_config = SettingsConfigDict(env_prefix="SIZING_")

    method: PositionSizingMethod = Field(default=PositionSizingMethod.FIXED_FRACTIONAL)
    risk_per_trade: float = Field(default=0.01)  # 1%
    max_position_pct: float = Field(default=0.05)  # 5% max single position
    kelly_fraction: float = Field(default=0.25)  # Quarter Kelly


class StopSettings(BaseSettings):
    """Stop loss configuration"""
    model_config = SettingsConfigDict(env_prefix="STOP_")

    method: StopMethod = Field(default=StopMethod.ATR_BASED)
    atr_multiplier: float = Field(default=2.0)
    percentage: float = Field(default=0.02)  # 2% default
    time_stop_minutes: int = Field(default=15)
    trailing_pct: float = Field(default=0.015)


class PortfolioSettings(BaseSettings):
    """Portfolio risk limits"""
    model_config = SettingsConfigDict(env_prefix="PORTFOLIO_")

    max_positions: int = Field(default=20)
    max_portfolio_heat: float = Field(default=0.05)  # 5%
    max_sector_exposure: float = Field(default=0.25)  # 25%
    max_correlated_positions: int = Field(default=3)
    max_daily_loss: float = Field(default=0.02)  # 2%
    max_weekly_loss: float = Field(default=0.06)  # 6%
    consecutive_loss_pause_days: int = Field(default=3)


class AISettings(BaseSettings):
    """AI decision engine configuration"""
    model_config = SettingsConfigDict(env_prefix="AI_")

    # Thresholds for AI involvement
    confidence_threshold: float = Field(default=0.80)  # 80%
    position_size_threshold: float = Field(default=0.03)  # 3% of equity
    vix_spike_threshold: float = Field(default=25.0)

    # Behavior
    enable_web_search: bool = Field(default=True)
    max_context_tokens: int = Field(default=8000)
    cache_decisions_seconds: int = Field(default=300)


class TradingHoursSettings(BaseSettings):
    """Trading hours configuration"""
    model_config = SettingsConfigDict(env_prefix="HOURS_")

    extended_hours_enabled: bool = Field(default=True)
    premarket_start: str = Field(default="04:00")
    market_open: str = Field(default="09:30")
    market_close: str = Field(default="16:00")
    afterhours_end: str = Field(default="20:00")
    timezone: str = Field(default="America/New_York")


class DatabaseSettings(BaseSettings):
    """Database configuration"""
    model_config = SettingsConfigDict(env_prefix="DB_")

    url: str = Field(default="sqlite+aiosqlite:///storage/trades.db")
    echo: bool = Field(default=False)


class LoggingSettings(BaseSettings):
    """Logging configuration"""
    model_config = SettingsConfigDict(env_prefix="LOG_")

    level: str = Field(default="INFO")
    format: str = Field(default="json")  # json or console
    file_path: Optional[str] = Field(default="logs/trader.log")


class Settings(BaseSettings):
    """Main settings aggregator"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Sub-settings
    alpaca: AlpacaSettings = Field(default_factory=AlpacaSettings)
    anthropic: AnthropicSettings = Field(default_factory=AnthropicSettings)
    scanner: ScannerSettings = Field(default_factory=ScannerSettings)
    position_sizing: PositionSizingSettings = Field(default_factory=PositionSizingSettings)
    stops: StopSettings = Field(default_factory=StopSettings)
    portfolio: PortfolioSettings = Field(default_factory=PortfolioSettings)
    ai: AISettings = Field(default_factory=AISettings)
    trading_hours: TradingHoursSettings = Field(default_factory=TradingHoursSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    # App-level settings
    dry_run: bool = Field(default=False)
    debug: bool = Field(default=False)

    # Default watchlist (fallback if scanner finds nothing)
    default_symbols: List[str] = Field(default=[
        "SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMD", "TSLA",
        "META", "GOOGL", "AMZN"
    ])


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get settings singleton, loading from env if needed"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Force reload settings from environment"""
    global _settings
    _settings = Settings()
    return _settings
