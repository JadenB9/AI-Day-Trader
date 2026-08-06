# AI-Day-Trader

An algorithmic day-trading system I built to see how far I could get combining
normal quantitative strategies with an LLM as a second opinion. It scans for
setups, sizes positions against a risk budget, routes orders through Alpaca,
and streams everything to a React dashboard.

> **This is a personal research project, not financial advice.** It can place
> real orders. Trading carries real risk of loss. Point it at Alpaca's paper
> endpoint (the default in `.env.template`) unless you know exactly what you're
> doing, and read `src/risk/` before you change anything. I'm not responsible
> for what it does with your money.

## How it works

A strategy proposes a trade. Before anything is sent, it goes through the risk
layer — position sizing, daily loss limits, stop placement, and a set of
validators that can veto the order outright. When a signal's confidence lands
below the configured threshold, the decision engine asks Claude to review the
setup with current market context instead of firing blind.

```
scanner → strategy → AI review (low-confidence only) → risk checks → broker
                                     ↓
                          event bus → WebSocket → dashboard
```

## Strategies

| Family | Strategies |
|---|---|
| Momentum | `gap_and_go` |
| Scalping | `one_minute_scalp`, `vwap_bounce` |
| Mean reversion | `rsi_reversal`, `bollinger_bounce` |
| HFT | `momentum_burst`, `crypto_scalp` |

Each one subclasses `src/strategies/base.py` and registers itself in
`registry.py`, so adding another is mostly writing the signal logic.

## Risk layer

This is the part I care about most:

- **Position sizing** — risk a fixed fraction of equity per trade
  (`SIZING_RISK_PER_TRADE`), sized off the stop distance rather than a flat
  share count.
- **Daily and weekly loss limits** — trading halts for the period once hit.
- **Portfolio heat** — caps total simultaneous risk exposure across positions.
- **Validators** — a last set of checks that can reject an order before it
  reaches the broker.

## Stack

- **Python** — asyncio throughout, Pydantic settings, SQLAlchemy + aiosqlite
- **Alpaca** (`alpaca-py`) — market data streams and order execution
- **Anthropic** — LLM review of low-confidence signals
- **FastAPI** — REST API + WebSocket event feed
- **React + Vite + Tailwind + Recharts** — the dashboard

## Running it

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.template .env      # add your Alpaca + Anthropic keys
python scripts/test_connections.py   # verify credentials before trading
python scripts/run_trader.py
```

Dashboard:

```bash
cd dashboard && npm install && npm run dev
```

Set `DRY_RUN=true` to run the whole pipeline with order execution disabled —
worth doing first.

## Design notes

`blueprint.md.pdf` is the original architecture document I wrote before
building this. It plans out a larger Interactive Brokers version with options
and futures; what's implemented here is the Alpaca equities/crypto subset.
