"""The decision engine: decide(withdrawal) -> tier + reasons, before the withdrawal is signed.

One deep module behind one seam (issue #1). Slice #3: release a payee this customer has paid
before, warn on a first-time payee, append every decision to the hash-chained log.
Later slices add payee-memory holds (#6), the question tier (#7) and capacity (#9).

The engine never reads the wall clock or the network: the clock, the wallet-history source
and payee memory are injected, so the same code serves the live API, the Result 2 replay and
the tests.

    python engine.py   # scenario self-check, on synthetic and on recorded snapshot wallets
"""
import gzip
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from decision_log import DecisionLog

ENGINE_VERSION = "c3-0.1"
TIERS = ("release", "warning", "question", "hold")
DATA = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class Withdrawal:
    customer_id: str
    wallet: str  # destination address, lowercase 0x...
    amount_usdt: float
    ts: int  # unix seconds: the moment before signing


@dataclass(frozen=True)
class Reason:
    signal: str  # e.g. "first_time_payee", "known_payee"
    source: str  # where the evidence came from
    kind: str  # "real" or "modelled"
    detail: str  # plain English, safe to show the customer or officer


@dataclass(frozen=True)
class Decision:
    tier: str
    reasons: tuple
    p_scam: float  # modelled until real signals land (#5, #6)
    expected_loss: float  # amount_usdt * p_scam; ranks the officer queue
    withdrawal: Withdrawal
    decided_at: int
    engine_version: str = ENGINE_VERSION


@dataclass
class Config:
    # Modelled, not measured: swept in Result 3 and labelled on every slide.
    base_rate: float = 0.005  # share of withdrawals that are scams (plan sweeps 0.1-1%)
    first_time_mult: float = 2.0  # first-time payees are riskier than average
    known_payee_mult: float = 0.1  # repeat payees much less so


class InMemoryMemory:
    """Payee memory for tests and the replay. #6 adds an SQLite store with the same methods."""

    def __init__(self):
        self.paid = {}  # (customer, wallet) -> first ts the customer paid it

    def paid_before(self, customer_id, wallet, now):
        ts = self.paid.get((customer_id, wallet))
        return ts is not None and ts < now

    def note_paid(self, customer_id, wallet, ts):
        self.paid.setdefault((customer_id, wallet), ts)


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
    def __init__(self, history, memory, clock, log, config=None):
        self.history, self.memory, self.clock, self.log = history, memory, clock, log
        self.config = config or Config()

    def decide(self, w, answer=None):
        now = self.clock()
        c = self.config
        if self.memory.paid_before(w.customer_id, w.wallet, now):
            tier, mult = "release", c.known_payee_mult
            reasons = [Reason("known_payee", "customer_history", "real",
                              "You have sent money to this wallet before.")]
        else:
            tier, mult = "warning", c.first_time_mult
            reasons = [Reason("first_time_payee", "customer_history", "real",
                              "You have never sent money to this wallet before.")]
        p = min(1.0, c.base_rate * mult)
        reasons.append(Reason("base_rate", "config", "modelled",
                              f"Assumed scam rate {c.base_rate:.1%} x {mult:g} for this payee type."))
        d = Decision(tier, tuple(reasons), p, w.amount_usdt * p, w, now)
        # Release and warning both let the payment go ahead, so the customer now knows this payee.
        if tier in ("release", "warning"):
            self.memory.note_paid(w.customer_id, w.wallet, w.ts)
        self.log.append({"inputs": {"withdrawal": asdict(w), "answer": answer}, "decision": to_dict(d)})
        return d

    def record(self, event):
        raise NotImplementedError("payee-memory events arrive in #6")


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
    with tempfile.TemporaryDirectory() as d:
        log_path = Path(d) / "decisions.jsonl"
        clock = FixedClock(100 * H)
        eng = Engine(history=lambda wallet, as_of: None, memory=InMemoryMemory(), clock=clock,
                     log=DecisionLog(log_path))
        # The engine must not touch the wall clock or the network.
        real = time.time, socket.socket, urllib.request.urlopen

        def boom(*a, **k):
            raise AssertionError("engine used the wall clock or network")
        time.time = socket.socket = urllib.request.urlopen = boom
        try:
            first = eng.decide(Withdrawal("alice", "0xscam", 5_000, clock.now))
            clock.now += H
            again = eng.decide(Withdrawal("alice", "0xscam", 5_000, clock.now))
            bob = eng.decide(Withdrawal("bob", "0xscam", 2_000, clock.now))
        finally:
            time.time, socket.socket, urllib.request.urlopen = real

        assert first.tier == "warning" and first.reasons[0].signal == "first_time_payee", first
        assert again.tier == "release" and again.reasons[0].signal == "known_payee", again
        assert bob.tier == "warning", "a first-time payee for bob, whatever alice did"
        assert first.expected_loss == 5_000 * 0.01 and again.p_scam < first.p_scam
        assert all(r.kind in ("real", "modelled") for x in (first, again, bob) for r in x.reasons)
        assert first.decided_at == 100 * H, "now comes from the injected clock"

        # Point-in-time: a payment noted at ts doesn't count for a decision at the same ts.
        mem = InMemoryMemory()
        mem.note_paid("carol", "0xw", 50)
        assert not mem.paid_before("carol", "0xw", 50) and mem.paid_before("carol", "0xw", 51)

        # Every decision is logged with its inputs and engine version, and the log verifies.
        entries = [json.loads(line) for line in log_path.read_text().splitlines()]
        assert [e["decision"]["tier"] for e in entries] == ["warning", "release", "warning"]
        assert entries[0]["inputs"]["withdrawal"]["customer_id"] == "alice"
        assert entries[0]["decision"]["engine_version"] == ENGINE_VERSION
        assert verify(log_path) is None
        lines = log_path.read_text().splitlines()
        tampered = json.loads(lines[1])
        tampered["decision"]["tier"] = "warning"
        log_path.write_text("\n".join([lines[0], json.dumps(tampered), lines[2]]) + "\n")
        assert verify(log_path) == 2, "editing a past decision is caught"

        # Recorded histories: replay one frozen test wallet's payments, one customer per payment.
        hist = RecordedHistories(("test_pos",))
        if hist.by_addr:
            h = next(h for h in hist.by_addr.values() if len(h["transfers"]) >= 3)
            me = h["address"]
            assert hist(me, h["transfers"][1]["ts"])["transfers"] == h["transfers"][:1], "cut before as_of"
            assert hist(me, 0)["freeze_ts"] is None, "the label never leaks"
            eng = Engine(hist, InMemoryMemory(), FixedClock(0), DecisionLog(Path(d) / "replay.jsonl"))
            pays = [t for t in h["transfers"] if t["to"] == me and t["from"] != me]
            for t in pays:
                eng.clock.now = t["ts"]
                dec = eng.decide(Withdrawal(t["from"], me, t["usdt"], t["ts"]))
                assert dec.tier in ("warning", "release")
            assert verify(Path(d) / "replay.jsonl") is None
            print(f"recorded-history replay passed: {len(pays)} payments to {me[:10]}...")
    print("self-check passed: first-time payee warned, repeat payee released, log verifies")


if __name__ == "__main__":
    _self_check()
