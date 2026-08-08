"""Phase 4: train the learned deployment policy and evaluate it honestly.

Validation is LEAVE-ONE-CIRCUIT-OUT. A random split would leak badly: consecutive points
on a lap are near-identical, so a model could memorise a circuit and look like it
generalises. Holding out whole circuits is the only split that tests the claim being made,
which is that the policy transfers to geometry it has never seen.

Models, per the brief:
  gbm       LightGBM classifier over the DP's discrete control set (primary)
  gbm_reg   LightGBM regressor on the deployment fraction
  linear    ridge regression
  always    the naive "deploy whenever available" rule

Every model is scored the same way: run closed-loop through the DP's own physics on the
held-out circuit, and report the percentage of the optimiser's lap-time gain it retains.
Regression metrics are printed too, but they are not the headline — a model can score well
on them while driving badly.

Run:  uv run python -m scripts.train_policy [--models gbm,linear,always]
"""

from __future__ import annotations

import argparse
import json
import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from config.regulations import ES_USABLE_WINDOW_J
from config.vehicle import air_density
from data.cache import PROCESSED_DIR
from ml.features import FEATURE_NAMES
from ml.policy import ClosedLoopResult, Policy, always_deploy_policy, run_closed_loop
from optimiser import dp
from physics.vehicle import VehicleModel

RESULTS_PATH = PROCESSED_DIR / "policy_evaluation.csv"
IMPORTANCE_PATH = PROCESSED_DIR / "feature_importance.csv"
# Evaluate closed-loop at this starting charge, matching the Phase 3 headline scenario.
EVAL_SOC_FRACTION = 0.5


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


def build_gbm_classifier(X, y, controls):
    import lightgbm as lgb

    classes = np.array(controls, dtype=float)
    labels = np.abs(y[:, None] - classes[None, :]).argmin(axis=1)
    present = np.unique(labels)

    model = lgb.LGBMClassifier(
        n_estimators=400, learning_rate=0.06, num_leaves=63,
        min_child_samples=40, subsample=0.9, subsample_freq=1,
        colsample_bytree=0.9, reg_lambda=1.0, verbose=-1, n_jobs=-1,
    )
    model.fit(X, labels)

    def predict(rows):
        idx = model.predict(rows)
        return classes[np.asarray(idx, dtype=int)]

    return Policy(predict, "gbm"), model, present


def build_gbm_regressor(X, y):
    import lightgbm as lgb

    model = lgb.LGBMRegressor(
        n_estimators=400, learning_rate=0.06, num_leaves=63,
        min_child_samples=40, subsample=0.9, subsample_freq=1,
        colsample_bytree=0.9, reg_lambda=1.0, verbose=-1, n_jobs=-1,
    )
    model.fit(X, y)
    return Policy(lambda rows: model.predict(rows), "gbm_reg"), model


def build_linear(X, y):
    model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    model.fit(X, y)
    return Policy(lambda rows: model.predict(rows), "linear"), model


