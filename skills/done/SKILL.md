---
name: done
description: Closes the task: records in the active context what the demand discovered that is worth keeping for the next ones — in the knowledge base (the demand's note and the system, integration, concept and decision notes it touched, linked without duplicating) and, for build and environment, in context.toml —, validates, reinstalls the AiDW and commits and pushes the context's repository. Only when the user calls it.
aidw: admin
disable-model-invocation: true
---

# done

`aidw.py` lives in `{{root}}` (the AiDW root). Run the commands exactly as `python "{{root}}/aidw.py" ...`, with the
quotes: that is the form the permission rules allow.

**Language:** talk to the user in the AiDW UI language (`[ui] language`, shown by `python "{{root}}/aidw.py" show`);
write the knowledge notes and the context content in the context's language (`language` in its `context.toml`; when
absent, the UI language).

The user calls this skill when a task is finished. **Calling it is the authorization** to commit and push the
**context's** repository (and only that one) on the current branch, even if it is `main`: it is the user's private
knowledge repository, not product code, by their decision. No commit, push or merge in the product repositories. The
user's request, if any, is in the message that called this skill.

## 1. What the task was

- **Active context:** `python "{{root}}/aidw.py" status --json` → `context.name`. The folder is
  `{{root}}/contexts/<name>`. No active context: say there is nowhere to record and stop.
- **Demand:** this session's, or the one in the request. If it is not clear, use `project detect --json` (the
  `demand` field) and `demand list --active --json`. A task without a demand (maintenance, investigation) also counts:
  use the conversation.
- **Knowledge base:** `status --json` does not show it; read `[knowledge] dir` in the context's `context.toml` (the
  folder is `<context>/<dir>`; conventions in its `README.md`). Without `[knowledge]`, everything goes to
  `context.toml` and `reference/`, as in the table of section 2.
- **Sources, cheapest first:**
  1. `python "{{root}}/aidw.py" kb collect <id>` — writes `collect-<id>.md` in the demand folder with what the demand
     already set aside for the base: the *Knowledge base* sections of the agents' reports, `learnings-<id>.md` (what
     was born in the chat), the notes the summary cited and the plan's decisions. **Start from it** and this
     conversation;
  2. a whole artifact (`exploration-*`, `plan-*`, `review-*`, `survey-*`) only when a fact from the collect needs more
     context;
  3. the worktree diff (`git -C <worktree> diff <base>...HEAD --stat`, and the diff of only the parts that matter).
- **Existing notes:** `kb show <note> --brief` to read the note without the list of who cites it; the full version
  only when you need the backlinks.

## 2. What is worth keeping

Keep only what passes **all** the criteria:
- **Useful for the next demand:** a fact about the system or the environment, not a detail of this delivery.
- **Verified:** a command that ran, `file:line`, build output. A hypothesis does not go in.
- **New, or corrects what is there:** before writing, look for where the fact already lives (`kb search <words>`,
  `kb show <note>`) and update that note; do not create another. What the base said and turned out wrong is
  corrected in the note itself, with the new source.
- **A fact, not a rule:** the base describes how the code **is** (including legacy that does not follow the standard);
  how it **should** be belongs to the team's guide and `policies/`. A legacy pattern goes into the note as a fact
  ("system-a uses ADO.NET with a procedure in X"), never as a recommendation; team conventions and work rules go to
  `shared/` or `policies/`.
- **Short:** one line per fact, with the source when it is not obvious. The *Systems* section of `context.toml` goes
  into the prompt of every message: only what every agent always needs goes there (build, test, environment block).
- **Never** a secret, token, password, connection string, PIN, personal data or customer data. This also applies to
  the card's content: name, e-mail and national id numbers do not go in.

For each fact, the right place:

| Fact | Where |
|---|---|
| Repository, stack, build, test or dependency of a system | `context.toml`, `[systems.<key>]` (`repos`, `stack`, `build`, `test`, `depends_on`) |
| Environment block and how to unblock it (clone, restore, flag, build order) | the system's `notes`, with the date `(checked YYYY-MM-DD)` |
| A neighboring folder the code reaches by a relative path (HintPath `..\X`) | the system's `worktree_link` |
| How the system works, where each thing lives, a trap in the code | the system's note (`sistemas/<key>.md`) or the component's |
| A contract between two sides (endpoint, SOAP, enum, event, shared configuration key, external service) | a note in `integracoes/`, linked to both systems |
| A business rule, a domain term | a note in `conceitos/` |
| How to operate the environment (host, authentication, database, API recipe) | a note in `ambiente/` |
| A durable decision of the PO, the Tech Lead or the user (with author and date) | a note in `decisoes/`; if it became a work rule, `policies/` or `shared/` |
| What the demand was | the demand's note, `demandas/<id>.md` (section 2.1) |
| A procedure that will repeat | propose a context skill (`skills/<name>/SKILL.md`) and ask before creating it |
| An improvement to the AiDW itself (`aidw.py`, generic agents and skills) | do not edit: list it as a suggestion in the report |

