from src.risk.daily_limits import DailyLimitsManager


def test_fresh_day_allows_trading():
    m = DailyLimitsManager(starting_equity=10_000, max_daily_loss_pct=0.02, max_weekly_loss_pct=0.06,
                           consecutive_loss_pause=3)
    status = m.get_status()
    assert status.trading_allowed
    assert status.daily_loss_pct == 0
    assert m.can_trade()


def test_gains_do_not_count_as_losses():
    m = DailyLimitsManager(10_000, 0.02, 0.06, 3)
    status = m.update_equity(10_500)
    assert status.trading_allowed
    assert status.daily_loss_pct == 0
    assert m.today_stats.high_water_mark == 10_500


async def test_daily_loss_limit_halts_trading():
    # async because hitting the limit publishes an event on the running loop
    m = DailyLimitsManager(10_000, 0.02, 0.06, 3)
    status = m.update_equity(9_790)  # down 2.1%
    assert not status.trading_allowed
    assert "Daily loss limit" in status.reason
    assert m.is_halted


def test_small_loss_stays_open():
    m = DailyLimitsManager(10_000, 0.02, 0.06, 3)
    status = m.update_equity(9_900)  # down 1%
    assert status.trading_allowed
    assert status.daily_limit_remaining > 0


def test_consecutive_losses_pause_with_a_cooldown():
    m = DailyLimitsManager(10_000, 0.5, 0.9, consecutive_loss_pause=2)
    m.record_trade(pnl=-10, is_winner=False)
    status = m.record_trade(pnl=-10, is_winner=False)
    assert not status.trading_allowed
    assert "Consecutive losses" in status.reason
    assert m.today_stats.consecutive_losses == 2
    assert m.today_stats.losing_trades == 2


def test_a_win_resets_the_streak():
    m = DailyLimitsManager(10_000, 0.5, 0.9, consecutive_loss_pause=3)
    m.record_trade(-10, False)
    m.record_trade(-10, False)
    m.record_trade(+30, True)
    assert m.today_stats.consecutive_losses == 0
    assert m.today_stats.winning_trades == 1
    assert m.can_trade()


def test_force_halt_and_resume():
    m = DailyLimitsManager(10_000, 0.02, 0.06, 3)
    m.force_halt("manual", duration_hours=1)
    assert m.is_halted
    assert m.halt_reason == "manual"
    assert not m.get_status().trading_allowed
    m.resume_trading()
    assert m.can_trade()
    assert m.get_status().trading_allowed
