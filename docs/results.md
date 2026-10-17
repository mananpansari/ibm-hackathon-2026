# Results

## Result 2: payments held after the first warning

Run on 17 Oct 2026. Reproduce with `python replay.py` (about 4 minutes on a laptop, no Blockscout calls). It writes `data/results/replay_*.csv` (one row per wallet) and `data/results/replay_summary.json`, which every number below comes from.

### What was replayed

- **Frozen wallets (test set):** the 134 wallets Tether froze between 1 Jul and 17 Oct 2026 (OFAC removed) that received at least one payment of 10 USDT or more before the freeze. 105 of them received two or more. Together they received **2,791 payments** before their freeze (2,762 in the 2+ subset). 3 of these wallets hit the 1,000-transfer cap, so some of their payments may be missing (flagged as `truncated` in the CSVs).
- **Comparison wallets:** 422 random USDT recipients (`test_neg`, 10,705 payments) and 550 volume-matched ones (`test_negv`, 141,148 payments, 289 truncated). Tether never froze any of them.
- **How:** each payment is one withdrawal by one customer (the sending address), sent through the same `Engine.decide()` the product uses. The clock is set to the payment's time, and every lookup sees only events from before it. Each wallet starts with a fresh payee memory, which carries forward from one payment to the next.
- **No hindsight:** Tether freezes are loaded into memory only once the clock has passed them. The history source asserts that it never returns a transfer at or after `now`, and never returns the freeze label. The self-check also replays 15 real frozen wallets using only each payment's past and checks that every decision matches the full replay.

### Definitions

- **Payment:** an inbound USDT transfer of at least 10 USDT from another wallet, before the freeze.
- **First warning (real):** the first payment at which the engine raised a Tether freeze signal, either a freeze of a wallet this one had exchanged at least 10 USDT with (counterparty) or of the wallet itself.
- **First warning (modelled):** the time of the first simulated customer report.
- **Payments after the first warning:** payments decided after a warning existed. This is the upper bound on what memory could stop.
- **Payments held:** payments the engine put in the `hold` tier (a call-back). Customer reports fade with a 7-day half-life (engine default) and freezes do not, so a held count can be below the after-warning count.
- **Lead time:** freeze time minus first-warning time, in days. Median over the wallets that got a warning.
- **Legitimate-hold rate:** held payments divided by all payments, on comparison wallets.

Counts are **payments, not victims**. One victim can pay several times, and many victims can share one exchange address. Quote at most "up to N victims".

### Results by warning source (never combined)

#### (a) Real: Tether freezes of counterparties or of the wallet itself

| | Frozen wallets | Wallets warned | Payments after first warning | Payments held | Median lead (days) |
|---|---|---|---|---|---|
| All | 134 | **2** | 3 | **3** | 713 (2 wallets) |
| 2+ payments | 105 | 2 | 3 | 3 | 713 (2 wallets) |

Legitimate holds from the same source:

| Comparison set | Wallets | Payments | Payments held | Hold rate | Wallets with any hold |
|---|---|---|---|---|---|
| Random (`test_neg`) | 422 | 10,705 | 49 | 0.46% | 2 (0.47%) |
| Volume-matched (`test_negv`) | 550 | 141,148 | 202 | 0.14% | 1 (0.18%) |

**The real source almost never fires on its own.** Only 2 of 134 frozen wallets had a counterparty Tether froze before their payments ended, so it holds 3 scam payments. On the comparison sets it holds 251 legitimate payments, and almost all of them come from 2 wallets (48 payments to one random wallet, 202 to one volume-matched wallet). This matches the feasibility report, where the known-bad rule alone got about 1% recall. On this data, Tether freezes do not carry Result 2. The modelled customer answers do.

#### (b) Modelled: customer answers

After each released or warned payment, the customer reports the wallet with probability r (no freezes loaded). Each r uses 20 fixed seeds and is shown as mean ± sd (min–max). **The answer rate is an assumption, not a measurement.**

All 134 frozen wallets (2,791 payments):

