"""Features for the learned deployment policy.

Hard constraint on what may go in here: every feature must be computable DURING a forward
simulation, from the circuit geometry plus the car's current speed and state of charge.
Anything that needs the finished lap — the DP's own speed trace, the eventual lap time,
total energy used — would make the model unusable as a controller and would leak the
answer into the inputs.

Features split into two groups:

  static   geometry only: curvature, gradient, distance to the next and last apex, the
           length of the straight the car is on, the cornering speed limit ahead. All
           precomputed once per circuit.
  dynamic  current speed, current state of charge, and the headroom to the taper
           threshold. Evaluated at each step.
"""

from __future__ import annotations

import numpy as np

from config.regulations import (
    DEPLOY_TAPER_FULL_POWER_KPH,
    ERSK_MAX_POWER_W,
    deploy_taper_fraction,
    max_deploy_power_w,
)

# Lookahead distances for the "what is coming" features, in metres.
LOOKAHEAD_M = (50.0, 100.0, 200.0, 400.0)

STATIC_FEATURES = [
    "curvature_abs",
    "gradient",
    "ceiling_mps",
    "dist_to_next_apex_m",
    "dist_from_last_apex_m",
    "straight_length_m",
    "dist_to_straight_end_m",
    "next_apex_speed_mps",
    "lap_fraction_remaining",
    *[f"ceiling_ahead_{int(m)}m" for m in LOOKAHEAD_M],
    *[f"ceiling_delta_{int(m)}m" for m in LOOKAHEAD_M],
]

DYNAMIC_FEATURES = [
    "speed_mps",
    "soc_fraction",
    "taper_headroom_kph",
    "taper_fraction",
    "speed_vs_ceiling",
    "speed_vs_next_apex",
]

FEATURE_NAMES = STATIC_FEATURES + DYNAMIC_FEATURES


def build_static(
    curvature: np.ndarray,
    gradient: np.ndarray,
    ceiling: np.ndarray,
    step_m: float,
) -> dict[str, np.ndarray]:
    """Geometry-derived features, computed once per circuit.

    Apexes are taken as local minima of the speed ceiling rather than from the
    segmentation, so this stays valid on a circuit that was never segmented and needs no
    agreement with the official corner list.
    """
    n = len(curvature)
    lap_m = n * step_m
    k = np.abs(curvature)

    is_apex = _local_minima(ceiling)
    apex_idx = np.flatnonzero(is_apex)
    if len(apex_idx) == 0:
        apex_idx = np.array([int(np.argmin(ceiling))])

    dist_to_next, dist_from_last, next_apex_speed = _apex_distances(
        apex_idx, ceiling, n, step_m
    )
    straight_len, dist_to_end = _straight_geometry(ceiling, step_m)

    out: dict[str, np.ndarray] = {
        "curvature_abs": k,
        "gradient": np.asarray(gradient, dtype=float),
        "ceiling_mps": np.asarray(ceiling, dtype=float),
        "dist_to_next_apex_m": dist_to_next,
        "dist_from_last_apex_m": dist_from_last,
        "straight_length_m": straight_len,
        "dist_to_straight_end_m": dist_to_end,
        "next_apex_speed_mps": next_apex_speed,
        "lap_fraction_remaining": 1.0 - np.arange(n) * step_m / lap_m,
    }

    for m in LOOKAHEAD_M:
        offset = int(round(m / step_m))
        ahead = np.roll(ceiling, -offset)
        out[f"ceiling_ahead_{int(m)}m"] = ahead
        out[f"ceiling_delta_{int(m)}m"] = ahead - ceiling

    return out


def _local_minima(values: np.ndarray) -> np.ndarray:
    """Circular local minima of the speed ceiling — the apexes."""
    prev = np.roll(values, 1)
    nxt = np.roll(values, -1)
    return (values <= prev) & (values < nxt)


def _apex_distances(
    apex_idx: np.ndarray, ceiling: np.ndarray, n: int, step_m: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Circular distance to the next apex, from the last, and the next apex's speed."""
    dist_to_next = np.zeros(n)
    dist_from_last = np.zeros(n)
    next_speed = np.zeros(n)

    # Tile the apex indices so the searches wrap across the start/finish line.
    tiled = np.concatenate([apex_idx - n, apex_idx, apex_idx + n])
    for i in range(n):
        after = tiled[tiled >= i]
        before = tiled[tiled <= i]
        nxt = int(after[0])
        last = int(before[-1])
        dist_to_next[i] = (nxt - i) * step_m
        dist_from_last[i] = (i - last) * step_m
        next_speed[i] = ceiling[nxt % n]
    return dist_to_next, dist_from_last, next_speed


def _straight_geometry(ceiling: np.ndarray, step_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Length of the flat-out stretch the car is on, and distance to its end.

    "Straight" here means the speed ceiling is not binding much — defined from the
    ceiling itself rather than the corner segmentation, so it needs no extra inputs.
    """
    n = len(ceiling)
    threshold = np.quantile(ceiling, 0.75)
    fast = ceiling >= threshold

    length = np.zeros(n)
    to_end = np.zeros(n)
    visited = np.zeros(n, dtype=bool)
    # Walk each contiguous fast run once, wrapping circularly.
    start = int(np.argmin(fast.astype(int))) if fast.any() else 0
    for offset in range(n):
        i = (start + offset) % n
        if visited[i] or not fast[i]:
            visited[i] = True
            continue
        run = []
        j = i
        while fast[j] and not visited[j]:
            visited[j] = True
            run.append(j)
            j = (j + 1) % n
        total = len(run) * step_m
        for pos, idx in enumerate(run):
            length[idx] = total
            to_end[idx] = total - pos * step_m
    return length, to_end


def dynamic_row(
    speed_mps: float,
    soc_j: float,
    capacity_j: float,
    ceiling_mps: float,
    next_apex_speed_mps: float,
) -> dict[str, float]:
    """Per-step features. Cheap, because this runs inside the simulation loop."""
    kph = speed_mps * 3.6
    return {
        "speed_mps": speed_mps,
        "soc_fraction": soc_j / capacity_j if capacity_j > 0 else 0.0,
        # Signed: negative once the car is inside the tapered band.
        "taper_headroom_kph": DEPLOY_TAPER_FULL_POWER_KPH - kph,
        "taper_fraction": deploy_taper_fraction(kph),
        "speed_vs_ceiling": speed_mps / ceiling_mps if ceiling_mps > 0 else 1.0,
        "speed_vs_next_apex": (
            speed_mps / next_apex_speed_mps if next_apex_speed_mps > 0 else 1.0
        ),
    }


def assemble(
    static: dict[str, np.ndarray], stage: int, dynamic: dict[str, float]
) -> np.ndarray:
    """One feature vector, ordered to match FEATURE_NAMES."""
    row = np.empty(len(FEATURE_NAMES), dtype=float)
    for j, name in enumerate(STATIC_FEATURES):
        row[j] = static[name][stage]
    base = len(STATIC_FEATURES)
    for j, name in enumerate(DYNAMIC_FEATURES):
        row[base + j] = dynamic[name]
    return row


def available_power_w(speed_mps: float) -> float:
    """Regulatory ceiling at this speed — useful for interpreting a prediction."""
    return max_deploy_power_w(speed_mps * 3.6)


def max_power_w() -> float:
    return ERSK_MAX_POWER_W
