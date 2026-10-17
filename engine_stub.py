"""Stand-in for C's decision engine (#3) so the app (#4) can be built before it lands.

Same seam as the spec (#1): decide(withdrawal, answer, now) -> decision, with the history
source injected and no wall clock or network inside. Only #3's first slice: warn on a
first-time payee, release a repeat payee. When #3 lands, app.py swaps its one import.

    withdrawal = {"customer", "wallet", "amount", "time"}
    decision   = {"tier", "reasons": [{"signal", "text", "source", "kind"}], "expected_loss", "engine_version"}

    python engine_stub.py   # self-check
"""
ENGINE_VERSION = "stub-0"
MIN_USDT = 10  # same payment floor as features.py


class StubEngine:
    def __init__(self, history):
        self.history = history  # address -> recorded history dict, or None
        self.paid = set()  # ponytail: in-process (customer, wallet) pairs; C's payee memory (#6) replaces it

    def decide(self, withdrawal, answer=None, now=None):
        c, w, now = withdrawal["customer"], withdrawal["wallet"], withdrawal["time"] if now is None else now
        h = self.history(w)
        if h is None:
            seen = {"signal": "no_history", "text": "We have no recorded history for this wallet.",
                    "source": "snapshot", "kind": "real"}
        else:
            n = sum(t["to"] == w and t["from"] != w and t["usdt"] >= MIN_USDT and t["ts"] < now for t in h["transfers"])
            seen = {"signal": "wallet_payments", "text": f"This wallet has received {n} payment{'s' * (n != 1)} of 10 USDT or more.",
                    "source": "on-chain history", "kind": "real"}
        if (c, w) in self.paid:
            tier, why = "release", {"signal": "repeat_payee", "text": "You have paid this wallet before.",
                                     "source": "your payment history", "kind": "real"}
        else:
            tier, why = "warning", {"signal": "first_time_payee", "text": "You have never paid this wallet before.",
                                     "source": "your payment history", "kind": "real"}
            self.paid.add((c, w))
        return {"tier": tier, "reasons": [why, seen], "expected_loss": 0.0, "engine_version": ENGINE_VERSION}


if __name__ == "__main__":
    me, other = "0x" + "a" * 40, "0x" + "b" * 40
    rec = {me: {"address": me, "transfers": [
        {"ts": 10, "from": other, "to": me, "usdt": 50}, {"ts": 20, "from": other, "to": me, "usdt": 5},
        {"ts": 99, "from": other, "to": me, "usdt": 50}]}}
    e = StubEngine(rec.get)
    d = e.decide({"customer": "tan", "wallet": me, "amount": 100, "time": 50})
    assert d["tier"] == "warning" and "1 payment " in d["reasons"][1]["text"], d  # dust and future payments skipped
    assert e.decide({"customer": "tan", "wallet": me, "amount": 100, "time": 60})["tier"] == "release"
    assert e.decide({"customer": "lee", "wallet": me, "amount": 100, "time": 60})["tier"] == "warning"
    assert e.decide({"customer": "lee", "wallet": other, "amount": 1, "time": 60})["reasons"][1]["signal"] == "no_history"
    print("stub engine self-check passed")
