"""Shared payee memory (issue #6): what the institution knows about each destination wallet.

Keyed by destination wallet and shared across customers, so customer A's report protects
customer B. SQLite-backed (":memory:" for tests and the replay, a file on the VM). Every query
takes `now` and only sees events from before it, so the replay can load all of Tether's freezes
up front without hindsight.

Evidence about a wallet:
- Customer reports decay with a half-life (default 7 days; the build plan's 6 h was too short
  for wallets that collect for ~4 months). One fresh report is enough to hold.
- An officer's "confirmed" pins the wallet with no decay; "cleared" drops everything before it.
  The latest officer outcome wins. Outcomes carry a real/modelled kind (a scripted demo or replay
  officer is modelled) and the reason code the officer picked; outcome_for() maps the officer
  console's decision + reason to "confirmed", "cleared" or nothing.
- Tether freezes of the wallet itself never decay (they are facts). Counterparty freezes are
  looked up by the engine through frozen_before().

    python payee_memory.py   # self-check
"""
import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
DAY = 86400


@dataclass(frozen=True)
class Report:
    """A warning about a wallet: a customer report now; a confirming answer (#7) or model flag later."""
    wallet: str
    ts: int
    source: str = "customer_report"
    kind: str = "real"  # the Result 2 replay records simulated reports as "modelled"
    actor: str = ""  # customer id, officer id or model name
    note: str = ""


@dataclass(frozen=True)
class OfficerOutcome:
    wallet: str
    outcome: str  # "cleared" or "confirmed"
    ts: int
    officer_id: str = ""
    kind: str = "real"  # "modelled" for a scripted officer (demo, replay)
    reason: str = ""  # a REASON_CODES key, from the officer console


# The officer console's reason codes (UI v2 wireframe), in display order.
REASON_CODES = {
    "confirmed_impersonation": "Confirmed scam: police or official impersonation",
    "confirmed_investment_romance": "Confirmed scam: investment or romance",
    "unsure_cancelled": "Customer unsure, cancelled to be safe",
    "genuine_known_recipient": "Genuine payment: customer knows the recipient",
    "genuine_own_wallet": "Genuine payment: customer's own wallet",
    "other": "Other (note required)",
}
DECISIONS = ("cancel", "release", "keep")


def outcome_for(decision, reason):
    """What an officer's decision on one payment tells payee memory about the wallet:
    "confirmed" (pins it for every customer), "cleared" (ends its holds) or None (this payment only).
    Raises ValueError on unknown values and on contradictions such as releasing a confirmed scam."""
    if decision not in DECISIONS:
        raise ValueError(f"unknown decision {decision!r}")
    if reason not in REASON_CODES:
        raise ValueError(f"unknown reason {reason!r}")
    scam, genuine = reason.startswith("confirmed_"), reason.startswith("genuine_")
    if decision == "release" and scam:
        raise ValueError("can't release a payment with a confirmed-scam reason")
    if decision == "cancel" and genuine:
        raise ValueError("a genuine payment is released or kept, not cancelled")
    if decision == "cancel" and scam:
        return "confirmed"
    if decision == "release" and genuine:
        return "cleared"
    return None  # unsure, other, keep on hold, or a release without a genuine reason: no change to the wallet


@dataclass(frozen=True)
class Freeze:
    """Tether added this wallet to the USDT blacklist at ts."""
    wallet: str
    ts: int


@dataclass(frozen=True)
class Evidence:
    signal: str  # "memory_hit", "officer_confirmed", "destination_freeze"
    source: str
    kind: str
    detail: str
    strength: float  # decayed weight of the reports, or 1.0 for facts


