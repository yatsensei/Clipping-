"""Baseline deployment strategies the optimiser is measured against.

A lap time gain is meaningless without naming what it is measured against, so both
baselines are defined here explicitly and evaluated on exactly the same physics as the
optimiser.

  greedy   deploy everything available, whenever it is available. The intuitive driver
           strategy, and the one that empties the battery early.
  uniform  spread the energy evenly around the lap, at whatever constant deployment
           fraction makes the lap energy-neutral.

Both are held to the SAME periodicity requirement as the optimiser: a lap that ends with
less energy than it started cannot be repeated, and comparing against a baseline that
cheats on that would inflate the gain.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from config.regulations import ES_USABLE_WINDOW_J, OPERATIVE_HARVEST_CAP_J
from energy.battery import BatteryState
from physics.simulate import LapResult, simulate_lap
from physics.vehicle import VehicleModel


@dataclass
class StrategyResult:
    name: str
    description: str
    lap_time_s: float
    speed_mps: np.ndarray
    soc_j: np.ndarray
    deploy_power_w: np.ndarray
    harvest_power_w: np.ndarray
    clipping: np.ndarray
    energy_deployed_j: float
    energy_harvested_j: float
    soc_start_j: float
    soc_end_j: float
    periodic: bool
    deploy_fraction: np.ndarray

    @property
    def soc_deficit_j(self) -> float:
        return self.soc_start_j - self.soc_end_j

    @property
    def clipping_fraction(self) -> float:
        return float(np.mean(self.clipping))


def _run(
    curvature, gradient, step_m, vehicle, policy, soc_start_j, capacity_j, harvest_cap_j
) -> LapResult:
    battery = BatteryState(
        soc_j=soc_start_j, capacity_j=capacity_j, harvest_cap_j=harvest_cap_j
    )
    return simulate_lap(curvature, gradient, step_m, vehicle, policy, battery)


def greedy(
    curvature: np.ndarray,
    gradient: np.ndarray,
    step_m: float,
    vehicle: VehicleModel,
    soc_start_j: float = ES_USABLE_WINDOW_J,
    capacity_j: float = ES_USABLE_WINDOW_J,
    harvest_cap_j: float = OPERATIVE_HARVEST_CAP_J,
) -> StrategyResult:
    """Deploy the full regulatory ceiling everywhere, until the battery is empty."""
    policy = np.ones(len(curvature))
    res = _run(curvature, gradient, step_m, vehicle, policy, soc_start_j, capacity_j,
               harvest_cap_j)
    return _wrap("greedy", "full deployment requested at every point", res, policy)


def uniform(
    curvature: np.ndarray,
    gradient: np.ndarray,
    step_m: float,
    vehicle: VehicleModel,
    soc_start_j: float = ES_USABLE_WINDOW_J,
    capacity_j: float = ES_USABLE_WINDOW_J,
    harvest_cap_j: float = OPERATIVE_HARVEST_CAP_J,
    tolerance_j: float = 5_000.0,
) -> StrategyResult:
    """Constant deployment fraction, bisected until the lap is energy-neutral.

    Spreading energy evenly is only a fair baseline if it is also repeatable, so the
    fraction is chosen to leave the state of charge where it started rather than fixed
    at some arbitrary level.

    Note on the starting charge: this degenerates to ~zero deployment if the store starts
    FULL, because a full store cannot accept braking energy, so nothing refills what a
    constant deployment drains. Callers should start with headroom (the runner uses half
    the usable window) or the comparison is against a baseline that simply never deploys.
    """
    n = len(curvature)
    lo, hi = 0.0, 1.0

    def deficit(frac: float) -> tuple[float, LapResult]:
        res = _run(curvature, gradient, step_m, vehicle, np.full(n, frac),
                   soc_start_j, capacity_j, harvest_cap_j)
        return res.soc_start_j - res.soc_end_j, res

    d_hi, res_hi = deficit(hi)
    if d_hi <= tolerance_j:
        # Even full deployment is self-sustaining on this circuit.
        return _wrap("uniform", "constant deployment, energy-neutral over the lap",
                     res_hi, np.full(n, hi))

    best = res_hi
    frac = hi
    for _ in range(28):
        mid = 0.5 * (lo + hi)
        d_mid, res_mid = deficit(mid)
        if d_mid > tolerance_j:
            hi = mid
        else:
            lo = mid
            best, frac = res_mid, mid
        if abs(d_mid) <= tolerance_j:
            best, frac = res_mid, mid
            break

    return _wrap("uniform", f"constant deployment at {frac:.3f} of the ceiling, "
                            "chosen so the lap is energy-neutral", best,
                 np.full(n, frac))


def _wrap(name: str, description: str, res: LapResult, policy: np.ndarray) -> StrategyResult:
    return StrategyResult(
        name=name,
        description=description,
        lap_time_s=res.lap_time_s,
        speed_mps=res.speed_mps,
        soc_j=res.soc_j,
        deploy_power_w=res.deploy_power_w,
        harvest_power_w=res.harvest_power_w,
        clipping=res.clipping,
        energy_deployed_j=res.energy_deployed_j,
        energy_harvested_j=res.energy_harvested_j,
        soc_start_j=res.soc_start_j,
        soc_end_j=res.soc_end_j,
        periodic=bool(res.soc_end_j >= res.soc_start_j - 5_000.0),
        deploy_fraction=policy,
    )
