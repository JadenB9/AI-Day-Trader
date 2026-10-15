"""
Position sizing module.
Determines appropriate position size based on risk parameters.
"""
import structlog

from config.settings import get_settings, PositionSizingMethod

logger = structlog.get_logger()
settings = get_settings()


class PositionSizer:
    """
    Calculate position sizes based on various methods:
    - Fixed Fractional: Risk fixed % of equity per trade
    - Kelly Criterion: Optimal sizing based on edge
    - ATR-Based: Size based on volatility
    """

    def __init__(
        self,
        equity: float,
        method: PositionSizingMethod = None,
        risk_per_trade: float = None
    ):
        self.equity = equity
        self.method = method or settings.position_sizing.method
        self.risk_per_trade = risk_per_trade or settings.position_sizing.risk_per_trade
        self.max_position_pct = settings.position_sizing.max_position_pct
        self.kelly_fraction = settings.position_sizing.kelly_fraction

    def calculate(
        self,
        entry_price: float,
        stop_price: float,
        win_rate: float = 0.55,
        avg_win_loss_ratio: float = 1.5,
        atr: float = None
    ) -> int:
        """
        Calculate position size (number of shares).

        Args:
            entry_price: Planned entry price
            stop_price: Stop loss price
            win_rate: Historical win rate (for Kelly)
            avg_win_loss_ratio: Average win / average loss (for Kelly)
            atr: ATR value (for ATR-based sizing)

        Returns:
            Number of shares to trade
        """
        if entry_price <= 0:
            return 0

        # Calculate risk per share
        risk_per_share = abs(entry_price - stop_price)
        if risk_per_share <= 0:
            risk_per_share = entry_price * 0.02  # Default 2% if no stop

        # Calculate based on method
        if self.method == PositionSizingMethod.FIXED_FRACTIONAL:
            shares = self._fixed_fractional(entry_price, risk_per_share)
        elif self.method == PositionSizingMethod.KELLY:
            shares = self._kelly(entry_price, risk_per_share, win_rate, avg_win_loss_ratio)
        elif self.method == PositionSizingMethod.ATR_BASED:
            if atr is None:
                atr = risk_per_share  # Fallback
            shares = self._atr_based(entry_price, atr)
        else:
            shares = self._fixed_fractional(entry_price, risk_per_share)

        # Apply max position constraint
        max_shares = int((self.equity * self.max_position_pct) / entry_price)
        shares = min(shares, max_shares)

        # Ensure at least 1 share if we have enough equity
        if shares <= 0 and self.equity > entry_price:
            shares = 1

        logger.debug(
            "position_size_calculated",
            method=self.method.value,
            shares=shares,
            entry=entry_price,
            risk_per_share=risk_per_share
        )

        return shares

    def _fixed_fractional(self, entry_price: float, risk_per_share: float) -> int:
        """
        Fixed fractional position sizing.
        Risk a fixed percentage of equity on each trade.
        """
        # Dollar amount at risk
        risk_amount = self.equity * self.risk_per_trade

        # Shares = Risk Amount / Risk per Share
        shares = int(risk_amount / risk_per_share)
        return max(shares, 0)

    def _kelly(
        self,
        entry_price: float,
        risk_per_share: float,
        win_rate: float,
        avg_win_loss_ratio: float
    ) -> int:
        """
        Kelly Criterion position sizing.
        Optimal sizing based on edge.

        Kelly % = W - (1-W)/R
        where W = win rate, R = avg win/loss ratio

        Uses fractional Kelly (quarter Kelly by default) to reduce variance.
        """
        if win_rate <= 0 or win_rate >= 1 or avg_win_loss_ratio <= 0:
            return self._fixed_fractional(entry_price, risk_per_share)

        # Kelly formula
        kelly_pct = win_rate - ((1 - win_rate) / avg_win_loss_ratio)

        # If negative edge, don't trade
        if kelly_pct <= 0:
            return 0

        # Apply Kelly fraction (e.g., quarter Kelly)
        kelly_pct *= self.kelly_fraction

        # Cap at risk per trade
        kelly_pct = min(kelly_pct, self.risk_per_trade * 3)  # Max 3x normal risk

        # Calculate shares
        risk_amount = self.equity * kelly_pct
        shares = int(risk_amount / risk_per_share)

        return max(shares, 0)

    def _atr_based(self, entry_price: float, atr: float) -> int:
        """
        ATR-based position sizing.
        Size inversely proportional to volatility.
        """
        if atr <= 0:
            return self._fixed_fractional(entry_price, entry_price * 0.02)

        # Risk amount
        risk_amount = self.equity * self.risk_per_trade

        # ATR multiplier (e.g., risk = 2 ATR)
        atr_mult = settings.stops.atr_multiplier
        risk_per_share = atr * atr_mult

        shares = int(risk_amount / risk_per_share)
        return max(shares, 0)

    def calculate_risk_amount(self, shares: int, entry_price: float, stop_price: float) -> float:
        """Calculate dollar risk for a position"""
        risk_per_share = abs(entry_price - stop_price)
        return shares * risk_per_share

    def calculate_risk_pct(self, shares: int, entry_price: float, stop_price: float) -> float:
        """Calculate risk as percentage of equity"""
        risk_amount = self.calculate_risk_amount(shares, entry_price, stop_price)
        return risk_amount / self.equity if self.equity > 0 else 0

    def update_equity(self, new_equity: float) -> None:
        """Update equity for position sizing calculations"""
        self.equity = new_equity


def calculate_position_size(
    equity: float,
    entry_price: float,
    stop_price: float,
    method: PositionSizingMethod = None,
    **kwargs
) -> int:
    """Convenience function for position sizing"""
    sizer = PositionSizer(equity, method)
    return sizer.calculate(entry_price, stop_price, **kwargs)
