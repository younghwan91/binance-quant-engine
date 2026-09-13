# Binance Quant Engine ⚙️

[![CI](https://github.com/younghwan91/binance-quant-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/younghwan91/binance-quant-engine/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/binance-quant-engine.svg)](https://pypi.org/project/binance-quant-engine/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-younghwan--chae-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/younghwan-chae/)

**A strategy-agnostic Binance USDT-M futures backtest & execution engine.** Backtest and live trading run through the *same* strategy code, so a look-ahead bug can't exist in one and not the other — and an [MCP server](#mcp-server-let-an-agent-run-your-backtests) lets any MCP-compatible agent run backtests without writing a line of Python.

Extracted from the infra layer of a real, currently-running Binance USDT-M futures bot — the alpha (strategy, parameters, live P&L) stays private; what's public is the part every retail algo trader rebuilds badly at least once: a backtester that can't cheat, and an execution layer that survives Binance's actual API quirks. The bundled demo strategy is textbook logic (Bollinger squeeze); it exists to exercise the engine end to end, not to make you money.

> This repository supersedes `quantbox-engine`, which is no longer maintained. If you have that repo cloned, switch to this one.

## Why not just write your own backtest loop?

Because the failure modes here are the ones that quietly wreck a real account, not the ones a unit test catches:

| Problem | What usually happens | What this engine does |
|---|---|---|
| Look-ahead bias | A signal computed over a full array accidentally sees future bars | The backtester physically hands the strategy only `close[: t + 1]` each step — there is no future in the array to peek at ([enforced by test](tests/test_backtest.py)) |
| Backtest/live divergence | Backtest logic gets "ported" to the live bot and drifts | One `TradingStrategy` object, same method calls, same order, in both paths |
| Binance tick-size rejection | A price a float-division away from the tick grid gets silently rejected or mispriced | [`round_to_tick`](src/binance_quant_engine/execution/utils.py) snaps every stop/limit/activation price to the symbol's grid before it leaves the process |
| Dead-man's switch | Bot crashes → open position has no stop-loss | SL/TP/trailing stops are placed **on Binance's Algo Order API**, so the exchange — not your process — enforces the exit |

## Quick start

```bash
pip install binance-quant-engine
# or: uv add binance-quant-engine

bqe-backtest --demo      # backtest the bundled demo strategy on synthetic data
```

![Demo backtest run](docs/images/demo-backtest.png)

> ⚠️ The numbers above are from a **demo strategy on synthetic data**. They prove the engine runs; they say nothing about profitability.

## Backtest your own data

```python
from binance_quant_engine.backtest.vectorized import run_backtest
from binance_quant_engine.data.klines import load_csv
from binance_quant_engine.strategy.demo_squeeze import SqueezeStrategy

high, low, close = load_csv("BTCUSDT_1h.csv")   # columns: high,low,close
result = run_backtest(SqueezeStrategy(), high, low, close, fee=0.0004, slippage=0.0002)
print(result.summary())
# {'n_trades': ..., 'total_return': ..., 'win_rate': ..., 'profit_factor': ..., 'max_drawdown': ...}
```

Bring your own strategy by implementing [`TradingStrategy`](src/binance_quant_engine/strategy/protocol.py) — a `typing.Protocol`, no base class required. Wiring it into live execution: [docs/USAGE.md](docs/USAGE.md).

## MCP server — let an agent run your backtests

```bash
pip install "binance-quant-engine[mcp]"
binance-quant-engine-mcp   # stdio MCP server
```

Exposes `run_demo_backtest`, `backtest_csv`, and `describe_strategy_protocol` to any MCP client (Claude Code, Claude Desktop, etc.) — point an agent at a CSV of OHLC data and it can backtest a strategy idea in the same turn, no local Python environment required on the agent's side.

**This is deliberately backtest-only.** Nothing under `execution/` (order placement, cancellation, bracket management) is reachable through the MCP server — there is no tool call that can touch a live Binance order. If you want an agent that also *trades*, that's a decision you wire yourself, explicitly, outside this server.

## Design

| Design choice | How |
|---|---|
| **No-look-ahead by construction** | The backtester hands the strategy `close[:t+1]` (bars completed as of now) every step — there's no future in the array to see. |
| **Backtest = live, same code** | The same `TradingStrategy` object is driven by the backtester and the live bot, in the same call order. No reimplementation gap. |
| **Pluggable strategy** | The engine only ever talks to a strategy through [`TradingStrategy`](src/binance_quant_engine/strategy/protocol.py) (PEP 544). No inheritance required. |
| **Costs are net, not gross** | Taker fee + slippage charged on both entry and exit legs. |
| **Server-side exits** | SL/TP/trailing stops live on Binance's Algo Order API — the exchange enforces them even if your process dies. ([brackets.py](src/binance_quant_engine/execution/brackets.py)) |
| **Tick-safe prices** | Every price sent to the exchange is snapped to the symbol's tick grid first ([utils.py](src/binance_quant_engine/execution/utils.py)) — a category of Binance rejection this engine doesn't have. |

## Structure

**Decide** (strategy) / **measure** (backtest) / **execute** (live) are kept apart and meet only at `TradingStrategy`.

```mermaid
flowchart LR
    subgraph Data["binance_quant_engine/data/"]
        CSV[("OHLCV CSV\nload_csv()")]
        SYN[["synth_ohlcv()\nsynthetic data"]]
        CACHE["cache.py\nmemory + gzip cache"]
    end

    subgraph Decide["binance_quant_engine/strategy/ — decide"]
        PROTO{{"TradingStrategy\n(PEP 544 protocol)"}}
        SQZ["demo_squeeze.py\nSqueezeStrategy"]
        PROTO -.implements.-> SQZ
    end

    CSV --> BT
    SYN --> BT
    CACHE -.caches.-> CSV

    subgraph Measure["binance_quant_engine/backtest/ — measure"]
        BT["vectorized.run_backtest()\nhands close[:t+1] only\n(no look-ahead)"]
        RES["BacktestResult\ntrades · equity curve · MDD"]
        BT --> RES
    end

    BT <-->|"update_market_data / on_bar\nopen·update·close_position"| PROTO

    subgraph Execute["binance_quant_engine/execution/ — execute (.[live])"]
        HOST["host.py\nScalperProtocol (live bot host)"]
        BRACKET["brackets.py\nBracketMixin — SL/TP/trailing"]
        UTIL["utils.py\nround_to_tick · dead-status set"]
        ALGO["algo_api.py\nAlgoApiClient"]
        HOST --> BRACKET --> ALGO
        BRACKET -.-> UTIL
    end

    subgraph MCP["binance_quant_engine/mcp/ — optional (.[mcp])"]
        SRV["server.py\nrun_demo_backtest · backtest_csv"]
    end
    BT -.callable via.-> SRV

    PROTO ==same interface\n(backtest = live)==> HOST
    ALGO --> BINANCE[("Binance USDT-M\nFutures Algo Order API")]
```

- How to plug in a strategy and wire up live execution → [docs/USAGE.md](docs/USAGE.md)
- Design rationale for no-look-ahead, backtest/live parity, and the cost model → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## License

MIT

---

Bugs and questions → [Issues](https://github.com/younghwan91/binance-quant-engine/issues).

**Younghwan Chae** · [GitHub @younghwan91](https://github.com/younghwan91) · [LinkedIn](https://www.linkedin.com/in/younghwan-chae/) — other open-source quant projects (Korean equities, US equities, crypto) are on the [profile page](https://github.com/younghwan91).
