"""Longitudinal point-mass vehicle model.

    F_traction = eta * P_available / v
    F_drag     = 0.5 * rho * Cd*A * v^2
    F_roll     = Crr * m * g
    F_grade    = m * g * sin(theta)
    m * dv/dt  = F_traction - F_drag - F_roll - F_grade

Aerodynamic and rolling coefficients are fitted from telemetry (scripts/fit_vehicle.py),
never assumed. Everything regulatory — the 350 kW cap and the speed taper — comes from
config/regulations.py.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from config.regulations import ERSK_MAX_POWER_W, Mode, max_deploy_power_w
from config.vehicle import GRAVITY_M_S2


@dataclass(frozen=True)
class VehicleModel:
    """A fitted 2026-spec car. All values SI."""

    mass_kg: float
    cd_a: float                    # drag area Cd*A [m^2]
    crr: float                     # rolling resistance coefficient [-]
    air_density: float             # [kg/m^3], from session weather
    p_ice_w: float                 # effective ICE crankshaft power [W]
    driveline_efficiency: float    # crankshaft/ES to road [-]
    # Grip is not a constant. An F1 car's cornering and braking limits rise with speed
    # because downforce rises with v^2 — a hairpin is grip-limited near 1.5 g while a
    # fast sweeper sustains 5 g. Modelling a single a_lat_max would misplace corner
    # speeds badly at both ends of the range, so grip is written as
    #     a_limit(v) = mu * (g + 0.5 * rho * Cl*A * v^2 / m)
    # with Cl*A and the friction coefficients fitted from telemetry.
    cl_a: float                    # downforce area Cl*A [m^2]
    mu_lat: float                  # lateral friction coefficient [-]
    mu_brake: float                # longitudinal braking friction coefficient [-]
    regen_efficiency: float        # braking energy recovered at the CU-K bus [-]
    # Constant retarding force present only when off throttle: engine braking plus MGU-K
    # regen at roughly constant torque. Measured on coasting, where it is ~13x rolling
    # resistance. Applying it while under power would be wrong, so it is kept separate
    # from the always-on resistive terms.
    f_offthrottle_n: float = 0.0
    # Absolute ceiling on lateral acceleration [m/s^2]. Without it the model is unbounded:
    # mu*(g + rho*Cl*A*v^2/2m) grows as v^2, exactly like the centripetal demand
    # v^2*kappa, so above a critical radius the downforce term wins and cornering speed
    # goes to infinity. Real tyres saturate and the measured envelope does plateau.
    # Omitting this made the simulated lap 13 s too fast and let Monaco reach 329 km/h.
    a_lat_ceiling: float = 50.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_fit(cls, fit: dict, air_density: float | None = None) -> "VehicleModel":
        """Build from scripts/fit_vehicle.py output.

        `air_density` overrides the pooled value so each circuit can be simulated at its
        own conditions — Mexico City's thin air is a ~20% change in drag.
        """
        missing = [
            k for k in ("cd_a", "crr", "cl_a", "mu_lat", "mu_brake", "p_ice_w",
                        "driveline_efficiency")
            if fit.get(k) is None or not np.isfinite(fit.get(k, np.nan))
        ]
        if missing:
            raise ValueError(f"vehicle fit is missing or non-finite: {', '.join(missing)}")

        return cls(
            mass_kg=float(fit["mass_kg"]),
            cd_a=float(fit["cd_a"]),
            crr=float(fit["crr"]),
            air_density=float(air_density if air_density is not None else fit["air_density"]),
            p_ice_w=float(fit["p_ice_w"]),
            driveline_efficiency=float(fit["driveline_efficiency"]),
            cl_a=float(fit["cl_a"]),
            mu_lat=float(fit["mu_lat"]),
            mu_brake=float(fit["mu_brake"]),
            regen_efficiency=float(fit.get("regen_efficiency", 0.9)),
            f_offthrottle_n=float(fit.get("f_offthrottle_n", 0.0)),
            a_lat_ceiling=float(fit.get("a_lat_ceiling", 50.0)),
        )

    # -- forces ------------------------------------------------------------------------

    def drag_force(self, v: np.ndarray | float) -> np.ndarray | float:
        return 0.5 * self.air_density * self.cd_a * np.square(v)

    def rolling_force(self) -> float:
        return self.crr * self.mass_kg * GRAVITY_M_S2

    def grade_force(self, gradient: np.ndarray | float) -> np.ndarray | float:
        """Gradient is rise over run; small-angle sin(atan(g)) == g/sqrt(1+g^2)."""
        g = np.asarray(gradient, dtype=float)
        return self.mass_kg * GRAVITY_M_S2 * g / np.sqrt(1.0 + g * g)

    def resistive_force(
        self, v: np.ndarray | float, gradient: np.ndarray | float = 0.0
    ) -> np.ndarray | float:
        return self.drag_force(v) + self.rolling_force() + self.grade_force(gradient)

    # -- power -------------------------------------------------------------------------

    def electrical_power_w(
        self, v_mps: np.ndarray | float, deploy_fraction: np.ndarray | float,
        mode: Mode = "normal",
    ) -> np.ndarray:
        """Deployed electrical power after the regulatory speed taper.

        deploy_fraction is the driver's request in [0, 1]; the taper is a ceiling the
        regulations impose on top of it. This is why energy spent at the top of a straight
        is wasted, and the optimiser has to discover that rather than being told.
        """
        v_kph = np.asarray(v_mps, dtype=float) * 3.6
        ceiling = np.vectorize(max_deploy_power_w)(v_kph, mode)
        return np.clip(np.asarray(deploy_fraction, dtype=float), 0.0, 1.0) * ceiling

    def propulsive_power_w(
        self, v_mps: np.ndarray | float, deploy_fraction: np.ndarray | float,
        mode: Mode = "normal",
    ) -> np.ndarray:
        """Total power at the road: ICE plus tapered electrical, after driveline loss."""
        elec = self.electrical_power_w(v_mps, deploy_fraction, mode)
        return self.driveline_efficiency * (self.p_ice_w + elec)

    def tractive_force(
        self, v_mps: np.ndarray | float, deploy_fraction: np.ndarray | float,
        mode: Mode = "normal",
    ) -> np.ndarray:
        v = np.maximum(np.asarray(v_mps, dtype=float), 1.0)  # avoid P/v blowing up at rest
        return self.propulsive_power_w(v, deploy_fraction, mode) / v

    # -- limits ------------------------------------------------------------------------

    def downforce_n(self, v: np.ndarray | float) -> np.ndarray | float:
        return 0.5 * self.air_density * self.cl_a * np.square(v)

    def lateral_limit(self, v: np.ndarray | float) -> np.ndarray | float:
        """Peak lateral acceleration available at speed v [m/s^2], with tyre saturation."""
        return np.minimum(
            self.mu_lat * (GRAVITY_M_S2 + self.downforce_n(v) / self.mass_kg),
            self.a_lat_ceiling,
        )

    def braking_limit(self, v: np.ndarray | float) -> np.ndarray | float:
        """Peak deceleration from the tyres at speed v, excluding aero drag [m/s^2]."""
        return self.mu_brake * (
            GRAVITY_M_S2 + self.downforce_n(v) / self.mass_kg
        )

    def grip_available_fraction(
        self, v: np.ndarray | float, curvature: np.ndarray | float
    ) -> np.ndarray | float:
        """Share of longitudinal grip still free while cornering — the friction ellipse.

        A tyre has one grip budget. Using it laterally leaves less for driving or
        braking, so longitudinal capability falls as sqrt(1 - (a_lat/a_lat_max)^2).
        Without this the model accelerates out of a corner at full traction from the
        apex, which is a large part of why the first simulation ran too fast.
        """
        a_lat = np.square(v) * np.abs(np.asarray(curvature, dtype=float))
        limit = np.maximum(self.lateral_limit(v), 1e-6)
        ratio = np.clip(a_lat / limit, 0.0, 1.0)
        return np.sqrt(np.maximum(1.0 - ratio * ratio, 0.0))

    def max_tractive_force(
        self, v: np.ndarray | float, curvature: np.ndarray | float = 0.0
    ) -> np.ndarray | float:
        """Longitudinal force the tyres can transmit at this speed and cornering load."""
        grip_n = self.mu_brake * (
            self.mass_kg * GRAVITY_M_S2 + self.downforce_n(v)
        )
        return grip_n * self.grip_available_fraction(v, curvature)

    def corner_speed_limit(self, curvature: np.ndarray | float) -> np.ndarray:
        """Steady-state cornering speed for a given curvature.

        The car must satisfy v^2*kappa <= min(mu*(g + rho*Cl*A*v^2/2m), a_lat_ceiling),
        so the limit is the smaller of two branches:

          - downforce branch: solving v^2*kappa = mu*g + c*v^2 gives a finite speed only
            while kappa exceeds c; below that the road is open enough to be flat out,
            which is why Copse and Curva Grande are taken at full throttle
          - saturation branch: v = sqrt(a_lat_ceiling / kappa), which always binds

        Taking the minimum keeps the result finite for every curvature.
        """
        k = np.abs(np.asarray(curvature, dtype=float))
        k = np.maximum(k, 1e-12)

        downforce_term = self.mu_lat * self.air_density * self.cl_a / (2.0 * self.mass_kg)
        denom = k - downforce_term
        with np.errstate(divide="ignore", invalid="ignore"):
            v_downforce = np.where(
                denom > 1e-12, np.sqrt(self.mu_lat * GRAVITY_M_S2 / denom), np.inf
            )
        v_saturated = np.sqrt(self.a_lat_ceiling / k)
        return np.minimum(v_downforce, v_saturated)

    def terminal_speed_mps(self, deploy_fraction: float = 1.0) -> float:
        """Speed where propulsive force equals resistance — the model's top speed.

        Bisection rather than fixed-point iteration: net force is monotonically
        decreasing in v over this range, so bisection is guaranteed to converge, whereas
        the gradient step it replaced could oscillate and silently return a stale value.
        """
        def net(v: float) -> float:
            return float(
                self.tractive_force(v, deploy_fraction) - self.resistive_force(v)
            )

        lo, hi = 5.0, 200.0
        if net(hi) > 0.0:
            return hi
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            if net(mid) > 0.0:
                lo = mid
            else:
                hi = mid
        return float(0.5 * (lo + hi))

    def max_harvest_power_w(self) -> float:
        """Harvest is bounded by the same absolute ERS-K limit as deployment (Art 5.4.7)."""
        return ERSK_MAX_POWER_W
