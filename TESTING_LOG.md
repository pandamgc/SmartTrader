# Testing and Change Log: nse-multi-agent-sr

Append-only record of every test, probe, backtest and code change. Newest entries go at the bottom.
Companion to `README.md` (summary) and `.kiro/logs/worklog-YYYY-MM-DD.md` (daily work log).

Entry format: what was done, command or method, result, status (PASS / FAIL / PARTIAL / NOT RUN).

---

## 2026-11-17

### Changes made

| # | Change | File | Verified how |
|---|---|---|---|
| C1 | Added Agent 9 (`build_trade_plan`): verdict, entry, stop, 2 targets, exit rules | `trade_planner.py` (new) | Syntax check + one synthetic scenario (T1) |
| C2 | Added Tab 4 (Entry & Exit Plan) | `app.py` | Syntax check only. Not opened in a browser. |
| C3 | Simplified stop-loss logic (removed a redundant order-block block) | `trade_planner.py` | Synthetic scenario (T1) |
| C4 | Added Agent 10: live NSE fetch + OI analysis | `oi_tools.py` (new) | Live NSE tests (T4-T7) |
| C5 | Fixed price + OI buildup check: now requires positive OI additions (both sides unwinding was wrongly read as put writing) | `oi_tools.py` | Re-test on HDFCBANK (T7). Result: "no clear buildup" |
| C6 | Added Tab 5 (OI Analysis), sidebar "Skip SSL verification" checkbox, default stock changed MOREPENLAB to HDFCBANK | `app.py` | Syntax check only. Not opened in a browser. |
| C7 | Added `build_hp_plan` (high-probability variant) | `trade_planner.py` | Backtest (T10). Not wired into UI. |
| C8 | Fixed Agent 8 SMC match: `"Bullish BOS"` to `"Bullish Break of Structure"`, same for bearish | `market_tools.py` | Syntax check + grep of the two lines. Behavior not re-tested. |
| C9 | Added backtest scripts | `backtest.py`, `backtest_hp.py` (new) | Ran (T8-T10) |
| C10 | README updated in place (user asked) | `README.md` | Read back after edit |

### Tests and probes

**T1. Agent 9 synthetic scenario** (PASS)
- Method: hand-made inputs (price 100, ATR 2, all MAs bullish, Agent 8 score +3).
- Result: BUY, entry 100, stop 97, T1 104 (Daily R1), T2 106 (Weekly R1), trail 96. Matches the rules.
- Gap: only the BUY path was tested. WAIT, BUY ON PULLBACK and AVOID were not.

**T2. Syntax checks** (PASS)
- `ast.parse` on `app.py`, `trade_planner.py`, `oi_tools.py`, `market_tools.py`: all parse.

**T3. Streamlit start** (PARTIAL)
- Streamlit 1.64.0 and dependencies present. App started on port 8501 and the port listened.
- Not done: no page was loaded in a browser, so Tabs 4 and 5 are untested in the UI. A shell hang earlier caused one failed start; retry worked.

**T4. NSE reachability** (PARTIAL, workaround needed)
- Normal HTTPS request failed: `CERTIFICATE_VERIFY_FAILED` (network intercepts SSL).
- With per-request `verify=False`: NSE home page HTTP 200. Session-level `verify=False` did not work (overridden).
- Old endpoint `option-chain-equities` returned `{}`. Do not use it.

**T5. NSE v3 option chain** (PASS, with SSL verification off)
- `option-chain-contract-info` and `option-chain-v3` returned OI, change in OI, volume, IV, LTP per strike.
- Futures endpoint `quote-derivative` returned non-JSON. Futures OI is not supported.

**T6. OI agent on RELIANCE and MOREPENLAB** (PASS)
- RELIANCE: PCR 0.79, max pain 1280, support 1100, resistance 1350, bias MILD BEARISH.
- MOREPENLAB: clear error "no option chain (not in F&O)". Correct handling.
- Found a bug here: price + OI buildup called "put writing" while both sides were unwinding. Fixed as C5.

