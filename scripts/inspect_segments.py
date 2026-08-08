"""Print the straight/corner segmentation for a circuit against its official corners.

Phase 1 acceptance is a human judgement: an F1 fan should recognise the output. This
prints segments alongside the official corner numbers falling inside each one, so the
mapping to real corner names can be checked by eye.

Run:  uv run python -m scripts.inspect_segments monza monte-carlo
"""

from __future__ import annotations

import json
import sys

from data.cache import PROCESSED_DIR


def show(circuit_id: str) -> None:
    path = PROCESSED_DIR / "circuits" / f"{circuit_id}.json"
    if not path.exists():
        print(f"{circuit_id}: not built ({path})")
        return
    geo = json.loads(path.read_text(encoding="utf-8"))
    d = geo["diagnostics"]

    print(f"\n{'=' * 84}")
    print(f"{circuit_id.upper()}   {d['session']}   ref: {d['reference_driver']} "
          f"{d['reference_lap_time_s']:.3f}s")
    print(f"lap {d['lap_distance_m']:.0f} m | GPS path {d['gps_path_length_m']:.0f} m "
          f"(err {d['path_vs_distance_error_pct']:.2f}%) | pooled {d['laps_pooled']} laps, "
          f"{d['samples']:,} samples | provenance: {d['provenance']}")
    print(f"{'=' * 84}")

    corners = geo["official_corners"]
    print(f"{'#':>3} {'kind':<9} {'start':>7} {'end':>7} {'len':>7} {'Rmin':>7} "
          f"{'apex':>7}  official corners in segment")
    print("-" * 84)
    for i, s in enumerate(geo["segments"], 1):
        lo, hi = s["start_m"], s["end_m"]
        if hi > lo:
            inside = [c for c in corners if lo <= c["distance_m"] < hi]
        else:  # wraps the start/finish line
            inside = [c for c in corners if c["distance_m"] >= lo or c["distance_m"] < hi]
        names = ", ".join(f"T{c['number']}{c['letter']}" for c in inside) or "-"
        rmin = s["min_radius_m"]
        rmin_s = f"{rmin:7.0f}" if rmin < 1e4 else "    inf"
        apex_s = f"{s['apex_m']:7.0f}" if s["apex_m"] is not None else "      -"
        print(f"{i:>3} {s['kind']:<9} {lo:>7.0f} {hi:>7.0f} {s['length_m']:>7.0f} "
              f"{rmin_s} {apex_s}  {names}")

    straights = [s for s in geo["segments"] if s["kind"] == "straight"]
    straights.sort(key=lambda s: -s["length_m"])
    print(f"\nlongest straights: " + ", ".join(f"{s['length_m']:.0f} m @ {s['start_m']:.0f}"
                                               for s in straights[:5]))


if __name__ == "__main__":
    for cid in sys.argv[1:] or ["monza"]:
        show(cid)
