"""Energy store model: state of charge, deployment draw, harvest and the per-lap cap.

Capacity is the 4 MJ state-of-charge window of Art. 5.4.9, and the per-lap harvest cap is
the operative qualifying figure from config/regulations.py. A depleted store is not an
error condition — it is *clipping*, the phenomenon this project exists to study: the
driver is flat out and the car is on combustion power alone.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from config.regulations import (
    ES_USABLE_WINDOW_J,
    OPERATIVE_HARVEST_CAP_J,
)


@dataclass
class BatteryState:
    """Mutable energy-store state carried through a lap simulation."""

    soc_j: float
    capacity_j: float = ES_USABLE_WINDOW_J
    harvest_cap_j: float = OPERATIVE_HARVEST_CAP_J
    harvested_j: float = 0.0
    deployed_j: float = 0.0
    clipping_time_s: float = 0.0

    @property
    def soc_fraction(self) -> float:
        return self.soc_j / self.capacity_j if self.capacity_j > 0 else 0.0

    @property
    def harvest_headroom_j(self) -> float:
        """Energy still recoverable this lap under the per-lap cap."""
        return max(0.0, self.harvest_cap_j - self.harvested_j)

    def deployable_energy_j(self, requested_j: float) -> float:
        """Energy actually available for a step's request, limited by what is stored."""
        return max(0.0, min(requested_j, self.soc_j))

    def draw(self, energy_j: float) -> float:
        """Remove energy from the store, returning what was actually delivered."""
        delivered = self.deployable_energy_j(energy_j)
        self.soc_j -= delivered
        self.deployed_j += delivered
        return delivered

    def charge(self, energy_j: float) -> float:
        """Add energy, respecting both the SoC ceiling and the per-lap harvest cap."""
        allowed = min(energy_j, self.harvest_headroom_j, self.capacity_j - self.soc_j)
        allowed = max(0.0, allowed)
        self.soc_j += allowed
        self.harvested_j += allowed
        return allowed

    def copy(self) -> "BatteryState":
        return BatteryState(
            soc_j=self.soc_j,
            capacity_j=self.capacity_j,
            harvest_cap_j=self.harvest_cap_j,
            harvested_j=self.harvested_j,
            deployed_j=self.deployed_j,
            clipping_time_s=self.clipping_time_s,
        )


def periodicity_error_j(soc_start_j: float, soc_end_j: float) -> float:
    """How far a lap falls short of being repeatable.

    Positive means the lap ended with less energy than it started, so it cannot be run
    again — the strategy is a one-off, not a strategy. Phase 3 constrains this to <= 0.
    """
    return soc_start_j - soc_end_j


def harvest_power_available_w(
    braking_power_w: float,
    max_rate_w: float,
    regen_efficiency: float,
) -> float:
    """Electrical power recoverable from a given mechanical braking power."""
    return max(0.0, min(braking_power_w * regen_efficiency, max_rate_w))


def clip_flags(
    deploy_request: np.ndarray,
    deploy_actual_w: np.ndarray,
    throttle_on: np.ndarray,
    tolerance_w: float = 1_000.0,
) -> np.ndarray:
    """True where the driver wanted electrical power and did not get it.

    Covers both causes: an empty store, and the speed taper cutting deployment away.
    """
    wanted = (np.asarray(deploy_request) > 0.0) & np.asarray(throttle_on, dtype=bool)
    shortfall = np.asarray(deploy_request) - np.asarray(deploy_actual_w)
    return wanted & (shortfall > tolerance_w)
