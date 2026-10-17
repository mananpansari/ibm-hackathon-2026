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
| [#5](https://github.com/mananpansari/ibm-hackathon-2026/issues/5) | Weak model signal | #3 | blocked |  |  |
| [#11](https://github.com/mananpansari/ibm-hackathon-2026/issues/11) | Deploy on LinuxONE | #4 | done | 17 Oct | Running on VM bob1 from the lab image (127.0.0.1:8000, stub engine); verified via SSH tunnel with 5 test cases. Not public: port not opened. Branch b/11-deploy-linuxone (merge after #4) |
| [#15](https://github.com/mananpansari/ibm-hackathon-2026/issues/15) | NNPA benchmark (Result 4) | #5, #11 | blocked |  |  |

## C: Router and simulation

| Ticket | Title | Blocked by | Status | Updated | Notes |
|---|---|---|---|---|---|
| [#3](https://github.com/mananpansari/ibm-hackathon-2026/issues/3) | Decision engine core: release or warn, logged | - | todo |  |  |
| [#6](https://github.com/mananpansari/ibm-hackathon-2026/issues/6) | Shared payee memory and call-back hold | #3 | blocked |  |  |
| [#7](https://github.com/mananpansari/ibm-hackathon-2026/issues/7) | Question tier in the engine | #6 | blocked |  |  |
| [#9](https://github.com/mananpansari/ibm-hackathon-2026/issues/9) | Capacity-aware holds and Result 3 sweep | #6 | blocked |  |  |

## D: App and delivery

| Ticket | Title | Blocked by | Status | Updated | Notes |
|---|---|---|---|---|---|
| [#4](https://github.com/mananpansari/ibm-hackathon-2026/issues/4) | Score API and bare customer page | #3 | review | 17 Oct | Wired to C's engine.py (#3/#6); stub deleted |
| [#8](https://github.com/mananpansari/ibm-hackathon-2026/issues/8) | Customer question flow | #4, #7 | blocked | 17 Oct | Page + /answer done; engine has no question tier until #7, so nothing asks yet. Interim bridge in app.py records a confirming answer as a Report |
| [#12](https://github.com/mananpansari/ibm-hackathon-2026/issues/12) | Officer queue and outcomes | #4, #6, #9 | review | 17 Oct | On C's engine: holds from payee memory, cleared/confirmed via record(OfficerOutcome); queue ranked in app.py until #9 |
| [#13](https://github.com/mananpansari/ibm-hackathon-2026/issues/13) | Why-card and payment graph | #12 | review | 17 Oct | Why-card shows engine reasons with real/modelled tags + memory evidence; Cytoscape 3.30.2 (SRI) graph |
| [#14](https://github.com/mananpansari/ibm-hackathon-2026/issues/14) | Granite asks and classifies | #7 | doing | 17 Oct | granite.py ask/classify + 2 s fallback + advisories.txt + eval. Keyword fallback: BothBosu 68%, SG 30/30 (optimistic, same author). Needs Granite on the VM for the real number |
| [#17](https://github.com/mananpansari/ibm-hackathon-2026/issues/17) | Demo spine and live address box | #8, #11, #13, #14, #16 | doing | 17 Oct | /live (cached client, 1,000-credit guard, 8 s snapshot fallback) + /demo replay with coached 1st answer; needs #16 wallet (DEMO_WALLET) and VM run |

## Log

Short dated lines for anything others need to know (decisions, blockers, handovers).

- 17 Oct (A): Snapshot and feasibility evidence committed; detector reframed per #1.
- 17 Oct (D): #4 score API + customer page on `advay/app-and-delivery`, running on a stub with #1's decide() shape. C: if your decision dict differs from engine_stub.py's docstring, tell me.
- 17 Oct (D): App side of #4 #8 #12 #13 built on `engine_stub.py`, whose docstring is the engine contract the app needs (decide/record/queue/case). C: please match it or tell D. A: set DEMO_WALLET for #16. B: `uvicorn app:app` is what #11 deploys.
- 17 Oct (D): app.py now runs on C's engine (merged `aariv/c6-payee-memory` into `advay/app-and-delivery`). Notes for C: (1) PayeeMemory's SQLite connection is per-thread, so the app runs engine routes on one thread (async); (2) the app needs `question` tier + answer handling (#7) and a ranked queue (#9) to drop its interim bridge and sort; (3) with the 7-day half-life the demo only holds payments within ~7 days of the first warning, so the demo wallet needs a quick 2nd payment (A, #16).
- 17 Oct (B): App container runs on LinuxONE VM bob1 behind localhost; tunnel to view. TF shows CPU only despite ibm-zdnn-plugin: verify in #15.
