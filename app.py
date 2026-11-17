import streamlit as st
import pandas as pd
from market_tools import (
    get_pivot_points,
    get_moving_averages,
    get_technical_indicators,
    calculate_position_risk,
    get_smart_money_concepts,
    generate_agent6_chart,
    generate_tab3_indicator_suite,
)
from screener_tools import scan_segment_movers_and_losers, INDEX_URLS
from trade_planner import build_trade_plan
from oi_tools import fetch_option_chain, analyze_oi, OIFetchError
from market_tools import _fetch_ohlcv

st.set_page_config(page_title="Multi-Agent NSE Screener, SMC & S&R Engine", layout="wide")
st.title("📈 Multi-Agent NSE Screener, Smart Money (SMC) & S&R Engine")

if "active_ticker" not in st.session_state:
    st.session_state.active_ticker = "HDFCBANK"

# --- SIDEBAR: GLOBAL PORTFOLIO SETTINGS ---
with st.sidebar:
    st.header("⚙️ Global Risk Settings")
    capital = st.number_input("Trading Capital (₹)", min_value=1000.0, value=100000.0, step=5000.0)
    risk_pct = st.slider("Risk per Trade (%)", min_value=0.5, max_value=5.0, value=1.0, step=0.5) / 100
    st.divider()
    skip_ssl = st.checkbox("Skip SSL verification for NSE OI fetch", value=False,
                           help="Only for networks that intercept SSL (corporate proxy).")
    st.info(f"**Active Stock for Tabs 2 & 3:** `{st.session_state.active_ticker}`")

# --- THREE MAIN TABS ---
tab_screener, tab_analysis, tab_indicators, tab_trade, tab_oi = st.tabs([
    "🔥 Tab 1: Top 5 Movers & Losers (Agents 0A & 0B)",
    "🎯 Tab 2: S&R, SMC & ATR Risk Setup (Agents 1–7)",
    "📊 Tab 3: 5 Best Indicators + SMC Decision Suite (Agent 8)",
    "🚦 Tab 4: Entry & Exit Plan (Agent 9)",
    "🧮 Tab 5: Open Interest Analysis (Agent 10)",
])

# ==============================================================================
# TAB 1: TOP MOVERS & TOP LOSERS SCREENER
# ==============================================================================
with tab_screener:
    st.subheader("Market-Cap Segment Screener (Top 5 Gainers & Top 5 Decliners)")

    sc_col1, sc_col2 = st.columns([3, 1])
    with sc_col1:
        selected_segment = st.selectbox(
            "Choose NSE Market-Cap Segment",
            list(INDEX_URLS.keys()),
            index=3,
        )
    with sc_col2:
        st.write("")
        st.write("")
        scan_btn = st.button("🔍 Scan Segment", type="primary", use_container_width=True)

    if scan_btn or "last_scan" not in st.session_state or st.session_state.get("last_segment") != selected_segment:
        with st.spinner(f"Agents 0A & 0B scanning {selected_segment}..."):
            st.session_state.last_scan = scan_segment_movers_and_losers(selected_segment, top_n=5)
            st.session_state.last_segment = selected_segment

    scan_res = st.session_state.last_scan
    gainers_df = scan_res.get("top_gainers", pd.DataFrame())
    losers_df = scan_res.get("top_losers", pd.DataFrame())

    col_g, col_l = st.columns(2)
    with col_g:
        st.markdown("### 🚀 Agent 0A: Top 5 Movers (Breakout Candidates)")
        if not gainers_df.empty:
            st.dataframe(gainers_df, hide_index=True, use_container_width=True)
        else:
            st.warning("No gainer data available.")

    with col_l:
        st.markdown("### 📉 Agent 0B: Top 5 Losers (Support Reversal Candidates)")
        if not losers_df.empty:
            st.dataframe(losers_df, hide_index=True, use_container_width=True)
        else:
            st.warning("No loser data available.")

    if not gainers_df.empty or not losers_df.empty:
        st.divider()
        combined_tickers = []
        if not gainers_df.empty:
            combined_tickers += [f"{t} (Top Mover 🚀)" for t in gainers_df["Ticker"].tolist()]
        if not losers_df.empty:
            combined_tickers += [f"{t} (Top Loser 📉)" for t in losers_df["Ticker"].tolist()]

        sel_col1, sel_col2 = st.columns([3, 1])
        with sel_col1:
            chosen_label = st.selectbox("Select any shortlisted stock to send to Tabs 2 & 3:", combined_tickers)
        with sel_col2:
            st.write("")
            st.write("")
            if st.button("➡️ Load into Analysis Tabs", use_container_width=True):
                st.session_state.active_ticker = chosen_label.split(" ")[0]
                st.success(f"Loaded **{st.session_state.active_ticker}**! Switch to **Tab 2** or **Tab 3** above.")

