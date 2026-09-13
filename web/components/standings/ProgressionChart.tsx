"use client";

import { useMemo } from "react";
import { polyline, ticks } from "@/lib/chart";
import type { Entity, Progression } from "@/lib/f1/types";
import { teamStyle } from "@/lib/teams";
import { TOKENS } from "@/lib/track";

/**
 * Points across the season, one line per entrant, in the same idiom as the telemetry
 * traces: a viewBox stretched to the panel width, HTML axis labels in a gutter so they
 * are not squashed with it, and non-scaling strokes so horizontal runs do not fatten.
 *
 * Only the leading entrants are drawn in colour; the rest are context in grey. Two
 * drivers of one team share a colour and are told apart by a dash.
 */

const WIDTH = 1000;
const HEIGHT = 220;
const GUTTER = 34;
const PAD_TOP = 8;

export function ProgressionChart({
  progression,
  entities,
  highlight,
  cursor,
  onCursor,
}: {
  progression: Progression;
  entities: Record<string, Entity>;
  /** Ids drawn in team colour, in standings order. */
  highlight: string[];
  /** Index into progression.rounds. */
  cursor: number;
  onCursor?: (index: number) => void;
}) {
  const { rounds, points } = progression;
  const n = rounds.length;

  const yMax = useMemo(() => {
    let m = 0;
    for (const series of Object.values(points)) for (const v of series) m = Math.max(m, v ?? 0);
    const marks = ticks(0, m || 10);
    return Math.max(marks[marks.length - 1], m);
  }, [points]);
  const marks = ticks(0, yMax);

  const x = (i: number) => (n > 1 ? (i / (n - 1)) * WIDTH : WIDTH / 2);
  const y = (v: number) => PAD_TOP + (HEIGHT - PAD_TOP) - (v / (yMax || 1)) * (HEIGHT - PAD_TOP);

  const pathOf = (id: string) =>
    polyline(points[id].map((v, i) => (v == null ? null : [x(i), y(v)])));

  // Dash the second driver of each highlighted team.
  const dashed = new Set<string>();
  const seenTeam = new Set<string>();
  for (const id of highlight) {
    const t = entities[id]?.teamId ?? id;
    if (seenTeam.has(t)) dashed.add(id);
    seenTeam.add(t);
  }
  const highlighted = new Set(highlight);
  const muted = progression.ids.filter((id) => !highlighted.has(id));

  return (
    <div className="rounded-lg border border-line bg-panel p-3">
      <div className="flex items-baseline justify-between px-1 pb-2">
        <span className="text-[10px] uppercase tracking-[0.18em] text-muted">
          Points through the season
        </span>
        <span className="text-[10px] text-muted">
          drag or click to scrub
        </span>
      </div>

      <div className="relative" style={{ height: HEIGHT }}>
        <div
          className="pointer-events-none absolute inset-y-0 left-0 z-10"
          style={{ width: GUTTER }}
          aria-hidden="true"
        >
          {marks.map((v) => (
            <span
              key={v}
              className="tabular absolute right-1 -translate-y-1/2 text-[9px] leading-none text-muted"
              style={{ top: y(v) }}
            >
              {v}
            </span>
          ))}
        </div>

        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          preserveAspectRatio="none"
          className="absolute inset-y-0 right-0 cursor-crosshair"
          style={{ left: GUTTER, width: `calc(100% - ${GUTTER}px)`, height: HEIGHT }}
          role="img"
          aria-label="Championship points after each round"
          onPointerDown={(ev) => {
            if (!onCursor) return;
            ev.currentTarget.setPointerCapture(ev.pointerId);
            onCursor(indexAt(ev, n));
          }}
          onPointerMove={(ev) => {
            if (!onCursor || ev.buttons === 0) return;
            onCursor(indexAt(ev, n));
          }}
        >
          {marks.map((v) => (
            <line
              key={v}
              x1={0}
              y1={y(v)}
              x2={WIDTH}
              y2={y(v)}
              stroke={TOKENS.line}
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
              opacity={0.65}
            />
          ))}

          {muted.map((id) => (
            <path
              key={id}
              d={pathOf(id)}
              fill="none"
              stroke={TOKENS.muted}
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
              opacity={0.35}
            />
          ))}

          {highlight.map((id) => (
            <path
              key={id}
              d={pathOf(id)}
              fill="none"
              stroke={teamStyle(entities[id]?.teamId).colour}
              strokeWidth={2}
              strokeDasharray={dashed.has(id) ? "5 4" : undefined}
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
          ))}

          <line
            x1={x(cursor)}
            y1={0}
            x2={x(cursor)}
            y2={HEIGHT}
            stroke={TOKENS.bone}
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
            opacity={0.7}
          />
          {highlight.map((id) => {
            const v = points[id][cursor];
            if (v == null) return null;
            return (
              <circle
                key={id}
                cx={x(cursor)}
                cy={y(v)}
                r={3.5}
                fill={teamStyle(entities[id]?.teamId).colour}
                stroke={TOKENS.panel}
                strokeWidth={1.5}
                vectorEffect="non-scaling-stroke"
              />
            );
          })}
        </svg>
      </div>

      {/* Round numbers under the plot, aligned with the SVG's x range. */}
      <div
        className="tabular mt-1 flex justify-between text-[9px] text-muted"
        style={{ marginLeft: GUTTER }}
        aria-hidden="true"
      >
        {rounds.map((r, i) => (
          <span key={r} className={i === cursor ? "text-ink" : undefined}>
            {r}
          </span>
        ))}
      </div>

      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5" aria-label="Series">
        {highlight.map((id) => {
          const e = entities[id];
          const team = teamStyle(e?.teamId);
          return (
            <li key={id} className="flex items-center gap-2 text-[11px]">
              <svg width="22" height="8" aria-hidden="true">
                <line
                  x1="1"
                  y1="4"
                  x2="21"
                  y2="4"
                  stroke={team.colour}
                  strokeWidth="2"
                  strokeDasharray={dashed.has(id) ? "5 4" : undefined}
                />
              </svg>
              <span className="text-ink">{e?.short ?? id}</span>
              <span className="tabular text-muted">{points[id][cursor] ?? "–"}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function indexAt(ev: React.PointerEvent<SVGSVGElement>, n: number): number {
  const rect = ev.currentTarget.getBoundingClientRect();
  const f = Math.min(Math.max((ev.clientX - rect.left) / rect.width, 0), 1);
  return Math.round(f * (n - 1));
}
