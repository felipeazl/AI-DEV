# Contexts

The AiDW core knows **how** to work: the flow, the roles, the protections. It does not know **where**: which systems
you have, how each one builds, what your team considers good code, what needs approval. That is the **context**: a
company's or team's rule package, in a **private Git repository** under `contexts/<name>/`.

A context renames nothing. Commands, agents and the flow stay the same; what changes is the quality of the delivery,
because every agent already gets what the team knows.

## Why it pays off

- **Less exploration:** the agent already knows where each system lives, its stack and a ready build command.
- **Less rework:** the team's conventions reach the coder and the reviewer; the reviewer enforces the team's guide, not
  the model's opinion.
- **More safety:** the team's permissions and validators apply to every agent.
- **It learns:** `/aidw:done` writes into the context what each demand discovered.

## Structure

```text
contexts/<name>/
├── context.toml      systems, permissions, worktree, MCPs, language and what each agent gets
├── agents/           rules per role (orchestrator.md, coder.md, reviewer.md…)
├── policies/         the team's policies (approvals, environments, secrets, scope)
├── shared/           guides used by several agents (e.g. the team's code guide)
├── reference/        references read only when their topic comes up
├── skills/           the team's own skills
├── tools/            validators and wrappers (read-only SQL, filtered build)
├── workflows/        optional: workflows that replace or add to the core ones
├── routing.toml      optional: overrides of the core rules and effort exceptions
├── conhecimento/     knowledge base: notes linked by [[links]]
├── .obsidian/        the Obsidian vault is the context folder (graph and excluded folders versioned)
└── demandas/         the demands' state (outside the context's Git)
```

`context create` makes this layout (the knowledge base folder is `conhecimento/` and the state folder `demandas/` by
default; both are configurable). The context repository is **separate** from AiDW: AiDW's `.gitignore` ignores
`contexts/`, and `doctor` and `context check` fail if that stops being true. The core can be public or shared between
companies while each one's rules stay private.

## `context.toml`

### Identity, language and folders

```toml
name = "my-team"
description = "Company X — Payments team"
language = "en"                              # content of the context and of the demand artifacts (BCP-47);
                                             # without it, the AiDW [ui] language applies

state_dir = "contexts/my-team/demandas"      # where the demand folders live (relative to the AiDW root)
additional_dirs = ["C:/Repos", "C:/Legacy"]  # allowed for the chat and the agents with this context

required_env = ["BOARD_TOKEN"]               # doctor checks they exist (never the value)
required_mcp = ["board"]                     # doctor checks they are registered

[env]
MCP_TIMEOUT = "60000"                        # variables passed to the sessions
```

