from config.settings import get_settings
from src.risk.daily_limits import DailyLimitsManager
from src.risk.validators import TradeValidator, PortfolioState, RejectionReason
from src.strategies.base import Signal, SignalDirection, SignalType

settings = get_settings()


def make_signal(symbol="AAPL", direction=SignalDirection.LONG, confidence=0.8,
                entry=100.0, stop=98.0, target=106.0):
    return Signal(symbol=symbol, direction=direction, signal_type=SignalType.ENTRY,
                  strategy="test", confidence=confidence, entry_price=entry,
                  stop_loss=stop, take_profit=target)


def make_validator(positions=None, equity=100_000, buying_power=None, open_risk=0.0):
    state = PortfolioState(
        equity=equity,
        cash=equity,
        buying_power=equity if buying_power is None else buying_power,
        positions=positions or {},
        daily_pnl=0,
        open_risk=open_risk,
    )
    limits = DailyLimitsManager(equity, max_daily_loss_pct=0.5, max_weekly_loss_pct=0.9,
                                consecutive_loss_pause=100)
    return TradeValidator(state, limits)


def test_clean_signal_is_approved_with_risk_metrics():
    result = make_validator().validate(make_signal(), current_price=100.0)
    assert result.approved
    assert result.rejection_reason is None
    assert result.risk_metrics["risk_per_share"] == 2.0
    assert result.risk_metrics["suggested_shares"] > 0
    assert result.risk_metrics["risk_reward"] == 3.0


def test_no_portfolio_state_rejects():
    v = TradeValidator(None, DailyLimitsManager(1_000))
    result = v.validate(make_signal())
    assert not result.approved


def test_halted_limits_reject_everything():
    v = make_validator()
    v._limits.force_halt("test halt")
    result = v.validate(make_signal())
    assert not result.approved
    assert result.rejection_reason == RejectionReason.DAILY_LIMIT


def test_max_positions_rejects():
    positions = {f"SYM{i}": {"direction": "long"} for i in range(settings.portfolio.max_positions)}
    result = make_validator(positions).validate(make_signal("NEW"))
    assert not result.approved
    assert result.rejection_reason == RejectionReason.POSITION_LIMIT


def test_duplicate_direction_rejects_but_opposite_is_fine():
    v = make_validator({"AAPL": {"direction": "long"}})
    same = v.validate(make_signal("AAPL", SignalDirection.LONG))
    assert same.rejection_reason == RejectionReason.DUPLICATE
    opposite = v.validate(make_signal("AAPL", SignalDirection.SHORT, entry=100.0, stop=102.0, target=94.0))
    assert opposite.approved


def test_portfolio_heat_rejects_when_already_maxed():
    equity = 100_000
    v = make_validator(equity=equity, open_risk=equity * settings.portfolio.max_portfolio_heat)
    result = v.validate(make_signal())
    assert not result.approved
    assert result.rejection_reason == RejectionReason.HEAT_LIMIT


def test_insufficient_buying_power_rejects():
    result = make_validator(buying_power=50.0).validate(make_signal(), current_price=100.0)
    assert not result.approved
    assert result.rejection_reason == RejectionReason.INSUFFICIENT_FUNDS


def test_low_confidence_rejects():
    result = make_validator().validate(make_signal(confidence=0.1))
    assert not result.approved
    assert result.rejection_reason == RejectionReason.LOW_CONFIDENCE


def test_wide_spread_rejects():
    v = make_validator()
    result = v.validate(make_signal(), current_price=100.0, spread=100.0 * (v.max_spread_pct + 1) / 100)
    assert not result.approved
    assert result.rejection_reason == RejectionReason.SPREAD_TOO_WIDE
