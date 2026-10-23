---
name: code-review
description: Review a diff against its spec in one pass — quality, real behavior defects (with a failure scenario) and exploitable vulnerabilities (with an attack path) — and return structured findings with stable IDs and a keep/discard recommendation. Use when the Reviewer receives SPEC + DIFF + BUILD/TEST RESULTS.
---

# code-review

Required input: SPEC (the plan), DIFF (usually a file), BUILD/TEST RESULTS. Refuse without them. In a review of
someone else's pull request, the work item summary is the SPEC and the PR is the TICKET (the Reviewer's definition,
*PR review*).

One pass covers three categories. Few findings, all real: a false positive costs a fix round and the user's time.

## Check, in order

1. **Spec fidelity** — does the diff meet every acceptance criterion and business rule of the delivery? Anything out
   of scope?
2. **Bugs** (category `bug`) — list the behaviors that changed (one line each) and open the full functions around each
   hunk: bugs live in the lines the diff did not touch. Attack each behavior with the probes below; stop at the first
   that yields a **traceable failure** — the path `file:line` → `file:line` from the trigger to the wrong result. If
   you cannot trace it, it is a doubt, not a finding.
   - **Values:** null/empty, 0/negative/max, **every enum/state value including default and unknown**, duplicates,
     culture/encoding (decimal separator, accents, code page).
   - **State:** called twice or out of order, partial failure midway, stale cache, flags left set on an early
     `return`.
   - **Time and concurrency:** UI thread blocked, re-entrancy (double click), timer × user action, late async response
     after the context changed, loops/polling without a bound, timeouts, cancellation.
   - **Exits:** every exit path (normal, cancel, exception, early return) restores what it changed (`finally`,
     rollback, `saving = false`, resources disposed, UI re-enabled).
   - **Integration:** the other side's contract — error status, empty body, enum value the caller does not know;
     retries that duplicate a side effect.
   - **Data:** SQL without the key in `WHERE`, transaction boundaries, rounding, truncation, `FirstOrDefault` → null
     used as if present.
3. **Security** (category `seguranca`) — only what the change touches: follow each untrusted input (endpoint, SOAP
   method, UI field, file, process argument) to the sinks it reaches. A finding needs an **attack path**: who
   (anonymous, authenticated user, another partner, local user), the input, and what they gain. Check injection (SQL
   by concatenation, command arguments, path traversal, XSS, unsafe deserialization), authentication (token
   validation, OTP brute force/reuse), authorization (who may do it on which record — IDOR), secrets (hardcoded, in
   logs, responses, URLs or config), crypto (algorithm, IV reuse, certificate validation off), personal data beyond
   need in logs/responses/errors, server-side input limits, new packages with known vulnerabilities. Generic advice
   without an attack path is noise.
4. **Tests** — is each internal step an end-to-end check would miss (a calculation, mapping, state transition,
   retry/timer, data never shown) covered by a test? A missing one is `IMPORTANTE`. A test that only repeats what the
   end-to-end check plainly shows is a `SUGESTAO` to remove it. Never ask for tests just to cover every criterion: QA
   verifies those end to end.
5. **Maintainability** (category `qualidade`) — naming, duplication, consistency with the team's standards and the
   project's conventions.

## Rules

- **Stable IDs:** `R<round>-<nn>` (e.g. `R1-03`). In later rounds keep the original IDs; new findings continue the
  numbering. Never renumber.
- **Smallest fix in scope first:** before saying a problem "can only be fixed elsewhere", propose the smallest fix
  inside the files in scope (e.g. at the caller). Recommend moving it out of scope only when no in-scope fix exists —
  and say why.
- **Evidence for coverage claims:** do not write "covers every case" or "stops on any close" without naming the code
  path for each case, including exceptions.
- **No speculation as fact:** uncertain findings go to `DOUBTS` with a concrete question.
- **Pre-existing:** a problem the change did not introduce or worsen is marked "não é regressão desta mudança"; it is a
  finding only when the change touches it or makes it worse.
- **Recommendation:** every finding says `manter` or `descartar` and why, in one line — the user and the orchestrator
  decide each one with it. Recommend `descartar` honestly (low confidence, pre-existing and untouched, cost beyond the
  benefit).

## Severity

- `CRITICO` — wrong behavior, security issue, data loss, crash/hang, or an acceptance criterion not met. Blocks.
- `IMPORTANTE` — likely bug in a realistic case, exploitable with preconditions, significant maintainability problem,
  or a **violation of the team's documented standards** (guideline, project conventions) even without a bug. Blocks.
- `SUGESTAO` — improvement the standards do not require, hardening, unlikely edge with a cheap guard. Does not block.
- `ELOGIO` — something done well.

## Output

One entry per finding, in the Reviewer OUTPUT defined in the Reviewer's agent definition (the only format — `state`,
`findings`, `doubts`):

```json
{"id": "R1-01", "severity": "CRITICO", "category": "qualidade | bug | seguranca", "status": "open", "file": "path",
 "line": 120, "problem": "...", "why": "...", "fix": "...", "fix_in_scope": true, "confidence": "high | medium",
 "recommendation": "manter | descartar", "recommendation_why": "..."}
```

Every round, write the full review (all findings with status, and the doubts) as Markdown to the path the task gives
(default `<state dir>/reviews/<ticket>-r<N>.md`), then return the OUTPUT JSON with the complete findings list in your
final message. If the active context defines a review template, use it. Otherwise the Markdown has: identification
(scope, branch, round); findings (category / what / why it matters — the failure scenario or the attack path / suggested
fix / recommendation, with `file:line`); doubts; **points checked without findings** (one line each, including the
probes and security categories you ran); risk notes; and a summary table by severity with whether the cycle can close.

Either way, three things the AiDW panel reads (Claude Code):
- The heading of each finding carries its category: `### R1-01 — IMPORTANTE — bug — <file>:<line>`.
- A finding whose fix changes code carries `**Antes:**` and `**Depois:**`, each followed by a fenced code block with
  the few lines that change, exact text (today's lines, then the same lines fixed).
- `**Recomendação:** manter | descartar — <why, one line>` under each finding; a doubt lists its options as
  `- (a) …`, `- (b) …` and ends with `**Recomendação:** <option and why, one line>`.

**Round ≥ 2:** you get the previous review, the user's decisions (which findings were kept) and the diff of the fixes.
Check each kept finding (`fixed` / `not_fixed`, with evidence), then look for regressions in the changed lines — a fix
can open a new failure scenario or attack path. Open the full files only where the fix needs context. Discarded
findings stay discarded.
