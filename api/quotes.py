# api/quotes.py
from http.server import BaseHTTPRequestHandler
import json
from datetime import date, datetime, timedelta
ALLOWED_ORIGIN = "*"  # oder "http://localhost:3000"

class handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        try:
            import yfinance as yf
            import pandas as pd
            from yfinance import set_tz_cache_location
            set_tz_cache_location("/tmp/py-yfinance")
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

        def pct(cur, base):
            if cur is None or base is None or base == 0:
                return None
            return (cur - base) / base * 100.0

        def close_series(df, tk: str):
            # df kann MultiIndex (mehrere Ticker) oder single sein
            try:
                if isinstance(df.columns, pd.MultiIndex):
                    s = df[tk]["Close"]
                else:
                    s = df["Close"]
                s = s.dropna().astype(float)
                return None if s.empty else s
            except Exception:
                return None

        # --- Daten laden: 1 Jahr (für YTD) + 3 Monate (schnell) ---
        try:
            sy = (date.today() - timedelta(days=366)).isoformat()
            df_1y = yf.download(
                tickers=list(TICKERS.values()),
                start=sy, end=(date.today() + timedelta(days=1)).isoformat(),
                interval="1d", auto_adjust=True, group_by="ticker", threads=True, progress=False
            )
            df_3m = yf.download(
                tickers=list(TICKERS.values()),
                period="3mo", interval="1d",
                auto_adjust=True, group_by="ticker", threads=True, progress=False
            )
        except Exception as e:
            return self._send_json({"error": f"Download error: {e.__class__.__name__}: {e}"}, 500)

        items = []

        # Grenzen für MTD / YTD
        today = date.today()
        m_start = datetime(today.year, today.month, 1)
        y_start = datetime(today.year, 1, 1)

        for name, tk in TICKERS.items():
            # Historien aus beiden Frames ziehen
            s3 = close_series(df_3m, tk)
            s1 = close_series(df_1y, tk)

            # Fallback, wenn im Batch was fehlt -> Einzelabruf
            if s3 is None or s1 is None:
                try:
                    h1 = yf.Ticker(tk).history(period="1y", interval="1d", auto_adjust=True)
                    s1 = h1["Close"].dropna().astype(float) if not h1.empty else None
                    h3 = yf.Ticker(tk).history(period="3mo", interval="1d", auto_adjust=True)
                    s3 = h3["Close"].dropna().astype(float) if not h3.empty else None
                except Exception:
                    s1 = s1 if s1 is not None else None
                    s3 = s3 if s3 is not None else None

            # Aktueller Wert & 1d
            cur = series_last(s3 if s3 is not None else s1)
            p1d = prev(s3 if s3 is not None else s1, 1)
            d1 = pct(cur, p1d)

            # MTD: erster Close ab Monatsanfang in s1 (oder s3, wenn Monat jung ist)
            m_base = None
            if s1 is not None and not s1.empty:
                s1m = s1[s1.index >= pd.Timestamp(m_start)]
                if not s1m.empty:
                    m_base = float(s1m.iloc[0])
            elif s3 is not None and not s3.empty:
                s3m = s3[s3.index >= pd.Timestamp(m_start)]
                if not s3m.empty:
                    m_base = float(s3m.iloc[0])
            mtd = pct(cur, m_base) if (cur is not None) else None

            # YTD: erster Close ab Jahresanfang in s1
            y_base = None
            if s1 is not None and not s1.empty:
                s1y = s1[s1.index >= pd.Timestamp(y_start)]
                if not s1y.empty:
                    y_base = float(s1y.iloc[0])
            ytd = pct(cur, y_base) if (cur is not None) else None

            items.append({
                "name": name,
                "ticker": tk,
                "value": None if cur is None else round(cur, 4),
                "delta1d": None if d1  is None else round(d1, 2),
                "mtd": None if mtd is None else round(mtd, 2),
                "ytd": None if ytd is None else round(ytd, 2),
            })

        body = {"asOf": str(today), "items": items}
        return self._send_json(body, 200, cache="s-maxage=60, stale-while-revalidate=300")

    # ---------- helpers ----------
    def _send_json(self, body: dict, status: int, cache: str | None = None):
        data = json.dumps(body).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        if cache:
            self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(data)