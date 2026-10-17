# D: App and delivery

Your tickets for the reframed plan (spec: [#1](https://github.com/mananpansari/ibm-hackathon-2026/issues/1)). Each one is a GitHub issue, which stays the source of truth. Update your rows in [progress.md](progress.md) as you go.

| Ticket | Title | Blocked by |
|---|---|---|
| [#4](https://github.com/mananpansari/ibm-hackathon-2026/issues/4) | Score API and bare customer page | [#3](https://github.com/mananpansari/ibm-hackathon-2026/issues/3) (C) |
| [#8](https://github.com/mananpansari/ibm-hackathon-2026/issues/8) | Customer question flow | [#4](https://github.com/mananpansari/ibm-hackathon-2026/issues/4) (D), [#7](https://github.com/mananpansari/ibm-hackathon-2026/issues/7) (C) |
| [#12](https://github.com/mananpansari/ibm-hackathon-2026/issues/12) | Officer queue and outcomes | [#4](https://github.com/mananpansari/ibm-hackathon-2026/issues/4) (D), [#6](https://github.com/mananpansari/ibm-hackathon-2026/issues/6) (C), [#9](https://github.com/mananpansari/ibm-hackathon-2026/issues/9) (C) |
| [#13](https://github.com/mananpansari/ibm-hackathon-2026/issues/13) | Why-card and payment graph | [#12](https://github.com/mananpansari/ibm-hackathon-2026/issues/12) (D) |
| [#14](https://github.com/mananpansari/ibm-hackathon-2026/issues/14) | Granite asks and classifies | [#7](https://github.com/mananpansari/ibm-hackathon-2026/issues/7) (C) |
| [#17](https://github.com/mananpansari/ibm-hackathon-2026/issues/17) | Demo spine and live address box | [#8](https://github.com/mananpansari/ibm-hackathon-2026/issues/8) (D), [#11](https://github.com/mananpansari/ibm-hackathon-2026/issues/11) (B), [#13](https://github.com/mananpansari/ibm-hackathon-2026/issues/13) (D), [#14](https://github.com/mananpansari/ibm-hackathon-2026/issues/14) (D), [#16](https://github.com/mananpansari/ibm-hackathon-2026/issues/16) (A) |

## [#4](https://github.com/mananpansari/ibm-hackathon-2026/issues/4) Score API and bare customer page

**Blocked by:** [#3](https://github.com/mananpansari/ibm-hackathon-2026/issues/3) (C)

### What to build

A customer can type a withdrawal (wallet and amount) into a plain page, submit it, and see the engine's tier and reasons. The API is a thin wrapper with no decision logic of its own.

## Acceptance criteria

- [ ] A score endpoint accepts a withdrawal and returns the engine's decision unchanged
- [ ] Customer page submits a withdrawal and shows the tier and plain-language reasons
- [ ] API reads the Blockscout key only from the environment, never sends it to the page
- [ ] Runs locally with the snapshot's recorded histories

## [#8](https://github.com/mananpansari/ibm-hackathon-2026/issues/8) Customer question flow

**Blocked by:** [#4](https://github.com/mananpansari/ibm-hackathon-2026/issues/4) (D), [#7](https://github.com/mananpansari/ibm-hackathon-2026/issues/7) (C)

### What to build

On the customer page, an unusual withdrawal shows the engine's question, the customer answers in their own words, and the page shows the outcome (released, or held for a call-back with a calm plain-language explanation).

## Acceptance criteria

- [ ] Answer endpoint passes the answer to the engine and returns the new decision
- [ ] Page shows the question, accepts free text, and shows release or hold
- [ ] Hold message explains in plain English what happens next
- [ ] Works end to end on recorded histories

## [#12](https://github.com/mananpansari/ibm-hackathon-2026/issues/12) Officer queue and outcomes

**Blocked by:** [#4](https://github.com/mananpansari/ibm-hackathon-2026/issues/4) (D), [#6](https://github.com/mananpansari/ibm-hackathon-2026/issues/6) (C), [#9](https://github.com/mananpansari/ibm-hackathon-2026/issues/9) (C)

### What to build

Fraud officers see held withdrawals in a queue ordered by expected loss, and can mark each destination wallet as cleared or scam-confirmed after a call; the outcome flows back into payee memory and changes later decisions.

## Acceptance criteria

- [ ] Queue lists held withdrawals by expected loss
- [ ] Officer can mark cleared or confirmed; payee memory updates
- [ ] A cleared wallet no longer triggers holds for new withdrawals
- [ ] Page is officer-only (not linked from the customer page)

## [#13](https://github.com/mananpansari/ibm-hackathon-2026/issues/13) Why-card and payment graph

**Blocked by:** [#12](https://github.com/mananpansari/ibm-hackathon-2026/issues/12) (D)

### What to build

Each held withdrawal in the officer queue opens a why-card showing the signals that fired (with real/modelled tags), the customer's answer, earlier warnings on the wallet, and a payment graph of every customer who paid or tried to pay the same wallet.

## Acceptance criteria

- [ ] Why-card shows signals, sources, the answer and prior warnings
- [ ] Payment graph shows customers and the destination wallet, growing as the replay runs
- [ ] Graph library loaded from a pinned CDN version
- [ ] Shows when Tether later froze the wallet, if it did

## [#14](https://github.com/mananpansari/ibm-hackathon-2026/issues/14) Granite asks and classifies

**Blocked by:** [#7](https://github.com/mananpansari/ibm-hackathon-2026/issues/7) (C)

### What to build

Granite running on llama.cpp on the same machine writes the customer question (grounded in a small set of advisories in our own words) and classifies the free-text answer into scam type and confirms-script, replacing the stub. If Granite is missing or slower than 2 s, template questions are used and only classification falls back.

## Acceptance criteria

- [ ] Granite question and classification behind the engine's classifier interface
- [ ] Fallback to templates when Granite is unavailable or exceeds 2 s
- [ ] Accuracy measured on BothBosu dialogues plus ~30 Singapore answers we write
- [ ] No answer text leaves the machine

## [#17](https://github.com/mananpansari/ibm-hackathon-2026/issues/17) Demo spine and live address box

**Blocked by:** [#8](https://github.com/mananpansari/ibm-hackathon-2026/issues/8) (D), [#11](https://github.com/mananpansari/ibm-hackathon-2026/issues/11) (B), [#13](https://github.com/mananpansari/ibm-hackathon-2026/issues/13) (D), [#14](https://github.com/mananpansari/ibm-hackathon-2026/issues/14) (D), [#16](https://github.com/mananpansari/ibm-hackathon-2026/issues/16) (A)

### What to build

On the VM, the demo replays the chosen frozen wallet payment by payment: the 1st customer's answer confirms the script, the 2nd customer's payment to the same wallet is held, and the officer view shows the why-card and the graph growing until the freeze date. A judge can paste any address and get a live decision through the cached Blockscout client.

## Acceptance criteria

- [ ] Full demo spine runs end to end on the VM in about 90 s
- [ ] 2nd customer is held because of the 1st customer's answer
- [ ] Live box scores a pasted address via the cached client and works from the snapshot if Blockscout is unreachable
- [ ] Credit guard respected for live lookups
