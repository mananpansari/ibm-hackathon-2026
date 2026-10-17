"""Result 3: at equal officer capacity, the ladder averts more than rules-only, a fixed threshold
or calling everyone (issue #9). Also the capacity rule's end-to-end check.

Real: every payment of >= 10 USDT to the test wallets (Tether-frozen wallets = scam payments,
random and volume-matched comparison wallets = legitimate ones), their amounts, senders (one
sender = one customer) and order, and Tether freezes. To give each officer-day a realistic load,
the payments keep their real order but are packed into DAYS equal bank days.

Modelled (swept or stated, never measured; label them on the slide):
- scam rate: share of withdrawals that are scam payments, set by sampling whole frozen wallets;
- a coached victim's answer confirms the scam script with P_CONFIRM; a legitimate one with P_FALSE;
- the chance a scam payment is stopped at each final tier (STOP);
- no customer reports after the fact; the ladder learns only from answers, holds and calls;
- at the end of each day officers call every hold still in a slot and mark the wallet confirmed or
  cleared, correctly with P_OFFICER_RIGHT (bumped holds get no call).

Policies, all with the same calls per day; when a day is full the smallest hold loses its slot:
- ladder: engine.decide() with Config.daily_capacity; questions answered by the modelled customer;
- rules-only: hold when Tether froze the wallet or a wallet it dealt with (before now), else release;
- fixed threshold: hold a first-time payee paying >= FIXED_USDT, else release;
- call everyone: hold every first-time payee, in arrival order, else release.

    python sweep.py          # table + chart -> docs/result3.md, docs/result3.svg
    python sweep.py check    # quick self-check on a small slice
    python sweep.py docs     # rewrite docs/result3.md and .svg from docs/result3.json, no re-run
"""
import gzip
import json
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

from engine import DAY, Config, Engine, FixedClock, Withdrawal
from payee_memory import OfficerOutcome
from payee_memory import PayeeMemory, load_freezes

DATA = Path(__file__).resolve().parent / "data"
DOCS = Path(__file__).resolve().parent / "docs"
DAYS = 30
P_CONFIRM, P_FALSE = 0.5, 0.02
STOP = {"release": 0.0, "warning": 0.05, "question": 0.25, "hold": 0.8}
P_OFFICER_RIGHT = 0.9  # after a call-back the officer marks the wallet confirmed (scam) or cleared, correctly this often
FIXED_USDT = 10_000
CAPACITIES = (0, 5, 10, 25, 50, 100, 250)
SCAM_RATES = (0.001, 0.005, 0.01)
POLICIES = ("ladder", "rules-only", "fixed threshold", "call everyone")


def payments():
    """Every payment to a test wallet, in time order, with the point-in-time Tether-rule flag."""
    freeze = dict(load_freezes())
    out = []
    for group in ("test_pos", "test_neg", "test_negv"):
        for line in gzip.open(DATA / "histories" / f"{group}.jsonl.gz", "rt"):
            h = json.loads(line)
            me, end = h["address"], h["freeze_ts"] or float("inf")
            first_cp_freeze = float("inf")  # earliest freeze among counterparties seen so far
            for t in h["transfers"]:
                if t["ts"] >= end:
                    break
                if t["to"] == me and t["from"] != me and t["usdt"] >= 10:
                    tether = first_cp_freeze < t["ts"] or freeze.get(me, float("inf")) < t["ts"]
                    out.append({"ts": t["ts"], "customer": t["from"], "wallet": me, "usdt": t["usdt"],
                                "scam": group == "test_pos", "tether_rule": tether})
                if t["usdt"] >= 10:
                    cp = t["from"] if t["to"] == me else t["to"]
                    first_cp_freeze = min(first_cp_freeze, freeze.get(cp, float("inf")))
    out.sort(key=lambda p: (p["ts"], p["wallet"], p["customer"]))
    return out


def stream(pays, scam_rate, seed=0):
    """Keep every legitimate payment; sample whole frozen wallets to hit scam_rate; pack into DAYS days."""
    legit = [p for p in pays if not p["scam"]]
    scam_wallets = sorted({p["wallet"] for p in pays if p["scam"]})
    random.Random(seed).shuffle(scam_wallets)
    want = scam_rate / (1 - scam_rate) * len(legit)
    keep, n = set(), 0
    by_wallet = defaultdict(int)
    for p in pays:
        if p["scam"]:
            by_wallet[p["wallet"]] += 1
    for w in scam_wallets:
        if n >= want:
            break
        keep.add(w)
        n += by_wallet[w]
    s = [p for p in pays if not p["scam"] or p["wallet"] in keep]
    per_day = len(s) / DAYS
    return [{**p, "t": int(i / per_day * DAY) + 1} for i, p in enumerate(s)]  # packed bank time


