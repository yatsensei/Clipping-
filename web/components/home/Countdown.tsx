"use client";

import { useEffect, useState } from "react";

/**
 * Time until lights-out. The server renders the placeholder and the numbers appear
 * after mount: a countdown computed during server render is wrong by the time it is
 * read, and would mismatch the client's first paint.
 */
export function Countdown({ to }: { to: string }) {
  const [remaining, setRemaining] = useState<number | null>(null);

  useEffect(() => {
    const target = new Date(to).getTime();
    const tick = () => setRemaining(Math.max(0, target - Date.now()));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [to]);

  if (remaining == null) {
    return (
      <div className="tabular text-2xl text-muted" aria-hidden="true">
        —
      </div>
    );
  }
  if (remaining === 0) {
    return <div className="display text-2xl text-deploy">Lights out</div>;
  }

  const s = Math.floor(remaining / 1000);
  const parts = [
    { v: Math.floor(s / 86400), u: "d" },
    { v: Math.floor((s % 86400) / 3600), u: "h" },
    { v: Math.floor((s % 3600) / 60), u: "m" },
    { v: s % 60, u: "s" },
  ];
  // Drop leading zero units so a race in two hours does not read "0d 2h".
  const first = parts.findIndex((p) => p.v > 0);
  const shown = parts.slice(Math.max(0, Math.min(first, 2)));

  return (
    <div className="tabular flex items-baseline gap-3 text-2xl text-ink" aria-live="off">
      {shown.map((p) => (
        <span key={p.u}>
          {String(p.v).padStart(2, "0")}
          <span className="ml-0.5 text-xs text-muted">{p.u}</span>
        </span>
      ))}
    </div>
  );
}
