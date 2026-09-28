#!/usr/bin/env python3
"""AiDW — ambiente de desenvolvimento agêntico com orquestrador e agentes especializados.

Uso:
    python aidw.py setup [--reconfigure]   # pré-requisitos + wizard + apply + doctor
    python aidw.py configure [--defaults]  # só o wizard; grava aidw.config.toml
    python aidw.py apply [--dry-run]       # gera o ambiente a partir da config (idempotente)
    python aidw.py doctor                  # verifica tudo e diz se o ambiente está pronto
    python aidw.py install [--dry-run]     # AiDW em qualquer pasta no Claude (plugin aidw)
    python aidw.py uninstall [--dry-run]   # remove só o que o install acrescentou
    python aidw.py install --provider codex|all   # também no Codex (skills, agentes, hooks, rules, perfil aidw)
    python aidw.py open [--provider codex] [--demand <id>]   # abre o chat no worktree da demanda
    python aidw.py worktree create --repo <pasta> --demand <id> [--slug s] [--base b]   # e list/inspect/remove/cleanup
    python aidw.py project detect [--path <pasta>] [--json]
    python aidw.py context list | check <nome> | use <nome> | create <nome> --description d
    python aidw.py demand set <id> [--step S] [--status active|paused|done] [--note n]   # e show/list
    python aidw.py show                    # agentes, nomes, modelos e efforts resolvidos
    python aidw.py chat                    # abre o orquestrador no CLI do provedor
    python aidw.py delegate --agent <papel|nome> --effort <e> --task <arq> --demand <pasta>

Um provedor por instalação ([provider].name): tudo roda no Claude Code ou tudo roda no Codex.
O chat aberto na raiz do AiDW é o orquestrador; cada agente roda headless, um processo por
tarefa, com o modelo do agente e o effort que o orquestrador escolher para aquela tarefa.
"""
from __future__ import annotations

import argparse
import contextlib
import io
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
ORCH_REF_DIR = ROOT / "orchestrator" / "reference"   # lidas sob demanda pelo orquestrador
POLICIES_DIR = ROOT / "orchestrator" / "policies"
AGENTS_DIR = ROOT / "agents"
SKILLS_DIR = ROOT / "skills"
CONTEXTS_DIR = ROOT / "contexts"
WORKFLOWS_DIR = ROOT / "workflows"

GEN_DIR = ROOT / ".aidw"                       # gerado, independente do provedor
GEN_AGENTS_DIR = GEN_DIR / "agents"            # definição de cada agente (markdown)
CLAUDE_AGENTS_JSON = GEN_DIR / "claude-agents.json"
RUNTIME_FILE = GEN_DIR / "runtime.json"
GEN_REF_DIR = GEN_DIR / "reference"           # referências do orquestrador, já renderizadas

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
# Instalação global no Claude (aidw.py install): um plugin por contexto num marketplace local.
CLAUDE_HOME = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
USER_SETTINGS = CLAUDE_HOME / "settings.json"
MARKETPLACE_DIR = GEN_DIR / "marketplace"
MARKETPLACE_NAME = "aidw-local"
INSTALL_MANIFEST = GEN_DIR / "install-manifest.json"
PLUGIN_VERSION_BASE = "3.0.0"
# Instalação global no Codex (aidw.py install --provider codex): arquivos próprios do AiDW, nomes `aidw-*`.
CODEX_NS = "aidw-"
CODEX_SKILLS_HOME = Path(os.environ.get("AIDW_CODEX_SKILLS_DIR") or Path.home() / ".agents" / "skills")
CODEX_AGENTS_HOME = CODEX_HOME / "agents"
CODEX_GLOBAL_RULES = CODEX_HOME / "rules" / "aidw.rules"
CODEX_HOOKS_FILE = CODEX_HOME / "hooks.json"
CODEX_PROFILE_NAME = "aidw"
CODEX_PROFILE = CODEX_HOME / f"{CODEX_PROFILE_NAME}.config.toml"
# Descrições do plugin entram em toda sessão: o aviso evita que o Claude use o AiDW fora de uma demanda.
PLUGIN_GUARD = "[AiDW] Só dentro de uma demanda conduzida pelo orquestrador AiDW."
ADMIN_GUARD = "[AiDW] Administração do AiDW."  # skills com `aidw: admin` (contextos): valem fora de uma demanda
# O Codex corta o AGENTS.md em 32 KiB por padrão; o AiDW sobe o limite do orquestrador.
CODEX_DOC_MAX_BYTES = 98304

IS_WINDOWS = os.name == "nt"
# Raiz dos worktrees das demandas: curta (MSBuild legado e MAX_PATH) e fora de qualquer repositório.
DEFAULT_WORKTREE_ROOT = "C:/wt" if IS_WINDOWS else "~/wt"
REGISTRY_FILE = ROOT / "state" / "worktrees.json"   # registro dos worktrees das demandas (o git é a verdade)
GUARD_SCRIPT = ROOT / "aidw_guard.py"               # hook PreToolUse do plugin
# Dependências de build fora do git que o worktree recebe por junction (se existirem no working copy).
DEFAULT_WORKTREE_LINKS = ["packages", "node_modules"]
DEMAND_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
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
# skills  = disponíveis para o agente (listadas no prompt; ele chama com o Skill tool quando precisa)
# preload = subconjunto injetado inteiro no início de cada execução — só o que ele usa sempre.
DEFAULT_AGENTS: dict[str, dict] = {
    "orchestrator": {"enabled": True, "tier": "top", "effort": "high",
                     "skills": ["to-spec", "verificar-premissa", "preparar-worktree"]},
    "coder": {"enabled": True, "tier": "top", "effort": "medium", "skills": ["preparar-worktree"]},
    "reviewer": {"enabled": True, "tier": "mid", "effort": "high",
                 "skills": ["code-review", "verificar-premissa"], "preload": ["code-review"]},
    "api-db": {"enabled": True, "tier": "mid", "effort": "medium", "skills": ["database-safe"]},
    "qa": {"enabled": False, "tier": "mid", "effort": "medium", "skills": []},
    "documenter": {"enabled": True, "tier": "fast", "effort": "medium", "skills": []},
    # Especialistas sob demanda: o orquestrador decide quando uma passada vale o custo.
    "bug-hunter": {"enabled": True, "tier": "mid", "effort": "high",
                   "skills": ["bug-hunt", "verificar-premissa"], "preload": ["bug-hunt"]},
    "security": {"enabled": True, "tier": "mid", "effort": "high",
                 "skills": ["security-audit", "verificar-premissa"], "preload": ["security-audit"]},
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
        "worktree": {"root": DEFAULT_WORKTREE_ROOT},
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
    for section in ("provider", "delegation", "workspace", "worktree", "mcp", "context", "policies"):
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
        "[worktree]",
        "# Onde ficam os worktrees das demandas (<raiz>/<repo>/<id>). Curta e fora de qualquer repositório.",
        f"root = {toml_value(cfg['worktree']['root'])}",
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
        if a.get("preload"):
            out.append(f"preload = {toml_value(a['preload'])}")
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


def worktree_root(cfg: dict) -> Path:
    return Path(os.path.expanduser(cfg["worktree"]["root"]))


def required_folders(cfg: dict, ctx: dict | None) -> list[tuple[Path, str]]:
    """Pastas que o AiDW precisa e que o setup cria quando faltam."""
    return [(CONTEXTS_DIR, "contextos de trabalho"), (state_dir(ctx), "estado das demandas"),
            (worktree_root(cfg), "worktrees das demandas")]


def code_dirs(cfg: dict, ctx: dict | None) -> list[str]:
    """Onde os agentes mexem em código: as pastas de projeto e a raiz dos worktrees das demandas."""
    return list(dict.fromkeys([*project_dirs(cfg, ctx), worktree_root(cfg).as_posix()]))


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


def orchestrator_policy_refs(ctx: dict | None) -> list[tuple[Path, str]]:
    """Policies que o orquestrador lê sob demanda (frontmatter `orchestrator_when`)."""
    return [(f, w) for f in policy_files(ctx) if (w := read_frontmatter(f)[0].get("orchestrator_when"))]


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
        ctx_agent = ctx.get("agents", {}).get(role, {}) if ctx else {}
        all_skills = list(dict.fromkeys([*a.get("skills", []), *ctx_agent.get("skills", [])]))
        preload = list(dict.fromkeys([*a.get("preload", []), *ctx_agent.get("preload", [])]))
        for s in all_skills:
            if s not in skills:
                rep.error(f"agente {role}: skill {s!r} não encontrada")
        for s in preload:
            if s not in all_skills:
                rep.error(f"agente {role}: preload {s!r} precisa estar também em skills")
        slug, display = agent_names(role, a)
        resolved[role] = {"role": role, "enabled": a.get("enabled", True), "name": slug,
                          "display": display, "skills": all_skills, "preload": preload, "model": model,
                          "effort": effort}

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
        "# Worktree por demanda: branch `<prefixo><número>-<slug>` e junctions de dependências fora do git.",
        "[worktree]",
        'branch_prefix = "feature/"',
        'link = ["packages", "node_modules"]',
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

    def __init__(self, resolved: dict, ctx: dict | None, rep: Report, ns: str = "") -> None:
        self.names = {role: ns + a["name"] for role, a in resolved.items()}
        self.ns = ns
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
        return f"<!-- fonte: {rel(path)} -->\n\n{self.render(read_frontmatter(path)[1].strip(), path)}"


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


def skills_section(names: list[str], skills: dict[str, Path], provider: str,
                   preload: list[str] | None = None, ns: str = "") -> str:
    if not names:
        return ""
    preload = preload or []
    how = ("Invoke one with the `Skill` tool when the step needs it; those marked *loaded* are already "
           "in your context — do not invoke them again." if provider == "claude" else
           "Codex may list them as skills; if not, read the `SKILL.md` below and follow it.")
    rows = ["## Skills", "", f"Procedures you use in your process. {how}", ""]
    rows += [f"- `{ns}{n}` — `{(skills[n] / 'SKILL.md').as_posix()}`" + (" (*loaded*)" if n in preload else "")
             for n in names if n in skills]
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
    rows = ["| Server | Triggers | Agents |", "|---|---|---|"]
    for key, s in servers.items():
        agents = ", ".join(f"`{resolved[r]['name']}`" for r in s.get("agents", []) if r in resolved) or "all"
        rows.append(f"| {s['name']} (`{key}`) | {'; '.join(s.get('triggers', []))} | {agents} |")
    return "\n".join([
        "## MCP tools", "",
        "Before every delegation, name in the task only the servers whose trigger clearly applies and "
        "that the receiving agent has, with the goal (e.g. \"Use the Playwright MCP to confirm acceptance "
        "criteria 2 and 3\"); if none applies, write \"No MCP tools needed\". Never add one speculatively.",
        "", *rows,
    ])


def render_agent(role: str, a: dict, cfg: dict, ctx: dict | None, tpl: Templater, servers: dict,
                 skills: dict, routing: dict, ns: str = "") -> tuple[dict, str]:
    """(frontmatter, markdown) da definição do agente — a mesma para Claude e Codex."""
    source = AGENTS_DIR / role / "AGENT.md"
    meta, body = read_frontmatter(source)
    provider = cfg["provider"]["name"]
    orch = tpl.names[ORCHESTRATOR]
    sources = [source, *policy_files(ctx), *context_files(ctx, role)]
    cmd = "install" if ns else "apply"
    parts = [
        f"<!-- {GENERATED_MARK} {cmd} a partir de: {', '.join(rel(s) for s in sources)}.\n"
        f"     Não edite: altere as fontes e rode `python aidw.py {cmd}`. -->",
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
        skills_section(a["skills"], skills, provider, a["preload"], ns),
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


def claude_agent_entry(role: str, meta: dict, prompt: str, ctx: dict | None, servers: dict,
                       preload: list[str] | None = None) -> dict:
    entry: dict = {"description": meta["description"], "prompt": prompt}
    if preload:
        entry["skills"] = list(preload)  # o --agents aceita o mesmo campo do frontmatter
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


def effort_table(resolved: dict, routing: dict, cfg: dict, ns: str = "") -> str:
    eff = routing.get("effort", {})
    levels = eff.get("levels", {})
    roles = [r for r, a in resolved.items() if r != ORCHESTRATOR and a["enabled"]]
    if not levels or not roles:
        return ""
    claude_native = cfg["provider"]["name"] == "claude" and cfg["delegation"]["mode"] == "native"
    rows = ["| Level | When | " + " | ".join(f"`{ns}{resolved[r]['name']}`" for r in roles) + " |",
            "|---|---|" + "---|" * len(roles)]
    for lvl, spec in levels.items():
        cells = []
        for r in roles:
            a = resolved[r]
            model, effort = a["by_level"].get(lvl, (a["model"], a["effort"]))
            if claude_native:
                cells.append(f"`{ns}{variant_name(a, model, effort)}`")
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


def aidw_command(global_mode: bool) -> str:
    """Como chamar o aidw.py: relativo no modo projeto (o chat está na raiz), absoluto no plugin."""
    return f'python "{ROOT.as_posix()}/aidw.py"' if global_mode else "python aidw.py"


def record_hint(codex: bool, global_mode: bool = False) -> str:
    usage = ("--codex-task <task_name>" if codex else
             "--tokens <subagent_tokens> --tool-uses <tool_uses> --duration-ms <duration_ms>")
    return (f"{aidw_command(global_mode)} record --agent <name> [--effort <effort>] --level <level> --label <label> "
            f"--demand <demand dir> --state <state> {usage}")


def delegation_section(cfg: dict, resolved: dict, global_mode: bool = False) -> str:
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
            "- Parallel tickets: several `Agent` calls in the same message, or `run_in_background`.",
            "- After **every** subagent returns, record it — this appends `metricas.md` and prints the "
            "`header` and `resumo` you must show (*SHOWING RESULTS*):",
            "", "```", record_hint(codex=False, global_mode=global_mode), "```", "",
            "  `--agent` is the `subagent_type` you used (the effort comes from it); the numbers are the "
            "ones in the Agent result (`subagent_tokens`, `tool_uses`, `duration_ms`). Never estimate.",
            "- Cheap exploration: the built-in `Explore` subagent (read-only) for sweeping code and "
            "returning `file:line` pointers.",
        ]
        return "\n".join(lines)
    if global_mode:
        return "\n".join([
            "## How to delegate", "",
            "The agents are **native Codex sub-agents** installed as roles (`~/.codex/agents/aidw-*.toml`): spawn "
            "them with `spawn_agent`.", "",
            "- `agent_type`: the agent name from the Team table (e.g. `aidw-codificador`) — the role carries the "
            "agent's standing instructions.",
            "- `fork_turns: \"none\"` (a full-history fork rejects `agent_type`, `model` and `reasoning_effort`).",
            "- `model`: the agent's model from the Team table. `reasoning_effort`: the cell of the *Effort per task* "
            "table — that is how you choose the effort.",
            "- `task_name`: `<agent>-<label>` (e.g. `aidw-codificador-t1-r1`), unique in the demand.",
            "- `message`: `Task: <task file>. Demand folder: <demand dir>. Worktree: <path>. Level: <level>, effort "
            "<effort>. Finish with the JSON of your OUTPUT section.` plus the MCP choice.",
            "- Sub-agents inherit your sandbox, rules and MCP servers; the `aidw` profile makes the worktree root "
            "writable. Only the agents allowed to edit code may edit it (their definition says so).",
            "- Wait for the sub-agent to finish. Then record it — this reads the real token usage of the sub-agent "
            "session, appends `metricas.md` and prints the `header` and `resumo` you must show:",
            "", "```", record_hint(codex=True, global_mode=True), "```", "",
            f"- There is no exploration role: for broad code exploration spawn `{example}` at level `trivial` asking "
            "for `file:line` pointers, or read short excerpts yourself.",
        ])
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
        "- Sub-agents inherit your sandbox, rules and MCP servers: the task must say which MCP to use, and "
        "only the agents allowed to edit code may edit it (their definition says so).",
        "- Wait for the sub-agent to finish. Then record it — this reads the real token usage of the "
        "sub-agent session, appends `metricas.md` and prints the `header` and `resumo` you must show:",
        "", "```", record_hint(codex=True, global_mode=global_mode), "```", "",
        f"- There is no exploration role: for broad code exploration spawn `{example}` at level `trivial` "
        "asking for `file:line` pointers, or read short excerpts yourself.",
        "- Your own skills: see the *Skills* section — read each `SKILL.md` and follow it when the "
        "workflow or a trigger says to use it.",
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
            "- Your own skills: see the *Skills* section — read each `SKILL.md` and follow it when the "
            "workflow or a trigger says to use it.",
        ]
    return "\n".join(lines)


