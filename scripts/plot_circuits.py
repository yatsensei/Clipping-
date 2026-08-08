"""Phase 1 visual acceptance: plot track maps coloured by segmentation.

Produces a grid of track maps (corners vs straights) and, optionally, a detail figure
for one circuit with its curvature trace. A correct map is judged by eye — the shape must
be recognisable and the corner/straight split must match where an F1 fan would put it.

Run:  uv run python -m scripts.plot_circuits
      uv run python -m scripts.plot_circuits --detail monza
"""

from __future__ import annotations

import argparse
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from data.cache import PROCESSED_DIR

OUT_DIR = PROCESSED_DIR / "figures"

VOID = "#0A0A0B"
PANEL = "#141619"
DEPLOY = "#FF2E17"
BONE = "#F2F0EB"
MUTED = "#5A6068"


def load(circuit_id: str) -> dict:
    return json.loads(
        (PROCESSED_DIR / "circuits" / f"{circuit_id}.json").read_text(encoding="utf-8")
    )


def segment_mask(geo: dict) -> np.ndarray:
    """Boolean per grid point: True where the point lies in a corner segment."""
    n = len(geo["distance_m"])
    step = geo["step_m"]
    mask = np.zeros(n, dtype=bool)
    for s in geo["segments"]:
        if s["kind"] != "corner":
            continue
        i0 = int(round(s["start_m"] / step))
        count = int(round(s["length_m"] / step))
        idx = [(i0 + j) % n for j in range(count)]
        mask[idx] = True
    return mask


def draw_map(ax, geo: dict, title: str) -> None:
    x = np.asarray(geo["x_m"])
    y = np.asarray(geo["y_m"])
    corner = segment_mask(geo)

    # Close the loop for drawing.
    xs, ys = np.append(x, x[0]), np.append(y, y[0])
    cs = np.append(corner, corner[0])

    # Draw as coloured segments so corner/straight transitions are visible.
    for i in range(len(xs) - 1):
        ax.plot(
            xs[i : i + 2],
            ys[i : i + 2],
            color=DEPLOY if cs[i] else MUTED,
            linewidth=3.0 if cs[i] else 2.0,
            solid_capstyle="round",
        )

    d = geo["diagnostics"]
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(
        f"{title}\n{d['n_detected_corners']} corners / {d['n_official_corners']} official"
        f"   longest straight {d['longest_straight_m']:.0f} m",
        color=BONE,
        fontsize=9,
        pad=6,
    )


def grid(circuit_ids: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cols = 4
    rows = int(np.ceil(len(circuit_ids) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 3.6 * rows), facecolor=VOID)
    axes = np.atleast_1d(axes).ravel()

    for ax in axes:
        ax.set_facecolor(VOID)
        ax.axis("off")

    for ax, cid in zip(axes, circuit_ids):
        geo = load(cid)
        draw_map(ax, geo, cid)

    fig.suptitle(
        "2026 calendar — circuit geometry from pooled qualifying GPS\n"
        "red = corner segment, grey = straight",
        color=BONE,
        fontsize=13,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    path = OUT_DIR / "track_maps.png"
    fig.savefig(path, dpi=110, facecolor=VOID)
    plt.close(fig)
    print(f"wrote {path}")


def detail(circuit_id: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    geo = load(circuit_id)
    d = geo["diagnostics"]
    dist = np.asarray(geo["distance_m"])
    kappa = np.asarray(geo["curvature_1_per_m"])
    corner = segment_mask(geo)

    fig = plt.figure(figsize=(15, 6.5), facecolor=VOID)
    gs = fig.add_gridspec(2, 2, width_ratios=[1, 1.5], height_ratios=[1, 1])
    ax_map = fig.add_subplot(gs[:, 0])
    ax_k = fig.add_subplot(gs[0, 1])
    ax_z = fig.add_subplot(gs[1, 1])
    for ax in (ax_map, ax_k, ax_z):
        ax.set_facecolor(PANEL)

    ax_map.set_facecolor(VOID)
    draw_map(ax_map, geo, circuit_id)

    ax_k.plot(dist, kappa, color=BONE, linewidth=1.0)
    ax_k.fill_between(dist, 0, kappa, where=corner, color=DEPLOY, alpha=0.45,
                      step="mid", label="corner segment")
    for c in geo["official_corners"]:
        ax_k.axvline(c["distance_m"], color="#3FE0D0", alpha=0.5, linewidth=0.8)
    ax_k.set_ylabel("curvature (1/m)", color=BONE, fontsize=9)
    ax_k.legend(loc="upper right", fontsize=8, facecolor=PANEL, labelcolor=BONE)
    ax_k.set_title("cyan lines = official corner positions (FastF1 circuit_info)",
                   color=BONE, fontsize=9)

    ax_z.plot(dist, np.asarray(geo["z_m"]), color="#3FE0D0", linewidth=1.2)
    ax_z.set_ylabel("elevation (m)", color=BONE, fontsize=9)
    ax_z.set_xlabel("lap distance (m)", color=BONE, fontsize=9)

    for ax in (ax_k, ax_z):
        ax.tick_params(colors=BONE, labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(MUTED)
        ax.grid(alpha=0.15, color=MUTED)

    fig.suptitle(
        f"{circuit_id} — {d['session']} | ref {d['reference_driver']} "
        f"{d['reference_lap_time_s']:.3f}s | {d['laps_pooled']} laps pooled, "
        f"{d['samples']:,} GPS samples | path error {d['path_vs_distance_error_pct']:.2f}%",
        color=BONE,
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    path = OUT_DIR / f"detail_{circuit_id}.png"
    fig.savefig(path, dpi=110, facecolor=VOID)
    plt.close(fig)
    print(f"wrote {path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail", default="")
    args = ap.parse_args()

    index = json.loads((PROCESSED_DIR / "circuits_index.json").read_text(encoding="utf-8"))
    ids = [c["circuit_id"] for c in index["circuits"]]
    if not ids:
        print("no circuits built")
        return 1

    if args.detail:
        detail(args.detail)
    else:
        grid(ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
