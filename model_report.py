"""Model scorecard: how the wallet model (#5) is actually doing, tracked from run to run.

Scores every test payment once with the models in models/ (or a candidate folder) and reports the
honest numbers: out-of-time, against volume-matched comparison wallets first (random ones only as
context). Each run is appended to docs/model_scores.jsonl and docs/model_scores.md is rewritten, so a
new model is always judged on the same yardstick as the one it would replace.

    python model_report.py                                # current models/: print, append, rewrite the table
    python model_report.py --models DIR --label "name"    # a candidate in DIR (xgb.json, mlp.keras, meta.json)
    python model_report.py --no-save                      # print only
    python model_report.py check                          # self-check of the metrics (no model needed)

Needs xgboost (and keras + tensorflow for the MLP): run it in the LinuxONE lab container, where the
models were trained. A copy there has no .git, so pass the commit and host:

    MODEL_REPORT_COMMIT=<short hash> MODEL_REPORT_HOST="LinuxONE lab container" python model_report.py

Definitions follow result1.py, and on the same models the numbers match its saved score points
(data/results/result1_points.csv.gz). Scoring all ~155k test payments takes about 10 minutes on the VM.

Rule: tune on the training period, then look here. Don't change a model because of these test numbers
and report the improvement; that's fitting to the test set.
"""
import argparse
import bisect
import csv
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import features as F
from result1 import auc, inbound, load, threshold

HERE = Path(__file__).resolve().parent
HISTORY = HERE / "docs" / "model_scores.jsonl"
TABLE = HERE / "docs" / "model_scores.md"
DAY = 86400
BASES = {"test_negv": "volume-matched", "test_neg": "random"}  # headline first
SPLITS = 200


# ---------- metrics (pure functions: lists of numbers in, numbers out) ----------

def recall_at(pos, comp_max, fa, window_days=None):
    """Wallet level. pos = [(ts list, score list, freeze_ts)]; comp_max = comparison wallets' max scores.
    The threshold flags <= fa of comparison wallets; a positive counts if any payment before its freeze
    (only the last `window_days` if given) reaches it."""
    t = threshold(comp_max, fa)
    hit = 0
    for ts, sc, fz in pos:
        lo = fz - window_days * DAY if window_days else -math.inf
        hit += any(s >= t for x, s in zip(ts, sc) if lo <= x < fz)
    return hit / len(pos), t


