# api/watchlist.py
from http.server import BaseHTTPRequestHandler
import json
from datetime import date, timedelta

ALLOWED_ORIGIN = "*"

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
            return self._send({"error": f"Import error: {e}"}, 500)

        # 👉 Hardcoded Watchlist (kannst du später dynamisieren)
        WATCH = {
            "Apple": "AAPL",
            "NVIDIA": "NVDA",
            "Meta": "META",
            "AMEX": "AXP",
            "Oracle": "ORCL",
            "Airbus": "1AIR.PA",
            "Tesla": "TSLA",
            "Auto1": "AG1.DE", 
            
        }

        def series_last(s):
            return None if s is None or s.empty else float(s.iloc[-1])
        def prev(s, n):
            if s is None or s.empty or len(s) <= n: return None
            return float(s.iloc[-(n+1)])
        def pct(cur, base):
            if cur is None or base is None or base == 0: return None
            return (cur - base) / base * 100.0

        try:
            # Batch-Download für Δ1d-Preis
            df = yf.download(
                tickers=list(WATCH.values()),
                period="5d", interval="1d",
                auto_adjust=True, group_by="ticker",
                threads=True, progress=False
            )
        except Exception as e:
            return self._send({"error": f"Download error: {e}"}, 500)

        items = []
        for name, tk in WATCH.items():
            # Preis + Δ1d
            try:
                if isinstance(df.columns, pd.MultiIndex):
                    s = df[tk]["Close"].dropna().astype(float)
                else:
                    s = df["Close"].dropna().astype(float)
            except Exception:
                s = None

            cur = series_last(s)
            p1d = prev(s, 1)
            d1 = pct(cur, p1d)

            # Fundamentals (schnell): fast_info, Fallback info
            mcap = pe = vol = None
            try:
                t = yf.Ticker(tk)
                fi = getattr(t, "fast_info", {}) or {}
                mcap = fi.get("market_cap")
                vol = fi.get("regular_market_volume") or fi.get("ten_day_average_volume")
                # trailing PE kann in fast_info "trailing_pe" heißen; sonst aus info
                pe = fi.get("trailing_pe")
                if pe is None:
                    inf = t.info or {}
                    pe = inf.get("trailingPE")
                    if mcap is None: mcap = inf.get("marketCap")
                    if vol is None:  vol = inf.get("volume")
            except Exception:
                pass

            items.append({
                "name": name,
                "ticker": tk,
                "price": None if cur is None else round(cur, 2),
                "delta1d": None if d1 is None else round(d1, 2),
                "marketCap": mcap,
                "pe": None if pe is None else float(pe),
                "volume": vol,
                "currency": inf.get("currency") if inf else fi.get("currency", "USD"),
            })

        return self._send({"asOf": str(date.today()), "items": items},
                          200, cache="s-maxage=60, stale-while-revalidate=300")

    def _send(self, body: dict, status: int, cache: str | None = None):
        data = json.dumps(body).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        if cache: self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(data)