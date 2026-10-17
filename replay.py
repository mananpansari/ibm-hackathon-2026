"""Result 2 (issue #10): replay wallets Tether froze through the decision engine.

Each wallet's inbound payments of >= 10 USDT are replayed in time order. Each payment is one
withdrawal by one customer (customer id = the sending address), decided by the same
Engine.decide() the product uses, with the clock set to the payment's time (every query sees
only events strictly before it). Payee memory carries forward within one wallet's replay; each
wallet starts with a fresh memory.

When the engine asks a question (#7: a first-time payee >= Config.large_usdt, or weak evidence),
the replay answers it through decide(w, answer, answer_kind="modelled"). A confirming answer
holds that payment and reports the wallet, which holds later payments from every customer; each
held attempt renews the report (#6). A clean answer releases.

Warning sources are replayed separately and never mixed:
- real: Tether freezes from freezes.csv, loaded into memory only once the clock has passed
  them. A counterparty freeze asks a question (never holds); a freeze of the wallet itself holds.
  Every question in this pass gets a clean answer, so only Tether's evidence can warn or hold.
- modelled: customer answers. A question on a frozen wallet gets a confirming answer with
  probability r (swept 0.1-0.9, fixed seeds; no freezes loaded). On comparison wallets the same
  mechanism runs with a false-confirm rate f.
- model flag: the engine has the hook (#5), but B's model needs xgboost + Keras/TensorFlow, which
  this replay doesn't load, so it is reported as "not available", never estimated.

The modelled source is also replayed with officers: every hold is a call-back, and a day later the
officer records "confirmed" (pins the wallet) or "cleared" (drops the evidence and ends the
renewal chain). The officer is right with probability q (modelled, swept). An officer only acts on
a hold, so the first warning still comes from the source alone.

The positives are payments, not victims: one victim can pay several times and several victims
can share one exchange address. Quote "up to N victims" at most.

    python replay.py           # self-check, then the full replay -> data/results/ and a summary
    python replay.py --check   # self-check only
"""
import bisect
import csv
import gzip
import json
import random
import statistics
import sys
from pathlib import Path

from engine import MIN_USDT, Config, Engine, FixedClock, RecordedHistories, Withdrawal
from payee_memory import DAY, OfficerOutcome, PayeeMemory, Report, load_freezes

DATA = Path(__file__).resolve().parent / "data"
RESULTS = DATA / "results"
RATES = [round(0.1 * i, 1) for i in range(1, 10)]
SEEDS = range(20)
FALSE_CONFIRM_RATES = (0.001, 0.01)  # legitimate customers whose answer wrongly confirms a scam: modelled
NEG_SEEDS = range(5)  # comparison sets are ~150k payments per pass
OFFICER_Q = (0.8, 0.9, 1.0)  # P(officer gets the call-back right): modelled
OFFICER_DELAY_S = DAY  # the outcome lands a day after the hold
HALF_LIVES_D = (3, 7, 30)  # report half-life sensitivity; 7 days (renewed by each held attempt) is C's setting
REAL_SIGNALS = {"counterparty_freeze", "destination_freeze"}
MODELLED_SIGNALS = {"answer_confirms_script", "memory_hit", "officer_confirmed"}
# Reasons that describe the payment or the answer, not a warning about the wallet.
CONTEXT = {"first_time_payee", "known_payee", "p_signal", "base_rate", "model_score", "large_new_payee", "answer_ok"}
MODEL_FLAG = "not available"


class NullLog:
    """The replay makes ~10^6 decisions; the hash-chained log is tested in decision_log.py."""
    def append(self, record):
        return None


class ReplayClassifier:
    """Stands in for Granite: the replay's answers are already "confirms" or "clean"."""
    def ask(self, withdrawal, reasons):
        return None  # the engine falls back to its template question

    def classify(self, answer):
        yes = answer == "confirms"
        return {"scam_type": "simulated" if yes else "none", "confirms_script": yes,
                "source": "replay_answer", "kind": "modelled"}


class GuardedHistory:
    """RecordedHistories for one wallet, asserting nothing at or after the clock's `now` leaks in."""

    def __init__(self, h, clock):
        self.inner = RecordedHistories(groups=())
        self.inner.by_addr = {h["address"]: h}
        self.clock = clock

    def __call__(self, wallet, as_of):
        assert as_of <= self.clock(), f"history asked for {as_of} after now {self.clock()}"
        out = self.inner(wallet, as_of)
        if out is not None:
            assert out["freeze_ts"] is None, "the label never leaks"
            assert all(t["ts"] < as_of for t in out["transfers"]), "a transfer from the future leaked"
        return out


