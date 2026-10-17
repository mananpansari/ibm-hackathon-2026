# Free-text answer classifier (B)

`answer_nlp.py` classifies what a customer types in the free-text box: does the answer match a scam script? It is a drop-in for `granite.classify()` and falls back to granite's keyword rules when the model is missing.

**Model:** `sentence-transformers/all-mpnet-base-v2` embeddings (pinned revision), followed by logistic regression (768 weights plus a bias in `models/answer_clf.json`). The threshold is 0.58. `p` is the head's score, **not a calibrated probability**.

**Rule (keyword floor):** an answer is flagged if the model flags it **or** granite's keyword rules do. The model can add catches but never release an answer the rules would flag. The rules also read the whole answer, while the model reads only the first 256 tokens. `source` records which one fired: `mpnet answer classifier`, `mpnet answer classifier + keyword rules`, or `keyword rules (floor)`.

## The keyword floor: trade-off

A security review flagged that the model alone could release scam answers the keyword rules used to catch. The fix was measured on the same tests before it was adopted.

| Rule | Persona: scams caught | Persona: legit flagged (tricky legit) | SG: caught, flagged |
|---|---|---|---|
| Model only | 76% | 5% (6%) | 21/21, 2/9 |
| Keyword rules only (before this classifier) | 40% | 9% (24%) | 21/21, 0/9 |
| **Model OR keyword rules (shipped)** | **81%** | **12% (27%)** | 21/21, 2/9 |

- **What the floor recovers:** 5 persona scams the model released at scores of 0.25–0.44 (romance, a fake friend on a new number, voucher and ticket resale).
- **What it costs:** legitimate answers that use scam-sounding words get flagged more often. For example, a partner met online who lives with the customer.
- **Why it's worth it:** for a payment safety check, a missed scam is money gone for good, while a false flag costs a call-back that an officer can clear. Every flag also reports the wallet to other customers through payee memory, so false flags aren't free.
- **Persona numbers are card-grouped CV.** The SG numbers come from the shipped model.

## Why this model

All candidates were scored on the same answers. Here "flagged" means the share of legitimate answers wrongly flagged.

**Test 1: persona answers.** These are 209 answers written by 16 persona agents (Opus, Sonnet, Haiku) to 120 scenario cards with hidden labels. No agent knew about the app or the classifiers. Rows marked "CV" are cross-validated with folds grouped by card; every other row is a straight held-out test.

| Approach | Scams caught | Legit flagged | Per answer |
|---|---|---|---|
| **mpnet + LR + keyword floor (shipped; card-grouped CV)** | **81%** | **12%** | 8 ms on NNPA |
| mpnet + LR trained on the answers here, model only (card-grouped CV) | 76% | 5% | 8 ms on NNPA |
| mpnet + LR trained on one author's 226 answers, threshold fixed in advance | 46% | 3% | 8 ms on NNPA |
| Keyword rules (`granite.keyword_classify`) | 40% | 9% | under 1 ms |
| qwen2.5:3b, zero-shot (Mac GPU) | 62% | 24% | 0.7 s |
| granite3.3:2b, zero-shot (Mac GPU) | 33% | 13% | 0.8 s |
| granite-4.0-h-350m base (VM, in-process) | 11% | 3% | 8.0 s |

**Test 2: the 30 SG answers** in `data/sg_answers.csv`, written by A and not used for training. The shipped rule catches 21 of 21 scams and flags 2 of 9 legitimate answers, the same with or without the floor.

## Training data (`data/answers_train.csv`, 435 answers)

| Source | Rows | How it was made |
|---|---|---|
| `synth_v1` | 226 | One author (Claude). 11 scam types × aware / deceived / coached, plus legitimate and hard legitimate answers, in 7 writing styles. |
| `persona_agents` | 209 | Built in two stages. First, an Opus agent wrote 120 labelled situation cards (`data/answer_cards.json`), using Singapore's scam-type mix. Then 16 persona agents (`data/answer_personas.json`: ages 19–81, citizens and foreign workers, a range of English, devices and typing styles) each answered about 15 unlabelled cards in character. Three agents declined the coached cards, which is why there are only 19 coached answers. |

**Which data trains best.** These scores are on the persona answers. AUC measures how well scam and legitimate answers are separated (1.0 is perfect, 0.5 is chance).

| Trained on | AUC | Scams caught at 5% false flags |
|---|---|---|
| Persona answers + `synth_v1` | 0.91 | 76% |
| Persona answers only | 0.88 | 67% |
| `synth_v1` only | 0.78 | 46% |
| `synth_v1` + real calls (Kaggle composite scam-call transcripts) | 0.75 | 45% |
| Real calls only | 0.62 | 19% |
| BothBosu synthetic calls only | 0.57 | 12% |

Answers in the customer's own voice, from many writers, beat call transcripts. Calls make the model worse.

## On LinuxONE (VM `bob1`, lab image)

| | Per answer, median / 90th / 99th percentile | Same verdicts as the Mac? |
|---|---|---|
| NNPA (`torch_nnpa`) | **8.3 / 9.5 / 22 ms** | yes, on all 239 test answers (scores within 0.009) |
| CPU, 3 threads | 143 / 225 / 286 ms | yes (scores within 0.000001) |

- **Loading:** the first call takes about 11 s while the model loads, so warm it up once at startup.
- **Big-endian:** the VM's embeddings are identical to the Mac's (cosine similarity 1.00000).
- **No extra installs:** PyTorch, `torch_nnpa`, transformers and tokenizers are already in the lab image.
- **NNPA speed-up:** NNPA runs mpnet about **18× faster** than the VM's CPU. That's a measured NNPA speed-up, unlike the wallet MLP in `docs/nnpa-benchmark.md`.

**How to run it on the VM:** download the model into a Hugging Face cache once (about 420 MB), then mount that cache:

    docker run ... -e HF_HOME=/hf -e HF_HUB_OFFLINE=1 -v ~/mpnet/hf:/hf:ro ...

**How to wire it into the app (D):** in `app.py`, set

    FREE_TEXT = types.SimpleNamespace(classify=answer_nlp.classify)

and add one warm-up call at startup.

## Caveats

- **All training and test text is synthetic,** written by Claude models. The persona agents add variety, but no real customer wrote any of it. The real check is a role-play study with 10–20 people, or a pilot.
- **The cross-validation grouped folds by card, not by persona or writer model,** so writer style is shared between training and test. Treat 0.91 as optimistic.
- **Coached victims remain the hard case.** A cover story such as "moving to my own wallet" reads like a legitimate answer. Payee memory catches those, not this classifier.
- **`p` isn't calibrated.** Use it for thresholds and ranking only, until it has been calibrated on real answers.
- **The scam type comes from the keyword rules,** or is "other". The model itself only decides scam or not.
