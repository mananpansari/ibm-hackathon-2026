"""Demo wallet shortlist (#16): rank the wallets Tether froze Jul-Oct 2026 for the demo spine.

Reads the snapshot only (data/histories/test_pos.jsonl.gz, data/freezes.csv); never calls Blockscout.
Every per-payment number uses only what was known at that payment's time: a counterparty counts as a
warning only if Tether froze it before the payment, as in engine.Engine._counterparty_freezes.

Payments are counted exactly as D's demo replays them (app.py demo_next): inbound, >= 10 USDT,
before the freeze. The table's "held" columns are quick estimates for ranking; --numbers replays one
wallet through the engine (as #10 does) and is what the narration quotes. The estimates assume:
- cp_held:     the counterparty-freeze rule alone (real evidence), from the first payment it fires on.
- ans_held:    customer 1's answer confirms the script and an officer confirms (pins, no decay),
               so every later payment is held. Modelled: depends on customer 1 answering.
- ans_held_7d: the same answer as an unconfirmed report, which decays (7-day half-life in
               payee_memory.py), so only later payments within 7 days of payment 1 are held.

    python demo_candidates.py                 # ranked table
    python demo_candidates.py --export 3      # also write data/demo/<address>.json for the top 3
    python demo_candidates.py --numbers 0x74f6...  # engine replay -> data/demo/narration_numbers.json
                                                   # (incl. ui_v2_spine: Mrs Tan as payment 2, the app's path)
"""
import argparse
import csv
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

DATA = Path(__file__).resolve().parent / "data"
DAY = 86400
MIN_USDT = 10  # as in features.py and engine.py
HOT_NONCE = 10_000  # sender nonce above this: an exchange hot wallet (the Mrs Tan pattern)
REPORT_HALF_LIFE_D = 7  # payee_memory.PayeeMemory default; one report holds for one half-life
# Demo pacing: the spine is ~90 s, so a handful of payments, not hundreds (D's stand-in uses 6-15).
MIN_PAYS, MAX_PAYS = 4, 20
# A retail story: payments a person could plausibly make from savings, in USDT.
RETAIL_LO, RETAIL_HI = 100, 150_000


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def load():
    freezes = {}
    for r in csv.DictReader(open(DATA / "freezes.csv")):
        freezes[r["address"]] = r
    hists = [json.loads(line) for line in gzip.open(DATA / "histories" / "test_pos.jsonl.gz", "rt")]
    return hists, freezes


def payments(h):
    """The payments D's demo replays, in time order."""
    me = h["address"]
    return [t for t in h["transfers"] if t["to"] == me and t["from"] != me and t["usdt"] >= MIN_USDT and t["ts"] < h["freeze_ts"]]


def frozen_counterparties(h, now, frozen_at):
    """Counterparties (>= 10 USDT, either direction, before now) that Tether froze before now."""
    me = h["address"]
    cps = {t["from"] if t["to"] == me else t["to"] for t in h["transfers"]
           if t["ts"] < now and t["usdt"] >= MIN_USDT and me in (t["from"], t["to"])}
    cps.discard(me)
    return {a: frozen_at[a] for a in cps if frozen_at.get(a, float("inf")) < now}


