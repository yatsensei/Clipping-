"""The vehicle as it is set up for one circuit.

Two things vary by circuit and both live in artefacts: the session's air density
(from the weather table) and the fitted track grip factor (from the validation). Every
script that simulates a circuit — the optimiser, the training-data builder, the policy
scorer — has to apply BOTH, or it times its laps on a different car from the one the
reference results were solved on. The first regeneration after grip factors were
introduced scored the learned policy at -388% on Monaco for exactly that reason.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from config.vehicle import air_density
from data.cache import PROCESSED_DIR
from physics.vehicle import VehicleModel


@dataclass(frozen=True)
class CircuitSetup:
    vehicle: VehicleModel
    air_density: float
    air_density_measured: bool
    grip_scale: float
    grip_scale_fitted: bool


def circuit_density(circuit_id: str, default: float,
                    processed: Path = PROCESSED_DIR) -> tuple[float, bool]:
    path = processed / "weather_2026.parquet"
    if not path.exists():
        return default, False
    w = pd.read_parquet(path)
    row = w[w["circuit"] == circuit_id]
    if row.empty or pd.isna(row.iloc[0].get("pressure_mbar")):
        return default, False
    r = row.iloc[0]
    return air_density(r["pressure_mbar"], r["air_temp_c"], r["humidity_pct"] or 0.0), True


def grip_factor(circuit_id: str, processed: Path = PROCESSED_DIR) -> tuple[float, bool]:
    """The circuit's fitted track grip factor, or 1.0 where no 2026 lap exists."""
    path = processed / "grip_factors.json"
    if not path.exists():
        return 1.0, False
    entry = json.loads(path.read_text(encoding="utf-8")).get(circuit_id)
    if not entry:
        return 1.0, False
    return float(entry["grip_scale"]), True


def vehicle_for_circuit(circuit_id: str, fit: dict,
                        processed: Path = PROCESSED_DIR) -> CircuitSetup:
    rho, measured = circuit_density(circuit_id, float(fit["air_density"]), processed)
    grip, fitted = grip_factor(circuit_id, processed)
    return CircuitSetup(
        vehicle=VehicleModel.from_fit(fit, air_density=rho, grip_scale=grip),
        air_density=rho,
        air_density_measured=measured,
        grip_scale=grip,
        grip_scale_fitted=fitted,
    )
