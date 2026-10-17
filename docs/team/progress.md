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
| [#11](https://github.com/mananpansari/ibm-hackathon-2026/issues/11) | Deploy on LinuxONE | #4 | blocked |  |  |
| [#15](https://github.com/mananpansari/ibm-hackathon-2026/issues/15) | NNPA benchmark (Result 4) | #5, #11 | blocked |  |  |

## C: Router and simulation

| Ticket | Title | Blocked by | Status | Updated | Notes |
|---|---|---|---|---|---|
| [#3](https://github.com/mananpansari/ibm-hackathon-2026/issues/3) | Decision engine core: release or warn, logged | - | review | 17 Oct | PR from `aariv/c-decision-engine`; self-checks pass on laptop and LinuxONE (s390x) |
| [#6](https://github.com/mananpansari/ibm-hackathon-2026/issues/6) | Shared payee memory and call-back hold | #3 | review | 17 Oct | PR #19 (stacked on #18; merge #18 first). Updated from A's replay: holds renew, counterparty freeze only warns, `Engine(model=model.score)` hook. Self-checks pass on laptop and LinuxONE |
| [#7](https://github.com/mananpansari/ibm-hackathon-2026/issues/7) | Question tier in the engine | #6 | review | 17 Oct | PR #22 (stacked on #19). D's app runs end to end on it with a 3-line app.py change (in the PR); self-checks pass on laptop and LinuxONE |
| [#9](https://github.com/mananpansari/ibm-hackathon-2026/issues/9) | Capacity-aware holds and Result 3 sweep | #6 | todo | 17 Oct | Can start on top of #6's branch |

## D: App and delivery

| Ticket | Title | Blocked by | Status | Updated | Notes |
|---|---|---|---|---|---|
| [#4](https://github.com/mananpansari/ibm-hackathon-2026/issues/4) | Score API and bare customer page | #3 | blocked |  |  |
| [#8](https://github.com/mananpansari/ibm-hackathon-2026/issues/8) | Customer question flow | #4, #7 | blocked |  |  |
| [#12](https://github.com/mananpansari/ibm-hackathon-2026/issues/12) | Officer queue and outcomes | #4, #6, #9 | blocked |  |  |
| [#13](https://github.com/mananpansari/ibm-hackathon-2026/issues/13) | Why-card and payment graph | #12 | blocked |  |  |
| [#14](https://github.com/mananpansari/ibm-hackathon-2026/issues/14) | Granite asks and classifies | #7 | blocked |  |  |
| [#17](https://github.com/mananpansari/ibm-hackathon-2026/issues/17) | Demo spine and live address box | #8, #11, #13, #14, #16 | blocked |  |  |

## Log

Short dated lines for anything others need to know (decisions, blockers, handovers).

- 17 Oct (A): Snapshot and feasibility evidence committed; detector reframed per #1.
- 17 Oct (C): Added CLAUDE.md (project guide for Claude Code, follows #1 and the team docs). Starting #3 next.
- 17 Oct (C): #3 interface ready for B (#5) and D (#4): `Engine(history, memory, clock, log).decide(Withdrawal(customer_id, wallet, amount_usdt, ts))` -> `Decision(tier, reasons, p_scam, expected_loss, ...)`; `engine.to_dict()` for JSON. Base rate is modelled (`Config`).
- 17 Oct (C): #6 decisions: report half-life 7 days (not 6 h), one report holds other customers' payments, latest officer outcome wins, transfers under 10 USDT never link wallets. Finding for #10 (A): with Tether freezes only (no reports), 0/765 payments to 25 frozen test wallets were held (0/9,787 on volume-matched), so Result 2 rests on customer reports/answers, which are modelled.
- 17 Oct (C): #6 in review (PR #19, stacked on #3's PR #18). Unblocks #10 (A) and #12 (D): call `engine.record(Report/OfficerOutcome/Freeze)`; load Tether freezes with `engine.memory.add_freezes(payee_memory.load_freezes())`; replay reports should use `Report(..., kind="modelled")`.
- 17 Oct (C): Fixed the three issues Aanya's #10 replay found (pushed to PR #19): (1) each held payment renews the report (same real/modelled kind), so holds no longer fade after 7 days while victims keep paying; officer "cleared" ends it. (2) Counterparty Tether freeze is now a weak signal: warning, never hold (p 0.02). (3) `Engine(..., model=model.score, known_bad=...)` adds B's score as `model_flag` (>= `Config.model_flag`, default 0.9, warns) or `model_score` (informational). #10 should re-run.
- 17 Oct (C): #7 question tier: first-time payee >= 1,000 USDT (`Config.large_usdt`) or weak evidence (counterparty freeze, model flag) -> question; `decide(w, answer=...)` re-decides: confirming -> hold + `Report(source="customer_answer")` for everyone, clean -> release. `Engine(classifier=granite)` uses D's ask/classify (template if it fails). Replay of 100 wallets each, no reports: questions on 53% of payments to frozen wallets vs 14% to volume-matched ones.
- 17 Oct (C): #7 in review (PR #22). For D: D's app already runs on C's engine; with #7, pass `classifier=granite` to Engine and replace the `answered()` bridge with `decide(w, answer, answer_kind)` (patch in PR #22). Tested end to end with FastAPI's test client. Also fixed: payee memory can now be used from another thread.
- 17 Oct (C): Review fixes on PR #22. (1) For D: decisions now carry `customer_reasons` (plain text safe for the customer page); `reasons` keeps everything with an `audience` tag for the why-card. The customer page currently shows modelled priors like "Assumed scam rate 0.5% x 2" to customers; switch it to `d.customer_reasons`. (2) `Config.model_flag` = 0.78, measured: flags 1% of comparison-wallet payments and 16.8% of frozen-wallet payments (24,522 test payments, B's models in the lab container). (3) Partial `Config(p_signal=...)` overrides keep the other defaults.
