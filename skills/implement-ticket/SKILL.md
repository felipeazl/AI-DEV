---
name: implement-ticket
description: Implement a single ticket end to end — understand, plan, implement, test, lint, typecheck and report the diff. Use when the Coder receives a ticket.
---

# implement-ticket

1. **Understand** — read the ticket, the spec and the files in scope (start from the
   `file:line` pointers the ticket gives; don't re-explore the whole repo). If an acceptance
   criterion is unclear or the plan is wrong for the code, return `status: "blocked"` with the
   question — don't guess and don't re-plan.
2. **Plan** — list the files you will change and why. Keep the plan inside the ticket scope.
3. **Implement** — follow the project's existing conventions.
4. **Test** — add or update tests for each acceptance criterion; run them.
5. **Build, lint, typecheck** — use the **exact commands** the ticket or the *Systems* section
   gives (see `testing`). Don't search for other build tools.
6. **Diff** — review your own diff; remove unrelated changes.
7. Return the Coder OUTPUT JSON defined in the Coder's agent definition.

- **Environment blocked** (missing tool, package, permission, network): report the exact
  command and error and stop. Don't try workarounds.
- When a step fails in your code, use `debug` before retrying. Do not loop more than the
  configured `max_retries`; report `status: "failed"` instead.
