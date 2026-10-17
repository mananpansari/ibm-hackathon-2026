"""Shared payee memory (issue #6): what the institution knows about each destination wallet.

Keyed by destination wallet and shared across customers, so customer A's report protects
customer B. SQLite-backed (":memory:" for tests and the replay, a file on the VM). Every query
takes `now` and only sees events from before it, so the replay can load all of Tether's freezes
up front without hindsight.

Evidence about a wallet:
- Customer reports decay with a half-life (default 7 days; the build plan's 6 h was too short
  for wallets that collect for ~4 months). One fresh report is enough to hold.
- An officer's "confirmed" pins the wallet with no decay; "cleared" drops everything before it.
  The latest officer outcome wins.
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
        self.db = sqlite3.connect(str(path))
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS paid (customer TEXT, wallet TEXT, ts INTEGER, PRIMARY KEY (customer, wallet));
            CREATE TABLE IF NOT EXISTS reports (wallet TEXT, ts INTEGER, source TEXT, kind TEXT, actor TEXT, note TEXT);
            CREATE TABLE IF NOT EXISTS outcomes (wallet TEXT, ts INTEGER, outcome TEXT, officer TEXT);
            CREATE TABLE IF NOT EXISTS freezes (wallet TEXT PRIMARY KEY, ts INTEGER);
            CREATE INDEX IF NOT EXISTS reports_wallet ON reports (wallet, ts);
            CREATE INDEX IF NOT EXISTS outcomes_wallet ON outcomes (wallet, ts);
        """)

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
            self.db.execute("INSERT INTO outcomes VALUES (?, ?, ?, ?)",
                            (event.wallet, event.ts, event.outcome, event.officer_id))
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
        last = self.db.execute("SELECT ts, outcome, officer FROM outcomes WHERE wallet = ? AND ts < ? "
                               "ORDER BY ts DESC, rowid DESC LIMIT 1", (wallet, now)).fetchone()
        if last and last[1] == "confirmed":
            out.append(Evidence("officer_confirmed", "officer", "real",
                                "A fraud officer confirmed this wallet as a scam.", 1.0))
        since = last[0] if last and last[1] == "cleared" else -1
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

    fz = load_freezes()
    assert fz and all(a.startswith("0x") for a, _ in fz)
    with tempfile.TemporaryDirectory() as d:  # the SQLite file survives a restart
        PayeeMemory(Path(d) / "m.sqlite").add(Report("0xp", 1))
        assert PayeeMemory(Path(d) / "m.sqlite").evidence("0xp", 2)
    print(f"self-check passed: payee memory ({len(fz)} non-OFAC freezes loadable)")


if __name__ == "__main__":
    _self_check()
