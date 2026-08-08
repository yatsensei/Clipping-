"""Evaluate segmentation parameters against every built circuit.

Re-segments from the stored curvature arrays, so no telemetry is reloaded. The objective
is agreement with FastF1's official corner count per circuit — an independent reference,
not something this code produced.

Run:  uv run python -m scripts.tune_segmentation [--sweep]
"""

from __future__ import annotations

import argparse
import json

import numpy as np

from data import geometry
from data.cache import PROCESSED_DIR


def load_all() -> list[dict]:
    out = []
    for path in sorted((PROCESSED_DIR / "circuits").glob("*.json")):
        out.append(json.loads(path.read_text(encoding="utf-8")))
    return out


def evaluate(circuits: list[dict], **overrides) -> tuple[list[tuple], float]:
    """Re-segment each circuit and compare detected vs official corner counts."""
    saved = {k: getattr(geometry, k) for k in overrides}
    for k, v in overrides.items():
        setattr(geometry, k, v)
    try:
        rows = []
        for c in circuits:
            k = np.asarray(c["curvature_1_per_m"], dtype=float)
            segs = geometry.segment_lap(k, c["step_m"])
            corners = [s for s in segs if s.kind == "corner"]
            straights = [s for s in segs if s.kind == "straight"]
            official = c["diagnostics"]["n_official_corners"]
            rows.append(
                (
                    c["circuit_id"],
                    len(corners),
                    official,
                    len(corners) - official,
                    max((s.length_m for s in straights), default=0.0),
                )
            )
    finally:
        for k, v in saved.items():
            setattr(geometry, k, v)

    scored = [r for r in rows if r[2] > 0]
    mae = float(np.mean([abs(r[3]) for r in scored])) if scored else float("nan")
    return rows, mae


def rewrite(circuits: list[dict]) -> None:
    """Re-segment from stored curvature and persist, without reloading telemetry."""
    for c in circuits:
        k = np.asarray(c["curvature_1_per_m"], dtype=float)
        segs = geometry.segment_lap(k, c["step_m"])
        corners = [s for s in segs if s.kind == "corner"]
        straights = [s for s in segs if s.kind == "straight"]
        c["segments"] = [s.to_dict() for s in segs]
        c["diagnostics"]["n_detected_corners"] = len(corners)
        c["diagnostics"]["n_detected_straights"] = len(straights)
        c["diagnostics"]["longest_straight_m"] = round(
            max((s.length_m for s in straights), default=0.0), 1
        )
        path = PROCESSED_DIR / "circuits" / f"{c['circuit_id']}.json"
        path.write_text(json.dumps(c), encoding="utf-8")

    index_path = PROCESSED_DIR / "circuits_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    by_id = {c["circuit_id"]: c for c in circuits}
    for entry in index["circuits"]:
        src = by_id.get(entry["circuit_id"])
        if src:
            entry["n_detected_corners"] = src["diagnostics"]["n_detected_corners"]
            entry["longest_straight_m"] = src["diagnostics"]["longest_straight_m"]
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"rewrote {len(circuits)} circuit files and the index")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--write", action="store_true", help="persist re-segmented output")
    args = ap.parse_args()

    circuits = load_all()
    if not circuits:
        print("No circuits built yet.")
        return 1
    print(f"Loaded {len(circuits)} circuits\n")

    if args.sweep:
        best = []
        for height in (0.25, 0.35, 0.45):
            for prom in (0.25, 0.35, 0.45, 0.55):
                for release in (0.5, 0.6, 0.7):
                    _, mae = evaluate(
                        circuits,
                        APEX_MIN_HEIGHT_FRAC=height,
                        APEX_PROMINENCE_FRAC=prom,
                        SPLIT_RELEASE_FRAC=release,
                    )
                    best.append((mae, height, prom, release))
        best.sort()
        print(f"{'MAE':>6} {'height':>7} {'prom':>6} {'release':>8}")
        for mae, h, p, r in best[:12]:
            print(f"{mae:>6.2f} {h:>7.2f} {p:>6.2f} {r:>8.2f}")
        print("\nWorst:")
        for mae, h, p, r in best[-3:]:
            print(f"{mae:>6.2f} {h:>7.2f} {p:>6.2f} {r:>8.2f}")
        return 0

    if args.write:
        rewrite(circuits)

    rows, mae = evaluate(circuits)
    print(f"{'circuit':<20} {'detected':>9} {'official':>9} {'diff':>6} {'longest str':>12}")
    print("-" * 60)
    for cid, det, off, diff, longest in sorted(rows, key=lambda r: -abs(r[3])):
        print(f"{cid:<20} {det:>9} {off:>9} {diff:>+6} {longest:>11.0f} m")
    print(f"\nMean absolute corner-count error: {mae:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
