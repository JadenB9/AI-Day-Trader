"""
Pre-trade validation.
Gate-keeper that validates all trades before execution.
"""
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from enum import Enum
import structlog

from config.settings import get_settings
from src.strategies.base import Signal, SignalDirection
from src.risk.daily_limits import get_limits_manager, DailyLimitsManager
from src.risk.position_sizer import PositionSizer
from src.core.exceptions import (
    RiskLimitExceeded, PositionLimitExceeded,
    InsufficientFunds, OrderRejected
)

logger = structlog.get_logger()
settings = get_settings()


class RejectionReason(str, Enum):
    DAILY_LIMIT = "daily_loss_limit"
    WEEKLY_LIMIT = "weekly_loss_limit"
    POSITION_LIMIT = "max_positions_exceeded"
    SECTOR_LIMIT = "sector_exposure_exceeded"
    HEAT_LIMIT = "portfolio_heat_exceeded"
    INSUFFICIENT_FUNDS = "insufficient_buying_power"
    CORRELATED = "too_many_correlated_positions"
    DUPLICATE = "duplicate_position"
    SIZE_TOO_LARGE = "position_size_too_large"
    LOW_CONFIDENCE = "confidence_below_minimum"
    SPREAD_TOO_WIDE = "bid_ask_spread_too_wide"
    MARKET_CLOSED = "market_closed"


@dataclass
class ValidationResult:
    """Result of pre-trade validation"""
    approved: bool
    original_signal: Signal
    adjusted_signal: Optional[Signal] = None
    rejection_reason: Optional[RejectionReason] = None
    message: str = ""
    risk_metrics: Dict = None

    def __post_init__(self):
        if self.risk_metrics is None:
            self.risk_metrics = {}


@dataclass
class PortfolioState:
    """Current portfolio state for validation"""
    equity: float
    cash: float
    buying_power: float
    positions: Dict[str, Dict]  # symbol -> position info
    daily_pnl: float
    open_risk: float  # Total risk in open positions