CODEX_SUBAGENT_GUARD = (
    "> **Sub-agents:** if you were spawned by the orchestrator and told that your standing instructions "
    "are in `.aidw/agents/<name>.md`, you are **not** the orchestrator: ignore this entire file and follow "
    "only that definition.")


def orchestrator_references(ctx: dict | None, tpl: Templater) -> dict[str, dict]:
    """{nome: {when, source, content}}: as genéricas (orchestrator/reference, `when` no frontmatter) e as
    do contexto ([agents.orchestrator] reference). Lidas só na etapa que precisa, fora do CLAUDE.md."""
    refs: dict[str, dict] = {}
    sources = [(f, read_frontmatter(f)[0].get("when", "")) for f in sorted(ORCH_REF_DIR.glob("*.md"))] \
        if ORCH_REF_DIR.is_dir() else []
    if ctx:
        sources += [(ctx["dir"] / r["path"], r.get("when", ""))
                    for r in ctx.get("agents", {}).get(ORCHESTRATOR, {}).get("reference", [])]
    sources += orchestrator_policy_refs(ctx)
    cmd = "install" if tpl.ns else "apply"
    for path, when in sources:
        if path.stem in refs:
            tpl.rep.error(f"referência do orquestrador com nome repetido {path.stem!r}: {rel(refs[path.stem]['source'])} "
                          f"e {rel(path)} (renomeie uma delas)")
            continue
        body = read_frontmatter(path)[1]
        header = (f"<!-- {GENERATED_MARK} {cmd} a partir de {rel(path)}; não edite: altere a fonte e rode "
                  f"`python aidw.py {cmd}`. -->")
        refs[path.stem] = {"when": when, "source": path,
                           "content": header + "\n\n" + tpl.render(body.strip(), path) + "\n"}
    return refs


def orchestrator_reference_section(refs: dict[str, dict], ref_dir: Path = GEN_REF_DIR) -> str:
    if not refs:
        return ""
    rows = ["## Reference (read on demand)", "",
            "Not in your context until you read it. Read a file when its moment comes (the workflow names "
            "it) — and again after a context compaction, if you are in that step.", ""]
    rows += [f"- *{name}* `{(ref_dir / (name + '.md')).as_posix()}` — {r['when']}" for name, r in refs.items()]
    return "\n".join(rows)


def render_orchestrator(resolved: dict, cfg: dict, ctx: dict | None, tpl: Templater, servers: dict,
                        skills: dict, routing: dict, refs: dict[str, dict] | None = None, ns: str = "",
                        ref_dir: Path = GEN_REF_DIR) -> str:
    orch = resolved[ORCHESTRATOR]
    provider, mode = cfg["provider"]["name"], cfg["delegation"]["mode"]
    codex_native = provider == "codex" and mode == "native"
    first_col = {"headless": "Agent (`--agent`)", "native": "Agent"}[mode]
    with_definition = not (provider == "claude" and mode == "native")
    team = [f"| {first_col} | Display name | Role | Model | Default effort |"
            + (" Definition |" if with_definition else "") + " Status |",
            "|---|---|---|---|---|" + ("---|" if with_definition else "") + "---|"]
    for role, a in resolved.items():
        if role == ORCHESTRATOR:
            continue
        status = "enabled" if a["enabled"] else "disabled — do not delegate"
        eff = a["effort"] if a["model"].get("efforts") else "—"
        definition = f"`{(GEN_AGENTS_DIR / (a['name'] + '.md')).as_posix()}`" if a["enabled"] else "—"
        team.append(f"| `{ns}{a['name']}` | {a['display']} | {role} | {a['model']['name']} "
                    f"(`{a['model']['model_id']}`) | {eff} |" + (f" {definition} |" if with_definition else "")
                    + f" {status} |")
    source_file = "CLAUDE.md" if provider == "claude" else "AGENTS.md"
    cmd = "install" if ns else "apply"
    parts = [
        f"<!-- {GENERATED_MARK} {cmd} — {'skill orquestrar' if ns else source_file + ' do orquestrador'}; "
        "não edite. Fontes: orchestrator/ORCHESTRATOR.md, orchestrator/policies/ e o contexto ativo; rode "
        f"`python aidw.py {cmd}` após alterá-las. -->",
        CODEX_SUBAGENT_GUARD if codex_native else "",
        tpl.include(ORCHESTRATOR_MD),
        "\n".join(["## Runtime", "",
                   f"- You are `{orch['name']}` — {orch['display']} (role `orchestrator`), the main chat.",
                   f"- Your model: {model_label(orch)}",
                   f"- Delegation mode: **{mode}**",
                   *runtime_lines(cfg, ctx),
                   *([f"- This chat may be in any folder: run the AiDW commands by absolute path "
                      f"(`{aidw_command(True)} ...`)."] if ns else [])]),
        "\n".join(["## Team", "", *team]),
        delegation_section(cfg, resolved, global_mode=bool(ns)),
        effort_table(resolved, routing, cfg, ns),
        skills_section(orch["skills"], skills, provider, ns=ns),
        mcp_orchestrator_section(servers, resolved),
        systems_section(ctx, detailed=False),
        orchestrator_reference_section(refs or {}, ref_dir),
        "# Policies",
        *[tpl.include(p) for p in policy_files(ctx) if p not in {r["source"] for r in (refs or {}).values()}],
    ]
    parts = [x for x in parts if x]
    if context_files(ctx, ORCHESTRATOR):
        parts.append(f"# Context: {ctx['description']}")
        parts += [tpl.include(p) for p in context_files(ctx, ORCHESTRATOR)]
    return "\n\n".join(parts) + "\n"


def render_claude_subagent(role: str, a: dict, meta: dict, prompt: str, effort: str, name: str,
                           ctx: dict | None, servers: dict, model: dict | None = None, ns: str = "",
                           guard: str = "") -> str:
    model = model or a["model"]
    entry = claude_agent_entry(role, meta, prompt, ctx, servers)
    description = meta["description"]
    # Variantes: descrição de uma linha. O orquestrador escolhe pela tabela Effort per task, e a lista
    # de agentes com as descrições entra em toda sessão (a descrição completa fica só no agente base).
    if model["key"] != a["model"]["key"]:
        description = (f"{a['display']} com {model['name']}, effort {effort or '—'}: mesmo papel de "
                       f"{ns}{a['name']}. Só quando a tabela Effort per task indicar.")
        prompt = prompt.replace(f"- Model: {a['model']['name']} (`{a['model']['model_id']}`).",
                                f"- Model: {model['name']} (`{model['model_id']}`).")
    elif name != a["name"]:
        description = (f"{a['display']}, effort {effort}: mesmo papel de {ns}{a['name']}. "
                       "Só quando a tabela Effort per task indicar.")
    if guard:
        description = f"{guard} {description}"
    front = ["---", f"name: {name}", f"description: {json.dumps(description, ensure_ascii=False)}",
             f"model: {model.get('alias') or model['model_id']}"]
    if effort:
        front.append(f"effort: {effort}")
    front.append("omitClaudeMd: true")
    if a["preload"]:
        front += ["skills:", *[f"  - {ns}{x}" for x in a["preload"]]]
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
        f"writable_roots = {toml_value([win(d) for d in code_dirs(cfg, ctx)])}",
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


def build(cfg: dict, catalog: dict, rep: Report, ns: str = "", ref_dir: Path = GEN_REF_DIR) -> dict | None:
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
    tpl = Templater(resolved, ctx, rep, ns)
    agents = {}
    for role, a in resolved.items():
        if role != ORCHESTRATOR and a["enabled"]:
            meta, prompt = render_agent(role, a, cfg, ctx, tpl, servers, skills, routing, ns)
            agents[role] = {"meta": meta, "prompt": prompt}
    refs = orchestrator_references(ctx, tpl)
    orchestrator_md = render_orchestrator(resolved, cfg, ctx, tpl, servers, skills, routing, refs, ns, ref_dir)
    if rep.errors:
        return None
    return {"ctx": ctx, "skills": skills, "resolved": resolved, "routing": routing, "servers": servers,
            "agents": agents, "orchestrator_md": orchestrator_md, "orchestrator_refs": refs}


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
    refs = b["orchestrator_refs"]
    sync_generated_dir(GEN_REF_DIR, {n: r["content"] for n, r in refs.items()}, ".md", dry, rep)
    if refs:
        rep.info(f"referências do orquestrador (lidas sob demanda): {', '.join(refs)}")

    if provider == "claude":
        heading("Claude Code (CLAUDE.md, .claude/, .mcp.json)")
        write_if_changed(CLAUDE_MD, b["orchestrator_md"], dry, rep)
        agents_json = {resolved[r]["name"]: claude_agent_entry(r, g["meta"], g["prompt"], ctx, servers,
                                                               resolved[r]["preload"])
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
            "additionalDirectories": code_dirs(cfg, ctx),  # projetos + raiz dos worktrees
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
                          "effort": a["effort"], "skills": a["skills"], "preload": a["preload"]}
                   for role, a in resolved.items()},
        "mcp": list(servers),
        "claude_settings": managed if provider == "claude" else prev.get("claude_settings", {}),
    }
    write_if_changed(RUNTIME_FILE, json.dumps(runtime, indent=2, ensure_ascii=False) + "\n", dry, rep)
    print(f"\nConcluído{' (nada foi alterado: dry-run)' if dry else ''}"
          f"{f' com {len(rep.warnings)} aviso(s)' if rep.warnings else ''}. Abra um chat novo na raiz do AiDW.")
    return True


# ---------------------------------------------------------------------------
# Instalação global no Claude: plugin por contexto (aidw.py install / uninstall)
# ---------------------------------------------------------------------------

def plugin_name(ctx: dict | None = None) -> str:
    """Sempre `aidw`: comandos e agentes têm o mesmo nome em qualquer máquina e contexto (o contexto ativo muda
    o conteúdo do plugin — regras, sistemas, políticas —, não o nome)."""
    return "aidw"


def sha(content: bytes) -> str:
    import hashlib
    return hashlib.sha256(content).hexdigest()


def is_admin_skill(path: Path) -> bool:
    return read_frontmatter(path)[0].get("aidw") == "admin"


