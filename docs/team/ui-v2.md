# UI v2: customer page and officer console from the new wireframes

Written 18 Oct, 01:00 SGT. **Code freeze is 05:00**, so this plan has about 4 hours. Anything not merged by **03:30** is cut.

**Wireframes** (Claude Design canvases; open them in the browser, or have your Claude Code read them with the Artifact tool):
- Customer page v2/v3: https://claude.ai/artifact/FiVzKZ5CvBBHKaJZnCRzah. Seven screens: check in progress, go ahead, warning, Q1, Q2, Q3, call-back hold.
- Officer console v1: https://claude.ai/artifact/V8tRFB8sGrZtuY8NRKequP. Four screens: sign-in, queue, case view, record outcome.

## Who owns what

| Work | Files | Owner |
|---|---|---|
| Both pages, built to the wireframes | `static/customer.html`, `static/officer.html` | **D (Advay)** |
| API changes the pages need | `app.py` | **D (Advay)**, who wrote it |
| Engine-side logic: structured answers, officer outcome codes, wallet facts, demo personas | `answers.py` (new), `payee_memory.py`, `wallet_facts.py` (new), `data/demo/*` | **A (Aanya)**. This is C's area, but Aariv isn't free, so A takes it |
| Free-text answer classifier (NLP model) and its synthetic training data | B's own module, behind the `classify()` interface below | **B (Manan)**, already in progress |

`engine.py` itself does **not** change. Structured answers reach it through the classifier it already accepts (`Engine(classifier=...)`), so Results 2–4 stay valid.

## Rules

1. **The API stays thin.** Tier, hold, scoring and outcome mapping come from A's modules or the engine. `app.py` only reads them, formats them and passes them through. Pages contain no decision logic.
2. **Additive only.** New fields and endpoints, no renames or removals. The current pages must keep working until D swaps them out.
3. **One owner per file.** Nobody edits a file they don't own. If you need something from someone else's file, send the request in the team chat.
4. **Honest numbers.** The wireframes are mockups and some of their sample text contradicts our results. Use the cut list below. Every number on screen is real (from the engine or the data) or labelled *sample* or *modelled*.
5. **Keep the demo controls.** The officer page's demo reset/next and the live address box stay, because the video uses them.

## Build, cut or fake: wireframe element by element

P1 = must have for the video. P2 = if time allows by 03:00. Cut = don't build.

### Customer page (D builds; data from A via D's API)

