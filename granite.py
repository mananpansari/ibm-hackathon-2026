"""Granite asks the customer question and classifies the answer (#14), with fallbacks.

Two ways to run Granite, both on this machine so answer text never leaves the box:
- GRANITE_GGUF=/path/model.gguf: in-process through llama_cpp_python (in the LinuxONE lab
  image). The VM's model is a small BASE model, so it only classifies, with a few-shot prompt;
  questions stay templated (the build plan's fallback).
- otherwise llama.cpp's server, an instruct model: `llama-server -m granite-4.2-3b-Q4_K_M.gguf
  --port 8080`; GRANITE_URL must be localhost. It writes the question and classifies.
If Granite is missing or slower than 2 s: template question, keyword classifier.

    ask(withdrawal, reasons) -> question text
    classify(answer) -> {"scam_type", "confirms_script", "source"}

    python granite.py          # self-check (works without Granite)
    python granite.py eval     # accuracy on BothBosu test dialogues + data/sg_answers.csv
"""
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
GRANITE_URL = os.environ.get("GRANITE_URL", "http://127.0.0.1:8080")
if urllib.parse.urlparse(GRANITE_URL).hostname not in ("127.0.0.1", "localhost", "::1"):
    raise SystemExit("GRANITE_URL must be on this machine: customer answers never leave it")
GRANITE_GGUF = os.environ.get("GRANITE_GGUF")
TIMEOUT_S = 2.0
RETRY_AFTER_S = 60  # after a failure, skip Granite this long so every request doesn't pay the timeout
_down_until = 0.0
_llm, _worker = None, ThreadPoolExecutor(1)  # one worker: llama.cpp is not thread-safe
ADVISORIES = (HERE / "advisories.txt").read_text(encoding="utf-8")
SCAM_TYPES = ["government_impersonation", "bank_impersonation", "fake_friend", "investment", "romance", "job",
              "tech_support", "loan", "recovery", "wallet_verification", "ecommerce", "none"]
TEMPLATE = ("Real police, bank or government officers never ask you to move your savings to a 'safe' wallet. "
            "In your own words, why are you sending this money, and did anyone ask you to?")
# ponytail: keyword fallback; Granite does the real work. Order matters: first match wins.
KEYWORDS = [
    ("government_impersonation", r"police|officer|\bmas\b|\bica\b|\bmoh\b|court|warrant|investigat|launder|customs|government"),
    ("bank_impersonation", r"bank'?s? (fraud|security|team|staff)|\b(dbs|ocbc|uob)\b|account (is |was )?(hacked|compromised)|keep (my |the )?money safe|safe (wallet|account)"),
    ("wallet_verification", r"verify (my )?wallet|test payment|recovery phrase|seed phrase|sync (my )?wallet"),
    ("recovery", r"recover(y)? .*(money|fund|lost)|get back the money"),
    ("tech_support", r"microsoft|apple support|computer is infected|virus|remote access|anydesk|teamviewer|tech support"),
    ("job", r"task|commission|unlock|online job|review(ing)? (tasks|products)|like videos"),
    ("loan", r"loan|lender|processing fee"),
    ("investment", r"guaranteed|returns|profit|trading (group|platform)|mentor|pay tax|withdraw my"),
    ("romance", r"boyfriend|girlfriend|met (on|online)|dating|we've been talking|stuck at customs"),
    ("fake_friend", r"new number|changed (phone |)number|borrow"),
    ("ecommerce", r"seller|marketplace|carousell|outside the platform"),
]
PRESSURE = r"don'?t tell|keep (it|this) secret|still on the (line|phone)|urgent|right now|immediately|suspend|arrest|you'?ll be sorry"


def _guarded(fn, *args):
    global _down_until
    if time.monotonic() < _down_until:
        raise ConnectionError("Granite marked down")
    try:
        return fn(*args)
    except Exception:
        _down_until = time.monotonic() + RETRY_AFTER_S
        raise


def _chat(system, user, max_tokens):
    return _guarded(_call, system, user, max_tokens)


def _complete(prompt, max_tokens):
    global _llm
    if _llm is None:
        from llama_cpp import Llama
        _llm = Llama(model_path=GRANITE_GGUF, n_ctx=1024, n_threads=os.cpu_count(), verbose=False)
    return _llm(prompt, max_tokens=max_tokens, temperature=0, stop=["\n"])["choices"][0]["text"]


def _local(prompt, max_tokens):
    # ponytail: a timed-out call keeps running in the worker; later calls queue behind it and fall back
    return _guarded(lambda: _worker.submit(_complete, prompt, max_tokens).result(timeout=TIMEOUT_S))


if GRANITE_GGUF:
    _worker.submit(_complete, "Hello", 1)  # load the model at startup, not on the first customer


FEW_SHOT = """Classify why a bank customer is sending money. Labels: """ + ", ".join(SCAM_TYPES) + """.

Customer: Paying the school fees for my son's next term into the school's account.
Label: none

Customer: A caller from the police said my account is under investigation and I must move my money to a protection wallet.
Label: government_impersonation

Customer: I'm moving my coins to my own Ledger.
Label: none

Customer: My friend from a dating app needs money for a hospital bill before he can visit.
Label: romance

Customer: The investment app says I must pay a release fee before I can withdraw my gains.
Label: investment

Customer: %s
Label:"""


def _label(text):
    """First known label in a completion, or None."""
    words = re.findall(r"[a-z_]+", text.lower())
    return next((w for w in words if w in SCAM_TYPES), None)


