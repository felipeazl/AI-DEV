#!/usr/bin/env python3
"""AiDW — agentic development environment with an orchestrator and specialized agents.

Usage:
    python aidw.py setup [--reconfigure]   # prerequisites + wizard + apply + doctor
    python aidw.py configure [--defaults]  # wizard only; writes aidw.config.toml
    python aidw.py apply [--dry-run]       # generates the environment from the config (idempotent)
    python aidw.py doctor                  # checks everything and says whether the environment is ready
    python aidw.py install [--dry-run]     # AiDW in any folder in Claude (aidw plugin)
    python aidw.py uninstall [--dry-run]   # removes only what install added
    python aidw.py install --provider codex|all   # also in Codex (agents and skills only)
    python aidw.py open [--provider codex] [--demand <id>]   # opens the chat in the demand's worktree
    python aidw.py worktree create --repo <dir> --demand <id> [--slug s] [--base b] [--pr n]
    python aidw.py worktree list | inspect | remove | cleanup
    python aidw.py project detect [--path <dir>] [--json]
    python aidw.py context list | check <name> | use <name> | create <name> --description d
    python aidw.py demand set <id> [--step S] [--status active|paused|done] [--note n]   # and show/list
    python aidw.py show                    # resolved agents, names, models and efforts
    python aidw.py chat                    # opens the orchestrator in the provider's CLI
    python aidw.py delegate --agent <role|name> --effort <e> --task <file> --demand <dir>

One provider per installation ([provider].name): everything runs on Claude Code or everything runs on Codex.
Claude Code is the main platform; on Codex, only the agents and the skills (docs/claude-and-codex.md).
The orchestrator is the chat (`/aidw:go` in any folder, or a chat opened at the AiDW root); each agent is a native
subagent with its model and effort pinned in its definition (`[delegation] mode = "headless"`: one process per task,
through `delegate`).
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
    sys.exit("AiDW requires Python 3.11+ (uses tomllib).")

import tomllib

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "aidw.config.toml"
MODELS_FILE = ROOT / "config" / "models.toml"
MCP_CATALOG_FILE = ROOT / "config" / "mcp.toml"
ROUTING_FILE = ROOT / "orchestrator" / "config" / "routing.toml"
ORCHESTRATOR_MD = ROOT / "orchestrator" / "ORCHESTRATOR.md"
SURVEY_MD = ROOT / "orchestrator" / "SURVEY.md"  # the survey-only orchestrator (survey skill)
# included whole in the survey prompt (old names too: a context may still ship its estimation scale as
# `regua-estimativa`)
SURVEY_REFS = ("survey", "levantamento", "estimation-scale", "regua-estimativa")
ORCH_REF_DIR = ROOT / "orchestrator" / "reference"   # read on demand by the orchestrator
POLICIES_DIR = ROOT / "orchestrator" / "policies"
KB_README_TEMPLATE = ROOT / "orchestrator" / "templates" / "knowledge-README.md"  # `context create`
AGENTS_DIR = ROOT / "agents"
SKILLS_DIR = ROOT / "skills"
CONTEXTS_DIR = ROOT / "contexts"
WORKFLOWS_DIR = ROOT / "workflows"

GEN_DIR = ROOT / ".aidw"                       # generated, provider-independent
GEN_AGENTS_DIR = GEN_DIR / "agents"            # each agent's definition (markdown)
CLAUDE_AGENTS_JSON = GEN_DIR / "claude-agents.json"
RUNTIME_FILE = GEN_DIR / "runtime.json"
GEN_REF_DIR = GEN_DIR / "reference"           # orchestrator references, already rendered

# Claude Code
CLAUDE_MD = ROOT / "CLAUDE.md"
# The project-mode CLAUDE.md, for `claudeMdExcludes` (glob over the absolute path, without the drive letter)
ROOT_CLAUDE_MD_EXCLUDE = "**/" + ROOT.as_posix().split(":", 1)[-1].lstrip("/") + "/CLAUDE.md"
CLAUDE_SETTINGS = ROOT / ".claude" / "settings.local.json"
CLAUDE_SKILLS = ROOT / ".claude" / "skills"
CLAUDE_SUBAGENTS = ROOT / ".claude" / "agents"   # native subagents (native mode)
MCP_JSON = ROOT / ".mcp.json"
# Codex
AGENTS_MD = ROOT / "AGENTS.md"
CODEX_CONFIG = ROOT / ".codex" / "config.toml"
CODEX_RULES = ROOT / ".codex" / "rules" / "aidw.rules"
CODEX_SUBAGENTS = ROOT / ".codex" / "agents"     # Codex native roles (native mode)
CODEX_SKILLS = ROOT / ".agents" / "skills"
CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
# Global install in Claude (aidw.py install): one plugin per context in a local marketplace.
CLAUDE_HOME = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
USER_SETTINGS = CLAUDE_HOME / "settings.json"
MARKETPLACE_DIR = GEN_DIR / "marketplace"
MARKETPLACE_NAME = "aidw-local"
# Claude Code mods (function-hook plugins): Claude only, installed together with the `aidw` plugin.
MODS_DIR = ROOT / "mods"
MODS_PLUGIN = "aidw-mods"
INSTALL_MANIFEST = GEN_DIR / "install-manifest.json"
PLUGIN_VERSION_BASE = "3.0.0"
# Global install in Codex (aidw.py install --provider codex): AiDW's own files, named `aidw-*`.
CODEX_NS = "aidw-"
CODEX_SKILLS_HOME = Path(os.environ.get("AIDW_CODEX_SKILLS_DIR") or Path.home() / ".agents" / "skills")
CODEX_AGENTS_HOME = CODEX_HOME / "agents"
# Only to clean up old installs (rules, hooks and profile); today's install is agents and skills.
CODEX_GLOBAL_RULES = CODEX_HOME / "rules" / "aidw.rules"
CODEX_HOOKS_FILE = CODEX_HOME / "hooks.json"
CODEX_PROFILE = CODEX_HOME / "aidw.config.toml"
# Plugin descriptions enter every session: the guard keeps Claude from using AiDW outside a demand.
PLUGIN_GUARD = "[AiDW] Only inside a demand run by the AiDW orchestrator."
ADMIN_GUARD = "[AiDW] AiDW administration."  # skills with `aidw: admin` (contexts): valid outside a demand
# Codex truncates AGENTS.md at 32 KiB by default; AiDW raises the limit for the orchestrator.
CODEX_DOC_MAX_BYTES = 98304

IS_WINDOWS = os.name == "nt"
# Root of the demands' worktrees: short (legacy MSBuild and MAX_PATH) and outside any repository.
DEFAULT_WORKTREE_ROOT = "C:/wt" if IS_WINDOWS else "~/wt"
REGISTRY_FILE = ROOT / "state" / "worktrees.json"   # registry of the demands' worktrees (git is the truth)
GUARD_SCRIPT = ROOT / "aidw_guard.py"               # the plugin's PreToolUse hook
# Build dependencies outside git that the worktree gets by junction (if they exist in the working copy).
DEFAULT_WORKTREE_LINKS = ["packages", "node_modules"]
DEMAND_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
GENERATED_MARK = "Generated by aidw.py"
# Every mark a generated file may carry (the old Portuguese one too): cleanup recognizes them all.
GENERATED_MARKS = (GENERATED_MARK, "Gerado por aidw.py")
DEFAULT_LANGUAGE = "en"   # [ui] language when aidw.config.toml does not set it
ORCHESTRATOR = "orchestrator"
PLANNER = "planner"
EXPLORER = "explorer"
# Roles added after the first configs: a config that does not list them gets them with the default.
LATE_ROLES = (PLANNER, EXPLORER)
# Roles removed in flow v3 (2026-10-23): the explorer and qa absorbed api; the reviewer, the bugs and security
# ones. An old config that still lists them is accepted, with a warning, and they are not generated.
REMOVED_ROLES = ("api-db", "bug-hunter", "security")
PROVIDERS = ("claude", "codex")
PROVIDER_LABEL = {"claude": "Claude (Claude Code)", "codex": "Codex (Codex CLI)"}
# native   = the provider's native subagents (Claude: Agent tool; Codex: spawn_agent)
# headless = one CLI process per task, via `aidw.py delegate`
DELEGATION_MODES = ("native", "headless")

ACTIONS = {"EXPLORE", "PLAN", "PLAN_APPROVAL", "PLAN_FIX", "IMPLEMENT", "TEST_PLAN", "REVIEW", "TRIAGE", "CODER_FIX",
           "USER_REVIEW", "TEST", "TEST_ADJUST", "MANUAL_TEST", "PR", "ESTIMATE", "FINAL_REVIEW", "DONE",
           "HUMAN_APPROVAL", "RETURN", "CODE_REVIEW", "QA_TEST"}
# Steps of the old flow: `demand set` still accepts them, so a demand opened before flow v3 can finish in the
# plugin it started in (the panel puts them in the equivalent phase).
LEGACY_STEPS = {"SPEC", "PLAN_REVIEW", "TICKETS", "PREPARE_REVIEW", "ORCHESTRATOR_TEST", "DOCS"}
# Steps outside AiDW (the team reviews the PR, QA tests): recorded when the user says so; the panel shows them apart.
# The context may declare others ([[workflows.external_steps]]), each one before one of these.
EXTERNAL_STEPS = ("CODE_REVIEW", "QA_TEST")
# Before which steps a context's outside step may come: the outside ones and the PR (e.g. UX validation, after
# the tests and before opening the PR — flow v3).
EXTERNAL_BEFORE = (*EXTERNAL_STEPS, "PR")
EXTERNAL_STEP_RE = re.compile(r"^[A-Z][A-Z0-9_]*[A-Z0-9]$")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_MCP = ["playwright", "chrome-devtools", "figma", "context7"]

DEFAULT_NAMES = {
    "orchestrator": "orchestrator",
    "planner": "planner",
    "explorer": "explorer",
    "coder": "coder",
    "reviewer": "reviewer",
    "qa": "qa",
    "documenter": "documenter",
}

# ---------------------------------------------------------------------------
# Old (Portuguese) → new (English) names: the single table (PR 2, 2026-11). The AiDW writes only the new name;
# everything that reads, globs or matches accepts the new name AND the old ones, so demands, configs and contexts
# from before the rename keep working. Add an alias here, never inline. Each entry: new → (old, ...).
# ---------------------------------------------------------------------------
LEGACY_NAMES: dict[str, dict[str, tuple[str, ...]]] = {
    # demand artifact file-name prefixes (longest first: `plan-review-` and `test-plan-` before `plan-`)
    "artifact": {
        "plan-review-": ("revisao-plano-",), "test-plan-": ("plano-testes-",), "test-script-": ("roteiro-testes-",),
        "test-env-": ("ambiente-teste-",), "summary-": ("resumo-",), "plan-": ("plano-",),
        "exploration-": ("exploracao-",), "task-": ("tarefa-",), "triage-": ("triagem-",),
        "learnings-": ("aprendizados-",), "survey-": ("levantamento-",), "coverage-": ("cobertura-",),
        "security-": ("seguranca-",), "points-": ("pontos-",),
    },
    # whole file names in a demand folder
    "file": {"state.md": ("estado.md",), "metrics.md": ("metricas.md",),
             "orchestrator-metrics.md": ("metricas-orquestrador.md",)},
    # folders
    "dir": {"ux-screenshots": ("prints-ux",), "knowledge": ("conhecimento",)},
    # workflows (workflows/*.yaml `name`, context.toml [workflows.by_type])
    "workflow": {"development": ("desenvolvimento",), "survey": ("levantamento",)},
    # core skills (agent skill lists in aidw.config.toml and context.toml)
    "skill": {"prepare-worktree": ("preparar-worktree",), "verify-premise": ("verificar-premissa",)},
    # core orchestrator references (orchestrator/reference/*.md)
    "reference": {"short-path": ("caminho-curto",), "testing": ("testes",), "pr-triage": ("triagem-pr",),
                  "survey": ("levantamento",)},
    # default agent names (`record --agent`, an old chat still naming them)
    "agent": {"orchestrator": ("orquestrador",), "planner": ("planejador",), "explorer": ("explorador",),
              "coder": ("codificador",), "reviewer": ("revisor",), "documenter": ("documentador",)},
    # words in commands: `/aidw:diff exit`; demand ids made from a survey (`survey-<slug>`)
    "word": {"exit": ("sair",), "survey-": ("lev-",)},
}


def legacy_names(kind: str, new: str) -> tuple[str, ...]:
    """The new name followed by its old aliases (`legacy_names("file", "metrics.md")`)."""
    return (new, *LEGACY_NAMES[kind].get(new, ()))


def modern_name(kind: str, name: str) -> str:
    """The new name for an old one (or the name itself, when it is already new or unknown)."""
    for new, olds in LEGACY_NAMES[kind].items():
        if name in olds:
            return new
    return name


def artifact_kind(file_name: str) -> str | None:
    """The NEW prefix of a demand artifact file name, old or new (`resumo-x.md` → `summary-`), or None."""
    for new, olds in LEGACY_NAMES["artifact"].items():
        if file_name.startswith((new, *olds)):
            return new
    return None


def demand_file(folder: Path, new: str) -> Path:
    """The file `new` in a demand folder: the new name, or the old one when only that exists (an older demand)."""
    for name in legacy_names("file", new):
        if (folder / name).exists():
            return folder / name
    return folder / new


def is_generated(text: str) -> bool:
    return any(m in text for m in GENERATED_MARKS)

# Model and effort of each role (flow v3, no levels; decision, 2026-10-23): Opus for the orchestrator; Sonnet high
# for the planner, coder and reviewer; Sonnet medium for qa; Haiku for the explorer and the documenter. The allowed
# exceptions (go down on a re-review, go up when the result made no sense) live in [effort.variants] of
# routing.toml. On Codex the tier picks the equivalent (config/models.toml).
# skills  = available to the agent (listed in the prompt; it calls them with the Skill tool when needed)
# preload = subset injected whole at the start of every run — only what it always uses.
DEFAULT_AGENTS: dict[str, dict] = {
    "orchestrator": {"enabled": True, "tier": "top", "effort": "medium",
                     "skills": ["to-spec", "verify-premise", "prepare-worktree"]},
    # Planner: the plan, its fix and the tickets, in a fresh context (the orchestrator's stays lean).
    "planner": {"enabled": True, "tier": "mid", "effort": "high",
                "skills": ["to-spec", "verify-premise"], "preload": ["to-spec"]},
    # Explorer: cheap code reading, with `file:line`, and the queries (ids, contracts, SELECT through the
    # context's validator) that belonged to api, in a report the plan and the code reuse.
    "explorer": {"enabled": True, "tier": "fast", "effort": "low", "skills": ["database-safe"]},
    "coder": {"enabled": True, "tier": "mid", "effort": "high", "skills": ["prepare-worktree"]},
    # Reviewer: quality, bugs and security in a single pass (the code-review skill covers all three).
    "reviewer": {"enabled": True, "tier": "mid", "effort": "high",
                 "skills": ["code-review", "verify-premise"], "preload": ["code-review"]},
    # QA: test script and test data in parallel with the coder; after the user's review, the test (API and browser
    # on its own, the rest assisted by the user).
    "qa": {"enabled": True, "tier": "mid", "effort": "medium", "skills": ["database-safe"]},
    # Documenter: the Tasks on the board and the PR text.
    "documenter": {"enabled": True, "tier": "fast", "effort": "medium", "skills": []},
}
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]*$")
RESERVED_NAMES = {"general-purpose", "explore", "plan", "statusline-setup", "claude-code-guide",
                  "default", "worker"}
PLACEHOLDER_RE = re.compile(r"\{\{agent:([\w-]+)\}\}")

# Headless run of each role.
#   claude_mode: --permission-mode. `auto` runs the routine and denies what would fall into `ask` (commit,
#                push, sqlcmd…), which comes back in permission_denials. api stays on `default`: only
#                what is in allow (SQL validator, read-only git).
#   write:       where the Codex agent may write besides the AiDW root (which includes the state dir).
#   network:     network access of the Codex agent's commands (build with restore, APIs).
RUN_PROFILE = {
    "planner": {"claude_mode": "auto", "max_turns": 50, "write": "state", "network": False},
    "explorer": {"claude_mode": "auto", "max_turns": 40, "write": "state", "network": True},
    "coder": {"claude_mode": "auto", "max_turns": 80, "write": "projects", "network": True},
    "reviewer": {"claude_mode": "auto", "max_turns": 40, "write": "state", "network": False},
    "documenter": {"claude_mode": "auto", "max_turns": 40, "write": "projects", "network": False},
    "qa": {"claude_mode": "auto", "max_turns": 40, "write": "state", "network": True},
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
# Output
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
        self._print("[warn] ", msg)

    def error(self, msg: str) -> None:
        self.errors.append(msg)
        self._print("[error]", msg)


def heading(title: str) -> None:
    print(f"\n== {title} ==")


def rel(p: Path) -> str:
    """Path relative to the root, without following links (skill junctions show the link itself)."""
    try:
        return Path(os.path.abspath(p)).relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def win(p: Path | str) -> str:
    """Path in the system's format (backslashes on Windows)."""
    return str(Path(p))


# ---------------------------------------------------------------------------
# Config, catalog and context
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
    """The provider's first model with the tier; on Codex, only those enabled for the account."""
    available = codex_available_models() if provider == "codex" else set()
    candidates = [k for k, m in catalog.items() if m.get("provider") == provider and tier in m.get("tiers", [])]
    for key in candidates:
        if not available or catalog[key]["model_id"] in available:
            return key
    return candidates[0] if candidates else None


def equivalent_model(catalog: dict, key: str, provider: str, fallback_tier: str = "mid") -> str | None:
    """The provider's model that matches `key` from another provider, by tier (Opus → top, Sonnet → mid,
    Haiku → fast): the same per-tier model table serves Claude and Codex. Without a tier (e.g. Fable), the
    role's tier."""
    m = catalog[key]
    if m["provider"] == provider:
        return key
    return tier_model(catalog, provider, (m.get("tiers") or [fallback_tier])[0])


def default_config(provider: str = "claude") -> dict:
    return {
        "provider": {"name": provider},
        "delegation": {"mode": "native"},
        "workspace": {"project_dirs": []},
        "worktree": {"root": DEFAULT_WORKTREE_ROOT},
        "mcp": {"enabled": list(DEFAULT_MCP)},
        "context": {"active": ""},
        "ui": {"language": DEFAULT_LANGUAGE},
        "policies": {"deny": list(DEFAULT_DENY), "ask": []},
        "agents": json.loads(json.dumps({role: {k: v for k, v in a.items() if k != "tier"}
                                         for role, a in DEFAULT_AGENTS.items()})),
    }


