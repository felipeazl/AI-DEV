---
name: bug-hunt
description: Hunt for real behavior defects in a diff or code area, or find the root cause of a reported bug, backing every finding with a concrete failure scenario. Use when the Bug Hunter receives a hunt or root-cause task.
---

# bug-hunt

Goal: few findings, all real. A false positive costs a fix round; a missed bug costs production.

## hunt (diff or area)

1. Read the SPEC and the DIFF. List the **behaviors that changed** (one line each). Open the full
   functions around each hunk — bugs live in the lines the diff did not touch.
2. For each changed behavior, attack it with the probes below. Stop at the first probe that
   yields a traceable failure; move to the next behavior.
3. For every candidate, **trace it**: name the path (`file:line` → `file:line`) from the trigger
   to the wrong result. If you cannot trace it, it is a doubt, not a finding.
4. Rank: CRITICO (wrong result, data loss/corruption, crash, hang, acceptance criterion broken),
   IMPORTANTE (wrong result in a realistic edge case), SUGESTAO (unlikely edge, cheap guard).

### Probes

- **Values:** null/empty/whitespace, 0/negative/max, every enum value **including default and
  unknown**, duplicated items, very long strings, special characters, culture/encoding
  (decimal separator, accents, code page).
- **State:** called twice, called out of order, partial failure midway (what was already
  written?), stale cache, object reused after dispose, flags left set on an early `return`.
- **Time and concurrency:** UI thread blocked, re-entrancy (double click), race between timer
  and user action, late async response after the context changed, timeouts, cancellation,
  loops/polling without a bound, time zones and date boundaries.
- **Exits:** every exit path (normal, cancel, exception, early return) restores what it changed
  (`finally`, rollback, `saving = false`, resources disposed, UI re-enabled).
- **Integration:** the other side's contract — error status, empty body, changed field, enum
  value the caller does not know; retries that duplicate a side effect.
- **Data:** SQL without the key in `WHERE`, transaction boundaries, rounding, truncation,
  implicit conversions, `FirstOrDefault` → null used as if present.

## root-cause (reported bug)

1. Restate the symptom and the expected behavior. Collect the evidence the task gives (steps,
   logs, ids) — do not ask for what you can read.
2. Form up to three hypotheses; for each, the code path that would produce the symptom and the
   evidence that would confirm or kill it. Check the cheapest first.
3. Confirm one with evidence (code path + log/data/repro). Read-only queries only through the
   tools the policies allow.
4. Deliver: `root_cause` (`file:line`, why), the smallest fix in the files in scope, the
   **regression test** that fails before and passes after, and other callers hit by the same
   cause (grep for the pattern).

## Report (Markdown, the path the task gives)

Identification (scope, mode, round) · Findings (`B<round>-<nn>`: what / failure scenario /
evidence / suggested fix / "not a regression of this change" when pre-existing) · Root cause
(root-cause mode) · Doubts · Probes run without findings (one line each, so the orchestrator
knows what was covered) · Summary table by severity.

**Round ≥ 2:** only your open findings and the diff of the fixes: mark each `fixed` /
`not_fixed` with evidence, and check the fix did not open a new failure scenario.
