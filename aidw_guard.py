"""Hooks do plugin do AiDW, num script só (rápido: só biblioteca padrão; qualquer erro libera a sessão).

- PreToolUse (Edit/Write/MultiEdit/NotebookEdit) — guard: um agente do AiDW não escreve no working copy
  principal de um repositório que tem worktree ativo de demanda (state/worktrees.json); ele trabalha no
  worktree. A conversa principal não tem regra: o usuário continua livre no working copy dele.
- PreToolUse (Bash/PowerShell) — `git commit` num worktree ativo de demanda que ainda tem a marca `AIDW-TESTE`
  (ajuste temporário de teste) é recusado, para qualquer sessão: o ajuste é revertido antes do commit.
- UserPromptSubmit — registra a sessão que entrou no modo orquestrador (`/aidw:orquestrar` ou `/aidw:levantamento`
  no Claude, `$aidw-orquestrar` ou `$aidw-levantamento` no Codex) ou saiu dele (`/aidw:sair`, `$aidw-sair`), em state/sessions.json. Nas outras mensagens só compara o texto e sai.
- SessionStart (compact|resume) — numa sessão no modo orquestrador, lembra de reler a skill e o
  demand.json (o Claude recoloca só o começo da skill depois de uma compactação).
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
# Claude: /aidw:orquestrar · Codex: $aidw-orquestrar (levantamento também entra no modo); sair e done encerram o modo
MODE_RE = re.compile(r"^\s*(?:/(aidw[\w-]*):|\$(aidw)-)(orquestrar|levantamento|sair|done)\b(.*)", re.S)
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$|^\*\*\* Move to: (.+)$", re.M)
# `git [-C <pasta>] [-c k=v] commit`; o grupo 1 tem as opções antes do subcomando
GIT_COMMIT_RE = re.compile(r"\bgit((?:\s+-[Cc]\s+(?:\"[^\"]*\"|'[^']*'|\S+))*)\s+commit\b")
GIT_DIR_RE = re.compile(r"-C\s+(\"[^\"]*\"|'[^']*'|\S+)")
TEST_MARK = "AIDW-TESTE"  # marca dos ajustes temporários de teste (codificador, modo ajuste de teste)


def norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(p))


def inside(child: str, parent: str) -> bool:
    c, p = norm(child), norm(parent)
    return c == p or c.startswith(p.rstrip("\\/") + os.sep)


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def is_aidw_agent(agent: str) -> bool:
    """Claude: `aidw:<agente>`. Codex: `aidw-<agente>`. Modo projeto: o nome do agente (ou variante) do runtime."""
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
    """Recusa `git commit` num worktree ativo de demanda que ainda tem ajuste de teste (marca AIDW-TESTE)."""
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
            return deny(f"AiDW: o worktree da demanda {e['demand']} ainda tem ajuste temporario de teste ({TEST_MARK}) "
                        f"em {', '.join(found[:5])}. Reverta os ajustes (git -C <worktree> apply -R "
                        "ambiente-teste-<id>.patch) antes do commit.")
    return None


def agent_policy(agent: str) -> tuple[dict, set]:
    """(`tools` do runtime para o agente — `aidw:codificador-high`, `aidw-codificador` ou `codificador-high` —,
    MCPs que o AiDW distribui entre os papéis). Servidor fora desse conjunto é do próprio CLI e não é julgado aqui."""
    base = agent.split(":", 1)[1] if ":" in agent else agent[5:] if agent.startswith("aidw-") else agent
    agents = [a for a in (read_json(RUNTIME, {}).get("agents") or {}).values() if isinstance(a, dict) and a.get("name")]
    managed = {s for a in agents for s in ((a.get("tools") or {}).get("mcp") or [])}
    hits = [a for a in agents if base == a["name"] or base.startswith(a["name"] + "-")]
    return (max(hits, key=lambda a: len(a["name"])).get("tools") or {}) if hits else {}, managed


def mcp_guard(agent: str, tool: str) -> dict | None:
    """Ferramenta MCP fora do papel do agente. O Claude já aplica pelo subagente; o Codex não limita MCP por agente
    (o hook é o que garante lá)."""
    policy, managed = agent_policy(agent)
    parts = tool.split("__", 2)
    server = parts[1] if len(parts) == 3 else ""
    if tool in policy.get("deny_tools", []):
        return deny(f"AiDW: {tool} é bloqueada para o agente {agent}. Proponha a ação e devolva "
                    "`policy_requires_approval`; quem executa é o orquestrador, com o OK do usuário.")
    if policy.get("mcp") is not None and server in managed and server not in policy["mcp"]:
        return deny(f"AiDW: o MCP {server} não é do papel do agente {agent} (permitidos: "
                    f"{', '.join(policy['mcp']) or 'nenhum'}). Peça ao orquestrador se precisar dele.")
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
    if data.get("tool_name") == "apply_patch":  # Codex: os caminhos vêm nas linhas do patch
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
                print("AiDW guard: caminho relativo sem cwd no payload; nada verificado", file=sys.stderr)
                return None
            target = os.path.join(data["cwd"], target)
        resolved.append(target)
    for e in read_json(REGISTRY, {}).get("worktrees", []):
        if e.get("status") == "active" and any(inside(x, e["repo"]) and not inside(x, e["path"]) for x in resolved):
            return deny(f"AiDW: {e['repo']} tem o worktree da demanda {e['demand']} em {e['path']} "
                        f"(branch {e['branch']}). Edite o arquivo correspondente no worktree, não no working copy "
                        "principal.")
    return None


def user_prompt_submit(data: dict) -> None:
    m = MODE_RE.match(data.get("prompt") or "")
    session = data.get("session_id")
    if not m or not session:
        return None
    SESSIONS.parent.mkdir(parents=True, exist_ok=True)
    lock = SESSIONS.with_name("sessions.lock")
    for _ in range(40):  # trava leve entre sessões (~2 s); sem ela, grava mesmo assim
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
        sessions = {k: v for k, v in sessions.items() if v.get("since", "") >= cutoff}  # sessões antigas saem
        if m.group(3) in ("orquestrar", "levantamento"):  # a skill orquestrar entende "levantamento <id>"
            argument = ("levantamento " if m.group(3) == "levantamento" else "") + m.group(4).strip()
            sessions[session] = {"plugin": m.group(1) or m.group(2), "provider": "claude" if m.group(1) else "codex",
                                 "argument": argument.strip()[:200], "cwd": data.get("cwd"),
                                 "since": datetime.datetime.now().isoformat(timespec="seconds")}
        else:
            sessions.pop(session, None)
        tmp = SESSIONS.with_name(f"sessions.json.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(sessions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, SESSIONS)
    finally:
        if fd is not None:
            os.close(fd)
            os.unlink(lock)
    return None


def session_start(data: dict) -> dict | None:
    entry = read_json(SESSIONS, {}).get(data.get("session_id") or "")
    if not entry:
        return None
    codex = entry.get("provider") == "codex"
    skill = (CODEX_SKILLS / "aidw-orquestrar" / "SKILL.md" if codex else
             MARKETPLACE / "plugins" / entry["plugin"] / "skills" / "orquestrar" / "SKILL.md")
    leave = "$aidw-sair" if codex else f"/{entry['plugin']}:sair"
    arg = f' (pedido literal do usuário: "{entry["argument"]}")' if entry.get("argument") else ""
    text = (f"AiDW: esta sessão está no modo orquestrador{arg} desde {entry['since']}. Antes de continuar, releia "
            f"{skill.as_posix()} e o demand.json da demanda (python \"{ROOT.as_posix()}/aidw.py\" demand list "
            f"--active) e retome da etapa gravada. {leave} encerra o modo.")
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}


def main() -> int:
    try:
        # o Claude Code manda UTF-8; o stdin do Windows decodificaria na página do console (cp1252)
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        event = data.get("hook_event_name")
        handler = {"PreToolUse": pre_tool_use, "UserPromptSubmit": user_prompt_submit,
                   "SessionStart": session_start}.get(event)
        result = handler(data) if handler else None
    except Exception:  # os hooks nunca travam a sessão
        return 0
    if result:
        print(json.dumps(result))  # ASCII puro: independe da codificação do console
    return 0


if __name__ == "__main__":
    sys.exit(main())
