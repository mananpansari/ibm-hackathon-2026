"""Five quick hypotheses to improve the v1 wallet model, tested on ONE training-period time holdout.

Holdout (the same for every variant; the Jul-Oct 2026 test set is never read):
- frozen wallets whose first training point is from 2026-01-01 on (frozen Jan-Jun 2026),
- a fixed quarter of the comparison wallets (random and volume-matched),
scored just before each payment (data/model_v2/train_points.csv.gz rows), as the engine scores.
Every variant trains only on the other wallets.

    python hypotheses.py      # needs xgboost, keras + tensorflow (the lab container)

Variants (12 v1 features unless noted):
  v1 recipe     XGBoost + MLP averaged, trained on the 4 snapshots per wallet (features.csv), all negatives
  H1            XGBoost alone, same rows
  H2            XGBoost, snapshots, negatives re-weighted to the positives' payment-size spread
  H2b           XGBoost, snapshots, volume-matched negatives only
  H3            XGBoost, every payment (train_points), all negatives
  H3+H2b        XGBoost, every payment, volume-matched negatives only
  H4            H3 with monotonic constraints: fewer senders and longer holding -> higher score
  H5            H3 without hack-like frozen wallets in training (a single payment >= 1M USDT, <= 2 senders)
"""
import csv
import gzip
import random
from pathlib import Path

import numpy as np

import features as F
from result1 import auc, threshold

DATA = F.DATA
CUT = 1767225600  # 2026-01-01 UTC
SEED = 0
PARAMS = dict(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8, eval_metric="logloss")  # model.py's v1 settings
IDX = {f: i for i, f in enumerate(F.FEATURES)}


def rows(path, gz=False):
    return list(csv.DictReader(gzip.open(path, "rt") if gz else open(path)))


def matrix(rs):
    return np.array([[float(r[f]) for f in F.FEATURES] for r in rs], dtype=np.float32)


