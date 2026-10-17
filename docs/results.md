# Results

## Result 2: payments held after the first warning

Run on 17 Oct 2026 against C's engine after the #6 fixes (holds renew, counterparty freezes warn, model hook). Reproduce with `python replay.py` (about 15 minutes on a laptop, no Blockscout calls). It writes `data/results/replay_*.csv` (one row per wallet) and `data/results/replay_summary.json`, which every number below comes from.

### What was replayed

- **Frozen wallets (test set):** the 134 wallets Tether froze between 1 Jul and 17 Oct 2026 (OFAC removed) that received at least one payment of 10 USDT or more before the freeze. 105 of them received two or more. Together they received **2,791 payments** before their freeze (2,762 in the 2+ subset). 3 of these wallets hit the 1,000-transfer cap (flagged `truncated` in the CSVs).
- **Comparison wallets:** 422 random USDT recipients (`test_neg`, 10,705 payments) and 550 volume-matched ones (`test_negv`, 141,148 payments, 289 truncated). Tether never froze any of them.
- **How:** each payment is one withdrawal by one customer (the sending address), sent through the same `Engine.decide()` the product uses. The clock is set to the payment's time, and every lookup sees only events from before it. Each wallet starts with a fresh payee memory, which carries forward from one payment to the next.
- **No hindsight:** Tether freezes are loaded only once the clock has passed them. The history source asserts that it never returns a transfer at or after `now`, and never returns the freeze label. The self-check also replays 15 real frozen wallets using only each payment's past and checks that every decision and reason matches the full replay.

### Definitions

- **Payment:** an inbound USDT transfer of at least 10 USDT from another wallet, before the freeze.
- **First warning (real):** the first payment at which the engine raised a Tether freeze signal. A freeze of a wallet this one exchanged at least 10 USDT with is a counterparty freeze, which warns. A freeze of the wallet itself holds.
- **First warning (modelled):** the time of the first simulated customer report.
- **Payments after the first warning:** payments decided after a warning existed. This is the upper bound on what memory could stop.
- **Payments held:** payments the engine put in the `hold` tier (a call-back). Each held attempt renews the report, so a hold lasts while payments keep coming. An officer's "cleared" ends it.
- **Lead time:** freeze time minus first-warning time, in days. Median over the wallets that got a warning.
- **Legitimate-hold rate:** held payments divided by all payments, on comparison wallets.

Counts are **payments, not victims**. One victim can pay several times, and many victims can share one exchange address. Quote at most "up to N victims".

### (a) Real: Tether freezes

| | Frozen wallets | Wallets warned | Payments after first warning | Payments warned | Payments held | Median lead (days) |
|---|---|---|---|---|---|---|
| All | 134 | **2** | 3 | 3 | **0** | 713 (2 wallets) |
| 2+ payments | 105 | 2 | 3 | 3 | 0 | 713 (2 wallets) |

On comparison wallets the same signal warns 49 of 10,705 random payments (2 wallets) and 202 of 141,148 volume-matched payments (1 wallet). It holds none, since a counterparty freeze is now a warning and not a hold.

**Tether freezes don't carry Result 2.** Only 2 of 134 frozen wallets had a counterparty Tether froze before their payments ended. C's change removed the 251 legitimate holds this signal caused before. It now holds nothing on either side.

### (b) Modelled: customer answers

After each released or warned payment, the customer reports the wallet with probability r (no freezes loaded). Each r uses 20 fixed seeds and is shown as mean ± sd. **The answer rate is an assumption, not a measurement.** The officer columns add call-backs: every hold triggers one, and a day later the officer confirms (pins the wallet) or clears (ends the hold). The officer is right with probability q, also **modelled**.

All 134 frozen wallets (2,791 payments):

| r | Wallets warned | After first warning (upper bound) | Held, no officer | Held, q = 0.8 | Held, q = 0.9 | Held, q = 1.0 | Median lead (days) |
|---|---|---|---|---|---|---|---|
| 0.1 | 61 ± 4 | 2,183 ± 30 | 1,836 ± 38 | 2,019 ± 50 | 2,067 ± 45 | 2,089 ± 37 | 129 |
| 0.2 | 82 ± 4 | 2,382 ± 20 | 2,054 ± 24 | 2,239 ± 45 | 2,272 ± 39 | 2,293 ± 35 | 135 |
| 0.3 | 94 ± 4 | 2,478 ± 24 | 2,170 ± 23 | 2,353 ± 35 | 2,384 ± 37 | 2,401 ± 34 | 131 |
| 0.4 | 105 ± 4 | 2,535 ± 15 | 2,259 ± 18 | 2,429 ± 20 | 2,458 ± 14 | 2,474 ± 13 | 128 |
| **0.5** | **110 ± 3** | **2,565 ± 10** | **2,309 ± 16** | 2,473 ± 21 | **2,494 ± 19** | 2,509 ± 19 | **126** |
| 0.6 | 118 ± 3 | 2,596 ± 12 | 2,354 ± 10 | 2,515 ± 17 | 2,536 ± 13 | 2,549 ± 10 | 130 |
| 0.7 | 124 ± 3 | 2,616 ± 6 | 2,392 ± 9 | 2,540 ± 12 | 2,559 ± 9 | 2,571 ± 7 | 129 |
| 0.8 | 128 ± 2 | 2,634 ± 3 | 2,420 ± 4 | 2,564 ± 8 | 2,580 ± 7 | 2,590 ± 5 | 127 |
| 0.9 | 131 ± 2 | 2,645 ± 3 | 2,446 ± 4 | 2,581 ± 8 | 2,596 ± 6 | 2,606 ± 2 | 129 |

