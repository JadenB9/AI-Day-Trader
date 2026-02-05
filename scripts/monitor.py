#!/usr/bin/env python3
"""
Simple monitoring dashboard for the trading system.
Shows real-time stats, positions, and recent activity.
"""
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, '/Users/jaden/Library/Mobile Documents/com~apple~CloudDocs/Projects/AI-Day-Trader')

from config.settings import get_settings
from src.execution.alpaca_broker import get_broker
from src.utils.helpers import is_market_open, is_premarket, is_regular_hours, get_eastern_time

settings = get_settings()


def clear_screen():
    os.system('clear' if os.name == 'posix' else 'cls')


async def show_dashboard():
    """Display trading dashboard"""
    broker = get_broker()

    while True:
        try:
            clear_screen()

            # Header
            now = get_eastern_time()
            print("=" * 60)
            print("        AI DAY TRADER - MONITORING DASHBOARD")
            print("=" * 60)
            print(f"  Time (ET): {now.strftime('%Y-%m-%d %H:%M:%S')}")

            # Market status
            if is_premarket():
                status = "🟡 PRE-MARKET"
            elif is_regular_hours():
                status = "🟢 MARKET OPEN"
            elif is_market_open(extended_hours=True):
                status = "🟠 AFTER-HOURS"
            else:
                status = "🔴 MARKET CLOSED"
            print(f"  Market: {status}")
            print("-" * 60)

            # Account info
            try:
                account = await broker.get_account()
                print("\n📊 ACCOUNT")
                print(f"  Equity:       ${account['equity']:>12,.2f}")
                print(f"  Cash:         ${account['cash']:>12,.2f}")
                print(f"  Buying Power: ${account['buying_power']:>12,.2f}")
                print(f"  Day Trades:   {account['day_trade_count']}/3")
            except Exception as e:
                print(f"\n⚠️  Could not fetch account: {e}")

            # Positions
            print("\n📈 OPEN POSITIONS")
            print("-" * 60)
            try:
                positions = await broker.get_positions()
                if positions:
                    print(f"  {'Symbol':<8} {'Qty':>6} {'Entry':>10} {'Current':>10} {'P&L':>12} {'%':>8}")
                    print("  " + "-" * 56)
                    total_pnl = 0
                    for sym, pos in positions.items():
                        pnl = pos['unrealized_pl']
                        pnl_pct = pos['unrealized_plpc'] * 100
                        total_pnl += pnl
                        pnl_color = "+" if pnl >= 0 else ""
                        print(f"  {sym:<8} {pos['qty']:>6} ${pos['avg_entry_price']:>9.2f} ${pos['current_price']:>9.2f} {pnl_color}${pnl:>10.2f} {pnl_color}{pnl_pct:>7.2f}%")
                    print("  " + "-" * 56)
                    print(f"  {'TOTAL':<8} {'':<6} {'':<10} {'':<10} ${total_pnl:>11.2f}")
                else:
                    print("  No open positions")
            except Exception as e:
                print(f"  ⚠️  Could not fetch positions: {e}")

            # Open orders
            print("\n📋 OPEN ORDERS")
            print("-" * 60)
            try:
                orders = await broker.get_open_orders()
                if orders:
                    for order in orders[:5]:
                        print(f"  {order['symbol']:<8} {order['side']:<5} {order['qty']:>5} @ {order.get('limit_price', 'MKT')}")
                else:
                    print("  No open orders")
            except Exception as e:
                print(f"  ⚠️  Could not fetch orders: {e}")

            # Footer
            print("\n" + "=" * 60)
            print("  Press Ctrl+C to exit | Refreshes every 2 seconds")
            print("=" * 60)

            await asyncio.sleep(2)

        except KeyboardInterrupt:
            print("\n\nMonitoring stopped.")
            break
        except Exception as e:
            print(f"\nError: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    print("Starting monitoring dashboard...")
    print("(Make sure your .env file has valid Alpaca API keys)\n")
    asyncio.run(show_dashboard())