def payments(h):
    """Inbound payments >= 10 USDT from another wallet, before the freeze, in time order."""
    me, end = h["address"], h["freeze_ts"] or float("inf")
    return [t for t in h["transfers"]
            if t["to"] == me and t["from"] != me and t["usdt"] >= MIN_USDT and t["ts"] < end]


def replay_wallet(h, freezes=(), answerer=None, reporter=None, officer=None, officer_delay_s=OFFICER_DELAY_S,
                  config=None, half_life_s=7 * DAY):
    """One wallet through a fresh engine and memory: ([(payment, final decision, questioned)], warnings).

    freezes: (ts, wallet) sorted by ts; each is loaded only once now has passed it.
    answerer(i, payment, decision) -> bool: does the answer to this question confirm a scam?
      None answers every question cleanly.
    reporter(i, payment, decision) -> bool: does the customer report the wallet after a released or
      warned payment (no question)? Used by the self-check; the sweep uses answers.
    officer() -> "confirmed" | "cleared": the outcome of a call-back. A hold starts one unless one is
      already pending or the wallet is confirmed; it is recorded officer_delay_s after the hold.
    warnings: (ts, index of the first payment it can protect, source) per confirming answer or report.
    """
    clock = FixedClock(0)
    mem = PayeeMemory(half_life_s=half_life_s)
    eng = Engine(GuardedHistory(h, clock), mem, clock, NullLog(), config, classifier=ReplayClassifier())
    fts = [ts for ts, _ in freezes]
    loaded, pending, warnings, out = 0, [], [], []
    calling, confirmed = False, False
    for i, t in enumerate(payments(h)):
        clock.now = t["ts"]
        j = bisect.bisect_left(fts, clock.now)  # freezes strictly before now
        if j > loaded:
            mem.add_freezes([(w, ts) for ts, w in freezes[loaded:j]])
            loaded = j
        assert h["freeze_ts"] is None or clock.now < h["freeze_ts"], "replayed past the freeze"
        assert loaded == 0 or fts[loaded - 1] < clock.now
        for e in sorted((e for e in pending if e.ts < clock.now), key=lambda e: e.ts):
            eng.record(e)
            if isinstance(e, OfficerOutcome):
                calling, confirmed = False, e.outcome == "confirmed"
        pending = [e for e in pending if e.ts >= clock.now]
        w = Withdrawal(t["from"], h["address"], t["usdt"], t["ts"])
        d = eng.decide(w)
        questioned = d.tier == "question"
        if questioned:
            yes = bool(answerer and answerer(i, t, d))
            d = eng.decide(w, answer="confirms" if yes else "clean", answer_kind="modelled")
            assert d.tier == "hold" if yes else d.tier == "release", d.tier
            if yes:
                warnings.append((t["ts"], i, "customer_answer"))
        out.append((t, d, questioned))
        if reporter and d.tier in ("release", "warning") and not questioned and reporter(i, t, d):
            pending.append(Report(h["address"], t["ts"], source="customer_report", kind="modelled",
                                  actor=t["from"], note="replay: simulated report"))
            warnings.append((t["ts"], i + 1, "customer_report"))
        if officer and d.tier == "hold" and not calling and not confirmed:
            pending.append(OfficerOutcome(h["address"], officer(), t["ts"] + officer_delay_s, "replay_officer"))
            calling = True
    return out, warnings


