"""Integration tests for BracketMixin against a fake host.

Exercises the mixin the way the live bot actually drives it — through
``self`` — rather than testing the extracted :mod:`utils` functions in
isolation. This is what proves the two correctness fixes upstreamed from
the private system (tick-safe activationPrice, REJECTED as terminal) are
actually wired into the code path a real bot calls, not just correct as
standalone functions.
"""

from __future__ import annotations

from binance_quant_engine.execution.brackets import BracketMixin
from binance_quant_engine.execution.host import TrailConfig


class FakeAlgoApi:
    def __init__(self):
        self.placed: list[dict] = []
        self.next_algo_id = 1
        self.raise_on_place: Exception | None = None
        self.get_order_response: dict | None = None

    def place_order(self, params: dict) -> dict:
        if self.raise_on_place is not None:
            raise self.raise_on_place
        self.placed.append(params)
        algo_id = self.next_algo_id
        self.next_algo_id += 1
        return {"algoId": algo_id}

    def cancel_order(self, algo_id: int) -> dict:
        return {"algoId": algo_id, "status": "CANCELLED"}

    def get_order(self, algo_id: int) -> dict:
        return self.get_order_response or {}


class FakeDiscord:
    def __init__(self):
        self.messages: list[str] = []

    def send(self, content: str) -> None:
        self.messages.append(content)


class FakeHost(BracketMixin):
    """Minimal concrete implementation of ScalperProtocol for tests."""

    def __init__(self, *, paper_mode: bool = False, tick_size: float = 0.01, price_precision: int = 2):
        self.paper_mode = paper_mode
        self.client = None
        self.discord = FakeDiscord()
        self.strategy = None
        self.trail_config = TrailConfig()
        self._algo_api = FakeAlgoApi()
        self._tick_size = tick_size
        self._price_precision = price_precision

    def get_symbol_info(self, symbol: str) -> dict:
        return {"tick_size": self._tick_size, "price_precision": self._price_precision}

    def _round_qty(self, qty: float, symbol: str) -> float:
        return qty

    def _save_state(self) -> None:
        pass


def test_paper_mode_stop_loss_never_calls_algo_api():
    host = FakeHost(paper_mode=True)
    algo_id = host._place_server_stop_loss(
        "BTCUSDT", signal=1, quantity=1.0, entry_price=100.0, move_size=0.05, stop_mult=1.0
    )
    assert algo_id.startswith("paper_sl_")
    assert host._algo_api.placed == []


def test_stop_loss_prices_are_tick_rounded():
    # tick_size=0.01 forces a price like 95.037 to round to 95.04.
    host = FakeHost(tick_size=0.01, price_precision=2)
    host._place_server_stop_loss(
        "BTCUSDT", signal=1, quantity=1.0, entry_price=100.037, move_size=0.05, stop_mult=1.0
    )
    assert len(host._algo_api.placed) == 1
    params = host._algo_api.placed[0]
    trigger = float(params["triggerPrice"])
    limit = float(params["price"])
    assert round(trigger / 0.01) * 0.01 == round(trigger, 10)  # exactly on the tick grid
    assert round(limit / 0.01) * 0.01 == round(limit, 10)


def test_stop_loss_negative_stop_mult_aborts_without_calling_api():
    host = FakeHost()
    algo_id = host._place_server_stop_loss(
        "BTCUSDT", signal=1, quantity=1.0, entry_price=100.0, move_size=0.05, stop_mult=-1.0
    )
    assert algo_id is None
    assert host._algo_api.placed == []


def test_take_profit_invariant_guards_reject_bad_inputs():
    host = FakeHost()
    assert host._place_server_take_profit(
        "BTCUSDT", signal=1, quantity=1.0, entry_price=100.0, move_size=0.05, target_retrace=0.0
    ) is None
    assert host._algo_api.placed == []


def test_trailing_stop_activation_price_is_tick_rounded():
    # An activation price that lands off the 0.1 tick grid must be snapped
    # before it reaches params — this is the exact bug fixed vs. the
    # quantbox-engine predecessor.
    host = FakeHost(tick_size=0.1, price_precision=1)
    host._place_trailing_stop_market(
        "BTCUSDT", side="SELL", quantity=1.0, callback_rate=1.0, activation_price=100.037
    )
    assert len(host._algo_api.placed) == 1
    activation = float(host._algo_api.placed[0]["activationPrice"])
    assert activation == 100.0  # 100.037 snapped to the nearest 0.1 tick


def test_algo_order_would_trigger_returns_sentinel():
    host = FakeHost()
    host._algo_api.raise_on_place = Exception("APIError(code=-2021): Order would immediately trigger")
    result = host._place_algo_order(
        "BTCUSDT", side="SELL", order_type="STOP", quantity=1.0, trigger_price=100.0
    )
    assert result == "WOULD_TRIGGER"


def test_cancel_server_order_treats_unknown_order_as_success():
    import json

    from binance.exceptions import BinanceAPIException

    class _FakeResponse:
        status_code = 400

    class _Raiser:
        def cancel_order(self, algo_id):
            body = json.dumps({"code": -2011, "msg": "Unknown order sent."})
            raise BinanceAPIException(_FakeResponse(), 400, body)

    host = FakeHost()
    host._algo_api = _Raiser()
    assert host._cancel_server_stop_loss("BTCUSDT", "12345") is True


def test_check_order_filled_recognizes_rejected_as_dead():
    # The exact upstreamed fix: quantbox-engine's predecessor set didn't
    # include REJECTED, so a rejected algo order stayed "tracked" forever.
    host = FakeHost()
    host._algo_api.get_order_response = {"algoStatus": "REJECTED"}
    result = host._check_order_filled("BTCUSDT", "999")
    assert result == {"status": "CANCELLED", "algoId": "999"}


def test_verify_algo_order_active_paper_mode_is_always_working():
    host = FakeHost(paper_mode=True)
    assert host._verify_algo_order_active("999", "BTCUSDT") == "WORKING"
