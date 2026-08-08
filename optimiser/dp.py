"""Dynamic programming solver for lap-time-optimal electrical deployment.

Formulation
-----------
  stage    distance along the lap, on the 5 m geometry grid
  state    (state of charge, speed)
  control  signed fraction of the ERS-K ceiling: positive deploys, negative harvests
  cost     time elapsed over the step
  goal     minimise lap time subject to the state of charge being periodic

Why speed is a state. The brief suggests treating speed as determined by forward
simulation given the deployment decision, but that only holds if deployment is fixed:
the whole point here is that it varies, and the speed a step inherits depends on every
decision before it. Carrying speed as a state is what makes the optimiser able to trade
energy between one part of the lap and another.

Two things keep this tractable:

  - The speed CEILING (cornering and braking limited) is independent of deployment,
    because braking is grip limited rather than power limited. It is computed once by
    the Phase 2 simulator and used as a hard cap at every stage.
  - The lap is rotated to start at its slowest point. There the ceiling binds whatever
    the driver has done, so start and end speed are equal by construction and speed
    periodicity is satisfied without a search over boundary speeds.

The per-lap harvest cap is a cumulative constraint, which would need a third state
dimension. It is instead enforced by a Lagrange multiplier on harvested energy, bisected
until the cap is met — standard practice, and the achieved harvest is always reported so
the constraint can be checked rather than trusted.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from config.regulations import ERSK_MAX_POWER_W, ES_USABLE_WINDOW_J, OPERATIVE_HARVEST_CAP_J
from physics.simulate import braking_profile, cornering_profile
from physics.vehicle import VehicleModel

# Deployment fractions. Negative values are deliberate off-throttle harvesting - the
# "super clipping" of lifting at the end of a straight to refill the battery, accepting a
# small loss where the taper was throttling deployment away anyway.
DEFAULT_CONTROLS = (-1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0)

DEFAULT_N_SOC = 81
DEFAULT_N_SPEED = 96
MIN_SPEED_MPS = 5.0
INF = 1e18
# Each step of the harvest-cap search is a full DP solve, so both loops stay short.
BRACKET_STEPS = 7
BISECT_STEPS = 9


@dataclass
class DPResult:
    lap_time_s: float
    deploy_fraction: np.ndarray     # control actually applied, per grid point
    speed_mps: np.ndarray
    soc_j: np.ndarray
    deploy_power_w: np.ndarray
    harvest_power_w: np.ndarray
    clipping: np.ndarray
    energy_deployed_j: float
    energy_harvested_j: float
    soc_start_j: float
    soc_end_j: float
    harvest_multiplier: float
    feasible: bool
    notes: list[str]

    @property
    def soc_deficit_j(self) -> float:
        return self.soc_start_j - self.soc_end_j


def _is_periodic(result: DPResult, soc_start_j: float) -> bool:
    """Did the lap end with at least the energy it started with?"""
    return bool(result.soc_end_j >= soc_start_j)


def speed_ceiling(
    curvature: np.ndarray, gradient: np.ndarray, step_m: float, vehicle: VehicleModel
) -> np.ndarray:
    """Cornering- and braking-limited speed, independent of the deployment strategy."""
    v_cap = vehicle.terminal_speed_mps(1.0) * 1.02
    v_corner = cornering_profile(curvature, vehicle, v_cap)
    return braking_profile(v_corner, step_m, vehicle, gradient, curvature)


def _transition(
    v: np.ndarray,
    control: float,
    curvature_i: float,
    gradient_i: float,
    ceiling_next: float,
    step_m: float,
    vehicle: VehicleModel,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Advance every speed on the grid by one step under one control.

    Returns (next speed, elapsed time, electrical energy drawn, energy harvested).
    Energy drawn is the request before any state-of-charge limit is applied; the caller
    handles running out, because that is what clipping is.
    """
    v = np.maximum(v, MIN_SPEED_MPS)

    deploy = max(control, 0.0)
    harvest_ctl = max(-control, 0.0)

    p_elec = vehicle.electrical_power_w(v, deploy)          # after the regulatory taper
    p_prop = vehicle.driveline_efficiency * (vehicle.p_ice_w + p_elec)
    f_power = p_prop / v
    f_grip = vehicle.max_tractive_force(v, curvature_i)
    f_drive = np.minimum(f_power, f_grip)

    # Deliberate off-throttle harvesting: the MGU-K applies a retarding force, and the
    # ICE is not driving.
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

    energy_out = np.where(coasting, 0.0, p_elec) * dt

    # Harvest comes from two places: the deliberate control, and any braking the speed
    # ceiling forces. Only the part of the deceleration produced by the brakes is
    # recoverable — drag and rolling resistance dissipate to heat and air.
    retarding_n = vehicle.mass_kg * (v * v - v_next * v_next) / (2.0 * step_m)
    resistive_n = vehicle.resistive_force(v_avg, gradient_i)
    brake_n = np.maximum(retarding_n - resistive_n, 0.0)
    p_brake = brake_n * v_avg
    p_recover = np.minimum(p_brake * vehicle.regen_efficiency, ERSK_MAX_POWER_W)
    energy_in = np.where(coasting, np.minimum(p_harvest_req, ERSK_MAX_POWER_W), p_recover) * dt

    return v_next, dt, energy_out, energy_in