def held_out_recall(pos, comp_max, fa, splits=SPLITS, seed=0):
    """Median recall when one half of the comparison wallets sets the threshold (as in Result 1)."""
    idx, out = list(range(len(comp_max))), []
    for s in range(splits):
        random.Random(seed + s).shuffle(idx)
        half = [comp_max[i] for i in idx[:len(idx) // 2]]
        out.append(recall_at(pos, half, fa)[0])
    out.sort()
    return out[len(out) // 2]


def payment_level(pos_scores, comp_scores, fa):
    """Payment level, as the engine uses the score: threshold flags `fa` of comparison payments;
    returns (share of scam payments flagged, threshold)."""
    c = sorted(comp_scores)
    k = math.floor(fa * len(c) + 1e-9)
    t = c[-k] if k else math.nextafter(c[-1], math.inf)  # >= t flags at most k comparison payments (ties aside)
    return sum(s >= t for s in pos_scores) / len(pos_scores), t


def flagged_at(pos_scores, comp_scores, t):
    return sum(s >= t for s in pos_scores) / len(pos_scores), sum(s >= t for s in comp_scores) / len(comp_scores)


def card(pos, comps, engine_flag):
    """All the numbers for one scorer. pos = [(ts, scores, freeze_ts)], comps = {basis: [scores per wallet]}."""
    pos_max = [max(sc) for _, sc, _ in pos]
    pos_all = [s for _, sc, _ in pos for s in sc]
    out = {}
    for basis, wallets in comps.items():
        cmax = [max(w) for w in wallets]
        call = [s for w in wallets for s in w]
        r1, t1 = recall_at(pos, cmax, 0.01)
        r5, t5 = recall_at(pos, cmax, 0.05)
        r5_90, _ = recall_at(pos, cmax, 0.05, window_days=90)
        p1, pt1 = payment_level(pos_all, call, 0.01)
        ef_pos, ef_comp = flagged_at(pos_all, call, engine_flag)
        out[basis] = {
            "auc_wallet": auc(pos_max, cmax), "auc_payment": auc(pos_all, call),
            "recall_1pct": r1, "threshold_1pct": t1, "recall_1pct_held_out": held_out_recall(pos, cmax, 0.01),
            "recall_5pct": r5, "recall_5pct_within_90d": r5_90,
            "payments_flagged_at_1pct_payments": p1, "payment_threshold_1pct": pt1,
            "engine_flag": engine_flag, "engine_flag_scam_payments": ef_pos, "engine_flag_comparison_payments": ef_comp,
            "comparison_wallets": len(wallets), "comparison_payments": len(call)}
    return out


# ---------- scoring the test set ----------

def load_v2(folder):
    """A v2 candidate (train_v2.py): XGBoost only, on features_v2. Returns (scorers, feature fn, names, meta)."""
    from xgboost import XGBClassifier
    from features_v2 import features_v2
    d = Path(folder)
    meta = json.loads((d / "meta.json").read_text())
    m = XGBClassifier()
    m.load_model(d / "xgb.json")
    return {"xgb": lambda x: m.predict_proba(x)[:, 1]}, features_v2, meta["features"], meta


def load_models(folder):
    import model
    if folder:
        d = Path(folder)
        model.XGB, model.MLP, model.META = d / "xgb.json", d / "mlp.keras", d / "meta.json"
        model._load.cache_clear()
    models = model._load()
    if not models:
        raise SystemExit(f"no model loaded from {folder or model.XGB.parent}")
    return model, models


def scorers(model, models):
    import numpy as np
    out = {}
    if "xgb" in models:
        out["xgb"] = lambda x: models["xgb"].predict_proba(x)[:, 1]
    if "mlp" in models:
        out["mlp"] = lambda x: np.asarray(models["mlp"](model._squash(x))).ravel()
    if len(out) > 1:
        parts = list(out.values())
        out["ensemble"] = lambda x: sum(f(x) for f in parts) / len(parts)  # what model.score() returns
    return out


def feature_points(hs, bad, frozen_at, ofac, feature_fn=F.features, names=F.FEATURES):
    """{group: [(address, ts list, feature matrix, freeze_ts)]}, one row per inbound payment >= 10 USDT."""
    import numpy as np
    out = {}
    for g, wallets in hs.items():
        rows = []
        for h in wallets:
            if g == "test_pos" and h["address"] in ofac:
                continue
            pays = inbound(h)
            if not pays:
                continue  # can never be flagged: left out, as in Result 1
            X = np.array([[float(feature_fn(h, t["ts"], bad, frozen_at)[k]) for k in names] for t in pays],
                         dtype=np.float32)
            rows.append((h["address"], [t["ts"] for t in pays], X, h.get("freeze_ts")))
        out[g] = rows
    return out


def file_hash(paths):
    h = hashlib.sha256()
    for p in paths:
        h.update(Path(p).read_bytes() if Path(p).exists() else b"-")
    return h.hexdigest()[:12]


def git_commit():
    if os.environ.get("MODEL_REPORT_COMMIT"):  # a copy without .git (e.g. the VM container) says which commit it is
        return os.environ["MODEL_REPORT_COMMIT"]
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=HERE).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "models", "model.py", "features.py"],
                               capture_output=True, text=True, cwd=HERE).stdout.strip()
        return (rev or "unknown") + ("+changes" if dirty else "")
    except OSError:
        return "unknown"


