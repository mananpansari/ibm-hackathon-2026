"""Cached Blockscout PRO API client (Etherscan-style module/action calls).

Every response is cached in SQLite keyed by the URL *without* the key, so no URL
is fetched twice. Throttled to 4 req/s across threads, logs x-credits-remaining.

Two modes:
- bulk (default; snapshot.py): retries 429/5xx/network errors with backoff, 60 s timeout,
  refuses new calls once credits drop below MIN_CREDITS (1,000).
- live (bulk=False; the "paste an address" box): one attempt, LIVE_TIMEOUT_S timeout, no
  retries, still allowed down to LIVE_MIN_CREDITS (100) so the box stays up for the judges.

Failures raise FetchError (a RuntimeError). Cache hits cost no credits and no throttle wait.
The API key never appears in a cache row, log line, exception or return value.

    python fetch.py   # one test call; prints the response and credits left
"""
import json
import logging
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

BASE = "https://api.blockscout.com/v2/api"
CHAIN = {"chain_id": "1"}  # PRO docs: chain_id (Etherscan V2 says chainid); confirmed by the test call
MIN_CREDITS = 1000  # bulk pulls stop below this
LIVE_MIN_CREDITS = 100  # live lookups stop below this
MIN_GAP_S = 0.25  # 4 requests/s
LIVE_TIMEOUT_S = 6  # under app.py's 8 s wait, so the live box answers instead of hanging
HERE = Path(__file__).resolve().parent
CACHE = HERE / "data" / "blockscout_cache.sqlite"
ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
ADDRESS_PARAMS = ("address", "contractaddress")

log = logging.getLogger("fetch")
credits_left = None  # last x-credits-remaining seen
calls = 0  # network calls made by this process
_last = 0.0  # monotonic time of the last reserved request slot
_lock = threading.Lock()  # guards credits_left, calls, _last
_local = threading.local()  # one SQLite connection per thread (FastAPI calls from a pool)
_urlopen = urllib.request.urlopen  # the HTTP seam; tests replace it
_apikey = None


class FetchError(RuntimeError):
    """A failed call. The message never contains the key; RuntimeError so old callers still catch it."""


class OutOfCredits(FetchError):
    pass


class LiveTimeout(FetchError):
    """No answer in LIVE_TIMEOUT_S; on tokentx usually too much history (exchange hot wallets)."""


def wallet(addr):
    """'0x' + 40 hex chars, lowercased (checksummed input is fine); anything else -> ValueError."""
    if not isinstance(addr, str) or not ADDRESS.fullmatch(addr.strip()):
        raise ValueError("not an Ethereum address (0x followed by 40 hex characters)")
    return addr.strip().lower()


def _key():
    global _apikey
    if _apikey:
        return _apikey
    key = os.environ.get("BLOCKSCOUT_API_KEY")
    env = HERE / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "BLOCKSCOUT_API_KEY":
                key = value.strip().strip("'\"")
    if not key:
        raise SystemExit("BLOCKSCOUT_API_KEY missing: put it in .env or the environment")
    _apikey = key
    return key


def _scrub(text):
    """Text that came back from the network (error bodies, reasons) with the key masked."""
    text = text.decode(errors="replace") if isinstance(text, bytes) else str(text)
    return text.replace(_apikey, "***") if _apikey else text


def _cache():
    db = getattr(_local, "db", None)
    if db is None or _local.path != CACHE:
        CACHE.parent.mkdir(exist_ok=True)
        db = sqlite3.connect(CACHE, timeout=60)
        db.execute("PRAGMA journal_mode=WAL")  # readers (analysis, the live box) never block the pull
        db.execute("CREATE TABLE IF NOT EXISTS cache (url TEXT PRIMARY KEY, body TEXT, fetched_at REAL)")
        _local.db, _local.path = db, CACHE
    return db


def _check(floor, what):
    if credits_left is not None and credits_left < floor:
        raise OutOfCredits(f"only {credits_left} credits left; {what} stopped")


