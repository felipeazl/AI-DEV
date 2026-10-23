---
when: conduzir a revisão da PR de outro dev (workflow pr-review): entender, worktree só leitura, revisor no modo PR, triagem, revisão final e nova versão da PR
---

# Revisão de PR de outro dev (workflow pr-review)

**PR review** (`pr-review`: someone else's pull request; no plan, coder or fix loop — the author fixes). Name the
demand after its work item (or `pr-<n>` without one); one demand may hold PRs of several repositories.
- **Understand:** `resumo-<id>.md` as usual, plus per PR: number, repository, author, title, description, target
  branch, linked work items and what reviewers already commented or voted (read only).
- **Worktree:** per PR, `python "{{root}}/aidw.py" worktree create --repo <repo> --demand <tipo-id> --pr <n>`: a
  read-only detached worktree of the PR already merged into its target, and `diff-pr<n>-<repo>.patch` in the demand
  folder. Run the system's build in it once, output to `build-pr<n>-<repo>.txt` (only its tail in this chat).
- `REVIEW`: one {{agent:reviewer}} task with every PR of the demand, in PR mode (summary, PR data, diffs, worktree paths
  with `base`/`source`, build output). `pr_review_done` → triage (skill `verificar-premissa` before dropping a finding)
  following the reference *triagem-pr*: findings that say the same thing become one comment (`C1`…), with a vote per PR.
- **Final review** (`FINAL_REVIEW`): per PR, its comments — ID, severity, `file:line`, the draft text, your
  recommendation — and its vote. The user picks the comments, edits their text and chooses each vote. Commenting,
  voting and completing the PR are locked actions: only with their explicit OK, exactly what they approved; never touch
  the work item's state. Record what was published (thread ids) and each vote in the triage.
- **The author updated the PR:** run the same `worktree create --pr <n>` again (writes
  `diff-pr<n>-<repo>-r<N>.patch` with only what changed); a fresh reviewer (the exception one level down) gets the
  previous review and that diff (round N, same IDs).
- **At the end:** `worktree remove <tipo-id>`.
