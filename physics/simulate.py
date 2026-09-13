"""Lap simulation on the distance grid: the speed ceiling, and a policy runner.

The speed CEILING — cornering- and braking-limited — is independent of deployment,
because braking is grip limited rather than power limited. It is computed once:

  1. cornering limit   v <= corner_speed_limit(kappa)
  2. braking pass      walk backwards so the car can decelerate into each corner

and used as a hard cap at every step. The lap is a closed loop, so the backward pass
iterates around it until the profile stops changing rather than assuming a boundary.

`rollout` then runs ANY deployment policy forward through physics/step.py from the
lap's slowest point, where the ceiling binds whatever the driver has done and start and
end speed are therefore equal by construction. The DP's table, a learned model, a
constant baseline and a deployment inferred from real telemetry are all timed here, so
no comparison between them can be contaminated by differing simulation details.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from config.regulations import ES_USABLE_WINDOW_J, OPERATIVE_HARVEST_CAP_J, Mode
from energy.battery import BatteryState
from physics.step import MIN_SPEED_MPS, transition
from physics.vehicle import VehicleModel

MAX_SWEEPS = 12
CONVERGENCE_MPS = 0.01
# Headroom above the model's terminal speed. The ceiling must not bind on a straight —
# that is the powertrain's job — but a large margin widens the DP's speed grid for
# nothing, since no strategy gets there.
TERMINAL_HEADROOM = 1.02


@dataclass
class LapResult:
    lap_time_s: float
    distance_m: np.ndarray
    speed_mps: np.ndarray
    deploy_fraction: np.ndarray     # control applied, per grid point
    deploy_power_w: np.ndarray      # electrical power actually delivered
    harvest_power_w: np.ndarray
    soc_j: np.ndarray
    clipping: np.ndarray            # asked for power the store could not give
    braking: np.ndarray             # decelerating over the step
    energy_deployed_j: float
    energy_harvested_j: float
    soc_start_j: float
    soc_end_j: float
    clipping_time_s: float
    # Set by the optimiser; defaults for every other policy.
    harvest_multiplier: float = 0.0
    feasible: bool = True
    notes: list[str] = field(default_factory=list)

    @property
    def speed_kph(self) -> np.ndarray:
        return self.speed_mps * 3.6

    @property
    def soc_deficit_j(self) -> float:
        return self.soc_start_j - self.soc_end_j

    @property
    def periodic(self) -> bool:
        """Did the lap end with at least the energy it started with?"""
        return bool(self.soc_end_j >= self.soc_start_j)


# ---------------------------------------------------------------------- ceiling


def cornering_profile(curvature: np.ndarray, vehicle: VehicleModel,
                      v_cap_mps: float) -> np.ndarray:
    return np.minimum(vehicle.corner_speed_limit(curvature), v_cap_mps)


def braking_profile(
    v_ceiling: np.ndarray,
    step_m: float,
    vehicle: VehicleModel,
    gradient: np.ndarray,
    curvature: np.ndarray,
) -> np.ndarray:
    """Backward pass: limit entry speed so each corner can still be braked for.

    Braking grip is shared with cornering through the friction ellipse, so a car already
    loaded up laterally cannot also brake at its straight-line maximum. Aerodynamic drag
    helps it slow down regardless, so that is added on top of the tyre-limited part.
    """
    v = v_ceiling.copy()
    n = len(v)
    for _ in range(MAX_SWEEPS):
        before = v.copy()
        for j in range(n):
            i = (n - 1 - j) % n
            nxt = (i + 1) % n
            tyre = vehicle.braking_limit(v[nxt]) * vehicle.grip_available_fraction(
                v[nxt], curvature[nxt]
            )
            decel = (
                float(tyre)
                + vehicle.resistive_force(v[nxt], gradient[nxt]) / vehicle.mass_kg
            )
            decel = max(decel, 0.5)
            reachable = np.sqrt(max(v[nxt] ** 2 + 2.0 * decel * step_m, 0.0))
            v[i] = min(v[i], reachable)
        if np.max(np.abs(before - v)) < CONVERGENCE_MPS:
            break
    return v


def speed_ceiling(
    curvature: np.ndarray, gradient: np.ndarray, step_m: float, vehicle: VehicleModel
) -> np.ndarray:
    """Cornering- and braking-limited speed, independent of the deployment strategy."""
    v_cap = vehicle.terminal_speed_mps(1.0) * TERMINAL_HEADROOM
    v_corner = cornering_profile(curvature, vehicle, v_cap)
    return braking_profile(v_corner, step_m, vehicle, gradient, curvature)


# ---------------------------------------------------------------------- rollout

Policy = Callable[[int, float, float, float], float]


def rollout(
    curvature: np.ndarray,
    gradient: np.ndarray,
    step_m: float,
    vehicle: VehicleModel,
    choose: Policy,
    ceiling: np.ndarray | None = None,
    soc_start_j: float | None = None,
    capacity_j: float = ES_USABLE_WINDOW_J,
    harvest_cap_j: float = OPERATIVE_HARVEST_CAP_J,
    rotate: bool = True,
    mode: Mode = "normal",
) -> LapResult:
    """Run a deployment policy forward through the exact physics.

    `choose(index, speed_mps, soc_j, ceiling_mps) -> control` in [-1, 1].

    With rotate=True (the default, and how the DP is solved) the lap starts at its
    slowest point. `index` is always in the CIRCUIT'S OWN grid space, not the rotated
    stage order, so callers can index geometry and precomputed features directly.
    Getting this wrong is silent and severe: feeding a policy features from the wrong
    part of the track scored -446% of the optimiser's gain when it was first tried.

    When the store cannot supply what a step asked for, the step is recomputed with
    the power that was actually available, so clipping costs the time it really costs.
    """
    soc_start_j = capacity_j if soc_start_j is None else soc_start_j
    if ceiling is None:
        ceiling = speed_ceiling(curvature, gradient, step_m, vehicle)
    shift = int(np.argmin(ceiling)) if rotate else 0
    if shift:
        ceiling = np.roll(ceiling, -shift)
        curvature = np.roll(curvature, -shift)
        gradient = np.roll(gradient, -shift)

    n = len(curvature)
    v = float(ceiling[0])
    soc = float(soc_start_j)
    total_t = 0.0
    deployed = harvested = clip_t = 0.0

    frac = np.zeros(n)
    speeds = np.zeros(n)
    socs = np.zeros(n)
    p_dep = np.zeros(n)
    p_har = np.zeros(n)
    clip = np.zeros(n, dtype=bool)
    brake = np.zeros(n, dtype=bool)

    for i in range(n):
        original_i = (i + shift) % n
        u = float(np.clip(choose(original_i, v, soc, float(ceiling[i])), -1.0, 1.0))

        v_next, dt, e_out, e_in = transition(
            np.array([v]), u, curvature[i], gradient[i], ceiling[(i + 1) % n],
            step_m, vehicle, mode,
        )
        v_next = float(v_next[0]); dt = float(dt[0])
        e_out = float(e_out[0]); e_in = float(e_in[0])

        draw = min(soc, e_out)
        if e_out - draw > 1.0:
            clip[i] = True
            available_frac = (draw / e_out) * max(u, 0.0) if e_out > 0 else 0.0
            v_next2, dt2, e_out2, e_in2 = transition(
                np.array([v]), available_frac, curvature[i], gradient[i],
                ceiling[(i + 1) % n], step_m, vehicle, mode,
            )
            v_next, dt = float(v_next2[0]), float(dt2[0])
            e_out, e_in = float(e_out2[0]), float(e_in2[0])
            draw = min(soc, e_out)
            clip_t += dt

        # Harvest is bounded by SoC headroom AND the per-lap regulatory cap.
        headroom = capacity_j - (soc - draw)
        gained = max(min(e_in, headroom, harvest_cap_j - harvested), 0.0)
        soc = min(max(soc - draw + gained, 0.0), capacity_j)

        deployed += draw
        harvested += gained
        total_t += dt

        frac[i] = u
        speeds[i] = v
        socs[i] = soc
        p_dep[i] = draw / dt if dt > 0 else 0.0
        p_har[i] = gained / dt if dt > 0 else 0.0
        brake[i] = v_next < v - 1e-6
        v = v_next

    result = LapResult(
        lap_time_s=total_t,
        distance_m=np.arange(n) * step_m,
        speed_mps=speeds,
        deploy_fraction=frac,
        deploy_power_w=p_dep,
        harvest_power_w=p_har,
        soc_j=socs,
        clipping=clip,
        braking=brake,
        energy_deployed_j=deployed,
        energy_harvested_j=harvested,
        soc_start_j=soc_start_j,
        soc_end_j=soc,
        clipping_time_s=clip_t,
    )
    if shift:
        for name in ("deploy_fraction", "speed_mps", "soc_j", "deploy_power_w",
                     "harvest_power_w", "clipping", "braking"):
            setattr(result, name, np.roll(getattr(result, name), shift))
    return result


def simulate_lap(
    curvature: np.ndarray,
    gradient: np.ndarray,
    step_m: float,
    vehicle: VehicleModel,
    deploy_fraction: np.ndarray,
    battery: BatteryState,
    mode: Mode = "normal",
    ceiling: np.ndarray | None = None,
) -> LapResult:
    """Simulate one lap under a fixed per-point control, in [-1, 1].

    A convenience over `rollout` for policies known in advance: the baselines, the
    validation, and a deployment inferred from a real lap.
    """
    n = len(curvature)
    if len(deploy_fraction) != n or len(gradient) != n:
        raise ValueError("policy, gradient and curvature must share the distance grid")
    policy = np.asarray(deploy_fraction, dtype=float)
    return rollout(
        curvature, gradient, step_m, vehicle,
        lambda i, _v, _soc, _ceiling: float(policy[i]),
        ceiling=ceiling,
        soc_start_j=battery.soc_j,
        capacity_j=battery.capacity_j,
        harvest_cap_j=battery.harvest_cap_j,
        mode=mode,
    )