def _bilinear(J: np.ndarray, soc_f: np.ndarray, v_f: np.ndarray) -> np.ndarray:
    """Bilinear lookup into J on its uniform (soc, speed) index grid."""
    n_s, n_v = J.shape
    s0 = np.clip(np.floor(soc_f).astype(np.intp), 0, n_s - 1)
    v0 = np.clip(np.floor(v_f).astype(np.intp), 0, n_v - 1)
    s1 = np.minimum(s0 + 1, n_s - 1)
    v1 = np.minimum(v0 + 1, n_v - 1)
    ds = np.clip(soc_f - s0, 0.0, 1.0)
    dv = np.clip(v_f - v0, 0.0, 1.0)

    return (
        J[s0, v0] * (1 - ds) * (1 - dv)
        + J[s1, v0] * ds * (1 - dv)
        + J[s0, v1] * (1 - ds) * dv
        + J[s1, v1] * ds * dv
    )


def solve(
    curvature: np.ndarray,
    gradient: np.ndarray,
    step_m: float,
    vehicle: VehicleModel,
    soc_start_j: float | None = None,
    capacity_j: float = ES_USABLE_WINDOW_J,
    harvest_cap_j: float = OPERATIVE_HARVEST_CAP_J,
    controls: tuple[float, ...] = DEFAULT_CONTROLS,
    n_soc: int = DEFAULT_N_SOC,
    n_speed: int = DEFAULT_N_SPEED,
    enforce_harvest_cap: bool = True,
    harvest_price: float | None = None,
) -> DPResult:
    """Solve for the lap-time-optimal deployment strategy.

    Pass `harvest_price` to skip the multiplier search and reuse a value already found
    for this circuit. The multiplier is nearly independent of the starting charge, so
    generating training data over a range of starting states costs one search rather
    than one per state — the difference between minutes and hours.
    """
    soc_start_j = capacity_j if soc_start_j is None else soc_start_j

    ceiling = speed_ceiling(curvature, gradient, step_m, vehicle)
    # Rotate so stage 0 is the slowest point on the lap, where the ceiling binds
    # regardless of strategy and the speed boundary condition therefore closes itself.
    shift = int(np.argmin(ceiling))
    ceiling = np.roll(ceiling, -shift)
    curvature = np.roll(curvature, -shift)
    gradient = np.roll(gradient, -shift)

    multiplier = 0.0 if harvest_price is None else float(harvest_price)
    notes: list[str] = []
    result = _solve_with_multiplier(
        ceiling, curvature, gradient, step_m, vehicle, soc_start_j, capacity_j,
        controls, n_soc, n_speed, multiplier, harvest_cap_j,
    )

    solves = 1
    if harvest_price is not None:
        # Caller supplied a price, so the search is skipped. Whether it actually worked
        # is checked rather than assumed: a multiplier tuned at one starting charge does
        # not always keep the lap periodic at another.
        if not _is_periodic(result, soc_start_j):
            notes.append(
                f"Reused multiplier {multiplier:.3e} s/J left the lap "
                f"{(soc_start_j - result.soc_end_j) / 1e3:.1f} kJ short of periodic."
            )
    elif enforce_harvest_cap and not _is_periodic(result, soc_start_j):
        # The per-lap harvest cap is enforced as a HARD clamp during the rollout, so
        # harvested energy can never exceed it. That means over-harvesting does not show
        # up as an exceeded cap — it shows up as a lap that ends short, because the plan
        # counted on recovery the clamp refused to deliver.
        #
        # So the multiplier is searched on PERIODICITY, not on harvest. Pricing harvest
        # makes the DP plan for less of it; once the plan fits under the cap, plan and
        # rollout agree again and the terminal constraint holds. Feasibility is monotone
        # in the price, so the smallest feasible price is the least distorted solution.
        #
        # Iteration counts stay tight: each step is a full DP solve.
        def attempt(price: float):
            nonlocal solves
            solves += 1
            return _solve_with_multiplier(
                ceiling, curvature, gradient, step_m, vehicle, soc_start_j, capacity_j,
                controls, n_soc, n_speed, price, harvest_cap_j,
            )

        lo, hi = 0.0, 2e-6
        bracketed = None
        for _ in range(BRACKET_STEPS):
            trial = attempt(hi)
            if _is_periodic(trial, soc_start_j):
                bracketed = trial
                break
            lo, hi = hi, hi * 8.0

        if bracketed is None:
            notes.append(
                f"Could not make the lap periodic under the {harvest_cap_j / 1e6:.2f} MJ "
                f"harvest cap even at multiplier {hi:.2e} s/J; reporting the best found. "
                "Treat this circuit's result as not repeatable."
            )
            result = trial
        else:
            result = bracketed
            for _ in range(BISECT_STEPS):
                mid = 0.5 * (lo + hi)
                trial = attempt(mid)
                if _is_periodic(trial, soc_start_j):
                    hi, result = mid, trial
                else:
                    lo = mid
            multiplier = hi
            notes.append(
                f"Harvest cap {harvest_cap_j / 1e6:.2f} MJ binds; periodicity restored "
                f"with multiplier {multiplier:.3e} s/J after {solves} DP solves."
            )

    # Undo the rotation so outputs line up with the circuit's own distance grid.
    back = shift
    result.deploy_fraction = np.roll(result.deploy_fraction, back)
    result.speed_mps = np.roll(result.speed_mps, back)
    result.soc_j = np.roll(result.soc_j, back)
    result.deploy_power_w = np.roll(result.deploy_power_w, back)
    result.harvest_power_w = np.roll(result.harvest_power_w, back)
    result.clipping = np.roll(result.clipping, back)
    result.harvest_multiplier = multiplier
    result.notes = notes
    return result


