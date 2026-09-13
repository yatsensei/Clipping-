"""
Capture real Jolpica-F1 responses as test fixtures for the frontend's standings logic.

    uv run python -m scripts.capture_fixtures [--season 2026]

The pure functions in web/lib/f1/standings.ts are tested against these files rather than
hand-written JSON, because the bug class that matters there is "the API's shape is not
what I assumed" — a position field that is a string, a driver with no permanentNumber, a
result whose positionText is "R". A synthetic fixture cannot contain surprises.

Jolpica requires a descriptive User-Agent; without one it answers 403.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx

BASE = "https://api.jolpi.ca/ergast/f1"
USER_AGENT = "clipping-f1-analytics/0.1 (https://github.com/yatsensei/Clipping-)"
OUT = Path(__file__).resolve().parents[1] / "web" / "lib" / "f1" / "__fixtures__"


def capture(client: httpx.Client, path: str, name: str) -> None:
    for attempt in range(3):
        response = client.get(f"{BASE}{path}")
        if response.status_code in (429, 500, 502, 503, 504):
            wait = float(response.headers.get("Retry-After", 2 ** attempt))
            print(f"  {response.status_code} on {path}; waiting {wait:.0f}s")
            time.sleep(wait)
            continue
        response.raise_for_status()
        break
    else:
        raise RuntimeError(f"gave up on {path}")

    target = OUT / f"{name}.json"
    target.write_text(json.dumps(response.json(), indent=2) + "\n", encoding="utf-8")
    print(f"  {name}.json  ({len(response.content) / 1024:.0f} KB)")
    # Stay under the documented 4 req/s burst.
    time.sleep(0.3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()
    s = args.season

    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30) as client:
        # Latest round from the live standings, then the one before it for the delta test.
        latest = client.get(f"{BASE}/{s}/driverStandings.json").json()
        r = int(latest["MRData"]["StandingsTable"]["StandingsLists"][0]["round"])
        print(f"season {s}, latest round {r}")

        fixtures = [
            (f"/{s}.json?limit=50", "schedule"),
            (f"/{s}/{r}/driverStandings.json", f"round-{r}-driverStandings"),
            (f"/{s}/{r - 1}/driverStandings.json", f"round-{r - 1}-driverStandings"),
            (f"/{s}/{r}/constructorStandings.json", f"round-{r}-constructorStandings"),
            (f"/{s}/{r - 1}/constructorStandings.json", f"round-{r - 1}-constructorStandings"),
            (f"/{s}/1/driverStandings.json", "round-1-driverStandings"),
            (f"/{s}/results.json?limit=100&offset=0", "results-p1"),
            (f"/{s}/qualifying.json?limit=100&offset=0", "qualifying-p1"),
            (f"/{s}/sprint.json?limit=100", "sprint-p1"),
            (f"/{s}/last/results.json", "last-results"),
        ]
        for path, name in fixtures:
            capture(client, path, name)

    (OUT / "README.md").write_text(
        "Real Jolpica-F1 responses, captured by `uv run python -m scripts.capture_fixtures`.\n"
        f"Season {s}, latest round {r} at capture time. Refresh whenever the API shape or\n"
        "the standings logic changes; the tests assert invariants, not specific points totals.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
