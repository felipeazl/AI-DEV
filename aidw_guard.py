"""Hooks do plugin do AiDW, num script só (rápido: só biblioteca padrão; qualquer erro libera a sessão).

- PreToolUse (Edit/Write/MultiEdit/NotebookEdit) — guard: um agente do AiDW não escreve no working copy
  principal de um repositório que tem worktree ativo de demanda (state/worktrees.json); ele trabalha no
  worktree. A conversa principal não tem regra: o usuário continua livre no working copy dele.
- UserPromptSubmit — registra a sessão que entrou no modo orquestrador (`/aidw:orquestrar` no Claude,
  `$aidw-orquestrar` no Codex) ou saiu dele (`/aidw:sair`, `$aidw-sair`), em state/sessions.json. Nas outras mensagens só compara o texto e sai.
- SessionStart (compact|resume) — numa sessão no modo orquestrador, lembra de reler a skill e o
  demand.json (o Claude recoloca só o começo da skill depois de uma compactação).
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REGISTRY = ROOT / "state" / "worktrees.json"
SESSIONS = ROOT / "state" / "sessions.json"
RUNTIME = ROOT / ".aidw" / "runtime.json"
MARKETPLACE = ROOT / ".aidw" / "marketplace"
CODEX_SKILLS = Path(os.environ.get("AIDW_CODEX_SKILLS_DIR") or Path.home() / ".agents" / "skills")
# Claude: /aidw:orquestrar · Codex: $aidw-orquestrar; sair e done encerram o modo
MODE_RE = re.compile(r"^\s*(?:/(aidw[\w-]*):|\$(aidw)-)(orquestrar|sair|done)\b(.*)", re.S)
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$|^\*\*\* Move to: (.+)$", re.M)


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


def pre_tool_use(data: dict) -> dict | None:
    agent = data.get("agent_type") or ""
    if not agent or not is_aidw_agent(agent):
        return None
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
            return {"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"AiDW: {e['repo']} tem o worktree da demanda {e['demand']} em {e['path']} "
                    f"(branch {e['branch']}). Edite o arquivo correspondente no worktree, não no working copy "
                    "principal.")}}
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
        if m.group(3) == "orquestrar":
            sessions[session] = {"plugin": m.group(1) or m.group(2), "provider": "claude" if m.group(1) else "codex",
                                 "argument": m.group(4).strip()[:200], "cwd": data.get("cwd"),
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
