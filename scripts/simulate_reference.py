"""Physics acceptance: does the model reproduce the real lap, given what the driver did?

For every 2026-native circuit the measured qualifying lap is first INVERTED — the
electrical deployment and harvest the observed accelerations required, given the
model's engine, drag and grip (physics/inverse.py) — and that deployment is then
replayed forward through the same rollout the optimiser is timed on. The replay's
speed trace and lap time against the measured ones are the model's error: what the
grip, braking and power models get wrong once the driver's energy decisions are taken
as given.

The earlier version of this script replayed FULL deployment everywhere and compared
that to a lap the driver demonstrably did not drive that way. Its speed bias was
positive on every circuit — the simulated car was spending energy the real driver was
saving — and the 2.23 s mean error it reported measured that mismatch as much as the
model. That run is kept as a secondary column for continuity, labelled as what it is.

Also written: the inferred lap as a strategy artefact per circuit, so the site can
show "what the driver did" beside the optimiser's answer. Inferred, not measured —
public telemetry has no energy channels — and labelled as such downstream.

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

from config.regulations import ES_USABLE_WINDOW_J, OPERATIVE_HARVEST_CAP_J
from data.cache import PROCESSED_DIR
from data.dynamics import load_reference_traces
from energy.battery import BatteryState
from physics.inverse import ice_power_floor, infer_deployment
from physics.setup import circuit_density
from physics.simulate import simulate_lap
from physics.vehicle import VehicleModel

FIG_DIR = PROCESSED_DIR / "figures"
MEASURED_DIR = PROCESSED_DIR / "measured"
VOID, PANEL, DEPLOY, HARVEST, BONE, MUTED = (
    "#0A0A0B", "#141619", "#FF2E17", "#3FE0D0", "#F2F0EB", "#5A6068",
)


def _errors(sim: np.ndarray, actual: np.ndarray, prefix: str) -> dict:
    err = (sim - actual) * 3.6
    n = len(err)
    thirds = np.array_split(np.arange(n), 3)
    out = {
        f"{prefix}rmse_kph": float(np.sqrt(np.mean(err**2))),
        f"{prefix}mae_kph": float(np.mean(np.abs(err))),
        f"{prefix}bias_kph": float(np.mean(err)),
        f"{prefix}max_err_kph": float(np.max(np.abs(err))),
        f"{prefix}vmax_err_kph": float((sim.max() - actual.max()) * 3.6),
    }
    for k, idx in enumerate(thirds, start=1):
        out[f"{prefix}s{k}_bias_kph"] = float(np.mean(err[idx]))
    return out


GRIP_SCALE_RANGE = (0.85, 1.45)
GRIP_FIT_TOL_S = 0.02


def _replay(vehicle: VehicleModel, trace: pd.DataFrame):
    """Invert the measured lap under this vehicle, then replay the inferred deployment."""
    curvature = trace["curvature"].to_numpy()
    gradient = trace["gradient"].to_numpy()
    step = float(trace["step_m"].iloc[0])
    actual = trace["speed_mps"].to_numpy()
    actual_lap = float(trace["lap_time_s"].iloc[0])
    inferred = infer_deployment(
        actual, trace["throttle"].to_numpy(), trace["brake"].to_numpy(),
        curvature, gradient, step, vehicle, actual_lap,
    )
    replay = simulate_lap(
        curvature, gradient, step, vehicle, inferred.deploy_fraction,
        BatteryState(soc_j=ES_USABLE_WINDOW_J),
    )
    return inferred, replay


def fit_grip_scale(fit: dict, rho: float, trace: pd.DataFrame) -> float:
    """The track grip factor at which the replayed lap matches the measured time.

    Lap time falls monotonically as grip rises, so this is a bisection. One number per
    circuit, fitted to one number (the lap time); the shape of the speed trace is left
    free, and that is what the accuracy table then measures.
    """
    actual_lap = float(trace["lap_time_s"].iloc[0])
    lo, hi = GRIP_SCALE_RANGE

    def err(scale: float) -> float:
        _, rep = _replay(VehicleModel.from_fit(fit, air_density=rho, grip_scale=scale), trace)
        return rep.lap_time_s - actual_lap

    if err(lo) < 0:
        return lo
    if err(hi) > 0:
        return hi
    for _ in range(12):
        mid = 0.5 * (lo + hi)
        e = err(mid)
        if abs(e) < GRIP_FIT_TOL_S:
            return mid
        if e > 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def run_one(circuit_id: str, trace: pd.DataFrame, fit: dict) -> dict:
    rho, _ = circuit_density(circuit_id, float(fit["air_density"]))

    curvature = trace["curvature"].to_numpy()
    gradient = trace["gradient"].to_numpy()
    step = float(trace["step_m"].iloc[0])
    n = len(curvature)
    actual = trace["speed_mps"].to_numpy()
    actual_lap = float(trace["lap_time_s"].iloc[0])
    throttle = trace["throttle"].to_numpy()
    brake = trace["brake"].to_numpy()

    # First with the pooled envelope as fitted, so the unscaled error is on record.
    base = VehicleModel.from_fit(fit, air_density=rho)
    _, replay_unscaled = _replay(base, trace)

    # Then with the circuit's grip factor.
    scale = fit_grip_scale(fit, rho, trace)
    vehicle = VehicleModel.from_fit(fit, air_density=rho, grip_scale=scale)
    inferred, replay = _replay(vehicle, trace)
    floor = ice_power_floor(
        actual, throttle, brake, curvature, gradient, step, vehicle, actual_lap
    )

    # And, for continuity, the old full-deployment run (at the fitted grip).
    full = simulate_lap(
        curvature, gradient, step, vehicle, np.ones(n),
        BatteryState(soc_j=ES_USABLE_WINDOW_J),
    )

    row = {
        "circuit": circuit_id,
        "n": n,
        "grip_scale": scale,
        "unscaled_lap_err_s": replay_unscaled.lap_time_s - actual_lap,
        "unscaled_rmse_kph": float(
            np.sqrt(np.mean(((replay_unscaled.speed_mps - actual) * 3.6) ** 2))
        ),
        "actual_lap_s": actual_lap,
        "actual_vmax_kph": float(actual.max() * 3.6),
        "sim_lap_s": replay.lap_time_s,
        "lap_err_s": replay.lap_time_s - actual_lap,
        "lap_err_pct": 100.0 * (replay.lap_time_s - actual_lap) / actual_lap,
        "sim_vmax_kph": float(replay.speed_mps.max() * 3.6),
        **_errors(replay.speed_mps, actual, ""),
        "replay_deployed_mj": replay.energy_deployed_j / 1e6,
        "replay_harvested_mj": replay.energy_harvested_j / 1e6,
        "replay_clipping_pct": 100.0 * float(replay.clipping.mean()),
        # The inversion's own accounting.
        "inferred_deployed_mj": inferred.energy_deployed_j / 1e6,
        "inferred_harvested_mj": inferred.energy_harvested_j / 1e6,
        "inferred_soc_end_mj": inferred.soc_end_j / 1e6,
        "unexplained_mj": inferred.unexplained_j / 1e6,
        "unexplained_over_ceiling_mj": inferred.unexplained_over_ceiling_j / 1e6,
        "masked_steps": inferred.masked_steps,
        "p_ice_floor_kw": floor / 1e3,
        # The legacy full-deployment comparison.
        "full_lap_s": full.lap_time_s,
        "full_lap_err_s": full.lap_time_s - actual_lap,
        **_errors(full.speed_mps, actual, "full_"),
        "air_density": rho,
        "_replay": replay,
        "_inferred": inferred,
        "_actual": actual,
    }
    return row


def write_measured(circuit_id: str, trace: pd.DataFrame, inferred, fit: dict) -> None:
    """The inferred lap as a strategy artefact, in the shape the API serves."""
    MEASURED_DIR.mkdir(parents=True, exist_ok=True)
    step = float(trace["step_m"].iloc[0])
    n = len(inferred.speed_mps)
    payload = {
        "circuit_id": circuit_id,
        "mode": "measured",
        "data_type": "inferred_from_telemetry",
        "lap_time_s": inferred.lap_time_s,
        "driver": str(trace["driver"].iloc[0]),
        "distance_m": (np.arange(n) * step).round(1).tolist(),
        "speed_kph": (inferred.speed_mps * 3.6).round(1).tolist(),
        "deploy_kw": (inferred.deploy_power_w / 1e3).round(1).tolist(),
        "harvest_kw": (inferred.harvest_power_w / 1e3).round(1).tolist(),
        "soc_mj": (inferred.soc_j / 1e6).round(4).tolist(),
        "deploy_fraction": inferred.deploy_fraction.round(3).tolist(),
        "clipping": [False] * n,
        "soc_start_mj": inferred.soc_start_j / 1e6,
        "soc_end_mj": inferred.soc_end_j / 1e6,
        "energy_deployed_mj": inferred.energy_deployed_j / 1e6,
        "energy_harvested_mj": inferred.energy_harvested_j / 1e6,
        "unexplained_mj": inferred.unexplained_j / 1e6,
        "harvest_cap_mj": OPERATIVE_HARVEST_CAP_J / 1e6,
        "p_ice_w": fit["p_ice_w"],
        "notes": inferred.notes,
        "note": (
            "Reconstructed from the measured speed trace by inverse dynamics under the "
            "fitted model: the electrical power the observed acceleration required "
            "beyond the engine, and the recoverable share of the observed braking. Not "
            "a measurement — public telemetry has no energy channels — and it inherits "
            "the model's assumed engine power."
        ),
    }
    (MEASURED_DIR / f"{circuit_id}.json").write_text(
        json.dumps(payload, separators=(",", ":")), encoding="utf-8"
    )


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
        d = r["_replay"].distance_m / 1000.0
        ax.plot(d, r["_actual"] * 3.6, color=BONE, linewidth=1.4, label="measured")
        ax.plot(d, r["_replay"].speed_kph, color=DEPLOY, linewidth=1.2,
                label="replay of inferred deployment")
        ax2 = ax.twinx()
        ax2.fill_between(d, 0, r["_inferred"].deploy_power_w / 1e3, color=DEPLOY,
                         alpha=0.18, linewidth=0)
        ax2.fill_between(d, 0, -r["_inferred"].harvest_power_w / 1e3, color=HARVEST,
                         alpha=0.18, linewidth=0)
        ax2.set_ylim(-400, 400)
        ax2.tick_params(colors=MUTED, labelsize=6)
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

    fig.suptitle("Replay of the inferred deployment vs the measured qualifying lap",
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
        trace = trace.reset_index(drop=True)
        try:
            row = run_one(str(circuit_id), trace, fit)
        except Exception as exc:  # noqa: BLE001
            print(f"{circuit_id}: FAILED {type(exc).__name__}: {exc}")
            continue
        rows.append(row)
        write_measured(str(circuit_id), trace, row["_inferred"], fit)

    if not rows:
        print("Nothing simulated.")
        return 1

    df = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")}
                       for r in rows])
    pd.set_option("display.width", 200)
    print("\n" + "=" * 110)
    print("REPLAY OF THE INFERRED DEPLOYMENT vs MEASURED REFERENCE LAP")
    print("=" * 110)
    show = df[["circuit", "grip_scale", "unscaled_lap_err_s", "rmse_kph", "bias_kph",
               "s1_bias_kph", "s2_bias_kph", "s3_bias_kph", "vmax_err_kph",
               "sim_lap_s", "actual_lap_s", "lap_err_s"]]
    print(show.to_string(index=False, float_format=lambda v: f"{v:8.2f}"))
    print("\n  grip_scale is fitted per circuit so the replayed lap matches the measured")
    print("  time; unscaled_lap_err_s is the error before that, with the pooled envelope.")
    print("  Everything else is measured at the fitted grip and is NOT fitted.")

    grip = {
        r["circuit"]: {
            "grip_scale": round(float(r["grip_scale"]), 4),
            "unscaled_lap_err_s": round(float(r["unscaled_lap_err_s"]), 3),
            "rmse_kph": round(float(r["rmse_kph"]), 2),
            "basis": "replayed inferred deployment matched to the measured lap time",
        }
        for r in rows
    }
    (PROCESSED_DIR / "grip_factors.json").write_text(
        json.dumps(grip, indent=2), encoding="utf-8"
    )

    print("\nINFERRED ENERGY (full store at the line, 7 MJ harvest cap)")
    show = df[["circuit", "inferred_deployed_mj", "inferred_harvested_mj",
               "inferred_soc_end_mj", "unexplained_mj", "p_ice_floor_kw", "masked_steps"]]
    print(show.to_string(index=False, float_format=lambda v: f"{v:8.2f}"))

    print(f"\nMean speed RMSE      {df['rmse_kph'].mean():6.2f} km/h   "
          f"(full-deployment replay: {df['full_rmse_kph'].mean():.2f})")
    print(f"Mean |lap error|     {df['lap_err_s'].abs().mean():6.3f} s     "
          f"(full-deployment replay: {df['full_lap_err_s'].abs().mean():.3f})")
    print(f"Mean speed bias      {df['bias_kph'].mean():+6.2f} km/h   "
          f"(full-deployment replay: {df['full_bias_kph'].mean():+.2f})")
    print(f"Mean vmax error      {df['vmax_err_kph'].mean():+6.2f} km/h")
    print(f"Unexplained energy   {df['unexplained_mj'].mean():6.2f} MJ per lap that the "
          "modelled engine plus tapered MGU-K could not have supplied")
    print(f"ICE power floor      {df['p_ice_floor_kw'].median():6.0f} kW median across "
          "circuits (smallest engine that closes each lap's budget)")

    df.to_csv(PROCESSED_DIR / "simulation_accuracy.csv", index=False)
    print(f"\nwrote {PROCESSED_DIR / 'simulation_accuracy.csv'} and "
          f"{len(rows)} inferred laps under {MEASURED_DIR}")
    if args.plot:
        plot(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
