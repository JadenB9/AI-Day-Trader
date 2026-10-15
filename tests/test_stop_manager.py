from datetime import datetime, timedelta

import pytest

from config.settings import StopMethod
from src.risk.stop_manager import StopManager, StopType
from src.strategies.base import SignalDirection


def test_atr_stop_sits_below_entry_for_longs_and_above_for_shorts():
    sm = StopManager(method=StopMethod.ATR_BASED, atr_multiplier=2.0)
    assert sm.calculate_initial_stop(100.0, SignalDirection.LONG, atr=1.5) == 97.0
    assert sm.calculate_initial_stop(100.0, SignalDirection.SHORT, atr=1.5) == 103.0


def test_atr_stop_needs_an_atr():
    sm = StopManager(method=StopMethod.ATR_BASED)
    with pytest.raises(ValueError):
        sm.calculate_initial_stop(100.0, SignalDirection.LONG)


def test_percentage_stop():
    sm = StopManager(method=StopMethod.PERCENTAGE, percentage=0.02)
    assert sm.calculate_initial_stop(100.0, SignalDirection.LONG) == pytest.approx(98.0)


def test_trailing_stop_only_moves_in_the_position_favour():
    sm = StopManager(trailing_pct=0.01)
    sm.register_position("AAPL", entry_price=100.0, direction=SignalDirection.LONG, stop_price=98.0)

    # price runs up: stop trails 1% under the high
    assert sm.update("AAPL", 110.0) == pytest.approx(108.9)
    # price pulls back: stop stays put
    assert sm.update("AAPL", 105.0) is None
    assert sm.get_stop("AAPL") == pytest.approx(108.9)
    assert sm.get_position_data("AAPL")["stop_type"] == StopType.TRAILING


def test_short_trailing_stop_moves_down_only():
    sm = StopManager(trailing_pct=0.01)
    sm.register_position("TSLA", entry_price=100.0, direction=SignalDirection.SHORT, stop_price=102.0)
    assert sm.update("TSLA", 90.0) == pytest.approx(90.9)
    assert sm.update("TSLA", 95.0) is None


def test_should_stop_out():
    sm = StopManager()
    sm.register_position("AAPL", 100.0, SignalDirection.LONG, 98.0)
    sm.register_position("TSLA", 100.0, SignalDirection.SHORT, 102.0)
    assert sm.should_stop_out("AAPL", 97.9)
    assert not sm.should_stop_out("AAPL", 98.1)
    assert sm.should_stop_out("TSLA", 102.5)
    assert not sm.should_stop_out("TSLA", 101.0)
    assert not sm.should_stop_out("NOPE", 1.0)


def test_breakeven_moves_once():
    sm = StopManager()
    sm.register_position("AAPL", 100.0, SignalDirection.LONG, 98.0)
    assert sm.move_to_breakeven("AAPL", buffer_pct=0.001) == pytest.approx(100.1)
    assert sm.move_to_breakeven("AAPL") is None
    assert sm.get_position_data("AAPL")["stop_type"] == StopType.BREAKEVEN


def test_time_stop():
    sm = StopManager(time_stop_minutes=15)
    sm.register_position("AAPL", 100.0, SignalDirection.LONG, 98.0,
                         entry_time=datetime.now() - timedelta(minutes=16))
    sm.register_position("MSFT", 100.0, SignalDirection.LONG, 98.0)
    assert sm.check_time_stop("AAPL")
    assert not sm.check_time_stop("MSFT")


def test_remove_position():
    sm = StopManager()
    sm.register_position("AAPL", 100.0, SignalDirection.LONG, 98.0)
    sm.remove_position("AAPL")
    assert sm.tracked_symbols == []
    assert sm.get_stop("AAPL") is None
