# Results

## Result 2: payments held after the first warning

Run on 17 Oct 2026. Reproduce with `python replay.py` (about 75 s on a laptop, no Blockscout calls). It writes `data/results/replay_*.csv` (one row per wallet) and `data/results/replay_summary.json`, which every number below comes from.

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

**Why held < after warning.** At r = 0.5, about 620 payments arrive after a warning exists but are released anyway. A single report fades below the hold threshold after one half-life (7 days). A held payment produces no new report, so memory can run dry on a wallet that collects for months. An officer's "confirmed" outcome pins the wallet with no decay, but the replay doesn't model officers.

**Legitimate holds from this source** are not replayed. r is the rate at which scam victims report. How often legitimate customers falsely report a payee is unknown, and no number is given.

#### (c) Model flag (B's #5)

**Not available.** `model.py` (`origin/b/5-weak-model-signal`) exposes `model.score()`, but the engine doesn't call it yet, so the replay can't use it through `decide()`. The column is marked `not available` in every CSV. Nothing is estimated in its place.

### Headline wording

- Modelled, r = 0.5: "In a replay of the 134 wallets Tether froze in Jul–Oct 2026, if half of customers who paid answered the question and confirmed the scam, the engine would have held about 1,940 of 2,791 payments (up to that many victims), a median of about 4 months before Tether's freeze." Always add: *customer answer rate modelled, swept 0.1–0.9.*
- Real only: "Tether freezes alone would have held 3 payments, on 2 of 134 wallets." Say it, because it's the honest reason the customer's answer is the main signal.

### Honest limits

- **The headline number is modelled.** Payment counts, amounts, timings and Tether freezes are real. Whether and when a customer confirms the scam is not. If the answer rate is 0.1 the number roughly halves, to about 1,190 held.
- **Payments are concentrated.** The 10 busiest frozen wallets received 1,801 of the 2,791 payments (65%), and the median wallet received 4. Some of the busiest may be exchange-like collection addresses. Per wallet, at r = 0.5 the median wallet has about half of its later payments held.
- **Counterfactual only at the decision.** A held payment still appears in the on-chain history the engine reads afterwards (for counterparty links), because other institutions' customers would have paid it anyway.
- **One institution sees every payment.** The replay treats every sender as a customer of one bank sharing one payee memory. In reality each bank sees only its own customers, so the shared-memory effect shrinks unless institutions share warnings.
- **Truncation.** Histories stop at 1,000 transfers (ascending). For 3 frozen wallets and 289 volume-matched wallets, later payments and counterparties are missing. That can understate payments on both sides and legitimate holds.
- **Tether freezes include hacks and other cases besides scams.** The set is "wallets Tether froze", minus OFAC.
- **Engine defaults are used as-is:** 7-day report half-life, hold threshold 0.5, one report enough to hold. Changing the half-life changes the held column, but not the after-warning column.
