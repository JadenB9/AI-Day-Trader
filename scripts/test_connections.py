#!/usr/bin/env python3
"""
Test script to verify Alpaca and Claude API connections.
Run this before starting the trading engine.
"""
import sys
from pathlib import Path
import asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import get_settings
from src.utils.connection_test import test_alpaca_connection, test_claude_connection, test_claude_web_search
from src.utils.helpers import get_trading_capital, get_available_capital, is_capital_depleted


async def main():
    settings = get_settings()

    print("\n" + "="*60)
    print("AI DAY TRADER - CONNECTION & CONFIGURATION TEST")
    print("="*60 + "\n")

    # Test connections
    print("1. TESTING API CONNECTIONS")
    print("-" * 40)

    # Alpaca
    print("\n[Alpaca API]")
    alpaca_ok, alpaca_result = await test_alpaca_connection()
    if alpaca_ok:
        print("   Status: CONNECTED")
        print(f"   Mode: {alpaca_result['mode'].upper()}")
        print(f"   Equity: ${alpaca_result['equity']:,.2f}")
        print(f"   Buying Power: ${alpaca_result['buying_power']:,.2f}")
    else:
        print("   Status: FAILED")
        print(f"   Error: {alpaca_result.get('error')}")
        print("\n   Check your ALPACA_API_KEY and ALPACA_SECRET_KEY in .env")

    # Claude
    print("\n[Claude API]")
    claude_ok, claude_result = await test_claude_connection()
    if claude_ok:
        print("   Status: CONNECTED")
        print(f"   Model: {claude_result['model']}")
        print(f"   Response Time: {claude_result['response_time_ms']}ms")
    else:
        print("   Status: FAILED")
        print(f"   Error: {claude_result.get('error')}")
        print("\n   Check your ANTHROPIC_API_KEY in .env")

    # Claude Web Search
    if claude_ok and settings.ai.enable_web_search:
        print("\n[Claude Web Search]")
        web_ok, web_result = await test_claude_web_search()
        if web_ok:
            print("   Status: WORKING")
            print(f"   Response Time: {web_result.get('response_time_ms', 0)}ms")
        else:
            print("   Status: FAILED")
            print(f"   Error: {web_result.get('error')}")

    # Configuration check
    print("\n\n2. CONFIGURATION CHECK")
    print("-" * 40)

    # Capital settings
    if alpaca_ok:
        actual_equity = alpaca_result['equity']
        trading_capital = get_trading_capital(actual_equity)
        available = get_available_capital(actual_equity)
        depleted = is_capital_depleted(actual_equity)

        print("\n[Trading Capital]")
        print(f"   Actual Account Equity: ${actual_equity:,.2f}")
        print(f"   Virtual Capital Limit: ${settings.portfolio.virtual_capital:,.2f}")
        print(f"   Capital Reserve: ${settings.portfolio.capital_reserve:,.2f}")
        print(f"   Available to Trade: ${available:,.2f}")
        print(f"   Capital Depleted: {'YES - CANNOT TRADE' if depleted else 'No'}")

        if settings.portfolio.virtual_capital > 0:
            print("\n   You're using VIRTUAL CAPITAL mode.")
            print(f"   Trading as if you have ${trading_capital:,.2f}, not ${actual_equity:,.2f}")

    # Risk settings
    print("\n[Risk Settings]")
    print(f"   Max Daily Loss: {settings.portfolio.max_daily_loss * 100:.1f}%")
    print(f"   Max Weekly Loss: {settings.portfolio.max_weekly_loss * 100:.1f}%")
    print(f"   Risk Per Trade: {settings.position_sizing.risk_per_trade * 100:.1f}%")
    print(f"   Max Position Size: {settings.position_sizing.max_position_pct * 100:.1f}%")
    print(f"   Max Positions: {settings.portfolio.max_positions}")

    # AI settings
    print("\n[AI Settings]")
    print(f"   Web Search Enabled: {settings.ai.enable_web_search}")
    print(f"   Confidence Threshold: {settings.ai.confidence_threshold * 100:.0f}%")
    print(f"   Decision Cache: {settings.ai.cache_decisions_seconds}s")

    # Features
    print("\n[Features]")
    print(f"   Crypto Trading: {'Enabled' if settings.crypto.enabled else 'Disabled'}")
    print(f"   HFT Mode: {'Enabled' if settings.hft.enabled else 'Disabled'}")
    print(f"   Extended Hours: {'Enabled' if settings.trading_hours.extended_hours_enabled else 'Disabled'}")

    # Summary
    print("\n\n" + "="*60)
    all_ok = alpaca_ok and claude_ok
    if all_ok:
        print("ALL TESTS PASSED - Ready to trade!")
    else:
        print("SOME TESTS FAILED - Fix issues before trading")
    print("="*60 + "\n")

    return all_ok


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
