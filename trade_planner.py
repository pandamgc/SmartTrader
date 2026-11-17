"""Agent 9: Entry / Exit Planner.

Pure function over the outputs of Agents 1, 2, 3, 7 and 8. Long-only (NSE cash
segment). Not financial advice; rules are heuristic.
"""


def _ma_points(mas: dict) -> int:
    ta = mas["trend_alignment"]
    flags = [ta["short_term_bullish"], ta["medium_term_bullish"], ta["long_term_bullish"]]
    return sum(1 if f else -1 for f in flags)


def build_trade_plan(pivots: dict, mas: dict, inds: dict, smc: dict, suite: dict) -> dict:
    price = float(pivots["last_close"])
    atr = float(inds["ATR_14"])
    d, w = pivots["daily_pivots"], pivots["weekly_pivots"]

    # ---- 1. Combined score: Agent 8 (-6..+6) + Agent 2 MA alignment (-3..+3) ----
    ma_pts = _ma_points(mas)
    total = int(suite["score"]) + ma_pts
    reasons = [f"Agent 8 consensus score {suite['score']:+d}", f"Agent 2 MA alignment {ma_pts:+d}"]

    # ---- 2. Candidate support / resistance levels from all agents ----
    supports = {
        "Daily S1": d["S1"], "Daily S2": d["S2"], "Weekly S1": w["S1"],
        "20 EMA": mas["EMA_20"], "50 EMA": mas["EMA_50"], "200 EMA": mas["EMA_200"],
        "SMC sell-side liquidity": smc["sell_side_liquidity_low"],
    }
    resistances = {
        "Daily R1": d["R1"], "Daily R2": d["R2"], "Weekly R1": w["R1"], "Weekly R2": w["R2"],
        "SMC buy-side liquidity": smc["buy_side_liquidity_high"],
    }
    b_ob, s_ob = smc.get("latest_bullish_ob"), smc.get("latest_bearish_ob")
    b_fvg = smc.get("latest_bullish_fvg")
    if b_ob:
        supports["Bullish Order Block (high)"] = b_ob["high"]
    if b_fvg:
        supports["Bullish FVG (top)"] = b_fvg["top"]
    if s_ob:
        resistances["Bearish Order Block (low)"] = s_ob["low"]

    below = sorted(((v, k) for k, v in supports.items() if v < price), reverse=True)
    above = sorted((v, k) for k, v in resistances.items() if v > price)

    # ---- 3. Verdict ----
    overextended = inds["RSI_14"] > 70
    if total >= 4:
        action = "BUY"
    elif total >= 2:
        action = "BUY ON PULLBACK"
    elif total >= -1:
        action = "WAIT"
    else:
        action = "AVOID / EXIT IF HOLDING"

    if overextended and action == "BUY":
        action = "BUY ON PULLBACK"
        reasons.append(f"RSI {inds['RSI_14']} is overbought, so wait for a pullback")

    plan = {"action": action, "score": total, "reasons": reasons, "price": price, "atr": atr}

    if action.startswith("AVOID") or action == "WAIT":
        # Give a trigger so "WAIT" is actionable.
        trigger = smc["buy_side_liquidity_high"]
        plan["trigger"] = (
            f"Re-evaluate on a close above Rs {trigger} (SMC buy-side liquidity) "
            f"with relative volume >= 1.2x (now {inds['volume_ratio']}x)."
        )
        plan["exit_rules"] = [
            "If holding: exit on a close below the 20 EMA "
            f"(Rs {mas['EMA_20']}) or MACD bearish cross.",
        ]
        return plan

    # ---- 4. Entry ----
    near_support = below[0] if below else None
    if action == "BUY":
        entry = price
        entry_note = "Enter at market / next-day open. Trend, momentum and SMC agree."
        if near_support and (price - near_support[0]) > 1.5 * atr:
            action = plan["action"] = "BUY ON PULLBACK"
            entry_note = ""
    if action == "BUY ON PULLBACK":
        if near_support:
            entry = near_support[0]
            entry_note = f"Place a limit buy near {near_support[1]} (Rs {near_support[0]}). Skip if not tested soon."
        else:
            entry = round(price - 0.5 * atr, 2)
            entry_note = "No support below. Limit buy 0.5 ATR under price."

    # ---- 5. Stop loss: below the support that backs the entry, plus 0.5 ATR buffer ----
    anchors = [v for v, _ in below if v <= entry]
    anchor = anchors[0] if anchors else entry - atr
    stop = round(min(anchor, entry - 0.5 * atr) - 0.5 * atr, 2)
    risk = entry - stop

    # ---- 6. Targets: nearest resistances giving at least 1R / 2R ----
    ups = [(v, k) for v, k in above if v > entry]
    t1 = next(((v, k) for v, k in ups if v - entry >= risk), (round(entry + risk, 2), "1R"))
    t2 = next(((v, k) for v, k in ups if v - entry >= 2 * risk and v > t1[0]),
              (round(entry + 2 * risk, 2), "2R"))

    plan.update({
        "entry": round(entry, 2), "entry_note": entry_note,
        "stop_loss": stop,
        "target_1": {"price": round(t1[0], 2), "source": t1[1]},
        "target_2": {"price": round(t2[0], 2), "source": t2[1]},
        "trail_stop_now": round(price - 2 * atr, 2),
        "exit_rules": [
            f"Hard stop: close below Rs {stop}.",
            f"At Target 1 (Rs {round(t1[0], 2)}): sell half, move stop to entry (Rs {round(entry, 2)}).",
            f"Remaining half: exit at Target 2 (Rs {round(t2[0], 2)}) or trail 2 x ATR below the highest close.",
            f"Exit early if close < 20 EMA (Rs {mas['EMA_20']}) after Target 1, or MACD turns bearish.",
            "Take profit into strength if RSI > 70 and a bearish order block or resistance is hit.",
        ],
    })
    return plan


