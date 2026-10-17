"""Stress tests for the go/no-go in feasibility.py.

1. Threshold stability: bootstrap the comparison wallets, re-set the 1% threshold each time.
2. Recent-window recall: only payments in the last 30 / 90 days before the freeze count.
3. Amount confound: retrain without the amount features.
4. Time-matched negatives: drop negative training rows dated before 2024.
5. Per-feature ablation: recall @1% with each feature removed.

    python feasibility_extra.py [random|volume-matched|both]
"""
import csv
import sys

import numpy as np
from sklearn.metrics import roc_auc_score

import features as F
from feasibility import COMPARE, DAY, load, model, replay

T_TRAIN = 1704067200
SET = sys.argv[1] if len(sys.argv) > 1 else "both"  # comparison set, see feasibility.COMPARE
AMOUNTS = ["usd_in", "usd_out", "out_in_ratio", "max_in_usd"]


def train(feats, drop_old_neg=False):
    rows = [r for r in csv.DictReader(open(F.DATA / "features.csv")) if r["group"].startswith("train")]
    if drop_old_neg:
        rows = [r for r in rows if r["label"] == "1" or int(r["as_of"]) >= T_TRAIN]
    X = np.array([[float(r[f]) for f in feats] for r in rows])
    y = np.array([int(r["label"]) for r in rows])
    return model().fit(X, y)


def score(clf, feats, pts):
    return [(h, ps, clf.predict_proba(np.array([[p[f] for f in feats] for _, p in ps]))[:, 1]) for h, ps in pts]


def evaluate(pos, neg, fa=0.01, window_days=None):
    neg_max = np.array([s.max() for _, _, s in neg])
    thr = np.quantile(neg_max, 1 - fa)
    hits, leads = 0, []
    for h, ps, s in pos:
        for (ts, _), v in zip(ps, s):
            lead = (h["freeze_ts"] - ts) / DAY
            if v > thr and (window_days is None or lead <= window_days):
                hits += 1
                leads.append(lead)
                break
    auc = roc_auc_score([1] * len(pos) + [0] * len(neg), np.r_[[s.max() for *_, s in pos], neg_max])
    return hits / len(pos), (np.median(leads) if leads else float("nan")), auc


def main():
    bad = set((F.DATA / "known_bad.txt").read_text().split())
    frozen_at = {r["address"]: int(r["freeze_ts"]) for r in csv.DictReader(open(F.DATA / "freezes.csv"))}
    pts = {g: [(h, ps) for h in load(g) if (ps := replay(h, bad, frozen_at))] for g in ("test_pos",) + COMPARE[SET]}
    pts["test_neg"] = [w for g in COMPARE[SET] for w in pts[g]]
    base = F.FEATURES

    def run(feats, **kw):
        clf = train(feats, **kw)
        return score(clf, feats, pts["test_pos"]), score(clf, feats, pts["test_neg"])

    pos, neg = run(base)
    r, lead, auc = evaluate(pos, neg)
    print(f"comparison set: {SET} ({len(neg)} wallets)")
    print(f"baseline: recall@1% {r:.1%}, median lead {lead:.0f} d, AUC {auc:.3f}")

    # 1. bootstrap the comparison set
    rng = np.random.default_rng(0)
    rs = [evaluate(pos, [neg[i] for i in rng.integers(0, len(neg), len(neg))])[0] for _ in range(500)]
    print(f"1. bootstrap recall@1%: median {np.median(rs):.1%}, 95% range {np.percentile(rs, 2.5):.1%} - {np.percentile(rs, 97.5):.1%}")
    rs5 = [evaluate(pos, [neg[i] for i in rng.integers(0, len(neg), len(neg))], fa=0.05)[0] for _ in range(500)]
    print(f"   bootstrap recall@5%: median {np.median(rs5):.1%}, 95% range {np.percentile(rs5, 2.5):.1%} - {np.percentile(rs5, 97.5):.1%}")

    # 2. only flags in the last N days before the freeze count
    for w in (7, 30, 90, 365):
        for fa in (0.01, 0.05):
            r, lead, _ = evaluate(pos, neg, fa=fa, window_days=w)
            print(f"2. flag within {w:>3} d of freeze @{fa:.0%}: recall {r:.1%}, median lead {lead:.0f} d")

    # 3. without amount features
    feats = [f for f in base if f not in AMOUNTS]
    r, lead, auc = evaluate(*run(feats))
    r90 = evaluate(*run(feats), window_days=90)[0]
    print(f"3. no amount features: recall@1% {r:.1%} (within 90 d {r90:.1%}), median lead {lead:.0f} d, AUC {auc:.3f}")
    r, lead, auc = evaluate(*run(AMOUNTS))
    print(f"   amount features only: recall@1% {r:.1%}, median lead {lead:.0f} d, AUC {auc:.3f}")

    # 4. time-matched negatives
    r, lead, auc = evaluate(*run(base, drop_old_neg=True))
    print(f"4. negatives from 2024+ only: recall@1% {r:.1%}, median lead {lead:.0f} d, AUC {auc:.3f}")

    # 5. drop one feature at a time
    for f in base:
        r, _, auc = evaluate(*run([x for x in base if x != f]))
        print(f"5. without {f:<26} recall@1% {r:.1%}  AUC {auc:.3f}")


if __name__ == "__main__":
    main()
