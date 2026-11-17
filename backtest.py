"""Walk-forward backtest of the Agent 1-9 price logic (no look-ahead).

Reuses the real agent functions: market_tools._fetch_ohlcv is patched to return
only bars up to the decision day, so every signal is computed point-in-time.
Agent 10 (OI) is NOT backtested: NSE exposes no historical option-chain OI.

Run:  python backtest.py [SYMBOL ...]
Writes: backtest_trades.csv, backtest_signal_quality.csv, backtest_report.md
"""
import sys
import warnings
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)

import market_tools as mt
from trade_planner import build_trade_plan

mt.make_subplots = lambda *a, **k: MagicMock()  # skip chart building (speed only)

DEFAULT_SYMBOLS = ["HDFCBANK", "RELIANCE", "TCS", "INFY", "ICICIBANK", "SBIN", "LT", "ITC", "AXISBANK", "BHARTIARTL"]
WARMUP = 260            # bars needed by the 1y indicators
PULLBACK_VALID_DAYS = 10
MAX_HOLD_DAYS = 30
ROUND_TRIP_COST = 0.002  # 0.2% brokerage + STT + slippage, assumption
LOOKAHEAD = (5, 10, 20)


def _signals(df_slice: pd.DataFrame) -> dict:
    mt._fetch_ohlcv = lambda t, period="1y": df_slice.tail(260)
    p, m = mt.get_pivot_points("X"), mt.get_moving_averages("X")
    i, s = mt.get_technical_indicators("X"), mt.get_smart_money_concepts("X")
    suite = mt.generate_tab3_indicator_suite("X")
    return build_trade_plan(p, m, i, s, suite)


def _simulate(df: pd.DataFrame, t: int, plan: dict):
    """Enter after decision bar t. Returns trade dict or None."""
    entry, stop = plan["entry"], plan["stop_loss"]
    t1, t2 = plan["target_1"]["price"], plan["target_2"]["price"]
    if not (stop < entry < t1 <= t2):
        return None

    # --- fill ---
    fill_i = None
    if plan["action"] == "BUY":
        fill_i, fill_px = t + 1, float(df["Open"].iloc[t + 1]) if t + 1 < len(df) else None
        if fill_px is None:
            return None
    else:  # pullback limit order
        for j in range(t + 1, min(t + 1 + PULLBACK_VALID_DAYS, len(df))):
            if df["Low"].iloc[j] <= entry:
                fill_i = j
                fill_px = min(entry, float(df["Open"].iloc[j]))
                break
        if fill_i is None:
            return None
    if fill_px <= stop:
        return None
    risk = fill_px - stop

    # --- manage: stop / T1 half / T2 / time ---
    cur_stop, half_done, realized, qty_left = stop, False, 0.0, 1.0
    start = fill_i if plan["action"] != "BUY" else fill_i  # same-bar stop check allowed on fill bar
    last_j = min(fill_i + MAX_HOLD_DAYS, len(df) - 1)
    exit_i, reason = last_j, "time"
    for j in range(start, last_j + 1):
        o, h, l, c = (float(df[k].iloc[j]) for k in ("Open", "High", "Low", "Close"))
        if j == fill_i and plan["action"] == "BUY":
            o = fill_px  # bar opened at our fill
        if l <= cur_stop:  # stop first (conservative)
            px = min(o, cur_stop)
            realized += qty_left * (px - fill_px)
            qty_left, exit_i, reason = 0.0, j, "stop" if not half_done else "stop_after_T1"
            break
        if not half_done and h >= t1:
            realized += 0.5 * (t1 - fill_px)
            qty_left, half_done, cur_stop = 0.5, True, fill_px
            if h >= t2 and l > cur_stop:
                realized += 0.5 * (t2 - fill_px)
                qty_left, exit_i, reason = 0.0, j, "T2"
                break
            continue
        if half_done and h >= t2:
            realized += qty_left * (t2 - fill_px)
            qty_left, exit_i, reason = 0.0, j, "T2"
            break
    if qty_left > 0:
        realized += qty_left * (float(df["Close"].iloc[last_j]) - fill_px)
    realized -= fill_px * ROUND_TRIP_COST
    return {
        "entry_date": df.index[fill_i].date(), "exit_date": df.index[exit_i].date(),
        "action": plan["action"], "score": plan["score"],
        "entry": round(fill_px, 2), "stop": stop, "T1": t1, "T2": t2,
        "exit_reason": reason, "bars_held": exit_i - fill_i,
        "R": round(realized / risk, 2), "ret_pct": round(realized / fill_px * 100, 2),
        "_exit_i": exit_i,
    }


