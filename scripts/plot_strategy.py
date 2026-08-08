"""Phase 3 visual acceptance: is the optimal deployment profile physically sensible?

Plots speed, deployment/harvest and state of charge against lap distance for the optimal
and baseline strategies. What to look for, per the brief:

  - energy going in on corner exits and the lower-speed part of straights
  - deployment backing off as the car approaches the 290 km/h taper threshold
  - the greedy strategy running the store flat and then clipping
  - the optimal state of charge returning to where it started

Run:  uv run python -m scripts.plot_strategy monza [monte-carlo ...]
"""

from __future__ import annotations

import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from config.regulations import DEPLOY_TAPER_FULL_POWER_KPH
from data.cache import PROCESSED_DIR

FIG_DIR = PROCESSED_DIR / "figures"
VOID, PANEL, DEPLOY, HARVEST, CLIP, BONE, MUTED = (
    "#0A0A0B", "#141619", "#FF2E17", "#3FE0D0", "#8A8F98", "#F2F0EB", "#5A6068",
)


def plot(circuit_id: str) -> None:
    path = PROCESSED_DIR / "strategies" / f"{circuit_id}.json"
    if not path.exists():
        print(f"{circuit_id}: not solved ({path})")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    d = np.asarray(data["distance_m"]) / 1000.0
    opt = data["strategies"]["optimal"]
    uni = data["strategies"]["uniform"]
    gre = data["strategies"]["greedy"]

    fig, axes = plt.subplots(4, 1, figsize=(15, 11), sharex=True, facecolor=VOID,
                             height_ratios=[2.0, 1.6, 1.4, 1.4])
    for ax in axes:
        ax.set_facecolor(PANEL)
        ax.tick_params(colors=BONE, labelsize=8)
        for s in ax.spines.values():
            s.set_color(MUTED)
        ax.grid(alpha=0.15, color=MUTED)

    # 1. Speed, with the taper threshold marked.
    ax = axes[0]
    ax.plot(d, uni["speed_kph"], color=MUTED, lw=1.1, label="uniform")
    ax.plot(d, gre["speed_kph"], color=CLIP, lw=1.1, ls="--", label="greedy")
    ax.plot(d, opt["speed_kph"], color=BONE, lw=1.5, label="optimal")
    ax.axhline(DEPLOY_TAPER_FULL_POWER_KPH, color=DEPLOY, lw=1.0, ls=":",
               label=f"{DEPLOY_TAPER_FULL_POWER_KPH:.0f} km/h — taper begins")
    ax.set_ylabel("speed (km/h)", color=BONE, fontsize=9)
    ax.legend(fontsize=8, facecolor=PANEL, labelcolor=BONE, ncol=4, loc="lower right")

    # 2. Optimal deployment and harvest.
    ax = axes[1]
    dep = np.asarray(opt["deploy_kw"])
    har = np.asarray(opt["harvest_kw"])
    ax.fill_between(d, 0, dep, color=DEPLOY, alpha=0.85, step="mid", label="deploy")
    ax.fill_between(d, 0, -har, color=HARVEST, alpha=0.75, step="mid", label="harvest")
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.set_ylabel("optimal (kW)", color=BONE, fontsize=9)
    ax.legend(fontsize=8, facecolor=PANEL, labelcolor=BONE, loc="upper right")

    # 3. State of charge for all three.
    ax = axes[2]
    ax.plot(d, uni["soc_mj"], color=MUTED, lw=1.1, label="uniform")
    ax.plot(d, gre["soc_mj"], color=CLIP, lw=1.2, ls="--", label="greedy")
    ax.plot(d, opt["soc_mj"], color=BONE, lw=1.5, label="optimal")
    # The DP enforces periodicity at the lap's SLOWEST point, which is its stage 0, not
    # the timing line. Marking soc_start here would point at the wrong place on the x
    # axis, so the reference drawn is the optimal trace's own value at the plotted start.
    ax.axhline(opt["soc_mj"][0], color=HARVEST, lw=0.9, ls=":",
               label=f"optimal SoC at lap start ({opt['soc_mj'][0]:.2f} MJ)")
    ax.set_ylabel("SoC (MJ)", color=BONE, fontsize=9)
    ax.legend(fontsize=8, facecolor=PANEL, labelcolor=BONE, ncol=4, loc="lower right")

    # 4. Where each strategy is clipping.
    ax = axes[3]
    for offset, (name, series, colour) in enumerate(
        [("optimal", opt, BONE), ("uniform", uni, MUTED), ("greedy", gre, CLIP)]
    ):
        flag = np.asarray(series["clipping"], dtype=bool)
        ax.fill_between(d, offset, offset + 0.85, where=flag, color=colour, alpha=0.9,
                        step="mid")
        ax.text(d[0], offset + 0.3, f" {name}", color=colour, fontsize=8, va="center")
    ax.set_ylim(-0.2, 3.1)
    ax.set_yticks([])
    ax.set_ylabel("clipping", color=BONE, fontsize=9)
    ax.set_xlabel("lap distance (km)", color=BONE, fontsize=9)

    fig.suptitle(
        f"{circuit_id} — optimal deployment strategy\n"
        f"optimal {data['optimal_lap_s']:.3f}s vs uniform {data['uniform_lap_s']:.3f}s "
        f"= {data['gain_vs_uniform_s']:+.3f}s  |  greedy {data['greedy_lap_s']:.3f}s but "
        f"{data['greedy_energy_debt_mj']:.2f} MJ in debt (not repeatable)  |  "
        f"deployed {data['optimal_deployed_mj']:.2f} MJ, "
        f"harvested {data['optimal_harvested_mj']:.2f} MJ\n"
        f"periodicity is enforced at the lap's slowest point "
        f"(SoC {data['soc_start_mj']:.2f} MJ there), not at the timing line",
        color=BONE, fontsize=10,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / f"strategy_{circuit_id}.png"
    fig.savefig(out, dpi=110, facecolor=VOID)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    for cid in sys.argv[1:] or ["monza"]:
        plot(cid)
