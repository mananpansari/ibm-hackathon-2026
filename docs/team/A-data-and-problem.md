# A: Data and problem

Your tickets for the reframed plan (spec: [#1](https://github.com/mananpansari/ibm-hackathon-2026/issues/1)). Each one is a GitHub issue, which stays the source of truth. Update your rows in [progress.md](progress.md) as you go.

| Ticket | Title | Blocked by |
|---|---|---|
| [#2](https://github.com/mananpansari/ibm-hackathon-2026/issues/2) | Commit P1 snapshot and feasibility evidence | None, can start now |
| [#10](https://github.com/mananpansari/ibm-hackathon-2026/issues/10) | Result 2 replay through the engine | [#2](https://github.com/mananpansari/ibm-hackathon-2026/issues/2) (A), [#6](https://github.com/mananpansari/ibm-hackathon-2026/issues/6) (C) |
| [#16](https://github.com/mananpansari/ibm-hackathon-2026/issues/16) | Demo wallet and narration numbers | [#10](https://github.com/mananpansari/ibm-hackathon-2026/issues/10) (A) |

## [#2](https://github.com/mananpansari/ibm-hackathon-2026/issues/2) Commit P1 snapshot and feasibility evidence

**Blocked by:** None, can start now

### What to build

Everything the team builds on is on the branch: the feasibility report, its three scripts, the volume-matched comparison wallets added to the snapshot, and the derived data (wallet histories, feature rows, freeze list, known-bad set, sample). The parent spec's links resolve for every teammate.

## Acceptance criteria

- [ ] Feasibility report and the three feasibility scripts are committed and pushed
- [ ] Derived data files are committed; the API response cache, logs and .env stay out of git
- [ ] A fresh clone can run the features self-check and the feasibility script without any Blockscout calls
- [ ] Repo has a short note on how to re-run the snapshot and what it costs in calls

## [#10](https://github.com/mananpansari/ibm-hackathon-2026/issues/10) Result 2 replay through the engine

**Blocked by:** [#2](https://github.com/mananpansari/ibm-hackathon-2026/issues/2) (A), [#6](https://github.com/mananpansari/ibm-hackathon-2026/issues/6) (C)

### What to build

Every wallet Tether froze in Jul-Oct 2026 is replayed through the same decide() calls the product uses, payment by payment with memory carried forward. The output reports how many payments came after the first available warning and how many the engine would have held, split by warning source (real: counterparty freeze; modelled: customer answer rate swept 0.1-0.9; model flag once available), plus the legitimate-hold rate from the same replay over both comparison sets.

## Acceptance criteria

- [ ] Replay uses only information available at each payment's time
- [ ] Results split by warning source; real and modelled numbers never mixed
- [ ] Legitimate-hold rate reported on random and volume-matched comparison wallets
- [ ] Numbers quoted as payments ('up to N victims' at most)
- [ ] One small fixed-history replay asserted exactly (e.g. 5 payments, warning at the 2nd -> 3 held)
- [ ] Results written into the feasibility report or a results doc

## [#16](https://github.com/mananpansari/ibm-hackathon-2026/issues/16) Demo wallet and narration numbers

**Blocked by:** [#10](https://github.com/mananpansari/ibm-hackathon-2026/issues/10) (A)

### What to build

One real wallet Tether froze is chosen for the demo, with its payment timeline prepared for replay and the exact numbers the voice-over will quote (payments, amounts, days until freeze, payments held).

## Acceptance criteria

- [ ] Demo wallet chosen with the reason recorded
- [ ] Payment timeline ready for the replay in the demo
- [ ] Every number in the narration traceable to the replay output
- [ ] Video script problem section drafted
