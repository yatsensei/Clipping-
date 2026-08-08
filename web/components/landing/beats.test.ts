import { describe, expect, it } from "vitest";
import { activeBeatForScroll, buildBeats, lapFractionForScroll } from "./beats";
import type { Strategy } from "@/lib/api";

/**
 * The landing page's scroll binding cannot be verified in a headless pane —
 * requestAnimationFrame never fires without compositing, so the car simply does not
 * move. These tests cover the pure mapping instead, which is where a bug would actually
 * live and would otherwise be invisible.
 */

/**
 * A synthetic Monza-shaped lap: flat out at the timing line, brakes into the chicane,
 * accelerates away, crosses the taper threshold, then runs dry and clips.
 *
 * The depletion rate matters. The real sequence is deploy -> taper -> empty -> clip, and
 * a fixture that empties the store before the car reaches 290 km/h is testing a lap that
 * does not happen.
 */
function greedyLap(): Strategy {
  const n = 200;
  const speed: number[] = [];
  const soc: number[] = [];
  const deploy: number[] = [];
  const clipping: boolean[] = [];

  for (let i = 0; i < n; i++) {
    // Fast at the timing line, slowest at i=40, then climbing again.
    const v = i < 40 ? 330 - i * 6 : Math.min(330, 90 + (i - 40) * 3);
    speed.push(v);
    const charge = Math.max(0, 2 - i * 0.012);
    soc.push(charge);
    deploy.push(charge > 0.01 && i > 40 ? 350 : 0);
    clipping.push(charge <= 0.01 && v > 200);
  }

  return {
    circuit_id: "monza",
    mode: "greedy",
    requested_mode: "greedy",
    lap_time_s: 76.9,
    distance_m: speed.map((_, i) => (i / (n - 1)) * 5762),
    speed_kph: speed,
    deploy_kw: deploy,
    harvest_kw: new Array(n).fill(0),
    soc_mj: soc,
    clipping,
    deploy_fraction: new Array(n).fill(1),
    soc_start_mj: 2,
    energy_deployed_mj: 2,
    repeatable: false,
    repeatability_note: "not repeatable",
    provenance: {} as Strategy["provenance"],
    data_type: "model_output",
  };
}

describe("buildBeats", () => {
  it("anchors the story after the slowest point, not at the timing line", () => {
    // Monza's line is mid-straight at 330 km/h with a full store, so a naive search
    // finds "deployment begins" and "the taper bites" both at distance zero.
    const beats = buildBeats(greedyLap(), 5762);
    const deploy = beats.find((b) => b.id === "deploy");
    const taper = beats.find((b) => b.id === "taper");

    expect(deploy).toBeDefined();
    expect(taper).toBeDefined();
    expect(deploy!.at).toBeGreaterThan(0);
    expect(taper!.at).toBeGreaterThan(0);
  });

  it("orders the beats monotonically around the lap", () => {
    const beats = buildBeats(greedyLap(), 5762);
    for (let i = 1; i < beats.length; i++) {
      expect(beats[i].at).toBeGreaterThanOrEqual(beats[i - 1].at);
    }
  });

  it("tells the story in the physically correct order", () => {
    const beats = buildBeats(greedyLap(), 5762);
    const order = beats.map((b) => b.id);
    expect(order.indexOf("deploy")).toBeLessThan(order.indexOf("empty"));
    expect(order.indexOf("empty")).toBeLessThanOrEqual(order.indexOf("clip"));
    expect(order[0]).toBe("open");
    expect(order[order.length - 1]).toBe("release");
  });

  it("drops a beat rather than telling the story out of order", () => {
    // A lap whose store empties before the car ever reaches the taper threshold. The
    // taper beat has nowhere sensible to go, so it must be omitted, not misplaced.
    const lap = greedyLap();
    lap.soc_mj = lap.soc_mj.map((_, i) => (i > 45 ? 0 : 2));
    lap.clipping = lap.clipping.map((_, i) => i > 45);

    const beats = buildBeats(lap, 5762);
    for (let i = 1; i < beats.length; i++) {
      expect(beats[i].at).toBeGreaterThanOrEqual(beats[i - 1].at);
    }
    expect(beats[0].id).toBe("open");
    expect(beats[beats.length - 1].id).toBe("release");
  });

  it("reads its figures from the data rather than hardcoding them", () => {
    const lap = greedyLap();
    const beats = buildBeats(lap, 5762);
    const clip = beats.find((b) => b.id === "clip");
    const expected = (100 * lap.clipping.filter(Boolean).length) / lap.clipping.length;
    expect(clip!.readout!.value).toBe(`${expected.toFixed(0)}%`);
  });
});

describe("lapFractionForScroll", () => {
  const knots = [0, 0.16, 0.209, 0.211, 0.212, 1];

  it("lands exactly on each beat at its share of the scroll", () => {
    knots.forEach((expected, i) => {
      const progress = i / (knots.length - 1);
      expect(lapFractionForScroll(progress, knots)).toBeCloseTo(expected, 9);
    });
  });

  it("is monotonically increasing, so the lap never runs backwards", () => {
    let previous = -1;
    for (let s = 0; s <= 1.0001; s += 0.01) {
      const lap = lapFractionForScroll(s, knots);
      expect(lap).toBeGreaterThanOrEqual(previous);
      previous = lap;
    }
  });

  it("gives the tightly clustered beats real scroll room", () => {
    // The three events inside 0.3% of the lap must each get a full share of the page,
    // otherwise the reader scrolls past the entire point of the story in a few pixels.
    const before = lapFractionForScroll(2 / 5, knots);
    const after = lapFractionForScroll(4 / 5, knots);
    expect(after - before).toBeLessThan(0.01); // still a tiny slice of the lap
    // ...but it occupied 40% of the scroll to get there.
    expect(lapFractionForScroll(3 / 5, knots)).toBeGreaterThan(before);
  });

  it("clamps out-of-range scroll rather than extrapolating off the lap", () => {
    expect(lapFractionForScroll(-0.5, knots)).toBeCloseTo(0, 9);
    expect(lapFractionForScroll(1.5, knots)).toBeCloseTo(1, 9);
  });

  it("degenerates gracefully with fewer than two beats", () => {
    expect(lapFractionForScroll(0.42, [0.3])).toBeCloseTo(0.42, 9);
  });
});

describe("activeBeatForScroll", () => {
  it("selects the nearest beat and stays in range", () => {
    expect(activeBeatForScroll(0, 6)).toBe(0);
    expect(activeBeatForScroll(1, 6)).toBe(5);
    expect(activeBeatForScroll(0.5, 6)).toBe(3);
    expect(activeBeatForScroll(2, 6)).toBe(5);
    expect(activeBeatForScroll(-1, 6)).toBe(0);
  });
});
