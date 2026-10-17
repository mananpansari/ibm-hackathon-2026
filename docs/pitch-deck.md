# Pitch deck: Score Before You Sign

The slides behind the 3-minute video, plus backup slides for questions. The video's shot list and voice-over live in `docs/demo-script.md` (rewritten for UI v2 in PR #38); this deck follows its eight segments and uses **the same numbers from the same sources**. If a number changes there, change it here.

Written 18 Oct, about 01:45 SGT. Submission is due before 10:00 SGT; code freeze is 05:00.

## Rules for every slide

- **One idea per slide**, readable in 3 seconds. The voice-over carries the detail.
- **Real and modelled are never mixed.** Anything scripted or simulated gets a visible "modelled" tag: Mrs Tan's answers, the officer's confirmation, answer rates, officer accuracy, scam rate, stop rates.
- **Say "payments", not "victims"**: at most "up to N victims". **Never say "Ethereum fraud detection."**
- Say **"before the withdrawal is signed"** in the first 15 seconds.
- **Show what ran where**: the judges check that it runs on LinuxONE.
- Every slide shows one person's role at the bottom (teamwork is scored, and no one should dominate).

**Look:** a dark background for the title and story cards, light for the data slides. One accent colour for "held", grey for "released". Two fixed tag styles: a filled badge for **REAL** and an outlined badge for **MODELLED**. Charts get large labels and no 3D or gradients.

---

## Main deck (video order)

### 1. Title, 0:00
- **On slide:** "Score Before You Sign". Subtitle: *The first warning is the last payment.* Small: IBM Z Datathon 2026 · Theme 1: Real-Time AI for Critical Decisions · team name.
- **Say:** "Score Before You Sign checks every crypto withdrawal before it is signed, because once it's signed, it's gone."
- **Visual:** a withdrawal button with a pause symbol over it.

### 2. Mrs Tan, 0:05–0:20
- **On slide:** black, white text, one line at a time: *Mrs Tan, 68.* / *A "police officer" calls.* / *"Move your savings to a safe wallet."* / *She does it herself, with her own OTP.*
- **Point:** the victim authorises the payment, so passwords, OTPs and the Shared Responsibility Framework don't help.
- **Source:** SPF brief, 81.8% of cases were victim-made transfers.

### 3. The problem in numbers, 0:20–0:30
- **On slide (three big numbers):**
  - **S$242.9M**: lost to government-impersonation scams in Singapore, 2025
  - **34%**: of those victims aged 65+
  - **129 days**: median time Tether-frozen wallets kept collecting after their 2nd payment
- **Footer:** "Blacklists come too late: 105 frozen wallets received 2,657 payments after their first."
- **Sources:**
  - SPF Annual Scam & Cybercrime Brief 2025: S$242.9M, 3,363 cases, S$72,229 average, 34% aged 65+.
  - `docs/feasibility.md` §1–2: the 129 days, 105 wallets and 2,657 payments.
- **Check before recording:** the SPF figures against the PDF (CLAUDE.md lists some of them as unverified).

### 4. Where it sits, 0:30–0:45
- **On slide:** one diagram: **Exchange withdrawal flow → Score Before You Sign → HSM signing → blockchain**. Our box sits just before signing.
- **Caption:** "Embedded in the exchange's own withdrawal flow. A bank can't see an on-chain withdrawal it didn't originate."
- **Footnote:** "Production signing: IBM Digital Asset Haven on LinuxONE (Crypto Express 8S HSMs). The LinuxONE lab VM has no HSM, so our customer screen is a simulated stand-in."

### 5. How it decides (shown during the demo, 0:45–1:15)
- **On slide:** the four-step ladder, left to right: **Release → Warning → Question → Call-back hold**.
- Under it, three bullets:
  - **Ask, don't guess:** a large payment to a new payee gets up to three short questions. The answer is the main scam signal.
  - **One victim protects the next:** a confirming answer flags the wallet in a payee memory shared by every customer.
  - **Ration the call-backs:** holds are ranked by expected loss under the team's daily capacity.
