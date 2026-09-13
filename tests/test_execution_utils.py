from binance_quant_engine.execution.utils import (
    ALGO_ORDER_DEAD_STATUSES,
    round_to_tick,
    to_api_symbol,
)


def test_round_to_tick_snaps_to_grid():
    assert round_to_tick(100.037, 0.01, 2) == 100.04
    assert round_to_tick(100.033, 0.01, 2) == 100.03


def test_round_to_tick_handles_zero_tick_size():
    assert round_to_tick(100.12345, 0.0, 4) == 100.1235


def test_to_api_symbol_strips_ccxt_settle_suffix():
    assert to_api_symbol("BTC/USDT:USDT") == "BTC/USDT"
    assert to_api_symbol("BTCUSDT") == "BTCUSDT"


def test_to_api_symbol_prefers_position_symbol():
    assert to_api_symbol("BTCUSDT", {"symbol": "BTC/USDT:USDT"}) == "BTC/USDT"


def test_algo_order_dead_statuses_are_terminal():
    assert "CANCELLED" in ALGO_ORDER_DEAD_STATUSES
    assert "NEW" not in ALGO_ORDER_DEAD_STATUSES
