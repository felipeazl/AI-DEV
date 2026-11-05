# Mods (Claude Code only)

Mods are Claude Code *function-hook* plugins: code that runs inside the session, draws on screen (a strip above the
prompt, panels, status) and reacts to events (a tool call, a message sent, a subagent that finished). AiDW ships its
own in the **`aidw-mods`** plugin, which `install` installs together with the `aidw` plugin.

**They exist only on Claude Code.** Codex has no mods ([claude-and-codex.md](claude-and-codex.md)).

The mods speak the `[ui] language` of `aidw.config.toml` (a `pt*` tag shows them in Portuguese, anything else in
English; [configuration.md](configuration.md#language)).

## When they are on

The AiDW mods are on **only in orchestrator mode**:

- **On:** `/aidw:go` or `/aidw:survey` register the session in `state/sessions.json`, and `aidw-mods` checks that
  registry on every message. The `go` skill writes it with `aidw.py session bind` (reads `CLAUDE_CODE_SESSION_ID`), and
  so does the guard hook where the client sends it the slash command (the desktop app does, the terminal does not).
- **Which demand:** the registry keeps the context, the id and the demand folder (`session bind --demand <id>`, and
  every `demand set` in a registered session). The mod reads the folder from there, without guessing the demand from
  the text, so any id works. With no demand in the registry, the chat's folder counts when it opened in the demand or
  one of its worktrees.
- **Off:** `/aidw:exit` or `/aidw:done` remove the session from the registry, and the panels close.

Outside orchestrator mode they do not block, record, filter or show anything.

**The panels are on in every context.** A context can turn them off in `context.toml`:

```toml
[mods]
panel = false
```

Then the panels do not open, `/panel`, `/metrics` and `/review-tests` are not registered and the strip has no buttons.
Everything else (metrics, locks, secret filter, notes in the prompt, state after compaction) works in any context.

## Overview

| Mod | What for | Where |
|---|---|---|
| [Demand strip](#demand-strip) | Demand, step, context and plan usage bars, running agents, panel buttons | above the prompt |
| [Panels](#panels) | General, Metrics and Tests and Review, read-only ([panel.md](panel.md)) | next to the chat, by button or command |
| [Automatic metrics](#automatic-metrics) | Each delegation becomes a line of `metrics.md`; each orchestrator turn adds to `orchestrator-metrics.md` | agent result, end of turn |
| [Delegation locks](#delegation-locks) | Orchestrator rules the model may forget, checked before the agent runs | the call is denied |
| [Lean context](#lean-context) | Compacts an idle conversation before the cache expires | end of turn |
| [Orchestrator economy](#orchestrator-economy) | Code read in the orchestrator's chat | a note to the model |
| [Secret filter](#secret-filter) | No conversation line carries a secret's value | status |
| [Notes in the prompt](#notes-in-the-prompt) | `[[note]]` in a message brings the note along | the message context |
| [State after compaction](#state-after-compaction) | The orchestrator does not lose the thread | a line in the conversation |

## Demand strip

```text
AiDW us-1234 Review ● waits for you        context ▰▰▰▱▱ 41% · 82k   7d ▰▰▰▰▱ 58%   5h ▰▰▰▰▰ 91% · renews 16:40
╭──────────────────────────────────╮
│ ● Coder Sonnet medium      2m10s │
│ fix r1               184k tokens │
╰──────────────────────────────────╯
                                                                  General  Metrics  Tests and Review 4
```

1. **Demand and usage:** the id, the step, **● waits for you** when the step is yours (approval, triage, your code
   review, manual test, PR, final review) and, on the other side, this chat's context as a % of the model's window,
   and the plan's usage windows (7d and 5h), each with a thin bar.
2. **Running agents**, one card each: name, model and effort, elapsed time, label and the tokens of its latest
   response. With no agent, the line does not appear. When the cards do not fit in one line, they become a list.
3. **The buttons** **General**, **Metrics** and **Tests and Review** (**Questions** in a survey), with the number of
   items waiting for a decision.

Bars turn yellow from 75% and red from 90%; from 75% the 7d and 5h windows show the local time they renew. The usage
windows appear only on a subscription account. The strip disappears in `DONE`; **`/strip`** hides and shows it. It
updates live: the context on every response, the demand when a file in its folder changes.

## Panels

Three panels, each next to the chat, opened only when you ask, by the strip button or the command:

| Panel | Command | Development | PR review | Survey |
|---|---|---|---|---|
| General | `/panel [tab]` | demand map, criteria and rules | map | map, card × code, estimate |
| Metrics | `/metrics` | usage | usage | usage |
| Tests and Review | `/review-tests` | Review · Tests | Comments | Questions |

`/panel <tab>` opens the panel that has the tab (`/panel review`, `/panel tests`, `/panel comments`,
`/panel questions` open Tests and Review). **The panels only inform:** keeping or discarding a finding, a manual
step's result, what to publish, approving a PR and answering a question are decided in the chat. What each panel shows
and where its data comes from: [panel.md](panel.md).

## Automatic metrics

Every AiDW delegation (an `Agent` call whose prompt has `Demand folder:`) becomes a line in `metrics.md` when the agent
finishes. The mod runs `aidw.py record` with the numbers Claude Code measured: tokens, tool calls, duration and the
`state` read from the agent's final JSON.

- **Label:** from the task file name (`task-coder-fee.md` → `fee`); without a task, from the call's description.
- **What the orchestrator gets:** the result comes back with `AiDW: delegation recorded…` and the header and summary to
  show. Then the orchestrator does **not** run `record`; without that line, or if the mod says it could not record, it
  runs it itself.
- **Background agents:** the line is written when the agent finishes, and the notice arrives as a note in the
  conversation. The pending agent is kept in the session state, so a `/reload-plugins` or an `install` in the middle
  does not lose it.
- **Cost:** the mod adds up the usage of all the subagent's responses (input, cache written, cache read, output) and
  `record` writes the API-price equivalent in the *Cost (USD)* column.
- **The orchestrator:** at the end of each main-chat turn, the mod adds the turn's usage to the demand's
  `orchestrator-metrics.md` through `aidw.py record-orchestrator`: one line per session and model, with the equivalent
  cost, and a *By step* section. It is what `metrics.md` does not show and is usually most of the spending.

## Delegation locks

Before an AiDW agent runs, the mod checks the call against the *Agents and effort* table, which `apply`/`install`
write to `.aidw/runtime.json`. It refuses, with the reason (`AiDW (delegation lock): …`), when:

| Rule | Refuses when |
|---|---|
| Model | the call passes `model` and you did not mention a model in your recent messages |
| Format | the prompt lacks `Demand folder:` |
| Table | the `subagent_type` is neither the agent's default nor one of its exceptions, or the agent is off |
| Pasted input | the prompt is over 6,000 characters (diff, plan and review go by path) |

There is no round lock: a demand iterates until it is done.

## Lean context

Coming back after an hour idle rewrites the whole conversation into the cache, at full price. So at the end of each
orchestrator turn the mod schedules a compaction **50 minutes** later (before the cache expires):

- Any message before then cancels it; a new one is scheduled at the end of the next turn.
- When the time comes, it measures the context again and compacts only with **100k tokens or more**; the summary keeps
  what is with you (the question, the approval), the next action, the running agents and unrecorded decisions, and the
  demand state comes back right after.
- The limits are `IDLE_MS` and `IDLE_MIN` in `hooks/aidw.ts`.

## Orchestrator economy

The most expensive rule to break is the orchestrator reading code in its own chat, because that text stays in the
context until the end of the demand. When the orchestrator reads a code file outside the AiDW folder, the mod counts it
and adds a note to the result to delegate to the explorer. A one-off premise check (skill `verify-premise`) is fine.

## Secret filter

Every tool result of the orchestrator and the agents goes through the filter before it becomes a conversation line,
including error results (a connection string in an exception). It masks the value and keeps only the name and length,
as the secrets policy asks: `Password=«secret hidden: Password, 5 characters»`.

- **Catches:** connection-string passwords (`Password`, `Pwd`, `AccountKey`, `SharedAccessKey`, `Client Secret`); JSON
  fields for password, secret, token, `apiKey`, `connectionString`; environment variables `*_TOKEN`, `*_SECRET`,
  `*_PASSWORD`, `*_API_KEY`, `*_PAT`; `Bearer` tokens, JWTs, PEM private keys and known API key formats.
- **Does not catch:** placeholders (`${VAR}`, `%VAR%`, `<password>`) and code.
- **Status:** how many secrets were hidden. The filter is idempotent.

## Notes in the prompt

In your message, `[[note-name]]` brings the text of that knowledge base note along with the message (up to three notes
per message).

## State after compaction

When the orchestrator's conversation is compacted, the mod rereads the demand from disk and adds a summary of the state
to your **first message after the compaction**, once: the step, the folder and worktrees, the loop round and open
findings, and a reminder to reread the skill and the artifacts.

## Configuration

`install` writes this machine's AiDW root into the plugin. Two fields can be changed in Claude Code's plugin settings:
`aidwRoot` (the folder of `aidw.py`) and `python` (the Python command, default `python`).

## Developing a mod

- **Source:** `mods/aidw-mods/` is the plugin and the source of truth. `install` copies everything but `tests/` into
  `.aidw/marketplace/plugins/aidw-mods/`, where Claude Code reads it. After changing the source: `python aidw.py install`
  and `/reload-plugins` (or a new chat).

| File | Content |
|---|---|
| `hooks/register.tsx` | **the only file that touches the engine (`$`)**: hooks, disk reads, `git`, `aidw.py record`. `$` does not cross an `import` |
| `hooks/views.tsx` | the strip and panel screens; they get the element table and navigation actions, never `$` |
| `hooks/snapshot.ts` | the demand snapshot (`wanted` says what to read, `buildSnapshot` builds it) |
| `hooks/artifacts.ts` | the artifact parsers (findings, triage, criteria, script, survey…) |
| `hooks/guards.ts` | the delegation locks |
| `hooks/secrets.ts` | the secret filter |
| `hooks/i18n.ts` | every user-visible string, in English and Portuguese |
| `hooks/names.ts` | the new and old (Portuguese) artifact names the mod accepts |
| `hooks/aidw.ts` | delegation prompt, `metrics.md`, `orchestrator-metrics.md`, `routing.toml`, context limits |
| `types/index.d.ts` | the state contract (`PluginState['aidw-mods']`) and the snapshot types |

- **A new mod** goes in as more hooks in `register.tsx`; pure logic goes in its own file, with a test. Mods turn on only
  in orchestrator mode (the `active` atom).
- **Check:**

```powershell
claude plugin validate mods/aidw-mods
claude plugin test mods/aidw-mods
```

The first reads the manifest and the module as the engine will. The second runs `tests/*.test.ts` against the engine,
with sample demands for each use.
