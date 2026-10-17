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
| [#6](https://github.com/mananpansari/ibm-hackathon-2026/issues/6) | Shared payee memory and call-back hold | #3 | review | 17 Oct | PR #19 (stacked on #18; merge #18 first). Updated from A's replay: holds renew, counterparty freeze only warns, `Engine(model=model.score)` hook. Self-checks pass on laptop and LinuxONE |
| [#7](https://github.com/mananpansari/ibm-hackathon-2026/issues/7) | Question tier in the engine | #6 | review | 17 Oct | PR #22 (stacked on #19). D's app runs end to end on it with a 3-line app.py change (in the PR); self-checks pass on laptop and LinuxONE |
| [#9](https://github.com/mananpansari/ibm-hackathon-2026/issues/9) | Capacity-aware holds and Result 3 sweep | #6 | todo | 17 Oct | Can start on top of #6's branch |

## D: App and delivery

| Ticket | Title | Blocked by | Status | Updated | Notes |
|---|---|---|---|---|---|
| [#4](https://github.com/mananpansari/ibm-hackathon-2026/issues/4) | Score API and bare customer page | #3 | done | 17 Oct | Wired to C's engine.py (#3/#6); stub deleted |
| [#8](https://github.com/mananpansari/ibm-hackathon-2026/issues/8) | Customer question flow | #4, #7 | done | 17 Oct | On C's #7 engine: large new payee gets the question, free-text answer, hold with calm call-back message or release. Bridge removed; customer page hides modelled config reasons |
| [#12](https://github.com/mananpansari/ibm-hackathon-2026/issues/12) | Officer queue and outcomes | #4, #6, #9 | done | 17 Oct | On C's engine: holds from payee memory, cleared/confirmed via record(OfficerOutcome); queue ranked in app.py until #9 |
| [#13](https://github.com/mananpansari/ibm-hackathon-2026/issues/13) | Why-card and payment graph | #12 | done | 17 Oct | Why-card shows engine reasons (real/modelled), the answer, memory evidence incl. the warning this decision created; Cytoscape 3.30.2 (SRI) graph |
| [#14](https://github.com/mananpansari/ibm-hackathon-2026/issues/14) | Granite asks and classifies | #7 | doing | 17 Oct | granite.py: GRANITE_GGUF runs the VM's base model in-process (llama_cpp_python, few-shot classify; questions templated) or llama-server; 2 s + keyword fallback. Keyword fallback: BothBosu 68%, SG 30/30 (optimistic). Needs a VM run for Granite's number |
| [#17](https://github.com/mananpansari/ibm-hackathon-2026/issues/17) | Demo spine and live address box | #8, #11, #13, #14, #16 | doing | 17 Oct | Demo on A's wallet 0x74f6…48b8: customers = sending wallets (payments 1-2 are customer-1), customer-2 (payment 3) held, scripted officer confirm (modelled), all 12 after payment 1 held to the 5 Aug freeze; no counts on screen. /live with snapshot fallback. Needs a VM run |

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
- 17 Oct (D): Demo per A's checks: on-screen customers follow the sending wallet (payments 1 and 2 are both customer-1), the officer confirm follows the first different customer's hold (payment 3), no payment counts shown. Default DEMO_WALLET is 0x74f645934fd288dfcb6359870779f68c2b0c48b8; A, confirm that's yours.
- 17 Oct (C): Fixed the three issues Aanya's #10 replay found (pushed to PR #19): (1) each held payment renews the report (same real/modelled kind), so holds no longer fade after 7 days while victims keep paying; officer "cleared" ends it. (2) Counterparty Tether freeze is now a weak signal: warning, never hold (p 0.02). (3) `Engine(..., model=model.score, known_bad=...)` adds B's score as `model_flag` (>= `Config.model_flag`, default 0.9, warns) or `model_score` (informational). #10 should re-run.
- 17 Oct (C): #7 question tier: first-time payee >= 1,000 USDT (`Config.large_usdt`) or weak evidence (counterparty freeze, model flag) -> question; `decide(w, answer=...)` re-decides: confirming -> hold + `Report(source="customer_answer")` for everyone, clean -> release. `Engine(classifier=granite)` uses D's ask/classify (template if it fails). Replay of 100 wallets each, no reports: questions on 53% of payments to frozen wallets vs 14% to volume-matched ones.
- 17 Oct (C): #7 in review (PR #22). For D: D's app already runs on C's engine; with #7, pass `classifier=granite` to Engine and replace the `answered()` bridge with `decide(w, answer, answer_kind)` (patch in PR #22). Tested end to end with FastAPI's test client. Also fixed: payee memory can now be used from another thread.
- 17 Oct (A): Idea doc updated per build plan §10 on branch aanya/idea-doc (docs/score-before-you-sign.md), awaiting review; not merged.
- 17 Oct (D): Merged `aariv/c7-question-tier` (PR #22) and applied C's patch: Engine(classifier=granite), answer_kind passed through, answered() bridge gone; why-card reads evidence at time + 1. Tested the full customer question flow in the browser and the demo on A's wallet (all 12 after payment 1 held). C: DecisionLog keeps the last hash in memory, so a second process appending to the same decisions.jsonl while the server runs forks the chain (verify fails); a lock or re-reading the tail before append would prevent it.
- 17 Oct (D): #4, #8, #12, #13 done (all acceptance criteria met on C's engine, tested in the browser). #14 needs Granite measured on the VM; #17 needs the full demo run on the VM.
- 17 Oct (A): fetch.py hardened for the live box on branch `aanya/fetch-live` (live lookups work down to 100 credits while bulk pulls stop below 1,000; one 6 s attempt, no retries; address validation; per-thread SQLite + locked 4 req/s throttle, which fixes a cross-thread crash; key never in errors/logs/cache). New `snapshot.live_history(addr)` never raises and returns a status (ok / no_transfers / not_a_wallet / too_much_history / no_credits / unavailable / invalid). Mocked tests: `python tests/test_fetch.py`. Awaiting review, not merged. D: app.py works unchanged; optional: show live_history's status message in /live.
