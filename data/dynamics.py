"""Per-sample longitudinal dynamics, extracted once and cached.

Walking every lap of every session and calling get_telemetry() costs ~20 minutes of CPU
for the 2026 calendar. Exploration, fitting and validation all need the same table, so it
is built once and cached to Parquet.

Only 2026-native sessions are included. Fallback sessions are a different car under
different regulations and must never reach the physics fit — they contribute geometry
only.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from data.cache import PROCESSED_DIR, enable
from data.sessions import (
    build_registry,
    candidate_reference_laps,
    load_qualifying,
    session_weather,
)

DYNAMICS_PATH = PROCESSED_DIR / "dynamics_2026.parquet"
WEATHER_PATH = PROCESSED_DIR / "weather_2026.parquet"
REFERENCE_PATH = PROCESSED_DIR / "reference_traces_2026.parquet"


def _lap_flags(lap, session_best_s: float) -> dict:
    """Lap-level quality metadata.

    Needed because a qualifying session is mostly NOT flying laps. Out-laps and in-laps
    are driven well below the limit and with quite different energy management, and
    pooling them into a power fit made the cars look like they were running on the ICE
    alone.
    """
    lap_time = lap.get("LapTime")
    lap_s = float(pd.Timedelta(lap_time).total_seconds()) if pd.notna(lap_time) else np.nan
    accurate = bool(lap.get("IsAccurate", False))
    deleted = bool(lap.get("Deleted", False)) if pd.notna(lap.get("Deleted")) else False
    green = str(lap.get("TrackStatus", "")).strip() == "1"
    ratio = lap_s / session_best_s if np.isfinite(lap_s) and session_best_s > 0 else np.nan
    return {
        "lap_time_s": np.float32(lap_s),
        "lap_time_ratio": np.float32(ratio),
        "is_clean": bool(accurate and not deleted and green and np.isfinite(lap_s)),
    }


def _lap_samples(lap) -> pd.DataFrame | None:
    """Raw car data for one lap.

    get_car_data(), not get_telemetry(). The merged telemetry frame interleaves car and
    position samples onto a ~8 Hz grid and interpolates the gaps, but Speed, Throttle and
    Brake are only measured at ~4 Hz. Differentiating the merged frame would manufacture
    smooth intermediate samples that carry no new information and would understate the
    noise in dv/dt. It is also far cheaper, since no position merge is performed.
    """
    try:
        tel = lap.get_car_data()
    except Exception:  # noqa: BLE001 - a bad lap is skipped, never fabricated
        return None
    need = {"Speed", "Throttle", "Brake", "Time"}
    if not need.issubset(tel.columns) or len(tel) < 20:
        return None

    t = tel["Time"].dt.total_seconds().to_numpy()
    v = tel["Speed"].to_numpy() / 3.6
    if not np.all(np.diff(t) > 0):
        return None

    dt = np.gradient(t)
    with np.errstate(invalid="ignore", divide="ignore"):
        accel = np.gradient(v) / dt

    # Distance travelled within the lap, integrated from speed. Needed to look up the
    # curvature at each sample: a car coasting through a corner is shedding speed to tyre
    # scrub, not to drag, and including those samples corrupts the aero fit.
    distance = np.concatenate([[0.0], np.cumsum(0.5 * (v[1:] + v[:-1]) * np.diff(t))])

    return pd.DataFrame(
        {
            "v": v.astype("float32"),
            "accel": accel.astype("float32"),
            "dt": dt.astype("float32"),
            "distance": distance.astype("float32"),
            "lap_distance": np.float32(distance[-1]),
            "throttle": tel["Throttle"].to_numpy().astype("float32"),
            "brake": tel["Brake"].to_numpy().astype(bool),
            "rpm": tel["RPM"].to_numpy().astype("float32")
            if "RPM" in tel.columns
            else np.zeros(len(tel), dtype="float32"),
            "gear": tel["nGear"].to_numpy().astype("int8")
            if "nGear" in tel.columns
            else np.zeros(len(tel), dtype="int8"),
        }
    )


def _attach_curvature(df: pd.DataFrame, circuit_id: str) -> pd.DataFrame:
    """Look up track curvature at each sample, and with it lateral acceleration.

    Only laps whose integrated distance matches the circuit length are mapped. An in-lap
    or out-lap covers the pit lane, so its distance axis does not correspond to track
    position and any curvature read from it would be meaningless. Those samples keep a
    NaN curvature and are excluded from fits that need it.
    """
    import json

    path = PROCESSED_DIR / "circuits" / f"{circuit_id}.json"
    df["curvature"] = np.nan
    df["a_lat"] = np.nan
    if not path.exists():
        return df

    geo = json.loads(path.read_text(encoding="utf-8"))
    grid = np.asarray(geo["distance_m"], dtype=float)
    kappa = np.asarray(geo["curvature_1_per_m"], dtype=float)
    track_len = float(geo["lap_distance_m"])

    full_lap = np.abs(df["lap_distance"].to_numpy() - track_len) / track_len < 0.05
    if not full_lap.any():
        return df

    frac = df.loc[full_lap, "distance"].to_numpy() / df.loc[full_lap, "lap_distance"].to_numpy()
    k = np.interp(np.clip(frac, 0.0, 1.0) * grid[-1], grid, kappa, period=grid[-1])
    df.loc[full_lap, "curvature"] = k.astype("float32")
    df.loc[full_lap, "a_lat"] = (
        df.loc[full_lap, "v"].to_numpy() ** 2 * np.abs(k)
    ).astype("float32")
    return df


def build(force: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Extract and cache per-sample dynamics for every 2026-native qualifying session."""
    if DYNAMICS_PATH.exists() and WEATHER_PATH.exists() and not force:
        return pd.read_parquet(DYNAMICS_PATH), pd.read_parquet(WEATHER_PATH)

    enable()
    available, _ = build_registry()
    native = [r for r in available if not r.is_fallback]
    print(f"Extracting dynamics from {len(native)} 2026-native sessions")

    frames, weather_rows = [], []
    for ref in native:
        try:
            session = load_qualifying(ref)
        except Exception as exc:  # noqa: BLE001
            print(f"  {ref.circuit_id:<16} FAILED {type(exc).__name__}: {exc}", flush=True)
            continue

        best = session.laps["LapTime"].dropna()
        session_best_s = (
            float(pd.Timedelta(best.min()).total_seconds()) if len(best) else float("nan")
        )

        laps = []
        for _, lap in session.laps.iterrows():
            got = _lap_samples(lap)
            if got is None:
                continue
            for key, value in _lap_flags(lap, session_best_s).items():
                got[key] = value
            laps.append(got)
        if not laps:
            print(f"  {ref.circuit_id:<16} no usable laps", flush=True)
            continue

        df = pd.concat(laps, ignore_index=True)
        df = df[np.isfinite(df["accel"]) & (df["dt"] > 0.05) & (df["dt"] < 1.5)]
        df["circuit"] = ref.circuit_id
        df = _attach_curvature(df, ref.circuit_id)
        frames.append(df)

        w = session_weather(session)
        w["circuit"] = ref.circuit_id
        weather_rows.append(w)
        print(f"  {ref.circuit_id:<16} {len(laps):>4} laps  {len(df):>7,} samples",
              flush=True)

    if not frames:
        raise RuntimeError("no 2026 sessions yielded usable dynamics")

    dynamics = pd.concat(frames, ignore_index=True)
    dynamics["circuit"] = dynamics["circuit"].astype("category")
    weather = pd.DataFrame(weather_rows)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    dynamics.to_parquet(DYNAMICS_PATH, index=False)
    weather.to_parquet(WEATHER_PATH, index=False)
    print(f"\nCached {len(dynamics):,} samples -> {DYNAMICS_PATH}")
    return dynamics, weather


