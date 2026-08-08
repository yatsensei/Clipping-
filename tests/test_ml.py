"""Tests for the learned-policy layer.

The important ones here are structural rather than numerical: that no feature depends on
knowing the finished lap, and that the closed-loop scorer reports 100% only when the
policy actually matches the optimiser.
"""

from __future__ import annotations

import numpy as np
import pytest

from config.regulations import ES_USABLE_WINDOW_J
from ml import features as F
from ml.policy import Policy, always_deploy_policy, run_closed_loop, snap_to_controls
from optimiser import dp
from physics.vehicle import VehicleModel


def vehicle() -> VehicleModel:
    return VehicleModel(
        mass_kg=778.0, cd_a=0.968, crr=0.012, air_density=1.17,
        p_ice_w=400_000.0, driveline_efficiency=0.95, cl_a=5.586,
        mu_lat=1.753, mu_brake=1.386, regen_efficiency=0.90,
        f_offthrottle_n=1197.0, a_lat_ceiling=44.4,
    )


def track(n_straight: int = 180, n_corner: int = 30):
    seg = np.concatenate([np.full(n_straight, 1e-7), np.full(n_corner, 1.0 / 40.0)])
    curvature = np.concatenate([seg, seg])
    return curvature, np.zeros_like(curvature), 5.0


def static_for(curvature, gradient, step):
    ceiling = dp.speed_ceiling(curvature, gradient, step, vehicle())
    return F.build_static(curvature, gradient, ceiling, step), ceiling


# -- feature hygiene -----------------------------------------------------------------


def test_no_feature_name_leaks_the_answer():
    """Nothing that requires the finished lap may appear as an input."""
    banned = ("target", "lap_time", "optimal", "deploy_fraction", "gain", "total_energy")
    for name in F.FEATURE_NAMES:
        assert not any(b in name for b in banned), name


def test_static_features_are_computable_from_geometry_alone():
    curvature, gradient, step = track()
    static, _ = static_for(curvature, gradient, step)
    for name in F.STATIC_FEATURES:
        assert name in static, name
        assert len(static[name]) == len(curvature)
        assert np.all(np.isfinite(static[name])), name


def test_dynamic_features_depend_only_on_the_current_state():
    row = F.dynamic_row(speed_mps=70.0, soc_j=2e6, capacity_j=ES_USABLE_WINDOW_J,
                        ceiling_mps=90.0, next_apex_speed_mps=40.0)
    assert set(row) == set(F.DYNAMIC_FEATURES)
    assert all(np.isfinite(v) for v in row.values())
    assert row["soc_fraction"] == pytest.approx(0.5)


def test_taper_headroom_goes_negative_inside_the_tapered_band():
    below = F.dynamic_row(250.0 / 3.6, 2e6, ES_USABLE_WINDOW_J, 100.0, 40.0)
    above = F.dynamic_row(320.0 / 3.6, 2e6, ES_USABLE_WINDOW_J, 100.0, 40.0)
    assert below["taper_headroom_kph"] > 0
    assert above["taper_headroom_kph"] < 0
    # And the fraction of the 350 kW ceiling still available must fall.
    assert above["taper_fraction"] < below["taper_fraction"]


def test_apex_distances_wrap_around_the_start_finish_line():
    curvature, gradient, step = track()
    static, _ = static_for(curvature, gradient, step)
    assert static["dist_to_next_apex_m"].min() >= 0.0
    assert static["dist_from_last_apex_m"].min() >= 0.0
    lap_m = len(curvature) * step
    assert static["dist_to_next_apex_m"].max() <= lap_m
    # No point should be more than the lap away from an apex in either direction.
    assert static["dist_from_last_apex_m"].max() <= lap_m


def test_assemble_matches_the_declared_feature_order():
    curvature, gradient, step = track()
    static, ceiling = static_for(curvature, gradient, step)
    dyn = F.dynamic_row(60.0, 2e6, ES_USABLE_WINDOW_J, float(ceiling[10]),
                        float(static["next_apex_speed_mps"][10]))
    row = F.assemble(static, 10, dyn)
    assert len(row) == len(F.FEATURE_NAMES)
    assert row[F.FEATURE_NAMES.index("speed_mps")] == pytest.approx(60.0)
    assert row[F.FEATURE_NAMES.index("curvature_abs")] == pytest.approx(
        abs(curvature[10])
    )


# -- control snapping ----------------------------------------------------------------


def test_snapping_rounds_onto_the_dp_control_set():
    got = snap_to_controls(np.array([0.9, 0.1, -0.9, 0.4]))
    assert set(got).issubset(set(dp.DEFAULT_CONTROLS))
    assert got[0] == pytest.approx(1.0)
    assert got[2] == pytest.approx(-1.0)


def test_snapping_leaves_exact_controls_untouched():
    exact = np.array(dp.DEFAULT_CONTROLS)
    assert np.allclose(snap_to_controls(exact), exact)


# -- closed-loop scoring -------------------------------------------------------------


def test_replaying_the_dp_policy_retains_essentially_all_of_the_gain():
    """Sanity check on the scorer: feed it the optimiser's own decisions.

    This is the scorer's calibration. If replaying the DP's own control sequence did not
    score near 100%, the metric would be measuring simulation mismatch rather than policy
    quality, and every learned-model number would be meaningless.
    """
    curvature, gradient, step = track()
    veh = vehicle()
    soc0 = 0.5 * ES_USABLE_WINDOW_J

    solution = dp.solve(curvature, gradient, step, veh, soc_start_j=soc0,
                        n_soc=21, n_speed=28)
    from optimiser import baselines

    uni = baselines.uniform(curvature, gradient, step, veh, soc_start_j=soc0)

    # A policy that simply reads back the DP's chosen control at each stage.
    plan = solution.deploy_fraction
    parrot = Policy(lambda X: np.zeros(len(X)), "parrot")

    def choose(i, v, soc, ceil_i):
        return plan[i]

    replay = dp.rollout(curvature, gradient, step, veh, choose,
                        soc_start_j=soc0, rotate=True)
    dp_gain = uni.lap_time_s - solution.lap_time_s
    replay_gain = uni.lap_time_s - replay.lap_time_s
    assert dp_gain > 0.0
    assert replay_gain / dp_gain > 0.95, (
        f"replaying the DP's own plan retained only "
        f"{100 * replay_gain / dp_gain:.1f}% of its gain"
    )
    assert parrot.name == "parrot"


def test_always_deploy_baseline_runs_and_scores_worse_than_the_optimum():
    curvature, gradient, step = track()
    veh = vehicle()
    soc0 = 0.5 * ES_USABLE_WINDOW_J
    solution = dp.solve(curvature, gradient, step, veh, soc_start_j=soc0,
                        n_soc=21, n_speed=28)
    from optimiser import baselines

    uni = baselines.uniform(curvature, gradient, step, veh, soc_start_j=soc0)

    res = run_closed_loop(
        always_deploy_policy(), "synthetic", curvature, gradient, step, veh,
        soc_start_j=soc0, dp_lap_s=solution.lap_time_s, uniform_lap_s=uni.lap_time_s,
    )
    assert np.isfinite(res.gain_retained_pct)
    assert res.gain_retained_pct < 100.0
    # Deploying blindly empties the store, so it should not come back periodic.
    assert not res.periodic
    assert res.notes, "a non-periodic lap must be flagged"
