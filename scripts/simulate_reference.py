"""Phase 2 acceptance: does the forward simulation reproduce the real speed trace?

For every 2026-native circuit, simulates the reference qualifying lap with the fitted
vehicle and compares against the measured speed trace on the same distance grid. Reports
RMSE in km/h and the lap-time error, and plots simulated against actual.

The deployment policy here is full request everywhere. That is not the optimal strategy —
finding that is Phase 3 — it is simply the closest match to what a driver does on a
qualifying flying lap, which is what the measured trace represents.

Run:  uv run python -m scripts.simulate_reference [--plot]
"""

from __future__ import annotations

import argparse
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config.regulations import ES_USABLE_WINDOW_J
from config.vehicle import air_density
from data.cache import PROCESSED_DIR
from data.dynamics import load_reference_traces
from energy.battery import BatteryState
from physics.simulate import simulate_lap
from physics.vehicle import VehicleModel

FIG_DIR = PROCESSED_DIR / "figures"
VOID, PANEL, DEPLOY, HARVEST, BONE, MUTED = (
    "#0A0A0B", "#141619", "#FF2E17", "#3FE0D0", "#F2F0EB", "#5A6068",
)


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


def run_one(circuit_id: str, trace: pd.DataFrame, fit: dict) -> dict:
    rho = circuit_density(circuit_id, float(fit["air_density"]))
    vehicle = VehicleModel.from_fit(fit, air_density=rho)

    curvature = trace["curvature"].to_numpy()
    gradient = trace["gradient"].to_numpy()
    step = float(trace["step_m"].iloc[0])
    n = len(curvature)

    battery = BatteryState(soc_j=ES_USABLE_WINDOW_J)
    result = simulate_lap(curvature, gradient, step, vehicle, np.ones(n), battery)

    actual = trace["speed_mps"].to_numpy()
    sim = result.speed_mps
    err = (sim - actual) * 3.6
    actual_lap = float(trace["lap_time_s"].iloc[0])

    return {
        "circuit": circuit_id,
        "n": n,
        "rmse_kph": float(np.sqrt(np.mean(err**2))),
        "mae_kph": float(np.mean(np.abs(err))),
        "bias_kph": float(np.mean(err)),
        "max_err_kph": float(np.max(np.abs(err))),
        "sim_lap_s": result.lap_time_s,
        "actual_lap_s": actual_lap,
        "lap_err_s": result.lap_time_s - actual_lap,
        "lap_err_pct": 100.0 * (result.lap_time_s - actual_lap) / actual_lap,
        "sim_vmax_kph": float(sim.max() * 3.6),
        "actual_vmax_kph": float(actual.max() * 3.6),
        "energy_deployed_mj": result.energy_deployed_j / 1e6,
        "energy_harvested_mj": result.energy_harvested_j / 1e6,
        "soc_start_mj": result.soc_start_j / 1e6,
        "soc_end_mj": result.soc_end_j / 1e6,
        "soc_deficit_mj": (result.soc_start_j - result.soc_end_j) / 1e6,
        "clipping_pct": 100.0 * float(result.clipping.mean()),
        "air_density": rho,
        "_result": result,
        "_actual": actual,
    }


