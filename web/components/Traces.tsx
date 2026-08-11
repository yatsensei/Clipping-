"use client";

import { useMemo } from "react";
import type { Strategy } from "@/lib/api";
import { TOKENS } from "@/lib/track";

/**
 * Speed, power and state of charge against lap distance, with a cursor tracking the car.
 *
 * All three share the distance index the API returns, so the cursor is one x position
 * across every panel and no re-interpolation happens on the client.
 *
 * Power uses fill DIRECTION rather than hue alone: deployment above the axis, harvest
 * below. That keeps the two states distinguishable without relying on red versus cyan.
 */

const HEIGHT = 96;
const WIDTH = 1000;

function pathFor(values: number[], min: number, max: number, height = HEIGHT): string {
  const span = max - min || 1;
  const n = values.length;
  return values
    .map((v, i) => {
      const x = (i / (n - 1)) * WIDTH;
      const y = height - ((v - min) / span) * height;
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

/** Round tick values covering [min, max], at roughly `target` intervals. */
function ticks(min: number, max: number, target = 4): number[] {
  const span = max - min;
  if (span <= 0) return [min];
  const raw = span / target;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  // Snap the interval to something a person would choose: 1, 2, 2.5, 5 or 10.
  const step =
    magnitude * ([1, 2, 2.5, 5, 10].find((m) => raw <= m * magnitude) ?? 10);

  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) {
    out.push(+v.toFixed(6));
  }
  return out;
}

const GUTTER = 34; // room for the y-axis labels, in pixels

function Panel({
  label,
  unit,
  value,
  children,
  cursorX,
  axis,
}: {
  label: string;
  unit: string;
  value: string;
  children: React.ReactNode;
  cursorX: number;
  /** Domain the y axis spans, bottom to top, and how to print a tick. */
  axis: { min: number; max: number; format?: (v: number) => string };
}) {
  const marks = ticks(axis.min, axis.max);
  const format = axis.format ?? ((v: number) => String(v));
  const span = axis.max - axis.min || 1;

  return (
    <div className="border-t border-line pt-2">
      <div className="flex items-baseline justify-between px-1 pb-1">
        <span className="text-[10px] uppercase tracking-[0.18em] text-muted">
          {label}
        </span>
        <span className="tabular text-xs text-ink">
          {value}
          <span className="text-muted ml-1">{unit}</span>
        </span>
      </div>

      <div className="relative" style={{ height: HEIGHT }}>
        {/*
          Labels are HTML, not SVG text. These charts stretch to the panel width with
          preserveAspectRatio="none", which would squash any text inside the viewBox
          horizontally by whatever factor the panel happens to be scaled by.
        */}
        <div
          className="pointer-events-none absolute inset-y-0 left-0 z-10"
          style={{ width: GUTTER }}
          aria-hidden="true"
        >
          {marks.map((v) => {
            const top = HEIGHT - ((v - axis.min) / span) * HEIGHT;
            return (
              <span
                key={v}
                className="tabular absolute right-1 -translate-y-1/2 text-[9px] leading-none text-muted"
                style={{ top }}
              >
                {format(v)}
              </span>
            );
          })}
        </div>

        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          preserveAspectRatio="none"
          className="absolute inset-y-0 right-0"
          style={{ left: GUTTER, width: `calc(100% - ${GUTTER}px)`, height: HEIGHT }}
          aria-hidden="true"
        >
          {/* Gridlines at each labelled value. */}
          {marks.map((v) => {
            const y = HEIGHT - ((v - axis.min) / span) * HEIGHT;
            return (
              <line
                key={v}
                x1={0}
                y1={y}
                x2={WIDTH}
                y2={y}
                stroke={TOKENS.line}
                strokeWidth={1}
                opacity={0.65}
              />
            );
          })}
          {children}
          <line
            x1={cursorX}
            y1={0}
            x2={cursorX}
            y2={HEIGHT}
            stroke={TOKENS.bone}
            strokeWidth={1}
            opacity={0.7}
          />
        </svg>
      </div>
    </div>
  );
}

export function Traces({
  strategy,
  carIndex,
  socCapacityMj,
}: {
  strategy: Strategy;
  carIndex: number;
  socCapacityMj: number;
}) {
  const n = strategy.speed_kph.length;
  const cursorX = (carIndex / (n - 1)) * WIDTH;
  const i = Math.floor(carIndex) % n;

  const speed = useMemo(() => {
    const max = Math.max(...strategy.speed_kph) * 1.05;
    return { d: pathFor(strategy.speed_kph, 0, max), max };
  }, [strategy]);

  const power = useMemo(() => {
    // One symmetric scale for both directions so their magnitudes stay comparable.
    const peak = Math.max(
      350,
      ...strategy.deploy_kw,
      ...strategy.harvest_kw,
    );
    const mid = HEIGHT / 2;
    const deploy = strategy.deploy_kw
      .map((v, idx) => {
        const x = (idx / (n - 1)) * WIDTH;
        return `${idx === 0 ? "M" : "L"}${x.toFixed(2)},${(mid - (v / peak) * mid).toFixed(2)}`;
      })
      .join(" ");
    const harvest = strategy.harvest_kw
      .map((v, idx) => {
        const x = (idx / (n - 1)) * WIDTH;
        return `${idx === 0 ? "M" : "L"}${x.toFixed(2)},${(mid + (v / peak) * mid).toFixed(2)}`;
      })
      .join(" ");
    return {
      deployArea: `M0,${mid} ${deploy.slice(1)} L${WIDTH},${mid} Z`,
      harvestArea: `M0,${mid} ${harvest.slice(1)} L${WIDTH},${mid} Z`,
      peak,
      mid,
    };
  }, [strategy, n]);

  const soc = useMemo(
    () => pathFor(strategy.soc_mj, 0, socCapacityMj),
    [strategy, socCapacityMj],
  );

  const clipSpans = useMemo(() => {
    const spans: { x: number; w: number }[] = [];
    let start: number | null = null;
    strategy.clipping.forEach((c, idx) => {
      if (c && start === null) start = idx;
      if (!c && start !== null) {
        spans.push({
          x: (start / (n - 1)) * WIDTH,
          w: ((idx - start) / (n - 1)) * WIDTH,
        });
        start = null;
      }
    });
    if (start !== null) {
      spans.push({
        x: (start / (n - 1)) * WIDTH,
        w: ((n - start) / (n - 1)) * WIDTH,
      });
    }
    return spans;
  }, [strategy, n]);

  return (
    <div className="space-y-1">
      <Panel
        label="Speed"
        unit="km/h"
        value={strategy.speed_kph[i].toFixed(0)}
        cursorX={cursorX}
        axis={{ min: 0, max: speed.max }}
      >
        <path d={speed.d} fill="none" stroke={TOKENS.bone} strokeWidth={1.4} />
        {clipSpans.map((s, k) => (
          <rect
            key={k}
            x={s.x}
            y={0}
            width={s.w}
            height={HEIGHT}
            fill={TOKENS.clip}
            opacity={0.18}
          />
        ))}
      </Panel>

      <Panel
        label="Deploy / Harvest"
        unit="kW"
        value={
          strategy.harvest_kw[i] > 1
            ? `−${strategy.harvest_kw[i].toFixed(0)}`
            : strategy.deploy_kw[i].toFixed(0)
        }
        cursorX={cursorX}
        // Deployment reads above the axis and harvest below, so the scale is signed.
        axis={{ min: -power.peak, max: power.peak }}
      >
        <line
          x1={0}
          y1={power.mid}
          x2={WIDTH}
          y2={power.mid}
          stroke={TOKENS.line}
          strokeWidth={1}
        />
        <path d={power.deployArea} fill={TOKENS.deploy} opacity={0.85} />
        <path d={power.harvestArea} fill={TOKENS.harvest} opacity={0.75} />
      </Panel>

      <Panel
        label="State of charge"
        unit="MJ"
        value={strategy.soc_mj[i].toFixed(2)}
        cursorX={cursorX}
        axis={{
          min: 0,
          max: socCapacityMj,
          format: (v) => v.toFixed(v % 1 === 0 ? 0 : 1),
        }}
      >
        <line
          x1={0}
          y1={HEIGHT - (strategy.soc_start_mj / socCapacityMj) * HEIGHT}
          x2={WIDTH}
          y2={HEIGHT - (strategy.soc_start_mj / socCapacityMj) * HEIGHT}
          stroke={TOKENS.harvest}
          strokeWidth={1}
          strokeDasharray="3 4"
          opacity={0.6}
        />
        <path d={soc} fill="none" stroke={TOKENS.bone} strokeWidth={1.6} />
      </Panel>
    </div>
  );
}
