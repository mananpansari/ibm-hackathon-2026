# Starlock (formerly Score Before You Sign)

**IBM Z Datathon 2026 · Theme: Real-Time AI for Critical Decisions**
Status: project idea, reframed on 17 Oct 2026 after the detector feasibility test (issue #1, `docs/feasibility.md`). The build plan and tickets carry the detail.

---

## One sentence

> **The first warning is the last payment:** once anyone has raised a warning about a scam wallet, every later withdrawal to it, from any customer, is held for a call-back before it is signed, decided in milliseconds on IBM LinuxONE.

## The problem

Mrs Tan, 68, gets a call from a "government officer." He tells her that her savings are at risk, that she must open a crypto account, and that she should move everything to a "safe wallet." She does it herself.

- Government-impersonation scams **more than doubled in 2025**: 3,363 cases (up 123.6%), S$242.9M lost, **an average of S$72,229 per case**. **34% of these victims are 65 or older.** SPF documents the variant where victims are told to open a crypto account, fund it, and transfer to wallets the scammers control.
- **Crypto made up S$182.2M, 20% of Singapore's S$913.1M scam losses** in 2025. Tether, Ethereum and Bitcoin account for 91.7% of crypto losses.
- **81.8% of scam cases were transfers the victim made**, so passwords and OTPs don't help. The Shared Responsibility Framework excludes these authorised payments.

Two things fail at the moment she presses send:

1. **The wallet looks ordinary, and it keeps getting paid.** We tested whether a model can tell a scam wallet from an ordinary one by its on-chain behaviour alone. Against wallets of similar size it can't (AUC 0.57; see "What we tried and dropped"). Meanwhile the wallets Tether froze in Jul–Oct 2026 kept receiving payments for a median of **129 days after their 2nd payment**, and 105 of them received **2,657 payments after their first** (real, Tether freeze data). Most of the loss comes from the second and later payments.
2. **The response is generic or missing.** Effective interventions are scarce: SMS alerts reached about 26,000 people (Project A.S.T.R.O., S$267.5M averted), but only **1,266 at-risk victims were stopped in person** in 2025 (joint police interventions, S$72.2M averted).

## The solution

In the withdrawal path of a regulated bank, custodian or exchange, **before the transaction is signed**, one decision engine checks every crypto withdrawal:

1. **Ask, don't guess.** When a withdrawal looks unusual (a first-time payee, an unusual amount), the customer gets one plain-language question. Example: *"Real officers never ask you to move savings to a 'safe wallet'. Did someone on a call tell you to do this?"* The customer's answer is the main scam signal. Granite classifies it into {scam type, confirms script}; template questions are the fallback if Granite is missing or slower than 2 s.
2. **Payee memory (one victim protects the next).** Any warning about a destination wallet goes into a memory shared across customers: an answer that confirms a scam script, a customer report, a Tether freeze of that wallet or of a wallet it has dealt with (only freezes before now), an officer's outcome, or a weak model flag. Unconfirmed warnings decay (configurable half-life); "scam-confirmed" never decays, and "cleared" stops future holds.
3. **Hold for a call-back.** A confirmed script, a memory hit or a counterparty freeze holds the withdrawal for a human call-back, from any customer, not just the one who raised the warning.
4. **Ration the call-backs (the response ladder).** *release → warning → question → call-back hold.* Holds are ranked by expected loss (amount × signal-derived probability) under the team's daily call-back capacity; anything over capacity drops to the question tier.
5. **Two user screens.** The customer's withdrawal screen, with the questions shown in the app. Our customer page is a simulated stand-in for an exchange's withdrawal screen: we built it standalone only because the L1CC VM has no HSM and we can't connect to a real exchange. The officer's call-back queue, with a "why" card (the signals, the customer's answer, prior warnings on the wallet) and a live graph of the payments into the wallet, visible to officers only.
6. **Tamper-evident.** Every decision goes into an append-only, hash-chained log (inputs, tier, reasons, engine version), with a verify step.

A bank cannot see an on-chain withdrawal it didn't originate, so this runs where the money leaves: at the institution, before the signature. In production it is not a standalone app: it is embedded in the exchange's, custodian's or wallet app's own withdrawal flow, as one call just before the payment is signed.

## Why IBM Z / LinuxONE

- **Checked before it is signed.** IBM Digital Asset Haven (Oct 2025) runs regulated digital-asset custody on LinuxONE/Z and signs inside Crypto Express 8S HSMs. Our check sits in the same system and transaction, just before the signature. This is the production path; the L1CC VM has no HSM.
- **On-chip inference on every withdrawal.** NNPA is confirmed on our VM (`nnpa` in `/proc/cpuinfo`). We show decide() p50/p99 latency and **withdrawals per second** on one VM, with the zDNN plugin on vs off. If zDNN won't run, we report CPU numbers and don't claim NNPA.
- **Predictive + generative on one platform.** Granite runs locally on the box, so customer answers never leave it. This matches both mandatory labs: hybrid multi-model, and predictive + generative.
- Everything is containerised with Docker on s390x.

## Real data

| Source | Use | Licence / access |
|---|---|---|
| [SPF Annual Scam & Cybercrime Brief 2025](https://www.police.gov.sg/-/media/SPF/Advisories/Scams/Annual-Scam-and-Cybercrime-Brief-2025.pdf) | Problem, victim profile, intervention capacity | Public |
| USDT `AddedBlackList` freeze events (on `0xdAC17F958D2ee523a2206206994597C13D831ec7`) | The clock and the label: the replay set (frozen Jul – Oct 2026), counterparty-freeze signal, model training (frozen Jan 2024 – Jun 2026) | Public, on-chain |
| [fesevu/ethereum_fraud_dataset_by_activity](https://hf.co/datasets/fesevu/ethereum_fraud_dataset_by_activity) | "Known bad" labels; 200-wallet check against a different label source | CC-BY-4.0, 3.85 MB |
| [Kaggle vagifa/ethereum-frauddetection-dataset](https://www.kaggle.com/datasets/vagifa/ethereum-frauddetection-dataset) | Labels via fesevu (its lifetime-total columns aren't used for training) | ODbL, 2.9 MB |
| [scamsniffer/scam-database](https://github.com/scamsniffer/scam-database) | Payee evidence | GPL-3.0, static list of 4,607 addresses; used as a blacklist hit |
| [BothBosu/scam-dialogue](https://hf.co/datasets/BothBosu/scam-dialogue) | Test set for Granite's answer → scam-type step | Apache-2.0, 1.6k synthetic phone dialogues |
| [Blockscout PRO API](https://api.blockscout.com) | Wallet histories at any point in time; payment counts per wallet; live "paste an address" box | Free key, about 5,000 calls/day |

**Real:** Tether freezes, payment counts, amounts and timings. **Modelled, not real:** how often a coached customer's answer confirms the script, call-back stop rates, friction, and the scam rate. These are swept across a range and labelled on every slide.

## What we will prove

1. **Headline (Result 2):** in a replay of the wallets Tether froze Jul–Oct 2026, *"N payments came after the first available warning; the engine would have held M of them,"* split by warning source (Tether freeze of a counterparty and model flag: real; customer answer: modelled and swept). The same replay over ordinary comparison wallets gives the legitimate-hold rate. (N, M: [pending: Result 2])
2. **Response matters (Result 3):** with the signals held fixed, the capacity-aware ladder averts more S$ at equal officer capacity than rules-only, a fixed threshold, or calling everyone. Also: the capacity sweep (S$ averted per extra call-back officer) and the guardrail metric (legitimate users held).
3. **Scale (Result 4):** decide() p50/p99 latency and withdrawals per second on one LinuxONE VM, zDNN plugin on vs off.
4. **Side result:** Granite answer → scam type accuracy on BothBosu dialogues and our Singapore answers.

## What we tried and dropped

- **Detecting scam wallets from their on-chain behaviour.** The original headline was "flagged X% of scam wallets N days before Tether froze them." Against random wallets it looked promising (AUC 0.73), but that compared wallet size, not scam behaviour. Against volume-matched wallets: **AUC 0.57, 0.7% recall within 90 days of the freeze at 1% false alarms** (`docs/feasibility.md`). We dropped the claim and kept the model as one weak signal. A surprise: frozen young wallets have *fewer* senders and *slower* forwarding than comparable wallets, the opposite of our hypothesis.
- **ScamSniffer's git history as a blacklist clock.** It has had 2 commits to its address list ever, so we use Tether's on-chain freeze events instead.
- **Kaggle's feature columns.** They are lifetime totals from a 2021 snapshot, which don't match what a live system sees; one point-in-time `features(history, as_of)` is used everywhere.
- **Db2.** SQLite is enough for payee memory and the log at this scale.

## How we score on the judging criteria

| Criterion | How we deliver it |
|---|---|
| Value to community & theme | Elderly victims of government-impersonation scams; a real-time decision before an irreversible transfer; most of the loss is in the repeat payments we stop |
| Novelty | Not wallet detection: a shared, cross-customer payee memory plus one question back, so one customer's warning protects the next |
| Technical design & LinuxONE | One deep, tested decision engine; NNPA on/off benchmark; Granite on the box; Docker on s390x; screenshots of what ran where |
| Execution & pitch | Live demo on a real wallet Tether later froze, a judge's paste-any-address box, an honest failure story, and real vs modelled labelled |

## How it matches what past winners did (2024 + 2025, 25 winners)

| What judges rewarded | How we deliver it |
|---|---|
| A person and a big number up front | Mrs Tan; S$182.2M; 34% aged 65+ |
| Action, not just a score | Four tiers, the question back, the call-back |
| Multiple or hybrid models (praised 6×) | Weak wallet model + payee memory + Tether freeze signal + Granite |
| Broad, real data (6×) | SPF + Tether freeze events + labelled wallets + live chain |
| Trust features (7×) | Why-card, officer-only access, hash-chained log, point-in-time replay |
| A UI for the real user (4×) | Customer screen + officer queue |
| Z at scale (all 6 global winners) | Measured throughput and latency on LinuxONE, NNPA on vs off |
| A never-seen concept (2024's 1st place) | Memory and response, not detection |

**Closest past winners, and how we differ:**
- **2024 Chennai 1st, Ethereum fraud detection:** it detected fraud. We show detection alone fails here and stop the repeat payments instead. **Never pitch this as "Ethereum fraud detection."**
- **2024 Global 3rd, automated call to the user on every anomaly:** it called on every alert. We ration scarce calls and ask a question that breaks the scam script first.

## Responsible AI

- No hard block. It warns, asks and holds; a hold is a call-back with a human, who can release the payment.
- An officer's "cleared" outcome stops future holds on that wallet, so a legitimate merchant isn't blocked repeatedly.
- Friction on legitimate users is reported next to every gain.
- Customer answers are processed on the box by local Granite. Payee memory stores warnings, not answer text.
- Sanctioned (OFAC) wallets stay with existing sanctions controls.

## Honest limits

- Ethereum and ERC-20 USDT only; Bitcoin and Tron-USDT are on the roadmap.
- No HSM on L1CC and no connection to a real exchange, so signing integration is described as the production path and the customer page is a simulated exchange withdrawal screen. The video says so.
- The wallet model is weak (AUC 0.57 against volume-matched wallets); it is one signal, not the product.
- Tether freezes include hacks and other cases besides scams; we remove OFAC addresses and report the set as "wallets Tether froze".
- Payments are counted, not people: victims paying through the same exchange look alike on-chain.
- Customer answer rates, call-back stop rates and the scam rate are modelled and swept, not measured.
- The training and test labels come from the same source (Tether), separated by time. The 200-wallet fesevu check is the only test against a different label source.

## Top risks and mitigations

1. **"Seen this in 2024."** Use concept-first framing ("the first warning is the last payment"), and show a chart where the signals stay fixed and only the response policy changes.
2. **Granite is missing or too slow on the VM.** Template questions take over after 2 s; the engine still decides.
3. **Blockscout credit budget (about 455 calls left).** Every request is cached; live use falls back to the snapshot.

## Roadmap (closing line of the video)

Better wallet signals (sender-overlap graphs) → Bitcoin and Tron-USDT → PayNow bank transfers with a bank's own data → signing integration inside Digital Asset Haven HSMs.

---

## Decision log

**Locked:**
- Theme 1, with the AI Innovation Excellence award as the target.
- Reframe (issue #1): detection is no longer the headline. Result 2 is the headline; Result 1 (lead time) is dropped from the pitch, with `docs/feasibility.md` as the evidence.
- Data: real data (above); customer responses and scam rate swept.
- Engine: one `decide(withdrawal, answer, now)` / `record(event)` module with injected history source, payee memory and clock; the API is a thin wrapper.
- Router: capacity-aware ladder across four tiers, holds ranked by expected loss.
- Granite: classifies the customer's answer and asks a script-probing question; templates as the fallback.
- Payee memory: shared across customers, keyed by destination wallet, with decaying unconfirmed warnings.
- Capacity-planning sweep and NNPA on/off benchmark plus throughput.
- Two user screens, the why-card and the payment graph.
- Docker on the VM; code freeze 05:00 Sun.
- Hash-chained decision log: yes. Db2: skipped (SQLite).
- Video: a 3-minute screen recording of the demo with a voice-over, opening with Mrs Tan; it says plainly that the check is embedded in the exchange's withdrawal flow and our customer page is a stand-in (script: `docs/demo-script.md`).
- The signals-fixed vs policy-varied chart is the main Result 3 chart.

**Still open:**
- Memory half-life for unconfirmed warnings (the build plan said 6 h; the app uses 7 days; wallets live about 4 months).

## Sources

- SPF Annual Scam & Cybercrime Brief 2025 (PDF, linked above); [SPF 2025 summary](https://www.police.gov.sg/media-hub/police-life/2026/02/scams-and-cybercrime-fell-by-almost-a-quarter-in-2025)
- Shared Responsibility Framework excludes authorised payments: [Reed Smith](https://www.reedsmith.com/articles/singapore-to-implement-shared-responsibility-framework-for-phishing-scams/)
- IBM Digital Asset Haven: [Fintech News SG](https://fintechnews.sg/120713/digitalassets/ibm-digital-asset-haven/)
- Lab repo, packages and NNPA notebooks: [linuxone-community-cloud/jupyter-lab-ml](https://github.com/linuxone-community-cloud/jupyter-lab-ml)
- Past winners: 2024 and 2025 IBM Z Datathon winner-announcement session transcripts; [StarHacks 2025 results](https://www.starhacks.org/2025-ssf-ibm-z-datathon)
- Detector feasibility test: `docs/feasibility.md`; current spec: GitHub issue #1
