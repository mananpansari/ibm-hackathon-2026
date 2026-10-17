"""Snapshot: Tether freezes, positives, negatives, histories -> data/.

    python snapshot.py sample   # ~20 calls: freezes + a few wallets -> data/sample.csv
    python snapshot.py          # full pull, ~3,550 calls -> data/

Everything goes through fetch.py's cache, so a rerun only pays for what is missing.
Outputs: freezes.csv, known_bad.txt, ofac_eth.txt, histories/{train,test}_{pos,neg,negv}.jsonl.gz, features.csv.
"""
import csv
import functools
import gzip
import io
import json
import logging
import random
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone

import features as F
import fetch

USDT = "0xdac17f958d2ee523a2206206994597c13d831ec7"
ADDED_BLACKLIST = "0x42e160154868087d6bfdc0ca23d96a1c1cfa32f1b72ba9ba27b69b98a0d819dc"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
OFAC_URL = "https://raw.githubusercontent.com/0xB10C/ofac-sanctioned-digital-currency-addresses/lists/sanctioned_addresses_ETH.txt"
FESEVU_URL = "https://huggingface.co/datasets/fesevu/ethereum_fraud_dataset_by_activity/resolve/main/addr_labels_balanced.csv.zst"


def utc(*d):
    return int(datetime(*d, tzinfo=timezone.utc).timestamp())


T_TRAIN, T_TEST, T_END = utc(2024, 1, 1), utc(2026, 7, 1), utc(2026, 10, 17)  # fixed so cached URLs repeat
POS_BUDGET = 1300  # positive tokentx calls (all test wallets, then training wallets)
NEG_PER_GROUP, NEG_MAX_TRANSFERS, NEG_CALL_CAP = 1000, 300, 1100
WINDOWS, WINDOW_BLOCKS, PER_WINDOW = 25, 100, 60  # random getLogs windows per negative group
MATCHED_TEST, MATCHED_TRAIN = 550, 450  # volume-matched comparison wallets (calls)
CALL_BUDGET = 3600
DATA = fetch.HERE / "data"
log = logging.getLogger("snapshot")


def over_budget():
    low = fetch.credits_left is not None and fetch.credits_left < fetch.MIN_CREDITS
    if fetch.calls >= CALL_BUDGET or low:
        log.warning("budget reached (calls %d, credits %s); stopping this stage", fetch.calls, fetch.credits_left)
    return fetch.calls >= CALL_BUDGET or low


def download(url, name):
    path = DATA / name
    if not path.exists():
        log.info("downloading %s", url)
        urllib.request.urlretrieve(url, path)
    return path


def freezes():
    """Every AddedBlackList event, earliest per address. All time (not just 2024+), so that
    'frozen before as_of' is complete for touched_known_bad; costs a few extra calls."""
    out, frm = {}, 0
    while True:
        logs = fetch.get(module="logs", action="getLogs", address=USDT, topic0=ADDED_BLACKLIST,
                         fromBlock=frm, toBlock="latest")["result"]
        assert isinstance(logs, list), logs
        for l in logs:
            a, ts = "0x" + l["data"][-40:].lower(), int(l["timeStamp"], 0)
            if a not in out or ts < out[a]["freeze_ts"]:
                out[a] = {"address": a, "freeze_ts": ts, "block": int(l["blockNumber"], 0), "tx_hash": l["transactionHash"]}
        prev, frm = frm, int(logs[-1]["blockNumber"], 0) if logs else frm
        if len(logs) < 1000 or frm == prev:
            return out


def ofac():
    return {l.strip().lower() for l in download(OFAC_URL, "ofac_eth.txt").read_text().splitlines() if l.startswith("0x")}


