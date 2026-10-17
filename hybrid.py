"""Hybrid wallet model (experiment): v1 (#5, models/) for small wallets, v2 (models_v2/) for large ones.

Routing and scale are fixed before the test set is looked at:
- route on usd_in, the USDT the wallet received before this payment: under ROUTE_USDT (1,000, the
  engine's large-payment line) -> v1, otherwise v2;
- the two models' scores aren't on one scale, so each becomes its percentile among the training
  period's normal payments (data/model_v2/train_points.csv.gz, train_neg + train_negv rows).

    python hybrid.py build    # needs xgboost + keras: write models_hybrid/meta.json (calibration)
    python hybrid.py check    # self-check of routing and percentiles (no model needed)

Scored with: python model_report.py --models models_hybrid   (reports v1, v2 and hybrid together)
"""
import bisect
import csv
import gzip
import json
import sys
from pathlib import Path

import features as F
from features_v2 import FEATURES_V2

HERE = Path(__file__).resolve().parent
OUT = HERE / "models_hybrid"
ROUTE_FEATURE, ROUTE_USDT = "usd_in", 1000.0
QUANTILES = 1001


def percentile(sorted_q, s):
    """Share of the calibration scores below s, from QUANTILES evenly spaced quantiles."""
    return bisect.bisect_left(sorted_q, s) / len(sorted_q)


def route(usd_in):
    return "v2" if usd_in >= ROUTE_USDT else "v1"


def v1_scorer():
    import numpy as np
    import model
    m = model._load()
    assert m, "no v1 model"
    parts = []
    if "xgb" in m:
        parts.append(lambda x: m["xgb"].predict_proba(x)[:, 1])
    if "mlp" in m:
        parts.append(lambda x: np.asarray(m["mlp"](model._squash(x))).ravel())
    return lambda x: sum(p(x) for p in parts) / len(parts)  # = model.score(), batched


def v2_scorer(folder=HERE / "models_v2"):
    from xgboost import XGBClassifier
    m = XGBClassifier()
    m.load_model(Path(folder) / "xgb.json")
    return lambda x: m.predict_proba(x)[:, 1]


def scorers(meta):
    """{"v1", "v2", "hybrid"} batch scorers on a FEATURES_V2 matrix (its first 12 columns are v1's features)."""
    import numpy as np
    n1, i = len(F.FEATURES), FEATURES_V2.index(ROUTE_FEATURE)
    assert FEATURES_V2[:n1] == F.FEATURES
    s1, s2 = v1_scorer(), v2_scorer()
    q1, q2 = meta["calibration"]["v1"], meta["calibration"]["v2"]

    def hybrid(x):
        a, b = s1(x[:, :n1]), s2(x)
        return np.array([percentile(q2, bb) if route(u) == "v2" else percentile(q1, aa)
                         for aa, bb, u in zip(a, b, x[:, i])])
    return {"v1": lambda x: s1(x[:, :n1]), "v2": s2, "hybrid": hybrid}


def build():
    import numpy as np
    rows = [r for r in csv.DictReader(gzip.open(F.DATA / "model_v2" / "train_points.csv.gz", "rt")) if r["label"] == "0"]
    x = np.array([[float(r[k]) for k in FEATURES_V2] for r in rows], dtype=np.float32)
    n1 = len(F.FEATURES)
    cal = {}
    for name, sc in (("v1", lambda x: v1_scorer()(x[:, :n1])), ("v2", v2_scorer())):
        s = np.sort(sc(x))
        cal[name] = [float(v) for v in np.quantile(s, np.linspace(0, 1, QUANTILES))]
    OUT.mkdir(exist_ok=True)
    (OUT / "meta.json").write_text(json.dumps({
        "feature_set": "hybrid", "features": FEATURES_V2, "route_feature": ROUTE_FEATURE, "route_usdt": ROUTE_USDT,
        "v1": "models/ (#5: XGBoost + MLP)", "v2": "models_v2/ (XGBoost, 26 features)",
        "calibration_rows": len(rows), "calibration": cal,
        "note": "experiment; routing and scale fixed before the test set was scored"}, indent=1))
    print(f"wrote {OUT.relative_to(HERE)}/meta.json: calibration on {len(rows)} training normal payments")


def _self_check():
    q = [i / 10 for i in range(11)]
    assert percentile(q, -1) == 0 and percentile(q, 0.55) == 6 / 11 and percentile(q, 2) == 1
    assert route(999.99) == "v1" and route(1000) == "v2" and route(0) == "v1"
    assert FEATURES_V2[:len(F.FEATURES)] == F.FEATURES and ROUTE_FEATURE in FEATURES_V2
    print("self-check passed: routing at 1,000 USDT received, percentiles, feature order")


if __name__ == "__main__":
    {"build": build, "check": _self_check}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: print(__doc__))()
