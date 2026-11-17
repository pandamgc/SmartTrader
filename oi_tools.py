"""Agent 10: Open Interest (OI) analysis from the live NSE stock option chain.

Read-only GETs against nseindia.com. Option-chain OI only (no futures OI).
Only stocks in the F&O segment have an option chain.
"""
import warnings

import pandas as pd
import requests

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/option-chain",
}
_BASE = "https://www.nseindia.com"


class OIFetchError(Exception):
    """Raised with a user-readable reason when the chain cannot be fetched."""


def fetch_option_chain(symbol: str, expiry_index: int = 0, verify_ssl: bool = True) -> dict:
    """Fetch the live option chain. Returns {symbol, expiry, expiries, underlying, timestamp, df}.

    df has one row per strike: CE_/PE_ OI, OI change, volume, IV, LTP.
    verify_ssl=False is for networks with SSL interception (corporate proxy).
    """
    sym = symbol.upper().strip().replace(".NS", "")
    kw = {"timeout": 15, "verify": verify_ssl}
    s = requests.Session()
    s.headers.update(_HEADERS)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s.get(_BASE, **kw)
            s.get(f"{_BASE}/option-chain", **kw)
            info = s.get(f"{_BASE}/api/option-chain-contract-info?symbol={sym}", **kw)
            expiries = info.json().get("expiryDates", []) if info.status_code == 200 else []
            if not expiries:
                raise OIFetchError(f"{sym} has no option chain (not in the NSE F&O segment, or NSE blocked the request).")
            expiry = expiries[min(expiry_index, len(expiries) - 1)]
            r = s.get(f"{_BASE}/api/option-chain-v3?type=Equity&symbol={sym}&expiry={expiry}", **kw)
            rec = r.json().get("records", {}) if r.status_code == 200 else {}
    except requests.exceptions.SSLError:
        raise OIFetchError("SSL certificate check failed (proxy?). Tick 'Skip SSL verification' in the sidebar.")
    except requests.exceptions.RequestException as e:
        raise OIFetchError(f"Network error reaching NSE: {e}")
    except ValueError:
        raise OIFetchError("NSE returned a non-JSON reply (rate limit or bot block). Retry in a minute.")

    rows = []
    for item in rec.get("data", []):
        ce, pe = item.get("CE") or {}, item.get("PE") or {}
        strike = ce.get("strikePrice") or pe.get("strikePrice")
        if strike is None:
            continue
        rows.append({
            "strike": float(strike),
            "CE_OI": ce.get("openInterest", 0), "CE_chgOI": ce.get("changeinOpenInterest", 0),
            "CE_vol": ce.get("totalTradedVolume", 0), "CE_IV": ce.get("impliedVolatility", 0),
            "CE_LTP": ce.get("lastPrice", 0),
            "PE_OI": pe.get("openInterest", 0), "PE_chgOI": pe.get("changeinOpenInterest", 0),
            "PE_vol": pe.get("totalTradedVolume", 0), "PE_IV": pe.get("impliedVolatility", 0),
            "PE_LTP": pe.get("lastPrice", 0),
        })
    if not rows:
        raise OIFetchError(f"Empty option chain returned for {sym}.")
    df = pd.DataFrame(rows).sort_values("strike").reset_index(drop=True)
    return {
        "symbol": sym, "expiry": expiry, "expiries": expiries,
        "underlying": float(rec.get("underlyingValue", 0)),
        "timestamp": rec.get("timestamp", ""), "df": df,
    }


def _max_pain(df: pd.DataFrame) -> float:
    """Strike at which total option-writer payout is lowest."""
    best, best_loss = None, None
    for k in df["strike"]:
        loss = ((k - df["strike"]).clip(lower=0) * df["CE_OI"]).sum() + \
               ((df["strike"] - k).clip(lower=0) * df["PE_OI"]).sum()
        if best_loss is None or loss < best_loss:
            best, best_loss = float(k), loss
    return best


