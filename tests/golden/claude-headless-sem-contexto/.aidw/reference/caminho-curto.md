<!-- Gerado por aidw.py apply a partir de orchestrator/reference/caminho-curto.md; não edite: altere a fonte e rode `python aidw.py apply`. -->

# Caminho curto — depois da entrega

**After delivery** — a bug the QA team returned, a change the team's code review asked for, or a small adjustment the
user asks: a fix, not a new demand. `resumo-bug-<n>.md` (or `resumo-ajuste-<slug>.md`) with the item, what failed, the
evidence and the criterion it breaks; the explorer only when the cause is not plain; a coder with a short task (the
exception for small fixes); a review of only the fix (`review-<id>-<item>-r<N>.md`, with
`demand set <id> --loop <item>`; `--loop -` at the end), its findings to the user; the qa retests only the affected
steps and the regression of the area. One line per fix in *Adendos* at the end of the plan. A new criterion, another
system or a contract change is new scope: the full workflow.
