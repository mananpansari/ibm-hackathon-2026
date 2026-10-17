"""Train the v2 wallet model on a payment-level training set (no Blockscout calls).

v1 (#5) learned from 4 snapshots per training wallet (first payment + 1/6/24/72 h: 8,560 rows). v2 scores
each training wallet just before each payment it received, which is how the engine uses the model
(up to 40 payments per wallet, each wallet weighted equally), with the 26 features of features_v2.py.

Choices are made by 5-fold cross-validation inside the training period, folds split by wallet, scored
the way the test is: each wallet's max score, frozen wallets against volume-matched wallets. The
Jul-Oct 2026 test wallets are never read here; model_report.py looks at them once, afterwards.

    python train_v2.py build     # data/model_v2/train_points.csv.gz (point-in-time rows, train wallets only)
    python train_v2.py cv        # compare the candidate setups, print the table
    python train_v2.py train     # fit the chosen setup on all training rows -> models_v2/
"""
import csv
import gzip
import json
import math
import random
import sys
from pathlib import Path

import features as F
from features_v2 import FEATURES_V2, features_v2
from payee_memory import load_freezes

HERE = Path(__file__).resolve().parent
POINTS = F.DATA / "model_v2" / "train_points.csv.gz"
OUT = HERE / "models_v2"
GROUPS = ("train_pos", "train_neg", "train_negv")
PER_WALLET = 40
SEED = 0
PARAMS = dict(n_estimators=400, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
              min_child_weight=5, eval_metric="logloss")
SETUPS = {  # name: (features, negative groups)
    "v1 features, payment points": (F.FEATURES, ("train_neg", "train_negv")),
    "v2 features, payment points": (FEATURES_V2, ("train_neg", "train_negv")),
    "v2 features, volume-matched negatives only": (FEATURES_V2, ("train_negv",)),
}


def build():
    frozen = dict(load_freezes())
    bad = frozenset((F.DATA / "known_bad.txt").read_text().split())
    test = {json.loads(l)["address"] for g in ("test_pos", "test_neg", "test_negv")
            for l in gzip.open(F.DATA / "histories" / f"{g}.jsonl.gz", "rt")}
    POINTS.parent.mkdir(exist_ok=True)
    n = 0
    with gzip.open(POINTS, "wt", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["wallet", "group", "label", "as_of", "weight"] + FEATURES_V2)
        for g in GROUPS:
            for line in gzip.open(F.DATA / "histories" / f"{g}.jsonl.gz", "rt"):
                h = json.loads(line)
                assert h["address"] not in test, "a test wallet in the training groups: stop"
                me, end = h["address"], h["freeze_ts"] or math.inf
                pays = [t["ts"] for t in h["transfers"]
                        if t["to"] == me and t["from"] != me and t["usdt"] >= F.MIN_USDT and t["ts"] < end]
                if not pays:
                    continue
                pick = sorted(random.Random(f"{SEED}{me}").sample(pays, min(PER_WALLET, len(pays))))
                for as_of in pick:
                    f = features_v2(h, as_of, bad, frozen)
                    w.writerow([me, g, int(g == "train_pos"), as_of, 1 / len(pick)] + [f[k] for k in FEATURES_V2])
                    n += 1
    print(f"wrote {POINTS.relative_to(HERE)}: {n} rows")


def load_points():
    import numpy as np
    rows = list(csv.DictReader(gzip.open(POINTS, "rt")))
    cols = {k: np.array([float(r[k]) for r in rows], dtype=np.float32) for k in FEATURES_V2}
    return rows, cols


def wallet_auc(wallets, groups, scores, neg_group="train_negv"):
    """Each wallet's max score; frozen wallets against neg_group wallets (Mann-Whitney, ties half)."""
    from result1 import auc
    mx = {}
    for w, s in zip(wallets, scores):
        mx[w] = max(mx.get(w, -1.0), float(s))
    g = dict(zip(wallets, groups))
    return auc([v for w, v in mx.items() if g[w] == "train_pos"], [v for w, v in mx.items() if g[w] == neg_group])


