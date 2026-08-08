"""Physics tests against hand-computed cases."""

from __future__ import annotations

import numpy as np
import pytest

from config.regulations import ERSK_MAX_POWER_W, max_deploy_power_w
from config.vehicle import GRAVITY_M_S2, air_density
from energy.battery import BatteryState
from physics.simulate import simulate_lap
from physics.vehicle import VehicleModel


def make_vehicle(**overrides) -> VehicleModel:
    base = dict(
        mass_kg=800.0,
        cd_a=1.2,
        crr=0.012,
        air_density=1.2,
        p_ice_w=400_000.0,
        driveline_efficiency=1.0,
        cl_a=0.0,          # no downforce unless a test asks for it
        mu_lat=1.8,
        mu_brake=1.5,
        regen_efficiency=0.9,
    )
    base.update(overrides)
    return VehicleModel(**base)


# -- forces --------------------------------------------------------------------------


def test_drag_force_matches_hand_calculation():
    v = make_vehicle()
    # 0.5 * 1.2 * 1.2 * 50^2 = 1800 N
    assert v.drag_force(50.0) == pytest.approx(1800.0)


def test_rolling_force_matches_hand_calculation():
    v = make_vehicle()
    assert v.rolling_force() == pytest.approx(0.012 * 800.0 * GRAVITY_M_S2)


def test_grade_force_is_zero_on_the_flat_and_signed_uphill():
    v = make_vehicle()
    assert v.grade_force(0.0) == pytest.approx(0.0)
    # 10% gradient -> m g sin(atan(0.1))
    assert v.grade_force(0.1) == pytest.approx(800.0 * GRAVITY_M_S2 * 0.0995, rel=1e-3)
    assert v.grade_force(-0.1) == pytest.approx(-v.grade_force(0.1))


def test_tractive_force_is_power_over_speed():
    v = make_vehicle(p_ice_w=300_000.0, driveline_efficiency=1.0)
    # No electrical deployment: F = P/v = 300kW / 50 = 6000 N
    assert v.tractive_force(50.0, deploy_fraction=0.0) == pytest.approx(6000.0)


# -- deployment taper ----------------------------------------------------------------


def test_taper_is_full_power_below_290_and_zero_above_345():
    assert max_deploy_power_w(100.0) == ERSK_MAX_POWER_W
    assert max_deploy_power_w(290.0) == ERSK_MAX_POWER_W
    assert max_deploy_power_w(345.0) == 0.0
    assert max_deploy_power_w(400.0) == 0.0


def test_taper_matches_the_regulation_formula_between_thresholds():
    # Art. 5.4.8(i): P(kW) = 1800 - 5*v below 340 kph.
    for v_kph in (300.0, 320.0, 335.0):
        assert max_deploy_power_w(v_kph) == pytest.approx((1800.0 - 5.0 * v_kph) * 1000.0)
    # and 6900 - 20*v at or above 340 kph
    for v_kph in (340.0, 342.0):
        assert max_deploy_power_w(v_kph) == pytest.approx((6900.0 - 20.0 * v_kph) * 1000.0)


def test_override_mode_holds_full_power_higher_than_normal_mode():
    assert max_deploy_power_w(330.0, "override") == ERSK_MAX_POWER_W
    assert max_deploy_power_w(330.0, "normal") < ERSK_MAX_POWER_W
    assert max_deploy_power_w(355.0, "override") == 0.0


def test_deploy_fraction_scales_the_tapered_ceiling_not_the_raw_cap():
    v = make_vehicle()
    # At 320 kph (88.9 m/s) the ceiling is 200 kW, so half deployment is 100 kW.
    got = v.electrical_power_w(320.0 / 3.6, 0.5)
    assert float(got) == pytest.approx(100_000.0, rel=1e-6)


# -- grip ----------------------------------------------------------------------------


def test_corner_speed_without_downforce_is_sqrt_mu_g_over_kappa():
    v = make_vehicle(cl_a=0.0, mu_lat=1.5)
    kappa = 1.0 / 100.0  # 100 m radius
    expected = np.sqrt(1.5 * GRAVITY_M_S2 / kappa)
    assert float(v.corner_speed_limit(kappa)) == pytest.approx(expected)


def test_downforce_raises_the_cornering_limit():
    plain = make_vehicle(cl_a=0.0)
    winged = make_vehicle(cl_a=4.0)
    kappa = 1.0 / 200.0
    assert winged.corner_speed_limit(kappa) > plain.corner_speed_limit(kappa)


def test_open_corner_is_effectively_flat_out_but_still_bounded():
    """Past the critical radius the downforce branch stops binding.

    The limit must stay FINITE even so. Tyres saturate, and without the ceiling the
    model returned infinity for every radius above ~138 m, which made the simulated lap
    13 s too fast and let Monaco reach 329 km/h.
    """
    v = make_vehicle(cl_a=5.0, mu_lat=1.5, a_lat_ceiling=50.0)
    critical = v.mu_lat * v.air_density * v.cl_a / (2.0 * v.mass_kg)
    limit = float(v.corner_speed_limit(critical * 0.5))

    assert np.isfinite(limit)
    # Falls back to the saturation branch, v = sqrt(a_ceiling / kappa).
    assert limit == pytest.approx(np.sqrt(50.0 / (critical * 0.5)))
    # Still far above any speed the car can actually reach, so the corner is flat out.
    assert limit > v.terminal_speed_mps(1.0)