def assess(h, freezes, frozen_at):
    pays = payments(h)
    n = len(pays)
    row = {"address": h["address"], "n_pays": n, "truncated": h["truncated"],
           "ofac": freezes.get(h["address"], {}).get("ofac") == "1", "freeze_ts": h["freeze_ts"]}
    if n < 2:
        return {**row, "eligible": False, "why_not": "fewer than 2 payments"}
    senders = {t["from"] for t in pays}
    hot = {t["from"] for t in pays if t["nonce"] > HOT_NONCE}
    amounts = [t["usdt"] for t in pays]
    warn_step = next((i + 1 for i, t in enumerate(pays) if frozen_counterparties(h, t["ts"], frozen_at)), None)
    p1 = pays[0]["ts"]
    row.update(
        n_senders=len(senders), n_hot_senders=len(hot),
        hot_share=sum(t["nonce"] > HOT_NONCE for t in pays) / n,
        total_usdt=sum(amounts), median_usdt=median(amounts), max_usdt=max(amounts),
        days_2nd_to_freeze=(h["freeze_ts"] - pays[1]["ts"]) / DAY,
        days_1st_to_freeze=(h["freeze_ts"] - p1) / DAY,
        cp_warn_step=warn_step,
        cp_warn_days_before_freeze=(h["freeze_ts"] - pays[warn_step - 1]["ts"]) / DAY if warn_step else None,
        cp_held=n - warn_step + 1 if warn_step else 0,
        cp_held_usdt=sum(amounts[warn_step - 1:]) if warn_step else 0.0,
        ans_held=n - 1, ans_held_usdt=sum(amounts[1:]),
        ans_held_7d=sum(t["ts"] - p1 < REPORT_HALF_LIFE_D * DAY for t in pays[1:]),
    )
    why_not = [w for w, bad in [
        ("OFAC", row["ofac"]), ("truncated history", h["truncated"]),
        (f"not {MIN_PAYS}-{MAX_PAYS} payments", not MIN_PAYS <= n <= MAX_PAYS),
        ("fewer than 3 senders", len(senders) < 3),
        ("no exchange hot-wallet sender", not hot),
        ("median payment outside retail range", not RETAIL_LO <= row["median_usdt"] <= RETAIL_HI),
        # D's spine holds payment 2 because of payment 1's answer; past the half-life that needs an officer pin
        (f"2nd payment more than {REPORT_HALF_LIFE_D} days after the 1st", row["ans_held_7d"] == 0),
        ("active over a year before the freeze", row["days_1st_to_freeze"] > 365),
    ] if bad]
    row["eligible"], row["why_not"] = not why_not, "; ".join(why_not)
    # Ranking: an early, real, explainable warning first; then a gap the line "N days before Tether
    # froze it" can quote (capped: ~3 months already makes the point); then the Mrs Tan pattern
    # (exchange withdrawals from several senders, ideally from the first payments).
    row["score"] = ((3 if warn_step == 2 else 2 if warn_step and warn_step <= 3 else 1 if warn_step else 0)
                    + min(row["days_2nd_to_freeze"], 90) / 60
                    + 2 * row["hot_share"] + min(len(senders), 10) / 5
                    + any(t["nonce"] > HOT_NONCE for t in pays[:2]))
    return row


def reason(r):
    bits = [f"{r['n_pays']} payments from {r['n_senders']} senders ({r['n_hot_senders']} exchange hot wallets)",
            f"median {r['median_usdt']:,.0f} USDT",
            f"2nd payment {r['days_2nd_to_freeze']:.0f} days before the freeze",
            f"{r['ans_held_7d']} later payment(s) within {REPORT_HALF_LIFE_D} days of the 1st"]
    if r["cp_warn_step"]:
        bits.append(f"counterparty-freeze warning fires at payment {r['cp_warn_step']} "
                    f"({r['cp_warn_days_before_freeze']:.0f} days before the freeze)")
    else:
        bits.append("no counterparty freeze before any payment: answer path only")
    return "; ".join(bits)


