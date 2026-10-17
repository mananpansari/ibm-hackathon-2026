# Result 1: model-flag lead time at 1% false alarms

**The detector claim does not hold.** Against volume-matched comparison wallets, the model flags **3 of 134**
wallets Tether froze Jul–Oct 2026 (**2.2%**, bootstrap 95% CI 0–9%) at 1% false alarms. When the threshold is
set on one half of the comparison wallets and checked on the other, recall drops to **0.7% (1 of 134)**. Over
200 random halvings the median is 0.4%. Only one of the three flags is a plausible early warning (64 days before
the freeze). The other two are old wallets in the same freeze batch, flagged 3.5 and 4.9 years before it.

This is the build plan's T+10 fallback (§5: "Recall at 1% false alarms is weak → lead with Result 2"), and #1
already made that call. Result 1 stays out of the pitch. These numbers are the evidence for that decision. We did
not change the model, features or threshold method afterwards to make the number look better.

Reproduce: `python result1.py` (self-check), `python result1.py run` (writes `data/results/result1_*`, ~30 s on a laptop).

## Definitions

- **Score point:** `model.score(features(history, as_of))` just before each inbound payment ≥ 10 USDT. `as_of` is
  that payment's timestamp, so only transfers with `ts < as_of` are seen. Frozen wallets are only scored on
  payments before `freeze_ts`. `touched_known_bad` uses the same inputs as the training rows: the static fesevu set,
  plus Tether freezes before `as_of` only. (The fesevu set touches none of the 134 positives.)
- **Flagged:** any score point ≥ threshold. Comparison wallets go through the same any-payment check.
- **Threshold:** the smallest attained wallet-max score that flags ≤ floor(1% × N) comparison wallets.
  Comparison wallets with no inbound payment ≥ 10 USDT can never be flagged, so they are left out of N
  (253 of 675 random wallets, 0 of 550 volume-matched).
- **Lead time:** `freeze_ts` − timestamp of the first flagged payment.
- **Held payments:** the first flagged payment (it is scored before signing) plus every later inbound payment before
  the freeze. **Payments after flag** = held − 1, which is the plan's "payments saved". Distinct senders give an
  upper bound on victims, because senders can be exchanges or mules.
- **Positives (Q7):** `test_pos` (137) minus OFAC (0) minus wallets with no payment ≥ 10 USDT before the freeze (3)
  = **134**. The subset with ≥ 2 payments has 105 wallets. 3 positives are truncated (only the first 1,000 transfers
  were fetched). We cannot tell contract wallets from ordinary ones without network calls, so none are removed.
- Leakage check: no test wallet appears in the model's training rows (`features.csv` train_* = 8,560 rows =
  `meta.json`). `run()` asserts this and stops if it fails. On sampled points, the batch score equals `model.score`
  on the history cut at `as_of`.

## Headline basis: volume-matched comparison wallets (`test_negv`, 550)

| | All positives (134) | ≥ 2 payments (105) |
|---|---|---|
| Wallet-level AUC (max score) | 0.557 | 0.699 |
| Threshold (1%, in-sample) | 0.952 (actual FA 0.9%) | same |
| **Recall, in-sample** | **2.2% (3/134)**, 95% CI 0–9.0% | 2.9% (3/105), CI 0–12.4% |
| Recall, held-out half (seed 0) | 0.7% (1/134), actual FA 0.7% | 1.0% (1/105) |
| Held-out, 200 splits: recall median [range] | 0.4% [0–8.2%] | 0.5% [0–10.5%] |
| Held-out, 200 splits: actual FA median [range] | 0.5% [0–2.9%] | same |
| Lead days, median [IQR] | 1,277 [64–1,793] | same 3 wallets |
| Median-lead 95% CI | 64–1,793 (375 of 1,000 reps flag nothing) | |
| Lead > 1 / 7 / 30 days | 3 / 3 / 3 | |
| Held payments, total (median) | 33 (10) | |
| Payments after flag, total (median) | 30 (9) | |
| Distinct senders of held payments | 14 ("up to 14 victims" at most) | |

