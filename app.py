"""Score API, customer page and officer console (#4, #8, #12, #13, #17, UI v2). A thin wrapper around
C's engine (engine.py): every tier comes from engine.decide(); this file loads data, sets the
injected clock and moves JSON. Structured answers, outcome codes, wallet facts and personas come
from A's modules (answers.py, payee_memory.py, wallet_facts.py, data/demo/); see docs/team/ui-v2.md.

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
import json
import os
import platform
import time
import types
from dataclasses import asdict
from pathlib import Path
from typing import Literal, Optional, Union

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import answers
import granite
from decision_log import DecisionLog
from engine import Engine, RecordedHistories, Withdrawal, to_dict
from payee_memory import REASON_CODES, OfficerOutcome, PayeeMemory, load_freezes, outcome_for
from wallet_facts import wallet_facts

try:
    from model import score as model_score  # B's weak signal (#5); warns at most, never holds
except ImportError:  # no numpy (e.g. the slim base image): the engine decides without it
    model_score = None

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
WALLET = r"^0x[0-9a-fA-F]{40}$"
LIVE_TIMEOUT_S = 8
COACHED = "The police officer on the phone said my account is linked to a crime and I must move my savings to this safe wallet."
COACHED_ANSWER = json.loads((DATA / "demo" / "coached_answer.json").read_text())["answer"]  # A's scripted answer (modelled)
HOST = platform.machine()  # "s390x" on LinuxONE; the customer page shows it as "LinuxONE"

RECORDED = RecordedHistories(("train_pos", "train_neg", "train_negv", "test_pos", "test_neg", "test_negv"))
FROZEN_AT = {r["address"]: int(r["freeze_ts"]) for r in csv.DictReader(open(DATA / "freezes.csv"))}
FREEZES = load_freezes()
BAD = frozenset((DATA / "known_bad.txt").read_text().split())
_people = json.loads((DATA / "demo" / "personas.json").read_text())
PERSONAS = {p["customer"]: p for p in _people["customers"]}
PERSONAS["mrs-tan"] = PERSONAS["customer-1"]  # the customer page's default ID is the video's Mrs Tan
DEFAULT_PERSONA = _people["default"]
LIVE = {}  # histories pulled by the live box this run
LOG = DecisionLog(DATA / "decisions.jsonl")  # one append-only chain across demo resets
pool = concurrent.futures.ThreadPoolExecutor(2)
clock = {"now": 0}  # the engine's injected clock; set to each withdrawal's time before deciding
# Engine routes are `async def` so they all run on the event-loop thread: the engine, its SQLite
# payee memory and the clock above are single-threaded. Only the Blockscout pull runs in `pool`.


# Only granite's classify(): the page asks answers.QUESTIONS itself, so the engine needn't wait up to
# 2 s for Granite to word a question nobody shows (StructuredClassifier falls back to the template).
FREE_TEXT = types.SimpleNamespace(classify=granite.classify)


def history(wallet, as_of):
    h = LIVE.get(wallet)
    if h is None:
        return RECORDED(wallet, as_of)
    return {**h, "freeze_ts": None, "transfers": [t for t in h["transfers"] if t["ts"] < as_of]}


def new_engine():
    memory = PayeeMemory()
    memory.add_freezes(FREEZES)
    return Engine(history, memory, lambda: clock["now"], LOG, model=model_score, known_bad=BAD,
                  classifier=answers.StructuredClassifier(FREE_TEXT))


def persona(customer):
    return PERSONAS.get(customer, DEFAULT_PERSONA)


engine = new_engine()
# id -> {"decision", "withdrawal", "answer", "status", "held_at", "claimed_by", "events"}; the queue and why-cards
# read these. status: open -> claimed -> closed, or cancelled by the customer; "answered" = replaced by its answer.
cases = {}
ids = itertools.count(1)
app = FastAPI(title="Score Before You Sign")


class WithdrawalIn(BaseModel):
    customer: str = Field(min_length=1, max_length=64)
    wallet: str = Field(pattern=WALLET)
    amount: float = Field(gt=0, le=1e9)


class Answer(BaseModel):
    id: int
    answer: Union[dict, str]  # structured {"why", "how", "asked", "text"} (UI v2) or free text (the old flow)


class Outcome(BaseModel):  # new body: id + call + decision + reason; old body: wallet + outcome
    wallet: str = Field(pattern=WALLET)
    outcome: Optional[Literal["cleared", "confirmed"]] = None
    id: Optional[int] = None
    call: Optional[Literal["confirmed_identity", "other_person", "no_answer"]] = None
    decision: Optional[str] = None
    reason: Optional[str] = None
    note: str = Field(default="", max_length=2000)


class CaseId(BaseModel):
    id: int


class Claim(BaseModel):
    id: int
    officer: str = Field(min_length=1, max_length=32)


class Live(BaseModel):
    wallet: str = Field(pattern=WALLET)
    amount: float = Field(default=1000, gt=0, le=1e9)


def event(c, what, who):
    """Per-case activity, also chained into the decision log so it can't be edited later."""
    e = {"ts": int(time.time()), "what": what, "who": who}
    c["events"].append(e)
    LOG.append({"event": what, "case": c["decision"]["id"], "ref": c["decision"]["ref"], "who": who, "ts": e["ts"]})


