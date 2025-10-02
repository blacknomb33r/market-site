'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';

type Item = {
  name: string;
  value: number | null;
  delta1d: number | null;
  mtd?: number | null;   // NEU (optional)
  ytd?: number | null;   // NEU (optional)
};

type ApiResp = {
  asOf?: string;
  items?: Item[];
  error?: string;
};
type WLItem = {
  name: string;
  ticker: string;
  price: number | null;
  delta1d: number | null;
  marketCap?: number | null;
  pe?: number | null;
  volume?: number | null;
};
type WLResp = { asOf?: string; items?: WLItem[]; error?: string };

const fmtPct = (x: number | null | undefined) =>
  x == null ? '–' : `${x > 0 ? '+' : ''}${x.toFixed(2)}%`;

const fmtUSDabbr = (n?: number | null) => {
  if (n == null) return '–';
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (abs >= 1e12) return `${sign}${(abs/1e12).toFixed(2)}T`;
  if (abs >= 1e9)  return `${sign}${(abs/1e9).toFixed(2)}B`;
  if (abs >= 1e6)  return `${sign}${(abs/1e6).toFixed(2)}M`;
  if (abs >= 1e3)  return `${sign}${(abs/1e3).toFixed(2)}K`;
  return `${sign}${abs.toFixed(0)}`;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '';

const MarketBar = dynamic(() => import('./components/MarketBar'), {
  ssr: false,
  loading: () => (
    <div className="market-bar">
      <div className="market-chip">Lade Börsenzeiten…</div>
    </div>
  ),
});

function formatValue(name: string, value: number | null): string {
  if (value == null) return "–";

  // Rohstoffe (Oil, Gold, Silver, Platinum)
  if (["WTI Oil", "Brent Oil", "Gold", "Silver", "Platinum"].includes(name)) {
    return `$${value.toFixed(2)}`;
  }

  // Krypto (Bitcoin, Ethereum)
  if (["Bitcoin", "Ethereum"].includes(name)) {
    return `$${value.toFixed(2)}`;
  }

  // Yields → % mit 2 Nachkommastellen
  if (name.includes("Yield")) {
    return `${value.toFixed(2)}%`;
  }

  // FX → 4 Nachkommastellen (EUR/USD, USD/JPY, etc.)
  if (name.includes("/") || name.includes("USD/")) {
    return value.toFixed(4);
  }

  // Indizes → 2 Nachkommastellen
  return value.toFixed(2);
}

export default function HomePage() {
  const [data, setData] = useState<ApiResp | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

const [autoRefresh, setAutoRefresh] = useState<boolean>(() => {
  if (typeof window === 'undefined') return true;
  const v = window.localStorage.getItem('autoRefresh');
  return v ? v === 'true' : true; // standard: an
});
const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

const [wl, setWl] = useState<WLResp | null>(null);
const [wlErr, setWlErr] = useState<string | null>(null);
const [wlLoading, setWlLoading] = useState<boolean>(true);

async function loadWatchlist() {
  setWlLoading(true);
  setWlErr(null);
  try {
    const res = await fetch(`${API_BASE}/api/watchlist`, { cache: 'no-store' });
    const j: WLResp = await res.json();
    if (!res.ok || j.error) throw new Error(j.error || `HTTP ${res.status}`);
    setWl(j);
  } catch (e: any) {
    setWlErr(e?.message ?? String(e));
  } finally {
    setWlLoading(false);
  }
}

async function load() {
    setLoading(true);
    setErr(null);
    try {
      const url = `${API_BASE}/api/quotes`; // lokal: absolute URL nach Vercel, prod: /api/quotes
      const res = await fetch(url, { cache: 'no-store' });

      // Versuche erst JSON; wenn das scheitert, lies Text und zeige ihn an
      let body: ApiResp | null = null;
      let raw = '';
      try {
        body = await res.json();
      } catch {
        raw = await res.text(); // HTML-Fehlerseite o.ä.
      }

      if (!res.ok || (body && (body as any).error)) {
        const msg = (body && (body as any).error) || `HTTP ${res.status} ${res.statusText} ${raw?.slice(0,200)}`;
        throw new Error(msg);
      }

      if (!body) throw new Error(`Leere Antwort: ${raw?.slice(0,200)}`);
      setData(body);
      setLastRefresh(new Date());   // NEU
    } catch (e: any) {
      console.error('quotes fetch failed:', e);
      setErr(e?.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }

useEffect(() => { load(); }, []);
useEffect(() => {
  window.localStorage.setItem('autoRefresh', String(autoRefresh));
  if (!autoRefresh) return;

  const id = setInterval(() => {
    load();
  }, 15 * 60 * 1000); // 15 Minuten

  return () => clearInterval(id);
}, [autoRefresh]);

  // Reload, wenn Tab wieder sichtbar ist
useEffect(() => {
  const onVis = () => {
    if (document.visibilityState !== 'visible') return;
    if (!lastRefresh) { load(); return; }
    const diff = Date.now() - lastRefresh.getTime();
    if (diff > 5 * 60 * 1000) load(); // älter als 5 min -> reload
  };
  document.addEventListener('visibilitychange', onVis);
  return () => document.removeEventListener('visibilitychange', onVis);
}, [lastRefresh]);
useEffect(() => { loadWatchlist(); }, []);

  return (
    <main className="max-w-6xl mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">Daily Market Dashboard</h1>

      {/* Horizontale Börsenzeiten-Leiste (fest auf Europe/Berlin) */}
      <MarketBar />

      <div className="flex items-center justify-between">
      <h2 className="section-title">Quick Overview</h2>

      <div className="flex items-center gap-2">
        <button
          className="button"
          onClick={() => load()}
          title="Jetzt aktualisieren"
          aria-label="Jetzt aktualisieren"
        >
          ↻ Refresh
        </button>

        <label className="text-sm muted" style={{display:'inline-flex', alignItems:'center', gap:6}}>
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />
          Auto(15min)
        </label>
      </div>
    </div>

      {loading && <p>Lade Daten…</p>}

      {!loading && err && (
        <div
          style={{
            background: '#fee2e2',
            border: '1px solid #fecaca',
            padding: '8px',
            borderRadius: '8px',
            color: '#991b1b',
            marginBottom: '12px',
          }}
        >
          <strong>API-Fehler:</strong> {err}
          <div style={{ marginTop: 8 }}>
            <button
              onClick={load}
              style={{
                padding: '6px 10px',
                border: '1px solid #991b1b',
                borderRadius: '6px',
                background: 'transparent',
                cursor: 'pointer',
              }}
            >
              Erneut versuchen
            </button>
          </div>
        </div>
      )}

      {!loading && data?.items && (
        <div className="overview-grid">
            {data.items.map((it) => {
                const d1 = it.delta1d;
                const mtd = it.mtd;
                const ytd = it.ytd;

                const d1Txt  = d1  != null ? `${d1 > 0 ? '+' : ''}${d1}%`   : '–';
                const mtdTxt = mtd != null ? `${mtd > 0 ? '+' : ''}${mtd}%` : '–';
                const ytdTxt = ytd != null ? `${ytd > 0 ? '+' : ''}${ytd}%` : '–';
            
                return (
                <div key={it.name} className="overview-chip">
                    <div className="overview-title">{it.name}</div>
                    <div className="overview-value">{formatValue(it.name, it.value)}</div>
                    <div className="overview-sub">
                    <span>Δ 1d: <b className={(d1 ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'}>{d1Txt}</b></span>
                    <span>MTD: {mtdTxt}</span>
                    <span>YTD: {ytdTxt}</span>
                    </div>
                </div>
                );
            })}
            </div>
      )}
    <p className="mt-3 text-xs opacity-70">
    Stand: {data?.asOf ?? '–'}
      {lastRefresh && (
        <> // {lastRefresh.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'})} -  Yahoo Finance</>
    )}
</p>

    <div className="divider"></div>
    {/* ==== Watchlist ==== */}
<h2 className="section-title mt-6">Meine Watchlist</h2>

{wlLoading && <p>Lade Watchlist…</p>}
{wlErr && (
  <div className="bg-red-100 border border-red-300 text-red-800 p-2 rounded mb-2">
    Fehler: {wlErr}
  </div>
)}

{!wlLoading && wl?.items && (
  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
    {wl.items.map((it) => (
      <div key={it.ticker} className="card" style={{ padding: '1rem' }}>
        <h2 className="font-bold mb-1">{it.name} ({it.ticker})</h2>
        <div className="value text-lg">{it.price ?? '–'} USD</div>
        <div
          className={`delta ${
            (it.delta1d ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'
          }`}
        >
          {fmtPct(it.delta1d)} (1d)
        </div>
        <div className="text-xs opacity-80 mt-2">
          MC: {fmtUSDabbr(it.marketCap)} | P/E: {it.pe ?? '–'} | Vol: {fmtUSDabbr(it.volume)}
        </div>
      </div>
    ))}
  </div>
)}
    </main>
  );

  
}