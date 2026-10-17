"""The decision engine: decide(withdrawal) -> tier + reasons, before the withdrawal is signed.

One deep module behind one seam (issue #1).
- #3: release a payee this customer has paid before, warn on a first-time payee, append every
  decision to the hash-chained log.
- #6: hold for a call-back when shared payee memory has evidence against the destination (a
  customer report, an officer's confirmation, a Tether freeze of the wallet). Holds beat
  everything else, so a scam wallet's 2nd payment is held, and each held attempt renews the
  report. Weak evidence (a Tether freeze of a wallet it has dealt with, B's model flag) warns
  but never holds on its own.
Later slices add the question tier (#7) and capacity (#9).

The engine never reads the wall clock or the network: the clock, the wallet-history source
and payee memory are injected, so the same code serves the live API, the Result 2 replay and
the tests.

    python engine.py   # scenario self-check, on synthetic and on recorded snapshot wallets
"""
import gzip
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from decision_log import DecisionLog
from features import features
from payee_memory import DAY, Freeze, OfficerOutcome, PayeeMemory, Report, load_freezes

ENGINE_VERSION = "c6-0.1"
TIERS = ("release", "warning", "question", "hold")
DATA = Path(__file__).resolve().parent / "data"
MIN_USDT = 10  # as in features.py: dust (e.g. address poisoning) never links a wallet to a freeze

InMemoryMemory = PayeeMemory  # the #3 name; PayeeMemory() defaults to an in-memory SQLite db


@dataclass(frozen=True)
class Withdrawal:
    customer_id: str
    wallet: str  # destination address, lowercase 0x...
    amount_usdt: float
    ts: int  # unix seconds: the moment before signing


@dataclass(frozen=True)
class Reason:
    signal: str  # e.g. "first_time_payee", "memory_hit", "counterparty_freeze"
    source: str  # where the evidence came from
    kind: str  # "real" or "modelled"
    detail: str  # plain English, safe to show the customer or officer


@dataclass(frozen=True)
class Decision:
    tier: str
    reasons: tuple
    p_scam: float  # signal-derived probability; the per-signal values are modelled (Config)
    expected_loss: float  # amount_usdt * p_scam; ranks the officer queue
    withdrawal: Withdrawal
    decided_at: int
    engine_version: str = ENGINE_VERSION


@dataclass
class Config:
    # Modelled, not measured: swept in Results 2-3 and labelled on every slide.
    base_rate: float = 0.005  # share of withdrawals that are scams (plan sweeps 0.1-1%)
    first_time_mult: float = 2.0  # first-time payees are riskier than average
    known_payee_mult: float = 0.1  # repeat payees much less so
    # P(scam) once a signal has fired; the strongest signal wins.
    p_signal: dict = None
    model_flag: float = 0.9  # B's model.score() at or above this escalates; set from the 1% false-alarm cut

    def __post_init__(self):
        self.p_signal = self.p_signal or {
            # hold signals
            "officer_confirmed": 0.95,
            "destination_freeze": 0.6,
            "memory_hit": 0.3,
            # weak signals: warn (a question once #7 lands), never hold on their own
            "counterparty_freeze": 0.02,
            "model_flag": 0.02,
        }


class RecordedHistories:
    """History source over the snapshot's histories/*.jsonl.gz, cut to transfers before as_of."""

    def __init__(self, groups=("test_pos", "test_neg", "test_negv")):
        self.by_addr = {}
        for g in groups:
            path = DATA / "histories" / f"{g}.jsonl.gz"
            if path.exists():
                for line in gzip.open(path, "rt"):
                    h = json.loads(line)
                    self.by_addr[h["address"]] = h

    def __call__(self, wallet, as_of):
        h = self.by_addr.get(wallet)
        if h is None:
            return None
        return {**h, "freeze_ts": None, "transfers": [t for t in h["transfers"] if t["ts"] < as_of]}


