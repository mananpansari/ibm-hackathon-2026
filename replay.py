"""Result 2 (issue #10): replay wallets Tether froze through the decision engine.

Each wallet's inbound payments of >= 10 USDT are replayed in time order. Each payment is one
withdrawal by one customer (customer id = the sending address), decided by the same
Engine.decide() the product uses, with the clock set to the payment's time (every query sees
only events strictly before it). Payee memory carries forward within one wallet's replay; each
wallet starts with a fresh memory.

Warning sources are replayed separately and never mixed:
- real: Tether freezes from freezes.csv, loaded into memory only once the clock has passed
  them. The engine raises a counterparty freeze (or a freeze of the wallet itself).
- modelled: customer answers. After each released or warned payment the customer reports the
  wallet with probability r (no freezes loaded). r is swept 0.1-0.9 over fixed seeds.
- model flag: B's weak model signal (#5) is not wired into the engine yet, so it is reported as
  "not available", never estimated.

Each source is also replayed with officers: every hold is a call-back, and a day later the officer
records "confirmed" (pins the wallet, no decay) or "cleared" (drops the evidence). The officer is
right with probability q (modelled, swept). An officer only acts on a hold, so the first warning
still comes from the source alone.

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
OFFICER_Q = (0.8, 0.9, 1.0)  # P(officer gets the call-back right): modelled
OFFICER_DELAY_S = DAY  # the outcome lands a day after the hold
REAL_SIGNALS = {"counterparty_freeze", "destination_freeze"}
CONTEXT = {"first_time_payee", "known_payee", "p_hold", "base_rate"}  # reasons on every decision, not warnings
MODEL_FLAG = "not available"  # #5 (origin/b/5-weak-model-signal) has model.score() but no engine hook yet


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


def summarise_real(h, decided):
    """Per-wallet row for the real (Tether freeze) source."""
    held = [i for i, (_, d) in enumerate(decided) if d.tier == "hold"]
    for i in held:
        sigs = {r.signal for r in decided[i][1].reasons} - CONTEXT
        assert sigs and sigs <= REAL_SIGNALS | {"officer_confirmed"}, f"non-real hold in the real pass: {sigs}"
        assert all(r.kind == "real" for r in decided[i][1].reasons if r.signal in sigs)
    row = _base_row(h, decided)
    if held:
        first_t, first_d = decided[held[0]]
        row.update(first_warning_ts=first_t["ts"],
                   first_warning_source="+".join(sorted({r.signal for r in first_d.reasons} & REAL_SIGNALS)),
                   payments_after_warning=len(decided) - held[0], held=len(held))
        row["lead_days"] = _lead(h, first_t["ts"])
    return row


def summarise_modelled(h, decided, report_ts):
    """Per-wallet row for the modelled (customer answer) source, from one seeded run."""
    for _, d in decided:
        if d.tier == "hold":
            warnings = [r for r in d.reasons if r.signal not in CONTEXT]
            assert warnings and all((r.signal == "memory_hit" and r.kind == "modelled")
                                    or r.signal == "officer_confirmed" for r in warnings), \
                f"a non-modelled signal fired in the modelled pass: {warnings}"
    row = _base_row(h, decided)
    if report_ts:
        first = min(report_ts)
        row.update(first_warning_ts=first, first_warning_source="customer_answer",
                   payments_after_warning=sum(t["ts"] > first for t, _ in decided),
                   held=sum(d.tier == "hold" for _, d in decided))
        row["lead_days"] = _lead(h, first)
    return row


def _base_row(h, decided):
    return {"address": h["address"], "truncated": int(h["truncated"]), "payments": len(decided),
            "first_warning_ts": "", "first_warning_source": "", "payments_after_warning": 0,
            "held": sum(d.tier == "hold" for _, d in decided), "lead_days": "", "model_flag": MODEL_FLAG}


def _lead(h, ts):
    return round((h["freeze_ts"] - ts) / DAY, 2) if h["freeze_ts"] else ""


def aggregate_pos(rows):
    warned = [r for r in rows if r["first_warning_ts"] != ""]
    leads = [r["lead_days"] for r in warned if r["lead_days"] != ""]
    return {"wallets": len(rows), "wallets_warned": len(warned),
            "payments": sum(r["payments"] for r in rows),
            "payments_after_warning": sum(r["payments_after_warning"] for r in rows),
            "payments_held": sum(r["held"] for r in rows),
            "median_lead_days": round(statistics.median(leads), 1) if leads else None}


def spread(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return {"mean": round(statistics.mean(vals), 1), "sd": round(statistics.pstdev(vals), 1),
            "min": min(vals), "max": max(vals)}


def load_group(group):
    return [json.loads(line) for line in gzip.open(DATA / "histories" / f"{group}.jsonl.gz", "rt")]


def positives():
    """Test positives: frozen Jul-Oct 2026, not OFAC, with >= 1 payment before the freeze."""
    ofac = {r["address"] for r in csv.DictReader(open(DATA / "freezes.csv")) if r["ofac"] == "1"}
    return [h for h in load_group("test_pos") if h["address"] not in ofac and payments(h)]


def write_csv(path, rows, extra_cols=()):
    cols = list(extra_cols) + ["address", "truncated", "payments", "first_warning_ts", "first_warning_source",
                               "payments_after_warning", "held", "lead_days", "model_flag"]
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


def run():
    RESULTS.mkdir(exist_ok=True)
    freezes = sorted((ts, w) for w, ts in load_freezes())
    pos = positives()
    subsets = {"all": lambda h: True, "2plus": lambda h: len(payments(h)) >= 2}
    summary = {"definitions": DEFINITIONS, "model_flag": MODEL_FLAG,
               "positives": {"group": "test_pos", "truncated_wallets": sum(h["truncated"] for h in pos)}}

    # (a) real: Tether freezes only
    real = [summarise_real(h, replay_wallet(h, freezes)[0]) for h in pos]
    write_csv(RESULTS / "replay_test_pos_real.csv", real)
    summary["positives"]["real"] = {k: aggregate_pos([r for r, h in zip(real, pos) if keep(h)])
                                    for k, keep in subsets.items()}

    # (b) modelled: customer answers at rate r, no freezes
    mrows, msum = [], {k: {} for k in subsets}
    for r in RATES:
        per_seed = {k: [] for k in subsets}
        for seed in SEEDS:
            rows = []
            for h in pos:
                decided, report_ts = replay_wallet(h, reporter=coin(seed, r, h["address"]))
                rows.append(summarise_modelled(h, decided, report_ts))
            mrows += [{"r": r, "seed": seed, **row} for row in rows]
            for k, keep in subsets.items():
                per_seed[k].append(aggregate_pos([row for row, h in zip(rows, pos) if keep(h)]))
        for k in subsets:
            msum[k][str(r)] = {m: spread([a[m] for a in per_seed[k]]) for m in per_seed[k][0]
                               if m not in ("wallets", "payments")}
            msum[k][str(r)].update(wallets=per_seed[k][0]["wallets"], payments=per_seed[k][0]["payments"])
        print(f"modelled r={r}: held {msum['all'][str(r)]['payments_held']}", flush=True)
    write_csv(RESULTS / "replay_test_pos_modelled.csv", mrows, extra_cols=("r", "seed"))
    summary["positives"]["modelled"] = {"seeds": len(SEEDS), "report_delay_s": 0, **msum}

    # Sensitivity: the answer only reaches the bank a day later (r = 0.5).
    sens = []
    for seed in SEEDS:
        rows = [summarise_modelled(h, *replay_wallet(h, reporter=coin(seed, 0.5, h["address"]), report_delay_s=DAY))
                for h in pos]
        sens.append(aggregate_pos(rows))
    summary["positives"]["modelled_r0.5_delay_1d"] = {m: spread([a[m] for a in sens])
                                                       for m in sens[0] if m not in ("wallets", "payments")}

    # (c) model flag: not wired into the engine
    summary["positives"]["model_flag"] = MODEL_FLAG

    # Legitimate holds: the real pass over both comparison sets
    summary["legitimate_holds"] = {}
    for g in ("test_neg", "test_negv"):
        hs = [h for h in load_group(g) if payments(h)]
        rows = [summarise_real(h, replay_wallet(h, freezes)[0]) for h in hs]
        write_csv(RESULTS / f"replay_{g}_real.csv", rows)
        n, held = sum(r["payments"] for r in rows), sum(r["held"] for r in rows)
        summary["legitimate_holds"][g] = {
            "wallets": len(rows), "truncated_wallets": sum(r["truncated"] for r in rows),
            "payments": n, "payments_held": held, "payment_hold_rate": round(held / n, 5),
            "wallets_with_any_hold": sum(r["held"] > 0 for r in rows),
            "wallet_hold_rate": round(sum(r["held"] > 0 for r in rows) / len(rows), 4),
            "modelled": "not replayed: r is the rate at which scam victims report; the false-report "
                        "rate of legitimate customers is unknown, so no modelled number is given"}
        print(f"{g}: {held}/{n} payments held", flush=True)

    summary["officer"] = run_officer(pos, freezes, subsets)
    (RESULTS / "replay_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def run_officer(pos, freezes, subsets):
    """The same passes with call-back officers who are right with probability q (modelled)."""
    out = {"q": list(OFFICER_Q), "officer_delay_s": OFFICER_DELAY_S, "seeds": len(SEEDS),
           "positives_modelled": {k: {} for k in subsets}, "positives_real": {}, "legitimate_holds": {}}
    for q in OFFICER_Q:
        qs = str(q)
        for k in subsets:
            out["positives_modelled"][k][qs] = {}
        for r in RATES:
            per_seed = {k: [] for k in subsets}
            for seed in SEEDS:
                rows = [summarise_modelled(h, *replay_wallet(h, reporter=coin(seed, r, h["address"]),
                                                             officer=officer_for(seed, q, h["address"], True)))
                        for h in pos]
                for k, keep in subsets.items():
                    per_seed[k].append(aggregate_pos([row for row, h in zip(rows, pos) if keep(h)]))
            for k in subsets:
                out["positives_modelled"][k][qs][str(r)] = {m: spread([a[m] for a in per_seed[k]])
                                                            for m in ("payments_after_warning", "payments_held")}
        print(f"officer q={q}: modelled r=0.5 held "
              f"{out['positives_modelled']['all'][qs]['0.5']['payments_held']}", flush=True)
        held = [sum(summarise_real(h, replay_wallet(h, freezes, officer=officer_for(seed, q, h["address"], True))[0])
                    ["held"] for h in pos) for seed in SEEDS]
        out["positives_real"][qs] = spread(held)

    # Officers only act on holds, so a comparison wallet with no hold in the plain real pass is
    # unchanged; only the wallets that had a hold are replayed again.
    for g in ("test_neg", "test_negv"):
        rows = list(csv.DictReader(open(RESULTS / f"replay_{g}_real.csv")))
        n = sum(int(r["payments"]) for r in rows)
        hit = {r["address"] for r in rows if int(r["held"]) > 0}
        hs = [h for h in load_group(g) if h["address"] in hit]
        out["legitimate_holds"][g] = {"payments": n, "wallets_replayed": len(hs)}
        for q in OFFICER_Q:
            held = [sum(summarise_real(h, replay_wallet(h, freezes, officer=officer_for(seed, q, h["address"], False))[0])
                        ["held"] for h in hs) for seed in SEEDS]
            out["legitimate_holds"][g][str(q)] = {"payments_held": spread(held),
                                                  "payment_hold_rate_mean": round(statistics.mean(held) / n, 6)}
        print(f"officer {g}: {out['legitimate_holds'][g]}", flush=True)
    return out


DEFINITIONS = {
    "payment": "an inbound USDT transfer >= 10 USDT from another wallet, before the freeze; one withdrawal by one customer (the sender)",
    "first_warning_real": "the first payment at which the engine raised a Tether freeze signal (counterparty or destination)",
    "first_warning_modelled": "the time of the first simulated customer report (made after a released or warned payment)",
    "payments_after_warning": "payments decided after the first warning existed (real: from that payment on, it is decided after the signal)",
    "payments_held": "payments the engine put in the hold tier (call-back); reports decay with a 7-day half-life, freezes do not",
    "lead_days": "freeze_ts - first warning ts, in days; median over wallets with a warning",
    "legit_hold_rate": "held payments / payments on comparison wallets Tether never froze (real pass only)",
    "officer": "each hold starts a call-back; a day later the officer records confirmed (no decay) or cleared; "
               "right with probability q (modelled)",
}


def _self_check():
    H = 3600
    me = "0xscam"
    tx = lambda ts, a, b, usdt: {"ts": ts, "from": a, "to": b, "usdt": usdt, "nonce": 1, "hash": f"{ts}{a}{b}"}
    victims = ["0xv1", "0xv2", "0xv3", "0xv4", "0xv5"]
    h = {"address": me, "group": "test_pos", "freeze_ts": 30 * DAY, "truncated": False, "transfers":
         [tx((1 + i) * DAY, v, me, 1_000) for i, v in enumerate(victims)]
         + [tx(int(1.5 * DAY), me, "0xmule", 900), tx(int(2.5 * DAY), "0xdust", me, 1), tx(40 * DAY, "0xv6", me, 500)]}
    assert len(payments(h)) == 5, "dust, outbound and post-freeze transfers are not payments"

    # Modelled: 5 payments, only the 2nd customer reports -> payments 3, 4, 5 held.
    decided, report_ts = replay_wallet(h, reporter=lambda i, t, d: i == 1)
    assert [d.tier for _, d in decided] == ["warning", "warning", "hold", "hold", "hold"], decided
    row = summarise_modelled(h, decided, report_ts)
    assert (row["payments"], row["payments_after_warning"], row["held"]) == (5, 3, 3), row
    assert row["first_warning_ts"] == 2 * DAY and row["lead_days"] == 28.0

    # A report delayed past the 3rd payment only holds the 4th and 5th.
    decided, report_ts = replay_wallet(h, reporter=lambda i, t, d: i == 1, report_delay_s=int(1.5 * DAY))
    assert summarise_modelled(h, decided, report_ts)["held"] == 2

    # Real: the mule (paid at 1.5 days) is frozen at 2.5 days, so the 3rd payment on are held.
    # A freeze at 100 days (after the wallet's own freeze) and the dust sender's freeze never count.
    freezes = sorted([(int(2.5 * DAY), "0xmule"), (int(2.6 * DAY), "0xdust"), (100 * DAY, "0xv1")])
    row = summarise_real(h, replay_wallet(h, freezes)[0])
    assert (row["payments_after_warning"], row["held"], row["first_warning_source"]) == (3, 3, "counterparty_freeze"), row
    assert row["first_warning_ts"] == 3 * DAY and row["lead_days"] == 27.0
    assert summarise_real(h, replay_wallet(h, [(int(5.5 * DAY), "0xmule")])[0])["held"] == 0, \
        "frozen after the last payment"

    # Officers: payments on days 1, 2, 3, 6, 12 and a report after the 2nd. Alone, the report has
    # faded by day 12 (10 days, under 0.5): 2 held. Confirmed on day 4 pins it: 3 held. Cleared on
    # day 4 drops it: only the 3rd is held.
    h2 = {**h, "transfers": [tx(d * DAY, v, me, 1_000) for d, v in zip((1, 2, 3, 6, 12), victims)]}
    tiers = lambda **kw: [d.tier for _, d in replay_wallet(h2, reporter=lambda i, t, d: i == 1, **kw)[0]]
    assert tiers() == ["warning", "warning", "hold", "hold", "warning"], tiers()
    assert tiers(officer=lambda: "confirmed") == ["warning", "warning", "hold", "hold", "hold"]
    assert tiers(officer=lambda: "cleared") == ["warning", "warning", "hold", "warning", "warning"]
    calls = []
    replay_wallet(h2, reporter=lambda i, t, d: i == 1, officer=lambda: calls.append(1) or "confirmed")
    assert len(calls) == 1, "one call-back per wallet while it is pending or confirmed"
    row = summarise_modelled(h2, *replay_wallet(h2, reporter=lambda i, t, d: i == 1, officer=lambda: "confirmed"))
    assert (row["payments_after_warning"], row["held"]) == (3, 3), row
    assert [d.tier for _, d in replay_wallet(h, officer=lambda: 1 / 0)[0]] == ["warning"] * 5, \
        "no hold, no call-back: the officer is never asked"

    # No warning at all: nothing held, no lead time.
    row = summarise_real(h, replay_wallet(h)[0])
    assert (row["held"], row["first_warning_ts"], row["lead_days"]) == (0, "", ""), row

    # The leak guard fires if the engine ever asks for history past now.
    clock = FixedClock(10)
    try:
        GuardedHistory(h, clock)(me, 11)
        raise RuntimeError("guard did not fire")
    except AssertionError:
        pass

    # On real wallets: a replay that can only see each payment's past gives the same decisions
    # as the full replay (no future transfer, freeze or label changes anything).
    freezes = sorted((ts, w) for w, ts in load_freezes())
    pos = positives()
    sample = random.Random(0).sample(pos, 15)
    for hh in sample:
        full = [d.tier for _, d in replay_wallet(hh, freezes)[0]]
        prefix = []
        for k, t in enumerate(payments(hh)):
            cut = {**hh, "freeze_ts": hh["freeze_ts"], "transfers": [x for x in hh["transfers"] if x["ts"] <= t["ts"]]}
            past = [f for f in freezes if f[0] < t["ts"]]
            prefix.append(replay_wallet(cut, past)[0][k][1].tier)
            if k >= 30:
                break
        assert full[:len(prefix)] == prefix, (hh["address"], full, prefix)
    print(f"self-check passed: fixed 5-payment replay (warning at the 2nd -> 3 held), real and modelled "
          f"sources, officer confirm/clear, no-future check on {len(sample)} frozen wallets")


if __name__ == "__main__":
    _self_check()
    if "--check" not in sys.argv:
        s = run()
        print(json.dumps({k: s["positives"][k] for k in ("real", "model_flag")}, indent=2))
        print(json.dumps(s["legitimate_holds"], indent=2))
        print(json.dumps({k: v for k, v in s["officer"].items() if k != "positives_modelled"}, indent=2))
