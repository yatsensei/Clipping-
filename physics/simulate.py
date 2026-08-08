"""Quasi-steady-state lap simulation on the distance grid.

Three passes, the standard structure for a lap simulator:

  1. cornering limit   v <= corner_speed_limit(kappa)
  2. braking pass      walk backwards so the car can decelerate into each corner
  3. traction pass     walk forwards applying available power, capped by the above

The lap is a closed loop, so the backward and forward passes iterate around it until the
speed profile stops changing rather than assuming a start-of-lap boundary condition.

Energy is integrated along the forward pass. When the store empties, deployment is cut to
whatever remains and the point is flagged as clipping.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from energy.battery import BatteryState
from physics.vehicle import VehicleModel

MAX_SWEEPS = 12
CONVERGENCE_MPS = 0.01


@dataclass
class LapResult:
    distance_m: np.ndarray
    speed_mps: np.ndarray
    time_s: np.ndarray            # cumulative
    lap_time_s: float
    deploy_power_w: np.ndarray    # electrical power actually delivered
    deploy_request: np.ndarray    # what the policy asked for, before taper and SoC
    harvest_power_w: np.ndarray
    soc_j: np.ndarray
    clipping: np.ndarray          # bool per point
    braking: np.ndarray
    energy_deployed_j: float
    energy_harvested_j: float
    soc_start_j: float
    soc_end_j: float
    clipping_time_s: float

    @property
    def speed_kph(self) -> np.ndarray:
        return self.speed_mps * 3.6


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


def simulate_lap(
    curvature: np.ndarray,
    gradient: np.ndarray,
    step_m: float,
    vehicle: VehicleModel,
    deploy_fraction: np.ndarray,
    battery: BatteryState,
    mode: str = "normal",
) -> LapResult:
    """Simulate one lap under a given deployment policy.

    `deploy_fraction` is the requested share of the regulatory ceiling at each point,
    in [0, 1]. The taper and the state of charge decide what is actually delivered.
    """
    n = len(curvature)
    if len(deploy_fraction) != n or len(gradient) != n:
        raise ValueError("policy, gradient and curvature must share the distance grid")

    v_cap = vehicle.terminal_speed_mps(1.0) * 1.05
    v_corner = cornering_profile(curvature, vehicle, v_cap)
    v_ceiling = braking_profile(v_corner, step_m, vehicle, gradient, curvature)

    # Forward sweeps settle the closed-loop speed profile before energy is integrated,
    # so the store is not charged against a speed profile that is still changing.
    v = v_ceiling.copy()
    for _ in range(MAX_SWEEPS):
        before = v.copy()
        for i in range(n):
            nxt = (i + 1) % n
            accel = _traction_accel(v[i], deploy_fraction[i], gradient[i],
                                    curvature[i], vehicle, mode)
            reachable = np.sqrt(max(v[i] ** 2 + 2.0 * accel * step_m, 0.0))
            v[nxt] = min(v_ceiling[nxt], reachable)
        if np.max(np.abs(before - v)) < CONVERGENCE_MPS:
            break

    return _integrate(v, v_ceiling, curvature, gradient, step_m, vehicle,
                      deploy_fraction, battery, mode)


def _traction_accel(
    v: float, deploy: float, gradient: float, curvature: float,
    vehicle: VehicleModel, mode: str,
) -> float:
    """Longitudinal acceleration, limited by BOTH available power and available grip."""
    power_n = float(vehicle.tractive_force(v, deploy, mode))
    grip_n = float(vehicle.max_tractive_force(v, curvature))
    drive_n = min(power_n, grip_n)
    return float((drive_n - vehicle.resistive_force(v, gradient)) / vehicle.mass_kg)


def _integrate(
    v: np.ndarray,
    v_ceiling: np.ndarray,
    curvature: np.ndarray,
    gradient: np.ndarray,
    step_m: float,
    vehicle: VehicleModel,
    deploy_fraction: np.ndarray,
    battery: BatteryState,
    mode: str,
) -> LapResult:
    n = len(v)
    soc_start = battery.soc_j
    times = np.zeros(n)
    deploy_actual = np.zeros(n)
    deploy_request = np.zeros(n)
    harvest = np.zeros(n)
    soc = np.zeros(n)
    clipping = np.zeros(n, dtype=bool)
    braking = np.zeros(n, dtype=bool)

    t = 0.0
    for i in range(n):
        nxt = (i + 1) % n
        v_avg = max(0.5 * (v[i] + v[nxt]), 1.0)
        dt = step_m / v_avg
        t += dt
        times[i] = t

        # Decelerating means the driver is off power and on the brakes.
        is_braking = v[nxt] < v[i] - 1e-6
        braking[i] = is_braking

        requested_w = float(
            vehicle.electrical_power_w(v_avg, deploy_fraction[i], mode)
        )
        deploy_request[i] = requested_w

        if is_braking:
            # Only the part of the deceleration produced by the brakes is recoverable.
            # Aerodynamic drag and rolling resistance also slow the car, and that energy
            # goes to heat and air — crediting it to the battery would inflate harvest.
            decel = (v[i] ** 2 - v[nxt] ** 2) / (2.0 * step_m)
            retarding_n = vehicle.mass_kg * decel
            resistive_n = float(vehicle.resistive_force(v_avg, gradient[i]))
            brake_power_w = max(0.0, (retarding_n - resistive_n) * v_avg)
            recoverable_w = min(
                brake_power_w * vehicle.regen_efficiency, vehicle.max_harvest_power_w()
            )
            gained = battery.charge(recoverable_w * dt)
            harvest[i] = gained / dt if dt > 0 else 0.0
        elif requested_w > 0.0:
            delivered = battery.draw(requested_w * dt)
            deploy_actual[i] = delivered / dt if dt > 0 else 0.0
            if requested_w - deploy_actual[i] > 1_000.0:
                clipping[i] = True
                battery.clipping_time_s += dt

        soc[i] = battery.soc_j

    return LapResult(
        distance_m=np.arange(n) * step_m,
        speed_mps=v,
        time_s=times,
        lap_time_s=float(t),
        deploy_power_w=deploy_actual,
        deploy_request=deploy_request,
        harvest_power_w=harvest,
        soc_j=soc,
        clipping=clipping,
        braking=braking,
        energy_deployed_j=battery.deployed_j,
        energy_harvested_j=battery.harvested_j,
        soc_start_j=soc_start,
        soc_end_j=battery.soc_j,
        clipping_time_s=battery.clipping_time_s,
    )
