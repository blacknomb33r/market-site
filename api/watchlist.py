# api/watchlist.py
from http.server import BaseHTTPRequestHandler
import json
from datetime import date, datetime, timedelta

ALLOWED_ORIGIN = "*"  # für lokal/Preview ok. In Prod ggf. deine Domain setzen.

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

        # ---- Hardcoded Watchlist (beliebig anpassen) ----
        WATCH = {
            "Apple": "AAPL",
            "Microsoft": "MSFT",
            "NVIDIA": "NVDA",
            "Amazon": "AMZN",
            "Alphabet (Class A)": "GOOGL",
            "Meta": "META",
            "Tesla": "TSLA",
            "Auto1 Group": "AG1.DE",  # EUR-Beispiel
        }

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

        def last(s): 
            return None if s is None or s.empty else float(s.iloc[-1])

        def prev(s, n):
            if s is None or s.empty or len(s) <= n:
                return None
            return float(s.iloc[-(n+1)])

        def pct(cur, base):
            if cur is None or base is None or base == 0:
                return None
            return (cur - base) / base * 100.0

        today = date.today()
        start_ytd = datetime(today.year, 1, 1)
        start_mtd = datetime(today.year, today.month, 1)
        end_dt = today + timedelta(days=1)

        tickers = list(WATCH.values())

        # ---- Batch: 1y Historie (für MTD/YTD) + 7d (für Δ1d robust) ----
        try:
            df_1y = yf.download(
                tickers=tickers,
                start=start_ytd.isoformat(),
                end=end_dt.isoformat(),
                interval="1d",
                auto_adjust=True,
                group_by="ticker",
                threads=True,
                progress=False,
            )
            df_7d = yf.download(
                tickers=tickers,
                period="7d",
                interval="1d",
                auto_adjust=True,
                group_by="ticker",
                threads=True,
                progress=False,
            )
        except Exception as e:
            return self._send({"error": f"Download error: {e}"}, 500)

        items = []

        for name, tk in WATCH.items():
            # --- Historie aus Batch ziehen ---
            s_ytd = close_series(df_1y, tk)
            s_7d  = close_series(df_7d, tk)

            # Fallback: Einzelabruf, falls Batch für diesen Ticker leer
            if (s_ytd is None) or (s_7d is None):
                try:
                    h1 = yf.Ticker(tk).history(period="1y", interval="1d", auto_adjust=True)
                    if s_ytd is None and not h1.empty:
                        s_ytd = h1["Close"].dropna().astype(float)
                    h7 = yf.Ticker(tk).history(period="7d", interval="1d", auto_adjust=True)
                    if s_7d is None and not h7.empty:
                        s_7d = h7["Close"].dropna().astype(float)
                except Exception:
                    pass

            cur = last(s_7d if s_7d is not None else s_ytd)
            p1d = prev(s_7d if s_7d is not None else s_ytd, 1)
            d1  = pct(cur, p1d)

            # MTD-Basis (erster Close >= Monatsanfang)
            m_base = None
            try:
                if s_ytd is not None and not s_ytd.empty:
                    s_m = s_ytd[s_ytd.index >= pd.Timestamp(start_mtd)]
                    if not s_m.empty:
                        m_base = float(s_m.iloc[0])
            except Exception:
                m_base = None
            mtd = pct(cur, m_base) if cur is not None else None

            # YTD-Basis (erster Close >= Jahresanfang)
            y_base = None
            try:
                if s_ytd is not None and not s_ytd.empty:
                    s_y = s_ytd[s_ytd.index >= pd.Timestamp(start_ytd)]
                    if not s_y.empty:
                        y_base = float(s_y.iloc[0])
            except Exception:
                y_base = None
            ytd = pct(cur, y_base) if cur is not None else None

            # ---- Fundamentals ----
            mcap = pe = vol = None
            currency = None
            try:
                t = yf.Ticker(tk)
                # fast_info (schnell)
                try:
                    fi = getattr(t, "fast_info", None) or {}
                    if isinstance(fi, dict) and fi:
                        mcap = fi.get("market_cap", mcap)
                        vol  = fi.get("regular_market_volume", vol) or fi.get("ten_day_average_volume", vol)
                        pe   = fi.get("trailing_pe", pe)
                        currency = fi.get("currency", currency)
                except Exception:
                    pass
                # info (Fallback)
                if mcap is None or vol is None or pe is None or currency is None:
                    try:
                        inf = t.info or {}
                        if mcap is None: mcap = inf.get("marketCap", mcap)
                        if vol  is None: vol  = inf.get("volume", vol) or inf.get("averageVolume", vol) or inf.get("averageDailyVolume10Day", vol)
                        if pe   is None: pe   = inf.get("trailingPE", pe)
                        if currency is None: currency = inf.get("currency", currency)
                    except Exception:
                        pass
            except Exception:
                pass

            items.append({
                "name": name,
                "ticker": tk,
                "price": None if cur is None else round(cur, 2),
                "delta1d": None if d1 is None else round(d1, 2),
                "mtd": None if mtd is None else round(mtd, 2),
                "ytd": None if ytd is None else round(ytd, 2),
                "marketCap": None if mcap is None else float(mcap),
                "pe": None if pe is None else float(pe),
                "volume": None if vol is None else float(vol),
                "currency": currency or "",
            })

        return self._send(
            {"asOf": str(today), "items": items},
            200,
            cache="s-maxage=60, stale-while-revalidate=300"
        )

    # ---- helpers ----
    def _send(self, body: dict, status: int, cache: str | None = None):
        data = json.dumps(body).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        if cache:
            self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(data)