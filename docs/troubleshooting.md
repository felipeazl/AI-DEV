# Troubleshooting

Common problems and how to fix them. Always start with `.\doctor.ps1` (`./doctor.sh` on Linux/macOS): it checks
everything, changes nothing, and ends with **READY** or **NOT READY** plus the list of what to fix. `.\setup.ps1`
(`./setup.sh`) fixes most of what it reports and can be run again at any time.

## First install

| Symptom | Likely cause | Fix |
|---|---|---|
| `Python 3.11+ not found` | No Python, or one older than 3.11 | Install Python 3.11+ (`setup.ps1` offers `winget`), reopen the terminal and run setup again |
| `aidw.config.toml not found` | Setup has not run on this machine | `.\setup.ps1` (`./setup.sh`): the wizard creates it |
| `doctor`: `git not found`, `` CLI `claude` not found `` or `npx not found` | A prerequisite is missing (Node.js is needed by the local MCPs) | Install it with the command `doctor` prints (setup offers to), reopen the terminal and run setup again |
| `doctor`: `not logged in`, or a headless run fails with an expired login | The Claude Code CLI is not authenticated | Run `claude` once and log in (Codex: `codex login`) |
| `` context '<name>' not found `` | The config names a context whose folder is not in `contexts/` (a context is its own Git repository) | Clone the team's context repository into `contexts/<name>/`, or run `setup` to choose another one, create one or go on without one |
| `doctor`: `` MCP '<name>' not registered in claude (required by the context) `` | The context requires an MCP server you have not added | Run the command `doctor` prints (`setup` offers to run it) |
| `doctor`: `MCP <name> needs authentication` | OAuth not done (e.g. Figma) | Claude: `/mcp` → the server → Authenticate · Codex: `codex mcp login <name>` |
| `doctor`: `MCP <name> with status 'Pending approval'` | Claude Code has not approved the AiDW project MCPs yet | Harmless for the plugin; to clear it, run `claude` in the AiDW folder once and approve them |
| `doctor`: `could not confirm the login` | `claude auth status` gave no answer (an info line, not an error) | If a chat opens normally, nothing to do; otherwise run `claude` and log in |
| `doctor`: `allowed folder … does not exist` | A path in `[workspace] project_dirs` (or in the context) is missing | Clone the repositories or fix the path in `aidw.config.toml` |
| `doctor`: `the worktree root (…) is inside a Git repository` | `[worktree] root` points inside a repository | Use a short folder outside any repository, e.g. `C:/wt` |
| `doctor`: `environment not generated yet` or `file(s) out of date` | `apply` has not run since the last change | `python aidw.py apply` and a new chat |
| `install`: `the plugin install is Claude's` | `[provider] name = "codex"` | `python aidw.py install --provider codex` ([claude-and-codex.md](claude-and-codex.md)) |
| `install`: `the global install uses native subagents` | `[delegation] mode = "headless"` | Set `mode = "native"`; headless only works in project mode |
| `install`: `settings.json is not valid JSON` | `~/.claude/settings.json` was broken by a manual edit | Fix the JSON, then `install` again |
| `/aidw:go` does not show up, or `doctor` says the plugin is missing or out of date | Plugin not installed, or the chat (or desktop app) opened before the install | `python aidw.py install` and a new chat |

## Day to day

| Symptom | Likely cause | Fix |
|---|---|---|
| I changed the config and nothing changed | The chat loads the definitions when it opens | `python aidw.py install` (and `apply` for project mode), and a new chat |
| The chat answers in the wrong language | `[ui] language` not set, or the chat opened before the change | Set `[ui] language` in `aidw.config.toml`, `install`, new chat ([configuration.md](configuration.md#language)) |
| Claude asks for approval on an `aidw.py` command | The path is written in a form that is not allowed | Use `python "<root>/aidw.py" …`; run `install` if the rules are gone |
| The diff panel is empty in a demand with several repositories | The chat is in the demand folder, which is not a repository | `/aidw:diff` to go to a repository |
| A delegation comes back denied with `AiDW (delegation lock)` | The `Agent` call broke a rule (table cell, `model`, prompt format, pasted input) | The reason says what to fix ([mods.md](mods.md#delegation-locks)) |
| The AiDW strip does not appear above the prompt | Session outside orchestrator mode, demand in `DONE`, strip hidden or `aidw-mods` not installed | `/aidw:go`; `/strip`; `python aidw.py install` and a new chat ([mods.md](mods.md)) |
| A strip button does not open its panel, or the strip has no buttons | The window is too narrow for the panel, or the context has `[mods] panel = false` | Widen the window (`/panel`, `/metrics` and `/review-tests` say why); remove the line from `context.toml` and run `install` ([panel.md](panel.md)) |
| An agent follows the orchestrator's rules | Project-mode `CLAUDE.md` loaded into the agent | Handled by `omitClaudeMd`/`claudeMdExcludes`; reinstall |
| A chat in a demand's state folder gets the orchestrator rules twice | The folder is inside the AiDW root: the project-mode `CLAUDE.md` loaded together with the `go` skill | `demand set` writes `.claude/settings.json` with `claudeMdExcludes` in the demand folder; it applies to the next chat opened there |
| Invalid or reserved agent name | It collides with a CLI agent (`plan`, `explore`, `default`…) | Choose another `name` |
| `worktree remove` refuses | Local changes or unpushed commits | Commit and push (with your OK) or discard, and try again |
| The build fails in the worktree but works in the working copy | A dependency outside Git did not come along | In `context.toml`: `[worktree] link` (folders linked into every worktree; default `packages`, `node_modules`) or the system's `worktree_link` |
| `install` stops saying a file `was changed outside AiDW` | A generated file was edited by hand | Move the change to its source (config, context, core) or use `--force` |

## Codex only

| Symptom | Likely cause | Fix |
|---|---|---|
| `npm`/`node` fail with `EPERM` in your user folder | The `node` on the PATH lives in the user profile (e.g. nvm), which the sandbox cannot read | Install Node outside the profile (e.g. Program Files) and put it first on the PATH |
| The orchestrator cannot call the agents | `multi_agent_v2` is off | Open with `python aidw.py open --provider codex`, or set `[features] multi_agent_v2 = true` in `~/.codex/config.toml` |
| `doctor` reports leftovers of an old Codex install | `aidw` profile, `aidw.rules` or AiDW hooks from an earlier install | `python aidw.py install --provider codex` removes them |
| `dubious ownership` in an agent | AiDW does not configure Codex's Git (agents and skills only) | `git config --global --add safe.directory <folder>` for the repository or worktree folder |
| `model … is not enabled for this account` | A Codex model outside your plan | Remove the agent's `model` (the tier applies) or pick an enabled one |
