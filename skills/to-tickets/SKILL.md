---
name: to-tickets
description: Break an approved spec into small, self-contained tickets that an agent can execute without the original conversation. Use right after to-spec.
---

# to-tickets

1. Read the spec. Every ticket must trace back to at least one acceptance criterion.
2. Split by independent units of work. A ticket should touch a small, known set of files.
3. A ticket must be executable by an agent that has never seen the conversation.
4. Order tickets by dependency. Tests and documentation may be their own tickets.
5. Write each ticket to `<state dir>/tickets/<PREFIX>-<NNN>-<slug>.md`.
6. If the active context defines where tickets live (e.g. Tasks in Azure DevOps), follow it.

## Template

```markdown
# <PREFIX>-<NNN> <Title>

- Spec: <state dir>/specs/<slug>.md
- Agent: coder | api-db | qa | documenter
- Depends on: <ticket ids or none>
- Risk: low | medium | high

## Goal

## Scope (files / modules)

## Acceptance criteria
- [ ] ...

## Out of scope
```

Finish with:

```json
{"status": "tickets_ready", "tickets": ["<state dir>/tickets/WS-001-client-reconnect.md"]}
```
