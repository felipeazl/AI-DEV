---
name: to-spec
description: Turn a request into a persistent specification that becomes the source of truth for the task, then break it into self-contained tickets. Use at the start of any feature, bugfix or refactor, and again to cut the tickets once the plan is approved.
---

# to-spec

1. Restate the request in one sentence.
2. **Check existing work first:** work item state, child tasks, linked PRs, attachments, and
   branches. If work already exists, ask whether this is a continuation, a fix or a redo.
   Read the work item's **comments** and its **linked items** (parent, related, predecessors):
   decisions often live only there and override the description.
3. Inspect the repository through a cheap exploration subagent (e.g. `Explore`), asking for
   the relevant files with `file:line` pointers. The *Systems* section gives repo, stack and
   commands — do not re-derive them.
4. **Inspect the dependencies:** if the change consumes another system (API, library, shared
   model), open that side too — contract, enums, events, error responses. The *Systems* section
   lists where each dependency lives.
5. Describe current behavior from the code, not from assumptions.
6. Run the checklists below and write the spec to `<state dir>/specs/<slug>.md` (or the location
   the active context defines, e.g. an execution plan attached to a work item).
7. **Open questions:** if there is a real doubt or more than one valid path, list them with
   options and your recommendation — that is the only reason to stop for the user. Otherwise
   the spec is final and the flow continues.

## Checklists (every spec)

- [ ] **Every value of every enum/state** the flow handles — including `0`/default/unknown —
      has a defined behavior. Say explicitly what happens to each one.
- [ ] **Loops, polling, retries, timers:** maximum time, maximum attempts, cancellation, what
      happens to a late response (e.g. after the context changed), and who guarantees it stops
      on every exit path (normal, user cancel, exception).
- [ ] **UI responsiveness:** no blocking call on the UI thread; if an existing API is
      synchronous, say how the caller avoids blocking.
- [ ] **Errors:** each external call — what happens on timeout, error status, empty response.
- [ ] **Out of scope** is justified: if something is excluded, say why it cannot or should not
      be solved within this change.
- [ ] Every acceptance criterion is verifiable by QA.

## Template

```markdown
# <Title> — v<N>

Nível: <level> — <why> (orchestrator's model table; decides model/effort of every agent)
(from v2 on: what changed since the previous version)

## Decisions taken
| # | Topic | Decision | Who / when |

## Premises verified
| Premise (card) | What the code/card showed (`file:line`) | Status ✅/⚠️ |

## Objective

## Current behavior

## Desired behavior

## Dependencies inspected

## Constraints

## Acceptance criteria
- [ ] ...

## Checklists
(enum/state values · limits · UI thread · errors)

## Out of scope (and why)

## Branch and PR (base, target, when the PR opens; dependency on unmerged work)

## Technical considerations

## Risks

## Open questions (only if any)
```

Finish with:

```json
{"state": "spec_ready | plan_has_open_questions", "spec": "<path>", "level": "<level>", "open_questions": []}
```

## Tickets (after the plan is approved)

1. Every ticket traces back to at least one acceptance criterion.
2. Split by independent units of work; a ticket touches a small, known set of files.
3. A ticket must be executable by an agent that never saw the conversation: goal, files in scope
   with `file:line`, acceptance criteria, out of scope, build/test command from *Systems*.
4. Order by dependency; tickets on the same files run in sequence.
5. Write them where the active context says (e.g. Tasks in Azure DevOps + `tarefa-<agente>-<assunto>.md`);
   otherwise `<state dir>/tickets/<PREFIX>-<NNN>-<slug>.md`.

```markdown
# <PREFIX>-<NNN> <Title>
- Spec: <path> · Agent: coder | api-db | qa | documenter · Depends on: <ids or none>
- Risk: low | medium | high · Level: <only when it differs from the demand's, and why>
## Goal
## Scope (files / modules, with file:line)
## Acceptance criteria
- [ ] ...
## Out of scope
```

Finish with `{"state": "tickets_ready", "tickets": ["<path>", "..."]}`.