def _wait_turn(floor, what):
    """Re-check credits and reserve the next 4 req/s slot under the lock, then sleep until it."""
    global _last
    with _lock:
        _check(floor, what)
        _last = slot = max(time.monotonic(), _last + MIN_GAP_S)
    time.sleep(max(0.0, slot - time.monotonic()))


def get(bulk=True, **params):
    """GET BASE?chain_id=1&<params>; returns the parsed JSON. bulk=False for the live box."""
    global credits_left, calls
    if "apikey" in params:
        raise ValueError("fetch.py adds the key itself")
    for p in ADDRESS_PARAMS:
        if p in params:
            params[p] = wallet(params[p])
    url = BASE + "?" + urllib.parse.urlencode({**CHAIN, **params})  # also the cache key: no key in it
    db = _cache()
    row = db.execute("SELECT body FROM cache WHERE url = ?", (url,)).fetchone()
    if row:  # zlib-compressed (responses are ~10x smaller); older rows are plain text
        return json.loads(row[0] if isinstance(row[0], str) else zlib.decompress(row[0]))
    floor, what = (MIN_CREDITS, "bulk pulls") if bulk else (LIVE_MIN_CREDITS, "live lookups")
    _check(floor, what)
    try:
        full = url + "&" + urllib.parse.urlencode({"apikey": _key()})
    except SystemExit:
        if bulk:
            raise
        raise FetchError("no Blockscout key on this server") from None
    for attempt in range(6 if bulk else 1):
        _wait_turn(floor, what)
        try:
            # Cloudflare answers Python's default User-Agent with 403 "error code: 1010"
            req = urllib.request.Request(full, headers={"User-Agent": "score-before-you-sign/0.1"})
            with _urlopen(req, timeout=60 if bulk else LIVE_TIMEOUT_S) as r:
                body, headers = r.read().decode(), r.headers
        except urllib.error.HTTPError as e:
            if bulk and (e.code == 429 or e.code >= 500):
                wait = 2 ** attempt
                log.warning("HTTP %s on %s; retrying in %ss", e.code, url, wait)
                time.sleep(wait)
                continue
            # raise from None so the traceback never carries the keyed URL
            raise FetchError(f"HTTP {e.code} on {url}: {_scrub(e.read()[:300])!r}") from None
        except (urllib.error.URLError, OSError) as e:  # TimeoutError is an OSError
            reason = getattr(e, "reason", e)
            if not bulk:
                timed_out = isinstance(e, TimeoutError) or isinstance(reason, TimeoutError) or "timed out" in str(reason)
                cls, what_failed = (LiveTimeout, "timed out") if timed_out else (FetchError, "network error")
                raise cls(f"{what_failed} on {url}: {_scrub(reason)}") from None
            log.warning("%s on %s; retrying", type(e).__name__, url)
            time.sleep(2 ** attempt)
            continue
        with _lock:
            calls += 1
            if headers.get("x-credits-remaining"):
                credits_left = int(float(headers["x-credits-remaining"]))
            n, left = calls, credits_left
        log.info("call %d  credits=%s  %s", n, left, url)
        try:
            data = json.loads(body)
        except ValueError:
            raise FetchError(f"non-JSON answer on {url}: {_scrub(body[:120])!r}") from None
        # Cache real answers, including empty lists ("No transactions found"); never errors.
        if isinstance(data, dict) and (isinstance(data.get("result"), list) or data.get("status") == "1"):
            db.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)", (url, zlib.compress(body.encode()), time.time()))
            db.commit()
        else:
            log.warning("not cached (%s): %s", data.get("message") if isinstance(data, dict) else "?", url)
        return data
    raise FetchError(f"gave up after retries: {url}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    # One cheap test call: the block at 2024-01-01 00:00 UTC.
    print(get(module="block", action="getblocknobytime", timestamp=1704067200, closest="after"))
    print("credits left:", credits_left)
