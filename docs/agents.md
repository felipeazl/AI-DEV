# Agents

An agent is a **role** with a definition (`agents/<role>/AGENT.md`), a model, an effort, tools and skills. The
orchestrator is the main chat; the others are the provider's **native subagents** (the `Agent` tool on Claude,
`spawn_agent` on Codex), each one in a fresh context on every delegation.

There are seven: orchestrator, explorer, planner, coder, reviewer, qa and documenter.

## Role and name

The **role** is fixed and is what AiDW uses internally (`coder`, `reviewer`…). The **name** is what you see and can be
changed in `aidw.config.toml` (by default it equals the role). In the Claude plugin the agents are called
`aidw:<name>`; on Codex, `aidw-<name>`.

| Role | Tools | Writes code? |
|---|---|---|
| `orchestrator` | the chat's | no (only when you ask, or when maintaining AiDW itself) |
| `explorer` | read, shell (SELECT through the context's validator), writes its report | no |
| `planner` | read, shell, writes the plan | no |
| `coder` | read, edit, shell | **yes**, only in the worktree |
| `reviewer` | read, shell, writes the review | no |
| `qa` | read, shell, browser (Claude in Chrome, Playwright, Chrome DevTools), writes the script and report | no (asks the coder for adjustments) |
| `documenter` | read, edit, shell, board | only text (Tasks, PR) |

Each role also gets the MCP servers `config/mcp.toml` allows it, minus the tools the context blocks for it
(`disallowed_tools`).

## What each one does

**Orchestrator** — drives the demand end to end: understands the card, orders the exploration and the plan, **reads the
plan** and brings it to your approval, starts the code, the Tasks and the test script in parallel, brings you the
review findings, runs the manual test steps with you and, with your OK, commits, pushes and opens the PR.

**Explorer** — the cheap reader. Gets numbered questions ("where is the validation?", "what is the contract of endpoint
X?") and answers with `file:line` or the query that proves it: ids, enums, real data through the context's SELECT
validator, read-only API calls. Does not design the solution or change anything. Its report
`exploration-<topic>.md` is reused by the plan. In **survey mode** it validates each point of the card and maps the flow
end to end.

**Planner** — writes `plan-<id>.md` (skill `to-spec`, preloaded): a **spec-driven, short, self-contained** plan —
verified premises, current and desired behavior, the card's acceptance criteria and business rules (`CA1`, `RN1`), and
the **deliveries** `E1`, `E2`… Each delivery is what one coder finishes in one pass: the files and what changes in each,
the criteria it covers, the code tests it needs, the repository docs it makes stale, and the build. In **fix mode** it
applies the adjustments you asked for. If it needs code it does not know, it returns `plan_needs_exploration`.

**Coder** — implements **one delivery at a time** in the worktree, follows the project's conventions, runs only the
plan's build and test commands, reviews its own diff and saves the patch. On an environment block it reports the exact
command and error and stops. It never commits: the work stays in the worktree until the PR step. Code tests only where
end-to-end testing cannot see (a calculation, a mapping, a state transition…). **Test adjustment** (asked by qa): a
temporary change marked `AIDW-TEST`, in its own patch; the review and the commit never see it.

**Reviewer** — reviews each delivery's **diff** against the plan in one pass (skill `code-review`, preloaded):
quality (the team's guide and the repository's conventions), **bugs** (each with a failure scenario) and **security**
(each with an attack path). Each finding has a stable ID, severity, category, the minimal fix, the code before and
after, and a **recommendation** (keep or discard, and why). In **PR mode** (someone else's PR) each finding worth telling
the author comes with a draft comment; it never comments, approves or completes a PR.

**QA** — two moments:
1. **Script and data** (`plan` mode, in parallel with the coder): `test-script-<id>.md` with each `CA`/`RN`, steps,
   expected result, evidence and how to prove it (`auto-api`, `auto-browser`, `auto-suite` or `manual`), and the test
   data, listing under *Approvals* what must be created or changed.
2. **Test** (`test` mode, after your code review): checks the script against the final diff, runs the approved writes
   and the automatic steps and marks ✅/❌ with evidence. Manual steps are left for you and the orchestrator.

**Documenter** — after the plan approval, attaches the plan to the card and creates one Task per delivery; after the
tests, writes `pr-<id>.md` (commit message, title, description, work items, pending items for QA). The orchestrator
commits, pushes and opens the PR with your OK.

## Models and effort

There are no demand levels. Each agent has a **default** model and effort, and only the **exceptions** listed for it,
each with the reason that allows it:

| Agent | Default | Exceptions (only for the reason) |
|---|---|---|
| orchestrator | the chat's (see below) | — |
| explorer | Haiku | Sonnet medium — redo once when the result made no sense; Sonnet high — survey |
| planner | Sonnet high | medium — plan adjustment you asked for at approval |
| coder | Sonnet high | medium — small fix (kept finding, failed test, your adjustment) or temporary test adjustment |
| reviewer | Sonnet high | medium — re-review of only the fixes; low — re-review of a trivial fix |
| qa | Sonnet medium | high — redo once when the result made no sense |
| documenter | Haiku | — |

**The orchestrator runs with the model and effort of the chat it is opened in — the config value is only the
recommendation shown in the Runtime section.** (Default recommendation: Opus, medium.)

### Where the defaults live

| What | Where |
|---|---|
| Each role's model **tier** (`top`/`mid`/`fast`) and default effort | `DEFAULT_AGENTS` in `aidw.py` — orchestrator `top`/medium (only the recommendation), planner, coder and reviewer `mid`/high, qa `mid`/medium, explorer `fast`/low, documenter `fast`/medium |
| Which model is each tier, and which efforts it accepts | `config/models.toml` — Claude: `top` = Opus, `mid` = Sonnet, `fast` = Haiku (Haiku takes no effort, so the explorer and documenter efforts are ignored on Claude) |
| The exceptions | `[[effort.variants.<role>]]` in `orchestrator/config/routing.toml` (`effort`, optional `model`, and `when`, the reason) |
| Your overrides | `[agents.<role>]` in `aidw.config.toml` |
| A team's overrides of the exceptions | `contexts/<name>/routing.toml` (merged on top of the core file) |

`python aidw.py show` prints the resolved name, model and effort of every agent.

### Change model and effort

**For good** — in `aidw.config.toml`, then `python aidw.py install` (and `apply` for project mode) and a new chat:

```toml
[agents.coder]
model = "opus"            # a key of config/models.toml; without it, the role's tier applies
effort = "medium"         # one of the model's efforts: low, medium, high, xhigh, max

[agents.reviewer]
effort = "medium"
```

Or rerun the wizard (`python aidw.py configure`, step 2). A model of the other provider becomes its equivalent by tier.

**The orchestrator** — pick the model and effort in the chat itself (Claude Code's model picker or `/model`). The
`[agents.orchestrator] effort` value only changes the recommendation printed in its Runtime section.

**For one task** — tell the orchestrator ("use Opus for the coder on this ticket"). It passes `model` in that
delegation only because you asked; the `aidw-mods` lock refuses a `model` nobody asked for.

**A new exception** — add an entry to `routing.toml` (core, by PR) or to the context's `routing.toml`:

```toml
[[effort.variants.coder]]
effort = "medium"
when = "small fix (kept finding, failed test, user adjustment) or temporary test adjustment"

[[effort.variants.explorer]]
model = "sonnet"          # a Claude key; on Codex the equivalent by tier applies
effort = "high"
when = "survey: the end-to-end flow map is the deliverable"
```

Every exception needs a `when`. Run the tests (`python -m unittest discover -s tests`) when changing the core file.

### Variants

On Claude the model and effort are pinned in the subagent file, so each exception becomes a **variant** subagent:

```text
aidw:coder                    ← the default (Sonnet high)
aidw:coder-medium             ← same model, effort medium
aidw:explorer-sonnet-high     ← another model: <name>-<alias>-<effort>
```

The orchestrator's *Agents and effort* table lists the `subagent_type` of each one, and the `aidw-mods` lock refuses a
variant outside it. On Codex each variant is a role too (`aidw-coder-medium`): see [claude-and-codex.md](claude-and-codex.md#agents-and-effort).

### Codex equivalence

The same table serves both providers through each model's **tier** (`config/models.toml`):

| Claude | Tier | Codex |
|---|---|---|
| Opus | `top` | the top model enabled for the account |
| Sonnet | `mid` | the middle one |
| Haiku | `fast` | the light one |

On Claude, `model_id` is the **alias** (`opus`, `sonnet`, `haiku`), which Claude Code resolves to the newest model of the
family it knows. On Codex it is the exact ID, and `metrics.md` records the model the session really used. Codex's
`fast` model accepts effort, so there the explorer runs at `low` and the documenter at `medium`.

## Output contract

Every agent ends with **one** JSON block:

```json
{
  "state": "<one of the agent's states>",
  "files_changed": [],
  "commands": ["<exact commands it ran>"],
  "errors": [],
  "questions": [],
  "approvals": [],
  "notes": []
}
```

`state` decides the next step ([workflow.md](workflow.md#how-the-next-step-is-chosen)). `questions`: what blocks, with
options. `approvals`: locked actions proposed (exact command or text) for the orchestrator to ask your OK.

| Agent | States |
|---|---|
| explorer | `exploration_complete`, `environment_blocked` |
| planner | `plan_ready`, `plan_has_open_questions`, `plan_needs_exploration` |
| coder | `implementation_complete`, `implementation_failed`, `environment_blocked`, `implementation_has_open_questions`, `policy_requires_approval` |
| reviewer | `review_findings`, `review_approved`, `pr_review_done` (PR mode) |
| qa | `test_plan_ready`, `test_plan_has_open_questions` (plan); `tests_passed`, `tests_failed`, `manual_test_required`, `test_adjustment_needed`, `environment_blocked`, `policy_requires_approval` (test) |
| documenter | `task_complete`, `pr_ready`, `environment_blocked`, `policy_requires_approval` |

## What an agent receives

`apply`/`install` assemble each agent's definition in layers:

1. `agents/<role>/AGENT.md` from the core: ROLE, INPUT, PROCESS, OUTPUT and RULES.
2. The core policies (`orchestrator/policies/`) and the context's (`contexts/<name>/policies/`).
3. What the context includes for the role (`[agents.<role>] include`).
4. The role's reference list (`reference`), with when to read each; the content is **not** in the prompt.
5. The context's *Systems*: repositories, stack, build and test commands.
6. The role's skills (core and context); the `preload` ones come already loaded.
7. The language rule: reports are written in the context's language.

At delegation time the orchestrator passes only paths: the plan and the delivery, the previous report, a short task
file when there is one. The less an agent has to search, the less it spends.

## Turn agents on and off

```toml
[agents.qa]
enabled = false           # the orchestrator never delegates to it and does its step cheaply, or skips it
```

With the explorer or planner off, the orchestrator does that step itself. The orchestrator cannot be turned off. An old
config with `[agents.api-db]`, `[agents.bug-hunter]` or `[agents.security]` (removed roles) is accepted with a warning.
Names that collide with the CLI's own agents (`plan`, `explore`, `default`, `general-purpose`…) are refused.

## Create an agent

1. `agents/<role>/AGENT.md` with frontmatter `tools` and `description`, and the sections ROLE, INPUT, PROCESS, OUTPUT
   (with its `state` values) and RULES.
2. The new states in `[rules]` of `orchestrator/config/routing.toml`.
3. The role in `DEFAULT_AGENTS`, `DEFAULT_NAMES` and `RUN_PROFILE` in `aidw.py` (tier and effort, name, headless profile).
4. Its exceptions, if any, in `[[effort.variants.<role>]]`.
5. `[agents.<role>]` in `aidw.config.example.toml` and, if needed, the MCPs in `config/mcp.toml`.
6. `python -m unittest discover -s tests` and `python aidw.py install`.
