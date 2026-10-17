# Score Before You Sign: Build Plan

**IBM Z Datathon 2026 · companion to `score-before-you-sign.md`**
Status: decisions Q1–Q18 settled in a grilling session on 17 Oct 2026. Team of 4. T+0 = actual kick-off; code freeze at 05:00 Sun (assumed T+20 for a 09:00 Sat start).

> **Partly superseded (17 Oct):** the detector failed its feasibility test (`docs/feasibility.md`), so GitHub issue #1 reframes the project as "the first warning is the last payment". The headline is now Result 2; Result 1 (lead time, "headline in days") is dropped from the pitch. Where this plan disagrees with issue #1 or `docs/score-before-you-sign.md`, those win.

---

## 1. What changed from the idea doc

Scanning the data (Hugging Face, Kaggle, live sources) broke three assumptions:

| Idea doc said | What the data shows | Decision |
|---|---|---|
| ScamSniffer's git history "shows when each wallet was added" | `address.json` has had 2 commits ever (bulk "refresh" Dec 2023, one removal Feb 2024). `all.json` has had 4,607 addresses, unchanged since about Mar 2024; the daily commits only change domains. The public list also runs 7 days behind by design. | **Tether's on-chain `AddedBlackList` events are the blacklist clock** (Q1). ScamSniffer stays as a static "known bad" hit. |
| "Hours before the blacklist" | Sample of 12 frozen USDT wallets (11 with deposits): first deposit → freeze ranges 161 h to 22,415 h, **median ≈ 2,041 h (≈ 85 days)**. Distinct senders before freeze: median 4 (1–25). | **The headline is in days**, measured from *our flag*, not from first deposit (Q8). |
| Train on Kaggle's feature columns | Kaggle's columns are lifetime totals from a 2021 snapshot. A fresh scam wallet has hours of history, so these features would not match what we see live. | **One `features(history, as_of)` function** for training, replay and live. Datasets give labels only (Q2). |
| "Victims" = distinct senders | Victims withdraw from exchanges. The first payer into one frozen wallet had sent 786,468 transactions, so it's a hot wallet. Distinct senders undercount victims. | Count **payments ≥ 10 USDT**; say "victims" only as "up to" (Q9). |
| Live-data snapshot at T+2 | Blockscout free tier: 5 requests/s, 100K credits/day, 20 credits per call → **about 5,000 calls/day**, reset at 00:00 UTC (08:00 SGT, after the freeze). | **One call per wallet**, cached, snapshot at **T+4**, about 3,500 calls total (Q12, Q17). |

---

## 2. Why this is a proper solution, not a demo

1. **It's scored against an outside, timestamped enforcement action.** Tether's freeze is on-chain and dated to the second, and it isn't our label. "We flagged it N days before Tether froze it" is checkable by anyone.
2. **There's no gap between training and serving.** The same `features(history, as_of)` code runs on training snapshots, the historical replay and live withdrawals. Nothing can see past `as_of`. That includes the "known bad" set, which only includes wallets frozen before `as_of`.
3. **The test is out of time.** Training uses wallets frozen Jan 2024 – Jun 2026, and the test uses wallets frozen Jul – Oct 2026. Train/validation splits are by wallet, so the 4 snapshots of one wallet never sit on both sides.
4. **The false-alarm budget is fixed before any claim.** The threshold is set so that 1% of real comparison wallets (ordinary USDT recipients from the same weeks) are flagged. Every recall and lead-time number is quoted at that rate.
5. **The value of the response is measured on its own.** With the detector fixed, only the policy changes (ladder vs rules-only vs fixed threshold vs call everyone). The modelled parts (customer stop rates, friction, scam rate) are swept and labelled as modelled.
6. **It runs where the money moves.** It's on LinuxONE, before the signature, with NNPA inference on every withdrawal and Granite on the same box, so answers never leave it.

---

## 3. Data inventory (scanned 17 Oct 2026)

