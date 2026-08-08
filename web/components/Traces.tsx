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

function Panel({
  label,
  unit,
  value,
  children,
  cursorX,
}: {
  label: string;
  unit: string;
  value: string;
  children: React.ReactNode;
  cursorX: number;
}) {
  return (
    <div className="border-t border-[#262A30] pt-2">
      <div className="flex items-baseline justify-between px-1 pb-1">
        <span className="text-[10px] uppercase tracking-[0.18em] text-[#6B7280]">
          {label}
        </span>
        <span className="tabular text-xs text-[#F2F0EB]">
          {value}
          <span className="text-[#6B7280] ml-1">{unit}</span>
        </span>
      </div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        preserveAspectRatio="none"
        className="w-full"
        style={{ height: HEIGHT }}
        aria-hidden="true"
      >
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