def known_bad():
    """fesevu scam labels (is_scam = 1); merges Kaggle, XBlock, ScamSniffer, Etherscan, CryptoScamDB."""
    txt = DATA / "known_bad.txt"
    if not txt.exists():
        import zstandard  # only needed once, to unpack the download
        with open(download(FESEVU_URL, "addr_labels_balanced.csv.zst"), "rb") as f:
            rows = csv.DictReader(io.TextIOWrapper(zstandard.ZstdDecompressor().stream_reader(f), "utf-8"))
            txt.write_text("".join(r["address"].lower() + "\n" for r in rows if r["is_scam"].strip() in ("1", "1.0", "True")))
    return set(txt.read_text().split())


def _tokentx(addr, offset, bulk):
    return fetch.get(bulk=bulk, module="account", action="tokentx", contractaddress=USDT, address=addr,
                     sort="asc", page=1, offset=offset)


def _as_history(addr, group, offset, freeze_ts, rows):
    txs = [{"ts": int(t["timeStamp"]), "from": t["from"].lower(), "to": t["to"].lower(),
            "usdt": int(t["value"]) / 1e6, "nonce": int(t["nonce"]), "hash": t["hash"]} for t in rows]
    return {"address": addr, "group": group, "freeze_ts": freeze_ts, "truncated": len(rows) >= offset, "transfers": txs}


def history(addr, group, offset, freeze_ts=None):
    """One ascending USDT tokentx call. truncated = there may be more than `offset` transfers.
    group "live" goes through live_history (live credit floor, short timeout); None if it failed."""
    if group == "live":
        return live_history(addr, offset)["history"]
    try:
        rows = _tokentx(addr, offset, bulk=True).get("result")
    except RuntimeError as e:  # one bad wallet must not stop the pull; a rerun retries it
        rows = str(e)
    if not isinstance(rows, list):
        log.warning("no history for %s: %s", addr, str(rows)[:120])
        return None
    return _as_history(addr, group, offset, freeze_ts, rows)


LIVE_MESSAGES = {
    "ok": "USDT history fetched live from Blockscout",
    "no_transfers": "no USDT transfers to or from this address",
    "not_a_wallet": "this is a token contract or the zero address, not a wallet",
    "too_much_history": "too much history to score live (likely an exchange or service wallet), or Blockscout is slow",
    "no_credits": "the live Blockscout budget is used up",
    "unavailable": "Blockscout is unavailable right now",
    "invalid": "not an Ethereum address (0x followed by 40 hex characters)",
}


def live_history(addr, offset=1000):
    """The live box's lookup; never raises. Returns {status, message, history}, with history the same
    shape as the snapshot's (group "live", truncated at `offset` exactly as there) or None.
    status: ok | no_transfers | not_a_wallet | too_much_history | no_credits | unavailable | invalid."""
    def out(status, h=None, detail=None):
        if detail:
            log.warning("live %s: %s (%s)", addr, status, detail)
        return {"status": status, "message": LIVE_MESSAGES[status], "history": h}
    try:
        addr = fetch.wallet(addr)
    except ValueError:
        return out("invalid")
    if addr in (USDT, "0x" + "0" * 40):
        return out("not_a_wallet")
    try:
        data = _tokentx(addr, offset, bulk=False)
    except fetch.LiveTimeout as e:
        return out("too_much_history", detail=e)
    except fetch.OutOfCredits as e:
        return out("no_credits", detail=e)
    except RuntimeError as e:  # FetchError: HTTP error, network, no key
        return out("unavailable", detail=e)
    rows = data.get("result") if isinstance(data, dict) else None
    if not isinstance(rows, list):  # Blockscout's own query timeout comes back as status 0 with a message
        said = f"{data.get('message')} {rows}" if isinstance(data, dict) else str(data)
        slow = "timeout" in said.lower() or "timed out" in said.lower()
        return out("too_much_history" if slow else "unavailable", detail=said[:120])
    h = _as_history(addr, "live", offset, None, rows)
    return out("ok" if rows else "no_transfers", h)


