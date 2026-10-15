from config.settings import get_settings
from src.utils.helpers import get_trading_capital, get_available_capital, is_capital_depleted

settings = get_settings()


def test_virtual_capital_caps_what_the_bot_thinks_it_has():
    virtual = settings.portfolio.virtual_capital
    if virtual > 0:
        assert get_trading_capital(1_000_000) == virtual
    else:
        assert get_trading_capital(1_000_000) == 1_000_000


def test_reserve_marks_capital_depleted():
    reserve = settings.portfolio.capital_reserve
    if reserve > 0:
        assert is_capital_depleted(reserve)
        assert is_capital_depleted(reserve - 1)
        assert not is_capital_depleted(reserve + 1)
        assert get_available_capital(reserve + 500) == 500
        assert get_available_capital(reserve - 500) == 0
    else:
        assert is_capital_depleted(0)
        assert not is_capital_depleted(1)
