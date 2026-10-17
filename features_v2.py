"""features_v2(history, as_of): the 12 features of features.py plus 14 more, for the v2 wallet model.

Same contract as features.py: only transfers with ts < as_of and usdt >= 10 are read, everything comes
from the destination wallet's own USDT history (one Blockscout call live, no other wallets), and
`python features_v2.py` proves no feature changes when everything from as_of on is cut away.

The extra features follow the leads in docs/feasibility.md: frozen young wallets have few senders and
hold money longer; scam wallets often open with a small test payment and then a big one.

    python features_v2.py   # self-check: no future data, on synthetic and real histories
"""
import bisect
import gzip
import json
import random
from statistics import median

import features as F

EXTRA = [
    "first_in_usd", "test_then_big", "gap1_h", "median_gap_in_h", "share_round_in", "n_hot_senders",
    "share_repeat_sender_pays", "hours_since_last_in", "hours_since_last_out", "share_forwarded_1h",
    "n_pay_in_7d", "usd_in_7d", "senders_per_payment", "out_in_count_ratio",
]
FEATURES_V2 = F.FEATURES + EXTRA
H = 3600


def features_v2(history, as_of, bad=frozenset(), frozen_at=None):
    me = history["address"]
    base = F.features(history, as_of, bad, frozen_at)
    txs = [t for t in history["transfers"] if t["ts"] < as_of and t["usdt"] >= F.MIN_USDT]
    ins = [t for t in txs if t["to"] == me and t["from"] != me]
    outs = [t for t in txs if t["from"] == me and t["to"] != me]
    in_ts, out_ts = [t["ts"] for t in ins], [t["ts"] for t in outs]
    gaps = [(b - a) / H for a, b in zip(in_ts, in_ts[1:])]
    pays_by_sender = {}
    for t in ins:
        pays_by_sender[t["from"]] = pays_by_sender.get(t["from"], 0) + 1
    week = [t for t in ins if t["ts"] >= as_of - 7 * 24 * H]

    def forwarded_within_1h(t):
        i = bisect.bisect_left(out_ts, t["ts"])
        return i < len(out_ts) and out_ts[i] - t["ts"] <= H

    n = len(ins)
    return {**base,
            "first_in_usd": ins[0]["usdt"] if ins else 0.0,
            "test_then_big": max(t["usdt"] for t in ins) / ins[0]["usdt"] if n >= 2 else 0.0,
            "gap1_h": gaps[0] if gaps else -1.0,
            "median_gap_in_h": median(gaps) if gaps else -1.0,
            "share_round_in": sum(t["usdt"] >= 100 and abs(t["usdt"] / 100 - round(t["usdt"] / 100)) < 1e-6
                                  for t in ins) / n if n else 0.0,
            "n_hot_senders": len({t["from"] for t in ins if t["nonce"] > F.HOT_NONCE}),
            "share_repeat_sender_pays": sum(pays_by_sender[t["from"]] > 1 for t in ins) / n if n else 0.0,
            "hours_since_last_in": (as_of - in_ts[-1]) / H if ins else -1.0,
            "hours_since_last_out": (as_of - out_ts[-1]) / H if outs else -1.0,
            "share_forwarded_1h": sum(map(forwarded_within_1h, ins)) / n if n else 0.0,
            "n_pay_in_7d": len(week),
            "usd_in_7d": sum(t["usdt"] for t in week),
            "senders_per_payment": base["n_senders_in"] / n if n else 0.0,
            "out_in_count_ratio": len(outs) / n if n else 0.0}


def _self_check():
    tx = lambda ts, a, b, usdt, nonce=5: {"ts": ts, "from": a, "to": b, "usdt": usdt, "nonce": nonce, "hash": f"{ts}{a}{b}"}
    h = {"address": "0xme", "freeze_ts": None, "transfers": [
        tx(0, "0xcex", "0xme", 150, nonce=900_000),     # test payment from an exchange
        tx(600, "0xcex", "0xme", 78_000, nonce=900_001),  # the big one, 10 minutes later
        tx(1200, "0xme", "0xmule", 70_000),             # forwarded 20 and 10 minutes after the two payments
        tx(5 * H, "0xdust", "0xme", 1),                 # dust: ignored
        tx(10 * 24 * H, "0xlater", "0xme", 500),        # after every as_of below
    ]}
    f = features_v2(h, 2 * H)
    assert set(f) == set(FEATURES_V2)
    assert f["first_in_usd"] == 150 and f["test_then_big"] == 520 and f["gap1_h"] == 600 / H, f
    assert f["n_hot_senders"] == 1 and f["share_repeat_sender_pays"] == 1.0 and f["share_round_in"] == 0.5, f
    assert f["share_forwarded_1h"] == 1.0 and f["n_pay_in_7d"] == 2 and f["hours_since_last_out"] == (2 * H - 1200) / H, f
    assert features_v2(h, 0)["first_in_usd"] == 0.0 and features_v2(h, 0)["gap1_h"] == -1.0, "nothing before as_of"
    # No feature may change when everything from as_of on (transfers, freezes, the label) is cut away.
    def check(hist, frozen_at, as_ofs):
        for as_of in as_ofs:
            past, pf = F._cut(hist, as_of, frozen_at)
            assert features_v2(hist, as_of, set(), frozen_at) == features_v2(past, as_of, set(), pf), (hist["address"], as_of)
    check(h, {"0xmule": 3 * H}, [0, 1, 600, 601, 2 * H, 4 * H, 11 * 24 * H])
    frozen = dict(__import__("payee_memory").load_freezes())
    for g in ("train_pos", "train_negv", "test_pos"):
        hs = [json.loads(l) for l in gzip.open(F.DATA / "histories" / f"{g}.jsonl.gz", "rt")]
        for hist in random.Random(0).sample(hs, min(30, len(hs))):
            ts = [t["ts"] for t in hist["transfers"]]
            if ts:
                check(hist, frozen, [ts[0], ts[len(ts) // 2], ts[-1], ts[-1] + 1])
        print("real-data check passed:", g)
    print("self-check passed: features_v2 uses no data from as_of on")


if __name__ == "__main__":
    _self_check()