def time_holdout(X, y, groups, wallets, wt, negs, cut_ts):
    """Out-of-time inside the training period: frozen wallets whose points are all from cut_ts on (i.e.
    frozen Jan-Jun 2026) and a fixed quarter of the comparison wallets are held out; train on the rest."""
    import numpy as np
    from xgboost import XGBClassifier
    first = {}
    for w, g, t in zip(wallets, groups, X[:, -1]):
        first[w] = min(first.get(w, t), t)
    late = {w for w, t in first.items() if t >= cut_ts}
    rng = random.Random(SEED)
    neg_w = sorted({w for w, g in zip(wallets, groups) if g != "train_pos"})
    held_neg = set(rng.sample(neg_w, len(neg_w) // 4))
    va = np.array([(g == "train_pos" and w in late) or (g != "train_pos" and w in held_neg) for w, g in zip(wallets, groups)])
    tr = ~va & (((y == 1) & np.array([w not in late for w in wallets])) | np.isin(groups, negs))
    m = XGBClassifier(**PARAMS).fit(X[tr][:, :-1], y[tr], sample_weight=wt[tr])
    sc = m.predict_proba(X[va][:, :-1])[:, 1]
    return (wallet_auc(wallets[va], groups[va], sc, "train_negv"), wallet_auc(wallets[va], groups[va], sc, "train_neg"),
            int(sum(1 for w in late)))


def cv():
    import numpy as np
    from sklearn.model_selection import GroupKFold
    from xgboost import XGBClassifier
    rows, cols = load_points()
    wallets = np.array([r["wallet"] for r in rows])
    groups = np.array([r["group"] for r in rows])
    y = np.array([int(r["label"]) for r in rows])
    wt = np.array([float(r["weight"]) for r in rows])
    print(f"{len(rows)} points from {len(set(wallets))} training wallets; 5-fold CV by wallet")
    as_of = np.array([float(r["as_of"]) for r in rows], dtype=np.float64)
    cut = 1767225600  # 2026-01-01 UTC: positives first paid after this are the "future" inside training
    print(f"{'setup':48} {'CV vs volume-matched':>21} {'CV vs random':>13} {'time holdout vs v-m':>20} {'vs random':>10}")
    result = {}
    for name, (feats, negs) in SETUPS.items():
        X = np.column_stack([cols[k] for k in feats])
        oof = np.full(len(y), np.nan)
        for tr, va in GroupKFold(5).split(X, y, wallets):
            keep = tr[(y[tr] == 1) | np.isin(groups[tr], negs)]
            m = XGBClassifier(**PARAMS).fit(X[keep], y[keep], sample_weight=wt[keep])
            oof[va] = m.predict_proba(X[va])[:, 1]
        a_v, a_r = wallet_auc(wallets, groups, oof, "train_negv"), wallet_auc(wallets, groups, oof, "train_neg")
        t_v, t_r, n_late = time_holdout(np.column_stack([X, as_of]), y, groups, wallets, wt, negs, cut)
        result[name] = {"cv_auc_volume_matched": round(a_v, 4), "cv_auc_random": round(a_r, 4),
                        "time_holdout_auc_volume_matched": round(t_v, 4), "time_holdout_auc_random": round(t_r, 4),
                        "time_holdout_late_frozen_wallets": n_late}
        print(f"{name:48} {a_v:21.3f} {a_r:13.3f} {t_v:20.3f} {t_r:10.3f}")
    return result


def train(setup):
    import numpy as np
    from xgboost import XGBClassifier
    feats, negs = SETUPS[setup]
    rows, cols = load_points()
    groups = np.array([r["group"] for r in rows])
    y = np.array([int(r["label"]) for r in rows])
    wt = np.array([float(r["weight"]) for r in rows])
    keep = (y == 1) | np.isin(groups, negs)
    X = np.column_stack([cols[k] for k in feats])
    m = XGBClassifier(**PARAMS).fit(X[keep], y[keep], sample_weight=wt[keep])
    OUT.mkdir(exist_ok=True)
    m.save_model(OUT / "xgb.json")  # JSON: loads on big-endian s390x
    cv_scores = json.loads((OUT / "cv.json").read_text()) if (OUT / "cv.json").exists() else {}
    (OUT / "meta.json").write_text(json.dumps({
        "feature_set": "v2" if feats == FEATURES_V2 else "v1", "features": feats, "setup": setup,
        "negatives": list(negs), "rows": int(keep.sum()), "wallets": len({r["wallet"] for r, k in zip(rows, keep) if k}),
        "params": PARAMS, "points_per_wallet": PER_WALLET, "cv": cv_scores, "note": "weak signal only"}, indent=1))
    print(f"saved {OUT.relative_to(HERE)}/xgb.json and meta.json ({setup}, {int(keep.sum())} rows)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build":
        build()
    elif cmd == "cv":
        OUT.mkdir(exist_ok=True)
        (OUT / "cv.json").write_text(json.dumps(cv(), indent=1))
    elif cmd == "train":
        train(sys.argv[2] if len(sys.argv) > 2 else max(json.loads((OUT / "cv.json").read_text()).items(),
                                                       key=lambda kv: kv[1]["time_holdout_auc_volume_matched"])[0])
    else:
        print(__doc__)
