"""wallet_facts(history, as_of): the officer's "Wallet record" card (UI v2), point in time.

Plain facts about a destination wallet from its recorded USDT transfers, using only transfers
before as_of and of at least 10 USDT, like features.py. All values are real (on-chain data);
nothing here decides a tier.

    python wallet_facts.py   # self-check: no fact uses data after as_of
"""
from collections import defaultdict

from features import MIN_USDT, features

DAY = 86400


def wallet_facts(history, as_of, bad=frozenset()):
    """dict for the why-card, or None without a history."""
    if not history:
        return None
    me = history["address"]
    txs = [t for t in history["transfers"] if t["ts"] < as_of and t["usdt"] >= MIN_USDT]
    ins = [t for t in txs if t["to"] == me and t["from"] != me]
    outs = [t for t in txs if t["from"] == me and t["to"] != me]
    flows = defaultdict(lambda: {"usdt": 0.0, "first_ts": None})
    for t in outs:
        f = flows[t["to"]]
        f["usdt"] += t["usdt"]
        f["first_ts"] = t["ts"] if f["first_ts"] is None else f["first_ts"]
    f = features(history, as_of, bad)
    return {
        "first_seen_ts": min((t["ts"] for t in txs), default=None),
        "n_payments_in": len(ins),
        "n_senders_in": len({t["from"] for t in ins}),
        "n_senders_in_7d": len({t["from"] for t in ins if t["ts"] >= as_of - 7 * DAY}),
        "usdt_in": round(sum(t["usdt"] for t in ins), 2),
        "usdt_out": round(sum(t["usdt"] for t in outs), 2),
        "median_forward_h": round(f["median_hold_h"], 1) if ins and outs else None,
        "out_flows": sorted(({"to": a, "usdt": round(v["usdt"], 2), "first_ts": v["first_ts"]} for a, v in flows.items()),
                            key=lambda x: -x["usdt"])[:3],
        "touched_known_bad": bool(f["touched_known_bad"]),
        "truncated": bool(history.get("truncated")),  # only the first 1,000 transfers were fetched
        "kind": "real",
    }


def _self_check():
    H = 3600
    me = "0xme"
    h = {"address": me, "truncated": False, "transfers": [
        {"ts": 1 * H, "from": "0xa", "to": me, "usdt": 100, "nonce": 1, "hash": "1"},
        {"ts": 2 * H, "from": "0xb", "to": me, "usdt": 5, "nonce": 1, "hash": "2"},  # dust: ignored
        {"ts": 3 * H, "from": me, "to": "0xmule", "usdt": 90, "nonce": 1, "hash": "3"},
        {"ts": 10 * DAY, "from": "0xbad", "to": me, "usdt": 500, "nonce": 1, "hash": "4"},
        {"ts": 11 * DAY, "from": me, "to": "0xcex", "usdt": 400, "nonce": 2, "hash": "5"},
    ]}
    f = wallet_facts(h, 5 * H, {"0xbad"})
    assert f["n_payments_in"] == 1 and f["n_senders_in"] == 1 and f["first_seen_ts"] == 1 * H, f
    assert f["out_flows"] == [{"to": "0xmule", "usdt": 90, "first_ts": 3 * H}] and f["median_forward_h"] == 2.0, f
    assert not f["touched_known_bad"], "the bad sender comes later"
    g = wallet_facts(h, 12 * DAY, {"0xbad"})
    assert g["n_payments_in"] == 2 and g["n_senders_in_7d"] == 1 and g["touched_known_bad"]
    assert [x["to"] for x in g["out_flows"]] == ["0xcex", "0xmule"]
    for as_of in (0, 1 * H, 5 * H, 10 * DAY, 12 * DAY):  # no future leakage
        past = {**h, "transfers": [t for t in h["transfers"] if t["ts"] < as_of]}
        assert wallet_facts(h, as_of, {"0xbad"}) == wallet_facts(past, as_of, {"0xbad"}), as_of
    assert wallet_facts(None, 1) is None
    assert wallet_facts({"address": me, "transfers": []}, 1)["first_seen_ts"] is None
    from engine import RecordedHistories
    rec = RecordedHistories(("test_pos",))
    a, hist = next(iter(rec.by_addr.items()))
    assert wallet_facts(rec(a, hist["freeze_ts"]), hist["freeze_ts"])["n_payments_in"] >= 1
    print(f"self-check passed: wallet facts (no leakage; {len(rec.by_addr)} recorded wallets readable)")


if __name__ == "__main__":
    _self_check()
