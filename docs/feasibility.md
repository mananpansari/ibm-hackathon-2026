# Feasibility: is the detector strong enough to build on?

Run on 17 Oct 2026 against the full P1 snapshot. Reproduce with `python feasibility.py` and `python feasibility_extra.py [random|volume-matched|both]`.

## Verdict

**No-go for the detector as currently designed.** Against comparison wallets that move similar amounts of USDT, the model barely beats chance: AUC 0.57, and 7% recall at 1% false alarms (95% range 1–13%). Within 90 days of the freeze it catches **0.7%** at 1% false alarms and **4.5%** at 5%.

The 25% recall in the first run came from comparing frozen wallets with mostly small random wallets. That compared wallet size, not scam behaviour. Once size is matched, the 12 point-in-time features carry very little signal.

Some things still hold:
- **Room to act:** frozen wallets receive weeks of payments before Tether acts, and half of them are 90 days old or younger.
- **The pipeline:** point-in-time features, a cached fetcher and an out-of-time test all work, and the self-check passes.

The gap is the features, not the data. Section 6 lists the options.

## 1. Data

| Group | Wallets | How it was picked |
|---|---|---|
| Training positives | 1,163 | Wallets Tether froze Jan 2024 – Jun 2026, not OFAC (randomly sampled from 1,720) |
| Test positives | 137 | Frozen Jul – Oct 2026; 134 got a payment of 10 USDT or more before the freeze, 105 got two or more |
| Random negatives (training / test) | 747 / 675 | Random USDT recipients with ≤300 transfers; only 422 test wallets ever received ≥10 USDT |
| **Volume-matched negatives (training / test)** | **450 / 550** | Recipients of random USDT transfers whose size follows the decile spread of frozen wallets' first payments (10 USDT to 31.8M), fetched exactly like positives (up to 1,000 transfers, no 300 cap) |
| Training rows (first payment + 1/6/24/72 h) | 8,560 | 4,275 positive, from 2,225 wallets |

The snapshot used 4,544 Blockscout calls and left 9,100 credits (about 455 calls). Everything excludes wallets Tether ever froze, fesevu scam labels and OFAC addresses. `features.py` passes its point-in-time self-check on real histories.

## 2. The ceiling: is there time to act?

| Test wallets | |
|---|---|
| Median gap from 2nd payment to freeze | 129 days (p25 13, p75 627) |
| At least 7 days between 2nd payment and freeze | 83 of 105 |
| Payments after the first one, before the freeze | median 3, 2,657 in total |
| Wallet age at freeze | 33% ≤ 30 days, 48% ≤ 90 days, 25% > 1 year |

There is room to act. What's missing is a way to tell these wallets apart from others.

## 3. Main result, by comparison set (`feasibility.py`)

XGBoost is trained on all training rows (random and volume-matched negatives together). Each test wallet is scored just before every payment it received. The threshold is set so 1% (or 5%) of the comparison wallets get flagged.

| Comparison set | Wallets | AUC | Recall at 1% | Recall at 5% | Median lead at 1% |
|---|---|---|---|---|---|
| Random (≤300 transfers) | 422 | 0.732 | 21% (28/134) | 35% | 348 days |
| **Volume-matched** | 550 | **0.565** | **7% (10/134)** | **14%** | 483 days |
| Both | 972 | 0.637 | 10% (14/134) | 21% | 389 days |
| Known-bad rule only | | | 1% (at 0.5–2.4% false alarms) | | |

Training-period AUC (5-fold, grouped by wallet) is 0.862. The model learns the training data well, but most of what it learns is size.

First run, before the volume-matched wallets were added (random comparison set only): AUC 0.744, 25% recall at 1%.

## 4. Stress tests against volume-matched wallets (`feasibility_extra.py volume-matched`)

### 4.1 Threshold stability (500 resamples of the comparison set)
| | Median | 95% range |
|---|---|---|
| Recall at 1% | 7.5% | 0.7% – 13.4% |
| Recall at 5% | 14.2% | 13.4% – 18.7% |

### 4.2 Recall when only flags within N days of the freeze count
| Window | Recall at 1% | Recall at 5% |
|---|---|---|
| 7 days | 0.0% | 0.0% |
| 30 days | 0.0% | 0.7% |
| 90 days | **0.7%** | **4.5%** |
| 365 days | 3.7% | 8.2% |
| Any time | 7.5% | 14.2% |

For comparison, against the random set the 90-day numbers were 4.5% at 1% and 13.4% at 5%.

### 4.3 Feature groups
| Model | Recall at 1% | AUC |
|---|---|---|
| All 12 features | 7.5% | 0.565 |
| Amount features only | 0.7% | 0.528 |
| Without amount features | 0.7% | 0.569 |
| Negative training rows from 2024+ only | 0.7% | 0.565 |

With size matched, no group of features separates the two populations on its own.

