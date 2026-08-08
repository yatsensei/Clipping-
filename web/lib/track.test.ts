import { describe, expect, it } from "vitest";
import { indexAtTime, interpolate, lapTiming, project } from "./track";
import type { Geometry, Strategy } from "./api";

/**
 * The animation timing is the one piece of non-trivial logic here whose failure mode is
 * invisible: a car that moves at a constant index per frame still looks like it is going
 * round the track, it is just wrong about where it should be. These tests pin the
 * property that matters — time is spent according to speed.
 */

function strategy(speedKph: number[], lapTimeS?: number): Strategy {
  const n = speedKph.length;
  const zeros = new Array(n).fill(0);
  return {
    circuit_id: "test",
    mode: "optimal",
    requested_mode: "optimal",
    lap_time_s: lapTimeS ?? 0,
    distance_m: speedKph.map((_, i) => i * 5),
    speed_kph: speedKph,
    deploy_kw: zeros,
    harvest_kw: zeros,
    soc_mj: zeros,
    clipping: new Array(n).fill(false),
    deploy_fraction: zeros,
    soc_start_mj: 2,
    energy_deployed_mj: 0,
    repeatable: true,
    repeatability_note: null,
    provenance: {} as Strategy["provenance"],
    data_type: "model_output",
  };
}

describe("lapTiming", () => {
  it("spends more time on the slow half of a lap than the fast half", () => {
    // 100 points at 100 km/h, then 100 at 300 km/h. The slow half must take ~3x longer.
    const speeds = [...new Array(100).fill(100), ...new Array(100).fill(300)];
    const { cumulative, total } = lapTiming(strategy(speeds, 1), 5);

    const slowHalf = cumulative[100] - cumulative[0];
    const fastHalf = cumulative[200] - cumulative[100];
    expect(slowHalf / fastHalf).toBeCloseTo(3, 1);
    expect(total).toBeCloseTo(1, 6);
  });

  it("scales the profile onto the simulator's authoritative lap time", () => {
    const speeds = new Array(50).fill(200);
    const { cumulative, total } = lapTiming(strategy(speeds, 42.5), 5);
    // Re-integrating the trace would give its own answer; the API's must win, so the
    // scrub bar and the headline lap time cannot disagree.
    expect(total).toBe(42.5);
    expect(cumulative[cumulative.length - 1]).toBeCloseTo(42.5, 9);
  });

  it("is monotonically increasing", () => {
    const speeds = [50, 300, 80, 250, 120, 90, 310, 60];
    const { cumulative } = lapTiming(strategy(speeds, 10), 5);
    for (let i = 1; i < cumulative.length; i++) {
      expect(cumulative[i]).toBeGreaterThan(cumulative[i - 1]);
    }
  });
});

describe("indexAtTime", () => {
  it("maps the start and end of the lap to the ends of the grid", () => {
    const speeds = new Array(40).fill(150);
    const { cumulative, total } = lapTiming(strategy(speeds, 8), 5);
    expect(indexAtTime(cumulative, 0)).toBeCloseTo(0, 6);
    expect(indexAtTime(cumulative, total * 0.5)).toBeCloseTo(20, 1);
  });

  it("wraps around rather than running off the end", () => {
    const speeds = new Array(30).fill(200);
    const { cumulative, total } = lapTiming(strategy(speeds, 6), 5);
    const wrapped = indexAtTime(cumulative, total * 1.25);
    const direct = indexAtTime(cumulative, total * 0.25);
    expect(wrapped).toBeCloseTo(direct, 6);
    expect(indexAtTime(cumulative, -total * 0.25)).toBeGreaterThanOrEqual(0);
  });

  it("advances slowly through a slow section and quickly through a fast one", () => {
    const speeds = [...new Array(100).fill(60), ...new Array(100).fill(320)];
    const { cumulative, total } = lapTiming(strategy(speeds, 10), 5);

    // Equal slices of TIME must cover unequal slices of DISTANCE. Both windows are
    // interior: sampling at exactly `total` wraps to the start of the lap by design.
    const early =
      indexAtTime(cumulative, total * 0.15) - indexAtTime(cumulative, total * 0.05);
    const late =
      indexAtTime(cumulative, total * 0.95) - indexAtTime(cumulative, total * 0.85);

    expect(early).toBeGreaterThan(0);
    // 320 vs 60 km/h is a factor of 5.3; allow margin for the window edges.
    expect(late).toBeGreaterThan(early * 3);
  });
});

describe("interpolate", () => {
  it("blends between neighbouring samples", () => {
    expect(interpolate([0, 10, 20], 0.5)).toBeCloseTo(5);
    expect(interpolate([0, 10, 20], 1.25)).toBeCloseTo(12.5);
  });

  it("wraps from the last sample back to the first", () => {
    expect(interpolate([0, 10, 20], 2.5)).toBeCloseTo(10);
  });
});

describe("project", () => {
  it("fits the outline inside the viewBox and closes the loop", () => {
    const n = 64;
    const geometry = {
      x_m: Array.from({ length: n }, (_, i) => Math.cos((i / n) * 2 * Math.PI) * 500),
      y_m: Array.from({ length: n }, (_, i) => Math.sin((i / n) * 2 * Math.PI) * 500),
    } as Geometry;

    const { points, width, height, path } = project(geometry, 1000, 40);
    expect(path.endsWith("Z")).toBe(true);
    for (const p of points) {
      expect(p.x).toBeGreaterThanOrEqual(-0.01);
      expect(p.x).toBeLessThanOrEqual(width + 0.01);
      expect(p.y).toBeGreaterThanOrEqual(-0.01);
      expect(p.y).toBeLessThanOrEqual(height + 0.01);
    }
  });

  it("preserves aspect ratio so a circuit is not visually distorted", () => {
    const n = 32;
    // A 2:1 oval must stay 2:1 on screen.
    const geometry = {
      x_m: Array.from({ length: n }, (_, i) => Math.cos((i / n) * 2 * Math.PI) * 1000),
      y_m: Array.from({ length: n }, (_, i) => Math.sin((i / n) * 2 * Math.PI) * 500),
    } as Geometry;

    const { points } = project(geometry, 1000, 0);
    const spanX = Math.max(...points.map((p) => p.x)) - Math.min(...points.map((p) => p.x));
    const spanY = Math.max(...points.map((p) => p.y)) - Math.min(...points.map((p) => p.y));
    expect(spanX / spanY).toBeCloseTo(2, 1);
  });
});
