# Commands

## In the chat

| Claude | Codex | What it does |
|---|---|---|
| `/aidw:go [demand]` | `$aidw-go` | Takes over the chat as the orchestrator: detects the project, opens or resumes the demand, creates the worktree and drives the flow. `pr <n>` after the demand reviews someone else's PR. Runs only when you call it |
| `/aidw:survey <card or text>` | `$aidw-survey` | Survey before implementing (workflow `survey`, read-only): validates each point of the card in the code, maps the flow and writes `survey-<id>.md` with hours, story points, complexity and open questions ([workflow.md](workflow.md#survey-survey)) |
| `/aidw:fix <demand> <what>` | `$aidw-fix` | Fix after delivery on a demand that already has code (short path): `bug <n>` (a Bug the QA team returned), `pr` (the comments on the demand's PR) or the adjustment's text; the fix, a review of only the fix and a retest of the affected steps, with no new plan or Task |
| `/aidw:ask <question>` | `$aidw-ask` | A question about the code, a contract or the environment, outside a demand: the explorer answers with `file:line` in `answer-<id>.md` (demand `ask-<slug>`); read-only |
| `/aidw:investigate <error, log or record>` | `$aidw-investigate` | Investigates a problem before there is a card: the explorer proves the root cause, `investigation-<id>.md` gives the diagnosis and the options and, if it is a defect, the documenter drafts the Bug or the technical debt (demand `inv-<slug>`); created only with your OK |
| `/aidw:card <idea or problem>` | `$aidw-card` | Drafts a User Story or a technical debt grounded in the code (`workitem-<id>.md`, demand `card-<slug>`); created on the board only with your OK of the fields |
| `/aidw:kb-review [system, note or number]` | `$aidw-kb-review` | Rechecks the knowledge base against the code: `kb check`, the oldest notes (or those named), each fact confirmed or corrected with `file:line`; the notes change only with your OK (demand `kb-review-<date>`) |
| `/aidw:exit` | `$aidw-exit` | Records the step and the next action (`paused`) and returns the chat to normal |
| `/aidw:diff [repo\|exit]` | — | Moves the session to a demand repository's worktree; the diff panel follows ([demands-and-worktrees.md](demands-and-worktrees.md#see-each-repositorys-diff)) |
| `/aidw:done` | `$aidw-done` | Closes the task: writes what it learned into the context (the demand's note and the knowledge notes it touched; build and environment in `context.toml`), validates, reinstalls, commits and pushes only the context repository and marks the demand `done` |
| `/aidw:knowledge [topic]` | `$aidw-knowledge` | Queries the context's knowledge base: a system, contract, concept or demand note, with its links and who cites it; fixes a note when you ask ([contexts.md](contexts.md#knowledge-base)) |
| `/aidw:context [list]` | `$aidw-context` | Contexts, which one is active, repository, systems, plugin status |
| `/aidw:context use <name>` | `$aidw-context use <name>` | Validates and activates a context and regenerates the environment |
| `/aidw:context create` | `$aidw-context create` | Creates a new context (analysis of the repositories + at least 10 questions) |
| `/strip` | — | Hides or shows the demand strip above the prompt (mod, [mods.md](mods.md)) |
| `/panel [tab]` | — | Opens the General panel, or the panel that has the tab ([panel.md](panel.md)) |
| `/metrics` | — | Opens the Metrics panel |
| `/review-tests` | — | Opens the Tests and Review panel (Questions in a survey); read-only |

`/aidw:go`, `/aidw:survey`, `/aidw:fix`, `/aidw:ask`, `/aidw:investigate`, `/aidw:card`, `/aidw:kb-review`, `/aidw:exit` and `/aidw:done` run only when you call them. The skills the agents use are
hidden from the `/` menu on Claude (`user-invocable: false`); Codex shows every `$aidw-*` skill.

## Command line (`python aidw.py …`)

With no command, `aidw.py` runs `setup`. Commands that take `--json` print machine-readable output.

### Install and diagnosis

| Command | What it does |
|---|---|
| `setup [--reconfigure] [--skip-tools]` | Prerequisites, wizard (only when there is no config, or with `--reconfigure`), folders, `apply`, MCP registration, `doctor`. `setup.ps1`/`setup.sh` call it |
| `configure [--defaults [--provider claude\|codex] [--language <tag>]]` | Only the wizard; rewrites `aidw.config.toml`. `--defaults` writes the default config without asking |
| `apply [--dry-run]` | Generates project mode from the config (idempotent) |
| `install [--provider claude\|codex\|all] [--dry-run] [--force] [--mcp]` | Claude (default): the `aidw` and `aidw-mods` plugins and AiDW's rules in `~/.claude/settings.json`; `--mcp` also registers the catalog MCPs in user scope. Codex: **only** the `aidw-*` agents and skills. Without `--provider`: Claude, plus Codex when it was installed. `--force` overwrites a generated file edited by hand |
| `uninstall [--provider claude\|codex\|all] [--dry-run]` | Removes only what `install` added (default `all`) |
| `doctor` | Core, CLIs and login, context, variables, MCPs, folders, install and generated environment; ends with **READY** or **NOT READY** |
| `status [--json]` | Quick view without calling the CLIs: context, install, active demands with step and worktree, and what needs attention |
| `show` | Name, display name, role, model, effort and kind of each agent, the state folder and the languages |

### Day to day

| Command | What it does |
|---|---|
| `open [--provider claude\|codex] [--demand <id> [--repo <repo>] \| --path <dir>] [--no-orchestrate] [--print] [--app]` | Opens the CLI in the demand's worktree (or a folder), already calling the orchestrator. `--print` only shows the command; `--app` (Codex) opens the Codex desktop app |
| `chat` | Opens the orchestrator in project mode (a chat at the AiDW root) |
| `project detect [--path <dir>] [--json]` | A folder's repository, context system and demand |
| `demand set <id> [--step S] [--status active\|paused\|done] [--title t] [--note n] [--summary s] [--pr REPO=N] [--task TICKET=ID] [--loop ID\|-] [--extra-step STEP]` | Writes the demand state (see below) |
| `demand show <id>` · `demand list [--active]` | Read the state |
| `session bind [--demand <id>]` · `session unbind` | Puts this Claude Code session into (or out of) orchestrator mode and binds the demand it drives; `--session` overrides `$CLAUDE_CODE_SESSION_ID` |
| `worktree create --repo <dir> --demand <id> [--slug s] [--base b] [--pr n]` | The demand's worktree, branch and junctions (idempotent); `--pr` makes a read-only worktree of someone else's PR |
| `worktree list` · `inspect <id>` · `remove <id>` · `cleanup` | Status, safe removal (`--repo` when the demand has several) and registry cleanup |

`demand set` options:

| Option | Effect |
|---|---|
| `--step` | Current step: `UNDERSTAND`, an action of the routing (`PLAN`, `REVIEW`, `TEST`, `PR`, `DONE`…), `CODE_REVIEW`/`QA_TEST` or an outside step the context declares |
| `--status` | `active`, `paused` or `done` |
| `--title`, `--note` | Card title; where it stopped / next step (the panel shows the note) |
| `--summary` | What the demand is about, up to 4 lines (the panel's demand map) |
| `--pr REPO=N` | The open PR of one of the demand's repositories (repeatable) |
| `--task TICKET=ID` | The work item created for a delivery, e.g. `E1=5001` (repeatable) |
| `--loop ID` | A fix loop after delivery (e.g. `bug-1234`): its review rounds count from 1; `-` clears it |
| `--extra-step STEP` | An outside step of the context the demand goes through (repeatable; `-STEP` removes it) |

### Contexts

| Command | What it does |
|---|---|
| `context list` | Lists the contexts |
| `context check <name>` | Validates a context as if it were active: full build, own Git repository, ignored by AiDW, exclusive state folder, knowledge base, upstream |
| `context upstream [--no-fetch]` | Fetches the active context's upstreams and warns when the copies (`synced`) or the local checkout fell behind the remote; run at the start of every workflow |
| `context use [<name>] [--skip-install]` | Activates it (empty name = none), runs `apply` and, if installed, `install` |
| `context create <name> [--description d] [--mcp a,b] [--env A,B] [--language <tag>]` | Creates `contexts/<name>/` with the minimal structure and its own Git repository |

### Knowledge base

| Command | What it does |
|---|---|
| `kb show <system\|note> [--brief] [--json]` | A note, its links and who cites it (system key, name, alias or title). `--brief`: only the note |
| `kb search <words> [--limit n] [--json]` | Notes with all the words, accent- and case-insensitive; title and keywords weigh more |
| `kb check [--json]` | Broken links, repeated names, frontmatter, unknown systems, systems without a note, orphans, secret-looking text; warns on notes over 150 lines or unchecked for 6 months (also runs in `context check`) |
| `kb index` | Regenerates `index.md`: notes by type and the concepts glossary |
| `kb collect <demand> [--json]` | Gathers what the demand learned (the reports' *Knowledge base* sections, `learnings-<id>.md`, the summary's notes, the plan's decisions) into `collect-<id>.md`, for `/aidw:done` |

### Used by the orchestrator and the mods

| Command | What it does |
|---|---|
| `record --agent <name> [--effort e] --label <x> --demand <dir> [--state s] (--tokens N --tool-uses N --duration-ms N \| --codex-task <t>)` | Records a native delegation in `metrics.md` and prints the header and summary |
| `record-orchestrator --demand <dir> --session <id> …` | Adds a turn of the main chat to `orchestrator-metrics.md` (run by the mod) |
| `delegate --agent <a> --task <file> --demand <dir> [--effort e] [--model m] [--label x] [--max-turns n] [--timeout s]` | Runs a headless agent for one task (headless mode). `AIDW_DEBUG=1` writes a debug log in the demand |

## Scripts and tests

```powershell
.\setup.ps1          # ./setup.sh on Linux/macOS
.\doctor.ps1         # ./doctor.sh — checks only, changes nothing
python -m unittest discover -s tests
python tests/test_apply.py --update     # rewrites the reference files when an output change is intended
```