**T7. OI agent on HDFCBANK, after fix** (PASS)
- Spot 814.95, expiry 23-Nov-2026, PCR 0.90, max pain 750, support 700, resistance 820, bias BEARISH (-3).
- Agent 9 input was a placeholder `BUY`, so the "OI conflicts" line is not a real combined verdict.
- Caveat: expiry dates were used as NSE returned them and not independently checked.

**T8. Timing check** (PASS)
- Point-in-time signal run: 0.43 s per day (mostly chart building). Chart building stubbed in backtests for speed.

**T9. Backtest of base plan (Agents 1-9), HDFCBANK only** (PASS, results stale)
- Run before the Agent 8 BOS fix (C8). 83 trades, win rate 42.2%, avg R -0.07, profit factor 0.86, max drawdown -19.1%.
- By action: BUY 23 trades / 47.8% / PF 1.11; BUY ON PULLBACK 60 trades / 40.0% / PF 0.78.
- Exits: stop 47, T2 25, stop after T1 9, time 2.
- Forward returns after verdict (all days): BUY -0.20% (5d), -1.33% (10d), -1.53% (20d). The BUY verdict did worse than the unconditional average (+0.40%, +0.50%, +0.97%).
- Buy and hold over the window: +14.2%.
- Outputs: `backtest_report.md`, `backtest_trades.csv`, `backtest_signal_quality.csv`.

**T9b. Backtest of base plan, 10 stocks** (NOT RUN)
- The run was interrupted before it reported. No result exists. Re-run needed with the C8 fix.

**T10. High-probability variant, 10 stocks, train/test** (PASS as a test, FAIL as a strategy)
- Stocks: HDFCBANK, RELIANCE, TCS, INFY, ICICIBANK, SBIN, LT, ITC, AXISBANK, BHARTIARTL. Includes the C8 fix.
- Train = entries before 2024-01-01. Test = entries on or after. Costs 0.2% round trip. Max hold 20 days.
- 9 parameter sets (target 0.75R / 1.0R / 1.5R x min score 3 / 4 / 5).
- Train: win rate 54.5-61.2%, avg R -0.05 to 0.00, PF 0.74-0.87.
- Test: win rate 45.5-54.3%, avg R -0.22 to -0.33, PF 0.39-0.53.
- Selection rule (best train win rate with avg R > 0 and 30+ trades) selected nothing.
- Goal of 55-80% win rate: NOT MET. Not wired into the UI.
- Outputs: `backtest_hp_report.md`, `backtest_hp_log.txt`, `backtest_snapshots.pkl`.

### Known gaps and risks

- Tabs 4 and 5 not opened in a browser. Errors in the UI would not have been caught.
- Agent 9 branches WAIT, BUY ON PULLBACK, AVOID untested by hand (they ran inside the backtests, which only checks they do not crash).
- C8 behavior (BOS now scoring) not tested on its own. Its effect shows only inside T10.
- Agent 10 OI logic is not backtested. NSE has no historical OI. Needs daily snapshots.
- No unit-test suite exists in the project.
- NSE fetch needs SSL verification off on this network. Treat that setting as a testing and proxy workaround only.
- Tests that ran read-only GETs against nseindia.com used `verify=False`.

### Open items

- Re-run base-plan backtest on 10 stocks with C8 (T9b).
- Browser test of Tabs 4 and 5.
- Decide next step: single-signal backtests, new inputs, or a different risk profile.

### Later entries, 2026-11-17

| # | Change | File | Verified how |
|---|---|---|---|
| C11 | Created this test record | `TESTING_LOG.md` (new) | Not applicable (documentation) |
| C12 | Added workspace rule requiring every test, probe, backtest and code change to be logged here, plus a pointer in the daily worklog | `CharterKiro/.kiro/steering/testing-log.md` (new) | Rule appeared in the active rule list in the next turn (PASS) |

- No code was run or changed in this step. Nothing was tested.
- Status of earlier open items is unchanged: T9b still NOT RUN, Tabs 4 and 5 still not opened in a browser.
