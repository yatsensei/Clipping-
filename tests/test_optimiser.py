"""Optimiser constraint and behaviour tests.

The physically interesting one is
test_deployment_is_biased_towards_low_speed_where_it_is_not_tapered_away: the optimiser
is never told about the speed taper as a strategy, only as a power ceiling, so preferring
the slow end of a straight has to be something it works out.
"""

from __future__ import annotations

import numpy as np
import pytest

from config.regulations import ES_USABLE_WINDOW_J, max_deploy_power_w
from optimiser import baselines, dp
from physics.vehicle import VehicleModel

# Small grids: these tests check constraints and qualitative behaviour, not precision.
GRID = dict(n_soc=21, n_speed=28)


def vehicle() -> VehicleModel:
    return VehicleModel(
        mass_kg=778.0,
        cd_a=0.968,
        crr=0.012,
        air_density=1.17,
        p_ice_w=400_000.0,
        driveline_efficiency=0.95,
        cl_a=5.586,
        mu_lat=1.753,
        mu_brake=1.386,
        regen_efficiency=0.90,
        f_offthrottle_n=1197.0,
        a_lat_ceiling=44.4,
    )


def straight_and_hairpin(n_straight: int = 200, n_corner: int = 30) -> tuple:
    """A long straight joined to a tight corner, repeated twice around the lap."""
    seg_k = np.concatenate([np.full(n_straight, 1e-7), np.full(n_corner, 1.0 / 40.0)])
    curvature = np.concatenate([seg_k, seg_k])
    return curvature, np.zeros_like(curvature), 5.0


# -- constraints ---------------------------------------------------------------------


def test_soc_never_leaves_its_bounds():
    curvature, gradient, step = straight_and_hairpin()
    res = dp.solve(curvature, gradient, step, vehicle(),
                   soc_start_j=0.5 * ES_USABLE_WINDOW_J, **GRID)
    assert res.soc_j.min() >= -1.0
    assert res.soc_j.max() <= ES_USABLE_WINDOW_J + 1.0


def test_harvest_never_exceeds_the_per_lap_cap():
    curvature, gradient, step = straight_and_hairpin()
    cap = 1.5e6
    res = dp.solve(curvature, gradient, step, vehicle(),
                   soc_start_j=0.5 * ES_USABLE_WINDOW_J, harvest_cap_j=cap, **GRID)
    assert res.energy_harvested_j <= cap * 1.02, (
        f"harvested {res.energy_harvested_j / 1e6:.3f} MJ against a "
        f"{cap / 1e6:.3f} MJ cap"
    )


def test_solution_is_periodic_in_state_of_charge():
    """Without this the optimiser empties the battery and posts an unrepeatable lap."""
    curvature, gradient, step = straight_and_hairpin()
    soc0 = 0.5 * ES_USABLE_WINDOW_J
    res = dp.solve(curvature, gradient, step, vehicle(), soc_start_j=soc0, **GRID)
    assert res.soc_end_j >= soc0 - 5_000.0
    assert res.soc_deficit_j <= 5_000.0


def test_deployment_never_exceeds_the_regulatory_taper():
    curvature, gradient, step = straight_and_hairpin()
    res = dp.solve(curvature, gradient, step, vehicle(),
                   soc_start_j=0.5 * ES_USABLE_WINDOW_J, **GRID)
    ceiling = np.array([max_deploy_power_w(v * 3.6) for v in res.speed_mps])
    assert np.all(res.deploy_power_w <= ceiling + 1_000.0)


def test_lap_time_is_finite_and_sane():
    curvature, gradient, step = straight_and_hairpin()
    res = dp.solve(curvature, gradient, step, vehicle(),
                   soc_start_j=0.5 * ES_USABLE_WINDOW_J, **GRID)
    assert res.feasible
    assert np.isfinite(res.lap_time_s)
    assert 5.0 < res.lap_time_s < 600.0


# -- one physics ---------------------------------------------------------------------


