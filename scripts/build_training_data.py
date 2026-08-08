"""Phase 4 data generation: run the DP to create its own ground truth.

There is no public dataset of optimal F1 energy deployment, and the telemetry has no
energy channels to infer one from, so the labels are generated here. For each circuit the
DP is solved at a range of starting states of charge, and every point of every optimal
trajectory becomes one (features -> optimal control) example.

The harvest-cap multiplier is searched once per circuit and then reused across starting
states. Each search is ~17 full DP solves, and the multiplier barely depends on the
starting charge, so this is the difference between minutes and hours. Whether the reuse
held is checked, not assumed: achieved harvest is recorded for every row.

Run:  uv run python -m scripts.build_training_data [--soc-levels 5]
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from config.regulations import ES_USABLE_WINDOW_J, OPERATIVE_HARVEST_CAP_J
from config.vehicle import air_density
from data.cache import PROCESSED_DIR
from ml.features import DYNAMIC_FEATURES, FEATURE_NAMES, build_static, dynamic_row
from optimiser import dp
from physics.vehicle import VehicleModel

OUT_PATH = PROCESSED_DIR / "training_data.parquet"
META_PATH = PROCESSED_DIR / "training_meta.json"


def circuit_density(circuit_id: str, default: float) -> float:
    path = PROCESSED_DIR / "weather_2026.parquet"
    if not path.exists():
        return default
    w = pd.read_parquet(path)
    row = w[w["circuit"] == circuit_id]
    if row.empty or pd.isna(row.iloc[0].get("pressure_mbar")):
        return default
    r = row.iloc[0]
    return air_density(r["pressure_mbar"], r["air_temp_c"], r["humidity_pct"] or 0.0)


def solve_circuit(circuit_id: str, fit: dict, soc_levels: np.ndarray, args):
    geo_path = PROCESSED_DIR / "circuits" / f"{circuit_id}.json"
    if not geo_path.exists():
        return None
    geo = json.loads(geo_path.read_text(encoding="utf-8"))

    vehicle = VehicleModel.from_fit(
        fit, air_density=circuit_density(circuit_id, float(fit["air_density"]))
    )
    curvature = np.asarray(geo["curvature_1_per_m"], dtype=float)
    gradient = np.asarray(geo["gradient"], dtype=float)
    step_m = float(geo["step_m"])

    ceiling = dp.speed_ceiling(curvature, gradient, step_m, vehicle)
    static = build_static(curvature, gradient, ceiling, step_m)

    frames = []
    price = None
    for soc0 in soc_levels:
        t0 = time.time()
        res = dp.solve(
            curvature, gradient, step_m, vehicle,
            soc_start_j=float(soc0), n_soc=args.n_soc, n_speed=args.n_speed,
            harvest_price=price,
        )
        # A multiplier tuned at one starting charge does not always keep the lap periodic
        # at another. Rather than train on a label from a lap that cannot be repeated,
        # pay for a fresh search on the states where the reuse failed.
        if price is not None and res.soc_end_j < soc0:
            res = dp.solve(
                curvature, gradient, step_m, vehicle,
                soc_start_j=float(soc0), n_soc=args.n_soc, n_speed=args.n_speed,
            )
            price = res.harvest_multiplier
        if price is None:
            price = res.harvest_multiplier
        elapsed = time.time() - t0

        rows = {name: static[name] for name in static}
        n = len(curvature)
        dyn = {name: np.zeros(n) for name in DYNAMIC_FEATURES}
        for i in range(n):
            d = dynamic_row(
                speed_mps=float(res.speed_mps[i]),
                soc_j=float(res.soc_j[i]),
                capacity_j=ES_USABLE_WINDOW_J,
                ceiling_mps=float(ceiling[i]),
                next_apex_speed_mps=float(static["next_apex_speed_mps"][i]),
            )
            for name in DYNAMIC_FEATURES:
                dyn[name][i] = d[name]
        rows.update(dyn)

        df = pd.DataFrame(rows)
        df["target_fraction"] = res.deploy_fraction
        df["circuit"] = circuit_id
        df["soc_start_mj"] = soc0 / 1e6
        df["lap_time_s"] = res.lap_time_s
        df["harvested_mj"] = res.energy_harvested_j / 1e6
        df["harvest_cap_respected"] = res.energy_harvested_j <= OPERATIVE_HARVEST_CAP_J * 1.001
        df["soc_periodic"] = res.soc_end_j >= soc0
        frames.append(df)

        print(f"    soc {soc0 / 1e6:.2f} MJ  lap {res.lap_time_s:7.3f}s  "
              f"harv {res.energy_harvested_j / 1e6:.2f} MJ  "
              f"periodic={res.soc_end_j >= soc0}  ({elapsed:.1f}s)", flush=True)

    return pd.concat(frames, ignore_index=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--soc-levels", type=int, default=5)
    ap.add_argument("--n-soc", type=int, default=61)
    ap.add_argument("--n-speed", type=int, default=72)
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    fit = json.loads((PROCESSED_DIR / "vehicle_fit.json").read_text(encoding="utf-8"))
    index = json.loads((PROCESSED_DIR / "circuits_index.json").read_text(encoding="utf-8"))
    ids = [c["circuit_id"] for c in index["circuits"]]
    wanted = {s.strip() for s in args.only.split(",") if s.strip()}
    if wanted:
        ids = [c for c in ids if c in wanted]

    # Spread starting states across the usable window, leaving headroom at the top: a
    # full store cannot accept braking energy, and the DP needs a cell of margin.
    soc_levels = np.linspace(0.25, 0.75, args.soc_levels) * ES_USABLE_WINDOW_J

    print(f"Generating training data: {len(ids)} circuits x {len(soc_levels)} "
          f"starting states = {len(ids) * len(soc_levels)} DP solves")
    print(f"SoC levels (MJ): {np.round(soc_levels / 1e6, 2).tolist()}\n")

    frames = []
    for cid in ids:
        print(f"  {cid}", flush=True)
        try:
            got = solve_circuit(cid, fit, soc_levels, args)
        except Exception as exc:  # noqa: BLE001
            print(f"    FAILED {type(exc).__name__}: {exc}", flush=True)
            continue
        if got is not None:
            frames.append(got)

    if not frames:
        print("No training data generated.")
        return 1

    data = pd.concat(frames, ignore_index=True)
    data["circuit"] = data["circuit"].astype("category")
    data.to_parquet(OUT_PATH, index=False)

    meta = {
        "n_rows": int(len(data)),
        "n_circuits": int(data["circuit"].nunique()),
        "soc_levels_mj": (soc_levels / 1e6).tolist(),
        "features": FEATURE_NAMES,
        "target": "target_fraction",
        "dp_grid": {"n_soc": args.n_soc, "n_speed": args.n_speed},
        "harvest_cap_respected_pct": float(100 * data["harvest_cap_respected"].mean()),
        "soc_periodic_pct": float(100 * data["soc_periodic"].mean()),
    }
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"\n{len(data):,} rows from {data['circuit'].nunique()} circuits "
          f"-> {OUT_PATH}")
    print(f"harvest cap respected on {meta['harvest_cap_respected_pct']:.1f}% of rows; "
          f"SoC periodic on {meta['soc_periodic_pct']:.1f}%")
    print("\ntarget distribution:")
    print(data["target_fraction"].value_counts().sort_index().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