MAX_TRACE_GAP_M = 60.0
# Longest run of unchanging speed tolerated before a lap is treated as frozen.
MAX_FROZEN_SAMPLES = 25


def _longest_frozen_run(speed: np.ndarray) -> int:
    """Longest run of consecutive samples with no change in speed.

    Catches held telemetry, which a gap check cannot: FastF1 derives Distance by
    integrating Speed, so a frozen speed still yields a smoothly increasing distance
    axis. Suzuka's fastest lap sat at exactly 189.0 km/h with throttle reading 104 for
    the final 1.45 km, and that stretch was being scored as simulation error.
    """
    if len(speed) < 2:
        return 0
    same = np.abs(np.diff(speed)) < 1e-9
    best = run = 0
    for flag in same:
        run = run + 1 if flag else 0
        best = max(best, run)
    return best


def _first_continuous_lap(candidates, grid: np.ndarray):
    """First candidate lap whose telemetry covers the lap without gaps or frozen data.

    Returns (lap, telemetry, source distance axis, largest gap, rank) or None.
    Interpolating across a multi-hundred-metre gap invents a straight line through a
    region where nothing was measured, which would then be scored as model error.
    """
    for rank, lap in enumerate(candidates):
        try:
            tel = lap.get_telemetry().add_distance()
        except Exception:  # noqa: BLE001
            continue
        if "Distance" not in tel.columns or len(tel) < 50:
            continue

        raw = tel["Distance"].to_numpy(dtype=float)
        keep = np.concatenate([[True], np.diff(raw) > 0.0])
        tel = tel.loc[keep]
        raw = raw[keep]
        if len(raw) < 50 or raw[-1] <= 0:
            continue

        gap_m = float(np.max(np.diff(raw))) if len(raw) > 1 else float("inf")
        if gap_m > MAX_TRACE_GAP_M:
            continue
        if _longest_frozen_run(tel["Speed"].to_numpy(dtype=float)) > MAX_FROZEN_SAMPLES:
            continue
        # Align on fractional lap position: telemetry distance and geometry length
        # differ by a fraction of a percent.
        return lap, tel, raw / raw[-1] * grid[-1], gap_m, rank
    return None