def timeline(h, freezes, frozen_at, r):
    pays = payments(h)
    out = []
    for i, t in enumerate(pays, 1):
        cps = frozen_counterparties(h, t["ts"], frozen_at)
        out.append({
            "step": i, "ts": t["ts"], "time": iso(t["ts"]), "usdt": round(t["usdt"], 6), "from": t["from"],
            "sender_nonce": t["nonce"], "sender_hot_wallet": t["nonce"] > HOT_NONCE, "hash": t["hash"],
            "days_before_freeze": round((h["freeze_ts"] - t["ts"]) / DAY, 1),
            # real evidence available at this payment's time (Tether froze these before t["ts"])
            "frozen_counterparties": [{"address": a, "freeze_ts": ts, "time": iso(ts)} for a, ts in sorted(cps.items(), key=lambda x: x[1])],
        })
    f = freezes.get(h["address"], {})
    return {
        "address": h["address"],
        "chain": "ethereum", "token": "USDT",
        "freeze_ts": h["freeze_ts"], "freeze_time": iso(h["freeze_ts"]), "freeze_tx": f.get("tx_hash"),
        "source": "data/histories/test_pos.jsonl.gz + data/freezes.csv (snapshot, #2)",
        "payment_rule": "inbound, >= 10 USDT, before freeze_ts (same as app.py demo_next)",
        "summary": {k: round(r[k], 2) if isinstance(r[k], float) else r[k]
                    for k in ("n_pays", "n_senders", "n_hot_senders", "total_usdt", "median_usdt",
                              "days_2nd_to_freeze", "cp_warn_step", "cp_held", "ans_held", "ans_held_7d")},
        "provisional": "cp_held / ans_held / ans_held_7d are quick estimates; quote data/demo/narration_numbers.json (engine replay)",
        "payments": out,
    }


def engine_numbers(h):
    """The demo wallet through the #10 replay's engine path (replay.replay_wallet): what it actually holds.

    Scenarios, all with customer 1's answer confirming the script (modelled, as in D's demo):
    - answer_only: that answer is the only warning; it decays (7-day half-life).
    - officer_confirms: the first hold starts a call-back and the officer confirms (pins the wallet),
      the outcome landing replay.OFFICER_DELAY_S (a day) later, as in #10's officer pass at q = 1.0.
    - real_freezes_only: no answer at all, Tether freezes only (the #10 real pass).
    """
    import replay
    from payee_memory import load_freezes

    freezes = sorted((ts, w) for w, ts in load_freezes())
    first_answers = lambda i, t, d: i == 0
    runs = {"answer_only": replay.replay_wallet(h, reporter=first_answers)[0],
            "officer_confirms": replay.replay_wallet(h, reporter=first_answers, officer=lambda: "confirmed")[0],
            "real_freezes_only": replay.replay_wallet(h, freezes)[0]}
    out = {}
    for name, decided in runs.items():
        held = [i for i, (_, d, *_) in enumerate(decided) if d.tier == "hold"]
        out[name] = {
            "tiers": [d.tier for _, d, *_ in decided],
            "payments_held": len(held),
            "usdt_held": round(sum(decided[i][0]["usdt"] for i in held), 2),
            "first_held_step": held[0] + 1 if held else None,
            "days_first_hold_to_freeze": round((h["freeze_ts"] - decided[held[0]][0]["ts"]) / DAY, 1) if held else None,
        }
    return out


TAN_STEP = 2  # UI v2 spine: Mrs Tan is the 78,000 USDT payment, which the engine itself asks about


