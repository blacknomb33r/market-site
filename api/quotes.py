import json
from datetime import date, timedelta
import yfinance as yf
import pandas as pd

def _series_last(s):
    return None if s is None or s.empty else float(s.iloc[-1])

def _prev(s, n):
    if s is None or s.empty or len(s) <= n: return None
    return float(s.iloc[-(n+1)])

def _delta_pct(cur, prev):
    if cur is None or prev is None or prev == 0: return None
    return (cur - prev) / prev * 100.0

def handler(request):
    tickers = {
        "S&P 500": "^GSPC",
        "DAX": "^GDAXI",
        "WTI Oil": "CL=F",
        "Gold": "GC=F",
        "Bitcoin": "BTC-USD",
        "VIX": "^VIX",
    }
    today = date.today()
    start = today - timedelta(days=90)

    df = yf.download(
        tickers=list(tickers.values()),
        start=start, end=today + timedelta(days=1),
        auto_adjust=True, group_by="ticker", threads=True, progress=False
    )

    out = []
    for name, tk in tickers.items():
        if isinstance(df.columns, pd.MultiIndex):
            s = df[tk]["Close"].dropna().astype(float)
        else:
            s = df["Close"].dropna().astype(float)
        cur = _series_last(s)
        prev1 = _prev(s, 1)
        d1 = _delta_pct(cur, prev1)
        out.append({
            "name": name,
            "ticker": tk,
            "value": None if cur is None else round(cur, 2),
            "delta1d": None if d1 is None else round(d1, 2)
        })

    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "s-maxage=60, stale-while-revalidate=300"
    }
    return (json.dumps({"asOf": str(today), "items": out}), 200, headers)