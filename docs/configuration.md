# Configuration

Where each setting lives, the language settings, and ready-made profiles.

## The three layers

| Layer | Where | Versioned | Who changes it | What it defines |
|---|---|---|---|---|
| **Core** | this repository | yes | AiDW maintainers | agents, skills, workflow, `state` rules, effort exceptions, model and MCP catalogs, generic policies |
| **Context** | `contexts/<name>/` | yes, the team's repo | the team | systems, rules per agent, policies, permissions, required MCPs, branch prefix, the context's language ([contexts.md](contexts.md)) |
| **Machine** | `aidw.config.toml` | **no** | you | provider, folders, active context, enabled MCPs, extra blocks, UI language, each agent's name, model, effort and status |

Rule of thumb: what is only yours goes in `aidw.config.toml`; what the whole team must follow goes in the context; what
is valid for any team goes in the core.

After changing any layer:

```powershell
python aidw.py install    # the global Claude plugin (and Codex, if you installed it)
python aidw.py apply      # project mode (a chat opened at the AiDW root)
```

Then open a new chat. To redo the file through the wizard: `python aidw.py configure` (it rewrites the file; your own
comments are lost). `python aidw.py configure --defaults [--provider codex] [--language pt-BR]` writes the default
config without asking.

## `aidw.config.toml` field by field

The template is `aidw.config.example.toml`; `setup` creates yours through the wizard.

### `[provider]`

```toml
[provider]
name = "claude"           # "claude" = everything on Claude Code · "codex" = everything on Codex CLI
```

`claude` is the default and the recommended one. With `codex`, AiDW is only agents and skills
([claude-and-codex.md](claude-and-codex.md)). The Claude plugin and the Codex install can coexist
(`install --provider all`); after that, `install` without `--provider` updates both.

### `[delegation]`

```toml
[delegation]
mode = "native"           # the provider's subagents (recommended) · "headless" = one process per task
```

The plugin (`install`) requires `native`. `headless` runs each agent with `aidw.py delegate` (`claude -p` or
`codex exec`), only in project mode — useful for automation.

### `[workspace]` and `[worktree]`

```toml
[workspace]
project_dirs = ["C:/Repos", "C:/Legacy"]   # your repositories; open to the orchestrator and every agent

[worktree]
root = "C:/wt"            # <root>/<demand>/<repo>; short and outside any repository
```

The default root is `C:/wt` on Windows and `~/wt` elsewhere. A short path avoids Windows' 260-character limit in .NET
and Node projects.

### `[context]` and `[mcp]`

```toml
[context]
active = "my-team"        # folder in contexts/ ("" = none). Switch with /aidw:context use <name>

[mcp]
enabled = ["playwright", "chrome-devtools", "figma", "context7"]   # keys of config/mcp.toml (this is the default)
```

The MCPs a context requires (`required_mcp`) are checked by `doctor` regardless of this list.

### `[ui]` — language

```toml
[ui]
language = "en"           # BCP-47 tag: "en", "pt-BR", "es"... Default "en"
```

### Language

Two settings, one inheriting the other:

| Setting | Where | Default | Controls |
|---|---|---|---|
| `[ui] language` | `aidw.config.toml` | `en` | the language the orchestrator talks to you in, and the `aidw-mods` strip and panels (any `pt*` tag shows them in Portuguese; anything else in English) |
| `language` | top level of `contexts/<name>/context.toml` | the `[ui] language` | the content of the context and of the demand artifacts (plans, reports, reviews, task files) |

- **File names are always English** (`plan-<id>.md`, `metrics.md`…), whatever the language.
- The wizard asks the UI language (step 6, before the context, so a context created there inherits it);
  `python aidw.py context create <name> --language <tag>` sets a context's language.
- `python aidw.py show` prints both, e.g. ``Language: UI English (`en`); demand artifacts Portuguese (Brazil) (`pt-BR`)``.
- After changing either: `install` (and `apply`) and a new chat.

### `[policies]`

```toml
[policies]
deny = ["Bash(git push --force *)", "Read(**/.env)"]   # always blocked
ask = ["Bash(npm publish *)"]                           # always asks for OK (beats any allow)
```

They add up with the context's rules. The default `deny` list blocks force push, `reset --hard`, `clean -f` and
reading `.env` files, in Bash and PowerShell.