class NoLog:
    """The sweep makes ~150k decisions per run and needs no audit trail; the product uses DecisionLog."""

    def append(self, record):
        pass


class ModelledCustomer:
    """Answers the engine's question: confirms the script with P_CONFIRM if scammed, else P_FALSE."""

    def __init__(self, seed=0):
        self.rng, self.scam = random.Random(seed), False

    def ask(self, withdrawal, reasons):
        return "template"

    def classify(self, answer):
        yes = self.rng.random() < (P_CONFIRM if self.scam else P_FALSE)
        return {"scam_type": "government_impersonation" if yes else "none", "confirms_script": yes,
                "source": "modelled customer", "kind": "modelled"}


def run_ladder(s, capacity, seed=0):
    cust = ModelledCustomer(seed)
    officer = random.Random(seed + 1)
    eng = Engine(lambda w, t: None, PayeeMemory(), FixedClock(0), NoLog(),
                 config=Config(daily_capacity=capacity, day_offset_s=0), classifier=cust)  # packed bank days start at t=0
    tiers, index = [], {}  # index: id(Withdrawal) -> stream position, to trace a bumped or called hold back
    ws = []  # keeps every Withdrawal alive so ids stay unique
    day = 0

    def call_backs(d):
        """End of day d: officers call the holds still in that day's slots and record what they find."""
        for held in eng.holds_by_day.get(d, []):
            scam = s[index[id(held.withdrawal)]]["scam"]
            right = officer.random() < P_OFFICER_RIGHT
            outcome = "confirmed" if scam == right else "cleared"
            eng.record(OfficerOutcome(held.withdrawal.wallet, outcome, (d + 1) * DAY - 1, "modelled officer", kind="modelled"))

    for i, p in enumerate(s):
        while p["t"] // DAY > day:
            call_backs(day)
            day += 1
        eng.clock.now = p["t"]
        w = Withdrawal(p["customer"], p["wallet"], p["usdt"], p["t"])
        ws.append(w)
        index[id(w)] = i
        dec = eng.decide(w)
        if dec.tier == "question":
            cust.scam = p["scam"]
            dec = eng.decide(w, answer="(modelled answer)")
        tiers.append(dec.tier)
        if dec.bumped is not None:
            tiers[index[id(dec.bumped.withdrawal)]] = "question"
    return tiers


