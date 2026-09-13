"""Small, strategy-agnostic helpers shared across the execution layer.

Kept separate from :mod:`brackets` so they can be unit-tested (and reused by
a host application) without pulling in the full bracket-order state machine.
"""

from __future__ import annotations

from typing import Any

#: Binance algo/conditional-order statuses that mean the order is no longer
#: live and bookkeeping can stop tracking it. Centralized here so a status
#: string Binance adds later only needs to be taught to one place.
ALGO_ORDER_DEAD_STATUSES = frozenset(
    {"CANCELLED", "CANCELED", "EXPIRED", "USER_CANCELLED", "ERROR"}
)


def round_to_tick(price: float, tick_size: float, price_precision: int) -> float:
    """Snap *price* to the symbol's tick grid.

    Binance rejects (or silently misprices) an order whose price isn't an
    exact multiple of the symbol's ``tickSize`` — a raw float division
    (``price / tick_size``) almost never lands exactly on the grid because of
    binary floating-point rounding. Round to the nearest tick first, then to
    the symbol's quoted decimal precision, in that order.
    """
    if tick_size <= 0:
        return round(price, price_precision)
    return round(round(price / tick_size) * tick_size, price_precision)


def to_api_symbol(symbol: str, position: dict[str, Any] | None = None) -> str:
    """Strip a CCXT-style ``BASE/QUOTE:SETTLE`` suffix for raw Binance REST calls.

    Position payloads from some data sources carry the exchange-agnostic form
    (e.g. ``"BTC/USDT:USDT"``); the Binance Futures REST API wants the bare
    ``"BTCUSDT"`` form. *position*, if given, may carry an already-resolved
    ``symbol`` field that takes precedence over *symbol*.
    """
    raw = (position or {}).get("symbol", symbol)
    return raw.split(":")[0] if ":" in raw else raw
