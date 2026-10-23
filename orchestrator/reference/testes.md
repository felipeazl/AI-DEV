---
when: a etapa de testes (TEST, TEST_ADJUST, MANUAL_TEST) e a conferência de que os ajustes de teste saíram antes do commit
---

# Testes — ajustes, passos manuais e a conferência antes do commit

- **Approvals first:** the script's *Aprovações* go to the user in one batch while the code is being written (block by
  block, as the active context says); the qa task lists what was approved, so the run never stops halfway.
- **Adjustments** (`TEST_ADJUST`): temporary code changes only for testing (bypass, flag, mock, DEV/QA pointing),
  requested by the qa. A coder (the exception for small changes) with `tarefa-codificador-ajuste-teste-<n>.md` (the
  adjustments, the patch `ambiente-teste-<id>.patch`), then a fresh qa that continues from the last report. They exist
  only while testing: revert them when a test step ends (`git -C <wt> apply -R <patch>`), re-apply to test again
  (`git -C <wt> apply <patch>`; if it no longer applies, `TEST_ADJUST` again). Review and commit never see them.
- **Manual test** (`MANUAL_TEST`): the manual steps of `roteiro-testes-<id>.md`, with the user. Re-apply the
  adjustments they need and start their servers as background tasks of this session. Show **one step at a time**,
  verbatim: what to do, the expected result, the evidence to send. Compare the evidence with the expected result,
  record ✅/❌ and a one-line description in the step's `Resultado` (never a secret or personal data), show the next
  step. On a ❌, record it and go on with the steps that do not depend on it. At the end, revert the adjustments and
  stop the servers; all ✅ → `PR`; any ❌ → `CODER_FIX` with the failing steps and their evidence.
- **Before the commit**, prove the adjustments are gone: `git -C <wt> grep -n -I -F --untracked AIDW-TESTE` prints
  nothing and `git -C <wt> diff <base> --stat` matches the last reviewed patch. The guard hook also refuses a
  `git commit` in a demand worktree that still has `AIDW-TESTE`.
