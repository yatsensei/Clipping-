"""Second first-action probe: how much of the 2026 calendar actually has data yet?

The brief assumes every circuit on the 2026 calendar is available. As of the run
date only part of the season has happened, so this establishes, per round:
  - whether a 2026 qualifying session loads with usable telemetry
  - the effective telemetry sample rate (the brief assumed ~10 Hz)
  - whether circuit_info corner data is available
  - whether a pre-2026 fallback session exists for rounds not yet run

Run:  uv run python -m scripts.probe_coverage
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import fastf1
import pandas as pd

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"
FALLBACK_YEARS = (2025, 2024, 2023)

# Same physical venue, different Location string between seasons. Keys and values are
# lowercase; both sides of a comparison are normalised through this map.
VENUE_ALIASES = {
    "yas marina": "yas island",
    "monte carlo": "monaco",
}


def sample_rate(df: pd.DataFrame) -> float | None:
    if "Time" not in df or len(df) < 2:
        return None
    span = (df["Time"].iloc[-1] - df["Time"].iloc[0]).total_seconds()
    return (len(df) - 1) / span if span > 0 else None


def try_session(year: int, rnd: int, ident: str = "Q") -> dict | None:
    """Load a session and summarise it. Returns None on any failure — never fabricates."""
    try:
        session = fastf1.get_session(year, rnd, ident)
        session.load(telemetry=True, laps=True, weather=False, messages=False)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}

    laps = session.laps
    if laps is None or laps.empty:
        return {"error": "session loaded but no laps"}

    try:
        fastest = laps.pick_fastest()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"pick_fastest: {type(exc).__name__}: {exc}"}
    if fastest is None or pd.isna(fastest.get("LapTime")):
        return {"error": "no valid fastest lap"}

    try:
        car = fastest.get_car_data()
        pos = fastest.get_pos_data()
        tel = fastest.get_telemetry().add_distance()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"telemetry: {type(exc).__name__}: {exc}"}

    corners = None
    try:
        ci = session.get_circuit_info()
        corners = len(ci.corners) if ci is not None else None
    except Exception:  # noqa: BLE001
        corners = None

    gps_ok = bool(pos[["X", "Y"]].notna().all(axis=1).any()) and pos["X"].nunique() > 10
    dist = float(tel["Distance"].iloc[-1]) if "Distance" in tel and len(tel) else float("nan")

    return {
        "driver": fastest["Driver"],
        "team": fastest["Team"],
        "laptime": str(fastest["LapTime"]),
        "n_car": len(car),
        "n_pos": len(pos),
        "hz_car": sample_rate(car),
        "hz_pos": sample_rate(pos),
        "corners": corners,
        "gps_ok": gps_ok,
        "lap_distance_m": dist,
        "n_laps": len(laps),
    }


def main() -> int:
    warnings.filterwarnings("ignore")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(CACHE_DIR))
    fastf1.set_log_level("ERROR")

    today = pd.Timestamp.now(tz="UTC").tz_localize(None)
    schedule = fastf1.get_event_schedule(2026, include_testing=False)
    print(f"Run date: {today.date()}   Rounds on 2026 calendar: {len(schedule)}\n")

    rows = []
    for _, ev in schedule.iterrows():
        rnd = int(ev["RoundNumber"])
        name = str(ev["EventName"])
        loc = str(ev["Location"])
        date = pd.Timestamp(ev["EventDate"])
        happened = date <= today

        print(f"[R{rnd:02d}] {name:<26} {loc:<18} {date.date()}", end="  ", flush=True)

        row = {
            "round": rnd, "event": name, "location": loc, "country": str(ev["Country"]),
            "date": date.date(), "in_past": happened,
        }

        if happened:
            res = try_session(2026, rnd, "Q")
            if res and "error" not in res:
                row.update({"source": "2026 Q", **res})
                print(
                    f"OK  {res['driver']:>3} {res['laptime'][:-3]}  "
                    f"car={res['n_car']:>4} ({res['hz_car']:.1f}Hz) "
                    f"pos={res['n_pos']:>4} ({res['hz_pos']:.1f}Hz) "
                    f"corners={res['corners']} gps={'Y' if res['gps_ok'] else 'N'}"
                )
                rows.append(row)
                continue
            print(f"2026 FAILED ({res.get('error', 'unknown')[:60]}) ->", end=" ", flush=True)

        # Not yet run, or 2026 load failed: look for a pre-2026 session at the SAME
        # VENUE. Match on location only, never on country or event name — in 2026 the
        # Bahrain Grand Prix is held at Sepang ("Bahrain Grand Prix in Malaysia"), so
        # matching that event to Sakhir would silently load the wrong circuit.
        found = False
        for fy in FALLBACK_YEARS:
            try:
                fsched = fastf1.get_event_schedule(fy, include_testing=False)
            except Exception:  # noqa: BLE001
                continue
            target = VENUE_ALIASES.get(loc.lower(), loc.lower())
            match = fsched[fsched["Location"].str.lower().map(
                lambda x: VENUE_ALIASES.get(x, x)) == target]
            if match.empty:
                continue
            frnd = int(match.iloc[0]["RoundNumber"])
            res = try_session(fy, frnd, "Q")
            if res and "error" not in res:
                row.update({"source": f"{fy} Q", **res})
                print(
                    f"fallback {fy}: {res['driver']} {res['laptime'][:-3]} "
                    f"car={res['n_car']} ({res['hz_car']:.1f}Hz) corners={res['corners']}"
                )
                rows.append(row)
                found = True
                break
        if not found:
            row["source"] = "NONE"
            print("NO DATA AVAILABLE IN ANY YEAR")
            rows.append(row)

    df = pd.DataFrame(rows)
    out = Path(__file__).resolve().parents[1] / "data" / "processed" / "coverage_probe.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    print("\n" + "=" * 78)
    print("COVERAGE SUMMARY")
    print("=" * 78)
    print(df["source"].value_counts().to_string())
    if "hz_car" in df:
        hz = df["hz_car"].dropna()
        if len(hz):
            print(f"\ncar_data sample rate across circuits: "
                  f"min={hz.min():.1f} median={hz.median():.1f} max={hz.max():.1f} Hz")
        hzp = df["hz_pos"].dropna()
        if len(hzp):
            print(f"pos_data sample rate across circuits: "
                  f"min={hzp.min():.1f} median={hzp.median():.1f} max={hzp.max():.1f} Hz")
    missing = df[df["source"] == "NONE"]
    if len(missing):
        print("\nCircuits with NO telemetry in any year:")
        for _, m in missing.iterrows():
            print(f"  R{m['round']:02d} {m['event']} ({m['location']})")
    print(f"\nWritten: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