def split():
    """Held-out wallet set, fixed across variants."""
    pts = rows(DATA / "model_v2" / "train_points.csv.gz", gz=True)
    first = {}
    for r in pts:
        first[r["wallet"]] = min(first.get(r["wallet"], 1e18), float(r["as_of"]))
    late = {w for r in pts if r["group"] == "train_pos" for w in [r["wallet"]] if first[w] >= CUT}
    neg = sorted({r["wallet"] for r in pts if r["group"] != "train_pos"})
    held_neg = set(random.Random(SEED).sample(neg, len(neg) // 4))
    return pts, late | held_neg


def evaluate(score, val):
    """Wallet-max AUC and recall@5% vs volume-matched; payment AUC; scam payments flagged at a 1% payment budget."""
    X = matrix(val)
    s = score(X)
    g = [r["group"] for r in val]
    w = [r["wallet"] for r in val]
    mx = {}
    for wi, si in zip(w, s):
        mx[wi] = max(mx.get(wi, -1), float(si))
    grp = dict(zip(w, g))
    pos = [v for k, v in mx.items() if grp[k] == "train_pos"]
    negv = [v for k, v in mx.items() if grp[k] == "train_negv"]
    neg = [v for k, v in mx.items() if grp[k] == "train_neg"]
    t5 = threshold(negv, 0.05)
    pp = [float(si) for si, gi in zip(s, g) if gi == "train_pos"]
    pn = sorted(float(si) for si, gi in zip(s, g) if gi == "train_negv")
    t1p = pn[-max(1, len(pn) // 100)]
    return {"wallet_auc_vm": auc(pos, negv), "recall5_vm": sum(x >= t5 for x in pos) / len(pos),
            "payment_auc_vm": auc(pp, pn), "pay_flag_1pct": sum(x >= t1p for x in pp) / len(pp),
            "wallet_auc_random": auc(pos, neg), "pos_wallets": len(pos)}


def xgb(X, y, w=None, mono=None):
    from xgboost import XGBClassifier
    p = dict(PARAMS)
    if mono:
        p["monotone_constraints"] = "(" + ",".join(str(mono.get(f, 0)) for f in F.FEATURES) + ")"
    m = XGBClassifier(**p).fit(X, y, sample_weight=w)
    return lambda Z: m.predict_proba(Z)[:, 1]


def size_weights(rs, y):
    """Negatives re-weighted so their max_in_usd decile spread matches the positives' (positives weight 1)."""
    v = np.array([float(r["max_in_usd"]) for r in rs])
    edges = np.quantile(v[y == 1], np.linspace(0, 1, 11)[1:-1])
    b = np.searchsorted(edges, v)
    pos_share = np.bincount(b[y == 1], minlength=10) / max(1, (y == 1).sum())
    neg_share = np.bincount(b[y == 0], minlength=10) / max(1, (y == 0).sum())
    w = np.ones(len(y))
    w[y == 0] = (pos_share[b[y == 0]] / np.maximum(neg_share[b[y == 0]], 1e-9))
    return w


def main():
    import model
    pts, held = split()
    val = [r for r in pts if r["wallet"] in held]
    snap = [r for r in rows(DATA / "features.csv") if r["group"].startswith("train") and r["address"] not in held]
    pay = [r for r in pts if r["wallet"] not in held]
    ys = np.array([int(r["label"]) for r in snap])
    yp = np.array([int(r["label"]) for r in pay])
    wp = np.array([float(r["weight"]) for r in pay])
    Xs, Xp = matrix(snap), matrix(pay)
    vm_s = np.array([r["group"] != "train_neg" for r in snap])
    vm_p = np.array([r["group"] != "train_neg" for r in pay])

    # H5: hack-like frozen wallets, from their own history (a single payment >= 1M USDT and <= 2 senders at any point)
    hacky = {r["wallet"] for r in pts if r["group"] == "train_pos" and float(r["max_in_usd"]) >= 1e6 and float(r["n_senders_in"]) <= 2}
    keep5 = np.array([not (r["group"] == "train_pos" and r["wallet"] in hacky) for r in pay])

    variants = {}
    xs = xgb(Xs, ys)
    mlp = model._fit_mlp(Xs, ys)
    import keras
    m_score = lambda Z: keras.ops.convert_to_numpy(mlp(model._squash(Z), training=False)).ravel()
    variants["v1 recipe (XGBoost + MLP, snapshots)"] = lambda Z: (xs(Z) + m_score(Z)) / 2
    variants["H1 XGBoost alone"] = xs
    variants["H2 size-reweighted negatives"] = xgb(Xs, ys, size_weights(snap, ys))
    variants["H2b volume-matched negatives only"] = xgb(Xs[vm_s], ys[vm_s])
    variants["H3 every payment"] = xgb(Xp, yp, wp)
    variants["H3+H2b every payment, volume-matched"] = xgb(Xp[vm_p], yp[vm_p], wp[vm_p])
    variants["H4 monotonic (senders -, holding +)"] = xgb(Xp, yp, wp, mono={"n_senders_in": -1, "median_hold_h": 1})
    variants["H5 no hack-like frozen wallets"] = xgb(Xp[keep5], yp[keep5], wp[keep5])

    print(f"holdout: {len({r['wallet'] for r in val if r['group'] == 'train_pos'})} frozen wallets (2026 H1), "
          f"{len({r['wallet'] for r in val if r['group'] != 'train_pos'})} comparison wallets, {len(val)} payments; "
          f"H5 drops {len(hacky)} hack-like frozen wallets from training")
    print(f"{'variant':40} {'wallet AUC v-m':>14} {'recall@5% v-m':>14} {'payment AUC v-m':>16} {'pay flag @1%':>13} {'wallet AUC rnd':>15}")
    out = {}
    for name, f in variants.items():
        e = evaluate(f, val)
        out[name] = e
        print(f"{name:40} {e['wallet_auc_vm']:14.3f} {e['recall5_vm']:14.1%} {e['payment_auc_vm']:16.3f} {e['pay_flag_1pct']:13.1%} {e['wallet_auc_random']:15.3f}")
    import json
    Path("docs").mkdir(exist_ok=True)
    (Path("docs") / "hypotheses_v1.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
