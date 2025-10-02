'use client';
import { useEffect, useState } from 'react';

type Item = { name: string; value: number|null; delta1d: number|null; };
type ApiResp = { asOf?: string; items?: Item[]; error?: string };

export default function HomePage() {
  const [data, setData] = useState<ApiResp | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const res = await fetch('/api/quotes', { cache: 'no-store' });
      const j: ApiResp = await res.json();
      if (!res.ok || j.error) {
        throw new Error(j.error || `HTTP ${res.status}`);
      }
      setData(j);
    } catch (e: any) {
      setErr(e.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <main className="max-w-6xl mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">📊 Daily Market Dashboard</h1>

      {loading && <p>Lade Daten…</p>}

      {!loading && err && (
        <div style={{background:'#fee2e2', border:'1px solid #fecaca', padding:'8px', borderRadius:'8px', color:'#991b1b'}}>
          <strong>API-Fehler:</strong> {err}
          <div className="mt-2">
            <button onClick={load} style={{padding:'6px 10px', border:'1px solid #991b1b', borderRadius:'6px'}}>Erneut versuchen</button>
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
                <div className={`delta ${ (it.delta1d ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {it.delta1d != null ? `${it.delta1d > 0 ? '+' : ''}${it.delta1d}% (1d)` : '–'}
                </div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs opacity-70">Stand: {data.asOf ?? '–'} • Yahoo Finance (verzögert)</p>
        </>
      )}
    </main>
  );
}