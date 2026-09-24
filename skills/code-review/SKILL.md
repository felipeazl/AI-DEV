---
name: code-review
description: Review a diff against its spec and ticket and return structured findings. Use when the Reviewer receives SPEC + TICKET + DIFF + TEST RESULTS.
---

# code-review

Required input: SPEC, TICKET, DIFF, TEST RESULTS. Refuse to review without them.

Check, in order:

1. **Spec fidelity** — does the diff meet every acceptance criterion of the ticket?
   Does it do anything out of scope?
2. **Correctness** — logic errors, edge cases, error handling, concurrency, resource leaks.
3. **Security** — secrets, injection, unsafe input handling, permission changes.
4. **Tests** — do the tests actually exercise the acceptance criteria?
5. **Maintainability** — naming, duplication, consistency with project conventions.

Severity:

- `high` — wrong behavior, security issue, or a spec criterion not met. Blocks approval.
- `medium` — likely bug or significant maintainability problem. Blocks approval.
- `low` — suggestion. Does not block.

Save the result to `<state dir>/reviews/<ticket>.json` and return the Reviewer
OUTPUT JSON defined in the Reviewer's agent definition.
