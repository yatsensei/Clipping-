"""Geometry tests against cases with a known analytic answer."""

from __future__ import annotations

import numpy as np
import pytest

from data.geometry import (
    compute_curvature,
    path_length_m,
    resample_closed_path,
    segment_lap,
)


def circle(radius: float, n: int = 720) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return radius * np.cos(t), radius * np.sin(t), np.zeros(n)


def test_curvature_of_a_circle_is_one_over_radius():
    for radius in (50.0, 200.0, 800.0):
        x, y, z = circle(radius)
        step = 2 * np.pi * radius / len(x)
        k = compute_curvature(x, y, step)
        assert np.allclose(np.abs(k), 1.0 / radius, rtol=0.02), radius


def test_curvature_of_a_straight_line_is_zero():
    x = np.linspace(0, 1000, 201)
    y = np.zeros_like(x)
    k = compute_curvature(x, y, step_m=5.0)
    assert np.max(np.abs(k)) < 1e-6


def test_resample_gives_uniform_spacing_and_closes_the_loop():
    x, y, z = circle(300.0, n=97)  # deliberately irregular sample count
    rx, ry, rz = resample_closed_path(x, y, z, step_m=5.0)
    seg = np.hypot(np.diff(np.append(rx, rx[0])), np.diff(np.append(ry, ry[0])))
    assert np.std(seg) < 0.05 * np.mean(seg)
    # Circumference recovered to within a fraction of a percent.
    assert path_length_m(rx, ry) == pytest.approx(2 * np.pi * 300.0, rel=0.01)


def test_oval_segments_into_two_corners_and_two_straights():
    """A stadium oval: two 500 m straights joined by two 100 m-radius hairpins."""
    step = 5.0
    straight = np.arange(0, 500, step)
    theta = np.linspace(-np.pi / 2, np.pi / 2, int(np.pi * 100 / step), endpoint=False)

    xs = [straight, 500 + 100 * np.cos(theta), 500 - straight, 100 * np.cos(theta + np.pi)]
    ys = [
        np.zeros_like(straight),
        100 + 100 * np.sin(theta),
        np.full_like(straight, 200.0),
        100 + 100 * np.sin(theta + np.pi),
    ]
    x = np.concatenate(xs)
    y = np.concatenate(ys)

    rx, ry, _ = resample_closed_path(x, y, np.zeros_like(x), step)
    k = compute_curvature(rx, ry, step)
    segments = segment_lap(k, step)

    corners = [s for s in segments if s.kind == "corner"]
    straights = [s for s in segments if s.kind == "straight"]
    assert len(corners) == 2, [(s.kind, s.length_m) for s in segments]
    assert len(straights) == 2
    for c in corners:
        assert c.min_radius_m == pytest.approx(100.0, rel=0.15)
    for s in straights:
        assert s.length_m == pytest.approx(500.0, abs=120.0)


def test_segments_tile_the_whole_lap_without_gaps():
    x, y, z = circle(400.0, n=400)
    rx, ry, _ = resample_closed_path(x, y, z, step_m=5.0)
    k = compute_curvature(rx, ry, 5.0)
    segments = segment_lap(k, 5.0)
    total = sum(s.length_m for s in segments)
    assert total == pytest.approx(len(rx) * 5.0, rel=1e-9)
