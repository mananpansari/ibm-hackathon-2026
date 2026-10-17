"""Checks for fetch.py and snapshot's live lookup. No network: the HTTP seam (fetch._urlopen) is faked
and the cache is a temporary SQLite file.

    python tests/test_fetch.py
"""
import io
import json
import logging
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fetch  # noqa: E402
import snapshot  # noqa: E402

KEY = "SECRET-test-key-123"
A = "0x" + "ab" * 20
CHECKSUMMED = "0xAbAbAbAbAbAbAbAbAbAbAbAbAbAbAbAbAbAbAbAb"
LOGS = io.StringIO()


class Resp:
    def __init__(self, body, credits=5000):
        self.body, self.headers = body.encode(), {"x-credits-remaining": str(credits)}

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeHTTP:
    """Answers in order from `script`; each item is a body (str/dict) or an exception to raise."""
    def __init__(self, *script, credits=5000):
        self.script, self.credits, self.urls, self.timeouts, self.times = list(script), credits, [], [], []
        self.lock = threading.Lock()

    def __call__(self, req, timeout):
        with self.lock:
            self.urls.append(req.full_url)
            self.timeouts.append(timeout)
            self.times.append(time.monotonic())
            item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, BaseException):
            raise item
        return Resp(item if isinstance(item, str) else json.dumps(item), self.credits)


def tx(i, frm="0x" + "11" * 20, to=A):
    return {"timeStamp": str(1_700_000_000 + i), "from": frm, "to": to, "value": str(50_000_000),
            "nonce": str(i), "hash": "0x%064x" % i}


def ok(rows):
    return {"status": "1" if rows else "0", "message": "OK" if rows else "No token transfers found", "result": rows}


def fresh(http, credits=None):
    """Reset fetch's state onto a new empty cache and the given fake HTTP."""
    fetch.CACHE = Path(tempfile.mkdtemp()) / "cache.sqlite"
    fetch._urlopen, fetch.credits_left, fetch.calls, fetch._last = http, credits, 0, 0.0
    fetch._apikey = KEY
    return http


def rows_in_cache():
    return sqlite3.connect(fetch.CACHE).execute("SELECT url, body FROM cache").fetchall()


def check_credit_floors():  # 1
    fresh(FakeHTTP(ok([tx(1)])), credits=900)
    try:
        fetch.get(module="account", action="tokentx", address=A)
        raise AssertionError("bulk call allowed at 900 credits")
    except fetch.OutOfCredits:
        pass
    r = snapshot.live_history(A)
    assert r["status"] == "ok" and len(r["history"]["transfers"]) == 1, r
    assert snapshot.history(A, "live", 1000)["transfers"], "app.py's call must use the live path"
    fresh(FakeHTTP(ok([tx(1)])), credits=50)
    assert snapshot.live_history(A)["status"] == "no_credits"
    assert fetch._urlopen.urls == [], "no network call below the live floor"
    # ...but a cached answer still works at 50
    fresh(FakeHTTP(ok([tx(1)])), credits=5000)
    snapshot.live_history(A)
    fetch.credits_left = 50
    assert snapshot.live_history(A)["status"] == "ok"
    assert snapshot.history(A, "train_pos", 1000) is not None, "bulk cache hits still served below the floor"


def check_validation():  # 2
    http = fresh(FakeHTTP(ok([])))
    for bad in ("", "0x123", "ab" * 21, "0x" + "g" * 40, A + "&apikey=x", A + "\n0x", None, "0x" + "a" * 41):
        assert snapshot.live_history(bad)["status"] == "invalid", bad
        try:
            fetch.get(bulk=False, module="account", action="tokentx", address=bad)
            raise AssertionError(f"accepted {bad!r}")
        except ValueError:
            pass
    assert http.urls == []
    r = snapshot.live_history(CHECKSUMMED)
    assert r["history"]["address"] == A and "address=" + A in http.urls[0], http.urls
    try:
        fetch.get(module="x", apikey="y")
        raise AssertionError("apikey param accepted")
    except ValueError:
        pass


def check_hot_wallets():  # 3
    http = fresh(FakeHTTP(urllib.error.URLError(TimeoutError("timed out")), ok([tx(1)])))
    t = time.monotonic()
    r = snapshot.live_history(A)
    assert r["status"] == "too_much_history" and r["history"] is None, r
    assert time.monotonic() - t < 1, "live lookups don't retry or back off"
    assert http.timeouts == [fetch.LIVE_TIMEOUT_S] and fetch.LIVE_TIMEOUT_S < 8
    assert rows_in_cache() == [], "a timeout is never cached"
    assert snapshot.live_history(A)["status"] == "ok", "the next lookup tries again"
    fresh(FakeHTTP(TimeoutError("The read operation timed out")))
    assert snapshot.live_history(A)["status"] == "too_much_history"
    fresh(FakeHTTP({"status": "0", "message": "Query timeout", "result": None}))
    assert snapshot.live_history(A)["status"] == "too_much_history" and rows_in_cache() == []
    fresh(FakeHTTP(urllib.error.HTTPError("u", 503, "busy", {}, io.BytesIO(b"busy"))))
    assert snapshot.live_history(A)["status"] == "unavailable" and len(fetch._urlopen.urls) == 1
    fresh(FakeHTTP("<html>cloudflare</html>"))
    assert snapshot.live_history(A)["status"] == "unavailable" and rows_in_cache() == []
    fresh(FakeHTTP(urllib.error.URLError("Name or service not known")))
    assert snapshot.live_history(A)["status"] == "unavailable"
    fetch._apikey = None  # no key on the server: unavailable, not SystemExit
    import os
    saved, os.environ["BLOCKSCOUT_API_KEY"] = os.environ.get("BLOCKSCOUT_API_KEY"), ""
    real_here, fetch.HERE = fetch.HERE, Path(tempfile.mkdtemp())
    try:
        assert snapshot.live_history(A)["status"] == "unavailable"
    finally:
        fetch.HERE = real_here
        if saved is None:
            del os.environ["BLOCKSCOUT_API_KEY"]
        else:
            os.environ["BLOCKSCOUT_API_KEY"] = saved


