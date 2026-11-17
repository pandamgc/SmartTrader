import pandas as pd
import yfinance as yf
import requests
import io

INDEX_URLS = {
    "Large Cap (Nifty 50)": "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
    "Nifty Next 50": "https://nsearchives.nseindia.com/content/indices/ind_niftynext50list.csv",
    "Midcap (Nifty Midcap 150)": "https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
    "Smallcap (Nifty Smallcap 250)": "https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv"
}

FALLBACK_UNIVERSE = {
    "Large Cap (Nifty 50)": ["RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "BHARTIARTL", "SBIN", "LT", "AXISBANK", "TATAMOTORS"],
    "Nifty Next 50": ["HAL", "BEL", "TRENT", "ZOMATO", "JIOFIN", "VBL", "CHOLAFIN", "DLF", "SIEMENS", "PIDILITIND"],
    "Midcap (Nifty Midcap 150)": ["POLYCAB", "PERSISTENT", "COFORGE", "AUROPHARMA", "FEDERALBNK", "SUZLON", "YESBANK", "IDFCFIRSTB", "ASHOKLEY", "KPITTECH"],
    "Smallcap (Nifty Smallcap 250)": ["MOREPENLAB", "NATIONALUM", "CDSL", "MCX", "ANGELONE", "IRB", "HUDCO", "NBCC", "HFCL", "TRIDENT"]
}

def get_segment_tickers(segment_name: str, limit: int = 50) -> list:
    """Fetches constituent tickers for a given market-cap segment."""
    url = INDEX_URLS.get(segment_name)
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            df = pd.read_csv(io.StringIO(resp.text))
            symbols = df["Symbol"].dropna().unique().tolist()[:limit]
            return [f"{s}.NS" for s in symbols]
    except Exception:
        pass
    return [f"{s}.NS" for s in FALLBACK_UNIVERSE.get(segment_name, [])]

def scan_segment_movers_and_losers(segment_name: str, top_n: int = 5) -> dict:
    """
    Runs Agent 0A (Top Movers) & Agent 0B (Top Losers) on a market cap segment.
    Returns Top 5 Gainers and Top 5 Losers based on daily % change.
    """
    tickers = get_segment_tickers(segment_name)
    data = yf.download(tickers, period="5d", interval="1d", group_by="ticker", progress=False, threads=True)

    movers = []
    for t in tickers:
        try:
            df_t = data[t].dropna()
            if len(df_t) >= 2:
                prev_close = float(df_t["Close"].iloc[-2])
                curr_close = float(df_t["Close"].iloc[-1])
                pct_change = round(((curr_close - prev_close) / prev_close) * 100, 2)
                movers.append({
                    "Ticker": t.replace(".NS", ""),
                    "Close (₹)": round(curr_close, 2),
                    "Change (%)": pct_change
                })
        except Exception:
            continue

    df_movers = pd.DataFrame(movers)
    if df_movers.empty:
        return {"top_gainers": pd.DataFrame(), "top_losers": pd.DataFrame()}

    top_gainers = df_movers.sort_values(by="Change (%)", ascending=False).head(top_n).reset_index(drop=True)
    top_losers = df_movers.sort_values(by="Change (%)", ascending=True).head(top_n).reset_index(drop=True)

    return {
        "segment": segment_name,
        "top_gainers": top_gainers,
        "top_losers": top_losers
    }
