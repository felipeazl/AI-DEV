---
name: preparar-worktree
description: Create an isolated git worktree and feature branch for a demand from the right base (including an unmerged branch it depends on), link untracked build dependencies such as .NET Framework packages/, and remove it at the end. Use when the user's working copy has other work in progress, or for a simulation/rework from an old base.
---

# preparar-worktree

1. **Decide the base** — the plan's *Branch and PR* section: the development branch, or the
   unmerged branch of another demand this one depends on, or (simulation/rework) the commit before
   the change being redone. `git fetch` first; confirm the base exists (`git rev-parse --verify`).
2. **Create** next to the repo, never inside it:
   ```
   git -C <repo> worktree add -b feature/<id>-<slug> <repo>-wt-<id> <base>
   ```
   `worktree add` is local and allowed; do not `checkout`/`switch` the user's working copy.
   If the branch already exists, reuse it with `git -C <repo> worktree add <path> feature/<id>-<slug>`.
3. **Untracked build dependencies** — anything the build needs that git does not version:
   - .NET Framework `packages/` (NuGet): link it instead of restoring,
     `New-Item -ItemType Junction -Path <wt>\packages -Target <repo>\packages`
     (PowerShell) or `cmd /c mklink /J <wt>\packages <repo>\packages`;
   - other local-only files the *Systems* build needs (e.g. a local config the project documents)
     — copy only what the build requires, never secrets into the demand folder.
4. **Validate** with the build command of *Systems*, pointing at the worktree. A failure here is
   environment, not code: report it.
5. **Hand over** the worktree path and branch to the tasks (every `file:line` and build command
   uses the worktree path).
6. **Clean up** at the end, only after the work is committed or explicitly discarded:
   remove the junction first (`Remove-Item <wt>\packages` removes the link, not the target — never
   delete recursively through a junction), then `git -C <repo> worktree remove <wt>`.
   Deleting the branch is a locked git action: propose it, do not run it.
