"""Circuit geometry: centreline extraction, curvature, and straight/corner segmentation.

The sampling problem
--------------------
F1 position telemetry arrives at roughly 3.8 Hz. On a single lap that is ~20 m between
samples at 300 km/h, which cannot resolve a corner of 10-50 m radius — Monaco's hairpin
would vanish entirely. So the centreline is not built from one lap: position samples from
every clean lap in the session are pooled, which densifies the sampling by an order of
magnitude and rejects the occasional lap where a driver ran wide.

The alignment problem
---------------------
Pooling requires knowing where along the lap each sample belongs. The obvious index,
RelativeDistance, is derived from Distance, which FastF1 integrates from speed — and that
integration drifts differently on every lap. At the Red Bull Ring laps disagreed by ~80 m,
so adjacent 5 m bins alternated between two clusters and the traced path came out 64%
too long. Samples are therefore aligned GEOMETRICALLY, by projection onto a seed path
(see build_centreline), which removes the dependence on speed integration entirely.

What comes out is a representative racing line rather than a surveyed track centreline.
That is the correct object here: the model simulates a car driving the line.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline
from scipy.signal import find_peaks, savgol_filter
from scipy.spatial import cKDTree

# FastF1 position data is in units of 1/10 metre. Validated per circuit by comparing the
# resulting path length against known track lengths: traced lines come out ~1% short,
# which is the expected sign, since a racing line cuts inside the official centreline.
POS_UNITS_PER_M = 10.0

DEFAULT_STEP_M = 5.0
DEFAULT_SMOOTH_M = 45.0

# Segmentation thresholds, in radius of curvature. Hysteresis: a point is a corner above
# the corner threshold, a straight below the straight threshold, and holds its previous
# state in between, which stops a segment flickering along a gentle transition.
CORNER_RADIUS_M = 250.0
STRAIGHT_RADIUS_M = 500.0
MIN_CORNER_M = 20.0
MIN_STRAIGHT_M = 60.0

# On a street circuit the road between two corners may never straighten past
# STRAIGHT_RADIUS_M, so hysteresis alone chains half a lap into one "corner" — at Monaco
# that merged T2 through T9 into a single 1,345 m segment. Compound runs are therefore
# split at their interior curvature minima, which is also the physically meaningful
# boundary: each apex is a separate point the car accelerates away from.
MIN_APEX_SEPARATION_M = 40.0
# Apexes are found by topographic PROMINENCE, not raw height. A long corner such as
# Parabolica is one broad curvature hump with wobble along its top; ranking local maxima
# by height alone treats that wobble as six separate apexes. Prominence asks how far the
# curvature must fall before rising again, which is exactly the distinction between a
# bump on a plateau and a genuinely separate corner.
# Chosen by sweep against FastF1's official corner counts across all 21 circuits
# (scripts/tune_segmentation.py --sweep): mean absolute error 2.29 corners, best of 36
# combinations. Detection still runs slightly under the official count because official
# numbering counts each corner inside a complex separately — Monza's Ascari is three
# numbered corners but one acceleration zone, which is the unit that matters here.
APEX_MIN_HEIGHT_FRAC = 0.25
APEX_PROMINENCE_FRAC = 0.25
# A dip between apexes only splits if the road opens out at least this much relative to
# the flanking apexes.
SPLIT_RELEASE_FRAC = 0.70


@dataclass(frozen=True)
class Segment:
    kind: str  # "corner" | "straight"
    start_m: float
    end_m: float
    length_m: float
    min_radius_m: float
    mean_radius_m: float
    apex_m: float | None  # distance of peak curvature, corners only

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CircuitGeometry:
    circuit_id: str
    lap_distance_m: float
    step_m: float
    distance_m: np.ndarray
    x_m: np.ndarray
    y_m: np.ndarray
    z_m: np.ndarray
    curvature_1_per_m: np.ndarray
    radius_m: np.ndarray
    gradient: np.ndarray
    segments: list[Segment]
    official_corners: list[dict]
    diagnostics: dict

    def to_json_dict(self) -> dict:
        return {
            "circuit_id": self.circuit_id,
            "lap_distance_m": round(self.lap_distance_m, 2),
            "step_m": self.step_m,
            "n_points": int(len(self.distance_m)),
            "distance_m": np.round(self.distance_m, 2).tolist(),
            "x_m": np.round(self.x_m, 2).tolist(),
            "y_m": np.round(self.y_m, 2).tolist(),
            "z_m": np.round(self.z_m, 2).tolist(),
            "curvature_1_per_m": np.round(self.curvature_1_per_m, 6).tolist(),
            "gradient": np.round(self.gradient, 5).tolist(),
            "segments": [s.to_dict() for s in self.segments],
            "official_corners": self.official_corners,
            "diagnostics": self.diagnostics,
        }


# A lap is only pooled if its own GPS trace agrees with its own Distance channel. FastF1
# reports "Position data is incomplete" for many drivers; those laps carry stretches of
# dropped or frozen coordinates that survive a median and corrupt the centreline.
MAX_LAP_PATH_ERROR = 0.05
# A sample projecting further than this from the seed path is not on that stretch of
# track; assigning it to the nearest grid point would bend the centreline toward it.
MAX_PROJECTION_M = 30.0


def pool_position_samples(laps: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Gather (relative lap position, x, y, z) from every supplied lap that passes QC.

    RelativeDistance is used to align laps: drivers cover slightly different absolute
    distances, but every lap starts and ends at the timing line, so normalised position
    is the common index.
    """
    frames: list[pd.DataFrame] = []
    used = failed = rejected = 0
    for _, lap in laps.iterrows():
        try:
            tel = lap.get_telemetry().add_distance()
        except Exception:  # noqa: BLE001 - a bad lap is skipped, never fabricated
            failed += 1
            continue
        need = {"RelativeDistance", "X", "Y", "Z", "Distance"}
        if not need.issubset(tel.columns) or len(tel) < 20:
            failed += 1
            continue

        sub = tel[["RelativeDistance", "X", "Y", "Z", "Distance", "Status"]].copy() \
            if "Status" in tel.columns else tel[
                ["RelativeDistance", "X", "Y", "Z", "Distance"]].copy()
        if "Status" in sub.columns:
            sub = sub[sub["Status"].astype(str) == "OnTrack"]
        sub = sub.dropna(subset=["RelativeDistance", "X", "Y", "Z", "Distance"])
        # Dropped position packets show up as an exact origin fix.
        sub = sub[~((sub["X"] == 0) & (sub["Y"] == 0))]
        if len(sub) < 20:
            failed += 1
            continue

        if not _lap_self_consistent(sub):
            rejected += 1
            continue

        frames.append(sub[["RelativeDistance", "X", "Y", "Z"]])
        used += 1

    if not frames:
        raise ValueError(
            "no laps passed position-data quality checks "
            f"({failed} unusable, {rejected} failed the path-length check)"
        )

    pooled = pd.concat(frames, ignore_index=True)
    pooled = pooled[(pooled["RelativeDistance"] >= 0) & (pooled["RelativeDistance"] <= 1)]
    return pooled, {
        "laps_pooled": used,
        "laps_failed": failed,
        "laps_rejected_qc": rejected,
        "samples": len(pooled),
    }