File names are always English; `language` changes only what is written inside them
([configuration.md](configuration.md#language)).

### The team's MCPs

```toml
[mcp.board]
add = "claude mcp add --scope user board -- npx -y @company/board-mcp"
add_codex = "codex mcp add board -- npx -y @company/board-mcp"
```

`doctor` shows the command when the server is not registered, and `setup` offers to run it.

### Worktree

```toml
[worktree]
branch_prefix = "feature/"                   # branch <prefix><number>-<slug>; default "aidw/"
link = ["packages", "node_modules"]          # folders git does not track, linked by junction (this is the default)
```

### Environments

```toml
[environments]
order = ["DEV", "QA", "HML", "PROD"]   # from the furthest to the closest to production
test = "DEV"                           # where the qa tests by default
test_fallback = "QA"                   # only for a step the default cannot prove; the user approves, for that demand only
explore = ["DEV", "QA"]                # the explorer queries every one; when they disagree: more data, then closest to production
```

Every agent gets these lines in its *Runtime*. Which environments a write may touch is still the policies' call.

### Permissions

```toml
[permissions]
allow = [                                    # run without asking
    "Bash(git *)",
    'PowerShell({{context}}\tools\sql-read.ps1 *)',
    "Bash(dotnet build *)",
]
git_ask = ["commit", "push", "merge", "rebase", "reset", "checkout", "switch", "branch -D"]
ask = ["Bash(sqlcmd *)"]                     # always ask for OK
deny = []                                    # always blocked
```

- Precedence: **deny > ask > allow**.
- `git_ask` generates the rules for `git <sub>` and `git -C <dir> <sub>`, in Bash and PowerShell.
- The syntax is Claude Code's and the rules apply on Claude Code. On Codex, only project mode (`apply` with
  `provider = "codex"`) turns them into `.codex/rules/aidw.rules`; the global Codex install carries no rules.

### Systems

```toml
[systems.payments-api]
name = "Payments API"
repos = ["C:/Repos/Payments"]
stack = ".NET 8, Clean Architecture"
depends_on = ["customers-api"]               # the plan inspects these contracts before planning
build = "dotnet build '<repo>' -v q -clp:ErrorsOnly"
test = "dotnet test '<repo>' -v q --nologo"
worktree_link = ["../Shared"]                # neighbor folders the code reaches by relative path
notes = [
    "Verified facts every agent needs whenever it touches this system: build order, environment blocks.",
]
```

- `<repo>` is replaced by the demand's worktree.
- **Ready build and test commands with filtered output** are among the biggest savings: the agent does not hunt for a
  build tool or read a thousand lines of log.
- `notes` are for what **every** agent needs whenever it touches the system. How the system works, contracts and code
  traps go to the knowledge base, which the agent reads when the system is in the task.

### Workflows by card type

```toml
[workflows]
by_type = { "User Story" = "development", "Bug" = "development" }
notes = ["One line the orchestrator reads with the workflows table."]
```

A file in `contexts/<name>/workflows/<name>.yaml` replaces the core workflow with the same name, or adds a new one.

### Outside steps

The core has two steps where the demand is with other people: `CODE_REVIEW` (the team reviews the PR) and `QA_TEST`
(QA tests). A context may add others before them or before the PR, e.g. a UX validation:

```toml
[[workflows.external_steps]]
step = "UX_VALIDATION"            # UPPERCASE_WITH_UNDERSCORES; becomes a `demand set --step` value
name = "UX validation"            # the name on the panel's progress bar
before = "PR"                     # PR, CODE_REVIEW or QA_TEST
who = "UX"                        # shown as "with UX" on the status label
when = "when a demand goes through it and what happens before and after"   # goes to the orchestrator
```

- `apply` validates the declaration and puts the step in the orchestrator's *Workflows* section and in `runtime.json`.
- As with `CODE_REVIEW` and `QA_TEST`, only you move a demand into or out of it; a change request follows the short path.
- The progress bar shows the step only for a demand that goes through it: marked with
  `demand set <id> --extra-step UX_VALIDATION` (the orchestrator does it when the plan says so) or already in it.

### Panels

```toml
[mods]
panel = false                     # turns off the aidw-mods panels and the strip buttons (default: on)
```

The panels are on in every context; each tab only appears when its data exists. With `panel = false`, the context keeps
the strip and the other mods ([mods.md](mods.md#when-they-are-on)). There is no vote scale to declare: in a PR review
the only question is "Approve the PR?" (manual, yes, no); how to approve in your tool is in the context's PR review
reference. A leftover `[[mods.votes]]` only produces a warning.

### What each agent gets

```toml
[agents.coder]
include = ["shared/team-guide.md", "agents/coder.md"]      # ALWAYS in the agent's prompt
skills = ["attach-file"]                                   # context skills available to it
preload = []                                               # context skills preloaded
disallowed_tools = ["mcp__board__comment"]                 # tools blocked for it
systems = "full"                                           # how much of [systems] it gets: full | short | none
reference = [                                              # read ONLY when the topic comes up
    { path = "reference/templates.md", when = "creating a Repository/Service/Controller from scratch" },
    { path = "reference/database.md", when = "creating or changing a table or SQL script" },
]

[agents.orchestrator]
include = ["agents/orchestrator.md"]                       # goes into the go skill and CLAUDE.md/AGENTS.md
reference = [
    { path = "reference/ux-validation.md", when = "the plan says `UX validation: yes`" },
]
```

#### `include` × `reference`

The most important cost decision of a context:

| | `include` | `reference` |
|---|---|---|
| In the prompt | **always**, whole | only one line with the path and `when` |
| Cost | in every delegation of that role | only when the topic comes up |
| Use for | short rules valid for every task | long guides, templates, API docs |

Write `when` as a concrete trigger ("creating or changing an endpoint"), not a subject ("API").

### Variables

- In `context.toml` strings: `{{context}}` is the context folder and `{{root}}` the AiDW root.
- In `.md` files: `{{agent:<role>}}` becomes the agent's configured name (e.g. `{{agent:reviewer}}` → `reviewer`), so
  the text stays right when someone renames an agent.

## Policies

A `.md` in `policies/` applies to the orchestrator and every agent. With `roles` in the frontmatter, it goes only to
those roles (`orchestrator`, `explorer`, `planner`, `coder`, `reviewer`, `qa`, `documenter`): every agent pays for each
policy it gets on every run, so give a policy only to whoever acts on it. With `orchestrator_when`, the orchestrator
reads that policy only at that moment (the agents in `roles` still get it whole):

```markdown
---
roles: documenter, orchestrator
orchestrator_when: the PR step (commit, push and the pending-items comment)
---

# Policy — Cards on the board
...
```

The context's policies **add** to the core ones (`orchestrator/policies/`: git, database, production, secrets,
permissions; git goes to the coder and the orchestrator, database and production to the explorer, coder, qa and the
orchestrator).

`systems` (in `[agents.<role>]`): `full` is the whole [systems] table with build, test and notes; `short` is one line
per system (repos, depends on, knowledge note); `none` leaves it out. The default is `full` for the explorer, planner
and coder and `short` for the others. A policy says what to do; the CLI permission enforces it. For a rule that must not fail, use both.

## Create a context

```text
/aidw:context create
```

1. Asks for the name and the repositories.
2. Analyzes each repository in parallel: stack, real build and test commands, dependencies outside Git, conventions,
   git and PR, integrations, environments, database, risks — always with `file:line` evidence.
3. Asks **at least 10 questions**, with options and a recommendation taken from the analysis (what needs approval,
   which environments are allowed, where demands live, which MCPs are required…).
4. Generates the context, creates its own Git repository and runs `context check`.
5. Commit and push of the context repository ask for your OK.

From the command line, only the skeleton:
`python aidw.py context create <name> --description "..." [--language <tag>]`.

## Knowledge base

What the demands learned about the systems, in Markdown notes linked by `[[links]]`. The **context folder** opens as an
**Obsidian vault**, with the graph view: notes appear next to the policies, agents and guides, and can cite them by
`[[name]]`. Turn it on in `context.toml`:

```toml
[knowledge]
dir = "conhecimento"      # relative to the context folder
```

The rule that matters most: **each fact lives in one note**; whoever needs it links with `[[note-name]]`. Notes have a
frontmatter (`tipo`, `resumo`, `sistemas`, `fontes`, `atualizado` and, in technical notes, `palavras-chave` — the
identifiers and synonyms search weighs like the title) and live in their type's folder:

| Folder | `tipo` | One note per |
|---|---|---|
| `sistemas/` | `sistema` | system of `context.toml` — the file name is the key (`[systems.portal]` → `sistemas/portal.md`) |
| `componentes/` | `componente` | shared library or project |
| `integracoes/` | `integracao` | contract between two sides: endpoint, SOAP, enum, event, shared config, external service |
| `conceitos/` | `conceito` | domain term; `evitar:` lists terms not to use (becomes the index glossary) |
| `ambiente/` | `ambiente` | how to operate: hosts, authentication, database, recipes |
| `decisoes/` | `decisao` | a durable decision, with author and date |
| `demandas/` | `demanda` | a closed demand — development, PR review or survey |

The folder's `README.md` holds the team's conventions; `index.md` is generated (`kb index`).

**How AiDW uses it:**

- Each agent's *Systems* section points to the system's note (`Knowledge:`), and the Runtime teaches `kb show` and
  `kb search`. Agents read the note before the code; when the code disagrees, the code wins and the difference comes
  back in the report.
- The orchestrator queries the base at the start, passes the paths in the tasks and keeps in `learnings-<id>.md` what
  was verified during the demand ([workflow.md](workflow.md#the-knowledge-base-in-the-flow)).
- `/aidw:done` creates the demand's note and updates the notes it touched, without duplicating.
- `/aidw:knowledge <topic>` answers what the base knows, outside a demand.
- `kb check` (also inside `context check`) reports broken links, repeated names, missing frontmatter, unknown systems,
  systems without a note, orphan notes and text that looks like a secret or a personal document number; it warns on notes
  over 150 lines and notes unchecked for more than 6 months.

**The base describes, the rules decide.** A note records how the code is today, legacy deviations included: a fact,
not a rule. Which pattern new code follows is decided by the team's guide and the context's policies, never by a note
alone. Team conventions do not go in the base (they go in `shared/` or `policies/`).

Version the Obsidian configuration (`.obsidian/graph.json`, with the colors per type, and `app.json`, which excludes
the demand state from the graph), not each machine's layout.

### Upstream

When the context summarizes an outside repository (e.g. the team's code guide), record the commit it reflects:

```toml
[upstream.guideline]
repo = "C:/Repos/Guideline"
synced = "<hash>"                     # git -C <repo> log -1 --format=%H
covers = ["reference/guide/", "shared/team-guide.md"]
branch = "main"                       # optional: compared as origin/<branch>; default: the checkout's tracking branch
```

`context upstream` fetches each upstream and warns when the remote has commits after `synced` (the copies are behind:
recheck what `covers` lists and update `synced`) or when the local checkout is behind the remote (agents reading its
files read old rules: pull it). The orchestrator runs it at the start of every workflow; `doctor` and `context check`
run it too.

## Activate, validate, list

```text
/aidw:context use <name>                ← validates, writes [context] active, regenerates; open a new chat
python aidw.py context check <name>     ← full build with the context, own repository, exclusive state folder
python aidw.py context list             ← (or /aidw:context list)
```

Only one context is active at a time. Each context's state folder is exclusive: two contexts never share demands.

## Good practices

- **Facts, not opinions:** each rule with the file, commit or decision it came from. No invented examples.
- **Short in `include`, complete in `reference`.**
- **Ready commands:** exact build and test commands, with filtered output.
- **A risky rule is a permission, not text:** what must never happen goes in `deny`/`ask`.
- **Secrets are never written:** only the variable name. `doctor` checks presence, never the value.
- **Let the context learn:** run `/aidw:done` at the end of each task.
- **One fact, one place:** in the knowledge base, link with `[[link]]` instead of copying.
