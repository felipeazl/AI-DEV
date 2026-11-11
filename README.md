# AiDW

[Português (Brasil)](README.pt-BR.md)

**AiDW** (AI Development Workflow) is an **agentic development** plugin for **Claude Code**: a workflow, a team of
agents and a set of skills. You talk to **one chat**, the **orchestrator**, the way you would talk to a tech lead. It
understands the request, sends a cheap agent to read the code, orders a short self-contained plan, brings the plan to
you for approval, delegates the code, the review and the tests, and calls you at the points that are yours: the plan,
the review findings, your code review, the manual test steps and the OK for the PR.

```text
 You ─► /aidw:go 1234
           │
           ▼
     orchestrator ── understands ─► explorer reads the code ─► planner writes the plan ─► you approve
           │
           ▼
     coder implements (isolated worktree)  ‖  documenter creates the Tasks  ‖  qa writes the test script and data
           │
           ▼
     reviewer (quality, bugs, security) ─► you decide the findings ─► coder fixes ⇄ reviewer
           │
           ▼
     your code review ─► qa tests (API, browser) + you run the manual steps ─► PR with one OK ─► done
```

> **Built for Claude Code.** AiDW runs in full there, and every new feature starts there. **On Codex, AiDW is only
> agents and skills:** `install --provider codex` copies the `aidw-*` agents and skills and nothing else — no permission
> rules, hooks, guard, profile, per-agent MCP or mods. See [docs/claude-and-codex.md](docs/claude-and-codex.md).

## Why

| Without AiDW | With AiDW |
|---|---|
| One chat does everything: reads hundreds of lines, plans, codes and reviews itself. The context fills up and quality drops. | Each step runs in a **fresh agent** with only what it needs. The orchestrator's chat stays small for the whole demand. |
| The same expensive model reads files and decides architecture. | **Model and effort per role**: Haiku reads code and writes to the board, Sonnet plans, codes and reviews. Opus only when you ask. |
| You review what the model wrote, alone. | An independent **reviewer** covers quality, bugs and security in one pass, with IDs, severity and a keep/discard recommendation; **you decide** each finding. |
| Team rules repeated in every prompt. | A **context** keeps systems, build commands, conventions and policies; every agent gets them. |
| The model decides what is safe. | **The model is never the last barrier**: CLI permissions, hooks and validators block what is risky. |
| Close the chat, lose the thread. | Each demand has a folder, a state and metrics: you **resume** where you stopped and see what each step cost. |

## Contents