def plot(rows: list[dict]) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda r: r["circuit"])
    cols = 3
    n_rows = int(np.ceil(len(rows) / cols))
    fig, axes = plt.subplots(n_rows, cols, figsize=(6 * cols, 3.0 * n_rows),
                             facecolor=VOID)
    axes = np.atleast_1d(axes).ravel()
    for ax in axes:
        ax.set_visible(False)

    for ax, r in zip(axes, rows):
        ax.set_visible(True)
        ax.set_facecolor(PANEL)
        d = r["_result"].distance_m / 1000.0
        ax.plot(d, r["_actual"] * 3.6, color=BONE, linewidth=1.4, label="measured")
        ax.plot(d, r["_result"].speed_kph, color=DEPLOY, linewidth=1.2,
                label="simulated")
        ax.set_title(
            f"{r['circuit']}  RMSE {r['rmse_kph']:.1f} km/h  "
            f"lap {r['sim_lap_s']:.2f}s vs {r['actual_lap_s']:.2f}s "
            f"({r['lap_err_s']:+.2f}s)",
            color=BONE, fontsize=9,
        )
        ax.tick_params(colors=BONE, labelsize=7)
        for s in ax.spines.values():
            s.set_color(MUTED)
        ax.grid(alpha=0.15, color=MUTED)
        ax.set_xlabel("lap distance (km)", color=BONE, fontsize=8)
        ax.set_ylabel("speed (km/h)", color=BONE, fontsize=8)
        ax.legend(fontsize=7, facecolor=PANEL, labelcolor=BONE, loc="lower right")

    fig.suptitle("Phase 2 — forward simulation vs measured qualifying lap",
                 color=BONE, fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    path = FIG_DIR / "simulation_vs_actual.png"
    fig.savefig(path, dpi=110, facecolor=VOID)
    plt.close(fig)
    print(f"\nwrote {path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plot", action="store_true")
    args = ap.parse_args()

    fit_path = PROCESSED_DIR / "vehicle_fit.json"
    if not fit_path.exists():
        print("No vehicle fit found. Run scripts.fit_vehicle first.")
        return 1
    fit = json.loads(fit_path.read_text(encoding="utf-8"))

    traces = load_reference_traces()
    rows = []
    for circuit_id, trace in traces.groupby("circuit", observed=True):
        try:
            rows.append(run_one(str(circuit_id), trace.reset_index(drop=True), fit))
        except Exception as exc:  # noqa: BLE001
            print(f"{circuit_id}: FAILED {type(exc).__name__}: {exc}")

    if not rows:
        print("Nothing simulated.")
        return 1

    df = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")}
                       for r in rows])
    print("\n" + "=" * 104)
    print("FORWARD SIMULATION vs MEASURED REFERENCE LAP")
    print("=" * 104)
    show = df[["circuit", "rmse_kph", "mae_kph", "bias_kph", "max_err_kph",
               "sim_lap_s", "actual_lap_s", "lap_err_s", "lap_err_pct",
               "sim_vmax_kph", "actual_vmax_kph"]]
    print(show.to_string(index=False, float_format=lambda v: f"{v:8.2f}"))

    print(f"\nMean speed RMSE   {df['rmse_kph'].mean():6.2f} km/h")
    print(f"Mean |lap error|  {df['lap_err_s'].abs().mean():6.3f} s "
          f"({df['lap_err_pct'].abs().mean():.2f}%)")
    print(f"Lap error range   {df['lap_err_s'].min():+.3f} to "
          f"{df['lap_err_s'].max():+.3f} s")
    print(f"\nEnergy: deployed {df['energy_deployed_mj'].mean():.2f} MJ, "
          f"harvested {df['energy_harvested_mj'].mean():.2f} MJ, "
          f"clipping {df['clipping_pct'].mean():.1f}% of lap (mean over circuits)")
    print(f"SoC: starts {df['soc_start_mj'].mean():.2f} MJ, ends "
          f"{df['soc_end_mj'].mean():.2f} MJ, mean deficit "
          f"{df['soc_deficit_mj'].mean():+.2f} MJ")
    if df["soc_deficit_mj"].mean() > 0.05:
        print("  -> This full-deployment run is NOT periodic: it ends the lap with less")
        print("     energy than it started, so the lap cannot be repeated. Enforcing")
        print("     SoC periodicity is a Phase 3 constraint, and it is why the greedy")
        print("     strategy is not a strategy.")
    print("\nThe simulation runs full deployment everywhere, which the Phase 2 power")
    print("analysis showed the real cars do NOT do. The residual positive speed bias on")
    print("straights is therefore expected: the simulated car is spending energy the")
    print("real driver was saving.")

    df.to_csv(PROCESSED_DIR / "simulation_accuracy.csv", index=False)
    if args.plot:
        plot(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
