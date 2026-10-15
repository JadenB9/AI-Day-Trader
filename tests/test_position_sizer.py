from config.settings import get_settings, PositionSizingMethod
from src.risk.position_sizer import PositionSizer, calculate_position_size

settings = get_settings()


def test_fixed_fractional_risks_the_configured_fraction():
    sizer = PositionSizer(equity=10_000, method=PositionSizingMethod.FIXED_FRACTIONAL, risk_per_trade=0.01)
    # $100 at risk, $2 per share -> 50 shares, well under the max position cap
    shares = sizer.calculate(entry_price=50.0, stop_price=48.0)
    assert shares == min(50, int(10_000 * settings.position_sizing.max_position_pct / 50.0))


def test_position_never_exceeds_max_position_pct():
    sizer = PositionSizer(equity=10_000, method=PositionSizingMethod.FIXED_FRACTIONAL, risk_per_trade=0.5)
    shares = sizer.calculate(entry_price=10.0, stop_price=9.99)
    assert shares <= int(10_000 * settings.position_sizing.max_position_pct / 10.0)


def test_missing_stop_falls_back_to_two_percent_risk():
    sizer = PositionSizer(equity=10_000, method=PositionSizingMethod.FIXED_FRACTIONAL, risk_per_trade=0.01)
    with_stop = sizer.calculate(entry_price=100.0, stop_price=98.0)
    without_stop = sizer.calculate(entry_price=100.0, stop_price=100.0)
    assert with_stop == without_stop


def test_zero_or_negative_entry_returns_zero():
    sizer = PositionSizer(equity=10_000)
    assert sizer.calculate(entry_price=0, stop_price=1) == 0
    assert sizer.calculate(entry_price=-5, stop_price=1) == 0


def test_kelly_with_negative_edge_sizes_nothing_beyond_the_one_share_floor():
    sizer = PositionSizer(equity=10_000, method=PositionSizingMethod.KELLY, risk_per_trade=0.01)
    # 30% win rate at 1:1 is a losing game; calculate() still floors at one share when equity covers it
    assert sizer._kelly(50.0, 2.0, win_rate=0.3, avg_win_loss_ratio=1.0) == 0
    assert sizer.calculate(entry_price=50.0, stop_price=48.0, win_rate=0.3, avg_win_loss_ratio=1.0) == 1


def test_kelly_sizes_bigger_with_a_bigger_edge():
    sizer = PositionSizer(equity=100_000, method=PositionSizingMethod.KELLY, risk_per_trade=0.01)
    # a wide stop keeps both under the max position cap so the edge is what differs
    small = sizer.calculate(entry_price=50.0, stop_price=30.0, win_rate=0.52, avg_win_loss_ratio=1.0)
    big = sizer.calculate(entry_price=50.0, stop_price=30.0, win_rate=0.60, avg_win_loss_ratio=1.5)
    assert big > small > 0


def test_risk_metrics_round_trip():
    sizer = PositionSizer(equity=10_000)
    assert sizer.calculate_risk_amount(10, 50.0, 48.0) == 20.0
    assert sizer.calculate_risk_pct(10, 50.0, 48.0) == 20.0 / 10_000


def test_convenience_wrapper_matches_class():
    direct = PositionSizer(10_000, PositionSizingMethod.FIXED_FRACTIONAL).calculate(50.0, 48.0)
    assert calculate_position_size(10_000, 50.0, 48.0, PositionSizingMethod.FIXED_FRACTIONAL) == direct