1. [Install](#1-install)
2. [Use](#2-use)
3. [What comes included](#3-what-comes-included)
4. [Configure](#4-configure)
5. [Security](#5-security)
6. [Documentation](#6-documentation)

## 1. Install

### Prerequisites

| Tool | For | Install (Windows) |
|---|---|---|
| **Python 3.11+** | `aidw.py` (standard library only, no `pip install`) | `winget install Python.Python.3.13` (`setup.ps1` offers it) |
| **Git** | repositories, worktrees and AiDW itself | `winget install Git.Git` |
| **Node.js LTS** | local MCP servers through `npx` | `winget install OpenJS.NodeJS.LTS` |
| **Claude Code** | runs the orchestrator and the agents | `irm https://claude.ai/install.ps1 \| iex` |
| **Codex CLI** (optional) | limited use: agents and skills | `npm i -g @openai/codex` |

No API key is needed: everything runs on the CLI login (a Claude subscription or a ChatGPT account).

### Steps

```powershell
git clone <AiDW url> C:\AiDW
cd C:\AiDW
git clone <your context url> contexts\<name>    # optional: your team's rules (docs/contexts.md)
.\setup.ps1                                     # Linux/macOS: ./setup.sh
python aidw.py install                          # Claude: AiDW is available in any folder
.\doctor.ps1                                    # checks everything; ends with READY or NOT READY
```

| Step | What it does |
|---|---|
| `setup` | Makes sure Python is there, runs the **wizard** (provider, delegation mode, each agent's model and effort, agents to disable, names, project folders, MCPs, language, context) and writes `aidw.config.toml`. Checks Git, Node, the CLIs and the login, creates missing folders, runs `apply`, offers to register the MCPs and ends with `doctor`. |
| `install` | Builds the **`aidw`** plugin (agents, skills, commands, hooks) and the **`aidw-mods`** plugin ([mods](docs/mods.md)) and installs both in Claude Code (CLI and desktop app). Adds AiDW's own rules to `~/.claude/settings.json`, only its items. If Codex was installed before, updates it too. |
| `install --provider codex` | Optional. **Only** the `aidw-*` agents (`~/.codex/agents`) and skills (`~/.agents/skills`). |
| `doctor` | Checks core, CLIs, login, context, environment variables, MCPs, folders and install. Changes nothing. |

After `install`, **open a new chat**. `/aidw:go` shows up in any folder.

- **Update:** `git pull` in AiDW (and in the context), then `python aidw.py install` and a new chat.
- **Another machine:** clone AiDW and the context, run `setup` and `install`. `aidw.config.toml` and the generated
  files are not versioned; `aidw.config.example.toml` is the template.
- **Uninstall:** `python aidw.py uninstall` removes only what `install` added.

## 2. Use

Open a Claude Code chat, preferably in the repository folder, and call:

```text
/aidw:go 1234                 ← card id, link or a description of what to do
/aidw:go 1234 pr 5678         ← review someone else's PR (no implementation)
/aidw:survey 1234             ← survey: validate the card in the code and estimate (no implementation)
/aidw:go                      ← no argument: resume this folder's demand
/aidw:fix us-1234 bug 5678    ← a bug the QA returned: the short path on the demand
/aidw:ask how does X work?    ← a question about the code, answered with file:line
/aidw:investigate <error>     ← root cause of a problem and, if it is a defect, the Bug drafted
```

The orchestrator detects the project, opens the demand (or **resumes from the recorded step**), creates the worktree,
moves the chat into it and drives the flow to the PR. It runs on its own between your fixed points (plan, review
findings, your code review, manual steps, PR), locked actions, real doubts and anything outside the plan.

### Chat commands

| Claude | Codex | What it does |
|---|---|---|
| `/aidw:go [demand]` | `$aidw-go` | Takes over the chat as the orchestrator and drives the demand |
| `/aidw:survey <card or text>` | `$aidw-survey` | Survey before implementing: validates each point of the card in the code, maps the flow, estimates effort, story points and complexity |
| `/aidw:fix <demand> <what>` | `$aidw-fix` | Fix after delivery (short path): a bug the QA returned, the PR's comments or an adjustment |
| `/aidw:ask <question>` | `$aidw-ask` | A question about the code or the environment, answered with `file:line`; read-only |
| `/aidw:investigate <evidence>` | `$aidw-investigate` | Root cause of an error, log or stuck record and, if it is a defect, the Bug or debt drafted |
| `/aidw:card <idea>` | `$aidw-card` | Drafts a User Story or technical debt grounded in the code; created with your OK |
| `/aidw:kb-review [scope]` | `$aidw-kb-review` | Rechecks the knowledge base against the code; notes change with your OK |
| `/aidw:exit` | `$aidw-exit` | Records where it stopped and returns the chat to normal |
| `/aidw:diff [repo\|exit]` | — | Moves the diff panel to the demand's next repository; `exit` returns to the demand folder |
| `/aidw:done` | `$aidw-done` | Closes the task: writes what it learned into the context and commits the context |
| `/aidw:knowledge [topic]` | `$aidw-knowledge` | What the context's knowledge base knows about a system, contract, concept or demand |
| `/aidw:context [list\|use <name>\|create]` | `$aidw-context` | Manages contexts |
| `/strip` · `/panel [tab]` · `/metrics` · `/review-tests` | — | Mods: hide/show the demand strip; open the General, Metrics and Tests and Review panels |

Every command and flag: [docs/commands.md](docs/commands.md).

### Talking to the orchestrator

| You want | Say |
|---|---|
| Where it is | "Which step are we in?" |
| Another model for one task | "Use Opus for the coder on this one" |
| Lower cost | "This fix is small, use the coder medium" |
| The diff of another repository | "Show me the front-end diff" |
| An answer, no flow | "Just answer, don't delegate" |

Each agent result is shown with its **measured** header and summary (never estimated):

```text
## Coder - claude-sonnet High
Coder (e1-r1) | Claude Sonnet | effort high | 67,448 tokens | 156 s
```

### Where things live

- **Worktrees:** `<worktree root>/<demand>/<repo>` (default `C:/wt` on Windows, `~/wt` elsewhere), one per repository,
  each on its own branch. Your working copy is never touched.
- **Artifacts:** `<state dir>/<demand>/` — card summary, exploration, plan, diffs, reviews, your decisions, the test
  script, the PR text, `metrics.md` and `demand.json` (the state to resume).

## 3. What comes included

### Workflows

| Workflow | For | File |
|---|---|---|
| `development` | Feature, improvement, bug, technical debt or urgent fix, from the card to the PR | `workflows/development.yaml` |
| `pr-review` | Reviewing someone else's PR; the author fixes, you choose what is published | `workflows/pr-review.yaml` |
| `survey` | Estimating a demand before anyone implements it; read-only | `workflows/survey.yaml` |

Step by step: [docs/workflow.md](docs/workflow.md).

### Agents and their defaults

| Agent | Does | Default model · effort | Exceptions |
|---|---|---|---|
| `orchestrator` | The main chat: drives, reads the plan, delegates, brings decisions to you, opens the PR with your OK | the chat's (see below) | — |
| `explorer` | Reads code and environment and answers numbered questions with `file:line` | Haiku | Sonnet medium (redo once), Sonnet high (survey) |
| `planner` | Writes the plan with its deliveries; adjusts it when you ask | Sonnet · high | medium (plan adjustment) |
| `coder` | Implements one delivery at a time: code, tests, build | Sonnet · high | medium (small fix, test adjustment) |
| `reviewer` | Reviews the diff against the plan: quality, bugs, security | Sonnet · high | medium (re-review), low (trivial fix) |
| `qa` | Test script and data in parallel with the code; then the tests | Sonnet · medium | high (redo once) |
| `documenter` | The demand README and the Tasks on the board, and the PR text | Haiku | — |

- The defaults live in `DEFAULT_AGENTS` in `aidw.py` (each role's model **tier** and effort) and in
  `config/models.toml` (which model is each tier); the exceptions live in `[effort.variants]` of
  `orchestrator/config/routing.toml`. Your `aidw.config.toml` overrides the defaults.
- **The orchestrator runs with the model and effort of the chat it is opened in — the config value is only the
  recommendation shown in the Runtime section.**
- Haiku takes no effort, so the explorer and documenter efforts are ignored on Claude.

Change model and effort: [docs/agents.md](docs/agents.md#change-model-and-effort).

### Skills

`to-spec` (planner), `code-review` (reviewer), `verify-premise`, `prepare-worktree`, `database-safe`, plus the commands
`go`, `survey`, `fix`, `ask`, `investigate`, `card`, `kb-review`, `exit`, `diff`, `done`, `knowledge`, `context`. See [docs/skills.md](docs/skills.md).

### Contexts

AiDW is **context-independent**. A **context** is a team's rule package in a private Git repository under
`contexts/<name>/`: systems and their build/test commands, rules per agent, policies, permissions, MCPs, skills,
validators and a knowledge base. Without one, AiDW runs on its generic rules. See [docs/contexts.md](docs/contexts.md).

## 4. Configure

Three layers, each one on top of the previous:

| Layer | Where | Versioned | Who changes it |
|---|---|---|---|
| **Core** | this repository: agents, skills, workflow, routing, model catalog, generic policies | yes | AiDW maintainers |
| **Context** | `contexts/<name>/`: systems, team rules, permissions, MCPs | yes (team repo) | the team |
| **Machine** | `aidw.config.toml`: your profile | no | you |

```toml
[provider]
name = "claude"                     # or "codex"

[workspace]
project_dirs = ["C:/Repos"]         # where your repositories live

[worktree]
root = "C:/wt"                      # where the demands' worktrees are created

[context]
active = "my-team"                  # which context to use ("" = none)

[ui]
language = "en"                     # language of the chat and the mods (BCP-47: "en", "pt-BR", ...)

[agents.coder]
model = "opus"                      # a key of config/models.toml
effort = "high"

[agents.qa]
enabled = false                     # turn an agent off
```

`python aidw.py configure` reruns the wizard; or edit by hand, run `python aidw.py install` (and `apply` for project
mode) and open a new chat. Field by field, the language settings and example profiles:
[docs/configuration.md](docs/configuration.md).

## 5. Security

**The model is never the last barrier.** On Claude Code:

- **CLI rules:** force push, `reset --hard`, `clean -f` and reading `.env` are always denied; what the context or your
  config marks as `ask` (commit, push, write SQL…) always asks for your OK.
- **Worktree and guard:** agents work in the worktree; a hook stops them from editing the main working copy, and a
  commit with a leftover test adjustment is refused.
- **Per-agent scope:** each role has only the tools and MCP servers it needs.
- **Context validators:** risky operations go through scripts that refuse what is not allowed.
- **Locked actions become proposals:** the agent returns the exact command, the orchestrator asks for your OK once.

On Codex, AiDW installs none of this: only Codex's own approvals apply. Details: [docs/security.md](docs/security.md).

## 6. Documentation

| Document | Content |
|---|---|
| [docs/workflow.md](docs/workflow.md) | The flow step by step, where you decide, states, review, tests, PR, PR review, survey, artifacts |
| [docs/agents.md](docs/agents.md) | Each agent, defaults, how to change model and effort, variants, output contract, creating an agent |
| [docs/configuration.md](docs/configuration.md) | `aidw.config.toml` field by field, language, profiles, core config files |
| [docs/commands.md](docs/commands.md) | Every chat command and every `aidw.py` command |
| [docs/contexts.md](docs/contexts.md) | A context's structure, `context.toml`, policies, knowledge base, creating one |
| [docs/demands-and-worktrees.md](docs/demands-and-worktrees.md) | Demand folder, worktrees, several repositories, `/aidw:diff`, resume and clean up |
| [docs/skills.md](docs/skills.md) | Each skill, `skills` × `preload`, context skills, writing one |
| [docs/mods.md](docs/mods.md) | The Claude Code mods (`aidw-mods`): strip, metrics, delegation locks, secret filter |
| [docs/panel.md](docs/panel.md) | What each panel shows and where its data comes from |
| [docs/security.md](docs/security.md) | The protection layers and the core policies |
| [docs/claude-and-codex.md](docs/claude-and-codex.md) | Claude Code first; what Codex gets, native and headless modes, generated files |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Common symptoms and fixes |
