"""Inverse dynamics: what did the driver actually deploy?

Public telemetry has speed, throttle and brake but no energy channels. The force
balance, however, runs both ways. Given the measured speed along the lap, the model's
resistive forces and its engine, the electrical power the car MUST have been receiving
at each point is whatever the observed acceleration needed beyond what the engine
could give:

    P_wheel  = (m * dv/dt + F_drag + F_roll + F_grade) * v
    P_elec   = clip(P_wheel / eta - P_ice, 0, ceiling(v))

and under braking, the recoverable part is the retarding force the brakes provided
beyond drag and rolling resistance, at the regen efficiency, capped at the MGU-K limit.

This gives two things. A "measured" deployment strategy — the only one on the site that
is not the optimiser's own output — and a check the model must pass: integrating that
deployment around a qualifying lap that started with a full store must not need more
energy than the store plus what it recovered. If it does, the engine in the model is
too weak, which is how the ICE power floor in `ice_power_floor` is found. That is the
closest thing to identifying P_ice the public data allows: the cars never run above
the taper's zero point where the engine would be alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.signal import savgol_filter

from config.regulations import (
    ERSK_MAX_POWER_W,
    ES_USABLE_WINDOW_J,
    OPERATIVE_HARVEST_CAP_J,
    max_deploy_power_w,
)
from physics.vehicle import VehicleModel

# Throttle below which the driver is off the pedal, and the ICE is not driving.
COAST_THROTTLE = 5.0
# Public speed is quantised to whole km/h at ~4 Hz. Differentiated raw on a 5 m grid at
# 80 m/s that quantisation alone is worth ~300 kW of noise, so the trace is smoothed over
# this distance first — long enough to average several samples, short against a
# braking zone. The geometry pipeline smooths curvature over 45 m for the same reason.
SMOOTH_WINDOW_M = 85.0
# No propulsion produces more than this; a step that implies it is a data artefact.
MAX_PLAUSIBLE_ACCEL = 25.0
# The resampled lap does not join at the line — the first samples of a lap are a ramp
# from wherever the telemetry stream picked up — so steps this close to the seam are
# not trusted in either direction.
SEAM_MARGIN_M = 30.0


@dataclass
class InferredLap:
    """A deployment reconstructed from a measured lap, on the geometry grid."""

    speed_mps: np.ndarray
    lap_time_s: float
    # Per step, as the rollout understands them: fraction of the ceiling (positive) or
    # of the harvest limit (negative).
    deploy_fraction: np.ndarray
    deploy_power_w: np.ndarray
    harvest_power_w: np.ndarray
    soc_j: np.ndarray
    # Power the observed acceleration required at the crank, and what the model's
    # engine alone could give. Their difference is the electrical demand.
    p_crank_w: np.ndarray
    p_ice_w: float
    energy_deployed_j: float
    energy_harvested_j: float
    soc_start_j: float
    soc_end_j: float
    # Electrical energy the lap needed that neither the ceiling nor the store could
    # supply. Zero means the model's engine and store explain the lap; positive means
    # something in the model is too weak.
    unexplained_j: float
    unexplained_over_ceiling_j: float
    unexplained_over_store_j: float
    # Steps not trusted: the seam, and implausible accelerations.
    masked_steps: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def budget_closes(self) -> bool:
        return self.unexplained_j < 1e3


def infer_deployment(
    speed_mps: np.ndarray,
    throttle: np.ndarray,
    brake: np.ndarray,
    curvature: np.ndarray,
    gradient: np.ndarray,
    step_m: float,
    vehicle: VehicleModel,
    lap_time_s: float,
    soc_start_j: float = ES_USABLE_WINDOW_J,
    capacity_j: float = ES_USABLE_WINDOW_J,
    harvest_cap_j: float = OPERATIVE_HARVEST_CAP_J,
    smooth_window_m: float = SMOOTH_WINDOW_M,
) -> InferredLap:
    """Reconstruct deployment and harvest from a measured speed trace.

    The trace is the reference lap resampled onto the circuit's distance grid, so the
    step is uniform in distance and the lap is closed. A qualifying lap starts with
    the store full — that is what the out-lap is for — so `soc_start_j` defaults to
    the top of the usable window.
    """
    raw = np.asarray(speed_mps, dtype=float)
    n = len(raw)
    if len(throttle) != n or len(brake) != n or len(curvature) != n:
        raise ValueError("speed, throttle, brake and geometry must share the grid")
    thr = np.asarray(throttle, dtype=float)
    brk = np.asarray(brake, dtype=bool)

    window = int(round(smooth_window_m / step_m))
    window += 1 - window % 2
    v = savgol_filter(raw, window, 2, mode="nearest") if window >= 5 else raw.copy()

    v0 = np.maximum(v, 1.0)
    v1 = np.maximum(np.roll(v, -1), 1.0)
    v_avg = 0.5 * (v0 + v1)
    accel = (v1 * v1 - v0 * v0) / (2.0 * step_m)
    dt = step_m / v_avg

    # Steps that cannot be trusted contribute nothing in either direction.
    seam = int(np.ceil(SEAM_MARGIN_M / step_m))
    trusted = np.ones(n, dtype=bool)
    trusted[:seam] = False
    trusted[n - seam:] = False
    trusted &= accel < MAX_PLAUSIBLE_ACCEL
    masked = int((~trusted).sum())

    on_power = thr > COAST_THROTTLE
    f_resist = vehicle.resistive_force(v_avg, gradient, curvature, driving=on_power)
    f_req = vehicle.mass_kg * accel + f_resist
    p_wheel = f_req * v_avg
    p_crank = p_wheel / vehicle.driveline_efficiency

    ceiling = np.array([max_deploy_power_w(x * 3.6, "normal") for x in v_avg])

    driving = (p_wheel > 0.0) & on_power & trusted
    # ICE first: the electrical demand is what the engine could not have given.
    demand = np.where(driving, np.maximum(p_crank - vehicle.p_ice_w, 0.0), 0.0)
    over_ceiling = np.maximum(demand - ceiling, 0.0)
    p_elec = np.minimum(demand, ceiling)

    # Off the throttle, anything slowing the car beyond drag and rolling resistance is
    # the brakes or the MGU-K, and the recoverable part of it is the regen share.
    retarding = np.where((~driving) & trusted, np.maximum(-f_req, 0.0), 0.0)
    p_recover = np.minimum(retarding * v_avg * vehicle.regen_efficiency, ERSK_MAX_POWER_W)
    # Only credit recovery where the driver is actually off the pedal or braking; a
    # part-throttle balance point is neither.
    p_recover = np.where(brk | (thr <= COAST_THROTTLE), p_recover, 0.0)

    # Integrate the store around the lap under the regulatory limits.
    soc = float(soc_start_j)
    socs = np.zeros(n)
    deployed = harvested = 0.0
    over_store = 0.0
    p_dep = np.zeros(n)
    p_har = np.zeros(n)
    for i in range(n):
        # The motor's output is what the lap needed; the store gave up a little more.
        want = p_elec[i] * dt[i] / vehicle.discharge_efficiency
        draw = min(want, soc)
        over_store += want - draw
        headroom = capacity_j - (soc - draw)
        gained = max(min(p_recover[i] * dt[i], headroom, harvest_cap_j - harvested), 0.0)
        soc = min(max(soc - draw + gained, 0.0), capacity_j)
        deployed += draw
        harvested += gained
        socs[i] = soc
        p_dep[i] = draw * vehicle.discharge_efficiency / dt[i]   # at the motor
        p_har[i] = gained / dt[i]

    over_ceiling_j = float(np.sum(over_ceiling * dt))
    fraction = np.where(
        driving & (ceiling > 0), p_elec / np.maximum(ceiling, 1.0), 0.0
    )
    # Deliberate lift-and-coast harvesting shows up as a negative control.
    coasting = (~driving) & (~brk) & (thr <= COAST_THROTTLE) & (p_recover > 0)
    fraction = np.where(coasting, -p_recover / ERSK_MAX_POWER_W, fraction)

    notes = []
    if over_ceiling_j > 1e3:
        notes.append(
            f"{over_ceiling_j / 1e6:.2f} MJ of the lap's propulsive energy exceeds what "
            "the engine plus the tapered MGU-K could deliver: the model's engine or "
            "driveline is too weak, or its drag too high, at those points."
        )
    if over_store > 1e3:
        notes.append(
            f"{over_store / 1e6:.2f} MJ of deployment came after the modelled store was "
            "empty: the lap needs more energy than a full store plus recovery provides."
        )

    return InferredLap(
        speed_mps=raw,
        lap_time_s=float(lap_time_s),
        deploy_fraction=fraction,
        deploy_power_w=p_dep,
        harvest_power_w=p_har,
        soc_j=socs,
        p_crank_w=p_crank,
        p_ice_w=vehicle.p_ice_w,
        energy_deployed_j=float(deployed),
        energy_harvested_j=float(harvested),
        soc_start_j=float(soc_start_j),
        soc_end_j=float(soc),
        unexplained_j=float(over_ceiling_j + over_store),
        unexplained_over_ceiling_j=over_ceiling_j,
        unexplained_over_store_j=float(over_store),
        masked_steps=masked,
        notes=notes,
    )


def ice_power_floor(
    speed_mps: np.ndarray,
    throttle: np.ndarray,
    brake: np.ndarray,
    curvature: np.ndarray,
    gradient: np.ndarray,
    step_m: float,
    vehicle: VehicleModel,
    lap_time_s: float,
    lo_w: float = 150_000.0,
    hi_w: float = 900_000.0,
    tolerance_w: float = 1_000.0,
    slack: float = 0.02,
    smooth_window_m: float = SMOOTH_WINDOW_M,
) -> float:
    """The smallest engine power at which the measured lap's energy budget closes.

    Electrical demand falls monotonically as the assumed engine grows, so this is a
    bisection on `unexplained_j`. "Closes" allows `slack` of the lap's deployed energy
    to go unexplained, because a handful of glitched samples would otherwise decide
    the answer. Returns `hi_w` if even that does not close the budget, which would
    mean the drag or mass in the model is wrong, not the engine.
    """
    from dataclasses import replace

    def closes(p_ice: float) -> bool:
        veh = replace(vehicle, p_ice_w=p_ice)
        lap = infer_deployment(
            speed_mps, throttle, brake, curvature, gradient, step_m, veh, lap_time_s,
            smooth_window_m=smooth_window_m,
        )
        return lap.unexplained_j <= slack * max(lap.energy_deployed_j, 1.0)

    if not closes(hi_w):
        return hi_w
    if closes(lo_w):
        return lo_w
    while hi_w - lo_w > tolerance_w:
        mid = 0.5 * (lo_w + hi_w)
        if closes(mid):
            hi_w = mid
        else:
            lo_w = mid
    return hi_w
