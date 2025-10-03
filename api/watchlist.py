# api/watchlist.py
from http.server import BaseHTTPRequestHandler
import json
from datetime import date, datetime, timedelta

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
            # yfinance Cachepfad in Serverless (schreibbar)
            try:
                try:
                    from yfinance import set_tz_cache_location
                except Exception:
                    from yfinance.utils import set_tz_cache_location
                set_tz_cache_location("/tmp/py-yfinance")
            except Exception:
                pass
        except Exception as e:
            return self._send({"error": f"Import error: {type(e).__name__}: {e}"}, 500)

        # ==== Watchlist ====
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

        # ---- Helpers: Timezone-Utilities ----
        def to_naive_utc_index(idx):
            """DatetimeIndex -> UTC -> tz-naiv. Funktioniert für tz-aware & tz-naiv."""
            dti = pd.to_datetime(idx)
            try:
                if getattr(dti, "tz", None) is not None:
                    # tz-aware -> nach UTC, dann tz-naiv
                    dti = dti.tz_convert("UTC").tz_localize(None)
                else:
                    # tz-naiv -> sicherstellen, dass .tz_localize(None) nicht crasht
                    # (braucht man eigentlich nicht, aber wir lassen es defensiv.)
                    dti = dti.tz_localize(None)
            except Exception:
                # Fallback: als tz-naiv belassen
                pass
            return dti

        def normalize_series_index(s):
            """Sichere Index-Normalisierung für Vergleiche/Resampling."""
            if s is None:
                return None
            s = s.copy()
            s.index = to_naive_utc_index(s.index)
            return s

        # ---- Numerik-Helpers ----
        def pct(cur, base):
            if cur is None or base is None or base == 0:
                return None
            return (cur - base) / base * 100.0

        def safe_series(s):
            if s is None:
                return None
            try:
                s = s.dropna().astype(float)
                if s.empty:
                    return None
                s = normalize_series_index(s)
                return s
            except Exception:
                return None

        def base_from(series, start_dt):
            """
            Robuste Basis am Monats-/Jahresanfang:
            - Index -> UTC tz-naiv
            - auf Tagesfrequenz + ffill
            - exakter Wert am Startdatum (WE/Feiertage egal)
            """
            if series is None:
                return None
            try:
                s = normalize_series_index(series)
                s = s.asfreq("D", method="ffill")
                ts = pd.Timestamp(start_dt)  # tz-naiv
                # Falls Start vor Serienbeginn liegt: ersten Wert nehmen
                if ts < s.index[0]:
                    return float(s.iloc[0])
                # Startdatum sicherstellen & ffill
                s2 = s.reindex(s.index.union([ts])).sort_index().ffill()
                return float(s2.loc[ts])
            except Exception:
                try:
                    return float(series.iloc[0])
                except Exception:
                    return None

        def last(s):
            return None if s is None or s.empty else float(s.iloc[-1])

        def prev(s, n):
            if s is None or s.empty or len(s) <= n:
                return None
            return float(s.iloc[-(n + 1)])

        # ---- Zeitfenster (tz-naiv Datetimes) ----
        today = date.today()
        start_ytd = datetime(today.year, 1, 1)
        start_mtd = datetime(today.year, today.month, 1)

        items = []
        for name, tk in WATCH.items():
            try:
                t = yf.Ticker(tk)

                # 1y Daily Close-Historie (robuster als Batch)
                h1y = t.history(period="1y", interval="1d", auto_adjust=True)
                s = safe_series(h1y["Close"] if "Close" in h1y.columns else None)
                if s is None or len(s) < 2:
                    items.append({
                        "name": name, "ticker": tk,
                        "price": None, "delta1d": None, "mtd": None, "ytd": None,
                        "currency": "", "marketCap": None, "pe": None, "volume": None,
                        "error": "no_series_or_too_short"
                    })
                    continue

                cur = float(s.iloc[-1])
                prev1d = float(s.iloc[-2]) if len(s) >= 2 else None
                d1 = pct(cur, prev1d)

                # MTD / YTD Basen robust bestimmen
                m_base = base_from(s, start_mtd)
                y_base = base_from(s, start_ytd)
                mtd = pct(cur, m_base) if m_base is not None else None
                ytd = pct(cur, y_base) if y_base is not None else None

                # Fundamentals/Currency
                currency = ""
                market_cap = pe = volume = None
                try:
                    fi = getattr(t, "fast_info", None)
                    if fi:
                        def get_fi(key):
                            return getattr(fi, key) if not isinstance(fi, dict) else fi.get(key)
                        currency   = get_fi("currency") or currency
                        market_cap = market_cap or get_fi("market_cap")
                        volume     = volume or get_fi("regular_market_volume") or get_fi("ten_day_average_volume")
                        pe         = pe or get_fi("trailing_pe")
                except Exception:
                    pass
                if market_cap is None or volume is None or pe is None or not currency:
                    try:
                        info = t.info or {}
                        currency   = currency or info.get("currency", "")
                        market_cap = market_cap or info.get("marketCap")
                        volume     = volume or info.get("volume") or info.get("averageVolume") or info.get("averageDailyVolume10Day")
                        pe         = pe or info.get("trailingPE")
                    except Exception:
                        pass

                items.append({
                    "name": name,
                    "ticker": tk,
                    "price": round(cur, 2),
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