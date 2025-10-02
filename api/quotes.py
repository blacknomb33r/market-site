# api/quotes.py
from http.server import BaseHTTPRequestHandler
import json
from datetime import date, datetime, timedelta
import pandas as pd

ALLOWED_ORIGIN = "*"  # oder "http://localhost:3000"

# ... bestehende imports + Handler bleiben ...

class handler(BaseHTTPRequestHandler):
    # _cors, do_OPTIONS etc. bleiben

    def do_GET(self):
        try:
            import urllib.parse as up
            import yfinance as yf
            import pandas as pd
            from datetime import date, datetime, timedelta
            from yfinance import set_tz_cache_location
            set_tz_cache_location("/tmp/py-yfinance")
        except Exception as e:
            return self._send({"error": f"Import error: {e}"}, 500)

        # 1) Standard-Map für Quick Overview (wie bisher)
        DEFAULT_TICKERS = {
            "S&P 500": "^GSPC",
            "Nasdaq": "^IXIC",
            "DAX": "^GDAXI",
            "EuroStoxx 50": "^STOXX50E",
            "Nikkei 225": "^N225",
            "WTI Oil": "CL=F",
            "Brent Oil": "BZ=F",
            "Gold": "GC=F",
            "Silver": "SI=F",
            "Platinum": "PL=F",
            "Bitcoin": "BTC-USD",
            "Ethereum": "ETH-USD",
            "VIX": "^VIX",
        }

        # 2) Query-Param ?symbols=AAPL,MSFT,NVDA (optional)
        #    Wenn gesetzt: wir verwenden genau diese Symbole und nehmen Namen aus Yahoo (shortName / symbol)
        q = up.urlparse(self.path).query
        params = up.parse_qs(q)
        symbols_arg = params.get("symbols", [None])[0]
        if symbols_arg:
            symbols = [s.strip() for s in symbols_arg.split(",") if s.strip()]
            # Namen dynamisch aus Yahoo holen
            tickers_map = {}
            for sym in symbols:
                try:
                    t = yf.Ticker(sym)
                    info = t.fast_info if getattr(t, "fast_info", None) else {}
                    short = None
                    # Fallback auf .info falls nötig
                    if not info:
                        try:
                            meta = t.info or {}
                            short = meta.get("shortName") or meta.get("longName") or sym
                        except Exception:
                            short = sym
                    else:
                        # fast_info hat keinen Namen → später nochmal .info
                        try:
                            meta = t.info or {}
                            short = meta.get("shortName") or meta.get("longName") or sym
                        except Exception:
                            short = sym
                    tickers_map[short or sym] = sym
                except Exception:
                    tickers_map[sym] = sym
        else:
            tickers_map = DEFAULT_TICKERS

        # ===== ab hier bleibt deine bestehende Berechnungslogik für Δ1d/MTD/YTD =====
        # nutzt 'tickers_map' statt 'TICKERS'

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

        # robustes Base-Value (Weekend/Feiertage) → asfreq/ffill
        def base_from(series, start_dt, pd_module):
            if series is None or series.empty:
                return None
            s = series.copy()
            s = s.asfreq("D", method="ffill")
            ts = pd_module.Timestamp(start_dt).normalize()
            if ts < s.index[0]:
                return float(s.iloc[0])
            s2 = s.reindex(s.index.union([ts])).sort_index().ffill()
            try:
                return float(s2.loc[ts])
            except Exception:
                return float(s.iloc[0])

        today = date.today()
        start_ytd = datetime(today.year, 1, 1)
        start_mtd = datetime(today.year, today.month, 1)
        end_dt = today + timedelta(days=1)

        syms = list(tickers_map.values())

        try:
            df_ytd = yf.download(
                tickers=syms,
                start=start_ytd.isoformat(),
                end=end_dt.isoformat(),
                interval="1d",
                auto_adjust=True,
                group_by="ticker",
                threads=True,
                progress=False,
            )
            df_7d = yf.download(
                tickers=syms,
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

        for label, tk in tickers_map.items():
            s_ytd = close_series(df_ytd, tk)
            s_7d  = close_series(df_7d, tk)

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

            m_base = base_from(s_ytd, start_mtd, pd)
            y_base = base_from(s_ytd, start_ytd, pd)

            mtd = pct(cur, m_base) if cur is not None and m_base is not None else None
            ytd = pct(cur, y_base) if cur is not None and y_base is not None else None

            # Bonus: currency/typ (für Frontend-Formatierung nützlich)
            currency = ""
            try:
                t = yf.Ticker(tk)
                fi = getattr(t, "fast_info", None) or {}
                if isinstance(fi, dict) and fi:
                    currency = fi.get("currency") or currency
                if not currency:
                    meta = t.info or {}
                    currency = meta.get("currency", "")
            except Exception:
                pass

            items.append({
                "name": label,      # bei symbols=… ist das meist shortName
                "ticker": tk,
                "value": None if cur is None else round(cur, 4),
                "delta1d": None if d1 is None else round(d1, 2),
                "mtd": None if mtd is None else round(mtd, 2),
                "ytd": None if ytd is None else round(ytd, 2),
                "currency": currency,
            })

        return self._send(
            {"asOf": str(today), "items": items},
            200,
            cache="s-maxage=60, stale-while-revalidate=300"
        )
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