class TradeValidator:
    """
    Validates trades against risk limits.
    Acts as final gate before order execution.
    """

    def __init__(
        self,
        portfolio_state: PortfolioState = None,
        limits_manager: DailyLimitsManager = None
    ):
        self._portfolio = portfolio_state
        self._limits = limits_manager or get_limits_manager()

        # Load limits from settings
        self.max_positions = settings.portfolio.max_positions
        self.max_portfolio_heat = settings.portfolio.max_portfolio_heat
        self.max_sector_exposure = settings.portfolio.max_sector_exposure
        self.max_correlated = settings.portfolio.max_correlated_positions
        self.min_confidence = 0.5
        self.max_spread_pct = 0.5  # 0.5%

    def update_portfolio(self, state: PortfolioState) -> None:
        """Update portfolio state"""
        self._portfolio = state

    def validate(
        self,
        signal: Signal,
        current_price: float = None,
        spread: float = None
    ) -> ValidationResult:
        """
        Validate a trading signal against all risk rules.

        Args:
            signal: Signal to validate
            current_price: Current market price
            spread: Current bid-ask spread

        Returns:
            ValidationResult with approval status
        """
        if self._portfolio is None:
            return ValidationResult(
                approved=False,
                original_signal=signal,
                rejection_reason=RejectionReason.INSUFFICIENT_FUNDS,
                message="Portfolio state not available"
            )

        # Run all validators
        validators = [
            self._check_daily_limits,
            self._check_position_count,
            self._check_duplicate_position,
            self._check_portfolio_heat,
            self._check_buying_power,
            self._check_confidence,
            self._check_spread,
            self._check_correlated_positions,
        ]

        for validator in validators:
            result = validator(signal, current_price, spread)
            if not result.approved:
                logger.warning(
                    "trade_rejected",
                    symbol=signal.symbol,
                    strategy=signal.strategy,
                    reason=result.rejection_reason.value if result.rejection_reason else "unknown",
                    message=result.message
                )
                return result

        # All checks passed
        risk_metrics = self._calculate_risk_metrics(signal, current_price)

        logger.info(
            "trade_approved",
            symbol=signal.symbol,
            strategy=signal.strategy,
            direction=signal.direction.value,
            confidence=signal.confidence
        )

        return ValidationResult(
            approved=True,
            original_signal=signal,
            adjusted_signal=signal,
            message="All validations passed",
            risk_metrics=risk_metrics
        )

    def _check_daily_limits(
        self,
        signal: Signal,
        current_price: float,
        spread: float
    ) -> ValidationResult:
        """Check daily/weekly loss limits"""
        status = self._limits.get_status()

        if not status.trading_allowed:
            return ValidationResult(
                approved=False,
                original_signal=signal,
                rejection_reason=RejectionReason.DAILY_LIMIT,
                message=status.reason
            )

        # Warning if approaching limit
        if status.daily_limit_remaining < 0.005:  # < 0.5% left
            logger.warning(
                "approaching_daily_limit",
                remaining=status.daily_limit_remaining
            )

        return ValidationResult(approved=True, original_signal=signal)

    def _check_position_count(
        self,
        signal: Signal,
        current_price: float,
        spread: float
    ) -> ValidationResult:
        """Check maximum position count"""
        current_count = len(self._portfolio.positions)

        if current_count >= self.max_positions:
            return ValidationResult(
                approved=False,
                original_signal=signal,
                rejection_reason=RejectionReason.POSITION_LIMIT,
                message=f"Max positions ({self.max_positions}) reached"
            )

        return ValidationResult(approved=True, original_signal=signal)

    def _check_duplicate_position(
        self,
        signal: Signal,
        current_price: float,
        spread: float
    ) -> ValidationResult:
        """Check if already in this position"""
        symbol = signal.symbol

        if symbol in self._portfolio.positions:
            existing = self._portfolio.positions[symbol]
            existing_direction = existing.get('direction', 'long')

            # Can't add to same direction
            if (signal.direction == SignalDirection.LONG and existing_direction == 'long') or \
               (signal.direction == SignalDirection.SHORT and existing_direction == 'short'):
                return ValidationResult(
                    approved=False,
                    original_signal=signal,
                    rejection_reason=RejectionReason.DUPLICATE,
                    message=f"Already {existing_direction} in {symbol}"
                )

        return ValidationResult(approved=True, original_signal=signal)

    def _check_portfolio_heat(
        self,
        signal: Signal,
        current_price: float,
        spread: float
    ) -> ValidationResult:
        """Check total portfolio risk (heat)"""
        # Calculate new trade risk
        if signal.entry_price and signal.stop_loss:
            entry = signal.entry_price
            stop = signal.stop_loss
            risk_per_share = abs(entry - stop)

            # Estimate position size
            sizer = PositionSizer(self._portfolio.equity)
            shares = sizer.calculate(entry, stop)
            trade_risk = shares * risk_per_share
            trade_risk_pct = trade_risk / self._portfolio.equity

            # Check total heat
            current_heat = self._portfolio.open_risk / self._portfolio.equity if self._portfolio.equity > 0 else 0
            new_heat = current_heat + trade_risk_pct

            if new_heat > self.max_portfolio_heat:
                return ValidationResult(
                    approved=False,
                    original_signal=signal,
                    rejection_reason=RejectionReason.HEAT_LIMIT,
                    message=f"Portfolio heat would be {new_heat:.1%} (max: {self.max_portfolio_heat:.1%})"
                )

        return ValidationResult(approved=True, original_signal=signal)

    def _check_buying_power(
        self,
        signal: Signal,
        current_price: float,
        spread: float
    ) -> ValidationResult:
        """Check sufficient buying power"""
        price = current_price or signal.entry_price or 0

        if price <= 0:
            return ValidationResult(approved=True, original_signal=signal)

        # Estimate position cost
        sizer = PositionSizer(self._portfolio.equity)
        entry = signal.entry_price or price
        stop = signal.stop_loss or entry * 0.98
        shares = sizer.calculate(entry, stop)
        position_cost = shares * price

        if position_cost > self._portfolio.buying_power:
            return ValidationResult(
                approved=False,
                original_signal=signal,
                rejection_reason=RejectionReason.INSUFFICIENT_FUNDS,
                message=f"Need ${position_cost:.0f}, have ${self._portfolio.buying_power:.0f}"
            )

        return ValidationResult(approved=True, original_signal=signal)

    def _check_confidence(
        self,
        signal: Signal,
        current_price: float,
        spread: float
    ) -> ValidationResult:
        """Check minimum signal confidence"""
        if signal.confidence < self.min_confidence:
            return ValidationResult(
                approved=False,
                original_signal=signal,
                rejection_reason=RejectionReason.LOW_CONFIDENCE,
                message=f"Confidence {signal.confidence:.1%} below minimum {self.min_confidence:.1%}"
            )

        return ValidationResult(approved=True, original_signal=signal)

    def _check_spread(
        self,
        signal: Signal,
        current_price: float,
        spread: float
    ) -> ValidationResult:
        """Check bid-ask spread isn't too wide"""
        if spread is not None and current_price and current_price > 0:
            spread_pct = (spread / current_price) * 100
            if spread_pct > self.max_spread_pct:
                return ValidationResult(
                    approved=False,
                    original_signal=signal,
                    rejection_reason=RejectionReason.SPREAD_TOO_WIDE,
                    message=f"Spread {spread_pct:.2f}% exceeds max {self.max_spread_pct}%"
                )

        return ValidationResult(approved=True, original_signal=signal)

    def _check_correlated_positions(
        self,
        signal: Signal,
        current_price: float,
        spread: float
    ) -> ValidationResult:
        """Check correlated position limits (simplified sector check)"""
        # Simplified: count positions in similar symbols
        # In production, would use sector/industry data

        symbol = signal.symbol
        same_direction_count = 0

        for pos_symbol, pos_data in self._portfolio.positions.items():
            pos_direction = pos_data.get('direction', 'long')
            signal_is_long = signal.direction == SignalDirection.LONG

            # Count same-direction positions
            if (signal_is_long and pos_direction == 'long') or \
               (not signal_is_long and pos_direction == 'short'):
                same_direction_count += 1

        if same_direction_count >= self.max_correlated * 2:  # Simplified
            return ValidationResult(
                approved=False,
                original_signal=signal,
                rejection_reason=RejectionReason.CORRELATED,
                message=f"Too many same-direction positions ({same_direction_count})"
            )

        return ValidationResult(approved=True, original_signal=signal)

    def _calculate_risk_metrics(
        self,
        signal: Signal,
        current_price: float
    ) -> Dict:
        """Calculate risk metrics for approved trade"""
        metrics = {}

        if signal.entry_price and signal.stop_loss:
            entry = signal.entry_price
            stop = signal.stop_loss

            # Risk per share
            risk_per_share = abs(entry - stop)
            metrics['risk_per_share'] = risk_per_share

            # Position sizing
            sizer = PositionSizer(self._portfolio.equity)
            shares = sizer.calculate(entry, stop)
            metrics['suggested_shares'] = shares

            # Total risk
            total_risk = shares * risk_per_share
            metrics['total_risk'] = total_risk
            metrics['risk_pct'] = total_risk / self._portfolio.equity if self._portfolio.equity > 0 else 0

            # R:R ratio
            if signal.take_profit:
                reward = abs(signal.take_profit - entry)
                metrics['risk_reward'] = reward / risk_per_share if risk_per_share > 0 else 0

        return metrics


# Singleton
_validator: Optional[TradeValidator] = None


def get_validator() -> TradeValidator:
    """Get or create validator singleton"""
    global _validator
    if _validator is None:
        _validator = TradeValidator()
    return _validator
