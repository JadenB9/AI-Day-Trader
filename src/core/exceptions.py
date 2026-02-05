"""
Custom exceptions for the trading system.
"""


class TradingException(Exception):
    """Base exception for all trading-related errors"""
    pass


class ConfigurationError(TradingException):
    """Invalid configuration"""
    pass


class ConnectionError(TradingException):
    """Connection to external service failed"""
    pass


class DataError(TradingException):
    """Error fetching or processing market data"""
    pass


class InsufficientDataError(DataError):
    """Not enough data for calculation"""
    pass


class StreamDisconnected(ConnectionError):
    """WebSocket stream disconnected"""
    pass


class OrderError(TradingException):
    """Base class for order-related errors"""
    pass


class OrderRejected(OrderError):
    """Order was rejected by broker"""
    def __init__(self, reason: str, order_id: str = None):
        self.reason = reason
        self.order_id = order_id
        super().__init__(f"Order rejected: {reason}")


class InsufficientFunds(OrderError):
    """Not enough buying power"""
    pass


class PositionLimitExceeded(OrderError):
    """Would exceed position limits"""
    pass


class RiskLimitExceeded(TradingException):
    """Risk limit violated"""
    def __init__(self, limit_type: str, current: float, limit: float):
        self.limit_type = limit_type
        self.current = current
        self.limit = limit
        super().__init__(f"{limit_type} exceeded: {current:.2%} > {limit:.2%}")


class DailyLossLimitExceeded(RiskLimitExceeded):
    """Daily loss limit hit"""
    pass


class WeeklyLossLimitExceeded(RiskLimitExceeded):
    """Weekly loss limit hit"""
    pass


class PortfolioHeatExceeded(RiskLimitExceeded):
    """Portfolio heat limit exceeded"""
    pass


class StrategyError(TradingException):
    """Error in strategy execution"""
    pass


class SignalError(TradingException):
    """Invalid signal generated"""
    pass


class AIError(TradingException):
    """Error in AI decision engine"""
    pass


class AITimeoutError(AIError):
    """AI took too long to respond"""
    pass


class AIRateLimitError(AIError):
    """AI API rate limit hit"""
    pass


class MarketClosedError(TradingException):
    """Attempted trade while market is closed"""
    pass


class InvalidSymbolError(TradingException):
    """Symbol not tradeable or doesn't exist"""
    pass


class ScannerError(TradingException):
    """Error in pre-market scanner"""
    pass
