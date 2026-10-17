"""Weak model signal (#5): XGBoost + Keras MLP on the point-in-time features.

The score is ONE weak input to the decision engine, not a detector: against volume-matched
wallets it reaches AUC ~0.57 (docs/feasibility.md). Models are saved in portable formats
(XGBoost JSON, Keras .keras) so they load on s390x; no pickle.

    python model.py train   # train on data/features.csv train_* rows, save to models/
    python model.py         # self-check (score range, missing models -> None)

Train with the TensorFlow backend (the LinuxONE/zDNN path). A .keras file trained on another
backend makes Keras import that backend at load time; torch + TensorFlow in one process
segfaults on macOS.
"""
import csv
import json
import sys
from functools import cache
from pathlib import Path

import numpy as np

import features as F

MODELS = Path(__file__).resolve().parent / "models"
XGB, MLP, META = MODELS / "xgb.json", MODELS / "mlp.keras", MODELS / "meta.json"


def _rows():
    rows = [r for r in csv.DictReader(open(F.DATA / "features.csv")) if r["group"].startswith("train")]
    X = np.array([[float(r[f]) for f in F.FEATURES] for r in rows], dtype=np.float32)
    y = np.array([int(r["label"]) for r in rows])
    return X, y, np.array([r["address"] for r in rows])


def _fit_xgb(X, y):
    from xgboost import XGBClassifier
    return XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8,
                         eval_metric="logloss").fit(X, y)


def _fit_mlp(X, y):
    import keras
    norm = keras.layers.Normalization()
    norm.adapt(_squash(X))
    m = keras.Sequential([keras.Input((X.shape[1],)), norm,
                          keras.layers.Dense(32, activation="relu"), keras.layers.Dense(16, activation="relu"),
                          keras.layers.Dense(1, activation="sigmoid")])
    m.compile(optimizer="adam", loss="binary_crossentropy")
    m.fit(_squash(X), y, epochs=30, batch_size=128, verbose=0)
    return m


def _squash(X):
    """Signed log: USD amounts are heavy-tailed, the MLP wants them on a log scale."""
    return (np.log1p(np.abs(X)) * np.sign(X)).astype(np.float32)


def train():
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupShuffleSplit
    X, y, wallets = _rows()
    tr, va = next(GroupShuffleSplit(1, test_size=0.2, random_state=0).split(X, y, wallets))  # by wallet
    assert not set(wallets[tr]) & set(wallets[va])
    xgb, mlp = _fit_xgb(X[tr], y[tr]), _fit_mlp(X[tr], y[tr])
    p_xgb = xgb.predict_proba(X[va])[:, 1]
    p_mlp = mlp.predict(_squash(X[va]), verbose=0).ravel()
    auc = {k: round(float(roc_auc_score(y[va], p)), 3)
           for k, p in (("xgb", p_xgb), ("mlp", p_mlp), ("mean", (p_xgb + p_mlp) / 2))}
    print("validation AUC (train period, split by wallet):", auc)
    # Final models on every training row.
    MODELS.mkdir(exist_ok=True)
    _fit_xgb(X, y).save_model(XGB)
    _fit_mlp(X, y).save(MLP)
    META.write_text(json.dumps({"features": F.FEATURES, "rows": int(len(y)), "positives": int(y.sum()),
                                "wallets": int(len(set(wallets))), "validation_auc": auc,
                                "out_of_time_auc_volume_matched": 0.565, "note": "weak signal only"}, indent=1))
    _load.cache_clear()


@cache
def _load():
    """Whatever models are present; an empty dict when none load (engine then decides without us)."""
    loaded = {}
    if XGB.exists():
        try:
            from xgboost import XGBClassifier
            m = XGBClassifier()
            m.load_model(XGB)
            loaded["xgb"] = m
        except Exception as e:  # ponytail: a broken model must never break a withdrawal decision
            print("xgb not loaded:", e, file=sys.stderr)
    if MLP.exists():
        try:
            import keras
            loaded["mlp"] = keras.models.load_model(MLP)
        except Exception as e:
            print("mlp not loaded:", e, file=sys.stderr)
    return loaded


def score(feats):
    """Mean P(frozen-like) over the loaded models for one features() dict, or None if no model loaded."""
    models = _load()
    if not models:
        return None
    x = np.array([[float(feats[f]) for f in F.FEATURES]], dtype=np.float32)
    ps = []
    if "xgb" in models:
        ps.append(float(models["xgb"].predict_proba(x)[0, 1]))
    if "mlp" in models:
        import keras
        ps.append(float(keras.ops.convert_to_numpy(models["mlp"](_squash(x), training=False)).ravel()[0]))
    return sum(ps) / len(ps)


def _self_check():
    global XGB, MLP
    zero = {f: 0.0 for f in F.FEATURES}
    busy = {**zero, "age_h": 24, "n_pay_in": 5, "n_senders_in": 3, "usd_in": 250_000, "usd_out": 249_000,
            "out_in_ratio": 0.996, "max_in_usd": 120_000, "share_in_from_hot_wallets": 1.0, "median_hold_h": 0.5}
    s = score(busy)
    assert s is not None, "no model loaded: run `python model.py train` first"
    assert 0.0 <= s <= 1.0 and 0.0 <= score(zero) <= 1.0, s
    print(f"loaded {sorted(_load())}; score(busy)={s:.3f}, score(empty)={score(zero):.3f}")
    # Missing models: the signal is absent (None), never an exception.
    XGB, MLP = MODELS / "missing.json", MODELS / "missing.keras"
    _load.cache_clear()
    assert score(busy) is None
    print("self-check passed: scores in [0, 1]; missing models -> None")


if __name__ == "__main__":
    train() if sys.argv[1:] == ["train"] else _self_check()
