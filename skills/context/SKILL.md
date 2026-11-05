---
name: context
description: Manages the AiDW work contexts (contexts/<name>, each one a private Git repository) — `list` shows the contexts and which one is active; `use <name>` validates, activates and regenerates the environment and the aidw plugin; `create` builds a new context from an analysis of the repositories and at least 10 questions to the user. Use when the user asks to list, switch, activate or create a context, or calls /context.
aidw: admin
---

# context

`aidw.py` lives in `{{root}}` (the AiDW root). The user's request (may be empty): $ARGUMENTS

**Language:** talk to the user in the AiDW UI language (`[ui] language`, shown by `python "{{root}}/aidw.py" show`);
write a context's content in that context's language (`language` in its `context.toml`; when absent, the UI language).

## Which subcommand

By the first word of the request (case-insensitive; the same words in the user's language also count, e.g. `listar`,
`usar`, `criar`):

| Request | Subcommand | Procedure (read the whole file and follow it) |
|---|---|---|
| empty, `list`, "show the contexts" | `list` | `references/list.md` |
| `use <name>`, "switch to", "activate" | `use` | `references/use.md` |
| `create`, "build a context" | `create` | `references/create.md` |

The files are in this skill's folder (next to this `SKILL.md`). With no clear subcommand, run `list` and finish by
saying that `use <name>` switches the active context and `create` builds a new one.
