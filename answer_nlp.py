"""Free-text answer classifier (B): mpnet sentence embeddings + logistic regression.

Drop-in for granite's classify(): classify(text) -> {"scam_type", "confirms_script", "source", "p"}, so app.py
plugs it in with one line (FREE_TEXT = types.SimpleNamespace(classify=answer_nlp.classify)).
- Embeddings: sentence-transformers/all-mpnet-base-v2 at a pinned revision, mean-pooled and L2-normalised, on
  NNPA when torch_nnpa is installed (the LinuxONE lab image), else Apple GPU, else CPU.
- Head: 768 weights + bias in models/answer_clf.json (plain JSON, so it loads the same on s390x; no pickle).
- p is the head's score, not a calibrated probability (trained with balanced classes on synthetic answers).
- Keyword floor: an answer is flagged if granite's keyword rules OR the model flag it, so the model can only add
  catches, never release one the rules would flag (they also read the whole text; the model reads 256 tokens).
- The scam type comes from granite's keyword rules when they name one, else "other".
- If torch, transformers or the mpnet weights are missing, it returns granite.keyword_classify() instead.

Results, data and caveats: docs/answer-classifier.md.

    python answer_nlp.py train   # refit the head on data/answers_train.csv -> models/answer_clf.json
    python answer_nlp.py         # self-check (shape, SG answers, missing model -> keyword fallback)

On the VM, mount a Hugging Face cache that already holds the model and set HF_HOME and HF_HUB_OFFLINE=1.
"""
import csv
import json
import sys
from functools import cache
from pathlib import Path

import granite

HERE = Path(__file__).resolve().parent
CLF = HERE / "models" / "answer_clf.json"
TRAIN = HERE / "data" / "answers_train.csv"
EMBEDDER = "sentence-transformers/all-mpnet-base-v2"
REVISION = "e8c3b32edf5434bc2275fc9bab85f82640a19130"


@cache
def _model():
    """(tokenizer, model, device), or None when anything is missing: the caller then uses the keyword rules."""
    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
        try:
            import torch_nnpa  # noqa: F401  IBM's backend for the on-chip AI accelerator
            dev = "nnpa"
        except ImportError:
            dev = "mps" if torch.backends.mps.is_available() else "cpu"
        tok = AutoTokenizer.from_pretrained(EMBEDDER, revision=REVISION)
        return tok, AutoModel.from_pretrained(EMBEDDER, revision=REVISION).eval().to(dev), dev
    except Exception as e:  # ponytail: a missing model must never break a withdrawal decision
        print("answer_nlp: embedder not loaded, using keyword rules:", e, file=sys.stderr)
        return None


@cache
def _head():
    return json.loads(CLF.read_text()) if CLF.exists() else None


def embed(texts):
    import torch
    tok, model, dev = _model()
    with torch.no_grad():
        b = tok(texts, padding=True, truncation=True, max_length=256, return_tensors="pt").to(dev)
        h = model(**b).last_hidden_state
        m = b["attention_mask"].unsqueeze(-1)
        return torch.nn.functional.normalize((h * m).sum(1) / m.sum(1), dim=1).cpu().numpy()


def score(text):
    """The head's score in [0, 1], or None without the embedder or the weights."""
    head = _head()
    if head is None or _model() is None:
        return None
    import numpy as np
    z = float(embed([" ".join(text.split())])[0] @ np.array(head["coef"], dtype=np.float32) + head["intercept"])
    return 1 / (1 + np.exp(-z))


def classify(text):
    kw = granite.keyword_classify(text)
    p = score(text)
    if p is None:
        return kw
    model_flag = p >= _head()["threshold"]
    confirms = model_flag or kw["confirms_script"]  # keyword floor: the model may add catches, never drop one
    kind = (kw["scam_type"] if kw["scam_type"] != "none" else "other") if confirms else "none"
    source = ("mpnet answer classifier" + (" + keyword rules" if kw["confirms_script"] else "") if model_flag
              else "keyword rules (floor)" if confirms else "mpnet answer classifier")
    return {"scam_type": kind, "confirms_script": bool(confirms), "source": source, "p": round(float(p), 3)}


def train(threshold=0.58):
    """Refit the head. Each source (synth_v1, persona_agents) gets equal total weight and balanced classes, as in the
    data comparison; threshold 0.58 is the median of the card-grouped CV thresholds (<= 10% false flags)."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    rows = list(csv.DictReader(open(TRAIN, encoding="utf-8")))
    X = embed([r["answer"] for r in rows])
    y = np.array([int(r["label"]) for r in rows])
    src = np.array([r["source"] for r in rows])
    w = np.zeros(len(y))
    for s in set(src):
        for c in (0, 1):
            m = (src == s) & (y == c)
            w[m] = 0.5 / m.sum()
    lr = LogisticRegression(max_iter=5000, C=2).fit(X, y, sample_weight=w * len(y))
    CLF.write_text(json.dumps({"embedder": EMBEDDER, "revision": REVISION, "threshold": threshold,
                               "pooling": "mean over attention mask, L2-normalised, max_length 256",
                               "trained_on": f"{TRAIN.name}: {len(y)} answers ({', '.join(sorted(set(src)))})",
                               "coef": [round(float(v), 6) for v in lr.coef_[0]], "intercept": float(lr.intercept_[0])}))
    _head.cache_clear()
    print(f"wrote {CLF.name}: {len(y)} training answers, threshold {threshold}")


def _self_check():
    global CLF
    r = classify("The police officer said my account is under investigation and I must move my savings to a safe wallet")
    assert set(r) >= {"scam_type", "confirms_script", "source"} and r["scam_type"] in granite.SCAM_TYPES + ["other"], r
    assert r["confirms_script"], r
    assert not classify("Moving my coins from Binance to my own Ledger, same as every month")["confirms_script"]
    if r["source"].startswith("mpnet"):
        sg = list(csv.DictReader(open(HERE / "data" / "sg_answers.csv", encoding="utf-8")))
        res = [(classify(a["answer"]), a["confirms_script"] == "1") for a in sg]
        caught = sum(c["confirms_script"] for c, s in res if s); flagged = sum(c["confirms_script"] for c, s in res if not s)
        print(f"SG answers (not in training): {caught}/{sum(s for _, s in res)} scams caught, "
              f"{flagged}/{sum(not s for _, s in res)} legit flagged; device {_model()[2]}")
        assert caught >= 18 and flagged <= 3, "SG answers regressed against the documented 21/21 caught, 2/9 flagged"
        # Keyword floor: a low model score never releases an answer the rules flag, even past the 256-token cut
        global score
        real = score
        try:
            score = lambda text: 0.0
            r2 = classify("My new friend from the dating app is stuck at customs and needs help with fees")
            assert r2["confirms_script"] and r2["source"] == "keyword rules (floor)", r2
            score = real
            long = "I am sending money for many ordinary reasons. " * 60 + "The police officer told me to move it to a safe wallet."
            assert classify(long)["confirms_script"], "scam words past the model's 256-token window still flag"
        finally:
            score = real
    CLF = HERE / "models" / "missing.json"
    _head.cache_clear()
    assert classify("police told me to move it")["source"] == "keyword fallback", "no weights -> keyword rules"
    print(f"self-check passed ({r['source']}): drop-in classify(); missing weights -> keyword rules")


if __name__ == "__main__":
    train() if sys.argv[1:] == ["train"] else _self_check()
