# Demo script (#16): draft

Draft for the 3-minute video: the problem section, and a narration skeleton for the demo spine (build-plan.md §7). `{{placeholders}}` are numbers that must come from the #10 replay (`replay.py` output). Don't fill them from this file's estimates.

Rules: never say "Ethereum fraud detection". Say **payments**, not victims ("up to N victims" at most). Every number cites its source, listed below each section. Label anything modelled as modelled on screen.

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

**Don't say:** "hours before any blacklist" (the idea doc's original line, superseded: the gap is in days, `build-plan.md` §1). Don't claim a detector headline: it failed against volume-matched wallets (`docs/feasibility.md`, Verdict). The no-go is worth one honest sentence in the results section, not here.

---

## 2. Demo spine narration (about 90 s)

Demo wallet: `0x74f645934fd288dfcb6359870779f68c2b0c48b8`, a real wallet Tether froze on 5 Aug 2026 (timeline: `data/demo/0x74f645934fd288dfcb6359870779f68c2b0c48b8.json`; shortlist: `python demo_candidates.py`). Run D's demo with `DEMO_WALLET=0x74f645934fd288dfcb6359870779f68c2b0c48b8`.

Two kinds of numbers below:
- **Snapshot facts** (real, already final): payments, amounts, dates, from `data/demo/<address>.json`.
- **`{{...}}` replay numbers**: what the engine held, which must come from #10.

**Beat 1: the withdrawal (payment 1).**
> It's 12 May 2026. Mrs Tan withdraws from her exchange account: 150 USDT, a test payment, to a wallet she's never paid. This is a real wallet. Tether will freeze it, but not for another 85 days.

Sources: payment 1 = 150 USDT, 2026-05-12 13:36 UTC, sender nonce 619,422 (exchange hot wallet); freeze 2026-08-05 14:49 UTC (`data/demo/…json`, `data/freezes.csv`). "85 days" = payment 1 to freeze, 85.1 (`days_before_freeze`, step 1).

**Beat 2: the score and the question.**
> Before it's signed, the engine scores it in {{decide_p50_ms}} milliseconds on LinuxONE. First-time payee, unusual amount, so it asks one question: "Real officers never ask you to move savings to a 'safe wallet'. Did someone on a call tell you to do this?"

Sources: `{{decide_p50_ms}}` from Result 4 (`bench.py`, B's #15). Question text: build-plan.md §7.

**Beat 3: the answer confirms the script.**
> She answers: "The police officer said my account is linked to a crime." That confirms the script, so the payment goes to a call-back. [On screen: "modelled answer".]

The answer is scripted for the demo (`COACHED` in D's `app.py`) and must be labelled modelled.

**Beat 4: the next payments are held.**
> Ten minutes later, 78,000 USDT goes to the same wallet. It's held, because of the first answer. The payee memory is shared, so every customer of the institution is protected, not just her.
>
> [Replay continues.] The wallet kept collecting: {{n_pays_after_first}} more payments from {{n_senders_after_first}} senders over the next 79 days, {{usdt_after_first}} USDT in all. The engine would have held {{payments_held}} of them.

Snapshot facts (final): payment 2 = 78,000 USDT at 13:46 UTC, 10 minutes after payment 1. 12 payments after the first, from 9 senders (one of them payment 1's sender), last on 2026-07-30 (79.3 days after payment 1), 120,229 USDT after the first. All 13 payments come from 9 distinct senders, 5 of them exchange hot wallets (nonce > 10,000).

Careful: payments 1 and 2 come from the **same** exchange hot wallet, so payment 2 may be Mrs Tan's own second payment and not another customer's. Say "the next payment", not "the next victim". Payment 3 (10 USDT, a different exchange, 12 minutes after payment 2) is the first from a different sender.

`{{payments_held}}`: script estimate = 12 if an officer confirms (pins, no decay); 2 if the answer alone stands as a report (7-day half-life, `payee_memory.py`). PROVISIONAL: quote #10.

**Beat 5: the officer view and the freeze.**
> The officer sees why: her answer, a first-time payee, and the payments graph growing. Then the date Tether froze it: 5 August, {{days_before_freeze}} days after we would have held it.

`{{days_before_freeze}}` = freeze time − time of the first held payment, from #10. Script estimate: 85 days (payment 2 is 85.0 days before the freeze).

**Beat 6 (bonus): live box.**
> A judge can paste any address. It's scored live through Blockscout, or from our snapshot if Blockscout is unreachable.

---

## 3. Results lines (numbers from #10)

> In a replay of {{n_test_wallets}} wallets Tether froze in Jul–Oct 2026, through the same engine the demo uses: after the first available warning, {{payments_after_warning}} payments (up to {{payments_after_warning}} victims) came in before the freeze, and the engine would have held {{payments_held_total}}.
>
> From real Tether freezes of a linked wallet alone: {{held_real_cp}}. With customer answers (modelled, swept {{answer_rate_range}}): {{held_modelled_range}}. Legitimate payments held: {{legit_hold_rate_random}} on random wallets, {{legit_hold_rate_volume_matched}} on volume-matched wallets.

Keep real and modelled on separate lines and separate slide columns.

Heads-up from the shortlist (`demo_candidates.py`, provisional): only **2 of 137** test wallets ever have a counterparty Tether froze before one of their payments, and both warnings fire late (payments 10 of 11 and 42 of 42). Expect `{{held_real_cp}}` to be small. Most held payments will come from the modelled answer path, so the pitch should lean on "the first warning is the last payment", whatever its source, and not on counterparty freezes.

---

## 4. Placeholder checklist

| Placeholder | Comes from | Script estimate (do not quote) |
|---|---|---|
| `{{payments_held}}` (demo wallet) | #10 replay, demo wallet row | 12 (officer pins) / 2 (answer only, decays) |
| `{{days_before_freeze}}` (demo wallet) | #10 replay | 85 |
| `{{n_pays_after_first}}`, `{{n_senders_after_first}}`, `{{usdt_after_first}}` | Snapshot (`data/demo/…json`); confirm the replay counts the same payments | 12, 9, 120,229 |
| `{{decide_p50_ms}}` | Result 4, `bench.py` | none |
| `{{n_test_wallets}}`, `{{payments_after_warning}}`, `{{payments_held_total}}`, `{{held_real_cp}}`, `{{held_modelled_range}}`, `{{answer_rate_range}}` | #10 replay (`docs/results.md`) | none |
| `{{legit_hold_rate_random}}`, `{{legit_hold_rate_volume_matched}}` | #10 replay | none |

## 5. Backup wallets

If #10 shows the top pick doesn't play well (for example payment 2 not held), use the next one from `python demo_candidates.py`:
- `0x5f8ab16fa80703ae86166d9af606fd68e58cd505`: 100 USDT test, then 17,900 USDT 7 hours later from the same sender; 19 payments, 10 senders; 2nd payment 253 days before the freeze. Long (19 steps) and few exchange senders early.
- `0xf10043bd447feb21b1db993dadbd6444c9913b8b`: 5 payments; payment 2 is 76,055 USDT from a **different** sender (an exchange) 5 days after payment 1, so "customer B held because of customer A" holds literally. 42 days to the freeze. Tether froze it on 17 Oct 2026 00:42 UTC, the morning of the hackathon.