def build_hp_plan(pivots, mas, inds, smc, suite, min_score=4, target_r=1.0,
                  rsi_lo=40, rsi_hi=65, min_confluence=2) -> dict:
    """High-probability mode: the base plan, but only when every filter agrees.

    Filters: base action is BUY/BUY ON PULLBACK, combined score >= min_score,
    price above 20/50/200 EMA, MACD bullish, RSI in [rsi_lo, rsi_hi], and at
    least min_confluence support levels within 1% of the entry.
    Exit: single full target at target_r x risk (pulled in to a nearer
    resistance that is at least 0.5R away). Stop is unchanged.
    """
    base = build_trade_plan(pivots, mas, inds, smc, suite)

    def reject(why):
        return {"action": "NO TRADE (HP filter)", "score": base["score"], "reasons": base["reasons"] + [why],
                "price": base["price"], "atr": base["atr"], "trigger": f"High-probability filter failed: {why}",
                "exit_rules": []}

    if "entry" not in base:
        return reject(f"base verdict is {base['action']}")
    if base["score"] < min_score:
        return reject(f"score {base['score']} < {min_score}")
    ta = mas["trend_alignment"]
    if not (ta["short_term_bullish"] and ta["medium_term_bullish"] and ta["long_term_bullish"]):
        return reject("price is not above all of 20/50/200 EMA")
    if not inds["MACD_bullish_crossover"]:
        return reject("MACD is bearish")
    if not (rsi_lo <= inds["RSI_14"] <= rsi_hi):
        return reject(f"RSI {inds['RSI_14']} outside {rsi_lo}-{rsi_hi}")

    entry, stop = base["entry"], base["stop_loss"]
    d, w = pivots["daily_pivots"], pivots["weekly_pivots"]
    levels = [d["S1"], d["S2"], w["S1"], mas["EMA_20"], mas["EMA_50"], smc["sell_side_liquidity_low"]]
    if smc.get("latest_bullish_ob"):
        levels.append(smc["latest_bullish_ob"]["high"])
    if smc.get("latest_bullish_fvg"):
        levels.append(smc["latest_bullish_fvg"]["top"])
    near = sum(1 for v in levels if abs(v - entry) / entry <= 0.01)
    if near < min_confluence:
        return reject(f"only {near} support level(s) within 1% of entry (need {min_confluence})")

    risk = entry - stop
    target, src = entry + target_r * risk, f"{target_r}R"
    res = [d["R1"], d["R2"], w["R1"], w["R2"], smc["buy_side_liquidity_high"]]
    if smc.get("latest_bearish_ob"):
        res.append(smc["latest_bearish_ob"]["low"])
    close_res = [v for v in res if entry + 0.5 * risk <= v < target]
    if close_res:
        target, src = min(close_res), "nearest resistance"
    target = round(target, 2)

    hp = dict(base)
    hp["action"] = base["action"]
    hp["reasons"] = base["reasons"] + [f"HP filters passed ({near} support levels near entry)"]
    hp["target_1"] = hp["target_2"] = {"price": target, "source": src}
    hp["exit_rules"] = [
        f"Hard stop: close below Rs {stop}.",
        f"Full exit at target Rs {target} ({src}).",
        f"Exit after {MAX_HOLD_DAYS_HP} trading days if neither is hit.",
        f"Exit early if close < 20 EMA (Rs {mas['EMA_20']}) with MACD turning bearish.",
    ]
    return hp


MAX_HOLD_DAYS_HP = 20
