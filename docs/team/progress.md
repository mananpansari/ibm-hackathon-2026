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
| [#11](https://github.com/mananpansari/ibm-hackathon-2026/issues/11) | Deploy on LinuxONE | #4 | doing | 17 Oct | Dockerfile + vm_check.sh + run steps on b/11-deploy-linuxone; app tested locally; VM SSH refused on port 20882, needs access |
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
| [#4](https://github.com/mananpansari/ibm-hackathon-2026/issues/4) | Score API and bare customer page | #3 | blocked | 17 Oct | Built and tested on engine_stub.py; swap the import in app.py when #3 lands |
| [#8](https://github.com/mananpansari/ibm-hackathon-2026/issues/8) | Customer question flow | #4, #7 | blocked |  |  |
| [#12](https://github.com/mananpansari/ibm-hackathon-2026/issues/12) | Officer queue and outcomes | #4, #6, #9 | blocked |  |  |
| [#13](https://github.com/mananpansari/ibm-hackathon-2026/issues/13) | Why-card and payment graph | #12 | blocked |  |  |
| [#14](https://github.com/mananpansari/ibm-hackathon-2026/issues/14) | Granite asks and classifies | #7 | blocked |  |  |
| [#17](https://github.com/mananpansari/ibm-hackathon-2026/issues/17) | Demo spine and live address box | #8, #11, #13, #14, #16 | blocked |  |  |

## Log

Short dated lines for anything others need to know (decisions, blockers, handovers).

- 17 Oct (A): Snapshot and feasibility evidence committed; detector reframed per #1.
- 17 Oct (D): #4 score API + customer page on `advay/app-and-delivery`, running on a stub with #1's decide() shape. C: if your decision dict differs from engine_stub.py's docstring, tell me.
