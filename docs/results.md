# Results

## Result 2: payments held after the first warning

Run on 17 Oct 2026 against the engine on `main` (#3, #6 with renewing holds, #7 question tier). #9's capacity limit is off by default (`daily_capacity=None`), and the c9 engine reproduces these results exactly. Reproduce with `python replay.py` (about 25 minutes on a laptop, no Blockscout calls). It writes `data/results/replay_*.csv` (one row per wallet) and `data/results/replay_summary.json`, which every number below comes from.

### What was replayed

- **Frozen wallets (test set):** the 134 wallets Tether froze between 1 Jul and 17 Oct 2026 (OFAC removed) that received at least one payment of 10 USDT or more before the freeze. 105 of them received two or more. Together they received **2,791 payments** before their freeze (2,762 in the 2+ subset). 3 of these wallets hit the 1,000-transfer cap (flagged `truncated` in the CSVs).
- **Comparison wallets:** 422 random USDT recipients (`test_neg`, 10,705 payments) and 550 volume-matched ones (`test_negv`, 141,148 payments, 289 truncated). Tether never froze any of them.
- **How:** each payment is one withdrawal by one customer (the sending address), sent through the same `Engine.decide()` the product uses. The clock is set to the payment's time, and every lookup sees only events from before it. Each wallet starts with a fresh payee memory, which carries forward from one payment to the next.
- **Questions:** when the engine asks a question (a first-time payee of 1,000 USDT or more, or weak evidence), the replay answers it with `decide(w, answer, answer_kind="modelled")`.
  - A confirming answer holds that payment and reports the wallet, so later payments from every customer are held too.
  - A clean answer releases.
  - Smaller first-time payments get a warning and no question.
- **No hindsight:** Tether freezes are loaded only once the clock has passed them. The history source asserts that it never returns a transfer at or after `now`, and never returns the freeze label. The self-check also replays 15 real frozen wallets using only each payment's past and checks that every decision and reason matches the full replay.

### Definitions

- **Payment:** an inbound USDT transfer of at least 10 USDT from another wallet, before the freeze.
- **Questioned:** payments the engine asked a question about.
- **First warning (real):** the first payment at which the engine raised a Tether freeze signal. A freeze of a wallet this one exchanged at least 10 USDT with (counterparty) asks a question. A freeze of the wallet itself holds.
- **First warning (modelled):** the first confirming answer. It holds that payment too.
- **Payments after the first warning:** payments decided once a warning existed, including the payment whose answer confirmed it. This is the upper bound on what memory could stop.
- **Payments held:** payments the engine put in the `hold` tier (a call-back). Each held attempt renews the report. A report fades with a **7-day half-life** once attempts stop (C's setting, modelled). An officer's "cleared" ends it.
- **Lead time:** freeze time minus first-warning time, in days. Median over the wallets that got a warning.
- **Legitimate-hold rate:** held payments divided by all payments, on comparison wallets.

Counts are **payments, not victims**. One victim can pay several times, and many victims can share one exchange address. Quote at most "up to N victims".

### (a) Real: Tether freezes

Every question in this pass gets a clean answer, so only Tether's evidence can warn or hold.

| | Frozen wallets | Wallets warned | Payments after first warning | Payments with a freeze signal | Payments held | Median lead (days) |
|---|---|---|---|---|---|---|
| All | 134 | **2** | 3 | 3 | **0** | 713 (2 wallets) |
| 2+ payments | 105 | 2 | 3 | 3 | 0 | 713 (2 wallets) |

On comparison wallets the signal fires on 49 of 10,705 random payments (2 wallets) and 202 of 141,148 volume-matched payments (1 wallet). It holds none.

**Tether freezes don't carry Result 2.** Only 2 of 134 frozen wallets had a counterparty Tether froze before their payments ended.

### (b) Modelled: customer answers

A question about a frozen wallet gets a confirming answer with probability r (no freezes loaded). Each r uses 20 fixed seeds and is shown as mean ± sd. **The answer rate is an assumption, not a measurement.** The officer columns add call-backs: every hold triggers one, and a day later the officer confirms (pins the wallet) or clears (ends the hold). The officer is right with probability q, also **modelled**.

All 134 frozen wallets (2,791 payments):

| r | Wallets warned | Payments questioned | After first warning (upper bound) | Held, no officer | Held, q = 0.8 | Held, q = 0.9 | Held, q = 1.0 | Median lead (days) |
|---|---|---|---|---|---|---|---|---|
| 0.1 | 27 ± 4 | 346 ± 12 | 1,201 ± 128 | 848 ± 112 | 1,109 ± 165 | 1,190 ± 131 | 1,201 ± 128 | 124 |
| 0.2 | 43 ± 4 | 312 ± 12 | 1,529 ± 96 | 1,155 ± 87 | 1,448 ± 110 | 1,510 ± 102 | 1,529 ± 96 | 127 |
| 0.3 | 55 ± 5 | 282 ± 13 | 1,719 ± 79 | 1,378 ± 109 | 1,639 ± 104 | 1,705 ± 82 | 1,719 ± 79 | 112 |
| 0.4 | 65 ± 4 | 266 ± 10 | 1,849 ± 81 | 1,530 ± 71 | 1,787 ± 102 | 1,834 ± 77 | 1,849 ± 81 | 104 |
| **0.5** | **73 ± 5** | 254 ± 7 | **1,938 ± 48** | **1,649 ± 73** | 1,876 ± 47 | **1,924 ± 44** | 1,938 ± 48 | **99** |
| 0.6 | 82 ± 4 | 246 ± 6 | 2,008 ± 46 | 1,742 ± 59 | 1,961 ± 57 | 1,997 ± 45 | 2,008 ± 46 | 112 |
| 0.7 | 92 ± 3 | 238 ± 6 | 2,058 ± 52 | 1,794 ± 62 | 2,007 ± 48 | 2,047 ± 51 | 2,058 ± 52 | 106 |
| 0.8 | 98 ± 3 | 232 ± 6 | 2,127 ± 18 | 1,904 ± 20 | 2,086 ± 34 | 2,120 ± 27 | 2,127 ± 18 | 103 |
| 0.9 | 103 ± 2 | 229 ± 4 | 2,155 ± 24 | 1,966 ± 25 | 2,119 ± 33 | 2,148 ± 28 | 2,155 ± 24 | 108 |

- **Only large first-time payments are asked.** About 550 of the 2,791 payments are first-time payments of 1,000 USDT or more. A wallet whose victims all pay less, or all pay it again, never gets a question, so even at r = 0.9 only 103 of 134 wallets get a warning.
  - Questions fall as r rises, because held payments aren't asked.
- **With perfect officers, every payment after the first warning is held** (the q = 1.0 column equals the upper bound). Without officers, about 290 are lost at r = 0.5. A report fades when no attempt comes within a few half-lives.
- **The 2+ payments subset (105 wallets, 2,762 payments)** has the same payment counts. Wallets warned: 25 ± 4 at r = 0.1, 60 ± 3 at 0.5, 79 ± 2 at 0.9. Median lead 123–149 days.
- **Sensitivity, asking from 100 USDT instead of 1,000 (r = 0.5, no officer):** 2,079 ± 90 held (against 1,649), 86 wallets warned. The cost is many more questions to legitimate customers (below).

### Legitimate holds and questions on comparison wallets

**Questions** (the friction of asking) in the real pass, which has no false confirms:

| Comparison set | Payments | Questioned at 1,000 USDT (default) | Questioned at 100 USDT |
|---|---|---|---|
| Random | 10,705 | 480 (4.5%) | 1,182 (11%) |
| Volume-matched | 141,148 | 17,337 (12.3%) | 35,156 (25%) |

**False confirms:** a legitimate customer's answer is wrongly read as confirming a scam with probability f (**modelled**, 5 seeds). A held attempt renews the report, so a false confirm keeps holding while payments keep coming:

| Comparison set | f | No officer | Officer q = 0.9 | Officer q = 1.0 | Wallets ever held |
|---|---|---|---|---|---|
| Random (10,705 payments) | 0.001 | 3 ± 3 (0.02%) | 1 ± 1 | 1 ± 1 | 0.6 of 422 |
| Random | 0.01 | 12 ± 11 (0.11%) | 7 ± 4 | 5 ± 3 (0.04%) | 3.4 of 422 |
| Volume-matched (141,148 payments) | 0.001 | 5,313 ± 1,052 (3.8%) | 2,581 ± 842 (1.8%) | 2,227 ± 786 (1.6%) | 16.8 of 550 |
| Volume-matched | 0.01 | 28,629 ± 768 (20%) | 15,265 ± 1,028 (11%) | 12,764 ± 1,236 (9.0%) | 92.8 of 550 |

**Busy payees remain the main legitimate cost.** Asking only on large first-time payments cut the exposure about fivefold compared with letting any customer report (an earlier run: 29,747 held at f = 0.001 with no officer). But on volume-matched wallets, perfect officers still leave 1.6% held at f = 0.001.
- **Why:** some payees receive hundreds to tens of thousands of payments a day; they look like exchange deposit or hot wallets. One false confirm holds every payment to them during the day before an officer's outcome lands.
- **Measured on short windows:** most of these wallets are truncated at 1,000 transfers, covering only a day or two.
- **Design options (C):**
  - Require 2 or more distinct confirming customers before holding a high-traffic payee.
  - Hold only the confirming customer's own payment until an officer confirms.
  - Make officer turnaround minutes, not a day.

### Report half-life sensitivity (modelled setting)

C's setting is 7 days, renewed by each held attempt. Payments held, mean ± sd:

| Half-life | Frozen, r = 0.5 | Frozen, r = 0.5, officer q = 0.9 | Random, f = 0.001 | Volume-matched, f = 0.001 | Volume-matched, f = 0.001, officer q = 1.0 |
|---|---|---|---|---|---|
| 3 days | 1,488 ± 71 | 1,924 ± 44 | 0.8 ± 0.7 | 5,052 ± 1,211 | 2,227 ± 786 |
| **7 days** | **1,649 ± 73** | **1,924 ± 44** | 2.6 ± 3.1 | 5,313 ± 1,052 | 2,227 ± 786 |
| 30 days | 1,779 ± 72 | 1,924 ± 44 | 5.4 ± 4.5 | 5,441 ± 1,019 | 2,227 ± 786 |

- **Without officers, a longer half-life holds more scam payments** (+130 from 7 to 30 days) at a small legitimate cost.
- **With officers, the half-life doesn't matter.** The call-back outcome lands after a day, before any of these half-lives runs out, and then it decides.
- **7 days is a reasonable middle.** Quote it as a modelled setting.

### (c) Model flag (B's #5)

**Not available.** The engine has the hook (`Engine(..., model=model.score, known_bad=...)`), and `model.py` is on `main`. But the model needs xgboost and Keras/TensorFlow. On this laptop xgboost can't load without `brew install libomp`, and TensorFlow has no stable release for Python 3.14. The threshold is now set on `main` (`Config.model_flag = 0.78`, which flags 1% of payments to comparison wallets, scored by B in the LinuxONE lab container). Run the replay with the model on the VM, where B's models load. The column is marked `not available` in every CSV, and nothing is estimated in its place.

### Headline wording

- **Main line** (modelled, r = 0.5, q = 0.9): "In a replay of the 134 wallets Tether froze in Jul–Oct 2026, if half of the customers asked the question confirmed the scam, and officers followed up each hold, the engine would have held about 1,920 of 2,791 payments (up to that many victims), a median of about 3 months before Tether's freeze." Always add: *answer rate and officer accuracy modelled; 7-day half-life renewed by each held attempt.*
- **Conservative line** (r = 0.1, no officers): "Even if only 1 in 10 customers asked confirms the scam, about 850 payments are held."
- **Real only:** "Tether freezes alone would have flagged 3 payments, on 2 of 134 wallets. Our detector also failed (feasibility report). So we ask the customer."
- **Legitimate cost:** "We ask about 1 in 8 payments to wallets like these. Holds on legitimate payees depend on how often an answer is misread, and they concentrate on very busy payees." Don't quote a single legitimate-hold rate.

### Honest limits

- **The headline number is modelled.** Payment counts, amounts, timings and Tether freezes are real. The answer rate, the false-confirm rate, the half-life and officer accuracy are not.
- **Only large first-time payments are asked** (1,000 USDT by default). Victims who pay less never get the question, so the threshold trades scam coverage against questions to legitimate customers.
- **Payments are concentrated.** The 10 busiest frozen wallets received 1,801 of the 2,791 payments (65%), and the median wallet received 4.
- **Officers are simplified.** One call-back per wallet at a time, with the outcome a day later. No capacity limit (C's #9). The officer's guess is independent of the evidence.
- **Counterfactual only at the decision.** A held payment still appears in the on-chain history the engine reads afterwards, because other institutions' customers would have paid it anyway.
- **One institution sees every payment.** In reality each bank sees only its own customers. That shrinks both the protection and the false-confirm exposure, unless institutions share warnings.
- **Truncation.** Histories stop at 1,000 transfers (ascending). For 3 frozen wallets and 289 volume-matched wallets, later payments and counterparties are missing.
- **Tether freezes include hacks and other cases besides scams.** The set is "wallets Tether froze", minus OFAC.