def test_lateral_limit_saturates_at_the_ceiling():
    v = make_vehicle(cl_a=5.0, mu_lat=1.5, a_lat_ceiling=45.0)
    assert float(v.lateral_limit(5.0)) < 45.0       # low speed: downforce-limited
    assert float(v.lateral_limit(120.0)) == pytest.approx(45.0)  # high speed: saturated


def test_friction_ellipse_removes_longitudinal_grip_while_cornering():
    """A tyre at its lateral limit has nothing left for driving or braking."""
    v = make_vehicle(cl_a=3.0, mu_lat=1.6, a_lat_ceiling=50.0)
    speed = 60.0

    straight = float(v.grip_available_fraction(speed, 0.0))
    assert straight == pytest.approx(1.0)

    # Curvature that exactly saturates the lateral limit leaves zero longitudinal grip.
    at_limit = float(v.lateral_limit(speed)) / speed**2
    assert float(v.grip_available_fraction(speed, at_limit)) == pytest.approx(0.0)
    assert float(v.max_tractive_force(speed, at_limit)) == pytest.approx(0.0)

    # And a mid-corner load leaves some, but less than on a straight.
    partial = float(v.grip_available_fraction(speed, at_limit * 0.6))
    assert 0.0 < partial < 1.0
    assert v.max_tractive_force(speed, at_limit * 0.6) < v.max_tractive_force(speed, 0.0)


# -- air density ---------------------------------------------------------------------


def test_air_density_matches_standard_atmosphere():
    assert air_density(1013.25, 15.0, 0.0) == pytest.approx(1.225, abs=0.002)


def test_altitude_reduces_air_density_substantially():
    """Mexico City sits at ~2,240 m; drag there is far lower than at sea level."""
    assert air_density(780.0, 20.0, 40.0) < 0.80 * air_density(1013.25, 20.0, 40.0)


# -- battery -------------------------------------------------------------------------


def test_battery_cannot_deliver_more_than_it_holds():
    b = BatteryState(soc_j=1_000.0, capacity_j=4_000_000.0)
    assert b.draw(5_000.0) == pytest.approx(1_000.0)
    assert b.soc_j == pytest.approx(0.0)


def test_battery_respects_capacity_ceiling_when_charging():
    b = BatteryState(soc_j=3_900_000.0, capacity_j=4_000_000.0)
    assert b.charge(500_000.0) == pytest.approx(100_000.0)
    assert b.soc_j == pytest.approx(4_000_000.0)


def test_battery_respects_the_per_lap_harvest_cap():
    b = BatteryState(soc_j=0.0, capacity_j=4_000_000.0, harvest_cap_j=1_000_000.0)
    b.charge(800_000.0)
    assert b.charge(800_000.0) == pytest.approx(200_000.0)
    assert b.harvested_j == pytest.approx(1_000_000.0)
    assert b.harvest_headroom_j == pytest.approx(0.0)


def test_energy_accounting_balances_over_draw_and_charge():
    b = BatteryState(soc_j=2_000_000.0, capacity_j=4_000_000.0)
    b.draw(500_000.0)
    b.charge(300_000.0)
    assert b.soc_j == pytest.approx(2_000_000.0 - 500_000.0 + 300_000.0)
    assert b.deployed_j == pytest.approx(500_000.0)
    assert b.harvested_j == pytest.approx(300_000.0)


# -- lap simulation ------------------------------------------------------------------


def test_constant_radius_circuit_settles_at_the_cornering_limit():
    """A circular track at constant radius: speed should be flat at the grip limit."""
    radius, step = 150.0, 5.0
    n = int(2 * np.pi * radius / step)
    curvature = np.full(n, 1.0 / radius)
    gradient = np.zeros(n)

    vehicle = make_vehicle(cl_a=0.0, mu_lat=1.4)
    battery = BatteryState(soc_j=4_000_000.0)
    result = simulate_lap(curvature, gradient, step, vehicle,
                          np.zeros(n), battery)

    expected_v = float(vehicle.corner_speed_limit(1.0 / radius))
    assert np.allclose(result.speed_mps, expected_v, rtol=0.02)
    assert result.lap_time_s == pytest.approx(n * step / expected_v, rel=0.02)


def test_deployment_drains_the_store_and_then_clips():
    """With a nearly empty store, requested deployment cannot all be delivered."""
    n, step = 400, 5.0
    curvature = np.full(n, 1e-6)  # effectively straight
    gradient = np.zeros(n)
    vehicle = make_vehicle()

    battery = BatteryState(soc_j=50_000.0, capacity_j=4_000_000.0)
    result = simulate_lap(curvature, gradient, step, vehicle, np.ones(n), battery)

    assert result.energy_deployed_j <= 50_000.0 + 1e-6
    assert result.clipping.any(), "an empty store must produce clipping"
    assert result.soc_end_j >= 0.0


def test_simulation_never_violates_soc_bounds():
    n, step = 600, 5.0
    rng = np.random.default_rng(0)
    curvature = np.abs(rng.normal(0, 0.004, n))
    gradient = np.zeros(n)
    vehicle = make_vehicle()
    battery = BatteryState(soc_j=2_000_000.0, capacity_j=4_000_000.0)

    result = simulate_lap(curvature, gradient, step, vehicle,
                          np.full(n, 0.5), battery)

    assert result.soc_j.min() >= -1e-6
    assert result.soc_j.max() <= 4_000_000.0 + 1e-6
    assert result.energy_harvested_j <= battery.harvest_cap_j + 1e-6