def guard_skill(text: str) -> str:
    """Põe o aviso do AiDW no começo da descrição do SKILL.md, tira a marca `aidw:` do frontmatter e resolve
    `{{root}}` (a skill roda em qualquer pasta e chama o aidw.py pelo caminho absoluto)."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return text
    end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), len(lines))
    admin = any(line.strip() == "aidw: admin" for line in lines[1:end])
    guard = ADMIN_GUARD if admin else PLUGIN_GUARD
    for i in range(1, end):
        if lines[i].startswith("description:"):
            value = lines[i][len("description:"):].strip()
            quote = value[:1] if value[:1] in "\"'" else ""
            value = value[1:] if quote else value
            lines[i] = f"description: {quote}{guard} {value}"
    lines = [line for i, line in enumerate(lines) if not (0 < i < end and line.startswith("aidw:"))]
    return "\n".join(lines).replace("{{root}}", ROOT.as_posix())


def orchestrator_skill(plugin: str, ctx: dict | None, orchestrator_md: str, skill_path: Path,
                       provider: str = "claude") -> str:
    aidw = aidw_command(True)
    codex = provider == "codex"
    leave = "$aidw-sair" if codex else f"/{plugin}:sair"
    workspace = ("6. **Código:** worktree da demanda (seção *Workspace*). No Codex não há `EnterWorktree`: toda tarefa "
                 "leva o caminho absoluto do worktree. O `worktree create` grava no `.git` do repositório, que o sandbox "
                 "do Codex deixa só leitura: peça aprovação (escalada) para esse comando. Se a raiz dos worktrees não for "
                 "gravável (sessão aberta sem o "
                 f"perfil `{CODEX_PROFILE_NAME}`), peça ao usuário para reabrir com `{aidw} open --provider codex "
                 "--demand <id>`." if codex else
                 "6. **Código:** worktree da demanda (seção *Workspace*) e `EnterWorktree` com o id da demanda.")
    description = (f"{PLUGIN_GUARD} Assume esta sessão como orquestrador do AiDW e conduz uma demanda de "
                   "ponta a ponta: spec, tickets, agentes, revisão e revisão final.")
    return "\n".join([
        "---", f"name: {CODEX_NS + 'orquestrar' if codex else 'orquestrar'}",
        f"description: {json.dumps(description, ensure_ascii=False)}",
        *([] if codex else ["disable-model-invocation: true"]), "---", "",
        f"<!-- {GENERATED_MARK} install; não edite: altere as fontes e rode `python aidw.py install`. -->", "",
        "# Modo orquestrador AiDW", "",
        f"A partir desta mensagem você é o orquestrador AiDW nesta sessão, até o usuário chamar "
        f"`{leave}` ou pedir para parar. Pedido do usuário (pode estar vazio): " +
        ("o texto da mensagem que chamou esta skill." if codex else "$ARGUMENTS"), "",
        f"Depois de uma compactação da conversa, releia `{skill_path.as_posix()}` antes de continuar.", "",
        "## Ao ser chamado: abrir ou retomar a demanda", "",
        f"1. Rode `{aidw} project detect --json` (pasta atual) e `{aidw} demand list --active --json`.",
        "2. **Qual demanda:** a do pedido, se ele citar uma (ex.: `1234` → `us-1234`, `bug-5678`); senão "
        "a da pasta (`demand`, quando o chat está num worktree); senão a única ativa deste repositório. Mais de "
        "uma candidata, ou nenhuma e sem pedido: pergunte ao usuário, com as opções.",
        "3. **Retomar:** se a demanda já tem `demand.json`, **não recomece** — leia a pasta dela (plano, triagens, "
        "reviews, `estado.md`) e continue da etapa gravada (`step`).",
        f"4. **Nova:** `{aidw} demand set <id> --status active --step UNDERSTAND --title \"<título>\"` e siga "
        "o fluxo.",
        f"5. **A cada etapa** (cada ação de *NEXT ACTION*): `{aidw} demand set <id> --step <AÇÃO>`; no fim, "
        "`--status done`. Pedido só de leitura (explicar, analisar) não abre demanda.",
        workspace, "",
        orchestrator_md.strip(), "",
    ])


def exit_skill(plugin: str, provider: str = "claude") -> str:
    codex = provider == "codex"
    description = f"{PLUGIN_GUARD} Encerra o modo orquestrador AiDW nesta sessão."
    return "\n".join([
        "---", f"name: {CODEX_NS + 'sair' if codex else 'sair'}", f"description: {json.dumps(description, ensure_ascii=False)}",
        *([] if codex else ["disable-model-invocation: true"]), "---", "",
        "Saia do modo orquestrador AiDW. Se há uma demanda aberta nesta sessão, grave onde parou: "
        f"`{aidw_command(True)} demand set <id> --status paused --note \"<próximo passo>\"` e, se ajudar, um "
        "`estado.md` curto na pasta dela. Depois responda normalmente, sem as regras do orquestrador, até "
        f"`{'$aidw-orquestrar' if codex else '/' + plugin + ':orquestrar'}` ser chamado de novo (ele retoma da etapa "
        "gravada).", "",
    ])


def build_plugin(cfg: dict, catalog: dict, rep: Report) -> dict | None:
    """Renderiza o marketplace local com o plugin `aidw` (conteúdo do contexto ativo): {caminho relativo: bytes}."""
    if cfg["provider"]["name"] != "claude":
        rep.error("a instalação global por plugin é do Claude; no Codex ela vem na F6 do plano v3")
        return None
    if cfg["delegation"]["mode"] != "native":
        rep.error('a instalação global usa subagentes nativos: use [delegation] mode = "native" '
                  "(o modo headless continua disponível pelo `apply`, na raiz do AiDW)")
        return None
    ctx = load_context(cfg, rep)
    plugin = plugin_name(ctx)
    base = f"plugins/{plugin}"
    plugin_dir = MARKETPLACE_DIR / base
    b = build(cfg, catalog, rep, ns=f"{plugin}:", ref_dir=plugin_dir / "reference")
    if b is None:
        return None
    resolved, ctx = b["resolved"], b["ctx"]
    files: dict[str, bytes] = {}

    def put(rel_path: str, text: str) -> None:
        files[rel_path] = text.encode("utf-8")

    for role, g in b["agents"].items():
        a = resolved[role]
        for name, v in a["variants"].items():
            put(f"{base}/agents/{name}.md",
                render_claude_subagent(role, a, g["meta"], g["prompt"], v["effort"], name, ctx, b["servers"],
                                       v["model"], ns=f"{plugin}:", guard=PLUGIN_GUARD))
    used = set(resolved[ORCHESTRATOR]["skills"])
    for a in resolved.values():
        if a["enabled"]:
            used |= set(a["skills"])
    used |= {n for n, d in b["skills"].items() if is_admin_skill(d / "SKILL.md")}
    for name in sorted(used & set(b["skills"])):
        src = b["skills"][name]
        for f in sorted(src.rglob("*")):
            if f.is_file():
                data = f.read_bytes()
                if f.name == "SKILL.md":
                    data = guard_skill(data.decode("utf-8")).encode("utf-8")
                files[f"{base}/skills/{name}/{f.relative_to(src).as_posix()}"] = data
    put(f"{base}/skills/orquestrar/SKILL.md",
        orchestrator_skill(plugin, ctx, b["orchestrator_md"], plugin_dir / "skills" / "orquestrar" / "SKILL.md"))
    put(f"{base}/skills/sair/SKILL.md", exit_skill(plugin))
    for name, r in b["orchestrator_refs"].items():
        put(f"{base}/reference/{name}.md", r["content"])
    py = f'python "{ROOT.as_posix()}/aidw.py"'
    put(f"{base}/hooks/hooks.json", json.dumps({"hooks": {
        "PreToolUse": [{"matcher": "Edit|Write|MultiEdit|NotebookEdit",
                        "hooks": [{"type": "command", "command": f'python "{GUARD_SCRIPT.as_posix()}"'}]}],
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": f'python "{GUARD_SCRIPT.as_posix()}"'}]}],
        "SessionStart": [{"matcher": "compact|resume",
                          "hooks": [{"type": "command", "command": f'python "{GUARD_SCRIPT.as_posix()}"'}]}],
        "WorktreeCreate": [{"hooks": [{"type": "command", "command": f"{py} worktree hook-create"}]}],
        "WorktreeRemove": [{"hooks": [{"type": "command", "command": f"{py} worktree hook-remove"}]}],
    }}, indent=2, ensure_ascii=False) + "\n")
    version = f"{PLUGIN_VERSION_BASE}-{sha(b''.join(k.encode() + v for k, v in sorted(files.items())))[:10]}"
    description = "AiDW — orquestrador e agentes especializados"
    put(f"{base}/.claude-plugin/plugin.json", json.dumps(
        {"name": plugin, "version": version, "description": description, "author": {"name": "AiDW"}},
        indent=2, ensure_ascii=False) + "\n")
    put(".claude-plugin/marketplace.json", json.dumps(
        {"name": MARKETPLACE_NAME, "owner": {"name": "AiDW"},
         "description": "Plugins gerados pelo AiDW nesta máquina (python aidw.py install).",
         "plugins": [{"name": plugin, "source": f"./{base}", "description": description}]},
        indent=2, ensure_ascii=False) + "\n")
    return {"plugin": plugin, "version": version, "files": files, "ctx": ctx, "build": b}


def global_managed_settings(cfg: dict, ctx: dict | None, servers: dict) -> dict:
    """O que o AiDW acrescenta ao ~/.claude/settings.json (camada 1 da D3 do plano v3)."""
    perms = ctx.get("permissions", {}) if ctx else {}
    # As grafias comuns do mesmo caminho (os modelos variam): com/sem aspas, / ou \, e /c/... no Git Bash.
    posix, windows = (ROOT / "aidw.py").as_posix(), win(ROOT / "aidw.py")
    drive = re.match(r"^([A-Za-z]):/(.*)$", posix)
    gitbash = f"/{drive.group(1).lower()}/{drive.group(2)}" if drive else posix
    forms = {"Bash": list(dict.fromkeys([f'"{posix}"', posix, f'"{windows}"', gitbash])),
             "PowerShell": list(dict.fromkeys([f'"{posix}"', posix, f'"{windows}"', windows]))}
    aidw_rules = [f"{tool}(python {form} {sub})" for tool, tool_forms in forms.items() for form in tool_forms
                  for sub in ("record *", "show", "doctor", "project *", "demand *", "worktree *", "context *")]
    return {
        "allow": list(dict.fromkeys([*perms.get("allow", []), *aidw_rules,
                                     *[f"mcp__{k}" for k, s in servers.items() if s.get("allow")]])),
        "ask": list(dict.fromkeys([*cfg["policies"]["ask"], *perms.get("ask", []),
                                   *expand_git_ask(perms.get("git_ask", []))])),
        "deny": list(dict.fromkeys([*cfg["policies"]["deny"], *perms.get("deny", [])])),
        # a sessão pode estar em qualquer pasta: o AiDW (estado das demandas), os projetos e os worktrees
        "additionalDirectories": list(dict.fromkeys([ROOT.as_posix(), *project_dirs(cfg, ctx),
                                                     worktree_root(cfg).as_posix()])),
        "env": {k: str(v) for k, v in ctx.get("env", {}).items()} if ctx else {},
    }


def merge_owned(existing: list, owned_before: list, managed: list) -> tuple[list, list]:
    """(lista final, itens do AiDW). Um item que o usuário já tinha continua dele e nunca é removido."""
    kept = [x for x in existing if x not in owned_before]
    owned = [x for x in managed if x not in kept]
    return kept + owned, owned


def merge_user_settings(managed: dict, owned_before: dict, dry: bool, rep: Report) -> dict | None:
    """Aplica no ~/.claude/settings.json só o que é do AiDW; devolve o que ficou sendo do AiDW."""
    try:
        data = json.loads(USER_SETTINGS.read_text(encoding="utf-8")) if USER_SETTINGS.exists() else {}
    except json.JSONDecodeError:
        rep.error(f"{USER_SETTINGS} não é JSON válido; corrija o arquivo antes de instalar")
        return None
    owned: dict = {}
    perms = data.setdefault("permissions", {})
    for key in ("allow", "ask", "deny", "additionalDirectories"):
        merged, owned[key] = merge_owned(perms.get(key, []), owned_before.get(key, []), managed.get(key, []))
        if merged:
            perms[key] = merged
        else:
            perms.pop(key, None)
    if not perms:
        data.pop("permissions")
    env = data.setdefault("env", {})
    for k, v in owned_before.get("env", {}).items():
        if env.get(k) == v:
            env.pop(k)
    owned["env"] = {}
    for k, v in managed.get("env", {}).items():
        if k not in env:  # valor que o usuário já definiu vence
            env[k] = v
            owned["env"][k] = v
    if not env:
        data.pop("env")
    write_if_changed(USER_SETTINGS, json.dumps(data, indent=2, ensure_ascii=False) + "\n", dry, rep)
    return owned


def load_manifest() -> dict:
    try:
        return json.loads(INSTALL_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def installed_plugins() -> dict[str, str]:
    """{"plugin@marketplace": versão} do ~/.claude/plugins/installed_plugins.json."""
    try:
        data = json.loads((CLAUDE_HOME / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: (v[0].get("version") if isinstance(v, list) and v else "") for k, v in data.get("plugins", {}).items()}


def known_marketplaces() -> set[str]:
    try:
        return set(json.loads((CLAUDE_HOME / "plugins" / "known_marketplaces.json").read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return set()


def claude_cli(args: list[str], rep: Report, dry: bool) -> bool:
    shown = "claude " + " ".join(args)
    if dry:
        rep.info(f"(dry-run) {shown}")
        return True
    exe = shutil.which("claude")
    if not exe:
        rep.error(f"CLI `claude` não encontrado; não foi possível rodar `{shown}`")
        return False
    proc = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=300, cwd=Path.home())
    if proc.returncode != 0:
        rep.error(f"`{shown}` falhou: {(proc.stderr or proc.stdout).strip()[-300:]}")
        return False
    rep.ok(shown)
    return True


def user_mcp_servers() -> dict[str, str] | None:
    """Servidores MCP visíveis fora de qualquer projeto (escopo do usuário)."""
    out = run(["claude", "mcp", "list"], cwd=Path.home())
    if out is None:
        return None
    return {m.group(1): m.group(3) for line in out.splitlines()
            if (m := re.match(r"^(.+?): (.+) - (.+)$", line.strip()))}


def mcp_add_args(key: str, s: dict) -> list[str]:
    if s["type"] == "http":
        return ["mcp", "add", "--scope", "user", "--transport", "http", key, s["url"]]
    env = [x for k, v in s.get("env", {}).items() for x in ("-e", f"{k}={v}")]
    return ["mcp", "add", "--scope", "user", *env, key, "--", s["command"], *s.get("args", [])]


def install(cfg: dict, catalog: dict, dry: bool, force: bool, skip_cli: bool, with_mcp: bool = False) -> bool:
    heading("Instalação global no Claude" + (" (dry-run)" if dry else ""))
    rep = Report()
    plug = build_plugin(cfg, catalog, rep)
    if plug is None:
        print("\nCorrija os erros acima e rode novamente.")
        return False
    manifest = load_manifest()
    if not manifest and MARKETPLACE_DIR.is_dir():
        rep.warn(f"{rel(MARKETPLACE_DIR)} existe, mas o manifest sumiu: não há como saber o que foi alterado à mão "
                 "nem quais regras das settings eram do AiDW; confira o ~/.claude/settings.json")
    plugin, version, files = plug["plugin"], plug["version"], plug["files"]
    rep.ok(f"plugin {plugin} {version}: {sum(1 for k in files if '/agents/' in k)} agentes, "
           f"{len({k.split('/')[3] for k in files if '/skills/' in k})} skills")

    heading("Marketplace local (.aidw/marketplace)")
    old_hashes = manifest.get("files", {})
    conflicts = [k for k, h in old_hashes.items()
                 if (MARKETPLACE_DIR / k).is_file() and sha((MARKETPLACE_DIR / k).read_bytes()) != h]
    if conflicts and not force:
        for k in conflicts:
            rep.error(f"{k} foi alterado fora do AiDW; altere as fontes (o arquivo é gerado) ou rode com --force")
        return False
    for k, content in files.items():
        path = MARKETPLACE_DIR / k
        if path.is_file() and path.read_bytes() == content:
            continue
        if dry:
            rep.info(f"(dry-run) {'atualizar' if path.exists() else 'criar'} {k}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    for k in old_hashes:
        if k not in files and (MARKETPLACE_DIR / k).is_file():
            if dry:
                rep.info(f"(dry-run) remover {k}")
            else:
                (MARKETPLACE_DIR / k).unlink()
    if not dry:
        for d in sorted((x for x in MARKETPLACE_DIR.rglob("*") if x.is_dir()), key=lambda x: -len(x.parts)):
            if not any(d.iterdir()):
                d.rmdir()

    heading(f"Settings do usuário ({USER_SETTINGS})")
    owned = merge_user_settings(global_managed_settings(cfg, plug["ctx"], plug["build"]["servers"]),
                                manifest.get("settings", {}), dry, rep)
    if owned is None:
        return False
    rep.info("regras: " + ", ".join(f"{len(owned[k])} {k}" for k in ("allow", "ask", "deny")) +
             f"; pastas liberadas: {len(owned['additionalDirectories'])}")

    mcp_added = list(manifest.get("mcp_added", []))

    def save_manifest(cli_done: bool) -> None:
        if dry:
            return
        plugins = list(dict.fromkeys([*manifest.get("plugins", []), f"{plugin}@{MARKETPLACE_NAME}"]))
        if cli_done:  # os plugins de contextos anteriores já foram desinstalados
            plugins = [f"{plugin}@{MARKETPLACE_NAME}"]
        write_if_changed(INSTALL_MANIFEST, json.dumps({
            "generated_by": "aidw.py install", "plugin": plugin, "version": version, "plugins": plugins,
            "marketplace": MARKETPLACE_NAME, "context": plug["ctx"]["name"] if plug["ctx"] else None,
            "files": {k: sha(v) for k, v in files.items()}, "settings": owned,
            "mcp_added": sorted(set(mcp_added)), "cli": not skip_cli, "cli_done": cli_done,
        }, indent=2, ensure_ascii=False) + "\n", dry, Report(quiet=True))

    save_manifest(cli_done=skip_cli)
    if not skip_cli:
        heading("Claude Code (plugin e MCPs)")
        key = f"{plugin}@{MARKETPLACE_NAME}"
        installed = installed_plugins()
        for old in manifest.get("plugins", []):
            if old != key and old in installed:
                claude_cli(["plugin", "uninstall", old], rep, dry)
        if MARKETPLACE_NAME not in known_marketplaces():
            claude_cli(["plugin", "marketplace", "add", str(MARKETPLACE_DIR)], rep, dry)
        elif installed.get(key) != version:
            claude_cli(["plugin", "marketplace", "update", MARKETPLACE_NAME], rep, dry)
        if key not in installed:
            claude_cli(["plugin", "install", key], rep, dry)
        elif installed[key] != version:
            claude_cli(["plugin", "update", key], rep, dry)
        else:
            rep.ok(f"plugin {key} já está na versão {version}")
        present = user_mcp_servers()
        if present is None:
            rep.warn("não foi possível rodar `claude mcp list`; MCPs do usuário não conferidos")
        else:
            missing = [k for k in plug["build"]["servers"] if k not in present]
            # MCP no escopo do usuário sobe em TODA sessão do Claude, não só no AiDW: só com --mcp.
            if missing and not with_mcp:
                rep.info(f"MCPs do catálogo fora do escopo do usuário: {', '.join(missing)}. Fora do AiDW os agentes "
                         "ficam sem eles; `install --mcp` registra (sobem em toda sessão do Claude)")
            for k in missing if with_mcp else []:
                if claude_cli(mcp_add_args(k, plug["build"]["servers"][k]), rep, dry) and not dry:
                    mcp_added.append(k)
    if rep.errors:
        save_manifest(cli_done=False)
        print(f"\n{len(rep.errors)} erro(s) no Claude Code. Arquivos e settings já registrados no manifest; "
              "corrija e rode `install` de novo (ou `uninstall` para desfazer).")
        return False
    save_manifest(cli_done=True)
    print(f"\nConcluído{' (nada foi alterado: dry-run)' if dry else ''}. Em qualquer pasta, abra um chat novo e "
          f"chame /{plugin}:orquestrar <demanda>.")
    return True


def uninstall(dry: bool, skip_cli: bool) -> bool:
    heading("Desinstalação global do Claude" + (" (dry-run)" if dry else ""))
    rep = Report()
    manifest = load_manifest()
    if not manifest:
        if MARKETPLACE_DIR.is_dir() or INSTALL_MANIFEST.exists():
            where = rel(MARKETPLACE_DIR) if MARKETPLACE_DIR.is_dir() else rel(INSTALL_MANIFEST)
            rep.warn(f"manifest ausente ou ilegível ({rel(INSTALL_MANIFEST)}), e há restos da instalação em {where}: "
                     "sem ele não dá para saber o que é do AiDW. Remova à mão o plugin (`claude plugin uninstall`), "
                     f"o marketplace {MARKETPLACE_NAME} e as regras do AiDW no ~/.claude/settings.json")
            return False
        rep.info("nada instalado pelo AiDW (sem .aidw/install-manifest.json)")
        return True
    if not skip_cli and manifest.get("cli", True):
        installed = installed_plugins()
        for key in manifest.get("plugins", []):
            if key in installed:
                claude_cli(["plugin", "uninstall", key], rep, dry)
        if manifest.get("marketplace") in known_marketplaces():
            claude_cli(["plugin", "marketplace", "remove", manifest["marketplace"]], rep, dry)
        for k in manifest.get("mcp_added", []):
            claude_cli(["mcp", "remove", "--scope", "user", k], rep, dry)
        cache = CLAUDE_HOME / "plugins" / "cache" / MARKETPLACE_NAME
        if cache.is_dir():
            if dry:
                rep.info(f"(dry-run) remover {cache}")
            else:
                shutil.rmtree(cache)
                rep.ok(f"removido {cache}")
    merge_user_settings({}, manifest.get("settings", {}), dry, rep)
    if not dry:  # o `marketplace remove` deixa `extraKnownMarketplaces: {}` para trás
        try:
            data = json.loads(USER_SETTINGS.read_text(encoding="utf-8"))
            if data.get("extraKnownMarketplaces") == {}:
                data.pop("extraKnownMarketplaces")
                write_if_changed(USER_SETTINGS, json.dumps(data, indent=2, ensure_ascii=False) + "\n", dry, rep)
        except (OSError, json.JSONDecodeError):
            pass
    for k, h in manifest.get("files", {}).items():
        path = MARKETPLACE_DIR / k
        if not path.is_file():
            continue
        if sha(path.read_bytes()) != h:
            rep.warn(f"{k} foi alterado fora do AiDW; mantido")
        elif not dry:
            path.unlink()
    if not dry:
        if MARKETPLACE_DIR.is_dir():
            for d in sorted((x for x in MARKETPLACE_DIR.rglob("*") if x.is_dir()), key=lambda x: -len(x.parts)):
                if not any(d.iterdir()):
                    d.rmdir()
            if not any(MARKETPLACE_DIR.iterdir()):
                MARKETPLACE_DIR.rmdir()
        if not rep.errors:
            INSTALL_MANIFEST.unlink()
    print(f"\nConcluído{' (nada foi alterado: dry-run)' if dry else ''}"
          f"{f' com {len(rep.errors)} erro(s)' if rep.errors else ''}.")
    return not rep.errors


def check_global_install(cfg: dict, catalog: dict, rep: Report) -> None:
    heading("Instalação global (Claude)")
    manifest = load_manifest()
    if not manifest:
        rep.info("não instalada (opcional): `python aidw.py install` deixa o AiDW disponível em qualquer pasta")
        return
    plugins = manifest.get("plugins") or []
    if not plugins or not isinstance(manifest.get("settings"), dict):
        rep.error(f"{rel(INSTALL_MANIFEST)} malformado — rode `python aidw.py install` de novo")
        return
    key = plugins[-1]
    plug = build_plugin(cfg, catalog, Report(quiet=True))
    if plug is None:
        rep.error("a configuração tem erros — rode `python aidw.py install` para ver quais")
        return
    if plug["version"] != manifest.get("version"):
        rep.warn(f"as fontes mudaram desde a instalação ({manifest.get('version')} → {plug['version']}) — "
                 "rode `python aidw.py install`")
    elif manifest.get("cli", True) and not manifest.get("cli_done", True):
        rep.warn("a última instalação parou no Claude Code (plugin ou MCP) — rode `python aidw.py install`")
    elif manifest.get("cli", True):
        installed = installed_plugins().get(key)
        if installed is None:
            rep.warn(f"plugin {key} não aparece no Claude — rode `python aidw.py install`")
        elif installed != manifest["version"]:
            rep.warn(f"o Claude tem {key} {installed}, e o gerado é {manifest['version']} (o app desktop usa o "
                     "cache) — rode `python aidw.py install`")
        else:
            rep.ok(f"plugin {key} {installed}, em dia com as fontes")
    try:
        data = json.loads(USER_SETTINGS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    perms = data.get("permissions", {})
    missing = [f"{k}: {x}" for k in ("allow", "ask", "deny", "additionalDirectories")
               for x in manifest.get("settings", {}).get(k, []) if x not in perms.get(k, [])]
    if missing:
        rep.warn(f"{len(missing)} regra(s) do AiDW sumiram de {USER_SETTINGS} (ex.: {missing[0]}) — "
                 "rode `python aidw.py install`")
    else:
        rep.ok(f"regras globais do AiDW presentes em {USER_SETTINGS}")


# ---------------------------------------------------------------------------
# Projeto, demanda e worktree (aidw.py project detect / worktree ...)
# ---------------------------------------------------------------------------

def norm_path(p: Path | str) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


def path_inside(child: Path | str, parent: Path | str) -> bool:
    c, par = norm_path(child), norm_path(parent)
    return c == par or c.startswith(par.rstrip("\\/") + os.sep)


def git_proc(repo: Path | str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=600)


def git_out(repo: Path | str, *args: str) -> str | None:
    proc = git_proc(repo, *args)
    return proc.stdout.strip() if proc.returncode == 0 else None


def repo_info(path: Path | str) -> dict | None:
    """Raiz do working tree, repositório principal (mesmo de dentro de um worktree) e branch."""
    top = git_out(path, "rev-parse", "--show-toplevel")
    common = git_out(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not top or not common:
        return None
    common_path = Path(common)
    main = common_path.parent if common_path.name == ".git" else Path(top)
    return {"root": Path(top).as_posix(), "main": main.as_posix(), "name": main.name,
            "is_worktree": norm_path(top) != norm_path(main),
            "branch": git_out(path, "rev-parse", "--abbrev-ref", "HEAD") or ""}


def load_registry() -> dict:
    try:
        data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    data.setdefault("worktrees", [])
    return data


def save_registry(reg: dict) -> None:
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def system_for(ctx: dict | None, main: str) -> str | None:
    for key, sysdef in (ctx.get("systems", {}) if ctx else {}).items():
        if any(norm_path(r) == norm_path(main) for r in sysdef.get("repos", [])):
            return key
    return None


def write_json_atomic(path: Path, data) -> None:
    """Grava num temporário e troca de uma vez: quem lê nunca vê um arquivo pela metade."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def demand_path(ctx: dict | None, demand: str) -> Path:
    return state_dir(ctx) / demand / "demand.json"


