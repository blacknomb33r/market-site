'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';

type Item = {
  name: string;
  value: number | null;
  delta1d: number | null;
};

type ApiResp = {
  asOf?: string;
  items?: Item[];
  error?: string;
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

export default function HomePage() {
  const [data, setData] = useState<ApiResp | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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
    } catch (e: any) {
      console.error('quotes fetch failed:', e);
      setErr(e?.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <main className="max-w-6xl mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">📊 Daily Market Dashboard</h1>

      {/* Horizontale Börsenzeiten-Leiste (fest auf Europe/Berlin) */}
      <MarketBar />

      <h2 className="section-title">Quick Overview</h2>

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
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {data.items.map((it) => (
              <div key={it.name} className="card">
                <h2>{it.name}</h2>
                <div className="value">{it.value ?? '–'}</div>
                <div
                  className={`delta ${
                    (it.delta1d ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}
                >
                  {it.delta1d != null
                    ? `${it.delta1d > 0 ? '+' : ''}${it.delta1d}% (1d)`
                    : '–'}
                </div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs opacity-70">
            Stand: {data.asOf ?? '–'} • Yahoo Finance (verzögert)
          </p>
        </>
      )}
    </main>
  );
}