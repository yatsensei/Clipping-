"""Measure what the telemetry can actually support before fitting anything.

Answers, across the 2026 qualifying sessions only (2025 fallback sessions are a different
car and are never used for physics):

  - how many samples are genuine coasting (throttle off, brake off), and over what speed
    range, since that is the only regime where propulsive power is known to be zero
  - how noisy a differentiated speed trace is at ~3.8 Hz
  - what top speeds are reached, which decides whether the deployment taper zone
    (290-345 km/h) is even visited
  - how much full-throttle data exists for the power fit

Run:  uv run python -m scripts.explore_dynamics
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from data.cache import enable
from data.sessions import build_registry, load_qualifying

COAST_THROTTLE_MAX = 3.0  # percent
FULL_THROTTLE_MIN = 98.0  # percent


def lap_frames(session) -> list[pd.DataFrame]:
    """Every lap's telemetry, including in/out laps — those hold most of the coasting."""
    out = []
    for _, lap in session.laps.iterrows():
        try:
            tel = lap.get_telemetry().add_distance()
        except Exception:  # noqa: BLE001
            continue
        need = {"Speed", "Throttle", "Brake", "Time", "Distance"}
        if not need.issubset(tel.columns) or len(tel) < 20:
            continue
        out.append(tel)
    return out


def analyse(tel: pd.DataFrame) -> pd.DataFrame:
    t = tel["Time"].dt.total_seconds().to_numpy()
    v = tel["Speed"].to_numpy() / 3.6  # m/s
    thr = tel["Throttle"].to_numpy()
    brk = tel["Brake"].to_numpy().astype(bool)
    s = tel["Distance"].to_numpy()

    dt = np.gradient(t)
    with np.errstate(invalid="ignore", divide="ignore"):
        accel = np.gradient(v) / dt

    return pd.DataFrame(
        {
            "t": t, "v": v, "throttle": thr, "brake": brk, "s": s,
            "dt": dt, "accel": accel,
        }
    )


def main() -> int:
    enable()
    available, _ = build_registry()
    native = [r for r in available if not r.is_fallback]
    print(f"2026-native qualifying sessions available: {len(native)}\n")

    rows = []
    for ref in native:
        try:
            session = load_qualifying(ref)
        except Exception as exc:  # noqa: BLE001
            print(f"{ref.circuit_id}: FAILED {type(exc).__name__}: {exc}")
            continue

        frames = lap_frames(session)
        if not frames:
            print(f"{ref.circuit_id}: no usable laps")
            continue
        df = pd.concat([analyse(f) for f in frames], ignore_index=True)
        df = df[np.isfinite(df["accel"]) & (df["dt"] > 0.01) & (df["dt"] < 2.0)]

        coast = df[(df["throttle"] <= COAST_THROTTLE_MAX) & (~df["brake"])]
        full = df[(df["throttle"] >= FULL_THROTTLE_MIN) & (~df["brake"])]
        braking = df[df["brake"]]

        rows.append(
            {
                "circuit": ref.circuit_id,
                "laps": len(frames),
                "samples": len(df),
                "coast_n": len(coast),
                "coast_pct": 100 * len(coast) / len(df),
                "coast_v_min_kph": 3.6 * coast["v"].min() if len(coast) else np.nan,
                "coast_v_max_kph": 3.6 * coast["v"].max() if len(coast) else np.nan,
                "coast_v_p90_kph": 3.6 * coast["v"].quantile(0.9) if len(coast) else np.nan,
                "full_n": len(full),
                "brake_n": len(braking),
                "v_max_kph": 3.6 * df["v"].max(),
                "pct_above_290": 100 * (df["v"] * 3.6 > 290).mean(),
                "pct_above_345": 100 * (df["v"] * 3.6 > 345).mean(),
                "median_dt": df["dt"].median(),
                "accel_p1": df["accel"].quantile(0.01),
                "accel_p99": df["accel"].quantile(0.99),
            }
        )
        print(f"  {ref.circuit_id:<16} laps {len(frames):>4}  coast {len(coast):>5} "
              f"({100 * len(coast) / len(df):>4.1f}%)  full {len(full):>5}  "
              f"vmax {3.6 * df['v'].max():>5.1f} kph")

    out = pd.DataFrame(rows)
    print("\n" + "=" * 96)
    print("COASTING AVAILABILITY (the only regime where propulsive power is known = 0)")
    print("=" * 96)
    print(out[["circuit", "coast_n", "coast_pct", "coast_v_min_kph",
               "coast_v_p90_kph", "coast_v_max_kph"]].to_string(index=False))

    print("\n" + "=" * 96)
    print("SPEED REGIME AND SAMPLING")
    print("=" * 96)
    print(out[["circuit", "v_max_kph", "pct_above_290", "pct_above_345",
               "median_dt", "accel_p1", "accel_p99", "full_n"]].to_string(index=False))

    print(f"\nTOTALS: coasting {out['coast_n'].sum():,} samples, "
          f"full-throttle {out['full_n'].sum():,}, braking {out['brake_n'].sum():,}")
    print(f"Median sample interval {out['median_dt'].median():.3f} s")
    q = 1.0 / 3.6 / out["median_dt"].median()
    print(f"Speed quantised to 1 km/h -> differentiating gives ~{q:.2f} m/s^2 of noise "
          "per sample; the fit must not rely on pointwise dv/dt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
