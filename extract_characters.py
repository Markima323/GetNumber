"""Generate characters.json from the upstream Vote2026 character roster.

Two upstream files are relevant:

* ``characterb.js``   - the *current contest stage* roster (40 candidates that
                       advanced to stage 6, etc.). This is what the website
                       actually shows during voting.
* ``characterOld.js`` - the full all-time roster (71 entries). Use only as a
                       fallback / cold-start.

Both look like:

    const characterData{Old} = [ {"id":1,"name":"...","gender":"...","image":"..."}, ... ];

We strip the JS wrapper and parse the rest as JSON.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

# The site advances through several stages, each backed by its own roster file
# (characterb.js → second round, characterc.js → revival, characterd.js →
# finals, etc.). Rather than hardcode the current one, we sniff index.html for
# whichever character*.js it currently loads. characterOld.js is the all-time
# fallback (71 entries).
INDEX_URL = "https://www.starrailawards.com/Vote2026/index.html"
STAGE_JS_RE = re.compile(
    r'src="(https://static\.appoint\.icu/Railvote/character[a-z]\.js[^"]*)"'
)
URL_FALLBACK = "https://static.appoint.icu/Railvote/characterOld.js?v=44"
OUT_PATH = Path(__file__).parent / "characters.json"


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Encoding": "identity",     # don't ask the server to gzip
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
        return raw.decode("utf-8")


def parse(js: str) -> list[dict]:
    body = re.sub(r"^\s*const\s+characterData(?:Old)?\s*=\s*", "", js)
    body = body.rstrip().rstrip(";")
    return json.loads(body)


def discover_current_url() -> str:
    """Scrape index.html for the current-stage character roster URL.

    Each contest stage swaps in a different ``character[a-z].js`` file. We pick
    the last match in the document — if multiple are referenced, the later one
    overrides earlier ones because that's how the page's <script> tags load.
    """
    html = fetch(INDEX_URL)
    matches = STAGE_JS_RE.findall(html)
    if not matches:
        raise RuntimeError(
            "no character[a-z].js reference found in index.html; site layout "
            "may have changed"
        )
    return matches[-1]


def slim(data: list[dict]) -> list[dict]:
    return [
        {
            "id": c["id"],
            "name": c["name"],
            "group": c.get("group", ""),
            "gender": c.get("gender", "unknown"),
            "image": c.get("image", ""),
        }
        for c in data
    ]


def write(data: list[dict]) -> None:
    OUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def fetch_current() -> list[dict]:
    """Fetch + parse the current-stage roster. Raises on any failure."""
    return slim(parse(fetch(discover_current_url())))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--full",
        action="store_true",
        help="Use the all-time roster (characterOld.js, 71 entries) instead "
             "of the current stage roster auto-detected from index.html.",
    )
    args = ap.parse_args()

    if args.full:
        url = URL_FALLBACK
    else:
        url = discover_current_url()
    print(f"Fetching {url} ...")
    data = slim(parse(fetch(url)))
    write(data)
    print(f"Wrote {len(data)} characters -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
