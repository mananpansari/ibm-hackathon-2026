"""Score API, customer page and officer console (#4, #8, #12, #13, #17). A thin wrapper:
every decision comes from the engine; this file only loads data and moves JSON.

The engine reads the snapshot's recorded histories. Only the live box (/live) touches
Blockscout, server-side through fetch.py (key from the environment or .env, never sent to a
page), and falls back to the snapshot if Blockscout is slow, unreachable or out of credits.

    pip install fastapi uvicorn
    uvicorn app:app --reload        # customer page http://127.0.0.1:8000, officer /officer
"""
import concurrent.futures
import csv
import gzip
import json
import os
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import granite
from engine_stub import StubEngine as Engine  # swap for C's engine when #3 lands

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
WALLET = r"^0x[0-9a-fA-F]{40}$"
LIVE_TIMEOUT_S = 8
COACHED = "The police officer on the phone said my account is linked to a crime and I must move my savings to this safe wallet."

HISTORIES = {}
for path in sorted((DATA / "histories").glob("*.jsonl.gz")):
    for line in gzip.open(path, "rt"):
        h = json.loads(line)
        HISTORIES[h["address"]] = h
BAD = set((DATA / "known_bad.txt").read_text().split())
FROZEN_AT = {r["address"]: int(r["freeze_ts"]) for r in csv.DictReader(open(DATA / "freezes.csv"))}
LIVE = {}  # histories pulled by the live box this run
pool = concurrent.futures.ThreadPoolExecutor(2)


def new_engine():
    return Engine(lambda a: LIVE.get(a) or HISTORIES.get(a), granite, BAD, FROZEN_AT)


engine = new_engine()
pending = {}  # decision id -> withdrawal, so an answer can be re-decided
app = FastAPI(title="Score Before You Sign")


class Withdrawal(BaseModel):
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
    d = engine.decide(w, answer)
    pending[d["id"]] = w
    return d


@app.post("/score")
def score(w: Withdrawal):
    return decide({**w.model_dump(), "wallet": w.wallet.lower(), "time": time.time()})


@app.post("/answer")
def answer(a: Answer):
    if a.id not in pending:
        raise HTTPException(404, "unknown withdrawal")
    return decide(pending[a.id], a.answer)


@app.get("/queue")
def queue():
    return engine.queue()


@app.post("/outcome")
def outcome(o: Outcome):
    engine.record({"type": "officer_outcome", "wallet": o.wallet.lower(), "outcome": o.outcome, "time": time.time()})
    return engine.queue()


@app.get("/case/{id}")
def case(id: int):
    try:
        c = engine.case(id)
    except KeyError:
        raise HTTPException(404, "unknown case")
    return {**c, "tether_froze_at": FROZEN_AT.get(c["withdrawal"]["wallet"]), "modelled_answer": c["answer"] == COACHED}


def _pull(addr):
    import snapshot  # fetch.py's cache, throttle and 1,000-credit guard (snapshot.history uses bulk calls)
    return snapshot.history(addr, "live", 1000)


@app.post("/live")
def live(l: Live):
    addr = l.wallet.lower()
    try:
        h = pool.submit(_pull, addr).result(timeout=LIVE_TIMEOUT_S)
    except (Exception, SystemExit):  # no key (SystemExit), timeout, credits, network
        h = None
    if h:
        LIVE[addr] = h
    src = "live Blockscout" if h else "snapshot" if addr in HISTORIES else "none"
    d = decide({"customer": "judge", "wallet": addr, "amount": l.amount, "time": time.time()})
    return {**d, "history_source": src}


# Demo spine (#17): replay one frozen wallet's real payments as customers 1..N, in time order.
def _demo_wallet():
    if os.environ.get("DEMO_WALLET"):  # A picks the final wallet in #16
        return os.environ["DEMO_WALLET"].lower()
    pays = lambda h: [t for t in h["transfers"] if t["to"] == h["address"] and t["usdt"] >= 10 and t["ts"] < h["freeze_ts"]]
    cands = [h for h in HISTORIES.values() if h["group"] == "test_pos" and 6 <= len(pays(h)) <= 15]
    return min(cands, key=lambda h: h["address"])["address"]  # ponytail: deterministic stand-in until #16


demo = {"wallet": None, "step": 0}


@app.post("/demo/reset")
def demo_reset():
    global engine
    engine = new_engine()
    pending.clear()
    demo.update(wallet=_demo_wallet(), step=0)
    h = HISTORIES[demo["wallet"]]
    return {"wallet": demo["wallet"], "tether_froze_at": h["freeze_ts"]}


@app.post("/demo/next")
def demo_next():
    if demo["wallet"] is None:
        demo_reset()
    h = HISTORIES[demo["wallet"]]
    pays = [t for t in h["transfers"] if t["to"] == h["address"] and t["usdt"] >= 10 and t["ts"] < h["freeze_ts"]]
    if demo["step"] >= len(pays):
        return {"done": True, "tether_froze_at": h["freeze_ts"]}
    t, demo["step"] = pays[demo["step"]], demo["step"] + 1
    w = {"customer": f"customer-{demo['step']}", "wallet": h["address"], "amount": t["usdt"], "time": t["ts"]}
    # customer 1 is asked and answers like a coached victim; everyone after just pays
    d = decide(w, COACHED if demo["step"] == 1 else None)
    return {"done": False, "step": demo["step"], "of": len(pays), "withdrawal": w, "decision": d,
            "answer": COACHED if demo["step"] == 1 else None}


@app.get("/")
def customer_page():
    return FileResponse(HERE / "static" / "customer.html")


@app.get("/officer")
def officer_page():  # ponytail: unlinked, no login; put it behind the bank's SSO in production
    return FileResponse(HERE / "static" / "officer.html")