class Engine:
    def __init__(self, history, memory, clock, log, config=None, model=None, known_bad=frozenset()):
        """model: features dict -> P or None (B's model.score); optional, decisions work without it.
        known_bad: the static scam list for the model's touched_known_bad feature, as in training."""
        self.history, self.memory, self.clock, self.log = history, memory, clock, log
        self.config = config or Config()
        self.model, self.known_bad = model, known_bad

    def decide(self, w, answer=None):
        now = self.clock()
        c = self.config
        known = self.memory.paid_before(w.customer_id, w.wallet, now)
        payee = (Reason("known_payee", "customer_history", "real", "You have sent money to this wallet before.")
                 if known else
                 Reason("first_time_payee", "customer_history", "real", "You have never sent money to this wallet before."))
        evidence = self.memory.evidence(w.wallet, now)
        holds = [Reason(e.signal, e.source, e.kind, e.detail) for e in evidence]
        h = self.history(w.wallet, now)
        weak, frozen_cps = self._counterparty_freezes(w.wallet, h, now)
        info = self._model_signal(h, now, frozen_cps)
        weak += [r for r in info if r.signal == "model_flag"]
        info = [r for r in info if r.signal != "model_flag"]
        if holds:
            tier = "hold"
            top = max(holds, key=lambda r: c.p_signal[r.signal])
            p = c.p_signal[top.signal]
            reasons = holds + weak + [payee] + info + [Reason("p_signal", "config", "modelled",
                                                              f"Assumed scam probability {p:.0%} once '{top.signal}' fires.")]
        elif weak:
            # Weak evidence warns even a known payee; it never holds on its own (#6 replay: counterparty
            # freezes held 251 legitimate payments on 3 comparison wallets for 3 scam payments).
            tier = "warning"
            top = max(weak, key=lambda r: c.p_signal[r.signal])
            p = c.p_signal[top.signal]
            reasons = weak + [payee] + info + [Reason("p_signal", "config", "modelled",
                                                      f"Assumed scam probability {p:.0%} once '{top.signal}' fires.")]
        else:
            tier, mult = ("release", c.known_payee_mult) if known else ("warning", c.first_time_mult)
            p = min(1.0, c.base_rate * mult)
            reasons = [payee] + info + [Reason("base_rate", "config", "modelled",
                                               f"Assumed scam rate {c.base_rate:.1%} x {mult:g} for this payee type.")]
        d = Decision(tier, tuple(reasons), p, w.amount_usdt * p, w, now)
        if tier == "hold":
            # Another attempt to pay a reported wallet is itself evidence: renew the report so the hold
            # outlives one half-life (wallets collect for a median of 129 days). Kept per kind, so a
            # modelled report only ever renews modelled evidence. An officer's "cleared" ends it.
            for kind in sorted({e.kind for e in evidence if e.signal == "memory_hit"}):
                self.memory.add(Report(w.wallet, w.ts, source="held_payment", kind=kind, actor=w.customer_id))
        else:
            # Release and warning let the payment go ahead, so the customer now knows this payee.
            # A held payment hasn't gone anywhere yet.
            self.memory.note_paid(w.customer_id, w.wallet, w.ts)
        self.log.append({"inputs": {"withdrawal": asdict(w), "answer": answer}, "decision": to_dict(d)})
        return d

    def record(self, event):
        """Customer reports, officer outcomes and Tether freezes go into payee memory (and the log)."""
        self.memory.add(event)
        self.log.append({"event": type(event).__name__, **asdict(event), "engine_version": ENGINE_VERSION})

    def _counterparty_freezes(self, wallet, h, now):
        """([weak reason] if a wallet the destination exchanged >= 10 USDT with was frozen before now,
        {counterparty: freeze ts} for the model's features)."""
        if not h:
            return [], {}
        cps = {t["from"] for t in h["transfers"] if t["to"] == wallet and t["usdt"] >= MIN_USDT and t["ts"] < now}
        cps |= {t["to"] for t in h["transfers"] if t["from"] == wallet and t["usdt"] >= MIN_USDT and t["ts"] < now}
        cps.discard(wallet)
        all_frozen = self.memory.frozen_before(cps, now)
        since = self.memory.cleared_at(wallet, now) or -1
        frozen = {a: ts for a, ts in all_frozen.items() if ts > since}
        if not frozen:
            return [], all_frozen
        n, days = len(frozen), (now - max(frozen.values())) / DAY
        return [Reason("counterparty_freeze", "tether", "real",
                       f"{n} wallet{'s' * (n > 1)} this one exchanged USDT with {'were' if n > 1 else 'was'} "
                       f"later frozen by Tether, the latest {days:.0f} days ago.")], all_frozen

    def _model_signal(self, h, now, frozen_cps):
        """B's weak model (#5) as one tagged input: a model_flag reason at or above Config.model_flag,
        else an informational model_score reason. Nothing when there is no model, history or score."""
        if self.model is None or not h:
            return []
        s = self.model(features(h, now, self.known_bad, frozen_cps))
        if s is None:
            return []
        flag = s >= self.config.model_flag
        return [Reason("model_flag" if flag else "model_score", "model", "real",
                       f"Weak model signal: score {s:.2f}{' (flagged)' if flag else ''}; "
                       "AUC 0.57 against similar wallets, so it never holds on its own.")]


