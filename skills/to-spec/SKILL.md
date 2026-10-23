---
name: to-spec
description: Turn a request into a persistent, self-contained specification (spec-driven development) that becomes the source of truth for the task and the coder's own task, with its deliveries in the same pass. Use at the start of any feature, bugfix or refactor, and again to adjust the plan.
---

# to-spec

1. Restate the request in one sentence.
2. **Check existing work first:** work item state, child tasks, linked PRs, attachments, and
   branches. If work already exists, ask whether this is a continuation, a fix or a redo (a sub-agent
   finds this in the demand summary and puts any doubt in its open questions).
   Read the work item's **comments** and its **linked items** (parent, related, predecessors):
   decisions often live only there and override the description.
3. Start from the exploration reports in the demand folder (`exploracao-*.md`); read code only to
   verify a premise or close a small gap. With no report and a large unknown area, ask for an
   exploration (the explorer agent, or the cheapest exploration available) instead of sweeping the
   code. The *Systems* section gives repo, stack and commands — do not re-derive them.
4. **Inspect the dependencies:** if the change consumes another system (API, library, shared
   model), open that side too — contract, enums, events, error responses. The *Systems* section
   lists where each dependency lives.
5. Describe current behavior from the code, not from assumptions.
6. Run the checklists below and write the spec to `<state dir>/specs/<slug>.md` (or the location
   the active context defines, e.g. `plano-<id>.md` in the demand folder).
7. **Open questions:** if there is a real doubt or more than one valid path, list them with
   options and your recommendation — that is the only reason to stop for the user. Otherwise
   the spec is final and goes to the user for approval.

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

(from v2 on: what changed since the previous version)

## Decisions taken
| # | Topic | Decision | Who / when |

## Premises verified
| Premise (card) | What the code/card showed (`file:line`) | Status ✅/⚠️ |

## Objective

## Current behavior

## Desired behavior

## Acceptance criteria
- CA1: <the card's text>
- CA2 (plano): <added by a decision or by the code, and why>

## Business rules
- RN1: <the card's text, or a rule the change must keep or introduce, with its source>

## Dependencies inspected

## Checklists
(enum/state values · limits · UI thread · errors)

## Deliveries
### E1 — <system>: <what it delivers, plain words>
- Covers: CA1, RN2 · Depends on: — · Worktree: <path> · Build: `<ready command>`
- Files: `path/File.cs:42` — <what changes>; `path/Other.cs` (new) — <what it holds>
- Tests: <only internal steps an end-to-end test would not show> | none
- Docs: <README/ARCHITECTURE/API doc of this repository the change makes stale> | none

## Out of scope (and why)

## Branch and PR (base, target; dependency on unmerged work)

## Risks

## Open questions (only if any)
```

## Deliveries

1. Every delivery traces back to at least one acceptance criterion (`CA1`) and names the rules (`RN1`) it touches.
2. One delivery per cohesive technical change — usually one system or repository, a known set of files that one coder
   finishes in one pass. Each delivery becomes a work item, so never split it into tiny ones (one per file, method or
   criterion, or a separate one for comments, tests or docs of the same code). Split only parts that are independent
   (another system, or one that must be done first).
3. A delivery must be executable by a coder that never saw the conversation: files with `file:line` and what changes,
   the criteria, the worktree and the build/test command from *Systems*. If the coder would have to search for where
   something lives, the delivery is not finished.
4. Order by dependency; deliveries on the same files run in sequence.

Finish with:

```json
{"state": "plan_ready | plan_has_open_questions", "spec": "<path>", "deliveries": ["E1"], "open_questions": []}
```
