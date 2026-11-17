"""Train/test backtest of the high-probability planner (build_hp_plan).

1. Cache point-in-time agent outputs per stock per day (slow, once).
2. Grid-search a few parameters on TRAIN dates only (entry < SPLIT).
3. Report the chosen setting on TEST dates (entry >= SPLIT), untouched by tuning.

Run: python backtest_hp.py [SYMBOL ...]     Writes backtest_hp_report.md
"""
import os
import pickle
import sys
import warnings
from itertools import product

import pandas as pd

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)

import backtest as bt
import market_tools as mt
from trade_planner import build_hp_plan

SPLIT = pd.Timestamp("2024-01-01").date()
GRID = list(product([0.75, 1.0, 1.5], [3, 4, 5]))  # (target_r, min_score)
MIN_TRAIN_TRADES = 30
CACHE = "backtest_snapshots.pkl"
bt.MAX_HOLD_DAYS = 20


def build_snapshots(symbols):
    cache = pickle.load(open(CACHE, "rb")) if os.path.exists(CACHE) else {}
    for sym in symbols:
        if sym in cache:
            continue
        full = mt.yf.Ticker(f"{sym}.NS").history(period="6y", interval="1d")
        snaps = {}
        for t in range(bt.WARMUP, len(full) - 2):
            sl = full.iloc[: t + 1]
            mt._fetch_ohlcv = lambda tk, period="1y", _s=sl: _s.tail(260)
            try:
                snaps[t] = (mt.get_pivot_points("X"), mt.get_moving_averages("X"),
                            mt.get_technical_indicators("X"), mt.get_smart_money_concepts("X"),
                            {"score": mt.generate_tab3_indicator_suite("X")["score"]})
            except Exception:
                continue
        cache[sym] = (full, snaps)
        pickle.dump(cache, open(CACHE, "wb"))
        print(f"cached {sym}: {len(snaps)} days", flush=True)
    return {s: cache[s] for s in symbols if s in cache}


def run(data, target_r, min_score):
    trades = []
    for sym, (full, snaps) in data.items():
        t, n = bt.WARMUP, len(full)
        while t < n - 2:
            sn = snaps.get(t)
            if not sn:
                t += 1
                continue
            plan = build_hp_plan(*sn, min_score=min_score, target_r=target_r)
            tr = bt._simulate(full, t, plan) if "entry" in plan else None
            if tr:
                tr["symbol"] = sym
                trades.append(tr)
                t = tr["_exit_i"] + 1
            else:
                t += 1
    df = pd.DataFrame(trades)
    return df.drop(columns=["_exit_i"], errors="ignore")


def main(symbols):
    data = build_snapshots(symbols)
    rows, runs = [], {}
    for tr_r, ms in GRID:
        df = run(data, tr_r, ms)
        runs[(tr_r, ms)] = df
        if df.empty:
            continue
        a, b = df[df["entry_date"] < SPLIT], df[df["entry_date"] >= SPLIT]
        sa, sb = bt._stats(a), bt._stats(b)
        rows.append({"target_R": tr_r, "min_score": ms,
                     "train_n": sa.get("trades", 0), "train_win%": sa.get("win_rate_%"), "train_avgR": sa.get("avg_R"), "train_PF": sa.get("profit_factor"),
                     "test_n": sb.get("trades", 0), "test_win%": sb.get("win_rate_%"), "test_avgR": sb.get("avg_R"), "test_PF": sb.get("profit_factor")})
    grid = pd.DataFrame(rows)

    ok = grid[(grid["train_n"] >= MIN_TRAIN_TRADES) & (grid["train_avgR"] > 0)] if len(grid) else grid
    out = ["# Backtest: high-probability mode (build_hp_plan)", "",
           f"Symbols: {', '.join(symbols)}. Train = entries before {SPLIT}; Test = entries on/after {SPLIT}.",
           f"Costs {bt.ROUND_TRIP_COST*100:.1f}% round trip, max hold {bt.MAX_HOLD_DAYS} days, stop assumed first on same-bar hits.",
           "Parameters are chosen on TRAIN only (best train win rate with avg R > 0 and enough trades).", "",
           "## Grid (train and test shown; test not used for selection)", "```", grid.to_string(index=False) if len(grid) else "no trades", "```", ""]
    if len(ok):
        best = ok.sort_values(["train_win%", "train_avgR"], ascending=False).iloc[0]
        key = (best["target_R"], int(best["min_score"]))
        df = runs[key]
        test = df[df["entry_date"] >= SPLIT]
        out += [f"## Selected on train: target_R={key[0]}, min_score={key[1]}", "",
                "### Test (out-of-sample)", "```", str(pd.Series(bt._stats(test))), "```", "",
                "Exit reasons (test):", "```", str(test["exit_reason"].value_counts()) if len(test) else "none", "```", "",
                "By symbol (test):", "```", str(pd.DataFrame({s: bt._stats(g) for s, g in test.groupby("symbol")}).T) if len(test) else "none", "```", ""]
        tw = bt._stats(test).get("win_rate_%", 0)
        out += [f"**Test win rate {tw}% vs 55-80% goal: {'MET' if 55 <= tw else 'NOT MET'}. "
                f"Test avg R {bt._stats(test).get('avg_R')}.**"]
        df.to_csv("backtest_hp_trades.csv", index=False)
    else:
        out += ["No parameter set had enough profitable train trades. Nothing selected."]
    open("backtest_hp_report.md", "w", encoding="utf-8").write("\n".join(out))
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1:] or bt.DEFAULT_SYMBOLS)
