# AI-Day-Trader

An algorithmic day-trading bot I built to see how far I could get combining
ordinary technical strategies with an LLM as a filter. It pulls 1-minute bars
from Alpaca, runs a set of strategies over them, pushes every signal through a
hard risk layer, routes the survivors to Alpaca as orders, and streams
everything to a React dashboard. Claude is asked once an hour to research the
watchlist with web search; its sentiment is cached and used to veto trades.

> **This is a personal research project, not financial advice.** It can place
> real orders. Trading carries real risk of loss. Keep it on Alpaca's paper
> endpoint (the default), read `src/risk/` before you change anything, and
> don't trust the defaults in `config/settings.py`, which I tuned aggressively
> while experimenting. I'm not responsible for what it does with your money.

## How it works

```
watchlist ─► 1m bars ─► indicators ─► strategies ─► signals
                                                       │
            hourly Claude research (web search) ───► bearish? skip
                                                       │
                     validators ─► position sizer ─► Alpaca order ─► stop manager
                                                       │
                              event bus ─► FastAPI + WebSocket ─► React dashboard
```

`scripts/run_trader.py` is the engine. Every 5 seconds it walks the watchlist,
builds a `MarketSnapshot` per symbol, enriches it with indicators, and asks each
enabled strategy for a signal. A signal becomes an order only if the research
cache for that symbol isn't strongly bearish (85%+ confidence) and every risk
check passes.

The LLM is deliberately kept out of the hot path. `src/ai/market_research.py`
runs once an hour, researches each symbol with Claude plus web search, and
caches a sentiment and confidence. The per-signal review engine in
`src/ai/decision_engine.py` exists but the main loop doesn't call it, so the
hourly research is the only Claude call while trading.

## Strategies

| Family | Strategy | File |
|---|---|---|
| Scalping | `one_minute_scalp` | `src/strategies/scalping/one_minute_scalp.py` |
| Scalping | `vwap_bounce` | `src/strategies/scalping/vwap_bounce.py` |
| Momentum | `gap_and_go` | `src/strategies/momentum/gap_and_go.py` |
| Mean reversion | `bollinger_bounce` | `src/strategies/mean_reversion/bollinger_bounce.py` |
| Mean reversion | `rsi_reversal` | `src/strategies/mean_reversion/rsi_reversal.py` |
| HFT | `momentum_burst` | `src/strategies/hft/momentum_burst.py` |
| HFT | `crypto_scalp` | `src/strategies/hft/crypto_scalp.py` |

The first five are registered at startup by `register_all_strategies()` in
`src/strategies/registry.py`. The two HFT ones are written and have `HFT_*`
settings but aren't wired into the registry yet. Each strategy subclasses
`src/strategies/base.py`, declares the indicators it needs, and returns a
`Signal` with entry, stop and target. Indicators live in `src/indicators/`
(RSI, MACD, stochastic, EMA/SMA, ADX, ATR, Bollinger, VWAP), all plain numpy.

## Risk layer

This is the part I care about most. It lives in `src/risk/` and every order
passes through it, in this order:

1. **Validators** (`validators.py`) can reject a signal outright: trading halted
   by a loss limit, max open positions, already in the same direction on that
   symbol, portfolio heat over the cap, not enough buying power, confidence
   under the floor, bid-ask spread too wide, too many same-direction positions.
2. **Position sizer** (`position_sizer.py`) turns the stop distance into a share
   count. Fixed fractional by default (risk a set fraction of equity per
   trade); Kelly and ATR-based sizing are there too. Hard cap at
   `SIZING_MAX_POSITION_PCT` of equity.
3. **Daily limits** (`daily_limits.py`) halt trading for the day or the week
   once a loss percentage is hit, and pause for two hours after a run of
   consecutive losers.
4. **Stop manager** (`stop_manager.py`) places the initial stop (ATR multiple
   or percentage), trails it in the trade's favour only, can move it to
   breakeven, and enforces a time stop.

On top of that, `PORTFOLIO_VIRTUAL_CAPITAL` lets you tell the bot it only has,
say, $1,000 of a $100k paper account, and `PORTFOLIO_CAPITAL_RESERVE` stops
the engine dead if account equity ever falls to that level.