def spine_numbers(h, tan_step=TAN_STEP):
    """The UI v2 demo spine through the engine exactly as the app runs it (answers.StructuredClassifier):
    every payment is its own customer (exchange hot wallets carry many customers' withdrawals), Mrs Tan
    is payment `tan_step`. Her structured answer (data/demo/coached_answer.json) and an officer's
    confirmation a day after her hold are scripted, so modelled. The tier before her answer is the
    engine's own: no scripted question."""
    import tempfile
    import granite
    from answers import StructuredClassifier
    from decision_log import DecisionLog
    from engine import Engine, Withdrawal
    from payee_memory import OfficerOutcome, PayeeMemory, load_freezes

    answer = json.loads((DATA / "demo" / "coached_answer.json").read_text())["answer"]
    pays = payments(h)
    out = {}
    for name, confirm in (("officer_confirms", True), ("answer_only", False)):
        clock = {"now": 0}
        memory = PayeeMemory()
        memory.add_freezes(load_freezes())
        eng = Engine(lambda w, as_of: {**h, "freeze_ts": None, "transfers": [t for t in h["transfers"] if t["ts"] < as_of]},
                     memory, lambda: clock["now"], DecisionLog(Path(tempfile.mkdtemp()) / "log.jsonl"),
                     classifier=StructuredClassifier(granite))
        tiers, before = [], None
        for i, t in enumerate(pays, 1):
            clock["now"] = t["ts"]
            w = Withdrawal("mrs-tan" if i == tan_step else f"customer-{i}", h["address"], t["usdt"], t["ts"])
            d = eng.decide(w)
            if i == tan_step:
                before = d.tier
                d = eng.decide(w, answer, "modelled")
                if confirm and d.tier == "hold":
                    eng.record(OfficerOutcome(h["address"], "confirmed", t["ts"] + DAY, "demo officer (scripted)",
                                              kind="modelled", reason="confirmed_impersonation"))
            tiers.append(d.tier)
        held = [i for i, tier in enumerate(tiers) if tier == "hold"]
        after = [i for i in held if i >= tan_step]
        out[name] = {"tiers": tiers, "payments_held": len(held), "usdt_held": round(sum(pays[i]["usdt"] for i in held), 2),
                     "held_after_tan": len(after), "usdt_held_after_tan": round(sum(pays[i]["usdt"] for i in after), 2)}
    t = pays[tan_step - 1]
    return {"tan_step": tan_step, "tan_usdt": t["usdt"], "tan_time": iso(t["ts"]), "tan_tier_before_answer": before,
            "days_tan_to_freeze": round((h["freeze_ts"] - t["ts"]) / DAY, 1),
            "days_tan_to_last_payment": round((pays[-1]["ts"] - t["ts"]) / DAY, 1),
            "n_senders_after_tan": len({p["from"] for p in pays[tan_step:]}), **out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", type=int, default=0, help="write data/demo/<address>.json for the top N")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--numbers", metavar="ADDRESS", help="replay one wallet through the engine -> data/demo/narration_numbers.json")
    args = ap.parse_args()
    if args.numbers:
        hists, _ = load()
        h = next(h for h in hists if h["address"] == args.numbers.lower())
        nums = {"address": h["address"], "source": "demo_candidates.py --numbers (engine via replay.replay_wallet)",
                "modelled": "customer 1's confirming answer and the officer's confirmation are scripted, not measured",
                **engine_numbers(h), "ui_v2_spine": spine_numbers(h)}
        path = DATA / "demo" / "narration_numbers.json"
        path.write_text(json.dumps(nums, indent=1) + "\n")
        print(json.dumps(nums, indent=1))
        return
    hists, freezes = load()
    # Counterparty evidence as the engine sees it: every Tether freeze minus OFAC (payee_memory.load_freezes).
    frozen_at = {a: int(r["freeze_ts"]) for a, r in freezes.items() if r["ofac"] != "1"}
    rows = [assess(h, freezes, frozen_at) for h in hists]
    ok = sorted((r for r in rows if r["eligible"]), key=lambda r: -r["score"])
    print(f"{len(ok)} of {len(rows)} test wallets pass the demo filters\n")
    print("rank address                                     pays snd hot  med_USDT  d2nd->frz cp_warn cp_held* ans_held* ans_7d* score")
    for i, r in enumerate(ok[:args.top], 1):
        print(f"{i:>4} {r['address']} {r['n_pays']:>4} {r['n_senders']:>3} {r['n_hot_senders']:>3} {r['median_usdt']:>9,.0f} "
              f"{r['days_2nd_to_freeze']:>10.0f} {str(r['cp_warn_step'] or '-'):>7} {r['cp_held']:>8} {r['ans_held']:>9} "
              f"{r['ans_held_7d']:>7} {r['score']:>5.2f}")
    print("\n* quick estimates for ranking; quote --numbers (engine replay) instead\n")
    for i, r in enumerate(ok[:args.top], 1):
        print(f"{i}. {r['address']}: {reason(r)}")
    by_addr = {h["address"]: h for h in hists}
    if args.export:
        (DATA / "demo").mkdir(exist_ok=True)
        for r in ok[:args.export]:
            path = DATA / "demo" / f"{r['address']}.json"
            path.write_text(json.dumps(timeline(by_addr[r["address"]], freezes, frozen_at, r), indent=1) + "\n")
            print(f"wrote {path.relative_to(DATA.parent)}")


if __name__ == "__main__":
    main()
