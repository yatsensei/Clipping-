"use client";

import { useEffect, useState } from "react";
import {
  API_BASE,
  paths,
  type CircuitListItem,
  type Geometry,
} from "@/lib/api";
import { TOKENS } from "@/lib/track";

/**
 * Grid of circuits with mini outlines. Selecting one swaps the analysis view in place —
 * no navigation, no full reload.
 *
 * Outlines are fetched lazily and cached in module scope, so switching back to a circuit
 * already seen is instant and the grid does not fire 21 requests on mount.
 */
const outlineCache = new Map<string, string>();

async function fetchOutline(id: string): Promise<string> {
  const cached = outlineCache.get(id);
  if (cached) return cached;
  // Built through `paths`, not by hand: the static snapshot serves files, so the URL
  // needs a .json suffix that a hand-written path silently omitted, 404ing every outline.
  const res = await fetch(`${API_BASE}${paths.geometry(id)}`);
  if (!res.ok) throw new Error(`outline for ${id}`);
  const geo: Geometry = await res.json();

  const minX = Math.min(...geo.x_m);
  const maxX = Math.max(...geo.x_m);
  const minY = Math.min(...geo.y_m);
  const maxY = Math.max(...geo.y_m);
  const span = Math.max(maxX - minX, maxY - minY, 1);
  const scale = 88 / span;
  const offX = (100 - (maxX - minX) * scale) / 2;
  const offY = (100 - (maxY - minY) * scale) / 2;

  // Every 3rd point: a 100px thumbnail cannot resolve 5 m spacing anyway.
  const d =
    geo.x_m
      .filter((_, i) => i % 3 === 0)
      .map((x, i) => {
        const y = geo.y_m[i * 3];
        const px = offX + (x - minX) * scale;
        const py = 100 - offY - (y - minY) * scale;
        return `${i === 0 ? "M" : "L"}${px.toFixed(1)},${py.toFixed(1)}`;
      })
      .join(" ") + " Z";

  outlineCache.set(id, d);
  return d;
}

function MiniTrack({ id, active }: { id: string; active: boolean }) {
  const [d, setD] = useState<string | null>(outlineCache.get(id) ?? null);

  useEffect(() => {
    let alive = true;
    if (!d) {
      fetchOutline(id)
        .then((path) => alive && setD(path))
        .catch(() => alive && setD(null));
    }
    return () => {
      alive = false;
    };
  }, [id, d]);

  return (
    <svg viewBox="0 0 100 100" className="w-full h-14" aria-hidden="true">
      {d ? (
        <path
          d={d}
          fill="none"
          stroke={active ? TOKENS.deploy : TOKENS.muted}
          strokeWidth={active ? 3 : 2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      ) : (
        <circle cx={50} cy={50} r={2} fill={TOKENS.line} />
      )}
    </svg>
  );
}

export function CircuitSelector({
  circuits,
  selected,
  onSelect,
}: {
  circuits: CircuitListItem[];
  selected: string;
  onSelect: (id: string) => void;
}) {
  return (
    <div
      className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-3 xl:grid-cols-4 gap-1.5"
      role="listbox"
      aria-label="Circuit"
    >
      {circuits.map((c) => {
        const active = c.circuit_id === selected;
        return (
          <button
            key={c.circuit_id}
            role="option"
            aria-selected={active}
            disabled={!c.has_strategy}
            onClick={() => onSelect(c.circuit_id)}
            className={`focus-ring rounded border p-1.5 text-left transition-colors ${
              active
                ? "border-deploy bg-panel-high"
                : "border-line hover:border-muted"
            } ${!c.has_strategy ? "opacity-30 cursor-not-allowed" : ""}`}
            title={`${c.event_name} — ${c.provenance}`}
          >
            <MiniTrack id={c.circuit_id} active={active} />
            <div className="mt-1 flex items-baseline justify-between gap-1">
              <span className="truncate text-[10px] text-ink">
                {c.location}
              </span>
              <span className="tabular text-[9px] text-muted">
                R{c.round_number}
              </span>
            </div>
            {c.is_fallback && (
              <span className="text-[9px] text-clip">{c.data_year} geometry</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
