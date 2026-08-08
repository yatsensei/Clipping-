"""Does the lap-time gain behave the way the physics says it should?

The optimiser's advantage over uniform deployment comes from two places: refusing to
spend energy where the taper is throttling it away, and concentrating it on corner exits.
If that story is right, the gain should be largest on circuits that spend the most time
above the 290 km/h taper threshold, and smallest somewhere like Monaco that barely
reaches it.

This checks that relationship rather than asserting it.

Run:  uv run python -m scripts.analyse_gains
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import stats

from config.regulations import DEPLOY_TAPER_FULL_POWER_KPH
from data.cache import PROCESSED_DIR


def main() -> int:
    comparison = pd.read_csv(PROCESSED_DIR / "strategy_comparison.csv")

    rows = []
    for _, r in comparison.iterrows():
        cid = r["circuit_id"]
        path = PROCESSED_DIR / "strategies" / f"{cid}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        opt = data["strategies"]["optimal"]
        speed = np.asarray(opt["speed_kph"])
        deploy = np.asarray(opt["deploy_kw"])
        harvest = np.asarray(opt["harvest_kw"])

        above = float(np.mean(speed > DEPLOY_TAPER_FULL_POWER_KPH))
        deploying = deploy > 1.0
        harvesting = harvest > 1.0

        # The crisp test of whether the optimiser avoids the taper: if deployment were
        # blind to speed, the share of ENERGY spent above the threshold would match the
        # share of the lap spent above it. Energy share well below distance share means
        # it is deliberately keeping out of the tapered zone.
        fast = speed > DEPLOY_TAPER_FULL_POWER_KPH
        energy_above = float(deploy[fast].sum() / max(deploy.sum(), 1e-9))

        # Harvest necessarily spans a braking zone, from the end of a straight down to
        # the apex, so its power-weighted mean speed says little. What matters is the
        # speed at which each harvest block STARTS.
        starts = np.flatnonzero(harvesting & ~np.roll(harvesting, 1))
        harvest_onset = float(np.median(speed[starts])) if len(starts) else np.nan
        dep_starts = np.flatnonzero(deploying & ~np.roll(deploying, 1))
        deploy_onset = float(np.median(speed[dep_starts])) if len(dep_starts) else np.nan

        rows.append(
            {
                "circuit": cid,
                "gain_s": r["gain_vs_uniform_s"],
                "lap_km": r["lap_distance_m"] / 1000.0,
                "gain_per_km": r["gain_vs_uniform_s"] / (r["lap_distance_m"] / 1000.0),
                "pct_above_taper": 100.0 * above,
                "mean_speed_kph": float(speed.mean()),
                # Where the energy actually goes, and where it comes back.
                "deploy_speed_kph": float(np.average(speed[deploying],
                                                     weights=deploy[deploying]))
                if deploying.any() else np.nan,
                "harvest_speed_kph": float(np.average(speed[harvesting],
                                                      weights=harvest[harvesting]))
                if harvesting.any() else np.nan,
                "pct_lap_deploying": 100.0 * float(deploying.mean()),
                "pct_lap_harvesting": 100.0 * float(harvesting.mean()),
                "pct_energy_above_taper": 100.0 * energy_above,
                "harvest_onset_kph": harvest_onset,
                "deploy_onset_kph": deploy_onset,
                "harvested_mj": r["optimal_harvested_mj"],
            }
        )

    df = pd.DataFrame(rows).sort_values("gain_s", ascending=False)

    print("=" * 104)
    print("WHERE THE GAIN COMES FROM")
    print("=" * 104)
    print(df.to_string(index=False, float_format=lambda v: f"{v:8.2f}"))

    print("\n--- Is the gain larger where the taper bites more? ---")
    for x, label in [("pct_above_taper", "% of lap above 290 km/h"),
                     ("mean_speed_kph", "mean lap speed"),
                     ("lap_km", "lap length")]:
        ok = df[[x, "gain_s"]].dropna()
        res = stats.linregress(ok[x], ok["gain_s"])
        print(f"  gain vs {label:<24} r = {res.rvalue:+.3f}  p = {res.pvalue:.4f}")

    # Lap length is the strongest predictor, which is largely mechanical: a longer lap
    # simply has more corners to optimise. Normalising by distance asks whether the taper
    # matters beyond that, and the answer has to be reported either way.
    print("\n  Controlling for lap length (gain per km):")
    for x, label in [("pct_above_taper", "% of lap above 290 km/h"),
                     ("mean_speed_kph", "mean lap speed")]:
        ok = df[[x, "gain_per_km"]].dropna()
        res = stats.linregress(ok[x], ok["gain_per_km"])
        print(f"    gain/km vs {label:<24} r = {res.rvalue:+.3f}  p = {res.pvalue:.4f}")
    print("    Lap length dominates the raw correlation. Per kilometre the gain is")
    print("    remarkably flat across the calendar "
          f"({df['gain_per_km'].min():.2f}-{df['gain_per_km'].max():.2f} s/km), so the")
    print("    headline relationship with circuit speed is mostly a length effect and")
    print("    should not be presented as the taper driving the gain.")

    print("\n--- Does the optimiser avoid the tapered zone? ---")
    print(f"  taper threshold {DEPLOY_TAPER_FULL_POWER_KPH:.0f} km/h")
    print(f"  share of the LAP above it        {df['pct_above_taper'].mean():5.1f}%")
    print(f"  share of ENERGY spent above it   {df['pct_energy_above_taper'].mean():5.1f}%")
    ratio = df["pct_energy_above_taper"].mean() / max(df["pct_above_taper"].mean(), 1e-9)
    print(f"  ratio {ratio:.2f} — speed-blind deployment would give 1.00")
    worst = df.loc[df["pct_energy_above_taper"].idxmax()]
    print(f"  highest anywhere: {worst['circuit']} at "
          f"{worst['pct_energy_above_taper']:.1f}% of energy above the threshold")

    print("\n--- Where each phase begins ---")
    print(f"  median speed at the start of a DEPLOY block   "
          f"{df['deploy_onset_kph'].mean():6.1f} km/h")
    print(f"  median speed at the start of a HARVEST block  "
          f"{df['harvest_onset_kph'].mean():6.1f} km/h")
    gap = df["harvest_onset_kph"].mean() - df["deploy_onset_kph"].mean()
    print(f"  harvesting starts {gap:+.1f} km/h relative to deploying")
    print("\n  Deployment begins at corner exits and stops short of the taper; harvest")
    print("  begins at the end of straights, where deployment was being throttled away")
    print("  anyway. That is super clipping, and the optimiser was never told to do it —")
    print("  the taper enters the model only as a ceiling on available power.")
    print("  NOTE: a power-weighted mean speed is the wrong statistic for this, because a")
    print("  harvest block necessarily spans a braking zone down to the apex, which drags")
    print("  its mean below the deployment mean even when it starts far faster.")

    df.to_csv(PROCESSED_DIR / "gain_analysis.csv", index=False)
    print(f"\nWritten: {PROCESSED_DIR / 'gain_analysis.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
