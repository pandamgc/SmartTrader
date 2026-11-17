from mcp.server.fastmcp import FastMCP
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

mcp = FastMCP("NSE-Technical-Analysis-Tools")

def _fetch_ohlcv(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Helper to fetch NSE/BSE historical OHLCV data cleanly."""
    clean_ticker = ticker.upper().strip()
    if not (clean_ticker.endswith(".NS") or clean_ticker.endswith(".BO")):
        clean_ticker += ".NS"
    df = yf.Ticker(clean_ticker).history(period=period, interval="1d")
    if df.empty or len(df) < 50:
        raise ValueError(f"Insufficient market data found for {clean_ticker}")
    return df

@mcp.tool()
def get_pivot_points(ticker: str) -> dict:
    """Agent 1 Tool: Calculates Daily and Weekly Floor Pivot Points (P, R1-R3, S1-S3)."""
    df = _fetch_ohlcv(ticker, period="3mo")

    prev_d = df.iloc[-1]
    dh, dl, dc = float(prev_d["High"]), float(prev_d["Low"]), float(prev_d["Close"])
    dp = (dh + dl + dc) / 3
    daily = {
        "P": round(dp, 2),
        "R1": round(2 * dp - dl, 2), "S1": round(2 * dp - dh, 2),
        "R2": round(dp + (dh - dl), 2), "S2": round(dp - (dh - dl), 2),
        "R3": round(dh + 2 * (dp - dl), 2), "S3": round(dl - 2 * (dh - dp), 2),
    }

    df_w = df.resample("W-FRI").agg({"High": "max", "Low": "min", "Close": "last"}).dropna()
    prev_w = df_w.iloc[-2] if len(df_w) > 1 else df_w.iloc[-1]
    wh, wl, wc = float(prev_w["High"]), float(prev_w["Low"]), float(prev_w["Close"])
    wp = (wh + wl + wc) / 3
    weekly = {
        "P": round(wp, 2),
        "R1": round(2 * wp - wl, 2), "S1": round(2 * wp - wh, 2),
        "R2": round(wp + (wh - wl), 2), "S2": round(wp - (wh - wl), 2),
        "R3": round(wh + 2 * (wp - wl), 2), "S3": round(wl - 2 * (wh - wp), 2),
    }

    return {"ticker": ticker, "last_close": round(dc, 2), "daily_pivots": daily, "weekly_pivots": weekly}

@mcp.tool()
def get_moving_averages(ticker: str) -> dict:
    """Agent 2 Tool: Calculates EMA 20, EMA 50, SMA 100, and EMA 200 dynamic S&R levels."""
    df = _fetch_ohlcv(ticker, period="1y")
    close = df["Close"]
    last_close = round(float(close.iloc[-1]), 2)

    ema_20 = round(float(close.ewm(span=20, adjust=False).mean().iloc[-1]), 2)
    ema_50 = round(float(close.ewm(span=50, adjust=False).mean().iloc[-1]), 2)
    sma_100 = round(float(close.rolling(window=100).mean().iloc[-1]), 2)
    ema_200 = round(float(close.ewm(span=200, adjust=False).mean().iloc[-1]), 2)

    return {
        "ticker": ticker,
        "last_close": last_close,
        "EMA_20": ema_20,
        "EMA_50": ema_50,
        "SMA_100": sma_100,
        "EMA_200": ema_200,
        "trend_alignment": {
            "short_term_bullish": bool(last_close > ema_20),
            "medium_term_bullish": bool(last_close > ema_50),
            "long_term_bullish": bool(last_close > ema_200),
        },
    }

@mcp.tool()
def get_technical_indicators(ticker: str) -> dict:
    """Agent 3 Tool: Calculates RSI (14), MACD (12,26,9), Relative Volume, and ATR (14)."""
    df = _fetch_ohlcv(ticker, period="1y")
    close, high, low, vol = df["Close"], df["High"], df["Low"], df["Volume"]

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rsi_14 = round(float((100 - (100 / (1 + (gain / loss)))).iloc[-1]), 2)

    macd_line = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    signal_line = macd_line.ewm(span=9, adjust=False).mean()

    vol_sma_20 = vol.rolling(window=20).mean().iloc[-1]
    vol_ratio = round(float(vol.iloc[-1] / vol_sma_20), 2) if vol_sma_20 > 0 else 0.0

    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr_14 = round(float(tr.ewm(alpha=1/14, adjust=False).mean().iloc[-1]), 2)

    return {
        "ticker": ticker,
        "RSI_14": rsi_14,
        "MACD_line": round(float(macd_line.iloc[-1]), 2),
        "MACD_signal": round(float(signal_line.iloc[-1]), 2),
        "MACD_bullish_crossover": bool(macd_line.iloc[-1] > signal_line.iloc[-1]),
        "volume_ratio": vol_ratio,
        "ATR_14": atr_14,
    }

@mcp.tool()
def calculate_position_risk(entry_price: float, stop_loss: float, target_price: float, capital_inr: float = 100000.0, risk_per_trade_pct: float = 0.01) -> dict:
    """Agent 5 Tool: Computes Risk-to-Reward ratio and ATR-safe position sizing."""
    risk_per_share = abs(entry_price - stop_loss)
    reward_per_share = abs(target_price - entry_price)
    if risk_per_share == 0:
        return {"error": "Entry and Stop-Loss cannot be equal."}

    rr_ratio = round(reward_per_share / risk_per_share, 2)
    max_risk_inr = capital_inr * risk_per_trade_pct
    qty = int(max_risk_inr // risk_per_share)

    return {
        "risk_reward_ratio": rr_ratio,
        "approved_min_rr_2": rr_ratio >= 2.0,
        "recommended_qty": qty,
        "max_loss_inr": round(qty * risk_per_share, 2),
        "capital_required_inr": round(qty * entry_price, 2),
    }

@mcp.tool()
def get_smart_money_concepts(ticker: str) -> dict:
    """Agent 7 Tool: Detects Bullish/Bearish Order Blocks, Fair Value Gaps (FVG), BOS, and Liquidity Pools."""
    df = _fetch_ohlcv(ticker, period="6mo").tail(60).copy()
    last_close = round(float(df["Close"].iloc[-1]), 2)

    recent_20 = df.iloc[-21:-1]
    bsl_high = round(float(recent_20["High"].max()), 2)
    ssl_low = round(float(recent_20["Low"].min()), 2)

    if last_close > bsl_high:
        structure = "Bullish Break of Structure (BOS) 🟢"
    elif last_close < ssl_low:
        structure = "Bearish Break of Structure (BOS) 🔴"
    else:
        structure = "Range / Internal Liquidity Consolidation 🟡"

    bullish_fvgs = []
    bearish_fvgs = []
    for i in range(2, len(df)):
        c1_high, c1_low = df["High"].iloc[i - 2], df["Low"].iloc[i - 2]
        c3_high, c3_low = df["High"].iloc[i], df["Low"].iloc[i]
        dt_str = str(df.index[i].date())

        if c3_low > c1_high and last_close >= c1_high:
            bullish_fvgs.append({"date": dt_str, "bottom": round(float(c1_high), 2), "top": round(float(c3_low), 2)})
        if c3_high < c1_low and last_close <= c1_low:
            bearish_fvgs.append({"date": dt_str, "bottom": round(float(c3_high), 2), "top": round(float(c1_low), 2)})

    tr = (df["High"] - df["Low"]).rolling(14).mean()
    bullish_obs = []
    bearish_obs = []

    for i in range(1, len(df) - 1):
        body_next = abs(df["Close"].iloc[i + 1] - df["Open"].iloc[i + 1])
        atr_curr = tr.iloc[i] if pd.notna(tr.iloc[i]) else body_next
        dt_str = str(df.index[i].date())

        if df["Close"].iloc[i] < df["Open"].iloc[i] and df["Close"].iloc[i + 1] > df["Open"].iloc[i + 1] and body_next > 1.3 * atr_curr:
            ob_low, ob_high = round(float(df["Low"].iloc[i]), 2), round(float(df["High"].iloc[i]), 2)
            if last_close >= ob_low:
                bullish_obs.append({"date": dt_str, "low": ob_low, "high": ob_high})

        if df["Close"].iloc[i] > df["Open"].iloc[i] and df["Close"].iloc[i + 1] < df["Open"].iloc[i + 1] and body_next > 1.3 * atr_curr:
            ob_low, ob_high = round(float(df["Low"].iloc[i]), 2), round(float(df["High"].iloc[i]), 2)
            if last_close <= ob_high:
                bearish_obs.append({"date": dt_str, "low": ob_low, "high": ob_high})

    return {
        "ticker": ticker,
        "market_structure": structure,
        "buy_side_liquidity_high": bsl_high,
        "sell_side_liquidity_low": ssl_low,
        "latest_bullish_ob": bullish_obs[-1] if bullish_obs else None,
        "latest_bearish_ob": bearish_obs[-1] if bearish_obs else None,
        "latest_bullish_fvg": bullish_fvgs[-1] if bullish_fvgs else None,
        "latest_bearish_fvg": bearish_fvgs[-1] if bearish_fvgs else None,
    }

def generate_agent6_chart(
    ticker: str,
    pivots: dict,
    mas: dict,
    inds: dict,
    smc: dict = None,
    entry_price: float = None,
    stop_loss: float = None,
    target_price: float = None,
    trailing_mult: float = 2.0,
) -> go.Figure:
    """Agent 6 Tool: Candlestick + Volume + S&R + SMC Order Blocks + Shaded ATR Risk/Target Bands."""
    df_full = _fetch_ohlcv(ticker, period="1y").copy()
    close, high, low = df_full["Close"], df_full["High"], df_full["Low"]

    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    df_full["ATR_14"] = tr.ewm(alpha=1/14, adjust=False).mean()
    df_full["ATR_Trail"] = df_full["Close"] - (trailing_mult * df_full["ATR_14"])
    df_full["EMA_20"] = close.ewm(span=20, adjust=False).mean()
    df_full["EMA_50"] = close.ewm(span=50, adjust=False).mean()

    df = df_full.tail(60)
    last_close = pivots["last_close"]
    atr = inds["ATR_14"]

    entry = entry_price if entry_price is not None else last_close
    sl = stop_loss if stop_loss is not None else round(pivots["daily_pivots"]["S1"] - (1.0 * atr), 2)
    target = target_price if target_price is not None else pivots["daily_pivots"]["R1"]

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.75, 0.25],
    )

    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
            name="Price",
            increasing_line_color="#00C805",
            decreasing_line_color="#FF3B30",
        ),
        row=1, col=1,
    )

    fig.add_trace(
        go.Scatter(x=df.index, y=df["EMA_20"], mode="lines", name=f"20 EMA (₹{mas['EMA_20']})", line=dict(color="#2962FF", width=1.4)),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=df.index, y=df["EMA_50"], mode="lines", name=f"50 EMA (₹{mas['EMA_50']})", line=dict(color="#FF6D00", width=1.4)),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=df.index, y=df["ATR_Trail"], mode="lines", name=f"ATR Trail ({trailing_mult}x)", line=dict(color="#E040FB", width=1.2, dash="dot")),
        row=1, col=1,
    )

    # Shaded Target & Risk Bands
    fig.add_hrect(
        y0=min(entry, target), y1=max(entry, target),
        fillcolor="rgba(0, 230, 118, 0.14)", line_width=0,
        annotation_text=f"🎯 Target Zone (₹{target})",
        annotation_position="top left",
        row=1, col=1,
    )
    fig.add_hrect(
        y0=min(sl, entry), y1=max(sl, entry),
        fillcolor="rgba(255, 59, 48, 0.16)", line_width=0,
        annotation_text=f"🛑 ATR Risk Zone (SL: ₹{sl})",
        annotation_position="bottom left",
        row=1, col=1,
    )

    # SMC Order Block Overlays
    if smc:
        if smc.get("latest_bullish_ob"):
            ob = smc["latest_bullish_ob"]
            fig.add_hrect(
                y0=ob["low"], y1=ob["high"],
                fillcolor="rgba(0, 188, 212, 0.22)", line_color="#00BCD4", line_width=1,
                annotation_text=f"🏦 Bullish OB (₹{ob['low']}–₹{ob['high']})",
                annotation_position="bottom right", row=1, col=1,
            )
        if smc.get("latest_bearish_ob"):
            ob = smc["latest_bearish_ob"]
            fig.add_hrect(
                y0=ob["low"], y1=ob["high"],
                fillcolor="rgba(171, 71, 188, 0.22)", line_color="#AB47BC", line_width=1,
                annotation_text=f"🏦 Bearish OB (₹{ob['low']}–₹{ob['high']})",
                annotation_position="top right", row=1, col=1,
            )

    trade_levels = [
        (f"Target: ₹{target}", target, "#00E676", "solid", 2.0),
        (f"Entry: ₹{entry}", entry, "#FFD600", "dash", 1.8),
        (f"ATR Stop-Loss: ₹{sl}", sl, "#FF1744", "solid", 2.0),
    ]
    for label, val, color, dash, width in trade_levels:
        fig.add_hline(
            y=val, line_dash=dash, line_color=color, line_width=width,
            annotation_text=label, annotation_position="top right",
            row=1, col=1,
        )

    vol_colors = ["#00C805" if c >= o else "#FF3B30" for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(
        go.Bar(x=df.index, y=df["Volume"], name="Volume", marker_color=vol_colors, opacity=0.7),
        row=2, col=1,
    )

    fig.update_layout(
        title=f"🤖 Agent 6 Visual Setup: {ticker} (ATR: ₹{atr} | Risk/Target Bands & SMC Order Blocks)",
        xaxis_rangeslider_visible=False,
        height=620,
        template="plotly_dark",
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_yaxes(title_text="Price (₹)", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)

    return fig

@mcp.tool()
def generate_tab3_indicator_suite(ticker: str) -> dict:
    """Agent 8 Tool: 5 Best Indicators + Smart Money Concepts (SMC) Chart & Buy/Sell Consensus."""
    df_full = _fetch_ohlcv(ticker, period="1y").copy()
    close, high, low = df_full["Close"], df_full["High"], df_full["Low"]

    smc = get_smart_money_concepts(ticker)

    # 1. Bollinger Bands (20, 2)
    df_full["BB_Mid"] = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    df_full["BB_Upper"] = df_full["BB_Mid"] + (2 * bb_std)
    df_full["BB_Lower"] = df_full["BB_Mid"] - (2 * bb_std)

    # 2. RSI (14)
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    df_full["RSI"] = 100 - (100 / (1 + (gain / loss)))

    # 3. MACD (12, 26, 9)
    df_full["MACD"] = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    df_full["MACD_Signal"] = df_full["MACD"].ewm(span=9, adjust=False).mean()
    df_full["MACD_Hist"] = df_full["MACD"] - df_full["MACD_Signal"]

    # 4. Stochastic Oscillator (14, 3)
    low_14 = low.rolling(14).min()
    high_14 = high.rolling(14).max()
    df_full["Stoch_K"] = 100 * ((close - low_14) / (high_14 - low_14))
    df_full["Stoch_D"] = df_full["Stoch_K"].rolling(3).mean()

    # 5. ADX (14) + DI+ / DI-
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr_smooth = tr.ewm(alpha=1/14, adjust=False).mean()
    df_full["Plus_DI"] = 100 * (pd.Series(plus_dm, index=df_full.index).ewm(alpha=1/14, adjust=False).mean() / atr_smooth)
    df_full["Minus_DI"] = 100 * (pd.Series(minus_dm, index=df_full.index).ewm(alpha=1/14, adjust=False).mean() / atr_smooth)
    dx = 100 * (abs(df_full["Plus_DI"] - df_full["Minus_DI"]) / (df_full["Plus_DI"] + df_full["Minus_DI"]))
    df_full["ADX"] = dx.ewm(alpha=1/14, adjust=False).mean()

    df = df_full.tail(60)
    last = df.iloc[-1]
    last_close = float(last["Close"])

    signals = {}
    score = 0

    if last_close <= last["BB_Lower"] * 1.01:
        signals["1. Bollinger Bands"] = "BUY (Lower Band Bounce) 🟢"
        score += 1
    elif last_close >= last["BB_Upper"] * 0.99:
        signals["1. Bollinger Bands"] = "SELL (Upper Band Reject) 🔴"
        score -= 1
    else:
        signals["1. Bollinger Bands"] = "NEUTRAL (Mid-Channel) 🟡"

    if last["RSI"] < 35:
        signals["2. RSI (14)"] = f"BUY (Oversold: {last['RSI']:.1f}) 🟢"
        score += 1
    elif last["RSI"] > 70:
        signals["2. RSI (14)"] = f"SELL (Overbought: {last['RSI']:.1f}) 🔴"
        score -= 1
    else:
        signals["2. RSI (14)"] = f"NEUTRAL ({last['RSI']:.1f}) 🟡"

    if last["MACD"] > last["MACD_Signal"]:
        signals["3. MACD (12,26,9)"] = "BUY (Bullish Cross) 🟢"
        score += 1
    else:
        signals["3. MACD (12,26,9)"] = "SELL (Bearish Cross) 🔴"
        score -= 1

    if last["Stoch_K"] < 25 and last["Stoch_K"] > last["Stoch_D"]:
        signals["4. Stochastic (14,3)"] = "BUY (Oversold Cross) 🟢"
        score += 1
    elif last["Stoch_K"] > 75 and last["Stoch_K"] < last["Stoch_D"]:
        signals["4. Stochastic (14,3)"] = "SELL (Overbought Cross) 🔴"
        score -= 1
    else:
        signals["4. Stochastic (14,3)"] = f"NEUTRAL ({last['Stoch_K']:.1f}) 🟡"

    if last["ADX"] > 20 and last["Plus_DI"] > last["Minus_DI"]:
        signals["5. ADX Trend (14)"] = "BUY (+DI Dominant) 🟢"
        score += 1
    elif last["ADX"] > 20 and last["Minus_DI"] > last["Plus_DI"]:
        signals["5. ADX Trend (14)"] = "SELL (-DI Dominant) 🔴"
        score -= 1
    else:
        signals["5. ADX Trend (14)"] = f"NEUTRAL (ADX {last['ADX']:.1f}) 🟡"

    b_ob = smc.get("latest_bullish_ob")
    s_ob = smc.get("latest_bearish_ob")
    struct = smc.get("market_structure", "")

    if "Bullish Break of Structure" in struct or (b_ob and b_ob["low"] <= last_close <= b_ob["high"] * 1.015):
        signals["6. Smart Money (SMC)"] = "BUY (Bullish OB / BOS) 🟢"
        score += 1
    elif "Bearish Break of Structure" in struct or (s_ob and s_ob["low"] * 0.985 <= last_close <= s_ob["high"]):
        signals["6. Smart Money (SMC)"] = "SELL (Bearish OB / BOS) 🔴"
        score -= 1
    else:
        signals["6. Smart Money (SMC)"] = "NEUTRAL (Internal Range) 🟡"

    if score >= 3:
        overall_call = "STRONG BUY / INSTITUTIONAL ACCUMULATION 🟢"
    elif score >= 1:
        overall_call = "MILD BUY BIAS 🟢"
    elif score <= -3:
        overall_call = "STRONG SELL / DISTRIBUTION 🔴"
    elif score <= -1:
        overall_call = "MILD SELL BIAS 🔴"
    else:
        overall_call = "WAIT / NEUTRAL CONSOLIDATION 🟡"

    fig = make_subplots(
        rows=5, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.36, 0.16, 0.16, 0.16, 0.16],
        subplot_titles=(
            "1. Price, Bollinger Bands & Smart Money Zones (Order Blocks, FVG & Liquidity)",
            "2. RSI (14) Momentum",
            "3. MACD (12, 26, 9)",
            "4. Stochastic Oscillator (14, 3)",
            "5. ADX (14) Trend Strength (+DI / -DI)",
        ),
    )

    fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Price"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["BB_Upper"], line=dict(color="rgba(0, 188, 212, 0.6)", width=1), name="BB Upper"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["BB_Lower"], line=dict(color="rgba(0, 188, 212, 0.6)", width=1), fill="tonexty", fillcolor="rgba(0, 188, 212, 0.06)", name="BB Lower"), row=1, col=1)

    if b_ob:
        fig.add_hrect(
            y0=b_ob["low"], y1=b_ob["high"],
            fillcolor="rgba(0, 230, 118, 0.20)", line_color="#00E676", line_width=1,
            annotation_text=f"🏦 Bullish OB (₹{b_ob['low']}–₹{b_ob['high']})",
            annotation_position="bottom left", row=1, col=1,
        )
    if s_ob:
        fig.add_hrect(
            y0=s_ob["low"], y1=s_ob["high"],
            fillcolor="rgba(255, 82, 82, 0.20)", line_color="#FF5252", line_width=1,
            annotation_text=f"🏦 Bearish OB (₹{s_ob['low']}–₹{s_ob['high']})",
            annotation_position="top left", row=1, col=1,
        )
    if smc.get("latest_bullish_fvg"):
        fvg = smc["latest_bullish_fvg"]
        fig.add_hrect(
            y0=fvg["bottom"], y1=fvg["top"],
            fillcolor="rgba(255, 214, 0, 0.16)", line_color="#FFD600", line_dash="dot", line_width=1,
            annotation_text=f"⚡ Bullish FVG (₹{fvg['bottom']}–₹{fvg['top']})",
            annotation_position="bottom right", row=1, col=1,
        )
    if smc.get("latest_bearish_fvg"):
        fvg = smc["latest_bearish_fvg"]
        fig.add_hrect(
            y0=fvg["bottom"], y1=fvg["top"],
            fillcolor="rgba(171, 71, 188, 0.16)", line_color="#AB47BC", line_dash="dot", line_width=1,
            annotation_text=f"⚡ Bearish FVG (₹{fvg['bottom']}–₹{fvg['top']})",
            annotation_position="top right", row=1, col=1,
        )

    fig.add_hline(y=smc["buy_side_liquidity_high"], line_dash="dash", line_color="#FF8A80", line_width=1, annotation_text=f"BSL High ₹{smc['buy_side_liquidity_high']}", annotation_position="top right", row=1, col=1)
    fig.add_hline(y=smc["sell_side_liquidity_low"], line_dash="dash", line_color="#69F0AE", line_width=1, annotation_text=f"SSL Low ₹{smc['sell_side_liquidity_low']}", annotation_position="bottom right", row=1, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df["RSI"], line=dict(color="#AB47BC", width=1.8), name="RSI 14"), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#FF5252", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#00E676", row=2, col=1)

    hist_colors = ["#00E676" if v >= 0 else "#FF5252" for v in df["MACD_Hist"]]
    fig.add_trace(go.Bar(x=df.index, y=df["MACD_Hist"], marker_color=hist_colors, name="MACD Hist"), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["MACD"], line=dict(color="#2962FF", width=1.5), name="MACD"), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["MACD_Signal"], line=dict(color="#FF6D00", width=1.5), name="Signal"), row=3, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df["Stoch_K"], line=dict(color="#26C6DA", width=1.5), name="%K"), row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["Stoch_D"], line=dict(color="#FFA726", width=1.5), name="%D"), row=4, col=1)
    fig.add_hline(y=80, line_dash="dot", line_color="#FF5252", row=4, col=1)
    fig.add_hline(y=20, line_dash="dot", line_color="#00E676", row=4, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df["ADX"], line=dict(color="#FFD600", width=2), name="ADX"), row=5, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["Plus_DI"], line=dict(color="#00E676", width=1.2), name="+DI"), row=5, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["Minus_DI"], line=dict(color="#FF5252", width=1.2), name="-DI"), row=5, col=1)
    fig.add_hline(y=25, line_dash="dot", line_color="#9E9E9E", row=5, col=1)

    fig.update_layout(
        height=1150,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        showlegend=False,
        margin=dict(l=10, r=10, t=40, b=10),
    )

    return {"overall_call": overall_call, "score": score, "signals": signals, "smc": smc, "figure": fig}

if __name__ == "__main__":
    mcp.run()
