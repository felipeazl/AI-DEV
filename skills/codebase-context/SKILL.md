---
name: codebase-context
description: Gather a project's architecture, stack, conventions, aliases, patterns, dependencies and constraints into a reusable context doc. Use before the first spec on a project, or when the context doc is stale.
---

# codebase-context

Write `<state dir>/specs/_context-<project>.md` with:

- **Stack** — languages, frameworks, versions, package manager.
- **Architecture** — main modules and how they depend on each other.
- **Conventions** — naming, folder layout, error handling, logging, tests.
- **Aliases** — import aliases and path mappings.
- **Commands** — install, build, test, lint, typecheck, run.
- **Dependencies** — key external services and libraries.
- **Constraints** — things that must not change, known pitfalls.

Base every item on files you read; cite the file. Keep it under two pages.