def run(folder, label, save):
    import numpy as np
    from engine import Config
    t0 = time.time()
    kind = json.loads((Path(folder) / "meta.json").read_text()).get("feature_set") if folder else None
    v2 = kind == "v2"
    train = {r["address"] for r in csv.DictReader(open(F.DATA / "features.csv")) if r["group"].startswith("train")}
    v2_points = F.DATA / "model_v2" / "train_points.csv.gz"
    if v2_points.exists():
        import gzip
        train |= {r["wallet"] for r in csv.DictReader(gzip.open(v2_points, "rt"))}
    hs, bad, frozen_at, ofac = load()
    assert not {h["address"] for g in hs.values() for h in g} & train, "test wallets in the training rows: stop"
    if kind == "hybrid":  # v1, v2 and the size-routed hybrid, all from one features_v2 pass
        import hybrid
        from features_v2 import FEATURES_V2, features_v2
        meta = json.loads((Path(folder) / "meta.json").read_text())
        score_fns = hybrid.scorers(meta)
        pts = feature_points(hs, bad, frozen_at, ofac, features_v2, FEATURES_V2)
        files = [HERE / "models" / "xgb.json", HERE / "models" / "mlp.keras", HERE / "models_v2" / "xgb.json", Path(folder) / "meta.json"]
    elif v2:
        score_fns, feature_fn, names, meta = load_v2(folder)
        pts = feature_points(hs, bad, frozen_at, ofac, feature_fn, names)
        files = [Path(folder) / "xgb.json"]
    else:
        model, models = load_models(folder)
        score_fns = scorers(model, models)
        pts = feature_points(hs, bad, frozen_at, ofac)
        one = pts["test_pos"][0]  # batch scoring == model.score() on the same features
        assert abs(float(score_fns[list(score_fns)[-1]](one[2][:1])[0])
                   - model.score(dict(zip(F.FEATURES, map(float, one[2][0]))))) < 1e-5
        meta = json.loads(model.META.read_text()) if model.META.exists() else {}
        files = [model.XGB, model.MLP]
    entry = {"when": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "label": label,
             "commit": git_commit(), "models": file_hash(files),
             "validation_auc_train_period": meta.get("validation_auc") or meta.get("cv"),
             "positives": len(pts["test_pos"]), "positive_payments": sum(len(r[1]) for r in pts["test_pos"]),
             "scores": {}}
    for name, f in score_fns.items():
        sc = lambda rows: [list(map(float, f(X))) for _, _, X, _ in rows]
        pos = [(ts, s, fz) for (_, ts, _, fz), s in zip(pts["test_pos"], sc(pts["test_pos"]))]
        entry["scores"][name] = card(pos, {b: sc(pts[b]) for b in BASES}, Config().model_flag)
    entry["seconds"] = round(time.time() - t0)
    entry["ran_on"] = os.environ.get("MODEL_REPORT_HOST", "")
    print_card(entry)
    if save:
        HISTORY.parent.mkdir(exist_ok=True)
        with open(HISTORY, "a") as fh:
            fh.write(json.dumps(entry) + "\n")
        write_table()
        print(f"\nappended to {HISTORY.relative_to(HERE)}; rewrote {TABLE.relative_to(HERE)}")


# ---------- output ----------

def pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def print_card(e):
    print(f"\nModel scorecard: {e['label']}  (models {e['models']}, commit {e['commit']}, {e['when']})")
    print(f"test: {e['positives']} frozen wallets, {e['positive_payments']} payments before the freeze")
    if e.get("validation_auc_train_period"):
        print(f"training-period validation AUC (flattering, size-driven): {e['validation_auc_train_period']}")
    for name, by in e["scores"].items():
        print(f"\n[{name}]")
        print(f"  {'':34}" + "".join(f"{BASES[b]:>16}" for b in BASES))
        rows = [("AUC, wallet max score", "auc_wallet", lambda v: f"{v:.3f}"),
                ("AUC, per payment", "auc_payment", lambda v: f"{v:.3f}"),
                ("recall @1% false alarms (wallets)", "recall_1pct", pct),
                ("  same, held-out threshold", "recall_1pct_held_out", pct),
                ("recall @5% false alarms", "recall_5pct", pct),
                ("  only flags within 90 days", "recall_5pct_within_90d", pct),
                ("scam payments flagged @1% payments", "payments_flagged_at_1pct_payments", pct),
                (f"engine cut {by[next(iter(BASES))]['engine_flag']}: scam payments", "engine_flag_scam_payments", pct),
                ("  comparison payments", "engine_flag_comparison_payments", pct)]
        for title, key, fmt in rows:
            print(f"  {title:34}" + "".join(f"{fmt(by[b][key]):>16}" for b in BASES))