Without a knowledge base in the context, the note rows become the system's `notes` or the topic's `reference/` file.

### 2.1 The demand's note and the links

Every closed demand gets `demandas/<id>.md` — development, PR review or survey —, short (up to ~20 lines), in the
format of the base's `README.md`: what the card asked (one line), what changed and where (`[[system]]`, main files),
the decisions, what was learned with the link to the note that received each fact, the PR. PR review: what the PR did,
the findings that matter for the system and whether the PR was approved. Survey: the estimate and the open doubts.
Investigation (`inv-*`): the symptom, the cause (proven or not) and the item drafted or created. Card (`card-*`): the
item created and its source. A question (`ask-*`) and a knowledge review (`kb-review-*`) get **no** demand note: their
facts go to the notes they belong to (the review already edited them; check only that `kb check` is clean).

- **Link, don't copy:** the demand's note points to the notes it touched; each updated note gets the source
  (`fontes:` with the demand id) and `atualizado:` with the date. A new fact goes in one note only; the others cite
  it with `[[link]]`.
- **A new note** only when the fact does not fit an existing one: right type and folder, unique name, `resumo`,
  `fontes`, `palavras-chave` (technical note) and at least one link from or to another note.
- **Keywords:** when a new fact brings an identifier someone will search for (class, config key, route, table, enum),
  add it to the note's `palavras-chave`; when splitting a large note, each part takes its own.

### 2.2 Calibration of the survey

When the collect has the section *Effort (calibration of the survey)* (a demand that was surveyed and then
developed), add **one row** to the *Calibration* table of the context's estimation rubric (the reference
*regua-estimativa*, or the context's rubric of another name; none → skip): the survey's estimate, the card's story
points at the planning when the summary or the card has them, the real numbers of the collect (days to the PR,
agents' and orchestrator's hours, rounds), what happened after the PR, and one line on what explained the difference.
Only the collect's numbers and what this conversation said — never ask the user to fill in hours. A row of this demand
that is already there is updated, not repeated. When the rows show the same drift for several similar cards, say so in
the report (a proposal to adjust the rubric's ranges or factor), without changing them yourself.

## 3. Record and validate

1. Edit the context's files. In `context.toml`, keep the comments and the style of the neighboring entries.
2. If the context changed nothing, say so and skip to section 5.
3. With a knowledge base: `python "{{root}}/aidw.py" kb index` (regenerates the map) and
   `python "{{root}}/aidw.py" kb check` — fix broken links, repeated names, frontmatter and secrets; an orphan note
   you created gets a link. In the warnings about the notes you touched: one that passed 150 lines, split into linked
   notes (a part becomes an integration, component or environment note); one unchecked for more than 6 months that
   this demand checked, update its `atualizado`. The others, only list in the report.
4. Run `python "{{root}}/aidw.py" context check <name>`. On error, fix and run again. Do not commit a broken context.
5. Regenerate and reinstall:
   - `python "{{root}}/aidw.py" apply`;
   - `python "{{root}}/aidw.py" status --json`: with `claude.installed`, run `install`; with `codex.installed`, run
     `install --provider codex`.

## 4. Commit and push the context

- `git -C "<context folder>" status --short`, then `git add` **only the files you changed** in this step. Never add the
  demands' state folder (the context's `state_dir`, e.g. `<context>/demandas/`), nor a file you did not edit. The
  base's notes (including `<base>/demandas/<id>.md`) go in.
- Commit with a short message: what was learned and in which demand. End it with the session's co-author line.
- `git -C "<context folder>" push` on the current branch. If it fails (no remote, no permission, protected branch that
  requires a PR, branch behind the remote), show the message and stop. Do not force, do not rebase, do not create
  another branch to get around it: the user decides.

## 5. Close the demand

- With a demand: `python "{{root}}/aidw.py" demand set <id> --status done --note "<one line of what was delivered>"`.
- Show the worktree's situation (`worktree inspect <id>`). If it is clean and published, suggest
  `worktree remove <id>`. Do not remove it unless the user asks: the branch or the PR may still be under review.
- This skill also ends the orchestrator mode of this session, like `exit`: last, run
  `python "{{root}}/aidw.py" session unbind` (in the terminal, the hook does not receive `/aidw:done`).

## 6. Report

- What went into the context, file by file, one line per fact; with a knowledge base, the demand's note and the notes
  it touched (the user sees the graph by opening the context folder in Obsidian).
- What you left out and why: not verified, only about this demand, or sensitive.
- The commit (hash) and the push result.
- The suggestions for the AiDW, if any.
- That the plugin was reinstalled and that the new rules apply in a **new chat**.
