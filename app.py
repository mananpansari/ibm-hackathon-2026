"""Score API, customer page and officer console (#4, #8, #12, #13, #17). A thin wrapper around
C's engine (engine.py): every tier comes from engine.decide(); this file loads data, sets the
injected clock and moves JSON.

The engine reads the snapshot's recorded histories. Only the live box (/live) touches
Blockscout, server-side through fetch.py (key from the environment or .env, never sent to a
page), and falls back to the snapshot if Blockscout is slow, unreachable or out of credits.

    pip install fastapi uvicorn
    uvicorn app:app --reload        # customer page http://127.0.0.1:8000, officer /officer
"""
import asyncio
import concurrent.futures
import csv
import itertools
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import granite
from decision_log import DecisionLog
from engine import Engine, RecordedHistories, Withdrawal, to_dict
from payee_memory import OfficerOutcome, PayeeMemory, Report, load_freezes

try:
    from model import score as model_score  # B's weak signal (#5); warns at most, never holds
except ImportError:  # no numpy (e.g. the slim base image): the engine decides without it
    model_score = None

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
WALLET = r"^0x[0-9a-fA-F]{40}$"
LIVE_TIMEOUT_S = 8
COACHED = "The police officer on the phone said my account is linked to a crime and I must move my savings to this safe wallet."

RECORDED = RecordedHistories(("train_pos", "train_neg", "train_negv", "test_pos", "test_neg", "test_negv"))
FROZEN_AT = {r["address"]: int(r["freeze_ts"]) for r in csv.DictReader(open(DATA / "freezes.csv"))}
FREEZES = load_freezes()
BAD = frozenset((DATA / "known_bad.txt").read_text().split())
LIVE = {}  # histories pulled by the live box this run
LOG = DecisionLog(DATA / "decisions.jsonl")  # one append-only chain across demo resets
pool = concurrent.futures.ThreadPoolExecutor(2)
clock = {"now": 0}  # the engine's injected clock; set to each withdrawal's time before deciding
# Engine routes are `async def` so they all run on the event-loop thread: the engine, its SQLite
# payee memory and the clock above are single-threaded. Only the Blockscout pull runs in `pool`.


def history(wallet, as_of):
    h = LIVE.get(wallet)
    if h is None:
        return RECORDED(wallet, as_of)
    return {**h, "freeze_ts": None, "transfers": [t for t in h["transfers"] if t["ts"] < as_of]}


def new_engine():
    memory = PayeeMemory()
    memory.add_freezes(FREEZES)
    return Engine(history, memory, lambda: clock["now"], LOG, model=model_score, known_bad=BAD)


engine = new_engine()
cases = {}  # id -> {"decision", "withdrawal", "answer", "status"}; the queue and why-cards read these
ids = itertools.count(1)
app = FastAPI(title="Score Before You Sign")


class WithdrawalIn(BaseModel):
    customer: str = Field(min_length=1, max_length=64)
    wallet: str = Field(pattern=WALLET)
    amount: float = Field(gt=0, le=1e9)


class Answer(BaseModel):
    id: int
    answer: str = Field(min_length=1, max_length=2000)


class Outcome(BaseModel):
    wallet: str = Field(pattern=WALLET)
    outcome: Literal["cleared", "confirmed"]


class Live(BaseModel):
    wallet: str = Field(pattern=WALLET)
    amount: float = Field(default=1000, gt=0, le=1e9)


def decide(w, answer=None):
    clock["now"] = w["time"]
    d = to_dict(engine.decide(Withdrawal(w["customer"], w["wallet"], w["amount"], w["time"]), answer))
    d["id"] = next(ids)
    cases[d["id"]] = {"decision": d, "withdrawal": w, "answer": answer, "status": "open"}
    return d


def answered(w, answer, kind="real"):
    """Bridge until #7 puts the question tier in the engine: a confirming answer becomes a
    payee-memory report (what #7 will do inside decide), then the withdrawal is re-decided."""
    cls = granite.classify(answer)
    if cls["confirms_script"]:
        engine.record(Report(w["wallet"], w["time"], source="customer_answer", kind=kind,
                             actor=w["customer"], note=cls["scam_type"]))
        w = {**w, "time": w["time"] + 1}  # memory only counts reports from before now
    return decide(w, answer)


@app.post("/score")
async def score(w: WithdrawalIn):
    return decide({**w.model_dump(), "wallet": w.wallet.lower(), "time": int(time.time())})


@app.post("/answer")
async def answer(a: Answer):
    if a.id not in cases:
        raise HTTPException(404, "unknown withdrawal")
    return answered(cases[a.id]["withdrawal"], a.answer)


@app.get("/queue")
async def queue():  # ponytail: ranked here until #9 gives the engine a capacity-aware queue
    latest = {}
    for id, c in cases.items():
        if c["decision"]["tier"] == "hold" and c["status"] == "open":
            w = c["withdrawal"]
            latest[(w["customer"], w["wallet"])] = {"id": id, **w, "expected_loss": c["decision"]["expected_loss"]}
    return sorted(latest.values(), key=lambda r: -r["expected_loss"])


