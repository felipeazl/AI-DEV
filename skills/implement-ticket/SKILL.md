---
name: implement-ticket
description: Implement a single ticket end to end — understand, plan, implement, test, lint, typecheck and report the diff. Use when the Coder receives a ticket.
---

# implement-ticket

1. **Understand** — read the ticket, the spec and the files in scope. If an acceptance
   criterion is unclear, return `status: "blocked"` with the question.
2. **Plan** — list the files you will change and why. Keep the plan inside the ticket scope.
3. **Implement** — follow the project's existing conventions.
4. **Test** — add or update tests for each acceptance criterion; run them.
5. **Lint** and **typecheck** — use the project's commands (see `testing`).
6. **Diff** — review your own diff; remove unrelated changes.
7. Return the Coder OUTPUT JSON defined in the Coder's agent definition.

When a step fails, use `debug` before retrying. Do not loop more than the configured
`max_retries`; report `status: "failed"` instead.
