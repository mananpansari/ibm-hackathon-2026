# Score Before You Sign

IBM Z Datathon 2026. Plan: `build-plan.md`. Current spec: issue #1. Why we reframed: `docs/feasibility.md`.

## Data (P1)

The snapshot is committed in `data/`, so you don't need a Blockscout key to use it:

| File | Contents |
|---|---|
| `freezes.csv` | Every Tether USDT freeze (address, time, block, tx, OFAC flag) |
| `known_bad.txt` | fesevu scam labels |
| `histories/*.jsonl.gz` | One wallet per line: `{address, group, freeze_ts, truncated, transfers[]}`. Groups: `{train,test}_{pos,neg,negv}` (`negv` = volume-matched comparison wallets) |
| `features.csv`, `sample.csv` | Training rows (first payment + 1/6/24/72 h) with the 12 point-in-time features |

```bash
python features.py              # self-check: no feature uses data after as_of
python feasibility.py           # go/no-go against each comparison set
python feasibility_extra.py volume-matched
python feasibility_young.py
```

## App (D)

```bash
pip install fastapi uvicorn
uvicorn app:app --reload        # customer page at http://127.0.0.1:8000
```

Runs on the recorded histories in `data/`, so no key is needed. Until C's engine (#3) lands, `app.py` uses `engine_stub.py`; swapping is a one-line import change.

## Re-running the snapshot (costs Blockscout credits)

Put `BLOCKSCOUT_API_KEY=...` in `.env` (it's git-ignored), then run `python fetch.py` (one test call), followed by `python snapshot.py`.

- **Cost:** the full pull is about 4,550 calls at 20 credits each. The free key gives 100K credits a day (about 5,000 calls), resetting at 00:00 UTC.
- **Cache:** every response is cached in `data/blockscout_cache.sqlite`, which is git-ignored and about 1 GB. A rerun only pays for URLs not already in the cache. Copy that file between machines rather than pulling again.
- **Guards:** the pull stops by itself below 1,000 credits or at 3,600 calls per run.