def officer(wallet, outcome, ts, officer_id):
    engine.record(OfficerOutcome(wallet, outcome, ts, officer_id))
    for c in cases.values():
        if c["withdrawal"]["wallet"] == wallet and c["withdrawal"]["time"] <= ts:
            c["status"] = outcome  # resolved: off the queue


@app.post("/outcome")
async def outcome(o: Outcome):
    officer(o.wallet.lower(), o.outcome, int(time.time()), "officer")
    return await queue()


@app.get("/case/{id}")
async def case(id: int):
    if id not in cases:
        raise HTTPException(404, "unknown case")
    c = cases[id]
    w = c["withdrawal"]
    payers = [{"customer": o["withdrawal"]["customer"], "amount": o["withdrawal"]["amount"],
               "time": o["withdrawal"]["time"], "tier": o["decision"]["tier"]}
              for o in cases.values() if o["withdrawal"]["wallet"] == w["wallet"]]
    prior = [asdict(e) for e in engine.memory.evidence(w["wallet"], w["time"])]
    if w["wallet"] == demo["confirmed"]:  # ponytail: OfficerOutcome has no kind yet (asked C); the demo's is scripted
        for r in prior + c["decision"]["reasons"]:
            if r["signal"] == "officer_confirmed":
                r["kind"] = "modelled"
    return {**c, "prior_warnings": prior, "payers": payers, "tether_froze_at": FROZEN_AT.get(w["wallet"]),
            "modelled_answer": c["answer"] == COACHED}


def _pull(addr):
    import snapshot  # fetch.py's cache, throttle and 1,000-credit guard (snapshot.history uses bulk calls)
    return snapshot.history(addr, "live", 1000)


@app.post("/live")
async def live(l: Live):
    addr = l.wallet.lower()
    try:
        h = await asyncio.wait_for(asyncio.wrap_future(pool.submit(_pull, addr)), LIVE_TIMEOUT_S)
    except (Exception, SystemExit):  # no key (SystemExit), timeout, credits, network
        h = None
    if h:
        LIVE[addr] = h
    src = "live Blockscout" if h else "snapshot" if addr in RECORDED.by_addr else "none"
    d = decide({"customer": "judge", "wallet": addr, "amount": l.amount, "time": int(time.time())})
    return {**d, "history_source": src}


# Demo spine (#17): replay one frozen wallet's real payments in time order. Customers are the
# sending wallets (payments from the same sender are the same customer). Customer 1 answers like
# a coached victim; the first different customer to pay is held because of it; an officer calls
# back and confirms the scam (both scripted: modelled), so every later payment is held until the
# freeze. Agreed with A for #16: "the engine holds all 12 once an officer confirms".
CONFIRM_AFTER_S = 3600  # scripted call-back one hour after that hold


def _pays(h):
    return [t for t in h["transfers"] if t["to"] == h["address"] and t["from"] != h["address"]
            and t["usdt"] >= 10 and t["ts"] < h["freeze_ts"]]


def _demo_wallet():
    # A's #16 wallet as described (13 payments; 1 and 2 from one exchange wallet 10 min apart, 3 the
    # first different sender, frozen 5 Aug 2026). DEMO_WALLET overrides.
    return os.environ.get("DEMO_WALLET", "0x74f645934fd288dfcb6359870779f68c2b0c48b8").lower()


demo = {"wallet": None, "step": 0, "confirmed": None, "senders": {}}


@app.post("/demo/reset")
async def demo_reset():
    global engine
    engine = new_engine()
    cases.clear()
    demo.update(wallet=_demo_wallet(), step=0, confirmed=None, senders={})
    return {"wallet": demo["wallet"], "tether_froze_at": FROZEN_AT.get(demo["wallet"])}


@app.post("/demo/next")
async def demo_next():
    if demo["wallet"] is None:
        await demo_reset()
    pays = _pays(RECORDED.by_addr[demo["wallet"]])
    if demo["step"] >= len(pays):
        return {"done": True, "tether_froze_at": FROZEN_AT.get(demo["wallet"])}
    t, demo["step"] = pays[demo["step"]], demo["step"] + 1
    customer = demo["senders"].setdefault(t["from"], f"customer-{len(demo['senders']) + 1}")
    w = {"customer": customer, "wallet": demo["wallet"], "amount": t["usdt"], "time": t["ts"]}
    # customer 1's first payment is asked and answered like a coached victim (modelled); the rest just pay
    d = answered(w, COACHED, kind="modelled") if demo["step"] == 1 else decide(w)
    confirmed = not demo["confirmed"] and customer != "customer-1" and d["tier"] == "hold"
    if confirmed:
        officer(demo["wallet"], "confirmed", w["time"] + CONFIRM_AFTER_S, "officer (demo script, modelled)")
        demo["confirmed"] = demo["wallet"]
    return {"done": False, "step": demo["step"], "withdrawal": w, "decision": d,
            "answer": COACHED if demo["step"] == 1 else None, "officer_confirmed": confirmed}


@app.get("/")
def customer_page():
    return FileResponse(HERE / "static" / "customer.html")


@app.get("/officer")
def officer_page():  # ponytail: unlinked, no login; put it behind the bank's SSO in production
    return FileResponse(HERE / "static" / "officer.html")
