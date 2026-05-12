"""Star Rail Awards 2026 vote tracker.

Polls https://www.starrailawards.com/Active2551/GetData every POLL_INTERVAL
seconds, persists each new value to SQLite, and serves a Flask dashboard with a
character selector and a live multi-color line chart.

Run: python app.py   (then open http://127.0.0.1:5000)
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template, request

import extract_characters

# ---------------------------------------------------------------- config
ROOT = Path(__file__).parent
DB_PATH = ROOT / "votes.db"
CHARACTERS_PATH = ROOT / "characters.json"

POLL_INTERVAL = 10                          # seconds between scrapes
ROSTER_REFRESH_INTERVAL = 3600              # re-pull characterb.js once per hour
SITE_BASE = "https://www.starrailawards.com"
ENDPOINT = f"{SITE_BASE}/Active2551/GetData"
HTTP_TIMEOUT = 15

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": SITE_BASE,
    "Referer": f"{SITE_BASE}/Vote2026/index.html",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("vote_tracker")


# ---------------------------------------------------------------- characters
class Roster:
    """Mutable holder for the current-stage character roster.

    The roster changes between contest stages (~40 in stage 6, fewer later).
    We refresh it from the upstream characterb.js periodically so the dashboard
    stays correct without restarting.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.list: list[dict] = []
        self.by_id: dict[int, dict] = {}
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if CHARACTERS_PATH.exists():
            with CHARACTERS_PATH.open(encoding="utf-8") as f:
                self._set(json.load(f))

    def _set(self, data: list[dict]) -> None:
        with self.lock:
            self.list = data
            self.by_id = {c["id"]: c for c in data}

    def refresh_from_upstream(self) -> bool:
        """Try to fetch + persist the latest roster. Returns True on change."""
        try:
            data = extract_characters.fetch_current()
        except Exception as e:                    # noqa: BLE001
            log.warning("roster refresh failed: %s", e)
            return False
        if data == self.list:
            return False
        self._set(data)
        CHARACTERS_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.info("roster updated: %d characters", len(data))
        return True


ROSTER = Roster()


# ---------------------------------------------------------------- storage
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with closing(db()) as conn, conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS votes (
                ts          INTEGER NOT NULL,
                vote_id     INTEGER NOT NULL,
                vote_count  INTEGER NOT NULL,
                PRIMARY KEY (vote_id, ts)
            );
            CREATE INDEX IF NOT EXISTS idx_votes_ts ON votes(ts);
            CREATE TABLE IF NOT EXISTS scraper_status (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )


def get_last_counts() -> dict[int, int]:
    sql = """
        SELECT v.vote_id, v.vote_count
        FROM votes v
        JOIN (
            SELECT vote_id, MAX(ts) AS ts FROM votes GROUP BY vote_id
        ) latest ON v.vote_id = latest.vote_id AND v.ts = latest.ts
    """
    with closing(db()) as conn:
        return {row[0]: row[1] for row in conn.execute(sql)}


def save_snapshot(ts: int, counts: dict[int, int], last_counts: dict[int, int]) -> int:
    rows = [
        (ts, vid, c)
        for vid, c in counts.items()
        if last_counts.get(vid) != c
    ]
    if not rows:
        return 0
    with closing(db()) as conn, conn:
        conn.executemany(
            "INSERT OR IGNORE INTO votes(ts, vote_id, vote_count) VALUES (?, ?, ?)",
            rows,
        )
    return len(rows)


def set_status(**kv) -> None:
    with closing(db()) as conn, conn:
        conn.executemany(
            "INSERT OR REPLACE INTO scraper_status(key, value) VALUES (?, ?)",
            [(k, str(v)) for k, v in kv.items()],
        )


def get_status() -> dict[str, str]:
    with closing(db()) as conn:
        return {k: v for k, v in conn.execute("SELECT key, value FROM scraper_status")}


