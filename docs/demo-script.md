# Demo script (#16, rewritten for UI v2)

The 3-minute video, shot by shot: what is on screen, the voice-over, and where every number comes from. It follows the UI v2 screens (`docs/team/ui-v2.md`) and issue #1's framing: **the first warning is the last payment**.

**Budget:** 180 s at about 150 words a minute is about 450 spoken words. The voice-over below is about 420, so there's room for pauses. Read it once against a timer before recording; if it runs over, cut the lines marked *(cut first)*.

**Rules**
- Say "before the withdrawal is signed" in the first 15 seconds.
- Say **payments**, not victims ("up to N victims" at most). Never say "Ethereum fraud detection".
- Anything scripted or simulated is labelled **modelled** on screen when it appears: Mrs Tan's answers, the officer's confirmation, answer rates and officer accuracy.
- Say plainly that the product is embedded in an exchange's withdrawal flow and that our customer page is a simulated stand-in.
- Show LinuxONE live (portal, `docker ps`, the app running on the VM), and be honest about what ran where.

**Sources**
- Demo wallet facts (real): `data/demo/0x74f645934fd288dfcb6359870779f68c2b0c48b8.json` (`python demo_candidates.py --export 3`).
- Demo engine numbers: `data/demo/narration_numbers.json` → `ui_v2_spine` (`python demo_candidates.py --numbers 0x74f645934fd288dfcb6359870779f68c2b0c48b8`), the app's own engine path (`answers.StructuredClassifier`).
- Results across all wallets: `docs/results.md`, `data/results/replay_summary.json` (Result 2); `docs/result3.md` (Result 3); `docs/nnpa-benchmark.md` (Result 4); `docs/feasibility.md` (the detector no-go).

---

## At a glance

| Time | Segment | Screen |
|---|---|---|
| 0:00–0:30 | 1. Problem | Title card, then Mrs Tan's phone call (text on black), stats card |
| 0:30–0:45 | 2. Where it sits | Simple diagram: exchange app → **Score Before You Sign** → signing → blockchain; then the customer page's "simulated exchange withdrawal screen" banner |
| 0:45–1:15 | 3. Customer screens | Customer page: withdrawal → check → Q1 → Q2 → Q3 → call-back hold |
| 1:15–1:40 | 4. Officer screens | Officer console: queue → case view (why-card, wallet record, graph) → record outcome "confirmed" |
| 1:40–1:55 | 5. The replay | Officer console demo controls: Next × 11, every payment held, then the freeze date |
| 1:55–2:25 | 6. Results | Results slide: real vs modelled in two columns; the "what we tried and dropped" line |
| 2:25–2:50 | 7. LinuxONE | LinuxONE portal, terminal `docker ps`, latency numbers, demo strip showing "LinuxONE" |
| 2:50–3:00 | 8. Close | Title card: next steps, team names and roles, repo link |

---

## 1. Problem (0:00–0:30)

**Screen:** title card "Score Before You Sign". Then black with white text, one line at a time, then the stats card.

> Score Before You Sign checks every crypto withdrawal **before it is signed**, because once it's signed, it's gone.
>
> Mrs Tan is 68. A "police officer" calls: her savings are linked to a crime, and she must move them to a "safe wallet". She does it herself, with her own OTP, so no security check stops it.
>
> She isn't rare. Government-impersonation scams cost Singapore S$242.9 million in 2025, and a third of the victims were 65 or older. Blacklists come too late: wallets Tether froze kept collecting payments for a median of 129 days.

| Number | Source |
|---|---|
| S$242.9M; 34% aged 65+ (3,363 cases, S$72,229 average) | SPF Annual Scam & Cybercrime Brief 2025 (idea doc, Sources) |
| 81.8% of cases were victim-made transfers (the "own OTP" point) | Same SPF brief |
| Median 129 days from the 2nd payment to the freeze (105 wallets, Jul–Oct 2026; 2,657 payments after the first) | `docs/feasibility.md` §1–2 |

*(cut first)* "Crypto made up S$182.2 million of the S$913.1 million lost to scams last year."

## 2. Where it sits (0:30–0:45)

**Screen:** the diagram (exchange or wallet app → Score Before You Sign → HSM signing → chain). Cut to the customer page header with its banner: "Simulated exchange withdrawal screen".

> It isn't a separate app: it runs inside the exchange's own withdrawal flow, just before signing, where the money leaves. The screen you'll see is our stand-in for an exchange's, because we can't connect to a real exchange or its signing hardware from the LinuxONE lab.

Source: idea doc "The solution" and "Why IBM Z" (Digital Asset Haven signs inside Crypto Express 8S HSMs; no HSM on L1CC).

## 3. Customer screens (0:45–1:15)

**Screen:** customer page, signed in as TAN SIEW LIAN (fictional persona, `data/demo/personas.json`). Withdrawal of **78,000 USDT** to `0x74f6…c48b8`. The check runs, then Q1 "Why are you sending this money?" with "An officer… asked me to" picked, Q2 "A phone call", Q3 ticking "Keep this a secret", "Act quickly or today" and "Move savings to a safe wallet". Then the call-back hold screen with its reference and masked phone. The demo strip shows "modelled answer".

