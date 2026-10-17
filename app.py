"""Score API and customer page (#4). A thin wrapper: no decision logic lives here.

The engine gets the snapshot's recorded histories (no network), so this never reads the
Blockscout key; the live box (#17) will, server-side only, through fetch.py.

    pip install fastapi uvicorn
    uvicorn app:app --reload        # http://127.0.0.1:8000
"""
import gzip
import json
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from engine_stub import StubEngine as Engine  # swap for C's engine when #3 lands

HERE = Path(__file__).resolve().parent
HISTORIES = {}
for path in sorted((HERE / "data" / "histories").glob("*.jsonl.gz")):
    for line in gzip.open(path, "rt"):
        h = json.loads(line)
        HISTORIES[h["address"]] = h

engine = Engine(HISTORIES.get)
app = FastAPI(title="Score Before You Sign")


class Withdrawal(BaseModel):
    customer: str = Field(min_length=1, max_length=64)
    wallet: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$")
    amount: float = Field(gt=0, le=1e9)


@app.post("/score")
def score(w: Withdrawal):
    return engine.decide({**w.model_dump(), "wallet": w.wallet.lower(), "time": time.time()})


@app.get("/")
def customer_page():
    return FileResponse(HERE / "static" / "customer.html")
