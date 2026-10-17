# Score Before You Sign

**IBM Z Datathon 2026 · Theme: Real-Time AI for Critical Decisions**
Status: locked project idea (17 Oct 2026, before kick-off). The build plan comes separately.

---

## One sentence

> We flag brand-new scam wallets **days before Tether freezes them**, and decide in milliseconds, on IBM LinuxONE's on-chip AI, **how to stop each victim before their withdrawal is signed**.

## The problem

Mrs Tan, 68, gets a call from a "government officer." He tells her that her savings are at risk, that she must open a crypto account, and that she should move everything to a "safe wallet." She does it herself.

- Government-impersonation scams **more than doubled in 2025**: 3,363 cases (up 123.6%), S$242.9M lost, **an average of S$72,229 per case**. **34% of these victims are 65 or older.** SPF documents the variant where victims are told to open a crypto account, fund it, and transfer to wallets the scammers control.
- **Crypto made up S$182.2M, 20% of Singapore's S$913.1M scam losses** in 2025. Tether, Ethereum and Bitcoin account for 91.7% of crypto losses.
- **81.8% of scam cases were transfers the victim made**, so passwords and OTPs don't help. The Shared Responsibility Framework excludes these authorised payments.

Two things fail at the moment she presses send:

1. **The wallet is new.** Blacklists only list a wallet after victims report it, so a fresh scam wallet is invisible during the days or weeks it collects money. Result 1 below measures how long that gap is.
2. **The response is generic or missing.** Effective interventions are scarce: SMS alerts reached about 26,000 people (Project A.S.T.R.O., S$267.5M averted), but only **1,266 at-risk victims were stopped in person** in 2025 (joint police interventions, S$72.2M averted).

## The solution

At the withdrawal, **before the transaction is signed**:

1. **Hybrid detector, milliseconds, on NNPA.** A Keras neural network (via `ibm-zdnn-plugin`) combined with XGBoost scores the destination wallet. It uses live on-chain features: wallet age, number of first-time senders, how fast money is forwarded onwards, value in vs out, and how close it sits to known scam wallets. It outputs P(scam).
2. **Payee memory (one victim protects the next).** Real fan-in seen on-chain (many payments from new senders into one wallet), hits on the ScamSniffer blacklist, and our own outcomes (cancellations, answers that confirm the script) raise the risk of the next transfer to the same wallet. The evidence decays over hours.
3. **Router (the response ladder).** For each risky withdrawal it picks the tier that averts the most expected loss per unit of capacity, within each tier's limit:
   *release → generic warning → Granite question that probes the scam script → human call-back.*
   `value = P(scam) × amount × stop_rate(tier) − (1 − P(scam)) × friction(tier)`
4. **Granite asks back.** The Granite tier is grounded with BM25 over short crypto-scam advisories we write in our own words, based on public SPF/ScamShield guidance. Example: *"Real officers never ask you to move savings to a 'safe wallet'. Did someone on a call tell you to do this?"* The customer's answer identifies the scam type, updates the score, and escalates or releases the payment.
5. **Two user screens.** The customer's withdrawal screen, with the question shown in the app. The officer's call-back queue, with a "why" card (top evidence plus the answer) and a live graph of the payments into the wallet, visible to officers only. Ops charts are secondary.

## Why IBM Z / LinuxONE

- **Score before you sign.** IBM Digital Asset Haven (Oct 2025) runs regulated digital-asset custody on LinuxONE/Z and signs inside Crypto Express 8S HSMs. Our check sits in the same system and transaction, just before the signature. This is the production path; the L1CC VM has no HSM.
- **On-chip inference on every withdrawal.** NNPA is confirmed on our VM (`nnpa` in `/proc/cpuinfo`). We show latency with the plugin on vs off, and **withdrawals scored per second at p99 latency** on one VM.
- **Predictive + generative on one platform.** Granite runs on llama.cpp's zDNN backend, locally, so customer answers never leave the box. This matches both mandatory labs: hybrid multi-model, and predictive + generative.
- Everything is containerised with Docker on s390x.

## Real data