Recall against false-alarm rate (in-sample thresholds):

| FA target | 0.5% | 1% | 2% | 5% | 10% | 20% |
|---|---|---|---|---|---|---|
| Recall, all (134) | 0% | 2.2% | 9.7% | 16.4% | 21.6% | 31.3% |
| Recall, ≥ 2 payments (105) | 0% | 2.9% | 12.4% | 21.0% | 27.6% | 40.0% |
| Median lead (days), all | n/a | 1,277 | 357 | 470 | 247 | 203 |

## Random comparison wallets (`test_neg`, 422 with a payment): optimistic, shown for context

| | All positives (134) | ≥ 2 payments (105) |
|---|---|---|
| Wallet-level AUC | 0.725 | 0.880 |
| Recall, in-sample at 1% | 17.2% (23/134), CI 6.0–25.4% | 21.9% (23/105), CI 7.6–32.4% |
| Recall, held-out half (seed 0) | 12.7% (17/134), actual FA 0.5% | 16.2% |
| Held-out, 200 splits: recall median [range] | 12.7% [12.7–29.9%] | 16.2% [16.2–38.1%] |
| Lead days, median [IQR] | 582 [129–1,008]; CI 136–1,001 | same |
| Lead > 1 / 7 / 30 days | 23 / 23 / 22 | |
| Payments after flag, total (median) | 608 (7) | |

| FA target | 0.5% | 1% | 2% | 5% | 10% | 20% |
|---|---|---|---|---|---|---|
| Recall, all (134) | 12.7% | 17.2% | 19.4% | 35.8% | 50.7% | 66.4% |

Random wallets are mostly small, so here the model is separating wallet size, not scam behaviour
(`docs/feasibility.md` §1). This basis is **not** a fair headline.

## Limits

- **Weak model.** `models/meta.json` records an out-of-time AUC of 0.565 against volume-matched wallets ("weak signal
  only"). The 0.87 validation AUC is within the training period and against random negatives. This run gives 0.557
  wallet-level.
- **Lead time measures wallet age.** Flags fire on long-lived wallets years before Tether acts. A median lead of
  1,277 days does not mean "we warned 3.5 years early". It means the model scores old, busy wallets high, and
  comparison wallets of the same size score just as high.
- **Same-source labels.** Positives are Tether freezes, the same source as the training labels, separated only by
  time. Freezes also cover hacks and other non-scam cases.
- **Small n.** With 134 positives, one wallet moves recall by 0.75 points, and the CIs above are wide. At 1% of 550,
  the threshold rests on the 5th-highest comparison wallet.
- **In-sample threshold is optimistic.** The held-out rows show the honest number.
- **Truncation.** 289 of 550 volume-matched wallets were truncated at 1,000 transfers. Their later payments were never
  scored, and those payments could only raise their max scores. The true threshold would be at least as high, so
  the volume-matched recall above is an upper bound.
- This differs from `docs/feasibility.md` (7%, 10/134). That was the earlier model, scored at +1/6/24/72 h snapshots.
  This run uses the retrained #5 model, scored before every payment. Neither number supports a detector headline.

## For B (#5)

- The current `models/` (commit c4083d7, retrained in the lab image) behaves the same as the feasibility model or
  slightly worse. It is fine as a weak signal in the engine, but at the 0.95 threshold it fires on almost nothing
  that matters.
- Every wallet's first payment has the same score (all features 0), about 0.30. Single-payment wallets can only
  be flagged through that constant score.
- Cheapest next experiment, from feasibility §7: train only on young-wallet rows, using the "few senders, slow
  forwarding" direction. No new calls are needed.
- Loading on a Mac: xgboost needs `libomp`. Pointing `DYLD_LIBRARY_PATH` at scikit-learn's bundled
  `sklearn/.dylibs` works without brew.
