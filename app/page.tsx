'use client';
import { useEffect, useState } from 'react';

type Item = { name: string; value: number|null; delta1d: number|null; };

export default function HomePage() {
  const [data, setData] = useState<{asOf: string; items: Item[]} | null>(null);

  useEffect(() => {
    fetch('/api/quotes')
      .then(r => r.json())
      .then(setData);
  }, []);

  return (
    <main className="max-w-6xl mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">Daily Market Dashboard</h1>
      {!data && <p>Lade Daten…</p>}
      {data && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {data.items.map((it) => (
              <div key={it.name} className="card">
                <h2>{it.name}</h2>
                <div className="value">{it.value ?? '–'}</div>
                <div className={`delta ${it.delta1d! >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {it.delta1d != null ? `${it.delta1d > 0 ? '+' : ''}${it.delta1d}% (1d)` : '–'}
                </div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs opacity-70">Stand: {data.asOf} • Yahoo Finance (verzögert)</p>
        </>
      )}
    </main>
  );
}