| Element | Source | Priority |
|---|---|---|
| Header: `[Exchange logo]` and "Protected by Starlock" | static | P1 |
| **New: a banner reading "Simulated exchange withdrawal screen. In production this check runs inside the exchange's own withdrawal flow, just before signing."** | static | P1 |
| "Signed in as TAN SIEW LIAN · Account ending 4821" | A's `data/demo/personas.json` (fictional), via the decision's `customer` field | P1 |
| Wallet, amount, Ethereum · USDT | existing form | P1 |
| "≈ S$" | page constant `USDT_SGD = 1.29`, labelled "sample rate" | P2 |
| Check-in-progress steps | page animation only; the real call takes milliseconds, so keep it to 1 s or less | P2 |
| Go ahead (release), Warning (warning), Questions (question), Hold (hold) | `tier` from `/score` and `/answer` (exists) | P1 |
| Q1 → Q2 → Q3 branching, multi-select Q3, optional free text | `GET /questions` (A's `answers.QUESTIONS`, served by D); the page walks the `next` pointers and posts the whole answer once | P1 |
| Option order shuffled (except "Something else" / "None of these") | page | P2 |
| Hold: reference number | `ref` (D formats `SL-0001` from the case id) | P1 |
| Hold: masked phone | persona `phone_masked` (A) | P1 |
| Hold: "Expected call-back: [time window]" | static "within 15 minutes", labelled *modelled* | P2 |
| Hold and Warning: "Cancel this payment" | `POST /cancel` (D): closes the case and logs it; no memory change | P2 |
| Demo strip: tier, P(scam), latency, platform | `tier`, `p_scam` (label *modelled*), `decide_ms` and `host` (D); show `host` = `s390x` as "LinuxONE". **Never write "NNPA" on this strip**: NNPA gives no speed-up (Result 4) | P1 |
| Language dropdown | **Cut.** English only; keep the dropdown disabled with a "demo: English only" tooltip, or drop it | cut |
| Per-question score path ("0.71 → 0.84 after Q1") | **Cut.** The engine doesn't score per question; showing it would be invented | cut |

### Officer console (D builds)

| Element | Source | Priority |
|---|---|---|
| Sign-in screen | demo only: pre-filled FO-20417 with a "Demo mode" strip, no real auth. Keep it short; the video can skip it | P2 |
| Queue table: rank, ref, masked customer, wallet, amount, expected loss, P(scam), "Why it is here", language, waiting, Claim | `/queue` rows (exists, plus D's new fields): `top_reason` is the strongest hold reason's `detail`; persona from A; `waiting_s` from D's wall-clock `held_at` | P1 |
| Summary strip: waiting count, USDT on hold, oldest waiting | `/queue` → `summary` (D computes from cases) | P1 |
| Summary strip: officers on shift, calls per hour, "my shift" | static, labelled *sample* | P2 |
| Tabs: Unclaimed / My cases / Closed today | case `status` (`open` → `claimed` → `closed`/`cancelled`), filtered on the page | P1 (Unclaimed and Closed); My cases P2 |
| Tab: Release requests (four-eyes) | **Cut.** Mention it as a production next step | cut |
| Claim lock | `POST /claim` (D); 409 if another officer holds it | P2 |
| Case view: payment, customer (name unmasked once claimed), account, masked phone, language | case + persona (A) | P1 |
| "What the customer told us": Q1–Q3 answers and free text | the case's stored `answer` (now a dict); D renders option text from `/questions` | P1 |
| "Why this was held" | engine `reasons` with real/modelled tags (exists). **Replace** the wireframe's "Detector: Keras 0.52 · XGBoost 0.41", "Same pattern as 14 wallets" and "BM25-retrieved reports" with the real reasons. The detector failed (AUC 0.57) and the other two don't exist | P1 |
| Wallet record: first seen, payments in, distinct senders, "other customers who sent here", Tether freeze, known-bad list, payee memory | `wallet_facts` (A, new) + `payers`, `tether_froze_at`, `prior_warnings` (exist). **Drop** "Public blacklist lags by 7 days" (not measured) | P1 |
| Money-flow graph, incoming and "where it went next" | existing Cytoscape graph + `wallet_facts.out_flows` (A) | P2 |
| Call checklist | static | P2 |
| Activity log | D's per-case event list (held, claimed, name viewed, outcome), also appended to the decision log | P2 |
| Notes textarea, Escalate, Call not answered, police report, customer SMS, 24-hour extra check | **Cut** | cut |
| Record outcome: call result, decision (cancel/release/keep), reason code, note | `POST /outcome` new body; D calls A's `payee_memory.outcome_for()`, which maps it to `confirmed` / `cleared` / nothing | P1 |
| "What this changes" box | static text matching what `outcome_for` does | P1 |

## API contract (D implements it; A's modules supply the logic)

Everything already returned stays. New pieces:

```text
GET  /questions          -> answers.QUESTIONS (A), e.g.
     {"start": "why",
      "questions": {
        "why":   {"text": "Why are you sending this money?", "type": "single", "free_text": true,
                  "options": [{"id": "known",        "text": "Paying someone I know and trust", "next": null},
                              {"id": "own_platform", "text": "Investing on a platform I chose myself", "next": null},
                              {"id": "contacted",    "text": "Someone contacted me and told me to move my money", "next": "how"},
                              {"id": "officer",      "text": "An officer from the government, a bank or the police asked me to", "next": "how"},
                              {"id": "other",        "text": "Something else", "next": null}]},
        "how":   {"text": "How did this person contact you?", "type": "single", "options": [... "next": "asked"]},
        "asked": {"text": "Did this person ask you to do any of these?", "type": "multi", "options": [... "next": null]}}}

POST /answer   {"id": 7, "answer": {"why": "officer", "how": "phone", "asked": ["secret", "act_fast"], "text": "optional free text"}}
               (a plain string still works: the old free-text flow)
     -> decision, as now

every decision response (/score, /answer, /live, /demo/next's decision) gains:
     "ref": "SL-0007", "decide_ms": 1.4, "host": "s390x" | "arm64" | ..., "model_on": true,
     "persona": {"name": "TAN SIEW LIAN", "name_masked": "TA* SI** LI**", "account_ending": "4821",
                 "phone_masked": "+65 **** 5678", "language": "English", "sample": true}

POST /cancel   {"id": 7} -> {"id": 7, "status": "cancelled"}
POST /claim    {"id": 7, "officer": "FO-20417"} -> case (409 if claimed by someone else)

GET  /queue -> {"rows": [{...existing fields, "ref", "persona", "p_scam", "top_reason": {"signal", "detail", "kind"},
                          "status", "claimed_by", "waiting_s"}],
                "summary": {"waiting": 5, "usdt_on_hold": 23500.0, "oldest_waiting_s": 660, "closed_today": 3}}
     The current pages read a bare list, so D switches both pages in the same PR as this change.

GET  /case/{id} -> existing fields + "persona", "wallet_facts" (A), "known_bad" (bool), "events": [{"ts", "what", "who"}]

POST /outcome  {"id": 7, "wallet": "0x...", "call": "confirmed_identity" | "other_person" | "no_answer",
                "decision": "cancel" | "release" | "keep", "reason": "<code from payee_memory.REASON_CODES>", "note": ""}
     -> app.py: outcome = payee_memory.outcome_for(decision, reason); if outcome:
               engine.record(OfficerOutcome(wallet, outcome, ts, officer, kind=..., reason=reason))
        422 if outcome_for raises (e.g. "release" with a confirmed-scam reason)
     The old body {"wallet", "outcome"} still works.
```

## Merge order and times

| By | What | Who |
|---|---|---|
| 01:20 | Both read this file; D says yes to the contract or posts changes in chat | A, D |
| 02:15 | **A's backend PR merged** (`aanya/ui-v2-backend`): `answers.py`, `wallet_facts.py`, `payee_memory.py` outcome codes, `data/demo/personas.json`, `data/demo/coached_answer.json` | A, reviewed by D |
| 02:15 | D has both pages laid out against mock JSON shaped like the contract above | D |
| 03:00 | D's `app.py` changes on top of A's PR; pages switched from mocks to the real API | D |
| 03:30 | **D's PR merged**; nothing new after this | D, reviewed by A |
| 03:30–04:15 | Both run the demo flow locally (below); fixes only | A, D |
| 04:15–04:45 | Pull on the VM, run in the container, take the screenshots for the submission | D (+ B for the VM) |
| 05:00 | Code freeze | all |

B's classifier joins only if it's ready by 03:00. Otherwise the keyword fallback stays and B's model is a "next step".

## Acceptance checks (both run these before the 03:30 merge)

1. `python answers.py`, `python wallet_facts.py`, `python payee_memory.py`, `python engine.py`: all self-checks pass.
2. Customer page, `uvicorn app:app --reload`, then `http://127.0.0.1:8000`:
   - a 50 USDT payment to a wallet the customer has paid before (from the warning step below) gives Go ahead
   - a first payment under 1,000 USDT gives Warning
   - a first payment of 1,000 USDT or more gives Q1
   - Q1 "Someone I know" gives Go ahead
   - Q1 "An officer…", then Q2, then Q3 with "Keep this a secret" ticked, gives Hold with a ref and the masked phone
3. Officer page, `/officer`:
   - the held case from step 2 appears in Unclaimed, top-ranked by expected loss
   - Claim, then the case view shows the answers, the real reasons with tags, and the wallet record
   - Record outcome "Cancel / Confirmed scam: police impersonation" takes it off the queue
   - a new payment to that wallet from another customer is held straight away
4. Demo spine: `/demo/reset`, then `/demo/next` ×13. The narration numbers still hold: the officer confirms after payment 2, all 12 later payments are held, 120,229 USDT. The scripted confirm shows as **modelled** with no relabel hack in `app.py`.
5. The decision log verifies.
6. Phone width (390 px): no horizontal scroll on the customer page.

---

## Prompt for A's agent (paste into Claude Code in your own folder)

```text
You are Person A's (Aanya) agent in /Users/aanyajain/ibm-hackathon-2026. Read CLAUDE.md and docs/team/ui-v2.md first:
ui-v2.md is the plan; you build the "A" pieces of its API contract. Work in your own worktree:

    git -C /Users/aanyajain/ibm-hackathon-2026 fetch origin
    git -C /Users/aanyajain/ibm-hackathon-2026 worktree add ../ibm-ui-v2-backend -b aanya/ui-v2-backend origin/main
    cd ../ibm-ui-v2-backend

You may edit ONLY: answers.py (new), wallet_facts.py (new), payee_memory.py, data/demo/personas.json (new),
data/demo/coached_answer.json (new), and A's own rows/log in docs/team/progress.md. Do NOT edit engine.py, app.py,
static/*, granite.py, model.py. Hard deadline: PR open by 02:00 SGT; keep it small. Python 3.12, stdlib only,
assert-based _self_check() in each module run by `python <module>.py`, same style as payee_memory.py / features.py.

1. answers.py
   - QUESTIONS: the Q1/Q2/Q3 tree exactly as in ui-v2.md's contract, with the wireframe's option text (Q1 "why",
     Q2 "how": phone / text_whatsapp / social_dating / email / in_person / not_sure, Q3 "asked" multi: secret /
     act_fast / new_account / safe_wallet / install_app / none). Q1 known / own_platform / other end the questions;
     contacted / officer go on to Q2 then Q3.
   - class StructuredClassifier(free_text=None): drop-in for Engine(classifier=...). ask(withdrawal, reasons)
     delegates to free_text.ask if it has one, else returns engine.TEMPLATE_QUESTION. classify(answer):
       * str  -> free_text.classify(answer) (the old flow, unchanged)
       * dict -> validate ids against QUESTIONS (ValueError on unknown ids, on a multi answer for a single
                 question, or on "none" ticked together with anything else).
                 confirms_script = (why == "officer") or (any Q3 item except "none") or (free text confirms).
                 A "no" never cancels a free-text confirm.
                 scam_type: one of granite.SCAM_TYPES; officer or safe_wallet -> government_impersonation;
                 how == social_dating -> romance; else the free-text classifier's type if it confirmed; else
                 "investment" for own_platform, "none" when nothing confirms. Pick and document a sensible
                 mapping for the rest.
                 source: "structured" or "structured+<free-text source>". Don't set kind (the app and demo pass
                 answer_kind).
   - The free-text classifier is injected (default: granite). B (Manan) will ship an NLP classifier with the same
     classify(text) -> {"scam_type", "confirms_script", "source"} shape; it must plug in with one line.
   - Self-check: run the engine end to end with Engine(classifier=StructuredClassifier(stub)), in-memory
     PayeeMemory, FixedClock: a structured "officer" answer to a question-tier withdrawal -> hold, and another
     customer's next payment to that wallet -> hold (memory hit); "known" -> release; string answers still work.

2. payee_memory.py (C's file; Aariv agreed A takes it tonight; keep changes additive)
   - OfficerOutcome gains kind: str = "real" and reason: str = "". The officer_confirmed Evidence must carry the
     outcome's kind (now hard-coded "real"), so a scripted demo confirm shows as modelled. Store it in the db; keep
     old rows/defaults working. Extend _self_check for it.
   - REASON_CODES: an ordered dict of code -> label (the wireframe's six: confirmed_impersonation,
     confirmed_investment_romance, unsure_cancelled, genuine_known_recipient, genuine_own_wallet, other).
   - outcome_for(decision, reason) -> "confirmed" | "cleared" | None:
     cancel + confirmed_* -> "confirmed"; release + genuine_* -> "cleared"; cancel + unsure_cancelled -> None;
     keep -> None; other -> None. ValueError for contradictions (release with confirmed_*, cancel with genuine_*)
     and unknown codes. Self-check each row.
   - Run python payee_memory.py, python engine.py, python replay.py's self-check (if any) and make sure Result 2's
     replay code still runs unchanged (the defaults must keep its behaviour).

3. wallet_facts.py
   - wallet_facts(history, as_of, bad=frozenset()) -> dict, using ONLY transfers with ts < as_of (point in time,
     like features.py; reuse its helpers where sensible): first_seen_ts, n_payments_in (>= 10 USDT, as MIN_USDT),
     n_senders_in, n_senders_in_7d, usdt_in, usdt_out, median_forward_h (or None), out_flows (top 3 destinations by
     USDT: {to, usdt, first_ts}), touched_known_bad (bool), truncated (from the history). All values are "real".
     None-safe for a missing history. Self-check includes a no-future-leakage assert like features.py's.

4. data/demo/personas.json: a list of 13 FICTIONAL customers in demo-sender order (customer-1 is "TAN SIEW LIAN",
   account ending 4821, phone "+65 **** 5678", English, as in the video). Fields: name, name_masked (PayNow-style:
   first two letters of each word then asterisks, e.g. "TA* SI** LI**"), account_ending, phone_masked, language
   (English for all; the page is English only), sample: true. Add a "default" persona for unknown customers.
   data/demo/coached_answer.json: the demo's scripted coached answer as a structured dict
   {"why": "officer", "how": "phone", "asked": ["secret", "act_fast", "safe_wallet"], "text": <app.py's COACHED string>}.
   Check, with the engine and the structured classifier, that the demo wallet replay still gives the narration
   numbers in data/demo/narration_numbers.json (officer confirms -> 12 held, 120,228.96 USDT). If not, stop and report.

5. Commit with clear messages. Push the branch and open a NORMAL (not draft) PR into main titled
   "UI v2 backend: structured answers, outcome codes, wallet facts, personas (A)". If git push / gh are blocked,
   stop and print the exact commands for Aanya to run in her terminal. Then add one Log line + A rows in
   docs/team/progress.md (A's section only) via a throwaway worktree on origin/main and push to main (retry on
   rejection with fetch+rebase, never force).

Final report: what each function returns (one example each), the exact import lines D needs in app.py, test output,
the PR link, and anything in ui-v2.md you had to change.
```

## Prompt for D's agent (Advay pastes into Claude Code in his folder)

```text
You are Person D's (Advay) agent in the ibm-hackathon-2026 repo. Read CLAUDE.md and docs/team/ui-v2.md first: it is
the plan, the cut list and the API contract. Read both wireframes (Claude Design canvases, readable with the Artifact
tool's read action; list files with scope "files", then read project/*.dc.html):
  customer: https://claude.ai/artifact/FiVzKZ5CvBBHKaJZnCRzah
  officer:  https://claude.ai/artifact/V8tRFB8sGrZtuY8NRKequP
Work in a worktree on branch advay/ui-v2 from origin/main. You own app.py, static/customer.html,
static/officer.html. Don't edit engine.py, payee_memory.py, answers.py, wallet_facts.py or data/: those are A's
(she is building them on aanya/ui-v2-backend, PR due 02:00). Hard deadline: your PR merged by 03:30 SGT.

Phase 1 (now, no backend dependency):
  - Rebuild static/customer.html to the customer wireframe: one mobile-first page (fits 390 px, no horizontal scroll),
    states check -> release / warning / question (Q1 -> Q2 -> Q3 from GET /questions, walking `next`) -> hold.
    Add the "Simulated exchange withdrawal screen" banner from ui-v2.md. Demo strip shows tier, P(scam) (labelled
    modelled), decide_ms, host (s390x shown as "LinuxONE"). Never say NNPA on it.
  - Rebuild static/officer.html to the officer wireframe: queue with summary strip and tabs, case view, record-outcome
    form. KEEP the existing demo reset/next controls, the live address box and the Cytoscape graph.
  - Plain HTML/CSS/JS as now, no build step; any CDN script pinned with SRI as the Cytoscape one is.
  - Follow the cut list exactly: no detector scores, no per-question score path, no BM25/Granite-summary claims,
    no four-eyes, English only. Sample-only values are labelled "sample".
  - Until A's PR lands, drive the pages from a MOCK object at the top of each script, shaped exactly like the contract.

Phase 2 (after A's PR is merged; rebase onto main):
  - app.py, additive only, per the contract: GET /questions; /answer accepts the structured dict or a string;
    Engine(classifier=answers.StructuredClassifier(granite)); ref/decide_ms/host/model_on/persona on every decision;
    /cancel; /claim; /queue -> {rows, summary}; /case adds persona, wallet_facts, known_bad, events; new /outcome
    body via payee_memory.outcome_for (keep the old body working); demo spine uses data/demo/coached_answer.json
    with answer_kind="modelled" and records the scripted confirm with OfficerOutcome(kind="modelled"); delete the
    officer_confirmed relabel ponytail in /case. No decision logic in app.py.
  - Swap the pages' mocks for the real endpoints.

Check: run every acceptance check in ui-v2.md section "Acceptance checks" (including the demo spine numbers and
decision-log verify) in the browser, locally. Then open a NORMAL (not draft) PR into main, ask Aanya to review, and
add your rows/log line to docs/team/progress.md (D's section only). After merge: pull on the VM, rebuild the
container, re-run the demo, and take the submission screenshots (customer hold screen, officer case view, docker ps).

Final report: what was built vs cut, anything in the contract you changed (tell Aanya first), test results, PR link.
```

## Note for B (Manan): free-text classifier

The structured questions decide most cases. Your NLP model reads only the optional free-text box. To plug in with one line, it needs:

- `classify(text) -> {"scam_type": <one of granite.SCAM_TYPES>, "confirms_script": bool, "source": "<model name>"}`
- under 2 s on the VM, with no network calls (answer text never leaves the box)
- loads on s390x (no pickle across architectures)

Report accuracy separately for real data (BothBosu test set, `data/sg_answers.csv`) and synthetic data. Label anything trained on synthetic data as *modelled* on the slides.

If it's ready and merged by **03:00**, D switches `StructuredClassifier(granite)` to `StructuredClassifier(<your module>)`. If not, the keyword fallback stays and your model goes on the "next steps" slide with its accuracy numbers.

## Round 2: team feedback on the merged pages (18 Oct, 02:15)

The team reviewed the merged pages and found them disconnected from what we had agreed. A fixed them on `aanya/ui-v2-fixes`, in D's files (`app.py`, `static/*`) because of the time left; **D reviews the PR before it merges**.

| Feedback | Fix | Status |
|---|---|---|
| No customer sign-in page | Demo sign-in screen first: customer ID (Mrs Tan pre-filled; `customer-2`…`customer-13` in a list), password and one-time code pre-filled, labelled "demo login"; Sign out returns to it | done |
| Language option for users | Dropdown in the header with Singapore's four official languages: English, 中文, Bahasa Melayu, தமிழ். Every customer screen and Q1–Q3 are translated; the engine still receives option ids, so the decision never depends on the language. Remembered per browser | done (draft translations: **a native speaker should check zh/ms/ta before the video**) |
| Currency converter too big; should be SGD; only 2 cryptos | Ticker, converter and 40-coin list removed. USDT or ETH only (Ethereum network, as the idea doc says); one small "≈ S$" line (CoinGecko live rate, or a labelled sample rate). ETH is scored at its USDT value, and the page says so | done |
| Must fit laptops, not only phones | Exchange-style web layout: top bar and nav, the withdrawal card plus a side column ("This session's withdrawals", "About this check") on wide screens; one column on phones. Checked at 1366 px and 390 px, no horizontal scroll | done |
| Officer page doesn't update when the customer page adds an entry | The queue only lists **holds**, and it only refreshed while the queue view was showing. Now there's an "Every check, live" table on the officer page (all tiers, from the new `GET /activity`), and a "New hold" banner appears even while an officer is inside a case | done |
| Cleaner outcome screens, as in the wireframe | Outcome boxes as drawn: green "Check complete", amber "Please review before sending", red question box, red hold box with the bullet list and a "What happens next" card; the stamp labels are gone | done |
| Product name | "Protected by Starlock"; officer console brand "Starlock"; references `SL-0001` | done |

API additions (additive, in `app.py`): `WithdrawalIn` takes optional `asset` (`USDT`/`ETH`) and `qty` for display; `GET /activity`; `POST /sent` (the customer pressed Send after go-ahead or a warning). The demo spine is unchanged: 12 held, 120,228.96 USDT.

### Still open (for an agent or a person, after the freeze or if time allows)

1. **Native-speaker check of the zh, ms and ta strings** (`T` and `QT` in `static/customer.html`). Highest priority if the video shows another language.
2. **Free-text answers in other languages:** the keyword classifier reads English only. B's NLP model could cover this; until then the structured answers carry the decision.
3. **"Old features that vanished":** the team should list any specific earlier feature still missing. Everything from the first pages is still there: customer ID (now the sign-in), the officer's demo reset/next/play, the live address box, the why-card and the graph.
4. **ETH wallet history:** the engine reads USDT transfers only, so an ETH payment is judged on the wallet's USDT history. Native ETH history is roadmap.
5. **Officer console styling** still uses the earlier ledger look (different fonts from the customer page). It's fine for the demo; aligning both is optional.
6. The customer page's Wallet and History tabs are decoration.