| Source | Use | Licence / access |
|---|---|---|
| [SPF Annual Scam & Cybercrime Brief 2025](https://www.police.gov.sg/-/media/SPF/Advisories/Scams/Annual-Scam-and-Cybercrime-Brief-2025.pdf) | Problem, victim profile, intervention capacity | Public |
| USDT `AddedBlackList` freeze events (on `0xdAC17F958D2ee523a2206206994597C13D831ec7`) | The blacklist clock; training positives (frozen Jan 2024 – Jun 2026); test set (frozen Jul – Oct 2026) | Public, on-chain |
| [fesevu/ethereum_fraud_dataset_by_activity](https://hf.co/datasets/fesevu/ethereum_fraud_dataset_by_activity) | "Known bad" labels for the proximity feature; 200-wallet check against a different label source | CC-BY-4.0, 3.85 MB |
| [Kaggle vagifa/ethereum-frauddetection-dataset](https://www.kaggle.com/datasets/vagifa/ethereum-frauddetection-dataset) | Labels via fesevu (its lifetime-total columns aren't used for training) | ODbL, 2.9 MB |
| [scamsniffer/scam-database](https://github.com/scamsniffer/scam-database) | Payee evidence | GPL-3.0, static list of 4,607 addresses; used as a blacklist hit |
| [BothBosu/scam-dialogue](https://hf.co/datasets/BothBosu/scam-dialogue) | Test set for Granite's answer → scam-type step | Apache-2.0, 1.6k synthetic phone dialogues |
| [Blockscout PRO API](https://api.blockscout.com) | Real live transactions; features at any point in time; payment counts per wallet | Free key, about 5,000 calls/day |

**Modelled, not real:** how customers respond to each tier, and the scam rate. This is swept across a range, with the break-even point shown.

## What we will prove

1. **Headline:** *"Of wallets Tether froze Jul–Oct 2026, we flagged X% a median of N days before the freeze, at 1% false alarms on ordinary USDT recipients."* (X, N: [pending: Result 1])
2. **The second-payment window:** *"After the first flagged payment, K−1 more payments (up to K−1 victims) could have been escalated."* (K: [pending: Result 2])
3. **Response matters:** with the detector held fixed, the ladder averts more S$ at equal capacity than rules-only, a fixed threshold, or calling everyone. Also: the capacity sweep (S$ averted per extra call-back officer), and the guardrail metric (legitimate users held).
4. **Scale:** N withdrawals per second at p99 latency on NNPA, plugin on vs off.

## How it matches what past winners did (2024 + 2025, 25 winners)

| What judges rewarded | How we deliver it |
|---|---|
| A person and a big number up front | Mrs Tan; S$182.2M; 34% aged 65+ |
| Action, not just a score | Four tiers, the question back, the call-back |
| Multiple or hybrid models (praised 6×) | Neural net + XGBoost + payment-graph signal + Granite |
| Broad, real data (6×) | SPF + Tether freeze events + labelled wallets + live chain |
| Trust features (7×) | Why-card, officer-only access, testing on post-training wallets |
| A UI for the real user (4×) | Customer screen + officer queue |
| Z at scale (all 6 global winners) | Measured throughput and latency on NNPA |
| A never-seen concept (2024's 1st place) | Timing and response, not detection |

**Closest past winners, and how we differ:**
- **2024 Chennai 1st, Ethereum fraud detection:** it detected fraud. We catch fresh wallets days before Tether freezes them and decide the response. **Never pitch this as "Ethereum fraud detection."**
- **2024 Global 3rd, automated call to the user on every anomaly:** it called on every alert. We ration scarce calls and ask a question that breaks the scam script first.

## Responsible AI

- No hard block. It holds, asks and escalates; only the human tier stops a payment.
- Friction on legitimate users is reported next to every gain.
- Customer answers are processed on the box by local Granite. Payee memory stores decaying counts, not text.
- Escalating a wallet requires multiple independent signals.

## Honest limits

- Ethereum and ERC-20 USDT only; Bitcoin and Tron-USDT are on the roadmap.
- No HSM on L1CC, so signing integration is described as the production path.
- Tether freezes include hacks and other cases besides scams; we remove OFAC addresses and report the set as "wallets Tether froze".
- Payments are counted, not people: victims paying through the same exchange look alike on-chain.
- Customer response rates and the scam rate are modelled and swept, not measured.
- The training and test labels come from the same source (Tether), separated by time. The 200-wallet fesevu check is the only test against a different label source.

## Top risks and mitigations

1. **"Seen this in 2024."** Use concept-first framing, and show a chart where the detector stays fixed and only the response policy changes.
2. **The lead-time result is weak.** At T+10 the headline switches to the second-payment window (Result 2).
3. **Blockscout credit budget (about 5k calls).** One call per wallet, every request cached, snapshot at T+4, and no new bulk pulls below 1,000 credits.

## Roadmap (closing line of the video)

Bitcoin and Tron-USDT → PayNow bank transfers with a bank's own data → signing integration inside Digital Asset Haven HSMs.

---

## Decision log

**Locked:**
- Theme 1, with the AI Innovation Excellence award as the target.
- Data: real data (above); customer responses swept.
- Detector: Keras MLP via zDNN, ensembled with XGBoost.
- Router: greedy expected-value allocation across four capacity-limited tiers.
- Granite: BM25-grounded, asks a script-probing question (L-A).
- Payee memory: real fan-in + blacklist (L-C).
- Capacity-planning sweep (L-E) and NNPA on/off benchmark plus throughput (L-H).
- Two user screens, the why-card and the payment graph.
- Hybrid-AI framing; concept-first positioning away from the 2024 Ethereum winner.
- Docker on the VM; code freeze 05:00 Sun; Granite falls back to templates at T+6 if it isn't working.
- Fallback headline at T+10: Result 2.
- Live-data snapshot at T+4.
- Hash-chained decision log: yes.
- Recall + roadmap slide: yes. Db2: skipped (SQLite).
- Video: a 3-minute screen recording of the demo with a voice-over, opening with Mrs Tan.
- The detector-fixed vs policy-varied chart is the main Result 3 chart.

**Assumed, not yet confirmed:**
- The customer's answer decides the scam type (the detector outputs P(scam) only).

## Sources

- SPF Annual Scam & Cybercrime Brief 2025 (PDF, linked above); [SPF 2025 summary](https://www.police.gov.sg/media-hub/police-life/2026/02/scams-and-cybercrime-fell-by-almost-a-quarter-in-2025)
- Shared Responsibility Framework excludes authorised payments: [Reed Smith](https://www.reedsmith.com/articles/singapore-to-implement-shared-responsibility-framework-for-phishing-scams/)
- IBM Digital Asset Haven: [Fintech News SG](https://fintechnews.sg/120713/digitalassets/ibm-digital-asset-haven/)
- Lab repo, packages and NNPA notebooks: [linuxone-community-cloud/jupyter-lab-ml](https://github.com/linuxone-community-cloud/jupyter-lab-ml)
- Past winners: 2024 and 2025 IBM Z Datathon winner-announcement session transcripts; [StarHacks 2025 results](https://www.starhacks.org/2025-ssf-ibm-z-datathon)
