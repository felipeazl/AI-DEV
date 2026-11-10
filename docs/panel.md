# Panels and strip

What the strip above the prompt and the AiDW panels show, where each piece of data comes from, and what the agents
write for it (the `aidw-mods` mod, Claude Code only). The mods in general are in [mods.md](mods.md).

The strip works in every context. The panels and the strip buttons disappear in a context that turns them off
(`[mods] panel = false` in `context.toml`); inside them, each tab appears only when the file it reads exists.

## Principles

- **Simple and in the Claude app's style:** cards with a subtle border, small grey labels, space between blocks.
  Claude's orange only marks what is happening now or waits for you.
- **Nothing opens by itself:** panels open by the strip button or the command. No toasts or notifications of their own.
- **Made for the desktop app.** The terminal gets the same information in a simpler drawing (▰▱ bars, keys).
- **The panels only inform:** every decision (keep or discard a finding, a manual step's result, what to publish,
  approving a PR, answering a question, commenting on a card) is made in the chat, with the orchestrator and the agent
  of the step. No panel has a decision button or an answer field.
- **No token budget or round limit** on any screen: a demand iterates until it is done.
- **Colors** come from the Claude theme, so they follow light and dark mode: orange = now or waiting for you; blue =
  with the team, QA or UX; yellow = attention (bars from 75%, returned from the team or QA, implemented without a test);
  red = from 90%, failed; green = covered, fixed, passed, done; purple = a question.

## Strip

```text
AiDW us-1234 Review ● waits for you        context ▰▰▰▱▱ 41% · 82k   7d ▰▰▰▰▱ 58%   5h ▰▰▰▰▰ 91% · renews 16:40
● Coder Sonnet medium · fix r1 · 2m10s
                                                                  General  Metrics  Tests and Review 4
```

1. **Demand and usage:** AiDW, the id, the current step (with the use in front when it is not development: "PR review ·
   Final review") and **● waits for you** when the step is yours (`HUMAN_APPROVAL`, plan approval, triage, your code
   review, manual test, PR, final review); on the other side, the context as a % of the model's real window with the
   tokens, and the 7d and 5h windows.
2. **Running agents** (name, model and effort, task, time), with the orange dot. With no agent, the line is not shown.
3. **The buttons**, on one line to the right: **General**; **Metrics** (when a delegation or orchestrator turn is
   recorded); **Tests and Review** (when the demand has a review, a script or PR comments; **Questions** in a survey),
   with the number still waiting for a decision.

- Bars: normal up to 74%, yellow 75–89%, red from 90%. From 75% the 7d and 5h show the local time the window renews
  ("91% · renews 16:40"); at 100%, "limit · back 16:40".
- Data: context and usage windows from the session (the windows only on a subscription); running agents from the mod.
- The strip disappears in `DONE`; **`/strip`** hides and shows it.

## Panels

| Panel | Button / command | Development | PR review | Survey |
|---|---|---|---|---|
| General | **General** · `/panel [tab]` | map, criteria and rules | map | map, card × code, estimate |
| Metrics | **Metrics** · `/metrics` | usage | usage | usage |
| Tests and Review | **Tests and Review** · `/review-tests` | tabs Review · Tests | Comments | becomes **Questions** |

The use (development, PR review, survey) comes from the demand's files. A demand that finished its survey and moved on
already shows as development, even before the plan is written.

- **Each panel is its own pane** ("AiDW · General", "AiDW · Metrics", "AiDW · Tests and Review" or "AiDW · Questions");
  with two or more open, the app shows tabs between them. Leaving orchestrator mode closes all of them. In a window too
  narrow, the panel does not open and the command says why.
- **`/panel <tab>`** opens the panel that has the tab: `review`, `tests`, `comments`, `questions` open Tests and
  Review; anything else opens General. The old Portuguese tab names still work.
- **Single header:** type and number, the situation (`● Review · waits for you`, `Code review · with the team` in blue,
  `Paused`, `Done` in green) and the card title.
- **Tabs** (only in Tests and Review, only with two or more): next to the name, in orange, what still waits for a
  decision. A tab without data is hidden. The panel opens on the first tab with something pending. In the terminal,
  keys `1`, `2`… and `r` (refresh) work; in the app, tabs are click only.

### Steps

The progress has two groups: **AiDW** and **Team and QA**.

| Use | AiDW | Team and QA |
|---|---|---|
| Development | Understanding · Plan · Your approval · Implementation · Review · Your review · Tests · PR | the context's (e.g. UX validation) · Code review · QA tests · Done |
| PR review | Understanding · Preparation · Review · Final review · Done | — |
| Survey | Understanding · Exploration · Estimate · Final review · Done | — |

Outside steps the context adds (`[[workflows.external_steps]]`) appear only in a demand that goes through them
(`demand set --extra-step`). Steps of the old flow fall into the equivalent phase.

## General

One page, no tabs:

1. **Demand map:** the summary (up to 4 lines) and the **progress** in both groups, with the current step's name. When
   the team or QA returns the demand, the outside step turns yellow with "returned from QA tests"; a counter keeps the
   returns per step.
2. **Numbers**, only what is in no other block: in a PR review, the PRs and the published comments; in a survey, the
   open questions.
