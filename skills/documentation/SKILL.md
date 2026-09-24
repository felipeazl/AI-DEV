---
name: documentation
description: Generate or update documentation (README, API docs, changelog, architecture notes, JSDoc, OpenAPI) from an approved diff. Use after review approval.
---

# documentation

1. Read the spec, the approved tickets and the final diff.
2. List what changed for users (behavior, API, config) and for maintainers (architecture).
3. Update only the docs affected by the diff, following the project's existing style.
4. Add a changelog entry if the project keeps one.
5. Never document behavior that is not in the diff.
