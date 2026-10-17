"""Go/no-go: is the detector strong enough to build the rest on?

Trains a quick XGBoost on the 2024 - Jun 2026 snapshot rows, replays every Jul - Oct 2026
frozen wallet and comparison wallet just before each inbound payment, sets the threshold
so 1% of comparison wallets are flagged, and reports recall, lead time and payments that
could be escalated (build-plan.md Results 1-2), next to a rules-only baseline.

    python feasibility.py
"""
import csv
import json
from statistics import median

import numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from xgboost import XGBClassifier

import features as F

DAY = 86400


def load(group):
    return [json.loads(line) for line in open(F.DATA / "histories" / f"{group}.jsonl")]


def replay(h, bad, frozen_at):
    """(ts, features) just before each inbound payment >= 10 USDT, before the freeze."""
    me, end = h["address"], h.get("freeze_ts") or float("inf")
    pays = [t["ts"] for t in h["transfers"]
            if t["to"] == me and t["from"] != me and t["usdt"] >= F.MIN_USDT and t["ts"] < end]
    return [(ts, F.features(h, ts, bad, frozen_at)) for ts in pays]


def model():
    return XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8, eval_metric="logloss")


def ci(k, n):
    p = k / n
    return f"{p:.0%} ({k}/{n}, ±{1.96 * (p * (1 - p) / n) ** 0.5:.0%})"


def outcome(pos, flag):
    """flag(points) -> index of the first flagged payment or None. Returns recall/lead/payments lines."""
    hit, leads, saved, total = 0, [], 0, 0
    hit2 = n2 = 0
    for h, ps, s in pos:
        total += len(ps)
        i = flag(ps, s)
        n2 += len(ps) >= 2
        if i is not None:
            hit += 1
            hit2 += len(ps) >= 2
            leads.append((h["freeze_ts"] - ps[i][0]) / DAY)
            saved += len(ps) - i
    lead = f"median lead {median(leads):.0f} days (p25 {np.percentile(leads, 25):.0f})" if leads else "no flags"
    return (f"recall {ci(hit, len(pos))}; >=2-payment subset {ci(hit2, n2)}\n"
            f"    {lead}; payments from first flag on: {saved}/{total}")


def main():
    rows = [r for r in csv.DictReader(open(F.DATA / "features.csv")) if r["group"].startswith("train")]
    X = np.array([[float(r[f]) for f in F.FEATURES] for r in rows])
    y = np.array([int(r["label"]) for r in rows])
    wallets = [r["address"] for r in rows]
    print(f"training rows {len(y)} ({y.sum()} pos) from {len(set(wallets))} wallets")

    oof = np.zeros(len(y))
    for a, b in GroupKFold(5).split(X, y, wallets):  # by wallet: its 4 rows never straddle folds
        oof[b] = model().fit(X[a], y[a]).predict_proba(X[b])[:, 1]
    print(f"wallet-grouped 5-fold AUC (train period): {roc_auc_score(y, oof):.3f}")
    clf = model().fit(X, y)
    top = sorted(zip(clf.feature_importances_, F.FEATURES), reverse=True)[:5]
    print("top features:", ", ".join(f"{f} {w:.2f}" for w, f in top))

    bad = set((F.DATA / "known_bad.txt").read_text().split())
    frozen_at = {r["address"]: int(r["freeze_ts"]) for r in csv.DictReader(open(F.DATA / "freezes.csv"))}
    scored = {}
    for g in ("test_pos", "test_neg"):
        scored[g] = []
        for h in load(g):
            ps = replay(h, bad, frozen_at)
            if ps:
                s = clf.predict_proba(np.array([[p[f] for f in F.FEATURES] for _, p in ps]))[:, 1]
                scored[g].append((h, ps, s))
    pos, neg = scored["test_pos"], scored["test_neg"]
    neg_max = np.array([s.max() for _, _, s in neg])
    pos_max = np.array([s.max() for _, _, s in pos])
    print(f"\ntest (out of time, Jul-Oct 2026): {len(pos)} frozen wallets, {len(neg)} comparison wallets")
    print(f"wallet-level AUC (max score over payments): "
          f"{roc_auc_score([1] * len(pos) + [0] * len(neg), np.r_[pos_max, neg_max]):.3f}")

    for fa in (0.01, 0.05):
        thr = np.quantile(neg_max, 1 - fa)
        fp = int((neg_max > thr).sum())
        first = lambda ps, s, thr=thr: next((i for i, v in enumerate(s) if v > thr), None)
        print(f"\nmodel @ {fa:.0%} false alarms (threshold {thr:.3f}, {fp}/{len(neg)} comparison wallets flagged):")
        print("   ", outcome(pos, first))

    rule = lambda ps, s: next((i for i, (_, p) in enumerate(ps) if p["touched_known_bad"]), None)
    fp = sum(rule(ps, s) is not None for _, ps, s in neg)
    print(f"\nrules-only baseline (touched_known_bad), {fp}/{len(neg)} = {fp / len(neg):.1%} false alarms:")
    print("   ", outcome(pos, rule))


if __name__ == "__main__":
    main()
