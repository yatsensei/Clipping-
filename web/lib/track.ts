/**
 * Track projection, colour scales and lap timing.
 *
 * The animation is driven by SIMULATED TIME, not by array index. Points are 5 m apart,
 * so stepping one index per frame would run the car at constant distance per frame —
 * fast through hairpins and slow down straights, exactly backwards. Instead the cumulative
 * time to reach each point is precomputed from the speed trace, and the car's position is
 * interpolated from elapsed time, which is what makes the motion read as a lap.
 */

import type { Geometry, Strategy } from "./api";

export interface Projection {
  path: string;
  points: { x: number; y: number }[];
  width: number;
  height: number;
}

/**
 * Fit the GPS outline into a viewBox, preserving aspect ratio.
 *
 * The viewBox HUGS THE TRACK rather than being a fixed square. A square viewBox left a
 * tall circuit like Monza pinned to the left edge with most of the box empty, and since
 * the SVG letterboxes to fit its container, that empty space shrank the track to about
 * half the height it could have used.
 *
 * `reserve` adds horizontal room on both sides for the telemetry card to sit beside the
 * racing line instead of on top of it.
 */
export function project(
  geometry: Geometry,
  size = 1000,
  padding = 48,
  reserve = 0,
): Projection {
  const xs = geometry.x_m;
  const ys = geometry.y_m;
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);

  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  // One scale for both axes, so a circuit is never visually distorted.
  const scale = size / Math.max(spanX, spanY);

  const width = spanX * scale + padding * 2 + reserve * 2;
  const height = spanY * scale + padding * 2;
  const offsetX = padding + reserve;

  const points = xs.map((x, i) => ({
    x: offsetX + (x - minX) * scale,
    // SVG y grows downward; flip so the map matches a conventional track plan.
    y: height - padding - (ys[i] - minY) * scale,
  }));

  const path =
    points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ") +
    " Z";

  return { path, points, width, height };
}

/**
 * Cumulative time at each grid point, integrated from the speed trace.
 * Returns seconds, starting at 0, plus the lap total.
 */
export function lapTiming(strategy: Strategy, stepM: number) {
  const n = strategy.speed_kph.length;
  const cumulative = new Float64Array(n + 1);
  for (let i = 0; i < n; i++) {
    const v0 = Math.max(strategy.speed_kph[i] / 3.6, 1);
    const v1 = Math.max(strategy.speed_kph[(i + 1) % n] / 3.6, 1);
    const vAvg = 0.5 * (v0 + v1);
    cumulative[i + 1] = cumulative[i] + stepM / vAvg;
  }

  // Re-integrating the rounded speed trace lands a few hundredths off the simulator's
  // own lap time, which would show as a scrub bar disagreeing with the headline figure.
  // The API's value is authoritative, so the profile is scaled onto it: the shape comes
  // from the trace, the duration from the model that produced it.
  const integrated = cumulative[n];
  const scale = integrated > 0 ? strategy.lap_time_s / integrated : 1;
  for (let i = 0; i <= n; i++) cumulative[i] *= scale;

  return { cumulative, total: strategy.lap_time_s };
}

/** Fractional grid index at a given elapsed time — binary search then interpolate. */
export function indexAtTime(cumulative: Float64Array, t: number): number {
  const n = cumulative.length - 1;
  const total = cumulative[n];
  const time = ((t % total) + total) % total;

  let lo = 0;
  let hi = n;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (cumulative[mid] <= time) lo = mid;
    else hi = mid;
  }
  const span = cumulative[hi] - cumulative[lo] || 1;
  return lo + (time - cumulative[lo]) / span;
}

export function interpolate(values: number[], index: number): number {
  const n = values.length;
  const i0 = Math.floor(index) % n;
  const i1 = (i0 + 1) % n;
  const frac = index - Math.floor(index);
  return values[i0] * (1 - frac) + values[i1] * frac;
}

export function interpolatePoint(
  points: { x: number; y: number }[],
  index: number,
) {
  const n = points.length;
  const i0 = Math.floor(index) % n;
  const i1 = (i0 + 1) % n;
  const frac = index - Math.floor(index);
  return {
    x: points[i0].x * (1 - frac) + points[i1].x * frac,
    y: points[i0].y * (1 - frac) + points[i1].y * frac,
  };
}

/**
 * SVG colours as CSS variable references rather than literals.
 *
 * Browsers resolve var() and color-mix() inside SVG presentation attributes, so the
 * markup carries no actual colour and switches theme purely in CSS. That matters for
 * more than tidiness: literals baked in during server rendering would disagree with the
 * client's theme after hydration, and every one of them would be a mismatch.
 */
export const TOKENS = {
  void: "var(--surface)",
  panel: "var(--panel)",
  panelHigh: "var(--panel-high)",
  deploy: "var(--deploy)",
  harvest: "var(--harvest)",
  clip: "var(--clip)",
  bone: "var(--ink)",
  line: "var(--line)",
  muted: "var(--muted)",
  warn: "var(--warn)",
} as const;

/**
 * Colour for a point on the track.
 *
 * Deployment runs a red heat scale, harvest is the cool counterpoint, and clipping
 * desaturates to grey — the absence of power reading as the absence of colour. Colour
 * alone is not relied upon: `strokeFor` widens the line with deployment intensity so the
 * state is legible without hue.
 */
export function colourFor(
  deployKw: number,
  harvestKw: number,
  clipping: boolean,
  maxDeployKw = 350,
): string {
  if (clipping) return TOKENS.clip;
  if (harvestKw > 1) return TOKENS.harvest;
  if (deployKw > 1) {
    // Dim ember through to full-saturation red as deployment intensity rises. Mixing
    // toward the page surface rather than a fixed dark keeps the ramp correct in both
    // themes: on light it fades to white, on dark to near-black.
    const t = Math.min(deployKw / maxDeployKw, 1);
    const strength = Math.round(34 + 66 * t);
    return `color-mix(in srgb, var(--deploy) ${strength}%, var(--surface))`;
  }
  return TOKENS.line;
}

export function strokeFor(
  deployKw: number,
  harvestKw: number,
  clipping: boolean,
  maxDeployKw = 350,
): number {
  if (clipping) return 5.5;
  if (harvestKw > 1) return 4;
  if (deployKw > 1) return 3.5 + 4 * Math.min(deployKw / maxDeployKw, 1);
  return 2.5;
}

export function formatLap(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  return m > 0 ? `${m}:${s.toFixed(3).padStart(6, "0")}` : s.toFixed(3);
}

export function formatDelta(seconds: number): string {
  return `${seconds >= 0 ? "+" : ""}${seconds.toFixed(3)}`;
}
