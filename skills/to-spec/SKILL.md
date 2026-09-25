---
name: to-spec
description: Turn a request into a persistent specification that becomes the source of truth for the task. Use at the start of any feature, bugfix or refactor, before creating tickets.
---

# to-spec

1. Restate the request in one sentence.
2. **Check existing work first:** work item state, child tasks, linked PRs, attachments, and
   branches. If work already exists, ask whether this is a continuation, a fix or a redo.
3. Inspect the repository through a cheap exploration subagent (e.g. `Explore`), asking for
   the relevant files with `file:line` pointers. Use `codebase-context` if no context doc exists.
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
# <Title>

Nível: <level> — <why> (orchestrator's model table; decides model/effort of every agent)

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

## Technical considerations

## Risks

## Open questions (only if any)
```

Finish with:

```json
{"state": "spec_ready | plan_has_open_questions", "spec": "<path>", "level": "<level>", "open_questions": []}
```