def positives(fz, ofac_set):
    pos = [f for a, f in fz.items() if f["freeze_ts"] >= T_TRAIN and a not in ofac_set]
    test = sorted((f for f in pos if f["freeze_ts"] >= T_TEST), key=lambda f: f["freeze_ts"])
    train = sorted((f for f in pos if f["freeze_ts"] < T_TEST), key=lambda f: f["freeze_ts"])
    random.Random(1).shuffle(train)
    # ponytail: random subsample of training freezes if they exceed the call budget
    return {"test_pos": test, "train_pos": train[:max(0, POS_BUDGET - len(test))]}


def pull(wallets, group):
    hs = []
    for f in wallets:
        if over_budget():
            break
        if h := history(f["address"], group, 1000, f["freeze_ts"]):
            hs.append(h)
    return hs


def block_by_time(ts):
    r = fetch.get(module="block", action="getblocknobytime", timestamp=ts, closest="before")["result"]
    return int(r["blockNumber"] if isinstance(r, dict) else r)


@functools.cache
def anchors():
    return [(t, block_by_time(t)) for t in (T_TRAIN, T_TEST, T_END)]


def block_at(ts):
    """Linear between exact anchor blocks; plenty for random sampling (log timestamps are re-checked)."""
    (t0, b0), (t1, b1) = anchors()[:2] if ts < T_TEST else anchors()[1:]
    return int(b0 + (ts - t0) * (b1 - b0) / (t1 - t0))


def negatives(group, t0, t1, exclude, n=NEG_PER_GROUP, windows=WINDOWS):
    """Random USDT recipients in [t0, t1) with <= 300 USDT transfers, not frozen, not known bad."""
    rng = random.Random(group)
    pool = []
    for _ in range(windows):
        if over_budget():
            break
        b = block_at(rng.uniform(t0, t1))
        logs = fetch.get(module="logs", action="getLogs", address=USDT, topic0=TRANSFER,
                         fromBlock=b, toBlock=b + WINDOW_BLOCKS)["result"]
        seen = Counter("0x" + l["topics"][2][-40:].lower() for l in logs if t0 <= int(l["timeStamp"], 0) < t1)
        # ponytail: 3+ receipts in ~20 min means a busy wallet (hot wallet, pool); skip it without spending a call
        cands = sorted(a for a, c in seen.items() if c <= 2 and a not in exclude)
        pool += rng.sample(cands, min(PER_WINDOW, len(cands)))
    pool = list(dict.fromkeys(pool))
    rng.shuffle(pool)
    hs, tried = [], 0
    for a in pool:
        if len(hs) >= n or tried >= NEG_CALL_CAP or over_budget():
            break
        tried += 1
        h = history(a, group, NEG_MAX_TRANSFERS + 1)
        if h and h["transfers"] and not h["truncated"]:
            hs.append(h)
    log.info("%s: %d accepted from %d tried (pool %d)", group, len(hs), tried, len(pool))
    return hs


def cached_transfer_logs(t0, t1):
    """(recipient, USDT amount) from the random Transfer windows already in the cache: no new calls."""
    import sqlite3, zlib
    db = sqlite3.connect(fetch.CACHE)
    out = []
    for (body,) in db.execute("SELECT body FROM cache WHERE url LIKE ?", (f"%topic0={TRANSFER}%",)):
        for l in json.loads(body if isinstance(body, str) else zlib.decompress(body))["result"]:
            if t0 <= int(l["timeStamp"], 0) < t1:
                out.append(("0x" + l["topics"][2][-40:].lower(), int(l["data"], 16) / 1e6))
    return out