| r | Wallets warned | Payments after first warning | Payments held | Median lead (days) |
|---|---|---|---|---|
| 0.1 | 61.4 ± 4.3 (51–70) | 2,182.9 ± 30.4 (2,130–2,251) | 1,193.6 ± 41.3 (1,114–1,264) | 129 (66–174) |
| 0.2 | 82.1 ± 4.5 (73–89) | 2,382.5 ± 20.2 (2,349–2,415) | 1,518.7 ± 31.6 (1,452–1,578) | 135 (115–165) |
| 0.3 | 94.4 ± 3.7 (84–101) | 2,477.9 ± 23.8 (2,440–2,528) | 1,713.1 ± 39.3 (1,644–1,791) | 131 (85–152) |
| 0.4 | 105.0 ± 4.1 (97–114) | 2,534.7 ± 15.4 (2,502–2,559) | 1,846.7 ± 16.6 (1,801–1,880) | 128 (90–149) |
| **0.5** | **110.1 ± 2.9 (105–115)** | **2,565.2 ± 9.6 (2,551–2,591)** | **1,941.6 ± 18.8 (1,908–1,973)** | **126 (77–151)** |
| 0.6 | 117.8 ± 2.6 (113–124) | 2,596.3 ± 12.3 (2,576–2,616) | 2,024.2 ± 13.6 (1,984–2,049) | 130 (118–146) |
| 0.7 | 123.5 ± 2.8 (117–128) | 2,616.4 ± 5.6 (2,604–2,626) | 2,084.1 ± 11.7 (2,060–2,103) | 129 (85–136) |
| 0.8 | 127.7 ± 2.1 (124–131) | 2,633.6 ± 2.7 (2,628–2,638) | 2,138.4 ± 9.0 (2,125–2,156) | 127 (108–140) |
| 0.9 | 130.9 ± 1.7 (127–134) | 2,645.4 ± 2.7 (2,639–2,650) | 2,181.7 ± 6.2 (2,171–2,195) | 129 (108–136) |

105 wallets with 2+ payments (2,762 payments). The payment columns match the table above, because a wallet with a single payment has nothing left to hold:

| r | Wallets warned | Median lead (days) |
|---|---|---|
| 0.1 | 58.5 ± 4.1 (50–67) | 138 (78–188) |
| 0.3 | 86.1 ± 3.0 (78–91) | 140 (120–164) |
| 0.5 | 96.0 ± 2.7 (89–100) | 140 (129–162) |
| 0.7 | 102.9 ± 1.1 (101–105) | 142 (134–152) |
| 0.9 | 104.9 ± 0.3 (104–105) | 145 (135–146) |

The JSON also has r = 0.2, 0.4, 0.6 and 0.8 for this subset.

**Sensitivity, answer arrives a day late (r = 0.5):** 1,581.8 ± 19.1 held, against 1,941.6 when the answer arrives at decision time. Payments often come in bursts, so a delay of one day costs about 360 holds.

**Why held < after warning.** At r = 0.5, about 620 payments arrive after a warning exists but are released anyway. A single report fades below the hold threshold after one half-life (7 days). A held payment produces no new report, so memory can run dry on a wallet that collects for months. The officer step below closes most of this gap.

**Legitimate holds from this source** are not replayed. r is the rate at which scam victims report. How often legitimate customers falsely report a payee is unknown, and no number is given.

#### (c) Model flag (B's #5)

**Not available.** `model.py` (`origin/b/5-weak-model-signal`) exposes `model.score()`, but the engine doesn't call it yet, so the replay can't use it through `decide()`. The column is marked `not available` in every CSV. Nothing is estimated in its place.

### With call-back officers

In the product, every hold is a call-back. Here the officer's outcome lands a day after the hold: **confirmed** pins the wallet with no decay, and **cleared** drops the evidence, so the next payment goes through. The officer is right with probability q, which is **modelled** and swept over 0.8, 0.9 and 1.0, with 20 seeds each. A wrong officer clears a scam wallet or confirms a legitimate one. An officer only acts on a hold, so the first warning still comes from the source alone, and the sources stay separate.

Frozen wallets, customer answers at rate r (payments held, mean ± sd, out of 2,791):

| r | No officer | q = 0.8 | q = 0.9 | q = 1.0 | Upper bound: after first warning |
|---|---|---|---|---|---|
| 0.1 | 1,194 ± 41 | 2,019 ± 50 | 2,067 ± 45 | 2,089 ± 37 | 2,183 ± 30 |
| 0.2 | 1,519 ± 32 | 2,239 ± 45 | 2,272 ± 39 | 2,293 ± 35 | 2,382 ± 20 |
| 0.3 | 1,713 ± 39 | 2,353 ± 35 | 2,384 ± 37 | 2,401 ± 34 | 2,478 ± 24 |
| 0.4 | 1,847 ± 17 | 2,429 ± 20 | 2,458 ± 14 | 2,474 ± 13 | 2,535 ± 15 |
| **0.5** | 1,942 ± 19 | 2,473 ± 21 | **2,493 ± 19** | 2,509 ± 19 | 2,565 ± 10 |
| 0.6 | 2,024 ± 14 | 2,515 ± 17 | 2,536 ± 13 | 2,549 ± 10 | 2,596 ± 12 |
| 0.7 | 2,084 ± 12 | 2,540 ± 12 | 2,559 ± 9 | 2,571 ± 7 | 2,616 ± 6 |
| 0.8 | 2,138 ± 9 | 2,564 ± 8 | 2,580 ± 7 | 2,590 ± 5 | 2,634 ± 3 |
| 0.9 | 2,182 ± 6 | 2,581 ± 8 | 2,596 ± 6 | 2,606 ± 2 | 2,645 ± 3 |

