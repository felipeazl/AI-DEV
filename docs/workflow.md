# The workflow

What happens between `/aidw:go 1234` and the open PR: the steps, who does each one, where you decide, how the
orchestrator picks the next step, and what is recorded.

## The idea

A single chat that does everything (reads code, plans, codes, reviews itself) accumulates context: by the end of the
demand it carries hundreds of lines read at the start, costs more on every message and makes more mistakes. AiDW
splits the roles without multiplying the steps:

- The **orchestrator** is the main chat. It reads, organizes and coordinates, but does not read code to plan nor
  implement. Its context is the largest cost of a demand, so it reads a file only when it must decide something from
  it.
- Each step runs in a **fresh agent** (a native subagent) that gets **files by path** — the plan is the coder's
  task —, writes its result in the demand folder and returns a JSON with a `state`.
- **Each agent runs once per step.** A new round needs a named reason: your adjustment, a kept finding, a failed test
  or a result that made no sense.
- **You decide** the plan, the review findings, your code review, the manual test steps and the PR; the rest runs on
  its own.

## Steps (`development`)

```text
Understand → Explore → Plan → Your approval
        → Implement (in parallel: README and Tasks on the board, test script and data)
        → Review → you decide the findings → Fix ⇄ Re-review
        → Your code review → Tests (qa runs API and browser; you run the manual steps with the orchestrator)
        → PR (commit, push and PR with one OK) → Code review and QA (outside AiDW) → /aidw:done
```