def matched_negatives(group, t0, t1, exclude, pos_amounts, n_calls):
    """Comparison wallets whose sampled receipt follows the positives' first-payment size
    (decile bins of log amount), fetched exactly like positives: 1,000 rows, truncation kept."""
    rng = random.Random(group)
    q = [pos_amounts[int(i * (len(pos_amounts) - 1) / 10)] for i in range(11)]
    cands = cached_transfer_logs(t0, t1)
    rng.shuffle(cands)
    picked, per_bin = [], n_calls // 10
    for lo, hi in zip(q, q[1:]):
        inbin = [a for a, v in cands if lo <= v <= hi and a not in exclude]
        picked += [a for a in dict.fromkeys(inbin) if a not in picked][:per_bin]
    hs = []
    for a in picked:
        if over_budget():
            break
        if (h := history(a, group, 1000)) and h["transfers"]:
            hs.append(h)
    log.info("%s: %d accepted from %d tried (amount bins %s)", group, len(hs), len(picked), [round(x) for x in q])
    return hs


def save(groups, bad, frozen_at):
    (DATA / "histories").mkdir(exist_ok=True)
    rows = []
    for g, hs in groups.items():
        with gzip.open(DATA / "histories" / f"{g}.jsonl.gz", "wt") as f:
            f.writelines(json.dumps(h) + "\n" for h in hs)
        rows += [r for h in hs for r in F.training_rows(h, bad, frozen_at)]
    F.write_csv(rows, DATA / "features.csv")
    log.info("saved %s; %d feature rows; calls this run %d; credits %s",
             {g: len(hs) for g, hs in groups.items()}, len(rows), fetch.calls, fetch.credits_left)


def main(sample=False):
    DATA.mkdir(exist_ok=True)
    fz, ofac_set, bad = freezes(), ofac(), known_bad()
    for a, f in fz.items():
        f["ofac"] = int(a in ofac_set)
    with open(DATA / "freezes.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["address", "freeze_ts", "block", "tx_hash", "ofac"])
        w.writeheader()
        w.writerows(sorted(fz.values(), key=lambda r: r["freeze_ts"]))
    frozen_at = {a: f["freeze_ts"] for a, f in fz.items()}
    pos = positives(fz, ofac_set)
    exclude = bad | set(fz) | ofac_set | {USDT, "0x" + "0" * 40}
    log.info("freezes: %d all time; positives to pull: %d train, %d test; known bad: %d; calls %d",
             len(fz), len(pos["train_pos"]), len(pos["test_pos"]), len(bad), fetch.calls)

    if sample:
        hs = pull(pos["train_pos"][:6], "train_pos") + negatives("train_neg", T_TRAIN, T_TEST, exclude, n=4, windows=1)
        rows = [r for h in hs for r in F.training_rows(h, bad, frozen_at)]
        rows = [r for r in rows if r["label"]][:12] + [r for r in rows if not r["label"]][:8]
        F.write_csv(rows, DATA / "sample.csv")
        log.info("sample.csv: %d rows; calls %d; credits %s", len(rows), fetch.calls, fetch.credits_left)
        return

    groups = {}
    for g in ("test_pos", "train_pos"):  # test set first: Results 1-2 depend on it
        groups[g] = pull(pos[g], g)
        save(groups, bad, frozen_at)
    groups["train_neg"] = negatives("train_neg", T_TRAIN, T_TEST, exclude)
    save(groups, bad, frozen_at)
    groups["test_neg"] = negatives("test_neg", T_TEST, T_END, exclude | {h["address"] for h in groups["train_neg"]})
    save(groups, bad, frozen_at)
    # Volume-matched comparison wallets (feasibility found the random ones skew small).
    first = [next((t["usdt"] for t in h["transfers"] if t["to"] == h["address"] and t["usdt"] >= F.MIN_USDT), None)
             for h in groups["train_pos"]]
    amounts = sorted(a for a in first if a)
    for g, t0, t1, n in (("test_negv", T_TEST, T_END, MATCHED_TEST), ("train_negv", T_TRAIN, T_TEST, MATCHED_TRAIN)):
        seen = {h["address"] for hs in groups.values() for h in hs}
        groups[g] = matched_negatives(g, t0, t1, exclude | seen, amounts, n)
        save(groups, bad, frozen_at)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(fetch.HERE / "snapshot.log")])
    main(sample=sys.argv[1:] == ["sample"])
