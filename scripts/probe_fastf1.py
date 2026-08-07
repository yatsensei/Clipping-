"""Section 8 first-action probe: what does FastF1 actually expose for 2026?

Answers three questions before any modelling is designed:
  1. How many rounds are on the 2026 calendar (per the schedule API, not per assumption)?
  2. What telemetry channels exist for a 2026 session?
  3. Do any energy/ERS channels exist? If they do, the whole architecture changes.

Run:  uv run python -m scripts.probe_fastf1
"""

from __future__ import annotations

import sys
from pathlib import Path

import fastf1
import pandas as pd

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"

# Channels that would mean F1 has started publishing energy data. If any of these
# (or anything matching the substring scan below) appears, stop and re-plan.
# Matched against tokens split out of CamelCase/snake_case column names, not as raw
# substrings — a substring scan flags "IsPersonalBest" for containing "ers".
ENERGY_CHANNEL_HINTS = (
    "soc",
    "stateofcharge",
    "energy",
    "ers",
    "mgu",
    "mguk",
    "mguh",
    "battery",
    "batt",
    "deploy",
    "deployment",
    "harvest",
    "regen",
    "store",
    "charge",
    "kj",
    "mj",
    "hybrid",
    "electric",
)


def banner(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def probe_schedule(year: int) -> pd.DataFrame:
    banner(f"1. {year} EVENT SCHEDULE")
    schedule = fastf1.get_event_schedule(year, include_testing=False)
    print(f"Rounds returned (excluding testing): {len(schedule)}")
    print(f"Max RoundNumber: {schedule['RoundNumber'].max()}")
    cols = ["RoundNumber", "Country", "Location", "EventName", "EventDate", "EventFormat"]
    print()
    print(schedule[cols].to_string(index=False))

    testing = fastf1.get_event_schedule(year, include_testing=True)
    print(f"\nRows including testing events: {len(testing)}")
    return schedule


def probe_telemetry(year: int, schedule: pd.DataFrame) -> None:
    banner(f"2. TELEMETRY CHANNELS — {year} QUALIFYING")

    # Walk backwards from the most recent event: later rounds are more likely to
    # have completed and had their data published.
    today = pd.Timestamp.now(tz="UTC").tz_localize(None)
    past = schedule[schedule["EventDate"] <= today].sort_values("RoundNumber", ascending=False)
    if past.empty:
        print(f"No {year} events have taken place yet. Nothing to probe.")
        return

    for _, event in past.iterrows():
        rnd = int(event["RoundNumber"])
        name = event["EventName"]
        print(f"\n--- Trying round {rnd}: {name} (Q) ---")
        try:
            session = fastf1.get_session(year, rnd, "Q")
            session.load(telemetry=True, laps=True, weather=False, messages=False)
        except Exception as exc:  # noqa: BLE001 - probe: report, never fabricate
            print(f"  FAILED to load: {type(exc).__name__}: {exc}")
            continue

        laps = session.laps
        if laps is None or laps.empty:
            print("  Session loaded but contains no laps.")
            continue

        fastest = laps.pick_fastest()
        if fastest is None or pd.isna(fastest.get("LapTime")):
            print("  No fastest lap available.")
            continue

        car = fastest.get_car_data()
        pos = fastest.get_pos_data()
        merged = fastest.get_telemetry()

        print(f"  Session: {session.event['EventName']} {session.name}")
        print(f"  Fastest: {fastest['Driver']} ({fastest['Team']}) {fastest['LapTime']}")
        print(f"  Samples: car_data={len(car)}  pos_data={len(pos)}  merged={len(merged)}")

        print("\n  car_data columns:")
        for c in car.columns:
            print(f"    - {c:<16} {str(car[c].dtype)}")
        print("\n  pos_data columns:")
        for c in pos.columns:
            print(f"    - {c:<16} {str(pos[c].dtype)}")
        print("\n  merged telemetry columns:")
        for c in merged.columns:
            print(f"    - {c:<16} {str(merged[c].dtype)}")

        print("\n  laps columns:")
        print("    " + ", ".join(map(str, laps.columns)))

        report_energy_scan(merged.columns, car.columns, pos.columns, laps.columns)

        # Effective sample rate, needed to justify the 5 m distance grid.
        if "Time" in merged and len(merged) > 1:
            span = merged["Time"].iloc[-1] - merged["Time"].iloc[0]
            hz = (len(merged) - 1) / span.total_seconds()
            print(f"\n  Merged telemetry effective rate: {hz:.1f} Hz over {span.total_seconds():.2f} s")
        if "Time" in car and len(car) > 1:
            span = car["Time"].iloc[-1] - car["Time"].iloc[0]
            hz = (len(car) - 1) / span.total_seconds()
            print(f"  Raw car_data effective rate:     {hz:.1f} Hz over {span.total_seconds():.2f} s")
        return

    print("\nNo session in the season loaded successfully.")


def tokenise(name: str) -> list[str]:
    """Split 'DistanceToDriverAhead' / 'lap_time' into lowercase word tokens."""
    out, cur = [], ""
    for ch in name:
        if ch in " _-":
            if cur:
                out.append(cur.lower())
            cur = ""
        elif ch.isupper() and cur and not cur[-1].isupper():
            out.append(cur.lower())
            cur = ch
        else:
            cur += ch
    if cur:
        out.append(cur.lower())
    return out


def report_energy_scan(*column_sets) -> None:
    banner("3. ENERGY / ERS CHANNEL SCAN")
    all_cols = sorted({str(c) for cols in column_sets for c in cols})
    hits = [c for c in all_cols if set(tokenise(c)) & set(ENERGY_CHANNEL_HINTS)]
    print(f"Scanned {len(all_cols)} distinct column names across car/pos/merged/laps.")
    if hits:
        print("\n!!! POSSIBLE ENERGY CHANNELS FOUND — STOP AND RE-PLAN !!!")
        for h in hits:
            print(f"    - {h}")
    else:
        print("\nNo energy, SoC, ERS, MGU, battery, deployment or harvest channels found.")
        print("Confirms the brief's assumption: energy state must be RECONSTRUCTED, not read.")


def main() -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(CACHE_DIR))
    print(f"fastf1 {fastf1.__version__} | cache: {CACHE_DIR}")

    schedule = probe_schedule(2026)
    probe_telemetry(2026, schedule)
    return 0


if __name__ == "__main__":
    sys.exit(main())
