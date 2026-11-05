"""AiDW plugin hooks, in a single script (fast: standard library only; any error lets the session through).

- PreToolUse (Edit/Write/MultiEdit/NotebookEdit) — guard: an AiDW agent does not write to the main working copy
  of a repository that has an active demand worktree (state/worktrees.json); it works in the worktree. A file of
  another git repository nested in it (e.g. contexts/<name>) does not count. The main conversation has no rule:
  the user stays free in their own working copy.
- PreToolUse (Bash/PowerShell) — `git commit` in an active demand worktree that still has the `AIDW-TEST` mark
  (temporary test adjustment; the old `AIDW-TESTE` matches too) is refused, for any session: the adjustment is
  reverted before the commit.
- UserPromptSubmit — records the session that entered orchestrator mode (`/aidw:go` or `/aidw:survey`
  on Claude, `$aidw-go` or `$aidw-survey` on Codex) or left it (`/aidw:exit`, `$aidw-exit`), in
  state/sessions.json. On any other message it only matches the text and returns.
- SessionStart (compact|resume) — in a session in orchestrator mode, reminds it to re-read the skill and the
  demand.json (Claude puts back only the start of the skill after a compaction).
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REGISTRY = ROOT / "state" / "worktrees.json"
SESSIONS = ROOT / "state" / "sessions.json"
RUNTIME = ROOT / ".aidw" / "runtime.json"
MARKETPLACE = ROOT / ".aidw" / "marketplace"
CODEX_SKILLS = Path(os.environ.get("AIDW_CODEX_SKILLS_DIR") or Path.home() / ".agents" / "skills")
# Claude: /aidw:go · Codex: $aidw-go (survey also enters the mode); exit and done end the mode
MODE_RE = re.compile(r"^\s*(?:/(aidw[\w-]*):|\$(aidw)-)(go|survey|exit|done)\b(.*)", re.S)
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$|^\*\*\* Move to: (.+)$", re.M)
# `git [-C <dir>] [-c k=v] commit`; group 1 holds the options before the subcommand
GIT_COMMIT_RE = re.compile(r"\bgit((?:\s+-[Cc]\s+(?:\"[^\"]*\"|'[^']*'|\S+))*)\s+commit\b")
GIT_DIR_RE = re.compile(r"-C\s+(\"[^\"]*\"|'[^']*'|\S+)")
# mark of the temporary test adjustments (coder, test-adjust mode); a fixed-string grep for it also matches the
# old mark `AIDW-TESTE`, so worktrees adjusted before the rename are still caught
TEST_MARK = "AIDW-TEST"


def norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(p))


def inside(child: str, parent: str) -> bool:
    c, p = norm(child), norm(parent)
    return c == p or c.startswith(p.rstrip("\\/") + os.sep)


def in_nested_repo(target: str, repo: str) -> bool:
    """The file lives in another git repository nested in the repo (e.g. contexts/<name> inside AiDW)."""
    root, d = norm(repo), os.path.dirname(norm(target))
    while d != root and inside(d, root):
        if os.path.exists(os.path.join(d, ".git")):
            return True
        d = os.path.dirname(d)
    return False


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def is_aidw_agent(agent: str) -> bool:
    """Claude: `aidw:<agent>`. Codex: `aidw-<agent>`. Project mode: the agent's name (or variant) from the runtime."""
    if ":" in agent:
        return agent.split(":", 1)[0].startswith("aidw")
    if agent.startswith("aidw-"):
        return True
    try:
        names = [a["name"] for a in read_json(RUNTIME, {})["agents"].values()]
    except (KeyError, TypeError, AttributeError):
        return False
    return any(agent == n or agent.startswith(n + "-") for n in names)


def deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def commit_guard(data: dict) -> dict | None:
    """Refuses `git commit` in an active demand worktree that still has a test adjustment (mark AIDW-TEST/AIDW-TESTE)."""
    cmd = str((data.get("tool_input") or {}).get("command") or "")
    if "commit" not in cmd:
        return None
    active = [e for e in read_json(REGISTRY, {}).get("worktrees", []) if e.get("status") == "active"]
    for m in GIT_COMMIT_RE.finditer(cmd) if active else ():
        dirs = GIT_DIR_RE.findall(m.group(1))
        repo = dirs[-1].strip("\"'") if dirs else data.get("cwd")
        if not repo:
            continue
        if not os.path.isabs(repo) and data.get("cwd"):
            repo = os.path.join(data["cwd"], repo)
        e = next((e for e in active if inside(repo, e["path"])), None)
        if not e:
            continue
        found = subprocess.run(["git", "-C", e["path"], "grep", "-l", "-I", "-F", "--untracked", TEST_MARK],
                               capture_output=True, text=True, timeout=15).stdout.split()
        if found:
            return deny(f"AiDW: the worktree of demand {e['demand']} still has a temporary test adjustment ({TEST_MARK}) "
                        f"in {', '.join(found[:5])}. Revert the adjustments (git -C <worktree> apply -R "
                        "test-env-<id>.patch) before the commit.")
    return None


def agent_policy(agent: str) -> tuple[dict, set]:
    """(the runtime's `tools` for the agent — `aidw:coder-high`, `aidw-coder` or `coder-high` —, the MCPs AiDW
    distributes among the roles). A server outside that set belongs to the CLI itself and is not judged here."""
    base = agent.split(":", 1)[1] if ":" in agent else agent[5:] if agent.startswith("aidw-") else agent
    agents = [a for a in (read_json(RUNTIME, {}).get("agents") or {}).values() if isinstance(a, dict) and a.get("name")]
    managed = {s for a in agents for s in ((a.get("tools") or {}).get("mcp") or [])}
    hits = [a for a in agents if base == a["name"] or base.startswith(a["name"] + "-")]
    return (max(hits, key=lambda a: len(a["name"])).get("tools") or {}) if hits else {}, managed


def mcp_guard(agent: str, tool: str) -> dict | None:
    """MCP tool outside the agent's role. Claude already enforces it through the subagent; Codex does not limit MCP
    per agent (this hook is what enforces it there)."""
    policy, managed = agent_policy(agent)
    parts = tool.split("__", 2)
    server = parts[1] if len(parts) == 3 else ""
    if tool in policy.get("deny_tools", []):
        return deny(f"AiDW: {tool} is blocked for agent {agent}. Propose the action and return "
                    "`policy_requires_approval`; the orchestrator runs it, with the user's OK.")
    if policy.get("mcp") is not None and server in managed and server not in policy["mcp"]:
        return deny(f"AiDW: the MCP {server} is not part of agent {agent}'s role (allowed: "
                    f"{', '.join(policy['mcp']) or 'none'}). Ask the orchestrator if you need it.")
    return None


def pre_tool_use(data: dict) -> dict | None:
    if data.get("tool_name") in ("Bash", "PowerShell"):
        return commit_guard(data)
    agent = data.get("agent_type") or ""
    if not agent or not is_aidw_agent(agent):
        return None
    if str(data.get("tool_name") or "").startswith("mcp__"):
        return mcp_guard(agent, data["tool_name"])
    ti = data.get("tool_input") or {}
    if data.get("tool_name") == "apply_patch":  # Codex: the paths come in the patch lines
        targets = [(a or b).strip() for a, b in PATCH_FILE_RE.findall(str(ti.get("command") or ""))]
    else:
        targets = [ti.get("file_path") or ti.get("notebook_path")]
    targets = [x for x in targets if x]
    if not targets:
        return None
    resolved = []
    for target in targets:
        if not os.path.isabs(target):
            if not data.get("cwd"):
                print("AiDW guard: relative path with no cwd in the payload; nothing checked", file=sys.stderr)
                return None
            target = os.path.join(data["cwd"], target)
        resolved.append(target)
    for e in read_json(REGISTRY, {}).get("worktrees", []):
        if e.get("status") == "active" and any(inside(x, e["repo"]) and not inside(x, e["path"])
                                               and not in_nested_repo(x, e["repo"]) for x in resolved):
            return deny(f"AiDW: {e['repo']} has the worktree of demand {e['demand']} at {e['path']} "
                        f"(branch {e['branch']}). Edit the matching file in the worktree, not in the main working "
                        "copy.")
    return None


