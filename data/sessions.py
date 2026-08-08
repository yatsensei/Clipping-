"""Circuit registry and reference-lap selection.

The circuit list is driven by the FastF1 event schedule, never hardcoded.

As of the 2026 season only part of the calendar has run, so each circuit resolves to a
data source: the 2026 qualifying session where it exists, otherwise the most recent
qualifying session AT THE SAME VENUE in a previous year. Fallback sessions contribute
GEOMETRY ONLY — their speed traces are from a different car under different regulations
and are never used for physics. Circuits with no session at the venue in any year are
excluded rather than invented.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date
from typing import Iterable

import fastf1
import pandas as pd

from data.cache import enable

TARGET_YEAR = 2026
FALLBACK_YEARS: tuple[int, ...] = (2025, 2024, 2023, 2022, 2021, 2019, 2018)

# Same physical venue, different Location string between seasons. Both sides of a
# comparison are normalised through this map.
#
# Deliberately matched on venue, never on country or event name: in 2026 the "Bahrain
# Grand Prix" is held at Sepang (official name "Bahrain Grand Prix in Malaysia"), so
# matching by name or country would silently load Sakhir's geometry for a Malaysian race.
VENUE_ALIASES: dict[str, str] = {
    "yas marina": "yas island",
    "monte carlo": "monaco",
}


def slugify(value: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")


def _venue_key(location: str) -> str:
    key = location.strip().lower()
    return VENUE_ALIASES.get(key, key)


@dataclass(frozen=True)
class CircuitRef:
    """Where a circuit's geometry comes from, and how trustworthy that is."""

    circuit_id: str
    round_number: int
    event_name: str
    official_event_name: str
    location: str
    country: str
    event_date: str
    data_year: int
    data_round: int
    is_fallback: bool
    provenance: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class UnavailableCircuit:
    circuit_id: str
    round_number: int
    event_name: str
    location: str
    reason: str


def build_registry(
    year: int = TARGET_YEAR,
    today: date | None = None,
) -> tuple[list[CircuitRef], list[UnavailableCircuit]]:
    """Resolve every round on the calendar to a usable qualifying session.

    Returns (available, unavailable). Never raises for a missing circuit — an absent
    venue is reported, not filled in.
    """
    enable()
    today = today or date.today()
    schedule = fastf1.get_event_schedule(year, include_testing=False)

    # Cache prior schedules once; resolution touches them repeatedly.
    prior: dict[int, pd.DataFrame] = {}
    for fy in FALLBACK_YEARS:
        if fy >= year:
            continue
        try:
            prior[fy] = fastf1.get_event_schedule(fy, include_testing=False)
        except Exception:  # noqa: BLE001 - a missing season is not fatal
            continue

    available: list[CircuitRef] = []
    unavailable: list[UnavailableCircuit] = []

    for _, ev in schedule.iterrows():
        rnd = int(ev["RoundNumber"])
        location = str(ev["Location"])
        circuit_id = slugify(location)
        event_date = pd.Timestamp(ev["EventDate"]).date()
        common = {
            "circuit_id": circuit_id,
            "round_number": rnd,
            "event_name": str(ev["EventName"]),
            "official_event_name": str(ev.get("OfficialEventName", "")),
            "location": location,
            "country": str(ev["Country"]),
            "event_date": event_date.isoformat(),
        }

        if event_date <= today:
            available.append(
                CircuitRef(
                    **common,
                    data_year=year,
                    data_round=rnd,
                    is_fallback=False,
                    provenance=f"{year} Qualifying",
                )
            )
            continue

        match = _find_prior_venue(location, prior)
        if match is None:
            unavailable.append(
                UnavailableCircuit(
                    circuit_id=circuit_id,
                    round_number=rnd,
                    event_name=str(ev["EventName"]),
                    location=location,
                    reason=(
                        f"Round has not yet run ({event_date}) and no qualifying session "
                        f"exists at this venue in {FALLBACK_YEARS[0]}-{FALLBACK_YEARS[-1]}."
                    ),
                )
            )
            continue

        fy, frnd = match
        available.append(
            CircuitRef(
                **common,
                data_year=fy,
                data_round=frnd,
                is_fallback=True,
                provenance=f"{fy} Qualifying (geometry only; {year} round not yet run)",
            )
        )

    return available, unavailable


