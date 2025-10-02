# api/quotes.py
import json
from datetime import date, timedelta

# Schnelle, robuste Quotes-API für Vercel
def handler(request):
    # Lazy-Import -> schnellerer Kaltstart, bessere Fehlermeldungen
    try:
        import yfinance as yf
        import pandas as pd
    except Exception as e:
        return _resp({"error": f"Import error: {e.__class__.__name__}: {e}"}, 500)

    TICKERS = {
        "S&P 500": "^GSPC",
        "DAX": "^GDAXI",
        "WTI Oil": "CL=F",
        "Gold": "GC=F",
        "Bitcoin": "BTC-USD",
        "VIX": "^VIX",
    }

    def series_last(s):
        return None if s is None or s.empty else float(s.iloc[-1])

    def prev(s, n):
        if s is None or s.empty or len(s) <= n:
            return None
        return float(s.iloc[-(n+1)])

    def delta_pct(cur, p):
        if cur is None or p is None or p == 0:
            return None
        return (cur - p) / p * 100.0

    try:
        # Verwende 'period' statt start/end -> stabiler/schneller bei Yahoo
        period = "3mo"  # ~90 Tage
        symbols = list(TICKERS.values())

        # EIN Batch-Call zuerst
        df = yf.download(
            tickers=symbols,
            period=period,
            interval="1d",
            auto_adjust=True,
            group_by="ticker",
            threads=True,
            progress=False,
        )

        def close_series(df, tk: str):
            try:
                if isinstance(df.columns, pd.MultiIndex):
                    s = df[tk]["Close"]
                else:
                    s = df["Close"]
                s = s.dropna().astype(float)
                if s.empty:
                    return None
                return s
            except Exception:
                return None

        items = []
        missing = []

        # Versuche erst aus dem Batch zu lesen
        for name, tk in TICKERS.items():
            s = close_series(df, tk)
            if s is None:
                missing.append((name, tk))
                continue
            cur = series_last(s)
            p1 = prev(s, 1)
            d1 = delta_pct(cur, p1)
            items.append({
                "name": name, "ticker": tk,
                "value": None if cur is None else round(cur, 4),
                "delta1d": None if d1 is None else round(d1, 2),
            })

        # Fallback pro fehlendem Ticker (selten nötig)
        for name, tk in missing:
            try:
                h = yf.Ticker(tk).history(period=period, interval="1d")
                s = h["Close"].dropna().astype(float) if not h.empty else None
                cur = series_last(s)
                p1 = prev(s, 1)
                d1 = delta_pct(cur, p1)
                items.append({
                    "name": name, "ticker": tk,
                    "value": None if cur is None else round(cur, 4),
                    "delta1d": None if d1 is None else round(d1, 2),
                })
            except Exception:
                items.append({
                    "name": name, "ticker": tk,
                    "value": None, "delta1d": None
                })

        body = {"asOf": str(date.today()), "items": items}
        # Edge-Cache: schnell, trotzdem max 60s alt
        return _resp(body, 200, cache="s-maxage=60, stale-while-revalidate=300")

    except Exception as e:
        # NIEMALS blank 500 – immer Fehlertext zurückgeben
        return _resp({"error": f"{e.__class__.__name__}: {e}"}, 500)

def _resp(body: dict, status: int, cache: str | None = None):
    headers = {"Content-Type": "application/json"}
    if cache:
        headers["Cache-Control"] = cache
    return (json.dumps(body), status, headers)