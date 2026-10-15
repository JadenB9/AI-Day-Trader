"""
Pydantic settings for the AI Day Trading System.
All configuration centralized here - other modules import from this.
"""
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from enum import Enum
from dotenv import load_dotenv

# Load .env file first
load_dotenv()


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
    model_config = SettingsConfigDict(env_prefix="ALPACA_", env_file=".env", extra="ignore")

    api_key: str = Field(default="")
    secret_key: str = Field(default="")
    base_url: str = Field(default="https://paper-api.alpaca.markets")
    data_url: str = Field(default="https://data.alpaca.markets")
    stream_url: str = Field(default="wss://stream.data.alpaca.markets/v2/iex")
    trading_mode: TradingMode = Field(default=TradingMode.PAPER)


class AnthropicSettings(BaseSettings):
    """Claude API configuration"""
    model_config = SettingsConfigDict(env_prefix="ANTHROPIC_", env_file=".env", extra="ignore")

    api_key: str = Field(default="")
    model: str = Field(default="claude-sonnet-4-20250514")
    max_tokens: int = Field(default=4096)
    temperature: float = Field(default=0.3)


class ScannerSettings(BaseSettings):
    """Pre-market scanner configuration"""
    model_config = SettingsConfigDict(env_prefix="SCANNER_", env_file=".env", extra="ignore")

    min_gap_percent: float = Field(default=3.0)
    max_gap_percent: float = Field(default=20.0)
    min_premarket_volume: int = Field(default=100000)
    require_news: bool = Field(default=False)
    relative_volume_min: float = Field(default=2.0)
    min_price: float = Field(default=5.0)
    max_price: float = Field(default=500.0)
    min_5d_change: float = Field(default=10.0)
    min_avg_volume: int = Field(default=500000)
    max_watchlist_size: int = Field(default=30)
    scan_start_time: str = Field(default="04:00")
    scan_end_time: str = Field(default="09:25")


class PositionSizingSettings(BaseSettings):
    """Position sizing configuration"""
    model_config = SettingsConfigDict(env_prefix="SIZING_", env_file=".env", extra="ignore")

    method: PositionSizingMethod = Field(default=PositionSizingMethod.FIXED_FRACTIONAL)
    risk_per_trade: float = Field(default=0.03)  # Increased from 0.01 - more aggressive
    max_position_pct: float = Field(default=0.10)  # Increased from 0.05 - larger positions
    kelly_fraction: float = Field(default=0.35)  # Increased from 0.25


class StopSettings(BaseSettings):
    """Stop loss configuration"""
    model_config = SettingsConfigDict(env_prefix="STOP_", env_file=".env", extra="ignore")

    method: StopMethod = Field(default=StopMethod.ATR_BASED)
    atr_multiplier: float = Field(default=2.0)
    percentage: float = Field(default=0.02)
    time_stop_minutes: int = Field(default=15)
    trailing_pct: float = Field(default=0.015)


class PortfolioSettings(BaseSettings):
    """Portfolio risk limits - AGGRESSIVE SETTINGS"""
    model_config = SettingsConfigDict(env_prefix="PORTFOLIO_", env_file=".env", extra="ignore")

    max_positions: int = Field(default=30)  # Increased from 20
    max_portfolio_heat: float = Field(default=0.25)  # Increased from 0.05 - allow 25% at risk
    max_sector_exposure: float = Field(default=0.40)  # Increased from 0.25
    max_correlated_positions: int = Field(default=6)  # Increased from 3
    max_daily_loss: float = Field(default=0.10)  # Increased from 0.02 - 10% daily tolerance
    max_weekly_loss: float = Field(default=0.20)  # Increased from 0.06 - 20% weekly tolerance
    consecutive_loss_pause_days: int = Field(default=1)  # Reduced from 3

    # Virtual capital limit - use this instead of actual account equity
    # Set to 0 to use actual account equity
    virtual_capital: float = Field(default=1000.0)
    # Reserve amount - trading stops if equity falls below this
    # For $100k paper account with $1k virtual capital, reserve = $99,000
    capital_reserve: float = Field(default=99000.0)


class AISettings(BaseSettings):
    """AI decision engine configuration - AGGRESSIVE SETTINGS"""
    model_config = SettingsConfigDict(env_prefix="AI_", env_file=".env", extra="ignore")

    confidence_threshold: float = Field(default=0.45)  # Lowered from 0.80 - let more signals through
    position_size_threshold: float = Field(default=0.01)  # Lowered from 0.03
    vix_spike_threshold: float = Field(default=35.0)  # Increased from 25.0 - trade in higher vol
    enable_web_search: bool = Field(default=True)
    max_context_tokens: int = Field(default=8000)
    cache_decisions_seconds: int = Field(default=300)


class TradingHoursSettings(BaseSettings):
    """Trading hours configuration"""
    model_config = SettingsConfigDict(env_prefix="HOURS_", env_file=".env", extra="ignore")

    extended_hours_enabled: bool = Field(default=True)
    premarket_start: str = Field(default="04:00")
    market_open: str = Field(default="09:30")
    market_close: str = Field(default="16:00")
    afterhours_end: str = Field(default="20:00")
    timezone: str = Field(default="America/New_York")