- **Then cut to the live customer screens** (demo segment 3): 78,000 USDT to `0x74f6…c48b8` → questions → call-back hold. Badge: **MODELLED answers**.
- **Facts:**
  - Payment 2 is a real 78,000 USDT payment on 12 May 2026.
  - The engine itself asks, because it's a first-time payee at 1,000 USDT or more (`narration_numbers.json` → `ui_v2_spine`).

### 6. The officer's view (live, 1:15–1:40)
- **Live screens:** queue (Mrs Tan's case first by expected loss) → case view (her answers, "why this was held" with REAL/MODELLED tags, wallet record, payments graph) → record outcome "Cancel / confirmed scam". Badge: **MODELLED officer confirmation**.
- **Point:** the officer sees the reasons; the customer never does (she only sees plain-language text).

### 7. The replay: the first warning is the last payment (live, 1:40–1:55)
- **Live:** demo controls, Next through payments 3–13. Every one is held, the graph grows, and it ends on "Tether froze this wallet on 5 August 2026".
- **Overlay at the end:** **11 more payments held · 42,229 USDT · 79 more days of collecting · frozen 85 days after her hold.**
- **Source:** `narration_numbers.json` → `ui_v2_spine.officer_confirms`. Say "payments", not victims: the 11 include three test payments of about 10 USDT.
- **Limits line** (here or on slide 9): "Without a confirmation, a warning lasts only while payments keep coming."

### 8. Result 2: across every frozen wallet, 1:55–2:15
- **Two columns.**

| REAL | MODELLED |
|---|---|
| 134 wallets Tether froze, Jul–Oct 2026 | Half of the customers asked confirm the script; officers follow up (90% right) |
| 2,791 payments before the freeze | **≈1,920 payments held** (1,841–1,992 over 20 seeds) |
| Tether freezes alone: 3 flagged, **0 held** | Median **≈3 months** (98.6 days) before Tether's freeze |
| | Conservative, 1 in 10 confirms: ≈1,190 held (≈850 without officers) |

- **Footer:** *answer rate and officer accuracy modelled; 7-day half-life renewed by each held attempt.*
- **Source:** `docs/results.md`, `data/results/replay_summary.json`.
- **Don't** quote a single legitimate-hold rate: holds concentrate on very busy payees.

### 9. What we tried and dropped (one line in the video, 2:15–2:25)
- **On slide:** "We first built a scam-wallet detector. Against wallets of similar size it scored **AUC 0.57**, near chance. So we dropped it and **ask the customer instead**."
- **Small print:** the model stays as one weak signal that can only ask a question, never hold.
- **Source:** `docs/feasibility.md` Verdict; `docs/results1.md`.
- Judges reward explaining what failed: say it plainly, without apologising.

### 10. Result 3: why ration the call-backs (optional, if time allows)
- **Chart:** `docs/result3.svg`: share of scam money averted against call-backs per day, with four lines (ladder, rules-only, fixed threshold, call everyone).
- **Headline:** "At 100 call-backs a day, the ladder stops **36%** of scam money, against **7%** for the best simpler policy." (0.5% scam rate.) Badge: **MODELLED** inputs (scam rate, answer and stop rates, officer accuracy). Real payments and amounts.
- **Source:** `docs/result3.md`.
- **Cost line:** "We ask about **1 in 8** payments to wallets this busy" (12.3% volume-matched, 4.5% random; `docs/results.md`, Questions table).
- **Watch out:** the ladder's lead partly rests on the modelled stop rate for a question.

### 11. Runs on IBM LinuxONE, 2:25–2:50
- **Live / screenshots:** the LinuxONE Community Cloud portal instance page → terminal `docker ps` (app container from the lab image) → benchmark output → the demo strip showing "LinuxONE".
- **On slide (three facts):**
  - **≈1.3 ms** per decision (p50), **600–750 withdrawals/s** on one thread, 3 vCPU VM.
  - **NNPA verified**; the model ran on it, with **no speed-up** at this size, so we don't claim one.
  - Everything runs in Docker on s390x. Granite runs locally: about 4 s per answer on this VM, so the live questions use templates and a keyword classifier.
- **Sources:** `docs/nnpa-benchmark.md` (#15); `docs/team/progress.md` #14 and #11 rows; `docs/screenshots/`.

### 12. Close, 2:50–3:00
- **On slide:** "Score before you sign." Three next steps: **signing inside Digital Asset Haven HSMs · sharing confirmed wallets between banks · more languages**. Team names and roles. Repo URL.

---

## Backup slides (Q&A, not in the video)

### B1. Team and roles
| Person | Role | Built |
|---|---|---|
| Aanya (A) | Data and problem, results, demo story | Result 2 replay, demo wallet and narration numbers, idea doc, live-box hardening, UI v2 backend |
| Manan (B) | Data pipeline, models and platform | Snapshot and feasibility test, weak model (XGBoost + MLP), LinuxONE deploy, NNPA benchmark |
| Aariv (C) | Decision engine and simulation | Engine, payee memory, question tier, officer capacity, tamper-evident log, Result 3, model scorecard |
| Advay (D) | App and delivery | Customer page, officer console, why-card and graph, Granite integration, demo spine, screenshots |

### B2. How we score on the judging criteria
| Criterion | Our evidence |
|---|---|
| Value to community & theme | Elderly victims of impersonation scams; a real-time decision before an irreversible transfer; most of the loss is in the repeat payments we stop |
| Novelty | Not wallet detection: a payee memory shared across customers, plus one question back, so one customer's warning protects the next |
| Technical design & LinuxONE | One tested decision engine, point-in-time everywhere, hash-chained log; measured latency and NNPA on LinuxONE; Docker on s390x; local Granite |
| Execution & pitch | Live demo on a real wallet Tether later froze; a paste-any-address box for judges; real vs modelled labelled; an honest failure story |

### B3. Trust and responsible AI
- No hard block: a hold is a call-back with a human, who can release it. An officer's "cleared" stops future holds on that wallet.
- The customer sees plain-language reasons only; the officer sees every reason, tagged real or modelled.
- Every decision and officer outcome goes into an append-only, hash-chained log (`decision_log.py`), with a verify step.
- Customer answers stay on the box. OFAC wallets stay with existing sanctions controls.

### B4. Honest limits
- Ethereum USDT only. No HSM on the lab VM, so signing is the described production path.
- The wallet model is weak (AUC about 0.6 against similar-sized wallets). It's one signal, not the product.
- Answer rates, officer accuracy, stop rates and scam rate are modelled and swept, not measured.
- Tether freezes include hacks as well as scams. We count payments, not people.
- Legitimate friction concentrates on very busy payees.

### B5. Data we used
- Tether USDT `AddedBlackList` events (the label and clock).
- Blockscout USDT histories (one call per wallet).
- fesevu scam labels; the OFAC list (removed from the data).
- BothBosu scam dialogues, plus our own Singapore answers (classifier test).
- SPF Scam & Cybercrime Brief 2025.

Links are in the idea doc's sources. Kaggle and Elliptic++ were considered and **not** used, because their features can't be computed live.

### B6. If asked about the model
- **Scorecard:** `docs/model_scores.md` (`model_report.py`, PR #36): ensemble AUC 0.596 against volume-matched wallets, out of time.
- **Experiment (not in the product):** `aariv/model-v2`, a payment-level model with 26 features. It ranks payments better (AUC 0.814 vs 0.761 per payment) but catches fewer wallets at 5% (14 vs 22 of 134). Kept as research (`docs/model_v2.md`).
- **PR #37** moves the model's question cut-off from a 1% to a 5% false-alarm budget. A model flag only asks, never holds, and a question is cheap.

---

## Before recording: checklist

- [ ] PR #38 (UI v2 backend and the rewritten demo script) is merged, and the demo runs on the VM with `/demo/reset` then 13 × `/demo/next`.
- [ ] If PR #37 (model flag at 5%) is merged, Aanya re-runs Result 2 and the question counts on slides 8 and 10 are updated. If it isn't merged by recording time, keep today's numbers.
- [ ] SPF figures on slide 3 checked against the PDF.
- [ ] Every MODELLED badge is visible on screen when its number appears.
- [ ] LinuxONE portal page, `docker ps` and the benchmark screenshots captured (judges check these).
- [ ] The repo is public, and the README lists the libraries and datasets.
- [ ] The voice-over is read once against a timer (target about 420 words in 3:00), cutting the lines marked *(cut first)* in `docs/demo-script.md` if it runs over.