| Source | Where | Use | Verdict |
|---|---|---|---|
| USDT `AddedBlackList` events (topic `0x42e16015…d819dc` on `0xdAC17F958D2ee523a2206206994597C13D831ec7`) | Blockscout `getLogs` | Blacklist clock; training positives (Jan 2024–Jun 2026); test set (Jul–Oct 2026) | **Use.** At least 1,000 since Jan 2024; 148 since 10 Jul 2026 |
| Blockscout PRO API (`api.blockscout.com`, `chainid=1`, Etherscan-style `module=account&action=tokentx&sort=asc`) | your free key | Point-in-time histories; live "paste an address" box | **Use.** Ascending works for young wallets and times out on exchange hot wallets (we skip those) |
| [fesevu/ethereum_fraud_dataset_by_activity](https://hf.co/datasets/fesevu/ethereum_fraud_dataset_by_activity) `addr_labels_balanced.csv.zst` (3.85 MB, about 115k addresses, CC-BY-4.0) | HF / Kaggle | "Known bad" set for the proximity feature; 200-wallet check against a different label source | **Use labels only.** It already merges Kaggle's labelled sets (vagifa, hamishhall), XBlock, ScamSniffer, Etherscan labels and CryptoScamDB |
| [scamsniffer/scam-database](https://github.com/scamsniffer/scam-database) `all.json` (4,607 addresses) | GitHub | Static blacklist hit in payee memory | **Use, static only.** Many entries aren't on Ethereum mainnet |
| [OFAC sanctioned ETH addresses](https://github.com/0xB10C/ofac-sanctioned-digital-currency-addresses/tree/lists) (120 lines) | GitHub | Remove sanctions freezes from the test set (Q7) | **Use** |
| [BothBosu/scam-dialogue](https://hf.co/datasets/BothBosu/scam-dialogue) (1.6k synthetic phone dialogues, Apache-2.0) | HF | Test set for Granite's answer → scam-type step, plus about 30 Singapore answers we write | **Use** |
| [ibm-granite/granite-4.2-3b-GGUF](https://hf.co/ibm-granite/granite-4.2-3b-GGUF) `granite-4.2-3b-Q4_K_M.gguf` (2.24 GB) | HF | Granite tier on llama.cpp | **Use** |
| SPF Annual Scam & Cybercrime Brief 2025 | police.gov.sg | Problem numbers; about 15 advisories written in our own words | **Use** |
| Kaggle [vagifa/ethereum-frauddetection-dataset](https://www.kaggle.com/datasets/vagifa/ethereum-frauddetection-dataset) (~9.8k rows) | Kaggle | — | **Skip for training.** Lifetime totals don't match live features; its labels are already in fesevu |
| Kaggle xblock phishing network (1.26 GB pickle, no licence), Eth-PSD, hamishhall, chaitya0623 (1.35 GB) | Kaggle | — | **Skip.** No licence, too large, or already in fesevu |
| fesevu raw transactions (92 GB) | HF | — | **Skip.** Too big for 20 h; Blockscout gives us what we need |
| Synthetic Kaggle crypto-scam / wash-trading sets | Kaggle | — | **Skip.** Synthetic |

### Call budget (one free key, about 5,000 calls)

| Step | Calls |
|---|---|
| Freeze list, Jan 2024 → now (`getLogs`, 1,000 per call) | ~5 |
| Positive histories (about 1,300 frozen wallets × 1 ascending `tokentx`, ≤ 1,000 rows) | ~1,300 |
| Training negatives: 1,000 random USDT recipients, Jan 2024–Jun 2026 | ~1,020 |
| Test comparison set: 1,000 random USDT recipients, Jul–Oct 2026 | ~1,020 |
| fesevu check against a different label source (200 wallets) | ~200 |
| **Subtotal** | **~3,550** |
| Left for retries, demo and the live box | ~1,450 |

Rules: every request goes through the cache (never fetch the same URL twice), throttle to 4 requests/s, log `x-credits-remaining`, and stop new bulk pulls below 1,000 credits.

---

## 4. System

```
withdrawal (wallet, amount, customer)
   │
   ├─ history = fetch(wallet)                 cached Blockscout, USDT transfers ≤ now
   ├─ x = features(history, as_of=now)        same function as training and replay
   ├─ P = mean(XGBoost(x), MLP_zDNN(x))       MLP inference on NNPA
   ├─ P' = payee_memory.adjust(wallet, P)     decaying evidence in SQLite
   ├─ tier = router.pick(P', amount, capacity)
   │     release → warning → Granite question → human call-back
   ├─ Granite: question → customer answer → {scam_type, confirms_script} → re-score
   ├─ log.append(decision)                    hash-chained JSONL
   └─ customer screen  |  officer queue (why-card + payment graph, officers only)
```

### Files (one owner each to avoid merge conflicts)

```
fetch.py        cached Blockscout client (SQLite cache keyed by URL, throttle, credit log)      P1
snapshot.py     freezes, positives, negatives, histories → data/                              P1
features.py     features(history, as_of) → dict                                               P1
replay.py       Results 1–2                                                                   P1
train.py        XGBoost + Keras MLP, ensemble, threshold at 1% false alarms                   P2
bench.py        NNPA on/off, p50/p99, withdrawals/s → Result 4                                P2
router.py       tiers, expected-value allocation, payee memory, capacity sweep → Result 3     P3
granite.py      BM25 (~15 lines numpy) + llama.cpp + template fallback                        P3
advisories/     about 15 short advisories in our own words                                    P3
app.py          FastAPI: /score /answer /queue /live, hash-chained log                         P4
static/customer.html, static/officer.html                                                     P4
Dockerfile      FROM the lab image (has TF, zDNN plugin, XGBoost, llama.cpp) + fastapi/uvicorn P4
```

The key goes in `.env` on the VM as `BLOCKSCOUT_API_KEY`, is listed in `.gitignore`, and is only ever read server-side. It never goes in a page or a commit.

### Features (point in time, USDT only, payments ≥ 10 USDT)

Every feature uses only transfers with a timestamp before `as_of`:

- `age_h`: hours since the first inbound payment
- `n_pay_in`, `n_senders_in`, `n_pay_in_6h`: fan-in and its speed
- `share_in_from_hot_wallets`: share of inbound payments whose sending transaction has nonce > 10,000 (an exchange-withdrawal proxy, the Mrs Tan pattern)
- `usd_in`, `usd_out`, `out_in_ratio`, `max_in_usd`
- `median_hold_h`: forwarding speed (inbound → next outbound)
- `n_out_counterparties`
- `touched_known_bad`: any counterparty in the fesevu scam set, ScamSniffer, or wallets **Tether froze before `as_of`**

Training rows: each wallet at first payment + {1 h, 6 h, 24 h, 72 h}. Replay rows: the test wallet just before each inbound payment.

### Definitions used in results

- **Flagged** = at any payment time, P' ≥ the threshold set for 1% false alarms. The comparison wallets go through the same check, so the 1% is on the same footing.
- **Lead time** = freeze time − time of the first flagged payment.
- **Payments saved** = payments ≥ 10 USDT after the first flag (and before the freeze).
- **Test set** (Q7): ordinary wallets (not contracts) frozen Jul–Oct 2026 with at least one payment ≥ 10 USDT before the freeze, minus OFAC. Report it all and the subset with 2 or more payments.

---

## 5. Workstreams and checkpoints

| T+ | P1 Data | P2 Models | P3 Decision | P4 Product |
|---|---|---|---|---|
| 0–1 | **All together:** VM and lab container up, repo created, one test call with the key, check that NNPA (`nnpa` in `/proc/cpuinfo`), the zDNN plugin and llama.cpp's zDNN backend work, agree the features schema ||||
| 1–4 | `fetch.py`, freeze list, 20-row feature sample by **T+1.5**, full snapshot by **T+4** | Training script on the T+1.5 sample | `granite.py` + advisories; Granite question loop | `app.py` with mocked `/score`; both pages |
| 4–7 | `replay.py` skeleton | **XGBoost trained (T+7)**, threshold at 1% | Granite working or **templates at T+6** | Customer screen flow end to end on the mock |
| 7–10 | Replay on the test set | **Keras MLP via zDNN (T+10)**, ensemble | Payee memory (SQLite, 6 h half-life), router | Officer queue, why-card, payment graph (Cytoscape.js, pinned CDN version) |
| 10–12 | **Results 1–2 (T+12)**; choose the demo wallet | 200-wallet fesevu check | Hash-chained log; Granite eval on BothBosu + 30 SG answers | Wire pages to the real API (**T+12**) |
| 12–14 | Support the live box | **NNPA on/off + throughput → Result 4 (T+14)** | **Capacity sweep → Result 3 (T+14)** | Docker on s390x; live "paste an address" box |
| 14–18 | **All together:** integrate, then a full rehearsal on the VM, fix only what breaks the demo ||||
| 18–20 | Results slide numbers | Benchmark slide | Responsible-AI slide | **Record the video**; code freeze at T+20 |

**If kick-off has already passed:** P1 does the snapshot first, and P2 trains on a 200-wallet partial snapshot until the full one lands.

### Fallbacks (decided in advance; no arguing at 3 a.m.)

| When | If | Then |
|---|---|---|
| T+4 | Snapshot incomplete | Train on whatever is cached (at least 200 wallets); finish the pull in the background |
| T+6 | Granite missing, too slow (> 2 s) or wrong | Template questions; Granite only classifies the answer |
| T+10 | Recall at 1% false alarms is weak | Lead with Result 2 ("K−1 payments after the first could have been escalated") |
| T+12 | zDNN plugin won't run | Report the measured CPU numbers and say so; never claim NNPA we didn't measure |
| Credits < 1,000 | Budget nearly gone | Stop bulk pulls; the demo runs from the snapshot, and the live box stays for the judges |

---

## 6. Results to produce

| # | Claim | Comes from |
|---|---|---|
| 1 | "Of wallets Tether froze Jul–Oct 2026, we flagged X% a median of N days before the freeze, at 1% false alarms on ordinary USDT recipients." | `replay.py` |
| 2 | "After the first flagged payment, K−1 more payments (up to K−1 victims) could have been escalated." | `replay.py` |
| 3 | With the detector fixed, the ladder averts more S$ at equal officer capacity than rules-only, a fixed threshold or calling everyone. The chart: capacity on x, S$ averted on y, 4 lines. Legitimate users held is shown alongside. | `router.py` sweep: real payment amounts from the snapshot; scam rate swept 0.1–1% (headline 0.5%); stop rates and friction swept |
| 4 | N withdrawals/s at p99 on one VM, with the zDNN plugin on vs off | `bench.py` |
| side | Granite answer → scam type accuracy | `granite.py` eval |

---

## 7. Demo spine (about 90 s)

1. Mrs Tan's withdrawal goes to a **real wallet Tether later froze**, with the clock replayed to its 2nd payment.
2. The score lands in milliseconds and the router picks the **Granite question**: *"Real officers never ask you to move savings to a 'safe wallet'. Did someone on a call tell you to do this?"*
3. She answers "yes, the officer said…", which confirms the script, so the payment is escalated to a **call-back**.
4. The officer queue shows the why-card (top features + her answer) and the payment graph growing as the replay continues, then shows the date Tether froze the wallet, N days later.
5. Bonus: a judge pastes any address, and it's scored live through Blockscout.

## 8. Pitch and video (T+18–T+20)

A 3-minute screen recording of the demo spine with a voice-over. It opens on Mrs Tan and S$182.2M, then shows the four results, one recall-and-roadmap slide, and closes with the roadmap line from the idea doc. Never call it "Ethereum fraud detection". Db2 is dropped (SQLite).

## 9. Honest limits (updated)

- USDT on Ethereum only. Tether freezes include hacks and other cases besides scams; we remove OFAC addresses and report the set as "wallets Tether froze".
- Payments are counted, not people: victims paying through the same exchange look alike on-chain.
- The training and test labels come from the same source (Tether), separated by time. The 200-wallet fesevu check is the only test against a different label source.
- Customer responses and scam rate are modelled and swept.
- No HSM on the L1CC VM, so signing integration is described, not shown.
- Up to 1,000 transfers are fetched per wallet; truncated wallets are flagged in the data.

## 10. Edits needed in `score-before-you-sign.md`

- **One sentence:** "hours before they reach any blacklist" → "days before Tether freezes them".
- **Solution §2, Real data table:** ScamSniffer "updated daily, git history shows when each wallet was added" → "static list of 4,607 addresses; used as a blacklist hit". Add rows for USDT freeze events, fesevu labels and BothBosu dialogues. Move Kaggle to "labels via fesevu".
- **What we will prove §1–2:** use the wording in section 6 above ("payments", "at 1% false alarms").
- **Top risks:** risk 3 (Kaggle definitions) is closed; replace it with "Blockscout credit budget (about 5k calls)".
- **Decision log:** close the open items: fallback headline = Result 2; snapshot at T+4; hash-chained log = yes; Db2 = skipped; video = screen recording + voice-over; detector-fixed chart = the main Result 3 chart.

## 11. Decision record (this session)

Q1 Tether freezes as the clock · Q2 point-in-time features, labels only · Q3 granite-4.2-3b Q4 + BothBosu + 30 SG answers · Q4 4 people, no code before kick-off, freeze at 05:00 Sun · Q5 SQLite, hash-chained log · Q6 this file · Q7 ordinary wallets with ≥ 1 payment, minus OFAC; full set and ≥ 2-payment subset · Q8 headline in days, fallback = Result 2 · Q9 payments not victims · Q10 1% false-alarm threshold on comparison wallets · Q11 snapshots at +1/6/24/72 h, test Jul–Oct 2026 · Q12 cached fetcher, snapshot at T+4 · Q13 replayed real wallet + live box · Q14 P1–P4 split · Q15 real amounts, scam rate swept 0.1–1% · Q16 pitch and video in plan · Q17 one call per wallet, training on older Tether freezes, ~3.5k calls · Q18 checkpoints relative to kick-off.

*Adjustment within Q17's budget: the comparison wallets are split into 1,000 training negatives and 1,000 test comparison wallets, not 1,500 (the model needs negatives from the training period).*