def load_demand(ctx: dict | None, demand: str) -> tuple[dict | None, str, str]:
    """(dados, aviso, tipo do aviso: "" | "corrupt" | "context"). Arquivo ilegível vira .bak (nunca some em silêncio); demanda de outro contexto não é
    desta sessão (dois contextos sem state_dir próprio dividem a pasta state/)."""
    path = demand_path(ctx, demand)
    if not path.exists():
        return None, "", ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        backup = path.with_name(f"demand.json.{datetime.now().strftime('%Y%m%d%H%M%S')}.bak")
        os.replace(path, backup)
        return None, f"demand.json ilegível; guardado em {backup.as_posix()} e recriado (confira o histórico)", "corrupt"
    mine = ctx["name"] if ctx else None
    if data.get("context", mine) != mine:
        return None, f"a demanda {demand} é do contexto {data.get('context')!r}, não de {mine!r}", "context"
    return data, "", ""


def update_demand_file(ctx: dict | None, demand: str, repo_entry: dict) -> Path:
    """demand.json na pasta da demanda: um item por repositório (demanda pode tocar mais de um)."""
    data, _, _ = load_demand(ctx, demand)
    data = data or {"id": demand, "context": ctx["name"] if ctx else None, "status": "active", "repos": []}
    data["repos"] = [r for r in data.get("repos", []) if norm_path(r["repo"]) != norm_path(repo_entry["repo"])]
    data["repos"].append(repo_entry)
    data["updated"] = datetime.now().isoformat(timespec="seconds")
    path = demand_path(ctx, demand)
    write_json_atomic(path, data)
    return path


