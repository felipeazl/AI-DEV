#!/usr/bin/env python3
"""AI-DEV — configuração do ambiente de desenvolvimento multi-agente.

Uso:
    python aidev.py setup                  # wizard (se ainda não houver config) + apply + doctor
    python aidev.py configure              # wizard interativo; grava aidev.config.toml
    python aidev.py configure --defaults   # grava a config padrão sem perguntar
    python aidev.py apply [--dry-run]      # gera o ambiente a partir da config
    python aidev.py doctor                 # verifica pré-requisitos
    python aidev.py show                   # mostra agentes e modelos resolvidos

Modelo de execução: um único chat do Claude Code aberto na raiz do AI-DEV é o
orquestrador; os demais agentes são subagentes nativos (.claude/agents/*.md),
gerados pelo apply. Tudo roda com o login do Claude Code, sem API key.

A fonte de verdade é o aidev.config.toml. Ele pode ser editado à mão; depois
basta rodar `python aidev.py apply`. O apply é idempotente.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit("AI-DEV requer Python 3.11+ (usa tomllib).")

import tomllib

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "aidev.config.toml"
MODELS_FILE = ROOT / "config" / "models.toml"
MCP_CATALOG_FILE = ROOT / "config" / "mcp.toml"
MCP_JSON = ROOT / ".mcp.json"
ROUTING_FILE = ROOT / "orchestrator" / "config" / "routing.toml"
RUNTIME_FILE = ROOT / "orchestrator" / "config" / "runtime.json"
ORCHESTRATOR_MD = ROOT / "orchestrator" / "CLAUDE.md"
POLICIES_DIR = ROOT / "orchestrator" / "policies"
AGENTS_DIR = ROOT / "agents"
SKILLS_DIR = ROOT / "skills"
CONTEXTS_DIR = ROOT / "contexts"
WORKFLOWS_DIR = ROOT / "workflows"
ROOT_CLAUDE_MD = ROOT / "CLAUDE.md"
ROOT_AGENTS_MD = ROOT / "AGENTS.md"          # instruções do orquestrador no Codex CLI
CLAUDE_DIR = ROOT / ".claude"
SUBAGENTS_DIR = CLAUDE_DIR / "agents"
LINKED_SKILLS_DIR = CLAUDE_DIR / "skills"
SETTINGS_FILE = CLAUDE_DIR / "settings.local.json"

DEFAULT_MCP = ["playwright", "chrome-devtools", "figma", "context7"]

IS_WINDOWS = os.name == "nt"
GENERATED_MARK = "Gerado por aidev.py"
ORCHESTRATOR = "orchestrator"

ACTIONS = {"TICKETS", "IMPLEMENT", "TEST", "PREPARE_REVIEW", "REVIEW", "CODER_FIX", "DOCS",
           "FINAL_REVIEW", "DONE", "HUMAN_APPROVAL"}
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
ALIASES = {"opus", "sonnet", "haiku", "fable"}
# Campos do frontmatter do subagente que o apply controla (os demais do AGENT.md são repassados).
RESERVED_FRONTMATTER = {"name", "description", "model", "effort", "skills", "omitClaudeMd",
                        "tools", "disallowedTools"}

# Nome padrão de cada papel; sobrescreva com [agents.<papel>].name no aidev.config.toml.
DEFAULT_NAMES = {
    "orchestrator": "orquestrador",
    "coder": "codificador",
    "reviewer": "revisor",
    "api-db": "api",
    "qa": "qa",
    "documenter": "documentador",
}
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
BUILTIN_AGENT_NAMES = {"general-purpose", "explore", "plan", "statusline-setup", "claude-code-guide"}
# Nos arquivos de instruções, {{agent:<papel>}} vira o nome configurado do agente.
PLACEHOLDER_RE = re.compile(r"\{\{agent:([\w-]+)\}\}")

# Padrão (nível "padrao" da demanda): codificador em Opus, revisor e api em Sonnet,
# documentador em Haiku.
# Os outros níveis vêm de [levels] no routing.toml.
DEFAULT_AGENTS: dict[str, dict] = {
    "orchestrator": {"enabled": True, "model": "opus-high",
                     "skills": ["to-spec", "to-tickets", "codebase-context"]},
    "coder": {"enabled": True, "model": "opus-medium",
              "skills": ["implement-ticket", "debug", "testing", "codebase-context"]},
    "reviewer": {"enabled": True, "model": "sonnet", "skills": ["code-review"]},
    "api-db": {"enabled": True, "model": "sonnet-medium", "skills": ["database-safe", "debug"]},
    "qa": {"enabled": False, "model": "sonnet", "skills": ["testing"]},
    "documenter": {"enabled": True, "model": "haiku", "skills": ["documentation"]},
}

# `delegate`: modo de permissão de cada papel no `claude -p`. Sem prompt interativo, o que pediria
# aprovação é negado e volta em `permission_denials`, para o orquestrador levar ao usuário.
# `auto`: comandos de rotina rodam (classificador); regras `ask` (commit, push, sqlcmd…) seguem
# negadas — testado em 2026-09-25. O api fica em `default`: só o que está no `allow` (validador
# SQL, git); chamada de API que muda estado precisa de OK um a um (policies/ambientes-e-escrita).
DELEGATE_PERMISSION = {"coder": "auto", "reviewer": "auto", "documenter": "auto",
                       "qa": "auto", "api-db": "default"}
DELEGATE_MAX_TURNS = {"coder": 80, "reviewer": 40, "documenter": 40, "qa": 40, "api-db": 30}

# Regras de negação do chat (valem para o orquestrador e todos os subagentes).
DEFAULT_DENY = [
    "Bash(git push --force *)",
    "Bash(git push -f *)",
    "Bash(git reset --hard *)",
    "Bash(git clean -f *)",
    "PowerShell(git push --force *)",
    "PowerShell(git push -f *)",
    "PowerShell(git reset --hard *)",
    "PowerShell(git clean -f *)",
    "Read(**/.env)",
    "Read(**/.env.*)",
]


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------

class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def ok(self, msg: str) -> None:
        print(f"  [ok]    {msg}")

    def info(self, msg: str) -> None:
        print(f"  [--]    {msg}")

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
        print(f"  [aviso] {msg}")

    def error(self, msg: str) -> None:
        self.errors.append(msg)
        print(f"  [erro]  {msg}")


def heading(title: str) -> None:
    print(f"\n== {title} ==")


def rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


# ---------------------------------------------------------------------------
# Config e contexto
# ---------------------------------------------------------------------------

def load_toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def load_catalog() -> dict[str, dict]:
    return load_toml(MODELS_FILE).get("models", {})


def load_mcp_catalog() -> dict[str, dict]:
    return load_toml(MCP_CATALOG_FILE).get("servers", {}) if MCP_CATALOG_FILE.exists() else {}


def resolve_mcp(cfg: dict, roles: list[str], rep: Report) -> dict[str, dict]:
    """Servidores MCP habilitados, validados contra o catálogo."""
    catalog = load_mcp_catalog()
    servers = {}
    for key in cfg["mcp"]["enabled"]:
        s = catalog.get(key)
        if s is None:
            rep.error(f"MCP {key!r} habilitado mas não existe em config/mcp.toml")
            continue
        if s.get("type") == "stdio" and not s.get("command"):
            rep.error(f"config/mcp.toml: {key} (stdio) sem `command`")
        elif s.get("type") == "http" and not s.get("url"):
            rep.error(f"config/mcp.toml: {key} (http) sem `url`")
        elif s.get("type") not in ("stdio", "http"):
            rep.error(f"config/mcp.toml: {key} com type inválido {s.get('type')!r}")
        for role in s.get("agents", []):
            if role not in roles:
                rep.warn(f"config/mcp.toml: {key} cita papel desconhecido {role!r}")
        servers[key] = s
    return servers


def mcp_json_entry(s: dict) -> dict:
    if s["type"] == "http":
        return {"type": "http", "url": s["url"]}
    entry = {"type": "stdio", "command": s["command"], "args": list(s.get("args", []))}
    if s.get("env"):
        entry["env"] = dict(s["env"])
    return entry


def default_config() -> dict:
    return {
        "models": {"mode": "multi", "default": "opus-high"},
        "workspace": {"project_dirs": []},
        "mcp": {"enabled": list(DEFAULT_MCP)},
        "context": {"active": ""},
        "jev": {"enabled": False, "model": "jev"},
        "codex": {"enabled": False, "model": "gpt-sol", "effort": "high"},
        "policies": {"deny": list(DEFAULT_DENY), "ask": []},
        "agents": json.loads(json.dumps(DEFAULT_AGENTS)),
    }


def load_config() -> dict | None:
    if not CONFIG_FILE.exists():
        return None
    cfg = load_toml(CONFIG_FILE)
    base = default_config()
    for section in ("models", "workspace", "mcp", "context", "jev", "codex", "policies"):
        base[section].update(cfg.get(section, {}))
    if "agents" in cfg:
        base["agents"] = {}
        for name, a in cfg["agents"].items():
            merged = {**DEFAULT_AGENTS.get(name, {"enabled": True, "skills": []}), **a}
            base["agents"][name] = {k: merged[k] for k in ("enabled", "model", "skills")}
            if merged.get("name"):
                base["agents"][name]["name"] = merged["name"]
    return base


def agent_name(role: str, agent: dict) -> str:
    return agent.get("name") or DEFAULT_NAMES.get(role, role)


def toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)  # string JSON é string básica TOML válida
    if isinstance(v, list):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    raise TypeError(f"tipo não suportado em TOML: {type(v)}")


def render_config(cfg: dict) -> str:
    m, j = cfg["models"], cfg["jev"]
    out = [
        f"# Configuração do AI-DEV. {GENERATED_MARK} configure em {date.today().isoformat()}.",
        "# Pode editar à mão; depois rode `python aidev.py apply`.",
        "# Atenção: `configure` reescreve este arquivo (comentários próprios são perdidos).",
        "# Modelos disponíveis: config/models.toml",
        "",
        "[models]",
        '# "multi"  = cada agente usa o modelo definido em [agents.<nome>].model',
        '# "single" = todos os agentes usam `default`',
        "# O modelo do orchestrator é o do chat. O modelo de cada agente aqui é o do nível padrão da",
        "# demanda; os outros níveis ficam em [levels] do orchestrator/config/routing.toml.",
        f"mode = {toml_value(m['mode'])}",
        f"default = {toml_value(m['default'])}",
        "",
        "[workspace]",
        "# Pastas dos seus projetos (opcional). Liberadas para o chat e todos os subagentes.",
        f"project_dirs = {toml_value(cfg['workspace']['project_dirs'])}",
        "",
        "[mcp]",
        "# Servidores de config/mcp.toml registrados no escopo do projeto (.mcp.json).",
        "# O orquestrador decide quando cada um é necessário (use_when/triggers do catálogo).",
        f"enabled = {toml_value(cfg['mcp']['enabled'])}",
        "",
        "[context]",
        '# Pacote de regras de trabalho em contexts/<nome>/ ("" = nenhum).',
        f"active = {toml_value(cfg['context']['active'])}",
        "",
        "[jev]",
        "# Camada de decisão (seção 7 do plano). Desligado = regras determinísticas",
        "# de orchestrator/config/routing.toml.",
        f"enabled = {toml_value(j['enabled'])}",
        f"model = {toml_value(j['model'])}",
        "",
        "[codex]",
        "# Orquestrador alternativo no Codex CLI (GPT): o apply gera AGENTS.md e o Codex delega aos",
        "# agentes Claude com `python aidev.py delegate` (claude -p, modelo/effort por chamada).",
        f"enabled = {toml_value(cfg['codex']['enabled'])}",
        f"model = {toml_value(cfg['codex']['model'])}",
        f"effort = {toml_value(cfg['codex']['effort'])}",
        "",
        "[policies]",
        "# Regras de permissão gravadas em .claude/settings.local.json (valem para todos os agentes):",
        "# deny = bloqueado sempre · ask = sempre pede sua confirmação, mesmo se liberado em outro lugar.",
        "deny = [",
        *[f"    {toml_value(d)}," for d in cfg["policies"]["deny"]],
        "]",
        "ask = [",
        *[f"    {toml_value(d)}," for d in cfg["policies"]["ask"]],
        "]",
    ]
    out += ["", "# [agents.<papel>] — o papel é fixo; `name` é opcional (sem ele, vale o padrão comentado)."]
    for role, a in cfg["agents"].items():
        default = DEFAULT_NAMES.get(role, role)
        name_line = (f"name = {toml_value(a['name'])}" if a.get("name")
                     else f"# name = {toml_value(default)}")
        out += [
            "",
            f"[agents.{role}]",
            name_line,
            f"enabled = {toml_value(a['enabled'])}",
            f"model = {toml_value(a['model'])}",
            f"skills = {toml_value(a['skills'])}",
        ]
    return "\n".join(out) + "\n"


def list_contexts() -> list[str]:
    if not CONTEXTS_DIR.is_dir():
        return []
    return sorted(d.name for d in CONTEXTS_DIR.iterdir() if (d / "context.toml").exists())


def load_context(cfg: dict, rep: Report) -> dict | None:
    name = cfg["context"]["active"]
    if not name:
        return None
    path = CONTEXTS_DIR / name / "context.toml"
    if not path.exists():
        rep.error(f"contexto {name!r} não encontrado ({rel(path)}): clone o repositório dele em "
                  f"contexts/{name}/ ou rode `setup` para escolher outro, criar um ou seguir sem")
        return None
    ctx = load_toml(path)
    ctx["name"] = name
    ctx["dir"] = path.parent
    ctx.setdefault("description", name)
    for agent, spec in ctx.get("agents", {}).items():
        for inc in spec.get("include", []):
            if not (ctx["dir"] / inc).is_file():
                rep.error(f"contexto {name}: [agents.{agent}] inclui arquivo inexistente {inc!r}")
        for ref in spec.get("reference", []):
            if not (ctx["dir"] / ref.get("path", "")).is_file():
                rep.error(f"contexto {name}: [agents.{agent}] referência inexistente {ref.get('path')!r}")
    systems = ctx.get("systems", {})
    for key, sysdef in systems.items():
        for dep in sysdef.get("depends_on", []):
            if dep not in systems:
                rep.warn(f"contexto {name}: sistema {key!r} depende de {dep!r}, que não está em [systems]")
        for repo in sysdef.get("repos", []):
            if not Path(repo).is_dir():
                rep.warn(f"contexto {name}: repositório do sistema {key!r} não existe: {repo}")
    return ctx


def expand_git_ask(subcommands: list[str]) -> list[str]:
    """`commit` → ask para `git commit ...` e `git -C <pasta> commit ...`, no Bash e no PowerShell."""
    rules = []
    for tool in ("Bash", "PowerShell"):
        for sub in subcommands:
            rules += [f"{tool}(git {sub})", f"{tool}(git {sub} *)", f"{tool}(git -C * {sub})",
                      f"{tool}(git -C * {sub} *)"]
    return rules


def systems_section(ctx: dict | None, detailed: bool) -> str:
    systems = ctx.get("systems", {}) if ctx else {}
    if not systems:
        return ""
    lines = ["## Systems", "",
             "Where each system lives and how to validate it. Use these commands as given; do not "
             "search for other build tools.", ""]
    for key, s in systems.items():
        lines.append(f"### {s.get('name', key)} (`{key}`)")
        if s.get("repos"):
            lines.append(f"- Repos: {', '.join(f'`{r}`' for r in s['repos'])}")
        if s.get("stack"):
            lines.append(f"- Stack: {s['stack']}")
        if s.get("depends_on"):
            deps = ", ".join(f"`{d}`" for d in s["depends_on"])
            lines.append(f"- Depends on: {deps} — when a change consumes one of these, inspect its "
                         "contract (endpoints, enums, events) in that repo before planning")
        if s.get("build"):
            lines.append(f"- Build: `{s['build']}`")
        if s.get("test"):
            lines.append(f"- Test: `{s['test']}`")
        if detailed and s.get("notes"):
            lines += ["- Notes:", *[f"  - {n}" for n in s["notes"]]]
        lines.append("")
    return "\n".join(lines).rstrip()


def reference_section(ctx: dict | None, role: str) -> str:
    refs = ctx.get("agents", {}).get(role, {}).get("reference", []) if ctx else []
    if not refs:
        return ""
    rows = ["## Reference (read on demand)", "",
            "Not loaded up front, to keep your context small. Read a file only when its topic "
            "applies to the task.", ""]
    rows += [f"- `{(ctx['dir'] / r['path']).as_posix()}` — {r.get('when', '')}" for r in refs]
    return "\n".join(rows)


def context_missing(cfg: dict) -> bool:
    name = cfg["context"]["active"]
    return bool(name) and not (CONTEXTS_DIR / name / "context.toml").exists()


def state_dir(ctx: dict | None) -> Path:
    return ROOT / (ctx.get("state_dir", "state") if ctx else "state")


def project_dirs(cfg: dict, ctx: dict | None) -> list[str]:
    """Pastas liberadas: as do workspace (máquina) + as do contexto, sem repetição."""
    dirs = [*cfg["workspace"]["project_dirs"], *(ctx.get("additional_dirs", []) if ctx else [])]
    return list(dict.fromkeys(d.replace("\\", "/").rstrip("/") for d in dirs))


def list_mcp_servers() -> dict[str, dict[str, str]] | None:
    """{nome: {command, status}} a partir de `claude mcp list`; None se o CLI falhar."""
    out = run(["claude", "mcp", "list"])
    if out is None:
        return None
    servers = {}
    for line in out.splitlines():
        m = re.match(r"^(.+?): (.+) - (.+)$", line.strip())
        if m:
            servers[m.group(1)] = {"command": m.group(2), "status": m.group(3)}
    return servers


def mcp_add_hint(name: str, command: str) -> str:
    if re.match(r"https?://", command):
        return f"claude mcp add --scope user --transport http {name} {command}"
    return f"claude mcp add --scope user {name} -- {command}"


def create_context(name: str, description: str, required_mcp: list[str],
                   required_env: list[str], registered: dict | None = None) -> Path:
    """Cria contexts/<nome>/ com a estrutura mínima e um repositório Git próprio."""
    d = CONTEXTS_DIR / name
    for sub in ("policies", "shared", "agents", "reference", "skills", "demandas"):
        (d / sub).mkdir(parents=True, exist_ok=True)
        if sub != "agents":
            (d / sub / ".gitkeep").touch()

    if registered is None:
        registered = (list_mcp_servers() or {}) if required_mcp else {}
    mcp_blocks = []
    for server in required_mcp:
        hint = mcp_add_hint(server, registered[server]["command"]) if server in registered else ""
        mcp_blocks += ["", f"[mcp.{json.dumps(server)}]",
                       "# Comando mostrado pelo `doctor` quando o MCP não estiver registrado.",
                       f"add = {toml_value(hint)}"]

    (d / "context.toml").write_text("\n".join([
        f"# Contexto de trabalho: {description}.",
        f"# {GENERATED_MARK} setup em {date.today().isoformat()}; edite à vontade e rode "
        "`python aidev.py apply`.",
        "# Caminhos de arquivos são relativos a esta pasta.",
        "",
        f"name = {toml_value(name)}",
        f"description = {toml_value(description)}",
        "",
        "# Onde ficam specs, planos e reviews das demandas. Relativo à raiz do AI-DEV.",
        f"state_dir = {toml_value(f'contexts/{name}/demandas')}",
        "",
        "# Pastas liberadas só com este contexto (as do [workspace] do aidev.config.toml já valem).",
        "additional_dirs = []",
        "",
        "# Verificados pelo `doctor`: variáveis (só a presença) e servidores MCP registrados.",
        f"required_env = {toml_value(required_env)}",
        f"required_mcp = {toml_value(required_mcp)}",
        "",
        "[env]",
        "",
        "[permissions]",
        "# Liberadas sem prompt / negadas, para o chat e todos os subagentes.",
        "allow = []",
        "deny = []",
        "",
        "# O que entra nas instruções de cada agente, além de policies/*.md (sempre incluídas).",
        "[agents.orchestrator]",
        'include = ["agents/orchestrator.md"]',
        "",
        "# [agents.coder]",
        '# include = ["shared/guia-time.md", "agents/coder.md"]',
        '# skills = ["minha-skill"]',
        *mcp_blocks,
    ]) + "\n", encoding="utf-8", newline="\n")

    (d / "agents" / "orchestrator.md").write_text(
        f"# Orquestrador — {description}\n\n"
        "<!-- Regras do orquestrador neste contexto: sistemas, repositórios, fluxo de trabalho,\n"
        "     pontos de aprovação. Cite agentes com {{agent:<papel>}}, ex.: {{agent:coder}}. -->\n",
        encoding="utf-8", newline="\n")
    (d / "README.md").write_text(
        f"# Contexto {name}\n\n{description}.\n\n"
        "Regras de trabalho usadas pelo AI-DEV quando `aidev.config.toml` tem "
        f'`[context] active = "{name}"`. Repositório Git **separado e privado**; o AI-DEV ignora '
        "esta pasta.\n\n"
        "| Pasta | Conteúdo |\n|---|---|\n"
        "| `policies/` | Regras duras (entram em todos os agentes) |\n"
        "| `shared/` | Guias compartilhados entre agentes |\n"
        "| `agents/` | Regras específicas de cada agente |\n"
        "| `reference/` | Documentação de referência |\n"
        "| `skills/` | Skills do contexto |\n"
        "| `demandas/` | Specs, planos e reviews |\n"
        "| `context.toml` | O que entra em cada agente, pastas, permissões, MCPs |\n\n"
        "Depois de editar, rode `python aidev.py apply` na raiz do AI-DEV.\n",
        encoding="utf-8", newline="\n")
    (d / ".gitignore").write_text(".env\n.env.*\ndemandas/**/bin/\ndemandas/**/obj/\n",
                                  encoding="utf-8", newline="\n")
    (d / ".gitattributes").write_text("* text=auto eol=lf\n*.ps1 text eol=crlf\n",
                                      encoding="utf-8", newline="\n")
    if shutil.which("git"):
        run(["git", "init", "-b", "main"], cwd=d)
    return d


def available_skills(ctx: dict | None, rep: Report) -> dict[str, Path]:
    skills = {d.name: d for d in sorted(SKILLS_DIR.iterdir()) if (d / "SKILL.md").exists()}
    ctx_skills = ctx["dir"] / "skills" if ctx else None
    if ctx_skills and ctx_skills.is_dir():
        for d in sorted(ctx_skills.iterdir()):
            if (d / "SKILL.md").exists():
                if d.name in skills:
                    rep.warn(f"skill {d.name!r} do contexto substitui a skill genérica")
                skills[d.name] = d
    return skills


def context_files(ctx: dict | None, agent: str) -> list[Path]:
    if not ctx:
        return []
    return [ctx["dir"] / inc for inc in ctx.get("agents", {}).get(agent, {}).get("include", [])]


def policy_files(ctx: dict | None) -> list[Path]:
    files = sorted(POLICIES_DIR.glob("*.md"))
    if ctx and (ctx["dir"] / "policies").is_dir():
        files += sorted((ctx["dir"] / "policies").glob("*.md"))
    return files


def resolve(cfg: dict, catalog: dict, ctx: dict | None, skills: dict, rep: Report) -> dict[str, dict]:
    """Valida a config e devolve {agente: {..., model: {...}}}."""
    mode = cfg["models"]["mode"]
    if mode not in ("single", "multi"):
        rep.error(f'models.mode deve ser "single" ou "multi" (atual: {mode!r})')
    for key, m in catalog.items():
        if m.get("effort") and m["effort"] not in EFFORTS:
            rep.error(f"config/models.toml: effort inválido em {key}: {m['effort']!r}")
        if m.get("alias") and m["alias"] not in ALIASES:
            rep.error(f"config/models.toml: alias inválido em {key}: {m['alias']!r}")

    agents = cfg["agents"]
    if ORCHESTRATOR not in agents or not agents[ORCHESTRATOR]["enabled"]:
        rep.error("o agente orchestrator é obrigatório e precisa estar habilitado")

    resolved = {}
    for name, a in agents.items():
        key = cfg["models"]["default"] if mode == "single" else a["model"]
        model = catalog.get(key)
        if model is None:
            rep.error(f"agente {name}: modelo {key!r} não existe em config/models.toml")
            continue
        if a["enabled"]:
            if model.get("router_only"):
                rep.error(f"agente {name}: {key!r} é router_only (só pode ser usado pelo JEV)")
            if model["provider"] != "anthropic":
                rep.error(f"agente {name}: {model['name']} exige API key, que ainda não é suportada; "
                          "escolha um modelo Anthropic")
            if name != ORCHESTRATOR:
                if not model.get("alias"):
                    rep.error(f"agente {name}: modelo {key!r} não tem `alias` (exigido por subagentes)")
                if not (AGENTS_DIR / name / "AGENT.md").exists():
                    rep.error(f"agente {name}: agents/{name}/AGENT.md não existe")
        ctx_skills = ctx.get("agents", {}).get(name, {}).get("skills", []) if ctx else []
        all_skills = list(dict.fromkeys([*a["skills"], *ctx_skills]))
        for s in all_skills:
            if s not in skills:
                rep.error(f"agente {name}: skill {s!r} não encontrada")
        resolved[name] = {**a, "name": agent_name(name, a), "skills": all_skills,
                          "model_key": key, "model": model}

    seen: dict[str, str] = {}
    for role, a in resolved.items():
        if not NAME_RE.match(a["name"]):
            rep.error(f"agente {role}: nome {a['name']!r} inválido (use minúsculas, dígitos e hífen)")
        elif a["name"] in BUILTIN_AGENT_NAMES:
            rep.error(f"agente {role}: nome {a['name']!r} é reservado pelo Claude Code")
        elif a["name"] in seen:
            rep.error(f"agentes {seen[a['name']]} e {role} têm o mesmo nome {a['name']!r}")
        seen.setdefault(a["name"], role)

    if cfg["jev"]["enabled"] and cfg["jev"]["model"] not in catalog:
        rep.error(f"jev.model {cfg['jev']['model']!r} não existe em config/models.toml")
    if cfg["codex"]["enabled"]:
        cm = catalog.get(cfg["codex"]["model"])
        if cm is None or cm.get("provider") != "openai":
            rep.error(f"codex.model {cfg['codex']['model']!r} precisa ser um modelo openai de config/models.toml")
    return resolved


def load_routing(rep: Report) -> dict:
    routing = load_toml(ROUTING_FILE) if ROUTING_FILE.exists() else {}
    for st, action in routing.get("rules", {}).items():
        if action not in ACTIONS:
            rep.error(f"routing.toml: ação desconhecida {action!r} em {st!r} "
                      f"(válidas: {', '.join(sorted(ACTIONS))})")
    return routing


def resolve_levels(routing: dict, cfg: dict, catalog: dict, resolved: dict,
                   rep: Report) -> dict[str, dict]:
    """Níveis da demanda → subagente (nome + modelo) de cada papel habilitado.

    Effort só é configurável no frontmatter do subagente (não por chamada), então cada
    combinação modelo/effort diferente da do agente base vira um arquivo `<nome>-<nível>`.
    Papel ausente no nível usa o agente base. No modo single não há níveis.
    """
    levels = routing.get("levels", {})
    if not levels or cfg["models"]["mode"] == "single":
        return {}
    out: dict[str, dict] = {}
    for lvl, spec in levels.items():
        if not NAME_RE.match(lvl):
            rep.error(f"routing.toml: nível {lvl!r} inválido (use minúsculas, dígitos e hífen)")
            continue
        roles = {}
        for role, a in resolved.items():
            if role == ORCHESTRATOR or not a["enabled"]:
                continue
            key = spec.get(role, a["model_key"])
            m = catalog.get(key)
            if m is None:
                rep.error(f"routing.toml: [levels.{lvl}] {role} = {key!r} não existe em config/models.toml")
                continue
            if not m.get("alias") or m.get("provider") != "anthropic" or m.get("router_only"):
                rep.error(f"routing.toml: [levels.{lvl}] {role} = {key!r} não serve para subagente")
                continue
            same = (m["alias"], m.get("effort")) == (a["model"]["alias"], a["model"].get("effort"))
            roles[role] = {"name": a["name"] if same else f"{a['name']}-{lvl}",
                           "model_key": key, "model": m}
        for role in spec:
            if role != "when" and role not in resolved:
                rep.error(f"routing.toml: [levels.{lvl}] cita papel desconhecido {role!r}")
        out[lvl] = {"when": spec.get("when", ""), "roles": roles}
    if routing.get("default_level", "") not in out:
        rep.error(f"routing.toml: default_level {routing.get('default_level')!r} não é um nível de [levels]")
    return out


def decision_label(cfg: dict, catalog: dict) -> str:
    if cfg["jev"]["enabled"]:
        jev = catalog.get(cfg["jev"]["model"], {"name": cfg["jev"]["model"]})
        return f"JEV — {jev['name']}, with deterministic rules as fallback"
    return "deterministic rules from `orchestrator/config/routing.toml` (JEV disabled)"


def model_label(agent_name: str, m: dict) -> str:
    if agent_name == ORCHESTRATOR:
        effort = f", effort {m['effort']}" if m.get("effort") else ""
        return f"{m['name']} (`{m['model_id']}`{effort})"
    effort = f"effort {m['effort']}" if m.get("effort") else "effort inherited from the chat"
    return f"{m['name']} (`{m.get('alias', '?')}`, {effort})"


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------

def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        answer = ""
    return answer or default


def confirm(prompt: str, default: bool) -> bool:
    answer = ask(f"{prompt} (s/n)", "s" if default else "n").lower()
    return answer in ("s", "sim", "y", "yes")


def choose(prompt: str, options: list[tuple[str, str]], current: str) -> str:
    print(prompt)
    keys = [k for k, _ in options]
    for i, (key, label) in enumerate(options, 1):
        mark = "  <- atual" if key == current else ""
        print(f"  {i}) {label}{mark}")
    default = str(keys.index(current) + 1) if current in keys else "1"
    while True:
        answer = ask("  Escolha", default)
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return keys[int(answer) - 1]
        if answer in keys:
            return answer
        print("  Opção inválida.")


def model_options(catalog: dict, router: bool = False) -> list[tuple[str, str]]:
    opts = []
    for key, m in catalog.items():
        if router or (m["provider"] == "anthropic" and not m.get("router_only")):
            opts.append((key, f"{m['name']:<26} {m['provider']}"))
    return opts


def split_answer(answer: str, sep: str = ",") -> list[str]:
    return [s.strip().strip("\"'") for s in answer.split(sep) if s.strip() and s.strip() != "-"]


def normalize_dir(path: str) -> str:
    p = os.path.expanduser(path).replace("\\", "/").rstrip("/")
    return p + "/" if re.fullmatch(r"[A-Za-z]:", p) else p  # raiz de drive: C:/


def ask_project_dirs(cfg: dict, step: str) -> None:
    print(f"{step} Pastas dos seus projetos (opcional) — liberadas para o chat e todos os subagentes.")
    current = cfg["workspace"]["project_dirs"]
    answer = ask("  Caminhos separados por ';' ('-' = nenhuma)", "; ".join(current) or "-")
    dirs = []
    for raw in split_answer(answer, ";"):
        p = normalize_dir(raw)
        if Path(p).is_dir() or confirm(f"  {p} não existe. Manter mesmo assim?", False):
            dirs.append(p)
    cfg["workspace"]["project_dirs"] = list(dict.fromkeys(dirs))


def ask_mcp(cfg: dict, step: str) -> None:
    catalog = load_mcp_catalog()
    print(f"{step} Servidores MCP (o orquestrador decide quando cada um é usado):")
    for key, s in catalog.items():
        mark = "x" if key in cfg["mcp"]["enabled"] else " "
        print(f"  [{mark}] {key:<16} {s['use_when'][:70]}…")
    while True:
        answer = ask("  Quais ativar? (vírgula, '-' = nenhum)", ",".join(cfg["mcp"]["enabled"]) or "-")
        chosen = split_answer(answer)
        unknown = [c for c in chosen if c not in catalog]
        if not unknown:
            break
        print(f"  Desconhecido(s): {', '.join(unknown)}. Opções: {', '.join(catalog)}")
    cfg["mcp"]["enabled"] = chosen


def ask_new_context() -> str:
    while True:
        name = ask("  Nome do novo contexto (minúsculas, dígitos e hífen)").lower()
        if not NAME_RE.match(name):
            print("  Nome inválido.")
        elif (CONTEXTS_DIR / name).exists():
            print(f"  Já existe contexts/{name}/.")
        else:
            break
    description = ask("  Descrição (ex.: Empresa X — Squad Y)", name)
    required_env = split_answer(ask("  Variáveis de ambiente exigidas (vírgula, '-' = nenhuma)", "-"))
    required_mcp: list[str] = []
    registered: dict = {}
    if confirm("  O contexto exige servidores MCP?", False):
        print("  Consultando `claude mcp list`…")
        registered = list_mcp_servers() or {}
        if registered:
            print(f"  Registrados: {', '.join(registered)}")
        required_mcp = split_answer(ask("  Quais? (vírgula, '-' = nenhum)", "-"))
    d = create_context(name, description, required_mcp, required_env, registered)
    print(f"  Criado {rel(d)}/ com repositório Git próprio. Escreva as regras nele depois.")
    return name


def ask_context(cfg: dict, step: str) -> None:
    contexts = list_contexts()
    current = cfg["context"]["active"]
    if current and current not in contexts:
        print(f"  O contexto configurado {current!r} não existe nesta máquina (contexts/{current}/).")
        print(f"  Para usá-lo, cancele (Ctrl+C), clone o repositório dele em contexts/{current}/ e "
              "rode o setup de novo.")
        current = ""
    options = ([("", "nenhum — só as regras genéricas do AI-DEV")] + [(c, c) for c in contexts]
               + [("+", "criar um novo contexto agora")])
    prefix = f"{step} " if step else ""
    choice = choose(f"{prefix}Contexto de trabalho (regras em contexts/<nome>/):", options, current)
    cfg["context"]["active"] = ask_new_context() if choice == "+" else choice


def wizard(cfg: dict, catalog: dict) -> dict:
    heading("AI-DEV · configuração")
    print("Enter mantém o valor atual. Tudo pode ser alterado depois em aidev.config.toml.\n")

    cfg["models"]["mode"] = choose("1/7 Como distribuir os modelos?", [
        ("multi", "multi  — cada agente usa o seu modelo"),
        ("single", "single — um único modelo para todos os agentes"),
    ], cfg["models"]["mode"])

    print()
    options = model_options(catalog)
    if cfg["models"]["mode"] == "single":
        cfg["models"]["default"] = choose("2/7 Modelo usado por todos os agentes:", options,
                                          cfg["models"]["default"])
    else:
        print("2/7 Modelo de cada agente (o do orchestrator é o do chat; subagentes herdam o effort):")
        for name, a in cfg["agents"].items():
            a["model"] = choose(f"\n  -> {name}", options, a["model"])

    print()
    optional = [n for n in cfg["agents"] if n != ORCHESTRATOR]
    disabled = [n for n in optional if not cfg["agents"][n]["enabled"]]
    print(f"3/7 Agentes opcionais: {', '.join(optional)}")
    answer = ask("  Quais desabilitar? (separados por vírgula, '-' = nenhum)",
                 ",".join(disabled) or "-")
    chosen = {s.strip() for s in answer.split(",") if s.strip() and s.strip() != "-"}
    for n in chosen - set(optional):
        print(f"  Ignorando agente desconhecido: {n}")
    for n in optional:
        cfg["agents"][n]["enabled"] = n not in chosen

    names = ", ".join(f"{r}={agent_name(r, a)}" for r, a in cfg["agents"].items())
    print(f"\n  Nomes atuais: {names}")
    if confirm("  Personalizar os nomes dos agentes?", False):
        for role, a in cfg["agents"].items():
            default = DEFAULT_NAMES.get(role, role)
            while True:
                name = ask(f"    {role} (padrão {default})", agent_name(role, a)).lower()
                if NAME_RE.match(name) and name not in BUILTIN_AGENT_NAMES:
                    break
                print("    Nome inválido: use minúsculas, dígitos e hífen (e não um nome do Claude Code).")
            if name == default:
                a.pop("name", None)
            else:
                a["name"] = name

    print()
    ask_project_dirs(cfg, "4/7")

    print()
    ask_mcp(cfg, "5/7")

    print()
    ask_context(cfg, "6/7")

    print()
    cfg["jev"]["enabled"] = confirm("7/7 Usar o JEV como camada de decisão?", cfg["jev"]["enabled"])
    if cfg["jev"]["enabled"]:
        cfg["jev"]["model"] = choose("  Modelo do JEV:", model_options(catalog, router=True),
                                     cfg["jev"]["model"])
    return cfg


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def write_if_changed(path: Path, content: str, dry: bool, rep: Report) -> None:
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == content:
        return
    if dry:
        rep.info(f"(dry-run) {'criar' if old is None else 'atualizar'} {rel(path)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    rep.ok(f"{'criado' if old is None else 'atualizado'} {rel(path)}")


def ensure_dir(path: Path, dry: bool, rep: Report) -> None:
    if path.is_dir():
        return
    if dry:
        rep.info(f"(dry-run) criar {rel(path)}/")
    else:
        path.mkdir(parents=True)
        rep.ok(f"criado {rel(path)}/")


def read_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = text.index("\n---\n", 4)
    meta = {}
    for line in text[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    return meta, text[end + 5:].lstrip()


class Templater:
    """Troca {{agent:<papel>}} pelo nome configurado do agente; papel desconhecido é erro."""

    def __init__(self, resolved: dict, rep: Report) -> None:
        self.names = {role: a["name"] for role, a in resolved.items()}
        self.rep = rep

    def render(self, text: str, source: Path) -> str:
        def repl(m: re.Match) -> str:
            role = m.group(1)
            if role not in self.names:
                self.rep.error(f"{rel(source)}: marcador {m.group(0)} usa papel desconhecido "
                               f"(válidos: {', '.join(self.names)})")
                return m.group(0)
            return self.names[role]
        return PLACEHOLDER_RE.sub(repl, text)

    def include(self, path: Path) -> str:
        body = self.render(path.read_text(encoding="utf-8").strip(), path)
        return f"<!-- fonte: {rel(path)} -->\n\n{body}"


def runtime_lines(cfg: dict, catalog: dict, ctx: dict | None) -> list[str]:
    ctx_label = f"`{ctx['name']}` — {ctx['description']}" if ctx else "none"
    dirs = ", ".join(f"`{d}`" for d in project_dirs(cfg, ctx)) or "none configured"
    return [
        f"- Decision layer: {decision_label(cfg, catalog)}",
        f"- Project dirs (search here for repositories): {dirs}",
        f"- State dir: `{state_dir(ctx).as_posix()}`",
        f"- Context: {ctx_label}",
        f"- AI-DEV root: `{ROOT.as_posix()}`",
    ]


def mcp_for_role(servers: dict, role: str) -> dict:
    return {k: s for k, s in servers.items() if not s.get("agents") or role in s["agents"]}


def mcp_orchestrator_section(servers: dict, resolved: dict, cfg: dict) -> str:
    if not servers:
        return "## MCP tools\n\nNo MCP servers enabled."
    if cfg["jev"]["enabled"]:
        rule = ("Ask the JEV decision layer which servers the ticket needs; if it gives no answer, "
                "fall back to matching the task against the triggers below.")
    else:
        rule = ("Decide deterministically: match the ticket against the triggers below. A server is "
                "needed only when at least one trigger clearly applies.")
    rows = ["| Server | Tool prefix | Use when | Triggers | Agents |", "|---|---|---|---|---|"]
    for key, s in servers.items():
        agents = ", ".join(f"`{resolved[r]['name']}`" for r in s.get("agents", []) if r in resolved) or "all"
        rows.append(f"| {s['name']} | `mcp__{key}__*` | {s['use_when']} | {'; '.join(s.get('triggers', []))} "
                    f"| {agents} |")
    return "\n".join([
        "## MCP tools", "",
        "You decide which MCP servers each delegated task needs. Before every delegation:", "",
        f"1. {rule}",
        "2. Pick only servers listed for the agent that will receive the task.",
        "3. Name them explicitly in the task, with the goal — e.g. \"Use the Playwright MCP to walk "
        "through the checkout flow and confirm acceptance criteria 2 and 3\".",
        "4. If no trigger applies, write \"No MCP tools needed\" in the task. Never add a server "
        "speculatively.",
        "5. Record the choice (server + reason) in the ticket or plan, so it can be measured later.",
        "", *rows,
    ])


def mcp_agent_section(servers: dict, role: str) -> str:
    mine = mcp_for_role(servers, role)
    if not mine:
        return "## MCP tools\n\nNo MCP servers are available for your role."
    rows = ["| Server | Tool prefix | Use when |", "|---|---|---|"]
    rows += [f"| {s['name']} | `mcp__{k}__*` | {s['use_when']} |" for k, s in mine.items()]
    return "\n".join([
        "## MCP tools", "",
        "Use a server when the task names it. Use one the task does not name only when its "
        "\"use when\" clearly applies and the task cannot be done well without it — and say so in "
        "your result. Report in the result which servers you used and why.",
        "", *rows,
    ])


def csv_field(value: str) -> list[str]:
    return [t.strip() for t in value.split(",") if t.strip()]


def subagent_tools(meta: dict, role: str, ctx: dict | None, servers: dict) -> list[str]:
    """Allowlist do AGENT.md + os servidores MCP do papel + os MCP exigidos pelo contexto.

    Sem `tools` no AGENT.md o subagente herda todas as ferramentas (comportamento antigo).
    """
    tools = csv_field(meta.get("tools", ""))
    if not tools:
        return []
    mcp = [*mcp_for_role(servers, role), *(ctx.get("required_mcp", []) if ctx else [])]
    return list(dict.fromkeys([*tools, *[f"mcp__{k}" for k in mcp]]))


def render_subagent(role: str, agent: dict, cfg: dict, catalog: dict, ctx: dict | None,
                    tpl: Templater, servers: dict, routing: dict,
                    variant: dict | None = None) -> str:
    """Instruções do subagente. `variant` = {"name", "model", "level"} gera a cópia de um nível."""
    source = AGENTS_DIR / role / "AGENT.md"
    meta, body = read_frontmatter(source)
    name = variant["name"] if variant else agent["name"]
    model = variant["model"] if variant else agent["model"]
    description = tpl.render(meta.get("description", name), source)
    if variant:
        description = (f"Mesmo papel de `{agent['name']}`, no nível {variant['level']} da demanda "
                       f"({model['name']}, effort {model.get('effort', 'do chat')}). Use só quando o "
                       f"orquestrador classificar a tarefa nesse nível.")
    front = ["---", f"name: {name}",
             f"description: {json.dumps(description, ensure_ascii=False)}",
             f"model: {model['alias']}"]
    if model.get("effort"):
        front.append(f"effort: {model['effort']}")
    front.append("omitClaudeMd: true")
    if agent["skills"]:
        front += ["skills:"] + [f"  - {s}" for s in agent["skills"]]
    tools = subagent_tools(meta, role, ctx, servers)
    if tools:
        front.append(f"tools: {', '.join(tools)}")
    ctx_agent = ctx.get("agents", {}).get(role, {}) if ctx else {}
    disallowed = csv_field(meta.get("disallowedTools", ""))
    disallowed += [t for t in ctx_agent.get("disallowed_tools", []) if t not in disallowed]
    if disallowed:
        front.append(f"disallowedTools: {', '.join(disallowed)}")
    front += [f"{k}: {v}" for k, v in meta.items() if k not in RESERVED_FRONTMATTER]
    front.append("---")

    sources = [source, *policy_files(ctx), *context_files(ctx, role)]
    parts = [
        "\n".join(front),
        f"<!-- {GENERATED_MARK} apply a partir de: {', '.join(rel(s) for s in sources)}.\n"
        "     Não edite: altere as fontes e rode `python aidev.py apply`. -->",
        tpl.render(body.strip(), source),
        "\n".join(["## Runtime", "",
                   f"- Agent: `{name}` (role `{role}`; subagent — you cannot talk to the user, "
                   f"return questions and approvals to `{tpl.names[ORCHESTRATOR]}`)",
                   f"- Model: {model_label(role, model)}",
                   f"- Skills: {', '.join(f'`{s}`' for s in agent['skills']) or '—'}",
                   f"- Max retries: {routing.get('max_retries', 3)} (the same failing step; then "
                   "stop and report the failure `state` of your OUTPUT)",
                   *runtime_lines(cfg, catalog, ctx)]),
        mcp_agent_section(servers, role),
        systems_section(ctx, detailed=True),
        reference_section(ctx, role),
        "# POLICIES",
        *[tpl.include(p) for p in policy_files(ctx)],
    ]
    parts = [x for x in parts if x]
    if context_files(ctx, role):
        parts.append(f"# CONTEXT: {ctx['description']}")
        parts += [tpl.include(p) for p in context_files(ctx, role)]
    return "\n\n".join(parts) + "\n"


def short_model(m: dict) -> str:
    return f"{m.get('alias', '?')}/{m['effort']}" if m.get("effort") else m.get("alias", "?")


def levels_section(levels: dict, resolved: dict, cfg: dict, routing: dict) -> str:
    if not levels:
        return ""
    roles = [r for r, a in resolved.items() if r != ORCHESTRATOR and a["enabled"]]
    rows = ["| Level | When | " + " | ".join(resolved[r]["name"] for r in roles) + " |",
            "|---|---|" + "---|" * len(roles)]
    for lvl, spec in levels.items():
        cells = [f"`{spec['roles'][r]['name']}` ({short_model(spec['roles'][r]['model'])})"
                 for r in roles if r in spec["roles"]]
        rows.append(f"| **{lvl}** | {spec['when']} | " + " | ".join(cells) + " |")
    default = routing.get("default_level", "")
    if cfg["jev"]["enabled"]:
        rule = ("1. Ask the JEV decision layer for the agent, model and effort of each task. Its answer "
                "must be a subagent from the table below (effort is fixed per subagent file). If it "
                "gives no valid answer, fall back to rule 2.")
    else:
        rule = ("1. JEV is disabled, so **you** choose: this is a cost decision, make it on every "
                "delegation. A simple demand does not need a strong model or a high effort.")
    return "\n".join([
        "## Model and effort per task", "",
        rule,
        "2. Classify the demand in the plan with one level from the table and why "
        f"(`Nível: <level> — <reason>`); if unsure, use **{default}**. A ticket may take another "
        "level when its own scope clearly fits it — write that in the ticket.",
        "3. Delegate to the subagent the table gives for that level and role. Do not pass `model` in "
        "the `Agent` call: each subagent already pins its model and effort.",
        "4. Escalate one level for the next attempt of a role when it failed the same step twice, "
        "when a review finds a CRITICO, or when a result shows the task is harder than classified.",
        "5. Record every delegation in `metricas.md` in the demand folder: agent, level, "
        "model/effort and the **real** usage from the completion notification (tokens, tool uses, "
        "duration). Never estimate tokens; those numbers are the evidence to tune these levels.",
        "", *rows,
    ])


def codex_delegation_section(resolved: dict, levels: dict, routing: dict) -> str:
    roles = [r for r, a in resolved.items() if r != ORCHESTRATOR and a["enabled"]]
    rows = ["| Level | When | " + " | ".join(f"{resolved[r]['name']} (`--role {r}`)" for r in roles) + " |",
            "|---|---|" + "---|" * len(roles)]
    for lvl, spec in levels.items():
        cells = [short_model(spec["roles"][r]["model"]) for r in roles if r in spec["roles"]]
        rows.append(f"| **{lvl}** | {spec['when']} | " + " | ".join(cells) + " |")
    default = routing.get("default_level", "padrao")
    return "\n".join([
        "## How to delegate (Codex runtime)", "",
        "You run in the Codex CLI. The agents are Claude Code agents run headless, one process per task:",
        "",
        "```",
        "python aidev.py delegate --role <role> --level <level> --task <task.md> --demand <demand dir> "
        "[--label <ticket>-r<N>]",
        "```",
        "",
        "- Write the task to a file first (`tarefa-<agente>-<assunto>.md` in the demand folder): SPEC + "
        "TICKET + files in scope with `file:line` + the build/test command + the paths of the diff, "
        "plan and previous review. Never paste large inputs into the command.",
        "- The command prints one JSON line: `state`, `output` (the agent's final JSON), `result_file`, "
        "`permission_denials`, tokens, cost and duration. Decide the next step from `state` "
        "(`routing.toml`). The full answer is in `result_file` — read it only when needed.",
        "- Usage is appended to `metricas.md` in the demand folder automatically; do not estimate it.",
        "- `permission_denials` lists what the agent tried and was not allowed (locked actions such as "
        "commit or SQL writes): treat them as proposals for the user, never retry them another way.",
        "- Never call `claude` directly and never pass `--model`/`--effort` yourself: the level decides.",
        "- Independent tickets may run in parallel (separate commands); tickets on the same files run in "
        "sequence. Each call is a fresh agent — a new review round is a new call.",
        "- There is no `Explore` subagent here: for broad code exploration delegate a read-only task to "
        "`--role coder --level simples` asking for `file:line` pointers, or read short excerpts yourself.",
        "- Skills of the orchestrator (`to-spec`, `to-tickets`, `codebase-context`): read "
        "`skills/<name>/SKILL.md` and follow it when the flow says to use it.",
        "",
        "## Model and effort per task", "",
        "1. Classify the demand in the plan with one level (`Nível: <level> — <reason>`); if unsure, "
        f"use **{default}**. A ticket may take another level when its own scope clearly fits it.",
        "2. Escalate one level for the next attempt of a role when it failed the same step twice, when a "
        "review finds a CRITICO, or when a result shows the task is harder than classified.",
        "3. With the JEV configured, ask it for role, level (model/effort) and MCPs before each delegation; "
        "this table is the fallback.",
        "", *rows,
    ])


def render_root_claude_md(resolved: dict, cfg: dict, catalog: dict, ctx: dict | None,
                          tpl: Templater, servers: dict, levels: dict, routing: dict,
                          runtime: str = "claude") -> str:
    orch = resolved[ORCHESTRATOR]
    codex = runtime == "codex"
    team = ["| Subagent (name) | Role | Model | Skills | Status |", "|---|---|---|---|---|"]
    for role, a in resolved.items():
        if role == ORCHESTRATOR:
            continue
        status = "enabled" if a["enabled"] else "disabled — do not delegate"
        team.append(f"| `{a['name']}` | {role} | {a['model']['name']} (`{short_model(a['model'])}`) | "
                    f"{', '.join(a['skills'])} | {status} |")

    orch_model = catalog.get(cfg["codex"]["model"], {"name": cfg["codex"]["model"]}) if codex else orch["model"]
    orch_label = (f"{orch_model['name']} (`{orch_model.get('model_id', '?')}`, effort "
                  f"{cfg['codex'].get('effort', '?')}) in the Codex CLI" if codex
                  else model_label(ORCHESTRATOR, orch_model))
    team_intro = ("Delegate with `python aidev.py delegate --role <role>` (next section); the model below "
                  "is the default level." if codex else
                  "Call subagents by the name in the first column (`subagent_type`). This is the "
                  "default level; the next section picks the variant for each task.")
    parts = [
        f"<!-- {GENERATED_MARK} apply — não edite. Fontes: orchestrator/CLAUDE.md, "
        "orchestrator/policies/ e o contexto ativo; rode `python aidev.py apply` após alterá-las. -->",
        "" if codex else ("> **Subagents:** if you were invoked as a subagent, ignore this file and "
                          "follow only your own agent definition."),
        tpl.include(ORCHESTRATOR_MD),
        "\n".join([
            "## Runtime", "",
            f"- You are `{orch['name']}` (role `orchestrator`), the main chat.",
            f"- Orchestrator model: {orch_label}",
            f"- Model mode: **{cfg['models']['mode']}**",
            f"- Orchestrator skills: {', '.join(f'`{s}`' for s in orch['skills'])}",
            *runtime_lines(cfg, catalog, ctx)]),
        "\n".join(["## Team", "", team_intro, "", *team]),
        codex_delegation_section(resolved, levels, routing) if codex
        else levels_section(levels, resolved, cfg, routing),
        mcp_orchestrator_section(servers, resolved, cfg),
        systems_section(ctx, detailed=False),
        "# Policies",
        *[tpl.include(p) for p in policy_files(ctx)],
    ]
    parts = [x for x in parts if x]
    if context_files(ctx, ORCHESTRATOR):
        parts.append(f"# Context: {ctx['description']}")
        parts += [tpl.include(p) for p in context_files(ctx, ORCHESTRATOR)]
    return "\n\n".join(parts) + "\n"


def is_link(p: Path) -> bool:
    return p.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(p))


def make_link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if not IS_WINDOWS:
        os.symlink(target, link, target_is_directory=True)
        return
    # Junction: não exige admin nem modo desenvolvedor no Windows.
    try:
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    except (ImportError, AttributeError, OSError):
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                       check=True, capture_output=True)


def remove_link(p: Path) -> None:
    # Remove só o link; o diretório de destino não é tocado.
    if IS_WINDOWS:
        os.rmdir(p)
    else:
        p.unlink()


def sync_skill_links(desired: dict[str, Path], dry: bool, rep: Report) -> None:
    desired = dict(desired)
    if LINKED_SKILLS_DIR.is_dir():
        for entry in LINKED_SKILLS_DIR.iterdir():
            if not is_link(entry):
                if entry.name in desired:
                    rep.warn(f"{rel(entry)} é um diretório real; não será substituído por link")
                    desired.pop(entry.name)
                continue
            target = desired.get(entry.name)
            if target and Path(os.path.realpath(entry)) == target.resolve():
                desired.pop(entry.name)
                continue
            if dry:
                rep.info(f"(dry-run) remover link .claude/skills/{entry.name}")
            else:
                remove_link(entry)
                rep.ok(f"removido link .claude/skills/{entry.name}")
    for name, target in desired.items():
        if dry:
            rep.info(f"(dry-run) linkar .claude/skills/{name} -> {rel(target)}")
        else:
            make_link(LINKED_SKILLS_DIR / name, target)
            rep.ok(f"linkado .claude/skills/{name} -> {rel(target)}")


def sync_subagents(files: dict[str, str], dry: bool, rep: Report) -> None:
    for name, content in files.items():
        write_if_changed(SUBAGENTS_DIR / f"{name}.md", content, dry, rep)
    if SUBAGENTS_DIR.is_dir():
        for f in SUBAGENTS_DIR.glob("*.md"):
            if f.stem not in files and GENERATED_MARK in f.read_text(encoding="utf-8"):
                if dry:
                    rep.info(f"(dry-run) remover {rel(f)}")
                else:
                    f.unlink()
                    rep.ok(f"removido {rel(f)} (agente renomeado, desabilitado ou removido)")


def merge_list(existing: list, previously_managed: list, managed: list) -> list:
    kept = [x for x in existing if x not in previously_managed]
    return kept + [x for x in managed if x not in kept]


def sync_settings(managed: dict, previous: dict, dry: bool, rep: Report) -> None:
    """Atualiza só as chaves que o apply gerencia; o resto do arquivo é preservado."""
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8")) if SETTINGS_FILE.exists() else {}
    except json.JSONDecodeError:
        rep.error(f"{rel(SETTINGS_FILE)} não é JSON válido; corrija ou apague o arquivo")
        return
    data["model"] = managed["model"]
    if managed["effortLevel"]:
        data["effortLevel"] = managed["effortLevel"]
    elif data.get("effortLevel") == previous.get("effortLevel"):
        data.pop("effortLevel", None)

    perms = data.setdefault("permissions", {})
    for key in ("allow", "ask", "deny", "additionalDirectories"):
        merged = merge_list(perms.get(key, []), previous.get(key, []), managed[key])
        if merged:
            perms[key] = merged
        else:
            perms.pop(key, None)
    if not perms:
        data.pop("permissions")

    # Servidores do .mcp.json pré-aprovados (sem o prompt de confiança do escopo de projeto).
    approved = merge_list(data.get("enabledMcpjsonServers", []),
                          previous.get("enabledMcpjsonServers", []), managed["enabledMcpjsonServers"])
    if approved:
        data["enabledMcpjsonServers"] = approved
    else:
        data.pop("enabledMcpjsonServers", None)

    env = data.setdefault("env", {})
    for k, v in previous.get("env", {}).items():
        if k not in managed["env"] and env.get(k) == v:
            env.pop(k)
    env.update(managed["env"])
    if not env:
        data.pop("env")
    write_if_changed(SETTINGS_FILE, json.dumps(data, indent=2, ensure_ascii=False) + "\n", dry, rep)


def check_workflows(resolved: dict, skills: dict, rep: Report) -> None:
    for wf in sorted(WORKFLOWS_DIR.glob("*.yaml")):
        text = wf.read_text(encoding="utf-8")
        for agent in sorted(set(re.findall(r"^\s*agent:\s*([\w-]+)", text, re.M))):
            if agent not in resolved:
                rep.warn(f"{rel(wf)}: agente desconhecido {agent!r}")
            elif not resolved[agent]["enabled"]:
                rep.info(f"{rel(wf)}: etapa do agente {agent!r} será pulada (desabilitado)")
        for skill in sorted(set(re.findall(r"^\s*skill:\s*([\w-]+)", text, re.M))):
            if skill not in skills:
                rep.warn(f"{rel(wf)}: skill desconhecida {skill!r}")


def sync_mcp_json(servers: dict, previous: list, dry: bool, rep: Report) -> None:
    """Mantém no .mcp.json os servidores habilitados; servidores adicionados à mão são preservados."""
    try:
        data = json.loads(MCP_JSON.read_text(encoding="utf-8")) if MCP_JSON.exists() else {}
    except json.JSONDecodeError:
        rep.error(f"{rel(MCP_JSON)} não é JSON válido; corrija ou apague o arquivo")
        return
    entries = data.setdefault("mcpServers", {})
    for key in previous:
        if key not in servers:
            entries.pop(key, None)
    for key, s in servers.items():
        entries[key] = mcp_json_entry(s)
    write_if_changed(MCP_JSON, json.dumps(data, indent=2, ensure_ascii=False) + "\n", dry, rep)


def previous_managed() -> dict:
    try:
        return json.loads(RUNTIME_FILE.read_text(encoding="utf-8")).get("managed_settings", {})
    except (OSError, json.JSONDecodeError):
        return {}


def apply(cfg: dict, catalog: dict, dry: bool) -> bool:
    heading("Validando configuração" + (" (dry-run)" if dry else ""))
    rep = Report()
    ctx = load_context(cfg, rep)
    skills = available_skills(ctx, rep)
    resolved = resolve(cfg, catalog, ctx, skills, rep)
    routing = load_routing(rep)
    levels = resolve_levels(routing, cfg, catalog, resolved, rep)
    check_workflows(resolved, skills, rep)
    servers = resolve_mcp(cfg, list(resolved), rep)
    if not rep.errors:
        # Gera tudo antes de gravar qualquer coisa: marcador inválido aborta sem meio-termo.
        tpl = Templater(resolved, rep)
        subagents = {a["name"]: render_subagent(role, a, cfg, catalog, ctx, tpl, servers, routing)
                     for role, a in resolved.items() if role != ORCHESTRATOR and a["enabled"]}
        taken = {a["name"] for a in resolved.values()} | BUILTIN_AGENT_NAMES
        for lvl, spec in levels.items():
            for role, v in spec["roles"].items():
                if v["name"] in subagents:
                    continue
                if v["name"] in taken:
                    rep.error(f"nível {lvl}: nome de variante {v['name']!r} colide com outro agente")
                    continue
                subagents[v["name"]] = render_subagent(role, resolved[role], cfg, catalog, ctx, tpl,
                                                       servers, routing, {**v, "level": lvl})
        root_md = render_root_claude_md(resolved, cfg, catalog, ctx, tpl, servers, levels, routing)
        agents_md = (render_root_claude_md(resolved, cfg, catalog, ctx, tpl, servers, levels, routing,
                                           runtime="codex") if cfg["codex"]["enabled"] else None)
    if rep.errors:
        print("\nCorrija os erros acima e rode novamente.")
        return False
    rep.ok("configuração válida" + (f" (contexto: {ctx['name']})" if ctx else ""))

    heading("Estado")
    sdir = state_dir(ctx)
    for d in [sdir] if ctx else [sdir / s for s in ("specs", "tickets", "reviews", "runs")]:
        ensure_dir(d, dry, rep)

    heading("Skills (.claude/skills)")
    sync_skill_links(skills, dry, rep)

    heading("Subagentes (.claude/agents)")
    sync_subagents(subagents, dry, rep)
    for role, a in resolved.items():
        if a["name"] in subagents:
            rep.info(f"{a['name']:<13} {role:<11} {short_model(a['model']):<14} "
                     f"~{len(subagents[a['name']]) // 3:,} tokens de instruções")
    for lvl, spec in levels.items():
        variants = [f"{v['name']} ({short_model(v['model'])})" for v in spec["roles"].values()]
        rep.info(f"nível {lvl}: {', '.join(variants)}")

    heading("Orquestrador (CLAUDE.md + .claude/settings.local.json)")
    write_if_changed(ROOT_CLAUDE_MD, root_md, dry, rep)
    if agents_md:
        write_if_changed(ROOT_AGENTS_MD, agents_md, dry, rep)
        rep.info(f"Codex: AGENTS.md para o orquestrador em {cfg['codex']['model']} "
                 "(abra `codex` na raiz do AI-DEV)")
    elif ROOT_AGENTS_MD.exists() and GENERATED_MARK in ROOT_AGENTS_MD.read_text(encoding="utf-8"):
        if not dry:
            ROOT_AGENTS_MD.unlink()
        rep.ok("removido AGENTS.md (codex desabilitado)")
    orch_model = resolved[ORCHESTRATOR]["model"]
    ctx_perms = ctx.get("permissions", {}) if ctx else {}
    managed = {
        "model": orch_model["model_id"],
        "effortLevel": orch_model.get("effort", ""),
        "allow": list(dict.fromkeys([*ctx_perms.get("allow", []),
                                     *[f"mcp__{k}" for k, s in servers.items() if s.get("allow")]])),
        "enabledMcpjsonServers": list(servers),
        "ask": list(dict.fromkeys([*cfg["policies"]["ask"], *ctx_perms.get("ask", []),
                                   *expand_git_ask(ctx_perms.get("git_ask", []))])),
        "deny": list(dict.fromkeys([*cfg["policies"]["deny"], *ctx_perms.get("deny", [])])),
        "additionalDirectories": project_dirs(cfg, ctx),
        "env": dict(ctx.get("env", {})) if ctx else {},
    }
    sync_settings(managed, previous_managed(), dry, rep)

    heading("MCP (.mcp.json)")
    sync_mcp_json(servers, previous_managed().get("enabledMcpjsonServers", []), dry, rep)
    for key, s in servers.items():
        roles = ", ".join(s.get("agents", [])) or "todos"
        extra = " · autenticar com /mcp" if s.get("auth") == "oauth" else ""
        rep.info(f"{key:<16} {s['type']:<6} agentes: {roles}{extra}")

    heading("Runtime")
    runtime = {
        "generated_by": "aidev.py apply",
        "root": ROOT.as_posix(),
        "model_mode": cfg["models"]["mode"],
        "context": ctx["name"] if ctx else None,
        "state_dir": sdir.as_posix(),
        "decision_layer": {
            "engine": "jev" if cfg["jev"]["enabled"] else "deterministic",
            "jev_model": catalog.get(cfg["jev"]["model"]) if cfg["jev"]["enabled"] else None,
            "max_retries": routing.get("max_retries", 3),
            "rules": routing.get("rules", {}),
            "default_level": routing.get("default_level"),
            "levels": {lvl: {"when": spec["when"],
                             "agents": {r: {"name": v["name"], "model_key": v["model_key"]}
                                        for r, v in spec["roles"].items()}}
                       for lvl, spec in levels.items()},
        },
        "agents": {role: {k: a[k] for k in ("name", "enabled", "skills", "model_key", "model")}
                   for role, a in resolved.items()},
        "mcp": servers,
        "managed_settings": managed,
    }
    write_if_changed(RUNTIME_FILE, json.dumps(runtime, indent=2, ensure_ascii=False) + "\n", dry, rep)

    print(f"\nConcluído{' (nada foi alterado: dry-run)' if dry else ''}"
          f"{f' com {len(rep.warnings)} aviso(s)' if rep.warnings else ''}.")
    return True


# ---------------------------------------------------------------------------
# Delegate (orquestrador fora do Claude Code → agente Claude headless)
# ---------------------------------------------------------------------------

def final_json(text: str) -> dict | None:
    """Último objeto JSON da resposta do agente (bloco ```json ou o último {...} parseável)."""
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = blocks[::-1] or []
    starts = [m.start() for m in re.finditer(r"\{", text)]
    candidates += [text[i:] for i in reversed(starts)]
    decoder = json.JSONDecoder()
    for c in candidates:
        try:
            obj, _ = decoder.raw_decode(c.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def append_metrics(demand: Path, row: dict) -> None:
    f = demand / "metricas.md"
    header = ("| Data | Agente | Nível | Modelo | Label | State | Turnos | Duração | Tokens entrada (soma dos turnos, com cache) | "
              "Tokens saída | Custo (USD, estimado) |\n|---|---|---|---|---|---|---|---|---|---|---|\n")
    line = ("| {date} | {agent} | {level} | {model} | {label} | {state} | {turns} | {duration_s}s | "
            "{tokens_in:,} | {tokens_out:,} | {cost_usd:.4f} |\n").format(**row)
    if not f.exists():
        f.write_text("# Métricas da demanda\n\nConsumo real de cada delegação (gravado por "
                     "`aidev.py delegate`).\n\n" + header, encoding="utf-8", newline="\n")
    with f.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(line)


def delegate(cfg: dict, catalog: dict, args: argparse.Namespace) -> int:
    rep = Report()
    ctx = load_context(cfg, rep)
    resolved = resolve(cfg, catalog, ctx, available_skills(ctx, rep), rep)
    routing = load_routing(rep)
    levels = resolve_levels(routing, cfg, catalog, resolved, rep)
    agent = resolved.get(args.role)
    if agent is None or args.role == ORCHESTRATOR or not agent["enabled"]:
        rep.error(f"papel {args.role!r} inexistente, desabilitado ou é o orquestrador")
    level = args.level or routing.get("default_level", "")
    if levels and level not in levels:
        rep.error(f"nível {level!r} não existe (válidos: {', '.join(levels)})")
    task, demand = Path(args.task).resolve(), Path(args.demand).resolve()
    if not task.is_file():
        rep.error(f"arquivo da tarefa não existe: {task}")
    claude = shutil.which("claude")
    if not claude:
        rep.error("CLI `claude` não encontrado no PATH")
    if rep.errors:
        print(json.dumps({"state": "environment_blocked", "error": "; ".join(rep.errors)}, ensure_ascii=False))
        return 2

    model = levels[level]["roles"][args.role]["model"] if levels else agent["model"]
    label = args.label or task.stem
    prompt = (f"Sua tarefa está no arquivo `{task.as_posix()}`: leia e execute. Pasta da demanda: "
              f"`{demand.as_posix()}`. Nível desta tarefa: {level or '—'} ({model['name']}, effort "
              f"{model.get('effort', 'padrão do modelo')}); vale sobre o modelo citado no Runtime. "
              "Termine com o JSON da seção OUTPUT da sua definição, com `state`.")
    # Sem o CLAUDE.md do orquestrador: com --agent o agente é a sessão principal e o carregaria.
    settings = {"claudeMdExcludes": [ROOT_CLAUDE_MD.as_posix(), str(ROOT_CLAUDE_MD)]}
    cmd = [claude, "-p", prompt, "--agent", agent["name"], "--model", model["alias"],
           "--output-format", "json", "--settings", json.dumps(settings),
           "--permission-mode", DELEGATE_PERMISSION.get(args.role, "default"),
           "--max-turns", str(args.max_turns or DELEGATE_MAX_TURNS.get(args.role, 40))]
    if model.get("effort"):
        cmd += ["--effort", model["effort"]]
    demand.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=args.timeout)
    except subprocess.TimeoutExpired:
        print(json.dumps({"state": "implementation_failed", "error": f"timeout de {args.timeout}s"}))
        return 1
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(json.dumps({"state": "environment_blocked", "error": "saída do claude não é JSON",
                          "stderr": proc.stderr[-800:]}, ensure_ascii=False))
        return 1

    result = data.get("result") or ""
    base = f"resultado-{agent['name']}-{label}"
    (demand / f"{base}.md").write_text(result, encoding="utf-8", newline="\n")
    (demand / f"{base}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                         encoding="utf-8", newline="\n")
    output = final_json(result)
    state = (output or {}).get("state") or ("implementation_failed" if data.get("is_error") else "missing_state")
    u = data.get("usage", {})
    row = {"date": date.today().isoformat(), "agent": agent["name"], "level": level or "—",
           "model": short_model(model), "label": label, "state": state,
           "turns": data.get("num_turns", 0), "duration_s": round(data.get("duration_ms", 0) / 1000),
           "tokens_in": u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                        + u.get("cache_read_input_tokens", 0),
           "tokens_out": u.get("output_tokens", 0), "cost_usd": data.get("total_cost_usd", 0.0)}
    append_metrics(demand, row)
    denials = [d.get("tool_name", "?") for d in data.get("permission_denials", [])]
    print(json.dumps({**row, "output": output, "result_file": (demand / f"{base}.md").as_posix(),
                      "permission_denials": denials, "session_id": data.get("session_id"),
                      "is_error": data.get("is_error", False)}, ensure_ascii=False))
    return 0 if not data.get("is_error") else 1


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------

def run(cmd: list[str], cwd: Path = ROOT) -> str | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=cwd).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def version_tuple(text: str) -> tuple[int, ...]:
    match = re.search(r"\d+(?:\.\d+)+", text)
    return tuple(int(x) for x in match.group().split(".")) if match else ()


def env_defined(name: str) -> bool:
    if os.environ.get(name):
        return True
    if IS_WINDOWS:  # variável de usuário definida depois que este terminal abriu
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                return bool(winreg.QueryValueEx(key, name)[0])
        except OSError:
            return False
    return False


def mcp_signature(command_or_url: str) -> str:
    """Identidade de um servidor para achar duplicatas: a URL, ou o pacote npm sem versão."""
    for token in command_or_url.split():
        if token.startswith(("http://", "https://")):
            return token.rstrip("/")
        if not token.startswith("-") and token not in ("npx", "cmd", "/c"):
            return re.sub(r"(?<=.)@[^/@]*$", "", token)
    return command_or_url


def check_mcp(cfg: dict, ctx: dict | None, rep: Report) -> None:
    project = resolve_mcp(cfg, list(cfg["agents"]), Report())
    required = ctx.get("required_mcp", []) if ctx else []
    if not project and not required:
        return
    if any(s["type"] == "stdio" and s["command"] == "npx" for s in project.values()) \
            and not shutil.which("npx"):
        rep.error("npx não encontrado — os MCPs locais precisam do Node.js (instale o Node LTS)")
    servers = list_mcp_servers() if shutil.which("claude") else None
    if servers is None:
        rep.warn("não foi possível rodar `claude mcp list`; MCPs não verificados")
        return

    for key, s in project.items():
        server = servers.get(key)
        if server is None:
            rep.warn(f"MCP {key} (padrão do AI-DEV) não aparece em `claude mcp list` — rode `apply` "
                     "e abra o Claude Code na raiz do AI-DEV")
        elif "connected" in server["status"].lower():
            rep.ok(f"MCP {key} conectado")
        elif "disabled" in server["status"].lower():
            rep.warn(f"MCP {key} está desativado neste projeto — reative no Claude Code com /mcp")
        elif s.get("auth") == "oauth":
            rep.warn(f"MCP {key} precisa de autenticação: no Claude Code, /mcp → {key} → Authenticate")
        else:
            rep.warn(f"MCP {key} com status {server['status']!r}")
        mine = mcp_signature(s.get("url") or " ".join([s["command"], *s.get("args", [])]))
        twins = [n for n, o in servers.items() if n != key and mcp_signature(o["command"]) == mine
                 and "disabled" not in o["status"].lower()]
        if twins:
            rep.info(f"MCP {key} também está registrado como {', '.join(repr(t) for t in twins)} "
                     "— as ferramentas aparecem em dobro; considere remover um deles")

    hints = ctx.get("mcp", {}) if ctx else {}
    for name in required:
        server = servers.get(name)
        if server is None:
            hint = hints.get(name, {}).get("add") or f"claude mcp add --scope user {name} -- <comando>"
            rep.warn(f"MCP {name!r} não registrado (exigido pelo contexto {ctx['name']}). Registre com:\n"
                     f"            {hint}")
        elif "connected" in server["status"].lower():
            rep.ok(f"MCP {name} conectado (exigido pelo contexto)")
        else:
            rep.warn(f"MCP {name} registrado, mas com status {server['status']!r}")


def doctor(cfg: dict, catalog: dict) -> bool:
    heading("Doctor")
    rep = Report()
    rep.ok(f"Python {sys.version.split()[0]}")

    if shutil.which("git"):
        rep.ok(run(["git", "--version"]) or "git")
        if not run(["git", "config", "user.email"]):
            rep.warn("git user.email não configurado")
    else:
        rep.error("git não encontrado no PATH")

    if shutil.which("claude"):
        version = run(["claude", "--version"]) or ""
        rep.ok(f"Claude Code {version}".strip())
        orch = catalog.get(cfg["models"]["default"] if cfg["models"]["mode"] == "single"
                           else cfg["agents"][ORCHESTRATOR]["model"], {})
        needed = orch.get("min_claude_code")
        if needed and version_tuple(version) < version_tuple(needed):
            rep.warn(f"o CLI `claude` do terminal é {version.split()[0]}; {orch['name']} exige {needed}+ "
                     "(rode `claude update`; o app desktop atualiza sozinho)")
    else:
        rep.error("Claude Code (`claude`) não encontrado — é ele que executa todos os agentes")

    if cfg["codex"]["enabled"]:
        if shutil.which("codex"):
            rep.ok(run(["codex", "--version"]) or "codex")
            try:  # `codex login status` escreve no stderr
                p = subprocess.run(["codex", "login", "status"], capture_output=True, text=True, cwd=ROOT)
                status = (p.stdout + p.stderr).strip()
            except OSError:
                status = ""
            if "Logged in" in status:
                rep.ok(f"Codex: {status.splitlines()[0]}")
            else:
                rep.warn("Codex sem login — rode `codex login`")
            model_id = catalog.get(cfg["codex"]["model"], {}).get("model_id", cfg["codex"]["model"])
            try:
                cache = json.loads((Path.home() / ".codex" / "models_cache.json").read_text(encoding="utf-8"))
                allowed = {m.get("slug") for m in cache.get("models", [])}
            except (OSError, json.JSONDecodeError):
                allowed = set()
            if allowed and model_id not in allowed:
                rep.warn(f"Codex: o modelo {model_id} não está liberado para esta conta "
                         f"(disponíveis: {', '.join(sorted(a for a in allowed if a))})")
            elif allowed:
                rep.ok(f"Codex: modelo {model_id} liberado para a conta")
        else:
            rep.error("[codex] habilitado, mas o CLI `codex` não está no PATH")

    ctx = load_context(cfg, rep)
    if ctx:
        if (ctx["dir"] / ".git").exists():
            rep.ok(f"contexto {ctx['name']}: repositório Git próprio")
        else:
            rep.warn(f"contexto {ctx['name']}: {rel(ctx['dir'])} não é um repositório Git")
        if run(["git", "rev-parse", "--is-inside-work-tree"]) is None:
            rep.info("o AI-DEV não é um repositório Git; checagem do .gitignore pulada")
        elif run(["git", "check-ignore", "-q", rel(ctx["dir"])]) is None:
            rep.error(f"{rel(ctx['dir'])} NÃO está no .gitignore do AI-DEV (conteúdo interno vazaria)")
        else:
            rep.ok(f"{rel(ctx['dir'])} ignorado pelo Git do AI-DEV")
        for var in ctx.get("required_env", []):
            if env_defined(var):
                rep.ok(f"variável {var} definida")
            else:
                rep.warn(f"variável {var} não definida (necessária para o contexto {ctx['name']})")
    else:
        rep.info("sem contexto de trabalho ativo")
    check_mcp(cfg, ctx, rep)

    dirs = project_dirs(cfg, ctx)
    if not dirs:
        rep.info("nenhuma pasta de projetos configurada ([workspace].project_dirs)")
    for d in dirs:
        if Path(d).is_dir():
            rep.ok(f"pasta liberada {d}")
        else:
            rep.warn(f"pasta liberada {d} não existe")

    if not RUNTIME_FILE.exists() or not ROOT_CLAUDE_MD.exists():
        rep.warn("ambiente ainda não gerado — rode `python aidev.py apply`")

    print(f"\n{len(rep.errors)} erro(s), {len(rep.warnings)} aviso(s).")
    return not rep.errors


# ---------------------------------------------------------------------------
# Show / CLI
# ---------------------------------------------------------------------------

def show(cfg: dict, catalog: dict) -> None:
    rep = Report()
    ctx = load_context(cfg, rep)
    resolved = resolve(cfg, catalog, ctx, available_skills(ctx, rep), rep)
    heading(f"AI-DEV · modo {cfg['models']['mode']} · contexto {ctx['name'] if ctx else 'nenhum'}")
    print(f"  {'NOME':<14} {'PAPEL':<13} {'MODELO':<26} TIPO")
    for role, a in resolved.items():
        kind = "chat" if role == ORCHESTRATOR else f"subagente ({a['model'].get('alias', '?')})"
        status = "" if a["enabled"] else "  (desabilitado)"
        print(f"  {a['name']:<14} {role:<13} {a['model']['name']:<26} {kind}{status}")
    print(f"\n  Decisão: {decision_label(cfg, catalog).replace('`', '')}")
    print(f"  Estado:  {state_dir(ctx).as_posix()}")


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(render_config(cfg), encoding="utf-8", newline="\n")
    print(f"\nGravado {rel(CONFIG_FILE)}.")


def main() -> int:
    # Console do Windows (cp1252) quebra em "→" e acentos; UTF-8 com substituição nunca falha.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Configuração do ambiente AI-DEV.")
    sub = parser.add_subparsers(dest="command")
    p_setup = sub.add_parser("setup", help="wizard (se necessário) + apply + doctor")
    p_setup.add_argument("--reconfigure", action="store_true", help="refaz o wizard mesmo com config existente")
    p_conf = sub.add_parser("configure", help="wizard interativo")
    p_conf.add_argument("--defaults", action="store_true", help="grava a config padrão sem perguntar")
    p_apply = sub.add_parser("apply", help="gera o ambiente a partir de aidev.config.toml")
    p_apply.add_argument("--dry-run", action="store_true", help="mostra o que mudaria, sem alterar nada")
    sub.add_parser("doctor", help="verifica pré-requisitos")
    sub.add_parser("show", help="mostra agentes e modelos resolvidos")
    p_del = sub.add_parser("delegate", help="roda um agente Claude headless para uma tarefa (orquestrador Codex)")
    p_del.add_argument("--role", required=True, help="papel: coder, reviewer, api-db, documenter, qa")
    p_del.add_argument("--level", help="nível da demanda ([levels] do routing.toml); padrão: default_level")
    p_del.add_argument("--task", required=True, help="arquivo .md com a tarefa")
    p_del.add_argument("--demand", required=True, help="pasta da demanda (resultado e metricas.md)")
    p_del.add_argument("--label", help="rótulo do resultado, ex.: t1-r1 (padrão: nome do arquivo da tarefa)")
    p_del.add_argument("--max-turns", type=int, help="limite de turnos do agente")
    p_del.add_argument("--timeout", type=int, default=3600, help="tempo máximo em segundos (padrão 3600)")
    args = parser.parse_args()
    command = args.command or "setup"

    catalog = load_catalog()
    cfg = load_config()

    if command == "configure":
        cfg = default_config() if args.defaults else wizard(cfg or default_config(), catalog)
        save_config(cfg)
        print("Próximo passo: python aidev.py apply")
        return 0

    if command == "setup":
        if cfg is None or getattr(args, "reconfigure", False):
            cfg = wizard(cfg or default_config(), catalog)
            if not confirm("\nGravar e aplicar esta configuração?", True):
                print("Nada foi gravado.")
                return 1
            save_config(cfg)
        elif context_missing(cfg):
            heading("Contexto não encontrado")
            ask_context(cfg, "")
            save_config(cfg)
        if not apply(cfg, catalog, dry=False):
            return 1
        return 0 if doctor(cfg, catalog) else 1

    if cfg is None:
        print("aidev.config.toml não encontrado. Rode `python aidev.py setup` ou `configure`.")
        return 1
    if command == "apply":
        return 0 if apply(cfg, catalog, dry=args.dry_run) else 1
    if command == "doctor":
        return 0 if doctor(cfg, catalog) else 1
    if command == "show":
        show(cfg, catalog)
        return 0
    if command == "delegate":
        return delegate(cfg, catalog, args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