def run_symbol(sym: str, full: pd.DataFrame):
    trades, quality = [], []
    t = WARMUP
    n = len(full)
    while t < n - 2:
        try:
            plan = _signals(full.iloc[: t + 1])
        except Exception:
            t += 1
            continue
        close = float(full["Close"].iloc[t])
        row = {"symbol": sym, "date": full.index[t].date(), "action": plan["action"], "score": plan["score"]}
        for k in LOOKAHEAD:
            row[f"fwd_{k}d_pct"] = round((float(full["Close"].iloc[t + k]) / close - 1) * 100, 2) if t + k < n else np.nan
        quality.append(row)

        tr = _simulate(full, t, plan) if "entry" in plan else None
        if tr:
            tr["symbol"] = sym
            trades.append(tr)
            t = tr["_exit_i"] + 1  # one position at a time
        else:
            t += 1
    return trades, quality


def _stats(tr: pd.DataFrame) -> dict:
    if tr.empty:
        return {"trades": 0}
    w, l = tr[tr["R"] > 0], tr[tr["R"] <= 0]
    gp, gl = w["ret_pct"].sum(), -l["ret_pct"].sum()
    eq = (1 + tr.sort_values("exit_date")["ret_pct"] / 100).cumprod()
    return {
        "trades": len(tr), "win_rate_%": round(len(w) / len(tr) * 100, 1),
        "avg_R": round(tr["R"].mean(), 2), "avg_ret_%": round(tr["ret_pct"].mean(), 2),
        "profit_factor": round(gp / gl, 2) if gl > 0 else float("inf"),
        "max_dd_%": round(((eq / eq.cummax()) - 1).min() * 100, 1),
        "avg_bars": round(tr["bars_held"].mean(), 1),
    }


def main(symbols):
    all_tr, all_q, bh = [], [], {}
    for sym in symbols:
        full = mt.yf.Ticker(f"{sym}.NS").history(period="6y", interval="1d")
        if len(full) < WARMUP + 50:
            print(sym, "insufficient data, skipped")
            continue
        print(f"{sym}: {len(full)} bars ...", flush=True)
        tr, q = run_symbol(sym, full)
        all_tr += tr
        all_q += q
        bh[sym] = round((float(full["Close"].iloc[-1]) / float(full["Close"].iloc[WARMUP]) - 1) * 100, 1)
        print(f"  trades={len(tr)}", flush=True)

    trades = pd.DataFrame(all_tr).drop(columns=["_exit_i"], errors="ignore")
    qual = pd.DataFrame(all_q)
    trades.to_csv("backtest_trades.csv", index=False)
    qual.to_csv("backtest_signal_quality.csv", index=False)

    out = ["# Backtest report: Agents 1-9 price logic", "",
           f"Symbols: {', '.join(symbols)}. Walk-forward, no look-ahead, long-only, one position per stock.",
           f"Costs: {ROUND_TRIP_COST*100:.1f}% round trip. Same-bar stop/target: stop assumed first. "
           f"Pullback limit valid {PULLBACK_VALID_DAYS} days, max hold {MAX_HOLD_DAYS} days.",
           "Agent 10 (OI) not backtested: no historical option-chain OI available.", ""]
    out += ["## Overall", "```", str(pd.Series(_stats(trades))), "```", ""]
    out += ["## By action", "```", str(pd.DataFrame({a: _stats(g) for a, g in trades.groupby("action")}).T) if len(trades) else "none", "```", ""]
    out += ["## By symbol", "```", str(pd.DataFrame({s: _stats(g) for s, g in trades.groupby("symbol")}).T) if len(trades) else "none", "```", ""]
    out += ["## Exit reasons", "```", str(trades["exit_reason"].value_counts()) if len(trades) else "none", "```", ""]
    if len(qual):
        base = qual[[f"fwd_{k}d_pct" for k in LOOKAHEAD]].mean().round(2)
        by_act = qual.groupby("action")[[f"fwd_{k}d_pct" for k in LOOKAHEAD]].agg("mean").round(2)
        by_act["days"] = qual.groupby("action").size()
        out += ["## Signal quality: average forward return (%) after each verdict, all days",
                "Unconditional average (every day):", "```", str(base), "```", "By verdict:", "```", str(by_act), "```", ""]
    out += ["## Buy & hold over the same window (%)", "```", str(pd.Series(bh)), "```"]
    open("backtest_report.md", "w", encoding="utf-8").write("\n".join(out))
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_SYMBOLS)
