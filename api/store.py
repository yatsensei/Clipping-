"""Loads the precomputed artifacts once and serves them from memory.

Nothing is solved on request. The DP takes seconds to minutes per circuit and the
circuits do not change, so Phases 1-4 write their output to data/processed and the API
just reads it. If an artifact is missing the endpoint says so rather than inventing a
substitute.

Every payload carries provenance: which session the geometry came from, which driver's
lap, whether that session is 2026 or an earlier-year fallback, and which figures are
model output rather than measurement. The UI is expected to surface that, so it has to
be in the response.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from config.regulations import (
    ES_USABLE_WINDOW_J,
    OPERATIVE_HARVEST_CAP_BASIS,
    OPERATIVE_HARVEST_CAP_J,
    PU_REGS_DATE,
    PU_REGS_ISSUE,
    PU_REGS_URL,
)

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

# The brief names the constant-deployment baseline "naive"; the code calls it "uniform".
STRATEGY_ALIASES = {"naive": "uniform", "uniform": "uniform",
                    "optimal": "optimal", "greedy": "greedy"}


class ArtifactMissing(RuntimeError):
    """Raised when a circuit has not been built or solved yet."""


@dataclass(frozen=True)
class CircuitSummary:
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


@lru_cache(maxsize=1)
def circuit_index() -> list[CircuitSummary]:
    path = PROCESSED / "circuits_index.json"
    if not path.exists():
        raise ArtifactMissing(
            "circuits_index.json not found — run `python -m scripts.build_circuits`"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: list[CircuitSummary] = []
    for c in raw["circuits"]:
        cid = c["circuit_id"]
        out.append(
            CircuitSummary(
                circuit_id=cid,
                event_name=c["event_name"],
                location=c["location"],
                country=c["country"],
                round_number=c["round_number"],
                event_date=c["event_date"],
                lap_distance_m=round(float(c["lap_distance_m"]), 1),
                corner_count=int(c["n_detected_corners"]),
                official_corner_count=int(c["n_official_corners"]),
                longest_straight_m=round(float(c["longest_straight_m"]), 1),
                data_year=int(c["data_year"]),
                is_fallback=bool(c["is_fallback"]),
                provenance=c["provenance"],
                reference_driver=c["reference_driver"],
                reference_lap_time_s=round(float(c["reference_lap_time_s"]), 3),
                has_strategy=(PROCESSED / "strategies" / f"{cid}.json").exists(),
            )
        )
    return sorted(out, key=lambda c: c.round_number)


@lru_cache(maxsize=None)
def geometry(circuit_id: str) -> dict:
    path = PROCESSED / "circuits" / f"{circuit_id}.json"
    if not path.exists():
        raise ArtifactMissing(f"no geometry for '{circuit_id}'")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def strategies(circuit_id: str) -> dict:
    path = PROCESSED / "strategies" / f"{circuit_id}.json"
    if not path.exists():
        raise ArtifactMissing(
            f"no strategy solved for '{circuit_id}' — run `python -m scripts.run_optimiser`"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_mode(mode: str) -> str:
    key = mode.strip().lower()
    if key not in STRATEGY_ALIASES:
        raise KeyError(mode)
    return STRATEGY_ALIASES[key]


@lru_cache(maxsize=1)
def vehicle_fit() -> dict:
    path = PROCESSED / "vehicle_fit.json"
    if not path.exists():
        raise ArtifactMissing("vehicle_fit.json not found — run `scripts.fit_vehicle`")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def policy_scores() -> dict[str, dict]:
    """Per-circuit learned-policy results, if Phase 4 has been run."""
    path = PROCESSED / "policy_evaluation.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    best = df[df["model"] == "gbm"]
    return {
        str(r["held_out"]): {
            "gain_retained_pct": round(float(r["gain_retained_pct"]), 1),
            "lap_time_s": round(float(r["model_lap_s"]), 3),
            "periodic": bool(r["periodic"]),
            # A lap that ends short spent energy it never repaid, so its time is not
            # comparable with the optimiser's. The UI must not present it as a win.
            "comparable": bool(r["periodic"]),
        }
        for _, r in best.iterrows()
    }


def provenance_for(circuit_id: str) -> dict:
    d = geometry(circuit_id)["diagnostics"]
    return {
        "session": d["session"],
        "data_year": d["data_year"],
        "is_fallback": d["is_fallback"],
        "reference_driver": d["reference_driver"],
        "reference_team": d["reference_team"],
        "reference_lap_time_s": round(float(d["reference_lap_time_s"]), 3),
        "laps_pooled": d["laps_pooled"],
        "gps_samples": d["samples"],
        "note": (
            "Geometry is derived from measured GPS. Speed, deployment, state of charge "
            "and clipping are MODEL OUTPUT from a fitted physics simulation, not "
            "measured data — public F1 telemetry contains no energy channels."
        ),
        "fallback_note": (
            "This circuit has not yet run in 2026. Geometry only is taken from the "
            "session named above; its speed trace is never used, and the physics is "
            "2026-spec throughout."
        ) if d["is_fallback"] else None,
    }


def model_basis() -> dict:
    """What the numbers rest on. Surfaced so the UI can label assumptions."""
    fit = vehicle_fit()
    return {
        "regulations": {
            "source": f"FIA 2026 F1 Power Unit Technical Regulations, {PU_REGS_ISSUE}",
            "published": PU_REGS_DATE,
            "url": PU_REGS_URL,
            "energy_store_window_mj": ES_USABLE_WINDOW_J / 1e6,
            "harvest_cap_mj": OPERATIVE_HARVEST_CAP_J / 1e6,
            "harvest_cap_basis": OPERATIVE_HARVEST_CAP_BASIS,
        },
        "vehicle": {
            "fitted": {
                "cd_a_m2": fit["cd_a"],
                "cl_a_m2": fit["cl_a"],
                "mu_lat": fit["mu_lat"],
                "mu_brake": fit["mu_brake"],
                "f_offthrottle_n": fit["f_offthrottle_n"],
                "a_lat_ceiling_m_s2": fit.get("a_lat_ceiling"),
            },
            "assumed": {
                "crr": fit["crr"],
                "p_ice_w": fit["p_ice_w"],
                "driveline_efficiency": fit["driveline_efficiency"],
                "regen_efficiency": fit.get("regen_efficiency"),
                "mass_kg": fit["mass_kg"],
            },
            "assumptions": fit.get("assumptions", []),
            "power_identifiable": fit.get("power_identifiable"),
        },
        "simulation_accuracy": _accuracy(),
    }


def _accuracy() -> dict | None:
    path = PROCESSED / "simulation_accuracy.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    return {
        "circuits": int(len(df)),
        "mean_speed_rmse_kph": round(float(df["rmse_kph"].mean()), 2),
        "mean_abs_lap_error_s": round(float(df["lap_err_s"].abs().mean()), 3),
        "note": (
            "Forward simulation versus the measured qualifying lap, on the circuits "
            "with 2026 telemetry. This is how far the physics model sits from reality."
        ),
    }


def clear_caches() -> None:
    for fn in (circuit_index, geometry, strategies, vehicle_fit, policy_scores):
        fn.cache_clear()