class DatabaseSettings(BaseSettings):
    """Database configuration"""
    model_config = SettingsConfigDict(env_prefix="DB_", env_file=".env", extra="ignore")

    url: str = Field(default="sqlite+aiosqlite:///storage/trades.db")
    echo: bool = Field(default=False)


class LoggingSettings(BaseSettings):
    """Logging configuration"""
    model_config = SettingsConfigDict(env_prefix="LOG_", env_file=".env", extra="ignore")

    level: str = Field(default="INFO")
    format: str = Field(default="json")
    file_path: Optional[str] = Field(default="logs/trader.log")


class CryptoSettings(BaseSettings):
    """Crypto trading configuration - ENABLED BY DEFAULT FOR 24/7 TRADING"""
    model_config = SettingsConfigDict(env_prefix="CRYPTO_", env_file=".env", extra="ignore")

    enabled: bool = Field(default=True)  # Enabled by default for aggressive trading
    # All available Alpaca crypto symbols
    symbols: List[str] = Field(default=[
        # Major coins
        "BTC/USD", "ETH/USD", "SOL/USD", "LTC/USD", "AVAX/USD", "LINK/USD",
        # Meme coins (high volatility)
        "DOGE/USD", "SHIB/USD",
        # DeFi tokens
        "UNI/USD", "AAVE/USD", "SUSHI/USD", "CRV/USD",
        # Other altcoins
        "DOT/USD", "MATIC/USD", "ATOM/USD", "ALGO/USD", "XLM/USD", "XTZ/USD",
        "BCH/USD", "BAT/USD"
    ])
    max_position_pct: float = Field(default=0.02)  # Smaller for volatile crypto
    volatility_multiplier: float = Field(default=1.5)  # Wider stops
    min_order_size: float = Field(default=1.0)  # Minimum $1 order


class HFTSettings(BaseSettings):
    """High-frequency trading configuration"""
    model_config = SettingsConfigDict(env_prefix="HFT_", env_file=".env", extra="ignore")

    enabled: bool = Field(default=False)
    cycle_time_ms: int = Field(default=1000)  # 1 second cycles
    skip_ai_evaluation: bool = Field(default=True)  # Bypass AI for speed
    max_positions: int = Field(default=30)
    max_daily_loss: float = Field(default=0.03)  # 3% tolerance
    indicator_cache_ttl_ms: int = Field(default=500)
    enable_momentum_burst: bool = Field(default=True)
    enable_spread_capture: bool = Field(default=False)
    enable_crypto_scalp: bool = Field(default=True)


class DashboardSettings(BaseSettings):
    """Web dashboard configuration"""
    model_config = SettingsConfigDict(env_prefix="DASHBOARD_", env_file=".env", extra="ignore")

    enabled: bool = Field(default=True)
    host: str = Field(default="127.0.0.1")  # loopback only; the API can start and stop trading
    port: int = Field(default=8000)
    cors_origins: List[str] = Field(default=["http://localhost:5173", "http://localhost:3000"])
    api_key: Optional[str] = Field(default=None)  # Optional API key auth
    websocket_heartbeat_sec: int = Field(default=2)


class Settings(BaseSettings):
    """Main settings aggregator"""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App-level settings
    dry_run: bool = Field(default=False)
    debug: bool = Field(default=False)

    # Default watchlist - EXPANDED for aggressive trading
    # Includes major tech, meme stocks, and high-volatility names
    default_symbols: List[str] = Field(default=[
        # Major indices & ETFs
        "SPY", "QQQ", "IWM",
        # Mega-cap tech (always liquid)
        "AAPL", "MSFT", "NVDA", "AMD", "TSLA", "META", "GOOGL", "AMZN",
        # High-volume volatile stocks
        "PLTR", "SOFI", "COIN", "HOOD", "RIVN", "LCID", "NIO", "BABA",
        # Meme & momentum stocks
        "GME", "AMC", "BBBY", "MARA", "RIOT", "HBAR",
        # Biotech (high volatility)
        "MRNA", "BNTX",
        # Semiconductors
        "INTC", "MU", "QCOM", "ARM",
        # Financials
        "JPM", "BAC", "GS"
    ])

    @property
    def alpaca(self) -> AlpacaSettings:
        return AlpacaSettings()

    @property
    def anthropic(self) -> AnthropicSettings:
        return AnthropicSettings()

    @property
    def scanner(self) -> ScannerSettings:
        return ScannerSettings()

    @property
    def position_sizing(self) -> PositionSizingSettings:
        return PositionSizingSettings()

    @property
    def stops(self) -> StopSettings:
        return StopSettings()

    @property
    def portfolio(self) -> PortfolioSettings:
        return PortfolioSettings()

    @property
    def ai(self) -> AISettings:
        return AISettings()

    @property
    def trading_hours(self) -> TradingHoursSettings:
        return TradingHoursSettings()

    @property
    def database(self) -> DatabaseSettings:
        return DatabaseSettings()

    @property
    def logging(self) -> LoggingSettings:
        return LoggingSettings()

    @property
    def crypto(self) -> CryptoSettings:
        return CryptoSettings()

    @property
    def hft(self) -> HFTSettings:
        return HFTSettings()

    @property
    def dashboard(self) -> DashboardSettings:
        return DashboardSettings()


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get settings singleton"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Force reload settings"""
    global _settings
    _settings = Settings()
    return _settings
