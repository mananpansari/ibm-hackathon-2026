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
> She answers: "The police officer said my account is linked to a crime." That confirms the script, and the wallet goes into the shared payee memory. [On screen: "modelled answer".]

The answer is scripted (`COACHED` in D's `app.py`) and is labelled modelled.

**Beat 4: the next payments are held.**
> Ten minutes later, 78,000 USDT goes to the same wallet. It's held for a call-back, because of the first answer. The memory is shared, so it protects every customer of the bank, not just her.
>
> The officer calls back and confirms the scam, so the wallet stays held. [Replay continues.] It kept collecting for 79 more days: 12 more payments, 120,229 USDT, from 9 senders. The engine holds all 12.

Engine (`narration_numbers.json`, `officer_confirms`): tiers `warning` then 12 × `hold`; 12 payments held, 120,228.96 USDT. Snapshot: payment 2 = 78,000 USDT at 13:46 UTC; last payment 2026-07-30, 79.3 days after payment 1.

**If D's demo has no officer confirmation step**, use this line instead: "The next two payments, 78,010 USDT, are held. Without an officer's confirmation the warning fades after a week, and the later payments go through." (`answer_only`: 2 held, 78,010 USDT). This is a real limit, and worth saying if it's what the screen shows.

Payments 1 and 2 come from the **same** exchange hot wallet, so payment 2 may be Mrs Tan's own second payment. Say "the next payment", not "the next victim". Payment 3 (10 USDT, from a different exchange, 12 minutes later) is the first from another sender.

Without any answer, Tether freezes alone hold **none** of this wallet's payments (`real_freezes_only`: 0 held; same as its row in `data/results/replay_test_pos_real.csv`).

**Beat 5: the officer view and the freeze.**
> The officer sees why: her answer, a first-time payee, and the payments graph growing. Then the date Tether froze it: 5 August 2026, 85 days after the first hold.

`days_first_hold_to_freeze` = 85.0 (`narration_numbers.json`, both answer scenarios).

**Beat 6 (bonus): live box.**
> A judge can paste any address. It's scored live through Blockscout, or from our snapshot if Blockscout is unreachable.

---

## 3. Results lines (`docs/results.md`, `data/results/replay_summary.json`)

> We replayed all 134 wallets Tether froze in July to October 2026, payment by payment, through the same engine as the demo. They received 2,791 payments before the freeze.
>
> **Modelled:** if half of the customers who paid answered the question and confirmed the scam, the engine would have held about 1,940 of those payments (up to that many victims), a median of about four months before Tether froze the wallet. Across answer rates from 10% to 90%, that's 1,190 to 2,180 held.
>
> **Real:** Tether freezes of linked wallets alone hold just 3 payments, on 2 wallets. That's why the customer's answer is the main signal, and why one answer has to protect every later payment.
>
> On ordinary wallets, freeze-based holds hit 0.46% of payments to random wallets and 0.14% to volume-matched ones.

| Line | Value | Source (`replay_summary.json`) |
|---|---|---|
| Wallets, payments | 134, 2,791 | `positives.real.all` |
| Held at r = 0.5 | 1,941.6 ± 18.8 (1,908–1,973) | `positives.modelled.all["0.5"].payments_held` |
| Median lead at r = 0.5 | 125.9 days | `…["0.5"].median_lead_days.mean` |
| Held at r = 0.1 / 0.9 | 1,193.6 / 2,181.7 | `…["0.1"]`, `…["0.9"]` |
| Real: held, wallets | 3, 2 | `positives.real.all` |
| Legitimate hold rate | 0.458% random, 0.143% volume-matched | `legitimate_holds.*.payment_hold_rate` |

Keep real and modelled on separate lines and in separate slide columns, and always add "customer answer rate modelled, swept 0.1–0.9". The legitimate-hold rates cover the real (freeze) source only. False reports from legitimate customers aren't modelled (`docs/results.md`).

Optional sensitivity line: if the answer reaches the bank a day late, about 1,580 are held instead of 1,940 (`modelled_r0.5_delay_1d`).

---

## 4. Backup wallets

If the demo doesn't play well on the top pick, use the next from `python demo_candidates.py`, and regenerate the numbers with `--numbers <address>`:
- `0xf10043bd447feb21b1db993dadbd6444c9913b8b`: 5 payments; payment 2 is 76,055 USDT from a **different** sender (an exchange) 5 days after payment 1, so "customer B held because of customer A" holds literally. 42 days to the freeze. Tether froze it on 17 Oct 2026 00:42 UTC, the morning of the hackathon.
- `0x5f8ab16fa80703ae86166d9af606fd68e58cd505`: 100 USDT test, then 17,900 USDT 7 hours later from the same sender; 19 payments, 10 senders; 2nd payment 253 days before the freeze. Long (19 steps), and few exchange senders early.
