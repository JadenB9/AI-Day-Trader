"""
Shared fixtures. Everything here is pure Python: no broker, no Claude, no network.
"""
from datetime import datetime, timedelta

import pytest

from src.data.models.market_snapshot import Bar


def make_bars(closes, symbol="TEST", spread=1.0, volume=1000):
    """Build 1-minute bars from a list of closes. High/low sit spread above/below."""
    bars = []
    start = datetime(2026, 1, 5, 9, 30)
    prev = closes[0]
    for i, close in enumerate(closes):
        bars.append(Bar(
            symbol=symbol,
            timestamp=start + timedelta(minutes=i),
            open=prev,
            high=max(prev, close) + spread,
            low=min(prev, close) - spread,
            close=close,
            volume=volume,
        ))
        prev = close
    return bars


@pytest.fixture
def rising_bars():
    return make_bars([100 + i * 0.5 for i in range(40)])


@pytest.fixture
def falling_bars():
    return make_bars([120 - i * 0.5 for i in range(40)])


@pytest.fixture
def flat_bars():
    return make_bars([100.0] * 40)
