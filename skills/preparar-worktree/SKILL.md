---
name: preparar-worktree
description: Create, inspect and remove the git worktree of a demand with `aidw.py worktree` — right base (including an unmerged branch it depends on, or an old commit for a simulation/rework), feature branch, junctions for untracked build dependencies (packages/, node_modules/), registry and demand.json. Use whenever a demand changes code.
---

# preparar-worktree

The AiDW command does the git work, the junctions and the registry; the agents never edit the main
working copy (a hook blocks it). Run it by the absolute path of `aidw.py` shown in your Runtime section.

1. **Decide the base** — the plan's *Branch and PR*: the development branch, the unmerged branch of
   another demand this one depends on, or (simulation/rework) the commit before the change being redone.
2. **Create:**
   ```
   python "<aidw root>/aidw.py" worktree create --repo <repo> --demand <tipo-id> --slug <slug> --base <base> --json
   ```
   It fetches, creates `<worktree root>/<tipo-id>/<repo>` (one folder per demand, a worktree per repository
   inside) on branch `<prefix><id>-<slug>` (prefix from the context), reuses the branch if it already exists,
   links `packages/`/`node_modules/` and writes `demand.json`. Running it again returns the same worktree. If
   `main_dirty` is true, tell the user once that the main working copy's local changes are not in the worktree.
3. **Move the session (Claude):** a demand with more than one repository gets one `create` per repository.
   - Desktop app: `mcp__ccd_directory__change_directory` to the worktree (one repository) or to the demand folder
     (more than one); the diff pane follows it, and `/aidw:diff` switches it between the repositories. Then add
     the Runtime *Session folders* (the active context's folder) with `mcp__ccd_directory__request_directory`, once
     per session, so the plans and reports open in the app.
   - Terminal: `EnterWorktree` with name `<tipo-id>` (the AiDW hook returns this worktree).
   - Every task still names the absolute path of its worktree.
4. **Validate** with the build command of *Systems*, pointing at the worktree. A failure here is
   environment, not code: report it.
5. **Hand over** the worktree path and branch in every task (`file:line` and build commands use it).
6. **Inspect / clean up:** `worktree list`, `worktree inspect <tipo-id>`. At the end, only after the work is
   pushed or explicitly discarded: `worktree remove <tipo-id>` — it refuses local changes and unpublished
   commits, removes the junctions first and keeps the branch (deleting a branch is a locked git action:
   propose it, do not run it). `worktree cleanup` drops entries whose folder is gone.