def _find_prior_venue(
    location: str, prior: dict[int, pd.DataFrame]
) -> tuple[int, int] | None:
    target = _venue_key(location)
    for fy in sorted(prior, reverse=True):
        sched = prior[fy]
        keys = sched["Location"].astype(str).map(_venue_key)
        hit = sched[keys == target]
        if not hit.empty:
            return fy, int(hit.iloc[0]["RoundNumber"])
    return None


def load_qualifying(ref: CircuitRef) -> fastf1.core.Session:
    """Load the qualifying session backing a circuit, with telemetry."""
    enable()
    session = fastf1.get_session(ref.data_year, ref.data_round, "Q")
    session.load(telemetry=True, laps=True, weather=True, messages=False)
    return session


def clean_laps(session: fastf1.core.Session) -> pd.DataFrame:
    """Laps usable for geometry: complete, accurate, not deleted, green track.

    TrackStatus '1' is all-green. Anything else means yellow flags, safety car or a red
    flag, under which the driving line is not representative.
    """
    laps = session.laps
    if laps is None or laps.empty:
        return pd.DataFrame()

    ok = laps["LapTime"].notna()
    if "IsAccurate" in laps:
        ok &= laps["IsAccurate"].astype("boolean").fillna(False).astype(bool)
    if "Deleted" in laps:
        ok &= ~laps["Deleted"].astype("boolean").fillna(False).astype(bool)
    if "TrackStatus" in laps:
        ok &= laps["TrackStatus"].astype(str).str.strip() == "1"
    return laps[ok]


def candidate_reference_laps(
    session: fastf1.core.Session, limit: int = 8
) -> list[pd.Series]:
    """Clean laps ordered fastest first, as fallbacks for the reference lap.

    The single fastest lap is not always usable: at Suzuka its telemetry has a gap that
    left 1.5 km of the trace as a flat line. Callers walk this list until one lap has
    continuous coverage.
    """
    laps = clean_laps(session)
    if laps.empty:
        laps = session.laps[session.laps["LapTime"].notna()]
    if laps.empty:
        return []
    ordered = laps.sort_values("LapTime").head(limit)
    return [row for _, row in ordered.iterrows()]


def pick_reference_lap(session: fastf1.core.Session) -> pd.Series:
    """Fastest clean qualifying lap in the session.

    Falls back to the fastest lap overall only if the clean filter leaves nothing, and
    that relaxation is reported by the caller rather than hidden.
    """
    laps = clean_laps(session)
    if laps.empty:
        laps = session.laps[session.laps["LapTime"].notna()]
    if laps.empty:
        raise ValueError("session contains no timed laps")
    return laps.loc[laps["LapTime"].idxmin()]


def session_weather(session: fastf1.core.Session) -> dict[str, float | None]:
    """Median session weather, used to compute real air density per circuit."""
    wd = getattr(session, "weather_data", None)
    if wd is None or len(wd) == 0:
        return {"air_temp_c": None, "pressure_mbar": None, "humidity_pct": None,
                "track_temp_c": None}
    return {
        "air_temp_c": float(wd["AirTemp"].median()),
        "pressure_mbar": float(wd["Pressure"].median()),
        "humidity_pct": float(wd["Humidity"].median()),
        "track_temp_c": float(wd["TrackTemp"].median()),
    }


def iter_registry(refs: Iterable[CircuitRef]) -> Iterable[CircuitRef]:
    return sorted(refs, key=lambda r: r.round_number)
