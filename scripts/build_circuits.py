"""Phase 1: build canonical circuit geometry for the calendar and persist it.

Run:  uv run python -m scripts.build_circuits [--only monza,monaco] [--step 5]

Writes data/processed/circuits/<circuit_id>.json plus an index.json carrying provenance
for every circuit, so the API and UI can state which session each track map came from.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

from data.cache import PROCESSED_DIR, enable
from data.geometry import (
    DEFAULT_STEP_M,
    POS_UNITS_PER_M,
    CircuitGeometry,
    build_centreline,
    compute_curvature,
    compute_gradient,
    path_length_m,
    pool_position_samples,
    segment_lap,
)
from data.sessions import (
    CircuitRef,
    build_registry,
    clean_laps,
    load_qualifying,
    pick_reference_lap,
    session_weather,
)

OUT_DIR = PROCESSED_DIR / "circuits"
SCHEMA_VERSION = 1


def official_corners(session) -> list[dict]:
    try:
        ci = session.get_circuit_info()
    except Exception:  # noqa: BLE001
        return []
    if ci is None or ci.corners is None or len(ci.corners) == 0:
        return []
    out = []
    for _, c in ci.corners.iterrows():
        out.append(
            {
                "number": int(c["Number"]),
                "letter": str(c.get("Letter", "") or ""),
                "distance_m": float(c["Distance"]),
                "angle_deg": float(c.get("Angle", float("nan"))),
            }
        )
    return out


def build_one(ref: CircuitRef, step_m: float) -> CircuitGeometry:
    session = load_qualifying(ref)

    reference = pick_reference_lap(session)
    ref_tel = reference.get_telemetry().add_distance()
    lap_distance_m = float(ref_tel["Distance"].iloc[-1])
    if not np.isfinite(lap_distance_m) or lap_distance_m < 1000:
        raise ValueError(f"implausible lap distance {lap_distance_m!r} m")

    laps = clean_laps(session)
    relaxed = False
    if len(laps) < 3:
        # Not enough green-flag accurate laps to pool; fall back to all timed laps and
        # record that the filter was relaxed rather than silently widening it.
        laps = session.laps[session.laps["LapTime"].notna()]
        relaxed = True

    # The reference lap seeds the spatial alignment: every pooled sample is matched to
    # the nearest point on it, rather than to a distance value integrated from speed.
    seed = ref_tel[["X", "Y", "Z"]].dropna()
    seed = seed[~((seed["X"] == 0) & (seed["Y"] == 0))]
    if len(seed) < 20:
        raise ValueError("reference lap has too few usable position samples to seed alignment")
    seed_xyz = (
        seed["X"].to_numpy() / POS_UNITS_PER_M,
        seed["Y"].to_numpy() / POS_UNITS_PER_M,
        seed["Z"].to_numpy() / POS_UNITS_PER_M,
    )

    pooled, pool_diag = pool_position_samples(laps)
    distance, x, y, z, grid_diag = build_centreline(pooled, seed_xyz, step_m)

    curvature = compute_curvature(x, y, step_m)
    gradient = compute_gradient(z, step_m)
    with np.errstate(divide="ignore"):
        radius = np.where(np.abs(curvature) > 1e-9, 1.0 / np.abs(curvature), np.inf)
    segments = segment_lap(curvature, step_m)

    # The traced path is now a direct geometric measurement of the driven line, so it —
    # not the speed-integrated Distance channel — defines lap length. The two are still
    # compared, because a large disagreement means the geometry is wrong.
    gps_len = path_length_m(x, y)
    closure_err = abs(gps_len - lap_distance_m) / lap_distance_m
    geometry_length_m = gps_len

    corners = official_corners(session)
    detected = [s for s in segments if s.kind == "corner"]
    straights = [s for s in segments if s.kind == "straight"]

    diagnostics = {
        "schema_version": SCHEMA_VERSION,
        "provenance": ref.provenance,
        "data_year": ref.data_year,
        "data_round": ref.data_round,
        "is_fallback": ref.is_fallback,
        "session": f"{ref.data_year} {ref.event_name} Qualifying",
        "reference_driver": str(reference["Driver"]),
        "reference_team": str(reference["Team"]),
        "reference_lap_time_s": float(
            pd.Timedelta(reference["LapTime"]).total_seconds()
        ),
        "lap_distance_m": round(geometry_length_m, 1),
        "telemetry_distance_m": round(lap_distance_m, 1),
        "gps_path_length_m": round(gps_len, 1),
        "path_vs_distance_error_pct": round(closure_err * 100, 3),
        # Flags a disagreement between the traced path and the speed-integrated Distance
        # channel. It does NOT say which is wrong: at Suzuka the geometry gives 5,775 m
        # against a true 5,807 m while Distance under-reads at 5,389 m, so here the
        # channel is at fault. Flagged for review, not auto-rejected.
        "length_disagreement": bool(closure_err > 0.02),
        "clean_lap_filter_relaxed": relaxed,
        "n_official_corners": len(corners),
        "n_detected_corners": len(detected),
        "n_detected_straights": len(straights),
        "longest_straight_m": round(max((s.length_m for s in straights), default=0.0), 1),
        "weather": session_weather(session),
        **pool_diag,
        **grid_diag,
    }

    return CircuitGeometry(
        circuit_id=ref.circuit_id,
        lap_distance_m=geometry_length_m,
        step_m=step_m,
        distance_m=distance,
        x_m=x,
        y_m=y,
        z_m=z,
        curvature_1_per_m=curvature,
        radius_m=radius,
        gradient=gradient,
        segments=segments,
        official_corners=corners,
        diagnostics=diagnostics,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated circuit ids")
    ap.add_argument("--step", type=float, default=DEFAULT_STEP_M)
    args = ap.parse_args(argv)

    enable()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    available, unavailable = build_registry()
    wanted = {s.strip() for s in args.only.split(",") if s.strip()}
    if wanted:
        available = [r for r in available if r.circuit_id in wanted]

    print(f"Circuits to build: {len(available)}   excluded: {len(unavailable)}")
    for u in unavailable:
        print(f"  EXCLUDED R{u.round_number:02d} {u.event_name} ({u.location}): {u.reason}")
    print()

    index, failures = [], []
    for ref in sorted(available, key=lambda r: r.round_number):
        tag = "fallback" if ref.is_fallback else "2026"
        print(f"[R{ref.round_number:02d}] {ref.circuit_id:<18} {tag:<9}", end=" ", flush=True)
        try:
            geo = build_one(ref, args.step)
        except Exception as exc:  # noqa: BLE001 - report and continue; never invent
            print(f"FAILED {type(exc).__name__}: {exc}")
            failures.append({"circuit_id": ref.circuit_id, "error": f"{type(exc).__name__}: {exc}"})
            traceback.print_exc(limit=2, file=sys.stdout)
            continue

        path = OUT_DIR / f"{ref.circuit_id}.json"
        path.write_text(json.dumps(geo.to_json_dict()), encoding="utf-8")
        d = geo.diagnostics
        print(
            f"{d['lap_distance_m']:>7.0f} m  corners {d['n_detected_corners']:>2}"
            f"/{d['n_official_corners']:<2} official  straights {d['n_detected_straights']:>2}"
            f"  longest {d['longest_straight_m']:>6.0f} m"
            f"  laps {d['laps_pooled']:>3}  path err {d['path_vs_distance_error_pct']:.2f}%"
        )
        index.append({**ref.to_dict(), **{k: d[k] for k in (
            "reference_driver", "reference_lap_time_s", "lap_distance_m",
            "n_detected_corners", "n_official_corners", "longest_straight_m",
            "path_vs_distance_error_pct", "weather",
        )}})

    (PROCESSED_DIR / "circuits_index.json").write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "step_m": args.step,
                "circuits": index,
                "excluded": [u.__dict__ for u in unavailable],
                "failures": failures,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nBuilt {len(index)} circuits, {len(failures)} failures -> {OUT_DIR}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
