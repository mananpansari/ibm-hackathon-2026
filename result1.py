"""Result 1: model-flag lead time at 1% false alarms (build-plan.md sections 2, 6, 9).

Every test wallet is scored just before each inbound payment >= 10 USDT (as_of = that payment's ts,
so features() only sees transfers with ts < as_of). Frozen wallets are scored only on payments before
their freeze. A wallet is flagged if any of its score points reaches the threshold; comparison wallets
(test_neg random, test_negv volume-matched) go through the same any-payment check, and the threshold is
the smallest one that flags <= 1% of comparison wallets.

    python result1.py       # self-check on a synthetic set (exact threshold, flags, lead days)
    python result1.py run   # score the test wallets, write data/results/result1_* and print the summary

The model comes from model.py (#5); on a Mac without libomp, xgboost needs DYLD_LIBRARY_PATH pointing at
a libomp.dylib (scikit-learn's wheel ships one in sklearn/.dylibs).
"""
import bisect
import csv
import gzip
import json
import math
import random
import sys
from pathlib import Path
from statistics import median

import features as F

OUT = F.DATA / "results"
FA_LEVELS = (0.005, 0.01, 0.02, 0.05, 0.10, 0.20)
HEADLINE_FA = 0.01
BASES = ("test_negv", "test_neg")  # volume-matched first: the harder, more honest comparison
SEED, BOOT, SPLITS = 0, 1000, 200


def inbound(h):
    """Payments into the wallet >= 10 USDT (the same definition features() uses), before any freeze."""
    me, end = h["address"], h.get("freeze_ts") or math.inf
    return [t for t in h["transfers"] if t["to"] == me and t["from"] != me and t["usdt"] >= F.MIN_USDT and t["ts"] < end]


def points(h, bad, frozen_at, scorer):
    """[(as_of, score, sender)] for one wallet, one point per inbound payment."""
    pays = inbound(h)
    feats = [F.features(h, t["ts"], bad, frozen_at) for t in pays]
    return list(zip([t["ts"] for t in pays], scorer(feats) if feats else [], [t["from"] for t in pays]))


def threshold(maxes, fa):
    """Smallest attained score t with #{wallet max >= t} <= floor(fa * N); just above the top score if 0."""
    m = sorted(maxes)
    k = math.floor(fa * len(m) + 1e-9)
    for v in sorted(set(m)):
        if len(m) - bisect.bisect_left(m, v) <= k:
            return v
    return math.nextafter(m[-1], math.inf)


def flagged_share(maxes, t):
    return sum(x >= t for x in maxes) / len(maxes)


def outcome(pts, freeze_ts, t):
    """First flag of one positive wallet at threshold t: lead days and the payments it would have caught."""
    i = next((j for j, p in enumerate(pts) if p[1] >= t), None)
    if i is None:
        return None
    caught = pts[i:]  # the flagged payment itself is scored before it is signed, so it counts
    return {"first_flag_ts": pts[i][0], "lead_days": (freeze_ts - pts[i][0]) / 86400,
            "held_payments": len(caught), "held_senders": len({p[2] for p in caught})}


def quartiles(xs):
    xs = sorted(xs)
    if not xs:
        return None, None, None
    q = lambda p: xs[min(len(xs) - 1, max(0, math.ceil(p * len(xs)) - 1))] if len(xs) > 1 else xs[0]
    return q(0.25), median(xs), q(0.75)


def metrics(pos, comp_maxes, t):
    """pos = [(pts, freeze_ts)]; comp_maxes = comparison wallets' max scores."""
    outs = [o for o in (outcome(p, fz, t) for p, fz in pos) if o]
    leads = [o["lead_days"] for o in outs]
    q1, med, q3 = quartiles(leads)
    held = [o["held_payments"] for o in outs]
    return {"threshold": t, "fa_rate": flagged_share(comp_maxes, t), "positives": len(pos), "flagged": len(outs),
            "recall": len(outs) / len(pos) if pos else 0.0,
            "lead_days_median": med, "lead_days_iqr": [q1, q3],
            "lead_gt_1d": sum(x > 1 for x in leads), "lead_gt_7d": sum(x > 7 for x in leads),
            "lead_gt_30d": sum(x > 30 for x in leads),
            "held_payments_total": sum(held), "held_payments_median": median(held) if held else None,
            "payments_after_flag_total": sum(held) - len(held),
            "payments_after_flag_median": median(h - 1 for h in held) if held else None,
            "held_senders_total": sum(o["held_senders"] for o in outs)}


