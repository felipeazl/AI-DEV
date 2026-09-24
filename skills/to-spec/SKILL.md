---
name: to-spec
description: Turn a request into a persistent specification that becomes the source of truth for the task. Use at the start of any feature, bugfix or refactor, before creating tickets.
---

# to-spec

1. Restate the request in one sentence. If the goal is ambiguous, ask before writing.
2. Inspect the repository (use `codebase-context` if no context doc exists yet).
3. Describe current behavior from the code, not from assumptions.
4. Write the spec to `<state dir>/specs/<slug>.md` using the template below.
   Update the existing file if one already exists for this task.
5. Every acceptance criterion must be verifiable by QA.
6. If the active context defines its own spec format or location (e.g. an execution plan
   attached to a work item), follow the context instead of the template below.

## Template

```markdown
# <Title>

## Objective

## Current behavior

## Desired behavior

## Constraints

## Acceptance criteria
- [ ] ...

## Out of scope

## Technical considerations

## Risks
```

Finish with:

```json
{"status": "spec_ready", "spec": "<state dir>/specs/<slug>.md", "open_questions": []}
```
