"""README 히어로 이미지 생성 — 한 트레이드 위에 "진입 시점에 이미 걸린 TP/SL" 을 그린다.

실행 (레포 루트):
    uv run --with matplotlib --with numpy --with pandas python scripts/make_hero.py

데이터: docs/images/hero-data.csv (없으면 Binance USDT-M 공개 kline 엔드포인트에서 받아 저장 —
API 키 불필요). 백테스트는 레포의 run_backtest + 번들 데모 전략을 그대로 돌린다.
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.request import urlopen
import json

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from hero_style import caption, render_both  # noqa: E402
from binance_quant_engine.backtest.vectorized import run_backtest  # noqa: E402
from binance_quant_engine.strategy.demo_squeeze import SqueezeStrategy  # noqa: E402

DATA = ROOT / "docs/images/hero-data.csv"
SYMBOL, INTERVAL, LIMIT = "BTCUSDT", "4h", 1500
GENERATED = "2026-10-19"


def fetch_klines() -> pd.DataFrame:
    url = (f"https://fapi.binance.com/fapi/v1/klines?symbol={SYMBOL}"
           f"&interval={INTERVAL}&limit={LIMIT}")
    with urlopen(url, timeout=30) as r:
        raw = json.load(r)
    df = pd.DataFrame(
        [(int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])) for k in raw],
        columns=["open_time", "open", "high", "low", "close", "volume"],
    )
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df


def load() -> pd.DataFrame:
    if DATA.exists():
        df = pd.read_csv(DATA, parse_dates=["open_time"])
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
        return df
    df = fetch_klines()
    DATA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA, index=False)
    return df


def pick_trade(trades):
    """TP/SL 로 끝난 트레이드 중 길이가 적당한 것 — take_profit 우선."""
    cands = [t for t in trades if t.reason in ("take_profit", "stop_loss") and 3 <= t.exit_idx - t.entry_idx <= 80]
    cands.sort(key=lambda t: (t.reason != "take_profit", t.exit_idx - t.entry_idx))
    if not cands:
        raise SystemExit("no suitable trade in data")
    return cands[0]


def main() -> int:
    df = load()
    strat = SqueezeStrategy()
    cfg = strat.config
    res = run_backtest(strat, df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy(), symbol=SYMBOL)
    if "--list" in sys.argv:
        for t in res.trades:
            print(t.entry_idx, t.exit_idx, t.signal, t.reason)
        return 0
    tr = pick_trade(res.trades)

    e, x = tr.entry_idx, tr.exit_idx
    i0, i1 = max(0, e - 28), min(len(df) - 1, x + 10)
    w = df.iloc[i0 : i1 + 1].reset_index(drop=True)
    ex, xx = e - i0, x - i0
    entry = tr.entry_price
    tp = entry * (1 + tr.signal * cfg.take_profit)
    sl = entry * (1 - tr.signal * cfg.stop_loss)
    side = "long" if tr.signal == 1 else "short"
    hit_tp = tr.reason == "take_profit"

    def draw(fig, ax, p):
        up = w["close"] >= w["open"]
        for i, row in w.iterrows():
            col = p["ink2"] if up[i] else p["ink3"]
            ax.plot([i, i], [row.low, row.high], color=col, lw=1.2, solid_capstyle="butt", zorder=2)
            lo, hi = sorted((row.open, row.close))
            ax.bar(i, max(hi - lo, entry * 2e-4), bottom=lo, width=0.62, color=col, lw=0, zorder=3)
        # 포지션 열린 구간
        ax.axvspan(ex, xx, color=p["blue_wash"], lw=0, zorder=1)
        # 진입 시점부터 걸린 TP/SL
        for lvl, col, lab in ((tp, p["blue"], "Take-profit, placed at entry"),
                              (sl, p["amber"], "Stop-loss, placed at entry")):
            ax.hlines(lvl, ex, len(w) - 1, color=col, lw=2, zorder=4, label=lab)
            ax.text(len(w) - 0.6, lvl, f"{lvl:,.0f}", color=p["ink2"], fontsize=10, va="center", ha="left")
        # 진입/청산 마커
        ax.plot(ex, entry, "o", ms=11, color=p["green"], mec=p["surface"], mew=2, zorder=6,
                label=f"Entry ({side})")
        # 마커는 트리거 레벨(TP/SL 선) 위에 — 라이브에선 알고 주문이 그 가격에서 체결된다.
        xcol = p["blue"] if hit_tp else p["amber"]
        exit_lvl = tp if hit_tp else sl
        ax.plot(xx, exit_lvl, "D", ms=10, color=xcol, mec=p["surface"], mew=2, zorder=6,
                label="Exit, " + ("take-profit triggered" if hit_tp else "stop-loss triggered"))
        ax.annotate("entry", (ex, entry), xytext=(-14, -28), textcoords="offset points",
                    color=p["ink"], fontsize=10.5, ha="right",
                    arrowprops=dict(arrowstyle="-", color=p["ink3"], lw=1))
        ax.annotate("exit (TP trigger)" if hit_tp else "exit (SL trigger)", (xx, exit_lvl),
                    xytext=(16, -30 if hit_tp else 24), textcoords="offset points",
                    color=p["ink"], fontsize=10.5, ha="left",
                    arrowprops=dict(arrowstyle="-", color=p["ink3"], lw=1))
        # 범례용 캔들 프록시
        from matplotlib.patches import Patch
        h, lbl = ax.get_legend_handles_labels()
        h = [Patch(color=p["ink2"], label="Up candle"), Patch(color=p["ink3"], label="Down candle")] + h
        ax.legend(handles=h, loc="upper left", ncol=2, frameon=False,
                  handlelength=1.6, columnspacing=2.0, borderaxespad=0.6).set_zorder(10)

        ax.set_xlim(-1, len(w) + 4.5)
        lo_, hi_ = min(w.low.min(), sl, tp), max(w.high.max(), sl, tp)
        pad = (hi_ - lo_) * 0.08
        ax.set_ylim(lo_ - pad, hi_ + pad * 3.2)
        ticks = list(range(0, len(w), 12))
        ax.set_xticks(ticks)
        ax.set_xticklabels([w.open_time[i].strftime("%b %d %H:%M") for i in ticks])
        ax.set_ylabel(f"{SYMBOL} perpetual, {INTERVAL} candles (USDT)")
        ax.grid(axis="x", visible=False)
        ax.set_title("Exits are placed as exchange-side algo orders at entry — backtest and live run the same path",
                     pad=14)
        t0, t1 = w.open_time.iloc[0], w.open_time.iloc[-1]
        caption(fig, f"Data: Binance USDT-M futures public klines, {SYMBOL} {INTERVAL}, "
                     f"{t0:%Y-%m-%d %H:%M} – {t1:%Y-%m-%d %H:%M} UTC (no API key).\n"
                     f"One trade from the bundled demo backtest. The demo backtester books this exit at the bar's close "
                     f"({tr.exit_price:,.0f}); a live algo order fills at the trigger. Generated {GENERATED}.", p)

    paths = render_both(draw, out_dir=str(ROOT / "docs/images"), name="hero", figsize=(12, 5))
    print("trade:", tr, "\nwritten:", *paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
