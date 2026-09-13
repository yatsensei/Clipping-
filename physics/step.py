"""The one-step transition every simulation in this project runs on.

There used to be two: a forward sweep in physics/simulate.py used by the baselines and
the validation, and a vectorised transition inside the DP used by the optimiser and the
learned-policy scorer. They disagreed in three ways — one modelled the off-throttle
retarding force and the other did not, one fed clipping back into the speed and the
other did not, and their top-speed headroom differed — so greedy and uniform were being
timed on slightly different physics from the strategy they were the baseline for. This
module is the single definition; nothing else integrates the equations of motion.

The control is a signed fraction of the ERS-K ceiling: positive requests deployment
(after the regulatory taper), negative is deliberate off-throttle harvesting with the
ICE not driving. Energy out is the REQUEST; the caller owns the state of charge and
decides what happens when it runs dry, because that is what clipping is.
"""

from __future__ import annotations

import numpy as np

from config.regulations import ERSK_MAX_POWER_W, Mode
from physics.vehicle import VehicleModel

MIN_SPEED_MPS = 5.0


def transition(
    v: np.ndarray,
    control: float,
    curvature_i: float,
    gradient_i: float,
    ceiling_next: float,
    step_m: float,
    vehicle: VehicleModel,
    mode: Mode = "normal",
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Advance every speed in `v` by one distance step under one control.

    Returns (next speed, elapsed time, electrical energy requested, energy harvested),
    all arrays the shape of `v`.
    """
    v = np.maximum(v, MIN_SPEED_MPS)

    deploy = max(control, 0.0)
    harvest_ctl = max(-control, 0.0)

    p_elec = vehicle.electrical_power_w(v, deploy, mode)      # after the regulatory taper
    p_prop = vehicle.driveline_efficiency * (vehicle.p_ice_w + p_elec)
    f_power = p_prop / v
    f_grip = vehicle.max_tractive_force(v, curvature_i)
    f_drive = np.minimum(f_power, f_grip)

    # Out of a slow corner the tyres, not the power unit, set the drive force. The
    # energy actually drawn from the store is then only what the wheels could use
    # beyond the engine — ICE first, MGU-K for the remainder. Charging the full request
    # here would bill a fixed policy for power that never reached the road.
    p_wheel = f_drive * v
    p_elec_used = np.clip(
        p_wheel / vehicle.driveline_efficiency - vehicle.p_ice_w, 0.0, p_elec
    )

    # Deliberate off-throttle harvesting: the MGU-K applies a retarding force and the
    # ICE is not driving, so engine braking applies as well.
    p_harvest_req = harvest_ctl * ERSK_MAX_POWER_W
    f_harvest = p_harvest_req / v
    coasting = harvest_ctl > 0.0
    f_drive = np.where(coasting, 0.0, f_drive)
    f_resist = vehicle.resistive_force(v, gradient_i) + np.where(
        coasting, vehicle.f_offthrottle_n + f_harvest, 0.0
    )

    accel = (f_drive - f_resist) / vehicle.mass_kg
    v_next = np.sqrt(np.maximum(v * v + 2.0 * accel * step_m, MIN_SPEED_MPS**2))
    v_next = np.minimum(v_next, ceiling_next)

    v_avg = np.maximum(0.5 * (v + v_next), MIN_SPEED_MPS)
    dt = step_m / v_avg

    energy_out = np.where(coasting, 0.0, p_elec_used) * dt

    # Harvest comes from two places: the deliberate control, and any braking the speed
    # ceiling forces. Only the part of the deceleration produced by the brakes is
    # recoverable — drag and rolling resistance dissipate to heat and air.
    retarding_n = vehicle.mass_kg * (v * v - v_next * v_next) / (2.0 * step_m)
    resistive_n = vehicle.resistive_force(v_avg, gradient_i)
    brake_n = np.maximum(retarding_n - resistive_n, 0.0)
    p_brake = brake_n * v_avg
    p_recover = np.minimum(p_brake * vehicle.regen_efficiency, ERSK_MAX_POWER_W)
    energy_in = np.where(
        coasting, np.minimum(p_harvest_req, ERSK_MAX_POWER_W), p_recover
    ) * dt

    return v_next, dt, energy_out, energy_in
