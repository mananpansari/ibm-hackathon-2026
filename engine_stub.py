"""Stand-in for C's decision engine (#3, #6, #7, #9) so D's app can be built before it lands.

Rules are the spec's tiering (#1) in their simplest form; C's engine replaces all of it.
No wall clock or network inside: history, known-bad set, freezes and classifier are injected.

What app.py needs from the real engine (C: this is the contract, tell D if yours differs):

    decide(withdrawal, answer=None, now=None) -> decision
        withdrawal = {"customer", "wallet", "amount", "time"}
        decision   = {"id", "tier", "reasons": [{"signal", "text", "source", "kind"}],
                      "expected_loss", "question" (question tier only), "engine_version"}
        tier in release | warning | question | hold. Calling again with the same withdrawal
        plus `answer` re-decides it (#7).
    record(event)    {"type": "officer_outcome", "wallet", "outcome": "cleared" | "confirmed", "time"}
                     {"type": "customer_report", "wallet", "customer", "time"}
    queue()          -> held decisions, largest expected loss first (#12)
    case(id)         -> {"decision", "withdrawal", "answer", "prior_warnings", "payers"} (#13)

    python engine_stub.py   # self-check
"""
import itertools

import features as F

ENGINE_VERSION = "stub-1"
LARGE_USDT = 1000  # ponytail: fixed "unusual amount" cut; C's engine decides per customer
P = {"release": 0.001, "warning": 0.01, "question": 0.05, "hold": 0.5}  # ponytail: tier -> scam probability, only to rank the queue


def reason(signal, text, source, kind="real"):
    return {"signal": signal, "text": text, "source": source, "kind": kind}


class StubEngine:
    def __init__(self, history, classifier, bad=frozenset(), frozen_at=None):
        self.history, self.classifier = history, classifier  # address -> history | None; has ask() and classify()
        self.bad, self.frozen_at = bad, frozen_at or {}
        self.paid = set()  # (customer, wallet) that went through
        self.memory = {}  # wallet -> list of warning dicts; ponytail: no decay, C's #6 adds it
        self.cleared = set()
        self.cases = {}  # id -> case
        self._ids = itertools.count(1)

    def decide(self, withdrawal, answer=None, now=None):
        w, c = withdrawal["wallet"], withdrawal["customer"]
        now = withdrawal["time"] if now is None else now
        reasons, tier = [], None
        h = self.history(w)
        if h is None:
            reasons.append(reason("no_history", "We have no recorded history for this wallet.", "snapshot"))
        else:
            f = F.features(h, now, self.bad, self.frozen_at)
            n = f["n_pay_in"]
            reasons.append(reason("wallet_payments", f"This wallet has received {n} payment{'s' * (n != 1)} of 10 USDT or more.",
                                  "on-chain history"))
            if f["touched_known_bad"]:
                tier = "hold"
                reasons.append(reason("counterparty_flagged", "This wallet has dealt with wallets already linked to scams or frozen by Tether.",
                                      "Tether freezes and scam lists"))
        if self.frozen_at.get(w, float("inf")) < now:
            tier = "hold"
            reasons.append(reason("wallet_frozen", "Tether has frozen this wallet.", "Tether freezes"))
        warnings = [m for m in self.memory.get(w, []) if m["time"] < now and m["customer"] != c]
        if w in self.cleared:
            reasons.append(reason("officer_cleared", "Our fraud team has checked and cleared this wallet.", "fraud officer"))
            tier = tier if tier == "hold" and any(r["signal"] == "wallet_frozen" for r in reasons) else None
        elif warnings:
            tier = "hold"
            reasons.append(reason("payee_memory", f"Another customer has raised {len(warnings)} warning{'s' * (len(warnings) != 1)} about this wallet.",
                                  "payee memory"))
        if answer is not None:
            cls = self.classifier.classify(answer)
            if cls["confirms_script"]:
                tier = "hold"
                reasons.append(reason("answer_confirms_script", f"Your answer matches a known scam pattern ({cls['scam_type'].replace('_', ' ')}).",
                                      cls["source"], "real"))
                self.memory.setdefault(w, []).append({"source": "customer answer", "customer": c, "time": now,
                                                     "detail": cls["scam_type"]})
            elif tier is None:
                tier = "release"
                reasons.append(reason("answer_ok", "Your answer doesn't match any scam pattern we know.", cls["source"]))
        first = (c, w) not in self.paid
        if tier is None:
            if first and withdrawal["amount"] >= LARGE_USDT:
                tier = "question"
                reasons.insert(0, reason("large_new_payee", "This is a large payment to a wallet you have never paid before.", "your payment history"))
            elif first:
                tier = "warning"
                reasons.insert(0, reason("first_time_payee", "You have never paid this wallet before.", "your payment history"))
            else:
                tier = "release"
                reasons.insert(0, reason("repeat_payee", "You have paid this wallet before.", "your payment history"))
        if tier in ("release", "warning"):
            self.paid.add((c, w))
        d = {"id": next(self._ids), "tier": tier, "reasons": reasons,
             "expected_loss": round(withdrawal["amount"] * P[tier], 2), "engine_version": ENGINE_VERSION}
        if tier == "question":
            d["question"] = self.classifier.ask(withdrawal, reasons)
        self.cases[d["id"]] = {"decision": d, "withdrawal": withdrawal, "answer": answer,
                               "prior_warnings": warnings, "status": "open"}
        return d

    def record(self, event):
        w = event["wallet"]
        if event["type"] == "officer_outcome":
            if event["outcome"] == "cleared":
                self.cleared.add(w)
                self.memory.pop(w, None)
            else:
                self.cleared.discard(w)
                self.memory.setdefault(w, []).append({"source": "officer confirmed scam", "customer": None,
                                                     "time": event["time"], "detail": "confirmed"})
            for case in self.cases.values():
                if case["withdrawal"]["wallet"] == w and case["decision"]["tier"] == "hold":
                    case["status"] = event["outcome"]
        elif event["type"] == "customer_report":
            self.memory.setdefault(w, []).append({"source": "customer report", "customer": event["customer"],
                                                 "time": event["time"], "detail": "report"})

    def queue(self):
        held = [c for c in self.cases.values() if c["decision"]["tier"] == "hold" and c["status"] == "open"]
        latest = {}  # one row per withdrawal: the last decision wins (a re-decided question replaces itself)
        for c in held:
            latest[(c["withdrawal"]["customer"], c["withdrawal"]["wallet"], c["withdrawal"]["time"])] = c
        return sorted(({"id": c["decision"]["id"], **c["withdrawal"], "expected_loss": c["decision"]["expected_loss"]}
                       for c in latest.values()), key=lambda r: -r["expected_loss"])

    def case(self, id):
        c = self.cases[id]
        w = c["withdrawal"]["wallet"]
        payers = [{"customer": o["withdrawal"]["customer"], "amount": o["withdrawal"]["amount"],
                   "time": o["withdrawal"]["time"], "tier": o["decision"]["tier"]}
                  for o in self.cases.values() if o["withdrawal"]["wallet"] == w]
        return {**c, "payers": payers}


