"""The learned deployment policy, and how it is scored.

Behavioural cloning of a physics-based planner. The DP generates the labels; the model
learns to reproduce its decisions from local features. There is no real-world label to
learn from — public F1 telemetry contains no energy channels at all — so this is imitation
of an optimiser, not supervised learning on measured deployment, and it is only as good as
the optimiser and the vehicle model behind it.

Scoring. Regression accuracy on deployment fraction is a poor measure: neighbouring points
on a lap are nearly identical, so a model can score well while producing a policy that
drives badly, and most of the target mass sits on three values. What matters is what the
policy DOES, so every model is run closed-loop through the same physics the DP used and
scored on

    gain retained = (uniform_time - model_time) / (uniform_time - dp_time)

100% means the learned policy matched the optimiser's lap time; 0% means it did no better
than uniform deployment; negative means it was worse than doing nothing clever.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from config.regulations import ES_USABLE_WINDOW_J
from ml.features import (
    DYNAMIC_FEATURES,
    FEATURE_NAMES,
    STATIC_FEATURES,
    build_static,
    dynamic_row,
)
from optimiser import dp
from physics.vehicle import VehicleModel


@dataclass
class ClosedLoopResult:
    circuit: str
    model_lap_s: float
    dp_lap_s: float
    uniform_lap_s: float
    gain_retained_pct: float
    model_deployed_mj: float
    dp_deployed_mj: float
    model_soc_end_mj: float
    soc_start_mj: float
    periodic: bool
    clip_pct: float
    notes: list[str] = field(default_factory=list)

    @property
    def model_gain_s(self) -> float:
        return self.uniform_lap_s - self.model_lap_s

    @property
    def dp_gain_s(self) -> float:
        return self.uniform_lap_s - self.dp_lap_s


class Policy:
    """Wraps a fitted estimator so it can drive a lap.

    `predict_fraction(X)` must return the requested control in [-1, 1] for a batch of
    feature rows. Classifiers return the control value of the most likely class.
    """

    def __init__(self, predict_fraction, name: str):
        self.predict_fraction = predict_fraction
        self.name = name


def snap_to_controls(values: np.ndarray, controls=dp.DEFAULT_CONTROLS) -> np.ndarray:
    """Round predictions onto the DP's control set.

    The optimal policy is bang-bang, so intermediate predictions are usually the model
    hedging between neighbouring decisions rather than a genuinely partial request.
    """
    grid = np.asarray(controls, dtype=float)
    idx = np.abs(np.asarray(values, dtype=float)[:, None] - grid[None, :]).argmin(axis=1)
    return grid[idx]


def run_closed_loop(
    policy: Policy,
    circuit_id: str,
    curvature: np.ndarray,
    gradient: np.ndarray,
    step_m: float,
    vehicle: VehicleModel,
    soc_start_j: float,
    dp_lap_s: float,
    uniform_lap_s: float,
    capacity_j: float = ES_USABLE_WINDOW_J,
    snap: bool = True,
) -> ClosedLoopResult:
    """Drive one lap under the learned policy, through the DP's own physics."""
    ceiling = dp.speed_ceiling(curvature, gradient, step_m, vehicle)
    static = build_static(curvature, gradient, ceiling, step_m)

    # Static features never change during the lap, so build the block once and only fill
    # in the dynamic columns per step. Predicting one row at a time is the cost driver.
    static_block = np.column_stack([static[name] for name in STATIC_FEATURES])
    dyn_index = {name: len(STATIC_FEATURES) + j for j, name in enumerate(DYNAMIC_FEATURES)}
    row = np.zeros((1, len(FEATURE_NAMES)))

    # `i` arrives in the circuit's own grid space (see dp.rollout), which is the space
    # static_block is built in, so it indexes directly.
    def choose(i: int, v: float, soc: float, ceil_i: float) -> float:
        row[0, : len(STATIC_FEATURES)] = static_block[i]
        d = dynamic_row(
            speed_mps=v,
            soc_j=soc,
            capacity_j=capacity_j,
            ceiling_mps=ceil_i,
            next_apex_speed_mps=float(static["next_apex_speed_mps"][i]),
        )
        for name, col in dyn_index.items():
            row[0, col] = d[name]
        pred = float(policy.predict_fraction(row)[0])
        return float(snap_to_controls(np.array([pred]))[0]) if snap else pred

    res = dp.rollout(
        curvature, gradient, step_m, vehicle, choose,
        ceiling=ceiling, soc_start_j=soc_start_j, capacity_j=capacity_j, rotate=True,
    )

    dp_gain = uniform_lap_s - dp_lap_s
    model_gain = uniform_lap_s - res.lap_time_s
    retained = 100.0 * model_gain / dp_gain if abs(dp_gain) > 1e-9 else float("nan")

    notes = []
    if res.soc_end_j < soc_start_j:
        notes.append(
            f"not periodic: ended {(soc_start_j - res.soc_end_j) / 1e6:.3f} MJ short, so "
            "this lap is not repeatable and its time flatters the policy"
        )

    return ClosedLoopResult(
        circuit=circuit_id,
        model_lap_s=res.lap_time_s,
        dp_lap_s=dp_lap_s,
        uniform_lap_s=uniform_lap_s,
        gain_retained_pct=retained,
        model_deployed_mj=res.energy_deployed_j / 1e6,
        dp_deployed_mj=float("nan"),
        model_soc_end_mj=res.soc_end_j / 1e6,
        soc_start_mj=soc_start_j / 1e6,
        periodic=bool(res.soc_end_j >= soc_start_j),
        clip_pct=100.0 * float(res.clipping.mean()),
        notes=notes,
    )


def always_deploy_policy() -> Policy:
    """The naive rule from the brief: ask for everything, always."""
    return Policy(lambda X: np.ones(len(X)), "always-deploy")