def auc(pos_maxes, comp_maxes):
    """Wallet-level AUC of the max score (Mann-Whitney, ties count half)."""
    c = sorted(comp_maxes)
    wins = sum(bisect.bisect_left(c, x) + 0.5 * (bisect.bisect_right(c, x) - bisect.bisect_left(c, x)) for x in pos_maxes)
    return wins / (len(pos_maxes) * len(c))


def evaluate(pos, comp, fa=HEADLINE_FA, rng=None):
    """Everything for one comparison basis. pos = [(pts, freeze_ts)], comp = [pts] (each with >= 1 point)."""
    rng = rng or random.Random(SEED)
    cmax = [max(p[1] for p in pts) for pts in comp]
    pmax = [max(p[1] for p in pts) for pts, _ in pos]
    t = threshold(cmax, fa)
    out = {"comparison_wallets": len(comp), "auc_wallet_max": auc(pmax, cmax),
           "in_sample": metrics(pos, cmax, t),
           "curve": [{"fa_target": a, **{k: v for k, v in metrics(pos, cmax, threshold(cmax, a)).items()
                                       if k in ("threshold", "fa_rate", "recall", "flagged", "lead_days_median")}}
                     for a in FA_LEVELS]}
    # Held-out: half the comparison wallets set the threshold, the other half measure the false alarms.
    idx = list(range(len(cmax)))
    split = []
    for s in range(SPLITS):
        random.Random(SEED + s).shuffle(idx)
        a, b = [cmax[i] for i in idx[:len(idx) // 2]], [cmax[i] for i in idx[len(idx) // 2:]]
        m = metrics(pos, b, threshold(a, fa))
        split.append(m)
        if s == 0:
            out["held_out_seed0"] = m
    fas, recs = sorted(m["fa_rate"] for m in split), sorted(m["recall"] for m in split)
    out["held_out_splits"] = {"splits": SPLITS, "fa_median": median(fas), "fa_range": [fas[0], fas[-1]],
                              "recall_median": median(recs), "recall_range": [recs[0], recs[-1]]}
    # Bootstrap by wallet: resample positives AND comparison wallets, re-pick the threshold each time.
    rec, lead = [], []
    for _ in range(BOOT):
        bp = [pos[rng.randrange(len(pos))] for _ in pos]
        bc = [cmax[rng.randrange(len(cmax))] for _ in cmax]
        m = metrics(bp, bc, threshold(bc, fa))
        rec.append(m["recall"])
        if m["lead_days_median"] is not None:
            lead.append(m["lead_days_median"])
    ci = lambda xs: [sorted(xs)[int(0.025 * len(xs))], sorted(xs)[int(0.975 * len(xs)) - 1]] if xs else None
    out["bootstrap"] = {"reps": BOOT, "recall_ci95": ci(rec), "lead_median_ci95": ci(lead),
                        "reps_with_no_flag": BOOT - len(lead)}
    return out


def load():
    hs = {g: [json.loads(l) for l in gzip.open(F.DATA / f"histories/{g}.jsonl.gz", "rt")]
          for g in ("test_pos",) + BASES}
    frozen_at = {r["address"]: int(r["freeze_ts"]) for r in csv.DictReader(open(F.DATA / "freezes.csv"))}
    bad = set((F.DATA / "known_bad.txt").read_text().split())  # same inputs as snapshot.py's training rows
    ofac = {l.strip().lower() for l in open(F.DATA / "ofac_eth.txt") if l.startswith("0x")}
    return hs, bad, frozen_at, ofac


def model_scorer():
    """Batch version of model.score (same models, same mean); checked against model.score below."""
    import numpy as np
    import model
    models = model._load()
    assert models, "no model loaded"

    def score(feats):
        x = np.array([[float(f[k]) for k in F.FEATURES] for f in feats], dtype=np.float32)
        ps = []
        if "xgb" in models:
            ps.append(models["xgb"].predict_proba(x)[:, 1])
        if "mlp" in models:
            ps.append(models["mlp"](model._squash(x)).numpy().ravel())
        return [float(v) for v in sum(ps) / len(ps)]
    return score, model.score


def run():
    import model
    train = {r["address"] for r in csv.DictReader(open(F.DATA / "features.csv")) if r["group"].startswith("train")}
    hs, bad, frozen_at, ofac = load()
    test = {h["address"] for g in hs.values() for h in g}
    assert not test & train, f"test wallets in training rows: {sorted(test & train)[:5]}"  # stop: no numbers
    meta = json.loads((model.META).read_text())
    assert meta["rows"] == sum(1 for r in csv.DictReader(open(F.DATA / "features.csv")) if r["group"].startswith("train"))
    score, one = model_scorer()
    rng = random.Random(SEED)
    pts = {}
    for g, wallets in hs.items():
        for h in wallets:
            pts[h["address"]] = points(h, bad, frozen_at, score)
            for as_of, s, _ in pts[h["address"]][:1] + ([rng.choice(pts[h["address"]])] if pts[h["address"]] else []):
                # batch == model.score, and the point is unchanged when everything from as_of on is cut
                past, past_frozen = F._cut(h, as_of, frozen_at)
                assert abs(one(F.features(past, as_of, bad, past_frozen)) - s) < 1e-5, (h["address"], as_of)
        print(f"scored {g}: {len(wallets)} wallets, {sum(len(pts[h['address']]) for h in wallets)} points", file=sys.stderr)

    pos_h = [h for h in hs["test_pos"] if h["address"] not in ofac and pts[h["address"]]]
    pos = [(pts[h["address"]], h["freeze_ts"]) for h in pos_h]
    pos2 = [(p, fz) for p, fz in pos if len(p) >= 2]
    summary = {"definitions": {
        "score_point": "model.score(features(history, as_of)) with as_of = ts of each inbound payment >= 10 USDT; "
                       "positives only before freeze_ts",
        "flagged": "any score point >= threshold", "threshold": "smallest attained score flagging <= floor(fa*N) comparison wallets",
        "comparison_wallets": "test wallets of that group with >= 1 inbound payment >= 10 USDT",
        "lead_days": "freeze_ts - ts of the first flagged payment",
        "held_payments": "the first flagged payment and every later inbound payment before the freeze",
        "payments_after_flag": "held_payments minus the flagged one (build plan's 'payments saved')",
        "held_senders": "distinct senders of held_payments (an upper bound on victims: senders can be mules or exchanges)"},
        "model": {k: meta[k] for k in ("validation_auc", "out_of_time_auc_volume_matched", "note")},
        "positives": {"test_pos": len(hs["test_pos"]), "ofac_excluded": sum(h["address"] in ofac for h in hs["test_pos"]),
                      "no_payment_before_freeze": sum(not pts[h["address"]] for h in hs["test_pos"]),
                      "used": len(pos), "with_2plus_payments": len(pos2),
                      "truncated": sum(h["truncated"] for h in pos_h)},
        "headline_basis": "test_negv", "bases": {}}
    for g in BASES:
        comp = [pts[h["address"]] for h in hs[g] if pts[h["address"]]]
        summary["bases"][g] = {"wallets": len(hs[g]), "no_payment": len(hs[g]) - len(comp),
                               "truncated": sum(h["truncated"] for h in hs[g]),
                               "all_positives": evaluate(pos, comp), "positives_2plus": evaluate(pos2, comp)}

    OUT.mkdir(exist_ok=True)
    with gzip.open(OUT / "result1_points.csv.gz", "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(["wallet", "group", "as_of", "score"])
        for g, wallets in hs.items():
            for h in wallets:
                w.writerows([h["address"], g, a, f"{s:.6f}"] for a, s, _ in pts[h["address"]])
    ts = {g: summary["bases"][g]["all_positives"]["in_sample"]["threshold"] for g in BASES}
    with open(OUT / "result1_wallets.csv", "w", newline="") as f:
        cols = ["wallet", "group", "n_points", "max_score", "truncated", "freeze_ts"]
        for g in BASES:
            cols += [f"flagged_{g}", f"first_flag_ts_{g}", f"lead_days_{g}", f"held_payments_{g}"]
        w = csv.DictWriter(f, cols)
        w.writeheader()
        for grp, wallets in hs.items():
            for h in wallets:
                p = pts[h["address"]]
                row = {"wallet": h["address"], "group": grp, "n_points": len(p), "truncated": int(h["truncated"]),
                       "max_score": f"{max(x[1] for x in p):.6f}" if p else "", "freeze_ts": h["freeze_ts"] or ""}
                for g in BASES:
                    hit = next((x[0] for x in p if x[1] >= ts[g]), None)
                    o = outcome(p, h["freeze_ts"], ts[g]) if hit and h["freeze_ts"] else None
                    row |= {f"flagged_{g}": int(hit is not None), f"first_flag_ts_{g}": hit or "",
                            f"lead_days_{g}": f"{o['lead_days']:.2f}" if o else "",
                            f"held_payments_{g}": o["held_payments"] if o else ""}
                w.writerow(row)
    (OUT / "result1_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


def _self_check():
    D = 86400
    tx = lambda ts, a, b, usdt: {"ts": ts, "from": a, "to": b, "usdt": usdt, "nonce": 1, "hash": f"{ts}{a}{b}"}
    pay = lambda me, *days, frm="0xv", usdt=100: [tx(d * D, f"{frm}{i}", me, usdt) for i, d in enumerate(days)]
    # Toy scorer: the score is the number of earlier payments, so the threshold and flags are known exactly.
    scorer = lambda feats: [f["n_pay_in"] / 10 for f in feats]
    pos_h = [
        {"address": "0xp1", "freeze_ts": 40 * D, "transfers": pay("0xp1", 0, 1, 2, 3, 4, 5)       # scores 0 .. .5; reaches .4 at day 4
         + pay("0xp1", 41, 42, 43, 44, 45, 46, 47, frm="0xlate")},                                 # after the freeze: never a point
        {"address": "0xp2", "freeze_ts": 10 * D, "transfers": pay("0xp2", 0, 1, 2)                 # max .2: never flagged
         + [tx(5 * D, "0xp2", "0xout", 50), tx(6 * D, "0xd", "0xp2", 5)]},                          # outbound and dust: not points
        {"address": "0xp3", "freeze_ts": 100 * D, "transfers": pay("0xp3", 0, 1, 2, 3, 4, 5, 6, 7)},  # reaches .4 at day 4: 4 payments held
    ]
    comp_h = [{"address": f"0xc{i}", "freeze_ts": None, "transfers": pay(f"0xc{i}", *range(i % 5 + 1))} for i in range(99)]
    comp_h.append({"address": "0xcbig", "freeze_ts": None, "transfers": pay("0xcbig", *range(9))})  # max .8
    P = {h["address"]: points(h, set(), {}, scorer) for h in pos_h + comp_h}
    assert [a for a, _, _ in P["0xp1"]] == [d * D for d in range(6)], "post-freeze payments are not score points"
    assert [s for _, s, _ in P["0xp1"]] == [0, .1, .2, .3, .4, .5], "each point sees only payments before as_of"
    assert len(P["0xp2"]) == 3
    cmax = [max(p[1] for p in P[h["address"]]) for h in comp_h]  # 0 .. .3 (20 each), .4 (19) and one .8
    # 100 comparison wallets: 1% = 1 wallet -> .8; 5% flags at most 5 -> still .8 (20 wallets are >= .4).
    assert threshold(cmax, 0.01) == 0.8 and threshold(cmax, 0.05) == 0.8
    assert threshold(cmax, 0.20) == 0.4 and flagged_share(cmax, 0.4) == 0.20 and threshold(cmax, 0.19) == 0.8
    assert threshold(cmax, 0.0) > 0.8 and flagged_share(cmax, threshold(cmax, 0.0)) == 0
    pos = [(P[h["address"]], h["freeze_ts"]) for h in pos_h]
    m = metrics(pos, cmax, 0.4)
    assert (m["flagged"], m["lead_gt_30d"], m["lead_gt_7d"]) == (2, 2, 2), m
    assert sorted(o["lead_days"] for o in (outcome(p, fz, 0.4) for p, fz in pos) if o) == [36, 96]
    assert outcome(*pos[0], 0.4)["held_payments"] == 2 and outcome(*pos[2], 0.4)["held_payments"] == 4
    assert outcome(*pos[1], 0.4) is None and m["held_payments_total"] == 6 and m["held_senders_total"] == 6
    assert (m["payments_after_flag_total"], m["payments_after_flag_median"]) == (4, 2)
    e = evaluate(pos, [P[h["address"]] for h in comp_h], fa=0.20)
    assert e["in_sample"]["threshold"] == 0.4 and abs(e["in_sample"]["recall"] - 2 / 3) < 1e-12
    assert auc([1.0], [0.0, 2.0]) == 0.5 and auc([1.0], [1.0]) == 0.5
    # No score point uses a transfer at or after its as_of: a huge future payment changes nothing.
    future = {**pos_h[2], "transfers": pos_h[2]["transfers"] + [tx(99 * D, "0xwhale", "0xp3", 10**9)]}
    assert points(future, set(), {}, lambda fs: [f["usd_in"] for f in fs])[:8] == \
        points(pos_h[2], set(), {}, lambda fs: [f["usd_in"] for f in fs])
    for h in pos_h:
        for as_of, _, _ in P[h["address"]]:
            assert as_of < h["freeze_ts"]
            F.check_no_future(h, set(), {}, [as_of])
    print("self-check passed: threshold, flags, lead days and held payments exact; no point sees as_of or later")


if __name__ == "__main__":
    run() if sys.argv[1:] == ["run"] else _self_check()
