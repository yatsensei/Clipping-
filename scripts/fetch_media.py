"""
Fetch driver portraits and team logos from Wikimedia Commons, with attribution.

    uv run python -m scripts.fetch_media [--force] [--only drivers|teams] [--season 2026]

Formula 1's own media is copyrighted, so the site uses freely licensed images and says
where each came from. The path for every entrant in the current standings:

    Jolpica standings  ->  Wikipedia article URL
    Wikipedia          ->  Wikidata item (pageprops.wikibase_item)
    Wikidata           ->  P18 image (drivers), P154 logo (teams — never P18, which
                           for a team is a photograph of a car, not a logo)
    Commons            ->  600px thumbnail URL + licence + author (imageinfo/extmetadata)

Only attribution licences are accepted: CC BY, CC BY-SA, CC0, public domain, and the
UK Open Government Licence (attribution-only, CC BY-compatible). Everything else — and
every entrant with no usable image at all — is recorded as missing so the site's
Avatar falls back to initials on the team colour. A miss is expected for rookies and
for trademarked logos; it is not an error and does not fail the script.

Output: web/public/media/{drivers,teams}/<id>.<ext> and web/public/media/credits.json.
Both are committed, because the deployment has no Python to run this.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

JOLPICA = "https://api.jolpi.ca/ergast/f1"
USER_AGENT = "clipping-f1-analytics/0.1 (https://github.com/yatsensei/Clipping-)"
ROOT = Path(__file__).resolve().parents[1] / "web" / "public" / "media"
MANIFEST = ROOT / "credits.json"
# Avatars render at 96 CSS px at most; 400 px covers a 3x display with margin.
THUMB_WIDTH = 400
PAUSE_S = 0.25

ACCEPTED_LICENCE = re.compile(r"^(CC BY|CC0|Public domain|PD|OGL)", re.IGNORECASE)
EXT_FOR_MIME = {"image/jpeg": "jpg", "image/png": "png", "image/svg+xml": "svg", "image/webp": "webp"}


class Client:
    def __init__(self) -> None:
        self.http = httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True
        )

    def get(self, url: str, **params: str) -> httpx.Response:
        for attempt in range(3):
            response = self.http.get(url, params=params or None)
            if response.status_code in (429, 500, 502, 503, 504):
                time.sleep(float(response.headers.get("Retry-After", 2**attempt)))
                continue
            response.raise_for_status()
            time.sleep(PAUSE_S)
            return response
        raise RuntimeError(f"gave up on {url}")

    def json(self, url: str, **params: str) -> dict:
        return self.get(url, **params).json()


# --------------------------------------------------------------------- lookups


def wikidata_item(client: Client, wiki_url: str) -> str | None:
    """Wikipedia article URL -> Q-id, following redirects."""
    title = unquote(urlparse(wiki_url).path.rsplit("/", 1)[-1])
    data = client.json(
        "https://en.wikipedia.org/w/api.php",
        action="query",
        prop="pageprops",
        ppprop="wikibase_item",
        titles=title,
        redirects="1",
        format="json",
    )
    for page in data.get("query", {}).get("pages", {}).values():
        item = page.get("pageprops", {}).get("wikibase_item")
        if item:
            return item
    return None


def claim_file(client: Client, qid: str, prop: str) -> str | None:
    """The Commons file name held by a Wikidata property, e.g. P18 -> 'Lando Norris 2024.jpg'."""
    data = client.json(
        "https://www.wikidata.org/w/api.php",
        action="wbgetclaims",
        entity=qid,
        property=prop,
        format="json",
    )
    claims = data.get("claims", {}).get(prop, [])
    # Prefer the preferred-rank claim when there are several images.
    claims.sort(key=lambda c: 0 if c.get("rank") == "preferred" else 1)
    for claim in claims:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, str) and value:
            return value
    return None


def commons_info(client: Client, filename: str) -> dict | None:
    data = client.json(
        "https://commons.wikimedia.org/w/api.php",
        action="query",
        titles=f"File:{filename}",
        prop="imageinfo",
        iiprop="url|mime|extmetadata",
        iiurlwidth=str(THUMB_WIDTH),
        format="json",
    )
    for page in data.get("query", {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [None])[0]
        if info:
            return info
    return None


def strip_html(text: str | None) -> str | None:
    if not text:
        return None
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip() or None


# --------------------------------------------------------------------- pipeline


def resolve(client: Client, kind: str, entity_id: str, wiki_url: str) -> tuple[dict | None, str]:
    """Returns (credit, reason). credit is None when nothing usable was found."""
    qid = wikidata_item(client, wiki_url)
    if not qid:
        return None, "no_wikidata"

    filename = claim_file(client, qid, "P18" if kind == "drivers" else "P154")
    if not filename:
        return None, "no_image"

    info = commons_info(client, filename)
    if not info:
        return None, "commons_missing"

    meta = info.get("extmetadata", {})
    licence = (meta.get("LicenseShortName") or {}).get("value", "")
    if not ACCEPTED_LICENCE.match(licence):
        return None, f"license_rejected:{licence or 'unknown'}"

    mime = info.get("mime", "")
    ext = EXT_FOR_MIME.get(mime)
    if not ext:
        return None, f"unsupported_mime:{mime}"

    # SVGs are served as-is; raster files come as a bounded thumbnail.
    url = info["url"] if ext == "svg" else info.get("thumburl") or info["url"]
    credit = {
        "file": f"{kind}/{entity_id}.{ext}",
        "title": f"File:{filename}",
        "license": licence,
        "license_url": (meta.get("LicenseUrl") or {}).get("value") or None,
        "author": strip_html((meta.get("Artist") or {}).get("value")),
        "source_url": info.get("descriptionurl")
        or f"https://commons.wikimedia.org/wiki/File:{filename.replace(' ', '_')}",
        "_download": url,
    }
    return credit, "ok"


def download(client: Client, url: str, target: Path) -> Path:
    """Fetch to `target`; a photographic PNG is re-encoded as JPEG (a lossless portrait
    is megabytes for nothing). Returns the path actually written."""
    target.parent.mkdir(parents=True, exist_ok=True)
    response = client.get(url)
    if target.suffix == ".png" and target.parent.name == "drivers":
        from io import BytesIO

        from PIL import Image  # via matplotlib, already a dependency

        image = Image.open(BytesIO(response.content)).convert("RGB")
        target = target.with_suffix(".jpg")
        image.save(target, "JPEG", quality=85, optimize=True)
        return target
    target.write_bytes(response.content)
    return target


def entrants(client: Client, season: int) -> dict[str, list[tuple[str, str]]]:
    drivers = client.json(f"{JOLPICA}/{season}/driverStandings.json")
    teams = client.json(f"{JOLPICA}/{season}/constructorStandings.json")
    d_rows = drivers["MRData"]["StandingsTable"]["StandingsLists"][0]["DriverStandings"]
    t_rows = teams["MRData"]["StandingsTable"]["StandingsLists"][0]["ConstructorStandings"]
    return {
        "drivers": [(r["Driver"]["driverId"], r["Driver"]["url"]) for r in d_rows],
        "teams": [(r["Constructor"]["constructorId"], r["Constructor"]["url"]) for r in t_rows],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--only", choices=["drivers", "teams"])
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    parser.add_argument("--ids", nargs="*", help="only these driver/constructor ids")
    args = parser.parse_args()

    client = Client()
    try:
        lists = entrants(client, args.season)
    except Exception as exc:  # noqa: BLE001 - the one failure that should stop the run
        print(f"could not read the standings from Jolpica: {exc}", file=sys.stderr)
        return 1

    manifest: dict = {"generated": None, "drivers": {}, "teams": {}, "missing": {}}
    if MANIFEST.exists():
        manifest.update(json.loads(MANIFEST.read_text(encoding="utf-8")))

    for kind in ("drivers", "teams"):
        if args.only and args.only != kind:
            continue
        print(f"{kind}:")
        for entity_id, wiki_url in lists[kind]:
            if args.ids and entity_id not in args.ids:
                continue
            existing = manifest[kind].get(entity_id)
            if existing and not args.force and (ROOT / existing["file"]).exists():
                print(f"  {entity_id:<14} kept    {existing['file']}")
                continue
            # Re-resolving: drop the old file so a changed extension leaves no orphan.
            if existing:
                (ROOT / existing["file"]).unlink(missing_ok=True)
            manifest["missing"].pop(entity_id, None)
            try:
                credit, reason = resolve(client, kind, entity_id, wiki_url)
            except Exception as exc:  # noqa: BLE001 - one entrant must not sink the rest
                credit, reason = None, f"error:{type(exc).__name__}"
            if credit is None:
                manifest[kind][entity_id] = None
                manifest["missing"][entity_id] = reason
                print(f"  {entity_id:<14} missing {reason}")
                continue
            url = credit.pop("_download")
            written = download(client, url, ROOT / credit["file"])
            credit["file"] = written.relative_to(ROOT).as_posix()
            manifest[kind][entity_id] = credit
            print(f"  {entity_id:<14} ok      {credit['file']}  [{credit['license']}]")

    manifest["generated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    have = sum(1 for k in ("drivers", "teams") for v in manifest[k].values() if v)
    print(f"\n{have} images, {len(manifest['missing'])} missing -> {MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