# ---------------------------------------------------------------- scraper
def fetch_once(session: requests.Session) -> tuple[dict[int, int], dict]:
    """Hit /Active2551/GetData and return (counts_by_char_id, raw_meta).

    The response shape is:
      {"errCode":0,"data":{
          "stage":6, "activeStage":0,
          "vote":{"lstV":[{"s":<char_id>,"c":<count>,"i":<voted>}, ...],
                  "rq":<popularity>, ...}
       }}
    Sometimes data.vote is missing and the lstV lives directly on data.
    """
    r = session.post(ENDPOINT, headers=HEADERS, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    payload = r.json()
    if payload.get("errCode") != 0:
        raise RuntimeError(f"errCode {payload.get('errCode')}: {payload.get('msg')}")

    data = payload.get("data") or {}
    vote = data.get("vote") or data
    lst = vote.get("lstV") or []
    counts = {item["s"]: item.get("c", 0) for item in lst if "s" in item}

    meta = {
        "stage": data.get("stage", 0),
        "active_stage": data.get("activeStage", 0),
        "rq": vote.get("rq", 0),
    }
    return counts, meta


def scraper_loop(stop: threading.Event) -> None:
    log.info("scraper started, interval=%ss, endpoint=%s", POLL_INTERVAL, ENDPOINT)
    session = requests.Session()
    last_counts = get_last_counts()
    next_roster_refresh = 0.0  # refresh on first iteration

    while not stop.is_set():
        started = time.time()
        ts = int(started)

        if started >= next_roster_refresh:
            ROSTER.refresh_from_upstream()
            next_roster_refresh = started + ROSTER_REFRESH_INTERVAL

        try:
            counts, meta = fetch_once(session)
            inserted = save_snapshot(ts, counts, last_counts) if counts else 0
            last_counts.update(counts)
            set_status(
                last_ts=ts,
                last_inserted=inserted,
                last_total=len(counts),
                stage=meta["stage"],
                active_stage=meta["active_stage"],
                last_error="",
            )
            if not counts:
                log.info(
                    "ts=%s lstV empty (stage=%s active=%s) — voting not open yet",
                    ts, meta["stage"], meta["active_stage"],
                )
            elif inserted:
                log.info(
                    "ts=%s wrote %d/%d rows (stage=%s active=%s)",
                    ts, inserted, len(counts), meta["stage"], meta["active_stage"],
                )
        except Exception as e:                # noqa: BLE001
            log.exception("scrape error: %s", e)
            set_status(last_error=str(e))

        elapsed = time.time() - started
        stop.wait(max(0.0, POLL_INTERVAL - elapsed))
    log.info("scraper stopped")


# ---------------------------------------------------------------- web
app = Flask(__name__, template_folder="templates", static_folder="static")
# Dev convenience: don't cache static files, so HTML/JS/CSS edits show up
# on a normal reload (otherwise stale assets confuse "why isn't my change live").
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


@app.after_request
def _no_cache(resp):
    if request.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/")
def index():
    return render_template("index.html", poll_interval=POLL_INTERVAL)


@app.get("/api/characters")
def api_characters():
    """Return characters in the current contest stage with latest counts.

    The roster is whatever characterb.js currently advertises (auto-refreshed
    once an hour by the scraper). vote_count is the latest value we observed,
    or 0 if we've never recorded a count for that character yet.
    """
    last = get_last_counts()
    with ROSTER.lock:
        roster = list(ROSTER.list)
    return jsonify(
        [{**c, "vote_count": last.get(c["id"], 0)} for c in roster]
    )


@app.get("/api/series")
def api_series():
    raw = request.args.get("ids", "").strip()
    if not raw:
        return jsonify({})
    try:
        ids = [int(x) for x in raw.split(",") if x]
    except ValueError:
        return jsonify({"error": "ids must be integers"}), 400
    since = int(request.args.get("since", 0) or 0)

    placeholders = ",".join("?" * len(ids))
    sql = (
        f"SELECT vote_id, ts, vote_count FROM votes "
        f"WHERE vote_id IN ({placeholders}) AND ts > ? ORDER BY ts"
    )
    out: dict[int, list[list[int]]] = {vid: [] for vid in ids}
    with closing(db()) as conn:
        for vid, ts, cnt in conn.execute(sql, (*ids, since)):
            out[vid].append([ts, cnt])
    return jsonify(out)


@app.get("/api/status")
def api_status():
    s = get_status()
    return jsonify(
        {
            "last_ts": int(s.get("last_ts", 0) or 0),
            "last_inserted": int(s.get("last_inserted", 0) or 0),
            "last_total": int(s.get("last_total", 0) or 0),
            "last_error": s.get("last_error", ""),
            "stage": int(s.get("stage", 0) or 0),
            "active_stage": int(s.get("active_stage", 0) or 0),
            "poll_interval": POLL_INTERVAL,
            "roster_size": len(ROSTER.list),
        }
    )


# ---------------------------------------------------------------- entry
def main() -> None:
    init_db()
    stop = threading.Event()
    t = threading.Thread(target=scraper_loop, args=(stop,), daemon=True, name="scraper")
    t.start()
    try:
        app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
    finally:
        stop.set()
        t.join(timeout=2)


if __name__ == "__main__":
    main()