3. **Next step:** the note of `demand.json` (`demand set --note`), when there is one.
4. **The use's block:** development → **Criteria and rules**; survey → **Card × code** and **Estimate**.

Data: the summary is `demand.json` → `summary`, written by the orchestrator when it understands the card; the outside
steps are written by the orchestrator **when you tell it** in the chat.

### Criteria and rules (development)

- Coverage per type at the top, and three cards: **Acceptance criteria** (`CA1…`), **Business rules** (`RN1…`) and
  **Scenarios** (`CN1…`), one line per item with the id, the text and the status.
- **Status by our code and our tests** (code review and QA do not count):
  - **Missing:** the demand has not passed implementation, or the item is in no delivery of the plan;
  - **Implemented** (yellow): past implementation and the item is in a delivery (`Covers:` in the plan);
  - **Covered** (green): a script step that proves the item (its `Criterion` column) has ✅.
- Data: the plan numbers the items with the card's text and says in each delivery what it covers (`Covers: CA1, RN2`);
  the qa script says in each step the criterion it proves. Without a plan, the criteria come from the card summary, all
  "Missing".

### Card × code and Estimate (survey)

- **Card × code:** what the card asks; the points validated in the code, each with its situation (must change, is the
  pain, no change, nothing to reuse), "today in the code" and "for the demand"; and **Where the change touches**.
- **Estimate:** the numbers (story points as the card is, split story points, dev and QA days, complexity, confidence),
  effort per block as min–max bars, the recommended split into items, and **Risks**. Commenting on the card is asked in
  the chat.
- Data: `survey-<id>.md` in the fixed format of the reference *survey*.

## Metrics

- **Summary:** delegations, review rounds, agent and orchestrator tokens ("not recorded" without
  `orchestrator-metrics.md`), time agents worked and the delegations' cost when `metrics.md` has it.
- **By agent:** token bars; the orchestrator is one more line, in orange, with its turns.
- **Orchestrator:** cache read, cache written, output, its share of the demand's total and one line per session and
  model, from `orchestrator-metrics.md`. The cost is the API-price equivalent: a gauge of the weight on the plan limit,
  not the bill.
- **Orchestrator by step:** the *By step* section of `orchestrator-metrics.md`, most expensive step first.
- **Tokens per day** (with two days or more) and **by model and effort**.
- **Call results and rework:** labels with counts and the returns.

## Tests and Review (Questions in a survey)

Read-only: the review findings, the manual test and the PR comments; in a survey, the questions. The number on the
strip button adds up what still waits for you in each tab: findings with no decision that the next round did not
report as fixed or closed, and the test steps (automatic and manual) not passed yet (no `Result` or `❌`), only
during the test steps (`TEST`, `TEST_ADJUST`, `MANUAL_TEST`): before them nothing runs, after them the test is closed.

### Review (development)

- **Round** buttons per kind: Plan r1, Code r1, Code r2… Opens on the round with a finding to decide; otherwise the last
  code round.
- **Situation** tabs: With you (to decide) · Kept · Discarded · All.
- **Filters** by severity, category (quality, bug, security) and status.
- **Each finding is a card:** severity, ID, `file:line` and situation; what was pointed out; the code **before and
  after** when the finding proposes a change; **AiDW's recommendation**; for questions, the finding's own options; and,
  once decided, the decision recorded in the triage.
- Data: findings in `review-*-rN.md` (category in the title, `Before:` and `After:`, `**Recommendation:**`); the
  decision from `triage-*-rN.md`, which the orchestrator writes from what you said in the chat.

### Tests (development)

- Progress at the top (passed, failed, remaining), active steps only.
- A **Next** card with the current step: section, what to do and the expected result. The result and evidence go in the
  chat, with the orchestrator, which marks the script.
- The list by the script's sections, with the evidence of each step done; the setup is collapsed; removed steps hidden.

### Comments (PR review)

- **The triage comments** (`C1`, `C2`…; reference *pr-triage*): each one joins the findings that say the same thing,
  grouped **by PR**. Filters: To decide · Published · All.
- **Each comment:** severity, id, `file:line`, situation, title, the **text that goes to the PR** and the
  recommendation. Published and rejected ones are collapsed.
- What to publish, the text adjustments and whether AiDW approves each PR (manual, the default; yes; no) are decided in
  the chat, in the final review.

### Questions (survey)

- The open ones by topic, each with who it is for, what it changes in the estimate and why it matters; answered ones,
  one line each. The answer goes in the chat; the orchestrator updates the survey.

## What feeds the panel

| Who | Writes |
|---|---|
| `aidw.py demand set` | `--summary`, `--note`, `--pr <repo>=<n>`, `--extra-step` and the steps `CODE_REVIEW` and `QA_TEST` |
| Orchestrator | the summary when it understands the card; the outside steps when you tell it; your finding decisions in `triage-*-rN.md` |
| Planner | the card's criteria and rules numbered `CA1`, `RN1`, and each delivery's `Covers:` |
| Reviewer | the category in the title, `Before:` and `After:` and the `Recommendation:` of each finding |
| qa | the `Criterion` and `How` columns and each step's `Result` in the script |
| Explorer (survey) | the survey format |
