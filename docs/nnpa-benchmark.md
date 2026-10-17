# Result 4: decide() on LinuxONE, zDNN (NNPA) on vs off

Measured 17 Oct 2026 (#15), rerun on `main`'s engine with the model wired into `decide()`. **Finding: the MLP really runs on NNPA, but it doesn't make decide() faster.** The model is too small (12 → 32 → 16 → 1, one row per withdrawal) for the accelerator to beat the CPU. Per-withdrawal time is dominated by Python, XGBoost and SQLite, not the MLP.

## Hardware and software
- LinuxONE Community Cloud VM `bob1`: s390x, 3 vCPU, 8 GB, `nnpa` in `/proc/cpuinfo`. A shared VM, so the numbers move a lot between runs.
- Lab image `registry.linuxone.cloud.marist.edu/l1cc/jupyterlab-image-s390x:latest`: Python 3.12, TensorFlow 2.18.1, ibm-zdnn-plugin 2.3.0, Keras 3.14, XGBoost 3.4.1.
- On = `NNPA_DEVICES` unset (the plugin's default), off = `NNPA_DEVICES=0`. Each mode runs as its own process.

## Is NNPA really used?
TF lists only `CPU:0` either way. That's expected: the plugin is a kernel library (`tensorflow/core/kernels/_z_ops.so`) that swaps out CPU kernels, not a separate device. Proof comes from `ZDNN_ENABLE_PRECHECK=true ZDNN_LOGLEVEL=debug`:

| run (25 withdrawals) | zDNN ops logged |
|---|---|
| on, `model.score()` as first written (eager Keras call) | **0**, so it was not on NNPA |
| on, MLP inside `tf.function` (current `model.py`), through `decide()` | 74 `zdnn_matmul_transpose_op` + 25 `zdnn_sigmoid` (about 3 + 1 per withdrawal) |
| off, `NNPA_DEVICES=0` | 0 |

So zDNN only accelerates graph execution, and `model.py` now wraps the MLP in `tf.function`.

## Method
`bench_decide.py` (run from the repo root on `main`'s code). One timed call = `Engine.decide()`, wired the way `app.py` wires it: `model=model.score` (XGBoost + MLP on the engine's own point-in-time features) and `known_bad`, plus payee memory with Tether freezes, the question tier and the hash-chained log. The score call is also timed separately from inside `decide()`. It replays 2,000 inbound payments to the recorded test wallets (plus 100 warm-up), spread across the whole period, in time order, single-threaded, with no network. All 2,000 decisions carry a `model_score`/`model_flag` reason, so the model is really inside `decide()`. The models were trained inside the lab image (`python model.py train`).

## Results: decide() per withdrawal, 3 runs per mode

| run | zDNN | p50 ms | p99 ms | withdrawals/s | of which score() p50 ms |
|---|---|---|---|---|---|
| 1 | on | 1.36 | 7.60 | 600 | 0.58 |
| 1 | off | 1.29 | 10.32 | 576 | 0.49 |
| 2 | on | 1.17 | 4.35 | 745 | 0.45 |
| 2 | off | 1.28 | 6.14 | 655 | 0.49 |
| 3 | on | 1.28 | 9.04 | 623 | 0.49 |
| 3 | off | 1.16 | 3.34 | 777 | 0.44 |
| **median** | **on** | **1.28** | **7.60** | **623** | **0.49** |
| **median** | **off** | **1.28** | **6.14** | **655** | **0.49** |

The differences between runs are bigger than the difference between on and off: no measurable effect. The score is under half of each decide() call. The rest is Python, payee-memory SQLite and the log.

**Decisions shift slightly with NNPA on.** Tiers with zDNN on: 919 question, 840 warning, 241 release. With it off: 921 question, 838 warning, 241 release. That's the same in every run, so 2 of 2,000 decisions change. zDNN computes in DLFLOAT16 (reduced precision), so a score right at the engine's 0.78 question threshold can fall on the other side. It never touches holds, because the model only ever asks.

## Context: the MLP alone, by batch size (`bench_nnpa.py --features 12 --hidden 32 16`)

| batch | p50 on ms | p50 off ms | off/on |
|---|---|---|---|
| 1 | 0.155 | 0.142 | 0.91x |
| 256 | 0.180 | 0.174 | 0.96x |
| 4096 | 0.393 | 0.443 | 1.13x |
| 16384 | 4.269 | 0.804 | 0.19x |

NNPA only pulls slightly ahead at batch 4096, and it is slower at 16384. That matches IBM's own note that small models and small batches see little or no gain.

## What we can claim
- decide() with both models runs on LinuxONE at about **1.3 ms p50 and about 600–750 withdrawals/s on one thread** (3 vCPU shared VM).
- The MLP's matrix multiplies run on the on-chip NNPA, verified from zDNN's own log.
- **Not** claimed: any speed-up from NNPA for this workload.
- NNPA's reduced precision changed 2 of 2,000 decisions (question ↔ warning at the model threshold), so the on and off runs aren't bit-identical.