def analyze_oi(chain: dict, price_change_pct: float, plan: dict = None) -> dict:
    """Agent 10: turns the chain into support/resistance, a condition checklist and a verdict.

    price_change_pct: today's % price change (from the price data).
    plan: optional Agent 9 plan dict, used to confirm or conflict with its action.
    """
    df, spot = chain["df"], chain["underlying"]
    ce_oi, pe_oi = df["CE_OI"].sum(), df["PE_OI"].sum()
    ce_chg, pe_chg = df["CE_chgOI"].sum(), df["PE_chgOI"].sum()
    if ce_oi == 0 or pe_oi == 0:
        raise OIFetchError("Chain has no open interest yet (illiquid or pre-market).")

    pcr_oi = round(pe_oi / ce_oi, 2)
    pcr_vol = round(df["PE_vol"].sum() / df["CE_vol"].sum(), 2) if df["CE_vol"].sum() else None
    max_pain = _max_pain(df)

    res_row = df.loc[df["CE_OI"].idxmax()]
    sup_row = df.loc[df["PE_OI"].idxmax()]
    resistance, support = float(res_row["strike"]), float(sup_row["strike"])
    top_res = df.nlargest(3, "CE_OI")["strike"].tolist()
    top_sup = df.nlargest(3, "PE_OI")["strike"].tolist()
    fresh_call = float(df.loc[df["CE_chgOI"].idxmax(), "strike"])
    fresh_put = float(df.loc[df["PE_chgOI"].idxmax(), "strike"])

    atm = df.iloc[(df["strike"] - spot).abs().argmin()]
    atm_strike = float(atm["strike"])
    iv_ce, iv_pe = float(atm["CE_IV"]), float(atm["PE_IV"])
    iv_skew = round(iv_pe - iv_ce, 2) if iv_ce and iv_pe else None

    # Each check: (name, passed_bullish: True/False/None, detail). None = neutral.
    checks = []
    if pcr_oi >= 1.3:
        checks.append(("PCR (OI)", True, f"{pcr_oi} >= 1.3: heavy put writing, bullish (very high can mean overbought)"))
    elif pcr_oi >= 0.8:
        checks.append(("PCR (OI)", None, f"{pcr_oi}: balanced"))
    else:
        checks.append(("PCR (OI)", False, f"{pcr_oi} < 0.8: call-heavy, bearish"))

    if pe_chg > ce_chg and pe_chg > 0:
        checks.append(("OI change today", True, f"Puts added {pe_chg:,} vs calls {ce_chg:,}: put writing"))
    elif ce_chg > pe_chg and ce_chg > 0:
        checks.append(("OI change today", False, f"Calls added {ce_chg:,} vs puts {pe_chg:,}: call writing"))
    else:
        checks.append(("OI change today", None, f"Calls {ce_chg:,}, puts {pe_chg:,}: unwinding on both sides"))

    # Price + OI interpretation
    if price_change_pct > 0.3 and pe_chg > 0 and pe_chg > ce_chg:
        bu = ("Price + OI buildup", True, f"Price {price_change_pct:+.2f}% with put writing: bullish buildup")
    elif price_change_pct > 0.3 and ce_chg > 0 and ce_chg > pe_chg:
        bu = ("Price + OI buildup", None, f"Price {price_change_pct:+.2f}% but call writing caps the move")
    elif price_change_pct < -0.3 and ce_chg > 0 and ce_chg > pe_chg:
        bu = ("Price + OI buildup", False, f"Price {price_change_pct:+.2f}% with call writing: bearish buildup")
    elif price_change_pct < -0.3 and pe_chg > 0 and pe_chg > ce_chg:
        bu = ("Price + OI buildup", None, f"Price {price_change_pct:+.2f}% but put writing is defending")
    else:
        bu = ("Price + OI buildup", None, f"Price {price_change_pct:+.2f}%: no clear buildup")
    checks.append(bu)

    room_up = round((resistance - spot) / spot * 100, 2)
    room_dn = round((spot - support) / spot * 100, 2)
    if spot >= resistance:
        checks.append(("Position in OI range", True, f"Price above max call-OI strike {resistance:g}: breakout, call writers under pressure"))
    elif spot <= support:
        checks.append(("Position in OI range", False, f"Price below max put-OI strike {support:g}: support broken"))
    elif room_up < 1.0:
        checks.append(("Position in OI range", False, f"Only {room_up}% below resistance {resistance:g}: little upside room"))
    elif room_dn < room_up:
        checks.append(("Position in OI range", True, f"Closer to support {support:g} ({room_dn}%) than resistance {resistance:g} ({room_up}%)"))
    else:
        checks.append(("Position in OI range", None, f"Between support {support:g} ({room_dn}%) and resistance {resistance:g} ({room_up}%)"))

    mp_gap = round((max_pain - spot) / spot * 100, 2)
    if mp_gap > 1.5:
        checks.append(("Max pain pull", True, f"Max pain {max_pain:g} is {mp_gap}% above price"))
    elif mp_gap < -1.5:
        checks.append(("Max pain pull", False, f"Max pain {max_pain:g} is {abs(mp_gap)}% below price"))
    else:
        checks.append(("Max pain pull", None, f"Max pain {max_pain:g} is near price"))

    if iv_skew is None:
        checks.append(("ATM IV skew", None, "IV not available at ATM"))
    elif iv_skew > 2:
        checks.append(("ATM IV skew", False, f"Put IV above call IV by {iv_skew}: downside hedging demand"))
    elif iv_skew < -2:
        checks.append(("ATM IV skew", True, f"Call IV above put IV by {abs(iv_skew)}: upside demand"))
    else:
        checks.append(("ATM IV skew", None, f"Skew {iv_skew}: flat"))

    score = sum(1 if c[1] is True else -1 if c[1] is False else 0 for c in checks)
    if score >= 3:
        bias = "BULLISH OI"
    elif score >= 1:
        bias = "MILD BULLISH OI"
    elif score <= -3:
        bias = "BEARISH OI"
    elif score <= -1:
        bias = "MILD BEARISH OI"
    else:
        bias = "NEUTRAL OI"

    confirmation = None
    if plan:
        act = plan.get("action", "")
        if act.startswith("BUY"):
            confirmation = ("OI CONFIRMS the Agent 9 entry" if score >= 1
                            else "OI CONFLICTS with the Agent 9 entry: wait or reduce size" if score <= -1
                            else "OI is neutral on the Agent 9 entry: rely on price levels")
        elif act.startswith("AVOID"):
            confirmation = ("OI agrees with Agent 9: stay out" if score <= 0
                            else "OI is bullish while Agent 9 says avoid: wait for price to confirm")
        else:
            confirmation = ("OI leans bullish: watch for the Agent 9 trigger" if score >= 2
                            else "OI gives no extra edge: keep waiting")

    return {
        "symbol": chain["symbol"], "expiry": chain["expiry"], "timestamp": chain["timestamp"],
        "spot": spot, "pcr_oi": pcr_oi, "pcr_volume": pcr_vol, "max_pain": max_pain,
        "support": support, "resistance": resistance,
        "top_supports": top_sup, "top_resistances": top_res,
        "fresh_put_writing_strike": fresh_put, "fresh_call_writing_strike": fresh_call,
        "total_ce_oi": int(ce_oi), "total_pe_oi": int(pe_oi),
        "ce_oi_change": int(ce_chg), "pe_oi_change": int(pe_chg),
        "atm_strike": atm_strike, "atm_iv_ce": iv_ce, "atm_iv_pe": iv_pe,
        "checks": checks, "score": score, "bias": bias, "confirmation": confirmation,
    }