def write_table():
    entries = [json.loads(l) for l in open(HISTORY)] if HISTORY.exists() else []
    head = "volume-matched"
    lines = ["# Model scorecard history", "",
             "Written by `python model_report.py` (one row per run; full numbers in `docs/model_scores.jsonl`).", "",
             "Out-of-time test: the Jul-Oct 2026 frozen wallets against **volume-matched** comparison wallets "
             "(random wallets in the last column, for context only). Each wallet is scored just before every payment "
             "it received. AUC: chance a frozen wallet scores above a comparison wallet (0.5 = coin flip). Recall @1%: "
             "share of frozen wallets flagged when only 1% of comparison wallets are; held-out sets that cut on half the "
             "comparison wallets. Within 90 days: only flags in the last 90 days before the freeze count. Engine cut: share "
             "of scam payments the engine's `Config.model_flag` turns into a question, and the same for comparison payments.", "",
             "Training-period validation AUC is in the jsonl; it is size-driven and not a measure of progress.", "",
             f"| When | Label | Models | Scorer | AUC ({head}) | Recall @1% | Held-out @1% | @5%, last 90 d | Engine cut: scam / comparison payments | AUC (random) |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for e in entries:
        for name, by in e["scores"].items():
            v, r = by["test_negv"], by["test_neg"]
            lines.append(f"| {e['when']} | {e['label']} | `{e['models']}` | {name} | {v['auc_wallet']:.3f} | {pct(v['recall_1pct'])} | "
                         f"{pct(v['recall_1pct_held_out'])} | {pct(v['recall_5pct_within_90d'])} | "
                         f"{pct(v['engine_flag_scam_payments'])} / {pct(v['engine_flag_comparison_payments'])} | {r['auc_wallet']:.3f} |")
    TABLE.write_text("\n".join(lines) + "\n")


# ---------- self-check ----------

def _self_check():
    # Perfect scorer: every frozen wallet above every comparison wallet.
    pos = [([10, 20], [0.9, 0.95], 30), ([5], [0.99], 6)]
    comp = [[0.1, 0.2], [0.3], [0.05]]
    cmax = [max(w) for w in comp]
    assert auc([0.95, 0.99], cmax) == 1.0 and auc([0.0, 0.0], cmax) == 0.0 and auc([0.3], [0.3]) == 0.5
    assert recall_at(pos, cmax, 0.01)[0] == 1.0
    # The 90-day window only counts flags in the last 90 days before the freeze.
    late = [([0, 200 * DAY], [0.99, 0.0], 210 * DAY)]
    assert recall_at(late, cmax, 0.05)[0] == 1.0 and recall_at(late, cmax, 0.05, window_days=90)[0] == 0.0
    # Payments after the freeze never count.
    assert recall_at([([40], [0.99], 30)], cmax, 0.05)[0] == 0.0
    # Payment-level cut: flags at most 1% of comparison payments.
    comp_pay = [i / 1000 for i in range(1000)]
    share, t = payment_level([0.5, 0.995, 0.999], comp_pay, 0.01)
    assert sum(s >= t for s in comp_pay) <= 10 and share == 2 / 3, (share, t)
    assert flagged_at([0.8, 0.2], [0.9, 0.1, 0.1, 0.1], 0.5) == (0.5, 0.25)
    # Held-out recall on a perfect scorer stays perfect.
    assert held_out_recall(pos, cmax * 40, 0.01, splits=5) == 1.0
    # The card has every number for both bases.
    c = card(pos, {"test_negv": comp, "test_neg": comp}, 0.78)
    assert set(c) == {"test_negv", "test_neg"} and c["test_negv"]["auc_wallet"] == 1.0
    print("self-check passed: AUC, recall, 90-day window, freeze cut-off, payment-level cut, held-out split")


if __name__ == "__main__":
    if sys.argv[1:] == ["check"]:
        _self_check()
    else:
        ap = argparse.ArgumentParser(description="Score the wallet model on the out-of-time test set.")
        ap.add_argument("--models", help="folder with xgb.json / mlp.keras / meta.json (default: models/)")
        ap.add_argument("--label", default="current models/", help="name for this run in the history")
        ap.add_argument("--no-save", action="store_true", help="print only; don't append to the history")
        a = ap.parse_args()
        run(a.models, a.label, not a.no_save)
