"""Snapshot the API to static JSON for deployment.

Every endpoint this project serves is a pure reader — nothing is computed on request,
because the DP is far too slow for a request cycle and the circuits do not change. So the
whole service can be replaced in production by the files it would have returned, and the
site deploys as static assets with no backend to run.

The snapshot is taken by CALLING THE REAL APP through a test client rather than
re-serialising data/processed by hand. That way the static payloads are byte-identical to
what the service returns, including the provenance and data_type fields, and they cannot
drift as the API evolves.

Query strings do not survive as static files, so `/strategy?mode=optimal` is written to
`/strategy/optimal.json`. lib/api.ts builds that path when it is in static mode.

Run:  uv run python -m scripts.export_static
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from api.store import STRATEGY_ALIASES

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public" / "api"

# "naive" is an alias for "uniform"; one file per distinct strategy is enough.
MODES = sorted(set(STRATEGY_ALIASES.values()))


def write(path: Path, payload: object) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Compact separators: this ships to every visitor, and the whitespace is pure weight.
    text = json.dumps(payload, separators=(",", ":"))
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def main() -> int:
    client = TestClient(app)

    if OUT.exists():
        shutil.rmtree(OUT)

    total = 0
    written = 0

    def snapshot(url: str, path: Path) -> bool:
        nonlocal total, written
        response = client.get(url)
        if response.status_code != 200:
            print(f"  SKIP {url} -> {response.status_code}")
            return False
        total += write(path, response.json())
        written += 1
        return True

    snapshot("/circuits", OUT / "circuits.json")
    snapshot("/meta", OUT / "meta.json")

    circuits = client.get("/circuits").json()
    for circuit in circuits:
        cid = circuit["circuit_id"]
        base = OUT / "circuits" / cid

        snapshot(f"/circuits/{cid}", OUT / "circuits" / f"{cid}.json")
        snapshot(f"/circuits/{cid}/geometry", base / "geometry.json")

        if not circuit["has_strategy"]:
            print(f"  {cid}: geometry only, no strategy solved")
            continue

        snapshot(f"/circuits/{cid}/comparison", base / "comparison.json")
        for mode in MODES:
            snapshot(
                f"/circuits/{cid}/strategy?mode={mode}",
                base / "strategy" / f"{mode}.json",
            )

    print(f"\n{written} files, {total / 1e6:.2f} MB -> {OUT.relative_to(ROOT)}")
    print(
        "Committed so the Vercel build (which has no Python) can serve them. "
        "Re-run after scripts.run_optimiser."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
