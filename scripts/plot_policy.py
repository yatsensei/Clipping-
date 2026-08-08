"""Phase 4 figure: how much of the optimiser's gain does the learned policy keep?

Two panels:
  left    per-circuit gain retained, held out, one bar group per model
  right   feature importance averaged over the folds

Run:  uv run python -m scripts.plot_policy
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from data.cache import PROCESSED_DIR
from ml.features import FEATURE_NAMES

FIG_DIR = PROCESSED_DIR / "figures"
VOID, PANEL, DEPLOY, HARVEST, CLIP, BONE, MUTED = (
    "#0A0A0B", "#141619", "#FF2E17", "#3FE0D0", "#8A8F98", "#F2F0EB", "#5A6068",
)
# Keys must match the Policy names used in ml/policy.py, not the CLI shorthand.
COLOURS = {"gbm": DEPLOY, "gbm_reg": "#FF8A6B", "linear": HARVEST,
           "always-deploy": CLIP}


def main() -> int:
    results = pd.read_csv(PROCESSED_DIR / "policy_evaluation.csv")
    fig = plt.figure(figsize=(16, 8), facecolor=VOID)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.7, 1.0])
    ax = fig.add_subplot(gs[0, 0])
    ax_imp = fig.add_subplot(gs[0, 1])
    for a in (ax, ax_imp):
        a.set_facecolor(PANEL)
        a.tick_params(colors=BONE, labelsize=8)
        for s in a.spines.values():
            s.set_color(MUTED)

    models = [m for m in ("gbm", "gbm_reg", "linear", "always-deploy")
              if m in set(results["model"])]
    order = (
        results[results["model"] == models[0]]
        .sort_values("gain_retained_pct", ascending=False)["held_out"].tolist()
    )
    x = np.arange(len(order))
    width = 0.8 / max(len(models), 1)

    for k, model in enumerate(models):
        sub = results[results["model"] == model].set_index("held_out").reindex(order)
        colour = COLOURS.get(model, BONE)
        bars = ax.bar(x + k * width, sub["gain_retained_pct"], width,
                      label=model, color=colour, alpha=0.9)
        # Hatch the laps that ended with less charge than they started: those spent
        # energy they never repaid, so their time is not comparable to the DP's.
        for bar, ok in zip(bars, sub["periodic"].fillna(False)):
            if not ok:
                bar.set_hatch("///")
                bar.set_edgecolor(VOID)
                bar.set_alpha(0.55)

    ax.bar(np.nan, np.nan, color=MUTED, hatch="///", edgecolor=VOID, alpha=0.55,
           label="hatched = not repeatable (spent energy it never repaid)")
    ax.axhline(100, color=BONE, lw=1.0, ls=":", label="the optimiser (100%)")
    ax.axhline(0, color=MUTED, lw=1.0, label="uniform deployment (0%)")
    ax.set_xticks(x + width * (len(models) - 1) / 2)
    ax.set_xticklabels(order, rotation=60, ha="right", color=BONE, fontsize=8)
    ax.set_ylabel("% of the optimiser's lap-time gain retained", color=BONE, fontsize=9)
    ax.set_title("Leave-one-circuit-out: closed-loop through the same physics",
                 color=BONE, fontsize=10)
    ax.legend(fontsize=8, facecolor=PANEL, labelcolor=BONE, loc="lower left")
    ax.grid(alpha=0.15, color=MUTED, axis="y")

    imp_path = PROCESSED_DIR / "feature_importance.csv"
    if imp_path.exists():
        imp = pd.read_csv(imp_path)
        gbm = imp[imp["model"] == "gbm"] if "gbm" in set(imp["model"]) else imp
        cols = [c for c in FEATURE_NAMES if c in gbm.columns]
        mean_imp = gbm[cols].mean()
        mean_imp = (mean_imp / mean_imp.sum() * 100).sort_values().tail(14)
        ax_imp.barh(mean_imp.index, mean_imp.to_numpy(), color=DEPLOY, alpha=0.9)
        ax_imp.set_xlabel("mean importance (%) across folds", color=BONE, fontsize=9)
        ax_imp.set_title("What the policy actually uses", color=BONE, fontsize=10)
        ax_imp.grid(alpha=0.15, color=MUTED, axis="x")

    strict = results[results["periodic"]]
    parts = []
    for model in models:
        s = strict[strict["model"] == model]["gain_retained_pct"]
        parts.append(f"{model}: {s.mean():.0f}% (n={len(s)})" if len(s)
                     else f"{model}: no repeatable lap")
    fig.suptitle(
        "Phase 4 — learned policy vs the DP optimiser, leave-one-circuit-out\n"
        "mean gain retained on REPEATABLE laps only:  " + "  |  ".join(parts),
        color=BONE, fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / "policy_evaluation.png"
    fig.savefig(out, dpi=110, facecolor=VOID)
    plt.close(fig)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
