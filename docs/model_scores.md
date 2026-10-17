# Model scorecard history

Written by `python model_report.py` (one row per run; full numbers in `docs/model_scores.jsonl`).

Out-of-time test: the Jul-Oct 2026 frozen wallets against **volume-matched** comparison wallets (random wallets in the last column, for context only). Each wallet is scored just before every payment it received. AUC: chance a frozen wallet scores above a comparison wallet (0.5 = coin flip). Recall @1%: share of frozen wallets flagged when only 1% of comparison wallets are; held-out sets that cut on half the comparison wallets. Within 90 days: only flags in the last 90 days before the freeze count. Engine cut: share of scam payments the engine's `Config.model_flag` turns into a question, and the same for comparison payments.

Training-period validation AUC is in the jsonl; it is size-driven and not a measure of progress.

| When | Label | Models | Scorer | AUC (volume-matched) | Recall @1% | Held-out @1% | @5%, last 90 d | Engine cut: scam / comparison payments | AUC (random) |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-17 15:40 UTC | baseline: #5 models on main | `643632b238be` | xgb | 0.571 | 7.5% | 7.5% | 4.5% | 12.9% / 4.2% | 0.741 |
| 2026-10-17 15:40 UTC | baseline: #5 models on main | `643632b238be` | mlp | 0.590 | 0.0% | 0.0% | 2.2% | 7.7% / 1.9% | 0.775 |
| 2026-10-17 15:40 UTC | baseline: #5 models on main | `643632b238be` | ensemble | 0.596 | 2.2% | 0.0% | 3.7% | 8.2% / 1.5% | 0.768 |
| 2026-10-17 16:52 UTC | v2: payment-level data, 26 features, XGBoost vs volume-matched | `de125c0ae63f` | xgb | 0.611 | 3.0% | 2.2% | 4.5% | 35.9% / 5.7% | 0.727 |
| 2026-10-17 17:36 UTC | hybrid: v1 under 1,000 USDT received, v2 above (percentile scale) | `0961e2392b14` | v1 | 0.596 | 2.2% | 0.0% | 3.7% | 8.2% / 1.5% | 0.768 |
| 2026-10-17 17:36 UTC | hybrid: v1 under 1,000 USDT received, v2 above (percentile scale) | `0961e2392b14` | v2 | 0.611 | 3.0% | 2.2% | 4.5% | 35.9% / 5.7% | 0.727 |
| 2026-10-17 17:36 UTC | hybrid: v1 under 1,000 USDT received, v2 above (percentile scale) | `0961e2392b14` | hybrid | 0.600 | 2.2% | 2.2% | 1.5% | 60.3% / 13.5% | 0.765 |
