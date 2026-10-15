"""
Custom exceptions for the trading system.
"""


class TradingException(Exception):
    """Base exception for all trading-related errors"""


class ConfigurationError(TradingException):
    """Invalid configuration"""


class ConnectionError(TradingException):
    """Connection to external service failed"""


class DataError(TradingException):
    """Error fetching or processing market data"""


class InsufficientDataError(DataError):
    """Not enough data for calculation"""


class StreamDisconnected(ConnectionError):
    """WebSocket stream disconnected"""


class OrderError(TradingException):
    """Base class for order-related errors"""


class OrderRejected(OrderError):
    """Order was rejected by broker"""
    def __init__(self, reason: str, order_id: str = None):
        self.reason = reason
        self.order_id = order_id
        super().__init__(f"Order rejected: {reason}")


class InsufficientFunds(OrderError):
    """Not enough buying power"""


class PositionLimitExceeded(OrderError):
    """Would exceed position limits"""


class RiskLimitExceeded(TradingException):
    """Risk limit violated"""
    def __init__(self, limit_type: str, current: float, limit: float):
        self.limit_type = limit_type
        self.current = current
        self.limit = limit
        super().__init__(f"{limit_type} exceeded: {current:.2%} > {limit:.2%}")


class DailyLossLimitExceeded(RiskLimitExceeded):
    """Daily loss limit hit"""


class WeeklyLossLimitExceeded(RiskLimitExceeded):
    """Weekly loss limit hit"""


class PortfolioHeatExceeded(RiskLimitExceeded):
    """Portfolio heat limit exceeded"""


class StrategyError(TradingException):
    """Error in strategy execution"""


class SignalError(TradingException):
    """Invalid signal generated"""


class AIError(TradingException):
    """Error in AI decision engine"""


class AITimeoutError(AIError):
    """AI took too long to respond"""


class AIRateLimitError(AIError):
    """AI API rate limit hit"""


class MarketClosedError(TradingException):
    """Attempted trade while market is closed"""


class InvalidSymbolError(TradingException):
    """Symbol not tradeable or doesn't exist"""


class ScannerError(TradingException):
    """Error in pre-market scanner"""
