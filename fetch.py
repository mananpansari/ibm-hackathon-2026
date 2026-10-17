"""Cached Blockscout PRO API client (Etherscan-style module/action calls).

Every response is cached in SQLite keyed by the URL *without* the key, so no URL
is fetched twice. Throttled to 4 req/s, backs off on 429, logs x-credits-remaining,
and refuses bulk calls once credits drop below 1,000.

    python fetch.py   # one test call; prints the response and credits left
"""
import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

BASE = "https://api.blockscout.com/v2/api"
CHAIN = {"chain_id": "1"}  # PRO docs: chain_id (Etherscan V2 says chainid); confirmed by the test call
MIN_CREDITS = 1000
MIN_GAP_S = 0.25  # 4 requests/s
HERE = Path(__file__).resolve().parent
CACHE = HERE / "data" / "blockscout_cache.sqlite"

log = logging.getLogger("fetch")
credits_left = None  # last x-credits-remaining seen
calls = 0  # network calls made by this process
_last = 0.0
_db = None


def _key():
    key = os.environ.get("BLOCKSCOUT_API_KEY")
    env = HERE / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "BLOCKSCOUT_API_KEY":
                key = value.strip().strip("'\"")
    if not key:
        raise SystemExit("BLOCKSCOUT_API_KEY missing: put it in .env or the environment")
    return key


def _cache():
    global _db
    if _db is None:
        CACHE.parent.mkdir(exist_ok=True)
        _db = sqlite3.connect(CACHE, timeout=60)
        _db.execute("PRAGMA journal_mode=WAL")  # readers (analysis, the live box) never block the pull
        _db.execute("CREATE TABLE IF NOT EXISTS cache (url TEXT PRIMARY KEY, body TEXT, fetched_at REAL)")
    return _db


def get(bulk=True, **params):
    """GET BASE?chain_id=1&<params>; returns the parsed JSON. bulk=False for the live box."""
    global credits_left, calls, _last
    url = BASE + "?" + urllib.parse.urlencode({**CHAIN, **params})
    db = _cache()
    row = db.execute("SELECT body FROM cache WHERE url = ?", (url,)).fetchone()
    if row:  # zlib-compressed (responses are ~10x smaller); older rows are plain text
        return json.loads(row[0] if isinstance(row[0], str) else zlib.decompress(row[0]))
    if bulk and credits_left is not None and credits_left < MIN_CREDITS:
        raise RuntimeError(f"only {credits_left} credits left; bulk pulls stopped")
    full = url + "&" + urllib.parse.urlencode({"apikey": _key()})
    for attempt in range(6):
        time.sleep(max(0.0, _last + MIN_GAP_S - time.monotonic()))
        _last = time.monotonic()
        try:
            # Cloudflare answers Python's default User-Agent with 403 "error code: 1010"
            req = urllib.request.Request(full, headers={"User-Agent": "score-before-you-sign/0.1"})
            with urllib.request.urlopen(req, timeout=60) as r:
                body, headers = r.read().decode(), r.headers
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                wait = 2 ** attempt
                log.warning("HTTP %s on %s; retrying in %ss", e.code, url, wait)
                time.sleep(wait)
                continue
            # ponytail: raise from None so the traceback never carries the keyed URL
            raise RuntimeError(f"HTTP {e.code} on {url}: {e.read()[:300]!r}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            log.warning("%s on %s; retrying", type(e).__name__, url)
            time.sleep(2 ** attempt)
            continue
        calls += 1
        if headers.get("x-credits-remaining"):
            credits_left = int(float(headers["x-credits-remaining"]))
        log.info("call %d  credits=%s  %s", calls, credits_left, url)
        data = json.loads(body)
        # Cache real answers, including empty lists ("No transactions found"); never errors.
        if isinstance(data.get("result"), list) or data.get("status") == "1":
            db.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)", (url, zlib.compress(body.encode()), time.time()))
            db.commit()
        else:
            log.warning("not cached (%s): %s", data.get("message"), url)
        return data
    raise RuntimeError(f"gave up after retries: {url}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    # One cheap test call: the block at 2024-01-01 00:00 UTC.
    print(get(module="block", action="getblocknobytime", timestamp=1704067200, closest="after"))
    print("credits left:", credits_left)
