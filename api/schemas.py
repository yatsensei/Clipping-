"""Response models.

Every payload that contains simulated quantities carries `data_type: "model_output"`.
Geometry carries `"measured_gps_derived"`. The distinction is not decoration: public F1
telemetry has no energy channels, so nothing about deployment or state of charge is
measured, and the interface is required to say so.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DataType = Literal["measured_gps_derived", "model_output"]


class Provenance(BaseModel):
    session: str
    data_year: int
    is_fallback: bool = Field(
        description="True when the 2026 round has not run and geometry comes from an "
                    "earlier season at the same venue."
    )
    reference_driver: str
    reference_team: str
    reference_lap_time_s: float
    laps_pooled: int
    gps_samples: int
    note: str
    fallback_note: str | None = None


class LearnedPolicyScore(BaseModel):
    gain_retained_pct: float
    lap_time_s: float
    periodic: bool
    comparable: bool = Field(
        description="False when the learned lap ended with less energy than it started, "
                    "which makes its lap time incomparable with the optimiser's."
    )


class CircuitListItem(BaseModel):
    circuit_id: str
    event_name: str
    location: str
    country: str
    round_number: int
    event_date: str
    lap_distance_m: float
    corner_count: int
    official_corner_count: int
    longest_straight_m: float
    data_year: int
    is_fallback: bool
    provenance: str
    reference_driver: str
    reference_lap_time_s: float
    has_strategy: bool


class CircuitDetail(CircuitListItem):
    provenance: Provenance  # type: ignore[assignment]
    segments: list[dict[str, Any]]
    official_corners: list[dict[str, Any]]
    learned_policy: LearnedPolicyScore | None = None


class GeometryResponse(BaseModel):
    circuit_id: str
    step_m: float
    lap_distance_m: float
    distance_m: list[float] = Field(
        description="Shared distance index. Strategy traces use the same grid, so the "
                    "client can overlay them without re-interpolating."
    )
    x_m: list[float]
    y_m: list[float]
    z_m: list[float]
    curvature_1_per_m: list[float]
    gradient: list[float]
    segments: list[dict[str, Any]]
    official_corners: list[dict[str, Any]]
    provenance: Provenance
    data_type: DataType


class StrategyResponse(BaseModel):
    circuit_id: str
    mode: Literal["optimal", "uniform", "greedy"]
    requested_mode: str
    lap_time_s: float
    distance_m: list[float]
    speed_kph: list[float]
    deploy_kw: list[float]
    harvest_kw: list[float]
    soc_mj: list[float]
    clipping: list[bool]
    deploy_fraction: list[float]
    soc_start_mj: float
    energy_deployed_mj: float
    repeatable: bool
    repeatability_note: str | None
    provenance: Provenance
    data_type: DataType


class StrategySummary(BaseModel):
    mode: str
    lap_time_s: float
    energy_deployed_mj: float
    energy_harvested_mj: float | None
    clipping_pct: float
    repeatable: bool
    soc_end_mj: float


class ComparisonResponse(BaseModel):
    circuit_id: str
    soc_start_mj: float
    harvest_cap_mj: float
    baseline: Literal["uniform"]
    baseline_statement: str = Field(
        description="A gain figure without a named baseline is meaningless, so the "
                    "baseline is stated in the payload."
    )
    gain_vs_uniform_s: float
    gain_vs_greedy_s: float
    greedy_energy_debt_mj: float
    greedy_caveat: str
    strategies: list[StrategySummary]
    learned_policy: LearnedPolicyScore | None
    provenance: Provenance
    data_type: DataType


class MetaResponse(BaseModel):
    regulations: dict[str, Any]
    vehicle: dict[str, Any]
    simulation_accuracy: dict[str, Any] | None