### `[agents.<role>]`

```toml
[agents.reviewer]
name = "reviewer"         # name shown in the chat (accents and spaces allowed); without it, the role
enabled = true            # false = the orchestrator never delegates to it
model = "sonnet"          # key of config/models.toml; without it, the role's default tier
effort = "high"           # default effort; the exceptions live in [effort.variants] of routing.toml
skills = ["code-review", "verify-premise"]
preload = ["code-review"]
```

| Role | Default tier (Claude model) | Default effort |
|---|---|---|
| `orchestrator` | `top` (Opus) — only a recommendation: the chat's model and effort apply | medium |
| `planner` | `mid` (Sonnet) | high |
| `explorer` | `fast` (Haiku) | low (ignored by Haiku) |
| `coder` | `mid` (Sonnet) | high |
| `reviewer` | `mid` (Sonnet) | high |
| `qa` | `mid` (Sonnet) | medium |
| `documenter` | `fast` (Haiku) | medium (ignored by Haiku) |

These come from `DEFAULT_AGENTS` in `aidw.py` and `config/models.toml`
([agents.md](agents.md#where-the-defaults-live)).

- A config without a newer role gets it with the default; a removed role (`api-db`, `bug-hunter`, `security`) is
  ignored with a warning.
- Old core skill names (`verificar-premissa`, `preparar-worktree`) are still accepted and mapped to the new ones.
- Names that collide with the CLI's agents (`plan`, `explore`, `default`…) are refused.

## Profiles

### Default

What the wizard writes. Nothing to change: each agent's default and the exceptions already balance cost and quality.

### Save the session (smaller plan)

```toml
[agents.coder]
effort = "medium"

[agents.reviewer]
effort = "medium"
```

And, day to day: "this fix is small, use the coder medium". `metrics.md` and `orchestrator-metrics.md` show where the
usage goes — usually the orchestrator's chat; a cheaper chat model is the biggest saving.

### Codex only

```toml
[provider]
name = "codex"
```

```powershell
python aidw.py install --provider codex              # aidw-* agents and skills
python aidw.py open --provider codex --demand 1234   # turns on multi_agent_v2 (spawn_agent needs it)
```

Agents and skills only: no permission rules, hooks, guard, profile, per-agent MCP, diff panel, session folders or mods
([claude-and-codex.md](claude-and-codex.md)).

### Front end

```toml
[mcp]
enabled = ["playwright", "chrome-devtools", "figma", "context7"]
```

Figma needs authentication once (Claude: `/mcp` → figma → Authenticate; Codex: `codex mcp login figma`).

### Your own names and language

```toml
[ui]
language = "pt-BR"

[agents.coder]
name = "Dev"

[agents.reviewer]
name = "Code Reviewer"
```

Context texts use `{{agent:<role>}}` and follow the new name.

## The core configuration files

Changes here apply to everyone who uses AiDW: do them by PR.

| File | What it defines |
|---|---|
| `config/models.toml` | Model catalog per provider: `model_id` (on Claude, the alias), `label`, `tiers` (`top`/`mid`/`fast`), accepted `efforts`, `min_cli`, `alias` |
| `orchestrator/config/routing.toml` | `[rules]` (`state` → action) and `[[effort.variants.<role>]]` (the exceptions: `effort`, optional `model`, `when`) |
| `config/mcp.toml` | MCP catalog: command or URL, `auth`, `allow`, the roles that may use each (`agents`), `use_when` and `triggers` |
| `orchestrator/ORCHESTRATOR.md` · `orchestrator/SURVEY.md` | The orchestrator's core, and the lean survey orchestrator |
| `orchestrator/reference/` | What the orchestrator reads on demand (`short-path`, `testing`, `pr-review`, `pr-triage`, `survey`) |
| `orchestrator/policies/` | Generic policies: git, database, production, secrets, permissions |
| `agents/`, `skills/`, `workflows/` | Agents, skills and workflows |

## What stays outside AiDW

`install` adds to `~/.claude/settings.json` only AiDW's items (permission rules, allowed folders, environment
variables) and removes only what it wrote itself. It does **not** write `model` or `effortLevel`: the chat's model is
the one you pick. Your `~/.claude/CLAUDE.md` and personal CLI settings stay yours.