def decide(w, answer=None, answer_kind=None):
    clock["now"] = w["time"]
    t0 = time.perf_counter()
    d = to_dict(engine.decide(Withdrawal(w["customer"], w["wallet"], w["amount"], w["time"]), answer, answer_kind))
    d["decide_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    d["id"] = next(ids)
    d.update(ref=f"SBYS-{d['id']:04d}", host=HOST, model_on=model_score is not None, persona=persona(w["customer"]))
    cases[d["id"]] = {"decision": d, "withdrawal": w, "answer": answer, "status": "open", "held_at": int(time.time()),
                      "claimed_by": None, "events": [{"ts": int(time.time()), "what": f"Decided: {d['tier']}", "who": "engine"}]}
    return d


def answered(w, answer, kind=None):
    """The engine (#7) classifies the answer (A's StructuredClassifier), holds and writes the payee-memory report."""
    return decide(w, answer, kind)


@app.post("/score")
async def score(w: WithdrawalIn):
    return decide({**w.model_dump(), "wallet": w.wallet.lower(), "time": int(time.time())})


@app.get("/questions")
async def questions():
    return answers.QUESTIONS


@app.get("/outcome-codes")
async def outcome_codes():
    return REASON_CODES


@app.get("/persona")
async def get_persona(customer: str):  # so the customer page can say who is signed in before the first check
    return persona(customer)


@app.post("/answer")
async def answer(a: Answer):
    if a.id not in cases:
        raise HTTPException(404, "unknown withdrawal")
    if isinstance(a.answer, str) and not 1 <= len(a.answer) <= 2000:
        raise HTTPException(422, "answer must be 1 to 2,000 characters")
    q = cases[a.id]
    try:
        d = answered(q["withdrawal"], a.answer)
    except ValueError as e:  # a structured answer that doesn't follow answers.QUESTIONS
        raise HTTPException(422, str(e))
    q["status"] = "answered"  # the answer's decision replaces the question
    return d


@app.post("/cancel")
async def cancel(c: CaseId):
    if c.id not in cases:
        raise HTTPException(404, "unknown withdrawal")
    case_ = cases[c.id]
    case_["status"] = "cancelled"  # this payment only: payee memory is unchanged
    event(case_, "Cancelled by the customer", "customer")
    return {"id": c.id, "status": "cancelled"}


@app.post("/claim")
async def claim(c: Claim):
    if c.id not in cases:
        raise HTTPException(404, "unknown case")
    case_ = cases[c.id]
    if case_["claimed_by"] not in (None, c.officer):
        raise HTTPException(409, f"claimed by {case_['claimed_by']}")
    if case_["claimed_by"] is None:
        case_.update(claimed_by=c.officer, status="claimed" if case_["status"] == "open" else case_["status"])
        event(case_, "Claimed", c.officer)
        event(case_, "Customer name viewed", c.officer)
    return await case(c.id)


@app.get("/queue")
async def queue():  # ponytail: ranked here; #9's capacity limit is off in the app (Config default)
    latest = {}
    now = int(time.time())
    for id, c in cases.items():
        d = c["decision"]
        if d["tier"] == "hold" and c["status"] != "answered":
            w = c["withdrawal"]
            top = d["reasons"][0] if d["reasons"] else None
            latest[(w["customer"], w["wallet"])] = {
                "id": id, **w, "expected_loss": d["expected_loss"], "ref": d["ref"], "persona": d["persona"], "p_scam": d["p_scam"],
                "top_reason": {k: top[k] for k in ("signal", "detail", "kind")} if top else None,
                "status": c["status"], "claimed_by": c["claimed_by"], "waiting_s": now - c["held_at"]}
    rows = sorted(latest.values(), key=lambda r: -r["expected_loss"])
    live = [r for r in rows if r["status"] in ("open", "claimed")]
    waiting = [r for r in rows if r["status"] == "open"]
    return {"rows": rows, "summary": {  # ponytail: "today" is this server run; the demo restarts daily
        "waiting": len(waiting), "usdt_on_hold": round(sum(r["amount"] for r in live), 2),
        "oldest_waiting_s": max((r["waiting_s"] for r in waiting), default=0),
        "closed_today": sum(r["status"] in ("closed", "cancelled") for r in rows)}}


def officer(wallet, outcome, ts, officer_id, kind="real", reason=""):
    engine.record(OfficerOutcome(wallet, outcome, ts, officer_id, kind=kind, reason=reason))
    for c in cases.values():
        if c["withdrawal"]["wallet"] == wallet and c["withdrawal"]["time"] <= ts and c["status"] in ("open", "claimed"):
            c["status"] = "closed"  # resolved: off the queue


@app.post("/outcome")
async def outcome(o: Outcome):
    wallet = o.wallet.lower()
    if o.decision is None:  # the old body
        if o.outcome is None:
            raise HTTPException(422, "send outcome, or id + call + decision + reason")
        officer(wallet, o.outcome, int(time.time()), "officer")
        return await queue()
    if o.id not in cases:
        raise HTTPException(404, "unknown case")
    try:
        result = outcome_for(o.decision, o.reason)  # A's mapping: "confirmed", "cleared" or None
    except ValueError as e:
        raise HTTPException(422, str(e))
    c, ts = cases[o.id], int(time.time())
    who = c["claimed_by"] or "officer"
    if result:
        officer(wallet, result, ts, who, reason=o.reason)
    if o.decision != "keep":
        c["status"] = "closed"
    event(c, f"Outcome: {o.decision} · {REASON_CODES[o.reason]}" + (f" · call: {o.call}" if o.call else "")
          + (f" · wallet {result}" if result else ""), who)
    return {"id": o.id, "status": c["status"], "outcome": result}


@app.get("/case/{id}")
async def case(id: int):
    if id not in cases:
        raise HTTPException(404, "unknown case")
    c = cases[id]
    w = c["withdrawal"]
    payers = [{"customer": o["withdrawal"]["customer"], "amount": o["withdrawal"]["amount"],
               "time": o["withdrawal"]["time"], "tier": o["decision"]["tier"]}
              for o in cases.values() if o["withdrawal"]["wallet"] == w["wallet"] and o["status"] != "answered"]
    prior = [asdict(e) for e in engine.memory.evidence(w["wallet"], w["time"] + 1)]  # +1: include what this decision recorded
    return {**c, "prior_warnings": prior, "payers": payers, "tether_froze_at": FROZEN_AT.get(w["wallet"]),
            "persona": c["decision"]["persona"], "wallet_facts": wallet_facts(history(w["wallet"], w["time"]), w["time"], BAD),
            "known_bad": w["wallet"] in BAD, "modelled_answer": c["answer"] in (COACHED, COACHED_ANSWER)}


def _pull(addr):
    import snapshot  # live_history: fetch.py's live mode (one try, 6 s, 100-credit floor); never raises
    return snapshot.live_history(addr)


@app.post("/live")
async def live(l: Live):
    addr = l.wallet.lower()
    try:
        r = await asyncio.wait_for(asyncio.wrap_future(pool.submit(_pull, addr)), LIVE_TIMEOUT_S)
    except (Exception, SystemExit):  # backstop: live_history already turns failures into a status
        r = {"status": "unavailable", "message": "Blockscout didn't answer in time.", "history": None}
    if r["history"]:
        LIVE[addr] = r["history"]
    src = "live Blockscout" if r["history"] else "snapshot" if addr in RECORDED.by_addr else "none"
    d = decide({"customer": "judge", "wallet": addr, "amount": l.amount, "time": int(time.time())})
    return {**d, "history_source": src, "live_status": r["status"], "live_message": r["message"]}


# Demo spine (#17): replay one frozen wallet's real payments in time order. Customers are the
# sending wallets (payments from the same sender are the same customer). As in docs/demo-script.md:
# customer 1 answers like a coached victim; the next payment is held by that warning; an officer
# calls back and confirms the scam (both scripted: modelled), so every later payment is held until
# the freeze ("the engine holds all 12 once an officer confirms").
CONFIRM_AFTER_S = 86400  # the officer confirms a day after that hold, #10's officer delay


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
    d = answered(w, COACHED_ANSWER, kind="modelled") if demo["step"] == 1 else decide(w)
    confirmed = not demo["confirmed"] and demo["step"] > 1 and d["tier"] == "hold"
    if confirmed:
        officer(demo["wallet"], "confirmed", w["time"] + CONFIRM_AFTER_S, "officer (demo script, modelled)",
                kind="modelled", reason="confirmed_impersonation")
        demo["confirmed"] = demo["wallet"]
    return {"done": False, "step": demo["step"], "withdrawal": w, "decision": d,
            "answer": COACHED_ANSWER if demo["step"] == 1 else None, "officer_confirmed": confirmed}


@app.get("/")
def customer_page():
    return FileResponse(HERE / "static" / "customer.html")


@app.get("/officer")
def officer_page():  # ponytail: demo login only; put it behind the bank's SSO in production
    return FileResponse(HERE / "static" / "officer.html")