- **Renewal raised holds from answers alone** by 260–640 depending on r (for example 1,940 → 2,310 at r = 0.5) compared with the engine before C's fix.
- **Officers add another 150–230.** What's left between held and the upper bound is a report that faded before the next payment arrived. With no hold, there's nothing to renew and no call-back.
- **The 2+ payments subset (105 wallets, 2,762 payments)** has the same payment counts. Wallets warned: 58 ± 4 at r = 0.1, 96 ± 3 at 0.5, 105 ± 0 at 0.9. Median lead 138–145 days.
- **Sensitivity, answer arrives a day late (r = 0.5, no officer):** 1,980 ± 12 held, against 2,309.

### Legitimate holds from the modelled source (false reports)

With renewal, a false report on a legitimate wallet keeps holding while payments keep coming. To measure it, legitimate customers wrongly report the payee with probability f after a payment (**modelled**, 5 seeds):

| Comparison set | f | No officer | Officer q = 0.9 | Officer q = 1.0 | Wallets ever held |
|---|---|---|---|---|---|
| Random (10,705 payments) | 0.001 | 368 ± 122 (3.4%) | 51 ± 46 (0.5%) | 31 ± 10 (0.3%) | 8 of 422 |
| Random | 0.01 | 2,596 ± 188 (24%) | 664 ± 108 (6.2%) | 290 ± 57 (2.7%) | 63 of 422 |
| Volume-matched (141,148 payments) | 0.001 | 29,747 ± 4,208 (21%) | 13,380 ± 1,880 (9.5%) | 11,235 ± 1,279 (8.0%) | 109 of 550 |
| Volume-matched | 0.01 | 101,743 ± 1,055 (72%) | 61,493 ± 1,943 (44%) | 48,211 ± 966 (34%) | 325 of 550 |

**This is the biggest risk the replay found.** On volume-matched wallets, even perfect officers leave about 8% of legitimate payments held at f = 0.001.
- **The cause is very busy payees.** At q = 1.0, f = 0.001, one seed, the 10 most-held wallets account for 44% of the holds. Each receives 400–44,000 payments a day; they look like exchange deposit or hot wallets. One false report holds every payment to them during the day before an officer's outcome lands. Then the next false report comes within hours.
- **Renewal isn't the main cause.** Even a perfect officer's one-day wait is enough to hold hundreds of payments.
- **The rates are measured on short windows.** Most of these wallets are truncated at 1,000 transfers, which covers only a day or two of their activity.
- **For the design (C):** one report shouldn't hold a high-traffic payee for every customer. Options:
  - Require reports from 2 or more distinct customers before holding a busy payee.
  - Hold only the reporting customer's own payments until an officer confirms.
  - Scale the hold threshold with the payee's payment rate.
  - Make officer turnaround minutes, not a day.

### (c) Model flag (B's #5)

**Not available.** The engine now has the hook (`Engine(..., model=model.score, known_bad=...)`). But `model.py` and `models/` are on `origin/b/5-weak-model-signal`, and they need xgboost and Keras/TensorFlow. On this laptop xgboost can't load without `brew install libomp`, and TensorFlow has no stable release for Python 3.14. The replay also needs the flag threshold set from the 1% false-alarm cut on comparison wallets. Run it on the LinuxONE VM, where B's models load, or after those installs. The column is marked `not available` in every CSV, and nothing is estimated in its place.

### Headline wording

- **Main line** (modelled, r = 0.5, q = 0.9): "In a replay of the 134 wallets Tether froze in Jul–Oct 2026, if half of the customers who paid confirmed the scam when asked, and officers followed up each hold, the engine would have held about 2,490 of 2,791 payments (up to that many victims), a median of about 4 months before Tether's freeze." Always add: *customer answer rate and officer accuracy modelled; swept.*
- **Conservative line** (r = 0.1, no officers): "Even if only 1 in 10 customers confirms the scam, about 1,840 payments are held."
- **Real only:** "Tether freezes alone would have warned on 3 payments, on 2 of 134 wallets. Our detector also failed (feasibility report). So we ask the customer."
- **Legitimate cost:** don't quote a single legitimate-hold rate yet. It depends on the false-report rate and on busy payees (see above). Say that the design needs corroboration for high-traffic payees.

### Honest limits

- **The headline number is modelled.** Payment counts, amounts, timings and Tether freezes are real. Whether and when a customer confirms the scam, how often legitimate customers falsely report, and how accurate officers are, are not.
- **Payments are concentrated.** The 10 busiest frozen wallets received 1,801 of the 2,791 payments (65%), and the median wallet received 4.
- **Officers are simplified.** One call-back per wallet at a time, with the outcome a day later. No capacity limit (C's #9). The officer's guess is independent of the evidence.
- **Counterfactual only at the decision.** A held payment still appears in the on-chain history the engine reads afterwards, because other institutions' customers would have paid it anyway.
- **One institution sees every payment.** In reality each bank sees only its own customers. That shrinks both the protection and the false-report exposure, unless institutions share warnings.
- **Truncation.** Histories stop at 1,000 transfers (ascending). For 3 frozen wallets and 289 volume-matched wallets, later payments and counterparties are missing.
- **Tether freezes include hacks and other cases besides scams.** The set is "wallets Tether froze", minus OFAC.
- **Engine defaults are used as-is:** 7-day report half-life, hold threshold 0.5, one report enough to hold, renewal on every held attempt.
