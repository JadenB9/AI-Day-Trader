#!/usr/bin/env python3
"""
Test script to verify your setup is working.
Run this before starting the trader.
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import get_settings


def test_settings():
    """Test configuration loading"""
    print("1. Testing configuration...")
    settings = get_settings()

    # Check Alpaca
    if not settings.alpaca.api_key or settings.alpaca.api_key == "your_alpaca_api_key":
        print("   ❌ Alpaca API key not set in .env")
        return False
    print("   ✓ Alpaca API key found")

    # Check Anthropic
    if not settings.anthropic.api_key or settings.anthropic.api_key == "your_anthropic_api_key":
        print("   ❌ Anthropic API key not set in .env")
        return False
    print("   ✓ Anthropic API key found")

    return True


async def test_alpaca():
    """Test Alpaca connection"""
    print("\n2. Testing Alpaca connection...")
    try:
        from src.execution.alpaca_broker import get_broker
        broker = get_broker()
        account = await broker.get_account()
        print(f"   ✓ Connected to Alpaca")
        print(f"   ✓ Account equity: ${account['equity']:,.2f}")
        print(f"   ✓ Buying power: ${account['buying_power']:,.2f}")
        return True
    except Exception as e:
        print(f"   ❌ Alpaca connection failed: {e}")
        return False


async def test_data():
    """Test market data"""
    print("\n3. Testing market data...")
    try:
        from src.data.historical.alpaca_client import get_historical_client
        client = get_historical_client()
        quote = await client.get_latest_quote("SPY")
        if quote:
            print(f"   ✓ Got SPY quote: ${quote.bid:.2f} / ${quote.ask:.2f}")
            return True
        else:
            print("   ⚠️  No quote data (market may be closed)")
            return True  # OK if market closed
    except Exception as e:
        print(f"   ❌ Data fetch failed: {e}")
        return False


def test_anthropic():
    """Test Anthropic API key format"""
    print("\n4. Testing Anthropic API key...")
    settings = get_settings()
    key = settings.anthropic.api_key
    if key.startswith("sk-ant-"):
        print("   ✓ Anthropic API key format looks valid")
        return True
    else:
        print("   ⚠️  Anthropic key should start with 'sk-ant-'")
        return False


async def main():
    print("=" * 50)
    print("  AI DAY TRADER - SETUP TEST")
    print("=" * 50)
    print()

    results = []

    # Test settings
    results.append(test_settings())

    if results[-1]:
        # Test Alpaca
        results.append(await test_alpaca())

        # Test data
        results.append(await test_data())

        # Test Anthropic
        results.append(test_anthropic())

    print("\n" + "=" * 50)
    if all(results):
        print("  ✅ ALL TESTS PASSED - Ready to trade!")
        print()
        print("  Next steps:")
        print("  1. Run: python scripts/run_trader.py --dry-run --verbose")
        print("  2. Monitor: python scripts/monitor.py")
    else:
        print("  ❌ SOME TESTS FAILED")
        print()
        print("  Fix your .env file and try again")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
