# Progress

Everyone edits **only their own section** here. Separate sections keep merge conflicts away; pull before you edit and commit small.

**Status:** `todo` · `blocked` · `doing` · `review` · `done`. When a ticket is done, also close its GitHub issue.

Per-person ticket details: [A: Data and problem](A-data-and-problem.md) · [B: Models and platform](B-models-and-platform.md) · [C: Router and simulation](C-router-and-simulation.md) · [D: App and delivery](D-app-and-delivery.md)

## A: Data and problem

| Ticket | Title | Blocked by | Status | Updated | Notes |
|---|---|---|---|---|---|
| [#2](https://github.com/mananpansari/ibm-hackathon-2026/issues/2) | Commit P1 snapshot and feasibility evidence | - | done | 17 Oct | Snapshot + feasibility committed (5be122e) |
| [#10](https://github.com/mananpansari/ibm-hackathon-2026/issues/10) | Result 2 replay through the engine | #2, #6 | blocked |  |  |
| [#16](https://github.com/mananpansari/ibm-hackathon-2026/issues/16) | Demo wallet and narration numbers | #10 | blocked |  |  |

## B: Models and platform

| Ticket | Title | Blocked by | Status | Updated | Notes |
|---|---|---|---|---|---|
| [#5](https://github.com/mananpansari/ibm-hackathon-2026/issues/5) | Weak model signal | #3 | doing | 17 Oct | Models trained + saved (models/, val AUC 0.87 by wallet; out-of-time 0.57 vs matched). `model.score(features) -> float or None`, 1.5 ms on TF 2.21. Engine wiring waits on #3. Branch b/5-weak-model-signal |
| [#11](https://github.com/mananpansari/ibm-hackathon-2026/issues/11) | Deploy on LinuxONE | #4 | done | 17 Oct | Running on VM bob1 from the lab image (127.0.0.1:8000, stub engine); verified via SSH tunnel with 5 test cases. Not public: port not opened. Branch b/11-deploy-linuxone (merge after #4) |
| [#15](https://github.com/mananpansari/ibm-hackathon-2026/issues/15) | NNPA benchmark (Result 4) | #5, #11 | blocked |  |  |

## C: Router and simulation

| Ticket | Title | Blocked by | Status | Updated | Notes |
|---|---|---|---|---|---|
| [#3](https://github.com/mananpansari/ibm-hackathon-2026/issues/3) | Decision engine core: release or warn, logged | - | review | 17 Oct | PR from `aariv/c-decision-engine`; self-checks pass on laptop and LinuxONE (s390x) |
| [#6](https://github.com/mananpansari/ibm-hackathon-2026/issues/6) | Shared payee memory and call-back hold | #3 | review | 17 Oct | PR #19 (stacked on #18; merge #18 first). Self-checks pass on laptop and LinuxONE (s390x) |
| [#7](https://github.com/mananpansari/ibm-hackathon-2026/issues/7) | Question tier in the engine | #6 | todo | 17 Oct | Can start on top of #6's branch |
| [#9](https://github.com/mananpansari/ibm-hackathon-2026/issues/9) | Capacity-aware holds and Result 3 sweep | #6 | todo | 17 Oct | Can start on top of #6's branch |

## D: App and delivery

| Ticket | Title | Blocked by | Status | Updated | Notes |
|---|---|---|---|---|---|
| [#4](https://github.com/mananpansari/ibm-hackathon-2026/issues/4) | Score API and bare customer page | #3 | review | 17 Oct | Wired to C's engine.py (#3/#6); stub deleted |
| [#8](https://github.com/mananpansari/ibm-hackathon-2026/issues/8) | Customer question flow | #4, #7 | blocked | 17 Oct | Page + /answer done; engine has no question tier until #7, so nothing asks yet. Interim bridge in app.py records a confirming answer as a Report |
| [#12](https://github.com/mananpansari/ibm-hackathon-2026/issues/12) | Officer queue and outcomes | #4, #6, #9 | review | 17 Oct | On C's engine: holds from payee memory, cleared/confirmed via record(OfficerOutcome); queue ranked in app.py until #9 |
| [#13](https://github.com/mananpansari/ibm-hackathon-2026/issues/13) | Why-card and payment graph | #12 | review | 17 Oct | Why-card shows engine reasons with real/modelled tags + memory evidence; Cytoscape 3.30.2 (SRI) graph |
| [#14](https://github.com/mananpansari/ibm-hackathon-2026/issues/14) | Granite asks and classifies | #7 | doing | 17 Oct | granite.py: GRANITE_GGUF runs the VM's base model in-process (llama_cpp_python, few-shot classify; questions templated) or llama-server; 2 s + keyword fallback. Keyword fallback: BothBosu 68%, SG 30/30 (optimistic). Needs a VM run for Granite's number |
| [#17](https://github.com/mananpansari/ibm-hackathon-2026/issues/17) | Demo spine and live address box | #8, #11, #13, #14, #16 | doing | 17 Oct | Demo: customer 1's coached answer, customer 2 held, scripted officer confirm (modelled), every later payment held to the freeze. /live with snapshot fallback. Needs #16 wallet (DEMO_WALLET) + VM run |

## Log

Short dated lines for anything others need to know (decisions, blockers, handovers).

- 17 Oct (A): Snapshot and feasibility evidence committed; detector reframed per #1.
- 17 Oct (D): #4 score API + customer page on `advay/app-and-delivery`, running on a stub with #1's decide() shape. C: if your decision dict differs from engine_stub.py's docstring, tell me.
- 17 Oct (D): App side of #4 #8 #12 #13 built on `engine_stub.py`, whose docstring is the engine contract the app needs (decide/record/queue/case). C: please match it or tell D. A: set DEMO_WALLET for #16. B: `uvicorn app:app` is what #11 deploys.
- 17 Oct (C): Added CLAUDE.md (project guide for Claude Code, follows #1 and the team docs). Starting #3 next.
- 17 Oct (C): #3 interface ready for B (#5) and D (#4): `Engine(history, memory, clock, log).decide(Withdrawal(customer_id, wallet, amount_usdt, ts))` -> `Decision(tier, reasons, p_scam, expected_loss, ...)`; `engine.to_dict()` for JSON. Base rate is modelled (`Config`).
- 17 Oct (C): #6 decisions: report half-life 7 days (not 6 h), one report holds other customers' payments, latest officer outcome wins, transfers under 10 USDT never link wallets. Finding for #10 (A): with Tether freezes only (no reports), 0/765 payments to 25 frozen test wallets were held (0/9,787 on volume-matched), so Result 2 rests on customer reports/answers, which are modelled.
- 17 Oct (C): #6 in review (PR #19, stacked on #3's PR #18). Unblocks #10 (A) and #12 (D): call `engine.record(Report/OfficerOutcome/Freeze)`; load Tether freezes with `engine.memory.add_freezes(payee_memory.load_freezes())`; replay reports should use `Report(..., kind="modelled")`.
- 17 Oct (D): app.py now runs on C's engine (merged `aariv/c6-payee-memory` into `advay/app-and-delivery`). Notes for C: (1) PayeeMemory's SQLite connection is per-thread, so the app runs engine routes on one thread (async); (2) the app needs `question` tier + answer handling (#7) and a ranked queue (#9) to drop its interim bridge and sort; (3) with the 7-day half-life the demo only holds payments within ~7 days of the first warning, so the demo wallet needs a quick 2nd payment (A, #16).
- 17 Oct (B): #5 model signal ready as `model.score(feats)`; returns None when models are missing so the engine can decide without it. Trained on the TensorFlow backend (TF 2.21 locally) so the same file loads under TF/zDNN on the VM; don't train on torch (loading imports torch and crashes alongside TF).
- 17 Oct (B): App container runs on LinuxONE VM bob1 behind localhost; tunnel to view. TF shows CPU only despite ibm-zdnn-plugin: verify in #15.
- 17 Oct (D): Decision for #17/#16: the demo INCLUDES the officer confirming the scam (scripted, labelled modelled), so the line is "the engine holds all of them once an officer confirms"; the fade is one sentence on limits ("without a confirmation, one warning fades after about a week"). Built on `advay/app-and-delivery`.
- 17 Oct (D): App now passes B's model.score + known_bad into C's Engine (merged C's d1307d4); verified the model_score reason with xgboost. C: OfficerOutcome has no real/modelled `kind`, so the app relabels the demo's scripted confirm as modelled; a `kind` field would let the engine do it. B: Dockerfile now also copies advisories.txt (granite.py needs it); the slim base has no numpy, so there the model signal is off.
