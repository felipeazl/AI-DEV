---
when: a bug the QA returned, a change request on the PR or an adjustment after delivery (the short path, no new plan)
---

# Short path — after delivery

**After delivery** — a bug the QA team returned, a change the team's code review asked for, or a small adjustment the
user asks: a fix, not a new demand. `summary-bug-<n>.md` (or `summary-adjust-<slug>.md`) with the item, what failed,
the evidence and the criterion it breaks; when the item does not already name the cause (`file:line`, the comment's
line), the explorer finds it — one task with the numbered questions, never this chat grepping code or reading reports
(each result stays in this context and is re-read on every action); a review comment that names its line goes to the
coder as it is; a coder with a short task (the
exception for small fixes); a review of only the fix (`review-<id>-<item>-r<N>.md`, with
`demand set <id> --loop <item>`; `--loop -` at the end), its findings to the user — for a bug the QA returned or a
change the team's code review asked for, the review task says it is an **escape** (skill `code-review`), so the
reviewer adds a *Checklist candidate* that `/aidw:done` takes to the user; the qa retests only the affected
steps and the regression of the area. One line per fix in *Addenda* at the end of the plan. A new criterion, another
system or a contract change is new scope: the full workflow.
