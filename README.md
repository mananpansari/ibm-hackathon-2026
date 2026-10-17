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
uvicorn app:app --reload        # customer page http://127.0.0.1:8000, officer console /officer
python engine.py                # C's engine scenario check
python granite.py eval          # answer classifier accuracy (BothBosu + data/sg_answers.csv)
```

Runs on the recorded histories in `data/`, so no key is needed (the live box falls back to the snapshot without one). `app.py` wraps C's engine (`engine.py`). Until #7 adds the question tier, a confirming answer is recorded as a payee-memory report by a small bridge in `app.py` (`answered()`). Granite: run `llama-server -m granite-4.2-3b-Q4_K_M.gguf --port 8080` on the same machine; without it, template questions and a keyword classifier are used. Demo wallet: `DEMO_WALLET=0x...` (otherwise a fixed test-set wallet).

## Re-running the snapshot (costs Blockscout credits)

Put `BLOCKSCOUT_API_KEY=...` in `.env` (it's git-ignored), then run `python fetch.py` (one test call), followed by `python snapshot.py`.

- **Cost:** the full pull is about 4,550 calls at 20 credits each. The free key gives 100K credits a day (about 5,000 calls), resetting at 00:00 UTC.
- **Cache:** every response is cached in `data/blockscout_cache.sqlite`, which is git-ignored and about 1 GB. A rerun only pays for URLs not already in the cache. Copy that file between machines rather than pulling again.
- **Guards:** the pull stops by itself below 1,000 credits or at 3,600 calls per run.

## Deploy on LinuxONE (#11)

VM: LinuxONE Community Cloud `bob1`, Ubuntu 24.04 on s390x, 3 vCPU, 8 GB, NNPA present. Lab image: `registry.linuxone.cloud.marist.edu/l1cc/jupyterlab-image-s390x:latest` (TF 2.18 + ibm-zdnn-plugin 2.3, XGBoost 3.4, scikit-learn 1.9, llama_cpp_python 0.3.36; Python is a venv at `/opt/venv`, running as `ibm-user`).

The repo is private, so copy committed files to the VM instead of cloning there (no GitHub credentials on the VM):

```bash
git archive --format=tar HEAD | ssh -i bob.pem linux1@148.100.108.187 'mkdir -p ~/sbys && tar -x -C ~/sbys'
```

Then on the VM, in `~/sbys`:

```bash
bash vm_check.sh <lab-image>                      # read-only: NNPA, docker, TF/zDNN, XGBoost, llama.cpp
docker build --build-arg BASE=<lab-image> -t sbys .
docker run -d --name sbys --restart unless-stopped -p 127.0.0.1:8000:8000 --env-file .env -v "$PWD/data:/app/data" sbys   # drop --env-file until .env exists
curl -s localhost:8000/score -H 'content-type: application/json' \
  -d '{"customer":"c1","wallet":"0x0000000000000000000000000000000000000001","amount":500}'
```

- The snapshot comes from git, so there's no Blockscout pull on the VM. To give the live box free lookups for wallets already seen, copy `data/blockscout_cache.sqlite` over with `scp`.
- `data/` is a volume, so payee memory survives container rebuilds. The key only enters at run time via `--env-file` (create `.env` with `chmod 600`). Neither is baked into the image.
- `.env` is optional until the live box (#17).
- The app binds to localhost on the VM, so it isn't public. View it from your laptop through a tunnel: `ssh -i bob.pem -L 8000:localhost:8000 linux1@148.100.108.187`, then open http://localhost:8000.
- TensorFlow lists only a CPU device in a bare check, even though ibm-zdnn-plugin is installed. Confirming that inference really runs on NNPA is part of #15.