# ==============================================================================
# TAB 2: S&R, SMC & ATR RISK SETUP
# ==============================================================================
with tab_analysis:
    t_col1, t_col2 = st.columns([3, 1])
    with t_col1:
        ticker_input = st.text_input(
            "Analyze NSE Ticker (Synced from Tab 1 or enter manually)",
            value=st.session_state.active_ticker,
        ).upper().strip()
        st.session_state.active_ticker = ticker_input
    with t_col2:
        st.write("")
        st.write("")
        analyze_btn = st.button("🚀 Run Agents 1–7", type="primary", use_container_width=True)

    if analyze_btn or ticker_input:
        try:
            with st.spinner(f"Running Agents 1–7 on {ticker_input}..."):
                pivots = get_pivot_points(ticker_input)
                mas = get_moving_averages(ticker_input)
                inds = get_technical_indicators(ticker_input)
                smc = get_smart_money_concepts(ticker_input)

            last_close = pivots["last_close"]
            atr_val = inds["ATR_14"]
            st.metric(label=f"{ticker_input} Last Close", value=f"₹{last_close}", delta=f"ATR (14): ₹{atr_val}")
            st.divider()

            # --- INTERACTIVE ATR BAND CONTROLS & AGENT 6 CHART ---
            st.subheader("🎛️ Interactive ATR Trade Setup & Agent 6 Visual Chart (with SMC)")
            ctrl1, ctrl2, ctrl3, ctrl4, ctrl5 = st.columns(5)
            with ctrl1:
                atr_mult = st.slider("ATR SL Buffer (x ATR)", min_value=0.5, max_value=2.5, value=1.0, step=0.25)
            with ctrl2:
                trail_mult = st.slider("ATR Trail Mult (x ATR)", min_value=1.0, max_value=4.0, value=2.0, step=0.5)
            with ctrl3:
                entry_in = st.number_input("Entry Price (₹)", value=float(last_close), step=0.5)
            with ctrl4:
                auto_sl = round(pivots["daily_pivots"]["S1"] - (atr_mult * atr_val), 2)
                sl_in = st.number_input("Stop-Loss Price (₹)", value=float(auto_sl), step=0.5)
            with ctrl5:
                tgt_in = st.number_input("Target Price (₹)", value=float(pivots["daily_pivots"]["R1"]), step=0.5)

            chart_fig = generate_agent6_chart(
                ticker_input, pivots, mas, inds, smc=smc,
                entry_price=entry_in,
                stop_loss=sl_in,
                target_price=tgt_in,
                trailing_mult=trail_mult,
            )
            st.plotly_chart(chart_fig, use_container_width=True)
            st.divider()

            # --- AGENT 7: SMART MONEY CONCEPTS PANEL ---
            st.subheader("🏦 Agent 7: Smart Money Concepts (SMC)")
            smc1, smc2, smc3, smc4 = st.columns(4)
            smc1.metric("Market Structure", smc["market_structure"].split(" (")[0])
            smc2.metric("Buy-Side Liquidity (BSL)", f"₹{smc['buy_side_liquidity_high']}")
            smc3.metric("Sell-Side Liquidity (SSL)", f"₹{smc['sell_side_liquidity_low']}")
            b_ob = smc["latest_bullish_ob"]
            smc4.metric("Bullish Order Block", f"₹{b_ob['low']} - ₹{b_ob['high']}" if b_ob else "None Active")
            st.divider()

            # --- WORKER AGENTS 1, 2, 3 ---
            col1, col2, col3 = st.columns(3)

            with col1:
                st.subheader("🤖 Agent 1: Pivot Points")
                pivot_df = pd.DataFrame({
                    "Level": ["R3", "R2", "R1", "Pivot (P)", "S1", "S2", "S3"],
                    "Daily (₹)": [
                        pivots["daily_pivots"]["R3"], pivots["daily_pivots"]["R2"],
                        pivots["daily_pivots"]["R1"], pivots["daily_pivots"]["P"],
                        pivots["daily_pivots"]["S1"], pivots["daily_pivots"]["S2"],
                        pivots["daily_pivots"]["S3"],
                    ],
                    "Weekly (₹)": [
                        pivots["weekly_pivots"]["R3"], pivots["weekly_pivots"]["R2"],
                        pivots["weekly_pivots"]["R1"], pivots["weekly_pivots"]["P"],
                        pivots["weekly_pivots"]["S1"], pivots["weekly_pivots"]["S2"],
                        pivots["weekly_pivots"]["S3"],
                    ],
                })
                st.dataframe(pivot_df, hide_index=True, use_container_width=True)

            with col2:
                st.subheader("🤖 Agent 2: Moving Averages")
                ma_df = pd.DataFrame({
                    "Indicator": ["20 EMA", "50 EMA", "100 SMA", "200 EMA"],
                    "Value (₹)": [mas["EMA_20"], mas["EMA_50"], mas["SMA_100"], mas["EMA_200"]],
                    "Status vs Price": [
                        "Above ✅" if mas["trend_alignment"]["short_term_bullish"] else "Below ❌",
                        "Above ✅" if mas["trend_alignment"]["medium_term_bullish"] else "Below ❌",
                        "Above ✅" if last_close > mas["SMA_100"] else "Below ❌",
                        "Above ✅" if mas["trend_alignment"]["long_term_bullish"] else "Below ❌",
                    ],
                })
                st.dataframe(ma_df, hide_index=True, use_container_width=True)

            with col3:
                st.subheader("🤖 Agent 3: Indicators")
                st.metric("RSI (14)", inds["RSI_14"], delta="Oversold" if inds["RSI_14"] < 30 else ("Overbought" if inds["RSI_14"] > 70 else "Neutral"))
                st.metric("ATR (14) Volatility", f"₹{inds['ATR_14']}")
                st.metric("Relative Volume (vs 20D)", f"{inds['volume_ratio']}x")
                macd_status = "Bullish Crossover 🟢" if inds["MACD_bullish_crossover"] else "Bearish 🔴"
                st.info(f"**MACD:** {inds['MACD_line']} | **Signal:** {inds['MACD_signal']} ({macd_status})")

            st.divider()

            # --- SYNTHESIS (AGENT 4) & RISK MANAGER (AGENT 5) ---
            c4, c5 = st.columns(2)

            with c4:
                st.subheader("🧠 Agent 4: Confluence Zones (< 1.5% Gap)")
                levels = {
                    "Daily S1": pivots["daily_pivots"]["S1"],
                    "Daily S2": pivots["daily_pivots"]["S2"],
                    "Daily R1": pivots["daily_pivots"]["R1"],
                    "Weekly S1": pivots["weekly_pivots"]["S1"],
                    "Weekly S2": pivots["weekly_pivots"]["S2"],
                    "Weekly R1": pivots["weekly_pivots"]["R1"],
                    "20 EMA": mas["EMA_20"],
                    "50 EMA": mas["EMA_50"],
                    "200 EMA": mas["EMA_200"],
                }
                confluences = []
                keys = list(levels.keys())
                for i in range(len(keys)):
                    for j in range(i + 1, len(keys)):
                        v1, v2 = levels[keys[i]], levels[keys[j]]
                        diff_pct = abs(v1 - v2) / v1 * 100
                        if diff_pct <= 1.5:
                            zone_type = "Support Zone 🟢" if v1 < last_close else "Resistance Zone 🔴"
                            confluences.append(f"**{zone_type}:** {keys[i]} (₹{v1}) + {keys[j]} (₹{v2}) — *Gap: {diff_pct:.2f}%*")

                if confluences:
                    for item in confluences:
                        st.write(item)
                else:
                    st.write("No tight pivot/EMA clusters within 1.5% currently.")

            with c5:
                st.subheader("🛡️ Agent 5: Risk & Execution Ticket")
                risk_res = calculate_position_risk(entry_in, sl_in, tgt_in, capital, risk_pct)
                if "error" in risk_res:
                    st.error(risk_res["error"])
                else:
                    verdict = "✅ APPROVED (R:R ≥ 1:2)" if risk_res["approved_min_rr_2"] else "⚠️ WAIT / REJECT (R:R < 1:2)"
                    st.markdown(f"**Verdict:** {verdict}")
                    st.write(f"• **Risk-to-Reward:** 1 : {risk_res['risk_reward_ratio']}")
                    st.write(f"• **Recommended Quantity:** {risk_res['recommended_qty']} shares")
                    st.write(f"• **Max Risk:** ₹{risk_res['max_loss_inr']} | **Capital Needed:** ₹{risk_res['capital_required_inr']}")

            with st.expander("🔍 Inspect Raw Agent JSON Payloads"):
                st.json({"Agent_1_Pivots": pivots, "Agent_2_MAs": mas, "Agent_3_Indicators": inds, "Agent_7_SMC": smc})

        except Exception as e:
            st.error(f"Error running agents on {ticker_input}: {e}")

