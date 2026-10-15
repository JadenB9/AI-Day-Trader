import pytest

from src.indicators.momentum.rsi import RSI
from src.indicators.trend.ema import EMA, SMA, EMACrossover
from src.indicators.volatility.atr import ATR
from tests.conftest import make_bars


def test_rsi_needs_period_plus_one_bars(rising_bars):
    rsi = RSI(14)
    assert rsi.calculate(rising_bars[:14]) is None
    assert rsi.calculate(rising_bars[:15]) is not None


def test_rsi_is_100_on_a_straight_climb_and_0_on_a_straight_fall(rising_bars, falling_bars):
    assert RSI(14).calculate(rising_bars) == 100.0
    assert RSI(14).calculate(falling_bars) == pytest.approx(0.0)


def test_rsi_interpretation_bands():
    assert RSI.interpret(85) == "extremely_overbought"
    assert RSI.interpret(72) == "overbought"
    assert RSI.interpret(50) == "neutral"
    assert RSI.interpret(25) == "oversold"
    assert RSI.interpret(10) == "extremely_oversold"


def test_sma_and_ema_on_flat_prices_equal_the_price(flat_bars):
    assert SMA(10).calculate(flat_bars) == pytest.approx(100.0)
    assert EMA(10).calculate(flat_bars) == pytest.approx(100.0)


def test_ema_lags_below_price_in_an_uptrend(rising_bars):
    ema = EMA(10).calculate(rising_bars)
    assert ema is not None
    assert ema < rising_bars[-1].close
    assert ema > rising_bars[-10].close


def test_ema_crossover_detects_a_bullish_cross():
    # a slide, then a sharp climb: the fast EMA starts under the slow one and crosses above it
    bars = make_bars([120 - i * 0.7 for i in range(30)] + [100 + i * 2 for i in range(1, 20)])
    cross = EMACrossover(fast=3, slow=9)
    results = [cross.calculate(bars[:i]) for i in range(10, len(bars) + 1)]
    assert "bullish_cross" in results
    assert results[-1] == "above"


def test_atr_matches_hand_calculation(flat_bars):
    # every bar: high = close + 1, low = close - 1, close = prev close -> true range is 2
    assert ATR(14).calculate(flat_bars) == pytest.approx(2.0)


def test_atr_needs_period_plus_one_bars(flat_bars):
    assert ATR(14).calculate(flat_bars[:14]) is None
