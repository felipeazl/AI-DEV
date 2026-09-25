---
name: verificar-premissa
description: Verify a premise with first-hand evidence before accepting it — "it can't be fixed here", "this covers every case", "it's the repo's convention", "that value never happens", "the other system already does X". Use before triaging, planning or reporting on such a claim, yours or another agent's.
---

# verificar-premissa

A false premise costs a whole round (plan, fix, review). Checking one costs a grep or a SELECT.
Run this whenever a decision depends on a claim you have not seen evidence for.

1. **Write the premise as a testable sentence** — "`Status` is never `0` when this runs", not
   "the flow is safe".
2. **Pick the cheapest evidence that can refute it**, in this order:
   - **Code path:** open the code (`file:line`) and follow every branch that matters, including
     exceptions and early returns. "Covers every case" needs one path per case.
   - **Occurrence count:** "it's the convention" → count usages (`grep`) in the repo and cite
     2–3; a convention with one occurrence is not a convention.
   - **Data:** "that value never happens" → a read-only `SELECT` through the allowed validator
     (distribution of the column, `COUNT` per value) in DEV/QA. Note that test data may be
     manipulated and not represent production.
   - **Contract:** "the other system does X" → open that system's code or documentation (the
     *Systems* section says where) — not the caller's assumption about it.
   - **Card:** "the business wants X" → the work item's fields **and comments**, and linked items.
3. **Verdict:** `confirmada` (evidence), `refutada` (evidence against — say what is true
   instead), or `não verificável aqui` (what would verify it and who can). Only `confirmada`
   may support a decision; `não verificável` becomes a doubt for the user, never an assumption.
4. **Record it** where the decision lives (plan table "Premissas verificadas", triage file,
   review finding): premise · evidence (`file:line`, query, count) · verdict.

Typical triggers: taking a finding out of scope; downgrading a CRITICO/IMPORTANTE; accepting
"not a regression"; a plan step that relies on a value, state or behavior of another system.
