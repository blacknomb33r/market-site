# api/watchlist.py
from http.server import BaseHTTPRequestHandler
import json
from datetime import date, datetime, timedelta

ALLOWED_ORIGIN = "*"  # in Prod auf deine Domain einschränken

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
            # --- Imports + yfinance-Cachepfad für Serverless ---
            try:
                import yfinance as yf
                import pandas as pd
            except Exception as e:
                return self._send({"error": f"Import error: {type(e).__name__}: {e}"}, 500)

            try:
                try:
                    from yfinance import set_tz_cache_location
                except Exception:
                    from yfinance.utils import set_tz_cache_location
                set_tz_cache_location("/tmp/py-yfinance")
            except Exception:
                pass

            # ==== Deine Watchlist ====
            WATCH = {
                "Apple": "AAPL",
                "Microsoft": "MSFT",
                "NVIDIA": "NVDA",
                "Amazon": "AMZN",
                "Alphabet (Class A)": "GOOGL",
                "Meta": "META",
                "Tesla": "TSLA",
                "Auto1 Group": "AG1.DE",  # EUR
                "Airbus": "AIR.PA",       # EUR
            }

            # ---------- Helper wie in quotes.py ----------
            def close_series(df, tk: str):
                """Close-Serie aus evtl. MultiIndex-DataFrame ziehen."""
                try:
                    if df is None or getattr(df, "empty", True):
                        return None
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

            def base_from(series, start_dt):
                """
                Robuste Basis am Monats-/Jahresanfang:
                - auf Tagesfrequenz bringen
                - forward-fill
                - Wert am exakten Startdatum nehmen (WE/Feiertage unkritisch)
                """
                if series is None or series.empty:
                    return None
                s = series.copy()
                if not isinstance(s.index, pd.DatetimeIndex):
                    s.index = pd.to_datetime(s.index)
                s = s.asfreq("D", method="ffill")
                ts = pd.Timestamp(start_dt).normalize()
                if ts < s.index[0]:
                    return float(s.iloc[0])
                s2 = s.reindex(s.index.union([ts])).sort_index().ffill()
                try:
                    return float(s2.loc[ts])
                except Exception:
                    return float(s.iloc[0])

            # ---------- Zeitfenster ----------
            today = date.today()
            start_ytd = datetime(today.year, 1, 1)
            start_mtd = datetime(today.year, today.month, 1)
            end_dt = today + timedelta(days=1)

            tickers = list(WATCH.values())

            # ---------- Batch-Download wie in quotes.py (YTD + 7d) ----------
            try:
                df_ytd = yf.download(
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
                return self._send({"error": f"Download error: {type(e).__name__}: {e}"}, 502)

            items = []
            for name, tk in WATCH.items():
                try:
                    # Historien
                    s_ytd = close_series(df_ytd, tk)
                    s_7d  = close_series(df_7d, tk)

                    # Fallback: Einzelabruf, falls Batch leer
                    if (s_ytd is None) or (s_7d is None):
                        try:
                            t_single = yf.Ticker(tk)
                            h1 = t_single.history(period="1y", interval="1d", auto_adjust=True)
                            if s_ytd is None and not h1.empty:
                                s_ytd = h1["Close"].dropna().astype(float)
                            h7 = t_single.history(period="7d", interval="1d", auto_adjust=True)
                            if s_7d is None and not h7.empty:
                                s_7d = h7["Close"].dropna().astype(float)
                        except Exception:
                            pass

                    cur = last(s_7d if s_7d is not None else s_ytd)
                    p1d = prev(s_7d if s_7d is not None else s_ytd, 1)
                    d1  = pct(cur, p1d)

                    m_base = base_from(s_ytd, start_mtd)
                    y_base = base_from(s_ytd, start_ytd)
                    mtd = pct(cur, m_base) if cur is not None and m_base is not None else None
                    ytd = pct(cur, y_base) if cur is not None and y_base is not None else None

                    # -------- Zusatzinfos (Currency, MC, P/E, Vol) --------
                    currency = ""
                    market_cap = pe = volume = None
                    try:
                        t = yf.Ticker(tk)

                        # fast_info (schnell)
                        fi = getattr(t, "fast_info", None)
                        if fi:
                            # Namespace (neue yfinance) ODER dict (alte)
                            def get_fi(key):
                                return getattr(fi, key) if not isinstance(fi, dict) else fi.get(key)
                            currency   = get_fi("currency") or currency
                            market_cap = market_cap or get_fi("market_cap")
                            volume     = volume or get_fi("regular_market_volume") or get_fi("ten_day_average_volume")
                            pe         = pe or get_fi("trailing_pe")

                        # info (fallback, langsamer)
                        info = t.info or {}
                        if not currency:                  currency   = info.get("currency", "")
                        if market_cap is None:           market_cap = info.get("marketCap")
                        if volume is None:               volume     = info.get("volume") or info.get("averageVolume") or info.get("averageDailyVolume10Day")
                        if pe is None:                   pe         = info.get("trailingPE")
                    except Exception:
                        pass

                    items.append({
                        "name": name,
                        "ticker": tk,
                        "price": None if cur is None else round(cur, 2),
                        "delta1d": None if d1 is None else round(d1, 2),
                        "mtd": None if mtd is None else round(mtd, 2),
                        "ytd": None if ytd is None else round(ytd, 2),
                        "currency": currency or "",
                        "marketCap": None if market_cap is None else float(market_cap),
                        "pe": None if pe is None else float(pe),
                        "volume": None if volume is None else float(volume),
                    })
                except Exception as e_item:
                    items.append({
                        "name": name, "ticker": tk,
                        "price": None, "delta1d": None, "mtd": None, "ytd": None,
                        "currency": "", "marketCap": None, "pe": None, "volume": None,
                        "error": f"{type(e_item).__name__}: {e_item}",
                    })

            return self._send(
                {"asOf": str(today), "items": items},
                200,
                cache="s-maxage=60, stale-while-revalidate=300"
            )

        except Exception as e_outer:
            return self._send({"error": f"Unhandled: {type(e_outer).__name__}: {e_outer}"}, 500)

    # ---------- helpers ----------
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