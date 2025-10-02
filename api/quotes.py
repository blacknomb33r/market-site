# api/quotes.py
from http.server import BaseHTTPRequestHandler
import json
from datetime import date, timedelta

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Lazy-Import: schneller Kaltstart, klarere Fehler
            import yfinance as yf
            import pandas as pd
        except Exception as e:
            return self._send_json({"error": f"Import error: {e.__class__.__name__}: {e}"}, 500)

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
            # Stabiler als start/end: period='3mo'
            df = yf.download(
                tickers=list(TICKERS.values()),
                period="3mo",
                interval="1d",
                auto_adjust=True,
                group_by="ticker",
                threads=True,
                progress=False
            )

            def close_series(df, tk: str):
                try:
                    if isinstance(df.columns, pd.MultiIndex):
                        s = df[tk]["Close"]
                    else:
                        s = df["Close"]
                    s = s.dropna().astype(float)
                    return None if s.empty else s
                except Exception:
                    return None

            items = []
            missing = []

            # Erst aus Batch lesen
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

            # Fallback: Einzelabruf (falls Batch-Fehler bei einzelnen Symbolen)
            for name, tk in missing:
                try:
                    h = yf.Ticker(tk).history(period="3mo", interval="1d")
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
                    items.append({"name": name, "ticker": tk, "value": None, "delta1d": None})

            body = {"asOf": str(date.today()), "items": items}
            return self._send_json(body, 200, cache="s-maxage=60, stale-while-revalidate=300")

        except Exception as e:
            return self._send_json({"error": f"{e.__class__.__name__}: {e}"}, 500)

    # ---------- helpers ----------
    def _send_json(self, body: dict, status: int, cache: str | None = None):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        if cache:
            self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(data)