| Step | Who | Output | You |
|---|---|---|---|
| **Understand** | orchestrator | `summary-<id>.md`: card fields, acceptance criteria and business rules (the card's text), decisions from the comments (author and date), existing work, the knowledge notes that matter | only if work already exists (Tasks, PR, branch): continuation, fix or redo? |
| **Explore** | explorer | `exploration-<topic>.md`: numbered questions answered with `file:line`, contracts between systems, real ids and data | — |
| **Plan** | planner | `plan-<id>.md`: spec-driven, short, self-contained — verified premises, current and desired behavior, the card's `CA`/`RN`, deliveries `E1…` with files and build | — |
| **Your approval** | you + orchestrator | the orchestrator reads the plan and points out gaps; you approve or ask for changes (planner in fix mode) | **yes: nothing goes to code without your OK** |
| **Implement** | coder (one per delivery), documenter, qa | the code in the worktree; one Task per delivery on the board; `test-script-<id>.md` with the test data | the test data writes, in one batch |
| **Review** | reviewer | `review-<id>-r<N>.md`: quality, bugs and security in one pass, each finding with a keep/discard recommendation | **yes: you decide each finding, every round** |
| **Fix** | coder → reviewer | only the kept findings; the re-review looks only at the fixes | — |
| **Your code review** | you | a change you ask for becomes a fix and a review of only that fix | **yes** |
| **Tests** | qa, then you + orchestrator | qa checks the script against the final diff, runs the automatic steps and marks the results; you run the manual steps, one at a time | **yes, the manual steps** |
| **PR** | documenter, then orchestrator | `pr-<id>.md` (commit message, title, description, pending items for QA); with your OK: commit, push, PR | **yes: one OK** |

Bugs, improvements, technical debt and urgent fixes all use this workflow. For a bug, the root cause is the
explorer's first question (reproduce it or show the cause); for debt with no behavior change, the plan says so and the
test script covers the regression. A context may add outside steps (e.g. a UX validation before the PR,
[contexts.md](contexts.md#outside-steps)).

## How the next step is chosen

Each agent ends with `"state": "<key>"`, and `[rules]` in `orchestrator/config/routing.toml` maps it to the next
action (`plan_ready` → `PLAN_APPROVAL`, `review_findings` → `TRIAGE`, `tests_passed` → `PR`…). The orchestrator applies
the rule; agents never choose the next step. A missing or unknown `state` is a failed result: the orchestrator asks
once more, only for the JSON. A context may override rules in `contexts/<name>/routing.toml`.

There is no round limit: a loop (explore ⇄ plan, review ⇄ fix) runs until its step is done, and each new round needs a
named reason.

## Agents and effort

No demand levels. Every agent runs on its default; the orchestrator uses an **exception** only for the reason written
in its *Agents and effort* table. Defaults, exceptions and how to change them: [agents.md](agents.md#models-and-effort).

## Review and triage

The reviewer reviews each delivery against the plan in one pass: the team's standards, **bugs** (each with a failure
scenario traced in the code) and **security** (each with an attack path). Each finding has an ID, severity, category,
the minimal fix in scope, the code before and after, and a recommendation (keep or discard, and why). Rule or
architecture doubts come as questions, not findings.

The findings go to **you** every round, and you decide in the chat. Before recommending to discard a critical or
important finding, the orchestrator verifies the premise (skill `verify-premise`). Decisions are recorded in
`triage-<id>-r<N>.md`; kept findings go to the coder, and a fresh reviewer checks only the fixes. With nothing left to
decide, the demand goes to your code review.

## Tests

- **Script and data, in parallel with the code:** right after you approve the plan, qa writes `test-script-<id>.md` —
  each `CA`/`RN` with steps, expected result, evidence and how to prove it (`auto-api`, `auto-browser`, `auto-suite`
  or `manual`) — and gathers the data: it finds existing records and lists under *Approvals* what must be created or
  changed. You approve the write blocks in one batch while the code is written.
- **After your review:** qa checks the script against the final diff, runs the approved writes, the automatic steps
  (API and browser — Claude in Chrome, your logged-in Chrome, or Playwright) and the area's regression, and writes
  ✅/❌ and the evidence in the script.
- **Manual steps** (desktop apps, or what qa could not do in the browser): the orchestrator shows one step at a time,
  you run it and send the evidence in the chat, and it marks the result.
- **Test adjustments:** a code change made only to test (bypass, flag, mock) is done by the coder, marked
  `AIDW-TEST`, in a separate patch (`test-env-<id>.patch`); it is reverted before the commit, and a hook refuses a
  commit that still has the mark.
- A failure → fix, review of only the fix, retest of only the affected steps.

## PR

The documenter writes `pr-<id>.md`: the commit message, the PR title and description in plain language, the linked
work items and the pending items for QA. The orchestrator checks that the test adjustments are gone, shows you
everything with the exact commands and, with **one OK**, commits, pushes and opens the PR (through the context's skill,
when it has one). From then on the demand is with the team (`CODE_REVIEW`) and then QA (`QA_TEST`); you tell the
orchestrator when it moves.

**After delivery** (a bug QA returned, a change asked in the PR, a small adjustment): the short path, no new plan — the
item's summary, the explorer only if the cause is unclear, the coder, a review of only the fix (findings go to you), a
retest of the affected steps and a line in *Addenda* at the end of the plan. `demand set <id> --loop bug-<n>` numbers
the review rounds of that loop from 1.

## Reviewing someone else's PR (`pr-review`)

The orchestrator reviews a PR someone else opened, with no plan or fix: the author fixes, you choose what is published.

```text
/aidw:go us-1234 pr 5678 5679      ← the card and the PRs (they may be in different repositories)
```

1. **Understand:** `summary-<id>.md` with the card and, per PR, author, description, target, linked items and what was
   already commented.
2. **PR worktree:** `aidw.py worktree create --repo <repo> --demand <id> --pr <n>` fetches the PR merged into its
   target, creates a read-only worktree and writes `diff-pr<n>-<repo>.patch`. The orchestrator runs the build there.
3. **Review:** a reviewer in PR mode (quality, bugs and security), with all the demand's PRs; each finding comes with a
   draft comment.
4. **Final review:** per PR, the proposed comments. You choose what to publish, adjust the text and answer "Approve the
   PR?": **manual** (the default: you approve in the tool), **yes** (AiDW approves) or **no**. Publishing and approving
   are locked actions. The card's state never changes.
5. **The author updated the PR:** the same `worktree create --pr <n>` writes the diff of only what changed, and a fresh
   reviewer checks it with the same IDs.

## Survey (`survey`)

Understand and estimate a card **before** implementing. Read-only: no worktree, plan or code.

```text
/aidw:survey 1234                  ← the card (id or link)
/aidw:survey "<demand text>"       ← no card: the demand is survey-<slug>
```

The orchestrator numbers what the card asks in `points-<id>.md`; the explorer, on the survey exception (Sonnet high),
confirms each point in the code and maps the flow end to end; the orchestrator estimates with the scale in the
reference *survey* and writes `survey-<id>.md` with hours, story points, complexity, confidence, risks and open
questions. A comment on the card only with your OK. If the card is implemented later (`/aidw:go <id>`), the flow
starts at `EXPLORE`, reusing the survey.

`/aidw:survey` loads a lean orchestrator (`orchestrator/SURVEY.md`): only the explorer, no development workflows, with
the procedure and the scale inline, so every orchestrator turn rereads a smaller context.

## When you are called

1. **Fixed points:** plan approval, the findings of each review round, your code review, the manual test steps and the
   PR OK.
2. **Locked actions:** write SQL, state-changing API calls, e-mail/OTP — the agent proposes, the orchestrator batches
   them and asks for your OK.
3. **A real doubt or more than one valid path:** one question, with options, a recommendation and why.
4. **Something outside the plan:** a bigger scope, a blocked environment.

## What is recorded

Everything about a demand lives in `<state dir>/<id>/`:

| File | Content |
|---|---|
| `demand.json` | step, status (`active`/`paused`/`done`), summary, repositories, Tasks, PRs, loop, step history |
| `summary-<id>.md` | the card, summarized, so no agent rereads the card |
| `exploration-<topic>.md` | the explorer's answers, reused by the plan |
| `plan-<id>.md` (and `plan-<id>-v<N>.md`) | the versioned plan: the source of truth and the coder's task |
| `task-<agent>-<topic>.md` | only when something is in no other file: the explorer's questions, plan adjustments, kept findings |
| `diff-<id>-<E>-r<N>.patch` · `review-<id>-r<N>.md` · `triage-<id>-r<N>.md` | each review round, with your decisions |
| `test-script-<id>.md` · `qa-<id>-r<N>.md` | the script with the data and each step's result, and qa's report |
| `test-env-<id>.patch` · `test-env-<id>.md` | the temporary test adjustments |
| `pr-<id>.md` | commit, PR and pending items for QA |
| `learnings-<id>.md` | what was born in the chat and matters for the next demands |
| `metrics.md` · `orchestrator-metrics.md` | one line per delegation (agent, model, effort, tokens, tools, duration) and the main chat's usage |

File names are always English; their content follows the context's language
([configuration.md](configuration.md#language)). Demands created before the English rename keep their old file names
(`resumo-`, `plano-`, `metricas.md`…) and are still read.

### Metrics

After each subagent, a line goes into `metrics.md` through `aidw.py record`, with the real numbers. On Claude Code the
`aidw-mods` plugin runs `record` by itself and adds the main chat's usage to `orchestrator-metrics.md`
([mods.md](mods.md)); without it, and on Codex, the orchestrator runs `record` itself. The numbers are **never
estimated**.

### Resume

`/aidw:exit` records the step and the next action (`paused`). Later, `/aidw:go` with no argument in the worktree or the
repository finds the demand and continues from the recorded step; `python aidw.py open --demand <id>` does the same
from the terminal. For long waits (the team's review, QA), close the chat and resume in a new one: the demand folder has
everything.

### Close

`/aidw:done` closes the task: it starts from `aidw.py kb collect <id>`, writes into the context only what was
**verified** and matters for the next demands, validates, reinstalls and commits and pushes **only the context
repository**.

## The knowledge base in the flow

When the context has a knowledge base ([contexts.md](contexts.md#knowledge-base)):

- **At the start**, the orchestrator runs `kb search` with the card's terms and lists in `summary-<id>.md` the
  **paths** of the notes that matter; every task carries those paths, and the agents read the notes before the code.
- **During**, each agent writes what it learned in its own report (a *Knowledge base* section). `learnings-<id>.md`
  holds only what was born in the chat: your decisions, the business's, environment blocks the orchestrator solved.
- **At the end**, `/aidw:done` runs `kb collect <id>` (gathers all of that into `collect-<id>.md`), updates the base and
  commits the context.