- **Officers make the answer rate matter much less.** At r = 0.1 the held count rises from about 1,190 to about 2,070 (q = 0.9). One confirmed call-back protects the rest of the wallet's life.
- The small remaining gap to the upper bound comes from a report that fades before the next payment arrives. With no hold, there's no call-back to confirm it.
- **Real source with officers:** still 3 held on frozen wallets, at every q. Officers can't help when the first warning never comes.

Legitimate holds from the real source, with officers (out of the same payments as above):

| Comparison set | No officer | q = 0.8 | q = 0.9 | q = 1.0 |
|---|---|---|---|---|
| Random (`test_neg`, 10,705 payments) | 49 (0.46%) | 11.4 ± 18.8 | 11.4 ± 18.8 | 2 (0.02%) |
| Volume-matched (`test_negv`, 141,148 payments) | 202 (0.14%) | 60.4 ± 70.8 | 33.9 ± 38.6 | 25 (0.02%) |

- An officer who clears a wallet ends its holds after one call. The 25 that remain at q = 1.0 arrive in the day before the officer's outcome lands.
- When an officer wrongly confirms a legitimate wallet, every later payment to it is held. That causes the wide spread at q < 1.
- Only the 3 comparison wallets that had a hold were replayed again. Officers act only on holds, so every other wallet is unchanged.

### Headline wording

- **Main line** (modelled, r = 0.5, q = 0.9): "In a replay of the 134 wallets Tether froze in Jul–Oct 2026, if half of the customers who paid confirmed the scam when asked, and officers followed up each hold, the engine would have held about 2,490 of 2,791 payments (up to that many victims), a median of about 4 months before Tether's freeze." Always add: *customer answer rate and officer accuracy modelled; swept.*
- **Conservative line** (r = 0.1): "Even if only 1 in 10 customers confirms the scam, about 2,000 payments are held once officers follow up (about 1,200 without officers)."
- **Per wallet:** "The typical frozen wallet had about half of its later payments held, from answers alone (r = 0.5, no officers)." Use it so the total doesn't rest on the 10 busiest wallets.
- **Real only:** "Tether freezes alone would have held 3 payments, on 2 of 134 wallets. Our detector also failed (feasibility report). So we ask the customer." Say it. It's the honest reason the customer's answer is the main signal.
- **Timing:** the question is asked before signing, so the answer arrives at decision time. A one-day delay costs about 360 holds (r = 0.5, no officers).

### Honest limits

- **The headline number is modelled.** Payment counts, amounts, timings and Tether freezes are real. Whether and when a customer confirms the scam is not, and neither is how accurate officers are. With no officers and an answer rate of 0.1, the number drops to about 1,190 held.
- **Officers are simplified.** One call-back per wallet at a time, with the outcome a day later. Officer capacity isn't modelled here (C's #9). The officer's guess is independent of how many reports the wallet has.
- **Payments are concentrated.** The 10 busiest frozen wallets received 1,801 of the 2,791 payments (65%), and the median wallet received 4. Some of the busiest may be exchange-like collection addresses. Per wallet, at r = 0.5 the median wallet has about half of its later payments held.
- **Counterfactual only at the decision.** A held payment still appears in the on-chain history the engine reads afterwards (for counterparty links), because other institutions' customers would have paid it anyway.
- **One institution sees every payment.** The replay treats every sender as a customer of one bank sharing one payee memory. In reality each bank sees only its own customers, so the shared-memory effect shrinks unless institutions share warnings.
- **Truncation.** Histories stop at 1,000 transfers (ascending). For 3 frozen wallets and 289 volume-matched wallets, later payments and counterparties are missing. That can understate payments on both sides and legitimate holds.
- **Tether freezes include hacks and other cases besides scams.** The set is "wallets Tether froze", minus OFAC.
- **Engine defaults are used as-is:** 7-day report half-life, hold threshold 0.5, one report enough to hold. Changing the half-life changes the held column, but not the after-warning column.