def default_base(main: Path) -> str:
    """Branch padrão do remoto (origin/HEAD); sem remoto, a branch atual do working copy."""
    head = git_out(main, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    return head or git_out(main, "rev-parse", "--abbrev-ref", "HEAD") or "HEAD"


def find_worktree(reg: dict, target: str, repo: str | None = None) -> list[dict]:
    """Entradas pelo caminho do worktree ou pelo id da demanda (opcionalmente só de um repositório)."""
    hits = [e for e in reg["worktrees"] if norm_path(e["path"]) == norm_path(target)]
    if not hits:
        hits = [e for e in reg["worktrees"] if e["demand"] == target]
    if repo:
        main = (repo_info(repo) or {}).get("main", repo)
        hits = [e for e in hits if norm_path(e["repo"]) == norm_path(main)]
    return hits


def worktree_create(cfg: dict, repo: str, demand: str, slug: str = "", base: str = "") -> dict:
    """Cria (ou devolve, se já existe) o worktree da demanda. {ok, path, branch, base, ...} ou {ok: False, error}."""
    ctx = load_context(cfg, Report(quiet=True))
    demand = demand.strip().lower()
    if not DEMAND_RE.match(demand):
        return {"ok": False, "error": f"id de demanda inválido {demand!r} (use letras minúsculas, números e -)"}
    info = repo_info(repo)
    if info is None:
        return {"ok": False, "error": f"{repo} não é um repositório Git"}
    main = Path(info["main"])
    reg = load_registry()
    for e in reg["worktrees"]:
        if e["demand"] == demand and norm_path(e["repo"]) == norm_path(main) and Path(e["path"]).is_dir():
            return {"ok": True, "created": False, **e}
    path = worktree_root(cfg) / main.name / demand
    if path.exists():
        return {"ok": False, "error": f"{path.as_posix()} já existe e não está no registro do AiDW; confira e remova à mão"}
    wt_cfg = ctx.get("worktree", {}) if ctx else {}
    number = re.sub(r"^[a-z]+-", "", demand)
    branch = f"{wt_cfg.get('branch_prefix', 'aidw/')}{number}" + (f"-{slugify(slug)[:40].strip('-')}" if slug else "")
    if git_proc(main, "check-ref-format", "--branch", branch).returncode != 0:
        return {"ok": False, "error": f"nome de branch inválido: {branch}"}
    warnings = []
    if git_out(main, "remote"):
        if git_proc(main, "fetch", "-q", "origin").returncode != 0:
            warnings.append("git fetch origin falhou; a base pode estar desatualizada")
    base = base or default_base(main)
    if git_proc(main, "rev-parse", "--verify", "-q", f"{base}^{{commit}}").returncode != 0:
        return {"ok": False, "error": f"base {base!r} não existe em {main.as_posix()}"}
    main_dirty = bool(git_out(main, "status", "--porcelain"))
    if main_dirty:
        warnings.append("o working copy principal tem alterações locais; elas NÃO entram no worktree")
    path.parent.mkdir(parents=True, exist_ok=True)
    if git_proc(main, "rev-parse", "--verify", "-q", f"refs/heads/{branch}").returncode == 0:
        proc = git_proc(main, "worktree", "add", str(path), branch)  # branch já existe: reaproveita
    else:
        proc = git_proc(main, "worktree", "add", "-b", branch, str(path), base)
    if proc.returncode != 0:
        return {"ok": False, "error": f"git worktree add falhou: {(proc.stderr or proc.stdout).strip()[-400:]}"}
    links = []
    try:
        for name in wt_cfg.get("link", DEFAULT_WORKTREE_LINKS):
            src, dst = main / name, path / name
            if src.is_dir() and not dst.exists():
                make_link(dst, src)
                links.append(name)
    except (OSError, subprocess.CalledProcessError) as exc:
        for name in links:
            if is_link(path / name):
                remove_link(path / name)
        undone = git_proc(main, "worktree", "remove", "--force", str(path)).returncode == 0
        return {"ok": False, "error": f"falha ao criar a junction de dependências ({exc}); " + (
            f"o worktree recém-criado foi desfeito (a branch {branch} ficou, sem commits novos)" if undone else
            f"e não foi possível desfazer o worktree {path.as_posix()}: remova à mão (git worktree remove)")}
    entry = {"demand": demand, "repo": main.as_posix(), "path": path.as_posix(), "branch": branch, "base": base,
             "links": links, "status": "active", "context": ctx["name"] if ctx else None,
             "system": system_for(ctx, main.as_posix()),
             "created_at": datetime.now().isoformat(timespec="seconds")}
    reg["worktrees"].append(entry)
    save_registry(reg)
    demand_file = update_demand_file(ctx, demand, {k: entry[k] for k in ("repo", "path", "branch", "base", "system")})
    return {"ok": True, "created": True, "main_dirty": main_dirty, "warnings": warnings,
            "demand_file": demand_file.as_posix(), **entry}


def worktree_state(e: dict) -> dict:
    """Situação atual: existe, alterações não commitadas, commits à frente/atrás da base, publicado."""
    path = Path(e["path"])
    if not path.is_dir():
        return {"exists": False}
    status = git_proc(path, "status", "--porcelain")
    counts = git_proc(path, "rev-list", "--left-right", "--count", f"{e['base']}...HEAD")
    parts = counts.stdout.split()
    if status.returncode != 0 or counts.returncode != 0 or len(parts) != 2:
        failed = status if status.returncode != 0 else counts
        return {"exists": True, "error": f"não foi possível conferir o worktree (git: "
                                         f"{(failed.stderr or failed.stdout).strip()[-200:] or 'saída inesperada'})"}
    published = bool(git_out(e["repo"], "branch", "-r", "--contains", e["branch"]))  # falha = não publicado
    return {"exists": True, "dirty": bool(status.stdout.strip()), "ahead": int(parts[1]), "behind": int(parts[0]),
            "published": published}


def worktree_remove(target: str, repo: str | None = None) -> dict:
    """Remove só worktree limpo e integrado (sem alteração local; commits publicados ou nenhum à frente)."""
    reg = load_registry()
    hits = find_worktree(reg, target, repo)
    if len(hits) != 1:
        return {"ok": False, "error": ("nenhum worktree do AiDW com esse caminho ou demanda" if not hits else
                                       "mais de um worktree para essa demanda; informe --repo")}
    e = hits[0]
    st = worktree_state(e)
    if st.get("exists"):
        if st.get("error"):
            return {"ok": False, "error": f"{st['error']}; nada foi removido (confira à mão com git status/log)"}
        if st["dirty"]:
            return {"ok": False, "error": f"{e['path']} tem alterações não commitadas; commite ou descarte antes"}
        if st["ahead"] and not st["published"]:
            return {"ok": False, "error": f"a branch {e['branch']} tem {st['ahead']} commit(s) não publicados; "
                                          "faça o push (ou descarte a branch) antes de remover"}
        for name in e.get("links", []):  # junction primeiro: nunca apagar recursivamente através dela
            link = Path(e["path"]) / name
            if is_link(link):
                remove_link(link)
        proc = git_proc(e["repo"], "worktree", "remove", e["path"])
        if proc.returncode != 0:
            return {"ok": False, "error": f"git worktree remove falhou: {(proc.stderr or proc.stdout).strip()[-400:]}"}
    else:
        git_proc(e["repo"], "worktree", "prune")
    reg["worktrees"] = [x for x in reg["worktrees"] if x is not e]
    save_registry(reg)
    return {"ok": True, "path": e["path"], "branch": e["branch"],
            "note": f"a branch {e['branch']} foi mantida (apagar branch é ação travada)"}


def worktree_cleanup() -> dict:
    """Tira do registro os worktrees cuja pasta sumiu e roda `git worktree prune` nos repositórios deles."""
    reg = load_registry()
    gone = [e for e in reg["worktrees"] if not Path(e["path"]).is_dir()]
    for repo in {e["repo"] for e in gone}:
        git_proc(repo, "worktree", "prune")
    reg["worktrees"] = [e for e in reg["worktrees"] if Path(e["path"]).is_dir()]
    save_registry(reg)
    return {"ok": True, "removed_from_registry": [e["path"] for e in gone]}


def project_detect(cfg: dict, path: str) -> dict:
    ctx = load_context(cfg, Report(quiet=True))
    info = repo_info(path)
    result = {"path": Path(path).resolve().as_posix(), "context": ctx["name"] if ctx else None, "git": bool(info)}
    if not info:
        return result
    reg = load_registry()
    active = [e for e in reg["worktrees"] if norm_path(e["repo"]) == norm_path(info["main"]) and e["status"] == "active"]
    here = [e for e in active if path_inside(path, e["path"])]
    result.update(info, system=system_for(ctx, info["main"]),
                  demand=here[0]["demand"] if here else None,
                  active_demands=[{"demand": e["demand"], "path": e["path"], "branch": e["branch"]} for e in active])
    return result


def worktree_hook_create() -> int:
    """Hook WorktreeCreate (EnterWorktree / claude --worktree): imprime o caminho do worktree da demanda."""
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))  # UTF-8, não a página do console
    except (json.JSONDecodeError, UnicodeDecodeError):
        print("AiDW: entrada inválida no hook WorktreeCreate", file=sys.stderr)
        return 1
    name = slugify(str(data.get("name") or "")) or "sessao"
    cwd = str(data.get("cwd") or os.getcwd())
    reg = load_registry()
    same = [e for e in reg["worktrees"] if e["demand"] == name and e["status"] == "active" and Path(e["path"]).is_dir()]
    info = repo_info(cwd)
    if info:
        same = [e for e in same if norm_path(e["repo"]) == norm_path(info["main"])]
    if len(same) == 1:  # criado antes pelo orquestrador (`worktree create`): a sessão só entra nele
        print(Path(same[0]["path"]))
        return 0
    cfg = load_config()
    if cfg is None:
        print("AiDW: aidw.config.toml não encontrado", file=sys.stderr)
        return 1
    result = worktree_create(cfg, cwd, name)
    if not result["ok"]:
        print(f"AiDW: {result['error']}", file=sys.stderr)
        return 1
    print(Path(result["path"]))
    return 0


def worktree_command(cfg: dict, args: argparse.Namespace) -> int:
    action = args.wt_action
    if action == "hook-create":
        return worktree_hook_create()
    if action == "hook-remove":  # o worktree fica; a remoção passa pelas checagens do `worktree remove`
        print("AiDW: worktree mantido; remova com `python aidw.py worktree remove <demanda>`", file=sys.stderr)
        return 0
    if action == "create":
        result = worktree_create(cfg, args.repo, args.demand, args.slug or "", args.base or "")
    elif action == "remove":
        result = worktree_remove(args.target, args.repo)
    elif action == "cleanup":
        result = worktree_cleanup()
    elif action == "inspect":
        hits = find_worktree(load_registry(), args.target, args.repo)
        result = ({"ok": True, **hits[0], **worktree_state(hits[0])} if len(hits) == 1 else
                  {"ok": False, "error": "nenhum ou mais de um worktree com esse caminho/demanda (use --repo)"})
    else:  # list
        result = {"ok": True, "worktrees": [{**e, **worktree_state(e)} for e in load_registry()["worktrees"]]}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    if not result["ok"]:
        print(f"[erro]  {result['error']}")
        return 1
    if action == "create":
        print(f"[ok]    worktree {'criado' if result['created'] else 'já existente'}: {result['path']}")
        print(f"        branch {result['branch']} (base {result['base']}); junctions: {', '.join(result['links']) or 'nenhuma'}")
        for w in result.get("warnings", []):
            print(f"[aviso] {w}")
    elif action == "remove":
        print(f"[ok]    removido {result['path']}; {result['note']}")
    elif action == "cleanup":
        print(f"[ok]    {len(result['removed_from_registry'])} worktree(s) órfão(s) tirado(s) do registro")
    elif action == "inspect":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if not result["worktrees"]:
            print("Nenhum worktree de demanda registrado.")
        for e in result["worktrees"]:
            if not e["exists"]:
                state = "órfão (pasta sumiu — rode `worktree cleanup`)"
            else:
                state = ("com alterações" if e["dirty"] else "limpo") + f", {e['ahead']} à frente da base" + \
                        (" (publicado)" if e["published"] else "")
            print(f"  {e['demand']:<14} {e['path']:<50} {e['branch']:<40} {state}")
    return 0


# ---------------------------------------------------------------------------
# Demanda: estado para retomar (aidw.py demand set / show / list)
# ---------------------------------------------------------------------------

DEMAND_STATUS = ("active", "paused", "done")


def demand_set(cfg: dict, demand: str, step: str = "", status: str = "", title: str = "", note: str = "") -> dict:
    ctx = load_context(cfg, Report(quiet=True))
    demand = demand.strip().lower()
    if not DEMAND_RE.match(demand):
        return {"ok": False, "error": f"id de demanda inválido {demand!r} (use letras minúsculas, números e -)"}
    if step and step not in ACTIONS and step != "UNDERSTAND":
        return {"ok": False, "error": f"etapa desconhecida {step!r} (use UNDERSTAND ou uma ação de NEXT ACTION)"}
    if status and status not in DEMAND_STATUS:
        return {"ok": False, "error": f"status inválido {status!r} (use {', '.join(DEMAND_STATUS)})"}
    data, warning, kind = load_demand(ctx, demand)
    if kind == "context":
        return {"ok": False, "error": warning}
    data = data or {"id": demand, "context": ctx["name"] if ctx else None, "status": "active", "repos": []}
    now = datetime.now().isoformat(timespec="seconds")
    if step and step != data.get("step"):
        data.setdefault("history", []).append({"step": step, "at": now})
        data["step"] = step
    for key, value in (("status", status), ("title", title), ("note", note)):
        if value:
            data[key] = value
    data["updated"] = now
    path = demand_path(ctx, demand)
    write_json_atomic(path, data)
    return {"ok": True, "folder": path.parent.as_posix(), **({"warning": warning} if warning else {}), **data}


def demand_list(cfg: dict, active_only: bool = False) -> list[dict]:
    ctx = load_context(cfg, Report(quiet=True))
    base = state_dir(ctx)
    out = []
    for f in sorted(base.glob("*/demand.json")) if base.is_dir() else []:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if d.get("context", ctx["name"] if ctx else None) != (ctx["name"] if ctx else None):
            continue  # outro contexto dividindo a pasta state/
        if active_only and d.get("status") == "done":
            continue
        out.append({"id": d.get("id", f.parent.name), "status": d.get("status"), "step": d.get("step"),
                    "title": d.get("title", ""), "note": d.get("note", ""), "updated": d.get("updated"),
                    "folder": f.parent.as_posix(), "repos": [r.get("repo") for r in d.get("repos", [])]})
    return sorted(out, key=lambda d: d.get("updated") or "", reverse=True)


