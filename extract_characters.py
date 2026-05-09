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

# characterb.js has no version query string; characterOld.js currently is v=44
URL_CURRENT = "https://static.appoint.icu/Railvote/characterb.js"
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
    return slim(parse(fetch(URL_CURRENT)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--full",
        action="store_true",
        help="Use the all-time roster (characterOld.js, 71 entries) instead of "
             "the current stage roster (characterb.js, ~40 entries).",
    )
    args = ap.parse_args()

    url = URL_FALLBACK if args.full else URL_CURRENT
    print(f"Fetching {url} ...")
    data = slim(parse(fetch(url)))
    write(data)
    print(f"Wrote {len(data)} characters -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