def _solve_with_multiplier(
    ceiling: np.ndarray,
    curvature: np.ndarray,
    gradient: np.ndarray,
    step_m: float,
    vehicle: VehicleModel,
    soc_start_j: float,
    capacity_j: float,
    controls: tuple[float, ...],
    n_soc: int,
    n_speed: int,
    harvest_price: float,
    harvest_cap_j: float = OPERATIVE_HARVEST_CAP_J,
) -> DPResult:
    n = len(curvature)
    soc_grid = np.linspace(0.0, capacity_j, n_soc)
    v_grid = np.linspace(MIN_SPEED_MPS, float(ceiling.max()), n_speed)
    d_soc = float(soc_grid[1] - soc_grid[0])
    d_v = float(v_grid[1] - v_grid[0])
    if soc_start_j + d_soc > capacity_j:
        raise ValueError(
            "starting state of charge leaves no headroom for the periodicity margin; "
            "start below the top of the usable window"
        )

    # Precompute every transition once: they depend on stage and control, not on SoC.
    trans = []
    for i in range(n):
        per_control = []
        for u in controls:
            per_control.append(
                _transition(v_grid, u, curvature[i], gradient[i],
                            ceiling[(i + 1) % n], step_m, vehicle)
            )
        trans.append(per_control)

    # Terminal cost: the lap must end with at least the energy it began with. Without
    # this the optimiser empties the battery and posts a lap that can never be repeated.
    #
    # The target is one grid cell ABOVE the starting charge. The backward pass works on
    # the discretised state with interpolation while the rollout recomputes the physics
    # exactly, and the two disagree by a fraction of a cell; asking only for
    # soc_end >= soc_start left Monza and Miami short by 16-24 kJ. Aiming one cell high
    # absorbs that, at negligible cost in lap time.
    target_j = soc_start_j + d_soc
    J = np.where(soc_grid[:, None] >= target_j - 1e-6, 0.0, INF)
    J = np.broadcast_to(J, (n_soc, n_speed)).copy()

    policy = np.zeros((n, n_soc, n_speed), dtype=np.int8)

    for i in range(n - 1, -1, -1):
        best = np.full((n_soc, n_speed), INF)
        best_u = np.zeros((n_soc, n_speed), dtype=np.int8)

        for ui in range(len(controls)):
            v_next, dt, e_out, e_in = trans[i][ui]

            # Energy actually available is capped by the current state of charge.
            draw = np.minimum(soc_grid[:, None], e_out[None, :])
            soc_next = np.clip(soc_grid[:, None] - draw + e_in[None, :], 0.0, capacity_j)

            # Running out mid-step means the car did not get the power it asked for, so
            # the step takes longer than this transition assumed. Penalise the shortfall
            # rather than letting the optimiser treat an empty battery as free.
            shortfall = e_out[None, :] - draw
            penalty = shortfall / np.maximum(
                vehicle.driveline_efficiency * (vehicle.p_ice_w + 1.0), 1.0
            )

            cost = (
                dt[None, :]
                + penalty
                + harvest_price * e_in[None, :]
                + _bilinear(J, soc_next / d_soc, (v_next[None, :] - v_grid[0]) / d_v)
            )

            improved = cost < best
            best = np.where(improved, cost, best)
            best_u = np.where(improved, np.int8(ui), best_u)

        J = best
        policy[i] = best_u

    return _rollout(
        policy, controls, trans, v_grid, soc_grid, ceiling, curvature, gradient,
        step_m, vehicle, soc_start_j, capacity_j, J, harvest_cap_j,
    )


