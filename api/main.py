"""FastAPI service exposing the precomputed deployment strategies.

Everything served here was computed offline by Phases 1-4. The DP is far too slow for a
request cycle and the circuits do not change, so nothing is solved on demand.

Two contracts the frontend depends on:

  Shared distance index. Geometry and every strategy for a circuit are sampled on the
  same distance grid, returned once as `distance_m`. The client can overlay traces
  directly without re-interpolating, and a chart cursor maps to one index everywhere.

  Provenance on every response. Which session, which driver, whether that session is a
  pre-2026 fallback, and which fields are model output rather than measurement.

Run:  uv run uvicorn api.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from api import store
from api.schemas import (
    CircuitDetail,
    CircuitListItem,
    ComparisonResponse,
    GeometryResponse,
    MetaResponse,
    StrategyResponse,
    StrategySummary,
)

app = FastAPI(
    title="Clipping — 2026 F1 energy deployment",
    version="0.1.0",
    description=(
        "Lap-time-optimal electrical deployment for the 2026 Formula 1 regulations. "
        "Geometry is derived from measured GPS; speed, deployment, state of charge and "
        "clipping are model output from a fitted physics simulation."
    ),
)

# The frontend is served separately in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.exception_handler(store.ArtifactMissing)
async def _missing(_request, exc: store.ArtifactMissing):
    raise HTTPException(status_code=404, detail=str(exc))


def _get_circuit(circuit_id: str):
    for c in store.circuit_index():
        if c.circuit_id == circuit_id:
            return c
    raise HTTPException(
        status_code=404,
        detail=f"unknown circuit '{circuit_id}'; see GET /circuits",
    )


@app.get("/health")
def health() -> dict:
    try:
        n = len(store.circuit_index())
    except store.ArtifactMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ok", "circuits": n}


@app.get("/meta", response_model=MetaResponse)
def meta() -> MetaResponse:
    """Regulation sources, fitted vs assumed parameters, and model accuracy."""
    try:
        return MetaResponse(**store.model_basis())
    except store.ArtifactMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/circuits", response_model=list[CircuitListItem])
def list_circuits() -> list[CircuitListItem]:
    """Every circuit with geometry built, in calendar order."""
    try:
        summaries = store.circuit_index()
    except store.ArtifactMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return [CircuitListItem(**vars(c)) for c in summaries]


@app.get("/circuits/{circuit_id}", response_model=CircuitDetail)
def circuit_detail(circuit_id: str) -> CircuitDetail:
    summary = _get_circuit(circuit_id)
    geo = store.geometry(circuit_id)
    return CircuitDetail(
        **vars(summary),
        provenance=store.provenance_for(circuit_id),
        segments=geo["segments"],
        official_corners=geo["official_corners"],
        learned_policy=store.policy_scores().get(circuit_id),
    )


@app.get("/circuits/{circuit_id}/geometry", response_model=GeometryResponse)
def circuit_geometry(circuit_id: str) -> GeometryResponse:
    """Centreline for rendering, on the shared distance index."""
    _get_circuit(circuit_id)
    geo = store.geometry(circuit_id)
    return GeometryResponse(
        circuit_id=circuit_id,
        step_m=geo["step_m"],
        lap_distance_m=geo["lap_distance_m"],
        distance_m=geo["distance_m"],
        x_m=geo["x_m"],
        y_m=geo["y_m"],
        z_m=geo["z_m"],
        curvature_1_per_m=geo["curvature_1_per_m"],
        gradient=geo["gradient"],
        segments=geo["segments"],
        official_corners=geo["official_corners"],
        provenance=store.provenance_for(circuit_id),
        data_type="measured_gps_derived",
    )


@app.get("/circuits/{circuit_id}/strategy", response_model=StrategyResponse)
def circuit_strategy(
    circuit_id: str,
    mode: str = Query("optimal", description="optimal | naive (= uniform) | greedy"),
) -> StrategyResponse:
    """Per-distance-point traces for one strategy, on the shared distance index."""
    _get_circuit(circuit_id)
    data = store.strategies(circuit_id)
    try:
        key = store.resolve_mode(mode)
    except KeyError:
        raise HTTPException(
            status_code=422,
            detail=f"unknown mode '{mode}'; expected one of "
                   f"{sorted(set(store.STRATEGY_ALIASES))}",
        ) from None

    series = data["strategies"][key]
    lap_s = float(data[f"{key}_lap_s"])
    periodic = bool(data[f"{key}_periodic"]) if f"{key}_periodic" in data else True

    return StrategyResponse(
        circuit_id=circuit_id,
        mode=key,
        requested_mode=mode,
        lap_time_s=round(lap_s, 3),
        distance_m=data["distance_m"],
        speed_kph=series["speed_kph"],
        deploy_kw=series["deploy_kw"],
        harvest_kw=series["harvest_kw"],
        soc_mj=series["soc_mj"],
        clipping=series["clipping"],
        deploy_fraction=series["deploy_fraction"],
        soc_start_mj=data["soc_start_mj"],
        energy_deployed_mj=round(float(data.get(f"{key}_deployed_mj", float("nan"))), 3),
        repeatable=periodic,
        repeatability_note=(
            None if periodic else
            "This lap ends with less energy than it started, so it cannot be repeated. "
            "Its lap time is not comparable with strategies that are energy-neutral."
        ),
        provenance=store.provenance_for(circuit_id),
        data_type="model_output",
    )


@app.get("/circuits/{circuit_id}/comparison", response_model=ComparisonResponse)
def circuit_comparison(circuit_id: str) -> ComparisonResponse:
    """Lap times, deltas and energy totals for all three strategies."""
    _get_circuit(circuit_id)
    d = store.strategies(circuit_id)

    def summary(key: str) -> StrategySummary:
        series = d["strategies"][key]
        clip = series["clipping"]
        return StrategySummary(
            mode=key,
            lap_time_s=round(float(d[f"{key}_lap_s"]), 3),
            energy_deployed_mj=round(float(d.get(f"{key}_deployed_mj", 0.0)), 3),
            energy_harvested_mj=(
                round(float(d["optimal_harvested_mj"]), 3) if key == "optimal" else None
            ),
            clipping_pct=round(100.0 * sum(clip) / max(len(clip), 1), 2),
            repeatable=bool(d.get(f"{key}_periodic", True)),
            soc_end_mj=round(float(d.get(f"{key}_soc_end_mj", d["soc_start_mj"])), 3),
        )

    return ComparisonResponse(
        circuit_id=circuit_id,
        soc_start_mj=d["soc_start_mj"],
        harvest_cap_mj=d["harvest_cap_mj"],
        baseline="uniform",
        baseline_statement=d["baseline_statement"],
        gain_vs_uniform_s=round(float(d["gain_vs_uniform_s"]), 3),
        gain_vs_greedy_s=round(float(d["gain_vs_greedy_s"]), 3),
        greedy_energy_debt_mj=round(float(d["greedy_energy_debt_mj"]), 3),
        greedy_caveat=(
            "Greedy is usually faster over a single lap, but it ends with an empty "
            "store and cannot be run again. The headline gain is measured against "
            "uniform deployment, which is repeatable."
        ),
        strategies=[summary(k) for k in ("optimal", "uniform", "greedy")],
        learned_policy=store.policy_scores().get(circuit_id),
        provenance=store.provenance_for(circuit_id),
        data_type="model_output",
    )
