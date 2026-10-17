"""Result 2 (issue #10): replay wallets Tether froze through the decision engine.

Each wallet's inbound payments of >= 10 USDT are replayed in time order. Each payment is one
withdrawal by one customer (customer id = the sending address), decided by the same
Engine.decide() the product uses, with the clock set to the payment's time (every query sees
only events strictly before it). Payee memory carries forward within one wallet's replay; each
wallet starts with a fresh memory.

Warning sources are replayed separately and never mixed:
- real: Tether freezes from freezes.csv, loaded into memory only once the clock has passed
  them. The engine raises a counterparty freeze, which warns but never holds (#6), or a freeze
  of the wallet itself, which holds.
- modelled: customer answers. After each released or warned payment the customer reports the
  wallet with probability r (no freezes loaded). r is swept 0.1-0.9 over fixed seeds. Each held
  attempt renews the report inside the engine (#6), so a hold lasts while victims keep paying.
  On comparison wallets the same mechanism runs with a false-report rate f (modelled).
- model flag: B's weak model signal (#5) is not wired into the engine yet, so it is reported as
  "not available", never estimated.

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

from engine import MIN_USDT, Engine, FixedClock, RecordedHistories, Withdrawal
from payee_memory import DAY, OfficerOutcome, PayeeMemory, Report, load_freezes

DATA = Path(__file__).resolve().parent / "data"
RESULTS = DATA / "results"
RATES = [round(0.1 * i, 1) for i in range(1, 10)]
SEEDS = range(20)
FALSE_REPORT_RATES = (0.001, 0.01)  # legitimate customers who wrongly report a payee: modelled
NEG_SEEDS = range(5)  # comparison sets are ~150k payments per pass
OFFICER_Q = (0.8, 0.9, 1.0)  # P(officer gets the call-back right): modelled
OFFICER_DELAY_S = DAY  # the outcome lands a day after the hold
REAL_SIGNALS = {"counterparty_freeze", "destination_freeze"}
CONTEXT = {"first_time_payee", "known_payee", "p_signal", "base_rate", "model_score"}  # context, not warnings
# The engine has the hook (Engine(..., model=model.score)), but model.py and models/ are on
# origin/b/5-weak-model-signal and need xgboost + Keras/TensorFlow, which this replay doesn't load yet.
MODEL_FLAG = "not available"


class NullLog:
    """The replay makes ~10^6 decisions; the hash-chained log is tested in decision_log.py."""
    def append(self, record):
        return None


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


def replay_wallet(h, freezes=(), reporter=None, report_delay_s=0, officer=None, officer_delay_s=OFFICER_DELAY_S,
                  config=None):
    """([(payment, decision)], [report ts]) for one wallet, through a fresh engine and memory.

    freezes: (ts, wallet) sorted by ts; each is loaded only once now has passed it.
    reporter(i, payment, decision) -> bool: does the customer report the wallet after this
    released or warned payment? The report is recorded at payment ts + report_delay_s, once the
    clock passes it.
    officer() -> "confirmed" | "cleared": the outcome of a call-back. A hold starts one unless one is
    already pending or the wallet is confirmed; it is recorded officer_delay_s after the hold.
    """
    clock = FixedClock(0)
    mem = PayeeMemory()
    eng = Engine(GuardedHistory(h, clock), mem, clock, NullLog(), config)
    fts = [ts for ts, _ in freezes]
    loaded, pending, made, out = 0, [], [], []
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
        d = eng.decide(Withdrawal(t["from"], h["address"], t["usdt"], t["ts"]))
        out.append((t, d))
        if reporter and d.tier in ("release", "warning") and reporter(i, t, d):
            pending.append(Report(h["address"], t["ts"] + report_delay_s, source="customer_answer",
                                  kind="modelled", actor=t["from"], note="replay: simulated report"))
            made.append(t["ts"] + report_delay_s)
        if officer and d.tier == "hold" and not calling and not confirmed:
            pending.append(OfficerOutcome(h["address"], officer(), t["ts"] + officer_delay_s, "replay_officer"))
            calling = True
    return out, made


def summarise(h, decided, source, report_ts=()):
    """Per-wallet row for one source: "real" (Tether freezes) or "modelled" (reports)."""
    if source == "real":
        cites = [any(r.signal in REAL_SIGNALS for r in d.reasons) for _, d in decided]
        for _, d in decided:
            warnings = {r.signal for r in d.reasons} - CONTEXT
            assert warnings <= REAL_SIGNALS, f"non-real signal in the real pass: {warnings}"
            assert d.tier != "hold" or "destination_freeze" in warnings, "only the wallet's own freeze holds"
    else:
        cites = [any(r.signal in ("memory_hit", "officer_confirmed") for r in d.reasons) for _, d in decided]
        for _, d in decided:
            warnings = [r for r in d.reasons if r.signal not in CONTEXT]
            assert all((r.signal == "memory_hit" and r.kind == "modelled") or r.signal == "officer_confirmed"
                       for r in warnings), f"a non-modelled signal fired in the modelled pass: {warnings}"
    row = {"address": h["address"], "truncated": int(h["truncated"]), "payments": len(decided),
           "first_warning_ts": "", "first_warning_source": "", "payments_after_warning": 0,
           "source_warned": sum(cites), "held": sum(d.tier == "hold" for _, d in decided),
           "lead_days": "", "model_flag": MODEL_FLAG}
    if source == "real" and any(cites):
        k = cites.index(True)
        row.update(first_warning_ts=decided[k][0]["ts"], payments_after_warning=len(decided) - k,
                   first_warning_source="+".join(sorted({r.signal for r in decided[k][1].reasons} & REAL_SIGNALS)))
    elif source == "modelled" and report_ts:
        first = min(report_ts)
        row.update(first_warning_ts=first, first_warning_source="customer_answer",
                   payments_after_warning=sum(t["ts"] > first for t, _ in decided))
    if row["first_warning_ts"] != "" and h["freeze_ts"]:
        row["lead_days"] = round((h["freeze_ts"] - row["first_warning_ts"]) / DAY, 2)
    return row


def aggregate(rows):
    warned = [r for r in rows if r["first_warning_ts"] != ""]
    leads = [r["lead_days"] for r in warned if r["lead_days"] != ""]
    n = sum(r["payments"] for r in rows)
    held = sum(r["held"] for r in rows)
    return {"wallets": len(rows), "wallets_warned": len(warned), "payments": n,
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
    cols = list(extra_cols) + ["address", "truncated", "payments", "first_warning_ts", "first_warning_source",
                               "payments_after_warning", "source_warned", "held", "lead_days", "model_flag"]
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


def modelled_runs(hs, rate, seeds, scam, q=None, report_delay_s=0, subsets=None):
    """{subset: [aggregate per seed]} and the per-wallet rows, for reports at `rate` (and officers if q)."""
    subsets = subsets or {"all": lambda h: True}
    per_seed, rows_out = {k: [] for k in subsets}, []
    for seed in seeds:
        rows = []
        for h in hs:
            officer = officer_for(seed, q, h["address"], scam) if q is not None else None
            decided, report_ts = replay_wallet(h, reporter=coin(seed, rate, h["address"]),
                                               report_delay_s=report_delay_s, officer=officer)
            rows.append(summarise(h, decided, "modelled", report_ts))
        rows_out += [{"r": rate, "seed": seed, **row} for row in rows]
        for k, keep in subsets.items():
            per_seed[k].append(aggregate([row for row, h in zip(rows, hs) if keep(h)]))
    return per_seed, rows_out


def run():
    RESULTS.mkdir(exist_ok=True)
    freezes = sorted((ts, w) for w, ts in load_freezes())
    pos = positives()
    subsets = {"all": lambda h: True, "2plus": lambda h: len(payments(h)) >= 2}
    summary = {"definitions": DEFINITIONS, "model_flag": MODEL_FLAG,
               "positives": {"group": "test_pos", "truncated_wallets": sum(h["truncated"] for h in pos)},
               "legitimate": {}}

    # (a) real: Tether freezes only
    real = [summarise(h, replay_wallet(h, freezes)[0], "real") for h in pos]
    write_csv(RESULTS / "replay_test_pos_real.csv", real)
    summary["positives"]["real"] = {k: aggregate([r for r, h in zip(real, pos) if keep(h)]) for k, keep in subsets.items()}

    # (b) modelled: customer answers at rate r, no freezes; then with officers
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
    summary["positives"]["modelled"] = {"seeds": len(SEEDS), "report_delay_s": 0, **msum}
    summary["positives"]["modelled_with_officers"] = {"officer_delay_s": OFFICER_DELAY_S, **osum}
    summary["positives"]["modelled_r0.5_delay_1d"] = spreads(
        modelled_runs(pos, 0.5, SEEDS, scam=True, report_delay_s=DAY)[0]["all"])

    # (c) model flag
    summary["positives"]["model_flag"] = MODEL_FLAG

    # Comparison wallets: the real pass, then false reports at rate f (modelled), without and with officers
    for g in ("test_neg", "test_negv"):
        hs = [h for h in load_group(g) if payments(h)]
        rows = [summarise(h, replay_wallet(h, freezes)[0], "real") for h in hs]
        write_csv(RESULTS / f"replay_{g}_real.csv", rows)
        out = {"wallets": len(hs), "truncated_wallets": sum(h["truncated"] for h in hs),
               "real": aggregate(rows), "false_reports": {"seeds": len(NEG_SEEDS)}}
        for f in FALSE_REPORT_RATES:
            out["false_reports"][str(f)] = {
                "no_officer": spreads(modelled_runs(hs, f, NEG_SEEDS, scam=False)[0]["all"]),
                "officer_q0.9": spreads(modelled_runs(hs, f, NEG_SEEDS, scam=False, q=0.9)[0]["all"]),
                "officer_q1.0": spreads(modelled_runs(hs, f, NEG_SEEDS, scam=False, q=1.0)[0]["all"])}
            print(f"{g} f={f}: held {out['false_reports'][str(f)]['no_officer']['payments_held']} without officers, "
                  f"{out['false_reports'][str(f)]['officer_q0.9']['payments_held']} with", flush=True)
        summary["legitimate"][g] = out

    (RESULTS / "replay_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


DEFINITIONS = {
    "payment": "an inbound USDT transfer >= 10 USDT from another wallet, before the freeze; one withdrawal by one customer (the sender)",
    "first_warning_real": "the first payment at which the engine raised a Tether freeze signal (counterparty: warning; destination: hold)",
    "first_warning_modelled": "the time of the first simulated customer report (made after a released or warned payment)",
    "payments_after_warning": "payments decided after the first warning existed (real: from that payment on, it is decided after the signal)",
    "payments_source_warned": "payments whose decision cites the source's signal (real: a warning shown; modelled: a hold)",
    "payments_held": "payments the engine put in the hold tier (call-back); each held attempt renews a report, an officer's cleared ends it",
    "lead_days": "freeze_ts - first warning ts, in days; median over wallets with a warning",
    "payment_hold_rate": "held payments / payments; on comparison wallets this is the legitimate-hold rate",
    "false_report_rate": "f: chance a legitimate customer reports the payee after paying (modelled)",
    "officer": "each hold starts a call-back; a day later the officer records confirmed or cleared; right with probability q (modelled)",
}


def _self_check():
    me = "0xscam"
    tx = lambda ts, a, b, usdt: {"ts": ts, "from": a, "to": b, "usdt": usdt, "nonce": 1, "hash": f"{ts}{a}{b}"}
    victims = ["0xv1", "0xv2", "0xv3", "0xv4", "0xv5"]
    h = {"address": me, "group": "test_pos", "freeze_ts": 30 * DAY, "truncated": False, "transfers":
         [tx((1 + i) * DAY, v, me, 1_000) for i, v in enumerate(victims)]
         + [tx(int(1.5 * DAY), me, "0xmule", 900), tx(int(2.5 * DAY), "0xdust", me, 1), tx(40 * DAY, "0xv6", me, 500)]}
    assert len(payments(h)) == 5, "dust, outbound and post-freeze transfers are not payments"
    tiers = lambda hh, **kw: [d.tier for _, d in replay_wallet(hh, **kw)[0]]
    second = lambda i, t, d: i == 1

    # Modelled: 5 payments, only the 2nd customer reports -> payments 3, 4, 5 held.
    decided, report_ts = replay_wallet(h, reporter=second)
    assert [d.tier for _, d in decided] == ["warning", "warning", "hold", "hold", "hold"], decided
    row = summarise(h, decided, "modelled", report_ts)
    assert (row["payments"], row["payments_after_warning"], row["held"]) == (5, 3, 3), row
    assert row["first_warning_ts"] == 2 * DAY and row["lead_days"] == 28.0

    # A report delayed past the 3rd payment only holds the 4th and 5th.
    decided, report_ts = replay_wallet(h, reporter=second, report_delay_s=int(1.5 * DAY))
    assert summarise(h, decided, "modelled", report_ts)["held"] == 2

    # Real: the mule (paid at 1.5 days) is frozen at 2.5 days, so the 3rd payment on are warned,
    # never held. A freeze after the wallet's own freeze and the dust sender's freeze never count.
    freezes = sorted([(int(2.5 * DAY), "0xmule"), (int(2.6 * DAY), "0xdust"), (100 * DAY, "0xv1")])
    row = summarise(h, replay_wallet(h, freezes)[0], "real")
    assert (row["payments_after_warning"], row["source_warned"], row["held"]) == (3, 3, 0), row
    assert row["first_warning_source"] == "counterparty_freeze" and row["first_warning_ts"] == 3 * DAY
    assert row["lead_days"] == 27.0
    assert summarise(h, replay_wallet(h, [(int(5.5 * DAY), "0xmule")])[0], "real")["source_warned"] == 0, \
        "frozen after the last payment"

    # Renewal and officers: payments on days 1, 2, 3, 6, 12, 40 and a report after the 2nd. Held
    # attempts renew the report, so days 3-12 are held; day 40 comes 28 days after the last renewal.
    # Confirmed (day 4) pins it, so day 40 is held too. Cleared (day 4) ends it after the 3rd.
    h2 = {**h, "freeze_ts": 50 * DAY,
          "transfers": [tx(d * DAY, f"0xv{d}", me, 1_000) for d in (1, 2, 3, 6, 12, 40)]}
    assert tiers(h2, reporter=second) == ["warning", "warning", "hold", "hold", "hold", "warning"]
    assert tiers(h2, reporter=second, officer=lambda: "confirmed") == ["warning", "warning"] + ["hold"] * 4
    assert tiers(h2, reporter=second, officer=lambda: "cleared") == ["warning", "warning", "hold"] + ["warning"] * 3
    calls = []
    replay_wallet(h2, reporter=second, officer=lambda: calls.append(1) or "confirmed")
    assert len(calls) == 1, "one call-back per wallet while it is pending or confirmed"
    assert tiers(h, officer=lambda: 1 / 0) == ["warning"] * 5, "no hold, no call-back: the officer is never asked"

    # No warning at all: nothing warned or held, no lead time.
    row = summarise(h, replay_wallet(h)[0], "real")
    assert (row["source_warned"], row["held"], row["first_warning_ts"], row["lead_days"]) == (0, 0, "", ""), row

    # The leak guard fires if the engine ever asks for history past now.
    try:
        GuardedHistory(h, FixedClock(10))(me, 11)
        raise RuntimeError("guard did not fire")
    except AssertionError:
        pass

    # On real wallets: a replay that can only see each payment's past gives the same decisions
    # as the full replay (no future transfer, freeze or label changes anything).
    freezes = sorted((ts, w) for w, ts in load_freezes())
    sample = random.Random(0).sample(positives(), 15)
    for hh in sample:
        full = [(d.tier, d.reasons) for _, d in replay_wallet(hh, freezes)[0]]
        prefix = []
        for k, t in enumerate(payments(hh)[:31]):
            cut = {**hh, "transfers": [x for x in hh["transfers"] if x["ts"] <= t["ts"]]}
            d = replay_wallet(cut, [f for f in freezes if f[0] < t["ts"]])[0][k][1]
            prefix.append((d.tier, d.reasons))
        assert full[:len(prefix)] == prefix, hh["address"]
    print(f"self-check passed: fixed 5-payment replay (warning at the 2nd -> 3 held), real and modelled "
          f"sources, renewal, officer confirm/clear, no-future check on {len(sample)} frozen wallets")


if __name__ == "__main__":
    _self_check()
    if "--check" not in sys.argv:
        s = run()
        print(json.dumps(s["positives"]["real"], indent=2))
        print(json.dumps({g: v["real"] for g, v in s["legitimate"].items()}, indent=2))
