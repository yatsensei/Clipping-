"""Vehicle parameter set for the longitudinal model.

Nothing in here is a tuned number. Parameters are in one of three categories:

    FIXED   a regulatory or physical constant, sourced in config/regulations.py
    DERIVED computed per session from real data (e.g. air density from weather)
    FITTED  estimated by regression against telemetry — declared here as None until
            the fit has been run, so that a missing fit fails loudly instead of
            silently falling back to an invented default

This module is the proposal referenced in the Phase 0 report. FITTED values stay None
until scripts/fit_vehicle.py has run and written its output to data/processed/.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config.regulations import (
    MIN_CAR_MASS_KG,
    QUALIFYING_FUEL_MASS_KG,
)

# --------------------------------------------------------------------------------------
# FIXED
# --------------------------------------------------------------------------------------

GRAVITY_M_S2: float = 9.80665

# Mass on a qualifying flying lap: regulatory minimum (includes driver, excludes fuel)
# plus a small fuel load. The fuel figure is an assumption — see regulations.py.
LAP_MASS_KG: float = MIN_CAR_MASS_KG + QUALIFYING_FUEL_MASS_KG

# --------------------------------------------------------------------------------------
# DERIVED — computed per circuit/session, never hardcoded
# --------------------------------------------------------------------------------------

# Air density is NOT a constant across the calendar. Mexico City sits at roughly 2,240 m,
# where density is ~20% below sea level; drag and therefore the whole deployment tradeoff
# shift materially. FastF1 exposes AirTemp, Pressure and Humidity per session, so density
# is computed from the actual session weather rather than assumed at 1.225 kg/m^3.
SEA_LEVEL_AIR_DENSITY_KG_M3: float = 1.225  # reference only; not used in the model


def air_density(pressure_mbar: float, air_temp_c: float, humidity_pct: float = 0.0) -> float:
    """Air density from session weather, via the ideal gas law with a humidity correction.

    Uses partial pressures of dry air and water vapour. Humidity's effect is small (<1%)
    but free to include given FastF1 reports it.
    """
    p = pressure_mbar * 100.0  # Pa
    t = air_temp_c + 273.15  # K
    # Saturation vapour pressure, Tetens formula (Pa).
    p_sat = 610.78 * 10.0 ** (7.5 * air_temp_c / (air_temp_c + 237.3))
    p_v = (humidity_pct / 100.0) * p_sat
    p_d = p - p_v
    return p_d / (287.058 * t) + p_v / (461.495 * t)


# --------------------------------------------------------------------------------------
# FITTED — None until scripts/fit_vehicle.py has run
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class FittedVehicleParams:
    """Parameters estimated from telemetry. See the Phase 0 report for the fit strategy.

    Fit order matters. cd_a_* and crr are identified on coasting phases only (throttle
    off, brake off), where propulsive power is zero and the deployment state — which is
    unobservable in public telemetry — therefore does not enter the equation. Only once
    drag is known can the full-throttle phases be used to infer total propulsive power.
    Fitting drag on full-throttle data instead would be circular.
    """

    # Drag area Cd*A [m^2], high-downforce configuration.
    cd_a_high: float | None = None
    # Drag area [m^2] in the 2026 low-drag straight-line ("X-mode") active aero state.
    cd_a_low: float | None = None
    # Rolling resistance coefficient [-]. NOT identifiable from this telemetry: rolling
    # resistance, engine braking and off-throttle MGU-K regen are all constant forces, so
    # nothing in their speed dependence separates them and only their sum is measurable.
    # Assigned a literature value and reported as an assumption, never as a fit result.
    crr: float | None = None
    # The measured remainder of that constant force [N] — engine braking plus regen —
    # applied only when off throttle, so it is not double counted under power.
    f_offthrottle_n: float | None = None
    # Effective ICE crankshaft power [W], possibly speed/rpm dependent.
    p_ice_max: float | None = None
    # Driveline efficiency from crankshaft/ES to road [-].
    driveline_efficiency: float | None = None
    # Downforce area Cl*A [m^2]. Grip rises with speed, so corner and braking limits are
    # mu * (g + rho*Cl*A*v^2 / 2m) rather than constants.
    cl_a: float | None = None
    mu_lat: float | None = None
    mu_brake: float | None = None
    # Fraction of braking energy recoverable at the CU-K bus [-].
    regen_efficiency: float | None = None

    # Fit diagnostics, populated alongside the values.
    fit_rmse_kph: float | None = None
    fit_r2: float | None = None
    fit_n_samples: int | None = None
    fit_sessions: tuple[str, ...] = field(default_factory=tuple)

    def require_fitted(self) -> None:
        """Raise if any parameter needed by the physics model is still unfitted."""
        missing = [
            name
            for name in (
                "cd_a_high",
                "crr",
                "p_ice_max",
                "driveline_efficiency",
                "cl_a",
                "mu_lat",
                "mu_brake",
                "regen_efficiency",
            )
            if getattr(self, name) is None
        ]
        if missing:
            raise ValueError(
                f"Vehicle parameters not fitted: {', '.join(missing)}. "
                "Run scripts/fit_vehicle.py before simulating."
            )
