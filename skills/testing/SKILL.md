---
name: testing
description: Run a project's validation suite in a standard way — unit, integration, lint, typecheck, build and targeted tests. Use whenever code must be validated.
---

# testing

1. **Use the ready-made commands first:** the ticket or the *Systems* section. Only if there
   are none, find them in package.json scripts, Makefile, CI config, README or the
   `codebase-context` doc. Never invent commands.
2. **Keep output small:** run with quiet/minimal verbosity and errors-only summaries (e.g.
   MSBuild `/v:minimal '/clp:ErrorsOnly;Summary'`, `dotnet test -v q`, `npm test -- --silent`).
   If a command prints thousands of warnings, filter to the lines of the files you changed —
   reading all of it wastes the context.
3. Run, in order, whatever exists: typecheck → lint → unit → integration → build.
4. For a single ticket, run targeted tests first, then the full suite.
5. Report each check as `passed`, `failed` or `skipped` (with the reason).
6. For failures include the command, the failing test names and the key error lines.
7. When asked for "new warnings", build the base and the change and compare only the
   warnings in the changed files.