def _call(system, user, max_tokens):
    body = json.dumps({"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                       "max_tokens": max_tokens, "temperature": 0}).encode()
    req = urllib.request.Request(GRANITE_URL + "/v1/chat/completions", body, {"Content-Type": "application/json"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:  # ponytail: socket timeout, not a hard wall; the check below catches slow streams
        out = json.loads(r.read())["choices"][0]["message"]["content"]
    if time.monotonic() - t0 > TIMEOUT_S:
        raise TimeoutError("Granite slower than 2 s")
    return out.strip()


def ask(withdrawal, reasons):
    why = "; ".join(r.get("detail") or r.get("text", "") for r in reasons)
    try:
        q = _chat("You protect bank customers from scams. Using only these advisories, write ONE short question "
                  "(under 40 words, plain English, no crypto jargon) asking why they are sending this payment and "
                  "whether anyone told them to. Start by stating one fact from the advisories.\n\n" + ADVISORIES,
                  f"Payment of {withdrawal['amount']:.0f} USDT to a wallet. Why it was flagged: {why}", 80)
        return q if 10 < len(q) < 400 else TEMPLATE
    except Exception:
        return TEMPLATE


def keyword_classify(answer):
    a = answer.lower()
    kind = next((k for k, pat in KEYWORDS if re.search(pat, a)), None)
    confirms = kind is not None or bool(re.search(PRESSURE, a))
    if kind is None:
        kind = "other" if confirms else "none"
    return {"scam_type": kind, "confirms_script": confirms, "source": "keyword fallback"}


def classify(answer):
    if GRANITE_GGUF:
        try:
            kind = _label(_local(FEW_SHOT % " ".join(answer.split())[:1500], 8))
            if kind:
                return {"scam_type": kind, "confirms_script": kind != "none", "source": "Granite"}
        except Exception:
            pass
        return keyword_classify(answer)
    try:
        out = _chat("Classify a bank customer's explanation for a payment, using these scam advisories.\n\n" + ADVISORIES +
                    f"\n\nReply with JSON only: {{\"scam_type\": one of {SCAM_TYPES}, \"confirms_script\": true or false}}. "
                    "confirms_script is true if the explanation matches a scam pattern above.",
                    answer[:4000], 40)
        d = json.loads(out[out.find("{"):out.rfind("}") + 1])
        if d.get("scam_type") in SCAM_TYPES and isinstance(d.get("confirms_script"), bool):
            return {"scam_type": d["scam_type"], "confirms_script": d["confirms_script"], "source": "Granite"}
    except Exception:
        pass
    return keyword_classify(answer)


def evaluate():
    path = HERE / "data" / "bothbosu_test.csv"
    if not path.exists():
        urllib.request.urlretrieve("https://huggingface.co/datasets/BothBosu/scam-dialogue/resolve/main/scam-dialogue_test.csv", path)
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    # BothBosu: classify only the receiver's side, i.e. what a customer would tell us
    said = lambda d: " ".join(re.findall(r"receiver:(.*?)(?=caller:|$)", d)) or d
    ms = []

    def timed(text):
        t0 = time.monotonic()
        out = classify(text)
        ms.append((time.monotonic() - t0) * 1000)
        return out

    res = [(timed(said(r["dialogue"])), r) for r in rows]
    ok = sum(c["confirms_script"] == (r["label"] == "1") for c, r in res)
    print(f"BothBosu test, scam vs not (receiver side): {ok}/{len(res)} = {ok / len(res):.0%}  [{res[0][0]['source']}]")
    sg = list(csv.DictReader(open(HERE / "data" / "sg_answers.csv", encoding="utf-8")))
    cs = [(timed(r["answer"]), r) for r in sg]
    conf = sum(c["confirms_script"] == (r["confirms_script"] == "1") for c, r in cs)
    kind = sum(c["scam_type"] == r["scam_type"] for c, r in cs)
    print(f"SG answers ({len(cs)}): confirms_script {conf}/{len(cs)} = {conf / len(cs):.0%}; "
          f"scam type {kind}/{len(cs)} = {kind / len(cs):.0%}  [{cs[0][0]['source']}]")
    ms.sort()
    srcs = {c["source"] for c, _ in res + cs}
    print(f"latency per answer: p50 {ms[len(ms) // 2]:.0f} ms, p95 {ms[int(len(ms) * .95)]:.0f} ms, max {ms[-1]:.0f} ms; "
          f"sources {sorted(srcs)}")
    for c, r in cs:
        if c["scam_type"] != r["scam_type"] or c["confirms_script"] != (r["confirms_script"] == "1"):
            print(f"  miss: {r['answer'][:70]!r} -> {c['scam_type']}/{c['confirms_script']}, want {r['scam_type']}/{r['confirms_script']}")


if __name__ == "__main__":
    if sys.argv[1:] == ["eval"]:
        evaluate()
    else:
        t0 = time.monotonic()
        q = ask({"amount": 5000}, [{"text": "large payment to a new wallet"}])
        c = classify("The police officer told me to move my savings to a safe wallet, don't tell anyone")
        assert q and c["confirms_script"] and c["scam_type"] in SCAM_TYPES + ["other"], (q, c)
        assert not classify("moving money to my own hardware wallet")["confirms_script"]
        assert time.monotonic() - t0 < 3 * TIMEOUT_S + 1, "fallback must not hang"
        assert _label(" government_impersonation\n") == "government_impersonation" and _label(" I think none") == "none"
        assert _label("no idea") is None
        assert ask({"amount": 1}, [{"detail": "engine reason"}]), "engine reasons use 'detail'"
        print(f"granite self-check passed ({c['source']}); question: {q}")
