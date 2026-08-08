"""Diagnose a circuit whose pooled centreline disagrees with the Distance channel.

A large gap between GPS path length and integrated distance means the pooled centreline
is not tracing the track — usually corrupt position samples surviving the median. This
prints where the path length accumulates so the bad region can be found.

Run:  uv run python -m scripts.diagnose_pooling shanghai
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from data.cache import enable
from data.geometry import POS_UNITS_PER_M, build_centreline, pool_position_samples
from data.sessions import build_registry, clean_laps, load_qualifying, pick_reference_lap


def main(circuit_id: str) -> int:
    enable()
    available, _ = build_registry()
    ref = next((r for r in available if r.circuit_id == circuit_id), None)
    if ref is None:
        print(f"unknown circuit {circuit_id}")
        return 1

    session = load_qualifying(ref)
    reference = pick_reference_lap(session)
    lap_distance = float(reference.get_telemetry().add_distance()["Distance"].iloc[-1])
    laps = clean_laps(session)
    print(f"{circuit_id}: {len(laps)} clean laps, reference distance {lap_distance:.0f} m")

    pooled, diag = pool_position_samples(laps)
    print(f"pooled: {diag}")

    # Raw sample hygiene.
    x, y = pooled["X"].to_numpy(), pooled["Y"].to_numpy()
    zero = int(np.sum((x == 0) & (y == 0)))
    print(f"exact (0,0) samples: {zero}  ({100 * zero / len(pooled):.2f}%)")
    print(f"X range {x.min():.0f}..{x.max():.0f}   Y range {y.min():.0f}..{y.max():.0f}")
    for q in (0.001, 0.01, 0.5, 0.99, 0.999):
        print(f"  q{q:<6} X={np.quantile(x, q):>9.0f}  Y={np.quantile(y, q):>9.0f}")

    distance, cx, cy, cz, grid_diag = build_centreline(pooled, lap_distance, 5.0)
    print(f"grid: {grid_diag}")

    step = np.hypot(np.diff(np.append(cx, cx[0])), np.diff(np.append(cy, cy[0])))
    total = float(step.sum())
    print(f"\ncentreline path {total:.0f} m vs distance {lap_distance:.0f} m "
          f"({100 * (total - lap_distance) / lap_distance:+.2f}%)")
    print(f"step per 5 m grid cell: median {np.median(step):.2f} m, "
          f"p99 {np.quantile(step, 0.99):.2f} m, max {step.max():.2f} m")

    bad = np.flatnonzero(step > 5.0 * 3)
    print(f"\ncells where the centreline jumps >15 m ({len(bad)} of {len(step)}):")
    for i in bad[:25]:
        print(f"  d={distance[i]:>7.0f} m  jump {step[i]:>8.1f} m  "
              f"xy=({cx[i]:.0f},{cy[i]:.0f}) -> ({cx[(i+1) % len(cx)]:.0f},"
              f"{cy[(i+1) % len(cy)]:.0f})")
    print(f"\nlength contributed by those cells: {step[bad].sum():.0f} m "
          f"({100 * step[bad].sum() / total:.1f}% of total)")

    # How many samples land in the worst bins, and how spread out are they?
    if len(bad):
        i = int(bad[0])
        lo, hi = distance[i] / lap_distance, distance[(i + 1) % len(distance)] / lap_distance
        sel = pooled[(pooled["RelativeDistance"] >= lo) & (pooled["RelativeDistance"] < hi)]
        print(f"\nsamples in the first bad bin (rel {lo:.4f}..{hi:.4f}): {len(sel)}")
        if len(sel):
            print(sel[["X", "Y"]].describe().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "shanghai"))
