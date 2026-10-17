# Score Before You Sign — IBM Z Datathon 2026

Team project for the IBM Z Datathon 2026 (NTU Singapore hub), Theme 1: Real-Time AI for Critical Decisions.

**Sources of truth, in order:**
1. GitHub issue #1 (the current spec: "the first warning is the last payment") and tickets #2–#17.
2. `docs/team/{A,B,C,D}-*.md` (per-person tickets) and `docs/team/progress.md` (status tracker).
3. `docs/feasibility.md` (why the plan was reframed), `build-plan.md` (original plan, partly superseded).
4. Planning Google Doc: https://docs.google.com/document/d/1BevOh4bw-K3683Zw7YqBSPycdmGqBzBxnEwtsEBIUTQ/edit (text: `.../export?format=txt`). Its Spec tab predates the reframe.

## Deadline
- Hacking window: 17 Oct 2026 09:00 SGT → 18 Oct 2026 10:00 SGT. Closing ceremony 10:30 SGT.
- Submit on Hack2Skill (https://hack2skill.com/event/datathon-2026) well before 10:00 SGT on 18 Oct.

## The problem
Scammers (often posing as police or bank officers) persuade people to move savings in USDT to a "safe" wallet. The victim authorises the transfer, so OTPs and the Shared Responsibility Framework don't help, and on-chain transfers are irreversible. Victims rarely pay once, and several victims usually pay the same wallet: Tether freeze data shows frozen wallets keep receiving payments for a median of 129 days from the 2nd payment; 105 test wallets (Jul–Oct 2026) received 2,657 payments after their first.

**Where it sits:** in the withdrawal path of a regulated bank/custodian/exchange, just before the transaction is signed. (A bank cannot see an on-chain withdrawal it didn't originate — say this in the video.)

## The reframe (issue #1)
The single-wallet detector **failed** against volume-matched comparison wallets (AUC 0.57; 0.7% recall within 90 days of freeze at 1% false alarms — see `docs/feasibility.md`). So detection is no longer the headline.

**New claim: "the first warning is the last payment."** Once *any* warning about a destination wallet exists, later withdrawals to it — from any customer — are held for a call-back.
- Unusual withdrawals get one plain-language question (Granite, or templates); the customer's answer is the main scam signal.
- Warnings go into a shared **payee memory** keyed by destination wallet: a confirming answer, a customer report, a Tether freeze of the wallet or a counterparty (before `now`), an officer outcome, or a weak model flag.
- Headline = **Result 2**: in a replay of Tether-frozen wallets, payments held after the first available warning, split by warning source. Result 1 (lead time) is dropped from the pitch.
- Result 3: capacity-aware ladder vs rules-only / fixed threshold / call-everyone. Result 4: decide() p50/p99 latency and throughput, NNPA on vs off.

## Architecture: one deep module, the decision engine
- `decide(withdrawal, answer=None, now) -> decision`. Withdrawal = customer id, destination wallet, amount, time. Decision = tier (`release` / `warning` / `question` / `hold`), reasons (signals that fired, each with source and tagged real or modelled), expected loss for ranking.
- `record(event)`: officer outcomes (cleared / confirmed), customer reports, Tether freeze events → payee memory.
- **Injected dependencies:** history source (live: cached Blockscout fetcher; replay/tests: recorded histories), payee memory (SQLite-backed store; in-memory for tests), clock. The engine never reads wall-clock time or the network.
- **Tiering:** first-time payee or weak signal → warning. Unusual amount or moderate signal → question. Confirmed script, memory hit or counterparty freeze → hold. Holds ranked by expected loss (amount × signal-derived probability) under a daily officer capacity; overflow drops to question.
- Memory: unconfirmed warnings decay (half-life configurable; plan said 6 h, revisit given ~4-month wallet lifetimes). "Cleared" suppresses holds; "confirmed" pins with no decay.
- Decision log: append-only, hash-chained JSONL (previous hash + decision + inputs + engine version) with a verify step.
- API (D's tickets) is a thin wrapper: score, answer, officer queue, officer outcome, live address. No logic in the API.
- Granite sits behind a classifier interface: answer → {scam type, confirms script}. Tests use a stub; template questions are the fallback if Granite is missing or slower than 2 s.

## Team roles and tickets
| Role | Area | Tickets |
|---|---|---|
| A (Manan) | Data and problem | #2 done, #10 Result 2 replay, #16 demo wallet |
| B | Models and platform | #5 weak model signal, #11 deploy on LinuxONE, #15 NNPA benchmark |
| C (Aariv) | Router and simulation | #3 engine core → #6 payee memory + holds → #7 question tier, #9 capacity + Result 3 sweep |
| D | App and delivery | #4 score API, #8 question flow, #12 officer queue, #13 why-card, #14 Granite, #17 demo |

#3 blocks #4, #5 and #6, so it is on the critical path. Update only your own section of `progress.md`; pull before editing.

## Data (committed in `data/`, no Blockscout key needed)
- `freezes.csv`: every Tether USDT `AddedBlackList` event (address, time, block, tx, OFAC flag). The label and clock; OFAC addresses excluded (sanctions stay with existing controls).
- `known_bad.txt`: fesevu scam labels (static, ~2025).
- `histories/*.jsonl.gz`: one wallet per line `{address, group, freeze_ts, truncated, transfers[{ts, from, to, usdt, nonce, hash}]}`. Groups `{train,test}_{pos,neg,negv}`; `negv` = volume-matched comparison wallets. Test = frozen Jul–Oct 2026.
- `features.csv`, `sample.csv`: training rows with the 12 point-in-time features.
- History source for live use: Blockscout PRO API (`chain_id=1`, USDT `tokentx`). Only ~455 calls are left today — never pull without the cache; live use must fall back to the snapshot.
- Real vs modelled: Tether freezes, payment counts, amounts and timings are real. Customer answer rates, call-back stop rates, scam prevalence and friction are **modelled and swept** — label them on every slide.

## Code map
- `fetch.py`: cached Blockscout client (SQLite cache keyed by URL without the key, 4 req/s, 429 backoff, custom User-Agent, refuses bulk calls below 1,000 credits, errors never cached).
- `snapshot.py`: builds `data/` (costs credits; don't rerun).
- `features.py`: the ONE `features(history, as_of)` used everywhere; `python features.py` runs the no-future-leakage self-check. Its `touched_known_bad` logic is the counterparty-freeze signal.
- `feasibility.py`, `feasibility_extra.py`, `feasibility_young.py`: evidence for `docs/feasibility.md`.

## Testing style
- One seam: the decision engine. Tests call `decide`/`record` with recorded histories, in-memory memory and a fixed clock, and assert only on the returned decision — never internal state.
- Follow `features.py`: a small runnable assert-based check per module (`python module.py`), no test frameworks.
- Scenarios to cover: first-time payee warned; coached answer → hold; customer B held because of customer A; cleared stops holds; decay after N half-lives; over capacity the largest expected loss keeps the hold; a freeze after `now` is never used; model absent still decides.

## Platform: IBM LinuxONE Community Cloud
- One shared VM (Ubuntu 24.04, 3 vCPU, 8 GB RAM). User `linux1`, SSH key auth, `sudo`. VM owner: Manan.
- VM IP, key path and Jupyter token live in `vm.local.md` (gitignored). Never put them in a committed file.
- **s390x, big-endian.** Check every dependency there. Save models in an architecture-neutral format (no pickle across architectures).
- **NNPA available** (zDNN plugin) — Result 4. If zDNN won't run, report CPU numbers and don't claim NNPA.
- Jupyter Lab in Docker container `notebook` (lab image `registry.linuxone.cloud.marist.edu/l1cc/jupyterlab-image-s390x:latest`), port 38888. Host `~/shared` = container `/home/jovyan/shared`. Our container starts from the lab image; data, memory and `.env` are mounted volumes.
- Granite on the VM: `granite-4.0-h-350m-base-be.f16.gguf` (big-endian BASE model — few-shot prompts; see `Loan_Approval_Demo.ipynb`). Plan mentions granite-4.2-3b on llama.cpp zDNN.
- Mandatory labs before our build: `Fraud_LSTM_Keras_TF.ipynb` and `Loan_Approval_Demo.ipynb`.

## Workflow
1. Edit on laptop. 2. `git push` to `mananpansari/ibm-hackathon-2026`, branch `p1/data-pipeline` (default branch; feature branches like `aanya/setup` also exist). 3. On the VM: `cd ~/shared/project && git pull`. 4. Run there.
- Each teammate commits under their own GitHub account from their laptop (the VM uses a repo deploy key, not a person). Commit small and often.
- The repo is private; the rules need it public/accessible before submission.

## Judging (40 pts: 4 × 10, half-points)
1. Value to community & theme alignment 2. Novelty 3. Technical design & use of LinuxONE + open-source AI/ML (with screenshots) 4. Execution & pitch (3-min video).
- IBM Z is the biggest way to lose marks: clearly run on LinuxONE, be honest about what ran where.
- Scams against vulnerable people are on the judge's wishlist. Impact beats polish. Unfinished is fine with stated next steps; explain what was rejected and what failed (the detector no-go is a good story).
- Teamwork is scored: everyone contributes, visible commit history, roles in the write-up.

## Submission checklist
- [ ] Title: `[Team Name_IBM Z Datathon 2026 Project]`
- [ ] Video ≤ 3 min: problem, data, solution, LinuxONE stack + live demo
- [ ] Public repo with README linking all open-source libraries/datasets
- [ ] Event code SSF2026 in the LinuxONE project description
- [ ] Both mandatory labs completed
- [ ] Screenshots: portal instance page, `docker ps`, NNPA check, latency/throughput
- [ ] (Optional) Architecture flowchart, working prototype
- [ ] All code written during the event window

## Coding conventions
- Python 3.12, runnable on laptop and VM. Standard library where possible.
- Never hard-code keys; `BLOCKSCOUT_API_KEY` from env or `.env`, never logged or put in a URL that reaches a log, page or cache.
- Models, raw downloads and the API cache are not committed; snapshot outputs in `data/` are.