> This is a real payment to a real wallet: 78,000 USDT on 12 May 2026. It's large, to a wallet she's never paid, so the engine asks three short questions. Her answers match the script. *[On screen: "answers modelled".]* The payment is held for a call-back, and her money stays put. And the wallet goes into a memory every customer is checked against.

| Fact | Source |
|---|---|
| Payment 2 = 78,000 USDT, 2026-05-12 13:46 UTC, a real payment to the demo wallet | `ui_v2_spine.tan_usdt`, `tan_time` |
| The engine itself gives `question` before any answer (a first-time payee at 1,000 USDT or more) | `ui_v2_spine.tan_tier_before_answer` = `question`; `engine.Config.large_usdt` |
| Her answer → hold | `ui_v2_spine.officer_confirms.tiers[1]` = `hold` (answer scripted: `data/demo/coached_answer.json`, modelled) |

**Why payment 2 and not payment 1:** payment 1 is a 150 USDT test sent ten minutes earlier from the same exchange. The engine gives it a generic warning (under 1,000 USDT) and it goes through. That's real engine behaviour, and also the scammer's usual first step. *(cut first)* "Ten minutes earlier, a 150 USDT test payment went through with a warning." Exchange hot wallets carry many customers' withdrawals, so the spine treats each payment as its own customer.

## 4. Officer screens (1:15–1:40)

**Screen:** officer console queue. Mrs Tan's case is ranked first by expected loss. Claim it, open the case view:
- her three answers
- "Why this was held", with each reason tagged real or modelled
- the wallet record (first seen, payments in, senders)
- the payments graph

Then Record outcome: "Cancel the payment", reason "Confirmed scam: police or official impersonation", Submit. The demo strip shows "officer confirmation modelled".

> The officer sees why: her answers, a first-time payee, the wallet's real history. Those reasons are never shown to her. The officer calls her back and confirms the scam. *[On screen: "officer confirmation modelled".]* A confirmed wallet stays flagged.

Source: why-card reasons are the engine's own (`engine.Decision.reasons`, tagged real or modelled); wallet record from `wallet_facts.py` (real, point in time); outcome mapping `payee_memory.outcome_for("cancel", "confirmed_impersonation")` → `confirmed`, recorded as `OfficerOutcome(kind="modelled")`. In the spine the confirmation lands a day after her hold (#10's officer delay).

## 5. The replay (1:40–1:55)

**Screen:** officer console demo controls, Next through payments 3–13. Each one is held, and the graph grows. It ends on "Tether froze this wallet on 5 August 2026".

> Here's what really happened next. The wallet kept collecting for 79 days: 11 more payments, from 8 other senders. Every one is held. Tether froze it 85 days after Mrs Tan's hold. The first warning was the last payment.

| Number | Source (`narration_numbers.json` → `ui_v2_spine`) |
|---|---|
| 79 days | `days_tan_to_last_payment` = 79.3 |
| 11 more payments held (42,229 USDT); 12 in total with hers (120,229 USDT) | `officer_confirms.held_after_tan` = 11, `usdt_held_after_tan` = 42,228.96; `payments_held` = 12, `usdt_held` = 120,228.96 |
| 8 other senders | `n_senders_after_tan` = 8 |
| 85 days to the freeze | `days_tan_to_freeze` = 85.0; freeze 2026-08-05 14:49 UTC |

Say **"payments"**, not "victims". The 11 include three test payments of about 10 USDT. If asked, "12 payments, 120,229 USDT" counts hers too.

**Limits line** (here or on the results slide): "Without a confirmation, a warning only lasts while payments keep coming. After a quiet month, the next one would get through." Source: `ui_v2_spine.answer_only` (holds payments 2–4, then warnings and questions; 7-day half-life renewed by each held attempt, `payee_memory.py`).

**Real-only line** *(cut first)*: "With Tether's freezes alone, none of these payments is held." Source: `real_freezes_only.payments_held` = 0.

## 6. Results (1:55–2:25)

**Screen:** results slide with two columns, **Real** and **Modelled**, and the footer *answer rate and officer accuracy modelled; 7-day half-life renewed by each held attempt*.

> We replayed all 134 wallets Tether froze from July to October 2026: 2,791 payments. Tether's freezes alone hold none of them. If half the customers asked confirm the script, and officers follow up, the engine holds about 1,920, a median of three months before the freeze. If only one in ten confirms, about 1,190.
>
> We first built a detector for scam wallets. Against similar busy wallets it scored 0.57, near chance, so we dropped it and ask the customer instead.