### 4.4 Remove one feature at a time (recall at 1% / AUC)
Removing `share_in_from_hot_wallets` (recall 0.7%), `max_in_usd` (1.5%) or `median_hold_h` (3.7%, AUC 0.546) hurts the most. Those are the only features with any real signal: the exchange-withdrawal pattern and forwarding speed. Removing any other feature changes almost nothing.

## 5. What changed between the two runs

| | Random comparison set | Volume-matched comparison set |
|---|---|---|
| AUC | 0.744 | 0.565 |
| Recall at 1% | 25% | 7% |
| Recall within 90 days, at 5% | 13% | 4.5% |
| What separated the groups | Amount features alone gave 24% recall | Amount features alone give 0.7% |

The first run looked promising only because the random comparison wallets were capped at 300 transfers and skewed small. In production, withdrawals go to exchanges, OTC desks and large personal wallets, so the volume-matched result is the realistic one.

## 6. Options from here

1. **Lead with Result 2 instead of detection.** This is the plan's T+10 fallback: "K−1 payments after the first could have been escalated". Frozen wallets keep receiving payments for weeks (2,657 payments after the first, across 105 wallets). Once *any* signal fires, such as a customer report, a Granite answer confirming a scam script, or a freeze on a linked wallet, payee memory would stop the rest. This needs no detector, and the data already supports it.
2. **Use graph features instead of single-wallet features.** The strongest remaining signal is who the victims pay. Candidates: senders that also paid wallets Tether froze earlier ("victim overlap"); money arriving from wallets one hop away from earlier freezes; and shared exchange deposit sources. These need the senders' histories, which costs about 1 call per sender and is beyond today's ~455 calls, so it would have to be a post-hackathon or next-day pull.
3. **Narrow the population.** Score only young wallets (first payment within 30 days) that receive exchange withdrawals. This is where the scam pattern lives, and where `share_in_from_hot_wallets` and `median_hold_h` showed signal. **Checked in section 7:** it covers only 41 of 134 frozen wallets, with 10% recall at 5% false alarms, so it doesn't rescue the headline. It did reveal that "few senders, slow forwarding" is the stronger signal.
4. **Change the claim for the pitch.** Present the detector as one input among several. The pipeline and the out-of-time evaluation are the strong parts, and the headline becomes "payments that could have been stopped after the first signal".

## 7. Option 3 checked: young wallets that receive exchange withdrawals (`feasibility_young.py`)

A payment counts only if, just before it, the wallet's first payment is **at most 30 days old** and **at least one earlier payment came from a hot wallet** (sender nonce > 10,000). Wallets with no such payment are left out on both sides. The threshold is set on these comparison wallets only, using the same model as section 3. This cost no calls.

**Coverage:** only **41 of the 134** frozen test wallets ever have a payment like this, against 172 of 422 random and 273 of 550 volume-matched comparison wallets. Most frozen wallets don't fit the "young wallet, exchange withdrawal" pattern.

| Comparison set (eligible wallets) | AUC | Recall at 1% | Recall at 5% | Within 90 days, at 5% |
|---|---|---|---|---|
| Random (172) | 0.826 | 9.8% (4/41) | 29.3% (12/41) | 12.2% |
| **Volume-matched (273)** | **0.688** | **4.9% (2/41)** | **9.8% (4/41)** | **4.9% (2/41)** |
| Both (445) | 0.742 | 4.9% | 12.2% | 4.9% |

Within this subset, ranking against volume-matched wallets improves (AUC 0.69, up from 0.57 overall). Recall at usable false-alarm rates is still 5–10%, though, on only 41 wallets, so each wallet moves the number by 2.4 points.

**One feature at a time** (subset, volume-matched set, AUC with the feature's natural direction flipped where needed):
- **Fewer distinct senders** points to a frozen wallet: AUC 0.78 when `n_senders_in` is reversed. Frozen young wallets are paid by a few senders, not many.
- **Holding money longer** points to a frozen wallet: AUC 0.72 when `median_hold_h` is used as is. I'd expected scam wallets to forward money fast, and the data says the opposite.
- The exchange-withdrawal share by itself is close to chance (AUC 0.56).

**Verdict on option 3:** it doesn't rescue the detector headline. It covers under a third of frozen wallets, and recall at 5% false alarms is 10%. It does show which direction to try next: *few senders, slow forwarding* separates frozen young wallets better than the original hypothesis (many victims, fast forwarding), and the current model doesn't use these features well. A model trained only on young-wallet rows with those directions in mind is the cheapest next experiment, and it needs no new calls.

## 8. Known limits

- The test set doesn't filter out contracts (that costs one call per wallet).
- The fesevu labels are a static list compiled around 2025. The test period is after that.
- Tether freezes include hacks and other cases as well as scams. OFAC addresses are removed.
- Volume matching uses the size of the sampled payment, not the wallet's lifetime volume.