if __name__ == "__main__":
    class Cls:
        def ask(self, w, r): return "Did someone tell you to send this?"
        def classify(self, a):
            yes = "officer" in a.lower()
            return {"scam_type": "government_impersonation" if yes else "none", "confirms_script": yes, "source": "stub"}

    me, other, bad = "0x" + "a" * 40, "0x" + "b" * 40, "0x" + "c" * 40
    rec = {me: {"address": me, "transfers": [
        {"ts": 10, "from": other, "to": me, "usdt": 50, "nonce": 1}, {"ts": 20, "from": other, "to": me, "usdt": 5, "nonce": 1},
        {"ts": 99, "from": other, "to": me, "usdt": 50, "nonce": 1}]},
           bad: {"address": bad, "transfers": [{"ts": 10, "from": other, "to": bad, "usdt": 50, "nonce": 1}]}}
    e = StubEngine(rec.get, Cls(), frozen_at={other: 30})
    wd = lambda c, a, t, w=me: {"customer": c, "wallet": w, "amount": a, "time": t}
    d = e.decide(wd("tan", 100, 25))
    assert d["tier"] == "warning" and "1 payment " in d["reasons"][1]["text"], d  # dust and future payments skipped
    assert e.decide(wd("tan", 100, 26))["tier"] == "release"
    q = wd("lee", 5000, 27)
    assert e.decide(q)["tier"] == "question" and e.decide(q)["question"]
    assert e.decide(q, answer="I'm buying a car")["tier"] == "release"
    q2 = wd("ong", 5000, 28)
    assert e.decide(q2, answer="the officer said my account is in danger")["tier"] == "hold"
    assert e.decide(wd("goh", 50, 29))["tier"] == "hold", "ong's answer holds goh's payment"
    assert e.decide(wd("goh", 50, 31))["reasons"][-1]["signal"] == "payee_memory"
    assert e.decide(wd("x", 50, 40, bad))["tier"] == "hold", "bad's sender was frozen at 30"
    assert e.decide(wd("x", 50, 29, bad))["tier"] == "warning", "freeze at 30 is not used before 30"
    assert [r["customer"] for r in e.queue()][:2] == ["ong", "goh"] and len(e.case(e.queue()[0]["id"])["payers"]) >= 5
    e.record({"type": "officer_outcome", "wallet": me, "outcome": "cleared", "time": 32})
    assert e.decide(wd("new", 50, 33))["tier"] == "warning" and not [r for r in e.queue() if r["wallet"] == me]
    print("stub engine self-check passed")
