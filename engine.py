"""The decision engine: decide(withdrawal) -> tier + reasons, before the withdrawal is signed.

One deep module behind one seam (issue #1).
- #3: release a payee this customer has paid before, warn on a first-time payee, append every
  decision to the hash-chained log.
- #6: hold for a call-back when shared payee memory has evidence against the destination (a
  customer report, an officer's confirmation, a Tether freeze of the wallet). Holds beat
  everything else, so a scam wallet's 2nd payment is held, and each held attempt renews the
  report. Weak evidence (a Tether freeze of a wallet it has dealt with, B's model flag) warns
  but never holds on its own.
- #7: a first-time payee at or above Config.large_usdt, or weak evidence, gets one question
  (Granite via D's granite module, else a template). decide(w, answer) re-decides it: a
  confirming answer holds and warns every other customer paying the wallet; a clean one releases.
- #9: with Config.daily_capacity set, at most that many holds per day (SGT). When the day is
  full, a hold with a bigger expected loss takes the slot of the day's smallest hold, which
  becomes a question (returned as decision.bumped); otherwise the new one becomes a question.

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

ENGINE_VERSION = "c7-0.1"
TIERS = ("release", "warning", "question", "hold")
DATA = Path(__file__).resolve().parent / "data"
TEMPLATE_QUESTION = ("Real police, bank or government officers never ask you to move your savings to a 'safe' wallet. "
                     "In your own words, why are you sending this money, and did anyone ask you to?")
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
    detail: str  # plain English
    audience: str = "customer"  # "customer": fine to show the customer; "officer": why-card only


@dataclass(frozen=True)
class Decision:
    tier: str
    reasons: tuple
    p_scam: float  # signal-derived probability; the per-signal values are modelled (Config)
    expected_loss: float  # amount_usdt * p_scam; ranks the officer queue
    withdrawal: Withdrawal
    decided_at: int
    engine_version: str = ENGINE_VERSION
    question: str = None  # question tier only: what to ask the customer
    bumped: "Decision" = None  # #9: an earlier hold this one displaced, now a question; the app shows it


@dataclass
class Config:
    # Modelled, not measured: swept in Results 2-3 and labelled on every slide.
    base_rate: float = 0.005  # share of withdrawals that are scams (plan sweeps 0.1-1%)
    first_time_mult: float = 2.0  # first-time payees are riskier than average
    known_payee_mult: float = 0.1  # repeat payees much less so
    # P(scam) once a signal has fired; the strongest signal wins.
    p_signal: dict = None
    # B's model.score() at or above this asks a question. 0.78 flags 1% of payments to comparison wallets
    # and 16.8% of payments to frozen ones (24,522 test payments, scored in the LinuxONE lab container).
    model_flag: float = 0.78
    large_usdt: float = 1000  # a first-time payee at or above this gets a question, not a warning
    daily_capacity: int = None  # officer call-backs per day; None = unlimited
    day_offset_s: int = 8 * 3600  # days run midnight to midnight Singapore time

    def __post_init__(self):
        self.p_signal = {**DEFAULT_P_SIGNAL, **(self.p_signal or {})}  # override some, keep the rest


DEFAULT_P_SIGNAL = {
    # hold signals
    "officer_confirmed": 0.95,
    "destination_freeze": 0.6,
    "answer_confirms_script": 0.5,
    "memory_hit": 0.3,
    # question signals: ask, never hold on their own
    "counterparty_freeze": 0.02,
    "model_flag": 0.02,
    "large_new_payee": 0.02,
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
    def __init__(self, history, memory, clock, log, config=None, model=None, known_bad=frozenset(), classifier=None):
        """model: features dict -> P or None (B's model.score); optional, decisions work without it.
        known_bad: the static scam list for the model's touched_known_bad feature, as in training.
        classifier: D's granite module, or anything with ask(withdrawal, reasons) -> str and
        classify(answer) -> {"scam_type", "confirms_script", "source"[, "kind"]}. Without one the
        question is the template and answers can't be decided."""
        self.history, self.memory, self.clock, self.log = history, memory, clock, log
        self.config = config or Config()
        self.model, self.known_bad, self.classifier = model, known_bad, classifier
        self.holds_by_day = {}  # day -> [Decision], the holds currently using that day's call-back slots

    def decide(self, w, answer=None, answer_kind=None):
        """Decide a withdrawal. Call again with the customer's `answer` to re-decide a question.
        answer_kind="modelled" marks a simulated answer (demo, replay) whatever the classifier says."""
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
        if not known and w.amount_usdt >= c.large_usdt:
            weak.append(Reason("large_new_payee", "customer_history", "real",
                               f"This is a large payment ({w.amount_usdt:,.0f} USDT) to a wallet you have never paid before."))
        cls = None
        if answer is not None:
            if self.classifier is None:
                raise ValueError("an answer needs a classifier (D's granite module or a stub)")
            cls = dict(self.classifier.classify(answer))
            if answer_kind:
                cls["kind"] = answer_kind
            kind = cls.get("kind", "real")  # the replay's simulated answers say "modelled"
            if cls["confirms_script"]:
                holds.append(Reason("answer_confirms_script", cls["source"], kind,
                                    f"Your answer matches a known scam pattern ({cls['scam_type'].replace('_', ' ')})."))
            else:
                info.append(Reason("answer_ok", cls["source"], kind, "Your answer doesn't match any scam pattern we know."))
        question = None
        if holds:
            tier, top = "hold", max(holds, key=lambda r: c.p_signal[r.signal])
        elif cls is not None:
            tier, top = "release", None  # a clean answer releases, weak signals and all
        elif weak:
            # Unusual or weakly flagged: one question. Weak evidence never holds on its own (#6 replay:
            # counterparty freezes held 251 legitimate payments on 3 comparison wallets for 3 scam payments).
            tier, top = "question", max(weak, key=lambda r: c.p_signal[r.signal])
        else:
            tier, top = ("release" if known else "warning"), None
        if top is not None:
            p = c.p_signal[top.signal]
            prior = Reason("p_signal", "config", "modelled", f"Assumed scam probability {p:.0%} once '{top.signal}' fires.", "officer")
        else:
            mult = c.known_payee_mult if known else c.first_time_mult
            p = min(1.0, c.base_rate * mult)
            prior = Reason("base_rate", "config", "modelled", f"Assumed scam rate {c.base_rate:.1%} x {mult:g} for this payee type.", "officer")
        reasons = holds + weak + [payee] + info + [prior]
        bumped = None
        if tier == "hold" and c.daily_capacity is not None:
            day = int((now + c.day_offset_s) // DAY)
            today = self.holds_by_day.setdefault(day, [])
            if len(today) >= c.daily_capacity:
                smallest = min(today, key=lambda x: x.expected_loss) if today else None
                if smallest is not None and w.amount_usdt * p > smallest.expected_loss:
                    today.remove(smallest)
                    bumped = self._to_question(smallest, now, "A payment at higher risk needed today's last call-back slot.")
                else:
                    tier = "question"
                    reasons.append(Reason("capacity_full", "officer_capacity", "real",
                                          "Our call-back team is fully booked today, so we need to ask you one question instead."))
        if tier == "question":
            question = self._ask(w, reasons)
        d = Decision(tier, tuple(reasons), p, w.amount_usdt * p, w, now, question=question, bumped=bumped)
        if tier == "hold" and c.daily_capacity is not None:
            self.holds_by_day[int((now + c.day_offset_s) // DAY)].append(d)
        if tier in ("hold", "question") and holds:
            # Another attempt to pay a reported wallet is itself evidence: renew the report so the hold
            # outlives one half-life (wallets collect for a median of 129 days). Kept per kind, so a
            # modelled report only ever renews modelled evidence. An officer's "cleared" ends it.
            for kind in sorted({e.kind for e in evidence if e.signal == "memory_hit"}):
                self.memory.add(Report(w.wallet, w.ts, source="held_payment", kind=kind, actor=w.customer_id))
            # A confirming answer warns every other customer paying this wallet.
            if cls is not None and cls["confirms_script"]:
                self.memory.add(Report(w.wallet, w.ts, source="customer_answer", kind=cls.get("kind", "real"),
                                       actor=w.customer_id, note=cls["scam_type"]))
        elif tier in ("release", "warning"):
            # These let the payment go ahead, so the customer now knows this payee. A held payment or
            # an unanswered question hasn't gone anywhere yet.
            self.memory.note_paid(w.customer_id, w.wallet, w.ts)
        self.log.append({"inputs": {"withdrawal": asdict(w), "answer": answer, "classified": cls},
                         "decision": to_dict(d)})
        return d

    def _to_question(self, held, now, why):
        """A hold that lost its call-back slot: same evidence, asked one question instead."""
        reasons = held.reasons + (Reason("capacity_bumped", "officer_capacity", "real",
                                         "Our call-back team is fully booked today, so we need to ask you one question instead. "
                                         + why, "customer"),)
        q = Decision("question", reasons, held.p_scam, held.expected_loss, held.withdrawal, now,
                     question=self._ask(held.withdrawal, list(reasons)))
        self.log.append({"inputs": {"withdrawal": asdict(held.withdrawal), "bumped_from": "hold"}, "decision": to_dict(q)})
        return q

    def _ask(self, w, reasons):
        if self.classifier is not None:
            try:
                q = self.classifier.ask({"customer": w.customer_id, "wallet": w.wallet, "amount": w.amount_usdt, "time": w.ts},
                                        [{"signal": r.signal, "text": r.detail, "source": r.source, "kind": r.kind}
                                         for r in reasons if r.audience == "customer"])
                if q:
                    return q
            except Exception:  # Granite trouble must never break a decision
                pass
        return TEMPLATE_QUESTION

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
                       "AUC 0.57 against similar wallets, so it never holds on its own.", "officer")]


def to_dict(d):
    """JSON-able decision, for the log and the API. customer_reasons is what the customer page may show;
    reasons (with audience and real/modelled tags) is for the officer's why-card."""
    out = asdict(d)
    out["reasons"] = [asdict(r) for r in d.reasons]
    out["customer_reasons"] = [r.detail for r in d.reasons if r.audience == "customer"]
    out["bumped"] = to_dict(d.bumped) if d.bumped else None
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
            first = eng.decide(Withdrawal("alice", "0xw", 500, clock.now))
            clock.now += H
            again = eng.decide(Withdrawal("alice", "0xw", 5_000, clock.now))
            bob = eng.decide(Withdrawal("bob", "0xw", 200, clock.now))
            eng.record(Report("0xw", clock.now, actor="bob"))
        finally:
            time.time, socket.socket, urllib.request.urlopen = real

        assert first.tier == "warning" and first.reasons[0].signal == "first_time_payee", first
        assert again.tier == "release" and again.reasons[0].signal == "known_payee", again
        assert bob.tier == "warning", "a first-time payee for bob, whatever alice did"
        assert first.expected_loss == 500 * 0.01 and again.p_scam < first.p_scam
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

        def at(eng, now, who, wallet="0xscam", amount=500):
            eng.clock.now = now
            return eng.decide(Withdrawal(who, wallet, amount, now))

        # Customer B is held because of customer A's report, and A's own 2nd payment too.
        eng = fresh()
        assert at(eng, 1 * H, "mrs_tan", amount=900).tier == "warning"
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
        assert cp.tier == "question" and cp.reasons[0].signal == "counterparty_freeze" and cp.reasons[0].kind == "real", cp
        assert cp.p_scam == 0.02, "weak evidence, even for a known payee"
        eng.record(OfficerOutcome("0xscam", "cleared", 22 * H))
        assert at(eng, 23 * H, "bob").tier == "release", "an officer can clear a counterparty-freeze question"
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
            assert dec.tier == {"warning": "question"}.get(tier, tier) and (sig is None) == all(not r.signal.startswith("model") for r in dec.reasons), (score, dec)
            assert all(r.signal != "model_flag" or r.kind == "real" for r in dec.reasons)
        assert seen[0]["n_pay_in"] == 1 and seen[0]["usd_in"] == 500, "model sees point-in-time features() only"
        eng = Engine(history, PayeeMemory(), FixedClock(10 * H), DecisionLog(d / "m_hold.jsonl"), model=lambda f: 0.99)
        eng.record(Report("0xscam", 1))
        assert eng.decide(Withdrawal("carol", "0xscam", 100, 10 * H)).tier == "hold", "a hold still beats a model flag"

        # Review fixes: customer-safe text, partial p_signal overrides.
        dec = held  # hold from memory, with modelled priors attached
        shown = to_dict(dec)["customer_reasons"]
        assert shown and not any("Assumed" in t or "model" in t.lower() for t in shown), shown
        assert any(r["audience"] == "officer" for r in to_dict(dec)["reasons"]), "officer still sees the priors"
        assert Config(p_signal={"memory_hit": 0.4}).p_signal["officer_confirmed"] == 0.95, "partial override keeps defaults"
        assert Config(p_signal={"memory_hit": 0.4}).p_signal["memory_hit"] == 0.4

        # ---- #7: question tier ----
        class StubClassifier:  # stands in for D's granite module
            def __init__(self, kind="real", broken=False):
                self.kind, self.broken, self.asked = kind, broken, []

            def ask(self, withdrawal, reasons):
                if self.broken:
                    raise ConnectionError("Granite down")
                self.asked.append((withdrawal, reasons))
                return "Did someone on a call tell you to send this?"

            def classify(self, answer):
                yes = "officer" in answer.lower()
                return {"scam_type": "government_impersonation" if yes else "none", "confirms_script": yes,
                        "source": "stub", "kind": self.kind}

        def asking(cls=None):
            return Engine(no_history, PayeeMemory(), FixedClock(0), DecisionLog(d / f"q{time.monotonic_ns()}.jsonl"),
                          classifier=cls or StubClassifier())

        # A large payment to a new payee gets one question; small ones a warning; repeat payees release.
        eng = asking()
        eng.clock.now = 1 * H
        q = eng.decide(Withdrawal("mrs_tan", "0xscam", 20_000, 1 * H))
        assert q.tier == "question" and q.question == "Did someone on a call tell you to send this?", q
        assert q.reasons[0].signal == "large_new_payee" and q.expected_loss == 20_000 * 0.02
        w_sent, r_sent = eng.classifier.asked[0]
        assert w_sent["amount"] == 20_000 and all("text" in r for r in r_sent), "granite.ask gets D's dict shape"
        assert not any(r["signal"] in ("p_signal", "base_rate") for r in r_sent), "no modelled priors in the prompt"
        assert not eng.memory.paid_before("mrs_tan", "0xscam", 2 * H), "an unanswered question hasn't paid"
        assert at(eng, 1 * H, "small", amount=999).tier == "warning"

        # A confirming answer holds and warns every other customer paying the wallet.
        coached = "The police officer said my account is linked to a crime"
        held = eng.decide(Withdrawal("mrs_tan", "0xscam", 20_000, 1 * H), answer=coached)
        assert held.tier == "hold" and held.reasons[0].signal == "answer_confirms_script" and held.p_scam == 0.5, held
        assert "government impersonation" in held.reasons[0].detail and held.reasons[0].kind == "real"
        nxt = at(eng, 2 * H, "mr_lim", amount=50)
        assert nxt.tier == "hold" and nxt.reasons[0].signal == "memory_hit" and nxt.reasons[0].source == "customer_answer", nxt

        # A clean answer releases, and the customer then knows the payee.
        eng = asking()
        eng.clock.now = 1 * H
        assert eng.decide(Withdrawal("bob", "0xw", 5_000, 1 * H)).tier == "question"
        ok = eng.decide(Withdrawal("bob", "0xw", 5_000, 1 * H), answer="Paying my own exchange account")
        assert ok.tier == "release" and any(r.signal == "answer_ok" for r in ok.reasons), ok
        assert at(eng, 2 * H, "bob", "0xw", 5_000).tier == "release" and not eng.memory.evidence("0xw", 3 * H)

        # A clean answer never overrides a hold that memory already had.
        eng = asking()
        eng.record(Report("0xscam", 0))
        eng.clock.now = 1 * H
        assert eng.decide(Withdrawal("bob", "0xscam", 50, 1 * H), answer="It's for my nephew").tier == "hold"

        # Granite down: the template question. No classifier: answers can't be decided.
        eng = asking(StubClassifier(broken=True))
        assert at(eng, 1 * H, "bob", amount=5_000).question == TEMPLATE_QUESTION
        eng = Engine(no_history, PayeeMemory(), FixedClock(1 * H), DecisionLog(d / "nocls.jsonl"))
        assert eng.decide(Withdrawal("bob", "0xw", 5_000, 1 * H)).question == TEMPLATE_QUESTION
        try:
            eng.decide(Withdrawal("bob", "0xw", 5_000, 1 * H), answer="hi")
            raise AssertionError("an answer without a classifier must fail loudly")
        except ValueError:
            pass

        # The caller can mark a simulated answer as modelled (the demo's coached customer 1).
        eng = asking()
        eng.clock.now = 1 * H
        demo = eng.decide(Withdrawal("customer-1", "0xscam", 300, 1 * H), answer=coached, answer_kind="modelled")
        assert demo.tier == "hold" and demo.reasons[0].kind == "modelled"
        assert {e.kind for e in eng.memory.evidence("0xscam", 2 * H)} == {"modelled"}

        # Simulated (modelled) answers stay modelled all the way into payee memory.
        eng = asking(StubClassifier(kind="modelled"))
        eng.clock.now = 1 * H
        eng.decide(Withdrawal("v1", "0xscam", 5_000, 1 * H), answer=coached)
        assert {e.kind for e in eng.memory.evidence("0xscam", 2 * H)} == {"modelled"}
        entry = json.loads(eng.log.path.read_text().splitlines()[-1])
        assert entry["inputs"]["classified"]["confirms_script"] is True, "the log keeps what the classifier said"

        # ---- #9: daily officer capacity ----
        eng = Engine(no_history, PayeeMemory(), FixedClock(0), DecisionLog(d / "cap.jsonl"),
                     config=Config(daily_capacity=2))
        for wal in ("0xa", "0xb", "0xc", "0xd", "0xe"):
            eng.record(Report(wal, 0))
        noon = 4 * H  # 12:00 SGT on day 0
        h1 = at(eng, noon, "c1", "0xa", 1_000)   # expected loss 300
        h2 = at(eng, noon, "c2", "0xb", 100)     # 30, the day's smallest
        assert h1.tier == h2.tier == "hold"
        big = at(eng, noon, "c3", "0xc", 3_000)  # 900: takes c2's slot
        assert big.tier == "hold" and big.bumped is not None and big.bumped.withdrawal.customer_id == "c2", big
        assert big.bumped.tier == "question" and big.bumped.question, "the bumped customer is asked instead"
        assert any(r.signal == "capacity_bumped" for r in big.bumped.reasons)
        assert to_dict(big)["bumped"]["tier"] == "question" and to_dict(h1)["bumped"] is None
        small = at(eng, noon, "c4", "0xd", 50)   # 15: too small to bump anyone
        assert small.tier == "question" and small.bumped is None
        assert any(r.signal == "capacity_full" for r in small.reasons) and small.question
        assert eng.memory.evidence("0xd", noon + H), "over capacity, the wallet stays flagged for everyone"
        assert not eng.memory.paid_before("c4", "0xd", noon + H), "and the payment hasn't gone"
        assert sorted(x.withdrawal.customer_id for x in eng.holds_by_day[0]) == ["c1", "c3"]
        assert at(eng, noon + DAY, "c5", "0xe", 10).tier == "hold", "a new SGT day has fresh slots"
        assert at(eng, 16 * H - 1, "c6", "0xe", 10).tier == "question", "23:59 SGT is still day 0"
        assert verify(eng.log.path) is None
        assert fresh().config.daily_capacity is None, "unlimited unless configured"

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
    print("self-check passed: #3 release/warn/log, #6 shared memory/holds/renewal/freezes/model, #7 question tier, #9 capacity")


if __name__ == "__main__":
    _self_check()
