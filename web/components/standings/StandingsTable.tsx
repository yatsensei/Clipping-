"use client";

import Link from "next/link";
import { useLayoutEffect, useRef } from "react";
import { Avatar } from "@/components/Avatar";
import type { Entity, StandingsKind, StandingsRow } from "@/lib/f1/types";
import { teamStyle, teamVars } from "@/lib/teams";
import { useReducedMotion } from "@/lib/useReducedMotion";

/**
 * The championship table, with rows that glide to their new places when the round
 * changes.
 *
 * FLIP, by hand: after every commit the layout position of each row is recorded; on
 * the next commit each row is first translated back to where it was, then released
 * to transition to where it now is. Positions come from offsetTop, not
 * getBoundingClientRect, so a scrub mid-animation measures the layout and not the
 * in-flight transform. Rows are a CSS grid with table roles rather than <tr>s, which
 * browsers do not reliably transform.
 */

const EASE = "transform 420ms cubic-bezier(0.2, 0.7, 0.2, 1)";

export function StandingsTable({
  kind,
  rows,
  entities,
  deltas,
  gaps,
}: {
  kind: StandingsKind;
  rows: StandingsRow[];
  entities: Record<string, Entity>;
  deltas: Record<string, number | null>;
  gaps: Record<string, number>;
}) {
  const refs = useRef(new Map<string, HTMLElement>());
  const lastTops = useRef<Map<string, number> | null>(null);
  const reduced = useReducedMotion();

  useLayoutEffect(() => {
    const prev = lastTops.current;
    const next = new Map<string, number>();
    refs.current.forEach((el, id) => next.set(id, el.offsetTop));

    if (prev && !reduced) {
      next.forEach((top, id) => {
        const was = prev.get(id);
        if (was == null || was === top) return;
        const el = refs.current.get(id);
        if (!el) return;
        el.style.transition = "none";
        el.style.transform = `translateY(${was - top}px)`;
        // Force the browser to apply the start position before we animate away from it.
        void el.offsetHeight;
        el.style.transition = EASE;
        el.style.transform = "";
      });
    }
    lastTops.current = next;
  }, [rows, reduced]);

  const base = kind === "drivers" ? "/drivers" : "/teams";

  return (
    <div
      role="table"
      aria-label={kind === "drivers" ? "Drivers' championship" : "Constructors' championship"}
      className="relative overflow-hidden rounded-lg border border-line bg-panel"
    >
      <div
        role="row"
        className="grid grid-cols-[2.75rem_minmax(0,1fr)_4rem_3.5rem] items-center gap-x-3 border-b border-line px-3 py-2 text-[10px] uppercase tracking-[0.18em] text-muted sm:grid-cols-[2.75rem_minmax(0,1fr)_4.5rem_3.5rem_4.5rem_3.5rem]"
      >
        <span role="columnheader">Pos</span>
        <span role="columnheader">{kind === "drivers" ? "Driver" : "Team"}</span>
        <span role="columnheader" className="text-right">Pts</span>
        <span role="columnheader" className="hidden text-right sm:block">Wins</span>
        <span role="columnheader" className="hidden text-right sm:block">Gap</span>
        <span role="columnheader" className="text-right">Δ</span>
      </div>

      <div role="rowgroup" className="relative">
        {rows.map((row) => {
          const e = entities[row.id];
          const label = e?.label ?? row.id;
          const delta = deltas[row.id];
          const team = teamStyle(row.teamId);
          return (
            <div
              key={row.id}
              role="row"
              ref={(el) => {
                if (el) refs.current.set(row.id, el);
                else refs.current.delete(row.id);
              }}
              onTransitionEnd={(ev) => {
                if (ev.propertyName === "transform") ev.currentTarget.style.transition = "";
              }}
              style={teamVars(row.teamId)}
              className="grid grid-cols-[2.75rem_minmax(0,1fr)_4rem_3.5rem] items-center gap-x-3 border-b border-line px-3 py-2 last:border-b-0 sm:grid-cols-[2.75rem_minmax(0,1fr)_4.5rem_3.5rem_4.5rem_3.5rem]"
            >
              <span role="cell" className="tabular text-sm text-ink">
                {row.position}
              </span>

              <span role="cell" className="flex min-w-0 items-center gap-3">
                <span className="team-bar h-8 w-1 shrink-0 rounded-full" aria-hidden="true" />
                <Avatar
                  kind={kind === "drivers" ? "drivers" : "teams"}
                  id={row.id}
                  label={label}
                  teamId={row.teamId}
                  size={32}
                />
                <span className="min-w-0">
                  <Link
                    href={`${base}/${row.id}`}
                    className="focus-ring block truncate font-sans text-sm text-ink hover:underline"
                  >
                    {label}
                  </Link>
                  {kind === "drivers" && (
                    <span className="team-text block truncate text-[10px] uppercase tracking-[0.14em]">
                      {team.short || row.teamId}
                    </span>
                  )}
                </span>
              </span>

              <span role="cell" className="tabular text-right text-sm text-ink">
                {row.points}
              </span>
              <span role="cell" className="tabular hidden text-right text-xs text-muted sm:block">
                {row.wins}
              </span>
              <span role="cell" className="tabular hidden text-right text-xs text-muted sm:block">
                {gaps[row.id] === 0 ? "—" : `−${gaps[row.id]}`}
              </span>
              <span role="cell" className="text-right">
                <Delta value={delta} />
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Delta({ value }: { value: number | null | undefined }) {
  if (value == null) {
    return (
      <span className="tabular text-xs text-muted" title="No previous round">
        <span aria-hidden="true">·</span>
        <span className="sr-only">new entry</span>
      </span>
    );
  }
  if (value === 0) {
    return (
      <span className="tabular text-xs text-muted">
        <span aria-hidden="true">–</span>
        <span className="sr-only">unchanged</span>
      </span>
    );
  }
  const up = value > 0;
  return (
    <span className={`tabular text-xs ${up ? "text-harvest" : "text-deploy"}`}>
      <span aria-hidden="true">
        {up ? "▲" : "▼"} {Math.abs(value)}
      </span>
      <span className="sr-only">
        {up ? "up" : "down"} {Math.abs(value)} {Math.abs(value) === 1 ? "place" : "places"}
      </span>
    </span>
  );
}