def to_dict(d):
    """JSON-able decision, for the log and the API."""
    out = asdict(d)
    out["reasons"] = [asdict(r) for r in d.reasons]
    return out


class FixedClock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def _self_check():
    import socket
    import tempfile
    import time
    import urllib.request

    from decision_log import verify

    H = 3600
    no_history = lambda wallet, as_of: None
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        # ---- #3: first-time payee warned, repeat payee released, logged ----
        clock = FixedClock(100 * H)
        eng = Engine(no_history, PayeeMemory(), clock, DecisionLog(d / "decisions.jsonl"))
        real = time.time, socket.socket, urllib.request.urlopen

        def boom(*a, **k):
            raise AssertionError("engine used the wall clock or network")
        time.time = socket.socket = urllib.request.urlopen = boom
        try:
            first = eng.decide(Withdrawal("alice", "0xw", 5_000, clock.now))
            clock.now += H
            again = eng.decide(Withdrawal("alice", "0xw", 5_000, clock.now))
            bob = eng.decide(Withdrawal("bob", "0xw", 2_000, clock.now))
            eng.record(Report("0xw", clock.now, actor="bob"))
        finally:
            time.time, socket.socket, urllib.request.urlopen = real

        assert first.tier == "warning" and first.reasons[0].signal == "first_time_payee", first
        assert again.tier == "release" and again.reasons[0].signal == "known_payee", again
        assert bob.tier == "warning", "a first-time payee for bob, whatever alice did"
        assert first.expected_loss == 5_000 * 0.01 and again.p_scam < first.p_scam
        assert first.decided_at == 100 * H, "now comes from the injected clock"
        entries = [json.loads(line) for line in (d / "decisions.jsonl").read_text().splitlines()]
        assert [e.get("decision", {}).get("tier", e.get("event")) for e in entries] == ["warning", "release", "warning", "Report"]
        assert entries[0]["decision"]["engine_version"] == ENGINE_VERSION
        assert verify(d / "decisions.jsonl") is None
        lines = (d / "decisions.jsonl").read_text().splitlines()
        tampered = json.loads(lines[1])
        tampered["decision"]["tier"] = "warning"
        (d / "decisions.jsonl").write_text("\n".join([lines[0], json.dumps(tampered)] + lines[2:]) + "\n")
        assert verify(d / "decisions.jsonl") == 2, "editing a past decision is caught"

        # ---- #6: shared payee memory and call-back hold ----
        def fresh(history=no_history, now=0):
            return Engine(history, PayeeMemory(), FixedClock(now), DecisionLog(d / f"e{time.monotonic_ns()}.jsonl"))

        def at(eng, now, who, wallet="0xscam", amount=1_000):
            eng.clock.now = now
            return eng.decide(Withdrawal(who, wallet, amount, now))

        # Customer B is held because of customer A's report, and A's own 2nd payment too.
        eng = fresh()
        assert at(eng, 1 * H, "mrs_tan", amount=20_000).tier == "warning"
        eng.record(Report("0xscam", 2 * H, actor="mrs_tan", note="caller said he was police"))
        held = at(eng, 3 * H, "mr_lim", amount=8_000)
        assert held.tier == "hold" and held.reasons[0].signal == "memory_hit", held
        assert held.reasons[0].source == "customer_report" and held.expected_loss == 8_000 * 0.3
        assert at(eng, 3 * H, "mrs_tan").tier == "hold", "a hold beats 'known payee'"
        assert not eng.memory.paid_before("mr_lim", "0xscam", 10 * H), "a held payment isn't 'paid'"
        assert at(eng, 3 * H, "someone", wallet="0xother").tier == "warning", "other wallets unaffected"

        # A report recorded after the decision time is never used.
        eng = fresh()
        eng.record(Report("0xscam", 10 * H))
        assert at(eng, 5 * H, "bob").tier == "warning"

        # Officer outcomes: cleared stops holds, confirmed pins with no decay.
        eng = fresh()
        eng.record(Report("0xscam", 1 * H))
        eng.record(OfficerOutcome("0xscam", "cleared", 2 * H, "officer_1"))
        assert at(eng, 3 * H, "bob").tier == "warning", "cleared"
        eng.record(OfficerOutcome("0xscam", "confirmed", 4 * H, "officer_1"))
        late = at(eng, 4 * H + 400 * DAY, "carol")
        assert late.tier == "hold" and late.reasons[0].signal == "officer_confirmed" and late.p_scam == 0.95

        # Decay: with no further attempts, one report holds for one half-life (7 days), then fades.
        eng = fresh()
        eng.record(Report("0xscam", 0))
        assert at(eng, int(7.1 * DAY), "carol").tier == "warning"
        eng = fresh()
        eng.record(Report("0xscam", 0))
        assert at(eng, int(6.9 * DAY), "bob").tier == "hold"

        # Renewal: each held attempt renews the report, so the hold lasts while victims keep paying.
        eng = fresh()
        eng.record(Report("0xscam", 0, actor="mrs_tan"))
        for day in (5, 10, 15, 20, 120):  # 120 is > 7 half-lives after day 20: faded by then
            dec = at(eng, day * DAY, f"victim_{day}")
            assert dec.tier == ("hold" if day < 120 else "warning"), (day, dec.tier)
        eng = fresh()
        eng.record(Report("0xscam", 0, kind="modelled"))
        at(eng, 5 * DAY, "v1")
        kinds = {e.kind for e in eng.memory.evidence("0xscam", 10 * DAY)}
        assert kinds == {"modelled"}, "a modelled report only renews modelled evidence"
        eng.record(OfficerOutcome("0xscam", "cleared", 11 * DAY))
        assert at(eng, 12 * DAY, "v2").tier == "warning", "cleared ends the renewal chain"

        # Tether freezes: of the wallet itself (hold), and of a wallet it exchanged >= 10 USDT with (weak: warn).
        tx = lambda ts, a, b, usdt: {"ts": ts, "from": a, "to": b, "usdt": usdt, "nonce": 1, "hash": f"{ts}{a}{b}"}
        hist = {"0xscam": {"address": "0xscam", "transfers": [
            tx(1 * H, "0xvictim1", "0xscam", 500), tx(2 * H, "0xscam", "0xmule", 450),
            tx(3 * H, "0xdust", "0xscam", 0.01), tx(50 * H, "0xlater", "0xscam", 900)]}}
        history = lambda wallet, as_of: (None if wallet not in hist else
                                         {**hist[wallet], "transfers": [t for t in hist[wallet]["transfers"] if t["ts"] < as_of]})
        eng = fresh(history)
        eng.memory.add_freezes([("0xmule", 20 * H), ("0xdust", 5 * H), ("0xlater", 6 * H)])
        assert at(eng, 10 * H, "bob").reasons[0].signal == "first_time_payee", "mule frozen later; dust and future senders don't count"
        cp = at(eng, 21 * H, "bob")
        assert cp.tier == "warning" and cp.reasons[0].signal == "counterparty_freeze" and cp.reasons[0].kind == "real", cp
        assert cp.p_scam == 0.02, "weak evidence, even for a known payee"
        eng.record(OfficerOutcome("0xscam", "cleared", 22 * H))
        assert at(eng, 23 * H, "bob").tier == "release", "an officer can clear a counterparty-freeze warning"
        eng.record(Freeze("0xscam", 30 * H))
        frz = at(eng, 31 * H, "erin")
        assert frz.tier == "hold" and frz.reasons[0].signal == "destination_freeze"

        # Weak model (#5) as one input: flags warn, scores inform, absence changes nothing.
        seen = []
        model = lambda f: seen.append(f) or score
        for score, tier, sig in ((0.95, "warning", "model_flag"), (0.3, "release", "model_score"), (None, "release", None)):
            eng = Engine(history, PayeeMemory(), FixedClock(10 * H), DecisionLog(d / f"m{score}.jsonl"), model=model)
            eng.memory.note_paid("bob", "0xscam", 1)
            dec = eng.decide(Withdrawal("bob", "0xscam", 100, 10 * H))
            assert dec.tier == tier and (sig is None) == all(not r.signal.startswith("model") for r in dec.reasons), (score, dec)
            assert all(r.signal != "model_flag" or r.kind == "real" for r in dec.reasons)
        assert seen[0]["n_pay_in"] == 1 and seen[0]["usd_in"] == 500, "model sees point-in-time features() only"
        eng = Engine(history, PayeeMemory(), FixedClock(10 * H), DecisionLog(d / "m_hold.jsonl"), model=lambda f: 0.99)
        eng.record(Report("0xscam", 1))
        assert eng.decide(Withdrawal("carol", "0xscam", 100, 10 * H)).tier == "hold", "a hold still beats a model flag"

        # Recorded histories with the real freeze list: holds come only from real evidence here.
        hist = RecordedHistories(("test_pos", "test_negv"))
        if hist.by_addr:
            h = next(h for h in hist.by_addr.values() if h["group"] == "test_pos" and len(h["transfers"]) >= 3)
            assert hist(h["address"], 0)["freeze_ts"] is None, "the label never leaks"
            eng = fresh(hist)
            eng.memory.add_freezes(load_freezes())
            count = {g: {"hold": 0, "counterparty_warning": 0, "payments": 0} for g in ("test_pos", "test_negv")}
            for g in count:
                for h in [h for h in hist.by_addr.values() if h["group"] == g][:25]:
                    me, end = h["address"], h["freeze_ts"] or float("inf")
                    for t in h["transfers"]:
                        if t["to"] == me and t["from"] != me and t["usdt"] >= MIN_USDT and t["ts"] < end:
                            dec = at(eng, t["ts"], t["from"], me, t["usdt"])
                            count[g]["hold"] += dec.tier == "hold"
                            count[g]["counterparty_warning"] += any(r.signal == "counterparty_freeze" for r in dec.reasons)
                            count[g]["payments"] += 1
                            assert all(r.kind == "real" for r in dec.reasons if r.signal not in ("p_signal", "base_rate"))
            assert all(c["hold"] == 0 for c in count.values()), "no reports: Tether freezes of others never hold"
            print("recorded-history replay (25 wallets each, Tether freezes only, no reports):", count)
    print("self-check passed: #3 release/warn/log and #6 shared memory, holds, outcomes, decay, freezes")


if __name__ == "__main__":
    _self_check()