def demand_command(cfg: dict, args: argparse.Namespace) -> int:
    if args.dm_action == "set":
        result = demand_set(cfg, args.id, args.step or "", args.status or "", args.title or "", args.note or "")
    elif args.dm_action == "show":
        ctx = load_context(cfg, Report(quiet=True))
        data, warning, _ = load_demand(ctx, args.id)
        result = {"ok": True, "folder": demand_path(ctx, args.id).parent.as_posix(), **data} if data else \
            {"ok": False, "error": warning or f"demanda {args.id!r} sem demand.json em {state_dir(ctx).as_posix()}"}
    else:
        result = {"ok": True, "demands": demand_list(cfg, args.active)}
    if args.json or args.dm_action != "list":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif not result["demands"]:
        print("Nenhuma demanda" + (" ativa." if args.active else "."))
    else:
        for d in result["demands"]:
            print(f"  {d['id']:<18} {d['status'] or '—':<7} {d['step'] or '—':<15} {d['updated'] or '':<20} {d['title']}")
    return 0 if result["ok"] else 1


# ---------------------------------------------------------------------------
# Instalação global no Codex (aidw.py install --provider codex)
# ---------------------------------------------------------------------------

CODEX_NO_IMPLICIT = "policy:\n  allow_implicit_invocation: false\n"  # agents/openai.yaml: só quando chamada


def codex_skill_copy(text: str, name: str) -> str:
    """SKILL.md para o Codex: nome `aidw-<nome>`, aviso do AiDW e {{root}} resolvido."""
    text = guard_skill(text)
    return re.sub(r"(?m)^name:\s*.*$", f"name: {CODEX_NS}{name}", text, count=1)


def codex_node_path() -> tuple[str | None, str]:
    """(pasta do Node para pôr na frente do PATH do Codex, aviso). O sandbox do Codex não lê o perfil do usuário:
    um `node` que resolve para lá (ex.: nvm em %LOCALAPPDATA%) nem inicia. Usa um Node fora do perfil, se houver."""
    home = norm_path(Path.home())
    found = [Path(d) / "node.exe" if IS_WINDOWS else Path(d) / "node" for d in os.environ.get("PATH", "").split(os.pathsep) if d]
    nodes = [n for n in dict.fromkeys(found) if n.is_file()]
    if not nodes or not path_inside(os.path.realpath(nodes[0]), home):
        return None, ""
    outside = next((n for n in nodes if not path_inside(os.path.realpath(n), home)), None)
    if outside is None:
        return None, ("o `node` do PATH fica dentro do perfil do usuário e o sandbox do Codex não o executa; instale um Node "
                      "fora do perfil (ex.: em Program Files) para os builds no Codex")
    version = run([str(outside), "--version"]) or "?"
    return str(outside.parent), (f"o `node` do PATH fica dentro do perfil do usuário (o sandbox do Codex não o executa); o perfil "
                                 f"`{CODEX_PROFILE_NAME}` usa {outside.parent} ({version}) na frente do PATH")


def codex_profile(cfg: dict, ctx: dict | None, resolved: dict, servers: dict) -> str:
    """~/.codex/aidw.config.toml (perfil `aidw`): arquivo só do AiDW. A confiança dos hooks o Codex grava no
    config.toml do usuário (nunca no perfil), que o AiDW não toca."""
    orch = resolved[ORCHESTRATOR]
    writable = list(dict.fromkeys([ROOT.as_posix(), *code_dirs(cfg, ctx)]))
    env = {**({k: str(v) for k, v in ctx.get("env", {}).items()} if ctx else {}), **codex_git_env(cfg, ctx)}
    node_dir, _ = codex_node_path()
    if node_dir:
        env["PATH"] = node_dir + os.pathsep + os.environ.get("PATH", "")
    lines = [
        f"# {GENERATED_MARK} install — perfil `{CODEX_PROFILE_NAME}` do Codex (`codex --profile {CODEX_PROFILE_NAME}` ou "
        "`python aidw.py open --provider codex`). Não edite: altere as fontes e rode o install.",
        f"model = {toml_value(orch['model']['model_id'])}",
        *([f"model_reasoning_effort = {toml_value(orch['effort'])}"] if orch["effort"] else []),
        'approval_policy = "on-request"', 'sandbox_mode = "workspace-write"', "",
        "[sandbox_workspace_write]", "network_access = true",
        f"writable_roots = {toml_value([win(d) for d in writable])}", "",
        "[shell_environment_policy.set]", *[f"{k} = {toml_value(v)}" for k, v in env.items()], "",
        "[features]", "multi_agent_v2 = true", "",
        "[agents]", "max_concurrent_threads_per_session = 4",
    ]
    for key, srv in servers.items():
        lines += ["", f"[mcp_servers.{key}]", *[f"{k} = {toml_value(v)}" for k, v in codex_mcp_table(srv).items()]]
    return "\n".join(lines) + "\n"


def codex_hook_groups() -> dict[str, list]:
    cmd = f'python "{GUARD_SCRIPT.as_posix()}"'
    group = lambda matcher=None: {**({"matcher": matcher} if matcher else {}),  # noqa: E731
                                  "hooks": [{"type": "command", "command": cmd}]}
    return {"PreToolUse": [group("apply_patch")], "UserPromptSubmit": [group()],
            "SessionStart": [group("compact|resume")]}


def is_aidw_hook_group(g: dict) -> bool:
    return any(GUARD_SCRIPT.name in str(h.get("command", "")) for h in g.get("hooks", []))


def merge_codex_hooks(data: dict, add: bool) -> dict:
    """Tira os grupos do AiDW do hooks.json e, com add, põe os atuais no fim (os do usuário ficam)."""
    hooks = data.setdefault("hooks", {})
    for event in list(hooks):
        hooks[event] = [g for g in hooks[event] if not is_aidw_hook_group(g)]
        if not hooks[event]:
            hooks.pop(event)
    if add:
        for event, groups in codex_hook_groups().items():
            hooks.setdefault(event, []).extend(groups)
    if not hooks:
        data.pop("hooks")
    return data


def build_codex_install(cfg: dict, catalog: dict, rep: Report) -> dict | None:
    """{arquivo: bytes} dos arquivos que são só do AiDW + o perfil (texto) — tudo com nomes `aidw-*`."""
    ccfg = json.loads(json.dumps(cfg))
    ccfg["provider"]["name"], ccfg["delegation"]["mode"] = "codex", "native"
    ref_dir = CODEX_SKILLS_HOME / f"{CODEX_NS}orquestrar" / "reference"
    sub = Report(quiet=True)  # avisos de modelo de outro provedor são esperados aqui (vale o tier do Codex)
    b = build(ccfg, catalog, sub, ns=CODEX_NS, ref_dir=ref_dir)
    for e in sub.errors:
        rep.error(e)
    if b is None:
        return None
    resolved, ctx = b["resolved"], b["ctx"]
    files: dict[Path, bytes] = {}
    for role, g in b["agents"].items():
        a = {**resolved[role], "name": CODEX_NS + resolved[role]["name"]}
        meta = {**g["meta"], "description": f"{PLUGIN_GUARD} {g['meta']['description']}"}
        files[CODEX_AGENTS_HOME / f"{a['name']}.toml"] = render_codex_role(a, meta, g["prompt"]).encode("utf-8")
    used = set(resolved[ORCHESTRATOR]["skills"]) | {n for a in resolved.values() if a["enabled"] for n in a["skills"]}
    used |= {n for n, d in b["skills"].items() if is_admin_skill(d / "SKILL.md")}
    for name in sorted(used & set(b["skills"])):
        src = b["skills"][name]
        for f in sorted(src.rglob("*")):
            if f.is_file():
                data = f.read_bytes()
                if f.name == "SKILL.md":
                    data = codex_skill_copy(data.decode("utf-8"), name).encode("utf-8")
                files[CODEX_SKILLS_HOME / f"{CODEX_NS}{name}" / f.relative_to(src)] = data
    orq = CODEX_SKILLS_HOME / f"{CODEX_NS}orquestrar"
    files[orq / "SKILL.md"] = orchestrator_skill(plugin_name(), ctx, b["orchestrator_md"], orq / "SKILL.md",
                                                 provider="codex").encode("utf-8")
    files[orq / "agents" / "openai.yaml"] = CODEX_NO_IMPLICIT.encode("utf-8")
    for name, r in b["orchestrator_refs"].items():
        files[ref_dir / f"{name}.md"] = r["content"].encode("utf-8")
    sair = CODEX_SKILLS_HOME / f"{CODEX_NS}sair"
    files[sair / "SKILL.md"] = exit_skill(plugin_name(), provider="codex").encode("utf-8")
    files[sair / "agents" / "openai.yaml"] = CODEX_NO_IMPLICIT.encode("utf-8")
    perms = ctx.get("permissions", {}) if ctx else {}
    git_ask = [["git", *sub.split()] for sub in perms.get("git_ask", [])]
    rules = codex_rules([*cfg["policies"]["deny"], *perms.get("deny", [])],
                        [*cfg["policies"]["ask"], *perms.get("ask", []), *[f"Bash({' '.join(x)} *)" for x in git_ask]])
    files[CODEX_GLOBAL_RULES] = rules.replace("apply a partir de", "install a partir de").encode("utf-8")
    return {"files": files, "ctx": ctx, "resolved": resolved, "servers": b["servers"]}


def codex_hook_signature() -> str:
    return sha(json.dumps(codex_hook_groups(), sort_keys=True).encode("utf-8"))