def _lap_self_consistent(sub: pd.DataFrame) -> bool:
    """True if the lap's GPS path length matches its own integrated Distance."""
    travelled = float(sub["Distance"].iloc[-1] - sub["Distance"].iloc[0])
    if travelled < 500:
        return False
    x = sub["X"].to_numpy() / POS_UNITS_PER_M
    y = sub["Y"].to_numpy() / POS_UNITS_PER_M
    gps = float(np.sum(np.hypot(np.diff(x), np.diff(y))))
    return abs(gps - travelled) / travelled <= MAX_LAP_PATH_ERROR


def trim_loop_overlap(
    x: np.ndarray, y: np.ndarray, z: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Drop trailing points that have already driven past the start of the loop.

    A lap's telemetry often runs a little beyond the timing line, so the last samples sit
    *ahead* of the first one. Closing the loop then folds that overlap back on itself: the
    resampled path retraces the same stretch in reverse, the smoothed tangent collapses to
    near zero, and curvature explodes — at Shanghai this produced a 0.04 m radius on the
    main straight.

    Detected geometrically: if the closing vector (last -> first) points against the
    direction of travel at the end of the path, the last point overshot.
    """
    xs, ys, zs = list(map(float, x)), list(map(float, y)), list(map(float, z))
    removed = 0
    max_trim = max(1, len(xs) // 10)
    while len(xs) > 4 and removed < max_trim:
        dex, dey = xs[-1] - xs[-2], ys[-1] - ys[-2]
        cx, cy = xs[0] - xs[-1], ys[0] - ys[-1]
        if dex * cx + dey * cy >= 0.0:
            break
        xs.pop(), ys.pop(), zs.pop()
        removed += 1
    return np.array(xs), np.array(ys), np.array(zs), removed


def count_folds(x: np.ndarray, y: np.ndarray) -> int:
    """Points where the path reverses on itself. A clean closed circuit has none."""
    dx = np.diff(np.append(x, x[0]))
    dy = np.diff(np.append(y, y[0]))
    dot = dx * np.roll(dx, -1) + dy * np.roll(dy, -1)
    return int((dot < 0).sum())


def resample_closed_path(
    x: np.ndarray, y: np.ndarray, z: np.ndarray, step_m: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Resample a closed loop onto a uniform arc-length grid via a periodic spline."""
    # Close the loop, then parametrise by cumulative chord length.
    xs = np.append(x, x[0])
    ys = np.append(y, y[0])
    zs = np.append(z, z[0])
    seg = np.hypot(np.diff(xs), np.diff(ys))
    u = np.concatenate([[0.0], np.cumsum(seg)])

    # CubicSpline requires a strictly increasing parameter.
    keep = np.concatenate([[True], np.diff(u) > 1e-6])
    u, xs, ys, zs = u[keep], xs[keep], ys[keep], zs[keep]
    total = float(u[-1])

    n = max(16, int(round(total / step_m)))
    grid = np.linspace(0.0, total, n, endpoint=False)
    spline = CubicSpline(u, np.c_[xs, ys, zs], bc_type="periodic")
    out = spline(grid)
    return out[:, 0], out[:, 1], out[:, 2]


def build_centreline(
    pooled: pd.DataFrame,
    seed_xyz: tuple[np.ndarray, np.ndarray, np.ndarray],
    step_m: float = DEFAULT_STEP_M,
    iterations: int = 2,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    """Reduce pooled samples onto a uniform distance grid, aligned SPATIALLY.

    Samples are not binned by RelativeDistance. That value derives from Distance, which
    FastF1 integrates from speed, and the integration drifts differently on each lap — at
    the Red Bull Ring laps disagreed by ~80 m, which made adjacent bins alternate between
    two clusters and inflated the traced path by 64%.

    Instead each sample is assigned to the nearest point on a seed path (the reference
    lap), so alignment comes from geometry and no longer depends on speed integration.
    The median path is then re-seeded and the projection repeated.
    """
    xy = np.c_[
        pooled["X"].to_numpy() / POS_UNITS_PER_M,
        pooled["Y"].to_numpy() / POS_UNITS_PER_M,
    ]
    zvals = pooled["Z"].to_numpy() / POS_UNITS_PER_M

    sx, sy, sz = seed_xyz
    sx, sy, sz, trimmed = trim_loop_overlap(sx, sy, sz)
    diag: dict = {"seed_points_trimmed": trimmed}

    for it in range(iterations):
        px, py, pz = resample_closed_path(sx, sy, sz, step_m)
        n = len(px)

        tree = cKDTree(np.c_[px, py])
        dist, idx = tree.query(xy, k=1)

        # A sample that lands far from the path belongs to a different part of the
        # circuit (or is corrupt); assigning it would bend the centreline.
        ok = dist <= MAX_PROJECTION_M
        rejected = int((~ok).sum())

        df = pd.DataFrame(
            {"bin": idx[ok], "X": xy[ok, 0], "Y": xy[ok, 1], "Z": zvals[ok]}
        )
        grouped = df.groupby("bin")[["X", "Y", "Z"]].median()

        xyz = np.full((n, 3), np.nan)
        xyz[grouped.index.to_numpy()] = grouped.to_numpy()
        empty = int(np.isnan(xyz[:, 0]).sum())
        xyz = _fill_circular(xyz)

        sx, sy, sz = xyz[:, 0], xyz[:, 1], xyz[:, 2]
        diag.update(
            {
                "bins": n,
                "empty_bins": empty,
                "samples_projected": int(ok.sum()),
                "samples_rejected_far": rejected,
                "alignment_iterations": it + 1,
            }
        )

    # Final pass onto an exactly uniform arc-length grid.
    x, y, z = resample_closed_path(sx, sy, sz, step_m)
    seg = np.hypot(np.diff(np.append(x, x[0])), np.diff(np.append(y, y[0])))
    distance = np.concatenate([[0.0], np.cumsum(seg)[:-1]])
    diag["folds"] = count_folds(x, y)
    return distance, x, y, z, diag


def _fill_circular(xyz: np.ndarray) -> np.ndarray:
    """Interpolate empty bins, wrapping across the start/finish line."""
    n = len(xyz)
    for c in range(xyz.shape[1]):
        col = xyz[:, c]
        bad = np.isnan(col)
        if bad.all():
            raise ValueError("centreline is entirely empty")
        if bad.any():
            good = np.flatnonzero(~bad)
            src = np.concatenate([good - n, good, good + n])
            val = np.tile(col[good], 3)
            col[bad] = np.interp(np.flatnonzero(bad), src, val)
            xyz[:, c] = col
    return xyz


def _odd_window(span_m: float, step_m: float, n_points: int) -> int:
    win = int(round(span_m / step_m))
    win = max(5, win | 1)
    return min(win, (n_points - 1) | 1)


def compute_curvature(
    x: np.ndarray,
    y: np.ndarray,
    step_m: float,
    smooth_m: float = DEFAULT_SMOOTH_M,
    polyorder: int = 3,
) -> np.ndarray:
    """Signed curvature on a uniform arc-length grid, in 1/m.

    Savitzky-Golay differentiation with circular wrap, so the start/finish line is not a
    discontinuity. Sign carries corner direction, which is useful for rendering.
    """
    win = _odd_window(smooth_m, step_m, len(x))
    poly = min(polyorder, win - 1)
    kw = dict(window_length=win, polyorder=poly, delta=step_m, mode="wrap")
    dx = savgol_filter(x, deriv=1, **kw)
    dy = savgol_filter(y, deriv=1, **kw)
    ddx = savgol_filter(x, deriv=2, **kw)
    ddy = savgol_filter(y, deriv=2, **kw)
    denom = (dx * dx + dy * dy) ** 1.5
    denom = np.where(denom < 1e-9, 1e-9, denom)
    return (dx * ddy - dy * ddx) / denom


def compute_gradient(z: np.ndarray, step_m: float, smooth_m: float = 100.0) -> np.ndarray:
    """Track gradient (rise over run) along the lap."""
    win = _odd_window(smooth_m, step_m, len(z))
    poly = min(2, win - 1)
    return savgol_filter(z, window_length=win, polyorder=poly, deriv=1,
                         delta=step_m, mode="wrap")


def segment_lap(
    curvature: np.ndarray,
    step_m: float,
    corner_radius_m: float = CORNER_RADIUS_M,
    straight_radius_m: float = STRAIGHT_RADIUS_M,
    min_corner_m: float = MIN_CORNER_M,
    min_straight_m: float = MIN_STRAIGHT_M,
) -> list[Segment]:
    """Split the lap into straights and corners by curvature, with hysteresis."""
    k = np.abs(curvature)
    k_corner = 1.0 / corner_radius_m
    k_straight = 1.0 / straight_radius_m
    n = len(k)

    # Seed the state from the least-curved point so the first classification is unambiguous.
    start = int(np.argmin(k))
    labels = np.empty(n, dtype=object)
    state = "straight"
    for step in range(n):
        i = (start + step) % n
        if k[i] > k_corner:
            state = "corner"
        elif k[i] < k_straight:
            state = "straight"
        labels[i] = state

    runs = _runs(labels, n, start)
    runs = _absorb_short(runs, step_m, min_corner_m, min_straight_m, n)
    runs = _split_compound_corners(runs, k, step_m, n)

    segments: list[Segment] = []
    for kind, i0, length in runs:
        idx = [(i0 + j) % n for j in range(length)]
        kk = k[idx]
        with np.errstate(divide="ignore"):
            radii = np.where(kk > 1e-9, 1.0 / kk, np.inf)
        apex = None
        if kind == "corner":
            apex = float(((i0 + int(np.argmax(kk))) % n) * step_m)
        segments.append(
            Segment(
                kind=kind,
                start_m=float(i0 * step_m),
                end_m=float(((i0 + length) % n) * step_m),
                length_m=float(length * step_m),
                min_radius_m=float(np.min(radii)),
                mean_radius_m=float(np.mean(radii[np.isfinite(radii)]))
                if np.isfinite(radii).any()
                else float("inf"),
                apex_m=apex,
            )
        )
    return sorted(segments, key=lambda s: s.start_m)


def _runs(labels: np.ndarray, n: int, start: int) -> list[list]:
    """Contiguous same-label runs, walking circularly from `start`."""
    runs: list[list] = []
    for step in range(n):
        i = (start + step) % n
        if runs and runs[-1][0] == labels[i]:
            runs[-1][2] += 1
        else:
            runs.append([labels[i], i, 1])
    # Merge the wrap-around pair if they share a label.
    if len(runs) > 1 and runs[0][0] == runs[-1][0]:
        runs[0][1] = runs[-1][1]
        runs[0][2] += runs[-1][2]
        runs.pop()
    return runs


def _absorb_short(
    runs: list[list], step_m: float, min_corner_m: float, min_straight_m: float, n: int
) -> list[list]:
    """Repeatedly dissolve runs below their minimum length into their neighbours."""
    minimum = {"corner": min_corner_m, "straight": min_straight_m}
    changed = True
    while changed and len(runs) > 1:
        changed = False
        for i, (kind, _, length) in enumerate(runs):
            if length * step_m >= minimum[kind]:
                continue
            prev_i, next_i = (i - 1) % len(runs), (i + 1) % len(runs)
            if prev_i == i or next_i == i:
                break
            # Give the run to whichever neighbour is longer.
            target = prev_i if runs[prev_i][2] >= runs[next_i][2] else next_i
            runs[i][0] = runs[target][0]
            merged: list[list] = []
            for r in runs:
                if merged and merged[-1][0] == r[0]:
                    merged[-1][2] += r[2]
                else:
                    merged.append(list(r))
            if len(merged) > 1 and merged[0][0] == merged[-1][0]:
                merged[0][1] = merged[-1][1]
                merged[0][2] += merged[-1][2]
                merged.pop()
            runs = merged
            changed = True
            break
    return runs


def _split_compound_corners(
    runs: list[list], k: np.ndarray, step_m: float, n: int
) -> list[list]:
    """Split corner runs containing several distinct apexes into one run per apex.

    Splits at the curvature minimum between consecutive apexes, which is where the road
    opens out and the driver can get back on power — the boundary that matters for
    deployment.
    """
    min_sep = max(1, int(round(MIN_APEX_SEPARATION_M / step_m)))
    out: list[list] = []

    for kind, i0, length in runs:
        if kind != "corner" or length < 2 * min_sep:
            out.append([kind, i0, length])
            continue

        idx = [(i0 + j) % n for j in range(length)]
        kk = k[idx]
        peaks = _local_peaks(kk, min_sep)
        if len(peaks) < 2:
            out.append([kind, i0, length])
            continue

        cuts = []
        for a, b in zip(peaks, peaks[1:]):
            valley = a + int(np.argmin(kk[a : b + 1]))
            # Require a real release between the two apexes.
            if kk[valley] <= SPLIT_RELEASE_FRAC * min(kk[a], kk[b]):
                cuts.append(valley)

        if not cuts:
            out.append([kind, i0, length])
            continue

        bounds = [0, *cuts, length]
        for s, e in zip(bounds, bounds[1:]):
            if e - s > 0:
                out.append([kind, (i0 + s) % n, e - s])

    return out


def _local_peaks(values: np.ndarray, min_sep: int) -> list[int]:
    """Apex indices within a corner run, by prominence."""
    peak = float(values.max())
    if peak <= 0:
        return []
    found, _ = find_peaks(
        values,
        distance=min_sep,
        height=APEX_MIN_HEIGHT_FRAC * peak,
        prominence=APEX_PROMINENCE_FRAC * peak,
    )
    return sorted(int(i) for i in found)


def path_length_m(x: np.ndarray, y: np.ndarray) -> float:
    dx = np.diff(np.append(x, x[0]))
    dy = np.diff(np.append(y, y[0]))
    return float(np.sum(np.hypot(dx, dy)))
