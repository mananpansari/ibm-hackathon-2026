# Model v2: an experiment, not wired into the engine

**Status:** experiment on branch `aariv/model-v2` (v2 and a v1/v2 hybrid). The engine and app still use the #5 models in `models/`. Nothing here changes a decision.

**Verdict:** mixed. v2 ranks individual **payments** better, which is how the engine uses the score, but it catches **fewer wallets** at a 5% false-alarm budget. At the wallet level, every difference is 1 to 8 of 134 wallets, so v2 is not clearly better. It isn't worth swapping in before the submission.

## What changed from #5
| | #5 (current, `models/`) | v2 (`models_v2/`) |
|---|---|---|
| Training rows | 4 snapshots per wallet (+1/6/24/72 h): 8,560 rows | Just before each payment the wallet received, up to 40 per wallet, each wallet weighted equally: 35,806 rows (`data/model_v2/train_points.csv.gz`) |
| Features | 12 (`features.py`) | 26: the 12 plus 14 from the wallet's own history (`features_v2.py`), such as the test-then-big ratio, gaps between payments, round amounts, repeat senders and forwarding within 1 h |
| Trained against | random and volume-matched wallets | volume-matched wallets only (so it can't win on wallet size) |
| Model | XGBoost + MLP, averaged | XGBoost, trained in the LinuxONE lab container (xgboost 3.4.1) |
| Blockscout calls | none | none: same snapshot, training wallets only |

The setup was picked inside the training period (`python train_v2.py cv`), before looking at the test set. It was tested on a time holdout: wallets first paid in 2026 H1 against a quarter of the comparison wallets, with AUC vs volume-matched wallets of **0.801** for v2, against 0.757 for the 12 features on the same rows. The test set was then scored once.

## Out-of-time test: Jul-Oct 2026 frozen wallets vs volume-matched normal wallets
134 frozen wallets (2,791 payments before the freeze) and 550 volume-matched wallets (141,148 payments), scored with `model_report.py` in the LinuxONE lab container. Full rows are in `docs/model_scores.md`.

| Measure | #5 ensemble (in use) | #5 XGBoost alone | **v2** | v2 vs in use |
|---|---|---|---|---|
| AUC, wallet max score | 0.596 | 0.571 | **0.611** | +0.015 |
| AUC, per payment | 0.761 | 0.735 | **0.814** | +0.053 |
| Recall at 1% false alarms (wallets) | 2.2% (3) | 7.5% (10) | 3.0% (4) | +1 wallet |
| Same, held-out threshold | 0.0% | 7.5% | 2.2% | |
| Recall at 5% false alarms | **16.4% (22)** | 14.9% (20) | 10.4% (14) | **-8 wallets** |
| At 5%, flags in the last 90 days only | 3.7% (5) | 4.5% (6) | 4.5% (6) | +1 wallet |
| Scam payments flagged at a 1% payment budget | 5.2% | — | **10.6%** | roughly doubled |
| Wallet cut-off at 1% | 0.952 | 0.973 | 0.993 | |
| Payment cut-off at 1% | 0.862 | 0.910 | 0.950 | |

Against **random** wallets (context only) v2 is worse: wallet AUC 0.727 against 0.768. That's expected, because v2 was trained not to use wallet size, which is what separates random wallets.

## How to read it
- **Better:** per-payment ranking (AUC 0.761 → 0.814), and twice the scam payments flagged at the same 1% payment budget. That's the part the engine would use.
- **Worse:** catching whole wallets at the 5% budget (22 → 14 of 134).
- **Too small to call:** recall at 1% and within 90 days. The changes are a single wallet.
- **Cut-offs aren't comparable between models.** v2's scores sit higher (its 1% payment cut-off is 0.950), so the engine's 0.78, or PR #37's 0.59, would flag far more with v2: 5.7% of volume-matched payments at 0.78. Wiring v2 in would need its own cut-off, measured the way PR #37 measured 0.59, plus an engine change to pass the history-based features.

## Hybrid: v1 for small wallets, v2 for large (also not wired in)
`hybrid.py` routes each payment by what the wallet had received before it: **under 1,000 USDT → v1, otherwise v2**. Both scores go onto one scale, their percentile among the training period's normal payments (23,769 payments, 1,001 steps). The routing line and the scale were fixed before the test, and v1, v2 and the hybrid were scored in one run in the lab container. That run reproduced v1's and v2's earlier rows exactly.

| Measure (vs volume-matched) | v1 (in use) | v2 | Hybrid |
|---|---|---|---|
| AUC, wallet max score | 0.596 | **0.611** | 0.600 |
| AUC, per payment | 0.761 | **0.814** | 0.809 |
| Recall at 1% false alarms | 2.2% | **3.0%** | 2.2% |
| Same, held-out threshold | 0.0% | **2.2%** | **2.2%** |
| Recall at 5% false alarms | **16.4%** | 10.4% | 2.2% |
| At 5%, flags in the last 90 days only | 3.7% | **4.5%** | 1.5% |
| Scam payments flagged at a 1% payment budget | 5.2% | **10.6%** | 10.3% |
| Wallet cut-off at 1% | 0.952 | 0.993 | **1.0 (the ceiling)** |

**Verdict: the hybrid doesn't help as built.** Per payment it's about as good as v2 (0.809). At the wallet level it collapses at 5% (3 of 134 wallets). That collapse comes from my calibration, not from routing: with only 1,001 steps from training data, many test wallets score above anything seen in training, so they all land on exactly 1.0 and tie. Keeping false alarms at 1% or 5% then forces the cut-off to the ceiling. A finer scale (interpolating, or breaking ties by the raw score) would fix the ties, but choosing it after seeing these numbers would be a second look at the test set. So it's left as a lesson, not re-run.

## If someone picks this up
1. Decide whether per-payment ranking or wallet recall matters more for the product. Engine questions are per payment, which favours v2.
2. Try v2's features on the old training rows, and a v2 + #5 average, choosing on the training-period time holdout as before.
3. Before wiring it in: `Engine` needs a hook that gives the model `features_v2(history, as_of)` and a v2 cut-off measured on comparison payments. The live latency (several feature passes per withdrawal) also needs checking.

Reproduce: `python train_v2.py build && python train_v2.py cv && python train_v2.py train`, then `python model_report.py --models models_v2 --label "..."`, both in the lab container.