def main() -> int:
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="gbm,gbm_reg,linear,always")
    args = ap.parse_args()
    wanted = {m.strip() for m in args.models.split(",") if m.strip()}

    data_path = PROCESSED_DIR / "training_data.parquet"
    if not data_path.exists():
        print("No training data. Run scripts.build_training_data first.")
        return 1
    data = pd.read_parquet(data_path)
    data["circuit"] = data["circuit"].astype(str)

    comparison = pd.read_csv(PROCESSED_DIR / "strategy_comparison.csv").set_index(
        "circuit_id"
    )
    fit = json.loads((PROCESSED_DIR / "vehicle_fit.json").read_text(encoding="utf-8"))
    circuits = sorted(data["circuit"].unique())
    soc_start_j = EVAL_SOC_FRACTION * ES_USABLE_WINDOW_J

    print(f"{len(data):,} training rows | {len(circuits)} circuits | "
          f"{len(FEATURE_NAMES)} features")
    print(f"Leave-one-circuit-out: {len(circuits)} folds, evaluated closed-loop at "
          f"SoC {soc_start_j / 1e6:.2f} MJ\n")

    rows: list[dict] = []
    importances: list[dict] = []

    for held_out in circuits:
        train = data[data["circuit"] != held_out]
        test = data[data["circuit"] == held_out]
        X_tr = train[FEATURE_NAMES].to_numpy(dtype=float)
        y_tr = train["target_fraction"].to_numpy(dtype=float)
        X_te = test[FEATURE_NAMES].to_numpy(dtype=float)
        y_te = test["target_fraction"].to_numpy(dtype=float)

        geo = json.loads(
            (PROCESSED_DIR / "circuits" / f"{held_out}.json").read_text(encoding="utf-8")
        )
        curvature = np.asarray(geo["curvature_1_per_m"], dtype=float)
        gradient = np.asarray(geo["gradient"], dtype=float)
        step_m = float(geo["step_m"])
        vehicle = VehicleModel.from_fit(
            fit, air_density=circuit_density(held_out, float(fit["air_density"]))
        )
        dp_lap = float(comparison.loc[held_out, "optimal_lap_s"])
        uni_lap = float(comparison.loc[held_out, "uniform_lap_s"])

        built: list[tuple[Policy, object]] = []
        if "gbm" in wanted:
            pol, model, _ = build_gbm_classifier(X_tr, y_tr, dp.DEFAULT_CONTROLS)
            built.append((pol, model))
            importances.append(
                {"held_out": held_out, "model": "gbm",
                 **dict(zip(FEATURE_NAMES, model.feature_importances_))}
            )
        if "gbm_reg" in wanted:
            pol, model = build_gbm_regressor(X_tr, y_tr)
            built.append((pol, model))
            importances.append(
                {"held_out": held_out, "model": "gbm_reg",
                 **dict(zip(FEATURE_NAMES, model.feature_importances_))}
            )
        if "linear" in wanted:
            pol, model = build_linear(X_tr, y_tr)
            built.append((pol, model))
        if "always" in wanted:
            built.append((always_deploy_policy(), None))

        for policy, _model in built:
            pred = policy.predict_fraction(X_te)
            mae = float(mean_absolute_error(y_te, pred))
            res: ClosedLoopResult = run_closed_loop(
                policy, held_out, curvature, gradient, step_m, vehicle,
                soc_start_j=soc_start_j, dp_lap_s=dp_lap, uniform_lap_s=uni_lap,
            )
            rows.append(
                {
                    "held_out": held_out,
                    "model": policy.name,
                    "mae_fraction": mae,
                    "model_lap_s": res.model_lap_s,
                    "dp_lap_s": res.dp_lap_s,
                    "uniform_lap_s": res.uniform_lap_s,
                    "model_gain_s": res.model_gain_s,
                    "dp_gain_s": res.dp_gain_s,
                    "gain_retained_pct": res.gain_retained_pct,
                    "periodic": res.periodic,
                    "soc_end_mj": res.model_soc_end_mj,
                    "clip_pct": res.clip_pct,
                    "notes": "; ".join(res.notes),
                }
            )
            print(f"  {held_out:<18} {policy.name:<9} lap {res.model_lap_s:7.3f}s  "
                  f"gain {res.model_gain_s:+6.3f}s of {res.dp_gain_s:+6.3f}s  "
                  f"retained {res.gain_retained_pct:6.1f}%  "
                  f"MAE {mae:.3f}  periodic={res.periodic}", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(RESULTS_PATH, index=False)

    print("\n" + "=" * 92)
    print("LEAVE-ONE-CIRCUIT-OUT: % OF THE OPTIMISER'S GAIN RETAINED")
    print("=" * 92)
    pivot = df.pivot_table(index="held_out", columns="model",
                           values="gain_retained_pct")
    print(pivot.to_string(float_format=lambda v: f"{v:8.1f}"))

    print("\nSummary by model (ALL folds — see the caveat below):")
    summary = df.groupby("model").agg(
        retained_mean=("gain_retained_pct", "mean"),
        retained_median=("gain_retained_pct", "median"),
        retained_min=("gain_retained_pct", "min"),
        retained_max=("gain_retained_pct", "max"),
        mae=("mae_fraction", "mean"),
        periodic_pct=("periodic", "mean"),
    ).sort_values("retained_mean", ascending=False)
    summary["periodic_pct"] = (100 * summary["periodic_pct"]).round(0)
    print(summary.to_string(float_format=lambda v: f"{v:9.2f}"))

    # A score above 100% is not a model beating the optimiser — the DP is optimal under
    # the periodicity constraint, and the only way past it is to break that constraint.
    # A lap that ends with less charge than it started spent energy it never repaid, so
    # its time is not comparable. The repeatable subset is the honest headline.
    print("\nSummary on REPEATABLE laps only (state of charge periodic):")
    periodic_only = df[df["periodic"]]
    if periodic_only.empty:
        print("  no model produced a repeatable lap on any held-out circuit")
    else:
        strict = periodic_only.groupby("model").agg(
            n_folds=("gain_retained_pct", "size"),
            retained_mean=("gain_retained_pct", "mean"),
            retained_median=("gain_retained_pct", "median"),
            retained_max=("gain_retained_pct", "max"),
        ).sort_values("retained_mean", ascending=False)
        print(strict.to_string(float_format=lambda v: f"{v:9.2f}"))

    over = df[df["gain_retained_pct"] > 100.0]
    if len(over):
        n_np = int((~over["periodic"]).sum())
        print(f"\n  {len(over)} fold(s) scored above 100%, of which {n_np} are NOT "
              "periodic.")
        print("  The DP is optimal subject to periodicity, so beating it means having")
        print("  broken that constraint rather than having found a better strategy.")
        print("  Behavioural cloning has no mechanism to enforce it: the DP gets the")
        print("  constraint as a hard terminal condition, the cloned policy only ever")
        print("  sees state-action pairs and has to rediscover it, which it does not.")

    if importances:
        imp = pd.DataFrame(importances)
        imp.to_csv(IMPORTANCE_PATH, index=False)
        for model_name in imp["model"].unique():
            sub = imp[imp["model"] == model_name][FEATURE_NAMES]
            mean_imp = (sub.mean() / sub.mean().sum() * 100).sort_values(ascending=False)
            print(f"\nFeature importance ({model_name}, mean % across folds):")
            print(mean_imp.head(12).to_string(float_format=lambda v: f"{v:6.2f}"))

    print(f"\nWritten: {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