# ==============================================================================
# TAB 3: 5 BEST INDICATOR CHARTS + SMC DECISION SUITE
# ==============================================================================
with tab_indicators:
    active_sym = st.session_state.active_ticker
    st.subheader(f"🤖 Agent 8: 5-Indicator + Smart Money (SMC) Decision Suite for `{active_sym}`")

    try:
        with st.spinner(f"Computing 5 Indicators & Smart Money Zones for {active_sym}..."):
            ind_suite = generate_tab3_indicator_suite(active_sym)

        st.metric(
            label="Agent 8 Consensus Trade Call (Score: -6 to +6)",
            value=ind_suite["overall_call"],
            delta=f"Net Consensus Score: {ind_suite['score']} / 6",
        )

        sig_items = list(ind_suite["signals"].items())
        sig_cols = st.columns(6)
        for idx, (sig_name, sig_text) in enumerate(sig_items):
            sig_cols[idx].info(f"**{sig_name}**\n\n{sig_text}")

        st.divider()
        st.plotly_chart(ind_suite["figure"], use_container_width=True)

    except Exception as e:
        st.error(f"Error loading Tab 3 Decision Suite for {active_sym}: {e}")

# ==============================================================================
# TAB 4: ENTRY & EXIT PLAN (AGENT 9)
# ==============================================================================
with tab_trade:
    sym = st.session_state.active_ticker
    st.subheader(f"🚦 Agent 9: Entry & Exit Plan for `{sym}`")
    st.caption("Combines Agents 1, 2, 3, 5, 7 and 8. Long-only, rule-based. Not financial advice.")

    try:
        with st.spinner(f"Agent 9 combining all agent data for {sym}..."):
            p9 = get_pivot_points(sym)
            m9 = get_moving_averages(sym)
            i9 = get_technical_indicators(sym)
            s9 = get_smart_money_concepts(sym)
            suite9 = generate_tab3_indicator_suite(sym)
            plan = build_trade_plan(p9, m9, i9, s9, suite9)

        act = plan["action"]
        icon = "🟢" if act.startswith("BUY") else ("🔴" if act.startswith("AVOID") else "🟡")
        h1, h2, h3 = st.columns(3)
        h1.metric("Decision", f"{icon} {act}")
        h2.metric("Combined Score (-9 to +9)", plan["score"])
        h3.metric("Last Close / ATR", f"₹{plan['price']}", delta=f"ATR ₹{plan['atr']}", delta_color="off")
        st.write("**Why:** " + " | ".join(plan["reasons"]))

        if "entry" in plan:
            e1, e2, e3, e4 = st.columns(4)
            e1.metric("Entry", f"₹{plan['entry']}")
            e2.metric("Stop-Loss", f"₹{plan['stop_loss']}")
            e3.metric("Target 1", f"₹{plan['target_1']['price']}", delta=plan["target_1"]["source"], delta_color="off")
            e4.metric("Target 2", f"₹{plan['target_2']['price']}", delta=plan["target_2"]["source"], delta_color="off")
            st.info(plan["entry_note"])

            risk9 = calculate_position_risk(plan["entry"], plan["stop_loss"], plan["target_2"]["price"], capital, risk_pct)
            if "error" not in risk9:
                st.write(
                    f"**Position size:** {risk9['recommended_qty']} shares | "
                    f"**R:R to Target 2:** 1 : {risk9['risk_reward_ratio']} | "
                    f"**Max loss:** ₹{risk9['max_loss_inr']} | **Capital needed:** ₹{risk9['capital_required_inr']}"
                )
            st.write(f"**Current 2x ATR trailing stop (if already in trade):** ₹{plan['trail_stop_now']}")
        else:
            st.warning(plan["trigger"])

        st.markdown("### 🚪 Exit Rules")
        for rule in plan["exit_rules"]:
            st.write(f"• {rule}")

        with st.expander("🔍 Agent 8 signals used"):
            st.json(suite9["signals"])

    except Exception as e:
        st.error(f"Error building trade plan for {sym}: {e}")

