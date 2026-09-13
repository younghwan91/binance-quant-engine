"""MCP stdio server exposing the backtest engine to any MCP-compatible agent.

Deliberately backtest-only. This process never touches an exchange account —
there is no tool here that can place, modify, or cancel a live order. An
agent can explore the engine's demo strategy, run its own parameter sweeps,
and backtest its own OHLC data, but "let an LLM trade my account" is not a
capability this server offers. Live execution (:mod:`binance_quant_engine.execution`)
is a library you wire into your own bot; it is intentionally not MCP-reachable.
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import replace
from typing import Any

from mcp.server.mcpserver import MCPServer

from binance_quant_engine.backtest.vectorized import run_backtest
from binance_quant_engine.data.klines import synth_ohlcv
from binance_quant_engine.strategy.demo_squeeze import SqueezeConfig, SqueezeStrategy

mcp = MCPServer("binance-quant-engine")


def _finite(x: float) -> float:
    """JSON has no representation for inf/nan; MCP transport is JSON."""
    return x if math.isfinite(x) else 0.0


def _summary_json(result: Any) -> dict[str, float]:
    return {k: _finite(float(v)) for k, v in result.summary().items()}


@mcp.tool()
def run_demo_backtest(
    n_bars: int = 2000,
    seed: int = 7,
    bb_period: int = 20,
    bb_std: float = 2.0,
    squeeze_pct: float = 0.25,
    stop_loss: float = 0.02,
    take_profit: float = 0.04,
) -> dict[str, Any]:
    """Backtest the bundled Bollinger-squeeze demo strategy on synthetic OHLC.

    Zero setup, no API keys, no data file — useful for confirming the engine
    works and for exploring how the demo strategy's parameters move its
    metrics. Not a real alpha; see the README before reading any number here
    as investment advice.
    """
    high, low, close = synth_ohlcv(n=n_bars, seed=seed)
    config = SqueezeConfig(
        bb_period=bb_period,
        bb_std=bb_std,
        squeeze_pct=squeeze_pct,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    result = run_backtest(SqueezeStrategy(config), high, low, close)
    return {"summary": _summary_json(result), "config": config.__dict__}


@mcp.tool()
def backtest_csv(csv_text: str, config_overrides: dict[str, float] | None = None) -> dict[str, Any]:
    """Backtest the demo squeeze strategy against caller-supplied OHLC data.

    Args:
        csv_text: CSV content (not a path — this process has no filesystem
            access to the caller's machine) with ``high``, ``low``, ``close``
            columns, case-insensitive.
        config_overrides: Optional subset of :class:`SqueezeConfig` fields to
            override (e.g. ``{"stop_loss": 0.015}``).
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    if not rows:
        raise ValueError("csv_text has no data rows")
    cols = {c.lower(): c for c in rows[0]}
    for required in ("high", "low", "close"):
        if required not in cols:
            raise ValueError(f"csv_text is missing a '{required}' column")

    high = [float(r[cols["high"]]) for r in rows]
    low = [float(r[cols["low"]]) for r in rows]
    close = [float(r[cols["close"]]) for r in rows]

    config = SqueezeConfig()
    if config_overrides:
        config = replace(config, **config_overrides)

    result = run_backtest(SqueezeStrategy(config), high, low, close)
    return {"summary": _summary_json(result), "n_bars": len(close), "config": config.__dict__}


@mcp.tool()
def describe_strategy_protocol() -> str:
    """Return the docstring of the TradingStrategy protocol.

    Read this before implementing a custom strategy — it's the exact
    interface :func:`run_backtest` (and the live engine) drives.
    """
    from binance_quant_engine.strategy.protocol import TradingStrategy

    return TradingStrategy.__doc__ or ""


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