def run_rule(s, capacity, wants_hold, rank):
    """A baseline: hold what wants_hold() picks, within capacity, the smallest rank losing its slot."""
    tiers = ["release"] * len(s)
    paid = set()
    day_holds = defaultdict(list)
    for i, p in enumerate(s):
        first = (p["customer"], p["wallet"]) not in paid
        if wants_hold(p, first):
            today = day_holds[p["t"] // DAY]
            if len(today) < capacity:
                today.append(i)
                tiers[i] = "hold"
            elif today and rank(p) > rank(s[min(today, key=lambda j: rank(s[j]))]):
                j = min(today, key=lambda j: rank(s[j]))
                today.remove(j)
                tiers[j] = "release"  # baselines have no question tier: a lost slot means release
                today.append(i)
                tiers[i] = "hold"
        if tiers[i] != "hold":
            paid.add((p["customer"], p["wallet"]))
    return tiers


def run(policy, s, capacity):
    if policy == "ladder":
        return run_ladder(s, capacity)
    if policy == "rules-only":
        return run_rule(s, capacity, lambda p, first: p["tether_rule"], lambda p: p["usdt"])
    if policy == "fixed threshold":
        return run_rule(s, capacity, lambda p, first: first and p["usdt"] >= FIXED_USDT, lambda p: p["usdt"])
    if policy == "call everyone":
        return run_rule(s, capacity, lambda p, first: first, lambda p: -p["t"])  # earlier = higher rank
    raise ValueError(policy)


def score(s, tiers):
    scam_total = sum(p["usdt"] for p in s if p["scam"])
    averted = sum(p["usdt"] * STOP[t] for p, t in zip(s, tiers) if p["scam"])
    legit = [t for p, t in zip(s, tiers) if not p["scam"]]
    return {"averted": averted, "share": averted / scam_total if scam_total else 0.0,
            "legit_held": legit.count("hold"), "legit_questioned": legit.count("question"),
            "legit": len(legit), "scam_payments": sum(p["scam"] for p in s)}


def svg_chart(rows, rate, path):
    """Capacity (calls/day) on x, share of scam USDT averted on y, one line per policy."""
    W, H, L, R, T, B = 720, 420, 70, 170, 30, 60
    caps = sorted({r["capacity"] for r in rows})
    xs = {c: L + (W - L - R) * i / (len(caps) - 1) for i, c in enumerate(caps)}
    y = lambda v: T + (H - T - B) * (1 - v)
    colors = {"ladder": "#0b6e4f", "rules-only": "#8a8a8a", "fixed threshold": "#c77d00", "call everyone": "#3b5bdb"}
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif" font-size="12">',
           f'<rect width="{W}" height="{H}" fill="white"/>',
           f'<text x="{L}" y="18" font-size="14" font-weight="bold">Scam USDT averted vs officer call-backs per day (scam rate {rate:.1%})</text>']
    for v in (0, 0.25, 0.5, 0.75, 1):
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v)}" y2="{y(v)}" stroke="#e5e5e5"/>'
                   f'<text x="{L - 8}" y="{y(v) + 4}" text-anchor="end">{v:.0%}</text>')
    for c in caps:
        out.append(f'<text x="{xs[c]}" y="{H - B + 18}" text-anchor="middle">{c}</text>')
    out.append(f'<text x="{(L + W - R) / 2}" y="{H - 15}" text-anchor="middle">call-backs per day (about {rows[0]["per_day"]:,.0f} withdrawals per day)</text>')
    for k, pol in enumerate(POLICIES):
        pts = sorted((r["capacity"], r["share"]) for r in rows if r["policy"] == pol)
        out.append(f'<polyline fill="none" stroke="{colors[pol]}" stroke-width="2.5" points="'
                   + " ".join(f"{xs[c]:.1f},{y(v):.1f}" for c, v in pts) + '"/>')
        out.append(f'<rect x="{W - R + 15}" y="{T + 20 * k}" width="12" height="12" fill="{colors[pol]}"/>'
                   f'<text x="{W - R + 32}" y="{T + 20 * k + 10}">{pol}</text>')
    out.append(f'<text x="{W - R + 15}" y="{T + 100}" font-size="10" fill="#666">Modelled: scam rate, answer</text>'
               f'<text x="{W - R + 15}" y="{T + 114}" font-size="10" fill="#666">confirm rates, stop rates.</text>'
               f'<text x="{W - R + 15}" y="{T + 128}" font-size="10" fill="#666">Real: payments, amounts,</text>'
               f'<text x="{W - R + 15}" y="{T + 142}" font-size="10" fill="#666">order, Tether freezes.</text></svg>')
    path.write_text("\n".join(out))


_streams = {}


def _job(args):
    """One (rate, capacity, policy) cell; each worker process builds the streams once."""
    rate, cap, pol = args
    if rate not in _streams:
        _streams[rate] = stream(payments(), rate)
    s = _streams[rate]
    return {"rate": rate, "capacity": cap, "policy": pol, "per_day": len(s) / DAYS, **score(s, run(pol, s, cap))}


def main():
    from multiprocessing import Pool
    t0 = time.time()
    jobs = [(r, c, p) for r in SCAM_RATES for c in CAPACITIES for p in POLICIES]
    jobs.sort(key=lambda j: j[2] != "ladder")  # the slow ladder runs first
    rows = []
    with Pool(max(1, (os.cpu_count() or 2) - 1)) as pool:
        for row in pool.imap_unordered(_job, jobs):
            rows.append(row)
            if row["policy"] == "ladder":
                print(f"ladder rate {row['rate']:.1%} capacity {row['capacity']}: {row['share']:.0%} averted "
                      f"({len(rows)}/{len(jobs)}, {time.time() - t0:.0f}s)", flush=True)
    DOCS.mkdir(exist_ok=True)
    (DOCS / "result3.json").write_text(json.dumps(rows, indent=0))
    write_docs(rows)
    print(f"wrote docs/result3.json, docs/result3.md and docs/result3.svg in {time.time() - t0:.0f}s")


