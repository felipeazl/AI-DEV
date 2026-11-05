# Troubleshooting

Always start with `.\doctor.ps1` (`./doctor.sh`): it shows what is missing and ends with **READY** or **NOT READY**.

| Symptom | Likely cause | Fix |
|---|---|---|
| `/aidw:go` does not show up | Plugin not installed, or chat opened before the install | `python aidw.py install` and a new chat |
| I changed the config and nothing changed | The chat loads the definitions when it opens | `python aidw.py install` (and `apply` for project mode), and a new chat |
| The chat answers in the wrong language | `[ui] language` not set, or the chat opened before the change | Set `[ui] language` in `aidw.config.toml`, `install`, new chat ([configuration.md](configuration.md#language)) |
| Claude asks for approval on an `aidw.py` command | The path is written in a form that is not allowed | Use `python "<root>/aidw.py" …`; run `install` if the rules are gone |
| The diff panel is empty in a demand with several repositories | The chat is in the demand folder, which is not a repository | `/aidw:diff` to go to a repository |
| Headless fails with "OAuth session expired" | The CLI login expired | `claude auth login` (`doctor` shows "no login") |
| On Codex, `npm`/`node` fail with `EPERM` in your user folder | The `node` on the PATH lives in the user profile (e.g. nvm), which the sandbox cannot read | Install Node outside the profile (e.g. Program Files) and put it first on the PATH |
| On Codex, the orchestrator cannot call the agents | `multi_agent_v2` is off | Open with `python aidw.py open --provider codex`, or set `[features] multi_agent_v2 = true` in `~/.codex/config.toml` |
| `doctor` reports leftovers of an old Codex install | `aidw` profile, `aidw.rules` or AiDW hooks from an earlier install | `python aidw.py install --provider codex` removes them |
| A delegation comes back denied with `AiDW (delegation lock)` | The `Agent` call broke a rule (table cell, `model`, prompt format, pasted input) | The reason says what to fix ([mods.md](mods.md#delegation-locks)) |
| The AiDW strip does not appear above the prompt | Session outside orchestrator mode, demand in `DONE`, strip hidden or `aidw-mods` not installed | `/aidw:go`; `/strip`; `python aidw.py install` and a new chat ([mods.md](mods.md)) |
| A strip button does not open its panel, or the strip has no buttons | The window is too narrow for the panel, or the context has `[mods] panel = false` | Widen the window (`/panel`, `/metrics` and `/review-tests` say why); remove the line from `context.toml` and run `install` ([panel.md](panel.md)) |
| An agent follows the orchestrator's rules | Project-mode `CLAUDE.md` loaded into the agent | Handled by `omitClaudeMd`/`claudeMdExcludes`; reinstall |
| A chat in a demand's state folder gets the orchestrator rules twice | The folder is inside the AiDW root: the project-mode `CLAUDE.md` loaded together with the `go` skill | `demand set` writes `.claude/settings.json` with `claudeMdExcludes` in the demand folder; it applies to the next chat opened there |
| `dubious ownership` in a Codex agent | AiDW does not configure Codex's Git (agents and skills only) | `git config --global --add safe.directory <folder>` for the repository or worktree folder |
| `MCP figma needs authentication` | OAuth not done | Claude: `/mcp` → figma → Authenticate · Codex: `codex mcp login figma` |
| `model … is not enabled for this account` | A Codex model outside your plan | Remove the agent's `model` (the tier applies) or pick an enabled one |
| Invalid or reserved agent name | It collides with a CLI agent (`plan`, `explore`, `default`…) | Choose another `name` |
| `worktree remove` refuses | Local changes or unpushed commits | Commit and push (with your OK) or discard, and try again |
| The build fails in the worktree but works in the working copy | A dependency outside Git did not come along | `[worktree] link` or the system's `worktree_link` in the context |
| `install` stops saying a file was changed | A generated file was edited by hand | Move the change to its source (config, context, core) or use `--force` |
