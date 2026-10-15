"""
Daily and weekly loss limits management.
Circuit breakers for risk control.
"""
from typing import Optional, Dict
from datetime import datetime, date, timedelta
from dataclasses import dataclass
import structlog

from config.settings import get_settings
from src.core.event_bus import get_event_bus, EventType, Event

logger = structlog.get_logger()
settings = get_settings()


@dataclass
class DailyStats:
    """Daily trading statistics"""
    date: date
    starting_equity: float
    current_equity: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    trades_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    high_water_mark: float = 0.0
    max_drawdown: float = 0.0
    consecutive_losses: int = 0


@dataclass
class LimitStatus:
    """Current limit status"""
    trading_allowed: bool = True
    daily_loss_pct: float = 0.0
    weekly_loss_pct: float = 0.0
    daily_limit_remaining: float = 0.0
    weekly_limit_remaining: float = 0.0
    reason: str = ""


class DailyLimitsManager:
    """
    Manages daily and weekly loss limits.
    Acts as circuit breaker to prevent catastrophic losses.
    """

    def __init__(
        self,
        starting_equity: float,
        max_daily_loss_pct: float = None,
        max_weekly_loss_pct: float = None,
        consecutive_loss_pause: int = None
    ):
        self.starting_equity = starting_equity
        self.max_daily_loss = max_daily_loss_pct or settings.portfolio.max_daily_loss
        self.max_weekly_loss = max_weekly_loss_pct or settings.portfolio.max_weekly_loss
        self.consecutive_loss_pause = consecutive_loss_pause or settings.portfolio.consecutive_loss_pause_days

        self._event_bus = get_event_bus()
        self._today_stats: Optional[DailyStats] = None
        self._weekly_stats: Dict[date, DailyStats] = {}
        self._trading_halted = False
        self._halt_reason = ""
        self._halt_until: Optional[datetime] = None

        # Initialize today
        self._init_day(starting_equity)

    def _init_day(self, equity: float) -> None:
        """Initialize new trading day"""
        today = date.today()

        if self._today_stats is None or self._today_stats.date != today:
            self._today_stats = DailyStats(
                date=today,
                starting_equity=equity,
                current_equity=equity,
                high_water_mark=equity
            )

            # Clean old weekly stats
            week_ago = today - timedelta(days=7)
            self._weekly_stats = {
                d: s for d, s in self._weekly_stats.items()
                if d > week_ago
            }
            self._weekly_stats[today] = self._today_stats

            logger.info(
                "daily_limits_initialized",
                equity=equity,
                max_daily_loss=self.max_daily_loss,
                max_weekly_loss=self.max_weekly_loss
            )

    def update_equity(self, current_equity: float, realized_only: bool = False) -> LimitStatus:
        """
        Update current equity and check limits.

        Args:
            current_equity: Current portfolio equity
            realized_only: If True, only count realized P&L

        Returns:
            Current limit status
        """
        self._init_day(self.starting_equity)

        old_equity = self._today_stats.current_equity
        self._today_stats.current_equity = current_equity

        # Update high water mark
        if current_equity > self._today_stats.high_water_mark:
            self._today_stats.high_water_mark = current_equity

        # Calculate P&L
        daily_pnl = current_equity - self._today_stats.starting_equity
        self._today_stats.realized_pnl = daily_pnl  # Simplified

        # Calculate daily loss %
        daily_loss_pct = 0.0
        if self._today_stats.starting_equity > 0:
            daily_loss_pct = -daily_pnl / self._today_stats.starting_equity
            daily_loss_pct = max(daily_loss_pct, 0)  # Only count losses

        # Calculate weekly loss %
        weekly_pnl = sum(s.realized_pnl for s in self._weekly_stats.values())
        weekly_starting = self._get_week_starting_equity()
        weekly_loss_pct = 0.0
        if weekly_starting > 0:
            weekly_loss_pct = -weekly_pnl / weekly_starting
            weekly_loss_pct = max(weekly_loss_pct, 0)

        # Check limits
        status = self._check_limits(daily_loss_pct, weekly_loss_pct)

        # Log warnings
        if daily_loss_pct >= self.max_daily_loss * 0.75:
            logger.warning(
                "approaching_daily_limit",
                daily_loss_pct=daily_loss_pct,
                limit=self.max_daily_loss
            )

        return status

    def record_trade(self, pnl: float, is_winner: bool) -> LimitStatus:
        """Record a completed trade"""
        self._init_day(self.starting_equity)

        self._today_stats.trades_count += 1

        if is_winner:
            self._today_stats.winning_trades += 1
            self._today_stats.consecutive_losses = 0
        else:
            self._today_stats.losing_trades += 1
            self._today_stats.consecutive_losses += 1

        # Check consecutive losses
        if self._today_stats.consecutive_losses >= 3:
            logger.warning(
                "consecutive_losses",
                count=self._today_stats.consecutive_losses
            )

        # Update equity
        new_equity = self._today_stats.current_equity + pnl
        return self.update_equity(new_equity, realized_only=True)

    def _check_limits(self, daily_loss_pct: float, weekly_loss_pct: float) -> LimitStatus:
        """Check if trading should be halted"""
        status = LimitStatus(
            daily_loss_pct=daily_loss_pct,
            weekly_loss_pct=weekly_loss_pct,
            daily_limit_remaining=self.max_daily_loss - daily_loss_pct,
            weekly_limit_remaining=self.max_weekly_loss - weekly_loss_pct
        )

        # Check halt expiry
        if self._halt_until and datetime.now() > self._halt_until:
            self._trading_halted = False
            self._halt_reason = ""
            self._halt_until = None

        # Check daily limit
        if daily_loss_pct >= self.max_daily_loss:
            self._trading_halted = True
            self._halt_reason = f"Daily loss limit hit: {daily_loss_pct:.2%}"
            status.trading_allowed = False
            status.reason = self._halt_reason

            # Emit event
            asyncio.create_task(self._emit_limit_event(
                EventType.DAILY_LIMIT_HIT,
                daily_loss_pct,
                self.max_daily_loss
            ))

            logger.error(
                "daily_limit_exceeded",
                loss_pct=daily_loss_pct,
                limit=self.max_daily_loss
            )

        # Check weekly limit
        elif weekly_loss_pct >= self.max_weekly_loss:
            self._trading_halted = True
            self._halt_reason = f"Weekly loss limit hit: {weekly_loss_pct:.2%}"
            status.trading_allowed = False
            status.reason = self._halt_reason

            logger.error(
                "weekly_limit_exceeded",
                loss_pct=weekly_loss_pct,
                limit=self.max_weekly_loss
            )

        # Check consecutive losses
        elif self._today_stats and self._today_stats.consecutive_losses >= self.consecutive_loss_pause:
            self._trading_halted = True
            self._halt_reason = f"Consecutive losses: {self._today_stats.consecutive_losses}"
            self._halt_until = datetime.now() + timedelta(hours=2)  # 2 hour cooldown
            status.trading_allowed = False
            status.reason = self._halt_reason

        else:
            status.trading_allowed = not self._trading_halted
            status.reason = self._halt_reason if self._trading_halted else ""

        return status

    async def _emit_limit_event(self, event_type: EventType, current: float, limit: float):
        """Emit limit warning/hit event"""
        await self._event_bus.publish(Event(
            type=event_type,
            data={'current': current, 'limit': limit},
            source="daily_limits"
        ))

    def _get_week_starting_equity(self) -> float:
        """Get equity at start of week"""
        if not self._weekly_stats:
            return self.starting_equity

        earliest = min(self._weekly_stats.keys())
        return self._weekly_stats[earliest].starting_equity

    def can_trade(self) -> bool:
        """Check if trading is currently allowed"""
        return not self._trading_halted

    def force_halt(self, reason: str, duration_hours: int = 24) -> None:
        """Manually halt trading"""
        self._trading_halted = True
        self._halt_reason = reason
        self._halt_until = datetime.now() + timedelta(hours=duration_hours)
        logger.warning("trading_halted", reason=reason, duration=duration_hours)

    def resume_trading(self) -> None:
        """Manually resume trading"""
        self._trading_halted = False
        self._halt_reason = ""
        self._halt_until = None
        logger.info("trading_resumed")

    def get_status(self) -> LimitStatus:
        """Get current limit status"""
        if self._today_stats:
            return self.update_equity(self._today_stats.current_equity)
        return LimitStatus()

    @property
    def today_stats(self) -> Optional[DailyStats]:
        return self._today_stats

    @property
    def is_halted(self) -> bool:
        return self._trading_halted

    @property
    def halt_reason(self) -> str:
        return self._halt_reason


# Need asyncio for event emission
import asyncio

# Singleton
_limits_manager: Optional[DailyLimitsManager] = None


def get_limits_manager(starting_equity: float = None) -> DailyLimitsManager:
    """Get or create limits manager"""
    global _limits_manager
    if _limits_manager is None:
        if starting_equity is None:
            starting_equity = 100000  # Default paper trading
        _limits_manager = DailyLimitsManager(starting_equity)
    return _limits_manager


def init_limits_manager(starting_equity: float) -> DailyLimitsManager:
    """Initialize limits manager with equity"""
    global _limits_manager
    _limits_manager = DailyLimitsManager(starting_equity)
    return _limits_manager
