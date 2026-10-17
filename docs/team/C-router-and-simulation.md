# C: Router and simulation

Your tickets for the reframed plan (spec: [#1](https://github.com/mananpansari/ibm-hackathon-2026/issues/1)). Each one is a GitHub issue, which stays the source of truth. Update your rows in [progress.md](progress.md) as you go.

| Ticket | Title | Blocked by |
|---|---|---|
| [#3](https://github.com/mananpansari/ibm-hackathon-2026/issues/3) | Decision engine core: release or warn, logged | None, can start now |
| [#6](https://github.com/mananpansari/ibm-hackathon-2026/issues/6) | Shared payee memory and call-back hold | [#3](https://github.com/mananpansari/ibm-hackathon-2026/issues/3) (C) |
| [#7](https://github.com/mananpansari/ibm-hackathon-2026/issues/7) | Question tier in the engine | [#6](https://github.com/mananpansari/ibm-hackathon-2026/issues/6) (C) |
| [#9](https://github.com/mananpansari/ibm-hackathon-2026/issues/9) | Capacity-aware holds and Result 3 sweep | [#6](https://github.com/mananpansari/ibm-hackathon-2026/issues/6) (C) |

## [#3](https://github.com/mananpansari/ibm-hackathon-2026/issues/3) Decision engine core: release or warn, logged

**Blocked by:** None, can start now

### What to build

The decision engine exists as one module behind the agreed seam: given a withdrawal (customer, destination wallet, amount, time), it returns a decision (tier, reasons with their source, expected loss). In this first slice it releases ordinary payments and warns on a first-time payee. Every decision is appended to a hash-chained log. History source, payee memory and clock are injected, so it runs on recorded histories with no network.

## Acceptance criteria

- [ ] decide() returns release or warning with reasons for recorded-history withdrawals
- [ ] Each decision is appended to an append-only log whose entries chain the previous entry's hash, with inputs and engine version
- [ ] Tampering with any past log entry is detected by a verify step
- [ ] No wall-clock or network access inside the engine; clock and history source are injected
- [ ] Runnable assert-based scenario check (first-time payee warned, repeat ordinary payee released, log verifies)

## [#6](https://github.com/mananpansari/ibm-hackathon-2026/issues/6) Shared payee memory and call-back hold

**Blocked by:** [#3](https://github.com/mananpansari/ibm-hackathon-2026/issues/3) (C)

### What to build

Warnings about a destination wallet are remembered across customers. A customer report, an officer outcome or a Tether freeze of the wallet or a counterparty (before now) is recorded, and later withdrawals to that wallet from any customer are held for a call-back. Officers can clear a wallet so it stops triggering holds, or confirm it as scam so it never decays.

## Acceptance criteria

- [ ] record() accepts customer reports, officer outcomes (cleared / confirmed) and freeze events
- [ ] Customer B's withdrawal to a wallet reported by customer A is held, with the report in the reasons
- [ ] 'Cleared' stops further holds; 'confirmed' pins the wallet with no decay
- [ ] Unconfirmed warnings decay over time (half-life configurable; revisit the plan's 6 h given ~4-month wallet lifetimes)
- [ ] A Tether freeze recorded after the decision time is never used
- [ ] Scenario checks for each of the above at the engine seam

## [#7](https://github.com/mananpansari/ibm-hackathon-2026/issues/7) Question tier in the engine

**Blocked by:** [#6](https://github.com/mananpansari/ibm-hackathon-2026/issues/6) (C)

### What to build

Unusual withdrawals (new payee plus large or unusual amount, or a moderate signal) get one template question instead of a straight warning. The customer's free-text answer goes through a classifier (stubbed for now) that returns a scam type and whether it confirms a scam script; a confirming answer turns into a call-back hold and a payee-memory warning.

## Acceptance criteria

- [ ] decide() returns a question tier with a template question for unusual withdrawals
- [ ] Submitting an answer re-decides the withdrawal using the classifier result
- [ ] A confirming answer produces a hold and a memory warning that affects other customers
- [ ] Classifier is behind an interface so Granite can replace the stub without engine changes
- [ ] Scenario checks at the engine seam with the stub classifier

## [#9](https://github.com/mananpansari/ibm-hackathon-2026/issues/9) Capacity-aware holds and Result 3 sweep

**Blocked by:** [#6](https://github.com/mananpansari/ibm-hackathon-2026/issues/6) (C)

### What to build

Call-back holds respect a daily officer capacity: they are ranked by expected loss (amount x signal-derived probability) and anything over capacity drops to the question tier. A sweep over capacity, using real payment amounts from the snapshot and a swept scam rate (0.1-1%), compares the ladder with rules-only, a fixed threshold and calling everyone, and produces the Result 3 chart (S$ averted vs capacity, legitimate users held alongside).

## Acceptance criteria

- [ ] Over capacity, the largest expected losses keep holds and the rest get questions
- [ ] Capacity is configurable per day
- [ ] Sweep produces a chart and a table for the four policies
- [ ] Modelled inputs (scam rate, stop rate, friction) are swept and labelled as modelled
- [ ] Scenario check for the capacity rule at the engine seam