def summarise(h, decided, source, warnings=()):
    """Per-wallet row for one source: "real" (Tether freezes) or "modelled" (answers, reports)."""
    allowed = REAL_SIGNALS if source == "real" else MODELLED_SIGNALS
    for _, d, _ in decided:
        sigs = {r.signal for r in d.reasons} - CONTEXT
        assert sigs <= allowed, f"a {sigs - allowed} signal fired in the {source} pass"
        if source == "real":
            assert d.tier != "hold" or "destination_freeze" in sigs, "only the wallet's own freeze holds"
        else:
            assert all(r.kind == "modelled" for r in d.reasons if r.signal in ("memory_hit", "answer_confirms_script"))
    cites = [bool({r.signal for r in d.reasons} & allowed) for _, d, _ in decided]
    row = {"address": h["address"], "truncated": int(h["truncated"]), "payments": len(decided),
           "questioned": sum(q for _, _, q in decided),
           "first_warning_ts": "", "first_warning_source": "", "payments_after_warning": 0,
           "source_warned": sum(cites), "held": sum(d.tier == "hold" for _, d, _ in decided),
           "lead_days": "", "model_flag": MODEL_FLAG}
    if source == "real" and any(cites):
        k = cites.index(True)
        row.update(first_warning_ts=decided[k][0]["ts"], payments_after_warning=len(decided) - k,
                   first_warning_source="+".join(sorted({r.signal for r in decided[k][1].reasons} & REAL_SIGNALS)))
    elif source == "modelled" and warnings:
        ts, k, src = min(warnings)
        row.update(first_warning_ts=ts, payments_after_warning=len(decided) - k, first_warning_source=src)
    if row["first_warning_ts"] != "" and h["freeze_ts"]:
        row["lead_days"] = round((h["freeze_ts"] - row["first_warning_ts"]) / DAY, 2)
    return row


def aggregate(rows):
    warned = [r for r in rows if r["first_warning_ts"] != ""]
    leads = [r["lead_days"] for r in warned if r["lead_days"] != ""]
    n = sum(r["payments"] for r in rows)
    held = sum(r["held"] for r in rows)
    return {"wallets": len(rows), "wallets_warned": len(warned), "payments": n,
            "payments_questioned": sum(r["questioned"] for r in rows),
            "payments_after_warning": sum(r["payments_after_warning"] for r in rows),
            "payments_source_warned": sum(r["source_warned"] for r in rows),
            "payments_held": held, "wallets_with_any_hold": sum(r["held"] > 0 for r in rows),
            "payment_hold_rate": round(held / n, 6) if n else None,
            "median_lead_days": round(statistics.median(leads), 1) if leads else None}