def test_optimiser_and_baselines_share_one_physics():
    """Replaying the DP's own controls through the baselines' path reproduces its lap.

    There used to be two simulators. The optimiser was timed on one and greedy and
    uniform on the other, so the reported gain included whatever they disagreed on.
    Now a fixed policy through simulate_lap and the DP's rollout must agree exactly.
    """
    from energy.battery import BatteryState
    from physics.simulate import simulate_lap

    curvature, gradient, step = straight_and_hairpin()
    soc0 = 0.5 * ES_USABLE_WINDOW_J
    res = dp.solve(curvature, gradient, step, vehicle(), soc_start_j=soc0, **GRID)

    replay = simulate_lap(
        curvature, gradient, step, vehicle(), res.deploy_fraction,
        BatteryState(soc_j=soc0),
    )
    assert replay.lap_time_s == pytest.approx(res.lap_time_s, abs=1e-9)
    assert np.allclose(replay.speed_mps, res.speed_mps)
    assert np.allclose(replay.soc_j, res.soc_j)
    assert replay.energy_harvested_j == pytest.approx(res.energy_harvested_j)


def test_greedy_baseline_clips_through_the_same_rollout():
    """Greedy's clipping must cost time, as it does in the optimiser's rollout."""
    from physics.simulate import rollout

    curvature, gradient, step = straight_and_hairpin()
    greedy = baselines.greedy(curvature, gradient, step, vehicle(),
                              soc_start_j=0.5 * ES_USABLE_WINDOW_J)
    direct = rollout(curvature, gradient, step, vehicle(),
                     lambda *_: 1.0, soc_start_j=0.5 * ES_USABLE_WINDOW_J)
    assert greedy.lap_time_s == pytest.approx(direct.lap_time_s, abs=1e-9)
    assert greedy.clipping.any()


# -- behaviour -----------------------------------------------------------------------


def test_optimiser_is_no_slower_than_the_uniform_baseline():
    curvature, gradient, step = straight_and_hairpin()
    soc0 = 0.5 * ES_USABLE_WINDOW_J
    opt = dp.solve(curvature, gradient, step, vehicle(), soc_start_j=soc0, **GRID)
    uni = baselines.uniform(curvature, gradient, step, vehicle(), soc_start_j=soc0)
    # Both are periodic, so this is like-for-like. Small tolerance for the coarse grid.
    assert opt.lap_time_s <= uni.lap_time_s + 0.25


def test_deployment_is_biased_towards_low_speed_where_it_is_not_tapered_away():
    """Energy spent near the taper threshold buys less speed, so it should go earlier.

    The optimiser only ever sees the taper as a ceiling on available power. That it ends
    up preferring the slower part of a straight is a consequence it has to derive.
    """
    curvature, gradient, step = straight_and_hairpin(n_straight=260, n_corner=30)
    res = dp.solve(curvature, gradient, step, vehicle(),
                   soc_start_j=0.5 * ES_USABLE_WINDOW_J, **GRID)

    deploying = res.deploy_power_w > 1_000.0
    if deploying.sum() < 10:
        pytest.skip("no meaningful deployment to analyse on this synthetic lap")

    speeds = res.speed_mps[deploying]
    taper_kph = 290.0
    # The mean speed at which energy is deployed should sit below the taper threshold.
    mean_deploy_kph = float(np.average(res.speed_mps[deploying] * 3.6,
                                      weights=res.deploy_power_w[deploying]))
    assert mean_deploy_kph < taper_kph, (
        f"energy is being spent at {mean_deploy_kph:.0f} km/h on average, above the "
        f"{taper_kph:.0f} km/h taper threshold where it is throttled away"
    )
    assert speeds.min() < np.median(res.speed_mps)


def test_greedy_empties_the_store_and_clips():
    curvature, gradient, step = straight_and_hairpin()
    res = baselines.greedy(curvature, gradient, step, vehicle(),
                           soc_start_j=ES_USABLE_WINDOW_J)
    assert res.soc_end_j < res.soc_start_j
    assert not res.periodic
    assert res.clipping_fraction > 0.0


def test_uniform_baseline_is_periodic_by_construction():
    curvature, gradient, step = straight_and_hairpin()
    soc0 = 0.5 * ES_USABLE_WINDOW_J
    res = baselines.uniform(curvature, gradient, step, vehicle(), soc_start_j=soc0)
    assert res.periodic, "the uniform baseline must be repeatable to be a fair baseline"