def rollout(
    curvature: np.ndarray,
    gradient: np.ndarray,
    step_m: float,
    vehicle: VehicleModel,
    choose,
    ceiling: np.ndarray | None = None,
    soc_start_j: float | None = None,
    capacity_j: float = ES_USABLE_WINDOW_J,
    harvest_cap_j: float = OPERATIVE_HARVEST_CAP_J,
    rotate: bool = False,
) -> DPResult:
    """Run any deployment policy forward through the exact physics.

    `choose(index, speed_mps, soc_j, ceiling_mps) -> control` in [-1, 1]. Both the DP's
    own table and a learned model are evaluated through this same function, so a
    comparison between them cannot be contaminated by differing simulation details.

    Set rotate=True to start at the lap's slowest point, matching how the DP is solved.

    `index` is always in the CIRCUIT'S OWN grid space, not the rotated stage order, so
    callers can index geometry and precomputed features directly. Getting this wrong is
    silent and severe: feeding a policy features from the wrong part of the track scored
    -446% of the optimiser's gain when it was first tried.
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
    deployed = harvested = 0.0

    frac = np.zeros(n)
    speeds = np.zeros(n)
    socs = np.zeros(n)
    p_dep = np.zeros(n)
    p_har = np.zeros(n)
    clip = np.zeros(n, dtype=bool)

    for i in range(n):
        original_i = (i + shift) % n
        u = float(np.clip(choose(original_i, v, soc, float(ceiling[i])), -1.0, 1.0))

        v_next, dt, e_out, e_in = _transition(
            np.array([v]), u, curvature[i], gradient[i], ceiling[(i + 1) % n],
            step_m, vehicle,
        )
        v_next = float(v_next[0]); dt = float(dt[0])
        e_out = float(e_out[0]); e_in = float(e_in[0])

        draw = min(soc, e_out)
        if e_out - draw > 1.0:
            clip[i] = True
            # Recompute the step with only the power that was actually available. Without
            # this the car would be credited with acceleration it could not produce.
            available_frac = (draw / e_out) * max(u, 0.0) if e_out > 0 else 0.0
            v_next2, dt2, e_out2, e_in2 = _transition(
                np.array([v]), available_frac, curvature[i], gradient[i],
                ceiling[(i + 1) % n], step_m, vehicle,
            )
            v_next, dt = float(v_next2[0]), float(dt2[0])
            e_out, e_in = float(e_out2[0]), float(e_in2[0])
            draw = min(soc, e_out)

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
        v = v_next

    result = DPResult(
        lap_time_s=total_t,
        deploy_fraction=frac,
        speed_mps=speeds,
        soc_j=socs,
        deploy_power_w=p_dep,
        harvest_power_w=p_har,
        clipping=clip,
        energy_deployed_j=deployed,
        energy_harvested_j=harvested,
        soc_start_j=soc_start_j,
        soc_end_j=soc,
        harvest_multiplier=0.0,
        feasible=True,
        notes=[],
    )
    if shift:
        for name in ("deploy_fraction", "speed_mps", "soc_j", "deploy_power_w",
                     "harvest_power_w", "clipping"):
            setattr(result, name, np.roll(getattr(result, name), shift))
    return result


def _rollout(
    policy, controls, trans, v_grid, soc_grid, ceiling, curvature, gradient,
    step_m, vehicle, soc_start_j, capacity_j, J, harvest_cap_j,
) -> DPResult:
    """Replay the DP table forward, recomputing physics exactly at each state."""
    d_soc = float(soc_grid[1] - soc_grid[0])
    d_v = float(v_grid[1] - v_grid[0])
    n_s, n_v = len(soc_grid), len(v_grid)

    def choose(i: int, v: float, soc: float, _ceiling: float) -> float:
        si = int(round(float(np.clip(soc / d_soc, 0, n_s - 1))))
        vi = int(round(float(np.clip((v - v_grid[0]) / d_v, 0, n_v - 1))))
        return controls[int(policy[i][si, vi])]

    res = rollout(
        curvature, gradient, step_m, vehicle, choose, ceiling=ceiling,
        soc_start_j=soc_start_j, capacity_j=capacity_j, harvest_cap_j=harvest_cap_j,
    )
    res.feasible = bool(np.isfinite(J).any())
    return res
