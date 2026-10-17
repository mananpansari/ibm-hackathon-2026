# Demo script (#16)

The 3-minute video's problem section, the demo spine narration (build-plan.md §7) and the results lines. Every number cites its source. The one open placeholder, `{{decide_p50_ms}}`, waits on Result 4 (`bench.py`, #15).

Rules: never say "Ethereum fraud detection". Say **payments**, not victims ("up to N victims" at most). Label anything modelled as modelled on screen.

Sources for the numbers below:
- **Snapshot facts** (real): `data/demo/0x74f645934fd288dfcb6359870779f68c2b0c48b8.json` (`python demo_candidates.py --export 3`).
- **Engine numbers for the demo wallet**: `data/demo/narration_numbers.json` (`python demo_candidates.py --numbers 0x74f645934fd288dfcb6359870779f68c2b0c48b8`), which replays the wallet through `replay.replay_wallet()`, the same engine path as #10.
- **Results across all wallets**: `data/results/replay_summary.json`, written up in `docs/results.md` (#10).

---

## 1. Problem (about 30 s)

> Mrs Tan is 68. A "government officer" calls: her savings are at risk, and she must open a crypto account and move everything to a "safe wallet". She does it herself, from her own account, with her own OTP.
>
> She isn't rare. Government-impersonation scams more than doubled in Singapore in 2025: 3,363 cases, S$242.9 million lost, an average of S$72,229 each. A third of the victims were 65 or older. Crypto made up S$182.2 million of the S$913.1 million lost to scams last year.
>
> 82% of scam cases were transfers the victim made themselves, so passwords and OTPs don't help, and the Shared Responsibility Framework doesn't cover them. On-chain, once it's signed, it's gone.
>
> Blacklists come too late. In the wallets Tether froze between July and October 2026, payments kept arriving for a median of 129 days after the second one. Across 105 of those wallets, 2,657 more payments came in after the first, every one of them before the freeze.

| Number | Source |
|---|---|
| 3,363 cases, S$242.9M, S$72,229 average, 34% aged 65+ | SPF Annual Scam & Cybercrime Brief 2025 (via idea doc `score-before-you-sign.md`, Sources) |
| S$182.2M crypto, of S$913.1M total (20%) | Same SPF brief |
| 81.8% of cases were victim-made transfers | Same SPF brief |
| SRF excludes authorised payments | Reed Smith article linked in the idea doc |
| Median 129 days from 2nd payment to freeze; 105 wallets with ≥ 2 payments; 2,657 payments after the first | `docs/feasibility.md` §1–2 (snapshot, `feasibility.py`) |

Optional line if time allows (`docs/feasibility.md` §2): "83 of those 105 wallets kept collecting for at least a week after the second payment."

**Don't say:** "hours before any blacklist" (the idea doc's original line, superseded: the gap is in days, `build-plan.md` §1). Don't claim a detector headline: it failed against volume-matched wallets (`docs/feasibility.md`, Verdict). The no-go gets one honest sentence in the results section, not here.

---

## 2. Demo spine narration (about 90 s)

Demo wallet: `0x74f645934fd288dfcb6359870779f68c2b0c48b8`, a real wallet Tether froze on 5 Aug 2026. Run D's demo with `DEMO_WALLET=0x74f645934fd288dfcb6359870779f68c2b0c48b8`.

**Why this wallet** (`python demo_candidates.py`, rank 1 of 5 that pass the filters): not OFAC, full history (not truncated); 13 payments, a good length for 90 s; 9 senders, 5 of them exchange hot wallets (the Mrs Tan pattern); it opens with a 150 USDT test payment and then 78,000 USDT ten minutes later; the 2nd payment is 85 days before the freeze, and it lands within the 7-day report half-life, so the first answer alone holds it. No wallet on the shortlist has a real counterparty-freeze warning (only 2 of 137 test wallets ever do), so the demo's warning is the customer's answer.

**Beat 1: the withdrawal (payment 1).**
> It's 12 May 2026. Mrs Tan withdraws from her exchange account: 150 USDT, a test payment, to a wallet she's never paid. This is a real wallet. Tether will freeze it, but not for another 85 days.

Payment 1 = 150 USDT, 2026-05-12 13:36 UTC, sender nonce 619,422 (exchange hot wallet); freeze 2026-08-05 14:49 UTC; 85.1 days (`days_before_freeze`, step 1). Engine tier: `warning` (first-time payee).

**Beat 2: the score and the question.**
> Before it's signed, the engine decides in {{decide_p50_ms}} milliseconds on LinuxONE. It's a first-time payee, so it asks one question: "Real officers never ask you to move savings to a 'safe wallet'. Did someone on a call tell you to do this?"