def update_sessions(change) -> dict:
    """Applies `change(sessions)` to state/sessions.json under the cross-session lock and returns the saved record.
    Used by the hook (/aidw:go, /aidw:exit) and by `aidw.py session bind`."""
    SESSIONS.parent.mkdir(parents=True, exist_ok=True)
    lock = SESSIONS.with_name("sessions.lock")
    for _ in range(40):  # light cross-session lock (~2 s); without it, saves anyway
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            time.sleep(0.05)
    else:
        fd = None
    try:
        sessions = read_json(SESSIONS, {})
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=14)).isoformat(timespec="seconds")
        sessions = {k: v for k, v in sessions.items() if v.get("since", "") >= cutoff}  # old sessions are dropped
        change(sessions)
        tmp = SESSIONS.with_name(f"sessions.json.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(sessions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, SESSIONS)
    finally:
        if fd is not None:
            os.close(fd)
            os.unlink(lock)
    return sessions


def user_prompt_submit(data: dict) -> None:
    m = MODE_RE.match(data.get("prompt") or "")
    session = data.get("session_id")
    if not m or not session:
        return None

    def change(sessions: dict) -> None:
        if m.group(3) in ("go", "survey"):  # the go skill understands "survey <id>"; the demand comes from `session bind`
            argument = ("survey " if m.group(3) == "survey" else "") + m.group(4).strip()
            sessions[session] = {"plugin": m.group(1) or m.group(2), "provider": "claude" if m.group(1) else "codex",
                                 "argument": argument.strip()[:200], "cwd": data.get("cwd"),
                                 "since": datetime.datetime.now().isoformat(timespec="seconds")}
        else:
            sessions.pop(session, None)

    update_sessions(change)
    return None


def session_start(data: dict) -> dict | None:
    entry = read_json(SESSIONS, {}).get(data.get("session_id") or "")
    if not entry:
        return None
    codex = entry.get("provider") == "codex"
    skill = (CODEX_SKILLS / "aidw-go" / "SKILL.md" if codex else
             MARKETPLACE / "plugins" / entry["plugin"] / "skills" / "go" / "SKILL.md")
    leave = "$aidw-exit" if codex else f"/{entry['plugin']}:exit"
    arg = f' (the user\'s literal request: "{entry["argument"]}")' if entry.get("argument") else ""
    if entry.get("demand"):
        arg += f", on demand {entry['demand']} of context {entry.get('context') or '?'} ({entry.get('folder')})"
    text = (f"AiDW: this session has been in orchestrator mode{arg} since {entry['since']}. Before going on, re-read "
            f"{skill.as_posix()} and the demand's demand.json (python \"{ROOT.as_posix()}/aidw.py\" demand list "
            f"--active) and resume from the recorded step. {leave} ends the mode.")
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}


def main() -> int:
    try:
        # Claude Code sends UTF-8; Windows stdin would decode it with the console code page (cp1252)
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        event = data.get("hook_event_name")
        handler = {"PreToolUse": pre_tool_use, "UserPromptSubmit": user_prompt_submit,
                   "SessionStart": session_start}.get(event)
        result = handler(data) if handler else None
    except Exception:  # the hooks never block the session
        return 0
    if result:
        print(json.dumps(result))  # pure ASCII: independent of the console encoding
    return 0


if __name__ == "__main__":
    sys.exit(main())
