"""
Pydantic models for API request/response schemas.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


# Settings schemas
class SettingsCategory(str, Enum):
    ALPACA = "alpaca"
    ANTHROPIC = "anthropic"
    SCANNER = "scanner"
    POSITION_SIZING = "position_sizing"
    STOPS = "stops"
    PORTFOLIO = "portfolio"
    AI = "ai"
    TRADING_HOURS = "trading_hours"
    CRYPTO = "crypto"
    HFT = "hft"
    DASHBOARD = "dashboard"


class SettingsUpdate(BaseModel):
    """Update settings for a category"""
    settings: Dict[str, Any]


class SettingsResponse(BaseModel):
    """All settings grouped by category"""
    alpaca: Dict[str, Any]
    anthropic: Dict[str, Any]
    scanner: Dict[str, Any]
    position_sizing: Dict[str, Any]
    stops: Dict[str, Any]
    portfolio: Dict[str, Any]
    ai: Dict[str, Any]
    trading_hours: Dict[str, Any]
    crypto: Dict[str, Any]
    hft: Dict[str, Any]
    dashboard: Dict[str, Any]


# Position schemas
class PositionResponse(BaseModel):
    symbol: str
    qty: float
    side: str
    avg_entry_price: float
    market_value: float
    current_price: float
    unrealized_pl: float
    unrealized_plpc: float
    change_today: float = 0
    asset_class: str = "us_equity"


class PositionsResponse(BaseModel):
    positions: List[PositionResponse]
    total_value: float
    total_unrealized_pl: float


# Order schemas
class OrderRequest(BaseModel):
    symbol: str
    qty: float = Field(gt=0)
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "day"
    extended_hours: bool = False


class OrderResponse(BaseModel):
    order_id: str
    client_order_id: Optional[str]
    symbol: str
    qty: float
    side: str
    type: str
    status: str
    limit_price: Optional[float]
    stop_price: Optional[float]
    filled_qty: float = 0
    filled_avg_price: Optional[float]
    created_at: Optional[datetime]
    asset_class: str = "us_equity"


class OrdersResponse(BaseModel):
    orders: List[OrderResponse]


# Strategy schemas
class StrategyStatus(BaseModel):
    name: str
    enabled: bool
    description: str
    signals_generated: int = 0
    win_rate: float = 0.0
    params: Dict[str, Any] = {}


class StrategyToggle(BaseModel):
    enabled: bool


class StrategyParamsUpdate(BaseModel):
    params: Dict[str, Any]


class StrategiesResponse(BaseModel):
    strategies: List[StrategyStatus]


# Risk schemas
class RiskMetrics(BaseModel):
    portfolio_heat: float  # Total risk as % of equity
    daily_pnl: float
    daily_pnl_pct: float
    weekly_pnl: float
    weekly_pnl_pct: float
    max_daily_loss: float
    max_weekly_loss: float
    daily_limit_remaining: float
    weekly_limit_remaining: float
    position_count: int
    max_positions: int
    consecutive_losses: int
    is_halted: bool
    halt_reason: Optional[str] = None


# System schemas
class SystemStatus(BaseModel):
    running: bool
    mode: str  # "live", "paper", "dry_run"
    uptime_seconds: float
    cycle_count: int
    last_cycle_time_ms: float
    equity: float
    cash: float
    buying_power: float
    position_count: int
    open_orders: int
    crypto_enabled: bool
    hft_enabled: bool


class SystemAction(BaseModel):
    action: str  # "start", "stop"


# WebSocket event schemas
class WSEventType(str, Enum):
    POSITION_UPDATE = "position_update"
    ORDER_UPDATE = "order_update"
    SIGNAL = "signal"
    RISK_ALERT = "risk_alert"
    HEARTBEAT = "heartbeat"
    SYSTEM_STATUS = "system_status"


class WSEvent(BaseModel):
    type: WSEventType
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)


# Trade history schemas
class TradeRecord(BaseModel):
    trade_id: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    exit_price: Optional[float]
    pnl: Optional[float]
    pnl_pct: Optional[float]
    strategy: str
    entry_time: datetime
    exit_time: Optional[datetime]
    status: str  # "open", "closed", "cancelled"


class TradesResponse(BaseModel):
    trades: List[TradeRecord]
    total_count: int
    page: int
    page_size: int
