import pytest

mcp_module = pytest.importorskip("mcp")

from binance_quant_engine.mcp.server import (  # noqa: E402
    backtest_csv,
    describe_strategy_protocol,
    run_demo_backtest,
)


def test_run_demo_backtest_returns_finite_summary():
    result = run_demo_backtest(n_bars=500, seed=1)
    summary = result["summary"]
    assert set(summary) == {"n_trades", "total_return", "win_rate", "profit_factor", "max_drawdown"}
    for v in summary.values():
        assert v == v  # not NaN
        assert v not in (float("inf"), float("-inf"))


def test_backtest_csv_parses_and_runs():
    csv_text = "high,low,close\n" + "\n".join(
        f"{100 + i * 0.1},{99 + i * 0.1},{99.5 + i * 0.1}" for i in range(150)
    )
    result = backtest_csv(csv_text)
    assert result["n_bars"] == 150
    assert "summary" in result


def test_backtest_csv_rejects_missing_column():
    with pytest.raises(ValueError):
        backtest_csv("open,close\n1,2\n")


def test_describe_strategy_protocol_returns_text():
    doc = describe_strategy_protocol()
    assert "TradingStrategy" in doc or len(doc) > 0
