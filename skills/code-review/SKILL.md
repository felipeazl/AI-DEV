---
name: code-review
description: Review a diff against its spec and ticket and return structured findings with stable IDs. Use when the Reviewer receives SPEC + TICKET + DIFF + TEST/BUILD RESULTS.
---

# code-review

Required input: SPEC, TICKET, DIFF (usually a file), TEST/BUILD RESULTS. Refuse without them.

Check, in order:

1. **Spec fidelity** — does the diff meet every acceptance criterion? Anything out of scope?
2. **Correctness** — logic errors, edge cases, **every enum/state value including the default**,
   error handling, concurrency, resource leaks, **every exit path** (normal, cancel, exception).
3. **Security** — secrets, injection, unsafe input handling, permission changes.
4. **Tests** — do the tests actually exercise the acceptance criteria?
5. **Maintainability** — naming, duplication, consistency with project conventions.

## Rules

- **Stable IDs:** `R<round>-<nn>` (e.g. `R1-03`). In later rounds keep the original IDs; new
  findings continue the numbering. Never renumber.
- **Smallest fix in scope first:** before saying a problem "can only be fixed elsewhere",
  propose the smallest fix inside the files in scope (e.g. at the caller). Recommend moving it
  out of scope only when no in-scope fix exists — and say why.
- **Evidence for coverage claims:** do not write "covers every case" or "stops on any close"
  without naming the code path for each case, including exceptions.
- **No speculation as fact:** uncertain findings go to `DOUBTS` with a concrete question.

## Severity

- `CRITICO` — wrong behavior, security issue, or an acceptance criterion not met. Blocks.
- `IMPORTANTE` — likely bug or significant maintainability problem. Blocks.
- `SUGESTAO` — improvement. Does not block.
- `ELOGIO` — something done well.

## Output (one entry per finding)

```json
{"id": "R1-01", "severity": "CRITICO", "file": "path", "line": 120,
 "problem": "...", "why": "...", "fix": "...",
 "fix_in_scope": true, "confidence": "high | medium"}
```

`fix_in_scope` and `confidence` let the orchestrator triage without the user. Save the result
to the location the orchestrator gives (default `<state dir>/reviews/<ticket>-r<N>.json`) and
return the Reviewer OUTPUT defined in the Reviewer's agent definition.