def write_docs(rows):
    """docs/result3.md and docs/result3.svg from the sweep's cells (also `python sweep.py docs`)."""
    head = 0.005
    svg_chart([r for r in rows if r["rate"] == head], head, DOCS / "result3.svg")
    lines = ["# Result 3: the ladder vs simpler policies at equal officer capacity", "",
             "Generated by `python sweep.py` (cells in `docs/result3.json`; `python sweep.py docs` rewrites this page from them). "
             "Chart: `docs/result3.svg` (scam rate 0.5%).", "",
             "Each cell: share and amount of scam USDT averted; legitimate payments held for a call-back; and, for the ladder, "
             "legitimate payments **left waiting at the question tier** (not released by the end: mostly payments to busy "
             "wallets that a misread answer flagged, while no call-back slot was free to clear them). That last figure is "
             "not the question rate: about 1 in 8 payments to volume-matched wallets gets a question (`docs/results.md`, #10).", "",
             "**Real:** payments of >= 10 USDT to the Jul-Oct 2026 test wallets (Tether-frozen = scam, comparison = legitimate), "
             "their amounts, senders and order, and Tether freezes. Payments are packed into "
             f"{DAYS} equal bank days so each officer-day carries a realistic load.", "",
             f"**Modelled (not measured):** scam rate (swept); coached victim confirms the script {P_CONFIRM:.0%}, legitimate "
             f"customer {P_FALSE:.0%}; scam stopped at final tier {STOP}; no after-the-fact customer reports. "
             f"Fixed threshold = first-time payee >= {FIXED_USDT:,} USDT. Officers call every hold left in a slot "
             f"at the end of its day and mark the wallet confirmed or cleared, correctly {P_OFFICER_RIGHT:.0%} of the time.", "",
             "**Read with care:**", "",
             "- Most legitimate payments here go to the volume-matched comparison wallets, which were chosen to look "
             "like frozen wallets in payment size. Real customer traffic has fewer large first-time payees and fewer "
             "very busy payees, so the legitimate friction here is likely overstated.",
             "- Only the ladder has a question tier, so 'left at question' has no counterpart in the baselines; part of "
             "the ladder's lead rests on the modelled stop rate for a question.",
             "- One random seed per cell: small differences between neighbouring capacities are noise.",
             "- Amounts are USDT (about S$1.3 each); none of this counts victims, only payments.", ""]
    for rate in SCAM_RATES:
        rs = [r for r in rows if r["rate"] == rate]
        lines += [f"## Scam rate {rate:.1%} ({rs[0]['scam_payments']:,} scam payments, {rs[0]['legit']:,} legitimate, "
                  f"about {rs[0]['per_day']:,.0f} withdrawals/day)", "",
                  "| Calls/day | " + " | ".join(POLICIES) + " |", "|---|" + "---|" * len(POLICIES)]
        for cap in CAPACITIES:
            cells = []
            for pol in POLICIES:
                r = next(x for x in rs if x["capacity"] == cap and x["policy"] == pol)
                cells.append(f"{r['share']:.0%} ({r['averted']:,.0f} USDT); {r['legit_held']:,} legit held"
                             + (f", {r['legit_questioned']:,} left at question" if r["legit_questioned"] else ""))
            lines.append(f"| {cap} | " + " | ".join(cells) + " |")
        lines.append("")
    (DOCS / "result3.md").write_text("\n".join(lines))


def _self_check():
    pays = payments()
    assert pays == sorted(pays, key=lambda p: (p["ts"], p["wallet"], p["customer"]))
    s = stream(pays, 0.005)[:6000]
    assert all(a["t"] <= b["t"] for a, b in zip(s, s[1:])), "packing keeps the real order"
    for cap in (0, 5):
        for pol in POLICIES:
            tiers = run(pol, s, cap)
            per_day = defaultdict(int)
            for p, t in zip(s, tiers):
                per_day[p["t"] // DAY] += t == "hold"
            assert max(per_day.values(), default=0) <= cap, (pol, cap, max(per_day.values()))
    print("self-check passed: order kept, no policy ever exceeds the day's call-backs")


if __name__ == "__main__":
    if sys.argv[1:] == ["check"]:
        _self_check()
    elif sys.argv[1:] == ["docs"]:
        write_docs(json.load(open(DOCS / "result3.json")))
    else:
        main()
