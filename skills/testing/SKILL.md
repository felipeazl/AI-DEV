---
name: testing
description: Run a project's validation suite in a standard way — unit, integration, lint, typecheck, build and targeted tests. Use whenever code must be validated.
---

# testing

1. Find the project's commands (package.json scripts, Makefile, CI config, README, or the
   `codebase-context` doc). Never invent commands.
2. Run, in order, whatever exists: typecheck → lint → unit → integration → build.
3. For a single ticket, run targeted tests first, then the full suite.
4. Report each check as `passed`, `failed` or `skipped` (with the reason).
5. For failures include the command, the failing test names and the key error lines.
