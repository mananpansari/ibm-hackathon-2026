# Result 4: decide() on LinuxONE, zDNN (NNPA) on vs off

Measured 17 Oct 2026 (#15). **Finding: the MLP really runs on NNPA, but it doesn't make decide() faster.** The model is too small (12 → 32 → 16 → 1, one row per withdrawal) for the accelerator to beat the CPU. Per-withdrawal time is dominated by Python, feature building, XGBoost and SQLite, not the MLP.

## Hardware and software
- LinuxONE Community Cloud VM `bob1`: s390x, 3 vCPU, 8 GB, `nnpa` in `/proc/cpuinfo`. A shared VM, so the numbers move a lot between runs.
- Lab image `registry.linuxone.cloud.marist.edu/l1cc/jupyterlab-image-s390x:latest`: Python 3.12, TensorFlow 2.18.1, ibm-zdnn-plugin 2.3.0, Keras 3.14, XGBoost 3.4.1.
- On = `NNPA_DEVICES` unset (the plugin's default), off = `NNPA_DEVICES=0`. Each mode runs as its own process.

## Is NNPA really used?
TF lists only `CPU:0` either way. That's expected: the plugin is a kernel library (`tensorflow/core/kernels/_z_ops.so`) that swaps out CPU kernels, not a separate device. Proof comes from `ZDNN_ENABLE_PRECHECK=true ZDNN_LOGLEVEL=debug`:

| run (25 withdrawals) | zDNN ops logged |
|---|---|
| on, `model.score()` as first written (eager Keras call) | **0**, so it was not on NNPA |
| on, MLP inside `tf.function` (current `model.py`) | 75 `zdnn_matmul_transpose_op` + 25 `zdnn_sigmoid` (3 + 1 per withdrawal) |
| off, `NNPA_DEVICES=0` | 0 |

So zDNN only accelerates graph execution, and `model.py` now wraps the MLP in `tf.function`.

## Method
`bench_decide.py`. One timed call = point-in-time `features()` from the recorded history → `model.score()` (XGBoost + MLP) → C's `Engine.decide()` (payee memory with Tether freezes, hash-chained log). It replays 2,000 inbound payments to the recorded test wallets (plus 100 warm-up), spread across the whole period, in time order, single-threaded, with no network. Tiers produced: 1,501 warning, 494 release, 5 hold, the same in every run. The models were trained inside the lab image (`python model.py train`).

The engine doesn't take the score as a reason yet (that's #5's wiring), so the score is computed and timed in the same call but doesn't change the tier.

## Results: decide() per withdrawal, 3 runs per mode

| run | zDNN | p50 ms | p99 ms | withdrawals/s | of which score() p50 ms |
|---|---|---|---|---|---|
| 1 | on | 1.22 | 5.18 | 720 | 0.86 |
| 1 | off | 1.39 | 7.61 | 599 | 1.02 |
| 2 | on | 1.49 | 14.74 | 453 | 1.10 |
| 2 | off | 1.41 | 7.11 | 585 | 1.03 |
| 3 | on | 1.35 | 3.19 | 689 | 1.00 |
| 3 | off | 1.25 | 3.47 | 729 | 0.91 |
| **median** | **on** | **1.35** | **5.18** | **689** | **1.00** |
| **median** | **off** | **1.39** | **7.11** | **599** | **1.02** |

The differences between runs are bigger than the difference between on and off: no measurable effect.

## Context: the MLP alone, by batch size (`bench_nnpa.py --features 12 --hidden 32 16`)

| batch | p50 on ms | p50 off ms | off/on |
|---|---|---|---|
| 1 | 0.155 | 0.142 | 0.91x |
| 256 | 0.180 | 0.174 | 0.96x |
| 4096 | 0.393 | 0.443 | 1.13x |
| 16384 | 4.269 | 0.804 | 0.19x |

NNPA only pulls slightly ahead at batch 4096, and it is slower at 16384. That matches IBM's own note that small models and small batches see little or no gain.

## What we can claim
- decide() with both models runs on LinuxONE at about **1.4 ms p50 and about 600–700 withdrawals/s on one thread** (3 vCPU shared VM).
- The MLP's matrix multiplies run on the on-chip NNPA, verified from zDNN's own log.
- **Not** claimed: any speed-up from NNPA for this workload.