def load_config() -> dict | None:
    if not CONFIG_FILE.exists():
        return None
    cfg = load_toml(CONFIG_FILE)
    base = default_config()
    for section in ("provider", "delegation", "workspace", "worktree", "mcp", "context", "ui", "policies"):
        base[section].update(cfg.get(section, {}))
    base["ui"]["language"] = str(base["ui"].get("language") or DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE
    if "agents" in cfg:
        base["agents"] = {}
        for role, a in cfg["agents"].items():
            if role in REMOVED_ROLES:  # old-flow role: resolve warns and it is not generated
                base.setdefault("removed_roles", []).append(role)
                continue
            defaults = {k: v for k, v in DEFAULT_AGENTS.get(role, {"enabled": True, "skills": []}).items()
                        if k != "tier"}
            base["agents"][role] = {**defaults, **a}
            for key in ("skills", "preload"):  # old core skill names (verificar-premissa…) → new
                if isinstance(base["agents"][role].get(key), list):
                    base["agents"][role][key] = [modern_name("skill", x) for x in base["agents"][role][key]]
        for role in LATE_ROLES:  # role added after the config: it comes with the default (turn off: enabled = false)
            if role not in base["agents"]:
                base["agents"][role] = {k: v for k, v in DEFAULT_AGENTS[role].items() if k != "tier"}
    return base


def ui_language(cfg: dict | None) -> str:
    """The language the orchestrator chat uses with the user ([ui] language; default English)."""
    return ((cfg or {}).get("ui", {}).get("language") or DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE


def context_language(cfg: dict | None, ctx: dict | None) -> str:
    """The language of the context's content and of the demand artifacts: context.toml `language`, inheriting
    the AiDW [ui] language."""
    return ((ctx or {}).get("language") or "").strip() or ui_language(cfg)


LANGUAGE_TAG_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
LANGUAGE_NAMES = {"en": "English", "pt-BR": "Portuguese (Brazil)", "pt": "Portuguese", "es": "Spanish"}


def language_label(tag: str) -> str:
    """`pt-BR` → `Portuguese (Brazil) (pt-BR)`; an unknown tag is shown as is."""
    name = LANGUAGE_NAMES.get(tag) or LANGUAGE_NAMES.get(tag.split("-")[0], "")
    return f"{name} (`{tag}`)" if name else f"`{tag}`"


def slugify(text: str) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")


def agent_names(role: str, agent: dict) -> tuple[str, str]:
    """(slug, display name). The configured name may have accents and spaces; the slug is the
    identifier used in commands and files."""
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
    raise TypeError(f"type not supported in TOML: {type(v)}")


def render_config(cfg: dict) -> str:
    out = [
        f"# AiDW configuration. {GENERATED_MARK} configure on {date.today().isoformat()}.",
        "# You may edit it by hand; then run `python aidw.py apply` and open a new chat.",
        "# Warning: `configure` rewrites this file (your own comments are lost).",
        "",
        "[provider]",
        '# "claude" = everything on Claude Code · "codex" = everything on Codex CLI. One provider at a time.',
        f"name = {toml_value(cfg['provider']['name'])}",
        "",
        "[delegation]",
        '# "native"   = the provider\'s native subagents (Claude: Agent tool; Codex: spawn_agent)',
        '# "headless" = one CLI process per task, via `python aidw.py delegate`',
        f"mode = {toml_value(cfg['delegation']['mode'])}",
        "",
        "[workspace]",
        "# Your projects' folders. Open to the orchestrator and every agent.",
        f"project_dirs = {toml_value(cfg['workspace']['project_dirs'])}",
        "",
        "[worktree]",
        "# Where the demands' worktrees live (<root>/<id>/<repo>). Short and outside any repository.",
        f"root = {toml_value(cfg['worktree']['root'])}",
        "",
        "[mcp]",
        "# Servers from config/mcp.toml registered in the project. The orchestrator decides when to use them.",
        f"enabled = {toml_value(cfg['mcp']['enabled'])}",
        "",
        "[context]",
        '# Package of work rules in contexts/<name>/ ("" = none).',
        f"active = {toml_value(cfg['context']['active'])}",
        "",
        "[ui]",
        '# The language the orchestrator chat talks to you in (BCP-47 tag: "en", "pt-BR", ...). A context\'s own',
        "# content and the demand artifacts use the context's `language` (context.toml), which inherits this one.",
        "# File names are always English.",
        f"language = {toml_value(ui_language(cfg))}",
        "",
        "[policies]",
        "# deny = always blocked · ask = always asks for confirmation (beats any allow).",
        "# Claude Code syntax; on Codex, the command rules become .codex/rules/aidw.rules.",
        "deny = [",
        *[f"    {toml_value(d)}," for d in cfg["policies"]["deny"]],
        "]",
        "ask = [",
        *[f"    {toml_value(d)}," for d in cfg["policies"]["ask"]],
        "]",
        "",
        "# [agents.<role>] — the role is fixed. Optional:",
        "#   name   agent name (accents and spaces allowed; without it, the commented default applies)",
        "#   model  key from the provider's config/models.toml; without it, the role's default tier applies",
        "#          (Opus/top for the orchestrator; Sonnet/mid for the planner, coder, reviewer and qa;",
        "#           Haiku/fast for the explorer and the documenter). Another provider's model becomes its equivalent.",
        "#   effort the agent's default effort; the allowed exceptions live in [effort.variants] of routing.toml.",
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
    """{{root}} and {{context}} in context.toml strings (paths in the system's format)."""
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
        rep.error(f"context {name!r} not found ({rel(path)}): clone its repository into "
                  f"contexts/{name}/ or run `setup` to choose another, create one or go on without one")
        return None
    ctx = expand_vars(load_toml(path), path_vars(path.parent))
    ctx["name"] = name
    ctx["dir"] = path.parent
    ctx.setdefault("description", name)
    wf = ctx.get("workflows", {})
    if isinstance(wf.get("by_type"), dict):  # old workflow names (desenvolvimento, levantamento) → new
        wf["by_type"] = {kind: modern_name("workflow", w) for kind, w in wf["by_type"].items()}
    for agent, spec in ctx.get("agents", {}).items():
        for inc in spec.get("include", []):
            if not (ctx["dir"] / inc).is_file():
                rep.error(f"context {name}: [agents.{agent}] includes a missing file {inc!r}")
        for ref in spec.get("reference", []):
            if not (ctx["dir"] / ref.get("path", "")).is_file():
                rep.error(f"context {name}: [agents.{agent}] missing reference {ref.get('path')!r}")
    systems = ctx.get("systems", {})
    for key, sysdef in systems.items():
        for dep in sysdef.get("depends_on", []):
            if dep not in systems:
                rep.warn(f"context {name}: system {key!r} depends on {dep!r}, which is not in [systems]")
        for repo in sysdef.get("repos", []):
            if not Path(repo).is_dir():
                rep.warn(f"context {name}: repository of system {key!r} does not exist: {repo}")
    check_environments(ctx, rep)
    return ctx


def check_environments(ctx: dict, rep: Report) -> None:
    """[environments]: test, test_fallback and every explore entry must be one of `order`."""
    envs = ctx.get("environments", {})
    order = envs.get("order", [])
    for field in ("test", "test_fallback"):
        if envs.get(field) and envs[field] not in order:
            rep.error(f"context {ctx['name']}: [environments] {field} = {envs[field]!r} is not in order {order}")
    for env in envs.get("explore", []):
        if env not in order:
            rep.error(f"context {ctx['name']}: [environments] explore names {env!r}, which is not in order {order}")


def environment_lines(ctx: dict | None) -> list[str]:
    """The context's environments ([environments]) as Runtime lines: the order towards production, where tests run,
    the fallback and where the explorer reads. Nothing when the context declares none."""
    envs = ctx.get("environments", {}) if ctx else {}
    order = envs.get("order", [])
    if not order:
        return []
    code = lambda names: ", ".join(f"`{n}`" for n in names)
    lines = [f"- Environments, from the furthest to the closest to production: {' → '.join(f'`{n}`' for n in order)}"]
    if envs.get("test"):
        fallback = (f"; `{envs['test_fallback']}` only for a step that cannot be proved there — proposed with the "
                    f"reason, for that case only, never as the new default" if envs.get("test_fallback") else "")
        lines.append(f"- Test environment: `{envs['test']}` by default{fallback}")
    if envs.get("explore"):
        lines.append(f"- Explore in: {code(envs['explore'])} — every one of them; when they disagree, trust the one "
                     f"with more data and, in a tie, the one closest to production")
    return lines


def context_missing(cfg: dict) -> bool:
    name = cfg["context"]["active"]
    return bool(name) and not (CONTEXTS_DIR / name / "context.toml").exists()


def state_dir(ctx: dict | None) -> Path:
    return ROOT / (ctx.get("state_dir", "state") if ctx else "state")


def session_dirs(ctx: dict | None) -> list[Path]:
    """Folders the orchestrator session takes along: the active context's (plans, references) and the demands'
    state when it lives outside it."""
    dirs = [ctx["dir"]] if ctx else []
    state = state_dir(ctx)
    if not any(state == d or d in state.parents for d in dirs):
        dirs.append(state)
    return dirs


def worktree_root(cfg: dict) -> Path:
    return Path(os.path.expanduser(cfg["worktree"]["root"]))


def required_folders(cfg: dict, ctx: dict | None) -> list[tuple[Path, str]]:
    """Folders AiDW needs and that setup creates when missing."""
    return [(CONTEXTS_DIR, "work contexts"), (state_dir(ctx), "demand state"),
            (worktree_root(cfg), "demand worktrees")]


def code_dirs(cfg: dict, ctx: dict | None) -> list[str]:
    """Where the agents touch code: the project folders and the root of the demands' worktrees."""
    return list(dict.fromkeys([*project_dirs(cfg, ctx), worktree_root(cfg).as_posix()]))


def project_dirs(cfg: dict, ctx: dict | None) -> list[str]:
    """Allowed folders: the workspace's (machine) + the context's, without repetition."""
    dirs = [*cfg["workspace"]["project_dirs"], *(ctx.get("additional_dirs", []) if ctx else [])]
    return list(dict.fromkeys(d.replace("\\", "/").rstrip("/") for d in dirs))


def available_skills(ctx: dict | None, rep: Report) -> dict[str, Path]:
    skills = {d.name: d for d in sorted(SKILLS_DIR.iterdir()) if (d / "SKILL.md").exists()}
    ctx_skills = ctx["dir"] / "skills" if ctx else None
    if ctx_skills and ctx_skills.is_dir():
        for d in sorted(ctx_skills.iterdir()):
            if (d / "SKILL.md").exists():
                if d.name in skills:
                    rep.warn(f"context skill {d.name!r} replaces the generic skill")
                skills[d.name] = d
    return skills


def context_files(ctx: dict | None, role: str) -> list[Path]:
    if not ctx:
        return []
    return [ctx["dir"] / inc for inc in ctx.get("agents", {}).get(role, {}).get("include", [])]


def orchestrator_policy_refs(ctx: dict | None) -> list[tuple[Path, str]]:
    """Policies the orchestrator reads on demand (frontmatter `orchestrator_when`)."""
    return [(f, w) for f in policy_files(ctx) if (w := read_frontmatter(f)[0].get("orchestrator_when"))]


def policy_files(ctx: dict | None) -> list[Path]:
    files = sorted(POLICIES_DIR.glob("*.md"))
    if ctx and (ctx["dir"] / "policies").is_dir():
        files += sorted((ctx["dir"] / "policies").glob("*.md"))
    return files


def resolve(cfg: dict, catalog: dict, ctx: dict | None, skills: dict, rep: Report) -> dict[str, dict]:
    """Validates the config and returns {role: {name, display, model, effort, skills, enabled…}}."""
    provider = cfg["provider"]["name"]
    if provider not in PROVIDERS:
        rep.error(f"provider.name must be {' or '.join(PROVIDERS)} (current: {provider!r})")
        return {}
    for key, m in catalog.items():
        if m.get("provider") not in PROVIDERS:
            rep.error(f"config/models.toml: {key} with invalid provider {m.get('provider')!r}")
        for e in m.get("efforts", []):
            if e not in EFFORTS:
                rep.error(f"config/models.toml: invalid effort in {key}: {e!r}")

    if cfg["delegation"]["mode"] not in DELEGATION_MODES:
        rep.error(f"delegation.mode must be {' or '.join(DELEGATION_MODES)} "
                  f"(current: {cfg['delegation']['mode']!r})")
    agents = cfg["agents"]
    if ORCHESTRATOR not in agents or not agents[ORCHESTRATOR].get("enabled", True):
        rep.error("the orchestrator agent is required and must be enabled")

    for role in cfg.get("removed_roles", []):
        rep.warn(f"aidw.config.toml: [agents.{role}] was removed in flow v3 (the explorer and qa do the api's job; "
                 "the reviewer, the bugs and security ones) and is ignored; delete the section")
    resolved = {}
    for role, a in agents.items():
        key = a.get("model")
        if key and key not in catalog:
            rep.error(f"agent {role}: model {key!r} does not exist in config/models.toml")
            continue
        if key and catalog[key]["provider"] != provider:
            key = equivalent_model(catalog, key, provider,  # e.g. `opus` on Codex → Codex's top
                                   DEFAULT_AGENTS.get(role, {}).get("tier", "mid"))
        if not key:
            key = tier_model(catalog, provider, DEFAULT_AGENTS.get(role, {}).get("tier", "mid"))
        if not key:
            rep.error(f"agent {role}: no model of provider {provider} in config/models.toml")
            continue
        model = {**catalog[key], "key": key}
        effort = a.get("effort") or ""
        if effort and effort not in EFFORTS:
            rep.error(f"agent {role}: invalid effort {effort!r} (valid: {', '.join(EFFORTS)})")
        if not model.get("efforts"):
            effort = ""
        elif effort and effort not in model["efforts"]:
            rep.error(f"agent {role}: {model['name']} does not accept effort {effort!r}")
        if a.get("enabled", True) and role != ORCHESTRATOR and not (AGENTS_DIR / role / "AGENT.md").exists():
            rep.error(f"agent {role}: agents/{role}/AGENT.md does not exist")
        ctx_agent = ctx.get("agents", {}).get(role, {}) if ctx else {}
        def skill_name(x: str) -> str:  # an old core skill name (verificar-premissa) → the new one
            return x if x in skills else modern_name("skill", x)
        all_skills = list(dict.fromkeys(map(skill_name, [*a.get("skills", []), *ctx_agent.get("skills", [])])))
        preload = list(dict.fromkeys(map(skill_name, [*a.get("preload", []), *ctx_agent.get("preload", [])])))
        for s in all_skills:
            if s not in skills:
                rep.error(f"agent {role}: skill {s!r} not found")
        for s in preload:
            if s not in all_skills:
                rep.error(f"agent {role}: preload {s!r} must also be in skills")
        slug, display = agent_names(role, a)
        resolved[role] = {"role": role, "enabled": a.get("enabled", True), "name": slug,
                          "display": display, "skills": all_skills, "preload": preload, "model": model,
                          "effort": effort}

    seen: dict[str, str] = {}
    for role, a in resolved.items():
        if not SLUG_RE.match(a["name"]):
            rep.error(f"agent {role}: invalid name {a['name']!r} (must start with a letter)")
        elif a["name"] in RESERVED_NAMES:
            rep.error(f"agent {role}: name {a['name']!r} is reserved by the CLI")
        elif a["name"] in seen:
            rep.error(f"agents {seen[a['name']]} and {role} have the same name {a['name']!r}")
        seen.setdefault(a["name"], role)
    return resolved


def deep_merge(base: dict, over: dict) -> dict:
    """`over` on top of `base`: tables merge, the rest (values and lists) replaces."""
    out = dict(base)
    for key, value in over.items():
        out[key] = deep_merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def context_routing_file(ctx: dict | None) -> Path | None:
    path = ctx["dir"] / "routing.toml" if ctx else None
    return path if path and path.is_file() else None


def load_routing(rep: Report, ctx: dict | None = None) -> dict:
    """The core routing.toml with the active context's on top (only what it redefines: variants and
    rules)."""
    routing = load_toml(ROUTING_FILE) if ROUTING_FILE.exists() else {}
    if over := context_routing_file(ctx):
        routing = deep_merge(routing, load_toml(over))
    for st, action in routing.get("rules", {}).items():
        if action not in ACTIONS:
            rep.error(f"routing.toml: unknown action {action!r} in {st!r} "
                      f"(valid: {', '.join(sorted(ACTIONS))})")
    eff = routing.get("effort", {})
    if "levels" in eff:
        rep.warn("routing.toml: [effort.levels] was removed in flow v3 (no levels) and is ignored; "
                 "use [effort.variants]")
    for role, variants in eff.get("variants", {}).items():
        if role not in DEFAULT_AGENTS or role == ORCHESTRATOR:
            rep.error(f"routing.toml: [effort.variants] names an unknown role {role!r}")
            continue
        if not isinstance(variants, list):
            rep.error(f"routing.toml: [effort.variants.{role}] must be a list ([[effort.variants.{role}]])")
            continue
        for v in variants:
            if not v.get("when"):
                rep.error(f"routing.toml: variant of {role} without `when` (the reason that allows using it)")
            if v.get("effort") and v["effort"] not in EFFORTS:
                rep.error(f"routing.toml: variant of {role}: invalid effort {v['effort']!r}")
    return routing


def attach_variants(resolved: dict, routing: dict, catalog: dict, rep: Report) -> None:
    """Resolves, per role, the variants (`a["variants"]`: name → model, effort and when to use): the agent's default
    and the exceptions in [effort.variants.<role>] (another effort and, sometimes, another model). The default keeps
    the base name; another effort becomes `<name>-<effort>` and another model `<name>-<alias>-<effort>` (Claude pins
    model and effort in the subagent file)."""
    specs = routing.get("effort", {}).get("variants", {})
    for role, a in resolved.items():
        if role == ORCHESTRATOR:
            continue
        base = a["model"]
        base_effort = a["effort"] if base.get("efforts") else ""
        variants: dict[str, dict] = {a["name"]: {"model": base, "effort": base_effort, "when": ""}}
        for spec in specs.get(role, []) if isinstance(specs.get(role), list) else []:
            model = base
            if key := spec.get("model"):
                if key not in catalog:
                    rep.error(f"routing.toml: variant of {role}: model {key!r} does not exist in config/models.toml")
                    continue
                eq = equivalent_model(catalog, key, base["provider"])  # from another provider: the equivalent
                model = {**catalog[eq], "key": eq} if eq else base
            effort = (spec.get("effort") or base_effort) if model.get("efforts") else ""
            if effort and effort not in model["efforts"]:
                rep.error(f"routing.toml: variant of {role}: {model['name']} does not accept effort {effort!r}")
                continue
            if model["key"] == base["key"] and effort == base_effort:
                name = a["name"]
            elif model["key"] == base["key"]:
                name = f"{a['name']}-{effort}"
            else:
                name = "-".join(x for x in (a["name"], model.get("alias") or model["key"], effort) if x)
            variants.setdefault(name, {"model": model, "effort": effort, "when": spec.get("when", "")})
        a["variants"] = variants


def variant_name(a: dict, model: dict, effort: str) -> str:
    for name, v in a.get("variants", {}).items():
        if v["model"]["key"] == model["key"] and v["effort"] == effort:
            return name
    return a["name"]


def model_tag(m: dict) -> str:
    """How the model appears to the user: the family without version (`label`); `model_id` is what goes to the CLI."""
    return m.get("label") or m["model_id"]


def model_label(a: dict, effort: str | None = None) -> str:
    effort = a["effort"] if effort is None else effort
    e = f", effort {effort}" if effort and a["model"].get("efforts") else ""
    return f"{a['model']['name']} (`{model_tag(a['model'])}`{e})"


def header(a: dict, effort: str) -> str:
    e = f" {effort.capitalize()}" if effort and a["model"].get("efforts") else ""
    return f"## {a['display']} - {model_tag(a['model'])}{e}"


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
    answer = ask(f"{prompt} (y/n)", "y" if default else "n").lower()
    return answer in ("s", "sim", "y", "yes")


def choose(prompt: str, options: list[tuple[str, str]], current: str) -> str:
    print(prompt)
    keys = [k for k, _ in options]
    for i, (key, label) in enumerate(options, 1):
        mark = "  <- current" if key == current else ""
        print(f"  {i}) {label}{mark}")
    default = str(keys.index(current) + 1) if current in keys else "1"
    while True:
        answer = ask("  Choose", default)
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return keys[int(answer) - 1]
        if answer in keys:
            return answer
        print("  Invalid option.")


def split_answer(answer: str, sep: str = ",") -> list[str]:
    return [s.strip().strip("\"'") for s in answer.split(sep) if s.strip() and s.strip() != "-"]


def normalize_dir(path: str) -> str:
    p = os.path.expanduser(path).replace("\\", "/").rstrip("/")
    return p + "/" if re.fullmatch(r"[A-Za-z]:", p) else p


def ask_project_dirs(cfg: dict, step: str) -> None:
    print(f"{step} Your projects' folders — open to the orchestrator and every agent.")
    current = cfg["workspace"]["project_dirs"]
    answer = ask("  Paths separated by ';' ('-' = none)", "; ".join(current) or "-")
    dirs = []
    for raw in split_answer(answer, ";"):
        p = normalize_dir(raw)
        if Path(p).is_dir() or confirm(f"  {p} does not exist. Keep it anyway?", False):
            dirs.append(p)
    cfg["workspace"]["project_dirs"] = list(dict.fromkeys(dirs))


def ask_mcp(cfg: dict, step: str) -> None:
    catalog = load_mcp_catalog()
    print(f"{step} MCP servers (the orchestrator decides when each one is used):")
    for key, s in catalog.items():
        mark = "x" if key in cfg["mcp"]["enabled"] else " "
        print(f"  [{mark}] {key:<16} {s['use_when'][:70]}…")
    while True:
        answer = ask("  Which to enable? (comma, '-' = none)", ",".join(cfg["mcp"]["enabled"]) or "-")
        chosen = split_answer(answer)
        unknown = [c for c in chosen if c not in catalog]
        if not unknown:
            break
        print(f"  Unknown: {', '.join(unknown)}. Options: {', '.join(catalog)}")
    cfg["mcp"]["enabled"] = chosen


def ask_new_context(language: str = DEFAULT_LANGUAGE) -> str:
    while True:
        name = ask("  Name of the new context (lowercase, digits and hyphen)").lower()
        if not SLUG_RE.match(name):
            print("  Invalid name.")
        elif (CONTEXTS_DIR / name).exists():
            print(f"  contexts/{name}/ already exists.")
        else:
            break
    description = ask("  Description (e.g. Company X — Squad Y)", name)
    required_env = split_answer(ask("  Required environment variables (comma, '-' = none)", "-"))
    required_mcp = split_answer(ask("  Required MCP servers (comma, '-' = none)", "-"))
    d = create_context(name, description, required_mcp, required_env, language=language)
    print(f"  Created {rel(d)}/ with its own Git repository. Write the rules in it later.")
    return name


def ask_context(cfg: dict, step: str) -> None:
    contexts = list_contexts()
    current = cfg["context"]["active"]
    if current and current not in contexts:
        print(f"  The configured context {current!r} does not exist on this machine (contexts/{current}/).")
        print(f"  To use it, cancel (Ctrl+C), clone its repository into contexts/{current}/ and "
              "run setup again.")
        current = ""
    options = ([("", "none — only AiDW's generic rules")] + [(c, c) for c in contexts]
               + [("+", "create a new context now")])
    prefix = f"{step} " if step else ""
    choice = choose(f"{prefix}Work context (rules in contexts/<name>/):", options, current)
    cfg["context"]["active"] = ask_new_context(ui_language(cfg)) if choice == "+" else choice


def installed_providers() -> list[str]:
    return [p for p in PROVIDERS if shutil.which(p)]


def wizard(cfg: dict, catalog: dict) -> dict:
    heading("AiDW · configuration")
    print("Enter keeps the current value. Everything can be changed later in aidw.config.toml.\n")

    installed = installed_providers()
    options = [(p, f"{PROVIDER_LABEL[p]}{'  — limited to agents and skills' if p == 'codex' else '  — recommended'}"
                   f"{'' if p in installed else '  (CLI not installed)'}")
               for p in PROVIDERS]
    previous = cfg["provider"]["name"]
    provider = choose("1/7 Which provider runs the orchestrator and every agent?", options, previous)
    cfg["provider"]["name"] = provider
    if provider != previous:  # the other provider's models do not apply
        for a in cfg["agents"].values():
            a.pop("model", None)
    cfg["delegation"]["mode"] = choose("\n   How does the orchestrator call the agents?", [
        ("native", "native   — the provider's native subagents (Agent on Claude, spawn_agent on Codex)"),
        ("headless", "headless — one CLI process per task (aidw.py delegate)"),
    ], cfg["delegation"]["mode"])

    print("\n2/7 Default model and effort of each agent (the orchestrator adjusts the effort per task):")
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
            a["effort"] = choose("     default effort:", [(e, e) for e in efforts], cur)

    print()
    optional = [n for n in cfg["agents"] if n != ORCHESTRATOR]
    disabled = [n for n in optional if not cfg["agents"][n].get("enabled", True)]
    print(f"3/7 Optional agents: {', '.join(optional)}")
    answer = ask("  Which to disable? (comma, '-' = none)", ",".join(disabled) or "-")
    chosen_off = {s.strip() for s in answer.split(",") if s.strip() and s.strip() != "-"}
    for n in chosen_off - set(optional):
        print(f"  Ignoring unknown agent: {n}")
    for n in optional:
        cfg["agents"][n]["enabled"] = n not in chosen_off

    names = ", ".join(f"{r}={agent_names(r, a)[1]}" for r, a in cfg["agents"].items())
    print(f"\n  Current names: {names}")
    if confirm("  Customize the agents' names?", False):
        print("  The name may have accents and spaces (e.g. \"José Reviewer\"); Enter keeps it.")
        for role, a in cfg["agents"].items():
            default = DEFAULT_NAMES.get(role, role)
            while True:
                name = ask(f"    {role} (default {default})", a.get("name") or default).strip()
                slug = slugify(name)
                if SLUG_RE.match(slug) and slug not in RESERVED_NAMES:
                    break
                print("    Invalid name: it must start with a letter and cannot be a name reserved by the CLI.")
            if slug == default and name.lower() == default:
                a.pop("name", None)
            else:
                a["name"] = name

    print()
    ask_project_dirs(cfg, "4/7")
    print()
    ask_mcp(cfg, "5/7")
    print()
    ask_language(cfg, "6/7")  # before the context: a context created now inherits it
    print()
    ask_context(cfg, "7/7")
    return cfg


def ask_language(cfg: dict, step: str) -> None:
    """[ui] language: the language the orchestrator chat talks to the user in (a context inherits it)."""
    current = ui_language(cfg)
    options = [("en", "English"), ("pt-BR", "Português (Brasil)"), ("other", "other — type a BCP-47 tag (e.g. es)")]
    choice = choose(f"{step} Language of the conversation with you (contexts inherit it):", options,
                    current if current in ("en", "pt-BR") else "other")
    if choice == "other":
        while True:
            tag = ask("  Language tag (BCP-47, e.g. es, fr, pt-PT)", "" if current in ("en", "pt-BR") else current)
            if LANGUAGE_TAG_RE.match(tag.strip()):
                choice = tag.strip()
                break
            print("  Invalid tag: letters, digits and hyphens, e.g. es or pt-PT.")
    cfg["ui"]["language"] = choice


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(render_config(cfg), encoding="utf-8", newline="\n")
    print(f"\nWrote {rel(CONFIG_FILE)}.")


# ---------------------------------------------------------------------------
# New context
# ---------------------------------------------------------------------------

def create_context(name: str, description: str, required_mcp: list[str], required_env: list[str],
                   language: str = DEFAULT_LANGUAGE) -> Path:
    """Creates contexts/<name>/ with the minimal structure and its own Git repository. `language` (the AiDW
    [ui] language by default) goes into context.toml: the language of the context's content and of the demand
    artifacts."""
    d = CONTEXTS_DIR / name
    for sub in ("policies", "shared", "agents", "reference", "skills", "tools", "demandas"):
        (d / sub).mkdir(parents=True, exist_ok=True)
        if sub != "agents":
            (d / sub / ".gitkeep").touch()
    mcp_blocks = []
    for server in required_mcp:
        mcp_blocks += ["", f"[mcp.{json.dumps(server)}]",
                       "# Commands shown by `doctor` when the MCP is not registered.",
                       'add = ""        # Claude: claude mcp add --scope user <name> -- <command>',
                       'add_codex = ""  # Codex:  codex mcp add <name> -- <command>']
    (d / "context.toml").write_text("\n".join([
        f"# Work context: {description}.",
        f"# {GENERATED_MARK} setup on {date.today().isoformat()}; edit freely and run "
        "`python aidw.py apply`.",
        "# File paths are relative to this folder. In strings, {{root}} is the AiDW root",
        "# and {{context}} is this folder.",
        "",
        f"name = {toml_value(name)}",
        f"description = {toml_value(description)}",
        "# Language of this context's content and of the demand artifacts (plans, reports, reviews; BCP-47 tag).",
        "# Without it, the AiDW [ui] language applies. File names are always English.",
        f"language = {toml_value(language)}",
        "",
        "# Where the demands' specs, plans and reviews live. Relative to the AiDW root.",
        f"state_dir = {toml_value(f'contexts/{name}/demandas')}",
        "",
        "# Folders allowed only with this context (the ones in [workspace] of aidw.config.toml already apply).",
        "additional_dirs = []",
        "",
        "# Checked by `doctor`: variables (presence only) and registered MCP servers.",
        f"required_env = {toml_value(required_env)}",
        f"required_mcp = {toml_value(required_mcp)}",
        "",
        "# Knowledge base: notes linked by [[links]] (Obsidian vault); conventions in conhecimento/README.md.",
        "[knowledge]",
        'dir = "conhecimento"',
        "",
        "[env]",
        "",
        "# One worktree per demand: branch `<prefix><number>-<slug>` and junctions for dependencies outside git.",
        "[worktree]",
        'branch_prefix = "feature/"',
        'link = ["packages", "node_modules"]',
        "",
        "[permissions]",
        "# Claude Code syntax. allow = no prompt · ask = always asks for OK · deny = blocked.",
        "# git_ask = git subcommands that always ask for OK.",
        "allow = []",
        "git_ask = []",
        "ask = []",
        "deny = []",
        "",
        "# What goes into each agent's instructions, besides policies/*.md (always included).",
        "[agents.orchestrator]",
        'include = ["agents/orchestrator.md"]',
        "",
        "# [agents.coder]",
        '# include = ["shared/team-guide.md", "agents/coder.md"]',
        '# skills = ["my-skill"]',
        *mcp_blocks,
    ]) + "\n", encoding="utf-8", newline="\n")
    (d / "agents" / "orchestrator.md").write_text(
        f"# Orchestrator — {description}\n\n"
        "<!-- The orchestrator's rules in this context: systems, repositories, workflow,\n"
        "     approval points. Name agents with {{agent:<role>}}, e.g. {{agent:coder}}. -->\n",
        encoding="utf-8", newline="\n")
    (d / "README.md").write_text(
        f"# Context {name}\n\n{description}.\n\n"
        f'Work rules AiDW uses when `aidw.config.toml` has `[context] active = "{name}"`. '
        "A **separate and private** Git repository; AiDW ignores this folder.\n\n"
        "After editing, run `python aidw.py apply` at the AiDW root.\n",
        encoding="utf-8", newline="\n")
    kb = d / "conhecimento"
    for tipo_dir in KB_TYPES.values():
        (kb / tipo_dir).mkdir(parents=True, exist_ok=True)
        (kb / tipo_dir / ".gitkeep").touch()
    (kb / "README.md").write_text(KB_README_TEMPLATE.read_text(encoding="utf-8").replace("{description}", description),
                                  encoding="utf-8", newline="\n")
    (d / ".obsidian").mkdir(exist_ok=True)  # the vault is the context folder: notes, policies, guides in one graph
    for fname, data in obsidian_config("conhecimento", ["demandas/"]).items():
        (d / ".obsidian" / fname).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8", newline="\n")
    (d / ".gitignore").write_text(".env\n.env.*\n/demandas/\n/.obsidian/*\n!/.obsidian/graph.json\n!/.obsidian/app.json\n",
                                  encoding="utf-8", newline="\n")
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
    """{{agent:<role>}} → agent name; {{root}}/{{context}} → paths. An unknown role is an error."""

    def __init__(self, resolved: dict, ctx: dict | None, rep: Report, ns: str = "") -> None:
        self.names = {role: ns + a["name"] for role, a in resolved.items()}
        self.ns = ns
        self.vars = path_vars(ctx["dir"] if ctx else None)
        self.rep = rep

    def render(self, text: str, source: Path) -> str:
        def repl(m: re.Match) -> str:
            role = m.group(1)
            if role not in self.names:
                self.rep.error(f"{rel(source)}: placeholder {m.group(0)} uses an unknown role "
                               f"(valid: {', '.join(self.names)})")
                return m.group(0)
            return self.names[role]
        return expand_vars(PLACEHOLDER_RE.sub(repl, text), self.vars)

    def include(self, path: Path) -> str:
        return f"<!-- source: {rel(path)} -->\n\n{self.render(read_frontmatter(path)[1].strip(), path)}"


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
            rep.error(f"MCP {key!r} enabled but it does not exist in config/mcp.toml")
            continue
        if s.get("type") == "stdio" and not s.get("command"):
            rep.error(f"config/mcp.toml: {key} (stdio) without `command`")
        elif s.get("type") == "http" and not s.get("url"):
            rep.error(f"config/mcp.toml: {key} (http) without `url`")
        elif s.get("type") not in ("stdio", "http"):
            rep.error(f"config/mcp.toml: {key} with invalid type {s.get('type')!r}")
        for role in s.get("agents", []):
            if role not in DEFAULT_AGENTS:
                rep.warn(f"config/mcp.toml: {key} names an unknown role {role!r}")
        servers[key] = s
    return servers


def runtime_lines(cfg: dict, ctx: dict | None, orchestrator: bool = False) -> list[str]:
    ctx_label = f"`{ctx['name']}` — {ctx['description']}" if ctx else "none"
    dirs = ", ".join(f"`{d}`" for d in project_dirs(cfg, ctx)) or "none configured"
    return [
        f"- Provider: **{PROVIDER_LABEL[cfg['provider']['name']]}** — every agent runs on it",
        f"- Project dirs (search here for repositories): {dirs}",
        f"- State dir: `{state_dir(ctx).as_posix()}`",
        f"- Context: {ctx_label}",
        *([f"- Knowledge base: `{kb_dir(ctx).as_posix()}` (index: `index.md`) — "
           f"`{aidw_command(True)} kb show <system|note>` prints a note with its links and backlinks; "
           f"`{aidw_command(True)} kb search <words>` finds notes"] if kb_dir(ctx) else []),
        *environment_lines(ctx),
        *([] if not orchestrator or cfg["provider"]["name"] == "codex" else
          ["- Session folders (add them to the session in the desktop app, *Workspace*): "
           + ", ".join(f"`{d.as_posix()}`" for d in session_dirs(ctx))]),
        f"- AiDW root: `{ROOT.as_posix()}`",
        *language_lines(cfg, ctx, orchestrator),
    ]


def language_lines(cfg: dict, ctx: dict | None, orchestrator: bool = False) -> list[str]:
    """The language rule of the generated prompts: the orchestrator talks in the UI language and writes the demand
    artifacts in the context's; an agent writes its reports in the context's. File names are always English."""
    ui, content = language_label(ui_language(cfg)), language_label(context_language(cfg, ctx))
    if orchestrator:
        return [f"- Language: talk to the user in {ui}. Write demand artifacts' content (plans, reports, reviews, "
                f"task files) in {content}; file names stay in English."]
    return [f"- Language: write your reports in {content}; file names stay in English."]


def context_external_steps(ctx: dict | None) -> list[dict]:
    """The outside steps the context adds ([[workflows.external_steps]]): step, name, before, who, when."""
    steps = (ctx.get("workflows", {}).get("external_steps", []) if ctx else []) or []
    return [s for s in steps if isinstance(s, dict) and s.get("step")]


def check_votes(ctx: dict | None, rep: Report) -> None:
    # the vote scale was removed: the PR review only asks "Approve the PR?" (manual, yes, no)
    if ctx and ctx.get("mods", {}).get("votes"):
        rep.warn(f"context {ctx['name']}: [[mods.votes]] is no longer used (the PR review only asks "
                 "\"Approve the PR?\": manual, yes or no); delete it from context.toml")


def check_external_steps(ctx: dict | None, rep: Report) -> None:
    seen: set[str] = set()
    for s in (ctx.get("workflows", {}).get("external_steps", []) if ctx else []) or []:
        where = f"context {ctx['name']}: [[workflows.external_steps]]"
        if not isinstance(s, dict) or not EXTERNAL_STEP_RE.match(str(s.get("step", ""))):
            rep.error(f"{where} needs `step` in UPPERCASE_WITH_UNDERSCORES (current: {s!r})")
            continue
        step = s["step"]
        if step in ACTIONS or step == "UNDERSTAND" or step in seen:
            rep.error(f"{where} {step!r} repeats a step that already exists")
        if s.get("before") not in EXTERNAL_BEFORE:
            rep.error(f"{where} {step!r}: `before` must be {', '.join(EXTERNAL_BEFORE)} (current: {s.get('before')!r})")
        for key in ("name", "when"):
            if not str(s.get(key, "")).strip():
                rep.error(f"{where} {step!r} without `{key}`")
        seen.add(step)


def workflows_section(ctx: dict | None) -> str:
    rows = ["## Workflows", "",
            "Each file lists the steps of one kind of demand (`agent:` is the role; map it with the Team table).", "",
            "| Workflow | File | Use for |", "|---|---|---|"]
    for name, f in workflow_files(ctx).items():
        desc = re.search(r"^description:\s*(.+)$", f.read_text(encoding="utf-8"), re.M)
        rows.append(f"| `{name}` | `{f.as_posix()}` | {desc.group(1).strip() if desc else ''} |")
    wf = ctx.get("workflows", {}) if ctx else {}
    if wf.get("by_type"):
        rows += ["", "Card type → workflow (active context):", "",
                 *[f"- {kind} → `{name}`" for kind, name in wf["by_type"].items()]]
    if wf.get("notes"):
        rows += ["", *[f"- {n}" for n in wf["notes"]]]
    if extra := context_external_steps(ctx):
        rows += ["", "Outside steps of the active context (handled like `CODE_REVIEW`/`QA_TEST`: only the user moves a "
                 "demand into or out of them). When the plan says a demand goes through one, record it with "
                 "`demand set <id> --extra-step <STEP>` so the panel shows it:", ""]
        rows += [f"- `{s['step']}` — {s['name']}, before `{s['before']}`: {s['when']}" for s in extra]
    return "\n".join(rows)


def systems_section(ctx: dict | None, detailed: bool) -> str:
    systems = ctx.get("systems", {}) if ctx else {}
    if not systems:
        return ""
    base = kb_dir(ctx)
    intro = ("Where each system lives and how to validate it. Use these commands as given; do not "
             "search for other build tools. `<repo>` is the demand's worktree (the repo itself only when there is "
             "none). *Depends on*: when a change consumes one of these, inspect its contract (endpoints, enums, "
             "events) in that repo before planning.")
    if base:
        intro += (" *Knowledge*: the system's note in the knowledge base — what earlier demands learned "
                  "(architecture, contracts, traps, decisions). Read it before exploring or changing that system "
                  "and follow its `[[links]]` only as far as the task needs; when the code disagrees, trust the code "
                  "and report the difference. A note describes how the code **is**, legacy deviations included — a "
                  "fact, not a rule: which pattern new code follows is decided by the team's guidelines and the "
                  "policies, never by a note alone.")
    if not detailed:
        # The orchestrator only locates the system and its note: build, test and stack go in the plan's deliveries
        # (the planner and the coder get the detailed section). One line per system, to keep its prompt short.
        rows = ["## Systems", "",
                "Where each system lives (`id` is the key the agents and the knowledge base use). The build and test "
                "commands are in the agents' definitions and in each delivery of the plan; *Depends on* is the system "
                "whose contract a change must inspect.", "",
                "| System | Repos | Depends on | Knowledge |", "|---|---|---|---|"]
        for key, s in systems.items():
            note = base / KB_TYPES["sistema"] / f"{key}.md" if base else None
            rows.append(f"| {s.get('name', key)} (`{key}`) | {', '.join(f'`{r}`' for r in s.get('repos', []))} | "
                        f"{', '.join(f'`{d}`' for d in s.get('depends_on', [])) or '—'} | "
                        f"{f'`{note.as_posix()}`' if note and note.is_file() else '—'} |")
        return "\n".join(rows)
    lines = ["## Systems", "", intro, ""]
    for key, s in systems.items():
        lines.append(f"### {s.get('name', key)} (`{key}`)")
        if s.get("repos"):
            lines.append(f"- Repos: {', '.join(f'`{r}`' for r in s['repos'])}")
        note = base / KB_TYPES["sistema"] / f"{key}.md" if base else None
        if note and note.is_file():
            lines.append(f"- Knowledge: `{note.as_posix()}`")
        if s.get("stack"):
            lines.append(f"- Stack: {s['stack']}")
        if s.get("depends_on"):
            deps = ", ".join(f"`{d}`" for d in s["depends_on"])
            lines.append(f"- Depends on: {deps}")
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


def final_message_reminder(body: str) -> str:
    """Closing of the definition: the output JSON sits hundreds of lines before the end (policies, context) and the
    smaller model forgets the format; repeating it at the end, with the role's states, holds the last message
    (smoke test of 2026-11-04)."""
    m = re.search(r'"state":\s*"([^"]+)"', body)
    states = ", ".join(f"`{s.strip()}`" for s in m.group(1).split("|")) if m else ""
    which = f", with `state` one of {states}" if states else ", with its `state`"
    return ("# FINAL MESSAGE\n\nEnd with the JSON block of your OUTPUT and nothing else — no text before or after "
            f"it{which}. A final message without that JSON is a failed run.")


def render_agent(role: str, a: dict, cfg: dict, ctx: dict | None, tpl: Templater, servers: dict,
                 skills: dict, routing: dict, ns: str = "") -> tuple[dict, str]:
    """(frontmatter, markdown) of the agent's definition — the same for Claude and Codex."""
    source = AGENTS_DIR / role / "AGENT.md"
    meta, body = read_frontmatter(source)
    provider = cfg["provider"]["name"]
    orch = tpl.names[ORCHESTRATOR]
    sources = [source, *policy_files(ctx), *context_files(ctx, role)]
    cmd = "install" if ns else "apply"
    parts = [
        f"<!-- {GENERATED_MARK} {cmd} from: {', '.join(rel(s) for s in sources)}.\n"
        f"     Do not edit: change the sources and run `python aidw.py {cmd}`. -->",
        tpl.render(body.strip(), source),
        "\n".join(["## Runtime", "",
                   f"- You are `{a['name']}` — {a['display']} (role `{role}`), a sub-agent of "
                   f"`{orch}`: one task per run, and you cannot talk to the user. Questions and approvals "
                   "go back to the orchestrator in your final JSON.",
                   f"- Model: {a['model']['name']} (`{model_tag(a['model'])}`). The orchestrator chose "
                   "the effort of this task.",
                   "- Max retries: 3 attempts at the same failing step (a build, a test); then stop and report "
                   "the failure `state` of your OUTPUT",
                   "- Your final message is the JSON block of your OUTPUT and nothing else: the orchestrator "
                   "only receives that; the details go in the report or the files the JSON names.",
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
    parts.append(final_message_reminder(body))
    description = tpl.render(meta.get("description", a["display"]), source)
    return {**meta, "description": description}, "\n\n".join(parts) + "\n"


def claude_agent_entry(role: str, meta: dict, prompt: str, ctx: dict | None, servers: dict,
                       preload: list[str] | None = None) -> dict:
    entry: dict = {"description": meta["description"], "prompt": prompt}
    if preload:
        entry["skills"] = list(preload)  # --agents accepts the same field as the frontmatter
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


def agent_tool_policy(role: str, meta: dict, prompt: str, ctx: dict | None, servers: dict) -> dict:
    """MCPs the agent may use (None = no list: all) and blocked MCP tools. Claude enforces this through the
    subagent's `tools`/`disallowedTools` and the guard (hook of the `aidw` plugin) checks again. On Codex there is
    no per-agent MCP limit nor guard: the install there is agents and skills only (docs/claude-and-codex.md)."""
    entry = claude_agent_entry(role, meta, prompt, ctx, servers)
    mcp = sorted({t[5:].split("__")[0] for t in entry.get("tools", []) if t.startswith("mcp__")})
    return {"mcp": mcp if entry.get("tools") else None,
            "deny_tools": [t for t in entry.get("disallowedTools", []) if t.startswith("mcp__")]}


def effort_table(resolved: dict, routing: dict, cfg: dict, ns: str = "") -> str:
    """*Agents and effort*: each agent's default and the only allowed exceptions, with the reason for each."""
    roles = [r for r, a in resolved.items() if r != ORCHESTRATOR and a["enabled"]]
    if not roles:
        return ""
    native = cfg["delegation"]["mode"] == "native"

    def cell(a: dict, name: str, v: dict) -> str:
        if native:
            return f"`{ns}{name}`"
        e = v["effort"] or "—"
        return e if v["model"]["key"] == a["model"]["key"] else f"{e} + model `{v['model']['key']}` (`{model_tag(v['model'])}`)"

    rows = ["| Agent | Default | Exceptions (only for the reason given) |", "|---|---|---|"]
    for r in roles:
        a = resolved[r]
        items = list(a.get("variants", {}).items())
        default = (f"`{ns}{a['name']}` — " if native else "") + model_label(a)
        others = "; ".join(f"{cell(a, n, v)} — {v['when']}" for n, v in items[1:]) or "—"
        rows.append(f"| `{ns}{a['name']}` | {default} | {others} |")
    if native:
        kind = "the `subagent_type` to use" if cfg["provider"]["name"] == "claude" else "the agent (role) to spawn"
        intro = (f"Each cell is {kind}: the agent's model with that effort already pinned in its definition (a "
                 "model in the name means another model, e.g. `explorer-sonnet-medium`).")
    else:
        intro = ("Each cell is the effort to pass (`—` = the model takes no effort: omit it); a cell with `+ model` "
                 "also names the model to pass.")
    return "\n".join([
        "## Agents and effort", "",
        "There are no demand levels: every task runs on the agent's default. " + intro, "",
        *rows, "",
        "Use an exception only for the reason in its cell, and say which one in the delegation. Each agent runs "
        "**once per step**: a new round needs a named reason (the user's adjustment, a finding kept, a test that "
        "failed, a result that made no sense). Another model only through an exception of this table or when the user "
        "asks."])


def variant_cells(resolved: dict) -> dict[str, list[str]]:
    """{agent name: [allowed subagent_types, without namespace]}: the default and the exceptions of the *Agents and
    effort* table, for whoever needs it as data (the delegation-lock mod)."""
    return {a["name"]: list(a.get("variants", {}) or [a["name"]])
            for r, a in resolved.items() if r != ORCHESTRATOR and a["enabled"]}


def aidw_command(global_mode: bool) -> str:
    """How to call aidw.py: relative in project mode (the chat is at the root), absolute in the plugin."""
    return f'python "{ROOT.as_posix()}/aidw.py"' if global_mode else "python aidw.py"


def explore_line(resolved: dict, fallback: str = "the built-in `Explore` subagent (read-only), "
                 "asking for `file:line` pointers") -> str:
    ex = resolved.get(EXPLORER)
    if not ex or not ex["enabled"]:
        return f"- Code exploration: {fallback}."
    return (f"- Code exploration: the `{ex['name']}` agent (*Agents and effort*), not this chat and "
            "not a generic "
            "explorer — it knows *Systems* and the policies, writes `exploration-<topic>.md` in the demand folder "
            "(the plan and the tickets reuse it) and answers numbered questions with `file:line`. Ask only what the "
            "next step needs; one exploration per topic, reused, not repeated.")


def record_hint(codex: bool, global_mode: bool = False) -> str:
    usage = ("--codex-task <task_name>" if codex else
             "--tokens <subagent_tokens> --tool-uses <tool_uses> --duration-ms <duration_ms>")
    return (f"{aidw_command(global_mode)} record --agent <name> [--effort <effort>] --label <label> "
            f"--demand <demand dir> --state <state> {usage}")


def delegation_section(cfg: dict, resolved: dict, global_mode: bool = False) -> str:
    provider, mode = cfg["provider"]["name"], cfg["delegation"]["mode"]
    agents = [a for r, a in resolved.items() if r != ORCHESTRATOR and a["enabled"]]
    example = agents[0]["name"] if agents else "coder"
    if mode == "headless":
        return headless_delegation_section(provider, example)
    if provider == "claude":
        lines = [
            "## How to delegate", "",
            "The agents are **native Claude Code subagents**: call them with the `Agent` tool.", "",
            "- `subagent_type`: the agent's default from *Agents and effort*, or one of its exceptions when its "
            "reason applies — each one has its model and effort pinned. That is how you choose the effort.",
            "- Do **not** pass `model`: it would override the agent's model. Only when the user asked "
            "for another model.",
            "- `prompt`: `Task: <task file>. Demand folder: <demand dir>.` plus the MCP "
            "choice (see *MCP tools*).",
            "- Parallel tickets: several `Agent` calls in the same message, or `run_in_background`.",
            "- After **every** subagent returns, record it — this appends `metrics.md` and prints the "
            "`header` and `summary` you must show (*SHOWING RESULTS*):",
            "", "```", record_hint(codex=False, global_mode=global_mode), "```", "",
            "  `--agent` is the `subagent_type` you used (the effort comes from it); the numbers are the "
            "ones in the Agent result (`subagent_tokens`, `tool_uses`, `duration_ms`). Never estimate.",
            "- With the `aidw-mods` plugin loaded (Claude Code only, on in orchestrator mode; docs/mods.md):",
            "  - The record is automatic: the Agent result (or, for a background agent, a note when it finishes) "
            "carries `AiDW: delegation recorded…` with the `header` and `summary` to show. Then do **not** run "
            "`record` for it; run it yourself only when that line is missing or says the mod could not record.",
            "  - An Agent call that breaks the delegation rules (a `subagent_type` outside *Agents and effort*, "
            "`model` the user did not ask for, missing task/folder, a pasted input) comes back denied with "
            "`AiDW (delegation lock)` and the reason: fix the call, never work around it.",
            "  - The AiDW panels (`/panel`, `/metrics`, `/review-tests`) only show the demand: every decision "
            "(findings, manual steps, what to publish, PR approval, doubts) is asked and answered in chat.",
            explore_line(resolved),
        ]
        return "\n".join(lines)
    if global_mode:
        return "\n".join([
            "## How to delegate", "",
            "The agents are **native Codex sub-agents** installed as roles (`~/.codex/agents/aidw-*.toml`): spawn "
            "them with `spawn_agent`.", "",
            "- `agent_type`: the agent's default from *Agents and effort* (e.g. `aidw-coder`), or one of its "
            "exceptions when its reason applies (e.g. `aidw-coder-medium`) — each role carries the agent's standing "
            "instructions with its model and effort pinned. That is how you choose the effort: never pass `model` "
            "or `reasoning_effort` (another model only when the user asks for it).",
            "- `fork_turns: \"none\"` (a full-history fork rejects `agent_type`).",
            "- `task_name`: `<agent>-<label>` (e.g. `aidw-coder-t1-r1`), unique in the demand.",
            "- `message`: `Task: <task file>. Demand folder: <demand dir>. Worktree: <path>. Finish with the JSON "
            "of your OUTPUT section.` plus the MCP choice.",
            "- Sub-agents inherit your sandbox, rules and MCP servers. The writable folders are this session's folder "
            "and its `--add-dir` folders (`python aidw.py open --provider codex --demand <id>` opens the session in the "
            "demand's worktree and adds the AiDW root); writing anywhere else asks for the sandbox's approval. Only "
            "the agents allowed to edit code may edit it (their definition says so).",
            "- Wait for the sub-agent to finish. Then record it — this reads the real token usage of the sub-agent "
            "session, appends `metrics.md` and prints the `header` and `summary` you must show:",
            "", "```", record_hint(codex=True, global_mode=True), "```", "",
            explore_line(resolved, fallback=f"spawn `{CODEX_NS}{example}` (its lowest-effort exception, if any) "
                         "asking for `file:line` pointers, or read short excerpts yourself"),
        ])
    lines = [
        "## How to delegate", "",
        "The agents are **native Codex sub-agents**: spawn them with `spawn_agent` (multi-agent).", "",
        "- `task_name`: `<agent>-<label>` (e.g. `coder-t1-r1`), unique in the demand.",
        "- Agent type/role: the agent's default from *Agents and effort*, or one of its exceptions when its reason "
        "applies — each role in `.codex/agents/` has its model and effort pinned. That is how you choose the "
        "effort: never pass `model` or `reasoning_effort` (another model only when the user asks for it).",
        "- `message` (always this shape): `You are the AiDW agent <name>. Your standing instructions are "
        "in <definition file> — read that file first and follow it; ignore the orchestrator instructions "
        "(AGENTS.md) you may have inherited. Task: <task file>. Demand folder: <demand dir>. Finish "
        "with the JSON of your OUTPUT section.` plus the MCP choice.",
        "- If your spawn tool takes an agent type/role, pass that name (the cell of *Agents and effort*); "
        "the definition file is the base agent's, the same for its exceptions.",
        "- Sub-agents inherit your sandbox, rules and MCP servers: the task must say which MCP to use, and "
        "only the agents allowed to edit code may edit it (their definition says so).",
        "- Wait for the sub-agent to finish. Then record it — this reads the real token usage of the "
        "sub-agent session, appends `metrics.md` and prints the `header` and `summary` you must show:",
        "", "```", record_hint(codex=True, global_mode=global_mode), "```", "",
        f"- There is no exploration role: for broad code exploration spawn `{example}` (its lowest-effort exception, if any) "
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
        "--task <task.md> --demand <demand dir> [--label <step>-r<N>]",
        "```",
        "",
        f"- `--agent`: the agent name from the Team table (e.g. `{example}`) or its role.",
        "- `--effort`: the agent's default in *Agents and effort*, or an exception when its reason applies. Omit "
        "it only for models marked `—`.",
        "- `--model <key>`: only for an exception whose cell names a model, or when the user asked for another "
        "model for this task.",
        "- The command prints one JSON line: `header`, `summary`, `state`, `output` (the agent's final "
        "JSON), `result_file`, `denials`, tokens and duration. The full answer is in `result_file` — read "
        "it only when needed. The same JSON is saved next to it (`resultado-<agent>-<label>.json`): if you "
        "lost the command output, read it from there.",
        "- Usage is appended to `metrics.md` in the demand folder automatically; never estimate it.",
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
            f"`{example}` with its lowest effort asking for `file:line` pointers, or read short excerpts yourself.",
            "- Your own skills: see the *Skills* section — read each `SKILL.md` and follow it when the "
            "workflow or a trigger says to use it.",
        ]
    return "\n".join(lines)


CODEX_SUBAGENT_GUARD = (
    "> **Sub-agents:** if you were spawned by the orchestrator and told that your standing instructions "
    "are in `.aidw/agents/<name>.md`, you are **not** the orchestrator: ignore this entire file and follow "
    "only that definition.")


def orchestrator_references(ctx: dict | None, tpl: Templater) -> dict[str, dict]:
    """{name: {when, source, content}}: the generic ones (orchestrator/reference, `when` in the frontmatter) and
    the context's ([agents.orchestrator] reference). Read only at the step that needs them, outside CLAUDE.md."""
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
            tpl.rep.error(f"duplicate orchestrator reference name {path.stem!r}: {rel(refs[path.stem]['source'])} "
                          f"and {rel(path)} (rename one of them)")
            continue
        body = tpl.render(read_frontmatter(path)[1].strip(), path)
        header = (f"<!-- {GENERATED_MARK} {cmd} from {rel(path)}; do not edit: change the source and run "
                  f"`python aidw.py {cmd}`. -->")
        refs[path.stem] = {"when": when, "source": path, "body": body, "content": header + "\n\n" + body + "\n"}
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
                        ref_dir: Path = GEN_REF_DIR, survey: bool = False) -> str:
    """The CLAUDE.md/AGENTS.md (and the go skill); with `survey`, the lean prompt of the survey skill: only the
    explorer, no workflows, with the procedure and the estimation scale inline (nothing to read on demand)."""
    orch = resolved[ORCHESTRATOR]
    refs = refs or {}
    if survey:
        resolved = {r: a for r, a in resolved.items() if r in (ORCHESTRATOR, "explorer")}
        servers = {k: v for k, v in servers.items() if not v.get("agents") or "explorer" in v["agents"]}
        policies = set(policy_files(ctx))
        inline = [refs[n]["body"] for n in SURVEY_REFS if n in refs]
        listed = {n: r for n, r in refs.items() if r["source"] in policies}
    else:
        inline, listed = [], refs
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
                    f"(`{model_tag(a['model'])}`) | {eff} |" + (f" {definition} |" if with_definition else "")
                    + f" {status} |")
    source_file = "CLAUDE.md" if provider == "claude" else "AGENTS.md"
    cmd = "install" if ns else "apply"
    parts = [
        f"<!-- {GENERATED_MARK} {cmd} — "
        f"{('skill survey' if survey else 'skill go') if ns else source_file + ' (orchestrator)'}; "
        f"do not edit. Sources: orchestrator/{SURVEY_MD.name if survey else ORCHESTRATOR_MD.name}, "
        "orchestrator/policies/ and the active context; run "
        f"`python aidw.py {cmd}` after changing them. -->",
        CODEX_SUBAGENT_GUARD if codex_native else "",
        tpl.include(SURVEY_MD if survey else ORCHESTRATOR_MD),
        *inline,
        "\n".join(["## Runtime", "",
                   f"- You are `{orch['name']}` — {orch['display']} (role `orchestrator`), the main chat.",
                   (f"- Your model: the one selected in this chat (recommended: {model_label(orch)})"
                    if provider == "claude" else f"- Your model: {model_label(orch)}"),
                   f"- Delegation mode: **{mode}**",
                   *runtime_lines(cfg, ctx, orchestrator=True),
                   *([f"- This chat may be in any folder: run the AiDW commands by absolute path "
                      f"(`{aidw_command(True)} ...`)."] if ns else [])]),
        "\n".join(["## Team", "", *team]),
        delegation_section(cfg, resolved, global_mode=bool(ns)),
        effort_table(resolved, routing, cfg, ns),
        "" if survey else workflows_section(ctx),
        skills_section(orch["skills"], skills, provider, ns=ns),
        mcp_orchestrator_section(servers, resolved),
        systems_section(ctx, detailed=False),
        orchestrator_reference_section(listed, ref_dir),
        "# Policies",
        *[tpl.include(p) for p in policy_files(ctx) if p not in {r["source"] for r in refs.values()}],
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
    # Variants: one-line description. The orchestrator picks them from the Agents and effort table, and the list
    # of agents with their descriptions goes into every session (the full description stays only on the base agent).
    if model["key"] != a["model"]["key"]:
        description = (f"{a['display']} with {model['name']}, effort {effort or '—'}: same role as "
                       f"{ns}{a['name']}. Only for the exception in the Agents and effort table.")
        prompt = prompt.replace(f"- Model: {a['model']['name']} (`{model_tag(a['model'])}`).",
                                f"- Model: {model['name']} (`{model_tag(model)}`).")
    elif name != a["name"]:
        description = (f"{a['display']}, effort {effort}: same role as {ns}{a['name']}. "
                       "Only for the exception in the Agents and effort table.")
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


def render_codex_role(a: dict, meta: dict, prompt: str, name: str = "", model: dict | None = None,
                      effort: str | None = None, ns: str = "") -> str:
    """Native Codex role (.codex/agents/<name>.toml), with the model and effort pinned. One per variant (the
    default and each exception of [effort.variants], like Claude's subagents): the orchestrator spawns the role by
    name and never passes `model`/`reasoning_effort`."""
    name = name or a["name"]
    model = model or a["model"]
    effort = a["effort"] if effort is None else effort
    description = meta["description"]
    if name != a["name"]:
        guard = f"{PLUGIN_GUARD} " if description.startswith(PLUGIN_GUARD) else ""
        description = (f"{guard}{a['display']} with {model['name']}, effort {effort or '—'}: same role as "
                       f"{ns}{a['name']}. Only for the exception in the Agents and effort table.")
    lines = [f"# {GENERATED_MARK} apply — do not edit; change the sources and run `python aidw.py apply`.",
             f"name = {toml_value(ns + name)}",
             f"description = {toml_value(description)}",
             f"model = {toml_value(model['model_id'])}"]
    if effort:
        lines.append(f"model_reasoning_effort = {toml_value(effort)}")
    lines.append("developer_instructions = " + toml_value(prompt))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Permission rules
# ---------------------------------------------------------------------------

def expand_git_ask(subcommands: list[str]) -> list[str]:
    """`commit` → ask for `git commit ...` and `git -C <folder> commit ...`, in Bash and PowerShell."""
    rules = []
    for tool in ("Bash", "PowerShell"):
        for sub in subcommands:
            rules += [f"{tool}(git {sub})", f"{tool}(git {sub} *)", f"{tool}(git -C * {sub})",
                      f"{tool}(git -C * {sub} *)"]
    return rules


def delegate_allow_rules() -> list[str]:
    """The orchestrator (Claude) runs delegate without a prompt; the forms match by prefix."""
    script_posix, script_win = (ROOT / "aidw.py").as_posix(), win(ROOT / "aidw.py")
    rules = []
    for tool in ("Bash", "PowerShell"):
        for py in ("python", "py"):
            for script in dict.fromkeys(["aidw.py", script_posix, script_win]):
                rules += [f"{tool}({py} {script} {sub} *)" for sub in ("delegate", "record", "kb")]
                rules += [f"{tool}({py} {script} {sub})" for sub in ("show", "doctor")]
    return rules


def rule_to_prefix(rule: str) -> list[str] | None:
    """`Bash(git push --force *)` → ["git", "push", "--force"]; rules that are not commands → None."""
    m = re.fullmatch(r"(Bash|PowerShell)\((.+)\)", rule.strip())
    if not m:
        return None
    tokens = m.group(2).split()
    if "*" in tokens[:-1] or not tokens:  # a wildcard in the middle (git -C * commit) does not become a prefix
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
    lines = [f"# {GENERATED_MARK} apply from [policies] and the context's permissions. Do not edit.",
             "# forbidden = blocked · prompt = asks for OK (in headless agents, it becomes a refusal).", ""]
    for prefix, decision in seen.items():
        lines.append(f"prefix_rule(pattern={json.dumps(list(prefix))}, decision={json.dumps(decision)})")
    lines += ["", "# The orchestrator runs delegate without a prompt, outside the sandbox (the agent needs network)."]
    for script in dict.fromkeys(["aidw.py", (ROOT / "aidw.py").as_posix(), win(ROOT / "aidw.py")]):
        for py in ("python", "py"):
            for sub in ("delegate", "record"):
                lines.append(f"prefix_rule(pattern={json.dumps([py, script, sub])}, decision=\"allow\")")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Writing and syncing
# ---------------------------------------------------------------------------

def write_if_changed(path: Path, content: str, dry: bool, rep: Report) -> None:
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == content:
        return
    if dry:
        rep.info(f"(dry-run) {'create' if old is None else 'update'} {rel(path)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    rep.ok(f"{'created' if old is None else 'updated'} {rel(path)}")


def remove_generated(path: Path, dry: bool, rep: Report, why: str) -> None:
    if not path.exists():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    if not is_generated(text) and '"generated_by": "aidw.py' not in text:
        return
    if dry:
        rep.info(f"(dry-run) remove {rel(path)}")
    else:
        path.unlink()
        rep.ok(f"removed {rel(path)} ({why})")


def is_link(p: Path) -> bool:
    return p.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(p))


def make_link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if not IS_WINDOWS:
        os.symlink(target, link, target_is_directory=True)
        return
    try:  # junction: needs neither admin nor developer mode on Windows
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
                    rep.warn(f"{rel(entry)} is a real directory; it will not be replaced by a link")
                    desired.pop(entry.name)
                continue
            target = desired.get(entry.name)
            if target and Path(os.path.realpath(entry)) == target.resolve():
                desired.pop(entry.name)
                continue
            if dry:
                rep.info(f"(dry-run) remove link {rel(entry)}")
            else:
                remove_link(entry)
                rep.ok(f"removed link {rel(entry)}")
    for name, target in desired.items():
        if dry:
            rep.info(f"(dry-run) link {rel(folder / name)} -> {rel(target)}")
        else:
            make_link(folder / name, target)
            rep.ok(f"linked {rel(folder / name)} -> {rel(target)}")


def merge_list(existing: list, previously_managed: list, managed: list) -> list:
    kept = [x for x in existing if x not in previously_managed]
    return kept + [x for x in managed if x not in kept]


def sync_claude_settings(managed: dict, previous: dict, dry: bool, rep: Report) -> None:
    """Updates only the keys apply manages; the rest of the file is preserved."""
    try:
        data = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8")) if CLAUDE_SETTINGS.exists() else {}
    except json.JSONDecodeError:
        rep.error(f"{rel(CLAUDE_SETTINGS)} is not valid JSON; fix or delete the file")
        return
    # the orchestrator's model and effort are the chat's: AiDW no longer pins them, and removes only what it wrote
    for key in ("model", "effortLevel"):
        if previous.get(key) and data.get(key) == previous[key]:
            data.pop(key)
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
        rep.error(f"{rel(MCP_JSON)} is not valid JSON; fix or delete the file")
        return
    entries = data.setdefault("mcpServers", {})
    for key in previous:
        if key not in servers:
            entries.pop(key, None)
    for key, s in servers.items():
        entries[key] = mcp_json_entry(s)
    write_if_changed(MCP_JSON, json.dumps(data, indent=2, ensure_ascii=False) + "\n", dry, rep)


def codex_mcp_table(s: dict) -> dict:
    """A catalog server in Codex format. On Windows npx is a .cmd: it runs via cmd /c."""
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
        f"# {GENERATED_MARK} apply — project config for Codex (applies when the project is",
        "# trusted: setup offers to mark it). `python aidw.py chat` passes the same values as flags.",
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
    lines += ["", "# GIT_CONFIG_*: safe.directory for the Windows sandbox (see codex_git_env).",
              "[shell_environment_policy.set]", *[f"{k} = {toml_value(v)}" for k, v in env.items()]]
    if cfg["delegation"]["mode"] == "native":
        lines += ["", "# Native subagents: the multi-agent v2 spawn_agent accepts model and effort per call.",
                  "[features]", "multi_agent_v2 = true", "",
                  "[agents]", "max_concurrent_threads_per_session = 4"]
    for key, s in servers.items():
        lines += ["", f"[mcp_servers.{key}]"]
        lines += [f"{k} = {toml_value(v)}" for k, v in codex_mcp_table(s).items()]
    return "\n".join(lines) + "\n"


def sync_generated_dir(folder: Path, files: dict[str, str], ext: str, dry: bool, rep: Report) -> None:
    """Writes {name: content} to folder/<name><ext> and removes leftover generated files."""
    for name, content in files.items():
        write_if_changed(folder / f"{name}{ext}", content, dry, rep)
    if folder.is_dir():
        for f in folder.glob(f"*{ext}"):
            if f.stem not in files:
                remove_generated(f, dry, rep, "no longer part of the config")


def previous_runtime() -> dict:
    try:
        return json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def workflow_files(ctx: dict | None) -> dict[str, Path]:
    """Available workflows: the core ones and those in contexts/<name>/workflows/, which replace same-named ones."""
    files = {f.stem: f for f in sorted(WORKFLOWS_DIR.glob("*.yaml"))}
    if ctx and (ctx["dir"] / "workflows").is_dir():  # a context file with an old name replaces the new one
        files.update({modern_name("workflow", f.stem): f for f in sorted((ctx["dir"] / "workflows").glob("*.yaml"))})
    return dict(sorted(files.items()))


def check_workflows(resolved: dict, skills: dict, ctx: dict | None, rep: Report) -> None:
    files = workflow_files(ctx)
    check_external_steps(ctx, rep)
    check_votes(ctx, rep)
    for kind, name in (ctx.get("workflows", {}).get("by_type", {}) if ctx else {}).items():
        if name not in files:
            rep.error(f"context {ctx['name']}: [workflows.by_type] {kind!r} points to the missing workflow {name!r}")
    for wf in files.values():
        text = wf.read_text(encoding="utf-8")
        for agent in sorted(set(re.findall(r"^\s*agent:\s*([\w-]+)", text, re.M))):
            if agent not in resolved:
                rep.warn(f"{rel(wf)}: unknown agent {agent!r}")
        for skill in sorted(set(re.findall(r"^\s*skill:\s*([\w-]+)", text, re.M))):
            if skill not in skills:
                rep.warn(f"{rel(wf)}: unknown skill {skill!r}")


def build(cfg: dict, catalog: dict, rep: Report, ns: str = "", ref_dir: Path = GEN_REF_DIR) -> dict | None:
    """Validates and renders everything in memory (nothing is written)."""
    ctx = load_context(cfg, rep)
    skills = available_skills(ctx, rep)
    resolved = resolve(cfg, catalog, ctx, skills, rep)
    routing = load_routing(rep, ctx)
    if not resolved:
        return None
    attach_variants(resolved, routing, catalog, rep)
    check_workflows(resolved, skills, ctx, rep)
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
    survey_md = render_orchestrator(resolved, cfg, ctx, tpl, servers, skills, routing, refs, ns, ref_dir, survey=True)
    if rep.errors:
        return None
    return {"ctx": ctx, "skills": skills, "resolved": resolved, "routing": routing, "servers": servers,
            "agents": agents, "orchestrator_md": orchestrator_md, "survey_md": survey_md, "orchestrator_refs": refs}


def apply(cfg: dict, catalog: dict, dry: bool) -> bool:
    heading("Validating configuration" + (" (dry-run)" if dry else ""))
    rep = Report()
    b = build(cfg, catalog, rep)
    if b is None:
        print("\nFix the errors above and run again.")
        return False
    ctx, resolved, servers = b["ctx"], b["resolved"], b["servers"]
    provider, mode = cfg["provider"]["name"], cfg["delegation"]["mode"]
    rep.ok(f"valid configuration · provider {provider} · delegation {mode}"
           + (f" · context {ctx['name']}" if ctx else ""))
    prev = previous_runtime()

    heading("State")
    sdir = state_dir(ctx)
    if not sdir.is_dir():
        if dry:
            rep.info(f"(dry-run) create {rel(sdir)}/")
        else:
            sdir.mkdir(parents=True)
            rep.ok(f"created {rel(sdir)}/")

    heading("Agents (.aidw/agents)")
    files = {}
    for role, g in b["agents"].items():
        a = resolved[role]
        files[a["name"]] = g["prompt"]
        write_if_changed(GEN_AGENTS_DIR / f"{a['name']}.md", g["prompt"], dry, rep)
        eff = a["effort"] or "—"
        rep.info(f"{a['name']:<14} {role:<11} {a['model']['model_id']:<26} default effort {eff:<7} "
                 f"~{len(g['prompt']) // 4:,} tokens of instructions")
    if GEN_AGENTS_DIR.is_dir():
        for f in GEN_AGENTS_DIR.glob("*.md"):
            if f.stem not in files:
                remove_generated(f, dry, rep, "agent renamed, disabled or removed")
    refs = b["orchestrator_refs"]
    sync_generated_dir(GEN_REF_DIR, {n: r["content"] for n, r in refs.items()}, ".md", dry, rep)
    if refs:
        rep.info(f"orchestrator references (read on demand): {', '.join(refs)}")

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
                rep.info(f"subagents of {a['name']}: " + ", ".join(
                    f"{n} ({v['model'].get('alias') or v['model']['key']}, {v['effort'] or 'no effort'})"
                    for n, v in a["variants"].items()))
        sync_generated_dir(CLAUDE_SUBAGENTS, subagents, ".md", dry, rep)
        sync_generated_dir(CODEX_SUBAGENTS, {}, ".toml", dry, rep)
        sync_skill_links(CLAUDE_SKILLS, b["skills"], dry, rep)
        orch = resolved[ORCHESTRATOR]
        ctx_perms = ctx.get("permissions", {}) if ctx else {}
        managed = {
            "allow": list(dict.fromkeys([*ctx_perms.get("allow", []), *delegate_allow_rules(),
                                         *[f"mcp__{k}" for k, s in servers.items() if s.get("allow")]])),
            "enabledMcpjsonServers": list(servers),
            "ask": list(dict.fromkeys([*cfg["policies"]["ask"], *ctx_perms.get("ask", []),
                                       *expand_git_ask(ctx_perms.get("git_ask", []))])),
            "deny": list(dict.fromkeys([*cfg["policies"]["deny"], *ctx_perms.get("deny", [])])),
            "additionalDirectories": code_dirs(cfg, ctx),  # projects + worktree root
            "env": {k: str(v) for k, v in ctx.get("env", {}).items()} if ctx else {},
        }
        sync_claude_settings(managed, prev.get("claude_settings", {}), dry, rep)
        sync_mcp_json(servers, prev.get("claude_settings", {}).get("enabledMcpjsonServers", []), dry, rep)
        for path, why in ((AGENTS_MD, "claude provider"), (CODEX_CONFIG, "claude provider"),
                          (CODEX_RULES, "claude provider")):
            remove_generated(path, dry, rep, why)
        if CODEX_SKILLS.is_dir():
            sync_skill_links(CODEX_SKILLS, {}, dry, rep)
    else:
        managed = {}
        heading("Codex (AGENTS.md, .codex/, .agents/skills)")
        write_if_changed(AGENTS_MD, b["orchestrator_md"], dry, rep)
        size = len(b["orchestrator_md"].encode("utf-8"))
        if size > CODEX_DOC_MAX_BYTES:
            rep.warn(f"AGENTS.md has {size:,} bytes, above project_doc_max_bytes ({CODEX_DOC_MAX_BYTES:,}); "
                     "Codex will cut off the end")
        write_if_changed(CODEX_CONFIG, render_codex_config(resolved, cfg, ctx, servers), dry, rep)
        ctx_perms = ctx.get("permissions", {}) if ctx else {}
        git_ask = [["git", *sub.split()] for sub in ctx_perms.get("git_ask", [])]
        ask_rules = [*cfg["policies"]["ask"], *ctx_perms.get("ask", []),
                     *[f"Bash({' '.join(g)} *)" for g in git_ask]]
        deny_rules = [*cfg["policies"]["deny"], *ctx_perms.get("deny", [])]
        write_if_changed(CODEX_RULES, codex_rules(deny_rules, ask_rules), dry, rep)
        roles = ({name: render_codex_role(resolved[r], g["meta"], g["prompt"], name, v["model"], v["effort"])
                  for r, g in b["agents"].items() for name, v in resolved[r]["variants"].items()}
                 if mode == "native" else {})
        sync_generated_dir(CODEX_SUBAGENTS, roles, ".toml", dry, rep)
        sync_generated_dir(CLAUDE_SUBAGENTS, {}, ".md", dry, rep)
        sync_skill_links(CODEX_SKILLS, b["skills"], dry, rep)
        for path, why in ((CLAUDE_MD, "codex provider"), (CLAUDE_AGENTS_JSON, "codex provider")):
            remove_generated(path, dry, rep, why)
        if CLAUDE_SKILLS.is_dir():
            sync_skill_links(CLAUDE_SKILLS, {}, dry, rep)

    for key, s in servers.items():
        roles = ", ".join(s.get("agents", [])) or "all"
        extra = " · authenticate once (OAuth)" if s.get("auth") == "oauth" else ""
        rep.info(f"MCP {key:<16} {s['type']:<6} agents: {roles}{extra}")

    runtime = {
        "generated_by": "aidw.py apply",
        "root": ROOT.as_posix(),
        "provider": provider,
        "delegation": mode,
        "context": ctx["name"] if ctx else None,
        "state_dir": sdir.as_posix(),
        "agents": {role: {"name": a["name"], "display": a["display"], "enabled": a["enabled"],
                          "model": a["model"]["key"], "model_id": a["model"]["model_id"],
                          "effort": a["effort"], "skills": a["skills"], "preload": a["preload"],
                          **({"tools": agent_tool_policy(role, b["agents"][role]["meta"], b["agents"][role]["prompt"],
                                                         ctx, servers)} if role in b["agents"] else {})}
                   for role, a in resolved.items()},
        "mcp": list(servers),
        "claude_settings": managed if provider == "claude" else prev.get("claude_settings", {}),
        # for the Claude mods (delegation locks): each agent's subagent_types (Agents and effort table)
        "variants": variant_cells(resolved),
        # the mod's side panel: on, unless the context turns it off ([mods] panel = false); without the
        # files of a template, its tabs disappear
        "panel": bool(ctx.get("mods", {}).get("panel", True)) if ctx else True,
        # the context's outside steps, for the panel's progress bar
        "external_steps": [{k: s.get(k, "") for k in ("step", "name", "before", "who")}
                           for s in context_external_steps(ctx)],
    }
    write_if_changed(RUNTIME_FILE, json.dumps(runtime, indent=2, ensure_ascii=False) + "\n", dry, rep)
    print(f"\nDone{' (nothing was changed: dry-run)' if dry else ''}"
          f"{f' with {len(rep.warnings)} warning(s)' if rep.warnings else ''}. Open a new chat at the AiDW root.")
    return True


# ---------------------------------------------------------------------------
# Global install in Claude: plugin per context (aidw.py install / uninstall)
# ---------------------------------------------------------------------------

def plugin_name(ctx: dict | None = None) -> str:
    """Always `aidw`: commands and agents have the same name on any machine and context (the active context changes
    the plugin's content — rules, systems, policies —, not its name)."""
    return "aidw"


def sha(content: bytes) -> str:
    import hashlib
    return hashlib.sha256(content).hexdigest()


def is_admin_skill(path: Path) -> bool:
    return read_frontmatter(path)[0].get("aidw") == "admin"


def guard_skill(text: str) -> str:
    """Puts the AiDW notice at the start of the SKILL.md description, removes the `aidw:` mark from the frontmatter
    and resolves `{{root}}` (the skill runs in any folder and calls aidw.py by absolute path). A skill without
    `aidw: admin` is a tool for the agents and the orchestrator, not a command: it gets `user-invocable: false`
    (hidden from the `/` menu; the model still calls it through the Skill tool). The user's commands are the
    `aidw: admin` skills and the generated ones (`go`, `survey`, `exit`, `diff`)."""
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
    hidden = not admin and not any(line.startswith("user-invocable:") for line in lines[1:end])
    if hidden:
        lines.insert(end, "user-invocable: false")
    lines = [line for i, line in enumerate(lines) if not (0 < i < end and line.startswith("aidw:"))]
    return "\n".join(lines).replace("{{root}}", ROOT.as_posix())


def orchestrator_skill(plugin: str, ctx: dict | None, orchestrator_md: str, skill_path: Path,
                       provider: str = "claude", survey: bool = False) -> str:
    """`go`, or `survey`: the survey-only orchestrator (lean `orchestrator_md`)."""
    aidw = aidw_command(True)
    codex = provider == "codex"
    leave = "$aidw-exit" if codex else f"/{plugin}:exit"
    name = "survey" if survey else "go"
    request = "the text of the message that called this skill." if codex else "$ARGUMENTS"
    workspace = "" if survey else ("6. **Code:** the demand's worktree (section *Workspace*). Codex has no "
                 "`EnterWorktree`: every task takes the worktree's absolute path. `worktree create` writes to the "
                 "repository's `.git`, which the Codex sandbox leaves read-only: ask for approval (escalation) for "
                 "that command and for any write outside the session folder (in Codex, AiDW installs no profile or "
                 "rules). After creating the worktree, ask the user to reopen with "
                 f"`{aidw} open --provider codex --demand <id>`." if codex else
                 "6. **Code:** the demand's worktree (section *Workspace*); all of them live in the demand folder "
                 "(`<worktree root>/<id>/<repository>`). If the session opened in that folder or in one of its "
                 "worktrees (`demand` in `project detect`, e.g. `aidw open --demand`), stay where you are. Otherwise, "
                 "in the desktop app, `mcp__ccd_directory__change_directory` to the worktree (one repository) or the "
                 "demand folder (more than one); with no worktree (read-only, or repositories used in place, as in an "
                 "imported demand), to the demand's state folder (`<State dir>/<id>`, which every demand has); in the "
                 "terminal, `EnterWorktree` with the demand id. In the app, after moving (or when staying), "
                 "add the Runtime *Session folders* with `mcp__ccd_directory__request_directory`, once per "
                 "session, so plans and reports open in the app. The diff panel shows one repository "
                 "at a time: `/"
                 f"{plugin}:diff` switches to the next, `/{plugin}:diff <repo>` goes to one and `/{plugin}:diff exit` "
                 "returns to the demand folder.")
    description = (f"{PLUGIN_GUARD} Survey of a demand before implementing it: the AiDW orchestrator reads the "
                   "card, an explorer validates each point in the code and maps the flow, and the result is the "
                   "effort estimate, story points and complexity, with the open questions. Read-only." if survey else
                   f"{PLUGIN_GUARD} Takes over this session as the AiDW orchestrator and runs a demand "
                   "end to end: spec, tickets, agents, review and final review.")
    survey_intro = [
        "**Survey:** this call is the `survey` workflow (the procedure, the scale and the format are "
        "below: there is no reference to read). The request is the card (id or link) or the demand's text (without "
        "a card, the demand is `survey-<slug>`, a short slug of the text); with no request, ask which. Read-only: "
        "no worktree, plan or code. "
        "An existing demand: if it is in progress (has a plan), do the survey without changing its `step` or "
        "`status`; if it already has `survey-<id>.md`, redo it against the current card, reusing the exploration "
        "where nothing changed. Once done, orchestrator mode ends with it; to implement, the user calls "
        f"`{'$aidw-go' if codex else '/' + plugin + ':go'} <id>`.", ""] if survey else []
    return "\n".join([
        "---", f"name: {CODEX_NS + name if codex else name}",
        f"description: {json.dumps(description, ensure_ascii=False)}",
        *([] if codex else ["disable-model-invocation: true"]), "---", "",
        f"<!-- {GENERATED_MARK} install; do not edit: change the sources and run `python aidw.py install`. -->", "",
        "# AiDW survey" if survey else "# AiDW orchestrator mode", "",
        f"From this message on you are the AiDW orchestrator in this session, until the user calls "
        f"`{leave}`, closes the task with `{'$aidw-done' if codex else '/' + plugin + ':done'}` or asks to stop. "
        "User request (may be empty): " + request, "",
        *survey_intro,
        f"After a conversation compaction, reread `{skill_path.as_posix()}` before continuing.", "",
        "## When called: open or resume the demand", "",
        f"1. Run `{aidw} project detect --json` (current folder) and `{aidw} demand list --active --json`"
        + ("." if codex else
           f"; and `{aidw} session bind`, which turns on orchestrator mode in this session (status band, metrics "
           "and the mods' locks) in any client. Once the demand is chosen, `session bind --demand <id>` "
           "(`demand set` already binds the demand it writes)."),
        "2. **Which demand:** the one in the request, if it names one (e.g. `1234` → `us-1234`, `bug-5678`); "
        "otherwise the folder's (`demand`, when the chat is in a worktree); otherwise the only active one in this "
        "repository. More than one candidate, or none and no request: ask the user, with the options. **Demand "
        "without a card** (a free-form improvement, a text request): the id is `<type>-<slug>`, the conventional "
        "commits type (`feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `chore`) and a short slug of the "
        "request, e.g. `feat-panel-v5`, `fix-terminal-registry`; if it already exists, `-2`.",
        *(["3. **Resume:** if the demand already has `survey-<id>.md`, read only it and what changed on the card; "
           "what the exploration already answered does not go back to the explorer.",
           f"4. **New:** `{aidw} demand set <id> --status active --step UNDERSTAND --title \"<title>\"` and follow "
           "the steps (*STEPS*)."] if survey else [
        "3. **Resume:** if the demand already has `demand.json`, **do not start over** — read its folder (plan, "
        "triages, reviews, `state.md`) and continue from the recorded step (`step`). Exception: a demand that only "
        "had a survey (`survey-<id>.md` and no plan), called to implement: close the survey with "
        f"`{aidw} demand set <id> --step DONE` and start its workflow at `EXPLORE` (`--status active`), "
        "reusing the survey (section *Survey*).",
        f"4. **New:** `{aidw} demand set <id> --status active --step UNDERSTAND --title \"<title>\"` and follow "
        "the flow. A request to review someone else's PR (`pr <n>`, a PR link, \"review the PR\"): workflow "
        "`pr-review` (section *PR review*), with no plan or implementation. A survey or estimate request "
        "(`survey <id>`, \"estimate\", \"how many points\"): workflow `survey` (section *Survey*).",
        f"5. **At each step** (each action of *NEXT ACTION*): `{aidw} demand set <id> --step <ACTION>`; at the "
        "end, `--status done`. A read-only request (explain, analyze) does not open a demand."]),
        *([workspace] if workspace else []), "",
        orchestrator_md.strip(), "",
    ])


def exit_skill(plugin: str, provider: str = "claude", language: str = DEFAULT_LANGUAGE) -> str:
    codex = provider == "codex"
    description = f"{PLUGIN_GUARD} Ends AiDW orchestrator mode in this session."
    return "\n".join([
        "---", f"name: {CODEX_NS + 'exit' if codex else 'exit'}", f"description: {json.dumps(description, ensure_ascii=False)}",
        *([] if codex else ["disable-model-invocation: true"]), "---", "",
        "Leave AiDW orchestrator mode. If a demand is open in this session, record where it stopped: "
        f"`{aidw_command(True)} demand set <id> --status paused --note \"<next step>\"` and, if it helps, a "
        "short `state.md` in its folder. "
        + ("" if codex else f"Finally, `{aidw_command(True)} session unbind`, which takes the session out of the "
           "mode (in the terminal, the hook does not receive the slash command). ")
        + "Then answer normally, without the orchestrator rules, until "
        f"`{'$aidw-go' if codex else '/' + plugin + ':go'}` is called again (it resumes from the recorded "
        f"step). Answer the user in {language_label(language)}.", "",
    ])


def diff_skill(plugin: str, language: str = DEFAULT_LANGUAGE) -> str:
    """Claude only: the diff panel follows the session folder, and Codex has no `EnterWorktree`."""
    aidw = aidw_command(True)
    description = (f"{PLUGIN_GUARD} Switches the repository the diff panel shows, without leaving the chat or "
                   "orchestrator mode: with no argument it goes to the demand's next repository (in a cycle), with "
                   "a name it goes to that one, and `exit` returns to the demand folder. Use when the user asks to "
                   "see the diff of a demand repository.")
    return "\n".join([
        "---", "name: diff", f"description: {json.dumps(description, ensure_ascii=False)}", "---", "",
        f"<!-- {GENERATED_MARK} install; do not edit: change the sources and run `python aidw.py install`. -->", "",
        "# Diff per demand repository", "",
        "Request (may be empty): $ARGUMENTS", "",
        f"1. **Where the chat is:** `{aidw} project detect --json` in the current folder. `demand` is the demand (in "
        "the worktree or the demand folder); otherwise, this session's demand; otherwise `demand list --active "
        "--json`, and ask if there is more than one.",
        f"2. **Worktrees:** `{aidw} worktree list --json`, the `active` ones of that demand, in list order (creation "
        "order). Each has `folder` (the repository, e.g. `App.Front`), `branch`, `base` and `path`. "
        f"With none (repositories used in place, as in an imported demand): the `repos` of `{aidw} demand show "
        "<id>`, in order; `folder` is the last part of the `path`.",
        "3. **Target:**",
        "   - empty: the repository **after** the one the chat is in, wrapping to the first after the last; outside "
        "all of them (in the demand folder, for example), the first;",
        "   - `exit`: the demand folder (the parent folder of its worktrees; with no worktree, the state folder, the "
        "`folder` of `demand show`);",
        "   - a name: the `folder` that matches it, case-insensitive; a fragment works (`front`). None or "
        "more than one: list the `folder`s and ask.",
        "   With a single worktree, empty and its name both lead to it; if the chat is already there, say so and stop.",
        "4. **Change the session folder.** The Claude desktop app has the tool "
        "`mcp__ccd_directory__change_directory` (if it is deferred, load it with ToolSearch "
        "`select:mcp__ccd_directory__change_directory`): call it with `path` = the target worktree's `path`, or the "
        "demand folder for `exit`. It is what takes the diff panel along; the folder changes when this answer ends, "
        "and the user may have to approve the folder. Do not use `EnterWorktree` in the app: it changes only Claude "
        "Code's folder and the panel stays behind.",
        "5. **Without that tool (terminal):** if the session entered a worktree with `EnterWorktree`, leave with "
        "`ExitWorktree` and `action: \"keep\"`, never `remove`; it returns to the folder where the session opened. "
        "For `exit`, stop there. Then `EnterWorktree` with "
        "`name: \"<demand>/<folder>\"` (e.g. `us-123/App.Front`); the AiDW hook returns the "
        "path. Do not use `path`: Claude only accepts a worktree of the repository where the chat opened.",
        f"6. Answer in {language_label(language)}, in up to 3 lines: where the chat is now (repository and branch, or the demand folder), "
        "`git -C <path> diff --stat <base>...HEAD` summarized and the next one in the cycle (`/" + plugin + ":diff`). "
        "The diff panel shows that repository; in the demand folder it is empty. Orchestrator mode continues: the "
        "adjustments the user points out enter the flow as always (triage and a task for the agent, with the "
        "absolute path).",
        "",
    ])


def build_plugin(cfg: dict, catalog: dict, rep: Report) -> dict | None:
    """Renders the local marketplace with the `aidw` plugin (active context content): {relative path: bytes}."""
    if cfg["provider"]["name"] != "claude":
        rep.error("the plugin install is Claude's; for Codex use `install --provider codex` (agents and skills)")
        return None
    if cfg["delegation"]["mode"] != "native":
        rep.error('the global install uses native subagents: use [delegation] mode = "native" '
                  "(headless mode is still available through `apply`, at the AiDW root)")
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
                elif f.suffix == ".md":  # skill references (e.g. context/references/*.md) also use {{root}}
                    data = data.replace(b"{{root}}", ROOT.as_posix().encode("utf-8"))
                files[f"{base}/skills/{name}/{f.relative_to(src).as_posix()}"] = data
    put(f"{base}/skills/go/SKILL.md",
        orchestrator_skill(plugin, ctx, b["orchestrator_md"], plugin_dir / "skills" / "go" / "SKILL.md"))
    put(f"{base}/skills/survey/SKILL.md",
        orchestrator_skill(plugin, ctx, b["survey_md"], plugin_dir / "skills" / "survey" / "SKILL.md",
                           survey=True))
    put(f"{base}/skills/exit/SKILL.md", exit_skill(plugin, language=ui_language(cfg)))
    put(f"{base}/skills/diff/SKILL.md", diff_skill(plugin, language=ui_language(cfg)))
    for name, r in b["orchestrator_refs"].items():
        put(f"{base}/reference/{name}.md", r["content"])
    py = f'python "{ROOT.as_posix()}/aidw.py"'
    put(f"{base}/hooks/hooks.json", json.dumps({"hooks": {
        "PreToolUse": [{"matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell",
                        "hooks": [{"type": "command", "command": f'python "{GUARD_SCRIPT.as_posix()}"'}]}],
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": f'python "{GUARD_SCRIPT.as_posix()}"'}]}],
        "SessionStart": [{"matcher": "compact|resume",
                          "hooks": [{"type": "command", "command": f'python "{GUARD_SCRIPT.as_posix()}"'}]}],
        "WorktreeCreate": [{"hooks": [{"type": "command", "command": f"{py} worktree hook-create"}]}],
        "WorktreeRemove": [{"hooks": [{"type": "command", "command": f"{py} worktree hook-remove"}]}],
    }}, indent=2, ensure_ascii=False) + "\n")
    version = f"{PLUGIN_VERSION_BASE}-{sha(b''.join(k.encode() + v for k, v in sorted(files.items())))[:10]}"
    description = "AiDW — orchestrator and specialized agents"
    put(f"{base}/.claude-plugin/plugin.json", json.dumps(
        {"name": plugin, "version": version, "description": description, "author": {"name": "AiDW"}},
        indent=2, ensure_ascii=False) + "\n")
    entries = [{"name": plugin, "source": f"./{base}", "description": description}]
    mods = build_mods(files)
    if mods:
        entries.insert(0, {"name": MODS_PLUGIN, "source": f"./plugins/{MODS_PLUGIN}", "description": mods["description"]})
    put(".claude-plugin/marketplace.json", json.dumps(
        {"name": MARKETPLACE_NAME, "owner": {"name": "AiDW"},
         "description": "Plugins generated by AiDW on this machine (python aidw.py install).",
         "plugins": entries},
        indent=2, ensure_ascii=False) + "\n")
    return {"plugin": plugin, "version": version, "files": files, "ctx": ctx, "build": b, "mods": mods}


def build_mods(files: dict[str, bytes]) -> dict | None:
    """Copies the mods plugin (`mods/aidw-mods`, Claude Code only) to the marketplace: the code as is, without the
    tests, and plugin.json with a content-based version and this machine's AiDW root. None when there are no mods."""
    src = MODS_DIR / MODS_PLUGIN
    manifest_file = src / ".claude-plugin" / "plugin.json"
    if not manifest_file.is_file():
        return None
    base = f"plugins/{MODS_PLUGIN}"
    own: dict[str, bytes] = {}
    for f in sorted(src.rglob("*")):
        rel_path = f.relative_to(src).as_posix()
        if (not f.is_file() or rel_path.startswith(("tests/", ".claude-plugin/")) or "node_modules" in f.parts
                or f.name == "tsconfig.json"):
            continue
        own[f"{base}/{rel_path}"] = f.read_bytes()
    meta = json.loads(manifest_file.read_text(encoding="utf-8"))
    meta.setdefault("userConfig", {}).setdefault("aidwRoot", {"type": "string", "title": "AiDW root"})
    meta["userConfig"]["aidwRoot"]["default"] = ROOT.as_posix()
    content = b"".join(k.encode() + v for k, v in sorted(own.items())) + json.dumps(meta, sort_keys=True).encode()
    meta["version"] = f"{meta.get('version', '0.1.0')}-{sha(content)[:10]}"
    own[f"{base}/.claude-plugin/plugin.json"] = (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    files.update(own)
    return {"plugin": MODS_PLUGIN, "version": meta["version"], "description": meta.get("description", "")}


def global_managed_settings(cfg: dict, ctx: dict | None, servers: dict) -> dict:
    """What AiDW adds to ~/.claude/settings.json (layer 1 of D3 in plan v3)."""
    perms = ctx.get("permissions", {}) if ctx else {}
    # The common spellings of the same path (models vary): with/without quotes, / or \, and /c/... in Git Bash.
    posix, windows = (ROOT / "aidw.py").as_posix(), win(ROOT / "aidw.py")
    drive = re.match(r"^([A-Za-z]):/(.*)$", posix)
    gitbash = f"/{drive.group(1).lower()}/{drive.group(2)}" if drive else posix
    forms = {"Bash": list(dict.fromkeys([f'"{posix}"', posix, f'"{windows}"', gitbash])),
             "PowerShell": list(dict.fromkeys([f'"{posix}"', posix, f'"{windows}"', windows]))}
    aidw_rules = [f"{tool}(python {form} {sub})" for tool, tool_forms in forms.items() for form in tool_forms
                  for sub in ("record *", "show", "doctor", "project *", "demand *", "session *", "worktree *",
                              "context *", "kb *")]
    return {
        "allow": list(dict.fromkeys([*perms.get("allow", []), *aidw_rules,
                                     *[f"mcp__{k}" for k, s in servers.items() if s.get("allow")]])),
        "ask": list(dict.fromkeys([*cfg["policies"]["ask"], *perms.get("ask", []),
                                   *expand_git_ask(perms.get("git_ask", []))])),
        "deny": list(dict.fromkeys([*cfg["policies"]["deny"], *perms.get("deny", [])])),
        # the session may be in any folder: AiDW (demand state), the projects and the worktrees
        "additionalDirectories": list(dict.fromkeys([ROOT.as_posix(), *project_dirs(cfg, ctx),
                                                     worktree_root(cfg).as_posix()])),
        "env": {k: str(v) for k, v in ctx.get("env", {}).items()} if ctx else {},
    }


def merge_owned(existing: list, owned_before: list, managed: list) -> tuple[list, list]:
    """(final list, AiDW's items). An item the user already had stays theirs and is never removed."""
    kept = [x for x in existing if x not in owned_before]
    owned = [x for x in managed if x not in kept]
    return kept + owned, owned


def merge_user_settings(managed: dict, owned_before: dict, dry: bool, rep: Report) -> dict | None:
    """Applies to ~/.claude/settings.json only what belongs to AiDW; returns what is now AiDW's."""
    try:
        data = json.loads(USER_SETTINGS.read_text(encoding="utf-8")) if USER_SETTINGS.exists() else {}
    except json.JSONDecodeError:
        rep.error(f"{USER_SETTINGS} is not valid JSON; fix the file before installing")
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
        if k not in env:  # a value the user already set wins
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
    """{"plugin@marketplace": version} from ~/.claude/plugins/installed_plugins.json."""
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
        rep.error(f"`claude` CLI not found; could not run `{shown}`")
        return False
    proc = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=300, cwd=Path.home())
    if proc.returncode != 0:
        rep.error(f"`{shown}` failed: {(proc.stderr or proc.stdout).strip()[-300:]}")
        return False
    rep.ok(shown)
    return True


def user_mcp_servers() -> dict[str, str] | None:
    """MCP servers visible outside any project (user scope)."""
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
    heading("Global install in Claude" + (" (dry-run)" if dry else ""))
    rep = Report()
    plug = build_plugin(cfg, catalog, rep)
    if plug is None:
        print("\nFix the errors above and run again.")
        return False
    manifest = load_manifest()
    if not manifest and MARKETPLACE_DIR.is_dir():
        rep.warn(f"{rel(MARKETPLACE_DIR)} exists, but the manifest is gone: there is no way to know what was changed "
                 "by hand or which settings rules were AiDW's; check ~/.claude/settings.json")
    plugin, version, files, mods = plug["plugin"], plug["version"], plug["files"], plug["mods"]
    rep.ok(f"plugin {plugin} {version}: {sum(1 for k in files if '/agents/' in k)} agents, "
           f"{len({k.split('/')[3] for k in files if '/skills/' in k})} skills")
    if mods:
        rep.ok(f"plugin {mods['plugin']} {mods['version']}: Claude Code mods (on in orchestrator mode)")
    # `aidw` goes last: status and doctor read its version from plugins[-1]
    wanted = {**({f"{mods['plugin']}@{MARKETPLACE_NAME}": mods["version"]} if mods else {}),
              f"{plugin}@{MARKETPLACE_NAME}": version}

    heading("Local marketplace (.aidw/marketplace)")
    old_hashes = manifest.get("files", {})
    conflicts = [k for k, h in old_hashes.items()
                 if (MARKETPLACE_DIR / k).is_file() and sha((MARKETPLACE_DIR / k).read_bytes()) != h]
    if conflicts and not force:
        for k in conflicts:
            rep.error(f"{k} was changed outside AiDW; change the sources (the file is generated) or run with --force")
        return False
    for k, content in files.items():
        path = MARKETPLACE_DIR / k
        if path.is_file() and path.read_bytes() == content:
            continue
        if dry:
            rep.info(f"(dry-run) {'update' if path.exists() else 'create'} {k}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    for k in old_hashes:
        if k not in files and (MARKETPLACE_DIR / k).is_file():
            if dry:
                rep.info(f"(dry-run) remove {k}")
            else:
                (MARKETPLACE_DIR / k).unlink()
    if not dry:
        for d in sorted((x for x in MARKETPLACE_DIR.rglob("*") if x.is_dir()), key=lambda x: -len(x.parts)):
            if not any(d.iterdir()):
                d.rmdir()

    heading(f"User settings ({USER_SETTINGS})")
    owned = merge_user_settings(global_managed_settings(cfg, plug["ctx"], plug["build"]["servers"]),
                                manifest.get("settings", {}), dry, rep)
    if owned is None:
        return False
    rep.info("rules: " + ", ".join(f"{len(owned[k])} {k}" for k in ("allow", "ask", "deny")) +
             f"; allowed folders: {len(owned['additionalDirectories'])}")

    mcp_added = list(manifest.get("mcp_added", []))

    def save_manifest(cli_done: bool) -> None:
        if dry:
            return
        plugins = [*[k for k in manifest.get("plugins", []) if k not in wanted], *wanted]
        if cli_done:  # plugins from previous contexts were already uninstalled
            plugins = list(wanted)
        write_if_changed(INSTALL_MANIFEST, json.dumps({
            "generated_by": "aidw.py install", "plugin": plugin, "version": version, "plugins": plugins,
            **({"mods_version": mods["version"]} if mods else {}),
            "marketplace": MARKETPLACE_NAME, "context": plug["ctx"]["name"] if plug["ctx"] else None,
            "files": {k: sha(v) for k, v in files.items()}, "settings": owned,
            "mcp_added": sorted(set(mcp_added)), "cli": not skip_cli, "cli_done": cli_done,
            **({"codex": codex} if (codex := load_manifest().get("codex")) else {}),  # the Codex record stays
        }, indent=2, ensure_ascii=False) + "\n", dry, Report(quiet=True))

    save_manifest(cli_done=skip_cli)
    if not skip_cli:
        heading("Claude Code (plugin and MCPs)")
        installed = installed_plugins()
        for old in manifest.get("plugins", []):
            if old not in wanted and old in installed:
                claude_cli(["plugin", "uninstall", old], rep, dry)
        if MARKETPLACE_NAME not in known_marketplaces():
            claude_cli(["plugin", "marketplace", "add", str(MARKETPLACE_DIR)], rep, dry)
        elif any(installed.get(k) != v for k, v in wanted.items()):
            claude_cli(["plugin", "marketplace", "update", MARKETPLACE_NAME], rep, dry)
        for key, ver in wanted.items():
            if key not in installed:
                claude_cli(["plugin", "install", key], rep, dry)
            elif installed[key] != ver:
                claude_cli(["plugin", "update", key], rep, dry)
            else:
                rep.ok(f"plugin {key} already at version {ver}")
        present = user_mcp_servers()
        if present is None:
            rep.warn("could not run `claude mcp list`; user MCPs not checked")
        else:
            missing = [k for k in plug["build"]["servers"] if k not in present]
            # An MCP in user scope starts in EVERY Claude session, not only in AiDW: only with --mcp.
            if missing and not with_mcp:
                rep.info(f"Catalog MCPs outside user scope: {', '.join(missing)}. Outside AiDW the agents "
                         "go without them; `install --mcp` registers them (they start in every Claude session)")
            for k in missing if with_mcp else []:
                if claude_cli(mcp_add_args(k, plug["build"]["servers"][k]), rep, dry) and not dry:
                    mcp_added.append(k)
    if rep.errors:
        save_manifest(cli_done=False)
        print(f"\n{len(rep.errors)} error(s) in Claude Code. Files and settings already recorded in the manifest; "
              "fix them and run `install` again (or `uninstall` to undo).")
        return False
    save_manifest(cli_done=True)
    print(f"\nDone{' (nothing was changed: dry-run)' if dry else ''}. In any folder, open a new chat and "
          f"call /{plugin}:go <demand>.")
    return True


def uninstall(dry: bool, skip_cli: bool) -> bool:
    heading("Global uninstall from Claude" + (" (dry-run)" if dry else ""))
    rep = Report()
    manifest = load_manifest()
    if not manifest:
        if MARKETPLACE_DIR.is_dir() or INSTALL_MANIFEST.exists():
            where = rel(MARKETPLACE_DIR) if MARKETPLACE_DIR.is_dir() else rel(INSTALL_MANIFEST)
            rep.warn(f"manifest missing or unreadable ({rel(INSTALL_MANIFEST)}), and install leftovers remain in "
                     f"{where}: "
                     "without it there is no way to know what is AiDW's. Remove by hand the plugin (`claude plugin "
                     f"uninstall`), the {MARKETPLACE_NAME} marketplace and the AiDW rules in ~/.claude/settings.json")
            return False
        rep.info("nothing installed by AiDW (no .aidw/install-manifest.json)")
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
                rep.info(f"(dry-run) remove {cache}")
            else:
                shutil.rmtree(cache)
                rep.ok(f"removed {cache}")
    merge_user_settings({}, manifest.get("settings", {}), dry, rep)
    if not dry:  # `marketplace remove` leaves `extraKnownMarketplaces: {}` behind
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
            rep.warn(f"{k} was changed outside AiDW; kept")
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
            codex = load_manifest().get("codex")
            if codex:  # Codex is still installed: only its record stays
                write_if_changed(INSTALL_MANIFEST, json.dumps({"codex": codex}, indent=2, ensure_ascii=False) + "\n",
                                 dry, Report(quiet=True))
            else:
                INSTALL_MANIFEST.unlink()
    print(f"\nDone{' (nothing was changed: dry-run)' if dry else ''}"
          f"{f' with {len(rep.errors)} error(s)' if rep.errors else ''}.")
    return not rep.errors


def check_global_install(cfg: dict, catalog: dict, rep: Report) -> None:
    heading("Global install (Claude)")
    manifest = load_manifest()
    if not manifest:
        rep.info("not installed (optional): `python aidw.py install` makes AiDW available in any folder")
        return
    plugins = manifest.get("plugins") or []
    if not plugins or not isinstance(manifest.get("settings"), dict):
        rep.error(f"{rel(INSTALL_MANIFEST)} malformed — run `python aidw.py install` again")
        return
    key = plugins[-1]
    plug = build_plugin(cfg, catalog, Report(quiet=True))
    if plug is None:
        rep.error("the configuration has errors — run `python aidw.py install` to see which")
        return
    if plug["version"] != manifest.get("version"):
        rep.warn(f"the sources changed since the install ({manifest.get('version')} → {plug['version']}) — "
                 "run `python aidw.py install`")
    elif manifest.get("cli", True) and not manifest.get("cli_done", True):
        rep.warn("the last install stopped at Claude Code (plugin or MCP) — run `python aidw.py install`")
    elif manifest.get("cli", True):
        installed = installed_plugins().get(key)
        if installed is None:
            rep.warn(f"plugin {key} does not show up in Claude — run `python aidw.py install`")
        elif installed != manifest["version"]:
            rep.warn(f"Claude has {key} {installed}, and the generated one is {manifest['version']} (the desktop app "
                     "uses the cache) — run `python aidw.py install`")
        else:
            rep.ok(f"plugin {key} {installed}, up to date with the sources")
        mods = plug.get("mods")
        if mods:
            mods_key = f"{mods['plugin']}@{MARKETPLACE_NAME}"
            got = installed_plugins().get(mods_key)
            if got == mods["version"]:
                rep.ok(f"plugin {mods_key} {got} (Claude Code mods), up to date")
            else:
                rep.warn(f"plugin {mods_key} {got or 'missing'}, and the generated one is {mods['version']} — "
                         "run `python aidw.py install`")
    try:
        data = json.loads(USER_SETTINGS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    perms = data.get("permissions", {})
    missing = [f"{k}: {x}" for k in ("allow", "ask", "deny", "additionalDirectories")
               for x in manifest.get("settings", {}).get(k, []) if x not in perms.get(k, [])]
    if missing:
        rep.warn(f"{len(missing)} AiDW rule(s) missing from {USER_SETTINGS} (e.g. {missing[0]}) — "
                 "run `python aidw.py install`")
    else:
        rep.ok(f"AiDW global rules present in {USER_SETTINGS}")


# ---------------------------------------------------------------------------
# Project, demand and worktree (aidw.py project detect / worktree ...)
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
    """Working tree root, main repository (even from inside a worktree) and branch."""
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
    """Writes to a temp file and swaps it in at once: a reader never sees a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def demand_path(ctx: dict | None, demand: str) -> Path:
    return state_dir(ctx) / demand / "demand.json"


def load_demand(ctx: dict | None, demand: str) -> tuple[dict | None, str, str]:
    """(data, warning, warning kind: "" | "corrupt" | "context"). An unreadable file becomes a .bak (it never
    vanishes silently); a demand from another context is not this session's (two contexts without their own
    state_dir share the state/ folder)."""
    path = demand_path(ctx, demand)
    if not path.exists():
        return None, "", ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        backup = path.with_name(f"demand.json.{datetime.now().strftime('%Y%m%d%H%M%S')}.bak")
        os.replace(path, backup)
        return None, f"demand.json unreadable; saved to {backup.as_posix()} and recreated (check the history)",             "corrupt"
    mine = ctx["name"] if ctx else None
    if data.get("context", mine) != mine:
        return None, f"demand {demand} belongs to context {data.get('context')!r}, not {mine!r}", "context"
    return data, "", ""


def update_demand_file(ctx: dict | None, demand: str, repo_entry: dict) -> Path:
    """demand.json in the demand folder: one item per repository (a demand may touch more than one)."""
    data, _, _ = load_demand(ctx, demand)
    data = data or {"id": demand, "context": ctx["name"] if ctx else None, "status": "active", "repos": []}
    data["repos"] = [r for r in data.get("repos", []) if norm_path(r["repo"]) != norm_path(repo_entry["repo"])]
    data["repos"].append(repo_entry)
    data["updated"] = datetime.now().isoformat(timespec="seconds")
    path = demand_path(ctx, demand)
    write_json_atomic(path, data)
    return path


def default_base(main: Path) -> str:
    """The remote's default branch (origin/HEAD); with no remote, the working copy's current branch."""
    head = git_out(main, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    return head or git_out(main, "rev-parse", "--abbrev-ref", "HEAD") or "HEAD"


def find_worktree(reg: dict, target: str, repo: str | None = None) -> list[dict]:
    """Entries by worktree path or by demand id (optionally only for one repository)."""
    hits = [e for e in reg["worktrees"] if norm_path(e["path"]) == norm_path(target)]
    if not hits:
        hits = [e for e in reg["worktrees"] if e["demand"] == target]
    if repo:
        main = (repo_info(repo) or {}).get("main", repo)
        hits = [e for e in hits if norm_path(e["repo"]) == norm_path(main)]
    return hits


def pr_ref(pr: str) -> str:
    return f"refs/aidw/pr/{pr}/merge"


def fetch_pr(main: Path, pr: str) -> tuple[dict | None, str]:
    """Fetches the PR already merged into the target (`refs/pull/<n>/merge`, on Azure Repos and GitHub):
    {head, base, source}. `head` is that merge, `base` the target (1st parent) and `source` the PR tip (2nd parent)."""
    proc = git_proc(main, "fetch", "-q", "origin", f"+refs/pull/{pr}/merge:{pr_ref(pr)}")
    if proc.returncode != 0:
        return None, (f"refs/pull/{pr}/merge not found on origin of {main.as_posix()}: the PR is not from this "
                      "repository, was already completed or conflicts with the target (with a conflict the server "
                      "does not generate the merge) "
                      f"(git: {(proc.stderr or proc.stdout).strip()[-200:]})")
    head = git_out(main, "rev-parse", pr_ref(pr)) or ""
    parents = (git_out(main, "rev-list", "--parents", "-n", "1", head) or "").split()[1:]
    return {"head": head, "base": parents[0] if parents else head,
            "source": parents[1] if len(parents) > 1 else head}, ""


def write_pr_diff(ctx: dict | None, demand: str, main: Path, name: str, args: list[str]) -> str:
    """Writes `git diff <args>` (raw bytes) to the demand folder; returns the path."""
    folder = state_dir(ctx) / demand
    folder.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(["git", "-C", str(main), "diff", *args], capture_output=True, timeout=600)
    (folder / name).write_bytes(proc.stdout)
    return (folder / name).as_posix()


def pr_refresh(ctx: dict | None, e: dict, reg: dict) -> dict:
    """Same PR again: did the author update it? Moves the worktree (detached, no local changes) to the new version
    and writes the diff of what changed since the reviewed version, only in the PR's files."""
    main, path, pr = Path(e["repo"]), Path(e["path"]), e["pr"]
    if git_out(path, "status", "--porcelain"):
        return {"ok": False, "error": f"{e['path']} has local changes; the PR worktree is read-only (discard them)"}
    new, error = fetch_pr(main, pr)
    if new is None:
        return {"ok": False, "error": error}
    if new["head"] == e["head"]:
        return {"ok": True, "created": False, "updated": False, **e}
    proc = git_proc(path, "checkout", "-q", "--detach", new["head"])
    if proc.returncode != 0:
        return {"ok": False, "error": f"could not update the worktree: {(proc.stderr or proc.stdout).strip()[-300:]}"}
    files = set()
    for v in (e, new):
        files |= set((git_out(main, "diff", "--name-only", v["base"], v["head"]) or "").splitlines())
    rnd = len(e.get("versions", [e["head"]])) + 1
    folder = wt_folder(e)
    incremental = write_pr_diff(ctx, e["demand"], main, f"diff-pr{pr}-{folder}-r{rnd}.patch",
                                [e["head"], new["head"], "--", *sorted(files)])
    full = write_pr_diff(ctx, e["demand"], main, f"diff-pr{pr}-{folder}.patch", [new["base"], new["head"]])
    previous = e["head"]
    e.update(new, versions=[*e.get("versions", [previous]), new["head"]])
    save_registry(reg)
    update_demand_file(ctx, e["demand"], {k: e[k] for k in ("repo", "path", "branch", "base", "system", "pr", "head",
                                                            "source")})
    return {"ok": True, "created": False, "updated": True, "previous": previous, "round": rnd, "diff": full,
            "incremental_diff": incremental, **e}


def fresh_base(main: Path, base: str) -> tuple[str, str]:
    """Replaces a stale local base with `origin/<base>` (the local `desenvolvimento` branch got stale; 2026-11-04)."""
    if base.startswith("origin/") or git_proc(main, "rev-parse", "--verify", "-q", f"refs/heads/{base}").returncode:
        return base, ""
    remote = f"origin/{base}"
    if git_proc(main, "rev-parse", "--verify", "-q", f"refs/remotes/{remote}").returncode:
        return base, ""
    local, upstream = git_out(main, "rev-parse", base), git_out(main, "rev-parse", remote)
    if local == upstream:
        return base, ""
    if git_proc(main, "merge-base", "--is-ancestor", base, remote).returncode == 0:
        return remote, f"local branch {base} is behind {remote}: the base used is {remote}"
    return base, f"local branch {base} has commits that are not in {remote}: the base used is the local one"


def worktree_create(cfg: dict, repo: str, demand: str, slug: str = "", base: str = "", pr: str = "") -> dict:
    """Creates (or returns, if it exists) the demand's worktree. {ok, path, branch, base, ...} or {ok: False, error}.
    With `pr`: a detached, read-only worktree on the PR already merged into the target, to review someone else's PR."""
    ctx = load_context(cfg, Report(quiet=True))
    demand = demand.strip().lower()
    if not DEMAND_RE.match(demand):
        return {"ok": False, "error": f"invalid demand id {demand!r} (use lowercase letters, numbers and -)"}
    pr = str(pr or "").strip().lstrip("#")
    if pr and not pr.isdigit():
        return {"ok": False, "error": f"invalid PR number {pr!r}"}
    info = repo_info(repo)
    if info is None:
        return {"ok": False, "error": f"{repo} is not a Git repository"}
    main = Path(info["main"])
    reg = load_registry()
    for e in reg["worktrees"]:
        if e["demand"] == demand and norm_path(e["repo"]) == norm_path(main) and Path(e["path"]).is_dir():
            if pr and e.get("pr") == pr:
                return pr_refresh(ctx, e, reg)
            if pr or e.get("pr"):
                return {"ok": False, "error": f"demand {demand} already has a {main.name} worktree at {e['path']} "
                                              f"({'PR ' + e['pr'] if e.get('pr') else 'branch ' + e['branch']}); "
                                              "one repository per demand: use another demand for this PR"}
            return {"ok": True, "created": False, **e}
    folder = main.name
    if any(e["demand"] == demand and Path(e["repo"]).name.lower() == folder.lower()
           and norm_path(e["repo"]) != norm_path(main)
           for e in reg["worktrees"]):  # e.g. C:/Repos/Legacy/App and C:/Repos/New/App in the same demand
        folder = f"{main.name}.{main.parent.name}"
    path = worktree_root(cfg) / demand / folder  # the demand folder gathers the worktrees of all its repositories
    warnings = []
    # another demand repository's worktree_link (e.g. ../eCommerce) becomes the demand's worktree; the junction is
    # removed only right before `git worktree add` and comes back if it fails
    was_link = is_link(path) and norm_path(os.path.realpath(path)) == norm_path(os.path.realpath(main))
    if path.exists() and not was_link:
        return {"ok": False, "error": f"{path.as_posix()} already exists and is not in the AiDW registry; check and "
                                      "remove it by hand"}
    wt_cfg = ctx.get("worktree", {}) if ctx else {}
    pr_info: dict = {}
    main_dirty = False
    if pr:  # no branch: `pr/<n>` is only the registry label
        branch = f"pr/{pr}"
        fetched, error = fetch_pr(main, pr)
        if fetched is None:
            return {"ok": False, "error": error}
        pr_info, base = fetched, fetched["base"]
    else:
        number = re.sub(r"^[a-z]+-", "", demand)
        branch = f"{wt_cfg.get('branch_prefix', 'aidw/')}{number}" + (f"-{slugify(slug)[:40].strip('-')}" if slug else "")
        if git_proc(main, "check-ref-format", "--branch", branch).returncode != 0:
            return {"ok": False, "error": f"invalid branch name: {branch}"}
        if git_out(main, "remote"):
            if git_proc(main, "fetch", "-q", "origin").returncode != 0:
                warnings.append("git fetch origin failed; the base may be outdated")
        base = base or default_base(main)
        if git_proc(main, "rev-parse", "--verify", "-q", f"{base}^{{commit}}").returncode != 0:
            return {"ok": False, "error": f"base {base!r} does not exist in {main.as_posix()}"}
        base, note = fresh_base(main, base)
        if note:
            warnings.append(note)
        main_dirty = bool(git_out(main, "status", "--porcelain"))
        if main_dirty:
            warnings.append("the main working copy has local changes; they do NOT go into the worktree")
    path.parent.mkdir(parents=True, exist_ok=True)
    if was_link:
        remove_link(path)
    if pr:
        proc = git_proc(main, "worktree", "add", "--detach", str(path), pr_info["head"])
    elif git_proc(main, "rev-parse", "--verify", "-q", f"refs/heads/{branch}").returncode == 0:
        proc = git_proc(main, "worktree", "add", str(path), branch)  # the branch already exists: reuse it
    else:
        proc = git_proc(main, "worktree", "add", "-b", branch, str(path), base)
    if proc.returncode != 0:
        if was_link and not path.exists():
            make_link(path, main)  # the build of the demand's other repositories still finds the dependency
        return {"ok": False, "error": f"git worktree add failed: {(proc.stderr or proc.stdout).strip()[-400:]}"}
    if was_link:
        warnings.append(f"{path.as_posix()} was a junction to {main.as_posix()}; it is now the demand's worktree, "
                        "and the build of the demand's other repositories now uses this version")
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
        return {"ok": False, "error": f"failed to create the dependency junction ({exc}); " + (
            "the just-created worktree was undone" + ("" if pr else f" (branch {branch} remains, with no new commits)")
            if undone else
            f"and the worktree {path.as_posix()} could not be undone: remove it by hand (git worktree remove)")}
    system = system_for(ctx, main.as_posix())
    outside = link_outside(cfg, ctx, system, main, path, warnings)
    entry = {"demand": demand, "repo": main.as_posix(), "path": path.as_posix(), "branch": branch, "base": base,
             "links": links, "outside_links": outside, "status": "active", "context": ctx["name"] if ctx else None,
             "system": system, "layout": "demanda", "created_at": datetime.now().isoformat(timespec="seconds")}
    extra = {}
    if pr:
        entry.update(pr=pr, head=pr_info["head"], source=pr_info["source"], versions=[pr_info["head"]])
        extra["diff"] = write_pr_diff(ctx, demand, main, f"diff-pr{pr}-{path.name}.patch", [base, pr_info["head"]])
    reg["worktrees"].append(entry)
    save_registry(reg)
    keys = ("repo", "path", "branch", "base", "system") + (("pr", "head", "source") if pr else ())
    demand_file = update_demand_file(ctx, demand, {k: entry[k] for k in keys})
    return {"ok": True, "created": True, "main_dirty": main_dirty, "warnings": warnings,
            "demand_file": demand_file.as_posix(), **extra, **entry}


def link_outside(cfg: dict, ctx: dict | None, system: str | None, main: Path, path: Path, warnings: list) -> list[str]:
    """The system's `worktree_link`: neighboring folders the code reaches by relative path (e.g. HintPath
    `..\\..\\eCommerce\\...\\bin\\x.dll`). The same relative path, from the worktree, becomes a junction to what it
    resolves to from the main working copy. They live in the demand folder (or above, at the worktree root,
    shared); `remove` of the demand's last worktree removes those in its folder."""
    made = []
    rels = (ctx or {}).get("systems", {}).get(system or "", {}).get("worktree_link", [])
    registered = load_registry()["worktrees"] if rels else []
    for rel in rels:
        src, dst = Path(os.path.normpath(main / rel)), Path(os.path.normpath(path / rel))
        if norm_path(src) == norm_path(main):
            continue  # the list applies to all of the system's repositories; a repository does not link to itself
        if not path_inside(dst, worktree_root(cfg)) or path_inside(dst, path) or path_inside(src, main):
            warnings.append(f"worktree_link {rel!r} ignored: it must leave the repository and stay inside the "
                            "worktree root")
        elif not src.is_dir():
            warnings.append(f"worktree_link {rel!r}: {src.as_posix()} does not exist; the build may not find this "
                            "dependency")
        elif any(norm_path(x["path"]) == norm_path(dst) and norm_path(x["repo"]) == norm_path(src)
                 and x["status"] == "active" and Path(x["path"]).is_dir() for x in registered):
            continue  # the demand has a worktree of that repository there: the build uses the demand's version
        elif is_link(dst) and norm_path(os.path.realpath(dst)) == norm_path(os.path.realpath(src)):
            made.append(rel)  # already created by another worktree of the demand
        elif is_link(dst):  # points elsewhere (old config, another repository) or nowhere
            warnings.append(f"worktree_link {rel!r}: {dst.as_posix()} is a junction to somewhere else; check it and "
                            f"remove it by hand so it points to {src.as_posix()}")
        elif dst.exists():
            warnings.append(f"worktree_link {rel!r}: {dst.as_posix()} already exists and is not a junction; nothing "
                            "was done")
        else:
            try:
                make_link(dst, src)
                made.append(rel)
            except (OSError, subprocess.CalledProcessError) as exc:
                warnings.append(f"worktree_link {rel!r}: failed to create the junction ({exc})")
    return made


def worktree_state(e: dict) -> dict:
    """Current state: exists, uncommitted changes, commits ahead of/behind the base, published."""
    path = Path(e["path"])
    if not path.is_dir():
        return {"exists": False}
    status = git_proc(path, "status", "--porcelain")
    counts = git_proc(path, "rev-list", "--left-right", "--count", f"{e['base']}...HEAD")
    parts = counts.stdout.split()
    if status.returncode != 0 or counts.returncode != 0 or len(parts) != 2:
        failed = status if status.returncode != 0 else counts
        return {"exists": True, "error": f"could not check the worktree (git: "
                                         f"{(failed.stderr or failed.stdout).strip()[-200:] or 'unexpected output'})"}
    # a PR worktree has no branch: what it has is the PR's, which is already on the server
    published = bool(e.get("pr")) or bool(git_out(e["repo"], "branch", "-r", "--contains", e["branch"]))
    return {"exists": True, "dirty": bool(status.stdout.strip()), "ahead": int(parts[1]), "behind": int(parts[0]),
            "published": published}


def worktree_remove(target: str, repo: str | None = None) -> dict:
    """Removes only a clean, integrated worktree (no local changes; commits published or none ahead)."""
    reg = load_registry()
    hits = find_worktree(reg, target, repo)
    if len(hits) != 1:
        return {"ok": False, "error": ("no AiDW worktree with that path or demand" if not hits else
                                       "more than one worktree for that demand; pass --repo")}
    e = hits[0]
    st = worktree_state(e)
    if st.get("exists"):
        if st.get("error"):
            return {"ok": False, "error": f"{st['error']}; nothing was removed (check by hand with git status/log)"}
        if st["dirty"]:
            return {"ok": False, "error": f"{e['path']} has uncommitted changes; commit or discard them first"}
        if st["ahead"] and not st["published"]:
            return {"ok": False, "error": f"branch {e['branch']} has {st['ahead']} unpublished commit(s); "
                                          "push (or discard the branch) before removing"}
        for name in e.get("links", []):  # junctions first: never delete recursively through one
            link = Path(e["path"]) / name
            if is_link(link):
                remove_link(link)
        proc = git_proc(e["repo"], "worktree", "remove", e["path"])
        if proc.returncode != 0:
            return {"ok": False, "error": f"git worktree remove failed: {(proc.stderr or proc.stdout).strip()[-400:]}"}
    else:
        git_proc(e["repo"], "worktree", "prune")
    if e.get("pr"):
        git_proc(e["repo"], "update-ref", "-d", pr_ref(e["pr"]))
    reg["worktrees"] = [x for x in reg["worktrees"] if x is not e]
    save_registry(reg)
    folder = Path(e["path"]).parent
    if in_demand_folder(e) and folder.is_dir() and not any(path_inside(x["path"], folder) for x in reg["worktrees"]):
        children = list(folder.iterdir())
        if all(is_link(c) for c in children):  # only the worktree_link junctions are left: the demand folder goes
            for child in children:
                remove_link(child)  # removes the junction, never deletes through it
            folder.rmdir()
    return {"ok": True, "path": e["path"], "branch": e["branch"],
            "note": "PR worktree, no local branch" if e.get("pr") else
            f"branch {e['branch']} was kept (deleting a branch is a locked action)"}


def in_demand_folder(e: dict) -> bool:
    """Worktree in the `<root>/<demand>/<folder>` layout (recorded in the registry); old ones are
    `<root>/<folder>/<demand>`."""
    return e.get("layout") == "demanda"


def wt_folder(e: dict) -> str:
    """The repository's folder in the worktree (e.g. `App.Front`), in both layouts."""
    p = Path(e["path"])
    return p.name if in_demand_folder(e) else p.parent.name


def worktree_cleanup() -> dict:
    """Drops from the registry the worktrees whose folder is gone and runs `git worktree prune` in their repos."""
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
    reg = load_registry()
    if not info:  # the demand folder (`<root>/<demand>`) is not a repository: its worktrees are inside it
        inner = [e for e in reg["worktrees"] if e["status"] == "active" and in_demand_folder(e)
                 and path_inside(path, Path(e["path"]).parent)]
        if inner:
            result.update(demand=inner[0]["demand"], demand_folder=Path(inner[0]["path"]).parent.as_posix(),
                          worktrees=[{"folder": wt_folder(e), "path": e["path"], "branch": e["branch"]}
                                     for e in inner if e["demand"] == inner[0]["demand"]])
        return result
    active = [e for e in reg["worktrees"] if norm_path(e["repo"]) == norm_path(info["main"]) and e["status"] == "active"]
    here = [e for e in active if path_inside(path, e["path"])]
    result.update(info, system=system_for(ctx, info["main"]),
                  demand=here[0]["demand"] if here else None,
                  active_demands=[{"demand": e["demand"], "path": e["path"], "branch": e["branch"]} for e in active])
    return result


def worktree_hook_create() -> int:
    """WorktreeCreate hook (EnterWorktree / claude --worktree): prints the path of the demand's worktree."""
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))  # UTF-8, not the console code page
    except (json.JSONDecodeError, UnicodeDecodeError):
        print("AiDW: invalid input in the WorktreeCreate hook", file=sys.stderr)
        return 1
    raw = str(data.get("name") or "")
    cwd = str(data.get("cwd") or os.getcwd())
    reg = load_registry()
    if "/" in raw:  # `<demand>/<repository folder>` (diff skill): that repository's worktree, from any folder
        demand, folder = (x.strip() for x in raw.split("/", 1))
        hits = [e for e in reg["worktrees"] if e["demand"] == slugify(demand) and e["status"] == "active"
                and Path(e["path"]).is_dir() and wt_folder(e).lower() == folder.lower()]
        if len(hits) != 1:
            print(f"AiDW: no active worktree of demand {demand} in folder {folder} "
                  "(`aidw.py worktree list`)", file=sys.stderr)
            return 1
        print(Path(hits[0]["path"]))
        return 0
    name = slugify(raw) or "sessao"
    same = [e for e in reg["worktrees"] if e["demand"] == name and e["status"] == "active" and Path(e["path"]).is_dir()]
    info = repo_info(cwd)
    here = [e for e in same if norm_path(e["repo"]) == norm_path(info["main"])] if info else same[:1]
    at_root = bool(info) and norm_path(info["main"]) == norm_path(ROOT)
    if at_root and not here and same:
        # chat opened at the AiDW root, which is never a demand repository: enter the worktree the demand already has
        # (with several, the first one created; the orchestrator reaches the others by absolute path). In another
        # repository, creating one is right (a demand with more than one repository, `claude --worktree <id>`).
        here = same[:1]
    same = here
    if len(same) == 1:  # created earlier by the orchestrator (`worktree create`): the session only enters it
        print(Path(same[0]["path"]))
        return 0
    cfg = load_config()
    if cfg is None:
        print("AiDW: aidw.config.toml not found", file=sys.stderr)
        return 1
    if at_root and demand_path(load_context(cfg, Report(quiet=True)), name).exists():
        print(f"AiDW: demand {name} has no worktree yet; create it with `worktree create --repo <repo> --demand "
              f"{name}` and call EnterWorktree again (the AiDW root is not a demand repository)", file=sys.stderr)
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
    if action == "hook-remove":  # the worktree stays; removal goes through the `worktree remove` checks
        print("AiDW: worktree kept; remove it with `python aidw.py worktree remove <demand>`", file=sys.stderr)
        return 0
    if action == "create":
        result = worktree_create(cfg, args.repo, args.demand, args.slug or "", args.base or "", args.pr or "")
    elif action == "remove":
        result = worktree_remove(args.target, args.repo)
    elif action == "cleanup":
        result = worktree_cleanup()
    elif action == "inspect":
        hits = find_worktree(load_registry(), args.target, args.repo)
        result = ({"ok": True, **hits[0], **worktree_state(hits[0])} if len(hits) == 1 else
                  {"ok": False, "error": "none or more than one worktree with that path/demand (use --repo)"})
    else:  # list
        result = {"ok": True, "worktrees": [{**e, "folder": wt_folder(e), **worktree_state(e)}
                                            for e in load_registry()["worktrees"]]}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    if not result["ok"]:
        print(f"[error] {result['error']}")
        return 1
    if action == "create" and result.get("pr"):
        state = "created" if result["created"] else ("updated" if result.get("updated") else "already up to date")
        print(f"[ok]    PR {result['pr']} worktree {state}: {result['path']} (read-only, detached)")
        print(f"        merge {result['head'][:8]} = target {result['base'][:8]} + PR {result['source'][:8]}; "
              f"junctions: {', '.join(result['links'] + result.get('outside_links', [])) or 'none'}")
        for key, label in (("diff", "PR diff"), ("incremental_diff", "what changed since the review")):
            if result.get(key):
                print(f"        {label}: {result[key]}")
        for w in result.get("warnings", []):
            print(f"[warn]  {w}")
    elif action == "create":
        print(f"[ok]    worktree {'created' if result['created'] else 'already exists'}: {result['path']}")
        print(f"        branch {result['branch']} (base {result['base']}); junctions: "
              f"{', '.join(result['links'] + result.get('outside_links', [])) or 'none'}")
        for w in result.get("warnings", []):
            print(f"[warn]  {w}")
    elif action == "remove":
        print(f"[ok]    removed {result['path']}; {result['note']}")
    elif action == "cleanup":
        print(f"[ok]    {len(result['removed_from_registry'])} orphan worktree(s) removed from the registry")
    elif action == "inspect":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if not result["worktrees"]:
            print("No demand worktree registered.")
        for e in result["worktrees"]:
            if not e["exists"]:
                state = "orphan (folder gone — run `worktree cleanup`)"
            else:
                state = ("with changes" if e["dirty"] else "clean") + f", {e['ahead']} ahead of the base" + \
                        (" (published)" if e["ahead"] and e["published"] else "")
            print(f"  {e['demand']:<14} {e['path']:<50} {e['branch']:<40} {state}")
    return 0


# ---------------------------------------------------------------------------
# Demand: state to resume (aidw.py demand set / show / list)
# ---------------------------------------------------------------------------

DEMAND_STATUS = ("active", "paused", "done")


def demand_set(cfg: dict, demand: str, step: str = "", status: str = "", title: str = "", note: str = "",
               summary: str = "", prs: list[str] | None = None,
               tasks: list[str] | None = None, loop: str | None = None, extra_steps: list[str] | None = None) -> dict:
    ctx = load_context(cfg, Report(quiet=True))
    demand = demand.strip().lower()
    if not DEMAND_RE.match(demand):
        return {"ok": False, "error": f"invalid demand id {demand!r} (use lowercase letters, digits and -)"}
    outside = [s["step"] for s in context_external_steps(ctx)]
    if step and step not in ACTIONS and step not in LEGACY_STEPS and step not in outside and step != "UNDERSTAND":
        return {"ok": False, "error": f"unknown step {step!r} (use UNDERSTAND, a NEXT ACTION action or an "
                                      "outside step of the context)"}
    for item in extra_steps or []:
        if item.lstrip("-") not in outside:
            return {"ok": False, "error": f"--extra-step {item!r}: not an outside step of the context "
                                          f"({', '.join(outside) or 'the context declares none'})"}
    if status and status not in DEMAND_STATUS:
        return {"ok": False, "error": f"invalid status {status!r} (use {', '.join(DEMAND_STATUS)})"}
    if summary and len(summary.splitlines()) > 4:
        return {"ok": False, "error": "the summary has at most 4 lines"}
    pr_map: dict[str, str] = {}
    for item in prs or []:
        repo, sep, number = item.partition("=")
        if not sep or not repo.strip() or not number.strip().isdigit():
            return {"ok": False, "error": f"invalid --pr {item!r} (use <repository>=<number>)"}
        pr_map[repo.strip().lower()] = number.strip()
    task_map: dict[str, str] = {}
    for item in tasks or []:
        ticket, sep, number = item.partition("=")
        if not sep or not ticket.strip() or not number.strip().lstrip("#").isdigit():
            return {"ok": False, "error": f"invalid --task {item!r} (use <ticket>=<work item id>)"}
        task_map[ticket.strip()] = number.strip().lstrip("#")
    data, warning, kind = load_demand(ctx, demand)
    if kind == "context":
        return {"ok": False, "error": warning}
    data = data or {"id": demand, "context": ctx["name"] if ctx else None, "status": "active", "repos": []}
    now = datetime.now().isoformat(timespec="seconds")
    if step and step != data.get("step"):
        data.setdefault("history", []).append({"step": step, "at": now})
        data["step"] = step
    for key, value in (("status", status), ("title", title), ("note", note), ("summary", summary.strip())):
        if value:
            data[key] = value
    data.pop("mode", None)  # the session mode (auto/interactive) was dropped in flow v3
    for name, number in pr_map.items():
        repo = next((r for r in data.get("repos", []) if name in (
            Path(r.get("repo") or "").name.lower(), Path(r.get("path") or "").name.lower())), None)
        if repo is None:
            return {"ok": False, "error": f"--pr: the demand has no repository {name!r}"}
        repo["pr"] = number
    if task_map:
        data["tasks"] = {**data.get("tasks", {}), **task_map}
    if loop == "-":
        data.pop("loop", None)
    elif loop:
        if not DEMAND_RE.match(loop.strip().lower()):
            return {"ok": False, "error": f"invalid --loop {loop!r} (use lowercase letters, digits and -, "
                                          "e.g. bug-1234)"}
        data["loop"] = loop.strip().lower()
    for item in extra_steps or []:
        chosen = [s for s in data.get("extra_steps", []) if s != item.lstrip("-")]
        data["extra_steps"] = chosen if item.startswith("-") else [*chosen, item]
        if not data["extra_steps"]:
            data.pop("extra_steps")
    data["updated"] = now
    path = demand_path(ctx, demand)
    write_json_atomic(path, data)
    exclude_root_claude_md(path.parent)
    session_follow(ctx, demand, path.parent)
    return {"ok": True, "folder": path.parent.as_posix(), **({"warning": warning} if warning else {}), **data}


def exclude_root_claude_md(folder: Path) -> None:
    """Demand folder inside the AiDW root: a chat opened there would load the project-mode CLAUDE.md on top of the
    go skill, the same rules twice. The folder's `.claude/settings.json` (read from the session folder)
    excludes the root one; whatever is already in the file stays."""
    try:
        folder.resolve().relative_to(ROOT)
    except ValueError:
        return
    f = folder / ".claude" / "settings.json"
    try:
        data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except (OSError, json.JSONDecodeError):
        return  # a file that is not ours and that we cannot read: leave it alone
    excludes = data.setdefault("claudeMdExcludes", [])
    if ROOT_CLAUDE_MD_EXCLUDE not in excludes:
        excludes.append(ROOT_CLAUDE_MD_EXCLUDE)
        write_json_atomic(f, data)


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
            continue  # another context sharing the state/ folder
        if active_only and d.get("status") == "done":
            continue
        out.append({"id": d.get("id", f.parent.name), "status": d.get("status"), "step": d.get("step"),
                    "title": d.get("title", ""), "note": d.get("note", ""),
                    "updated": d.get("updated"),
                    "folder": f.parent.as_posix(), "repos": [r.get("repo") for r in d.get("repos", [])]})
    return sorted(out, key=lambda d: d.get("updated") or "", reverse=True)


# ---------------------------------------------------------------------------
# Orchestrator session ↔ demand (state/sessions.json)
# ---------------------------------------------------------------------------
# The registry says the session is in orchestrator mode and which demand (context, id and folder) it drives; the
# aidw-mods read its folder without guessing the demand from the text. The /aidw:go hook turns the mode on where the
# client sends the command to the hook (the app); the go skill's `session bind` turns it on in any client (the
# terminal does not send the slash command).

SESSION_ENV = "CLAUDE_CODE_SESSION_ID"


def guard_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("aidw_guard", GUARD_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def session_follow(ctx: dict | None, demand: str, folder: Path) -> None:
    """`demand set` in a session already in orchestrator mode: the registry now points to this demand."""
    session = os.environ.get(SESSION_ENV)
    if not session:
        return
    try:
        guard = guard_module()
        if session not in guard.read_json(guard.SESSIONS, {}):
            return
        def change(sessions: dict) -> None:
            if session in sessions:  # left the mode between the read and the lock: do not turn it back on
                sessions[session].update(context=ctx["name"] if ctx else None, demand=demand,
                                         folder=folder.as_posix())

        guard.update_sessions(change)
    except Exception:  # the session registry never breaks demand set
        pass


def session_command(cfg: dict, args: argparse.Namespace) -> int:
    session = (args.session or os.environ.get(SESSION_ENV) or "").strip()
    if not session:
        result = {"ok": False, "error": f"no session id: pass --session or run inside Claude Code "
                                        f"({SESSION_ENV})"}
    elif args.ss_action == "unbind":
        guard_module().update_sessions(lambda s: s.pop(session, None))
        result = {"ok": True, "session": session, "bound": False}
    else:
        ctx = load_context(cfg, Report(quiet=True))
        fields: dict = {}
        if args.demand:
            demand = args.demand.strip().lower()
            path = demand_path(ctx, demand)
            if not DEMAND_RE.match(demand) or not path.exists():
                print(json.dumps({"ok": False, "error": f"demand {demand!r} has no demand.json in "
                                  f"{state_dir(ctx).as_posix()} (create it with `demand set`)"}, ensure_ascii=False))
                return 1
            fields = {"context": ctx["name"] if ctx else None, "demand": demand, "folder": path.parent.as_posix()}

        def change(sessions: dict) -> None:
            entry = sessions.get(session) or {
                "plugin": plugin_name(ctx), "provider": "claude", "argument": "", "cwd": os.getcwd(),
                "since": datetime.now().isoformat(timespec="seconds")}
            sessions[session] = {**entry, **fields}

        entry = guard_module().update_sessions(change)[session]
        result = {"ok": True, "session": session, **entry}
    if args.json or not result["ok"]:
        print(json.dumps(result, ensure_ascii=False))
    elif args.ss_action == "unbind":
        print(f"session {session[:8]}: out of orchestrator mode")
    else:
        print(f"session {session[:8]}: orchestrator mode" + (f", demand {result['demand']} ({result['context']})"
                                                             if result.get("demand") else ", no demand yet"))
    return 0 if result["ok"] else 1


def demand_command(cfg: dict, args: argparse.Namespace) -> int:
    if args.dm_action == "set":
        result = demand_set(cfg, args.id, args.step or "", args.status or "", args.title or "", args.note or "",
                            args.summary or "", args.pr, args.task, args.loop, args.extra_step)
        if not args.json:  # one line: the whole demand.json (with history) would only weigh on the chat
            if result["ok"]:
                print(f"{result['id']}: {result.get('step') or '—'} ({result.get('status') or '—'})"
                      + (f" — warning: {result['warning']}" if result.get("warning") else ""))
            else:
                print(f"error: {result['error']}")
            return 0 if result["ok"] else 1
    elif args.dm_action == "show":
        ctx = load_context(cfg, Report(quiet=True))
        data, warning, _ = load_demand(ctx, args.id)
        result = {"ok": True, "folder": demand_path(ctx, args.id).parent.as_posix(), **data} if data else \
            {"ok": False, "error": warning or f"demand {args.id!r} has no demand.json in {state_dir(ctx).as_posix()}"}
    else:
        result = {"ok": True, "demands": demand_list(cfg, args.active)}
    if args.json or args.dm_action != "list":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif not result["demands"]:
        print("No" + (" active" if args.active else "") + " demands.")
    else:
        for d in result["demands"]:
            print(f"  {d['id']:<18} {d['status'] or '—':<7} {d['step'] or '—':<15} {d['updated'] or '':<20} {d['title']}")
    return 0 if result["ok"] else 1


# ---------------------------------------------------------------------------
# Global install in Codex (aidw.py install --provider codex)
# ---------------------------------------------------------------------------

CODEX_NO_IMPLICIT = "policy:\n  allow_implicit_invocation: false\n"  # agents/openai.yaml: only when invoked


def codex_skill_copy(text: str, name: str) -> str:
    """SKILL.md for Codex: name `aidw-<name>`, the AiDW notice and {{root}} resolved. `disable-model-invocation`
    becomes agents/openai.yaml; `user-invocable` is dropped (Codex does not hide skills from the user: every
    `$aidw-*` shows up)."""
    text = re.sub(r"(?m)^disable-model-invocation:.*\n", "", guard_skill(text), count=1)  # in Codex: agents/openai.yaml
    text = re.sub(r"(?m)^user-invocable:.*\n", "", text, count=1)
    return re.sub(r"(?m)^name:\s*.*$", f"name: {CODEX_NS}{name}", text, count=1)


def is_aidw_hook_group(g: dict) -> bool:
    return any(GUARD_SCRIPT.name in str(h.get("command", "")) for h in g.get("hooks", []))


def remove_codex_hooks(data: dict) -> dict:
    """Removes from hooks.json the groups that old AiDW installs added (the user's own stay)."""
    hooks = data.setdefault("hooks", {})
    for event in list(hooks):
        hooks[event] = [g for g in hooks[event] if not is_aidw_hook_group(g)]
        if not hooks[event]:
            hooks.pop(event)
    if not hooks:
        data.pop("hooks")
    return data


def remove_legacy_codex(dry: bool, rep: Report) -> None:
    """Old installs put the `aidw` profile, the AiDW rules and hooks into Codex; today's install is only agents and
    skills. Removes the profile (an AiDW file) and the AiDW groups in hooks.json; the rules go away through the
    manifest, like any file that is no longer generated."""
    if CODEX_PROFILE.is_file() and is_generated(CODEX_PROFILE.read_text(encoding="utf-8", errors="replace")):
        rep.info(f"old profile {CODEX_PROFILE.name} removed (the Codex install is only agents and skills)")
        if not dry:
            CODEX_PROFILE.unlink()
    if not CODEX_HOOKS_FILE.is_file():
        return
    try:
        data = json.loads(CODEX_HOOKS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        rep.warn(f"{CODEX_HOOKS_FILE} is not valid JSON; remove the AiDW hooks by hand, if any")
        return
    if not any(is_aidw_hook_group(g) for gs in data.get("hooks", {}).values() for g in gs):
        return
    rep.info(f"old AiDW hooks removed from {CODEX_HOOKS_FILE.name}")
    if dry:
        return
    data = remove_codex_hooks(data)
    if data:
        CODEX_HOOKS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        CODEX_HOOKS_FILE.unlink()


def codex_multi_agent_enabled() -> bool:
    """`[features] multi_agent_v2 = true` in ~/.codex/config.toml: without it, the orchestrator does not call
    `spawn_agent`."""
    try:
        return load_toml(CODEX_HOME / "config.toml").get("features", {}).get("multi_agent_v2") is True
    except (OSError, tomllib.TOMLDecodeError):
        return False


CODEX_MULTI_AGENT_HINT = ("the AiDW orchestrator in Codex uses `spawn_agent`: turn on `multi_agent_v2` in your "
                          "~/.codex/config.toml (`[features]` → `multi_agent_v2 = true`) or open it with "
                          "`python aidw.py open --provider codex`, which already passes `--enable multi_agent_v2`")


def build_codex_install(cfg: dict, catalog: dict, rep: Report) -> dict | None:
    """{file: bytes} of the AiDW agents and skills, with `aidw-*` names: the Codex install is only that
    (no rules, hooks or profile; see docs/claude-and-codex.md)."""
    ccfg = json.loads(json.dumps(cfg))
    ccfg["provider"]["name"], ccfg["delegation"]["mode"] = "codex", "native"
    ref_dir = CODEX_SKILLS_HOME / f"{CODEX_NS}go" / "reference"
    sub = Report(quiet=True)  # warnings about another provider's models are expected here (the Codex tier applies)
    b = build(ccfg, catalog, sub, ns=CODEX_NS, ref_dir=ref_dir)
    for e in sub.errors:
        rep.error(e)
    if b is None:
        return None
    resolved, ctx = b["resolved"], b["ctx"]
    files: dict[Path, bytes] = {}
    for role, g in b["agents"].items():
        a = resolved[role]
        meta = {**g["meta"], "description": f"{PLUGIN_GUARD} {g['meta']['description']}"}
        for name, v in a["variants"].items():  # the default and each exception, model and effort pinned
            files[CODEX_AGENTS_HOME / f"{CODEX_NS}{name}.toml"] = render_codex_role(
                a, meta, g["prompt"], name, v["model"], v["effort"], ns=CODEX_NS).encode("utf-8")
    used = set(resolved[ORCHESTRATOR]["skills"]) | {n for a in resolved.values() if a["enabled"] for n in a["skills"]}
    used |= {n for n, d in b["skills"].items() if is_admin_skill(d / "SKILL.md")}
    for name in sorted(used & set(b["skills"])):
        src = b["skills"][name]
        for f in sorted(src.rglob("*")):
            if f.is_file():
                data = f.read_bytes()
                if f.name == "SKILL.md":
                    data = codex_skill_copy(data.decode("utf-8"), name).encode("utf-8")
                elif f.suffix == ".md":
                    data = data.replace(b"{{root}}", ROOT.as_posix().encode("utf-8"))
                files[CODEX_SKILLS_HOME / f"{CODEX_NS}{name}" / f.relative_to(src)] = data
        if read_frontmatter(src / "SKILL.md")[0].get("disable-model-invocation") == "true":  # only when invoked
            files[CODEX_SKILLS_HOME / f"{CODEX_NS}{name}" / "agents" / "openai.yaml"] = CODEX_NO_IMPLICIT.encode("utf-8")
    orq = CODEX_SKILLS_HOME / f"{CODEX_NS}go"
    files[orq / "SKILL.md"] = orchestrator_skill(plugin_name(), ctx, b["orchestrator_md"], orq / "SKILL.md",
                                                 provider="codex").encode("utf-8")
    files[orq / "agents" / "openai.yaml"] = CODEX_NO_IMPLICIT.encode("utf-8")
    survey = CODEX_SKILLS_HOME / f"{CODEX_NS}survey"
    files[survey / "SKILL.md"] = orchestrator_skill(plugin_name(), ctx, b["survey_md"], survey / "SKILL.md",
                                                    provider="codex", survey=True).encode("utf-8")
    files[survey / "agents" / "openai.yaml"] = CODEX_NO_IMPLICIT.encode("utf-8")
    for name, r in b["orchestrator_refs"].items():
        files[ref_dir / f"{name}.md"] = r["content"].encode("utf-8")
    leave = CODEX_SKILLS_HOME / f"{CODEX_NS}exit"
    files[leave / "SKILL.md"] = exit_skill(plugin_name(), provider="codex", language=ui_language(cfg)).encode("utf-8")
    files[leave / "agents" / "openai.yaml"] = CODEX_NO_IMPLICIT.encode("utf-8")
    return {"files": files, "ctx": ctx, "resolved": resolved, "servers": b["servers"]}


def remove_empty_codex_dirs(paths) -> None:
    """Deletes the empty folders the AiDW files left in Codex (walks up to the root folders, which stay)."""
    for d in sorted({Path(k).parent for k in paths}, key=lambda x: -len(x.parts)):
        while d not in (CODEX_SKILLS_HOME, CODEX_AGENTS_HOME, CODEX_HOME, CODEX_GLOBAL_RULES.parent) and d.is_dir() \
                and not any(d.iterdir()):
            d.rmdir()
            d = d.parent


def install_codex(cfg: dict, catalog: dict, dry: bool, force: bool) -> bool:
    """Global install in Codex: only the agents (`~/.codex/agents/aidw-*.toml`) and the skills
    (`~/.agents/skills/aidw-*`). Rules, hooks, profile and MCPs stay with the user's Codex; the rest of AiDW belongs
    to Claude Code."""
    heading("Global install in Codex — agents and skills" + (" (dry-run)" if dry else ""))
    rep = Report()
    built = build_codex_install(cfg, catalog, rep)
    if built is None:
        print("\nFix the errors above and run again.")
        return False
    manifest = load_manifest()
    old = manifest.get("codex", {})
    files = built["files"]
    conflicts = [k for k, h in old.get("files", {}).items() if Path(k).is_file() and sha(Path(k).read_bytes()) != h]
    if conflicts and not force:
        for k in conflicts:
            rep.error(f"{k} was changed outside AiDW; change the sources (the file is generated) or run with --force")
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
    if not dry:  # folders of skills no longer generated (e.g. aidw-lev → aidw-survey) are not left empty
        remove_empty_codex_dirs(old.get("files", {}))
    remove_legacy_codex(dry, rep)
    agents = sum(1 for k in files if k.parent == CODEX_AGENTS_HOME)
    skills = len({k.relative_to(CODEX_SKILLS_HOME).parts[0] for k in files if CODEX_SKILLS_HOME in k.parents})
    rep.ok(f"{agents} agents in {CODEX_AGENTS_HOME}, {skills} skills in {CODEX_SKILLS_HOME} "
           f"({changed} file(s) {'to change' if dry else 'changed'})")
    if not dry:
        manifest["codex"] = {"files": {str(k): sha(v) for k, v in files.items()}}
        write_if_changed(INSTALL_MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", dry, Report(quiet=True))
    if not codex_multi_agent_enabled():
        rep.warn(CODEX_MULTI_AGENT_HINT)
    rep.info("in Codex, AiDW is only agents and skills: no rules, hooks, guard, profile or per-agent MCP "
             "(docs/claude-and-codex.md)")
    print(f"\nDone{' (nothing was changed: dry-run)' if dry else ''}. In Codex: `python aidw.py open --provider codex` "
          "and call $aidw-go <demand>.")
    return not rep.errors


def uninstall_codex(dry: bool) -> bool:
    heading("Global uninstall from Codex" + (" (dry-run)" if dry else ""))
    rep = Report()
    manifest = load_manifest()
    old = manifest.get("codex")
    if not old:
        rep.info("nothing installed by AiDW in Codex")
        return True
    for k, h in old.get("files", {}).items():
        path = Path(k)
        if not path.is_file():
            continue
        if sha(path.read_bytes()) != h:
            rep.warn(f"{k} was changed outside AiDW; kept")
        elif not dry:
            path.unlink()
    remove_legacy_codex(dry, rep)
    if not dry:
        remove_empty_codex_dirs(old.get("files", {}))
        manifest.pop("codex")
        if manifest.get("plugins") or manifest.get("files"):
            write_if_changed(INSTALL_MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", dry, rep)
        elif INSTALL_MANIFEST.exists():
            INSTALL_MANIFEST.unlink()
    print(f"\nDone{' (nothing was changed: dry-run)' if dry else ''}.")
    return not rep.errors


def check_codex_install(rep: Report, cfg: dict, catalog: dict) -> None:
    heading("Global install (Codex — agents and skills)")
    old = load_manifest().get("codex")
    if not old:
        rep.info("not installed (optional): `python aidw.py install --provider codex`")
        return
    missing = [k for k in old.get("files", {}) if not Path(k).is_file()]
    built = build_codex_install(cfg, catalog, Report(quiet=True))
    stale = [] if built is None else [p for p, c in built["files"].items() if not p.is_file() or p.read_bytes() != c]
    if missing:
        rep.warn(f"{len(missing)} AiDW file(s) disappeared from Codex (e.g. {missing[0]}) — run install")
    elif stale:
        rep.warn(f"Codex is out of date ({len(stale)} file(s), e.g. {stale[0].name}): run "
                 "`python aidw.py install` (updates Claude and Codex)")
    else:
        rep.ok(f"{len(old.get('files', {}))} AiDW files in Codex (agents and skills), up to date")
    if CODEX_PROFILE.is_file() or CODEX_GLOBAL_RULES.is_file():
        rep.warn("leftovers of an old install in Codex (AiDW profile, rules or hooks): run install to remove them")
    if codex_multi_agent_enabled():
        rep.ok("multi_agent_v2 on in ~/.codex/config.toml")
    else:
        rep.info(CODEX_MULTI_AGENT_HINT)


def demand_worktrees(demand: str) -> list[dict]:
    """Active worktrees of the demand; `1234` also finds `us-1234`/`bug-1234`."""
    demand = demand.strip().lower()
    return [e for e in load_registry()["worktrees"] if e["status"] == "active" and
            (e["demand"] == demand or (demand.isdigit() and e["demand"].endswith("-" + demand)))]


def open_command(cfg: dict, provider: str, demand: str, path: str, print_only: bool, orchestrate: bool = True,
                 repo: str = "", app: bool = False) -> int:
    """Opens Claude or Codex right in the demand folder (its worktree) — Codex with `multi_agent_v2` — and, with
    `--demand`, calls the orchestrator to resume the demand (the session's first message). A demand with more than
    one repository: the session opens in the demand folder, which holds the worktrees (`/aidw:diff` switches the
    diff panel between them); with `--repo`, or with old-format worktrees, in that worktree (default: the first one
    created), and the others come in through `--add-dir`."""
    target = Path(path).resolve() if path else Path.cwd()
    folder = prompt = None
    extra: list[Path] = []
    shared: list[Path] = []
    if demand:
        hits = demand_worktrees(demand)
        ids = sorted({e["demand"] for e in hits})
        if not hits or len(ids) > 1:
            print(f"[error] {'no active worktree' if not hits else 'more than one demand (' + ', '.join(ids) + ')'} "
                  f"for {demand!r} (`aidw.py worktree list`)")
            return 1
        main = hits[0]
        if repo:
            chosen = [e for e in hits if norm_path(e["repo"]) == norm_path(repo) or Path(e["repo"]).name.lower() ==
                      Path(repo).name.lower()]
            if len(chosen) != 1:
                print(f"[error] demand {ids[0]} does not have exactly one worktree in {repo!r}; its repositories: "
                      + ", ".join(e["repo"] for e in hits))
                return 1
            main = chosen[0]
        extra = [Path(e["path"]) for e in hits if e is not main]
        demand, target = main["demand"], Path(main["path"])
        parents = {norm_path(Path(e["path"]).parent) for e in hits}
        if (provider == "claude" or app) and not repo and len(hits) > 1 and len(parents) == 1 and \
                all(in_demand_folder(e) for e in hits):
            target, extra = Path(main["path"]).parent, []  # the demand folder: the worktrees are inside it
        ctx = load_context(cfg, Report(quiet=True))
        folder = state_dir(ctx) / demand
        if provider == "claude":  # the whole context (plans, reports, references) opens in the app; covers the folder
            shared = [d for d in session_dirs(ctx) if d.is_dir()]
            folder = None if any(d == folder or d in folder.parents for d in shared) else folder
        manifest = load_manifest()
        installed = bool(manifest.get("codex")) if provider == "codex" else bool(manifest.get("plugins"))
        if orchestrate and installed:
            prompt = f"$aidw-go {demand}" if provider == "codex" else f"/{plugin_name()}:go {demand}"
        elif orchestrate:
            print(f"[warn]  AiDW is not installed in {provider} (`aidw.py install --provider {provider}`): "
                  "opening without calling the orchestrator")
    exe = shutil.which(provider) or (provider if print_only else None)
    if not exe:
        print(f"[error] CLI `{provider}` not found")
        return 1
    if app:  # Codex desktop app: opens the folder as a workspace; the conversation starts empty
        cmd = [exe, "app", str(target)]
        print(f"[ok]    in the app, start the conversation with `{prompt or '$aidw-go <demand>'}`")
        print(f"Opening the Codex app in {target}: {subprocess.list2cmdline([Path(exe).stem, *cmd[1:]])}")
        return 0 if print_only else subprocess.run(cmd, cwd=target).returncode
    if provider == "codex":  # no AiDW profile: only the subagent and the AiDW folder (demand artifacts) allowed
        cmd = [exe, "-C", str(target), "--enable", "multi_agent_v2", "--add-dir", str(ROOT)]
    else:
        cmd = [exe]
    for d in [*extra, *shared, *([folder] if folder else [])]:
        cmd += ["--add-dir", str(d)]
    if extra:
        print(f"[ok]    the demand has {len(extra) + 1} worktrees: the session opens in {target} and the others come "
              "in through --add-dir (switch with --repo)")
    elif demand and not (target / ".git").exists():
        print(f"[ok]    demand folder {target}: the worktrees are inside; /aidw:diff switches the diff panel "
              "between them")
    if prompt:
        cmd.append(prompt)
    print(f"Opening {provider} in {target}: {subprocess.list2cmdline([Path(exe).stem, *cmd[1:]])}")
    if print_only:
        return 0
    return subprocess.run(cmd, cwd=target).returncode


# ---------------------------------------------------------------------------
# Overview: aidw.py status
# ---------------------------------------------------------------------------

def status_data(cfg: dict, catalog: dict) -> dict:
    """Quick snapshot (without calling the CLIs): context, install, active demands with each one's worktree and
    what needs attention. The full diagnosis is `doctor`."""
    ctx = load_context(cfg, Report(quiet=True))
    manifest = load_manifest()
    claude = {"installed": bool(manifest.get("plugins"))}
    if claude["installed"]:
        plug = build_plugin(cfg, catalog, Report(quiet=True)) if cfg["provider"]["name"] == "claude" else None
        claude.update(version=manifest.get("version"), sources=plug["version"] if plug else None,
                      cli=installed_plugins().get(manifest["plugins"][-1], "") if manifest.get("cli", True) else None,
                      cli_done=manifest.get("cli_done", True), context=manifest.get("context"))
    codex = {"installed": bool(manifest.get("codex"))}
    if codex["installed"]:
        files = manifest["codex"].get("files", {})
        codex.update(files=len(files), missing=sum(not Path(k).is_file() for k in files))
    reg = load_registry()["worktrees"]
    demands = demand_list(cfg, active_only=True)
    known = {d["id"] for d in demand_list(cfg)}
    for d in demands:
        d["worktrees"] = [{**e, **worktree_state(e)} for e in reg if e["status"] == "active" and e["demand"] == d["id"]]
    attention = []
    active_ids = {d["id"] for d in demands}
    for e in reg:
        if e["status"] != "active" or e["demand"] in active_ids:
            continue
        state = worktree_state(e)
        if not state["exists"]:
            attention.append(f"orphan worktree of {e['demand']} (the folder is gone): `aidw.py worktree cleanup`")
        elif e["demand"] in known:
            pending = state.get("error") or ("has uncommitted changes" if state["dirty"] else
                                             "has unpublished commits" if state["ahead"] and not state["published"]
                                             else "")
            attention.append(f"worktree of finished demand {e['demand']} ({e['path']}) " +
                             (f"{pending}: check before removing" if pending else
                              f"can go: `aidw.py worktree remove {e['demand']}`"))
        elif e.get("context") == (ctx["name"] if ctx else None):
            attention.append(f"worktree of {e['demand']} ({e['path']}) without demand.json: "
                             f"`aidw.py demand set {e['demand']} --status active` or `worktree remove`")
    notes_dir = kb_dir(ctx) / KB_TYPES["demanda"] if kb_dir(ctx) else None
    for d in demand_list(cfg) if notes_dir else []:
        if (d["status"] == "done" and any(f for n in legacy_names("artifact", "learnings-") for f in Path(d["folder"]).glob(n + "*.md"))
                and not (notes_dir / f"{d['id']}.md").is_file()):
            attention.append(f"finished demand {d['id']} has learnings that did not go to the knowledge "
                             "base: run `/aidw:done` in one of its sessions")
    if claude["installed"] and ctx and claude.get("context") != ctx["name"]:
        attention.append(f"the plugin was installed with context {claude.get('context')!r} and the active one is "
                         f"{ctx['name']!r}: `aidw.py install`")
    return {"context": {"name": ctx["name"], "description": ctx["description"]} if ctx else None,
            "state_dir": state_dir(ctx).as_posix(), "claude": claude, "codex": codex, "demands": demands,
            "attention": attention}


def status_command(cfg: dict, catalog: dict, as_json: bool) -> int:
    data = status_data(cfg, catalog)
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    ctx = data["context"]
    print(f"AiDW — context {ctx['name']}: {ctx['description']}" if ctx else "AiDW — no active context")
    rep = Report()
    heading("Install")
    c = data["claude"]
    if not c["installed"]:
        rep.info("Claude: not installed for every folder (`aidw.py install`)")
    elif c.get("cli") is not None and not c["cli_done"]:
        rep.warn("Claude: the last install stopped at Claude Code (plugin or MCP): `aidw.py install`")
    elif c.get("sources") and c["sources"] != c["version"]:
        rep.warn(f"Claude: the sources changed since the install ({c['version']} → {c['sources']}): "
                 "`aidw.py install`")
    elif c.get("cli") is not None and c["cli"] != c["version"]:
        rep.warn(f"Claude: Claude has plugin {c['cli'] or '(missing)'} and the generated one is {c['version']}: "
                 "`aidw.py install`")
    else:
        rep.ok(f"Claude: plugin {plugin_name()} {c['version']}, up to date")
    x = data["codex"]
    if not x["installed"]:
        rep.info("Codex: not installed (`aidw.py install --provider codex`)")
    elif x["missing"]:
        rep.warn(f"Codex: {x['missing']} of {x['files']} AiDW files disappeared: `aidw.py install --provider codex`")
    else:
        rep.ok(f"Codex: {x['files']} files (agents and skills)")
    heading(f"Active demands ({len(data['demands'])})")
    if not data["demands"]:
        print(f"  none in {data['state_dir']}")
    for d in data["demands"]:
        print(f"  {d['id']:<16} {d['status'] or '—':<7} {d['step'] or '—':<15} {(d['updated'] or '')[:16]:<17} {d['title']}")
        if d.get("note"):
            print(f"  {'':<16} note: {d['note']}")
        for w in d["worktrees"]:
            if not w["exists"]:
                state = "the folder is gone"
            elif w.get("error"):
                state = w["error"]
            else:
                state = ("with changes" if w["dirty"] else "clean") + f", {w['ahead']} commit(s) ahead of the base" + \
                        (" (published)" if w["ahead"] and w["published"] else "")
            print(f"  {'':<16} {w['path']} ({w['branch']}): {state}")
        if not d["worktrees"]:
            print(f"  {'':<16} no worktree (read-only or not created yet)")
    if data["attention"]:
        heading("Attention")
        for a in data["attention"]:
            rep.warn(a)
    if data["demands"]:
        print("\nResume: `aidw.py open --demand <id>` (Claude) or `--provider codex`.")
    return 0


# ---------------------------------------------------------------------------
# Contexts: aidw.py context list / check / use / create (context-* skills)
# ---------------------------------------------------------------------------

def remote_host(url: str | None) -> str | None:
    """Only the remote's host: the URL may have an embedded user/token and is never shown."""
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
        return {**info, "ok": False, "error": f"invalid context.toml: {exc}"}
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
    """Validates a context as if it were active: full build, its own repository, an exclusive state folder."""
    if name not in list_contexts():
        return {"ok": False, "errors": [f"context {name!r} does not exist in {rel(CONTEXTS_DIR)}/"], "warnings": []}
    test_cfg = json.loads(json.dumps(cfg))
    test_cfg["context"]["active"] = name
    rep = Report(quiet=True)
    build(test_cfg, catalog, rep)
    errors, warnings = list(rep.errors), list(rep.warnings)
    ctx = load_context(test_cfg, Report(quiet=True))
    kb = kb_check(ctx)
    errors += [f"knowledge base: {e}" for e in kb["errors"]]
    warnings += [f"knowledge base: {w}" for w in kb["warnings"]]
    warnings += upstream_check(ctx)
    st = context_status(cfg, name)
    if not st.get("git"):
        warnings.append(f"{rel(CONTEXTS_DIR / name)} is not its own Git repository (run `git init` in it)")
    if not st.get("ignored_by_aidw"):
        errors.append(f"{rel(CONTEXTS_DIR / name)} is NOT in the AiDW .gitignore (the private content would leak)")
    mine = st.get("state_dir")
    for other in list_contexts():
        if other != name and context_status(cfg, other).get("state_dir") == mine:
            errors.append(f"state_dir {mine!r} is the same as context {other!r}'s: each context needs its own folder")
    return {"ok": not errors, "errors": errors, "warnings": warnings, **{k: st.get(k) for k in ("description", "systems")}}


def upstream_ref(repo: str, up: dict) -> str:
    """The ref an upstream is compared against: `origin/<branch>` when the context names the branch, else the
    tracking branch of the checkout (`@{u}`), else HEAD (a repository without a remote)."""
    if up.get("branch"):
        return f"origin/{up['branch']}"
    tracking = git_out(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    return tracking or "HEAD"


def upstream_check(ctx: dict | None, fetch: bool = False) -> list[str]:
    """[upstream.<name>]: an outside repository the context summarizes (e.g. the team's code guide). Warns when the
    remote has commits after `synced` (the copies in the context fell behind) and when the local checkout is behind
    the remote (agents that read its files read old rules). `fetch` refreshes the remote ref first."""
    warnings = []
    for name, up in (ctx or {}).get("upstream", {}).items():
        repo, synced, covers = up.get("repo", ""), up.get("synced", ""), ", ".join(up.get("covers", [])) or "context"
        if not Path(repo).is_dir():
            warnings.append(f"upstream {name}: {repo} does not exist on this machine (cannot check {covers})")
            continue
        if fetch:
            try:
                fetched = subprocess.run(["git", "-C", repo, "fetch", "--quiet"], capture_output=True, text=True,
                                         encoding="utf-8", errors="replace", timeout=60)
                if fetched.returncode:
                    warnings.append(f"upstream {name}: `git fetch` failed in {repo} (network/VPN?) — compared with "
                                    f"the last fetched state")
            except subprocess.TimeoutExpired:
                warnings.append(f"upstream {name}: `git fetch` timed out in {repo} — compared with the last fetched "
                                f"state")
        ref = upstream_ref(repo, up)
        if not synced:
            warnings.append(f"upstream {name}: `synced` is missing (the commit of {repo} that {covers} reflects)")
        else:
            log = git_proc(repo, "log", "--format=%h %ad %s", "--date=short", f"{synced}..{ref}")
            if log.returncode:
                warnings.append(f"upstream {name}: the `synced` commit {synced[:10]} does not exist in {repo} "
                                f"(fetch?)")
            elif log.stdout.strip():
                new = log.stdout.strip().splitlines()
                warnings.append(f"upstream {name}: {ref} has {len(new)} commit(s) after {synced[:10]} "
                                f"(e.g. {'; '.join(new[:3])}) — recheck {covers} and update `synced`")
        if ref != "HEAD":
            behind = git_out(repo, "rev-list", "--count", f"HEAD..{ref}")
            if behind and behind != "0":
                warnings.append(f"upstream {name}: the local checkout of {repo} is {behind} commit(s) behind {ref} — "
                                f"whoever reads its files reads old rules; pull it (`git -C {repo} pull --ff-only`)")
    return warnings


def upstream_command(cfg: dict, args: argparse.Namespace) -> int:
    """`context upstream`: fetches and checks the active context's upstreams (cheap; run at the start of a demand)."""
    ctx = load_context(cfg, Report(quiet=True))
    warnings = upstream_check(ctx, fetch=not args.no_fetch)
    names = list((ctx or {}).get("upstream", {}))
    if args.json:
        print(json.dumps({"ok": not warnings, "upstreams": names, "warnings": warnings}, ensure_ascii=False, indent=2))
        return 0
    if not names:
        print("The active context declares no [upstream.*].")
    for w in warnings:
        print(f"[warn]  {w}")
    if names and not warnings:
        print(f"[ok]    up to date: {', '.join(names)}")
    return 0


def set_active_context(name: str) -> None:
    """Changes only the `active` line of the [context] section of aidw.config.toml (the comments stay)."""
    text = CONFIG_FILE.read_text(encoding="utf-8")
    pattern = re.compile(r"(^\[context\][^\[]*?^active\s*=\s*)\"[^\"]*\"", re.M | re.S)
    if pattern.search(text):
        text = pattern.sub(lambda m: m.group(1) + json.dumps(name), text, count=1)
    else:
        text = text.rstrip("\n") + f"\n\n[context]\nactive = {json.dumps(name)}\n"
    CONFIG_FILE.write_text(text, encoding="utf-8", newline="\n")


def context_command(cfg: dict, catalog: dict, args: argparse.Namespace) -> int:
    action = args.ctx_action
    if action == "upstream":
        return upstream_command(cfg, args)
    if action == "list":
        items = context_list(cfg)
        if args.json:
            print(json.dumps({"ok": True, "active": cfg["context"]["active"] or None, "contexts": items},
                             ensure_ascii=False, indent=2))
            return 0
        if not items:
            print("No context in contexts/. Create one with `/aidw:context create` (or `aidw.py context create`).")
        for c in items:
            mark = "*" if c["active"] else " "
            if not c["ok"]:
                print(f" {mark} {c['name']:<16} [error] {c['error']}")
                continue
            repo = ("own git" + (f", remote {c['remote']}" if c["remote"] else ", no remote")) if c["git"] else \
                "NO git repository"
            print(f" {mark} {c['name']:<16} {c['description']}")
            print(f"   {'':<16} {repo}; systems: {', '.join(c['systems']) or 'none'}; "
                  f"plugin {'installed' if c['plugin_installed'] else 'not installed'}")
        print(f"\nActive: {cfg['context']['active'] or 'none'}")
        return 0
    if action == "check":
        result = context_check(cfg, catalog, args.name)
    elif action == "create":
        name = args.name.strip().lower()
        if not SLUG_RE.match(name) or name in RESERVED_NAMES:
            result = {"ok": False, "errors": [f"invalid name {name!r} (lowercase, digits and hyphen)"], "warnings": []}
        elif (CONTEXTS_DIR / name).exists():
            result = {"ok": False, "errors": [f"{rel(CONTEXTS_DIR / name)} already exists"], "warnings": []}
        elif args.language and not LANGUAGE_TAG_RE.match(args.language.strip()):
            result = {"ok": False, "errors": [f"invalid language tag {args.language!r} (BCP-47, e.g. en, pt-BR)"],
                      "warnings": []}
        else:
            d = create_context(name, args.description or name, split_answer(args.mcp or ""), split_answer(args.env or ""),
                               language=(args.language or "").strip() or ui_language(cfg))
            result = {"ok": True, "errors": [], "warnings": [], "path": d.as_posix(),
                      "note": "own git repository created (no remote). Fill in context.toml and run "
                              f"`aidw.py context check {name}`."}
    else:  # use
        check = context_check(cfg, catalog, args.name) if args.name else {"ok": True, "errors": [], "warnings": []}
        previous = cfg["context"]["active"]
        open_demands = [d["id"] for d in demand_list(cfg, active_only=True)] if previous != args.name else []
        if open_demands:
            check["warnings"].append(f"active demands in context {previous!r} are paused: {', '.join(open_demands)}")
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
            if not applied:  # aidw.config.toml never stays pointing to an environment that was not generated
                set_active_context(previous)
            result = {"ok": applied and installed is not False,
                      "errors": [] if applied else [f"apply failed; active context kept as {previous!r}"],
                      "warnings": check["warnings"], "active": args.name or None,
                      "plugin": plugin_name(load_context(new_cfg, Report(quiet=True))) if installed else None,
                      "log_tail": out.getvalue().strip().splitlines()[-3:]}
            if installed is False:
                result["errors"].append("install failed — run `python aidw.py install` to see the error")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for e in result.get("errors", []):
            print(f"[error] {e}")
        for w in result.get("warnings", []):
            print(f"[warn]  {w}")
        if result["ok"]:
            print(f"[ok]    {action} {args.name or ''}".rstrip() +
                  (f" — {result['note']}" if result.get("note") else "") +
                  (f" — plugin {result['plugin']}; open a new chat" if result.get("plugin") else "") +
                  (" — open a new chat" if action == "use" and not result.get("plugin") else ""))
    return 0 if result["ok"] else 1


# ---------------------------------------------------------------------------
# The context's knowledge base ([knowledge] dir): notes linked by [[links]], an Obsidian vault.
# aidw.py kb show / search / check / index
# ---------------------------------------------------------------------------

# type → folder where the note lives (the order is the index's)
KB_TYPES = {"sistema": "sistemas", "componente": "componentes", "integracao": "integracoes", "conceito": "conceitos",
            "ambiente": "ambiente", "decisao": "decisoes", "demanda": "demandas"}
KB_TITLES = {"sistema": "Systems", "componente": "Components", "integracao": "Integrations and contracts",
             "conceito": "Domain concepts", "ambiente": "Environment and operations", "decisao": "Decisions",
             "demanda": "Demands"}
KB_SPECIAL = {"index", "readme"}                     # the generated index and the conventions: outside the note rules
KB_NEEDS_SOURCE = set(KB_TYPES) - {"conceito", "demanda"}
KB_NEEDS_KEYWORDS = {"sistema", "componente", "integracao", "ambiente"}  # technical notes: searched by identifier
KB_MAX_LINES = 150       # above this, whoever reads the note pays a lot: split it
KB_STALE_DAYS = 180      # note not checked for longer than this: recheck in the code (demand and decision don't age)
WIKILINK_RE = re.compile(r"!?\[\[([^\]|#^]+)(?:[#^][^\]|]*)?(?:\|[^\]]*)?\]\]")
KB_SECRET_RE = re.compile(
    r"\b(password|pwd|senha|secret|client_secret|api_?key)\s*=\s*[^\s;'\"<>{}]{4,}"
    r"|\bbearer\s+[A-Za-z0-9._~+/-]{20,}"
    r"|\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    r"|\b(data source|server)\s*=[^;\n]+;[^\n]*\b(user id|uid)\s*=", re.I)
KB_CPF_RE = re.compile(r"\b(?!000\.000\.000)\d{3}\.\d{3}\.\d{3}-\d{2}\b")


KB_COLORS = {"sistema": 5012441, "componente": 2860442, "integracao": 15241530, "conceito": 10185944,
             "ambiente": 8034890, "decisao": 14242639, "demanda": 13214247}


def obsidian_config(kb_rel: str, ignore: list[str]) -> dict[str, dict]:
    """graph.json (one color per note type, plus policies and guides; index and READMEs left out) and app.json
    (short `[[name]]` links, excluded folders) of the vault in the context folder."""
    groups = [{"query": f"path:{kb_rel}/{folder}", "color": {"a": 1, "rgb": KB_COLORS[tipo]}}
              for tipo, folder in KB_TYPES.items()]
    groups += [{"query": "path:policies", "color": {"a": 1, "rgb": 12597547}},
               {"query": "path:agents OR path:skills", "color": {"a": 1, "rgb": 7701657}},
               {"query": "path:shared OR path:reference", "color": {"a": 1, "rgb": 11184810}}]
    return {"graph.json": {"search": "-file:index -file:README", "showOrphans": True, "colorGroups": groups,
                           "collapse-color-groups": False, "nodeSizeMultiplier": 1.2, "repelStrength": 12,
                           "linkDistance": 220},
            "app.json": {"newLinkFormat": "shortest", "useMarkdownLinks": False, "alwaysUpdateLinks": True,
                         "userIgnoreFilters": ignore}}


def kb_dir(ctx: dict | None) -> Path | None:
    d = (ctx or {}).get("knowledge", {}).get("dir")
    return ctx["dir"] / d if d else None


def kb_frontmatter(text: str) -> tuple[dict, str]:
    """Simple YAML frontmatter: `key: value`, lists `[a, b]` or as a block (`  - a`, as Obsidian writes them)."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    meta: dict = {}
    current = None
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.lstrip().startswith("- ") and current is not None:
            if not isinstance(meta.get(current), list):
                meta[current] = []
            meta[current].append(line.lstrip()[2:].strip().strip("'\""))
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        current, value = key.strip(), value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[current] = [v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[current] = value.strip("'\"") if value else []
    return meta, text[end + 4:].lstrip("-").lstrip("\n")


def kb_key(target: str) -> str:
    """`[[sistemas/Portal.md]]` → `portal`: Obsidian finds the note by its name, in any folder."""
    name = target.strip().replace("\\", "/").split("/")[-1]
    return (name[:-3] if name.lower().endswith(".md") else name).strip().lower()


def kb_norm(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def kb_load(base: Path) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """({key: note}, {repeated key: [paths]}). Folders starting with `.` (the .obsidian) are left out."""
    notes: dict[str, dict] = {}
    dups: dict[str, list[str]] = {}
    for p in sorted(base.rglob("*.md")):
        relp = p.relative_to(base)
        if any(part.startswith(".") for part in relp.parts):
            continue
        meta, body = kb_frontmatter(p.read_text(encoding="utf-8"))
        title = next((ln[2:].strip() for ln in body.splitlines() if ln.startswith("# ")), p.stem)
        links = []
        for m in WIKILINK_RE.finditer(body):
            target = m.group(1)
            if "." in target.split("/")[-1] and not target.lower().endswith(".md"):
                continue  # attachment (image, pdf)
            if kb_key(target) not in links:
                links.append(kb_key(target))
        note = {"key": p.stem.lower(), "path": p, "rel": relp.as_posix(), "meta": meta, "body": body,
                "title": title, "links": links}
        if note["key"] in notes:
            dups.setdefault(note["key"], [notes[note["key"]]["rel"]]).append(note["rel"])
        else:
            notes[note["key"]] = note
    for n in notes.values():
        n["backlinks"] = sorted(k for k, o in notes.items() if n["key"] in o["links"] and k != n["key"])
    return notes, dups


def kb_list(meta: dict, key: str) -> list[str]:
    v = meta.get(key, [])
    return v if isinstance(v, list) else [v] if v else []


def kb_check(ctx: dict | None) -> dict:
    base = kb_dir(ctx)
    if base is None:
        return {"ok": True, "errors": [], "warnings": [], "notes": 0}
    if not base.is_dir():
        return {"ok": False, "errors": [f"[knowledge] dir points to {rel(base)}, which does not exist"], "warnings": [],
                "notes": 0}
    notes, dups = kb_load(base)
    errors = [f"repeated name {k!r}: {', '.join(paths)} (the [[link]] becomes ambiguous)" for k, paths in dups.items()]
    warnings: list[str] = []
    systems = set(ctx.get("systems", {}))
    outside = kb_outside(ctx)
    for key in sorted(set(notes) & set(outside) - KB_SPECIAL):
        warnings.append(f"{notes[key]['rel']}: the name {key!r} also exists in {', '.join(outside[key])} — with the "
                        "vault in the context folder the [[link]] becomes ambiguous in Obsidian; rename the note")
    index = base / "index.md"
    if index.is_file() and index.read_text(encoding="utf-8").replace("\r\n", "\n") != kb_index_text(ctx, notes):
        warnings.append("index.md out of date: run `aidw.py kb index`")
    for n in notes.values():
        if n["key"] in KB_SPECIAL:
            continue
        where, meta = n["rel"], n["meta"]
        tipo = meta.get("tipo")
        if tipo not in KB_TYPES:
            errors.append(f"{where}: invalid `tipo` {tipo!r} (use: {', '.join(KB_TYPES)})")
        elif n["rel"].split("/")[0] != KB_TYPES[tipo]:
            warnings.append(f"{where}: tipo {tipo!r} lives in {KB_TYPES[tipo]}/")
        if not meta.get("resumo"):
            errors.append(f"{where}: `resumo` is missing (one line)")
        if tipo in KB_NEEDS_SOURCE and not kb_list(meta, "fontes"):
            errors.append(f"{where}: `fontes` is missing (where the fact came from)")
        if tipo in KB_NEEDS_KEYWORDS and not kb_list(meta, "palavras-chave"):
            warnings.append(f"{where}: `palavras-chave` is missing (identifiers, config keys, routes, tables and "
                            "synonyms someone would type to find this note)")
        stamp = str(meta.get("atualizado", ""))
        try:
            checked = date.fromisoformat(stamp) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp) else None
        except ValueError:
            checked = None
        if checked is None:
            warnings.append(f"{where}: `atualizado: YYYY-MM-DD` is missing")
        elif tipo not in ("demanda", "decisao") and (date.today() - checked).days > KB_STALE_DAYS:
            warnings.append(f"{where}: last checked on {stamp} (more than {KB_STALE_DAYS} days ago) — "
                            "recheck in the code and update the date")
        size = len(n["path"].read_text(encoding="utf-8").splitlines())
        if size > KB_MAX_LINES:
            warnings.append(f"{where}: {size} lines (suggested maximum {KB_MAX_LINES}) — split into linked notes "
                            "(e.g. one part becomes an integration or a component) so readers pay less")
        unknown = [s for s in kb_list(meta, "sistemas") if s not in systems]
        if unknown:
            errors.append(f"{where}: `sistemas` cites {', '.join(unknown)}, which is not in [systems] of context.toml")
        for target in n["links"]:
            if target not in notes and target not in outside:
                errors.append(f"{where}: broken link [[{target}]]")
        if not [k for k in n["links"] if k not in KB_SPECIAL] and not [k for k in n["backlinks"] if k not in KB_SPECIAL]:
            warnings.append(f"{where}: orphan note (no link to or from another note)")
        text = n["path"].read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if KB_SECRET_RE.search(line):
                errors.append(f"{where}:{i}: looks like a secret (password, token or connection string) — remove it "
                              "from the note")
            elif KB_CPF_RE.search(line):
                warnings.append(f"{where}:{i}: looks like a CPF — personal data does not go into the base")
    for key in sorted(systems):
        if key not in notes or notes[key]["meta"].get("tipo") != "sistema":
            warnings.append(f"system {key!r} has no note (create {KB_TYPES['sistema']}/{key}.md)")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "notes": len(notes)}


def kb_outside(ctx: dict) -> dict[str, list[str]]:
    """The context's other .md files ({name: [paths]}): with the Obsidian vault in the context folder, a note may
    cite a policy or a guide by [[name]]. The base, hidden folders and the demands' state are left out."""
    base, state = kb_dir(ctx), state_dir(ctx)
    found: dict[str, list[str]] = {}
    for p in sorted(ctx["dir"].rglob("*.md")):
        relp = p.relative_to(ctx["dir"])
        if (any(part.startswith(".") for part in relp.parts) or base in p.parents
                or state == p.parent or state in p.parents):
            continue
        found.setdefault(p.stem.lower(), []).append(relp.as_posix())
    return found


def kb_index(ctx: dict) -> Path:
    path = kb_dir(ctx) / "index.md"
    path.write_text(kb_index_text(ctx, kb_load(kb_dir(ctx))[0]), encoding="utf-8", newline="\n")
    return path


def kb_index_text(ctx: dict, notes: dict[str, dict]) -> str:
    """index.md: the notes by type, with their summary, and the glossary of the concepts (field `evitar`)."""
    readme = (kb_dir(ctx) / "README").relative_to(ctx["dir"]).as_posix()  # a path: there are other READMEs in the vault
    lines = ["---", "tipo: indice", f"resumo: Map of the knowledge base of context {ctx['name']}.", "---", "",
             f"# Knowledge base — {ctx['description']}", "",
             f"<!-- Generated by `python aidw.py kb index`; do not edit. Conventions: [[{readme}|README]]. -->", ""]
    for tipo, title in KB_TITLES.items():
        group = sorted((n for n in notes.values() if n["meta"].get("tipo") == tipo),
                       key=lambda n: n["key"], reverse=(tipo == "demanda"))
        if not group:
            continue
        lines += [f"## {title} ({len(group)})", ""]
        lines += [f"- [[{n['key']}]] — {n['meta'].get('resumo', '')}".rstrip(" —") for n in group]
        lines.append("")
    glossary = sorted((n for n in notes.values() if n["meta"].get("tipo") == "conceito"), key=lambda n: n["key"])
    if any(kb_list(n["meta"], "evitar") for n in glossary):
        lines += ["## Glossary", "", "| Term | Do not use |", "|---|---|"]
        lines += [f"| [[{n['key']}\\|{n['title']}]] | {', '.join(kb_list(n['meta'], 'evitar')) or '—'} |"
                  for n in glossary]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def kb_find(notes: dict[str, dict], name: str) -> dict | None:
    """By file name, system key, path, alias or title."""
    key = kb_key(name)
    if key in notes:
        return notes[key]
    wanted = kb_norm(name.strip())
    for n in notes.values():
        if wanted in {kb_norm(a) for a in kb_list(n["meta"], "aliases")} | {kb_norm(n["title"])}:
            return n
    return None


def kb_brief(n: dict) -> dict:
    return {"key": n["key"], "path": n["path"].as_posix(), "tipo": n["meta"].get("tipo"),
            "resumo": n["meta"].get("resumo", "")}


def kb_search(notes: dict[str, dict], term: str, limit: int = 15) -> list[dict]:
    """Notes that have all the words (accent- and case-insensitive); title, alias and name weigh more."""
    words = [kb_norm(w) for w in term.split() if w.strip()]
    hits = []
    for n in notes.values():
        if n["key"] == "index":
            continue
        raw = n["path"].read_text(encoding="utf-8").replace("\r\n", "\n")
        text = kb_norm(raw)
        if not words or not all(w in text for w in words):
            continue
        head = kb_norm(" ".join([n["key"], n["title"], *kb_list(n["meta"], "aliases"),
                                 *kb_list(n["meta"], "palavras-chave")]))
        score = sum(text.count(w) for w in words) + 20 * sum(w in head for w in words)
        lines = [(i, ln.strip()) for i, ln in enumerate(raw.splitlines(), 1)
                 if any(w in kb_norm(ln) for w in words) and not ln.startswith("---")]
        hits.append({**kb_brief(n), "score": score,
                     "lines": [{"line": i, "text": t[:200]} for i, t in lines[:4]]})
    return sorted(hits, key=lambda h: -h["score"])[:limit]


# Headings read from the demand artifacts: the English one and the old Portuguese ones.
KB_SECTION_RE = re.compile(r"^##\s+(?:Knowledge base|Knowledge|Base de conhecimento|Conhecimento)\s*$", re.M | re.I)
DECISIONS_RE = re.compile(r"^##\s+(?:Decisions made|Decisions taken|Decis(?:ões|oes) tomadas)\s*$", re.M | re.I)


def md_section(text: str, heading: re.Pattern) -> str:
    """The body of the `## …` section that matches `heading`, up to the next `## ` (or the end)."""
    m = heading.search(text)
    if not m:
        return ""
    rest = text[m.end():]
    nxt = re.search(r"^##\s", rest, re.M)
    return (rest[:nxt.start()] if nxt else rest).strip()


def kb_collect(ctx: dict | None, demand: str, out) -> int:
    """Gathers in a single file what the demand learned, so /aidw:done starts from it instead of rereading every
    artifact: the *Knowledge base* sections of the agents' reports, the `learnings-<id>.md` (what was born in the
    chat), the notes the summary cited and the plan's decisions. Writes `collect-<id>.md` in the demand folder."""
    folder = state_dir(ctx) / demand
    if not folder.is_dir():
        return out({"ok": False, "errors": [f"demand folder does not exist: {folder.as_posix()}"]},
                   [f"[error] demand folder does not exist: {folder.as_posix()}"])
    skip = ("collect-", *legacy_names("file", "metrics.md"), *legacy_names("file", "orchestrator-metrics.md"))
    files = sorted(f for f in folder.glob("*.md") if not f.name.startswith(skip))
    parts: list[str] = []
    sources: list[str] = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        kind = artifact_kind(f.name)
        if kind == "learnings-":
            body = text.strip()
        elif kind == "summary-":
            body = md_section(text, KB_SECTION_RE)
            body = f"(notes cited by the summary)\n{body}" if body else ""
        elif kind == "plan-" and not re.search(r"-v\d+\.md$", f.name):
            found = [x for x in (md_section(text, DECISIONS_RE), md_section(text, KB_SECTION_RE)) if x]
            body = "\n\n".join(found)
        else:
            body = md_section(text, KB_SECTION_RE)
        if body:
            parts += [f"## {f.name}", "", body, ""]
            sources.append(f.name)
    target = folder / f"collect-{demand}.md"
    header = [f"# What demand {demand} learned", "",
              "Generated by `aidw.py kb collect` for `/aidw:done`: only the *Knowledge base* sections of the reports, "
              "the `learnings`, the summary's notes and the plan's decisions. Open the whole artifact only when a fact "
              "needs more context.", ""]
    target.write_text("\n".join(header + (parts or ["Nothing recorded in the demand's artifacts.", ""])),
                      encoding="utf-8", newline="\n")
    return out({"ok": True, "path": target.as_posix(), "sources": sources},
               [f"[ok]    {target.as_posix()} — {len(sources)} source(s): {', '.join(sources) or 'none'}"])


def kb_command(cfg: dict, args: argparse.Namespace) -> int:
    ctx = load_context(cfg, Report(quiet=True))
    base = kb_dir(ctx)
    action = args.kb_action

    def out(result: dict, text: list[str]) -> int:
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("\n".join(text))
        return 0 if result.get("ok", True) else 1

    if action == "collect":
        return kb_collect(ctx, args.demand, out)
    if base is None or not base.is_dir():
        why = ("no active context" if not ctx else
               f"context {ctx['name']} has no [knowledge] dir" if base is None else f"{rel(base)} does not exist")
        return out({"ok": False, "errors": [f"knowledge base unavailable: {why}"]},
                   [f"[error] knowledge base unavailable: {why}"])
    if action == "check":
        r = kb_check(ctx)
        return out(r, [*(f"[error] {e}" for e in r["errors"]), *(f"[warn]  {w}" for w in r["warnings"]),
                       f"[{'ok' if r['ok'] else 'error'}]    {r['notes']} notes in {rel(base)}"])
    if action == "index":
        path = kb_index(ctx)
        return out({"ok": True, "path": path.as_posix()}, [f"[ok]    {rel(path)} regenerated"])
    notes, _ = kb_load(base)
    if action == "search":
        term = " ".join(args.term)
        hits = kb_search(notes, term, args.limit)
        text = [f"{len(hits)} note(s) for {term!r} in {rel(base)}"]
        for h in hits:
            text.append(f"\n[[{h['key']}]] ({h['tipo']}) — {h['resumo']}\n  {h['path']}")
            text += [f"  {ln['line']:>4}: {ln['text']}" for ln in h["lines"]]
        return out({"ok": True, "term": term, "hits": hits}, text)
    note = kb_find(notes, args.name)
    if note is None:
        hits = kb_search(notes, args.name, 5)
        sug = ", ".join(f"[[{h['key']}]]" for h in hits) or "none"
        return out({"ok": False, "errors": [f"note {args.name!r} not found"], "suggestions": hits},
                   [f"[error] note {args.name!r} not found. Similar: {sug}"])
    outside = kb_outside(ctx)

    def target(k: str) -> dict:
        if k in notes:
            return kb_brief(notes[k])
        if k in outside:  # policy, guide, agent: a context file outside the base
            return {"key": k, "outside": [(ctx["dir"] / p).as_posix() for p in outside[k]]}
        return {"key": k, "missing": True}

    links = [target(k) for k in note["links"]]
    back = [kb_brief(notes[k]) for k in note["backlinks"] if k not in KB_SPECIAL]
    result = {"ok": True, **kb_brief(note), "meta": note["meta"], "links": links, "backlinks": back}
    if not args.json:
        def item(b: dict) -> str:
            if b.get("missing"):
                return f"- [[{b['key']}]] — BROKEN"
            if b.get("outside"):
                return f"- [[{b['key']}]] (context, outside the base) — `{b['outside'][0]}`"
            resumo = b["resumo"] if len(b["resumo"]) <= 110 else b["resumo"][:107].rstrip() + "…"
            return f"- [[{b['key']}]] ({b['tipo'] or '—'}) {resumo} — `{notes[b['key']]['rel']}`"
        body = note["path"].read_text(encoding="utf-8").replace("\r\n", "\n").rstrip()
        if args.brief:  # only the note: its links are already in its text; of who cites it, only the count
            print("\n".join([f"<!-- {note['path'].as_posix()} -->", body, "",
                              f"(cited by {len(back)} note(s): `kb show {note['key']}` lists them)"]))
            return 0
        text = [f"<!-- {note['path'].as_posix()} (paths below relative to {base.as_posix()}) -->", body, "",
                f"## Links of this note ({len(links)})"]
        text += [item(l) for l in links] or ["- none"]
        text += ["", f"## Cited by ({len(back)})"]
        text += [item(b) for b in back] or ["- nobody"]
        print("\n".join(text))
        return 0
    return out(result, [])


# ---------------------------------------------------------------------------
# Delegate: one headless agent per task
# ---------------------------------------------------------------------------

def final_json(text: str) -> dict | None:
    """The agent's final JSON: the top-level object with `state` that ends last
    (inner items, like those of `operations`, do not count)."""
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
        return "no current data"
    if not w or w.get("pct") is None:
        return "?"
    when = f" (resets {datetime.fromtimestamp(w['resets_at']).strftime(fmt)})" if w.get("resets_at") else ""
    return f"{w['pct']:.0f}%{when}"


def claude_limits(events: list[dict]) -> str:
    for e in reversed(events):
        if e.get("type") == "rate_limit_event":
            windows = (e.get("rate_limit_info") or {}).get("unifiedWindows") or {}
            out = {}
            for key, name in (("five_hour", "5h"), ("seven_day", "week")):
                w = windows.get(key) or {}
                if w.get("utilization") is not None:
                    out[name] = {"pct": round(w["utilization"] * 100), "resets_at": w.get("resetsAt")}
            if out:
                return (f"Claude 5h {fmt_window(out.get('5h'), '%H:%M')} · week "
                        f"{fmt_window(out.get('week'), '%d/%m %H:%M')}")
    return "Claude limits ?"


def codex_limits() -> str:
    """ChatGPT plan windows from the most recent event of the Codex sessions."""
    root = CODEX_HOME / "sessions"
    try:
        files = sorted(root.rglob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)[:3]
    except OSError:
        return "Codex limits ?"
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
                name = {300: "5h", 10080: "week", 43200: "month"}.get(minutes, f"{minutes // 60}h")
                stale = bool(w.get("resets_at")) and w["resets_at"] < time.time()
                parts.append(f"{name} " + fmt_window({"pct": w["used_percent"], "resets_at": w.get("resets_at"),
                                                      "stale": stale}, "%H:%M" if name == "5h" else "%d/%m %H:%M"))
            if parts:
                plan = f" ({rl['plan_type']})" if rl.get("plan_type") else ""
                return f"Codex{plan} " + " · ".join(parts)
    return "Codex limits ?"


METRICS_LEVEL_RE = re.compile(r"^\|\s*(?:Date|Data)\s*\|.*\|\s*(?:Level|N[ií]vel)\s*\|", re.M | re.I)


def metrics_has_level(text: str) -> bool:
    """A metrics.md from before flow v3 has a Level column (`| Date | Agent | Level | …`); new files do not."""
    return bool(METRICS_LEVEL_RE.search(text))


def append_metrics(demand: Path, row: dict) -> None:
    f = demand_file(demand, "metrics.md")
    head = ("| Date | Agent | Model | Effort | Label | State | Turns or tools | Duration | Input tokens "
            "(with cache) | Output tokens | Cost (USD) | Plan limits |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    cost = f"{row['cost_usd']:.4f}" if row["cost_usd"] is not None else "—"

    def num(v) -> str:
        return f"{v:,}" if isinstance(v, int) else "—"

    # an old file keeps its Level column, so its rows stay aligned
    level = "— | " if f.exists() and metrics_has_level(f.read_text(encoding="utf-8", errors="replace")) else ""
    line = (f"| {row['date']} | {row['agent']} | {level}{row['model']} | {row['effort'] or '—'} | "
            f"{row['label']} | {row['state']} | {num(row['turns'])} | {row['duration_s']}s | "
            f"{num(row['tokens_in'])} | {num(row['tokens_out'])} | {cost} | {row['limits']} |\n")
    if not f.exists():
        f.write_text("# Demand metrics\n\nReal usage of each delegation (recorded by "
                     "`aidw.py delegate` or `aidw.py record`). For Claude's native subagent, the input "
                     "is the total tokens and the output is —.\n\n" + head, encoding="utf-8", newline="\n")
    elif not f.read_bytes().endswith(b"\n"):
        line = "\n" + line  # file edited by hand without the trailing newline
    with f.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(line)


def recorded_by_mod(demand: Path, row: dict) -> dict | None:
    """The delegation the aidw-mods mod already recorded (with the numbers) among the last lines of metrics.md: a
    `record` without numbers would repeat the line, empty. Returns its turns, duration and tokens."""
    f = demand_file(demand, "metrics.md")
    if not f.exists():
        return None
    text = f.read_text(encoding="utf-8")
    o = 1 if metrics_has_level(text) else 0  # the old Level column shifts the cells after Agent
    rows = [r for r in text.splitlines() if r.startswith("| 2")][-3:]
    for r in reversed(rows):
        c = [x.strip() for x in r.strip().strip("|").split("|")]
        if len(c) >= 9 + o and c[0] == row["date"] and c[1] == row["agent"] and c[4 + o] == row["label"] \
                and c[8 + o] != "—":
            num = lambda v: int(v.replace(",", "")) if v.replace(",", "").isdigit() else None
            return {"turns": num(c[6 + o]), "duration_s": num(c[7 + o].rstrip("s")) or 0, "tokens_in": num(c[8 + o])}
    return None


# API price in US$ per million tokens (input, output, cache read), by model id prefix; the first one that matches
# wins. Cache writes cost 2× the input (1h TTL, the Claude Code chat's). A yardstick of the weight on the plan limit,
# not the bill: a subscription has no per-token charge.
API_PRICES = (("claude-opus-5-5", 4, 20, 0.2), ("claude-opus", 5, 25, 0.5), ("claude-sonnet-4", 3, 15, 0.3),
              ("claude-sonnet", 2, 10, 0.2), ("claude-haiku-5-5", 0.1, 0.5, 0.01), ("claude-haiku", 1, 5, 0.1))
ORCH_METRICS = "orchestrator-metrics.md"
# The mods read these tables by position, not by column name.
ORCH_COLS = ("Session", "Started", "Updated", "Model", "Turns", "Duration", "Input", "Cache written",
             "Cache read", "Output", "Equiv. cost (USD)")
STEP_COLS = ("Step", "Turns", "Duration", "Input", "Cache written", "Cache read", "Output", "Equiv. cost (USD)")
NO_STEP = "NO_STEP"   # turns before any step was recorded (old files: SEM_ETAPA)


def api_cost(model: str, tokens_in: int, cache_write: int, cache_read: int, tokens_out: int) -> float | None:
    price = next((p for p in API_PRICES if model.startswith(p[0])), None)
    if price is None:
        return None
    _, inp, out, read = price
    return (tokens_in * inp + cache_write * inp * 2 + cache_read * read + tokens_out * out) / 1_000_000


def record_orchestrator(args: argparse.Namespace) -> int:
    """Adds one turn of the main chat (the orchestrator) to the session-and-model row of the orchestrator metrics
    file."""
    f = demand_file(Path(args.demand).resolve(), ORCH_METRICS)
    session, model = args.session[:8], args.model or "?"
    rows: list[list[str]] = []
    steps: list[list[str]] = []
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == len(ORCH_COLS) and re.fullmatch(r"[0-9a-f-]{4,}", cells[0]):
                rows.append(cells)
            elif len(cells) == len(STEP_COLS) and re.fullmatch(r"[A-Z][A-Z_]*", cells[0]):
                steps.append([NO_STEP if cells[0] == "SEM_ETAPA" else cells[0], *cells[1:]])

    def num(s: str) -> int:
        return int(re.sub(r"\D", "", s) or 0)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    row = next((r for r in rows if r[0] == session and r[3] == model), None)
    if row is None:
        row = [session, now, now, model, "0", "0s", "0", "0", "0", "0", "—"]
        rows.append(row)
    sums = [num(row[4]) + 1, num(row[5]) + round((args.duration_ms or 0) / 1000), num(row[6]) + args.input,
            num(row[7]) + args.cache_write, num(row[8]) + args.cache_read, num(row[9]) + args.output]
    cost = api_cost(model, *sums[2:])
    f.parent.mkdir(parents=True, exist_ok=True)
    row[2:] = [now, model, str(sums[0]), f"{sums[1]}s", *(f"{n:,}" for n in sums[2:]),
               f"{cost:.2f}" if cost is not None else "—"]
    # per step (the step recorded in demand.json when the turn started): adds each turn's cost on its own model
    step = (args.step or "").strip().upper() or NO_STEP
    srow = next((r for r in steps if r[0] == step), None)
    if srow is None:
        srow = [step, "0", "0s", "0", "0", "0", "0", "—"]
        steps.append(srow)
    turn = (args.input, args.cache_write, args.cache_read, args.output)
    ssums = [num(srow[1]) + 1, num(srow[2]) + round((args.duration_ms or 0) / 1000),
             *(num(srow[3 + i]) + turn[i] for i in range(4))]
    tcost = api_cost(model, *turn)
    prev = None if srow[7] == "—" else float(srow[7].replace(",", "."))
    scost = None if tcost is None and prev is None else (prev or 0) + (tcost or 0)
    srow[1:] = [str(ssums[0]), f"{ssums[1]}s", *(f"{n:,}" for n in ssums[2:]),
                f"{scost:.4f}" if scost is not None else "—"]
    f.write_text("# Orchestrator metrics\n\nUsage of the main chat (the orchestrator) by session and model, added on "
                 "every turn by the aidw-mods mod. The cost is the API-price equivalent (cache written at 2× the input), "
                 "a yardstick of the weight on the plan limit, not the bill. The delegations are in metrics.md.\n\n"
                 "| " + " | ".join(ORCH_COLS) + " |\n|" + "---|" * len(ORCH_COLS) + "\n"
                 + "".join("| " + " | ".join(r) + " |\n" for r in rows)
                 + "\n## By step\n\nThe same turns added up by the demand step they happened in.\n\n"
                 "| " + " | ".join(STEP_COLS) + " |\n|" + "---|" * len(STEP_COLS) + "\n"
                 + "".join("| " + " | ".join(r) + " |\n" for r in steps), encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "file": f.as_posix(), "session": session, "model": model, "turns": sums[0],
                      "cost_usd": cost}, ensure_ascii=False))
    return 0


def codex_subagent_usage(task_name: str) -> dict | None:
    """Real tokens, duration and model of the Codex subagent, from its session in ~/.codex/sessions
    (the most recent one whose agent_path ends in /<task_name>)."""
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
    """Records a delegation made with a native subagent: metrics.md + header and summary."""
    if getattr(args, "codex_task", None) and cfg["provider"]["name"] != "codex":
        # a Codex delegation (global install) on a machine whose config is Claude's: Codex models and tokens
        cfg = json.loads(json.dumps(cfg))
        cfg["provider"]["name"] = "codex"
    rep = Report(quiet=True)
    ctx = load_context(cfg, rep)
    resolved = resolve(cfg, catalog, ctx, available_skills(ctx, rep), rep)
    routing = load_routing(rep, ctx)
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
        print(json.dumps({"error": f"unknown agent {args.agent!r}"}, ensure_ascii=False))
        return 2
    a = resolved[role]
    model = model or a["model"]
    if not effort and model.get("efforts"):
        effort = a["effort"]
    if not model.get("efforts"):
        effort = ""
    # flow v3 has no levels: `level` only fills the Level column of an old metrics.md
    row = {"date": date.today().isoformat(), "agent": a["name"], "level": args.level or "—", "model": model["model_id"],
           "effort": effort, "label": args.label, "state": args.state or "missing_state", "turns": None,
           "duration_s": round((args.duration_ms or 0) / 1000), "tokens_in": args.tokens,
           "tokens_out": None, "cost_usd": None, "limits": "—"}
    if args.tool_uses is not None:
        row["turns"] = args.tool_uses  # in the Claude subagent, the column holds the tool calls
    if args.usage_model:  # the mod added up the usage of each subagent response: the equivalent cost at API price
        row["cost_usd"] = api_cost(args.usage_model, args.input, args.cache_write, args.cache_read, args.output)
    if provider == "codex" and args.codex_task:
        usage = codex_subagent_usage(args.codex_task)
        if usage:
            row.update({k: usage[k] for k in ("tokens_in", "tokens_out", "duration_s", "turns")})
            if usage.get("model") and usage["model"] != model["model_id"]:
                row["model"] = usage["model"]
        else:
            rep.warn(f"session of subagent {args.codex_task!r} not found in {CODEX_HOME / 'sessions'}")
        row["limits"] = codex_limits()
    demand = Path(args.demand).resolve()
    demand.mkdir(parents=True, exist_ok=True)
    known = recorded_by_mod(demand, row) if args.tokens is None and not args.codex_task else None
    if known:
        row.update(known)
        rep.warn("the aidw-mods mod already recorded this delegation: nothing was written")
    else:
        append_metrics(demand, row)
    real_id = row["model"] != model["model_id"]
    if real_id:  # the Codex session ran on another model: the header shows the real one
        real = next((m for m in catalog.values() if m["model_id"] == row["model"]), {})
        model = {**model, "name": real.get("name", row["model"]), "label": real.get("label", row["model"]),
                 "model_id": row["model"]}
    head = header({**a, "model": model}, effort)
    if row["tokens_out"] is None:
        tokens = f"{row['tokens_in']:,} tokens" if row["tokens_in"] is not None else "tokens ?"
    else:
        tokens = f"{row['tokens_in']:,} input tokens + {row['tokens_out']:,} output"
    shown = model["name"] + (f" ({row['model']})" if real_id else "")  # same family, different versions
    parts = [f"{a['display']} ({args.label})", shown, f"effort {effort or '—'}", tokens, f"{row['duration_s']} s"]
    if row["limits"] != "—":
        parts.append(row["limits"])
    print(json.dumps({"header": head, "resumo": " | ".join(parts), **row, "warnings": rep.warnings},
                     ensure_ascii=False))
    return 0


def debug_dump(demand: Path, name: str, cmd: list[str], proc: subprocess.CompletedProcess) -> None:
    """With AIDW_DEBUG=1, saves the command, the stdout (events) and the stderr of the run in the demand."""
    if not os.environ.get("AIDW_DEBUG"):
        return
    stamp = datetime.now().strftime("%H%M%S")
    (demand / f"debug-{name}-{stamp}.log").write_text(
        "CMD: " + json.dumps(cmd, ensure_ascii=False) + "\n\n--- STDOUT ---\n" + (proc.stdout or "")
        + "\n--- STDERR ---\n" + (proc.stderr or ""), encoding="utf-8", newline="\n")


def run_claude(a: dict, role: str, model: dict, effort: str, prompt: str, args, ctx) -> dict:
    settings = {"claudeMdExcludes": [ROOT_CLAUDE_MD_EXCLUDE]}
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
        return {"ok": False, "error": "claude output has no result event", "stderr": proc.stderr[-1500:],
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
    """The Codex sandbox on Windows runs commands under another identity and git refuses the
    repositories ("dubious ownership"). Allows safe.directory only for the AiDW and project folders,
    and only in the Codex commands (GIT_CONFIG_* variables, without touching .gitconfig)."""
    dirs = [ROOT.as_posix(), *code_dirs(cfg, ctx)]
    values = [d.rstrip("/") + "/*" for d in dirs] + [ROOT.as_posix()]
    env = {"GIT_CONFIG_COUNT": str(len(values))}
    for i, v in enumerate(values):
        env[f"GIT_CONFIG_KEY_{i}"] = "safe.directory"
        env[f"GIT_CONFIG_VALUE_{i}"] = v
    return env


def codex_role_overrides(role: str, ctx: dict | None, servers: dict) -> list[str]:
    """Codex -c: the role's MCPs on, the others off, tools blocked by the context."""
    out = []
    mine = mcp_for_role(servers, role)
    for key, s in servers.items():
        if key in mine:
            out += ["-c", f"mcp_servers.{key}={toml_value(codex_mcp_table(s))}"]
        elif codex_trusted():  # only exists in the project config when the project is trusted
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
        return {"ok": False, "error": failed or f"codex exec exited with code {proc.returncode}",
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
    routing = load_routing(rep, ctx)
    servers = resolve_mcp(cfg, rep)
    provider = cfg["provider"]["name"]

    by_name = {a["name"]: r for r, a in resolved.items()}
    role = args.agent if args.agent in resolved else by_name.get(slugify(args.agent))
    a = resolved.get(role) if role else None
    if a is None or role == ORCHESTRATOR or not a["enabled"]:
        valid = ", ".join(x["name"] for r, x in resolved.items() if r != ORCHESTRATOR and x["enabled"])
        rep.error(f"agent {args.agent!r} does not exist, is disabled or is the orchestrator (valid: {valid})")
    attach_variants(resolved, routing, catalog, rep)
    model = a["model"] if a else {}  # the agent's; `--model` wins (an exception with another model or the user's ask)
    if a and args.model:
        m = catalog.get(args.model) or next((dict(v, key=k) for k, v in catalog.items()
                                             if v["model_id"] == args.model), None)
        if m is None or m["provider"] != provider:
            rep.error(f"--model {args.model!r} is not a {provider} model of config/models.toml")
        else:
            model = {**m, "key": m.get("key", args.model)}
    effort = args.effort or (a["effort"] if a else "")
    if effort and effort not in EFFORTS:
        rep.error(f"invalid --effort {effort!r} (valid: {', '.join(EFFORTS)})")
    if model and not model.get("efforts"):
        effort = ""
    elif model and effort and effort not in model["efforts"]:
        rep.error(f"{model['name']} does not accept effort {effort!r}")
    task, demand = Path(args.task).resolve(), Path(args.demand).resolve()
    if not task.is_file():
        rep.error(f"task file does not exist: {task}")
    if not shutil.which(provider):
        rep.error(f"CLI `{provider}` not found in PATH")
    gen = GEN_AGENTS_DIR / f"{a['name']}.md" if a else None
    if gen and not gen.exists():
        rep.error(f"{rel(gen)} does not exist — run `python aidw.py apply`")
    if provider == "claude" and not CLAUDE_AGENTS_JSON.exists():
        rep.error(f"{rel(CLAUDE_AGENTS_JSON)} does not exist — run `python aidw.py apply`")
    if rep.errors:
        print(json.dumps({"state": "environment_blocked", "error": "; ".join(rep.errors)}, ensure_ascii=False))
        return 2

    shown = {**a, "model": model}
    head = header(shown, effort)
    label = args.label or task.stem
    effort_txt = f"effort **{effort}**" if effort else "no effort setting"
    prompt = (f"Model for this task: {model['name']} (`{model_tag(model)}`), {effort_txt}.\n\n"
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
        res = {"ok": False, "error": f"timeout of {args.timeout}s"}

    if "text" not in res:
        print(json.dumps({"header": head, "state": "environment_blocked", "agent": a["name"],
                          "error": res.get("error"), "stderr": res.get("stderr", ""),
                          "stdout": res.get("stdout", "")}, ensure_ascii=False))
        return 1

    base = f"resultado-{a['name']}-{label}"
    (demand / f"{base}.md").write_text(f"{head}\n\n{res['text']}", encoding="utf-8", newline="\n")
    output = final_json(res["text"])
    state = (output or {}).get("state") or ("implementation_failed" if not res["ok"] else "missing_state")
    row = {"date": date.today().isoformat(), "agent": a["name"], "level": "—", "model": model["model_id"],
           "effort": effort, "label": label, "state": state, "turns": res["turns"],
           "duration_s": res["duration_s"], "tokens_in": res["tokens_in"], "tokens_out": res["tokens_out"],
           "cost_usd": res["cost_usd"], "limits": res["limits"]}
    append_metrics(demand, row)
    cost = f"US$ {res['cost_usd']:.2f}" if res["cost_usd"] is not None else "subscription"
    resumo = " | ".join([f"{a['display']} ({label})", model["name"], f"effort {effort or '—'}",
                         f"{res['tokens_in']:,} input tokens + {res['tokens_out']:,} output",
                         f"{res['duration_s']} s", cost, res["limits"]])
    summary = {"header": head, "resumo": resumo, **row, "output": output,
               "result_file": (demand / f"{base}.md").as_posix(), "denials": res["denials"],
               "session": res["session"], "is_error": not res["ok"]}
    # The same printed JSON stays on disk: if the chat loses the command output, it reads it from here.
    (demand / f"{base}.json").write_text(json.dumps({**summary, "raw": res["raw"]}, indent=2, ensure_ascii=False),
                                         encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if res["ok"] else 1


# ---------------------------------------------------------------------------
# Doctor and setup
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
    if IS_WINDOWS:  # user variable defined after this terminal opened
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                return bool(winreg.QueryValueEx(key, name)[0])
        except OSError:
            return False
    return False


def list_mcp_servers(provider: str) -> dict[str, str] | None:
    """{name: status} from `claude mcp list` / `codex mcp list`; None if the CLI fails."""
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
        rep.error("npx not found — the local MCPs need Node.js (install Node LTS)")
    if not required and not project:
        return
    servers = list_mcp_servers(provider) if shutil.which(provider) else None
    if servers is None:
        rep.warn(f"could not run `{provider} mcp list`; MCPs not checked")
        return
    if provider == "claude":
        for key, s in project.items():
            status = servers.get(key)
            if status is None:
                rep.warn(f"MCP {key} does not show up in `claude mcp list` — run `apply` and open Claude Code "
                         "at the root")
            elif "connected" in status.lower():
                rep.ok(f"MCP {key} connected")
            elif s.get("auth") == "oauth":
                rep.warn(f"MCP {key} needs authentication: in Claude Code, /mcp → {key} → Authenticate")
            else:
                rep.warn(f"MCP {key} with status {status!r}")
    else:
        for key, s in project.items():
            extra = " (OAuth: `codex mcp login " + key + "`)" if s.get("auth") == "oauth" else ""
            rep.info(f"MCP {key}: passed by AiDW to each agent and in .codex/config.toml{extra}")
    hints = ctx.get("mcp", {}) if ctx else {}
    for name in required:
        if name not in servers:
            hint = hints.get(name, {}).get("add" if provider == "claude" else "add_codex") or \
                f"{provider} mcp add {name} -- <command>"
            rep.warn(f"MCP {name!r} not registered in {provider} (required by the context). Register it with:\n"
                     f"            {hint}")
        else:
            rep.ok(f"MCP {name} registered in {provider} (required by the context)")


def codex_trusted() -> bool:
    try:
        text = (CODEX_HOME / "config.toml").read_text(encoding="utf-8")
    except OSError:
        return False
    key = str(ROOT).lower()
    return any(key in line.lower() and "projects" in line for line in text.splitlines())


def claude_login() -> bool | None:
    """Claude Code login from `claude auth status` (JSON); None when it cannot be known."""
    out = run(["claude", "auth", "status"])
    try:
        return bool(json.loads(out).get("loggedIn")) if out else None
    except (json.JSONDecodeError, AttributeError):
        return None


def codex_login() -> bool:
    return "logged in" in (run(["codex", "login", "status"]) or "").lower()


def check_provider(provider: str, cfg: dict, resolved: dict, rep: Report) -> None:
    """A provider's CLI, version and login. The active one is mandatory; the other, optional (informational only)."""
    active = cfg["provider"]["name"] == provider
    heading(f"{PROVIDER_LABEL[provider]} — {'active provider' if active else 'optional'}")
    if not shutil.which(provider):
        hint = INSTALL_HINTS[provider][platform_key()]
        if active:
            rep.error(f"CLI `{provider}` not found — it runs the orchestrator and the agents. "
                      f"Install it with: {hint}")
        else:
            rep.info(f"`{provider}` not installed (optional). To install: {hint}")
        return
    version = run([provider, "--version"]) or "?"
    rep.ok(f"{provider} {version.splitlines()[0]}")
    logged = claude_login() if provider == "claude" else codex_login()
    login_hint = "run `claude` and authenticate" if provider == "claude" else "run `codex login`"
    if logged:
        rep.ok("logged in")
    elif logged is None:
        rep.info("could not confirm the login (`claude auth status`)")
    else:
        (rep.warn if active else rep.info)(f"not logged in — {login_hint}")
    if not active:
        return
    for a in resolved.values():
        need = a["model"].get("min_cli")
        if need and version_tuple(version) < version_tuple(need):
            rep.warn(f"{a['model']['name']} requires {provider} {need}+ (current {version.split()[0]}); "
                     f"run `{provider} update`")
            break
    if provider != "codex":
        return
    available = codex_available_models()
    for a in resolved.values():
        if available and a["model"]["model_id"] not in available:
            rep.warn(f"{a['name']}: {a['model']['model_id']} is not enabled for this account "
                     f"(available: {', '.join(sorted(available))})")
    if cfg["delegation"]["mode"] == "native":
        features = run(["codex", "features", "list"]) or ""
        if re.search(r"^multi_agent_v2\s", features, re.M):
            rep.ok("multi_agent_v2 available (subagents with model and effort per spawn)")
        else:
            rep.error("this Codex version does not have multi_agent_v2 — update Codex or use "
                      '[delegation] mode = "headless"')
    if codex_trusted():
        rep.ok("project marked as trusted in Codex (.codex/config.toml applies in the app)")
    else:
        rep.info("project not marked as trusted in Codex: .codex/config.toml only applies through "
                 "`python aidw.py chat` (setup offers to mark it)")


def inside_git_repo(path: Path) -> bool:
    return path.is_dir() and run(["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"]) == "true"


def check_folders(cfg: dict, ctx: dict | None, rep: Report, created: tuple[Path, ...] = ()) -> None:
    heading("Folders")
    for path, why in required_folders(cfg, ctx):
        if path.is_dir():
            rep.ok(f"{why}: {path.as_posix()}" + (" (created)" if path in created else ""))
        else:
            rep.warn(f"{why}: {path.as_posix()} does not exist — `setup` creates it")
    root = worktree_root(cfg)
    if inside_git_repo(root):
        rep.warn(f"the worktree root ({root.as_posix()}) is inside a Git repository; "
                 "use a folder outside any repository ([worktree] root)")
    for d in project_dirs(cfg, ctx):
        if Path(d).is_dir():
            rep.ok(f"allowed folder {d}")
        else:
            rep.warn(f"allowed folder {d} does not exist (clone the repositories or adjust the config)")


def pending_apply(cfg: dict, catalog: dict) -> int | None:
    """How many files `apply` would change now; None if the config has errors."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        ok = apply(cfg, catalog, dry=True)
    # Only the report lines ("  [--]    (dry-run) create …"), not the section title.
    return sum(bool(re.match(r"\s+\[[^]]+\]\s+\(dry-run\) ", line))
               for line in out.getvalue().splitlines()) if ok else None


def one_line(msg: str) -> str:
    """A multi-line message (e.g. a warning with the fix command) on a single line, for the summary."""
    return " ".join(part.strip() for part in msg.splitlines() if part.strip())


def doctor(cfg: dict, catalog: dict) -> bool:
    """Checks everything and ends with the verdict: READY or NOT READY (with what is missing)."""
    rep = Report()
    heading("Core")
    rep.ok(f"Python {sys.version.split()[0]}")
    if shutil.which("git"):
        rep.ok(run(["git", "--version"]) or "git")
        if not run(["git", "config", "user.email"]):
            rep.warn("git user.email not configured")
    else:
        rep.error(f"git not found in PATH. Install it with: {INSTALL_HINTS['git'][platform_key()]}")
    if shutil.which("npx"):
        rep.ok(f"Node.js {run(['node', '--version']) or '?'} (npx for the local MCPs)")
    else:
        rep.warn("npx not found — the local MCPs need Node.js. "
                 f"Install it with: {INSTALL_HINTS['npx'][platform_key()]}")

    b = build(cfg, catalog, Report(quiet=True))
    resolved = b["resolved"] if b else {}
    for provider in PROVIDERS:
        check_provider(provider, cfg, resolved, rep)

    heading("Context")
    ctx = load_context(cfg, rep)
    if ctx:
        rep.ok(f"context {ctx['name']}: {ctx['description']}")
        if not (ctx["dir"] / ".git").exists():
            rep.warn(f"context {ctx['name']}: {rel(ctx['dir'])} is not a Git repository")
        if run(["git", "rev-parse", "--is-inside-work-tree"]) is not None:
            if run(["git", "check-ignore", "-q", rel(ctx["dir"])]) is None:
                rep.error(f"{rel(ctx['dir'])} is NOT in the AiDW .gitignore (internal content would leak)")
            else:
                rep.ok(f"{rel(ctx['dir'])} ignored by the AiDW Git")
        for var in ctx.get("required_env", []):
            if env_defined(var):
                rep.ok(f"variable {var} defined")
            else:
                rep.warn(f"variable {var} not defined (needed by context {ctx['name']})")
        for w in upstream_check(ctx, fetch=True):
            rep.warn(w)
    else:
        rep.info("no active work context")

    heading("MCP")
    check_mcp(cfg, ctx, rep)
    check_folders(cfg, ctx, rep)

    if cfg["provider"]["name"] == "claude":
        check_global_install(cfg, catalog, rep)
    if shutil.which("codex") or load_manifest().get("codex"):
        check_codex_install(rep, cfg, catalog)

    heading("Generated environment")
    pending = pending_apply(cfg, catalog)
    if pending is None:
        rep.error("the configuration has errors — run `python aidw.py apply` to see which")
    elif not RUNTIME_FILE.exists():
        rep.warn("environment not generated yet — run `python aidw.py apply`")
    elif pending:
        rep.warn(f"{pending} file(s) out of date relative to the sources — run `python aidw.py apply` "
                 "and open a new chat")
    else:
        rep.ok(f"up to date with the sources ({PROVIDER_LABEL[cfg['provider']['name']]}, "
               f"delegation {cfg['delegation']['mode']})")

    heading("Result")
    if rep.errors:
        print(f"  NOT READY — {len(rep.errors)} error(s) to fix:")
        for msg in rep.errors:
            print(f"    - {one_line(msg)}")
        if rep.warnings:
            print(f"  and {len(rep.warnings)} warning(s):")
    else:
        print("  READY to use" + (f", with {len(rep.warnings)} warning(s):" if rep.warnings else "."))
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
    if confirm(f"  Install {tool} now? ({hint})", default):
        shell = ["powershell", "-NoProfile", "-Command", hint] if IS_WINDOWS else ["bash", "-lc", hint]
        code = subprocess.run(shell).returncode
        result = "installed" if code == 0 else f"failed (code {code})"
        print(f"  {result} — if the command is not found, reopen the terminal and run setup again")


def ensure_tools(provider: str) -> None:
    """Git, Node and both CLIs. The active provider is mandatory; the other is offered as optional."""
    heading("Prerequisites")
    for tool in ("git", "npx", *PROVIDERS):
        if shutil.which(tool):
            print(f"  [ok]    {tool}")
        elif tool not in PROVIDERS or tool == provider:
            print(f"  [missing] {tool}")
            install_tool(tool, True)
        else:
            print(f"  [--]    {tool} not installed (optional: the other provider)")
            install_tool(tool, False)
    if shutil.which("claude") and claude_login() is False:
        print("  [--]    Claude Code not logged in: run `claude` once and authenticate")
    if shutil.which("codex") and not codex_login():
        print("  [--]    Codex not logged in: run `codex login` (ChatGPT account)")


def ensure_folders(cfg: dict) -> None:
    """Creates the folders AiDW needs; the project folders are only checked."""
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
            print(f"  [warn]  MCP {name!r} required by the context and without a registration command for {provider}")
            continue
        heading(f"MCP {name}")
        print(f"  Required by context {ctx['name']} and not registered in {provider}:\n    {hint}")
        if confirm("  Register now (user scope)?", True):
            shell = ["powershell", "-NoProfile", "-Command", hint] if IS_WINDOWS else ["bash", "-lc", hint]
            subprocess.run(shell)


def offer_codex_trust(cfg: dict) -> None:
    if cfg["provider"]["name"] != "codex" or codex_trusted():
        return
    heading("Codex: trusted project")
    print(f"  Marking {ROOT} as trusted in ~/.codex/config.toml makes the Codex app/CLI use the AiDW\n"
          "  .codex/config.toml (model, effort, network, MCPs) even without `python aidw.py chat`.")
    if confirm("  Mark it now?", True):
        entry = f"\n[projects.'{str(ROOT).lower()}']\ntrust_level = \"trusted\"\n"
        CODEX_HOME.mkdir(parents=True, exist_ok=True)
        with (CODEX_HOME / "config.toml").open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(entry)
        print("  Done.")


def chat(cfg: dict, catalog: dict) -> int:
    rep = Report()
    b = build(cfg, catalog, rep)
    if b is None:
        return 1
    provider = cfg["provider"]["name"]
    if not shutil.which(provider):
        print(f"CLI `{provider}` not found.")
        return 1
    orch = b["resolved"][ORCHESTRATOR]
    if provider == "claude":
        cmd = [shutil.which("claude")]  # permissions come from .claude/settings.local.json; model and effort are the chat's
    else:
        cmd = [shutil.which("codex"), "-C", str(ROOT), "-m", orch["model"]["model_id"],
               "-c", f"project_doc_max_bytes={CODEX_DOC_MAX_BYTES}", "-s", "workspace-write",
               "-a", "on-request", "-c", "sandbox_workspace_write.network_access=true"]
        if orch["effort"]:
            cmd += ["-c", f'model_reasoning_effort="{orch["effort"]}"']
        if cfg["delegation"]["mode"] == "native":
            cmd += ["--enable", "multi_agent_v2"]
        for key, s in b["servers"].items():  # without a trusted project, .codex/config.toml does not load
            cmd += ["-c", f"mcp_servers.{key}={toml_value(codex_mcp_table(s))}"]
        for k, v in codex_git_env(cfg, b["ctx"]).items():
            cmd += ["-c", f"shell_environment_policy.set.{k}={toml_value(v)}"]
        for d in code_dirs(cfg, b["ctx"]):
            if Path(d).is_dir():
                cmd += ["--add-dir", win(d)]
    print(f"Opening the orchestrator: {' '.join(Path(cmd[0]).stem if i == 0 else c for i, c in enumerate(cmd))}")
    return subprocess.run(cmd, cwd=ROOT).returncode


def show(cfg: dict, catalog: dict) -> None:
    rep = Report()
    ctx = load_context(cfg, rep)
    resolved = resolve(cfg, catalog, ctx, available_skills(ctx, rep), rep)
    heading(f"AiDW · {PROVIDER_LABEL.get(cfg['provider']['name'], '?')} · delegation "
            f"{cfg['delegation']['mode']} · context {ctx['name'] if ctx else 'none'}")
    print(f"  {'NAME':<16} {'DISPLAY':<16} {'ROLE':<13} {'MODEL':<26} {'EFFORT':<8} KIND")
    for role, a in resolved.items():
        kind = "chat" if role == ORCHESTRATOR else (
            "subagent" if cfg["delegation"]["mode"] == "native" else "headless")
        status = "" if a["enabled"] else "  (disabled)"
        print(f"  {a['name']:<16} {a['display']:<16} {role:<13} {a['model']['model_id']:<26} "
              f"{a['effort'] or '—':<8} {kind}{status}")
    print(f"\n  State: {state_dir(ctx).as_posix()}")
    inherited = bool(ctx) and not (ctx.get("language") or "").strip()
    print(f"  Language: UI {language_label(ui_language(cfg))}; demand artifacts "
          f"{language_label(context_language(cfg, ctx))}" + (" (inherited from the UI)" if inherited else ""))


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # a cp1252 console breaks on accents and arrows
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="AiDW — orchestrator and specialized agents.")
    sub = parser.add_subparsers(dest="command")
    p_setup = sub.add_parser("setup", help="prerequisites + wizard (if needed) + apply + doctor")
    p_setup.add_argument("--reconfigure", action="store_true", help="redoes the wizard even with an existing config")
    p_setup.add_argument("--skip-tools", action="store_true", help="does not check/install prerequisites")
    p_conf = sub.add_parser("configure", help="interactive wizard")
    p_conf.add_argument("--defaults", action="store_true", help="writes the default config without asking")
    p_conf.add_argument("--provider", choices=PROVIDERS, help="with --defaults: provider of the default config")
    p_conf.add_argument("--language", help='with --defaults: [ui] language, a BCP-47 tag ("en", "pt-BR"; default en)')
    p_apply = sub.add_parser("apply", help="generates the environment from aidw.config.toml")
    p_apply.add_argument("--dry-run", action="store_true", help="shows what would change, without changing anything")
    p_inst = sub.add_parser("install", help="installs AiDW in Claude for every folder (aidw plugin, with the active "
                            "context)")
    p_inst.add_argument("--dry-run", action="store_true", help="shows what would change, without changing anything")
    p_inst.add_argument("--force", action="store_true", help="overwrites a generated file changed by hand")
    p_inst.add_argument("--mcp", action="store_true",
                        help="registers in user scope the catalog MCPs that are missing (they start in every session)")
    p_inst.add_argument("--skip-cli", action="store_true", help=argparse.SUPPRESS)  # tests: without the Claude CLI
    p_inst.add_argument("--provider", choices=("claude", "codex", "all"),
                        help="where to install (default: Claude and, if already installed, Codex)")
    p_uninst = sub.add_parser("uninstall", help="removes from Claude only what install added")
    p_uninst.add_argument("--dry-run", action="store_true", help="shows what would change, without changing anything")
    p_uninst.add_argument("--skip-cli", action="store_true", help=argparse.SUPPRESS)
    p_uninst.add_argument("--provider", choices=("claude", "codex", "all"), default="all")
    p_open = sub.add_parser("open", help="opens Claude or Codex in the folder (or in the demand's worktree)")
    p_open.add_argument("--provider", choices=("claude", "codex"), default="claude")
    p_open.add_argument("--demand", help="demand id: opens in its worktree")
    p_open.add_argument("--path", help="folder (default: the current one)")
    p_open.add_argument("--print", action="store_true", help="only shows the command")
    p_open.add_argument("--no-orchestrate", action="store_true", help="with --demand: opens without calling the "
                        "orchestrator")
    p_open.add_argument("--app", action="store_true", help="with --provider codex: opens the Codex desktop app in the "
                        "folder (the worktree, or the demand folder when there are several) instead of the terminal")
    p_open.add_argument("--repo", help="with --demand of more than one repository: the worktree where the session "
                        "opens (repository path or name; default: the first one created)")
    p_status = sub.add_parser("status", help="quick view: install, active demands, worktrees and pending items")
    p_status.add_argument("--json", action="store_true")
    p_wt = sub.add_parser("worktree", help="worktree per demand: create, list, inspect, remove, cleanup")
    wt = p_wt.add_subparsers(dest="wt_action", required=True)
    w_create = wt.add_parser("create", help="creates (or returns) the demand's worktree in a repository")
    w_create.add_argument("--repo", required=True, help="repository folder (or a folder inside it)")
    w_create.add_argument("--demand", required=True, help="demand id, e.g. us-1234")
    w_create.add_argument("--slug", help="short summary for the branch name")
    w_create.add_argument("--base", help="worktree base (default: origin's default branch)")
    w_create.add_argument("--pr", help="review someone else's PR <n>: a read-only worktree on the PR merged into the "
                          "target, with no branch, and the diff in the demand folder; run again to update to the new "
                          "version")
    wt.add_parser("list", help="registered worktrees and the state of each one")
    for name, help_text in (("inspect", "details of a worktree"), ("remove", "removes a clean, integrated worktree")):
        w = wt.add_parser(name, help=help_text)
        w.add_argument("target", help="worktree path or demand id")
        w.add_argument("--repo", help="repository, when the demand has more than one")
    wt.add_parser("cleanup", help="removes from the registry the worktrees whose folder is gone")
    wt.add_parser("hook-create")  # the plugin's WorktreeCreate/WorktreeRemove hooks (internal use)
    wt.add_parser("hook-remove")
    for w in wt.choices.values():
        w.add_argument("--json", action="store_true", help="JSON output")
    p_ctx = sub.add_parser("context", help="work contexts: list, check, use, create")
    cx = p_ctx.add_subparsers(dest="ctx_action", required=True)
    cx.add_parser("list", help="available contexts and which one is active")
    c_check = cx.add_parser("check", help="validates a context as if it were active")
    c_check.add_argument("name")
    c_up = cx.add_parser("upstream", help="fetches the active context's upstreams and says whether the copies or the "
                                          "local checkout fell behind")
    c_up.add_argument("--no-fetch", action="store_true", help="compares with the last fetched state")
    c_use = cx.add_parser("use", help="activates a context (apply and, if installed, install)")
    c_use.add_argument("name", nargs="?", default="", help="context name (empty = none)")
    c_use.add_argument("--skip-install", action="store_true", help="does not reinstall the plugin")
    c_use.add_argument("--skip-cli", action="store_true", help=argparse.SUPPRESS)
    c_create = cx.add_parser("create", help="creates contexts/<name>/ with the minimal structure and its own git")
    c_create.add_argument("name")
    c_create.add_argument("--description")
    c_create.add_argument("--mcp", help="required MCP servers (comma-separated)")
    c_create.add_argument("--env", help="required environment variables (comma-separated)")
    c_create.add_argument("--language", help="language of the context's content and demand artifacts (BCP-47 tag; "
                          "default: the AiDW [ui] language)")
    for c in cx.choices.values():
        c.add_argument("--json", action="store_true", help="JSON output")
    p_dm = sub.add_parser("demand", help="demand state for resuming: set, show, list")
    dm = p_dm.add_subparsers(dest="dm_action", required=True)
    d_set = dm.add_parser("set", help="creates or updates demand.json (step, status, title, note)")
    d_set.add_argument("id", help="demand id, e.g. us-1234")
    d_set.add_argument("--step", help="current step: UNDERSTAND or a NEXT ACTION action")
    d_set.add_argument("--status", choices=("active", "paused", "done"))
    d_set.add_argument("--title")
    d_set.add_argument("--note", help="where it stopped / next step")
    d_set.add_argument("--summary", help="what the demand is about, in up to 4 lines (the panel shows it in the "
                       "demand map)")
    d_set.add_argument("--pr", action="append", metavar="REPO=N",
                       help="open PR of one of the demand's repositories (repeatable): App=1234")
    d_set.add_argument("--task", action="append", metavar="TICKET=ID",
                       help="work item (Task) created for a ticket (repeatable): front=5001")
    d_set.add_argument("--loop", help="fix loop after delivery (e.g. bug-1234): the rounds of "
                                      "review-<id>-<loop>-r<N>.md count from 1; `-` clears it")
    d_set.add_argument("--extra-step", action="append", metavar="STEP",
                       help="outside step of the context that the demand goes through (repeatable; the panel shows "
                            "it): UX_VALIDATION; `-UX_VALIDATION` removes it")
    d_show = dm.add_parser("show", help="shows demand.json")
    d_show.add_argument("id")
    d_list = dm.add_parser("list", help="the context's demands (most recent first)")
    d_list.add_argument("--active", action="store_true", help="only the unfinished ones")
    for d in dm.choices.values():
        d.add_argument("--json", action="store_true", help="JSON output")
    p_ss = sub.add_parser("session", help="binds this session to orchestrator mode and to the demand: bind, unbind")
    ss = p_ss.add_subparsers(dest="ss_action", required=True)
    s_bind = ss.add_parser("bind", help="registers the session in orchestrator mode (and the demand it drives)")
    s_bind.add_argument("--demand", help="demand id in the active context (the folder with demand.json)")
    ss.add_parser("unbind", help="takes the session out of orchestrator mode")
    for s in ss.choices.values():
        s.add_argument("--session", help=f"session id (default: ${SESSION_ENV})")
        s.add_argument("--json", action="store_true", help="JSON output")
    p_kb = sub.add_parser("kb", help="the context's knowledge base: show, search, check, index, collect")
    kb = p_kb.add_subparsers(dest="kb_action", required=True)
    k_show = kb.add_parser("show", help="a note with its links and who cites it")
    k_show.add_argument("name", help="note name, system key, alias or title")
    k_show.add_argument("--brief", action="store_true", help="only the note, without the list of links and citers")
    k_search = kb.add_parser("search", help="notes with all the words (accent- and case-insensitive)")
    k_search.add_argument("term", nargs="+")
    k_search.add_argument("--limit", type=int, default=15)
    kb.add_parser("check", help="broken links, repeated names, frontmatter, orphans and secrets")
    kb.add_parser("index", help="regenerates index.md (notes by type and glossary)")
    k_collect = kb.add_parser("collect", help="gathers what the demand learned into collect-<id>.md (for /aidw:done)")
    k_collect.add_argument("demand", help="demand id (the folder in state_dir)")
    for k in kb.choices.values():
        k.add_argument("--json", action="store_true", help="JSON output")
    p_proj = sub.add_parser("project", help="the folder's project: repository, system, context and demand")
    proj = p_proj.add_subparsers(dest="proj_action", required=True)
    p_detect = proj.add_parser("detect", help="detects the project from a folder")
    p_detect.add_argument("--path", default=".", help="folder (default: the current one)")
    p_detect.add_argument("--json", action="store_true", help="JSON output")
    sub.add_parser("doctor", help="checks everything and says whether the environment is ready")
    sub.add_parser("show", help="shows agents, models and efforts")
    sub.add_parser("chat", help="opens the orchestrator in the provider's CLI")
    p_del = sub.add_parser("delegate", help="runs a headless agent for a task")
    p_del.add_argument("--agent", required=True, help="agent name or role")
    p_del.add_argument("--effort", choices=EFFORTS, help="effort of this task (default: the level's/agent's)")
    p_del.add_argument("--level", help=argparse.SUPPRESS)  # flow v3: no levels; accepted and ignored
    p_del.add_argument("--model", help="another model of the provider (only when the user asks)")
    p_del.add_argument("--task", required=True, help=".md file with the task")
    p_del.add_argument("--demand", required=True, help="demand folder (result and metrics.md)")
    p_del.add_argument("--label", help="result label, e.g. t1-r1 (default: the task file name)")
    p_del.add_argument("--max-turns", type=int, help="turn limit (Claude)")
    p_del.add_argument("--timeout", type=int, default=3600, help="maximum time in seconds (default 3600)")
    p_rec = sub.add_parser("record", help="records a delegation made with a native subagent")
    p_rec.add_argument("--agent", required=True, help="name, role or variant (e.g. coder-high)")
    p_rec.add_argument("--effort", choices=EFFORTS, help="effort used (default: the variant's or the level's)")
    p_rec.add_argument("--level", help=argparse.SUPPRESS)  # flow v3: no levels; accepted and ignored
    p_rec.add_argument("--label", required=True, help="label, e.g. t1-r1")
    p_rec.add_argument("--demand", required=True, help="demand folder (metrics.md)")
    p_rec.add_argument("--state", help="state of the agent's final JSON")
    p_rec.add_argument("--tokens", type=int, help="Claude: subagent_tokens from the Agent result")
    p_rec.add_argument("--tool-uses", type=int, help="Claude: tool_uses from the Agent result")
    p_rec.add_argument("--duration-ms", type=int, help="Claude: duration_ms from the Agent result")
    p_rec.add_argument("--codex-task", help="Codex: task_name of the spawn (reads the real tokens from the session)")
    p_rec.add_argument("--usage-model", help="Claude (mod): model of the subagent's responses, for the cost in US$")
    for name in ("input", "cache-write", "cache-read", "output"):
        p_rec.add_argument(f"--{name}", type=int, default=0, help=f"Claude (mod): {name} tokens summed from the "
                                                                       "subagent")
    p_orc = sub.add_parser("record-orchestrator",
                           help="adds an orchestrator turn to the orchestrator metrics file (written by the mod)")
    p_orc.add_argument("--demand", required=True, help="demand folder")
    p_orc.add_argument("--session", required=True, help="chat session id")
    p_orc.add_argument("--model", help="model that answered (API id)")
    for name in ("input", "cache-write", "cache-read", "output"):
        p_orc.add_argument(f"--{name}", type=int, default=0, help=f"{name} tokens of the turn")
    p_orc.add_argument("--duration-ms", type=int, help="turn duration")
    p_orc.add_argument("--step", help="demand step in which the turn happened")
    args = parser.parse_args()
    command = args.command or "setup"
    if command == "record-orchestrator":
        return record_orchestrator(args)  # on every turn: without loading the catalog or the configuration

    catalog = load_catalog()
    cfg = load_config()

    if command == "configure":
        if args.defaults:
            cfg = default_config(args.provider or (cfg or default_config())["provider"]["name"])
            if args.language:
                if not LANGUAGE_TAG_RE.match(args.language.strip()):
                    print(f"[error] invalid language tag {args.language!r} (BCP-47, e.g. en, pt-BR)")
                    return 1
                cfg["ui"]["language"] = args.language.strip()
        else:
            cfg = wizard(cfg or default_config((installed_providers() or ["claude"])[0]), catalog)
        save_config(cfg)
        print("Next step: python aidw.py apply")
        return 0

    if command == "setup":
        if cfg is None or getattr(args, "reconfigure", False):
            cfg = wizard(cfg or default_config((installed_providers() or ["claude"])[0]), catalog)
            if not confirm("\nSave and apply this configuration?", True):
                print("Nothing was saved.")
                return 1
            save_config(cfg)
        elif context_missing(cfg):
            heading("Context not found")
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
        print("\nReady. Open the orchestrator: `python aidw.py chat` (or the provider's app in the AiDW folder).")
        return 0 if ok else 1

    if cfg is None:
        print("aidw.config.toml not found. Run `python aidw.py setup` or `configure`.")
        return 1
    if command == "apply":
        return 0 if apply(cfg, catalog, dry=args.dry_run) else 1
    if command == "worktree":
        return worktree_command(cfg, args)
    if command == "demand":
        return demand_command(cfg, args)
    if command == "session":
        return session_command(cfg, args)
    if command == "context":
        return context_command(cfg, catalog, args)
    if command == "kb":
        return kb_command(cfg, args)
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
        if not args.provider:  # both stay the same: whoever has Codex installed updates both at once
            args.provider = "all" if load_manifest().get("codex") else "claude"
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
        if args.app and args.provider != "codex":
            print("[error] --app is Codex's (`--provider codex --app`); in Claude, the desktop app opens the folder "
                  "through the picker")
            return 1
        return open_command(cfg, args.provider, args.demand or "", args.path or "", args.print,
                            not args.no_orchestrate, args.repo or "", args.app)
    if command == "status":
        return status_command(cfg, catalog, args.json)
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
