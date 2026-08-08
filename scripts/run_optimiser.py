"""Phase 3: solve the deployment strategy for every circuit and tabulate the result.

Runs three strategies on identical physics and reports lap times, energy and clipping:

  greedy   full deployment everywhere
  uniform  constant deployment, bisected so the lap is energy-neutral
  optimal  the DP solution, periodic by construction

THE HEADLINE GAIN IS MEASURED AGAINST UNIFORM, because uniform is the only baseline that
is also repeatable. Greedy usually posts a faster single lap, and that is not a fair
comparison: it ends the lap with an empty store, so it is spending energy it never
repays. That is reported explicitly rather than hidden.

Starting state of charge defaults to half the usable window, not full. A full store
cannot accept braking energy, so a lap that starts full and must end full has almost no
harvesting headroom and no constant deployment is self-sustaining.

Run:  uv run python -m scripts.run_optimiser [--only monza] [--plot]
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from config.regulations import (
    ES_USABLE_WINDOW_J,
    OPERATIVE_HARVEST_CAP_BASIS,
    OPERATIVE_HARVEST_CAP_J,
)
from config.vehicle import air_density
from data.cache import PROCESSED_DIR
from optimiser import baselines, dp
from physics.vehicle import VehicleModel

OUT_DIR = PROCESSED_DIR / "strategies"
DEFAULT_SOC_FRACTION = 0.5


def circuit_density(circuit_id: str, default: float) -> tuple[float, bool]:
    path = PROCESSED_DIR / "weather_2026.parquet"
    if not path.exists():
        return default, False
    w = pd.read_parquet(path)
    row = w[w["circuit"] == circuit_id]
    if row.empty or pd.isna(row.iloc[0].get("pressure_mbar")):
        return default, False
    r = row.iloc[0]
    return air_density(r["pressure_mbar"], r["air_temp_c"], r["humidity_pct"] or 0.0), True


def run_circuit(circuit_id: str, fit: dict, soc_start_j: float, args) -> dict | None:
    path = PROCESSED_DIR / "circuits" / f"{circuit_id}.json"
    if not path.exists():
        return None
    geo = json.loads(path.read_text(encoding="utf-8"))

    rho, measured = circuit_density(circuit_id, float(fit["air_density"]))
    vehicle = VehicleModel.from_fit(fit, air_density=rho)

    curvature = np.asarray(geo["curvature_1_per_m"], dtype=float)
    gradient = np.asarray(geo["gradient"], dtype=float)
    step_m = float(geo["step_m"])

    t0 = time.time()
    optimal = dp.solve(
        curvature, gradient, step_m, vehicle,
        soc_start_j=soc_start_j, n_soc=args.n_soc, n_speed=args.n_speed,
    )
    solve_s = time.time() - t0

    greedy = baselines.greedy(curvature, gradient, step_m, vehicle,
                              soc_start_j=soc_start_j)
    uniform = baselines.uniform(curvature, gradient, step_m, vehicle,
                                soc_start_j=soc_start_j)

    record = {
        "circuit_id": circuit_id,
        "lap_distance_m": geo["lap_distance_m"],
        "provenance": geo["diagnostics"]["provenance"],
        "air_density": rho,
        "air_density_measured": measured,
        "soc_start_mj": soc_start_j / 1e6,
        "harvest_cap_mj": OPERATIVE_HARVEST_CAP_J / 1e6,
        "solve_seconds": solve_s,

        "optimal_lap_s": optimal.lap_time_s,
        "uniform_lap_s": uniform.lap_time_s,
        "greedy_lap_s": greedy.lap_time_s,

        "gain_vs_uniform_s": uniform.lap_time_s - optimal.lap_time_s,
        "gain_vs_greedy_s": greedy.lap_time_s - optimal.lap_time_s,

        "optimal_deployed_mj": optimal.energy_deployed_j / 1e6,
        "optimal_harvested_mj": optimal.energy_harvested_j / 1e6,
        "uniform_deployed_mj": uniform.energy_deployed_j / 1e6,
        "greedy_deployed_mj": greedy.energy_deployed_j / 1e6,

        "optimal_soc_end_mj": optimal.soc_end_j / 1e6,
        "greedy_soc_end_mj": greedy.soc_end_j / 1e6,
        "greedy_energy_debt_mj": greedy.soc_deficit_j / 1e6,
        "greedy_periodic": greedy.periodic,
        "uniform_periodic": uniform.periodic,
        "optimal_periodic": bool(optimal.soc_end_j >= soc_start_j),
        "optimal_soc_deficit_j": optimal.soc_deficit_j,

        "optimal_clip_pct": 100.0 * float(optimal.clipping.mean()),
        "uniform_clip_pct": 100.0 * uniform.clipping_fraction,
        "greedy_clip_pct": 100.0 * greedy.clipping_fraction,
        "uniform_fraction": float(uniform.deploy_fraction[0]),
        "harvest_multiplier": optimal.harvest_multiplier,
        "notes": optimal.notes,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        **record,
        "baseline_statement": (
            "Gain is measured against uniform constant deployment at the same starting "
            "state of charge, both strategies required to end the lap with at least the "
            "energy they started with."
        ),
        "harvest_cap_basis": OPERATIVE_HARVEST_CAP_BASIS,
        "distance_m": geo["distance_m"],
        "strategies": {
            "optimal": _series(optimal.speed_mps, optimal.deploy_power_w,
                               optimal.harvest_power_w, optimal.soc_j, optimal.clipping,
                               optimal.deploy_fraction),
            "uniform": _series(uniform.speed_mps, uniform.deploy_power_w,
                               uniform.harvest_power_w, uniform.soc_j, uniform.clipping,
                               uniform.deploy_fraction),
            "greedy": _series(greedy.speed_mps, greedy.deploy_power_w,
                              greedy.harvest_power_w, greedy.soc_j, greedy.clipping,
                              greedy.deploy_fraction),
        },
    }
    (OUT_DIR / f"{circuit_id}.json").write_text(json.dumps(payload), encoding="utf-8")
    return record


def _series(speed, deploy_w, harvest_w, soc, clipping, fraction) -> dict:
    return {
        "speed_kph": np.round(np.asarray(speed) * 3.6, 2).tolist(),
        "deploy_kw": np.round(np.asarray(deploy_w) / 1e3, 2).tolist(),
        "harvest_kw": np.round(np.asarray(harvest_w) / 1e3, 2).tolist(),
        "soc_mj": np.round(np.asarray(soc) / 1e6, 4).tolist(),
        "clipping": np.asarray(clipping).astype(bool).tolist(),
        "deploy_fraction": np.round(np.asarray(fraction), 3).tolist(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--n-soc", type=int, default=dp.DEFAULT_N_SOC)
    ap.add_argument("--n-speed", type=int, default=dp.DEFAULT_N_SPEED)
    ap.add_argument("--soc-fraction", type=float, default=DEFAULT_SOC_FRACTION)
    args = ap.parse_args()

    fit_path = PROCESSED_DIR / "vehicle_fit.json"
    if not fit_path.exists():
        print("No vehicle fit. Run scripts.fit_vehicle first.")
        return 1
    fit = json.loads(fit_path.read_text(encoding="utf-8"))

    index = json.loads((PROCESSED_DIR / "circuits_index.json").read_text(encoding="utf-8"))
    ids = [c["circuit_id"] for c in index["circuits"]]
    wanted = {s.strip() for s in args.only.split(",") if s.strip()}
    if wanted:
        ids = [c for c in ids if c in wanted]

    soc_start_j = args.soc_fraction * ES_USABLE_WINDOW_J
    print(f"Solving {len(ids)} circuits | SoC start {soc_start_j / 1e6:.2f} MJ "
          f"({args.soc_fraction:.0%} of the {ES_USABLE_WINDOW_J / 1e6:.0f} MJ window) | "
          f"harvest cap {OPERATIVE_HARVEST_CAP_J / 1e6:.1f} MJ")
    print(f"grid: {args.n_soc} SoC levels x {args.n_speed} speed levels x "
          f"{len(dp.DEFAULT_CONTROLS)} controls\n")

    rows = []
    for cid in ids:
        try:
            rec = run_circuit(cid, fit, soc_start_j, args)
        except Exception as exc:  # noqa: BLE001
            print(f"  {cid:<18} FAILED {type(exc).__name__}: {exc}")
            continue
        if rec is None:
            continue
        rows.append(rec)
        flag = "" if rec["optimal_periodic"] else \
            f"  !! NOT PERIODIC (short {rec['optimal_soc_deficit_j'] / 1e3:.1f} kJ)"
        print(f"  {cid:<18} optimal {rec['optimal_lap_s']:7.3f}s  "
              f"uniform {rec['uniform_lap_s']:7.3f}s  "
              f"gain {rec['gain_vs_uniform_s']:+6.3f}s  "
              f"dep {rec['optimal_deployed_mj']:4.2f} MJ  "
              f"clip {rec['optimal_clip_pct']:4.1f}%  ({rec['solve_seconds']:.1f}s)"
              f"{flag}", flush=True)

    if not rows:
        print("Nothing solved.")
        return 1

    df = pd.DataFrame(rows)
    df.to_csv(PROCESSED_DIR / "strategy_comparison.csv", index=False)

    print("\n" + "=" * 100)
    print("STRATEGY COMPARISON — gain is against UNIFORM constant deployment")
    print("=" * 100)
    show = df[["circuit_id", "uniform_lap_s", "optimal_lap_s", "gain_vs_uniform_s",
               "greedy_lap_s", "greedy_energy_debt_mj", "optimal_deployed_mj",
               "optimal_clip_pct", "greedy_clip_pct"]]
    print(show.to_string(index=False, float_format=lambda v: f"{v:8.3f}"))

    print(f"\nGain vs uniform: mean {df['gain_vs_uniform_s'].mean():+.3f} s, "
          f"range {df['gain_vs_uniform_s'].min():+.3f} to "
          f"{df['gain_vs_uniform_s'].max():+.3f} s")
    print(f"Optimal is periodic on {int(df['optimal_periodic'].sum())}/{len(df)} circuits; "
          f"greedy on {int(df['greedy_periodic'].sum())}/{len(df)}.")
    print(f"Greedy is faster than optimal on "
          f"{int((df['gain_vs_greedy_s'] < 0).sum())}/{len(df)} circuits, by "
          f"{-df['gain_vs_greedy_s'].min():.2f} s at most — while ending the lap "
          f"{df['greedy_energy_debt_mj'].mean():.2f} MJ in debt on average.")
    print("That debt is why greedy is not the baseline: it cannot be run twice.")
    print(f"\nWritten: {OUT_DIR} and strategy_comparison.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