`{{decide_p50_ms}}`: Result 4 (`bench.py`, #15). Question text: build-plan.md §7.

**Beat 3: the answer confirms the script.**
> She answers: "The police officer said my account is linked to a crime." That matches a scam script, so her payment is held for a call-back, and the wallet goes into the shared payee memory. [On screen: "modelled answer".]

The answer is scripted (`COACHED` in D's `app.py`) and is labelled modelled. Holding payment 1 itself comes from the question tier (#7), which the #10 replay doesn't include yet: in `narration_numbers.json` payment 1 is `warning` and the holds start at payment 2. So no number below counts payment 1.

**Beat 4: the next payments are held.**
> Ten minutes later, 78,000 USDT goes to the same wallet. It's held too, because of that warning. The memory is shared, so it protects every customer of the bank, not just her.
>
> An officer calls back and confirms the scam. A confirmed wallet never fades. [Replay continues.] It kept collecting for 79 more days: 12 more payments, 120,229 USDT, from 9 senders. The engine holds all 12 once an officer confirms. [On screen: "officer confirmation modelled".]

Engine (`narration_numbers.json`, `officer_confirms`, through `replay.replay_wallet(officer=…)` with #10's one-day officer delay): tiers `warning` then 12 × `hold`; 12 payments held, 120,228.96 USDT. The confirmation lands a day after payment 2 and payment 4 is 10.7 days later, so the delay changes nothing here. Snapshot: payment 2 = 78,000 USDT at 13:46 UTC; last payment 2026-07-30, 79.3 days after payment 1.

D confirmed (17 Oct) that the demo includes the officer step, in this order: customer 1's answer → held; the next payment held by that warning; officer confirms; every later payment held up to the freeze. Both customer 1's answer and the officer's confirmation are scripted, so both are labelled modelled.

Limits line (one sentence, results or limits slide): "Without a confirmation, a warning lasts only while payments keep coming; after a quiet month, the next payment goes through." Source: `answer_only` in `narration_numbers.json` (re-run 17 Oct on main's engine: payments 2–4 held, each hold renewing the report; payment 5 arrives 35 days after the last hold and goes through); 7-day half-life and renewal in `payee_memory.py`.

Payments 1 and 2 come from the **same** exchange hot wallet, so payment 2 may be Mrs Tan's own second payment. Say "the next payment", not "the next victim". Payment 3 (10 USDT, from a different exchange, 12 minutes later) is the first from another sender.

Without any answer, Tether freezes alone hold **none** of this wallet's payments (`real_freezes_only`: 0 held; same as its row in `data/results/replay_test_pos_real.csv`).

**Beat 5: the officer view and the freeze.**
> The officer sees why: her answer, a first-time payee, and the payments graph growing. Then the date Tether froze it: 5 August 2026, 85 days after the first hold.

`days_first_hold_to_freeze` = 85.0 (`narration_numbers.json`, both answer scenarios).

**Beat 6 (bonus): live box.**
> A judge can paste any address. It's scored live through Blockscout, or from our snapshot if Blockscout is unreachable.

---

## 3. Results lines (`docs/results.md`, `data/results/replay_summary.json`)

Re-synced 17 Oct to the #10 re-run on main's engine (PR #31: answers to the #7 question, 7-day half-life renewed by each held attempt).

> We replayed all 134 wallets Tether froze in July to October 2026, payment by payment, through the same engine as the demo. They received 2,791 payments before the freeze.
>
> **Modelled:** if half of the customers asked the question confirmed the scam, and officers followed up each hold, the engine would have held about 1,920 of those payments (up to that many victims), a median of about 3 months before Tether's freeze. Even if only 1 in 10 customers asked confirms, about 1,190 are held once officers follow up (about 850 without).
>
> **Real:** Tether freezes alone would have flagged 3 payments, on 2 of 134 wallets, and held none. Our detector also failed. So we ask the customer.
>
> **Cost:** we ask about 1 in 8 payments to wallets like these. Holds on legitimate payees depend on how often an answer is misread, and they concentrate on very busy payees.

On screen, always: *answer rate and officer accuracy modelled; 7-day half-life renewed by each held attempt.*

| Line | Value | Source (`data/results/replay_summary.json`) |
|---|---|---|
| Wallets, payments | 134, 2,791 | `positives.real.all` |
| Main: held at r = 0.5, q = 0.9 | 1,924.0 ± 43.9 (1,841–1,992) | `positives.modelled_with_officers["0.9"]["0.5"].payments_held` |
| Median lead at r = 0.5 | 98.6 days ("about 3 months") | `positives.modelled.all["0.5"].median_lead_days.mean` (no-officer pass; officers don't change the first warning) |
| Conservative: r = 0.1, q = 0.9 / no officer | 1,189.5 / 848.5 | `positives.modelled_with_officers["0.9"]["0.1"]`, `positives.modelled.all["0.1"]` |
| Real: flagged, held, wallets | 3, 0, 2 | `positives.real.all` (`payments_source_warned`, `payments_held`, `wallets_warned`) |
| Cost: questions asked | about 1 in 8 payments to volume-matched wallets (12.3%; 4.5% random) | `docs/results.md`, Questions table (real pass, 1,000 USDT default) |

Keep real and modelled on separate lines and in separate slide columns. Don't quote a single legitimate-hold rate: holds concentrate on very busy payees (on volume-matched wallets, perfect officers still leave 1.6% of payments held at a 0.1% misread rate; `docs/results.md`, "Busy payees remain the main legitimate cost").

---

## 4. Backup wallets

If the demo doesn't play well on the top pick, use the next from `python demo_candidates.py`, and regenerate the numbers with `--numbers <address>`:
- `0xf10043bd447feb21b1db993dadbd6444c9913b8b`: 5 payments; payment 2 is 76,055 USDT from a **different** sender (an exchange) 5 days after payment 1, so "customer B held because of customer A" holds literally. 42 days to the freeze. Tether froze it on 17 Oct 2026 00:42 UTC, the morning of the hackathon.
- `0x5f8ab16fa80703ae86166d9af606fd68e58cd505`: 100 USDT test, then 17,900 USDT 7 hours later from the same sender; 19 payments, 10 senders; 2nd payment 253 days before the freeze. Long (19 steps), and few exchange senders early.
