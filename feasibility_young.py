"""Option 3: score only young wallets that receive exchange withdrawals.

A payment is eligible when, just before it, the wallet's first payment is at most 30 days old
and at least one earlier payment came from a hot wallet (sender nonce > 10,000). Thresholds are
set on eligible comparison wallets only; recall is over eligible frozen wallets.

    python feasibility_young.py
"""
import csv

import numpy as np
from sklearn.metrics import roc_auc_score

import features as F
from feasibility import COMPARE, DAY, load, replay
from feasibility_extra import evaluate, score, train

MAX_AGE_H = 30 * 24


def eligible(pts):
    out = []
    for h, ps in pts:
        keep = [(ts, p) for ts, p in ps if p["age_h"] <= MAX_AGE_H and p["share_in_from_hot_wallets"] > 0]
        if keep:
            out.append((h, keep))
    return out


def main():
    bad = set((F.DATA / "known_bad.txt").read_text().split())
    frozen_at = {r["address"]: int(r["freeze_ts"]) for r in csv.DictReader(open(F.DATA / "freezes.csv"))}
    groups = ("test_pos",) + COMPARE["both"]
    pts = {g: [(h, ps) for h in load(g) if (ps := replay(h, bad, frozen_at))] for g in groups}
    young = {g: eligible(v) for g, v in pts.items()}
    for g in groups:
        print(f"{g}: {len(young[g])} of {len(pts[g])} wallets have an eligible payment")

    clf = train(F.FEATURES)
    pos = score(clf, F.FEATURES, young["test_pos"])
    single = lambda f: [(h, ps, np.array([p[f] for _, p in ps])) for h, ps in young["test_pos"]]
    for name, gs in COMPARE.items():
        negpts = [w for g in gs for w in young[g]]
        neg = score(clf, F.FEATURES, negpts)
        print(f"\n=== {name}: {len(pos)} frozen vs {len(neg)} comparison wallets (eligible only) ===")
        for fa in (0.01, 0.05):
            for w in (None, 90):
                r, lead, auc = evaluate(pos, neg, fa=fa, window_days=w)
                print(f"model @{fa:.0%}{'' if w is None else f', within {w} d'}: recall {r:.1%} "
                      f"({round(r * len(pos))}/{len(pos)}), median lead {lead:.0f} d, AUC {auc:.3f}")
        # single-feature scores, to see whether the model adds anything inside the subset
        for f in ("median_hold_h", "share_in_from_hot_wallets", "n_senders_in"):
            sign = -1 if f == "median_hold_h" else 1  # fast forwarding = suspicious
            p1 = [(h, ps, sign * s) for h, ps, s in single(f)]
            n1 = [(h, ps, sign * np.array([p[f] for _, p in ps])) for h, ps in negpts]
            r, lead, auc = evaluate(p1, n1, fa=0.05)
            print(f"  {f} alone @5%: recall {r:.1%}, AUC {auc:.3f}")


if __name__ == "__main__":
    main()
