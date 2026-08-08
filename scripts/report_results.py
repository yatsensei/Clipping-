"""Generate the README's results tables from the artifacts.

The README is required to carry the measured numbers, and numbers pasted by hand go
stale the moment anything is re-run. This regenerates the block between the RESULTS
markers directly from data/processed, so the document can always be brought back into
agreement with the artifacts by running one command.

Run:  uv run python -m scripts.report_results          # rewrite README.md in place
      uv run python -m scripts.report_results --print  # just show the block
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from data.cache import PROCESSED_DIR

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
START = "<!-- RESULTS:START -->"
END = "<!-- RESULTS:END -->"


def strategy_table() -> str:
    df = pd.read_csv(PROCESSED_DIR / "strategy_comparison.csv").sort_values(
        "gain_vs_uniform_s", ascending=False
    )
    lines = [
        "| Circuit | Uniform | Optimal | **Gain** | Greedy | Greedy debt | Optimal clipping | Greedy clipping |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in df.iterrows():
        lines.append(
            f"| {r['circuit_id']} | {r['uniform_lap_s']:.3f} | {r['optimal_lap_s']:.3f} "
            f"| **+{r['gain_vs_uniform_s']:.3f}** | {r['greedy_lap_s']:.3f} "
            f"| −{r['greedy_energy_debt_mj']:.2f} MJ | {r['optimal_clip_pct']:.0f}% "
            f"| {r['greedy_clip_pct']:.0f}% |"
        )
    lines.append(
        f"| **mean** | | | **+{df['gain_vs_uniform_s'].mean():.3f}** | | "
        f"−{df['greedy_energy_debt_mj'].mean():.2f} MJ | "
        f"{df['optimal_clip_pct'].mean():.0f}% | {df['greedy_clip_pct'].mean():.0f}% |"
    )
    return "\n".join(lines)


def policy_table() -> str:
    df = pd.read_csv(PROCESSED_DIR / "policy_evaluation.csv")
    gbm = df[df["model"] == "gbm"].sort_values("gain_retained_pct", ascending=False)

    lines = [
        "| Held-out circuit | DP gain | Model gain | Retained | Repeatable |",
        "|---|---:|---:|---:|:--:|",
    ]
    for _, r in gbm.iterrows():
        mark = "yes" if r["periodic"] else "**no**"
        lines.append(
            f"| {r['held_out']} | +{r['dp_gain_s']:.3f} s | {r['model_gain_s']:+.3f} s "
            f"| {r['gain_retained_pct']:.0f}% | {mark} |"
        )

    strict = gbm[gbm["periodic"]]
    lines.append("")
    lines.append(
        f"Mean across all {len(gbm)} folds: **{gbm['gain_retained_pct'].mean():.0f}%**. "
        f"On the {len(strict)} folds that produced a repeatable lap: "
        f"**{strict['gain_retained_pct'].mean():.0f}%** "
        f"(median {strict['gain_retained_pct'].median():.0f}%, "
        f"best {strict['gain_retained_pct'].max():.0f}%)."
    )
    return "\n".join(lines)


def model_comparison_table() -> str:
    df = pd.read_csv(PROCESSED_DIR / "policy_evaluation.csv")
    lines = [
        "| Model | All folds | Repeatable laps only | Repeatable | Mean MAE |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in ("gbm", "gbm_reg", "linear", "always-deploy"):
        sub = df[df["model"] == name]
        if sub.empty:
            continue
        strict = sub[sub["periodic"]]
        strict_txt = (
            f"{strict['gain_retained_pct'].mean():.0f}%" if len(strict) else "—"
        )
        lines.append(
            f"| `{name}` | {sub['gain_retained_pct'].mean():.0f}% | {strict_txt} "
            f"| {int(sub['periodic'].sum())}/{len(sub)} "
            f"| {sub['mae_fraction'].mean():.2f} |"
        )
    return "\n".join(lines)


def accuracy_table() -> str:
    df = pd.read_csv(PROCESSED_DIR / "simulation_accuracy.csv").sort_values("circuit")
    lines = [
        "| Circuit | Speed RMSE | Simulated lap | Measured lap | Error |",
        "|---|---:|---:|---:|---:|",
    ]
    for _, r in df.iterrows():
        lines.append(
            f"| {r['circuit']} | {r['rmse_kph']:.1f} km/h | {r['sim_lap_s']:.2f} s "
            f"| {r['actual_lap_s']:.2f} s | {r['lap_err_s']:+.2f} s |"
        )
    # The per-row errors are signed; the summary is a mean ABSOLUTE error, which would
    # otherwise read as though the model were biased by that amount.
    lines.append(
        f"| **mean** | **{df['rmse_kph'].mean():.1f} km/h** | | | "
        f"**{df['lap_err_s'].abs().mean():.2f} s abs** |"
    )
    return "\n".join(lines)


def parameter_table() -> str:
    fit = json.loads((PROCESSED_DIR / "vehicle_fit.json").read_text(encoding="utf-8"))
    rows = [
        ("Cd·A", f"{fit['cd_a']:.3f} m²",
         f"fitted — 95% CI [{fit['cd_a_ci'][0]:.3f}, {fit['cd_a_ci'][1]:.3f}], "
         f"{fit['coast_n']:,} straight-line coasting samples"),
        ("Cl·A", f"{fit['cl_a']:.3f} m²", "fitted — lateral-acceleration envelope"),
        ("μ lateral", f"{fit['mu_lat']:.3f}", "fitted"),
        ("μ braking", f"{fit['mu_brake']:.3f}", "fitted"),
        ("Lateral ceiling", f"{fit['a_lat_ceiling']:.1f} m/s²",
         f"fitted — tyre saturation, {fit['a_lat_ceiling'] / 9.80665:.1f} g"),
        ("Off-throttle force", f"{fit['f_offthrottle_n']:.0f} N",
         "fitted — engine braking plus MGU-K regen"),
        ("Crr", f"{fit['crr']}", "**assumed** — not identifiable (see below)"),
        ("ICE power", f"{fit['p_ice_w'] / 1000:.0f} kW",
         "**assumed** — published figure, not identifiable"),
        ("Driveline efficiency", f"{fit['driveline_efficiency']:.2f}", "**assumed**"),
        ("Regen efficiency", f"{fit['regen_efficiency']:.2f}",
         "**assumed** — no energy channels exist to measure it"),
        ("Mass", f"{fit['mass_kg']:.0f} kg",
         "768 kg regulatory minimum + 10 kg assumed qualifying fuel"),
    ]
    lines = ["| Parameter | Value | Basis |", "|---|---:|---|"]
    lines += [f"| {n} | {v} | {b} |" for n, v, b in rows]
    return "\n".join(lines)


def build_block() -> str:
    # Joined with single newlines; blank lines are explicit entries, so the markdown
    # does not end up double-spaced.
    return "\n".join(
        [
            START,
            "",
            "### Lap time gained, per circuit",
            "",
            "Measured against **uniform constant deployment** at the same starting "
            "state of charge, both strategies required to end the lap with at least the "
            "energy they began with. All times in seconds.",
            "",
            strategy_table(),
            "",
            "Greedy is faster on every circuit and repeatable on none of them: it ends "
            "each lap around 2 MJ in debt, having spent energy it never repays. That is "
            "why it is not the baseline.",
            "",
            "### Learned policy — leave-one-circuit-out",
            "",
            policy_table(),
            "",
            "Scores above 100% are not the model beating the optimiser. The DP is "
            "optimal subject to periodicity, and the only way past it is to break that "
            "constraint — every fold above 100% ends the lap with less charge than it "
            "started.",
            "",
            model_comparison_table(),
            "",
            "### Physics model accuracy",
            "",
            "Forward simulation against the measured qualifying lap, on the circuits "
            "with 2026 telemetry.",
            "",
            accuracy_table(),
            "",
            "### Fitted vehicle parameters",
            "",
            parameter_table(),
            "",
            END,
        ]
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true", dest="show")
    args = ap.parse_args()

    block = build_block()
    if args.show or not README.exists():
        print(block)
        return 0

    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        print(f"README.md has no {START} / {END} markers; nothing rewritten.")
        return 1
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    README.write_text(head + block + tail, encoding="utf-8")
    print(f"Rewrote the results block in {README}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