def build_reference_traces(force: bool = False) -> pd.DataFrame:
    """Reference-lap speed/throttle/brake resampled onto each circuit's geometry grid.

    This is the ground truth the Phase 2 forward simulation is scored against, and the
    input to the grip fit, which needs speed paired with curvature at the same point.

    2026-native circuits only — a 2025 lap is a different car, so its speed trace must
    never be used as a physics target.
    """
    if REFERENCE_PATH.exists() and not force:
        return pd.read_parquet(REFERENCE_PATH)

    import json

    enable()
    available, _ = build_registry()
    native = [r for r in available if not r.is_fallback]

    rows = []
    for ref in native:
        geo_path = PROCESSED_DIR / "circuits" / f"{ref.circuit_id}.json"
        if not geo_path.exists():
            print(f"  {ref.circuit_id:<16} no geometry built; skipped", flush=True)
            continue
        geo = json.loads(geo_path.read_text(encoding="utf-8"))

        grid = np.asarray(geo["distance_m"], dtype=float)
        try:
            session = load_qualifying(ref)
            candidates = candidate_reference_laps(session)
        except Exception as exc:  # noqa: BLE001
            print(f"  {ref.circuit_id:<16} FAILED {type(exc).__name__}: {exc}", flush=True)
            continue

        chosen = _first_continuous_lap(candidates, grid)
        if chosen is None:
            print(f"  {ref.circuit_id:<16} no lap with continuous telemetry; skipped",
                  flush=True)
            continue
        lap, tel, src, gap_m, rank = chosen

        rows.append(
            pd.DataFrame(
                {
                    "circuit": ref.circuit_id,
                    "distance_m": grid,
                    "speed_mps": np.interp(grid, src, tel["Speed"].to_numpy() / 3.6),
                    "throttle": np.interp(grid, src, tel["Throttle"].to_numpy()),
                    "brake": np.interp(
                        grid, src, tel["Brake"].to_numpy().astype(float)
                    ) > 0.5,
                    "curvature": np.asarray(geo["curvature_1_per_m"], dtype=float),
                    "gradient": np.asarray(geo["gradient"], dtype=float),
                    "step_m": geo["step_m"],
                    "lap_time_s": float(pd.Timedelta(lap["LapTime"]).total_seconds()),
                    "driver": str(lap["Driver"]),
                    "max_gap_m": gap_m,
                }
            )
        )
        note = "" if rank == 0 else f"  (fell back {rank} lap(s): gaps in faster laps)"
        print(f"  {ref.circuit_id:<16} {len(grid):>5} points  ref {lap['Driver']} "
              f"{pd.Timedelta(lap['LapTime']).total_seconds():.3f}s  "
              f"max gap {gap_m:.0f} m{note}", flush=True)

    if not rows:
        raise RuntimeError("no reference traces could be built")

    out = pd.concat(rows, ignore_index=True)
    out.to_parquet(REFERENCE_PATH, index=False)
    print(f"\nCached reference traces -> {REFERENCE_PATH}")
    return out


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not DYNAMICS_PATH.exists():
        return build()
    return pd.read_parquet(DYNAMICS_PATH), pd.read_parquet(WEATHER_PATH)


def load_reference_traces() -> pd.DataFrame:
    if not REFERENCE_PATH.exists():
        return build_reference_traces()
    return pd.read_parquet(REFERENCE_PATH)


if __name__ == "__main__":
    build(force=True)
    build_reference_traces(force=True)
