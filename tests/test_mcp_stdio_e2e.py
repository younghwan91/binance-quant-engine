"""End-to-end smoke test: spawn the actual `binance-quant-engine-mcp` process
and speak real MCP-over-stdio to it, instead of calling the tool functions
in-process. This is what proves the packaged entry point (not just the
Python module) works for a real MCP client.
"""

from __future__ import annotations

import shutil
import sys

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


@pytest.mark.asyncio
async def test_mcp_server_entry_point_lists_and_calls_tools():
    exe = shutil.which("binance-quant-engine-mcp") or sys.executable
    args = [] if exe != sys.executable else ["-m", "binance_quant_engine.mcp.server"]

    params = StdioServerParameters(command=exe, args=args)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {"run_demo_backtest", "backtest_csv", "describe_strategy_protocol"} <= names

            result = await session.call_tool("run_demo_backtest", {"n_bars": 400, "seed": 3})
            assert not result.is_error
