# B: Models and platform

Your tickets for the reframed plan (spec: [#1](https://github.com/mananpansari/ibm-hackathon-2026/issues/1)). Each one is a GitHub issue, which stays the source of truth. Update your rows in [progress.md](progress.md) as you go.

| Ticket | Title | Blocked by |
|---|---|---|
| [#5](https://github.com/mananpansari/ibm-hackathon-2026/issues/5) | Weak model signal | [#3](https://github.com/mananpansari/ibm-hackathon-2026/issues/3) (C) |
| [#11](https://github.com/mananpansari/ibm-hackathon-2026/issues/11) | Deploy on LinuxONE | [#4](https://github.com/mananpansari/ibm-hackathon-2026/issues/4) (D) |
| [#15](https://github.com/mananpansari/ibm-hackathon-2026/issues/15) | NNPA benchmark (Result 4) | [#5](https://github.com/mananpansari/ibm-hackathon-2026/issues/5) (B), [#11](https://github.com/mananpansari/ibm-hackathon-2026/issues/11) (B) |

## [#5](https://github.com/mananpansari/ibm-hackathon-2026/issues/5) Weak model signal

**Blocked by:** [#3](https://github.com/mananpansari/ibm-hackathon-2026/issues/3) (C)

### What to build

The point-in-time model becomes one tagged input to the engine. XGBoost and a Keras MLP are trained on the P1 training rows (split by wallet), saved in an architecture-neutral form, and their averaged score appears in decisions as a 'model' signal. Decisions still work when the model is absent.

## Acceptance criteria

- [ ] Both models trained on training rows only, validation split by wallet
- [ ] Models saved in a portable format that loads on s390x (no pickle across architectures)
- [ ] Engine decisions include a model-score reason tagged as a weak signal
- [ ] With the model missing, decide() still returns a decision from the other signals
- [ ] Out-of-time numbers quoted from the feasibility report, not re-claimed as stronger

## [#11](https://github.com/mananpansari/ibm-hackathon-2026/issues/11) Deploy on LinuxONE

**Blocked by:** [#4](https://github.com/mananpansari/ibm-hackathon-2026/issues/4) (D)

### What to build

The API and pages run on the LinuxONE VM in one container built from the hackathon lab image, with the snapshot data and payee memory as mounted volumes and the Blockscout key passed from the environment at run time. NNPA availability is checked and recorded.

## Acceptance criteria

- [ ] Container builds from the lab image and serves the customer page on the VM
- [ ] Data and memory are volumes; the key never enters the image or git
- [ ] NNPA presence checked and noted
- [ ] Snapshot data copied to the VM without a second Blockscout pull
- [ ] Short run instructions in the repo

## [#15](https://github.com/mananpansari/ibm-hackathon-2026/issues/15) NNPA benchmark (Result 4)

**Blocked by:** [#5](https://github.com/mananpansari/ibm-hackathon-2026/issues/5) (B), [#11](https://github.com/mananpansari/ibm-hackathon-2026/issues/11) (B)

### What to build

On the VM, decide() latency and throughput are measured with the model's MLP inference on the zDNN plugin and with it off: p50/p99 and withdrawals per second. If zDNN won't run, measured CPU numbers are reported and NNPA is not claimed.

## Acceptance criteria

- [ ] p50 and p99 latency and withdrawals/s for zDNN on and off
- [ ] Benchmark runs through decide(), not the model alone
- [ ] Method and hardware recorded with the numbers
- [ ] No NNPA claim without a measured run

## Free-text answer classifier (NLP model)

**Blocked by:** none (in progress). Interface and deadline: [ui-v2.md](ui-v2.md), "Note for B".

### What to build

A classifier for the customer's optional free-text answer, trained partly on synthetic data, that plugs into A's `answers.StructuredClassifier` with one line: `classify(text) -> {"scam_type", "confirms_script", "source"}`, under 2 s on the VM, no network.

## Acceptance criteria

- [ ] Same output shape as `granite.classify`; loads on s390x
- [ ] Accuracy reported separately on real (BothBosu, `data/sg_answers.csv`) and synthetic test data
- [ ] Merged by 03:00 SGT, 18 Oct, or listed as a next step with its numbers