| Line | Value | Source |
|---|---|---|
| Wallets, payments | 134, 2,791 | `replay_summary.json` `positives.real.all` |
| Real: Tether freezes alone | 3 flagged, 0 held | `positives.real.all` |
| Modelled: r = 0.5, q = 0.9 | 1,924 held (1,841–1,992) | `positives.modelled_with_officers["0.9"]["0.5"]` |
| Median lead | 98.6 days ("about 3 months") | `positives.modelled.all["0.5"].median_lead_days` |
| Conservative: r = 0.1, q = 0.9 | 1,189.5 held (848.5 without officers) | `positives.modelled_with_officers["0.9"]["0.1"]`, `positives.modelled.all["0.1"]` |
| Detector no-go | out-of-time AUC 0.57 vs volume-matched wallets | `docs/feasibility.md`, Verdict; `docs/results1.md` |

*(cut first)* Cost and capacity line: "We ask about 1 in 8 payments to wallets this busy. At 100 call-backs a day, asking first stops 36% of scam money, against 7% for a fixed score threshold." Sources: `docs/results.md` Questions table (12.3% volume-matched, 4.5% random); `docs/result3.md` (0.5% scam rate, 100 calls/day; modelled inputs).

Keep real and modelled in separate columns. Don't quote a single legitimate-hold rate: holds concentrate on very busy payees (`docs/results.md`, "Busy payees remain the main legitimate cost").

## 7. LinuxONE (2:25–2:50)

**Screen:** the LinuxONE Community Cloud portal instance page, then a terminal on the VM showing `docker ps` (the app container from the lab image) and the benchmark output. Then back to the customer page's demo strip showing "LinuxONE" and the decision time.

> All of this runs on IBM LinuxONE, in a container from the lab image. A decision takes about 1.3 milliseconds: 600 to 750 withdrawals a second on three cores. The model ran on the NNPA accelerator but gave no speed-up, so we don't claim one. Granite was too slow on this VM, so the questions are templates.

| Claim | Source |
|---|---|
| decide() p50 about 1.3 ms; about 600–750 withdrawals/s; 3 vCPU | `docs/nnpa-benchmark.md` (#15) |
| NNPA verified, no speed-up | `docs/nnpa-benchmark.md` |
| Granite about 4 s per answer on the VM, so templates + keyword classifier | `docs/team/progress.md`, #14 row |
| Container from the lab image on the VM | #11 row; `docs/screenshots/` |

If B's free-text model is merged and measured by 03:00, replace the Granite sentence with its own one-line result (real vs synthetic test accuracy, labelled).

## 8. Close (2:50–3:00)

**Screen:** title card with three next steps, the team's names and roles, and the repo URL.

> Next: signing inside Digital Asset Haven's HSMs, sharing confirmed wallets between banks, and more languages. Score before you sign.

Team roles on the card: A (Aanya), data and problem; B (Manan), models and platform; C (Aariv), engine; D (Advay), app and delivery.

---

## For D: what the app's demo spine must do

`docs/team/ui-v2.md` covers the build; this is what the script needs from it.

1. **Mrs Tan is payment 2.** In `/demo/next`, give each payment its own customer, and give payment 2 Mrs Tan's persona (`personas.json` customer-1). Don't map customers by sending wallet: payments 1 and 2 share an exchange hot wallet, and mapping them to the same customer turns payment 2 into a known payee with no questions. These rules must match `demo_candidates.spine_numbers()`, which the numbers above come from.
2. **Payment 2 shows the real question tier first.** Call `decide(w)` with no answer. It returns `question`, and the customer page shows Q1–Q3. Then call `decide(w, coached_answer, "modelled")`, which returns `hold`. The customer page can drive this step itself, or follow the officer page's demo state; either is fine as long as the tiers come from the engine.
3. **Officer confirm comes after her hold.** On the record-outcome form, use `OfficerOutcome(kind="modelled", reason="confirmed_impersonation")`, timed a day after her payment as in the spine.
4. **Checks:** after Next × 13, the officer page shows 12 held (120,228.96 USDT) and 11 after hers (42,228.96 USDT). Payment 1 is a warning.

## Backup wallets

If the demo doesn't play well on the top pick, use the next from `python demo_candidates.py` and regenerate the numbers with `--numbers <address>`. Check `ui_v2_spine.tan_tier_before_answer` is `question`; if not, pick a different `tan_step` (`spine_numbers(h, tan_step=N)`).
- `0xf10043bd447feb21b1db993dadbd6444c9913b8b`: 5 payments; payment 2 is 76,055 USDT from a **different** sender (an exchange) 5 days after payment 1. 42 days to the freeze. Tether froze it on 17 Oct 2026 00:42 UTC, the morning of the hackathon.
- `0x5f8ab16fa80703ae86166d9af606fd68e58cd505`: 100 USDT test, then 17,900 USDT 7 hours later from the same sender; 19 payments, 10 senders; 2nd payment 253 days before the freeze. Long (19 steps).

## Don't say

- "Hours before any blacklist" (the gap is in days).
- "We detect scam wallets", or any detector headline: it failed (AUC 0.57).
- "Flagged N days before the freeze" as a detector claim. The 85 days is from Mrs Tan's hold, driven by her (modelled) answer.
- "NNPA made it faster."
- "Granite reads her answer", unless B's or Granite's measured run is in.
- "Victims" for payment counts.