def spread(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    nd = 1 if max(abs(v) for v in vals) >= 1 else 6  # rates stay readable
    return {"mean": round(statistics.mean(vals), nd), "sd": round(statistics.pstdev(vals), nd),
            "min": min(vals), "max": max(vals)}


def spreads(per_seed, skip=("wallets", "payments")):
    out = {m: spread([a[m] for a in per_seed]) for m in per_seed[0] if m not in skip}
    out.update({m: per_seed[0][m] for m in skip})
    return out


def load_group(group):
    return [json.loads(line) for line in gzip.open(DATA / "histories" / f"{group}.jsonl.gz", "rt")]


def positives():
    """Test positives: frozen Jul-Oct 2026, not OFAC, with >= 1 payment before the freeze."""
    ofac = {r["address"] for r in csv.DictReader(open(DATA / "freezes.csv")) if r["ofac"] == "1"}
    return [h for h in load_group("test_pos") if h["address"] not in ofac and payments(h)]


def write_csv(path, rows, extra_cols=()):
    cols = list(extra_cols) + ["address", "truncated", "payments", "questioned", "first_warning_ts",
                               "first_warning_source", "payments_after_warning", "source_warned", "held",
                               "lead_days", "model_flag"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def coin(seed, r, addr):
    rng = random.Random(f"{seed}:{r}:{addr}")
    return lambda i, t, d: rng.random() < r


def officer_for(seed, q, addr, scam):
    """A call-back officer who is right with probability q: confirms a scam wallet, clears a legitimate one."""
    rng = random.Random(f"officer:{seed}:{q}:{addr}")
    right, wrong = ("confirmed", "cleared") if scam else ("cleared", "confirmed")
    return lambda: right if rng.random() < q else wrong


def modelled_runs(hs, rate, seeds, scam, q=None, config=None, subsets=None, half_life_s=7 * DAY):
    """({subset: [aggregate per seed]}, per-wallet rows) for answers confirming at `rate` (officers if q)."""
    subsets = subsets or {"all": lambda h: True}
    per_seed, rows_out = {k: [] for k in subsets}, []
    for seed in seeds:
        rows = []
        for h in hs:
            officer = officer_for(seed, q, h["address"], scam) if q is not None else None
            decided, warnings = replay_wallet(h, answerer=coin(seed, rate, h["address"]), officer=officer, config=config,
                                              half_life_s=half_life_s)
            rows.append(summarise(h, decided, "modelled", warnings))
        rows_out += [{"r": rate, "seed": seed, **row} for row in rows]
        for k, keep in subsets.items():
            per_seed[k].append(aggregate([row for row, h in zip(rows, hs) if keep(h)]))
    return per_seed, rows_out


def run():
    RESULTS.mkdir(exist_ok=True)
    freezes = sorted((ts, w) for w, ts in load_freezes())
    pos = positives()
    subsets = {"all": lambda h: True, "2plus": lambda h: len(payments(h)) >= 2}
    summary = {"definitions": DEFINITIONS, "model_flag": MODEL_FLAG, "large_usdt": Config().large_usdt,
               "positives": {"group": "test_pos", "truncated_wallets": sum(h["truncated"] for h in pos)},
               "legitimate": {}}

    # (a) real: Tether freezes only; every question answered cleanly
    real = [summarise(h, replay_wallet(h, freezes)[0], "real") for h in pos]
    write_csv(RESULTS / "replay_test_pos_real.csv", real)
    summary["positives"]["real"] = {k: aggregate([r for r, h in zip(real, pos) if keep(h)]) for k, keep in subsets.items()}

    # (b) modelled: answers confirm at rate r, no freezes; then with officers
    mrows, msum = [], {k: {} for k in subsets}
    osum = {str(q): {} for q in OFFICER_Q}
    for r in RATES:
        per_seed, rows = modelled_runs(pos, r, SEEDS, scam=True, subsets=subsets)
        mrows += rows
        for k in subsets:
            msum[k][str(r)] = spreads(per_seed[k])
        for q in OFFICER_Q:
            osum[str(q)][str(r)] = spreads(modelled_runs(pos, r, SEEDS, scam=True, q=q)[0]["all"])
        print(f"modelled r={r}: held {msum['all'][str(r)]['payments_held']}", flush=True)
    write_csv(RESULTS / "replay_test_pos_modelled.csv", mrows, extra_cols=("r", "seed"))
    summary["positives"]["modelled"] = {"seeds": len(SEEDS), **msum}
    summary["positives"]["modelled_with_officers"] = {"officer_delay_s": OFFICER_DELAY_S, **osum}
    # Sensitivity: ask on every first-time payee >= 100 USDT instead of >= 1,000.
    low = Config(large_usdt=100)
    summary["positives"]["modelled_r0.5_large_usdt_100"] = spreads(modelled_runs(pos, 0.5, SEEDS, scam=True, config=low)[0]["all"])

    # (c) model flag
    summary["positives"]["model_flag"] = MODEL_FLAG

    # Comparison wallets: the real pass, then false confirms at rate f (modelled), without and with officers
    for g in ("test_neg", "test_negv"):
        hs = [h for h in load_group(g) if payments(h)]
        rows = [summarise(h, replay_wallet(h, freezes)[0], "real") for h in hs]
        write_csv(RESULTS / f"replay_{g}_real.csv", rows)
        out = {"wallets": len(hs), "truncated_wallets": sum(h["truncated"] for h in hs),
               "real": aggregate(rows), "false_confirms": {"seeds": len(NEG_SEEDS)}}
        for f in FALSE_CONFIRM_RATES:
            out["false_confirms"][str(f)] = {
                "no_officer": spreads(modelled_runs(hs, f, NEG_SEEDS, scam=False)[0]["all"]),
                "officer_q0.9": spreads(modelled_runs(hs, f, NEG_SEEDS, scam=False, q=0.9)[0]["all"]),
                "officer_q1.0": spreads(modelled_runs(hs, f, NEG_SEEDS, scam=False, q=1.0)[0]["all"])}
            print(f"{g} f={f}: held {out['false_confirms'][str(f)]['no_officer']['payments_held']} without officers, "
                  f"{out['false_confirms'][str(f)]['officer_q1.0']['payments_held']} with perfect ones", flush=True)
        out["questions_large_usdt_100"] = aggregate([summarise(h, replay_wallet(h, freezes, config=low)[0], "real")
                                                     for h in hs])["payments_questioned"]
        summary["legitimate"][g] = out

    summary["half_life"] = run_half_life(pos)
    (RESULTS / "replay_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def run_half_life(pos):
    """The report half-life is a modelled setting: r = 0.5 on frozen wallets, f = 0.001 on comparison wallets."""
    out = {}
    for d in HALF_LIVES_D:
        hl = d * DAY
        out[f"{d}d"] = {"positives_r0.5": spreads(modelled_runs(pos, 0.5, SEEDS, scam=True, half_life_s=hl)[0]["all"]),
                        "positives_r0.5_officer_q0.9": spreads(
                            modelled_runs(pos, 0.5, SEEDS, scam=True, q=0.9, half_life_s=hl)[0]["all"])}
        for g in ("test_neg", "test_negv"):
            hs = [h for h in load_group(g) if payments(h)]
            out[f"{d}d"][f"{g}_f0.001"] = spreads(modelled_runs(hs, 0.001, NEG_SEEDS, scam=False, half_life_s=hl)[0]["all"])
            out[f"{d}d"][f"{g}_f0.001_officer_q1.0"] = spreads(
                modelled_runs(hs, 0.001, NEG_SEEDS, scam=False, q=1.0, half_life_s=hl)[0]["all"])
        print(f"half-life {d}d: {out[f'{d}d']['positives_r0.5']['payments_held']} held on frozen wallets", flush=True)
    return out


DEFINITIONS = {
    "payment": "an inbound USDT transfer >= 10 USDT from another wallet, before the freeze; one withdrawal by one customer (the sender)",
    "questioned": "payments the engine asked a question about (#7: first-time payee >= large_usdt, or weak evidence)",
    "first_warning_real": "the first payment at which the engine raised a Tether freeze signal (counterparty: question; destination: hold)",
    "first_warning_modelled": "the first confirming answer (it holds that payment) or simulated report",
    "payments_after_warning": "payments decided once a warning existed, including the payment whose answer confirmed it",
    "payments_source_warned": "payments whose decision cites the source's signal",
    "payments_held": "payments the engine put in the hold tier (call-back); each held attempt renews the report, an officer's cleared ends it",
    "lead_days": "freeze_ts - first warning ts, in days; median over wallets with a warning",
    "payment_hold_rate": "held payments / payments; on comparison wallets this is the legitimate-hold rate",
    "false_confirm_rate": "f: chance a legitimate customer's answer is classified as confirming a scam (modelled)",
    "half_life": "report half-life in payee memory (modelled setting; C's default 7 days, renewed by each held attempt)",
    "officer": "each hold starts a call-back; a day later the officer records confirmed or cleared; right with probability q (modelled)",
}


def _self_check():
    me = "0xscam"
    tx = lambda ts, a, b, usdt: {"ts": ts, "from": a, "to": b, "usdt": usdt, "nonce": 1, "hash": f"{ts}{a}{b}"}
    victims = ["0xv1", "0xv2", "0xv3", "0xv4", "0xv5"]
    small = {"address": me, "group": "test_pos", "freeze_ts": 30 * DAY, "truncated": False, "transfers":
             [tx((1 + i) * DAY, v, me, 500) for i, v in enumerate(victims)]
             + [tx(int(1.5 * DAY), me, "0xmule", 400), tx(int(2.5 * DAY), "0xdust", me, 1), tx(40 * DAY, "0xv6", me, 500)]}
    large = {**small, "transfers": [{**t, "usdt": 5_000} if t["usdt"] == 500 else t for t in small["transfers"]]}
    assert len(payments(small)) == 5, "dust, outbound and post-freeze transfers are not payments"
    tiers = lambda hh, **kw: [d.tier for _, d, _ in replay_wallet(hh, **kw)[0]]
    second = lambda i, t, d: i == 1

    # 5 small payments (warnings, no questions); the 2nd customer reports after paying -> 3, 4, 5 held.
    decided, warnings = replay_wallet(small, reporter=second)
    assert [d.tier for _, d, _ in decided] == ["warning", "warning", "hold", "hold", "hold"], decided
    row = summarise(small, decided, "modelled", warnings)
    assert (row["payments"], row["questioned"], row["payments_after_warning"], row["held"]) == (5, 0, 3, 3), row
    assert row["first_warning_ts"] == 2 * DAY and row["lead_days"] == 28.0 and row["first_warning_source"] == "customer_report"

    # 5 large payments: each is a question (#7). The 2nd answer confirms: it and the 3 after it are held.
    assert tiers(large) == ["release"] * 5, "clean answers release"
    decided, warnings = replay_wallet(large, answerer=second)
    assert [d.tier for _, d, _ in decided] == ["release", "hold", "hold", "hold", "hold"], decided
    row = summarise(large, decided, "modelled", warnings)
    assert (row["questioned"], row["payments_after_warning"], row["held"]) == (2, 4, 4), row
    assert row["first_warning_source"] == "customer_answer" and row["lead_days"] == 28.0
    assert any(r.signal == "answer_confirms_script" and r.kind == "modelled" for r in decided[1][1].reasons)
    assert decided[2][1].reasons[0].signal == "memory_hit", "later customers are held by the answer's report"

    # Real: the mule (paid at 1.5 days) is frozen at 2.5 days, so the 3rd payment on are questioned
    # (answered cleanly), never held. A freeze after the wallet's own freeze and the dust sender's
    # freeze never count.
    freezes = sorted([(int(2.5 * DAY), "0xmule"), (int(2.6 * DAY), "0xdust"), (100 * DAY, "0xv1")])
    row = summarise(small, replay_wallet(small, freezes)[0], "real")
    assert (row["payments_after_warning"], row["source_warned"], row["questioned"], row["held"]) == (3, 3, 3, 0), row
    assert row["first_warning_source"] == "counterparty_freeze" and row["first_warning_ts"] == 3 * DAY
    assert row["lead_days"] == 27.0
    assert summarise(small, replay_wallet(small, [(int(5.5 * DAY), "0xmule")])[0], "real")["source_warned"] == 0, \
        "frozen after the last payment"

    # Renewal and officers: large payments on days 1, 2, 3, 6, 12, 40; the 2nd answer confirms. Held
    # attempts renew the report, so days 3-12 are held; day 40 comes 28 days after the last renewal
    # (its question is answered cleanly). Confirmed (day 3) pins it; cleared (day 3) ends it.
    h2 = {**large, "freeze_ts": 50 * DAY,
          "transfers": [tx(d * DAY, f"0xv{d}", me, 5_000) for d in (1, 2, 3, 6, 12, 40)]}
    assert tiers(h2, answerer=second) == ["release"] + ["hold"] * 4 + ["release"]
    assert tiers(h2, answerer=second, officer=lambda: "confirmed") == ["release"] + ["hold"] * 5
    assert tiers(h2, answerer=second, officer=lambda: "cleared") == ["release", "hold", "hold"] + ["release"] * 3
    calls = []
    replay_wallet(h2, answerer=second, officer=lambda: calls.append(1) or "confirmed")
    assert len(calls) == 1, "one call-back per wallet while it is pending or confirmed"
    assert tiers(large, officer=lambda: 1 / 0) == ["release"] * 5, "no hold, no call-back: the officer is never asked"

    # No warning at all: nothing warned or held, no lead time.
    row = summarise(small, replay_wallet(small)[0], "real")
    assert (row["source_warned"], row["held"], row["first_warning_ts"], row["lead_days"]) == (0, 0, "", ""), row

    # The leak guard fires if the engine ever asks for history past now.
    try:
        GuardedHistory(small, FixedClock(10))(me, 11)
        raise RuntimeError("guard did not fire")
    except AssertionError:
        pass

    # On real wallets: a replay that can only see each payment's past gives the same decisions
    # as the full replay (no future transfer, freeze or label changes anything).
    freezes = sorted((ts, w) for w, ts in load_freezes())
    sample = random.Random(0).sample(positives(), 15)
    for hh in sample:
        full = [(d.tier, d.reasons) for _, d, _ in replay_wallet(hh, freezes)[0]]
        prefix = []
        for k, t in enumerate(payments(hh)[:31]):
            cut = {**hh, "transfers": [x for x in hh["transfers"] if x["ts"] <= t["ts"]]}
            d = replay_wallet(cut, [f for f in freezes if f[0] < t["ts"]])[0][k][1]
            prefix.append((d.tier, d.reasons))
        assert full[:len(prefix)] == prefix, hh["address"]
    print(f"self-check passed: fixed 5-payment replays (report at the 2nd -> 3 held; confirming answer at the "
          f"2nd -> 4 held), real and modelled sources, renewal, officers, no-future check on {len(sample)} frozen wallets")


if __name__ == "__main__":
    _self_check()
    if "--check" not in sys.argv:
        s = run()
        print(json.dumps(s["positives"]["real"], indent=2))
        print(json.dumps({g: v["real"] for g, v in s["legitimate"].items()}, indent=2))