class PayeeMemory:
    def __init__(self, path=":memory:", half_life_s=7 * DAY, hold_threshold=0.5):
        self.half_life_s, self.hold_threshold = half_life_s, hold_threshold
        # The app may create memory on one thread and serve from another (uvicorn workers, test
        # clients). It calls the engine from one thread at a time, so sharing the connection is safe.
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS paid (customer TEXT, wallet TEXT, ts INTEGER, PRIMARY KEY (customer, wallet));
            CREATE TABLE IF NOT EXISTS reports (wallet TEXT, ts INTEGER, source TEXT, kind TEXT, actor TEXT, note TEXT);
            CREATE TABLE IF NOT EXISTS outcomes (wallet TEXT, ts INTEGER, outcome TEXT, officer TEXT,
                                                 kind TEXT DEFAULT 'real', reason TEXT DEFAULT '');
            CREATE TABLE IF NOT EXISTS freezes (wallet TEXT PRIMARY KEY, ts INTEGER);
            CREATE INDEX IF NOT EXISTS reports_wallet ON reports (wallet, ts);
            CREATE INDEX IF NOT EXISTS outcomes_wallet ON outcomes (wallet, ts);
        """)
        cols = {row[1] for row in self.db.execute("PRAGMA table_info(outcomes)")}
        for col in ("kind TEXT DEFAULT 'real'", "reason TEXT DEFAULT ''"):  # files made before outcomes had them
            if col.split()[0] not in cols:
                self.db.execute(f"ALTER TABLE outcomes ADD COLUMN {col}")

    # --- customer's own payees (#3) ---
    def paid_before(self, customer_id, wallet, now):
        row = self.db.execute("SELECT ts FROM paid WHERE customer = ? AND wallet = ?", (customer_id, wallet)).fetchone()
        return row is not None and row[0] < now

    def note_paid(self, customer_id, wallet, ts):
        self.db.execute("INSERT OR IGNORE INTO paid VALUES (?, ?, ?)", (customer_id, wallet, ts))
        self.db.commit()

    # --- events ---
    def add(self, event):
        if isinstance(event, Report):
            self.db.execute("INSERT INTO reports VALUES (?, ?, ?, ?, ?, ?)",
                            (event.wallet, event.ts, event.source, event.kind, event.actor, event.note))
        elif isinstance(event, OfficerOutcome):
            if event.outcome not in ("cleared", "confirmed"):
                raise ValueError(f"unknown officer outcome {event.outcome!r}")
            if event.reason and event.reason not in REASON_CODES:
                raise ValueError(f"unknown reason {event.reason!r}")
            self.db.execute("INSERT INTO outcomes (wallet, ts, outcome, officer, kind, reason) VALUES (?, ?, ?, ?, ?, ?)",
                            (event.wallet, event.ts, event.outcome, event.officer_id, event.kind, event.reason))
        elif isinstance(event, Freeze):  # earliest freeze per wallet, as in snapshot.py
            self.db.execute("INSERT INTO freezes VALUES (?, ?) ON CONFLICT (wallet) DO UPDATE "
                            "SET ts = min(ts, excluded.ts)", (event.wallet, event.ts))
        else:
            raise TypeError(f"unknown event {event!r}")
        self.db.commit()

    def add_freezes(self, rows):
        """Bulk-load (wallet, ts) freezes, e.g. from load_freezes()."""
        self.db.executemany("INSERT INTO freezes VALUES (?, ?) ON CONFLICT (wallet) DO UPDATE "
                            "SET ts = min(ts, excluded.ts)", rows)
        self.db.commit()

    # --- queries (point-in-time) ---
    def cleared_at(self, wallet, now):
        """ts of the latest 'cleared' if it is the latest outcome before now, else None."""
        row = self.db.execute("SELECT ts, outcome FROM outcomes WHERE wallet = ? AND ts < ? "
                              "ORDER BY ts DESC, rowid DESC LIMIT 1", (wallet, now)).fetchone()
        return row[0] if row and row[1] == "cleared" else None

    def evidence(self, wallet, now):
        """Evidence strong enough to hold a withdrawal to `wallet` at `now`."""
        out = []
        last = self.db.execute("SELECT ts, outcome, officer, kind FROM outcomes WHERE wallet = ? AND ts < ? "
                               "ORDER BY ts DESC, rowid DESC LIMIT 1", (wallet, now)).fetchone()
        if last and last[1] == "confirmed":
            out.append(Evidence("officer_confirmed", "officer", last[3],
                                "A fraud officer confirmed this wallet as a scam.", 1.0))
        since = last[0] if last and last[1] == "cleared" else -1
        # Reports older than 20 half-lives weigh < 1e-6 each, so they can't decide a hold; skipping them
        # keeps busy wallets (one renewal per held attempt) fast.
        since = max(since, now - 20 * self.half_life_s)
        rows = self.db.execute("SELECT ts, source, kind FROM reports WHERE wallet = ? AND ts < ? AND ts > ?",
                               (wallet, now, since)).fetchall()
        for kind in ("real", "modelled"):  # never mix real and modelled evidence in one reason
            mine = [(ts, src) for ts, src, k in rows if k == kind]
            strength = sum(0.5 ** ((now - ts) / self.half_life_s) for ts, _ in mine)
            if mine and strength >= self.hold_threshold:
                days = (now - max(ts for ts, _ in mine)) / DAY
                n = len(mine)
                out.append(Evidence("memory_hit", ",".join(sorted({s for _, s in mine})), kind,
                                    f"{n} earlier warning{'s' * (n > 1)} about this wallet, "
                                    f"the latest {days:.1f} days ago.", round(strength, 3)))
        frozen = self.frozen_before([wallet], now)
        if wallet in frozen and frozen[wallet] > since:
            out.append(Evidence("destination_freeze", "tether", "real",
                                "Tether has frozen this wallet's USDT.", 1.0))
        return out

    def frozen_before(self, wallets, now):
        """{wallet: freeze ts} for wallets Tether froze before now."""
        wallets = list(set(wallets))
        out = {}
        for i in range(0, len(wallets), 500):  # stay under SQLite's variable limit
            chunk = wallets[i:i + 500]
            q = f"SELECT wallet, ts FROM freezes WHERE ts < ? AND wallet IN ({','.join('?' * len(chunk))})"
            out.update(self.db.execute(q, (now, *chunk)).fetchall())
        return out


def load_freezes(path=DATA / "freezes.csv"):
    """(wallet, ts) for every Tether freeze, minus OFAC (sanctions stay with existing controls)."""
    return [(r["address"], int(r["freeze_ts"])) for r in csv.DictReader(open(path)) if r["ofac"] != "1"]


def _self_check():
    import tempfile
    H = 3600
    m = PayeeMemory()
    m.add(Report("0xw", 10 * H, actor="alice"))
    assert m.evidence("0xw", 10 * H) == [], "a report at now is not before now"
    [e] = m.evidence("0xw", 11 * H)
    assert e.signal == "memory_hit" and e.kind == "real" and e.strength > 0.99, e
    assert m.evidence("0xw", 10 * H + int(6.9 * DAY)), "one report still holds just under a half-life"
    assert not m.evidence("0xw", 10 * H + int(7.1 * DAY)), "and fades just after it"
    m.add(Report("0xw", 10 * H + 6 * DAY))
    assert m.evidence("0xw", 10 * H + 10 * DAY), "a second report reinforces it"

    m.add(OfficerOutcome("0xw", "cleared", 20 * DAY))
    assert not m.evidence("0xw", 20 * DAY + 1), "cleared drops earlier reports"
    m.add(Report("0xw", 21 * DAY))
    assert m.evidence("0xw", 21 * DAY + 1), "a new report after clearing counts again"
    m.add(OfficerOutcome("0xw", "confirmed", 22 * DAY))
    assert any(e.signal == "officer_confirmed" for e in m.evidence("0xw", 900 * DAY)), "confirmed never decays"
    assert not any(e.signal == "officer_confirmed" for e in m.evidence("0xw", 22 * DAY)), "not before it happened"

    m.add(Report("0xsim", 0, kind="modelled"))
    m.add(Report("0xsim", 0, kind="real"))
    assert sorted(e.kind for e in m.evidence("0xsim", 1)) == ["modelled", "real"], "kept apart"

    m.add(Freeze("0xf", 100))
    m.add(Freeze("0xf", 50))
    assert m.frozen_before(["0xf", "0xnope"], 51) == {"0xf": 50}, "earliest freeze, before now only"
    assert m.frozen_before(["0xf"], 50) == {}
    assert [e.signal for e in m.evidence("0xf", 51)] == ["destination_freeze"]
    m.add(OfficerOutcome("0xf", "cleared", 60))
    assert m.evidence("0xf", 61) == [], "an officer can clear a frozen wallet too"

    m.add(OfficerOutcome("0xdemo", "confirmed", 5, "demo officer", kind="modelled", reason="confirmed_impersonation"))
    [e] = m.evidence("0xdemo", 6)
    assert e.signal == "officer_confirmed" and e.kind == "modelled", "a scripted officer stays modelled"
    assert m.evidence("0xw", 900 * DAY)[0].kind == "real", "officers are real by default"
    try:
        m.add(OfficerOutcome("0xdemo", "confirmed", 7, reason="made_up"))
        raise AssertionError("unknown reason accepted")
    except ValueError:
        pass

    assert outcome_for("cancel", "confirmed_impersonation") == "confirmed"
    assert outcome_for("cancel", "confirmed_investment_romance") == "confirmed"
    assert outcome_for("release", "genuine_known_recipient") == "cleared"
    assert outcome_for("release", "genuine_own_wallet") == "cleared"
    assert outcome_for("cancel", "unsure_cancelled") is None, "unsure cancels this payment only"
    assert outcome_for("cancel", "other") is None and outcome_for("release", "other") is None
    assert all(outcome_for("keep", r) is None for r in REASON_CODES), "keep on hold changes nothing"
    for bad in (("release", "confirmed_impersonation"), ("cancel", "genuine_own_wallet"),
                ("approve", "other"), ("cancel", "nope")):
        try:
            outcome_for(*bad)
            raise AssertionError(f"accepted {bad}")
        except ValueError:
            pass

    fz = load_freezes()
    assert fz and all(a.startswith("0x") for a, _ in fz)
    with tempfile.TemporaryDirectory() as d:  # the SQLite file survives a restart
        PayeeMemory(Path(d) / "m.sqlite").add(Report("0xp", 1))
        assert PayeeMemory(Path(d) / "m.sqlite").evidence("0xp", 2)
        old = sqlite3.connect(str(Path(d) / "old.sqlite"))  # a file from before outcomes had kind/reason
        old.execute("CREATE TABLE outcomes (wallet TEXT, ts INTEGER, outcome TEXT, officer TEXT)")
        old.execute("INSERT INTO outcomes VALUES ('0xo', 1, 'confirmed', 'x')")
        old.commit(); old.close()
        assert PayeeMemory(Path(d) / "old.sqlite").evidence("0xo", 2)[0].kind == "real", "old files migrate"
    import threading
    m = PayeeMemory()
    t = threading.Thread(target=lambda: m.add(Report("0xt", 1)))
    t.start(); t.join()
    assert m.evidence("0xt", 2), "usable from another thread"
    print(f"self-check passed: payee memory ({len(fz)} non-OFAC freezes loadable)")


if __name__ == "__main__":
    _self_check()