def codex_trust_state() -> dict:
    """`[hooks.state]` do config.toml do Codex: onde o TUI grava a confiança (`trusted_hash`) de cada hook."""
    try:
        return load_toml(CODEX_HOME / "config.toml").get("hooks", {}).get("state", {})
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def aidw_hook_keys() -> list[str]:
    """As chaves de confiança dos grupos do AiDW no hooks.json (`<arquivo>:<evento_snake>:<grupo>:<handler>`)."""
    try:
        data = json.loads(CODEX_HOOKS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    snake = lambda ev: re.sub(r"(?<!^)(?=[A-Z])", "_", ev).lower()  # noqa: E731 — PreToolUse → pre_tool_use
    return [f"{CODEX_HOOKS_FILE}:{snake(ev)}:{i}:0" for ev, groups in data.get("hooks", {}).items()
            for i, g in enumerate(groups) if is_aidw_hook_group(g)]


def install_codex(cfg: dict, catalog: dict, dry: bool, force: bool) -> bool:
    heading("Instalação global no Codex" + (" (dry-run)" if dry else ""))
    rep = Report()
    built = build_codex_install(cfg, catalog, rep)
    if built is None:
        print("\nCorrija os erros acima e rode novamente.")
        return False
    manifest = load_manifest()
    old = manifest.get("codex", {})
    files = built["files"]
    conflicts = [k for k, h in old.get("files", {}).items() if Path(k).is_file() and sha(Path(k).read_bytes()) != h]
    if conflicts and not force:
        for k in conflicts:
            rep.error(f"{k} foi alterado fora do AiDW; altere as fontes (o arquivo é gerado) ou rode com --force")
        return False
    changed = 0
    for path, content in files.items():
        if path.is_file() and path.read_bytes() == content:
            continue
        changed += 1
        if not dry:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    for k in old.get("files", {}):
        if Path(k) not in files and Path(k).is_file():
            changed += 1
            if not dry:
                Path(k).unlink()
    agents = sum(1 for k in files if k.parent == CODEX_AGENTS_HOME)
    skills = len({k.relative_to(CODEX_SKILLS_HOME).parts[0] for k in files if CODEX_SKILLS_HOME in k.parents})
    rep.ok(f"{agents} agentes em {CODEX_AGENTS_HOME}, {skills} skills em {CODEX_SKILLS_HOME}, rules em "
           f"{CODEX_GLOBAL_RULES.name} ({changed} arquivo(s) {'a mudar' if dry else 'mudaram'})")
    profile = codex_profile(cfg, built["ctx"], built["resolved"], built["servers"])
    write_if_changed(CODEX_PROFILE, profile, dry, rep)
    try:
        hooks = json.loads(CODEX_HOOKS_FILE.read_text(encoding="utf-8")) if CODEX_HOOKS_FILE.exists() else {}
    except json.JSONDecodeError:
        rep.error(f"{CODEX_HOOKS_FILE} não é JSON válido; corrija antes de instalar")
        return False
    write_if_changed(CODEX_HOOKS_FILE, json.dumps(merge_codex_hooks(hooks, add=True), indent=2,
                                                  ensure_ascii=False) + "\n", dry, rep)
    signature = codex_hook_signature()
    stale = dict(old.get("stale_trust", {}))
    if old.get("hooks_signature") and old["hooks_signature"] != signature:
        # o comando/matcher dos hooks mudou: o Codex marca como "Modified" e não roda até nova aprovação
        ours = {norm_path(k) for k in aidw_hook_keys()}
        stale.update({norm_path(k): v.get("trusted_hash") for k, v in codex_trust_state().items() if norm_path(k) in ours})
    if not dry:
        manifest["codex"] = {"files": {str(k): sha(v) for k, v in files.items()},
                             "profile": str(CODEX_PROFILE), "hooks": str(CODEX_HOOKS_FILE),
                             "hooks_signature": signature, "stale_trust": stale}
        write_if_changed(INSTALL_MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", dry, Report(quiet=True))
    node_dir, node_note = codex_node_path()
    if node_note:
        (rep.info if node_dir else rep.warn)(node_note)
    trusted = codex_hooks_trusted()
    if trusted is False:
        rep.warn("os hooks do AiDW no Codex só rodam depois de aprovados uma vez: abra `codex --profile "
                 f"{CODEX_PROFILE_NAME}` num terminal e escolha \"Trust all and continue\"")
    print(f"\nConcluído{' (nada foi alterado: dry-run)' if dry else ''}. No Codex: `python aidw.py open --provider codex` "
          "(ou `codex --profile aidw`) e chame $aidw-orquestrar <demanda>.")
    return not rep.errors


def uninstall_codex(dry: bool) -> bool:
    heading("Desinstalação global do Codex" + (" (dry-run)" if dry else ""))
    rep = Report()
    manifest = load_manifest()
    old = manifest.get("codex")
    if not old:
        rep.info("nada instalado pelo AiDW no Codex")
        return True
    for k, h in old.get("files", {}).items():
        path = Path(k)
        if not path.is_file():
            continue
        if sha(path.read_bytes()) != h:
            rep.warn(f"{k} foi alterado fora do AiDW; mantido")
        elif not dry:
            path.unlink()
    if not dry:
        for d in sorted({Path(k).parent for k in old.get("files", {})}, key=lambda x: -len(x.parts)):
            while d not in (CODEX_SKILLS_HOME, CODEX_AGENTS_HOME, CODEX_HOME, CODEX_GLOBAL_RULES.parent) and d.is_dir() \
                    and not any(d.iterdir()):
                d.rmdir()
                d = d.parent
        if CODEX_PROFILE.exists():
            CODEX_PROFILE.unlink()
        if CODEX_HOOKS_FILE.exists():
            try:
                data = merge_codex_hooks(json.loads(CODEX_HOOKS_FILE.read_text(encoding="utf-8")), add=False)
                if data:
                    write_if_changed(CODEX_HOOKS_FILE, json.dumps(data, indent=2, ensure_ascii=False) + "\n", dry, rep)
                else:
                    CODEX_HOOKS_FILE.unlink()
            except json.JSONDecodeError:
                rep.warn(f"{CODEX_HOOKS_FILE} não é JSON válido; tire os hooks do AiDW à mão")
        manifest.pop("codex")
        if manifest.get("plugins") or manifest.get("files"):
            write_if_changed(INSTALL_MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", dry, rep)
        elif INSTALL_MANIFEST.exists():
            INSTALL_MANIFEST.unlink()
    print(f"\nConcluído{' (nada foi alterado: dry-run)' if dry else ''}.")
    return not rep.errors


def codex_hooks_trusted() -> bool | None:
    """True quando cada hook do AiDW tem confiança gravada que não ficou vencida (o Codex só roda o hook se o
    `trusted_hash` bate com o hook atual; depois de uma mudança, o hash antigo não vale mais). None = sem hooks."""
    keys = aidw_hook_keys()
    if not keys:
        return None
    state = codex_trust_state()
    stale = {norm_path(k): v for k, v in load_manifest().get("codex", {}).get("stale_trust", {}).items()}
    for key in keys:
        entry = next((v for k, v in state.items() if norm_path(k) == norm_path(key)), None)
        if not entry or not entry.get("trusted_hash") or stale.get(norm_path(key)) == entry.get("trusted_hash"):
            return False
    return True


def check_codex_install(rep: Report) -> None:
    heading("Instalação global (Codex)")
    old = load_manifest().get("codex")
    if not old:
        rep.info("não instalada (opcional): `python aidw.py install --provider codex`")
        return
    missing = [k for k in old.get("files", {}) if not Path(k).is_file()]
    if missing:
        rep.warn(f"{len(missing)} arquivo(s) do AiDW sumiram do Codex (ex.: {missing[0]}) — rode o install")
    else:
        rep.ok(f"{len(old.get('files', {}))} arquivos do AiDW no Codex; perfil {CODEX_PROFILE.name}")
    node_dir, node_note = codex_node_path()
    if node_note and not node_dir:
        rep.warn(node_note)
    trusted = codex_hooks_trusted()
    if trusted:
        rep.ok("hooks do AiDW aprovados no Codex")
    elif trusted is False:
        rep.warn(f"hooks do AiDW ainda não aprovados no Codex: abra `codex --profile {CODEX_PROFILE_NAME}` e escolha "
                 "\"Trust all and continue\"")


def open_command(cfg: dict, provider: str, demand: str, path: str, print_only: bool) -> int:
    """Abre o Claude ou o Codex já na pasta da demanda (o worktree dela) — o Codex com o perfil `aidw`."""
    target = Path(path).resolve() if path else Path.cwd()
    folder = None
    if demand:
        hits = [e for e in load_registry()["worktrees"] if e["demand"] == demand and e["status"] == "active"]
        if len(hits) != 1:
            print(f"[erro]  {'nenhum' if not hits else 'mais de um'} worktree ativo para a demanda {demand!r} "
                  "(`aidw.py worktree list`)")
            return 1
        target = Path(hits[0]["path"])
        folder = state_dir(load_context(cfg, Report(quiet=True))) / demand
    exe = shutil.which(provider)
    if not exe:
        print(f"[erro]  CLI `{provider}` não encontrado")
        return 1
    if provider == "codex":
        cmd = [exe, "--profile", CODEX_PROFILE_NAME, "-C", str(target)]
        if folder:
            cmd += ["--add-dir", str(folder)]
    else:
        cmd = [exe]
    print(f"Abrindo {provider} em {target}: {' '.join(Path(cmd[0]).stem if i == 0 else c for i, c in enumerate(cmd))}")
    if print_only:
        return 0
    return subprocess.run(cmd, cwd=target).returncode


# ---------------------------------------------------------------------------
# Contextos: aidw.py context list / check / use / create (skills contexto-*)
# ---------------------------------------------------------------------------

def remote_host(url: str | None) -> str | None:
    """Só o host do remoto: a URL pode ter usuário/token embutido e nunca é mostrada."""
    if not url:
        return None
    if "://" not in url and "@" not in url and re.match(r"^([A-Za-z]:[\/]|/|\.)", url.strip()):
        return "local"
    m = re.match(r"^(?:[a-z+]+://)?(?:[^@/]+@)?([^/:]+)", url.strip())
    return m.group(1) if m else "?"


def context_status(cfg: dict, name: str) -> dict:
    d = CONTEXTS_DIR / name
    info = {"name": name, "active": cfg["context"]["active"] == name, "path": d.as_posix()}
    try:
        raw = load_toml(d / "context.toml")
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {**info, "ok": False, "error": f"context.toml inválido: {exc}"}
    info.update(description=raw.get("description", name), systems=sorted(raw.get("systems", {})),
                state_dir=expand_vars(raw.get("state_dir", "state"), path_vars(d)))
    info["git"] = (d / ".git").exists()
    info["remote"] = remote_host(git_out(d, "remote", "get-url", "origin")) if info["git"] else None
    ignored = run(["git", "check-ignore", "-q", rel(d)]) is not None
    info["ignored_by_aidw"] = ignored or run(["git", "rev-parse", "--is-inside-work-tree"]) is None
    manifest = load_manifest()
    info["plugin_installed"] = bool(manifest) and manifest.get("context") == name
    info["ok"] = True
    return info


def context_list(cfg: dict) -> list[dict]:
    return [context_status(cfg, n) for n in list_contexts()]


def context_check(cfg: dict, catalog: dict, name: str) -> dict:
    """Valida um contexto como se estivesse ativo: build completo, repositório próprio, pasta de estado exclusiva."""
    if name not in list_contexts():
        return {"ok": False, "errors": [f"contexto {name!r} não existe em {rel(CONTEXTS_DIR)}/"], "warnings": []}
    test_cfg = json.loads(json.dumps(cfg))
    test_cfg["context"]["active"] = name
    rep = Report(quiet=True)
    build(test_cfg, catalog, rep)
    errors, warnings = list(rep.errors), list(rep.warnings)
    st = context_status(cfg, name)
    if not st.get("git"):
        warnings.append(f"{rel(CONTEXTS_DIR / name)} não é um repositório Git próprio (rode `git init` nele)")
    if not st.get("ignored_by_aidw"):
        errors.append(f"{rel(CONTEXTS_DIR / name)} NÃO está no .gitignore do AiDW (o conteúdo privado vazaria)")
    mine = st.get("state_dir")
    for other in list_contexts():
        if other != name and context_status(cfg, other).get("state_dir") == mine:
            errors.append(f"state_dir {mine!r} é o mesmo do contexto {other!r}: cada contexto precisa da sua pasta")
    return {"ok": not errors, "errors": errors, "warnings": warnings, **{k: st.get(k) for k in ("description", "systems")}}


def set_active_context(name: str) -> None:
    """Troca só a linha `active` da seção [context] do aidw.config.toml (os comentários ficam)."""
    text = CONFIG_FILE.read_text(encoding="utf-8")
    pattern = re.compile(r"(^\[context\][^\[]*?^active\s*=\s*)\"[^\"]*\"", re.M | re.S)
    if pattern.search(text):
        text = pattern.sub(lambda m: m.group(1) + json.dumps(name), text, count=1)
    else:
        text = text.rstrip("\n") + f"\n\n[context]\nactive = {json.dumps(name)}\n"
    CONFIG_FILE.write_text(text, encoding="utf-8", newline="\n")


def context_command(cfg: dict, catalog: dict, args: argparse.Namespace) -> int:
    action = args.ctx_action
    if action == "list":
        items = context_list(cfg)
        if args.json:
            print(json.dumps({"ok": True, "active": cfg["context"]["active"] or None, "contexts": items},
                             ensure_ascii=False, indent=2))
            return 0
        if not items:
            print("Nenhum contexto em contexts/. Crie um com a skill contexto-criar (ou `aidw.py context create`).")
        for c in items:
            mark = "*" if c["active"] else " "
            if not c["ok"]:
                print(f" {mark} {c['name']:<16} [erro] {c['error']}")
                continue
            repo = ("git próprio" + (f", remoto {c['remote']}" if c["remote"] else ", sem remoto")) if c["git"] else \
                "SEM repositório git"
            print(f" {mark} {c['name']:<16} {c['description']}")
            print(f"   {'':<16} {repo}; sistemas: {', '.join(c['systems']) or 'nenhum'}; "
                  f"plugin {'instalado' if c['plugin_installed'] else 'não instalado'}")
        print(f"\nAtivo: {cfg['context']['active'] or 'nenhum'}")
        return 0
    if action == "check":
        result = context_check(cfg, catalog, args.name)
    elif action == "create":
        name = args.name.strip().lower()
        if not SLUG_RE.match(name) or name in RESERVED_NAMES:
            result = {"ok": False, "errors": [f"nome inválido {name!r} (minúsculas, dígitos e hífen)"], "warnings": []}
        elif (CONTEXTS_DIR / name).exists():
            result = {"ok": False, "errors": [f"{rel(CONTEXTS_DIR / name)} já existe"], "warnings": []}
        else:
            d = create_context(name, args.description or name, split_answer(args.mcp or ""), split_answer(args.env or ""))
            result = {"ok": True, "errors": [], "warnings": [], "path": d.as_posix(),
                      "note": "repositório git próprio criado (sem remoto). Preencha o context.toml e rode "
                              f"`aidw.py context check {name}`."}
    else:  # use
        check = context_check(cfg, catalog, args.name) if args.name else {"ok": True, "errors": [], "warnings": []}
        previous = cfg["context"]["active"]
        open_demands = [d["id"] for d in demand_list(cfg, active_only=True)] if previous != args.name else []
        if open_demands:
            check["warnings"].append(f"demandas ativas no contexto {previous!r} ficam pausadas: {', '.join(open_demands)}")
        if not check["ok"]:
            result = check
        else:
            set_active_context(args.name)
            new_cfg = load_config()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                applied = apply(new_cfg, catalog, dry=False)
                installed = None
                if applied and load_manifest() and not args.skip_install:
                    installed = install(new_cfg, catalog, dry=False, force=False, skip_cli=args.skip_cli)
            if not applied:  # o aidw.config.toml nunca fica apontando para um ambiente que não foi gerado
                set_active_context(previous)
            result = {"ok": applied and installed is not False,
                      "errors": [] if applied else [f"apply falhou; contexto ativo mantido em {previous!r}"],
                      "warnings": check["warnings"], "active": args.name or None,
                      "plugin": plugin_name(load_context(new_cfg, Report(quiet=True))) if installed else None,
                      "log_tail": out.getvalue().strip().splitlines()[-3:]}
            if installed is False:
                result["errors"].append("install falhou — rode `python aidw.py install` para ver o erro")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for e in result.get("errors", []):
            print(f"[erro]  {e}")
        for w in result.get("warnings", []):
            print(f"[aviso] {w}")
        if result["ok"]:
            print(f"[ok]    {action} {args.name or ''}".rstrip() +
                  (f" — {result['note']}" if result.get("note") else "") +
                  (f" — plugin {result['plugin']}; abra um chat novo" if result.get("plugin") else "") +
                  (" — abra um chat novo" if action == "use" and not result.get("plugin") else ""))
    return 0 if result["ok"] else 1


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
    if getattr(args, "codex_task", None) and cfg["provider"]["name"] != "codex":
        # delegação do Codex (instalação global) numa máquina cuja config é do Claude: modelos e tokens do Codex
        cfg = json.loads(json.dumps(cfg))
        cfg["provider"]["name"] = "codex"
    rep = Report(quiet=True)
    ctx = load_context(cfg, rep)
    resolved = resolve(cfg, catalog, ctx, available_skills(ctx, rep), rep)
    routing = load_routing(rep)
    provider = cfg["provider"]["name"]
    attach_variants(resolved, routing, catalog, rep)
    wanted = slugify(args.agent.rsplit(":", 1)[-1])
    if wanted.startswith(CODEX_NS) and not any(wanted in (r, a["name"]) for r, a in resolved.items()):
        wanted = wanted[len(CODEX_NS):]
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
    dirs = [ROOT.as_posix(), *code_dirs(cfg, ctx)]
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
        write_dirs += [win(d) for d in code_dirs(cfg, ctx)]
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


def claude_login() -> bool | None:
    """Login do Claude Code por `claude auth status` (JSON); None quando não dá para saber."""
    out = run(["claude", "auth", "status"])
    try:
        return bool(json.loads(out).get("loggedIn")) if out else None
    except (json.JSONDecodeError, AttributeError):
        return None


def codex_login() -> bool:
    return "logged in" in (run(["codex", "login", "status"]) or "").lower()


def check_provider(provider: str, cfg: dict, resolved: dict, rep: Report) -> None:
    """CLI, versão e login de um provedor. O ativo é obrigatório; o outro, opcional (só informa)."""
    active = cfg["provider"]["name"] == provider
    heading(f"{PROVIDER_LABEL[provider]} — {'provedor ativo' if active else 'opcional'}")
    if not shutil.which(provider):
        hint = INSTALL_HINTS[provider][platform_key()]
        if active:
            rep.error(f"CLI `{provider}` não encontrado — é ele que executa o orquestrador e os agentes. "
                      f"Instale com: {hint}")
        else:
            rep.info(f"`{provider}` não instalado (opcional). Para instalar: {hint}")
        return
    version = run([provider, "--version"]) or "?"
    rep.ok(f"{provider} {version.splitlines()[0]}")
    logged = claude_login() if provider == "claude" else codex_login()
    login_hint = "rode `claude` e autentique" if provider == "claude" else "rode `codex login`"
    if logged:
        rep.ok("login ativo")
    elif logged is None:
        rep.info("não foi possível confirmar o login (`claude auth status`)")
    else:
        (rep.warn if active else rep.info)(f"sem login — {login_hint}")
    if not active:
        return
    for a in resolved.values():
        need = a["model"].get("min_cli")
        if need and version_tuple(version) < version_tuple(need):
            rep.warn(f"{a['model']['name']} exige {provider} {need}+ (atual {version.split()[0]}); "
                     f"rode `{provider} update`")
            break
    if provider != "codex":
        return
    available = codex_available_models()
    for a in resolved.values():
        if available and a["model"]["model_id"] not in available:
            rep.warn(f"{a['name']}: {a['model']['model_id']} não está liberado para esta conta "
                     f"(disponíveis: {', '.join(sorted(available))})")
    if cfg["delegation"]["mode"] == "native":
        features = run(["codex", "features", "list"]) or ""
        if re.search(r"^multi_agent_v2\s", features, re.M):
            rep.ok("multi_agent_v2 disponível (subagentes com modelo e effort por spawn)")
        else:
            rep.error("esta versão do Codex não tem multi_agent_v2 — atualize o Codex ou use "
                      '[delegation] mode = "headless"')
    if codex_trusted():
        rep.ok("projeto marcado como confiável no Codex (.codex/config.toml vale no app)")
    else:
        rep.info("projeto não marcado como confiável no Codex: .codex/config.toml só vale via "
                 "`python aidw.py chat` (o setup oferece marcar)")


def inside_git_repo(path: Path) -> bool:
    return path.is_dir() and run(["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"]) == "true"


def check_folders(cfg: dict, ctx: dict | None, rep: Report, created: tuple[Path, ...] = ()) -> None:
    heading("Pastas")
    for path, why in required_folders(cfg, ctx):
        if path.is_dir():
            rep.ok(f"{why}: {path.as_posix()}" + (" (criada)" if path in created else ""))
        else:
            rep.warn(f"{why}: {path.as_posix()} não existe — o `setup` cria")
    root = worktree_root(cfg)
    if inside_git_repo(root):
        rep.warn(f"a raiz dos worktrees ({root.as_posix()}) está dentro de um repositório Git; "
                 "use uma pasta fora de qualquer repositório ([worktree] root)")
    for d in project_dirs(cfg, ctx):
        if Path(d).is_dir():
            rep.ok(f"pasta liberada {d}")
        else:
            rep.warn(f"pasta liberada {d} não existe (clone os repositórios ou ajuste a config)")


def pending_apply(cfg: dict, catalog: dict) -> int | None:
    """Quantos arquivos o `apply` mudaria agora; None se a config tem erro."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        ok = apply(cfg, catalog, dry=True)
    # Só as linhas do relatório ("  [--]    (dry-run) criar …"), não o título da seção.
    return sum(bool(re.match(r"\s+\[[^]]+\]\s+\(dry-run\) ", line))
               for line in out.getvalue().splitlines()) if ok else None


def one_line(msg: str) -> str:
    """Mensagem de várias linhas (ex.: aviso com o comando de correção) numa linha só, para o resumo."""
    return " ".join(part.strip() for part in msg.splitlines() if part.strip())


def doctor(cfg: dict, catalog: dict) -> bool:
    """Verifica tudo e termina com o veredito: PRONTO ou NÃO PRONTO (com o que falta)."""
    rep = Report()
    heading("Núcleo")
    rep.ok(f"Python {sys.version.split()[0]}")
    if shutil.which("git"):
        rep.ok(run(["git", "--version"]) or "git")
        if not run(["git", "config", "user.email"]):
            rep.warn("git user.email não configurado")
    else:
        rep.error(f"git não encontrado no PATH. Instale com: {INSTALL_HINTS['git'][platform_key()]}")
    if shutil.which("npx"):
        rep.ok(f"Node.js {run(['node', '--version']) or '?'} (npx para os MCPs locais)")
    else:
        rep.warn("npx não encontrado — os MCPs locais precisam do Node.js. "
                 f"Instale com: {INSTALL_HINTS['npx'][platform_key()]}")

    b = build(cfg, catalog, Report(quiet=True))
    resolved = b["resolved"] if b else {}
    for provider in PROVIDERS:
        check_provider(provider, cfg, resolved, rep)

    heading("Contexto")
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

    heading("MCP")
    check_mcp(cfg, ctx, rep)
    check_folders(cfg, ctx, rep)

    if cfg["provider"]["name"] == "claude":
        check_global_install(cfg, catalog, rep)
    if shutil.which("codex") or load_manifest().get("codex"):
        check_codex_install(rep)

    heading("Ambiente gerado")
    pending = pending_apply(cfg, catalog)
    if pending is None:
        rep.error("a configuração tem erros — rode `python aidw.py apply` para ver quais")
    elif not RUNTIME_FILE.exists():
        rep.warn("ambiente ainda não gerado — rode `python aidw.py apply`")
    elif pending:
        rep.warn(f"{pending} arquivo(s) desatualizado(s) em relação às fontes — rode `python aidw.py apply` "
                 "e abra um chat novo")
    else:
        rep.ok(f"em dia com as fontes ({PROVIDER_LABEL[cfg['provider']['name']]}, "
               f"delegação {cfg['delegation']['mode']})")

    heading("Resultado")
    if rep.errors:
        print(f"  NÃO PRONTO — {len(rep.errors)} erro(s) para corrigir:")
        for msg in rep.errors:
            print(f"    - {one_line(msg)}")
        if rep.warnings:
            print(f"  e {len(rep.warnings)} aviso(s):")
    else:
        print("  PRONTO para usar" + (f", com {len(rep.warnings)} aviso(s):" if rep.warnings else "."))
    for msg in rep.warnings:
        print(f"    - {one_line(msg)}")
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


def install_tool(tool: str, default: bool) -> None:
    hint = INSTALL_HINTS[tool][platform_key()]
    if confirm(f"  Instalar {tool} agora? ({hint})", default):
        shell = ["powershell", "-NoProfile", "-Command", hint] if IS_WINDOWS else ["bash", "-lc", hint]
        code = subprocess.run(shell).returncode
        result = "instalado" if code == 0 else f"falhou (código {code})"
        print(f"  {result} — se o comando não for encontrado, reabra o terminal e rode o setup de novo")


def ensure_tools(provider: str) -> None:
    """Git, Node e os dois CLIs. O provedor ativo é obrigatório; o outro é oferecido como opcional."""
    heading("Pré-requisitos")
    for tool in ("git", "npx", *PROVIDERS):
        if shutil.which(tool):
            print(f"  [ok]    {tool}")
        elif tool not in PROVIDERS or tool == provider:
            print(f"  [falta] {tool}")
            install_tool(tool, True)
        else:
            print(f"  [--]    {tool} não instalado (opcional: outro provedor)")
            install_tool(tool, False)
    if shutil.which("claude") and claude_login() is False:
        print("  [--]    Claude Code sem login: rode `claude` uma vez e autentique")
    if shutil.which("codex") and not codex_login():
        print("  [--]    Codex sem login: rode `codex login` (conta ChatGPT)")


def ensure_folders(cfg: dict) -> None:
    """Cria as pastas que o AiDW precisa; as pastas de projeto só são conferidas."""
    ctx = load_context(cfg, Report(quiet=True))
    created = tuple(path for path, _ in required_folders(cfg, ctx) if not path.is_dir())
    for path in created:
        path.mkdir(parents=True, exist_ok=True)
    check_folders(cfg, ctx, Report(), created)


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
        for d in code_dirs(cfg, b["ctx"]):
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
    p_inst = sub.add_parser("install", help="instala o AiDW no Claude para qualquer pasta (plugin aidw, com o contexto ativo)")
    p_inst.add_argument("--dry-run", action="store_true", help="mostra o que mudaria, sem alterar nada")
    p_inst.add_argument("--force", action="store_true", help="sobrescreve arquivo gerado alterado à mão")
    p_inst.add_argument("--mcp", action="store_true",
                        help="registra no escopo do usuário os MCPs do catálogo que faltam (sobem em toda sessão)")
    p_inst.add_argument("--skip-cli", action="store_true", help=argparse.SUPPRESS)  # testes: sem o CLI do Claude
    p_inst.add_argument("--provider", choices=("claude", "codex", "all"), default="claude",
                        help="onde instalar (padrão: claude)")
    p_uninst = sub.add_parser("uninstall", help="remove do Claude só o que o install acrescentou")
    p_uninst.add_argument("--dry-run", action="store_true", help="mostra o que mudaria, sem alterar nada")
    p_uninst.add_argument("--skip-cli", action="store_true", help=argparse.SUPPRESS)
    p_uninst.add_argument("--provider", choices=("claude", "codex", "all"), default="all")
    p_open = sub.add_parser("open", help="abre o Claude ou o Codex na pasta (ou no worktree da demanda)")
    p_open.add_argument("--provider", choices=("claude", "codex"), default="claude")
    p_open.add_argument("--demand", help="id da demanda: abre no worktree dela")
    p_open.add_argument("--path", help="pasta (padrão: a atual)")
    p_open.add_argument("--print", action="store_true", help="só mostra o comando")
    p_wt = sub.add_parser("worktree", help="worktree por demanda: create, list, inspect, remove, cleanup")
    wt = p_wt.add_subparsers(dest="wt_action", required=True)
    w_create = wt.add_parser("create", help="cria (ou devolve) o worktree da demanda num repositório")
    w_create.add_argument("--repo", required=True, help="pasta do repositório (ou de dentro dele)")
    w_create.add_argument("--demand", required=True, help="id da demanda, ex.: us-1234")
    w_create.add_argument("--slug", help="resumo curto para o nome da branch")
    w_create.add_argument("--base", help="base do worktree (padrão: a branch padrão do origin)")
    wt.add_parser("list", help="worktrees registrados e a situação de cada um")
    for name, help_text in (("inspect", "detalhes de um worktree"), ("remove", "remove um worktree limpo e integrado")):
        w = wt.add_parser(name, help=help_text)
        w.add_argument("target", help="caminho do worktree ou id da demanda")
        w.add_argument("--repo", help="repositório, quando a demanda tem mais de um")
    wt.add_parser("cleanup", help="tira do registro os worktrees cuja pasta sumiu")
    wt.add_parser("hook-create")  # hooks WorktreeCreate/WorktreeRemove do plugin (uso interno)
    wt.add_parser("hook-remove")
    for w in wt.choices.values():
        w.add_argument("--json", action="store_true", help="saída em JSON")
    p_ctx = sub.add_parser("context", help="contextos de trabalho: list, check, use, create")
    cx = p_ctx.add_subparsers(dest="ctx_action", required=True)
    cx.add_parser("list", help="contextos disponíveis e qual está ativo")
    c_check = cx.add_parser("check", help="valida um contexto como se estivesse ativo")
    c_check.add_argument("name")
    c_use = cx.add_parser("use", help="ativa um contexto (apply e, se instalado, install)")
    c_use.add_argument("name", nargs="?", default="", help="nome do contexto (vazio = nenhum)")
    c_use.add_argument("--skip-install", action="store_true", help="não reinstala o plugin")
    c_use.add_argument("--skip-cli", action="store_true", help=argparse.SUPPRESS)
    c_create = cx.add_parser("create", help="cria contexts/<nome>/ com a estrutura mínima e git próprio")
    c_create.add_argument("name")
    c_create.add_argument("--description")
    c_create.add_argument("--mcp", help="servidores MCP exigidos (vírgula)")
    c_create.add_argument("--env", help="variáveis de ambiente exigidas (vírgula)")
    for c in cx.choices.values():
        c.add_argument("--json", action="store_true", help="saída em JSON")
    p_dm = sub.add_parser("demand", help="estado da demanda para retomar: set, show, list")
    dm = p_dm.add_subparsers(dest="dm_action", required=True)
    d_set = dm.add_parser("set", help="cria ou atualiza o demand.json (etapa, status, título, nota)")
    d_set.add_argument("id", help="id da demanda, ex.: us-1234")
    d_set.add_argument("--step", help="etapa atual: UNDERSTAND ou uma ação de NEXT ACTION")
    d_set.add_argument("--status", choices=("active", "paused", "done"))
    d_set.add_argument("--title")
    d_set.add_argument("--note", help="onde parou / próximo passo")
    d_show = dm.add_parser("show", help="mostra o demand.json")
    d_show.add_argument("id")
    d_list = dm.add_parser("list", help="demandas do contexto (mais recentes primeiro)")
    d_list.add_argument("--active", action="store_true", help="só as não concluídas")
    for d in dm.choices.values():
        d.add_argument("--json", action="store_true", help="saída em JSON")
    p_proj = sub.add_parser("project", help="projeto da pasta: repositório, sistema, contexto e demanda")
    proj = p_proj.add_subparsers(dest="proj_action", required=True)
    p_detect = proj.add_parser("detect", help="detecta o projeto a partir de uma pasta")
    p_detect.add_argument("--path", default=".", help="pasta (padrão: a atual)")
    p_detect.add_argument("--json", action="store_true", help="saída em JSON")
    sub.add_parser("doctor", help="verifica tudo e diz se o ambiente está pronto")
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
        ensure_folders(cfg)
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
    if command == "worktree":
        return worktree_command(cfg, args)
    if command == "demand":
        return demand_command(cfg, args)
    if command == "context":
        return context_command(cfg, catalog, args)
    if command == "project":
        result = project_detect(cfg, args.path)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            for k, v in result.items():
                print(f"  {k:<15} {v}")
        return 0
    if command == "install":
        ok = True
        if args.provider in ("claude", "all"):
            ok = install(cfg, catalog, args.dry_run, args.force, args.skip_cli, args.mcp) and ok
        if args.provider in ("codex", "all"):
            ok = install_codex(cfg, catalog, args.dry_run, args.force) and ok
        return 0 if ok else 1
    if command == "uninstall":
        ok = True
        if args.provider in ("codex", "all"):
            ok = uninstall_codex(args.dry_run) and ok
        if args.provider in ("claude", "all"):
            ok = uninstall(args.dry_run, args.skip_cli) and ok
        return 0 if ok else 1
    if command == "open":
        return open_command(cfg, args.provider, args.demand or "", args.path or "", args.print)
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