def check_contracts_and_empty():  # 4
    http = fresh(FakeHTTP(ok([])))
    for addr in (snapshot.USDT, "0x" + "0" * 40):
        assert snapshot.live_history(addr)["status"] == "not_a_wallet"
    assert http.urls == []
    r = snapshot.live_history(A)
    assert r["status"] == "no_transfers" and r["history"]["transfers"] == [] and not r["history"]["truncated"], r
    assert len(rows_in_cache()) == 1, "an empty answer is a real answer: cached"


def check_cache():  # 5, 6
    http = fresh(FakeHTTP(ok([tx(1)])))
    snapshot.live_history(A)
    fetch._last = time.monotonic() + 10  # a hit must not wait for the throttle
    t = time.monotonic()
    assert snapshot.live_history(A)["status"] == "ok"
    assert time.monotonic() - t < 0.5 and len(http.urls) == 1 and fetch.calls == 1
    (url, body), = rows_in_cache()
    assert KEY not in url and "apikey" not in url and KEY.encode() not in body
    assert KEY in http.urls[0], "the key is sent to Blockscout"


def check_secrets():  # 6
    leak = urllib.error.HTTPError("u", 401, "no", {}, io.BytesIO(f"bad apikey {KEY}".encode()))
    for http in (FakeHTTP(leak), FakeHTTP(urllib.error.URLError(f"refused {KEY}")), FakeHTTP(f"oops {KEY}")):
        fresh(http)
        LOGS.truncate(0)
        r = snapshot.live_history(A)
        assert r["status"] == "unavailable" and KEY not in json.dumps(r), r
        try:
            fetch.get(bulk=False, module="account", action="tokentx", address="0x" + "cd" * 20)
            raise AssertionError("expected an error")
        except fetch.FetchError as e:
            assert KEY not in str(e) and e.__cause__ is None and e.__suppress_context__, e
        assert KEY not in LOGS.getvalue()
    fresh(FakeHTTP(ok([tx(1)])))
    LOGS.truncate(0)
    snapshot.live_history(A)
    assert KEY not in LOGS.getvalue() and "call 1" in LOGS.getvalue()


def check_threads():  # 7
    n = 8
    http = fresh(FakeHTTP(ok([tx(1)]), credits=4000))
    out, errors = [], []

    def one(i):
        try:
            out.append(snapshot.live_history("0x%040x" % (i + 1))["status"])
        except Exception as e:  # a shared SQLite connection used to fail here from a second thread
            errors.append(e)
    ts = [threading.Thread(target=one, args=(i,)) for i in range(n)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors and out == ["ok"] * n, (errors, out)
    gaps = [b - a for a, b in zip(sorted(http.times), sorted(http.times)[1:])]
    assert min(gaps) >= fetch.MIN_GAP_S - 0.01, gaps
    assert fetch.calls == n and fetch.credits_left == 4000


def check_truncation():  # 8
    rows = [tx(i) for i in range(1000)]
    fresh(FakeHTTP(ok(rows)))
    live = snapshot.live_history(A)["history"]
    fresh(FakeHTTP(ok(rows)))
    bulk = snapshot.history(A, "test_pos", 1000, freeze_ts=123)
    assert live["truncated"] and bulk["truncated"] and live["transfers"] == bulk["transfers"]
    assert {**live, "group": "test_pos", "freeze_ts": 123} == bulk
    fresh(FakeHTTP(ok(rows[:999])))
    assert not snapshot.live_history(A)["history"]["truncated"]


def check_bulk_unchanged():
    http = fresh(FakeHTTP(urllib.error.HTTPError("u", 429, "slow", {}, io.BytesIO(b"")), ok([tx(1)])))
    real_sleep, slept = time.sleep, []
    fetch.time.sleep = lambda s: slept.append(s)
    try:
        h = snapshot.history(A, "train_pos", 1000)
    finally:
        fetch.time.sleep = real_sleep
    assert h and len(http.urls) == 2 and http.timeouts == [60, 60] and 1 in slept, (http.urls, slept)


def _self_check():
    handler = logging.StreamHandler(LOGS)
    for name in ("fetch", "snapshot"):
        logging.getLogger(name).addHandler(handler)
        logging.getLogger(name).setLevel(logging.INFO)
    for check in (check_credit_floors, check_validation, check_hot_wallets, check_contracts_and_empty,
                  check_cache, check_secrets, check_threads, check_truncation, check_bulk_unchanged):
        check()
        print("ok", check.__name__)
    print("fetch self-check passed (no network calls)")


if __name__ == "__main__":
    _self_check()
