"""
Stop loss management.
Handles initial stops, trailing stops, and time-based stops.
"""
from typing import Optional, Dict
from datetime import datetime, timedelta
from enum import Enum
import structlog

from config.settings import get_settings, StopMethod
from src.strategies.base import SignalDirection

logger = structlog.get_logger()
settings = get_settings()


class StopType(str, Enum):
    INITIAL = "initial"
    TRAILING = "trailing"
    TIME = "time"
    BREAKEVEN = "breakeven"


class StopManager:
    """
    Manages stop losses for positions.
    Supports ATR-based, percentage, and trailing stops.
    """

    def __init__(
        self,
        method: StopMethod = None,
        atr_multiplier: float = None,
        percentage: float = None,
        trailing_pct: float = None,
        time_stop_minutes: int = None
    ):
        self.method = method or settings.stops.method
        self.atr_multiplier = atr_multiplier or settings.stops.atr_multiplier
        self.percentage = percentage or settings.stops.percentage
        self.trailing_pct = trailing_pct or settings.stops.trailing_pct
        self.time_stop_minutes = time_stop_minutes or settings.stops.time_stop_minutes

        # Track positions
        self._positions: Dict[str, Dict] = {}  # symbol -> position data

    def calculate_initial_stop(
        self,
        entry_price: float,
        direction: SignalDirection,
        atr: float = None
    ) -> float:
        """
        Calculate initial stop loss price.

        Args:
            entry_price: Entry price
            direction: LONG or SHORT
            atr: ATR value (required for ATR method)

        Returns:
            Stop loss price
        """
        if self.method == StopMethod.ATR_BASED:
            if atr is None:
                raise ValueError("ATR required for ATR-based stops")
            stop_distance = atr * self.atr_multiplier
        elif self.method == StopMethod.PERCENTAGE:
            stop_distance = entry_price * self.percentage
        else:
            stop_distance = entry_price * self.percentage

        if direction == SignalDirection.LONG:
            return entry_price - stop_distance
        else:
            return entry_price + stop_distance

    def register_position(
        self,
        symbol: str,
        entry_price: float,
        direction: SignalDirection,
        stop_price: float,
        entry_time: datetime = None
    ) -> None:
        """Register a new position for stop management"""
        self._positions[symbol] = {
            'entry_price': entry_price,
            'direction': direction,
            'initial_stop': stop_price,
            'current_stop': stop_price,
            'highest_price': entry_price if direction == SignalDirection.LONG else None,
            'lowest_price': entry_price if direction == SignalDirection.SHORT else None,
            'entry_time': entry_time or datetime.now(),
            'stop_type': StopType.INITIAL,
            'at_breakeven': False
        }

    def update(self, symbol: str, current_price: float) -> Optional[float]:
        """
        Update stop for a position based on current price.
        Returns new stop price if updated, None otherwise.
        """
        if symbol not in self._positions:
            return None

        pos = self._positions[symbol]
        direction = pos['direction']
        old_stop = pos['current_stop']

        # Update highest/lowest tracking
        if direction == SignalDirection.LONG:
            if current_price > (pos['highest_price'] or 0):
                pos['highest_price'] = current_price
        else:
            if pos['lowest_price'] is None or current_price < pos['lowest_price']:
                pos['lowest_price'] = current_price

        # Apply trailing stop
        new_stop = self._calculate_trailing_stop(pos, current_price)

        if new_stop != old_stop:
            pos['current_stop'] = new_stop
            pos['stop_type'] = StopType.TRAILING
            logger.info(
                "stop_updated",
                symbol=symbol,
                old_stop=old_stop,
                new_stop=new_stop,
                reason="trailing"
            )
            return new_stop

        return None

    def _calculate_trailing_stop(self, pos: Dict, current_price: float) -> float:
        """Calculate trailing stop level"""
        direction = pos['direction']
        current_stop = pos['current_stop']

        if direction == SignalDirection.LONG:
            # Trail below highest price
            highest = pos['highest_price']
            trail_distance = highest * self.trailing_pct
            trailing_stop = highest - trail_distance

            # Only move stop up, never down
            return max(trailing_stop, current_stop)

        else:  # SHORT
            # Trail above lowest price
            lowest = pos['lowest_price']
            trail_distance = lowest * self.trailing_pct
            trailing_stop = lowest + trail_distance

            # Only move stop down, never up
            return min(trailing_stop, current_stop)

    def move_to_breakeven(self, symbol: str, buffer_pct: float = 0.001) -> Optional[float]:
        """
        Move stop to breakeven (entry price).
        Add small buffer to cover commissions.
        """
        if symbol not in self._positions:
            return None

        pos = self._positions[symbol]
        if pos['at_breakeven']:
            return None

        entry = pos['entry_price']
        direction = pos['direction']

        if direction == SignalDirection.LONG:
            breakeven_stop = entry * (1 + buffer_pct)
        else:
            breakeven_stop = entry * (1 - buffer_pct)

        pos['current_stop'] = breakeven_stop
        pos['at_breakeven'] = True
        pos['stop_type'] = StopType.BREAKEVEN

        logger.info("stop_moved_breakeven", symbol=symbol, stop=breakeven_stop)
        return breakeven_stop

    def should_stop_out(self, symbol: str, current_price: float) -> bool:
        """Check if position should be stopped out"""
        if symbol not in self._positions:
            return False

        pos = self._positions[symbol]
        direction = pos['direction']
        stop_price = pos['current_stop']

        if direction == SignalDirection.LONG:
            return current_price <= stop_price
        else:
            return current_price >= stop_price

    def check_time_stop(self, symbol: str) -> bool:
        """Check if time-based stop has triggered"""
        if symbol not in self._positions:
            return False

        pos = self._positions[symbol]
        entry_time = pos['entry_time']
        max_duration = timedelta(minutes=self.time_stop_minutes)

        return datetime.now() > entry_time + max_duration

    def get_stop(self, symbol: str) -> Optional[float]:
        """Get current stop price for symbol"""
        if symbol in self._positions:
            return self._positions[symbol]['current_stop']
        return None

    def get_position_data(self, symbol: str) -> Optional[Dict]:
        """Get full position data"""
        return self._positions.get(symbol)

    def remove_position(self, symbol: str) -> None:
        """Remove position from tracking"""
        self._positions.pop(symbol, None)

    @property
    def tracked_symbols(self) -> list:
        """Get list of tracked symbols"""
        return list(self._positions.keys())


# Singleton instance
_stop_manager: Optional[StopManager] = None


def get_stop_manager() -> StopManager:
    """Get or create stop manager singleton"""
    global _stop_manager
    if _stop_manager is None:
        _stop_manager = StopManager()
    return _stop_manager