## Running it (paper trading)

Needs Python 3.11+ and Node 18+ for the dashboard.

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # add your Alpaca paper keys and an Anthropic key
python scripts/test_connections.py   # checks both APIs before anything trades

python scripts/run_trader.py --dry-run     # full pipeline, orders only logged
python scripts/run_trader.py               # paper orders through Alpaca
```

`--single-cycle` runs one pass over the watchlist and exits, `-v` switches to
console logging. `scripts/monitor.py` is a small terminal view of the account.
Leave `ALPACA_BASE_URL` on `https://paper-api.alpaca.markets` unless you really
mean it.

### Dashboard

`./start.sh` creates the venv if needed, installs both sides, starts the API on
`127.0.0.1:8000` and the Vite dev server on `5173`, and opens the browser.
`./stop.sh` tears it down. By hand:

```bash
uvicorn api.main:app --host 127.0.0.1 --port 8000
cd dashboard && npm ci && npm run dev
```

The API has no auth by default and its `/api/system/start` endpoint starts the
trading engine, so it binds to localhost only. Set `DASHBOARD_API_KEY` to
require an `X-API-Key` header if you ever expose it. Swagger docs are at
`/docs`.

## Configuration

Everything is read from `.env` by the Pydantic settings in
`config/settings.py`, grouped by prefix:

| Prefix | What it controls |
|---|---|
| `ALPACA_` | keys, paper vs live base URL, data and stream URLs |
| `ANTHROPIC_` | key, model, max tokens, temperature |
| `PORTFOLIO_` | max positions, portfolio heat, daily and weekly loss limits, virtual capital, reserve |
| `SIZING_` | sizing method, risk per trade, max position size, Kelly fraction |
| `STOP_` | stop method, ATR multiplier, percentage, trailing distance, time stop |
| `AI_` | research and review thresholds, web search on/off, decision cache |
| `SCANNER_` | pre-market gap scanner filters and watchlist size |
| `HOURS_` | extended hours, session times, time zone |
| `CRYPTO_` | 24/7 crypto symbols and their smaller position cap |
| `HFT_` | the 1-second cycle mode (off by default) |
| `DASHBOARD_` | API host and port, CORS origins, optional API key |
| `DB_`, `LOG_` | SQLite URL, log level, format and file |

`.env.example` carries conservative values (2% daily loss, 1% risk per trade,
5% heat). The code defaults are looser, so copy the example rather than
relying on them. Trades, signals, positions and daily summaries are written to
`storage/trades.db` (SQLite via SQLAlchemy + aiosqlite).

## Tests and lint

```bash
pytest                 # risk layer, indicators, AI response parsing, registry
flake8                 # settings in .flake8
cd dashboard && npm run lint && npm run build
```

The tests are pure Python and never touch Alpaca or Claude.

## Layout

```
scripts/run_trader.py   engine and main loop
config/settings.py      every setting, with env prefixes
src/data/               Alpaca clients, streams, market snapshot model, scanner
src/indicators/         technical indicators
src/strategies/         strategy base, registry and the strategies
src/ai/                 Claude client, hourly research, prompt templates
src/risk/               validators, position sizer, daily limits, stops
src/execution/          Alpaca broker wrapper and order manager
src/core/               event bus and exceptions
storage/                SQLAlchemy models and session setup
api/                    FastAPI routers and WebSocket manager
dashboard/              React + Vite + Tailwind + Recharts front end
tests/                  pytest suite
docs/                   design notes
```

## Design notes

`docs/blueprint.pdf` is the architecture document I wrote before building
this. It plans a larger Interactive Brokers version with options and futures;
what's here is the Alpaca equities and crypto subset.
`docs/day-trading-encyclopedia.pdf` is the strategy reference I worked from.

## Stack

Python with asyncio throughout, `alpaca-py`, `anthropic`, Pydantic settings,
SQLAlchemy + aiosqlite, structlog, FastAPI + uvicorn; React 18, Vite,
Tailwind, Recharts, zustand and TanStack Query on the dashboard.
