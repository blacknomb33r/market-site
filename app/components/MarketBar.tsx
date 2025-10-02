'use client';

import { useEffect, useMemo, useState } from 'react';
import { DateTime, Duration } from 'luxon';

const USER_TZ = 'Europe/Berlin';

type Market = {
  name: string;
  tz: string;
  open: [number, number];
  close: [number, number];
  days: number[];           // 0=Mo ... 6=So (Luxon: Monday=1 ... Sunday=7 → wir rechnen unten um)
  alwaysOpen?: boolean;
};

const MARKETS: Market[] = [
  { name: 'NYSE/Nasdaq',      tz: 'America/New_York', open: [9,30],  close: [16,0],  days: [0,1,2,3,4] },
  { name: 'Xetra (Frankfurt)',tz: 'Europe/Berlin',    open: [9,0],   close: [17,30], days: [0,1,2,3,4] },
  { name: 'LSE (London)',     tz: 'Europe/London',    open: [8,0],   close: [16,30], days: [0,1,2,3,4] },
  { name: 'SIX (Zürich)',     tz: 'Europe/Zurich',    open: [9,0],   close: [17,30], days: [0,1,2,3,4] },
  { name: 'Tokyo (TSE) ',     tz: 'Asia/Tokyo',       open: [9,0],   close: [15,0],  days: [0,1,2,3,4] },
  { name: 'Hong Kong (HKEX)', tz: 'Asia/Hong_Kong',   open: [9,30],  close: [16,0], days: [0,1,2,3,4] },
  { name: 'Crypto (BTC/ETH)', tz: 'UTC',              open: [0,0],   close: [23,59], days: [0,1,2,3,4,5,6], alwaysOpen: true },
];

function formatHM(dt: DateTime) {
  return dt.toFormat('HH:mm');
}

function nextValidDay(dt: DateTime, validDays: number[]) {
  // validDays: 0..6 (Mo..So) ; Luxon: Monday=1..Sunday=7 → normieren
  const luxonToZeroBased = (w: number) => (w % 7); // 7 -> 0
  for (let i = 1; i <= 7; i++) {
    const cand = dt.plus({ days: i });
    if (validDays.includes(luxonToZeroBased(cand.weekday))) return cand;
  }
  return dt.plus({ days: 1 });
}

type View = {
  name: string;
  isOpen: boolean;
  statusText: 'Offen' | 'Geschlossen';
  hoursLocal: string;
  countdown: string;
};

export default function MarketBar() {
  // live tick – 1 Hz
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => (t + 1) % 1_000_000), 1000);
    return () => clearInterval(id);
  }, []);

  // Berechnung bei jedem Tick – sehr leichtgewichtig (nur Zeitmathematik)
  const views = useMemo<View[]>(() => {
    const now = DateTime.now(); // lokale Zeit; wir setzen Zonen explizit
    const luxonToZeroBased = (w: number) => (w % 7); // Monday=1..Sunday=7 -> 0..6

    return MARKETS.map((m) => {
      if (m.alwaysOpen) {
        // 24/7: Stunden in User-Zone anzeigen, statischer "24/7"-Hinweis
        const openLocal  = now.setZone(m.tz).set({ hour: m.open[0], minute: m.open[1], second: 0 }).setZone(USER_TZ);
        const closeLocal = now.setZone(m.tz).set({ hour: m.close[0], minute: m.close[1], second: 0 }).setZone(USER_TZ);
        return {
          name: m.name,
          isOpen: true,
          statusText: 'Offen',
          hoursLocal: `${formatHM(openLocal)}–${formatHM(closeLocal)} (deine Zeit)`,
          countdown: '24/7',
        };
      }

      const nowMkt = now.setZone(m.tz);
      const isTradingDay = m.days.includes(luxonToZeroBased(nowMkt.weekday));

      const openToday = nowMkt.set({
        hour: m.open[0],
        minute: m.open[1],
        second: 0,
        millisecond: 0,
      });
      const closeToday = nowMkt.set({
        hour: m.close[0],
        minute: m.close[1],
        second: 0,
        millisecond: 0,
      });

      const hoursLocal = `${formatHM(openToday.setZone(USER_TZ))}–${formatHM(closeToday.setZone(USER_TZ))} (deine Zeit)`;

      if (isTradingDay && nowMkt >= openToday && nowMkt <= closeToday) {
        // Offen → Countdown bis Close
        const diff = closeToday.diff(nowMkt);
        const dur = Duration.fromMillis(diff.toMillis()).shiftTo('hours', 'minutes', 'seconds');
        const countdown = `schließt in ${String(Math.floor(dur.hours)).padStart(2, '0')}:${String(dur.minutes).padStart(2, '0')}:${String(Math.floor(dur.seconds)).padStart(2, '0')}`;
        return { name: m.name, isOpen: true, statusText: 'Offen', hoursLocal, countdown };
      } else {
        // Geschlossen → Countdown bis nächste Öffnung
        let nextOpen = openToday;
        if (!(isTradingDay && nowMkt < openToday)) {
          const nd = nextValidDay(nowMkt, m.days);
          nextOpen = nd.set({ hour: m.open[0], minute: m.open[1], second: 0, millisecond: 0 });
        }
        const diff = nextOpen.diff(nowMkt);
        const dur = Duration.fromMillis(diff.toMillis()).shiftTo('hours', 'minutes', 'seconds');
        const countdown = `öffnet in ${String(Math.floor(dur.hours)).padStart(2, '0')}:${String(dur.minutes).padStart(2, '0')}:${String(Math.floor(dur.seconds)).padStart(2, '0')}`;
        return { name: m.name, isOpen: false, statusText: 'Geschlossen', hoursLocal, countdown };
      }
    });
  }, [tick]);

  return (
    <>
      <h2 className="section-title">Börsenzeiten &amp; Status</h2>
      <div className="market-bar">
        {views.map((v) => (
          <div key={v.name} className="market-chip">
            <div className="market-title">{v.name}</div>
            <div className={v.isOpen ? 'market-open' : 'market-closed'}>{v.statusText}</div>
            <div className="market-sub">{v.hoursLocal}</div>
            <div className="market-sub">{v.countdown}</div>
          </div>
        ))}
      </div>
    </>
  );
}