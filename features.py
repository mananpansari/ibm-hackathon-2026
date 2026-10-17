"""features(history, as_of): point-in-time USDT features.

history = {"address", "transfers": [{"ts", "from", "to", "usdt", "nonce", "hash"}, ...]}
(transfers ascending by ts, addresses lowercase). Only transfers with ts < as_of and
usdt >= 10 are ever read. `bad` is the static known-bad set (fesevu scam labels);
`frozen_at` maps address -> Tether freeze ts and only freezes before as_of count.

    python features.py   # self-check: no feature uses data after as_of
"""
import bisect
import csv
import gzip
import json
import random
from pathlib import Path
from statistics import median

DATA = Path(__file__).resolve().parent / "data"

MIN_USDT = 10
HOT_NONCE = 10_000
OFFSETS_H = (1, 6, 24, 72)
FEATURES = [
    "age_h", "n_pay_in", "n_senders_in", "n_pay_in_6h", "share_in_from_hot_wallets",
    "usd_in", "usd_out", "out_in_ratio", "max_in_usd", "median_hold_h",
    "n_out_counterparties", "touched_known_bad",
]
ROW_COLS = ["address", "group", "label", "offset_h", "as_of", "freeze_ts"] + FEATURES


def features(history, as_of, bad=frozenset(), frozen_at=None):
    me = history["address"]
    frozen_at = frozen_at or {}
    txs = [t for t in history["transfers"] if t["ts"] < as_of and t["usdt"] >= MIN_USDT]
    ins = [t for t in txs if t["to"] == me and t["from"] != me]
    outs = [t for t in txs if t["from"] == me and t["to"] != me]
    out_ts = [t["ts"] for t in outs]
    usd_in = sum(t["usdt"] for t in ins)
    usd_out = sum(t["usdt"] for t in outs)
    # Hold = inbound -> next outbound. ponytail: censored at as_of when nothing went out yet, so no NaNs.
    holds = [((out_ts[i] if (i := bisect.bisect_left(out_ts, t["ts"])) < len(out_ts) else as_of) - t["ts"]) / 3600
             for t in ins]
    counterparties = {t["from"] for t in ins} | {t["to"] for t in outs}
    return {
        "age_h": (as_of - ins[0]["ts"]) / 3600 if ins else 0.0,
        "n_pay_in": len(ins),
        "n_senders_in": len({t["from"] for t in ins}),
        "n_pay_in_6h": sum(t["ts"] >= as_of - 6 * 3600 for t in ins),
        "share_in_from_hot_wallets": sum(t["nonce"] > HOT_NONCE for t in ins) / len(ins) if ins else 0.0,
        "usd_in": usd_in,
        "usd_out": usd_out,
        "out_in_ratio": usd_out / usd_in if usd_in else 0.0,
        "max_in_usd": max((t["usdt"] for t in ins), default=0.0),
        "median_hold_h": median(holds) if holds else 0.0,
        "n_out_counterparties": len({t["to"] for t in outs}),
        "touched_known_bad": int(any(c in bad or frozen_at.get(c, float("inf")) < as_of for c in counterparties)),
    }


def training_rows(history, bad=frozenset(), frozen_at=None):
    """The wallet at first payment + 1/6/24/72 h (only rows before its freeze, within fetched data)."""
    me, txs = history["address"], history["transfers"]
    first = next((t["ts"] for t in txs if t["to"] == me and t["from"] != me and t["usdt"] >= MIN_USDT), None)
    if first is None:
        return []
    rows = []
    for k in OFFSETS_H:
        as_of = first + k * 3600
        if history.get("freeze_ts") and as_of >= history["freeze_ts"]:
            break  # already frozen: not "before the blacklist"
        if history.get("truncated") and as_of > txs[-1]["ts"]:
            break  # only the first 1,000 transfers were fetched; later ones are missing
        rows.append({"address": me, "group": history["group"], "label": int(history["group"].endswith("pos")),
                     "offset_h": k, "as_of": as_of, "freeze_ts": history.get("freeze_ts") or "",
                     **features(history, as_of, bad, frozen_at)})
    return rows


def write_csv(rows, path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, ROW_COLS)
        w.writeheader()
        w.writerows(rows)


def _cut(history, as_of, frozen_at):
    """What the world looked like at as_of: drop every later transfer, later freeze and the label."""
    past = {**history, "freeze_ts": None, "transfers": [t for t in history["transfers"] if t["ts"] < as_of]}
    return past, {a: ts for a, ts in frozen_at.items() if ts < as_of}


def check_no_future(history, bad, frozen_at, as_ofs):
    for as_of in as_ofs:
        past, past_frozen = _cut(history, as_of, frozen_at)
        assert features(history, as_of, bad, frozen_at) == features(past, as_of, bad, past_frozen), (history["address"], as_of)


def _self_check():
    H = 3600
    me, scammer, cex, mule, later_bad = "0xme", "0xscam", "0xcex", "0xmule", "0xlater"
    tx = lambda ts, a, b, usdt, nonce=5: {"ts": ts, "from": a, "to": b, "usdt": usdt, "nonce": nonce, "hash": f"{ts}{a}{b}"}
    h = {"address": me, "group": "train_pos", "freeze_ts": 100 * H, "truncated": False, "transfers": [
        tx(0, cex, me, 500, nonce=900_000),   # exchange withdrawal (hot wallet)
        tx(1 * H, later_bad, me, 2),          # dust: ignored
        tx(2 * H, later_bad, me, 300),        # from a wallet Tether freezes at 30 h
        tx(3 * H, me, mule, 700),             # forwarded after 3 h and 1 h
        tx(50 * H, scammer, me, 9_999),       # after every as_of below
        tx(51 * H, me, scammer, 9_999),
    ]}
    frozen_at = {later_bad: 30 * H, scammer: 60 * H}
    f = features(h, 24 * H, frozen_at=frozen_at)
    assert (f["n_pay_in"], f["n_senders_in"], f["usd_in"], f["usd_out"]) == (2, 2, 800, 700), f
    assert f["median_hold_h"] == 2.0 and f["share_in_from_hot_wallets"] == 0.5 and f["age_h"] == 24.0, f
    assert f["touched_known_bad"] == 0, "later_bad is frozen at 30 h, after as_of = 24 h"
    assert features(h, 31 * H, frozen_at=frozen_at)["touched_known_bad"] == 1
    assert features(h, 24 * H, bad={mule})["touched_known_bad"] == 1
    assert [r["offset_h"] for r in training_rows(h)] == [1, 6, 24, 72]
    assert [r["offset_h"] for r in training_rows({**h, "freeze_ts": 10 * H})] == [1, 6]
    # Future transfers, future freezes and the label never change a feature, at any as_of.
    check_no_future(h, {cex}, frozen_at, [t * H for t in range(0, 60)] + [2 * H + 1])
    # Same check on real histories, if the snapshot has been pulled.
    for path in sorted(DATA.glob("histories/*.jsonl.gz")):
        frozen = {r["address"]: int(r["freeze_ts"]) for r in csv.DictReader(open(DATA / "freezes.csv"))}
        hs = [json.loads(line) for line in gzip.open(path, "rt")]
        for hist in random.Random(0).sample(hs, min(50, len(hs))):
            ts = [t["ts"] for t in hist["transfers"]]
            if ts:
                check_no_future(hist, set(), frozen, [ts[0], ts[len(ts) // 2], ts[-1], ts[-1] + 1])
        print("real-data check passed:", path.name)
    print("self-check passed: no feature uses data after as_of")


if __name__ == "__main__":
    _self_check()