# ==============================================================================
# TAB 5: OPEN INTEREST ANALYSIS (AGENT 10)
# ==============================================================================
with tab_oi:
    oi_sym = st.session_state.active_ticker
    st.subheader(f"🧮 Agent 10: Open Interest (OI) Analysis for `{oi_sym}`")
    st.caption("Live NSE option chain (OI, OI change, IV). Only F&O stocks have one. Not financial advice.")

    oc1, oc2 = st.columns([1, 3])
    with oc1:
        expiry_idx = st.selectbox("Expiry", [0, 1, 2], format_func=lambda i: ["Current", "Next", "Far"][i])
    with oc2:
        st.write("")
        st.button("🔄 Refresh OI", key="oi_refresh")

    try:
        with st.spinner(f"Fetching live option chain for {oi_sym} from NSE..."):
            chain = fetch_option_chain(oi_sym, expiry_index=expiry_idx, verify_ssl=not skip_ssl)
            px = _fetch_ohlcv(oi_sym, period="3mo")["Close"]
            chg_pct = float((px.iloc[-1] - px.iloc[-2]) / px.iloc[-2] * 100)

            plan9 = None
            try:
                plan9 = build_trade_plan(
                    get_pivot_points(oi_sym), get_moving_averages(oi_sym),
                    get_technical_indicators(oi_sym), get_smart_money_concepts(oi_sym),
                    generate_tab3_indicator_suite(oi_sym),
                )
            except Exception:
                plan9 = None
            oi = analyze_oi(chain, chg_pct, plan9)

        st.caption(f"Expiry **{oi['expiry']}** | NSE timestamp: {oi['timestamp']}")
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("OI Bias", oi["bias"], delta=f"Score {oi['score']:+d} / 6", delta_color="off")
        b2.metric("PCR (OI)", oi["pcr_oi"], delta=f"Volume PCR {oi['pcr_volume']}", delta_color="off")
        b3.metric("Max Pain", f"₹{oi['max_pain']:g}")
        b4.metric("Spot", f"₹{oi['spot']:g}", delta=f"{chg_pct:+.2f}% today", delta_color="off")

        if oi["confirmation"]:
            st.info(f"**Agent 9 + Agent 10:** {oi['confirmation']}" + (f"  (Agent 9: {plan9['action']})" if plan9 else ""))

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("OI Support (max put OI)", f"₹{oi['support']:g}", delta=f"Top: {', '.join(f'{x:g}' for x in oi['top_supports'])}", delta_color="off")
        k2.metric("OI Resistance (max call OI)", f"₹{oi['resistance']:g}", delta=f"Top: {', '.join(f'{x:g}' for x in oi['top_resistances'])}", delta_color="off")
        k3.metric("Fresh Put Writing", f"₹{oi['fresh_put_writing_strike']:g}")
        k4.metric("Fresh Call Writing", f"₹{oi['fresh_call_writing_strike']:g}")

        st.markdown("### ✅ Condition Checklist")
        rows = []
        for name, flag, detail in oi["checks"]:
            rows.append({"Condition": name, "Signal": "🟢 Bullish" if flag is True else ("🔴 Bearish" if flag is False else "🟡 Neutral"), "Detail": detail})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        import plotly.graph_objects as go
        d = chain["df"]
        win = d[(d["strike"] >= oi["spot"] * 0.85) & (d["strike"] <= oi["spot"] * 1.15)]
        fig = go.Figure()
        fig.add_bar(x=win["strike"], y=win["CE_OI"], name="Call OI", marker_color="#ef5350")
        fig.add_bar(x=win["strike"], y=win["PE_OI"], name="Put OI", marker_color="#26a69a")
        fig.add_vline(x=oi["spot"], line_dash="dash", annotation_text="Spot")
        fig.add_vline(x=oi["max_pain"], line_dash="dot", line_color="orange", annotation_text="Max Pain")
        fig.update_layout(barmode="group", height=420, title="Open Interest by Strike (±15% of spot)", xaxis_title="Strike", yaxis_title="OI")
        st.plotly_chart(fig, use_container_width=True)

        fig2 = go.Figure()
        fig2.add_bar(x=win["strike"], y=win["CE_chgOI"], name="Call OI Change", marker_color="#ef5350")
        fig2.add_bar(x=win["strike"], y=win["PE_chgOI"], name="Put OI Change", marker_color="#26a69a")
        fig2.add_vline(x=oi["spot"], line_dash="dash")
        fig2.update_layout(barmode="group", height=340, title="Change in OI by Strike (today)", xaxis_title="Strike")
        st.plotly_chart(fig2, use_container_width=True)

        with st.expander("🔍 Raw option chain"):
            st.dataframe(d, hide_index=True, use_container_width=True)

    except OIFetchError as e:
        st.warning(str(e))
    except Exception as e:
        st.error(f"Error running Agent 10 on {oi_sym}: {e}")
