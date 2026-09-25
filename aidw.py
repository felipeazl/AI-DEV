#!/usr/bin/env python3
"""AiDW — ambiente de desenvolvimento agêntico com orquestrador e agentes especializados.

Uso:
    python aidw.py setup [--reconfigure]   # pré-requisitos + wizard + apply + doctor
    python aidw.py configure [--defaults]  # só o wizard; grava aidw.config.toml
    python aidw.py apply [--dry-run]       # gera o ambiente a partir da config (idempotente)
    python aidw.py doctor                  # verifica o ambiente
    python aidw.py show                    # agentes, nomes, modelos e efforts resolvidos
    python aidw.py chat                    # abre o orquestrador no CLI do provedor
    python aidw.py delegate --agent <papel|nome> --effort <e> --task <arq> --demand <pasta>

Um provedor por instalação ([provider].name): tudo roda no Claude Code ou tudo roda no Codex.
O chat aberto na raiz do AiDW é o orquestrador; cada agente roda headless, um processo por
tarefa, com o modelo do agente e o effort que o orquestrador escolher para aquela tarefa.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from datetime import date, datetime
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit("AiDW requer Python 3.11+ (usa tomllib).")

import tomllib

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "aidw.config.toml"
MODELS_FILE = ROOT / "config" / "models.toml"
MCP_CATALOG_FILE = ROOT / "config" / "mcp.toml"
ROUTING_FILE = ROOT / "orchestrator" / "config" / "routing.toml"
ORCHESTRATOR_MD = ROOT / "orchestrator" / "ORCHESTRATOR.md"
POLICIES_DIR = ROOT / "orchestrator" / "policies"
AGENTS_DIR = ROOT / "agents"
SKILLS_DIR = ROOT / "skills"
CONTEXTS_DIR = ROOT / "contexts"
WORKFLOWS_DIR = ROOT / "workflows"

GEN_DIR = ROOT / ".aidw"                       # gerado, independente do provedor
GEN_AGENTS_DIR = GEN_DIR / "agents"            # definição de cada agente (markdown)
CLAUDE_AGENTS_JSON = GEN_DIR / "claude-agents.json"
RUNTIME_FILE = GEN_DIR / "runtime.json"

# Claude Code
CLAUDE_MD = ROOT / "CLAUDE.md"
CLAUDE_SETTINGS = ROOT / ".claude" / "settings.local.json"
CLAUDE_SKILLS = ROOT / ".claude" / "skills"
CLAUDE_SUBAGENTS = ROOT / ".claude" / "agents"   # subagentes nativos (modo native)
MCP_JSON = ROOT / ".mcp.json"
# Codex
AGENTS_MD = ROOT / "AGENTS.md"
CODEX_CONFIG = ROOT / ".codex" / "config.toml"
CODEX_RULES = ROOT / ".codex" / "rules" / "aidw.rules"
CODEX_SUBAGENTS = ROOT / ".codex" / "agents"     # papéis nativos do Codex (modo native)
CODEX_SKILLS = ROOT / ".agents" / "skills"
CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
# O Codex corta o AGENTS.md em 32 KiB por padrão; o AiDW sobe o limite do orquestrador.
CODEX_DOC_MAX_BYTES = 98304

IS_WINDOWS = os.name == "nt"
GENERATED_MARK = "Gerado por aidw.py"
ORCHESTRATOR = "orchestrator"
PROVIDERS = ("claude", "codex")
PROVIDER_LABEL = {"claude": "Claude (Claude Code)", "codex": "Codex (Codex CLI)"}
# native   = subagentes nativos do provedor (Claude: ferramenta Agent; Codex: spawn_agent)
# headless = um processo do CLI por tarefa, via `aidw.py delegate`
DELEGATION_MODES = ("native", "headless")

ACTIONS = {"PLAN_REVIEW", "PLAN_FIX", "TICKETS", "IMPLEMENT", "TEST", "PREPARE_REVIEW", "REVIEW", "CODER_FIX", "DOCS",
           "FINAL_REVIEW", "DONE", "HUMAN_APPROVAL", "RETURN"}
EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_MCP = ["playwright", "chrome-devtools", "figma", "context7"]

DEFAULT_NAMES = {
    "orchestrator": "orquestrador",
    "coder": "codificador",
    "reviewer": "revisor",
    "api-db": "api",
    "qa": "qa",
    "documenter": "documentador",
    "bug-hunter": "bugs",
    "security": "seguranca",
}
# Opus no orquestrador e no codificador, Sonnet no api e no revisor, Haiku no documentador.
# No Codex o tier escolhe o equivalente (config/models.toml).
DEFAULT_AGENTS: dict[str, dict] = {
    "orchestrator": {"enabled": True, "tier": "top", "effort": "high",
                     "skills": ["to-spec", "to-tickets", "codebase-context"]},
    "coder": {"enabled": True, "tier": "top", "effort": "medium",
              "skills": ["implement-ticket", "debug", "testing", "codebase-context"]},
    "reviewer": {"enabled": True, "tier": "mid", "effort": "high", "skills": ["code-review"]},
    "api-db": {"enabled": True, "tier": "mid", "effort": "medium", "skills": ["database-safe", "debug"]},
    "qa": {"enabled": False, "tier": "mid", "effort": "medium", "skills": ["testing"]},
    "documenter": {"enabled": True, "tier": "fast", "effort": "medium", "skills": ["documentation"]},
    # Especialistas sob demanda: o orquestrador decide quando uma passada vale o custo.
    "bug-hunter": {"enabled": True, "tier": "mid", "effort": "high", "skills": ["bug-hunt"]},
    "security": {"enabled": True, "tier": "mid", "effort": "high", "skills": ["security-audit"]},
}
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]*$")
RESERVED_NAMES = {"general-purpose", "explore", "plan", "statusline-setup", "claude-code-guide",
                  "default", "worker", "explorer"}
PLACEHOLDER_RE = re.compile(r"\{\{agent:([\w-]+)\}\}")

# Execução headless de cada papel.
#   claude_mode: --permission-mode. `auto` roda a rotina e nega o que cairia em `ask` (commit,
#                push, sqlcmd…), que volta em permission_denials. O api fica em `default`: só o
#                que está no allow (validador SQL, git de leitura).
#   write:       onde o agente Codex pode escrever além da raiz do AiDW (que inclui o state dir).
#   network:     acesso de rede dos comandos do agente Codex (build com restore, APIs).
RUN_PROFILE = {
    "coder": {"claude_mode": "auto", "max_turns": 80, "write": "projects", "network": True},
    "reviewer": {"claude_mode": "auto", "max_turns": 40, "write": "state", "network": False},
    "documenter": {"claude_mode": "auto", "max_turns": 40, "write": "projects", "network": False},
    "qa": {"claude_mode": "auto", "max_turns": 40, "write": "state", "network": True},
    "api-db": {"claude_mode": "default", "max_turns": 30, "write": "state", "network": True},
    "bug-hunter": {"claude_mode": "auto", "max_turns": 50, "write": "state", "network": False},
    "security": {"claude_mode": "auto", "max_turns": 50, "write": "state", "network": False},
}

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
    def __init__(self, quiet: bool = False) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.quiet = quiet

    def _print(self, tag: str, msg: str) -> None:
        if not self.quiet:
            print(f"  {tag} {msg}")

    def ok(self, msg: str) -> None:
        self._print("[ok]   ", msg)

    def info(self, msg: str) -> None:
        self._print("[--]   ", msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
        self._print("[aviso]", msg)

    def error(self, msg: str) -> None:
        self.errors.append(msg)
        self._print("[erro] ", msg)


def heading(title: str) -> None:
    print(f"\n== {title} ==")


def rel(p: Path) -> str:
    """Caminho relativo à raiz, sem seguir links (junctions de skills mostram o próprio link)."""
    try:
        return Path(os.path.abspath(p)).relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def win(p: Path | str) -> str:
    """Caminho no formato do sistema (barras invertidas no Windows)."""
    return str(Path(p))


# ---------------------------------------------------------------------------
# Config, catálogo e contexto
# ---------------------------------------------------------------------------

def load_toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def load_catalog() -> dict[str, dict]:
    return load_toml(MODELS_FILE).get("models", {})


def load_mcp_catalog() -> dict[str, dict]:
    return load_toml(MCP_CATALOG_FILE).get("servers", {}) if MCP_CATALOG_FILE.exists() else {}


def codex_available_models() -> set[str]:
    try:
        cache = json.loads((CODEX_HOME / "models_cache.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {m.get("slug") for m in cache.get("models", []) if m.get("slug")}


def tier_model(catalog: dict, provider: str, tier: str) -> str | None:
    """Primeiro modelo do provedor com o tier; no Codex, só os liberados para a conta."""
    available = codex_available_models() if provider == "codex" else set()
    candidates = [k for k, m in catalog.items() if m.get("provider") == provider and tier in m.get("tiers", [])]
    for key in candidates:
        if not available or catalog[key]["model_id"] in available:
            return key
    return candidates[0] if candidates else None


def default_config(provider: str = "claude") -> dict:
    return {
        "provider": {"name": provider},
        "delegation": {"mode": "native"},
        "workspace": {"project_dirs": []},
        "mcp": {"enabled": list(DEFAULT_MCP)},
        "context": {"active": ""},
        "policies": {"deny": list(DEFAULT_DENY), "ask": []},
        "agents": json.loads(json.dumps({role: {k: v for k, v in a.items() if k != "tier"}
                                         for role, a in DEFAULT_AGENTS.items()})),
    }


def load_config() -> dict | None:
    if not CONFIG_FILE.exists():
        return None
    cfg = load_toml(CONFIG_FILE)
    base = default_config()
    for section in ("provider", "delegation", "workspace", "mcp", "context", "policies"):
        base[section].update(cfg.get(section, {}))
    if "agents" in cfg:
        base["agents"] = {}
        for role, a in cfg["agents"].items():
            defaults = {k: v for k, v in DEFAULT_AGENTS.get(role, {"enabled": True, "skills": []}).items()
                        if k != "tier"}
            base["agents"][role] = {**defaults, **a}
    return base


def slugify(text: str) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")


def agent_names(role: str, agent: dict) -> tuple[str, str]:
    """(slug, nome de exibição). O nome configurado pode ter acento e espaço; o slug é o
    identificador usado em comandos e arquivos."""
    raw = (agent.get("name") or "").strip() or DEFAULT_NAMES.get(role, role)
    slug = slugify(raw)
    if raw != slug:
        return slug, raw
    words = [w.upper() if len(w) <= 3 else w.capitalize() for w in raw.split("-")]
    return slug, " ".join(words)


def toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {toml_value(x)}" for k, x in v.items()) + " }"
    raise TypeError(f"tipo não suportado em TOML: {type(v)}")


def render_config(cfg: dict) -> str:
    out = [
        f"# Configuração do AiDW. {GENERATED_MARK} configure em {date.today().isoformat()}.",
        "# Pode editar à mão; depois rode `python aidw.py apply` e abra um chat novo.",
        "# Atenção: `configure` reescreve este arquivo (comentários próprios são perdidos).",
        "",
        "[provider]",
        '# "claude" = tudo no Claude Code · "codex" = tudo no Codex CLI. Um provedor por vez.',
        f"name = {toml_value(cfg['provider']['name'])}",
        "",
        "[delegation]",
        '# "native"   = subagentes nativos do provedor (Claude: ferramenta Agent; Codex: spawn_agent)',
        '# "headless" = um processo do CLI por tarefa, via `python aidw.py delegate`',
        f"mode = {toml_value(cfg['delegation']['mode'])}",
        "",
        "[workspace]",
        "# Pastas dos seus projetos. Liberadas para o orquestrador e todos os agentes.",
        f"project_dirs = {toml_value(cfg['workspace']['project_dirs'])}",
        "",
        "[mcp]",
        "# Servidores de config/mcp.toml registrados no projeto. O orquestrador decide quando usar.",
        f"enabled = {toml_value(cfg['mcp']['enabled'])}",
        "",
        "[context]",
        '# Pacote de regras de trabalho em contexts/<nome>/ ("" = nenhum).',
        f"active = {toml_value(cfg['context']['active'])}",
        "",
        "[policies]",
        "# deny = bloqueado sempre · ask = sempre pede confirmação (vence qualquer allow).",
        "# Sintaxe do Claude Code; no Codex, as regras de comando viram .codex/rules/aidw.rules.",
        "deny = [",
        *[f"    {toml_value(d)}," for d in cfg["policies"]["deny"]],
        "]",
        "ask = [",
        *[f"    {toml_value(d)}," for d in cfg["policies"]["ask"]],
        "]",
        "",
        "# [agents.<papel>] — o papel é fixo. Opcionais:",
        "#   name   nome do agente (aceita acento e espaço; sem ele, vale o padrão comentado)",
        "#   model  chave de config/models.toml do provedor; sem ele, vale o tier padrão do papel",
        "#          (Opus/top no orquestrador e codificador, Sonnet/mid no revisor e api,",
        "#           Haiku/fast no documentador). Modelo de outro provedor é ignorado com aviso.",
        "#   effort effort padrão do agente; o orquestrador escolhe o de cada tarefa (routing.toml).",
    ]
    for role, a in cfg["agents"].items():
        default = DEFAULT_NAMES.get(role, role)
        out += ["", f"[agents.{role}]",
                f"name = {toml_value(a['name'])}" if a.get("name") else f"# name = {toml_value(default)}",
                f"enabled = {toml_value(a['enabled'])}"]
        if a.get("model"):
            out.append(f"model = {toml_value(a['model'])}")
        if a.get("effort"):
            out.append(f"effort = {toml_value(a['effort'])}")
        out.append(f"skills = {toml_value(a.get('skills', []))}")
    return "\n".join(out) + "\n"


def list_contexts() -> list[str]:
    if not CONTEXTS_DIR.is_dir():
        return []
    return sorted(d.name for d in CONTEXTS_DIR.iterdir() if (d / "context.toml").exists())


def expand_vars(value, variables: dict[str, str]):
    """{{root}} e {{context}} nas strings do context.toml (caminhos no formato do sistema)."""
    if isinstance(value, str):
        for k, v in variables.items():
            value = value.replace("{{" + k + "}}", v)
        return value
    if isinstance(value, list):
        return [expand_vars(x, variables) for x in value]
    if isinstance(value, dict):
        return {k: expand_vars(x, variables) for k, x in value.items()}
    return value


def path_vars(ctx_dir: Path | None) -> dict[str, str]:
    variables = {"root": win(ROOT)}
    if ctx_dir:
        variables["context"] = win(ctx_dir)
    return variables


def load_context(cfg: dict, rep: Report) -> dict | None:
    name = cfg["context"]["active"]
    if not name:
        return None
    path = CONTEXTS_DIR / name / "context.toml"
    if not path.exists():
        rep.error(f"contexto {name!r} não encontrado ({rel(path)}): clone o repositório dele em "
                  f"contexts/{name}/ ou rode `setup` para escolher outro, criar um ou seguir sem")
        return None
    ctx = expand_vars(load_toml(path), path_vars(path.parent))
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


def context_missing(cfg: dict) -> bool:
    name = cfg["context"]["active"]
    return bool(name) and not (CONTEXTS_DIR / name / "context.toml").exists()


def state_dir(ctx: dict | None) -> Path:
    return ROOT / (ctx.get("state_dir", "state") if ctx else "state")


def project_dirs(cfg: dict, ctx: dict | None) -> list[str]:
    """Pastas liberadas: as do workspace (máquina) + as do contexto, sem repetição."""
    dirs = [*cfg["workspace"]["project_dirs"], *(ctx.get("additional_dirs", []) if ctx else [])]
    return list(dict.fromkeys(d.replace("\\", "/").rstrip("/") for d in dirs))


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


def context_files(ctx: dict | None, role: str) -> list[Path]:
    if not ctx:
        return []
    return [ctx["dir"] / inc for inc in ctx.get("agents", {}).get(role, {}).get("include", [])]


def policy_files(ctx: dict | None) -> list[Path]:
    files = sorted(POLICIES_DIR.glob("*.md"))
    if ctx and (ctx["dir"] / "policies").is_dir():
        files += sorted((ctx["dir"] / "policies").glob("*.md"))
    return files


def resolve(cfg: dict, catalog: dict, ctx: dict | None, skills: dict, rep: Report) -> dict[str, dict]:
    """Valida a config e devolve {papel: {name, display, model, effort, skills, enabled…}}."""
    provider = cfg["provider"]["name"]
    if provider not in PROVIDERS:
        rep.error(f"provider.name deve ser {' ou '.join(PROVIDERS)} (atual: {provider!r})")
        return {}
    for key, m in catalog.items():
        if m.get("provider") not in PROVIDERS:
            rep.error(f"config/models.toml: {key} com provider inválido {m.get('provider')!r}")
        for e in m.get("efforts", []):
            if e not in EFFORTS:
                rep.error(f"config/models.toml: effort inválido em {key}: {e!r}")

    if cfg["delegation"]["mode"] not in DELEGATION_MODES:
        rep.error(f"delegation.mode deve ser {' ou '.join(DELEGATION_MODES)} "
                  f"(atual: {cfg['delegation']['mode']!r})")
    agents = cfg["agents"]
    if ORCHESTRATOR not in agents or not agents[ORCHESTRATOR].get("enabled", True):
        rep.error("o agente orchestrator é obrigatório e precisa estar habilitado")

    resolved = {}
    for role, a in agents.items():
        key = a.get("model")
        if key and key not in catalog:
            rep.error(f"agente {role}: modelo {key!r} não existe em config/models.toml")
            continue
        if key and catalog[key]["provider"] != provider:
            fallback = tier_model(catalog, provider, DEFAULT_AGENTS.get(role, {}).get("tier", "mid"))
            rep.warn(f"agente {role}: {key!r} é do provedor {catalog[key]['provider']}; usando "
                     f"{fallback!r} (tire o `model` do aidw.config.toml ou escolha um de {provider})")
            key = fallback
        if not key:
            key = tier_model(catalog, provider, DEFAULT_AGENTS.get(role, {}).get("tier", "mid"))
        if not key:
            rep.error(f"agente {role}: nenhum modelo do provedor {provider} em config/models.toml")
            continue
        model = {**catalog[key], "key": key}
        effort = a.get("effort") or ""
        if effort and effort not in EFFORTS:
            rep.error(f"agente {role}: effort inválido {effort!r} (válidos: {', '.join(EFFORTS)})")
        if not model.get("efforts"):
            effort = ""
        elif effort and effort not in model["efforts"]:
            rep.error(f"agente {role}: {model['name']} não aceita effort {effort!r}")
        if a.get("enabled", True) and role != ORCHESTRATOR and not (AGENTS_DIR / role / "AGENT.md").exists():
            rep.error(f"agente {role}: agents/{role}/AGENT.md não existe")
        ctx_skills = ctx.get("agents", {}).get(role, {}).get("skills", []) if ctx else []
        all_skills = list(dict.fromkeys([*a.get("skills", []), *ctx_skills]))
        for s in all_skills:
            if s not in skills:
                rep.error(f"agente {role}: skill {s!r} não encontrada")
        slug, display = agent_names(role, a)
        resolved[role] = {"role": role, "enabled": a.get("enabled", True), "name": slug,
                          "display": display, "skills": all_skills, "model": model, "effort": effort}

    seen: dict[str, str] = {}
    for role, a in resolved.items():
        if not SLUG_RE.match(a["name"]):
            rep.error(f"agente {role}: nome {a['name']!r} inválido (precisa começar por letra)")
        elif a["name"] in RESERVED_NAMES:
            rep.error(f"agente {role}: nome {a['name']!r} é reservado pelo CLI")
        elif a["name"] in seen:
            rep.error(f"agentes {seen[a['name']]} e {role} têm o mesmo nome {a['name']!r}")
        seen.setdefault(a["name"], role)
    return resolved


def load_routing(rep: Report) -> dict:
    routing = load_toml(ROUTING_FILE) if ROUTING_FILE.exists() else {}
    for st, action in routing.get("rules", {}).items():
        if action not in ACTIONS:
            rep.error(f"routing.toml: ação desconhecida {action!r} em {st!r} "
                      f"(válidas: {', '.join(sorted(ACTIONS))})")
    eff = routing.get("effort", {})
    levels = eff.get("levels", {})
    for lvl, spec in levels.items():
        for role, value in spec.items():
            if role == "when":
                continue
            if role == "models":
                for r in value:
                    if r not in DEFAULT_AGENTS:
                        rep.error(f"routing.toml: [effort.levels.{lvl}.models] cita papel desconhecido {r!r}")
                continue
            if role not in DEFAULT_AGENTS:
                rep.error(f"routing.toml: [effort.levels.{lvl}] cita papel desconhecido {role!r}")
            elif value not in EFFORTS:
                rep.error(f"routing.toml: [effort.levels.{lvl}] {role} = {value!r} não é effort válido")
    if levels and eff.get("default_level") not in levels:
        rep.error(f"routing.toml: effort.default_level {eff.get('default_level')!r} não está em [effort.levels]")
    return routing


def effort_for(routing: dict, role: str, level: str, agent: dict) -> str:
    spec = routing.get("effort", {}).get("levels", {}).get(level, {})
    return spec.get(role) or agent["effort"]


def attach_variants(resolved: dict, routing: dict, catalog: dict, rep: Report) -> None:
    """Resolve, por papel, o modelo e o effort de cada nível (`a["by_level"]`) e as variantes
    nativas do Claude (`a["variants"]`: nome → modelo/effort). O modelo do nível vem de
    [effort.levels.<nível>.models] (exceção à regra de modelo fixo); sem ele, o do agente. O effort
    padrão com o modelo do agente fica com o nome base; outro effort vira `<nome>-<effort>` e outro
    modelo `<nome>-<alias>-<effort>` (o Claude fixa modelo e effort no arquivo do subagente)."""
    levels = routing.get("effort", {}).get("levels", {})
    for role, a in resolved.items():
        if role == ORCHESTRATOR:
            continue
        base = a["model"]
        by_level = {}
        for lvl, spec in levels.items():
            key = spec.get("models", {}).get(role)
            model = base
            if key:
                if key not in catalog:
                    rep.error(f"routing.toml: [effort.levels.{lvl}.models] {role} = {key!r} não existe em "
                              "config/models.toml")
                elif catalog[key]["provider"] != base["provider"]:
                    rep.warn(f"routing.toml: [effort.levels.{lvl}.models] {role} = {key!r} é de outro "
                             f"provedor; usando {base['key']!r}")
                else:
                    model = {**catalog[key], "key": key}
            effort = effort_for(routing, role, lvl, a) if model.get("efforts") else ""
            if effort and effort not in model["efforts"]:
                rep.error(f"routing.toml: [effort.levels.{lvl}] {model['name']} não aceita effort {effort!r}")
            by_level[lvl] = (model, effort)
        base_effort = a["effort"] if base.get("efforts") else ""
        pairs = [(base, base_effort), *by_level.values()]
        pairs.sort(key=lambda p: (p[0]["key"] != base["key"], p[0]["key"],
                                  EFFORTS.index(p[1]) if p[1] in EFFORTS else -1))
        variants: dict[str, dict] = {}
        for model, effort in pairs:
            if model["key"] == base["key"] and effort == base_effort:
                name = a["name"]
            elif model["key"] == base["key"]:
                name = f"{a['name']}-{effort}"
            else:
                name = "-".join(x for x in (a["name"], model.get("alias") or model["key"], effort) if x)
            variants.setdefault(name, {"model": model, "effort": effort})
        a["by_level"], a["variants"] = by_level, variants


def variant_name(a: dict, model: dict, effort: str) -> str:
    for name, v in a.get("variants", {}).items():
        if v["model"]["key"] == model["key"] and v["effort"] == effort:
            return name
    return a["name"]


def model_label(a: dict, effort: str | None = None) -> str:
    effort = a["effort"] if effort is None else effort
    e = f", effort {effort}" if effort and a["model"].get("efforts") else ""
    return f"{a['model']['name']} (`{a['model']['model_id']}`{e})"


def header(a: dict, effort: str) -> str:
    e = f" {effort.capitalize()}" if effort and a["model"].get("efforts") else ""
    return f"## {a['display']} - {a['model']['model_id']}{e}"


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


def split_answer(answer: str, sep: str = ",") -> list[str]:
    return [s.strip().strip("\"'") for s in answer.split(sep) if s.strip() and s.strip() != "-"]


def normalize_dir(path: str) -> str:
    p = os.path.expanduser(path).replace("\\", "/").rstrip("/")
    return p + "/" if re.fullmatch(r"[A-Za-z]:", p) else p


def ask_project_dirs(cfg: dict, step: str) -> None:
    print(f"{step} Pastas dos seus projetos — liberadas para o orquestrador e todos os agentes.")
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
        if not SLUG_RE.match(name):
            print("  Nome inválido.")
        elif (CONTEXTS_DIR / name).exists():
            print(f"  Já existe contexts/{name}/.")
        else:
            break
    description = ask("  Descrição (ex.: Empresa X — Squad Y)", name)
    required_env = split_answer(ask("  Variáveis de ambiente exigidas (vírgula, '-' = nenhuma)", "-"))
    required_mcp = split_answer(ask("  Servidores MCP exigidos (vírgula, '-' = nenhum)", "-"))
    d = create_context(name, description, required_mcp, required_env)
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
    options = ([("", "nenhum — só as regras genéricas do AiDW")] + [(c, c) for c in contexts]
               + [("+", "criar um novo contexto agora")])
    prefix = f"{step} " if step else ""
    choice = choose(f"{prefix}Contexto de trabalho (regras em contexts/<nome>/):", options, current)
    cfg["context"]["active"] = ask_new_context() if choice == "+" else choice


def installed_providers() -> list[str]:
    return [p for p in PROVIDERS if shutil.which(p)]


def wizard(cfg: dict, catalog: dict) -> dict:
    heading("AiDW · configuração")
    print("Enter mantém o valor atual. Tudo pode ser alterado depois em aidw.config.toml.\n")

    installed = installed_providers()
    options = [(p, f"{PROVIDER_LABEL[p]}{'' if p in installed else '  (CLI não instalado)'}")
               for p in PROVIDERS]
    previous = cfg["provider"]["name"]
    provider = choose("1/6 Qual provedor roda o orquestrador e todos os agentes?", options, previous)
    cfg["provider"]["name"] = provider
    if provider != previous:  # modelos do outro provedor não servem
        for a in cfg["agents"].values():
            a.pop("model", None)
    cfg["delegation"]["mode"] = choose("\n   Como o orquestrador aciona os agentes?", [
        ("native", "native   — subagentes nativos do provedor (Agent no Claude, spawn_agent no Codex)"),
        ("headless", "headless — um processo do CLI por tarefa (aidw.py delegate)"),
    ], cfg["delegation"]["mode"])

    print("\n2/6 Modelo e effort padrão de cada agente (o orquestrador ajusta o effort por tarefa):")
    models = [(k, f"{m['name']:<18} ({m['model_id']})") for k, m in catalog.items() if m["provider"] == provider]
    for role, a in cfg["agents"].items():
        current = a.get("model") or tier_model(catalog, provider, DEFAULT_AGENTS.get(role, {}).get("tier", "mid"))
        chosen = choose(f"\n  -> {role} ({agent_names(role, a)[1]})", models, current)
        default_key = tier_model(catalog, provider, DEFAULT_AGENTS.get(role, {}).get("tier", "mid"))
        if chosen == default_key:
            a.pop("model", None)
        else:
            a["model"] = chosen
        efforts = catalog[chosen].get("efforts", [])
        if efforts:
            cur = a.get("effort") if a.get("effort") in efforts else DEFAULT_AGENTS.get(role, {}).get("effort", "medium")
            a["effort"] = choose("     effort padrão:", [(e, e) for e in efforts], cur)

    print()
    optional = [n for n in cfg["agents"] if n != ORCHESTRATOR]
    disabled = [n for n in optional if not cfg["agents"][n].get("enabled", True)]
    print(f"3/6 Agentes opcionais: {', '.join(optional)}")
    answer = ask("  Quais desabilitar? (vírgula, '-' = nenhum)", ",".join(disabled) or "-")
    chosen_off = {s.strip() for s in answer.split(",") if s.strip() and s.strip() != "-"}
    for n in chosen_off - set(optional):
        print(f"  Ignorando agente desconhecido: {n}")
    for n in optional:
        cfg["agents"][n]["enabled"] = n not in chosen_off

    names = ", ".join(f"{r}={agent_names(r, a)[1]}" for r, a in cfg["agents"].items())
    print(f"\n  Nomes atuais: {names}")
    if confirm("  Personalizar os nomes dos agentes?", False):
        print("  O nome pode ter acento e espaço (ex.: \"Zé Revisor\"); Enter mantém.")
        for role, a in cfg["agents"].items():
            default = DEFAULT_NAMES.get(role, role)
            while True:
                name = ask(f"    {role} (padrão {default})", a.get("name") or default).strip()
                slug = slugify(name)
                if SLUG_RE.match(slug) and slug not in RESERVED_NAMES:
                    break
                print("    Nome inválido: precisa começar por letra e não pode ser um nome reservado do CLI.")
            if slug == default and name.lower() == default:
                a.pop("name", None)
            else:
                a["name"] = name

    print()
    ask_project_dirs(cfg, "4/6")
    print()
    ask_mcp(cfg, "5/6")
    print()
    ask_context(cfg, "6/6")
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(render_config(cfg), encoding="utf-8", newline="\n")
    print(f"\nGravado {rel(CONFIG_FILE)}.")


# ---------------------------------------------------------------------------
# Contexto novo
# ---------------------------------------------------------------------------

def create_context(name: str, description: str, required_mcp: list[str], required_env: list[str]) -> Path:
    """Cria contexts/<nome>/ com a estrutura mínima e um repositório Git próprio."""
    d = CONTEXTS_DIR / name
    for sub in ("policies", "shared", "agents", "reference", "skills", "tools", "demandas"):
        (d / sub).mkdir(parents=True, exist_ok=True)
        if sub != "agents":
            (d / sub / ".gitkeep").touch()
    mcp_blocks = []
    for server in required_mcp:
        mcp_blocks += ["", f"[mcp.{json.dumps(server)}]",
                       "# Comandos mostrados pelo `doctor` quando o MCP não estiver registrado.",
                       'add = ""        # Claude: claude mcp add --scope user <nome> -- <comando>',
                       'add_codex = ""  # Codex:  codex mcp add <nome> -- <comando>']
    (d / "context.toml").write_text("\n".join([
        f"# Contexto de trabalho: {description}.",
        f"# {GENERATED_MARK} setup em {date.today().isoformat()}; edite à vontade e rode "
        "`python aidw.py apply`.",
        "# Caminhos de arquivos são relativos a esta pasta. Nas strings, {{root}} é a raiz do AiDW",
        "# e {{context}} é esta pasta.",
        "",
        f"name = {toml_value(name)}",
        f"description = {toml_value(description)}",
        "",
        "# Onde ficam specs, planos e reviews das demandas. Relativo à raiz do AiDW.",
        f"state_dir = {toml_value(f'contexts/{name}/demandas')}",
        "",
        "# Pastas liberadas só com este contexto (as do [workspace] do aidw.config.toml já valem).",
        "additional_dirs = []",
        "",
        "# Verificados pelo `doctor`: variáveis (só a presença) e servidores MCP registrados.",
        f"required_env = {toml_value(required_env)}",
        f"required_mcp = {toml_value(required_mcp)}",
        "",
        "[env]",
        "",
        "[permissions]",
        "# Sintaxe do Claude Code. allow = sem prompt · ask = sempre pede OK · deny = bloqueado.",
        "# git_ask = subcomandos git que sempre pedem OK.",
        "allow = []",
        "git_ask = []",
        "ask = []",
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
        f'Regras de trabalho usadas pelo AiDW quando `aidw.config.toml` tem `[context] active = "{name}"`. '
        "Repositório Git **separado e privado**; o AiDW ignora esta pasta.\n\n"
        "Depois de editar, rode `python aidw.py apply` na raiz do AiDW.\n",
        encoding="utf-8", newline="\n")
    (d / ".gitignore").write_text(".env\n.env.*\ndemandas/\n", encoding="utf-8", newline="\n")
    (d / ".gitattributes").write_text("* text=auto eol=lf\n*.ps1 text eol=crlf\n", encoding="utf-8", newline="\n")
    if shutil.which("git"):
        run(["git", "init", "-b", "main"], cwd=d)
    return d


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

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
    """{{agent:<papel>}} → nome do agente; {{root}}/{{context}} → caminhos. Papel desconhecido é erro."""

    def __init__(self, resolved: dict, ctx: dict | None, rep: Report) -> None:
        self.names = {role: a["name"] for role, a in resolved.items()}
        self.vars = path_vars(ctx["dir"] if ctx else None)
        self.rep = rep

    def render(self, text: str, source: Path) -> str:
        def repl(m: re.Match) -> str:
            role = m.group(1)
            if role not in self.names:
                self.rep.error(f"{rel(source)}: marcador {m.group(0)} usa papel desconhecido "
                               f"(válidos: {', '.join(self.names)})")
                return m.group(0)
            return self.names[role]
        return expand_vars(PLACEHOLDER_RE.sub(repl, text), self.vars)

    def include(self, path: Path) -> str:
        return f"<!-- fonte: {rel(path)} -->\n\n{self.render(path.read_text(encoding='utf-8').strip(), path)}"


def csv_field(value: str) -> list[str]:
    return [t.strip() for t in value.split(",") if t.strip()]


def mcp_for_role(servers: dict, role: str) -> dict:
    return {k: s for k, s in servers.items() if not s.get("agents") or role in s["agents"]}


def resolve_mcp(cfg: dict, rep: Report) -> dict[str, dict]:
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
            if role not in DEFAULT_AGENTS:
                rep.warn(f"config/mcp.toml: {key} cita papel desconhecido {role!r}")
        servers[key] = s
    return servers


def runtime_lines(cfg: dict, ctx: dict | None) -> list[str]:
    ctx_label = f"`{ctx['name']}` — {ctx['description']}" if ctx else "none"
    dirs = ", ".join(f"`{d}`" for d in project_dirs(cfg, ctx)) or "none configured"
    return [
        f"- Provider: **{PROVIDER_LABEL[cfg['provider']['name']]}** — every agent runs on it",
        f"- Project dirs (search here for repositories): {dirs}",
        f"- State dir: `{state_dir(ctx).as_posix()}`",
        f"- Context: {ctx_label}",
        f"- AiDW root: `{ROOT.as_posix()}`",
    ]


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


def skills_section(names: list[str], skills: dict[str, Path], provider: str) -> str:
    if not names:
        return ""
    how = ("Invoke them with the `Skill` tool." if provider == "claude" else
           "Codex may list them as skills; if not, read the `SKILL.md` below and follow it.")
    rows = ["## Skills", "", f"Procedures you use in your process. {how}", ""]
    rows += [f"- `{n}` — `{(skills[n] / 'SKILL.md').as_posix()}`" for n in names if n in skills]
    return "\n".join(rows)


def mcp_agent_section(servers: dict, role: str) -> str:
    mine = mcp_for_role(servers, role)
    if not mine:
        return "## MCP tools\n\nNo MCP servers of the AiDW catalog are available for your role."
    rows = ["| Server | Use when |", "|---|---|"]
    rows += [f"| {s['name']} (`{k}`) | {s['use_when']} |" for k, s in mine.items()]
    return "\n".join([
        "## MCP tools", "",
        "Use a server when the task names it. Use one the task does not name only when its "
        "\"use when\" clearly applies and the task cannot be done well without it — and say so in "
        "your result. Report in the result which servers you used and why.",
        "", *rows,
    ])


def mcp_orchestrator_section(servers: dict, resolved: dict) -> str:
    if not servers:
        return "## MCP tools\n\nNo MCP servers enabled."
    rows = ["| Server | Use when | Triggers | Agents |", "|---|---|---|---|"]
    for key, s in servers.items():
        agents = ", ".join(f"`{resolved[r]['name']}`" for r in s.get("agents", []) if r in resolved) or "all"
        rows.append(f"| {s['name']} (`{key}`) | {s['use_when']} | {'; '.join(s.get('triggers', []))} | {agents} |")
    return "\n".join([
        "## MCP tools", "",
        "You decide which MCP servers each delegated task needs. Before every delegation:", "",
        "1. Match the ticket against the triggers below. A server is needed only when at least one "
        "trigger clearly applies.",
        "2. Pick only servers listed for the agent that will receive the task (the agent only has those).",
        "3. Name them explicitly in the task, with the goal — e.g. \"Use the Playwright MCP to walk "
        "through the checkout flow and confirm acceptance criteria 2 and 3\".",
        "4. If no trigger applies, write \"No MCP tools needed\" in the task. Never add a server "
        "speculatively.",
        "", *rows,
    ])


def render_agent(role: str, a: dict, cfg: dict, ctx: dict | None, tpl: Templater, servers: dict,
                 skills: dict, routing: dict) -> tuple[dict, str]:
    """(frontmatter, markdown) da definição do agente — a mesma para Claude e Codex."""
    source = AGENTS_DIR / role / "AGENT.md"
    meta, body = read_frontmatter(source)
    provider = cfg["provider"]["name"]
    orch = tpl.names[ORCHESTRATOR]
    sources = [source, *policy_files(ctx), *context_files(ctx, role)]
    parts = [
        f"<!-- {GENERATED_MARK} apply a partir de: {', '.join(rel(s) for s in sources)}.\n"
        "     Não edite: altere as fontes e rode `python aidw.py apply`. -->",
        tpl.render(body.strip(), source),
        "\n".join(["## Runtime", "",
                   f"- You are `{a['name']}` — {a['display']} (role `{role}`), a sub-agent of "
                   f"`{orch}`: one task per run, and you cannot talk to the user. Questions and approvals "
                   "go back to the orchestrator in your final JSON.",
                   f"- Model: {a['model']['name']} (`{a['model']['model_id']}`). The orchestrator chose "
                   "the effort of this task.",
                   f"- Max retries: {routing.get('max_retries', 3)} (the same failing step; then stop and "
                   "report the failure `state` of your OUTPUT)",
                   "- Put the whole result in your final message: the orchestrator only receives that.",
                   *runtime_lines(cfg, ctx)]),
        skills_section(a["skills"], skills, provider),
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
    description = tpl.render(meta.get("description", a["display"]), source)
    return {**meta, "description": description}, "\n\n".join(parts) + "\n"


def claude_agent_entry(role: str, meta: dict, prompt: str, ctx: dict | None, servers: dict) -> dict:
    entry: dict = {"description": meta["description"], "prompt": prompt}
    tools = csv_field(meta.get("tools", ""))
    if tools:
        mcp = [*mcp_for_role(servers, role), *(ctx.get("required_mcp", []) if ctx else [])]
        entry["tools"] = list(dict.fromkeys([*tools, *[f"mcp__{k}" for k in mcp]]))
    disallowed = csv_field(meta.get("disallowedTools", ""))
    ctx_agent = ctx.get("agents", {}).get(role, {}) if ctx else {}
    disallowed += [t for t in ctx_agent.get("disallowed_tools", []) if t not in disallowed]
    if disallowed:
        entry["disallowedTools"] = disallowed
    return entry


def effort_table(resolved: dict, routing: dict, cfg: dict) -> str:
    eff = routing.get("effort", {})
    levels = eff.get("levels", {})
    roles = [r for r, a in resolved.items() if r != ORCHESTRATOR and a["enabled"]]
    if not levels or not roles:
        return ""
    claude_native = cfg["provider"]["name"] == "claude" and cfg["delegation"]["mode"] == "native"
    rows = ["| Level | When | " + " | ".join(f"`{resolved[r]['name']}`" for r in roles) + " |",
            "|---|---|" + "---|" * len(roles)]
    for lvl, spec in levels.items():
        cells = []
        for r in roles:
            a = resolved[r]
            model, effort = a["by_level"].get(lvl, (a["model"], a["effort"]))
            if claude_native:
                cells.append(f"`{variant_name(a, model, effort)}`")
            elif model["key"] != a["model"]["key"]:
                cells.append(f"{effort or '—'} + model `{model['key']}` (`{model['model_id']}`)")
            else:
                cells.append(effort or "—")
        rows.append(f"| **{lvl}** | {spec.get('when', '')} | " + " | ".join(cells) + " |")
    esc = eff.get("escalate", {})
    if claude_native:
        intro = ("Each cell is the `subagent_type` to use: the agent's model with the effort of that "
                 "level already pinned in its definition (a `-<alias>-` in the name means that level "
                 "uses another model, e.g. `revisor-opus-high`).")
    else:
        intro = ("Each cell is the effort to pass. `—` = the model takes no effort (omit it). A cell "
                 "with `+ model` also names the model to pass for that level.")
    lines = ["## Effort per task", "", f"Default level: **{eff.get('default_level', 'padrao')}**. {intro}",
             "", *rows]
    if esc.get("rules"):
        lines += ["", "Escalate one level for the next attempt of a role when: " + "; ".join(esc["rules"]) + "."]
    if esc.get("downgrade"):
        lines += [f"Go one level down for: {esc['downgrade']}."]
    return "\n".join(lines)


def record_hint(codex: bool) -> str:
    usage = ("--codex-task <task_name>" if codex else
             "--tokens <subagent_tokens> --tool-uses <tool_uses> --duration-ms <duration_ms>")
    return (f"python aidw.py record --agent <name> [--effort <effort>] --level <level> --label <label> "
            f"--demand <demand dir> --state <state> {usage}")


COMMON_DELEGATION = [
    "- Write the task file first (`tarefa-<agente>-<assunto>.md` in the demand folder): SPEC + TICKET + "
    "files in scope with `file:line` + the build/test command + paths of the diff, plan and previous "
    "review. The message to the agent only points to it — never paste large inputs.",
    "- The agent ends with the JSON of its OUTPUT section; decide the next step from its `state`.",
    "- Locked actions the agent could not run come back as proposals (`approvals`, denials): take them "
    "to the user, never retry them another way.",
    "- Independent tickets may run in parallel; tickets on the same files run in sequence. Each "
    "delegation is a fresh agent.",
]


def delegation_section(cfg: dict, resolved: dict) -> str:
    provider, mode = cfg["provider"]["name"], cfg["delegation"]["mode"]
    agents = [a for r, a in resolved.items() if r != ORCHESTRATOR and a["enabled"]]
    example = agents[0]["name"] if agents else "codificador"
    if mode == "headless":
        return headless_delegation_section(provider, example)
    if provider == "claude":
        lines = [
            "## How to delegate", "",
            "The agents are **native Claude Code subagents**: call them with the `Agent` tool.", "",
            "- `subagent_type`: take it from the *Effort per task* table — each cell is the agent with "
            "its model and that level's effort pinned. That is how you choose the effort.",
            "- Do **not** pass `model`: it would override the agent's model. Only when the user asked "
            "for another model.",
            "- `prompt`: `Tarefa: <task file>. Pasta da demanda: <demand dir>. Nível: <level>.` plus the MCP "
            "choice (see *MCP tools*).",
            *COMMON_DELEGATION,
            "- Parallel tickets: several `Agent` calls in the same message, or `run_in_background`.",
            "- After **every** subagent returns, record it — this appends `metricas.md` and prints the "
            "`header` and `resumo` you must show (*SHOWING RESULTS*):",
            "", "```", record_hint(codex=False), "```", "",
            "  `--agent` is the `subagent_type` you used (the effort comes from it); the numbers are the "
            "ones in the Agent result (`subagent_tokens`, `tool_uses`, `duration_ms`). Never estimate.",
            "- Cheap exploration: the built-in `Explore` subagent (read-only) for sweeping code and "
            "returning `file:line` pointers.",
        ]
        return "\n".join(lines)
    lines = [
        "## How to delegate", "",
        "The agents are **native Codex sub-agents**: spawn them with `spawn_agent` (multi-agent).", "",
        "- `task_name`: `<agent>-<label>` (e.g. `codificador-t1-r1`), unique in the demand.",
        "- `model`: the agent's model from the Team table. `reasoning_effort`: the cell of the *Effort per "
        "task* table — that is how you choose the effort.",
        "- `message` (always this shape): `You are the AiDW agent <name>. Your standing instructions are "
        "in <definition file> — read that file first and follow it; ignore the orchestrator instructions "
        "(AGENTS.md) you may have inherited. Task: <task file>. Demand folder: <demand dir>. Level: <level>, "
        "effort <effort>. Finish with the JSON of your OUTPUT section.` plus the MCP choice.",
        "- If your spawn tool also takes an agent type/role, pass the agent name too (roles are defined "
        "in `.codex/agents/`).",
        *COMMON_DELEGATION,
        "- Sub-agents inherit your sandbox, rules and MCP servers: the task must say which MCP to use, and "
        "only the agents allowed to edit code may edit it (their definition says so).",
        "- Wait for the sub-agent to finish. Then record it — this reads the real token usage of the "
        "sub-agent session, appends `metricas.md` and prints the `header` and `resumo` you must show:",
        "", "```", record_hint(codex=True), "```", "",
        f"- There is no exploration role: for broad code exploration spawn `{example}` at level `trivial` "
        "asking for `file:line` pointers, or read short excerpts yourself.",
        "- Your own skills (`to-spec`, `to-tickets`, `codebase-context`): read `skills/<name>/SKILL.md` and "
        "follow it when the workflow says to use it.",
    ]
    return "\n".join(lines)


def headless_delegation_section(provider: str, example: str) -> str:
    lines = [
        "## How to delegate", "",
        "Every agent runs headless, one process per task, in the same provider as you. Always run from "
        f"the AiDW root (`{ROOT.as_posix()}`), exactly in this form (the permission rules match it):",
        "",
        "```",
        "python aidw.py delegate --agent <name> --effort <low|medium|high|xhigh|max> "
        "--level <level> --task <task.md> --demand <demand dir> [--label <ticket>-r<N>]",
        "```",
        "",
        f"- `--agent`: the agent name from the Team table (e.g. `{example}`) or its role.",
        "- `--effort` and `--level`: your decision for this task (*Effort per task*). Omit `--effort` "
        "only for models marked `—`.",
        "- `--model <key>`: only when the user asked for another model for this task (a level whose "
        "*Effort per task* cell names a model already gets it without `--model`).",
        *COMMON_DELEGATION,
        "- The command prints one JSON line: `header`, `resumo`, `state`, `output` (the agent's final "
        "JSON), `result_file`, `denials`, tokens and duration. The full answer is in `result_file` — read "
        "it only when needed. The same JSON is saved next to it (`resultado-<agent>-<label>.json`): if you "
        "lost the command output, read it from there.",
        "- Usage is appended to `metricas.md` in the demand folder automatically; never estimate it.",
        "- Never call the provider CLI (`claude -p`, `codex exec`) yourself: the delegate sets the "
        "agent's instructions, model, effort, sandbox and MCPs.",
    ]
    if provider == "claude":
        lines += [
            "- A delegation can take many minutes: run it with the Bash/PowerShell tool in the "
            "**background** (`run_in_background: true`) and continue when it notifies you; parallel "
            "tickets are parallel background commands.",
            "- Cheap exploration: the built-in `Explore` subagent (read-only) is fine for sweeping code "
            "and returning `file:line` pointers. The AiDW agents are **not** subagents in this mode — "
            "reach them only through the delegate.",
        ]
    else:
        lines += [
            "- A delegation can take many minutes: give the shell command a long timeout (at least "
            "3600000 ms). If the tool returns while the process is still running, keep polling that same "
            "process until it exits — never conclude before the JSON line appears (or read it from the "
            "`.json` file above once the process ended).",
            "- The delegate starts another Codex process; if your sandbox blocks it (no network), rerun "
            "it asking for escalated permissions — the project rules allow this command.",
            "- There is no exploration subagent: for broad code exploration delegate a read-only task to "
            f"`{example}` at level `trivial` asking for `file:line` pointers, or read short excerpts yourself.",
            "- Your own skills (`to-spec`, `to-tickets`, `codebase-context`): read `skills/<name>/SKILL.md` "
            "and follow it when the workflow says to use it.",
        ]
    return "\n".join(lines)


CODEX_SUBAGENT_GUARD = (
    "> **Sub-agents:** if you were spawned by the orchestrator and told that your standing instructions "
    "are in `.aidw/agents/<name>.md`, you are **not** the orchestrator: ignore this entire file and follow "
    "only that definition.")


def render_orchestrator(resolved: dict, cfg: dict, ctx: dict | None, tpl: Templater, servers: dict,
                        skills: dict, routing: dict) -> str:
    orch = resolved[ORCHESTRATOR]
    provider, mode = cfg["provider"]["name"], cfg["delegation"]["mode"]
    codex_native = provider == "codex" and mode == "native"
    first_col = {"headless": "Agent (`--agent`)", "native": "Agent"}[mode]
    team = [f"| {first_col} | Display name | Role | Model | Default effort | Definition | Status |",
            "|---|---|---|---|---|---|---|"]
    for role, a in resolved.items():
        if role == ORCHESTRATOR:
            continue
        status = "enabled" if a["enabled"] else "disabled — do not delegate"
        eff = a["effort"] if a["model"].get("efforts") else "—"
        definition = f"`{(GEN_AGENTS_DIR / (a['name'] + '.md')).as_posix()}`" if a["enabled"] else "—"
        team.append(f"| `{a['name']}` | {a['display']} | {role} | {a['model']['name']} "
                    f"(`{a['model']['model_id']}`) | {eff} | {definition} | {status} |")
    source_file = "CLAUDE.md" if provider == "claude" else "AGENTS.md"
    parts = [
        f"<!-- {GENERATED_MARK} apply — {source_file} do orquestrador; não edite. Fontes: "
        "orchestrator/ORCHESTRATOR.md, orchestrator/policies/ e o contexto ativo; rode "
        "`python aidw.py apply` após alterá-las. -->",
        CODEX_SUBAGENT_GUARD if codex_native else "",
        tpl.include(ORCHESTRATOR_MD),
        "\n".join(["## Runtime", "",
                   f"- You are `{orch['name']}` — {orch['display']} (role `orchestrator`), the main chat.",
                   f"- Your model: {model_label(orch)}",
                   f"- Delegation mode: **{mode}**",
                   *runtime_lines(cfg, ctx)]),
        "\n".join(["## Team", "", *team]),
        delegation_section(cfg, resolved),
        effort_table(resolved, routing, cfg),
        skills_section(orch["skills"], skills, provider),
        mcp_orchestrator_section(servers, resolved),
        systems_section(ctx, detailed=False),
        "# Policies",
        *[tpl.include(p) for p in policy_files(ctx)],
    ]
    parts = [x for x in parts if x]
    if context_files(ctx, ORCHESTRATOR):
        parts.append(f"# Context: {ctx['description']}")
        parts += [tpl.include(p) for p in context_files(ctx, ORCHESTRATOR)]
    return "\n\n".join(parts) + "\n"


def render_claude_subagent(role: str, a: dict, meta: dict, prompt: str, effort: str, name: str,
                           ctx: dict | None, servers: dict, model: dict | None = None) -> str:
    model = model or a["model"]
    entry = claude_agent_entry(role, meta, prompt, ctx, servers)
    description = meta["description"]
    if model["key"] != a["model"]["key"]:
        description = (f"{a['display']} com {model['name']} e effort {effort or '—'}. {description} Use esta "
                       "variante só quando a tabela Effort per task a indicar para o nível da tarefa.")
        prompt = prompt.replace(f"- Model: {a['model']['name']} (`{a['model']['model_id']}`).",
                                f"- Model: {model['name']} (`{model['model_id']}`).")
    elif name != a["name"]:
        description = (f"{a['display']} com effort {effort}. {description} Use esta variante só quando o "
                       f"orquestrador escolher effort {effort} para a tarefa.")
    front = ["---", f"name: {name}", f"description: {json.dumps(description, ensure_ascii=False)}",
             f"model: {model.get('alias') or model['model_id']}"]
    if effort:
        front.append(f"effort: {effort}")
    front.append("omitClaudeMd: true")
    if a["skills"]:
        front += ["skills:", *[f"  - {x}" for x in a["skills"]]]
    if entry.get("tools"):
        front.append("tools: " + ", ".join(entry["tools"]))
    if entry.get("disallowedTools"):
        front.append("disallowedTools: " + ", ".join(entry["disallowedTools"]))
    reserved = {"name", "description", "model", "effort", "skills", "omitClaudeMd", "tools", "disallowedTools"}
    front += [f"{k}: {v}" for k, v in meta.items() if k not in reserved]
    front.append("---")
    note = f"Effort of this run: **{effort}** (pinned in this definition)." if effort else ""
    return "\n".join(front) + "\n\n" + (note + "\n\n" if note else "") + prompt


def render_codex_role(a: dict, meta: dict, prompt: str) -> str:
    """Papel nativo do Codex (.codex/agents/<nome>.toml). Vale quando a ferramenta de spawn aceita
    papel; senão o orquestrador passa o arquivo de definição na mensagem."""
    lines = [f"# {GENERATED_MARK} apply — não edite; altere as fontes e rode `python aidw.py apply`.",
             f"name = {toml_value(a['name'])}",
             f"description = {toml_value(meta['description'])}",
             f"model = {toml_value(a['model']['model_id'])}"]
    if a["effort"]:
        lines.append(f"model_reasoning_effort = {toml_value(a['effort'])}")
    lines.append("developer_instructions = " + toml_value(prompt))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Regras de permissão
# ---------------------------------------------------------------------------

def expand_git_ask(subcommands: list[str]) -> list[str]:
    """`commit` → ask para `git commit ...` e `git -C <pasta> commit ...`, no Bash e no PowerShell."""
    rules = []
    for tool in ("Bash", "PowerShell"):
        for sub in subcommands:
            rules += [f"{tool}(git {sub})", f"{tool}(git {sub} *)", f"{tool}(git -C * {sub})",
                      f"{tool}(git -C * {sub} *)"]
    return rules


def delegate_allow_rules() -> list[str]:
    """O orquestrador (Claude) roda o delegate sem prompt; as formas batem por prefixo."""
    script_posix, script_win = (ROOT / "aidw.py").as_posix(), win(ROOT / "aidw.py")
    rules = []
    for tool in ("Bash", "PowerShell"):
        for py in ("python", "py"):
            for script in dict.fromkeys(["aidw.py", script_posix, script_win]):
                rules += [f"{tool}({py} {script} {sub} *)" for sub in ("delegate", "record")]
                rules += [f"{tool}({py} {script} {sub})" for sub in ("show", "doctor")]
    return rules


def rule_to_prefix(rule: str) -> list[str] | None:
    """`Bash(git push --force *)` → ["git", "push", "--force"]; regras que não são de comando → None."""
    m = re.fullmatch(r"(Bash|PowerShell)\((.+)\)", rule.strip())
    if not m:
        return None
    tokens = m.group(2).split()
    if "*" in tokens[:-1] or not tokens:  # curinga no meio (git -C * commit) não vira prefixo
        return None
    tokens = [t for t in tokens if t != "*"]
    return tokens or None


def codex_rules(deny: list[str], ask_rules: list[str]) -> str:
    seen: dict[tuple, str] = {}
    for decision, rules in (("forbidden", deny), ("prompt", ask_rules)):
        for r in rules:
            prefix = rule_to_prefix(r)
            if prefix and tuple(prefix) not in seen:
                seen[tuple(prefix)] = decision
    lines = [f"# {GENERATED_MARK} apply a partir de [policies] e das permissões do contexto. Não edite.",
             "# forbidden = bloqueado · prompt = pede OK (nos agentes headless, vira recusa).", ""]
    for prefix, decision in seen.items():
        lines.append(f"prefix_rule(pattern={json.dumps(list(prefix))}, decision={json.dumps(decision)})")
    lines += ["", "# O orquestrador roda o delegate sem prompt e fora do sandbox (o agente precisa de rede)."]
    for script in dict.fromkeys(["aidw.py", (ROOT / "aidw.py").as_posix(), win(ROOT / "aidw.py")]):
        for py in ("python", "py"):
            for sub in ("delegate", "record"):
                lines.append(f"prefix_rule(pattern={json.dumps([py, script, sub])}, decision=\"allow\")")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Escrita e sincronização
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


def remove_generated(path: Path, dry: bool, rep: Report, why: str) -> None:
    if not path.exists():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    if GENERATED_MARK not in text and '"generated_by": "aidw.py' not in text:
        return
    if dry:
        rep.info(f"(dry-run) remover {rel(path)}")
    else:
        path.unlink()
        rep.ok(f"removido {rel(path)} ({why})")


def is_link(p: Path) -> bool:
    return p.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(p))


def make_link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if not IS_WINDOWS:
        os.symlink(target, link, target_is_directory=True)
        return
    try:  # junction: não exige admin nem modo desenvolvedor no Windows
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    except (ImportError, AttributeError, OSError):
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)


def remove_link(p: Path) -> None:
    if IS_WINDOWS:
        os.rmdir(p)
    else:
        p.unlink()


def sync_skill_links(folder: Path, desired: dict[str, Path], dry: bool, rep: Report) -> None:
    desired = dict(desired)
    if folder.is_dir():
        for entry in folder.iterdir():
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
                rep.info(f"(dry-run) remover link {rel(entry)}")
            else:
                remove_link(entry)
                rep.ok(f"removido link {rel(entry)}")
    for name, target in desired.items():
        if dry:
            rep.info(f"(dry-run) linkar {rel(folder / name)} -> {rel(target)}")
        else:
            make_link(folder / name, target)
            rep.ok(f"linkado {rel(folder / name)} -> {rel(target)}")


def merge_list(existing: list, previously_managed: list, managed: list) -> list:
    kept = [x for x in existing if x not in previously_managed]
    return kept + [x for x in managed if x not in kept]


def sync_claude_settings(managed: dict, previous: dict, dry: bool, rep: Report) -> None:
    """Atualiza só as chaves que o apply gerencia; o resto do arquivo é preservado."""
    try:
        data = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8")) if CLAUDE_SETTINGS.exists() else {}
    except json.JSONDecodeError:
        rep.error(f"{rel(CLAUDE_SETTINGS)} não é JSON válido; corrija ou apague o arquivo")
        return
    data["model"] = managed["model"]
    if managed["effortLevel"]:
        data["effortLevel"] = managed["effortLevel"]
    else:
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
    approved = merge_list(data.get("enabledMcpjsonServers", []), previous.get("enabledMcpjsonServers", []),
                          managed["enabledMcpjsonServers"])
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
    write_if_changed(CLAUDE_SETTINGS, json.dumps(data, indent=2, ensure_ascii=False) + "\n", dry, rep)


def mcp_json_entry(s: dict) -> dict:
    if s["type"] == "http":
        return {"type": "http", "url": s["url"]}
    entry = {"type": "stdio", "command": s["command"], "args": list(s.get("args", []))}
    if s.get("env"):
        entry["env"] = dict(s["env"])
    return entry


def sync_mcp_json(servers: dict, previous: list, dry: bool, rep: Report) -> None:
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


def codex_mcp_table(s: dict) -> dict:
    """Servidor do catálogo no formato do Codex. No Windows o npx é .cmd: roda via cmd /c."""
    if s["type"] == "http":
        return {"url": s["url"]}
    command, args = s["command"], list(s.get("args", []))
    if IS_WINDOWS and command in ("npx", "npm"):
        command, args = "cmd", ["/c", s["command"], *args]
    table: dict = {"command": command, "args": args}
    if s.get("env"):
        table["env"] = dict(s["env"])
    return table


def render_codex_config(resolved: dict, cfg: dict, ctx: dict | None, servers: dict) -> str:
    orch = resolved[ORCHESTRATOR]
    lines = [
        f"# {GENERATED_MARK} apply — config do projeto para o Codex (vale quando o projeto é",
        "# confiável: o setup oferece marcar). `python aidw.py chat` passa os mesmos valores por flag.",
        "",
        f"model = {toml_value(orch['model']['model_id'])}",
    ]
    if orch["effort"]:
        lines.append(f"model_reasoning_effort = {toml_value(orch['effort'])}")
    lines += [
        f"project_doc_max_bytes = {CODEX_DOC_MAX_BYTES}",
        'approval_policy = "on-request"',
        'sandbox_mode = "workspace-write"',
        "",
        "[sandbox_workspace_write]",
        "network_access = true",
        f"writable_roots = {toml_value([win(d) for d in project_dirs(cfg, ctx)])}",
    ]
    env = {**({k: str(v) for k, v in ctx.get("env", {}).items()} if ctx else {}), **codex_git_env(cfg, ctx)}
    lines += ["", "# GIT_CONFIG_*: safe.directory para o sandbox do Windows (ver codex_git_env).",
              "[shell_environment_policy.set]", *[f"{k} = {toml_value(v)}" for k, v in env.items()]]
    if cfg["delegation"]["mode"] == "native":
        lines += ["", "# Subagentes nativos: o spawn_agent do multi-agente v2 aceita modelo e effort por chamada.",
                  "[features]", "multi_agent_v2 = true", "",
                  "[agents]", "max_concurrent_threads_per_session = 4"]
    for key, s in servers.items():
        lines += ["", f"[mcp_servers.{key}]"]
        lines += [f"{k} = {toml_value(v)}" for k, v in codex_mcp_table(s).items()]
    return "\n".join(lines) + "\n"


def sync_generated_dir(folder: Path, files: dict[str, str], ext: str, dry: bool, rep: Report) -> None:
    """Grava {nome: conteúdo} em folder/<nome><ext> e remove os gerados que sobraram."""
    for name, content in files.items():
        write_if_changed(folder / f"{name}{ext}", content, dry, rep)
    if folder.is_dir():
        for f in folder.glob(f"*{ext}"):
            if f.stem not in files:
                remove_generated(f, dry, rep, "não faz mais parte da config")


def previous_runtime() -> dict:
    try:
        return json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def check_workflows(resolved: dict, skills: dict, rep: Report) -> None:
    for wf in sorted(WORKFLOWS_DIR.glob("*.yaml")):
        text = wf.read_text(encoding="utf-8")
        for agent in sorted(set(re.findall(r"^\s*agent:\s*([\w-]+)", text, re.M))):
            if agent not in resolved:
                rep.warn(f"{rel(wf)}: agente desconhecido {agent!r}")
        for skill in sorted(set(re.findall(r"^\s*skill:\s*([\w-]+)", text, re.M))):
            if skill not in skills:
                rep.warn(f"{rel(wf)}: skill desconhecida {skill!r}")


def build(cfg: dict, catalog: dict, rep: Report) -> dict | None:
    """Valida e renderiza tudo em memória (nada é gravado)."""
    ctx = load_context(cfg, rep)
    skills = available_skills(ctx, rep)
    resolved = resolve(cfg, catalog, ctx, skills, rep)
    routing = load_routing(rep)
    if not resolved:
        return None
    attach_variants(resolved, routing, catalog, rep)
    check_workflows(resolved, skills, rep)
    servers = resolve_mcp(cfg, rep)
    if rep.errors:
        return None
    tpl = Templater(resolved, ctx, rep)
    agents = {}
    for role, a in resolved.items():
        if role != ORCHESTRATOR and a["enabled"]:
            meta, prompt = render_agent(role, a, cfg, ctx, tpl, servers, skills, routing)
            agents[role] = {"meta": meta, "prompt": prompt}
    orchestrator_md = render_orchestrator(resolved, cfg, ctx, tpl, servers, skills, routing)
    if rep.errors:
        return None
    return {"ctx": ctx, "skills": skills, "resolved": resolved, "routing": routing, "servers": servers,
            "agents": agents, "orchestrator_md": orchestrator_md}


def apply(cfg: dict, catalog: dict, dry: bool) -> bool:
    heading("Validando configuração" + (" (dry-run)" if dry else ""))
    rep = Report()
    b = build(cfg, catalog, rep)
    if b is None:
        print("\nCorrija os erros acima e rode novamente.")
        return False
    ctx, resolved, servers = b["ctx"], b["resolved"], b["servers"]
    provider, mode = cfg["provider"]["name"], cfg["delegation"]["mode"]
    rep.ok(f"configuração válida · provedor {provider} · delegação {mode}"
           + (f" · contexto {ctx['name']}" if ctx else ""))
    prev = previous_runtime()

    heading("Estado")
    sdir = state_dir(ctx)
    if not sdir.is_dir():
        if dry:
            rep.info(f"(dry-run) criar {rel(sdir)}/")
        else:
            sdir.mkdir(parents=True)
            rep.ok(f"criado {rel(sdir)}/")

    heading("Agentes (.aidw/agents)")
    files = {}
    for role, g in b["agents"].items():
        a = resolved[role]
        files[a["name"]] = g["prompt"]
        write_if_changed(GEN_AGENTS_DIR / f"{a['name']}.md", g["prompt"], dry, rep)
        eff = a["effort"] or "—"
        rep.info(f"{a['name']:<14} {role:<11} {a['model']['model_id']:<26} effort padrão {eff:<7} "
                 f"~{len(g['prompt']) // 4:,} tokens de instruções")
    if GEN_AGENTS_DIR.is_dir():
        for f in GEN_AGENTS_DIR.glob("*.md"):
            if f.stem not in files:
                remove_generated(f, dry, rep, "agente renomeado, desabilitado ou removido")

    if provider == "claude":
        heading("Claude Code (CLAUDE.md, .claude/, .mcp.json)")
        write_if_changed(CLAUDE_MD, b["orchestrator_md"], dry, rep)
        agents_json = {resolved[r]["name"]: claude_agent_entry(r, g["meta"], g["prompt"], ctx, servers)
                       for r, g in b["agents"].items()}
        write_if_changed(CLAUDE_AGENTS_JSON, json.dumps(agents_json, indent=2, ensure_ascii=False) + "\n", dry, rep)
        subagents = {}
        if mode == "native":
            for role, g in b["agents"].items():
                a = resolved[role]
                for name, v in a["variants"].items():
                    subagents[name] = render_claude_subagent(role, a, g["meta"], g["prompt"], v["effort"], name,
                                                             ctx, servers, v["model"])
                rep.info(f"subagentes de {a['name']}: " + ", ".join(
                    f"{n} ({v['model'].get('alias') or v['model']['key']}, {v['effort'] or 'sem effort'})"
                    for n, v in a["variants"].items()))
        sync_generated_dir(CLAUDE_SUBAGENTS, subagents, ".md", dry, rep)
        sync_generated_dir(CODEX_SUBAGENTS, {}, ".toml", dry, rep)
        sync_skill_links(CLAUDE_SKILLS, b["skills"], dry, rep)
        orch = resolved[ORCHESTRATOR]
        ctx_perms = ctx.get("permissions", {}) if ctx else {}
        managed = {
            "model": orch["model"]["model_id"],
            "effortLevel": orch["effort"],
            "allow": list(dict.fromkeys([*ctx_perms.get("allow", []), *delegate_allow_rules(),
                                         *[f"mcp__{k}" for k, s in servers.items() if s.get("allow")]])),
            "enabledMcpjsonServers": list(servers),
            "ask": list(dict.fromkeys([*cfg["policies"]["ask"], *ctx_perms.get("ask", []),
                                       *expand_git_ask(ctx_perms.get("git_ask", []))])),
            "deny": list(dict.fromkeys([*cfg["policies"]["deny"], *ctx_perms.get("deny", [])])),
            "additionalDirectories": project_dirs(cfg, ctx),
            "env": {k: str(v) for k, v in ctx.get("env", {}).items()} if ctx else {},
        }
        sync_claude_settings(managed, prev.get("claude_settings", {}), dry, rep)
        sync_mcp_json(servers, prev.get("claude_settings", {}).get("enabledMcpjsonServers", []), dry, rep)
        for path, why in ((AGENTS_MD, "provedor claude"), (CODEX_CONFIG, "provedor claude"),
                          (CODEX_RULES, "provedor claude")):
            remove_generated(path, dry, rep, why)
        if CODEX_SKILLS.is_dir():
            sync_skill_links(CODEX_SKILLS, {}, dry, rep)
    else:
        managed = {}
        heading("Codex (AGENTS.md, .codex/, .agents/skills)")
        write_if_changed(AGENTS_MD, b["orchestrator_md"], dry, rep)
        size = len(b["orchestrator_md"].encode("utf-8"))
        if size > CODEX_DOC_MAX_BYTES:
            rep.warn(f"AGENTS.md tem {size:,} bytes, acima de project_doc_max_bytes ({CODEX_DOC_MAX_BYTES:,}); "
                     "o Codex vai cortar o fim")
        write_if_changed(CODEX_CONFIG, render_codex_config(resolved, cfg, ctx, servers), dry, rep)
        ctx_perms = ctx.get("permissions", {}) if ctx else {}
        git_ask = [["git", *sub.split()] for sub in ctx_perms.get("git_ask", [])]
        ask_rules = [*cfg["policies"]["ask"], *ctx_perms.get("ask", []),
                     *[f"Bash({' '.join(g)} *)" for g in git_ask]]
        deny_rules = [*cfg["policies"]["deny"], *ctx_perms.get("deny", [])]
        write_if_changed(CODEX_RULES, codex_rules(deny_rules, ask_rules), dry, rep)
        roles = ({resolved[r]["name"]: render_codex_role(resolved[r], g["meta"], g["prompt"])
                  for r, g in b["agents"].items()} if mode == "native" else {})
        sync_generated_dir(CODEX_SUBAGENTS, roles, ".toml", dry, rep)
        sync_generated_dir(CLAUDE_SUBAGENTS, {}, ".md", dry, rep)
        sync_skill_links(CODEX_SKILLS, b["skills"], dry, rep)
        for path, why in ((CLAUDE_MD, "provedor codex"), (CLAUDE_AGENTS_JSON, "provedor codex")):
            remove_generated(path, dry, rep, why)
        if CLAUDE_SKILLS.is_dir():
            sync_skill_links(CLAUDE_SKILLS, {}, dry, rep)

    for key, s in servers.items():
        roles = ", ".join(s.get("agents", [])) or "todos"
        extra = " · autenticar uma vez (OAuth)" if s.get("auth") == "oauth" else ""
        rep.info(f"MCP {key:<16} {s['type']:<6} agentes: {roles}{extra}")

    runtime = {
        "generated_by": "aidw.py apply",
        "root": ROOT.as_posix(),
        "provider": provider,
        "delegation": mode,
        "context": ctx["name"] if ctx else None,
        "state_dir": sdir.as_posix(),
        "agents": {role: {"name": a["name"], "display": a["display"], "enabled": a["enabled"],
                          "model": a["model"]["key"], "model_id": a["model"]["model_id"],
                          "effort": a["effort"], "skills": a["skills"]}
                   for role, a in resolved.items()},
        "mcp": list(servers),
        "claude_settings": managed if provider == "claude" else prev.get("claude_settings", {}),
    }
    write_if_changed(RUNTIME_FILE, json.dumps(runtime, indent=2, ensure_ascii=False) + "\n", dry, rep)
    print(f"\nConcluído{' (nada foi alterado: dry-run)' if dry else ''}"
          f"{f' com {len(rep.warnings)} aviso(s)' if rep.warnings else ''}. Abra um chat novo na raiz do AiDW.")
    return True


# ---------------------------------------------------------------------------
# Delegate: um agente headless por tarefa
# ---------------------------------------------------------------------------

def final_json(text: str) -> dict | None:
    """O JSON final do agente: o objeto de nível mais alto com `state` que termina por último
    (itens internos, como os de `operations`, não contam)."""
    decoder = json.JSONDecoder()
    found = []
    for m in re.finditer(r"\{", text):
        try:
            obj, end = decoder.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            found.append((m.start(), end, obj))
    top = [f for f in found if not any(o[0] < f[0] and f[1] <= o[1] for o in found)]
    with_state = [f for f in top if "state" in f[2]]
    pick = (with_state or top)
    return max(pick, key=lambda f: f[1])[2] if pick else None


def fmt_window(w: dict | None, fmt: str) -> str:
    if w and w.get("stale"):
        return "sem dado atual"
    if not w or w.get("pct") is None:
        return "?"
    when = f" (reinicia {datetime.fromtimestamp(w['resets_at']).strftime(fmt)})" if w.get("resets_at") else ""
    return f"{w['pct']:.0f}%{when}"


def claude_limits(events: list[dict]) -> str:
    for e in reversed(events):
        if e.get("type") == "rate_limit_event":
            windows = (e.get("rate_limit_info") or {}).get("unifiedWindows") or {}
            out = {}
            for key, name in (("five_hour", "5h"), ("seven_day", "semana")):
                w = windows.get(key) or {}
                if w.get("utilization") is not None:
                    out[name] = {"pct": round(w["utilization"] * 100), "resets_at": w.get("resetsAt")}
            if out:
                return (f"Claude 5h {fmt_window(out.get('5h'), '%H:%M')} · semana "
                        f"{fmt_window(out.get('semana'), '%d/%m %H:%M')}")
    return "Claude limites ?"


def codex_limits() -> str:
    """Janelas do plano ChatGPT no evento mais recente das sessões do Codex."""
    root = CODEX_HOME / "sessions"
    try:
        files = sorted(root.rglob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)[:3]
    except OSError:
        return "Codex limites ?"
    for f in files:
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
        except OSError:
            continue
        for line in reversed(lines):
            if '"rate_limits"' not in line:
                continue
            try:
                payload = json.loads(line).get("payload") or {}
            except json.JSONDecodeError:
                continue
            rl = payload.get("rate_limits") or (payload.get("info") or {}).get("rate_limits")
            if not rl:
                continue
            parts = []
            for key in ("primary", "secondary"):
                w = rl.get(key) or {}
                if w.get("used_percent") is None:
                    continue
                minutes = w.get("window_minutes") or 0
                name = {300: "5h", 10080: "semana", 43200: "mês"}.get(minutes, f"{minutes // 60}h")
                stale = bool(w.get("resets_at")) and w["resets_at"] < time.time()
                parts.append(f"{name} " + fmt_window({"pct": w["used_percent"], "resets_at": w.get("resets_at"),
                                                      "stale": stale}, "%H:%M" if name == "5h" else "%d/%m %H:%M"))
            if parts:
                plan = f" ({rl['plan_type']})" if rl.get("plan_type") else ""
                return f"Codex{plan} " + " · ".join(parts)
    return "Codex limites ?"


def append_metrics(demand: Path, row: dict) -> None:
    f = demand / "metricas.md"
    head = ("| Data | Agente | Nível | Modelo | Effort | Label | State | Turnos ou ferramentas | Duração | Tokens entrada "
            "(com cache) | Tokens saída | Custo (USD) | Limites do plano |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    cost = f"{row['cost_usd']:.4f}" if row["cost_usd"] is not None else "—"

    def num(v) -> str:
        return f"{v:,}" if isinstance(v, int) else "—"

    line = (f"| {row['date']} | {row['agent']} | {row['level']} | {row['model']} | {row['effort'] or '—'} | "
            f"{row['label']} | {row['state']} | {num(row['turns'])} | {row['duration_s']}s | "
            f"{num(row['tokens_in'])} | {num(row['tokens_out'])} | {cost} | {row['limits']} |\n")
    if not f.exists():
        f.write_text("# Métricas da demanda\n\nConsumo real de cada delegação (gravado por "
                     "`aidw.py delegate` ou `aidw.py record`). No subagente nativo do Claude, a entrada "
                     "é o total de tokens e a saída fica —.\n\n" + head, encoding="utf-8", newline="\n")
    with f.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(line)


def codex_subagent_usage(task_name: str) -> dict | None:
    """Tokens, duração e modelo reais do subagente Codex, pela sessão dele em ~/.codex/sessions
    (a mais recente cujo agent_path termina em /<task_name>)."""
    root = CODEX_HOME / "sessions"
    try:
        files = sorted(root.rglob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)[:60]
    except OSError:
        return None
    for f in files:
        try:
            with f.open(encoding="utf-8", errors="replace") as fh:
                meta = json.loads(fh.readline()).get("payload") or {}
                if not str(meta.get("agent_path", "")).endswith("/" + task_name):
                    continue
                lines = fh.readlines()
        except (OSError, json.JSONDecodeError):
            continue
        usage, model, last_ts, turns = {}, None, meta.get("timestamp"), 0
        for line in lines:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            last_ts = e.get("timestamp") or last_ts
            payload = e.get("payload") or {}
            if e.get("type") == "turn_context":
                model = payload.get("model") or model
                turns += 1
            info = payload.get("info") if isinstance(payload, dict) else None
            if isinstance(info, dict) and info.get("total_token_usage"):
                usage = info["total_token_usage"]
        duration = 0
        try:
            t0 = datetime.fromisoformat(meta["timestamp"].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            duration = round((t1 - t0).total_seconds())
        except (KeyError, AttributeError, ValueError):
            pass
        return {"tokens_in": usage.get("input_tokens", 0),
                "tokens_out": usage.get("output_tokens", 0) + usage.get("reasoning_output_tokens", 0),
                "duration_s": duration, "model": model, "turns": turns or None, "thread": meta.get("id")}
    return None


def record(cfg: dict, catalog: dict, args: argparse.Namespace) -> int:
    """Registra uma delegação feita com subagente nativo: metricas.md + header e resumo."""
    rep = Report(quiet=True)
    ctx = load_context(cfg, rep)
    resolved = resolve(cfg, catalog, ctx, available_skills(ctx, rep), rep)
    routing = load_routing(rep)
    provider = cfg["provider"]["name"]
    attach_variants(resolved, routing, catalog, rep)
    wanted = slugify(args.agent)
    role, effort, model = None, args.effort or "", None
    for r, a in resolved.items():
        if r == ORCHESTRATOR:
            continue
        if wanted in (r, a["name"]):
            role = r
            break
        for name, v in a["variants"].items():
            if wanted == name:
                role, effort, model = r, effort or v["effort"], v["model"]
                break
        if role:
            break
    if role is None:
        print(json.dumps({"error": f"agente {args.agent!r} desconhecido"}, ensure_ascii=False))
        return 2
    a = resolved[role]
    level = args.level or routing.get("effort", {}).get("default_level", "padrao")
    model = model or a["model"]
    if not effort and model.get("efforts"):
        effort = effort_for(routing, role, level, a)
    if not model.get("efforts"):
        effort = ""
    row = {"date": date.today().isoformat(), "agent": a["name"], "level": level, "model": model["model_id"],
           "effort": effort, "label": args.label, "state": args.state or "missing_state", "turns": None,
           "duration_s": round((args.duration_ms or 0) / 1000), "tokens_in": args.tokens,
           "tokens_out": None, "cost_usd": None, "limits": "—"}
    if args.tool_uses is not None:
        row["turns"] = args.tool_uses  # no subagente do Claude, a coluna guarda as chamadas de ferramenta
    if provider == "codex" and args.codex_task:
        usage = codex_subagent_usage(args.codex_task)
        if usage:
            row.update({k: usage[k] for k in ("tokens_in", "tokens_out", "duration_s", "turns")})
            if usage.get("model") and usage["model"] != model["model_id"]:
                row["model"] = usage["model"]
        else:
            rep.warn(f"sessão do subagente {args.codex_task!r} não encontrada em {CODEX_HOME / 'sessions'}")
        row["limits"] = codex_limits()
    demand = Path(args.demand).resolve()
    demand.mkdir(parents=True, exist_ok=True)
    append_metrics(demand, row)
    shown = {**a, "model": {**model, "model_id": row["model"]}}
    head = header(shown, effort)
    if row["tokens_out"] is None:
        tokens = f"{row['tokens_in']:,} tokens".replace(",", ".") if row["tokens_in"] is not None else "tokens ?"
    else:
        tokens = f"{row['tokens_in']:,} tokens entrada + {row['tokens_out']:,} saída".replace(",", ".")
    parts = [f"{a['display']} ({level})", model["name"], f"effort {effort or '—'}", tokens, f"{row['duration_s']} s"]
    if row["limits"] != "—":
        parts.append(row["limits"])
    print(json.dumps({"header": head, "resumo": " | ".join(parts), **row, "warnings": rep.warnings},
                     ensure_ascii=False))
    return 0


def debug_dump(demand: Path, name: str, cmd: list[str], proc: subprocess.CompletedProcess) -> None:
    """Com AIDW_DEBUG=1, guarda o comando, o stdout (eventos) e o stderr da execução na demanda."""
    if not os.environ.get("AIDW_DEBUG"):
        return
    stamp = datetime.now().strftime("%H%M%S")
    (demand / f"debug-{name}-{stamp}.log").write_text(
        "CMD: " + json.dumps(cmd, ensure_ascii=False) + "\n\n--- STDOUT ---\n" + (proc.stdout or "")
        + "\n--- STDERR ---\n" + (proc.stderr or ""), encoding="utf-8", newline="\n")


def run_claude(a: dict, role: str, model: dict, effort: str, prompt: str, args, ctx) -> dict:
    exclude = "**/" + ROOT.as_posix().split(":", 1)[-1].lstrip("/") + "/CLAUDE.md"
    settings = {"claudeMdExcludes": [exclude]}
    profile = RUN_PROFILE.get(role, {})
    cmd = [shutil.which("claude"), "-p", "--agents", str(CLAUDE_AGENTS_JSON), "--agent", a["name"],
           "--model", model["model_id"], "--output-format", "stream-json", "--verbose",
           "--settings", json.dumps(settings),
           "--permission-mode", profile.get("claude_mode", "default"),
           "--max-turns", str(args.max_turns or profile.get("max_turns", 40))]
    if effort:
        cmd += ["--effort", effort]
    started = time.time()
    proc = subprocess.run(cmd, input=prompt, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=args.timeout)
    debug_dump(Path(args.demand).resolve(), a["name"], cmd, proc)
    events = []
    for line in proc.stdout.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    data = next((e for e in reversed(events) if e.get("type") == "result"), None)
    if data is None:
        return {"ok": False, "error": "saída do claude sem evento result", "stderr": proc.stderr[-1500:],
                "stdout": proc.stdout[-800:]}
    u = data.get("usage", {})
    return {
        "ok": not data.get("is_error"), "text": data.get("result") or "", "raw": data,
        "turns": data.get("num_turns", 0),
        "duration_s": round(data.get("duration_ms", (time.time() - started) * 1000) / 1000),
        "tokens_in": u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                     + u.get("cache_read_input_tokens", 0),
        "tokens_out": u.get("output_tokens", 0), "cost_usd": data.get("total_cost_usd", 0.0),
        "denials": [d.get("tool_name", "?") + (f": {json.dumps(d.get('tool_input'), ensure_ascii=False)[:200]}"
                                               if d.get("tool_input") else "")
                    for d in data.get("permission_denials", [])],
        "session": data.get("session_id"), "limits": claude_limits(events),
    }


def codex_git_env(cfg: dict, ctx: dict | None) -> dict[str, str]:
    """O sandbox do Codex no Windows roda os comandos com outra identidade e o git recusa os
    repositórios ("dubious ownership"). Libera safe.directory só para as pastas do AiDW e dos
    projetos, e só nos comandos do Codex (variáveis GIT_CONFIG_*, sem tocar no .gitconfig)."""
    dirs = [ROOT.as_posix(), *project_dirs(cfg, ctx)]
    values = [d.rstrip("/") + "/*" for d in dirs] + [ROOT.as_posix()]
    env = {"GIT_CONFIG_COUNT": str(len(values))}
    for i, v in enumerate(values):
        env[f"GIT_CONFIG_KEY_{i}"] = "safe.directory"
        env[f"GIT_CONFIG_VALUE_{i}"] = v
    return env


def codex_role_overrides(role: str, ctx: dict | None, servers: dict) -> list[str]:
    """-c do Codex: MCPs do papel ligados, os demais desligados, ferramentas bloqueadas por contexto."""
    out = []
    mine = mcp_for_role(servers, role)
    for key, s in servers.items():
        if key in mine:
            out += ["-c", f"mcp_servers.{key}={toml_value(codex_mcp_table(s))}"]
        elif codex_trusted():  # só existe no config do projeto quando ele é confiável
            out += ["-c", f"mcp_servers.{key}.enabled=false"]
    blocked: dict[str, list[str]] = {}
    ctx_agent = ctx.get("agents", {}).get(role, {}) if ctx else {}
    for t in ctx_agent.get("disallowed_tools", []):
        m = re.fullmatch(r"mcp__([^_]+(?:_[^_]+)*?)__(.+)", t)
        if m:
            blocked.setdefault(m.group(1), []).append(m.group(2))
    for server, tools in blocked.items():
        out += ["-c", f"mcp_servers.{server}.disabled_tools={toml_value(tools)}"]
    return out


def run_codex(a: dict, role: str, model: dict, effort: str, prompt: str, args, ctx, cfg, servers) -> dict:
    profile = RUN_PROFILE.get(role, {})
    definition = (GEN_AGENTS_DIR / f"{a['name']}.md").read_text(encoding="utf-8")
    last = Path(args.demand).resolve() / f".last-{a['name']}-{os.getpid()}.txt"
    cmd = [shutil.which("codex"), "exec", "-m", model["model_id"], "-c", "project_doc_max_bytes=0",
           "-s", "workspace-write", "-C", str(ROOT), "--skip-git-repo-check", "--ephemeral", "--json",
           "-o", str(last)]
    if effort:
        cmd += ["-c", f'model_reasoning_effort="{effort}"']
    if profile.get("network"):
        cmd += ["-c", "sandbox_workspace_write.network_access=true"]
    write_dirs = [str(Path(args.demand).resolve())]
    if profile.get("write") == "projects":
        write_dirs += [win(d) for d in project_dirs(cfg, ctx)]
    for d in dict.fromkeys(write_dirs):
        if Path(d).is_dir():
            cmd += ["--add-dir", d]
    cmd += codex_role_overrides(role, ctx, servers)
    env = {**({k: str(v) for k, v in ctx.get("env", {}).items()} if ctx else {}), **codex_git_env(cfg, ctx)}
    for k, v in env.items():
        cmd += ["-c", f"shell_environment_policy.set.{k}={toml_value(v)}"]
    cmd.append("-")
    stdin = (f"# Agent definition\n\nThese are your standing instructions for this whole session.\n\n"
             f"{definition}\n\n# Task\n\n{prompt}")
    started = time.time()
    proc = subprocess.run(cmd, input=stdin, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=args.timeout)
    duration = round(time.time() - started)
    debug_dump(Path(args.demand).resolve(), a["name"], cmd, proc)
    tokens_in = tokens_out = turns = 0
    thread, failed, messages = None, None, []
    for line in proc.stdout.splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("type") == "thread.started":
            thread = e.get("thread_id")
        elif e.get("type") == "turn.completed":
            turns += 1
            u = e.get("usage") or {}
            tokens_in += u.get("input_tokens", 0)
            tokens_out += u.get("output_tokens", 0) + u.get("reasoning_output_tokens", 0)
        elif e.get("type") in ("turn.failed", "error"):
            failed = (e.get("error") or {}).get("message") or e.get("message") or json.dumps(e)[:300]
        elif (e.get("item") or {}).get("type") == "agent_message":
            messages.append(e["item"].get("text", ""))
    text = last.read_text(encoding="utf-8") if last.exists() else (messages[-1] if messages else "")
    last.unlink(missing_ok=True)
    # stderr: ... CreateProcess { message: "Rejected(\"approval required by policy ...\")" }
    denials = list(dict.fromkeys(m.group(1) for m in re.finditer(r'Rejected\(\\?"(.+?)\\?"\)', proc.stderr)))
    if not text and (failed or proc.returncode != 0):
        return {"ok": False, "error": failed or f"codex exec saiu com código {proc.returncode}",
                "stderr": proc.stderr[-1500:]}
    return {"ok": proc.returncode == 0 and not failed, "text": text, "raw": {"thread_id": thread,
            "returncode": proc.returncode, "error": failed, "stderr_tail": proc.stderr[-4000:]},
            "turns": turns, "duration_s": duration,
            "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": None, "denials": denials,
            "session": thread, "limits": codex_limits()}


def delegate(cfg: dict, catalog: dict, args: argparse.Namespace) -> int:
    rep = Report(quiet=True)
    ctx = load_context(cfg, rep)
    skills = available_skills(ctx, rep)
    resolved = resolve(cfg, catalog, ctx, skills, rep)
    routing = load_routing(rep)
    servers = resolve_mcp(cfg, rep)
    provider = cfg["provider"]["name"]

    by_name = {a["name"]: r for r, a in resolved.items()}
    role = args.agent if args.agent in resolved else by_name.get(slugify(args.agent))
    a = resolved.get(role) if role else None
    if a is None or role == ORCHESTRATOR or not a["enabled"]:
        valid = ", ".join(x["name"] for r, x in resolved.items() if r != ORCHESTRATOR and x["enabled"])
        rep.error(f"agente {args.agent!r} inexistente, desabilitado ou é o orquestrador (válidos: {valid})")
    attach_variants(resolved, routing, catalog, rep)
    level = args.level or routing.get("effort", {}).get("default_level", "padrao")
    # Modelo do nível ([effort.levels.<nível>.models]) quando houver; `--model` vence.
    model = a["by_level"].get(level, (a["model"], ""))[0] if a else {}
    if a and args.model:
        m = catalog.get(args.model) or next((dict(v, key=k) for k, v in catalog.items()
                                             if v["model_id"] == args.model), None)
        if m is None or m["provider"] != provider:
            rep.error(f"--model {args.model!r} não é um modelo {provider} de config/models.toml")
        else:
            model = {**m, "key": m.get("key", args.model)}
    effort = args.effort or (effort_for(routing, role, level, a) if a else "")
    if effort and effort not in EFFORTS:
        rep.error(f"--effort {effort!r} inválido (válidos: {', '.join(EFFORTS)})")
    if model and not model.get("efforts"):
        effort = ""
    elif model and effort and effort not in model["efforts"]:
        rep.error(f"{model['name']} não aceita effort {effort!r}")
    task, demand = Path(args.task).resolve(), Path(args.demand).resolve()
    if not task.is_file():
        rep.error(f"arquivo da tarefa não existe: {task}")
    if not shutil.which(provider):
        rep.error(f"CLI `{provider}` não encontrado no PATH")
    gen = GEN_AGENTS_DIR / f"{a['name']}.md" if a else None
    if gen and not gen.exists():
        rep.error(f"{rel(gen)} não existe — rode `python aidw.py apply`")
    if provider == "claude" and not CLAUDE_AGENTS_JSON.exists():
        rep.error(f"{rel(CLAUDE_AGENTS_JSON)} não existe — rode `python aidw.py apply`")
    if rep.errors:
        print(json.dumps({"state": "environment_blocked", "error": "; ".join(rep.errors)}, ensure_ascii=False))
        return 2

    shown = {**a, "model": model}
    head = header(shown, effort)
    label = args.label or task.stem
    effort_txt = f"effort **{effort}**" if effort else "no effort setting"
    prompt = (f"Model for this task: {model['name']} (`{model['model_id']}`), {effort_txt}, level `{level}`.\n\n"
              f"Your task is in the file `{task.as_posix()}`: read it and execute it. Demand folder: "
              f"`{demand.as_posix()}`. Finish with the JSON of the OUTPUT section of your definition, "
              "with `state`.")
    demand.mkdir(parents=True, exist_ok=True)
    try:
        if provider == "claude":
            res = run_claude(a, role, model, effort, prompt, args, ctx)
        else:
            res = run_codex(a, role, model, effort, prompt, args, ctx, cfg, servers)
    except subprocess.TimeoutExpired:
        res = {"ok": False, "error": f"timeout de {args.timeout}s"}

    if "text" not in res:
        print(json.dumps({"header": head, "state": "environment_blocked", "agent": a["name"],
                          "error": res.get("error"), "stderr": res.get("stderr", ""),
                          "stdout": res.get("stdout", "")}, ensure_ascii=False))
        return 1

    base = f"resultado-{a['name']}-{label}"
    (demand / f"{base}.md").write_text(f"{head}\n\n{res['text']}", encoding="utf-8", newline="\n")
    output = final_json(res["text"])
    state = (output or {}).get("state") or ("implementation_failed" if not res["ok"] else "missing_state")
    row = {"date": date.today().isoformat(), "agent": a["name"], "level": level, "model": model["model_id"],
           "effort": effort, "label": label, "state": state, "turns": res["turns"],
           "duration_s": res["duration_s"], "tokens_in": res["tokens_in"], "tokens_out": res["tokens_out"],
           "cost_usd": res["cost_usd"], "limits": res["limits"]}
    append_metrics(demand, row)
    cost = f"US$ {res['cost_usd']:.2f}".replace(".", ",") if res["cost_usd"] is not None else "assinatura"
    resumo = " | ".join([f"{a['display']} ({level})", model["name"], f"effort {effort or '—'}",
                         f"{res['tokens_in']:,} tokens entrada + {res['tokens_out']:,} saída".replace(",", "."),
                         f"{res['duration_s']} s", cost, res["limits"]])
    summary = {"header": head, "resumo": resumo, **row, "output": output,
               "result_file": (demand / f"{base}.md").as_posix(), "denials": res["denials"],
               "session": res["session"], "is_error": not res["ok"]}
    # O mesmo JSON impresso fica em disco: se o chat perder a saída do comando, lê daqui.
    (demand / f"{base}.json").write_text(json.dumps({**summary, "raw": res["raw"]}, indent=2, ensure_ascii=False),
                                         encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if res["ok"] else 1


# ---------------------------------------------------------------------------
# Doctor e setup
# ---------------------------------------------------------------------------

def run(cmd: list[str], cwd: Path = ROOT) -> str | None:
    exe = shutil.which(cmd[0])
    if not exe:
        return None
    try:
        p = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, check=True, cwd=cwd,
                           encoding="utf-8", errors="replace", timeout=120)
        return (p.stdout or p.stderr).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def version_tuple(text: str) -> tuple[int, ...]:
    match = re.search(r"\d+(?:\.\d+)+", text or "")
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


def list_mcp_servers(provider: str) -> dict[str, str] | None:
    """{nome: status} a partir de `claude mcp list` / `codex mcp list`; None se o CLI falhar."""
    out = run([provider, "mcp", "list"])
    if out is None:
        return None
    servers = {}
    for line in out.splitlines():
        line = line.strip()
        if provider == "claude":
            m = re.match(r"^(.+?): (.+) - (.+)$", line)
            if m:
                servers[m.group(1)] = m.group(3)
        else:
            m = re.match(r"^([\w.-]+)\s+(.*)$", line)
            if m and m.group(1).lower() not in ("name", "no"):
                servers[m.group(1)] = m.group(2)
    return servers


def check_mcp(cfg: dict, ctx: dict | None, rep: Report) -> None:
    provider = cfg["provider"]["name"]
    project = resolve_mcp(cfg, Report(quiet=True))
    required = ctx.get("required_mcp", []) if ctx else []
    if any(s["type"] == "stdio" and s["command"] == "npx" for s in project.values()) and not shutil.which("npx"):
        rep.error("npx não encontrado — os MCPs locais precisam do Node.js (instale o Node LTS)")
    if not required and not project:
        return
    servers = list_mcp_servers(provider) if shutil.which(provider) else None
    if servers is None:
        rep.warn(f"não foi possível rodar `{provider} mcp list`; MCPs não verificados")
        return
    if provider == "claude":
        for key, s in project.items():
            status = servers.get(key)
            if status is None:
                rep.warn(f"MCP {key} não aparece em `claude mcp list` — rode `apply` e abra o Claude Code na raiz")
            elif "connected" in status.lower():
                rep.ok(f"MCP {key} conectado")
            elif s.get("auth") == "oauth":
                rep.warn(f"MCP {key} precisa de autenticação: no Claude Code, /mcp → {key} → Authenticate")
            else:
                rep.warn(f"MCP {key} com status {status!r}")
    else:
        for key, s in project.items():
            extra = " (OAuth: `codex mcp login " + key + "`)" if s.get("auth") == "oauth" else ""
            rep.info(f"MCP {key}: passado pelo AiDW a cada agente e em .codex/config.toml{extra}")
    hints = ctx.get("mcp", {}) if ctx else {}
    for name in required:
        if name not in servers:
            hint = hints.get(name, {}).get("add" if provider == "claude" else "add_codex") or \
                f"{provider} mcp add {name} -- <comando>"
            rep.warn(f"MCP {name!r} não registrado no {provider} (exigido pelo contexto). Registre com:\n"
                     f"            {hint}")
        else:
            rep.ok(f"MCP {name} registrado no {provider} (exigido pelo contexto)")


def codex_trusted() -> bool:
    try:
        text = (CODEX_HOME / "config.toml").read_text(encoding="utf-8")
    except OSError:
        return False
    key = str(ROOT).lower()
    return any(key in line.lower() and "projects" in line for line in text.splitlines())


def doctor(cfg: dict, catalog: dict) -> bool:
    heading("Doctor")
    rep = Report()
    provider = cfg["provider"]["name"]
    rep.ok(f"Python {sys.version.split()[0]}")
    if shutil.which("git"):
        rep.ok(run(["git", "--version"]) or "git")
        if not run(["git", "config", "user.email"]):
            rep.warn("git user.email não configurado")
    else:
        rep.error("git não encontrado no PATH")

    b = build(cfg, catalog, Report(quiet=True))
    resolved = b["resolved"] if b else {}
    version = run([provider, "--version"]) if shutil.which(provider) else None
    if version is None:
        rep.error(f"CLI `{provider}` não encontrado — é ele que executa o orquestrador e todos os agentes")
    else:
        rep.ok(f"{PROVIDER_LABEL[provider]} {version.splitlines()[0]}")
        for a in resolved.values():
            need = a["model"].get("min_cli")
            if need and version_tuple(version) < version_tuple(need):
                rep.warn(f"{a['model']['name']} exige {provider} {need}+ (atual {version.split()[0]}); "
                         f"rode `{provider} update`")
                break
        if provider == "codex":
            status = run(["codex", "login", "status"]) or ""
            if "logged in" in status.lower():
                rep.ok(f"Codex: {status.splitlines()[0]}")
            else:
                rep.warn("Codex sem login — rode `codex login`")
            available = codex_available_models()
            for a in resolved.values():
                if available and a["model"]["model_id"] not in available:
                    rep.warn(f"{a['name']}: {a['model']['model_id']} não está liberado para esta conta "
                             f"(disponíveis: {', '.join(sorted(available))})")
            if cfg["delegation"]["mode"] == "native":
                features = run(["codex", "features", "list"]) or ""
                if re.search(r"^multi_agent_v2\s", features, re.M):
                    rep.ok("Codex: multi_agent_v2 disponível (subagentes com modelo e effort por spawn)")
                else:
                    rep.error("Codex: esta versão não tem multi_agent_v2 — atualize o Codex ou use "
                              '[delegation] mode = "headless"')
            if codex_trusted():
                rep.ok("projeto marcado como confiável no Codex (.codex/config.toml vale no app)")
            else:
                rep.info("projeto não marcado como confiável no Codex: .codex/config.toml só vale via "
                         "`python aidw.py chat` (o setup oferece marcar)")

    ctx = load_context(cfg, rep)
    if ctx:
        rep.ok(f"contexto {ctx['name']}: {ctx['description']}")
        if not (ctx["dir"] / ".git").exists():
            rep.warn(f"contexto {ctx['name']}: {rel(ctx['dir'])} não é um repositório Git")
        if run(["git", "rev-parse", "--is-inside-work-tree"]) is not None:
            if run(["git", "check-ignore", "-q", rel(ctx["dir"])]) is None:
                rep.error(f"{rel(ctx['dir'])} NÃO está no .gitignore do AiDW (conteúdo interno vazaria)")
            else:
                rep.ok(f"{rel(ctx['dir'])} ignorado pelo Git do AiDW")
        for var in ctx.get("required_env", []):
            if env_defined(var):
                rep.ok(f"variável {var} definida")
            else:
                rep.warn(f"variável {var} não definida (necessária para o contexto {ctx['name']})")
    else:
        rep.info("sem contexto de trabalho ativo")
    check_mcp(cfg, ctx, rep)

    for d in project_dirs(cfg, ctx):
        (rep.ok if Path(d).is_dir() else rep.warn)(f"pasta liberada {d}" + ("" if Path(d).is_dir() else " não existe"))

    orch_file = CLAUDE_MD if provider == "claude" else AGENTS_MD
    if not RUNTIME_FILE.exists() or not orch_file.exists():
        rep.warn("ambiente ainda não gerado — rode `python aidw.py apply`")
    elif previous_runtime().get("provider") != provider:
        rep.warn("o ambiente gerado é de outro provedor — rode `python aidw.py apply`")

    print(f"\n{len(rep.errors)} erro(s), {len(rep.warnings)} aviso(s).")
    return not rep.errors


INSTALL_HINTS = {
    "git": {"win": "winget install --id Git.Git -e", "mac": "brew install git", "linux": "sudo apt install git"},
    "npx": {"win": "winget install --id OpenJS.NodeJS.LTS -e", "mac": "brew install node",
            "linux": "sudo apt install nodejs npm"},
    "claude": {"win": "irm https://claude.ai/install.ps1 | iex", "mac": "curl -fsSL https://claude.ai/install.sh | bash",
               "linux": "curl -fsSL https://claude.ai/install.sh | bash"},
    "codex": {"win": "npm install -g @openai/codex", "mac": "npm install -g @openai/codex",
              "linux": "npm install -g @openai/codex"},
}


def platform_key() -> str:
    return "win" if IS_WINDOWS else ("mac" if sys.platform == "darwin" else "linux")


def ensure_tools(provider: str) -> None:
    heading("Pré-requisitos")
    for tool in ("git", "npx", provider):
        if shutil.which(tool):
            print(f"  [ok]    {tool}")
            continue
        hint = INSTALL_HINTS[tool][platform_key()]
        print(f"  [falta] {tool} — instalar com: {hint}")
        if confirm(f"  Instalar {tool} agora?", True):
            shell = ["powershell", "-NoProfile", "-Command", hint] if IS_WINDOWS else ["bash", "-lc", hint]
            code = subprocess.run(shell).returncode
            print(f"  {'instalado' if code == 0 else f'falhou (código {code})'} — se o comando não for "
                  "encontrado, reabra o terminal e rode o setup de novo")
    if provider == "codex" and shutil.which("codex"):
        status = run(["codex", "login", "status"]) or ""
        if "logged in" not in status.lower():
            print("  [--]    Codex sem login: rode `codex login` (conta ChatGPT)")
    if provider == "claude" and shutil.which("claude"):
        print("  [--]    Claude Code: se ainda não fez login, rode `claude` uma vez e autentique")


def offer_mcp_registration(cfg: dict) -> None:
    rep = Report(quiet=True)
    ctx = load_context(cfg, rep)
    provider = cfg["provider"]["name"]
    required = ctx.get("required_mcp", []) if ctx else []
    if not required or not shutil.which(provider):
        return
    servers = list_mcp_servers(provider) or {}
    for name in required:
        if name in servers:
            continue
        hint = ctx.get("mcp", {}).get(name, {}).get("add" if provider == "claude" else "add_codex")
        if not hint:
            print(f"  [aviso] MCP {name!r} exigido pelo contexto e sem comando de registro para {provider}")
            continue
        heading(f"MCP {name}")
        print(f"  Exigido pelo contexto {ctx['name']} e não registrado no {provider}:\n    {hint}")
        if confirm("  Registrar agora (escopo do usuário)?", True):
            shell = ["powershell", "-NoProfile", "-Command", hint] if IS_WINDOWS else ["bash", "-lc", hint]
            subprocess.run(shell)


def offer_codex_trust(cfg: dict) -> None:
    if cfg["provider"]["name"] != "codex" or codex_trusted():
        return
    heading("Codex: projeto confiável")
    print(f"  Marcar {ROOT} como confiável no ~/.codex/config.toml faz o app/CLI do Codex usar o\n"
          "  .codex/config.toml do AiDW (modelo, effort, rede, MCPs) mesmo sem `python aidw.py chat`.")
    if confirm("  Marcar agora?", True):
        entry = f"\n[projects.'{str(ROOT).lower()}']\ntrust_level = \"trusted\"\n"
        CODEX_HOME.mkdir(parents=True, exist_ok=True)
        with (CODEX_HOME / "config.toml").open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(entry)
        print("  Feito.")


def chat(cfg: dict, catalog: dict) -> int:
    rep = Report()
    b = build(cfg, catalog, rep)
    if b is None:
        return 1
    provider = cfg["provider"]["name"]
    if not shutil.which(provider):
        print(f"CLI `{provider}` não encontrado.")
        return 1
    orch = b["resolved"][ORCHESTRATOR]
    if provider == "claude":
        cmd = [shutil.which("claude")]  # modelo, effort e permissões vêm do .claude/settings.local.json
    else:
        cmd = [shutil.which("codex"), "-C", str(ROOT), "-m", orch["model"]["model_id"],
               "-c", f"project_doc_max_bytes={CODEX_DOC_MAX_BYTES}", "-s", "workspace-write",
               "-a", "on-request", "-c", "sandbox_workspace_write.network_access=true"]
        if orch["effort"]:
            cmd += ["-c", f'model_reasoning_effort="{orch["effort"]}"']
        if cfg["delegation"]["mode"] == "native":
            cmd += ["--enable", "multi_agent_v2"]
        for key, s in b["servers"].items():  # sem projeto confiável, o .codex/config.toml não carrega
            cmd += ["-c", f"mcp_servers.{key}={toml_value(codex_mcp_table(s))}"]
        for k, v in codex_git_env(cfg, b["ctx"]).items():
            cmd += ["-c", f"shell_environment_policy.set.{k}={toml_value(v)}"]
        for d in project_dirs(cfg, b["ctx"]):
            if Path(d).is_dir():
                cmd += ["--add-dir", win(d)]
    print(f"Abrindo o orquestrador: {' '.join(Path(cmd[0]).stem if i == 0 else c for i, c in enumerate(cmd))}")
    return subprocess.run(cmd, cwd=ROOT).returncode


def show(cfg: dict, catalog: dict) -> None:
    rep = Report()
    ctx = load_context(cfg, rep)
    resolved = resolve(cfg, catalog, ctx, available_skills(ctx, rep), rep)
    heading(f"AiDW · {PROVIDER_LABEL.get(cfg['provider']['name'], '?')} · delegação "
            f"{cfg['delegation']['mode']} · contexto {ctx['name'] if ctx else 'nenhum'}")
    print(f"  {'NOME':<16} {'EXIBIÇÃO':<16} {'PAPEL':<13} {'MODELO':<26} {'EFFORT':<8} TIPO")
    for role, a in resolved.items():
        kind = "chat" if role == ORCHESTRATOR else (
            "subagente" if cfg["delegation"]["mode"] == "native" else "headless")
        status = "" if a["enabled"] else "  (desabilitado)"
        print(f"  {a['name']:<16} {a['display']:<16} {role:<13} {a['model']['model_id']:<26} "
              f"{a['effort'] or '—':<8} {kind}{status}")
    print(f"\n  Estado: {state_dir(ctx).as_posix()}")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # console cp1252 quebra em acentos e setas
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="AiDW — orquestrador e agentes especializados.")
    sub = parser.add_subparsers(dest="command")
    p_setup = sub.add_parser("setup", help="pré-requisitos + wizard (se necessário) + apply + doctor")
    p_setup.add_argument("--reconfigure", action="store_true", help="refaz o wizard mesmo com config existente")
    p_setup.add_argument("--skip-tools", action="store_true", help="não verifica/instala pré-requisitos")
    p_conf = sub.add_parser("configure", help="wizard interativo")
    p_conf.add_argument("--defaults", action="store_true", help="grava a config padrão sem perguntar")
    p_conf.add_argument("--provider", choices=PROVIDERS, help="com --defaults: provedor da config padrão")
    p_apply = sub.add_parser("apply", help="gera o ambiente a partir de aidw.config.toml")
    p_apply.add_argument("--dry-run", action="store_true", help="mostra o que mudaria, sem alterar nada")
    sub.add_parser("doctor", help="verifica o ambiente")
    sub.add_parser("show", help="mostra agentes, modelos e efforts")
    sub.add_parser("chat", help="abre o orquestrador no CLI do provedor")
    p_del = sub.add_parser("delegate", help="roda um agente headless para uma tarefa")
    p_del.add_argument("--agent", required=True, help="nome ou papel do agente")
    p_del.add_argument("--effort", choices=EFFORTS, help="effort desta tarefa (padrão: o do nível/agente)")
    p_del.add_argument("--level", help="nível da tarefa ([effort.levels] do routing.toml)")
    p_del.add_argument("--model", help="outro modelo do provedor (só quando o usuário pedir)")
    p_del.add_argument("--task", required=True, help="arquivo .md com a tarefa")
    p_del.add_argument("--demand", required=True, help="pasta da demanda (resultado e metricas.md)")
    p_del.add_argument("--label", help="rótulo do resultado, ex.: t1-r1 (padrão: nome do arquivo da tarefa)")
    p_del.add_argument("--max-turns", type=int, help="limite de turnos (Claude)")
    p_del.add_argument("--timeout", type=int, default=3600, help="tempo máximo em segundos (padrão 3600)")
    p_rec = sub.add_parser("record", help="registra uma delegação feita com subagente nativo")
    p_rec.add_argument("--agent", required=True, help="nome, papel ou variante (ex.: codificador-high)")
    p_rec.add_argument("--effort", choices=EFFORTS, help="effort usado (padrão: o da variante ou do nível)")
    p_rec.add_argument("--level", help="nível da tarefa")
    p_rec.add_argument("--label", required=True, help="rótulo, ex.: t1-r1")
    p_rec.add_argument("--demand", required=True, help="pasta da demanda (metricas.md)")
    p_rec.add_argument("--state", help="state do JSON final do agente")
    p_rec.add_argument("--tokens", type=int, help="Claude: subagent_tokens do resultado do Agent")
    p_rec.add_argument("--tool-uses", type=int, help="Claude: tool_uses do resultado do Agent")
    p_rec.add_argument("--duration-ms", type=int, help="Claude: duration_ms do resultado do Agent")
    p_rec.add_argument("--codex-task", help="Codex: task_name do spawn (lê os tokens reais da sessão)")
    args = parser.parse_args()
    command = args.command or "setup"

    catalog = load_catalog()
    cfg = load_config()

    if command == "configure":
        if args.defaults:
            cfg = default_config(args.provider or (cfg or default_config())["provider"]["name"])
        else:
            cfg = wizard(cfg or default_config((installed_providers() or ["claude"])[0]), catalog)
        save_config(cfg)
        print("Próximo passo: python aidw.py apply")
        return 0

    if command == "setup":
        if cfg is None or getattr(args, "reconfigure", False):
            cfg = wizard(cfg or default_config((installed_providers() or ["claude"])[0]), catalog)
            if not confirm("\nGravar e aplicar esta configuração?", True):
                print("Nada foi gravado.")
                return 1
            save_config(cfg)
        elif context_missing(cfg):
            heading("Contexto não encontrado")
            ask_context(cfg, "")
            save_config(cfg)
        if not args.skip_tools:
            ensure_tools(cfg["provider"]["name"])
        if not apply(cfg, catalog, dry=False):
            return 1
        offer_mcp_registration(cfg)
        offer_codex_trust(cfg)
        ok = doctor(cfg, catalog)
        print("\nPronto. Abra o orquestrador: `python aidw.py chat` (ou o app do provedor na pasta do AiDW).")
        return 0 if ok else 1

    if cfg is None:
        print("aidw.config.toml não encontrado. Rode `python aidw.py setup` ou `configure`.")
        return 1
    if command == "apply":
        return 0 if apply(cfg, catalog, dry=args.dry_run) else 1
    if command == "doctor":
        return 0 if doctor(cfg, catalog) else 1
    if command == "show":
        show(cfg, catalog)
        return 0
    if command == "chat":
        return chat(cfg, catalog)
    if command == "delegate":
        return delegate(cfg, catalog, args)
    if command == "record":
        return record(cfg, catalog, args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
