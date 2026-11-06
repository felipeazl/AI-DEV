# Demands and worktrees

Every demand that changes code gets **its own git worktree**: a separate working copy, on its own branch, attached to
the same repository. The agents work there; your main working copy is never touched. Read-only requests need no
worktree.

## Why worktrees

- **Isolation:** you keep working (or have another demand open) in your working copy while the agent works elsewhere.
- **Several demands at once:** each one in its worktree, on its branch.
- **A clean diff:** what the agent changed is exactly the worktree's diff against its base.
- **Protection:** a hook stops an AiDW agent from editing the main working copy of a repository that has an active
  demand worktree.

## The demand folder

```text
C:\wt\                                   ← [worktree] root
└── us-1234\                             ← the demand folder: the chat stays here when there is more than one repository
    ├── App\                             ← back-end worktree (branch feature/1234-fee-adjustment)
    ├── App.Front\                       ← front-end worktree (same demand, same branch)
    └── Shared\                          ← junction to a neighbor folder (worktree_link)
```

- Branch `<context branch_prefix><number>-<slug>` (prefix `aidw/` without a context), created from the base the plan
  sets (by default the origin's default branch; it may be someone else's unmerged branch the demand depends on).
- `packages/` and `node_modules/` come in by **junction** from the main working copy (the context's `[worktree] link`
  changes the list): the build runs without restoring everything again.
- The registry lives in `state/worktrees.json`; the demand's repositories in its `demand.json`.

### Repositories with the same name

Two repositories with the same name (e.g. `C:/New/Portal` and `C:/Legacy/Portal`) do not share the folder: the second
one goes to `<root>/<demand>/<repo>.<parent folder>`.

### Neighbor folders (`worktree_link`)

Legacy code sometimes reaches another repository by relative path (e.g. a HintPath `..\..\Shared\bin\x.dll`). In a
worktree that path would not exist. So a system can list `worktree_link = ["../Shared"]` in `context.toml`:

- `worktree create` creates, next to the worktree, a junction with the same relative path, pointing to what it resolves
  to from the main working copy.
- If the demand also has a worktree of that repository, it is already there and the build uses the demand's version.
  If the junction came first, it becomes the worktree when that one is created.
- `remove` of the demand's last worktree removes the junctions, deleting nothing through them.
- Paths that climb above the demand folder (`../../Other`) stay at the root, shared.

Worktrees created before the per-demand folder, in `<root>/<repo>/<demand>`, keep working where they are.

## Where the chat goes

| Situation | The chat goes to |
|---|---|
| One repository, Claude desktop app | the worktree (the app's `change_directory`; the diff panel follows) |
| Several repositories, desktop app | the demand folder |
| No worktree (read-only, or repositories used in place, as in an imported demand), desktop app | the demand's state folder (`<state_dir>/<id>`), which every demand has |
| Claude terminal | `EnterWorktree` with the demand id |
| Codex | it does not move: every command and task uses the worktree's absolute path |
| Chat already in the demand folder or one of its worktrees | stays |
| Chat opened at the AiDW root | goes into the demand's worktree (with several, the first created) |
| Chat opened in another repository | creates that repository's worktree for the same demand |

If the main working copy has local changes, `worktree create` warns and the orchestrator asks you once.

In the desktop app, after moving (or when the chat already opened in the demand folder), the orchestrator also adds the
**active context's folder** to the session (and the state folder, when it lives outside the context) with the app's
`request_directory`, once per session, so the plan, the test script and the reports open in the app. `aidw open
--demand` does the same with `--add-dir`.

## See each repository's diff

The app's diff panel shows the repository of the session's current folder. In a demand with several repositories:

```text
/aidw:diff            ← goes to the demand's next repository, in a cycle
/aidw:diff front      ← goes straight to one (by folder name; a fragment works)
/aidw:diff exit       ← back to the demand folder
```

The chat, the conversation context and orchestrator mode continue: point at something in the front end, switch to the
back end, point at something else, all in the same session. The orchestrator also switches when you ask ("show me the
back-end diff").

- **Desktop app:** uses the app's `change_directory`, and the panel follows.
- **Terminal:** `ExitWorktree` and `EnterWorktree` with `<demand>/<folder>`; `exit` returns to where the session opened.
- **Codex:** not available (there is no way to change the session folder).

Without worktrees (repositories used in place), `/aidw:diff` walks the `repos` of `demand.json` and `exit` returns to
the demand's state folder. The app's extra folders (the folder button with +) grant access to another folder, but the
diff panel does not show them: use `/aidw:diff`.

## Open and resume

```powershell
python aidw.py open --demand 1234                    # opens Claude in the demand, already calling /aidw:go
python aidw.py open --demand 1234 --repo App.Front   # in one repository; the others come in through --add-dir
python aidw.py open --provider codex --demand 1234   # Codex in the worktree, with multi_agent_v2 and the AiDW folder
python aidw.py open --demand 1234 --no-orchestrate   # only opens, without calling the orchestrator
```

`1234` finds `us-1234`. In the chat, `/aidw:go` with no argument in a worktree folder finds the demand and continues
from the recorded step.

## Inspect and clean up

```powershell
python aidw.py worktree list            # every worktree (folder, branch, changes, unpushed commits)
python aidw.py worktree inspect us-1234
python aidw.py worktree remove us-1234  # only with a clean worktree and pushed commits; the branch stays
python aidw.py worktree cleanup         # removes from the registry what is gone from disk
python aidw.py status                   # includes worktrees of finished demands and orphans
```

Deleting the branch is a locked action: ask the orchestrator, which asks for your OK.

## Someone else's PR worktree

To review a PR someone else opened (workflow `pr-review`):

```powershell
python aidw.py worktree create --repo C:\Repos\App --demand us-1234 --pr 5678
```

- Fetches `refs/pull/<n>/merge` from `origin`: the PR already merged into its target, as it would be after the merge.
  Works with Azure Repos and GitHub. If the ref does not exist, the PR is from another repository, already completed or
  in conflict with its target.
- Creates the worktree in `<root>/<demand>/<repo>`, **detached, without a branch**, with the dependency junctions and
  the neighbor folders, and writes `diff-pr<n>-<repo>.patch` in the demand folder. In the registry, `base` is the
  target commit, `source` the PR's tip and `head` the merge.
- Running it again after the author updates the PR moves the worktree to the new version (refused with local changes)
  and writes `diff-pr<n>-<repo>-r<N>.patch` with only what changed, in the PR's files.
- One repository per demand: the same demand cannot have the PR and a working branch in the same repository.
- `worktree remove` removes the junctions first, then the worktree and the PR ref; there is no branch to keep.

## Demand state

```powershell
python aidw.py demand list --active
python aidw.py demand show us-1234
python aidw.py demand set us-1234 --step REVIEW --status paused --note "waiting for QA"
```

`demand.json` keeps the step, the status (`active`, `paused`, `done`), the summary, the repositories, Tasks, PRs and the
step history. It is what lets you close the chat and come back later. Every option of `demand set`:
[commands.md](commands.md#day-to-day).
