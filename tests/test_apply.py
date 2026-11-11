"""Reference tests of `aidw.py apply` (F0 of plan v3).

Each scenario copies the AiDW sources into a temporary folder, writes an aidw.config.toml, runs `apply` and compares
the generated files with tests/golden/<scenario>/. The reference only changes on purpose:

    python -m unittest discover -s tests -v          # runs
    python tests/test_apply.py --update              # rewrites the references (review the diff in git)

The references are generated on Windows (paths, junctions and npx's `cmd /c` depend on the OS); on another OS the
reference tests are skipped.
"""
from __future__ import annotations

import contextlib
import difflib
import hashlib
import io
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

# ignore_cleanup_errors: doctor runs `claude mcp list`, which may leave MCP servers holding the temporary folder on
# Windows; the folder is disposable.
REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"
GOLDEN = TESTS / "golden"
FIXTURE_CONTEXT = TESTS / "fixtures" / "contexts" / "exemplo"
SOURCES = ["aidw.py", "aidw_guard.py", "config", "agents", "skills", "orchestrator", "workflows", "mods"]
# Everything apply generates, relative to the root.
GENERATED = ["CLAUDE.md", "AGENTS.md", ".mcp.json", ".aidw", ".claude", ".codex", ".agents"]
UPDATE = os.environ.get("AIDW_UPDATE_GOLDEN") == "1"

# name: (provider, delegation, context)
SCENARIOS = {
    "claude-native-contexto": ("claude", "native", "exemplo"),
    "claude-headless-sem-contexto": ("claude", "headless", ""),
    "codex-native-contexto": ("codex", "native", "exemplo"),
}


def load_aidw(root: Path):
    spec = importlib.util.spec_from_file_location(f"aidw_{root.name}", root / "aidw.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_sandbox(tmp: Path, provider: str, mode: str, context: str, copy_context: bool = True) -> Path:
    root = tmp / "aidw"
    root.mkdir()
    for name in SOURCES:
        src = REPO / name
        if src.is_dir():
            shutil.copytree(src, root / name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, root / name)
    if context and copy_context:
        shutil.copytree(FIXTURE_CONTEXT, root / "contexts" / context)
    aidw = load_aidw(root)
    cfg = aidw.default_config(provider)
    cfg["delegation"]["mode"] = mode
    cfg["context"]["active"] = context
    cfg["worktree"]["root"] = (tmp / "wt").as_posix()  # never the machine's real root
    (root / "aidw.config.toml").write_text(aidw.render_config(cfg), encoding="utf-8", newline="\n")
    return root


def run_aidw(root: Path, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "CODEX_HOME": str(root.parent / "codex-home"), "PYTHONIOENCODING": "utf-8",
           "CLAUDE_CONFIG_DIR": str(root.parent / "claude-home"),  # never the real ~/.claude
           "AIDW_CODEX_SKILLS_DIR": str(root.parent / "agents-skills"), **(env_extra or {})}  # nor ~/.agents
    return subprocess.run([sys.executable, str(root / "aidw.py"), *args], cwd=root, env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)


def normalize(text: str, root: Path) -> str:
    """Replaces the temporary folder's path with <ROOT> (and the folder above it, where the test's worktree root
    lives, with <TMP>) in every spelling apply uses."""
    for path, mark in ((root.resolve(), "<ROOT>"), (root.resolve().parent, "<TMP>")):
        win = str(path)
        for form in (json.dumps(win)[1:-1], win, win.replace("\\", "/"), json.dumps(win.lower())[1:-1],
                     win.lower(), win.lower().replace("\\", "/")):
            text = text.replace(form, mark)
    return text


def is_link(p: Path) -> bool:
    return p.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(p))


def snapshot(root: Path) -> dict[str, str]:
    """{relative path: normalized content}. Links become `-> <relative target>`."""
    files: dict[str, str] = {}

    def add(p: Path) -> None:
        key = p.relative_to(root).as_posix()
        if is_link(p):
            target = Path(os.path.realpath(p)).resolve()
            files[key + ".link"] = "-> " + target.relative_to(root.resolve()).as_posix() + "\n"
        elif p.is_dir():
            for child in sorted(p.iterdir()):
                add(child)
        else:
            files[key] = normalize(p.read_text(encoding="utf-8"), root)

    for name in GENERATED:
        if (root / name).exists() or is_link(root / name):
            add(root / name)
    return files


def read_golden(name: str) -> dict[str, str]:
    base = GOLDEN / name
    if not base.is_dir():
        return {}
    return {p.relative_to(base).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(base.rglob("*")) if p.is_file()}


def write_golden(name: str, files: dict[str, str]) -> None:
    base = GOLDEN / name
    if base.exists():
        shutil.rmtree(base)
    for key, content in files.items():
        path = base / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def diff_report(expected: dict[str, str], actual: dict[str, str], limit: int = 60) -> str:
    out = []
    for key in sorted(set(expected) - set(actual)):
        out.append(f"- missing: {key}")
    for key in sorted(set(actual) - set(expected)):
        out.append(f"+ new:     {key}")
    for key in sorted(set(expected) & set(actual)):
        if expected[key] != actual[key]:
            out.append(f"~ changed: {key}")
            out += list(difflib.unified_diff(expected[key].splitlines(), actual[key].splitlines(),
                                             "reference", "generated", lineterm="", n=1))[:limit]
    return "\n".join(out)


@unittest.skipUnless(os.name == "nt", "references generated on Windows")
class ApplyGoldenTest(unittest.TestCase):
    maxDiff = None

    def check_scenario(self, name: str) -> None:
        provider, mode, context = SCENARIOS[name]
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), provider, mode, context)

            dry = run_aidw(root, "apply", "--dry-run")
            self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)
            self.assertEqual(snapshot(root), {}, "dry-run must not write anything")

            first = run_aidw(root, "apply")
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            actual = snapshot(root)
            state = "contexts/exemplo/demandas" if context else "state"
            self.assertTrue((root / state).is_dir(), f"apply should create {state}/")

            second = run_aidw(root, "apply")
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(snapshot(root), actual, "apply is not idempotent")
            for word in ("created", "updated", "removed", "linked"):
                self.assertNotIn(f"[ok]    {word}", second.stdout, "the 2nd apply should change nothing")

        if UPDATE:
            write_golden(name, actual)
            return
        expected = read_golden(name)
        self.assertTrue(expected, f"no reference for {name}: run `python tests/test_apply.py --update`")
        if expected != actual:
            self.fail(f"apply output changed in {name}:\n{diff_report(expected, actual)}\n\n"
                      "If the change is intentional: python tests/test_apply.py --update")

    def test_claude_native_context(self) -> None:
        self.check_scenario("claude-native-contexto")

    def test_claude_headless_no_context(self) -> None:
        self.check_scenario("claude-headless-sem-contexto")

    def test_codex_native_context(self) -> None:
        self.check_scenario("codex-native-contexto")


class OrchestratorReferenceTest(unittest.TestCase):
    """References and `orchestrator_when` policies stay out of the orchestrator prompt, only listed; the agents keep
    the whole policy; the frontmatter never leaks."""

    def test_references_on_demand(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            aidw = load_aidw(root)
            rep = aidw.Report(quiet=True)
            b = aidw.build(aidw.load_config(), aidw.load_catalog(), rep)
            self.assertEqual(rep.errors, [])
            orch, refs = b["orchestrator_md"], b["orchestrator_refs"]
            self.assertIn("sob-demanda", refs)
            self.assertIn("etapa", refs)
            self.assertNotIn("TEXTO-POLICY-SOB-DEMANDA", orch)
            self.assertNotIn("TEXTO-REFERENCIA-ORQUESTRADOR", orch)
            self.assertIn("preparar a revisão no contexto de exemplo", orch)
            self.assertIn("orchestrator", refs["etapa"]["content"], "{{agent:}} placeholder rendered")
            for g in b["agents"].values():
                self.assertIn("TEXTO-POLICY-SOB-DEMANDA", g["prompt"])
            for text in (orch, *[g["prompt"] for g in b["agents"].values()], *[r["content"] for r in refs.values()]):
                self.assertNotIn("orchestrator_when", text)

    def test_repeated_name_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            (root / "orchestrator" / "reference" / "etapa.md").write_text(
                "---\nwhen: x\n---\n\nGeneric.\n", encoding="utf-8")
            aidw = load_aidw(root)
            rep = aidw.Report(quiet=True)
            self.assertIsNone(aidw.build(aidw.load_config(), aidw.load_catalog(), rep))
            self.assertTrue(any("reference name 'etapa'" in e for e in rep.errors), rep.errors)

    def test_agents_and_variants(self) -> None:
        """Flow v3 (decision, 2026-10-23): no levels; each agent on its default and only the routing.toml
        exceptions (go down on a re-review, go up when the result made no sense, the survey's explorer); nothing above
        high; the api, bugs and security agents are gone; on Codex, each model's equivalent by tier."""
        expected = {  # role: {variant: model/effort}
            "planner": {"planner": "sonnet/high", "planner-medium": "sonnet/medium"},
            "explorer": {"explorer": "haiku/low", "explorer-sonnet-medium": "sonnet/medium",
                         "explorer-sonnet-high": "sonnet/high"},
            "coder": {"coder": "sonnet/high", "coder-medium": "sonnet/medium", "coder-opus-medium": "opus/medium"},
            "reviewer": {"reviewer": "sonnet/high", "reviewer-medium": "sonnet/medium", "reviewer-low": "sonnet/low"},
            "qa": {"qa": "sonnet/medium", "qa-high": "sonnet/high"},
            "documenter": {"documenter": "haiku/medium"},
        }
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            aidw = load_aidw(root)
            rep = aidw.Report(quiet=True)
            b = aidw.build(aidw.load_config(), aidw.load_catalog(), rep)
            self.assertEqual(rep.errors, [])
            self.assertEqual(set(b["resolved"]) - {"orchestrator"}, set(expected), "api, bugs and security are gone")
            for role, variants in expected.items():
                got = {n: f"{v['model']['key']}/{v['effort']}" for n, v in b["resolved"][role]["variants"].items()}
                self.assertEqual(got, variants, role)
                for n, v in b["resolved"][role]["variants"].items():
                    if n != b["resolved"][role]["name"]:
                        self.assertTrue(v["when"], f"{n}: the exception says when it applies")
            efforts = {v["effort"] for a in b["resolved"].values() for v in a.get("variants", {}).values()}
            self.assertFalse(efforts & {"xhigh", "max"}, "nothing above high")
            orq = b["orchestrator_md"]
            self.assertIn("## Agents and effort", orq)
            self.assertIn("`reviewer-medium` — re-review of only the fixes", orq)
            self.assertNotIn("Effort per task", orq)
            self.assertNotIn("Level:", orq)
            cat = aidw.load_catalog()
            tiers = {t: aidw.tier_model(cat, "codex", t) for t in ("top", "mid", "fast")}
            self.assertEqual(len(set(tiers.values())), 3, f"three tiers on Codex: {tiers}")

    def test_policies_and_systems_by_role(self) -> None:
        """Prompts by role (2026-11-11): a policy with `roles` in its frontmatter goes only to those roles (none =
        every role, the orchestrator included); the full *Systems* only for explorer, planner and coder, the short
        table for the others, and the context may change it per role."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            pol = root / "contexts" / "exemplo" / "policies"
            pol.mkdir(parents=True, exist_ok=True)
            (pol / "so-orquestrador.md").write_text("---\nroles: [orchestrator]\n---\n\n# Policy only-orch\n",
                                                   encoding="utf-8")
            aidw = load_aidw(root)
            rep = aidw.Report(quiet=True)
            b = aidw.build(aidw.load_config(), aidw.load_catalog(), rep)
            self.assertEqual(rep.errors, [])
            prompts = {r: g["prompt"] for r, g in b["agents"].items()}
            self.assertIn("# Git policy", prompts["coder"])
            self.assertNotIn("# Git policy", prompts["reviewer"], "git only for coder and orchestrator")
            self.assertIn("# Secrets policy", prompts["documenter"], "no `roles` = every role")
            for role, prompt in prompts.items():
                self.assertNotIn("# Policy only-orch", prompt, role)
            self.assertIn("# Policy only-orch", b["orchestrator_md"])
            self.assertIn("# Git policy", b["orchestrator_md"])
            self.assertIn("Max retries", prompts["coder"])
            self.assertNotIn("Max retries", prompts["reviewer"])
        self.assertEqual(aidw.systems_mode(None, "coder"), "full")
        self.assertEqual(aidw.systems_mode(None, "reviewer"), "short")
        self.assertEqual(aidw.systems_mode({"agents": {"qa": {"systems": "full"}}}, "qa"), "full")
        self.assertEqual(aidw.systems_mode({"agents": {"coder": {"systems": "none"}}}, "coder"), "none")

    def test_config_with_removed_agents(self) -> None:
        """A config from before flow v3 with [agents.api-db] and [agents.bug-hunter]: a warning, not an error, and
        they are not generated."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            cfg_file = root / "aidw.config.toml"
            cfg_file.write_text(cfg_file.read_text(encoding="utf-8") + '\n[agents.api-db]\nenabled = true\n'
                                '\n[agents.bug-hunter]\nenabled = true\n', encoding="utf-8")
            aidw = load_aidw(root)
            rep = aidw.Report(quiet=True)
            b = aidw.build(aidw.load_config(), aidw.load_catalog(), rep)
            self.assertEqual(rep.errors, [])
            self.assertNotIn("api-db", b["resolved"])
            self.assertTrue(any("[agents.api-db]" in w for w in rep.warnings), rep.warnings)

    def test_settings_lose_only_what_aidw_wrote(self) -> None:
        """The orchestrator's model is the chat's: apply removes `model`/`effortLevel` only when they are the value it
        wrote itself before; the user's choice and the other keys stay."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            aidw = load_aidw(root)
            managed = {"allow": ["Read"], "ask": [], "deny": [], "additionalDirectories": [],
                       "enabledMcpjsonServers": [], "env": {}}
            previous = {"model": "opus", "effortLevel": "high"}
            for model, stays in (("opus", False), ("sonnet", True)):
                aidw.CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
                aidw.CLAUDE_SETTINGS.write_text(json.dumps({"model": model, "effortLevel": "high",
                                                            "env": {"MINE": "1"}}), encoding="utf-8")
                aidw.sync_claude_settings(managed, previous, False, aidw.Report(quiet=True))
                data = json.loads(aidw.CLAUDE_SETTINGS.read_text(encoding="utf-8"))
                self.assertEqual("model" in data, stays, model)
                self.assertNotIn("effortLevel", data)
                self.assertEqual(data["env"], {"MINE": "1"})
                self.assertEqual(data["permissions"]["allow"], ["Read"])
            data["model"] = "opus"  # after that AiDW writes nothing else: a chosen `opus` stays
            aidw.CLAUDE_SETTINGS.write_text(json.dumps(data), encoding="utf-8")
            aidw.sync_claude_settings(managed, {**managed}, False, aidw.Report(quiet=True))
            self.assertEqual(json.loads(aidw.CLAUDE_SETTINGS.read_text(encoding="utf-8"))["model"], "opus")

    def test_old_config_gets_the_new_agents(self) -> None:
        """A config with [agents.*] from before the planner and the explorer: both come with the default and the
        orchestrator delegates the exploration to the explorer."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            cfg_file = root / "aidw.config.toml"
            text = cfg_file.read_text(encoding="utf-8")
            text = re.sub(r"\[agents\.(planner|explorer)\]\n(?:(?!\n\[).)*\n", "", text, flags=re.S)
            self.assertNotIn("[agents.planner]", text)
            cfg_file.write_text(text, encoding="utf-8")
            aidw = load_aidw(root)
            rep = aidw.Report(quiet=True)
            b = aidw.build(aidw.load_config(), aidw.load_catalog(), rep)
            self.assertEqual(rep.errors, [])
            self.assertEqual(b["resolved"]["explorer"]["model"]["key"], "haiku")
            self.assertEqual(b["resolved"]["planner"]["model"]["key"], "sonnet")
            self.assertEqual(b["resolved"]["planner"]["effort"], "high")
            self.assertIn("the `explorer` agent", b["orchestrator_md"])
            self.assertIn("`coder-medium`", b["orchestrator_md"], "the small-fix exception")
            cat = aidw.load_catalog()
            self.assertEqual(aidw.equivalent_model(cat, "opus", "codex"), aidw.tier_model(cat, "codex", "top"))
            self.assertEqual(aidw.equivalent_model(cat, "haiku", "codex"), aidw.tier_model(cat, "codex", "fast"))
            self.assertEqual(aidw.equivalent_model(cat, "sonnet", "claude"), "sonnet")

    def test_old_names_still_read(self) -> None:
        """PR 2 (English identifiers): a config and a context written with the old Portuguese names keep working —
        old core skill names in [agents.*], old workflow names in [workflows.by_type] and a context workflow file
        with an old name replacing the new core one."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            cfg_file = root / "aidw.config.toml"
            text = cfg_file.read_text(encoding="utf-8")
            self.assertIn('skills = ["to-spec", "verify-premise"]', text)
            cfg_file.write_text(text.replace('skills = ["to-spec", "verify-premise"]',
                                             'skills = ["to-spec", "verificar-premissa"]', 1), encoding="utf-8")
            ctx_dir = root / "contexts" / "exemplo"
            toml = ctx_dir / "context.toml"
            toml.write_text(toml.read_text(encoding="utf-8") + '\n[workflows]\nby_type = { "Bug" = "desenvolvimento", '
                            '"Estimate" = "levantamento" }\n', encoding="utf-8")
            (ctx_dir / "workflows").mkdir()
            (ctx_dir / "workflows" / "levantamento.yaml").write_text(
                "name: levantamento\ndescription: Old-name survey of the context.\nsteps:\n"
                "  - id: explore\n    agent: explorer\n", encoding="utf-8")
            aidw = load_aidw(root)
            cfg = aidw.load_config()
            self.assertIn("verify-premise", cfg["agents"]["planner"]["skills"])
            rep = aidw.Report(quiet=True)
            b = aidw.build(cfg, aidw.load_catalog(), rep)
            self.assertEqual(rep.errors, [])
            orq = b["orchestrator_md"]
            self.assertIn("- Bug → `development`", orq)
            self.assertIn("- Estimate → `survey`", orq)
            self.assertIn("Old-name survey of the context.", orq, "the context's old-name file replaces the core one")
            self.assertEqual(aidw.modern_name("workflow", "desenvolvimento"), "development")
            self.assertEqual(aidw.legacy_names("file", "metrics.md"), ("metrics.md", "metricas.md"))
            self.assertEqual(aidw.artifact_kind("roteiro-testes-us-1.md"), "test-script-")
            self.assertEqual(aidw.artifact_kind("plano-testes-us-1.md"), "test-plan-")
            self.assertEqual(aidw.artifact_kind("plan-us-1.md"), "plan-")
            self.assertTrue(aidw.is_generated("<!-- Gerado por aidw.py apply -->"), "the old mark is still cleaned up")


class LanguageTest(unittest.TestCase):
    """[ui] language (default English) is the language the orchestrator talks in; a context's `language` (inheriting
    it) is the language of the demand artifacts and the agents' reports. File names are always English."""

    def build(self, root: Path) -> tuple[object, dict]:
        aidw = load_aidw(root)
        rep = aidw.Report(quiet=True)
        b = aidw.build(aidw.load_config(), aidw.load_catalog(), rep)
        self.assertEqual(rep.errors, [])
        return aidw, b

    def test_default_and_propagation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            cfg_file = root / "aidw.config.toml"
            self.assertIn('[ui]', cfg_file.read_text(encoding="utf-8"))
            self.assertIn('language = "en"', cfg_file.read_text(encoding="utf-8"))
            # a config from before the setting (no [ui]) defaults to English
            cfg_file.write_text(re.sub(r"\[ui\]\n(?:#[^\n]*\n)*language = \"en\"\n", "",
                                       cfg_file.read_text(encoding="utf-8")), encoding="utf-8")
            self.assertNotIn("[ui]", cfg_file.read_text(encoding="utf-8"))
            aidw, b = self.build(root)
            self.assertEqual(aidw.load_config()["ui"]["language"], "en")
            self.assertIn("talk to the user in English (`en`). Write demand artifacts' content", b["orchestrator_md"])
            self.assertIn("in English (`en`); file names stay in English", b["orchestrator_md"])
            for g in b["agents"].values():
                self.assertIn("- Language: write your reports in English (`en`)", g["prompt"])

            cfg_file.write_text(cfg_file.read_text(encoding="utf-8") + '\n[ui]\nlanguage = "pt-BR"\n', encoding="utf-8")
            aidw, b = self.build(root)
            self.assertIn("talk to the user in Portuguese (Brazil) (`pt-BR`)", b["orchestrator_md"])
            self.assertIn("task files) in Portuguese (Brazil) (`pt-BR`)", b["orchestrator_md"],
                          "the context without `language` inherits the UI language")
            plug = aidw.build_plugin(aidw.load_config(), aidw.load_catalog(), aidw.Report(quiet=True))
            for skill in ("exit", "diff"):
                self.assertIn("Portuguese (Brazil)", plug["files"][f"plugins/aidw/skills/{skill}/SKILL.md"].decode("utf-8"))
            go = plug["files"]["plugins/aidw/skills/go/SKILL.md"].decode("utf-8")
            self.assertIn("talk to the user in Portuguese (Brazil)", go)
            show = run_aidw(root, "show")
            self.assertIn("Language: UI Portuguese (Brazil) (`pt-BR`); demand artifacts Portuguese (Brazil) (`pt-BR`) "
                          "(inherited from the UI)", show.stdout)

    def test_context_language(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            toml = root / "contexts" / "exemplo" / "context.toml"
            toml.write_text(toml.read_text(encoding="utf-8").replace(
                'description = "', 'language = "es"\ndescription = "', 1), encoding="utf-8")
            aidw, b = self.build(root)
            self.assertIn("talk to the user in English (`en`)", b["orchestrator_md"])
            self.assertIn("task files) in Spanish (`es`)", b["orchestrator_md"])
            self.assertIn("write your reports in Spanish (`es`)", b["agents"]["coder"]["prompt"])
            (Path(tmp) / "codex").mkdir()
            codex = make_sandbox(Path(tmp).resolve() / "codex", "codex", "native", "exemplo")
            toml = codex / "contexts" / "exemplo" / "context.toml"
            toml.write_text(toml.read_text(encoding="utf-8").replace(
                'description = "', 'language = "es"\ndescription = "', 1), encoding="utf-8")
            self.assertEqual(run_aidw(codex, "apply").returncode, 0)
            role = next((codex / ".codex" / "agents").glob("*.toml")).read_text(encoding="utf-8")
            self.assertIn("write your reports in Spanish", role, "Codex agent definitions too")

            # context create: the AiDW language by default, or --language; an invalid tag is refused
            cfg_file = root / "aidw.config.toml"
            cfg_file.write_text(cfg_file.read_text(encoding="utf-8").replace('language = "en"', 'language = "pt-BR"'),
                                encoding="utf-8")
            wt = WorktreeTest()
            code, made = wt.aidw_json(root, "context", "create", "herda", "--json")
            self.assertEqual(code, 0, made)
            self.assertIn('language = "pt-BR"', (root / "contexts" / "herda" / "context.toml").read_text(encoding="utf-8"))
            code, made = wt.aidw_json(root, "context", "create", "outro", "--language", "fr", "--json")
            self.assertEqual(code, 0, made)
            self.assertIn('language = "fr"', (root / "contexts" / "outro" / "context.toml").read_text(encoding="utf-8"))
            code, bad = wt.aidw_json(root, "context", "create", "ruim", "--language", "not a tag", "--json")
            self.assertEqual(code, 1, bad)

    def test_configure_defaults_language(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "")
            proc = run_aidw(root, "configure", "--defaults", "--language", "pt-BR")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn('language = "pt-BR"', (root / "aidw.config.toml").read_text(encoding="utf-8"))
            self.assertEqual(run_aidw(root, "configure", "--defaults", "--language", "x y").returncode, 1)


class InstallTest(unittest.TestCase):
    """install/uninstall in Claude (without the CLI): generated plugin, merge of the user's settings, idempotence,
    conflict with a hand-edited file and removal of only what AiDW added."""

    USER_SETTINGS = {"theme": "dark", "permissions": {"allow": ["Bash(git *)", "Bash(ls *)"]},
                     "env": {"MCP_TIMEOUT": "123"}}

    def marketplace(self, root: Path) -> dict[str, bytes]:
        base = root / ".aidw" / "marketplace"
        return {p.relative_to(base).as_posix(): p.read_bytes() for p in base.rglob("*") if p.is_file()}

    def test_install_uninstall(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            settings = root.parent / "claude-home" / "settings.json"
            settings.parent.mkdir()
            original = json.dumps(self.USER_SETTINGS, indent=2) + "\n"
            settings.write_text(original, encoding="utf-8")

            proc = run_aidw(root, "install", "--skip-cli")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            files = self.marketplace(root)
            base = "plugins/aidw"
            self.assertIn(".claude-plugin/marketplace.json", files)
            self.assertIn(f"{base}/agents/coder.md", files)
            self.assertIn(f"{base}/skills/skill-exemplo/SKILL.md", files)
            orq = files[f"{base}/skills/go/SKILL.md"].decode("utf-8")
            self.assertIn("disable-model-invocation: true", orq)
            self.assertIn("`aidw:coder", orq, "effort table with the plugin name")
            self.assertIn(f'python "{root.as_posix()}/aidw.py" record', orq, "aidw.py by absolute path")
            self.assertIn(f"{(root / '.aidw' / 'marketplace' / base / 'reference').as_posix()}/etapa.md", orq)
            self.assertIn("[AiDW]", files[f"{base}/agents/coder.md"].decode("utf-8"))
            exemplo = files[f"{base}/skills/skill-exemplo/SKILL.md"].decode("utf-8")
            self.assertIn("[AiDW]", exemplo)
            self.assertIn("\nuser-invocable: false\n---", exemplo, "flow skill out of the / menu")
            done = files[f"{base}/skills/done/SKILL.md"].decode("utf-8")
            self.assertIn("disable-model-invocation: true", done, "/aidw:done only when the user calls it")
            self.assertIn(f'python "{root.as_posix()}/aidw.py" context check', done)
            self.assertIn("aidw.py\" session unbind", done, "done takes the session out of the mode without the hook")
            self.assertIn("session unbind", files[f"{base}/skills/exit/SKILL.md"].decode("utf-8"))
            self.assertNotIn("user-invocable", done, "aidw: admin is a user command")
            self.assertNotIn("user-invocable", orq)
            self.assertIn("session bind", orq, "go turns the mode on without the hook")
            self.assertNotIn("aidw: admin", done)
            data = json.loads(settings.read_text(encoding="utf-8"))
            self.assertEqual(data["theme"], "dark")
            self.assertIn("Bash(rm -rf *)", data["permissions"]["deny"])
            self.assertIn("Bash(git commit *)", data["permissions"]["ask"])
            for sub in ("record *", "demand *", "worktree *", "project *", "context *"):
                self.assertIn(f'PowerShell(python "{root.as_posix()}/aidw.py" {sub})', data["permissions"]["allow"])
            self.assertEqual(data["env"]["MCP_TIMEOUT"], "123", "the user's value wins")

            before = (self.marketplace(root), settings.read_text(encoding="utf-8"))
            again = run_aidw(root, "install", "--skip-cli")
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
            self.assertEqual((self.marketplace(root), settings.read_text(encoding="utf-8")), before,
                             "install is not idempotent")

            edited = root / ".aidw" / "marketplace" / base / "agents" / "coder.md"
            edited.write_text("edited by hand\n", encoding="utf-8")
            conflict = run_aidw(root, "install", "--skip-cli")
            self.assertEqual(conflict.returncode, 1)
            self.assertIn("changed outside AiDW", conflict.stdout)
            self.assertEqual(run_aidw(root, "install", "--skip-cli", "--force").returncode, 0)

            gone = run_aidw(root, "uninstall", "--skip-cli")
            self.assertEqual(gone.returncode, 0, gone.stdout + gone.stderr)
            self.assertEqual(json.loads(settings.read_text(encoding="utf-8")), self.USER_SETTINGS,
                             "uninstall must give the user's settings back as they were")
            self.assertFalse((root / ".aidw" / "marketplace").exists())
            self.assertFalse((root / ".aidw" / "install-manifest.json").exists())

    def sandbox_with_settings(self, tmp: str, mode: str = "native") -> tuple[Path, Path]:
        root = make_sandbox(Path(tmp).resolve(), "claude", mode, "exemplo")
        settings = root.parent / "claude-home" / "settings.json"
        settings.parent.mkdir()
        settings.write_text(json.dumps(self.USER_SETTINGS, indent=2) + "\n", encoding="utf-8")
        return root, settings

    def test_cli_failure_keeps_the_rules_owner(self) -> None:
        """R1-01: the CLI fails after the settings are written; the manifest already records what is AiDW's."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root, settings = self.sandbox_with_settings(tmp)
            no_claude = {"PATH": os.pathsep.join([os.path.dirname(sys.executable),
                                                  os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")])}
            proc = run_aidw(root, "install", env_extra=no_claude)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            manifest = json.loads((root / ".aidw" / "install-manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["cli_done"])
            self.assertIn("Bash(rm -rf *)", manifest["settings"]["deny"])
            self.assertIn("Bash(rm -rf *)", json.loads(settings.read_text(encoding="utf-8"))["permissions"]["deny"])
            gone = run_aidw(root, "uninstall", "--skip-cli")
            self.assertEqual(gone.returncode, 0, gone.stdout + gone.stderr)
            self.assertEqual(json.loads(settings.read_text(encoding="utf-8")), self.USER_SETTINGS)

    def test_headless_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root, _ = self.sandbox_with_settings(tmp, mode="headless")
            proc = run_aidw(root, "install", "--skip-cli")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("native subagents", proc.stdout)

    def test_uninstall_without_manifest_warns(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root, _ = self.sandbox_with_settings(tmp)
            self.assertEqual(run_aidw(root, "install", "--skip-cli").returncode, 0)
            (root / ".aidw" / "install-manifest.json").unlink()
            proc = run_aidw(root, "uninstall", "--skip-cli")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("manifest missing", proc.stdout)


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                           *args], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


class WorktreeTest(unittest.TestCase):
    """worktree create/list/inspect/remove/cleanup, project detect, the WorktreeCreate hook and the guard."""

    def make_repo(self, tmp: Path) -> Path:
        repo = tmp / "repos" / "Aplicação"  # accent in the path: the hook has to read stdin as UTF-8
        repo.mkdir(parents=True)
        git(repo, "init", "-q", "-b", "main")
        (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        (repo / "app.txt").write_text("v1\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "initial")
        (repo / "node_modules" / "lib").mkdir(parents=True)
        (repo / "node_modules" / "lib" / "index.js").write_text("// dependency\n", encoding="utf-8")
        return repo

    def aidw_json(self, root: Path, *args: str, stdin: str | None = None) -> tuple[int, dict | str]:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "CLAUDE_CONFIG_DIR": str(root.parent / "claude-home"),
               "CODEX_HOME": str(root.parent / "codex-home"), "AIDW_CODEX_SKILLS_DIR": str(root.parent / "agents-skills")}
        proc = subprocess.run([sys.executable, str(root / "aidw.py"), *args], cwd=root, env=env, input=stdin,
                              capture_output=True, text=True, encoding="utf-8", timeout=120)
        try:
            return proc.returncode, json.loads(proc.stdout)
        except json.JSONDecodeError:
            return proc.returncode, proc.stdout + proc.stderr

    def guard(self, root: Path, payload: dict) -> str:
        # like Claude Code: UTF-8 JSON without escaping the accents
        proc = subprocess.run([sys.executable, str(root / "aidw_guard.py")],
                              input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                              capture_output=True, timeout=30)
        proc.stdout = proc.stdout.decode("utf-8")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_worktree_cycle(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "exemplo")
            repo = self.make_repo(tmp)

            code, wt = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-1",
                                      "--slug", "Slug test", "--json")
            self.assertEqual(code, 0, wt)
            path = Path(wt["path"])
            self.assertEqual(path, tmp / "wt" / "us-1" / "Aplicação")
            self.assertEqual(wt["branch"], "feature/1-slug-test")
            self.assertEqual(wt["base"], "main")
            self.assertEqual(wt["links"], ["node_modules"])
            self.assertTrue((path / "node_modules" / "lib" / "index.js").is_file())
            demand = json.loads((root / "contexts" / "exemplo" / "demandas" / "us-1" / "demand.json").read_text(encoding="utf-8"))
            self.assertEqual(demand["repos"][0]["branch"], "feature/1-slug-test")

            code, again = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-1", "--json")
            self.assertEqual((code, again["created"], again["path"]), (0, False, wt["path"]), "create is not idempotent")

            code, det = self.aidw_json(root, "project", "detect", "--path", str(path), "--json")
            self.assertEqual((det["demand"], det["is_worktree"], det["name"]), ("us-1", True, "Aplicação"))

            code, hook = self.aidw_json(root, "worktree", "hook-create",
                                        stdin=json.dumps({"name": "us-1", "cwd": str(tmp)}))
            self.assertEqual((code, hook.strip() if isinstance(hook, str) else hook), (0, str(path)))

            coder = {"hook_event_name": "PreToolUse", "agent_type": "aidw:coder-low", "tool_name": "Write",
                     "cwd": str(repo)}
            self.assertIn('"deny"', self.guard(root, {**coder, "tool_input": {"file_path": str(repo / "app.txt")}}))
            self.assertEqual(self.guard(root, {**coder, "tool_input": {"file_path": str(path / "app.txt")}}), "")
            old_name = {**coder, "agent_type": "aidw:codificador-low"}
            self.assertIn('"deny"', self.guard(root, {**old_name, "tool_input": {"file_path": str(repo / "app.txt")}}),
                          "an agent with the old default name is still an AiDW agent")
            nested = repo / "contexts" / "ctx"
            (nested / ".git").mkdir(parents=True)
            self.assertEqual(self.guard(root, {**coder, "tool_input": {"file_path": str(nested / "demandas" / "x.md")}}), "",
                             "another git repository nested in the repo is not its working copy")
            self.assertIn('"deny"', self.guard(root, {**coder, "tool_input": {"file_path": str(repo / "contexts" / "x.md")}}))
            codex = {"hook_event_name": "PreToolUse", "agent_type": "aidw-coder", "tool_name": "apply_patch",
                     "cwd": str(repo)}
            patch = lambda f: "*** Begin Patch\n*** Update File: " + f + "\n@@\n-v1\n+v2\n*** End Patch"  # noqa: E731
            self.assertIn('"deny"', self.guard(root, {**codex, "tool_input": {"command": patch("app.txt")}}),
                          "the patch's relative path, resolved by the cwd (main working copy)")
            self.assertEqual(self.guard(root, {**codex, "tool_input": {"command": patch(str(path / "app.txt"))}}), "")
            self.assertEqual(self.guard(root, {"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": str(repo),
                                               "tool_input": {"file_path": str(repo / "app.txt")}}), "",
                             "the main conversation has no rule")
            self.assertEqual(self.guard(root, {"hook_event_name": "PreToolUse", "agent_type": "Explore", "tool_name": "Write",
                                               "tool_input": {"file_path": str(repo / "app.txt")}}), "")

            commit = {"hook_event_name": "PreToolUse", "tool_name": "PowerShell", "cwd": str(tmp),
                      "tool_input": {"command": f'git -C "{path}" add -A && git -C "{path}" commit -m x'}}
            (path / "Mock.cs").write_text("// AIDW-TEST A1\n", encoding="utf-8")
            self.assertIn("AIDW-TEST", self.guard(root, commit), "commit with a test adjustment in the worktree")
            self.assertEqual(self.guard(root, {**commit, "tool_input": {"command": f'git -C "{path}" status'}}), "")
            (path / "Mock.cs").write_text("// AIDW-TESTE A1\n", encoding="utf-8")
            self.assertIn("AIDW-TEST", self.guard(root, commit), "the old mark is still caught")
            (path / "Mock.cs").unlink()
            self.assertEqual(self.guard(root, commit), "", "without the mark, the commit goes to the permission prompt")

            (path / "app.txt").write_text("v2\n", encoding="utf-8")
            code, err = self.aidw_json(root, "worktree", "remove", "us-1", "--json")
            self.assertEqual(code, 1)
            self.assertIn("uncommitted", err["error"])
            git(path, "commit", "-q", "-am", "change")
            code, err = self.aidw_json(root, "worktree", "remove", "us-1", "--json")
            self.assertEqual(code, 1)
            self.assertIn("unpublished", err["error"])
            git(path, "reset", "-q", "--keep", "main")  # drops the test commit (disposable worktree)
            code, done = self.aidw_json(root, "worktree", "remove", "us-1", "--json")
            self.assertEqual(code, 0, done)
            self.assertFalse(path.exists())
            self.assertTrue((repo / "node_modules" / "lib" / "index.js").is_file(), "the junction must not delete the source")
            self.assertIn("feature/1-slug-test", git(repo, "branch"), "the branch is kept")

            code, wt2 = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-2", "--json")
            self.assertEqual(code, 0, wt2)
            os.rmdir(Path(wt2["path"]) / "node_modules")  # removes only the junction
            shutil.rmtree(wt2["path"])
            code, clean = self.aidw_json(root, "worktree", "cleanup", "--json")
            self.assertEqual(clean["removed_from_registry"], [wt2["path"]])
            code, listed = self.aidw_json(root, "worktree", "list", "--json")
            self.assertEqual(listed["worktrees"], [])

    def test_pr_worktree(self) -> None:
        """`worktree create --pr`: worktree detached at the PR merged into the target (refs/pull/<n>/merge), diff in
        the demand folder, update when the author changes the PR (only what changed) and removal without a branch."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "exemplo")
            origin = tmp / "origin"
            origin.mkdir()
            git(origin, "init", "-q", "-b", "main")
            (origin / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
            (origin / "app.txt").write_text("v1\n", encoding="utf-8")
            git(origin, "add", ".")
            git(origin, "commit", "-q", "-m", "initial")

            def publish_pr(content: str) -> None:  # the server builds the PR's merge with the target
                git(origin, "checkout", "-q", "-B", "feature/author")
                (origin / "app.txt").write_text(content, encoding="utf-8")
                git(origin, "commit", "-q", "-am", f"author: {content.strip()}")
                git(origin, "checkout", "-q", "--detach", "main")
                git(origin, "merge", "-q", "--no-ff", "-m", "PR merge", "feature/author")
                git(origin, "update-ref", "refs/pull/1/merge", "HEAD")
                git(origin, "checkout", "-q", "main")

            publish_pr("v2\n")
            repo = tmp / "repos" / "Aplicação"
            repo.parent.mkdir(parents=True)
            subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True, capture_output=True)
            (repo / "node_modules" / "lib").mkdir(parents=True)
            (repo / "node_modules" / "lib" / "index.js").write_text("// dependency\n", encoding="utf-8")
            folder = root / "contexts" / "exemplo" / "demandas" / "us-7"

            code, err = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-7",
                                       "--pr", "9", "--json")
            self.assertEqual(code, 1)
            self.assertIn("refs/pull/9/merge", err["error"])

            code, wt = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-7",
                                      "--pr", "1", "--json")
            self.assertEqual(code, 0, wt)
            path = Path(wt["path"])
            self.assertEqual((wt["branch"], wt["pr"]), ("pr/1", "1"))
            self.assertEqual(git(path, "rev-parse", "--abbrev-ref", "HEAD").strip(), "HEAD", "detached, no branch")
            self.assertEqual((path / "app.txt").read_text(encoding="utf-8"), "v2\n")
            self.assertTrue((path / "node_modules" / "lib" / "index.js").is_file())
            self.assertNotIn("feature/", git(repo, "branch"), "no local branch is created")
            diff = (folder / "diff-pr1-Aplicação.patch").read_text(encoding="utf-8")
            self.assertIn("+v2", diff)
            self.assertEqual(json.loads((folder / "demand.json").read_text(encoding="utf-8"))["repos"][0]["pr"], "1")

            code, same = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-7",
                                        "--pr", "1", "--json")
            self.assertEqual((code, same["updated"]), (0, False))
            code, other = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-7", "--json")
            self.assertEqual(code, 1, "the demand already has the PR in that repository")

            publish_pr("v3\n")
            code, upd = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-7",
                                       "--pr", "1", "--json")
            self.assertEqual((code, upd["updated"], upd["round"]), (0, True, 2), upd)
            self.assertEqual((path / "app.txt").read_text(encoding="utf-8"), "v3\n")
            incremental = (folder / "diff-pr1-Aplicação-r2.patch").read_text(encoding="utf-8")
            self.assertIn("-v2", incremental)
            self.assertIn("+v3", incremental)
            self.assertIn("+v3", (folder / "diff-pr1-Aplicação.patch").read_text(encoding="utf-8"))

            code, done = self.aidw_json(root, "worktree", "remove", "us-7", "--json")
            self.assertEqual(code, 0, done)
            self.assertFalse(path.exists())
            self.assertTrue((repo / "node_modules" / "lib" / "index.js").is_file(), "the junction must not delete the source")
            self.assertEqual(git(repo, "for-each-ref", "refs/aidw").strip(), "", "the PR ref goes too")

    def test_guard_mcp_per_agent(self) -> None:
        """Codex does not limit MCP per agent: the guard refuses a server outside the role and a tool blocked by the
        context; the CLI's own MCP and the main conversation pass."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "codex", "native", "exemplo")
            proc = run_aidw(root, "apply")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            def call(agent: str | None, tool: str) -> str:
                return self.guard(root, {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {},
                                         **({"agent_type": agent} if agent else {})})

            self.assertIn('"deny"', call("aidw-coder", "mcp__servidor-exemplo__escrever"), "blocked by the context")
            self.assertIn('"deny"', call("aidw:coder-high", "mcp__servidor-exemplo__escrever"), "a Claude variant")
            self.assertEqual(call("aidw-coder", "mcp__servidor-exemplo__ler"), "")
            self.assertIn('"deny"', call("aidw-explorer", "mcp__playwright__browser_click"), "not the role's")
            self.assertEqual(call("aidw-qa", "mcp__playwright__browser_click"), "")
            self.assertEqual(call("aidw-explorer", "mcp__node_repl__js"), "", "Codex's own MCP")
            self.assertEqual(call(None, "mcp__servidor-exemplo__escrever"), "", "the main conversation")

    def test_worktree_link_of_neighbor_folders(self) -> None:
        """The system's `worktree_link`: the relative path the code uses (HintPath `..\\..\\X`) becomes a junction
        next to the worktree; outside the worktree root it is refused; remove does not delete the shared junction."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "exemplo")
            repo = self.make_repo(tmp)
            (tmp / "repos" / "Vizinho" / "bin").mkdir(parents=True)
            (tmp / "repos" / "Vizinho" / "bin" / "lib.dll").write_text("dll\n", encoding="utf-8")
            with open(root / "contexts" / "exemplo" / "context.toml", "a", encoding="utf-8") as f:
                f.write(f'\n[systems.app]\nname = "App"\nrepos = ["{repo.as_posix()}"]\n'
                        'worktree_link = ["../Vizinho", "../../fora", "../../../escapa"]\n')
            code, wt = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-5", "--json")
            self.assertEqual(code, 0, wt)
            self.assertEqual(wt["system"], "app")
            self.assertEqual(wt["outside_links"], ["../Vizinho"])
            neighbor = tmp / "wt" / "us-5" / "Vizinho"
            self.assertTrue((neighbor / "bin" / "lib.dll").is_file(), "the HintPath ..\\Vizinho resolves from the worktree")
            self.assertTrue(any("does not exist" in w for w in wt["warnings"]), wt["warnings"])
            self.assertTrue(any("ignored" in w for w in wt["warnings"]), wt["warnings"])
            self.assertFalse((tmp / "escapa").exists(), "never creates a junction outside the worktree root")
            code, wt2 = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-6", "--json")
            self.assertEqual(wt2["outside_links"], ["../Vizinho"], "each demand has its own, in its folder")
            self.assertTrue((tmp / "wt" / "us-6" / "Vizinho" / "bin" / "lib.dll").is_file())
            (tmp / "outra").mkdir()
            (tmp / "wt" / "us-7").mkdir()
            load_aidw(root).make_link(tmp / "wt" / "us-7" / "Vizinho", tmp / "outra")
            code, wt3 = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-7", "--json")
            self.assertEqual(wt3["outside_links"], [], "a junction to somewhere else is not reused")
            self.assertTrue(any("somewhere else" in w for w in wt3["warnings"]), wt3["warnings"])

            namesake = tmp / "outros" / "Aplicação"  # same name, another repository (e.g. New/App x Legacy/App)
            namesake.mkdir(parents=True)
            git(namesake, "init", "-q", "-b", "main")
            (namesake / "b.txt").write_text("b\n", encoding="utf-8")
            git(namesake, "add", ".")
            git(namesake, "commit", "-q", "-m", "initial")
            code, wt4 = self.aidw_json(root, "worktree", "create", "--repo", str(namesake), "--demand", "us-5", "--json")
            self.assertEqual(code, 0, wt4)
            self.assertEqual(Path(wt4["path"]), tmp / "wt" / "us-5" / "Aplicação.outros", "does not take the namesake's folder")
            code, done = self.aidw_json(root, "worktree", "remove", "us-5", "--repo", str(repo), "--json")
            self.assertEqual(code, 0, done)
            self.assertTrue((neighbor / "bin" / "lib.dll").is_file(), "the demand still has a worktree: the junction stays")
            code, done = self.aidw_json(root, "worktree", "remove", "us-5", "--repo", str(namesake), "--json")
            self.assertEqual(code, 0, done)
            self.assertFalse((tmp / "wt" / "us-5").exists(), "without worktrees, the demand folder goes with the junctions")
            self.assertTrue((tmp / "repos" / "Vizinho" / "bin" / "lib.dll").is_file(), "never deletes through the junction")

            # the demand also changes the neighbor: its junction becomes the demand's worktree
            aidw = load_aidw(root)
            viz = tmp / "repos" / "Vizinho"
            git(viz, "init", "-q", "-b", "main")
            git(viz, "add", ".")
            git(viz, "commit", "-q", "-m", "initial")
            code, w8 = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-8", "--json")
            self.assertEqual(code, 0, w8)
            junction = tmp / "wt" / "us-8" / "Vizinho"
            self.assertTrue(aidw.is_link(junction))
            code, err = self.aidw_json(root, "worktree", "create", "--repo", str(viz), "--demand", "us-8",
                                       "--base", "does-not-exist", "--json")
            self.assertEqual(code, 1, err)
            self.assertTrue(aidw.is_link(junction), "an error in create does not remove the junction the build needs")
            code, w8v = self.aidw_json(root, "worktree", "create", "--repo", str(viz), "--demand", "us-8", "--json")
            self.assertEqual((code, Path(w8v["path"])), (0, junction), w8v)
            self.assertFalse(aidw.is_link(junction))
            self.assertTrue(any("was a junction" in w for w in w8v["warnings"]), w8v["warnings"])
            self.assertTrue((viz / "bin" / "lib.dll").is_file())
            (tmp / "wt" / "us-8" / "notes.txt").write_text("x\n", encoding="utf-8")
            for r in (repo, viz):
                code, rm = self.aidw_json(root, "worktree", "remove", "us-8", "--repo", str(r), "--json")
                self.assertEqual(code, 0, rm)
            self.assertTrue((tmp / "wt" / "us-8" / "notes.txt").is_file(), "with another file, the demand folder stays")

    def test_worktree_in_the_old_layout(self) -> None:
        """Worktrees created before the per-demand folder (`<root>/<repo>/<demand>`, no `layout` in the registry)
        still work: list, the `<demand>/<folder>` hook, open and remove."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "exemplo")
            repo = self.make_repo(tmp)
            old = tmp / "wt" / repo.name / "us-40"
            git(repo, "worktree", "add", "-q", "-b", "feature/40", str(old), "main")
            reg = root / "state" / "worktrees.json"
            reg.parent.mkdir(parents=True, exist_ok=True)
            reg.write_text(json.dumps({"worktrees": [
                {"demand": "us-40", "repo": repo.as_posix(), "path": old.as_posix(), "branch": "feature/40",
                 "base": "main", "links": [], "status": "active", "context": "exemplo"}]}), encoding="utf-8")
            code, lst = self.aidw_json(root, "worktree", "list", "--json")
            self.assertEqual(lst["worktrees"][0]["folder"], repo.name)
            code, hook = self.aidw_json(root, "worktree", "hook-create",
                                        stdin=json.dumps({"name": f"us-40/{repo.name}", "cwd": str(tmp)}))
            self.assertEqual((code, Path(hook.strip())), (0, old))
            code, out = self.aidw_json(root, "open", "--demand", "us-40", "--print")
            self.assertIn(f"Opening claude in {old}", out)
            code, rm = self.aidw_json(root, "worktree", "remove", "us-40", "--json")
            self.assertEqual(code, 0, rm)
            self.assertFalse(old.exists())

    def test_status_and_open(self) -> None:
        """F7: `status` joins active demand and worktree and points out what needs attention; `open --demand` opens
        in the worktree calling the orchestrator (only if AiDW is installed in that provider)."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "exemplo")
            repo = self.make_repo(tmp)
            code, wt = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-1", "--json")
            self.assertEqual(code, 0, wt)
            self.aidw_json(root, "demand", "set", "us-1", "--step", "IMPLEMENT", "--title", "Test")
            code, st = self.aidw_json(root, "status", "--json")
            self.assertEqual(code, 0, st)
            self.assertEqual([(d["id"], d["step"]) for d in st["demands"]], [("us-1", "IMPLEMENT")])
            w = st["demands"][0]["worktrees"][0]
            self.assertEqual((w["path"], w["dirty"], w["ahead"]), (wt["path"], False, 0))
            self.assertFalse(st["claude"]["installed"])
            self.assertEqual(st["attention"], [])

            code, out = self.aidw_json(root, "open", "--demand", "1", "--print")
            self.assertEqual(code, 0, out)
            self.assertIn(f"Opening claude in {Path(wt['path'])}", out)
            self.assertIn("not installed", out)
            self.assertNotRegex(out.strip().splitlines()[-1], r"(:|aidw-)go\b", "without the plugin, the command does not exist")
            manifest = root / ".aidw" / "install-manifest.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"plugins": ["aidw@aidw-local"], "context": "exemplo", "codex": {"files": {}}}),
                                encoding="utf-8")
            code, out = self.aidw_json(root, "open", "--demand", "us-1", "--print")
            self.assertIn('"/aidw:go us-1"', out)
            self.assertIn("--add-dir", out)
            code, out = self.aidw_json(root, "open", "--demand", "us-1", "--provider", "codex", "--print")
            self.assertIn("--enable multi_agent_v2", out)
            self.assertNotIn("--profile", out, "on Codex AiDW installs no profile")
            self.assertIn('"$aidw-go us-1"', out)
            code, out = self.aidw_json(root, "open", "--demand", "us-1", "--no-orchestrate", "--print")
            self.assertNotRegex(out, r"(:|aidw-)go\b")
            code, out = self.aidw_json(root, "open", "--demand", "us-9", "--print")
            self.assertEqual(code, 1)

            # back and front in the same demand: opens in the demand folder; --repo opens in one, the other by --add-dir
            front = tmp / "repos" / "Front"
            front.mkdir(parents=True)
            git(front, "init", "-q", "-b", "main")
            (front / "a.txt").write_text("a\n", encoding="utf-8")
            git(front, "add", ".")
            git(front, "commit", "-q", "-m", "initial")
            code, wtf = self.aidw_json(root, "worktree", "create", "--repo", str(front), "--demand", "us-1", "--json")
            self.assertEqual(code, 0, wtf)
            code, out = self.aidw_json(root, "open", "--demand", "us-1", "--print")
            self.assertEqual(code, 0, out)
            self.assertIn(f"Opening claude in {Path(wt['path']).parent}", out, "opens in the demand folder")
            self.assertNotIn(f"--add-dir {Path(wtf['path'])}", out, "the worktrees are already inside it")
            code, out = self.aidw_json(root, "open", "--demand", "us-1", "--repo", "Front", "--print")
            self.assertIn(f"Opening claude in {Path(wtf['path'])}", out)
            self.assertIn(f"--add-dir {Path(wt['path'])}", out)
            code, out = self.aidw_json(root, "open", "--demand", "us-1", "--repo", "None", "--print")
            self.assertEqual(code, 1, out)
            code, wtb = self.aidw_json(root, "worktree", "create", "--repo", str(front), "--demand", "bug-1",
                                       "--slug", "other", "--json")
            self.assertEqual(code, 0, wtb)
            code, out = self.aidw_json(root, "open", "--demand", "1", "--print")
            self.assertEqual(code, 1, "1 matches us-1 and bug-1: it does not choose")
            self.assertIn("more than one demand", out)
            for demand in ("us-1", "bug-1"):
                code, rm = self.aidw_json(root, "worktree", "remove", demand, "--repo", str(front), "--json")
                self.assertEqual(code, 0, rm)
            self.aidw_json(root, "demand", "set", "bug-1", "--status", "done")

            self.aidw_json(root, "demand", "set", "us-1", "--status", "done")
            (Path(wt["path"]) / "app.txt").write_text("v2\n", encoding="utf-8")
            code, st = self.aidw_json(root, "status", "--json")
            self.assertEqual(st["demands"], [])
            self.assertEqual(len(st["attention"]), 1, st["attention"])
            self.assertIn("uncommitted", st["attention"][0])
            git(Path(wt["path"]), "checkout", "--", "app.txt")
            code, st = self.aidw_json(root, "status", "--json")
            self.assertIn("worktree remove us-1", st["attention"][0])
            code, text = self.aidw_json(root, "status")
            self.assertEqual(code, 0, text)
            self.assertIn("Active demands (0)", text)
            (root / "contexts" / "exemplo" / "demandas" / "us-1" / "demand.json").unlink()
            code, st = self.aidw_json(root, "status", "--json")
            self.assertIn("without demand.json", st["attention"][0], "a worktree without demand.json must not vanish")
            manifest.write_text(json.dumps({"plugins": ["aidw@aidw-local"], "context": "exemplo", "cli_done": False}),
                                encoding="utf-8")
            code, text = self.aidw_json(root, "status")
            self.assertIn("the last install stopped", text, "an incomplete install is not 'up to date'")

    def test_creation_and_detection_scenarios(self) -> None:
        """F4 exit criteria: subfolder, outside git, existing branch, branch used by another worktree, git failure on
        remove (fail-safe) and the hook filtering by repository."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "exemplo")
            repo = self.make_repo(tmp)
            (repo / "src").mkdir()
            code, det = self.aidw_json(root, "project", "detect", "--path", str(repo / "src"), "--json")
            self.assertEqual((det["git"], det["main"], det["is_worktree"]), (True, repo.as_posix(), False))
            code, det = self.aidw_json(root, "project", "detect", "--path", str(tmp), "--json")
            self.assertFalse(det["git"])

            git(repo, "branch", "feature/7-existing")
            code, wt = self.aidw_json(root, "worktree", "create", "--repo", str(repo / "src"), "--demand", "us-7",
                                      "--slug", "existing", "--json")
            self.assertEqual((code, wt["branch"]), (0, "feature/7-existing"), wt)
            git(repo, "branch", "feature/8")
            git(repo, "worktree", "add", str(tmp / "manual"), "feature/8")
            code, err = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-8", "--json")
            self.assertEqual(code, 1)
            self.assertIn("git worktree add failed", err["error"])

            other = tmp / "repos" / "Outro"
            other.mkdir(parents=True)
            git(other, "init", "-q", "-b", "main")
            (other / "a.txt").write_text("a\n", encoding="utf-8")
            git(other, "add", ".")
            git(other, "commit", "-q", "-m", "initial")
            code, hook = self.aidw_json(root, "worktree", "hook-create", stdin=json.dumps({"name": "us-7", "cwd": str(other)}))
            self.assertEqual(code, 0, hook)
            self.assertEqual(Path(hook.strip()), tmp / "wt" / "us-7" / "Outro", "the hook must not lead to another repository")

            # chat opened at the AiDW root (also a repository): enters the worktree the demand already has
            git(root, "init", "-q", "-b", "main")
            code, hook = self.aidw_json(root, "worktree", "hook-create", stdin=json.dumps({"name": "us-7", "cwd": str(root)}))
            self.assertEqual((code, Path(hook.strip())), (0, Path(wt["path"])),
                             "us-7 has worktrees in two repositories: the root enters the first one created")
            # diff skill: `<demand>/<folder>` leads to that repository's worktree, from any folder
            code, hook = self.aidw_json(root, "worktree", "hook-create",
                                        stdin=json.dumps({"name": "us-7/outro", "cwd": str(repo)}))
            self.assertEqual((code, Path(hook.strip())), (0, tmp / "wt" / "us-7" / "Outro"))
            code, det = self.aidw_json(root, "project", "detect", "--path", str(tmp / "wt" / "us-7"), "--json")
            self.assertEqual((det["demand"], [w["folder"] for w in det["worktrees"]]), ("us-7", ["Aplicação", "Outro"]),
                             "the demand folder (not git) is recognized")
            code, err = self.aidw_json(root, "worktree", "hook-create",
                                       stdin=json.dumps({"name": "us-7/None", "cwd": str(repo)}))
            self.assertEqual(code, 1, err)
            code, wt9 = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-9", "--json")
            self.assertEqual(code, 0, wt9)
            code, hook = self.aidw_json(root, "worktree", "hook-create", stdin=json.dumps({"name": "us-9", "cwd": str(root)}))
            self.assertEqual((code, Path(hook.strip())), (0, Path(wt9["path"])), "no worktree of AiDW itself")
            self.assertFalse((tmp / "wt" / "us-9" / root.name).exists())
            self.aidw_json(root, "demand", "set", "us-10", "--status", "active", "--json")
            code, err = self.aidw_json(root, "worktree", "hook-create", stdin=json.dumps({"name": "us-10", "cwd": str(root)}))
            self.assertEqual(code, 1, "demand without a worktree: the AiDW root does not become its worktree")
            self.assertIn("worktree create --repo", err)
            self.assertFalse((tmp / "wt" / "us-10").exists())

            path = Path(wt["path"])
            (path / "new.txt").write_text("x\n", encoding="utf-8")
            git(path, "add", ".")
            git(path, "commit", "-q", "-m", "unpublished")
            git(repo, "branch", "-m", "main", "principal")  # the base is gone: git fails to count the commits
            code, err = self.aidw_json(root, "worktree", "remove", "us-7", "--repo", str(repo), "--json")
            self.assertEqual(code, 1, err)
            self.assertIn("could not check", err["error"])
            self.assertTrue(path.is_dir(), "a git failure never removes the worktree")


class SessionModeTest(unittest.TestCase):
    """F5: demand set/show/list and the session hooks (UserPromptSubmit records the mode; SessionStart reminds it)."""

    def test_demand_and_orchestrator_mode(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "exemplo")
            wt = WorktreeTest()
            code, d = wt.aidw_json(root, "demand", "set", "us-5", "--status", "active", "--step", "UNDERSTAND",
                                   "--title", "Test", "--json")
            self.assertEqual((code, d["step"], d["status"]), (0, "UNDERSTAND", "active"), d)
            code, d = wt.aidw_json(root, "demand", "set", "us-5", "--step", "IMPLEMENT", "--json")
            self.assertEqual([h["step"] for h in d["history"]], ["UNDERSTAND", "IMPLEMENT"])
            code, bad = wt.aidw_json(root, "demand", "set", "us-5", "--step", "ANYTHING", "--json")
            self.assertEqual(code, 1)
            wt.aidw_json(root, "demand", "set", "us-6", "--status", "done", "--json")
            code, lst = wt.aidw_json(root, "demand", "list", "--active", "--json")
            self.assertEqual([x["id"] for x in lst["demands"]], ["us-5"])
            code, show = wt.aidw_json(root, "demand", "show", "us-5")
            self.assertEqual(show["title"], "Test")
            self.assertNotIn("mode", lst["demands"][0], "the session mode left in flow v3")
            proc = run_aidw(root, "demand", "set", "us-5", "--note", "waiting")
            self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "us-5: IMPLEMENT (active)"),
                             "without --json, one line: the whole demand.json would only weigh on the orchestrator chat")
            proc = run_aidw(root, "demand", "set", "us-5", "--step", "ANYTHING")
            self.assertEqual(proc.returncode, 1)
            self.assertTrue(proc.stdout.startswith("error: unknown step"), proc.stdout)
            # panel V2: summary, steps outside AiDW and PR per repository
            code, d = wt.aidw_json(root, "demand", "set", "us-5", "--summary", "Line 1\nLine 2", "--step",
                                   "CODE_REVIEW", "--json")
            self.assertEqual((code, d["summary"], d["step"]), (0, "Line 1\nLine 2", "CODE_REVIEW"), d)
            code, bad = wt.aidw_json(root, "demand", "set", "us-5", "--summary", "1\n2\n3\n4\n5", "--json")
            self.assertEqual(code, 1, "summary over 4 lines")
            code, bad = wt.aidw_json(root, "demand", "set", "us-5", "--pr", "Front=7789", "--json")
            self.assertEqual(code, 1, "a repository the demand does not have")
            code, bad = wt.aidw_json(root, "demand", "set", "us-5", "--pr", "Front", "--json")
            self.assertEqual(code, 1, "--pr without a number")
            code, d = wt.aidw_json(root, "demand", "set", "us-5", "--step", "QA_TEST", "--json")
            self.assertEqual(d["history"][-1]["step"], "QA_TEST")
            demand_file = Path(d["folder"]) / "demand.json"
            data = json.loads(demand_file.read_text(encoding="utf-8"))
            data["repos"] = [{"repo": "C:/p/App.Front", "path": "C:/wt/us-5/App.Front", "branch": "b"}]
            demand_file.write_text(json.dumps(data), encoding="utf-8")
            code, d = wt.aidw_json(root, "demand", "set", "us-5", "--pr", "app.front=7789", "--json")
            self.assertEqual((code, d["repos"][0]["pr"]), (0, "7789"), d)

            hook = lambda payload: subprocess.run([sys.executable, str(root / "aidw_guard.py")],  # noqa: E731
                                                  input=json.dumps(payload), capture_output=True, text=True,
                                                  encoding="utf-8", timeout=30).stdout
            base = {"session_id": "s1", "cwd": str(tmp)}
            self.assertEqual(hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "hi, how are you?"}), "")
            self.assertFalse((root / "state" / "sessions.json").exists(), "a plain message writes nothing")
            self.assertEqual(hook({**base, "hook_event_name": "SessionStart", "source": "compact"}), "")
            hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "/aidw:go us-5 continue"})
            out = json.loads(hook({**base, "hook_event_name": "SessionStart", "source": "compact"}))
            ctx = out["hookSpecificOutput"]["additionalContext"]
            self.assertIn("orchestrator mode", ctx)
            self.assertIn("aidw/skills/go/SKILL.md", ctx)
            self.assertIn("us-5 continue", ctx)
            self.assertLess(len(ctx.encode()), 2000, "the hook only injects ~2 KB")
            self.assertEqual(hook({"session_id": "s2", "hook_event_name": "SessionStart", "source": "compact"}), "")
            hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "/aidw:exit"})
            cx = {"session_id": "c1", "cwd": str(tmp)}
            hook({**cx, "hook_event_name": "UserPromptSubmit", "prompt": "$aidw-go us-7"})
            out = json.loads(hook({**cx, "hook_event_name": "SessionStart", "source": "compact"}))
            ctx_codex = out["hookSpecificOutput"]["additionalContext"]
            self.assertIn("aidw-go/SKILL.md", ctx_codex)
            self.assertIn("$aidw-exit", ctx_codex)
            self.assertEqual(hook({**base, "hook_event_name": "SessionStart", "source": "resume"}), "")
            hook({**cx, "hook_event_name": "UserPromptSubmit", "prompt": "$aidw-done"})
            self.assertEqual(hook({**cx, "hook_event_name": "SessionStart", "source": "compact"}), "",
                             "done closes the task and ends orchestrator mode, like exit")
            lv = {"session_id": "l1", "cwd": str(tmp)}
            hook({**lv, "hook_event_name": "UserPromptSubmit", "prompt": "/aidw:survey us-8"})
            out = json.loads(hook({**lv, "hook_event_name": "SessionStart", "source": "compact"}))
            ctx_survey = out["hookSpecificOutput"]["additionalContext"]
            self.assertIn("aidw/skills/survey/SKILL.md", ctx_survey, "a survey resumes with its own lean skill")
            self.assertIn('"survey us-8"', ctx_survey)
            # the other orchestrator skills enter the mode and resume with their own skill
            for n, (prompt, skill) in enumerate((("/aidw:ask how does the token expire?", "aidw/skills/ask/"),
                                                 ("/aidw:fix bug 123", "aidw/skills/fix/"),
                                                 ("/aidw:kb-review liveness", "aidw/skills/kb-review/"),
                                                 ("$aidw-investigate timeout no Hope", "aidw-investigate/"))):
                sx = {"session_id": f"m{n}", "cwd": str(tmp)}
                hook({**sx, "hook_event_name": "UserPromptSubmit", "prompt": prompt})
                out = json.loads(hook({**sx, "hook_event_name": "SessionStart", "source": "compact"}))
                self.assertIn(skill + "SKILL.md", out["hookSpecificOutput"]["additionalContext"], prompt)
            hook({"session_id": "m9", "cwd": str(tmp), "hook_event_name": "UserPromptSubmit",
                  "prompt": "/aidw:cardapio"})
            self.assertEqual(hook({"session_id": "m9", "hook_event_name": "SessionStart", "source": "compact"}), "",
                             "a skill whose name only starts like a mode's is not one")
            code, d = wt.aidw_json(root, "demand", "set", "us-8", "--step", "ESTIMATE", "--json")
            self.assertEqual((code, d["step"]), (0, "ESTIMATE"), d)

            # session bind: turns the mode on without the hook (the terminal does not send /aidw:go to the hook) and
            # the demand comes from the registry, with context and folder, for any id (a free demand without a number)
            sessions = lambda: json.loads((root / "state" / "sessions.json").read_text(encoding="utf-8"))  # noqa: E731
            with unittest.mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "t1"}):
                code, d = wt.aidw_json(root, "session", "bind", "--json")
                self.assertEqual((code, d.get("demand")), (0, None), d)
                code, d = wt.aidw_json(root, "session", "bind", "--demand", "feat-does-not-exist", "--json")
                self.assertEqual(code, 1, "a demand without demand.json does not bind")
                code, d = wt.aidw_json(root, "demand", "set", "feat-panel-v5", "--status", "active", "--json")
                self.assertEqual(code, 0, d)
                entry = sessions()["t1"]
                self.assertEqual((entry["demand"], entry["context"]), ("feat-panel-v5", d["context"]))
                self.assertTrue(entry["folder"].endswith("/feat-panel-v5"), entry)
                code, d = wt.aidw_json(root, "session", "bind", "--demand", "us-8", "--json")
                self.assertEqual((code, sessions()["t1"]["demand"]), (0, "us-8"), d)
            out = json.loads(hook({"session_id": "t1", "hook_event_name": "SessionStart", "source": "compact"}))
            self.assertIn("on demand us-8", out["hookSpecificOutput"]["additionalContext"])
            with unittest.mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "t3"}):
                wt.aidw_json(root, "session", "bind", "--json")
                code, d = wt.aidw_json(root, "demand", "set", "inv-hope-timeout", "--step", "ANSWER", "--json")
                self.assertEqual((code, d["step"]), (0, "ANSWER"), d)
            out = json.loads(hook({"session_id": "t3", "hook_event_name": "SessionStart", "source": "compact"}))
            self.assertIn("aidw/skills/investigate/SKILL.md", out["hookSpecificOutput"]["additionalContext"],
                          "bound without the hook (terminal): the demand's prefix gives the skill")
            with unittest.mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "t2"}):
                wt.aidw_json(root, "demand", "set", "us-8", "--step", "DONE", "--json")
            self.assertNotIn("t2", sessions(), "demand set outside orchestrator mode does not bind the session")
            code, d = wt.aidw_json(root, "session", "unbind", "--session", "t1", "--json")
            self.assertNotIn("t1", sessions())

    def test_context_and_corrupt_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            wt = WorktreeTest()
            folder = root / "contexts" / "exemplo" / "demandas"
            (folder / "us-8").mkdir(parents=True)
            (folder / "us-8" / "demand.json").write_text(json.dumps({"id": "us-8", "context": "other"}), encoding="utf-8")
            code, lst = wt.aidw_json(root, "demand", "list", "--json")
            self.assertEqual(lst["demands"], [], "a demand of another context does not show")
            code, err = wt.aidw_json(root, "demand", "set", "us-8", "--step", "IMPLEMENT", "--json")
            self.assertEqual(code, 1)
            self.assertIn("context", err["error"])
            (folder / "us-9").mkdir()
            (folder / "us-9" / "demand.json").write_text("{broken", encoding="utf-8")
            code, d = wt.aidw_json(root, "demand", "set", "us-9", "--step", "IMPLEMENT", "--json")
            self.assertEqual(code, 0, d)
            self.assertIn("unreadable", d["warning"])
            self.assertTrue(list((folder / "us-9").glob("demand.json.*.bak")), "the unreadable file is kept")

    def test_plugin_carries_hooks_and_protocol(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            aidw = load_aidw(root)
            plug = aidw.build_plugin(aidw.load_config(), aidw.load_catalog(), aidw.Report(quiet=True))
            files = plug["files"]
            hooks = json.loads(files["plugins/aidw/hooks/hooks.json"])["hooks"]
            self.assertEqual(set(hooks), {"PreToolUse", "UserPromptSubmit", "SessionStart", "WorktreeCreate",
                                          "WorktreeRemove"})
            self.assertEqual(hooks["SessionStart"][0]["matcher"], "compact|resume")
            self.assertIn("aidw_guard.py", hooks["UserPromptSubmit"][0]["hooks"][0]["command"])
            # Claude Code mods: their own plugin in the marketplace, without the tests, with this machine's AiDW root
            self.assertEqual(plug["mods"]["plugin"], "aidw-mods")
            self.assertIn("plugins/aidw-mods/hooks/register.tsx", files)
            self.assertFalse([k for k in files if k.startswith("plugins/aidw-mods/tests/")], "the tests do not go")
            mods_meta = json.loads(files["plugins/aidw-mods/.claude-plugin/plugin.json"])
            self.assertEqual(mods_meta["userConfig"]["aidwRoot"]["default"], root.as_posix())
            self.assertEqual(mods_meta["version"], plug["mods"]["version"])
            market = json.loads(files[".claude-plugin/marketplace.json"])
            self.assertEqual([p["name"] for p in market["plugins"]], ["aidw-mods", "aidw"])
            orq = files["plugins/aidw/skills/go/SKILL.md"].decode("utf-8")
            for step in ("project detect --json", "demand list --active --json", "do not start over",
                         "demand set <id> --step <ACTION>", "EnterWorktree"):
                self.assertIn(step, orq)
            for gone in ("--mode", "AskUserQuestion", "## Interactive mode"):
                self.assertNotIn(gone, orq, "no session mode choice")
            self.assertLess(orq.index("When called"), orq.index("# ROLE"), "the protocol comes before the rest")
            leave = files["plugins/aidw/skills/exit/SKILL.md"].decode("utf-8")
            diff = files["plugins/aidw/skills/diff/SKILL.md"].decode("utf-8")
            for step in ("ExitWorktree", 'action: "keep"', 'name: "<demand>/<folder>"', "worktree list --json",
                         "**after**", "`exit`: the demand folder"):
                self.assertIn(step, diff)
            self.assertIn("/aidw:diff exit", orq)
            self.assertIn("workflow `survey`", orq)
            survey = files["plugins/aidw/skills/survey/SKILL.md"].decode("utf-8")
            self.assertIn("name: survey", survey)
            self.assertIn("disable-model-invocation: true", survey)
            self.assertIn("**Survey:**", survey)
            # the survey's lean orchestrator: only the explorer, the procedure inside, without development
            self.assertLess(survey.index("**Survey:**"), survey.index("# ROLE"))
            for part in ("# STEPS", "`UNDERSTAND` → `EXPLORE` → `ESTIMATE` → `FINAL_REVIEW`", "## 4. Estimate",
                         "/aidw:go <id>", "`aidw:explorer`"):
                self.assertIn(part, survey)
            for gone in ("# WORKFLOW", "## Workflows", "**Panel**", "`aidw:coder`", "EnterWorktree",
                         "*survey* `"):
                self.assertNotIn(gone, survey)
            self.assertLess(len(survey), len(orq), "smaller than the go skill, even with the procedure inside")
            # the other lean modes: their own prompt, only the roles they delegate to, no workflows
            lean = {"ask": ("`ask-<slug>`", "answer-<id>.md", ()),
                    "investigate": ("`inv-<slug>`", "investigation-<id>.md", ("`aidw:documenter`",)),
                    "card": ("`card-<slug>`", "workitem-<id>.md", ("`aidw:documenter`",)),
                    "kb-review": ("`kb-review-<YYYY-MM-DD>`", "kb-review-<id>.md", ())}
            for mode, (demand_id, artifact, roles) in lean.items():
                text = files[f"plugins/aidw/skills/{mode}/SKILL.md"].decode("utf-8")
                self.assertIn(f"name: {mode}", text)
                self.assertIn("disable-model-invocation: true", text)
                for part in (demand_id, artifact, "`UNDERSTAND` → `EXPLORE`", "`ANSWER`", "`aidw:explorer`", *roles):
                    self.assertIn(part, text, mode)
                for gone in ("# WORKFLOW", "## Workflows", "`aidw:coder`", "`aidw:reviewer`", "EnterWorktree"):
                    self.assertNotIn(gone, text, mode)
                self.assertLess(len(text), len(orq), mode)
            self.assertNotIn("`aidw:documenter`", files["plugins/aidw/skills/ask/SKILL.md"].decode("utf-8"))
            fix = files["plugins/aidw/skills/fix/SKILL.md"].decode("utf-8")
            for part in ("name: fix", "**Fix (short path):**", "*short-path*", "# WORKFLOW", "`aidw:coder`",
                         "suggest `/aidw:go <id>`"):
                self.assertIn(part, fix)
            self.assertIn("plugins/aidw/reference/survey.md", files)
            for ref in ("short-path", "testing", "pr-triage", "pr-review"):
                self.assertIn(f"plugins/aidw/reference/{ref}.md", files)
            for old in ("caminho-curto", "testes", "triagem-pr", "levantamento"):
                self.assertNotIn(f"plugins/aidw/reference/{old}.md", files, "old reference names are not generated")
            self.assertIn("--status paused", leave)
            self.assertIn("name: exit", leave)
            self.assertIn("disable-model-invocation: true", leave)
            for old in ("lev", "sair", "conhecimento", "contexto-usar", "preparar-worktree", "verificar-premissa"):
                self.assertNotIn(f"plugins/aidw/skills/{old}/SKILL.md", files, "old names are not generated")


class ContextTest(unittest.TestCase):
    """aidw.py context list / check / create / use (skill context: list, use, create)."""

    def test_context_overrides_routing_and_workflows(self) -> None:
        """contexts/<name>/routing.toml goes on top of the core; the context's workflows/ replace the same-named
        ones; the card type → workflow map shows in the orchestrator and a missing workflow in the map is an error."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            ctx_dir = root / "contexts" / "exemplo"
            (ctx_dir / "routing.toml").write_text('[rules]\nreview_approved = "TEST"\n\n[[effort.variants.reviewer]]\neffort = "low"\n'
                                                  'when = "only the context\'s"\n', encoding="utf-8")
            (ctx_dir / "workflows").mkdir()
            (ctx_dir / "workflows" / "bugfix.yaml").write_text(
                "name: bugfix\ndescription: The context's bug.\nsteps:\n  - id: implement\n    agent: coder\n",
                encoding="utf-8")
            toml = ctx_dir / "context.toml"
            toml.write_text(toml.read_text(encoding="utf-8") + '\n[workflows]\nby_type = { "Bug" = "bugfix" }\n',
                            encoding="utf-8")
            aidw = load_aidw(root)
            rep = aidw.Report(quiet=True)
            b = aidw.build(aidw.load_config(), aidw.load_catalog(), rep)
            self.assertEqual(rep.errors, [])
            self.assertEqual(b["routing"]["rules"]["review_approved"], "TEST", "the context's value replaces")
            self.assertEqual(b["routing"]["rules"]["plan_ready"], "PLAN_APPROVAL", "the rest comes from the core")
            self.assertEqual(list(b["resolved"]["reviewer"]["variants"]), ["reviewer", "reviewer-low"],
                             "the context's list replaces the core's")
            self.assertIn("coder-medium", b["resolved"]["coder"]["variants"], "the rest comes from the core")
            orq = b["orchestrator_md"]
            self.assertIn("## Workflows", orq)
            self.assertIn("The context's bug.", orq)
            self.assertIn("contexts/exemplo/workflows/bugfix.yaml", orq)
            self.assertIn("- Bug → `bugfix`", orq)
            self.assertIn("workflows/development.yaml", orq)

            toml.write_text(toml.read_text(encoding="utf-8").replace('"bugfix" }', '"does-not-exist" }'), encoding="utf-8")
            rep = aidw.Report(quiet=True)
            aidw.build(aidw.load_config(), aidw.load_catalog(), rep)
            self.assertTrue(any("does-not-exist" in e for e in rep.errors), rep.errors)

    def test_demand_keeps_the_tickets_tasks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            wt = WorktreeTest()
            code, d = wt.aidw_json(root, "demand", "set", "us-9", "--task", "front=5001", "--json")
            self.assertEqual((code, d["tasks"]), (0, {"front": "5001"}), d)
            code, d = wt.aidw_json(root, "demand", "set", "us-9", "--task", "api=#5002", "--json")
            self.assertEqual(d["tasks"], {"front": "5001", "api": "5002"}, "adds to the ones already there")
            code, err = wt.aidw_json(root, "demand", "set", "us-9", "--task", "api", "--json")
            self.assertEqual(code, 1, err)
            code, d = wt.aidw_json(root, "demand", "set", "us-9", "--loop", "bug-1234", "--json")
            self.assertEqual(d["loop"], "bug-1234")
            code, d = wt.aidw_json(root, "demand", "set", "us-9", "--loop", "-", "--json")
            self.assertNotIn("loop", d)
            code, err = wt.aidw_json(root, "demand", "set", "us-9", "--loop", "Bug 1", "--json")
            self.assertEqual(code, 1, err)

    def test_context_outside_step(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            wt = WorktreeTest()
            code, err = wt.aidw_json(root, "demand", "set", "us-9", "--step", "UX_VALIDATION", "--json")
            self.assertEqual(code, 1, "unless the context declares it, the step does not exist")
            toml = root / "contexts" / "exemplo" / "context.toml"
            toml.write_text(toml.read_text(encoding="utf-8") + (
                '\n[[workflows.external_steps]]\nstep = "UX_VALIDATION"\nname = "UX validation"\nbefore = "CODE_REVIEW"\n'
                'who = "UX"\nwhen = "the card has a UX Owner"\n'), encoding="utf-8")
            code, d = wt.aidw_json(root, "demand", "set", "us-9", "--extra-step", "UX_VALIDATION", "--json")
            self.assertEqual((code, d["extra_steps"]), (0, ["UX_VALIDATION"]), d)
            code, d = wt.aidw_json(root, "demand", "set", "us-9", "--step", "UX_VALIDATION", "--json")
            self.assertEqual((code, d["step"]), (0, "UX_VALIDATION"), d)
            code, d = wt.aidw_json(root, "demand", "set", "us-9", "--extra-step", "-UX_VALIDATION", "--json")
            self.assertNotIn("extra_steps", d)
            code, err = wt.aidw_json(root, "demand", "set", "us-9", "--extra-step", "QA_TEST", "--json")
            self.assertEqual(code, 1, "only a step the context declares")

            aidw = load_aidw(root)
            rep = aidw.Report(quiet=True)
            aidw.check_external_steps({"name": "x", "workflows": {"external_steps": [
                {"step": "REVIEW", "name": "a", "before": "CODE_REVIEW", "when": "b"},
                {"step": "UX", "name": "a", "before": "DONE", "when": "b"},
                {"step": "ux-val", "name": "a", "before": "CODE_REVIEW", "when": "b"},
                {"step": "NO_NAME", "before": "QA_TEST", "when": "b"}]}}, rep)
            self.assertEqual(len(rep.errors), 4, rep.errors)

            # [environments]: every name must be in order; the Runtime lines follow what is declared
            rep = aidw.Report(quiet=True)
            envs = {"order": ["DEV", "QA", "PROD"], "test": "DEV", "test_fallback": "HML", "explore": ["DEV", "X"]}
            aidw.check_environments({"name": "x", "environments": envs}, rep)
            self.assertEqual(len(rep.errors), 2, rep.errors)
            self.assertEqual(aidw.environment_lines({"environments": {}}), [])
            lines = aidw.environment_lines({"environments": {"order": ["DEV", "QA"], "test": "DEV"}})
            self.assertEqual(len(lines), 2, lines)
            self.assertNotIn("only for a step", lines[1], "no fallback declared, none offered")

            # the PR vote scale is gone: a context that still declares [[mods.votes]] gets a warning, not an error
            rep = aidw.Report(quiet=True)
            aidw.check_votes({"name": "x", "mods": {"votes": [{"value": "10", "label": "Approve"}]}}, rep)
            self.assertEqual((len(rep.errors), len(rep.warnings)), (0, 1))

    def test_demand_folder_excludes_the_root_claude_md(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            wt = WorktreeTest()
            code, d = wt.aidw_json(root, "demand", "set", "us-9", "--step", "UNDERSTAND", "--json")
            settings = Path(d["folder"]) / ".claude" / "settings.json"
            pattern = "**/" + root.as_posix().split(":", 1)[-1].lstrip("/") + "/CLAUDE.md"
            self.assertEqual(json.loads(settings.read_text(encoding="utf-8")), {"claudeMdExcludes": [pattern]},
                             "a chat opened in the demand folder does not load the root's CLAUDE.md with the skill")
            settings.write_text(json.dumps({"claudeMdExcludes": ["**/other/CLAUDE.md"], "model": "x"}), encoding="utf-8")
            wt.aidw_json(root, "demand", "set", "us-9", "--step", "EXPLORE", "--json")
            self.assertEqual(json.loads(settings.read_text(encoding="utf-8")),
                             {"claudeMdExcludes": ["**/other/CLAUDE.md", pattern], "model": "x"}, "what was there stays")

    def test_orchestrator_metrics_sum_per_session_and_model(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            wt = WorktreeTest()
            demand = Path(tmp) / "us-9"
            turn = ["record-orchestrator", "--demand", str(demand), "--session", "79aafeb8-0000",
                    "--input", "10", "--cache-write", "300000", "--cache-read", "0", "--output", "800",
                    "--duration-ms", "30000"]
            code, r = wt.aidw_json(root, *turn, "--model", "claude-opus-5-5")
            self.assertEqual((code, r["turns"]), (0, 1), r)
            self.assertAlmostEqual(r["cost_usd"], (10 * 4 + 300000 * 8 + 800 * 20) / 1e6,
                                   msg="cache written at 2× the input")
            code, r = wt.aidw_json(root, *turn, "--model", "claude-opus-5-5")
            self.assertEqual(r["turns"], 2, "the same session and model add up in the same row")
            code, r = wt.aidw_json(root, *turn, "--model", "claude-sonnet-5-5")
            self.assertEqual(r["turns"], 1, "another model is another row")
            text = (demand / "orchestrator-metrics.md").read_text(encoding="utf-8")
            rows = [line for line in text.splitlines() if line.startswith("| 79aafeb8 |")]
            self.assertEqual(len(rows), 2, text)
            self.assertIn("| claude-opus-5-5 | 2 | 60s | 20 | 600,000 | 0 | 1,600 |", rows[0])

            old = Path(tmp) / "us-8"  # a demand from before the rename keeps its old-named file
            old.mkdir()
            (old / "metricas-orquestrador.md").write_text(text, encoding="utf-8")
            code, r = wt.aidw_json(root, *turn[:2], str(old), *turn[3:], "--model", "claude-opus-5-5")
            self.assertEqual((code, r["turns"]), (0, 3), r)
            self.assertFalse((old / "orchestrator-metrics.md").exists())

    def test_record_does_not_repeat_what_the_mod_recorded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            wt = WorktreeTest()
            demand = Path(tmp) / "us-9"
            base = ["record", "--agent", "explorer", "--demand", str(demand), "--state", "exploration_complete"]
            code, r = wt.aidw_json(root, *base, "--label", "lev", "--tokens", "1000", "--tool-uses", "5",
                                   "--duration-ms", "60000")
            self.assertEqual((code, r["tokens_in"]), (0, 1000), r)
            f = demand / "metrics.md"
            f.write_text(f.read_text(encoding="utf-8").rstrip("\n"), encoding="utf-8")  # edited by hand, no line break
            code, r = wt.aidw_json(root, *base, "--label", "lev")
            self.assertEqual((code, r["tokens_in"], r["turns"], r["duration_s"]), (0, 1000, 5, 60), r)
            self.assertIn("1,000 tokens", r["resumo"])
            self.assertTrue(any("already recorded" in w for w in r["warnings"]), r)
            wt.aidw_json(root, *base, "--label", "other", "--tokens", "50")
            rows = [x for x in f.read_text(encoding="utf-8").splitlines() if x.startswith("| 2")]
            self.assertEqual([x.split(" | ")[4] for x in rows], ["lev", "other"], "no repeated or glued row")
            self.assertNotIn("| Level |", f.read_text(encoding="utf-8"), "a new metrics.md has no Level column")
            # an old metrics.md (with the Level column) keeps its layout, and the mod's row is still found
            old = Path(tmp) / "us-10"
            old.mkdir()
            (old / "metrics.md").write_text(
                "| Date | Agent | Level | Model | Effort | Label | State | Turns or tools | Duration | Input tokens "
                "(with cache) | Output tokens | Cost (USD) | Plan limits |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|\n",
                encoding="utf-8")
            old_base = ["record", "--agent", "explorer", "--demand", str(old), "--state", "exploration_complete"]
            wt.aidw_json(root, *old_base, "--label", "lev", "--tokens", "700", "--tool-uses", "3", "--duration-ms", "9000")
            code, r = wt.aidw_json(root, *old_base, "--label", "lev")
            self.assertEqual((code, r["tokens_in"], r["turns"]), (0, 700, 3), r)
            rows = [x for x in (old / "metrics.md").read_text(encoding="utf-8").splitlines() if x.startswith("| 2")]
            self.assertEqual([x.split(" | ")[2] for x in rows], ["—"], "the old file keeps its Level column")

    def test_context_cycle(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            wt = WorktreeTest()
            code, lst = wt.aidw_json(root, "context", "list", "--json")
            self.assertEqual((lst["active"], [c["name"] for c in lst["contexts"]]), ("exemplo", ["exemplo"]))

            code, made = wt.aidw_json(root, "context", "create", "novo", "--description", "Company — Squad", "--json")
            self.assertEqual(code, 0, made)
            novo = root / "contexts" / "novo"
            self.assertTrue((novo / ".git").exists(), "a new context has its own git repository")
            self.assertIn("[worktree]", (novo / "context.toml").read_text(encoding="utf-8"))
            self.assertIn('language = "en"', (novo / "context.toml").read_text(encoding="utf-8"))
            code, dup = wt.aidw_json(root, "context", "create", "novo", "--json")
            self.assertEqual(code, 1)
            code, chk = wt.aidw_json(root, "context", "check", "novo", "--json")
            self.assertEqual(code, 0, chk)

            code, err = wt.aidw_json(root, "context", "use", "does-not-exist", "--skip-cli", "--json")
            self.assertEqual(code, 1)
            before = (root / "aidw.config.toml").read_text(encoding="utf-8")
            code, used = wt.aidw_json(root, "context", "use", "novo", "--skip-cli", "--json")
            self.assertEqual(code, 0, used)
            after = (root / "aidw.config.toml").read_text(encoding="utf-8")
            self.assertIn('active = "novo"', after)
            self.assertEqual(before.replace('active = "exemplo"', 'active = "novo"'), after,
                             "only the active line changes; comments and the rest stay")
            code, lst = wt.aidw_json(root, "context", "list", "--json")
            self.assertEqual(lst["active"], "novo")
            wt.aidw_json(root, "demand", "set", "us-3", "--status", "active", "--json")
            code, none = wt.aidw_json(root, "context", "use", "", "--skip-cli", "--json")
            self.assertEqual(code, 0, none)
            self.assertIn('active = ""', (root / "aidw.config.toml").read_text(encoding="utf-8"))
            self.assertTrue(any("us-3" in w for w in none["warnings"]), "warns about the active demand that is paused")
            code, back = wt.aidw_json(root, "context", "use", "novo", "--skip-cli", "--json")
            self.assertEqual(code, 0, back)

            toml = novo / "context.toml"
            toml.write_text(toml.read_text(encoding="utf-8").replace(
                'state_dir = "contexts/novo/demandas"', 'state_dir = "contexts/exemplo/demandas"'), encoding="utf-8")
            code, chk = wt.aidw_json(root, "context", "check", "novo", "--json")
            self.assertEqual(code, 1)
            self.assertTrue(any("state_dir" in e for e in chk["errors"]), chk)


class KnowledgeTest(unittest.TestCase):
    """`aidw.py kb`: the context's knowledge base (notes linked by [[links]])."""

    def test_show_brief_and_collect(self) -> None:
        """Flow v3: `kb show --brief` without the list of who cites the note, and `kb collect <id>` gathering what the
        demand learned (*Knowledge base* sections, learnings, the summary's notes and the plan's decisions) for
        /aidw:done."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            full = run_aidw(root, "kb", "show", "sistema-a")
            brief = run_aidw(root, "kb", "show", "sistema-a", "--brief")
            self.assertEqual(brief.returncode, 0, brief.stderr)
            self.assertIn("## Cited by", full.stdout)
            self.assertNotIn("## Cited by", brief.stdout)
            self.assertIn("cited by 2 note(s)", brief.stdout)

            demand = root / "contexts" / "exemplo" / "demandas" / "us-9"
            demand.mkdir(parents=True)
            (demand / "exploration-route.md").write_text(
                "# Exploration\n\n## Q1 where\n- fact\n\n## Knowledge base\n- new → [[sistema-a]]: route X — `a.cs:1`\n",
                encoding="utf-8")
            (demand / "plan-us-9.md").write_text(
                "# Plan v1\n\n## Decisions made\n| 1 | Topic | Decision | user, 2026-10-23 |\n\n## Goal\nx\n",
                encoding="utf-8")
            (demand / "plan-us-9-v1.md").write_text("## Decisions made\nstale\n", encoding="utf-8")
            (demand / "review-us-9-r1.md").write_text("### R1-01 — SUGGESTION — `a.cs:2`\n", encoding="utf-8")
            (demand / "learnings-us-9.md").write_text("- Tech Lead decision → [[sistema-a]]\n", encoding="utf-8")
            (demand / "summary-us-9.md").write_text("# Summary\n\n## Knowledge\n- `sistemas/sistema-a.md` — core\n",
                                                    encoding="utf-8")
            (demand / "metrics.md").write_text("## Knowledge base\n- never collected\n", encoding="utf-8")
            out = run_aidw(root, "kb", "collect", "us-9")
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            text = (demand / "collect-us-9.md").read_text(encoding="utf-8")
            self.assertIn("## exploration-route.md", text)
            self.assertIn("route X", text)
            self.assertNotIn("## Q1", text, "only the report's Knowledge base section")
            self.assertIn("user, 2026-10-23", text)
            self.assertNotIn("stale", text, "the plan's old version does not go in")
            self.assertNotIn("review-us-9-r1.md", text, "a report without the section does not go in")
            self.assertIn("Tech Lead decision", text)
            self.assertIn("(notes cited by the summary)", text)
            self.assertNotIn("never collected", text, "the metrics are not collected")
            self.assertNotEqual(run_aidw(root, "kb", "collect", "does-not-exist").returncode, 0)

    def test_collect_reads_old_artifact_names(self) -> None:
        """A demand from before the rename (Portuguese file names and headings) is still collected."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            demand = root / "contexts" / "exemplo" / "demandas" / "us-9"
            demand.mkdir(parents=True)
            (demand / "exploracao-rota.md").write_text(
                "# Exploração\n\n## Q1 onde\n- fato\n\n## Base de conhecimento\n- novo → [[sistema-a]]: rota X — `a.cs:1`\n",
                encoding="utf-8")
            (demand / "plano-us-9.md").write_text(
                "# Plano v1\n\n## Decisões tomadas\n| 1 | Tema | Decisão | usuário, 2026-10-23 |\n\n## Objetivo\nx\n",
                encoding="utf-8")
            (demand / "plano-us-9-v1.md").write_text("## Decisões tomadas\nvelha\n", encoding="utf-8")
            (demand / "aprendizados-us-9.md").write_text("- decisão do Tech Lead → [[sistema-a]]\n", encoding="utf-8")
            (demand / "resumo-us-9.md").write_text("# Resumo\n\n## Conhecimento\n- `sistemas/sistema-a.md` — núcleo\n",
                                                   encoding="utf-8")
            (demand / "metricas.md").write_text("## Base de conhecimento\n- nunca colhido\n", encoding="utf-8")
            out = run_aidw(root, "kb", "collect", "us-9")
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            text = (demand / "collect-us-9.md").read_text(encoding="utf-8")
            for expected in ("## exploracao-rota.md", "rota X", "usuário, 2026-10-23", "decisão do Tech Lead",
                             "(notes cited by the summary)", "núcleo"):
                self.assertIn(expected, text)
            for absent in ("## Q1", "velha", "nunca colhido"):
                self.assertNotIn(absent, text)
            self.assertNotIn("## Effort", text, "no survey: no calibration section")

    def test_collect_effort_of_a_surveyed_demand(self) -> None:
        """A surveyed demand that reached the PR: the collect measures it from what the flow recorded, without the
        survey's own exploration (also the one of its open questions) and apart from what came after the PR."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            demand = root / "contexts" / "exemplo" / "demandas" / "dt-7"
            demand.mkdir(parents=True)
            (demand / "survey-dt-7.md").write_text(
                "## Estimate\n| Block | With AiDW (h) |\n|---|---|\n| x | 1–2 |\n| **Total dev** | **6–9 h · ~2 days to the PR** |\n\n"
                "- **Story points:** 8 — two systems\n", encoding="utf-8")
            steps = [("UNDERSTAND", "2026-11-04T09:00"), ("EXPLORE", "2026-11-04T09:10"), ("ESTIMATE", "2026-11-04T10:00"),
                     ("FINAL_REVIEW", "2026-11-04T10:30"), ("EXPLORE", "2026-11-05T09:00"),
                     ("FINAL_REVIEW", "2026-11-05T09:30"), ("DONE", "2026-11-09T08:00"), ("EXPLORE", "2026-11-09T08:05"),
                     ("PLAN", "2026-11-09T09:00"), ("IMPLEMENT", "2026-11-09T10:00"), ("REVIEW", "2026-11-09T11:00"),
                     ("CODER_FIX", "2026-11-10T09:00"), ("REVIEW", "2026-11-10T10:00"), ("PR", "2026-11-10T11:00"),
                     ("CODE_REVIEW", "2026-11-10T11:05"), ("CODER_FIX", "2026-11-12T09:00"),
                     ("CODE_REVIEW", "2026-11-12T10:00")]
            (demand / "demand.json").write_text(json.dumps(
                {"id": "dt-7", "history": [{"step": s, "at": a} for s, a in steps]}), encoding="utf-8")
            (demand / "metrics.md").write_text(
                "# Metrics\n\n| Date | Agent | Model | Effort | Label | State | Tool uses | Duration |\n|---|---|---|---|---|---|---|---|\n"
                "| 2026-11-04 | busca | sonnet | high | survey | exploration_complete | 40 | 3600s |\n"
                "| 2026-11-09 | busca | haiku | medium | levantamento-duvidas | exploration_complete | 9 | 600s |\n"
                "| 2026-11-09 | dev | sonnet | high | E1 | implementation_complete | 50 | 5400s |\n"
                "| 2026-11-10 | revisao | sonnet | high | E1 | review_approved | 20 | 1800s |\n"
                "| 2026-11-12 | dev | sonnet | medium | cr | implementation_complete | 10 | 720s |\n", encoding="utf-8")
            (demand / "orchestrator-metrics.md").write_text(
                "# Orchestrator metrics\n\n| Session | Duration |\n|---|---|\n| abc | 999s |\n\n## By step\n\n"
                "| Step | Turns | Duration |\n|---|---|---|\n| ESTIMATE | 3 | 900s |\n| PLAN | 2 | 600s |\n"
                "| REVIEW | 4 | 1200s |\n| CODE_REVIEW | 1 | 300s |\n", encoding="utf-8")
            out = run_aidw(root, "kb", "collect", "dt-7", "--json")
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            e = json.loads(out.stdout)["effort"]
            self.assertEqual((e["estimate_sp"], e["estimate_total"]), (8, "6–9 h · ~2 days to the PR"))
            self.assertEqual((e["dev_start"], e["pr_at"], e["days_to_pr"]), ("2026-11-09T08:05", "2026-11-10T11:00", 2))
            self.assertEqual((e["agents_hours_to_pr"], e["agents_hours_after_pr"]), (2.0, 0.2))
            self.assertEqual((e["orchestrator_hours_dev"], e["orchestrator_measured"]), (0.5, True))
            self.assertEqual((e["review_rounds"], e["fix_rounds"], e["returns_after_pr"]), (2, 1, 1))
            text = (demand / "collect-dt-7.md").read_text(encoding="utf-8")
            self.assertIn("## Effort (calibration of the survey)", text)
            self.assertIn("2 working day(s)", text)

    def test_knowledge_base(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            wt = WorktreeTest()
            kb = root / "contexts" / "exemplo" / "conhecimento"
            code, chk = wt.aidw_json(root, "kb", "check", "--json")
            self.assertEqual((code, chk["errors"], chk["notes"]), (0, [], 4), chk)

            code, a = wt.aidw_json(root, "kb", "show", "sistema-a", "--json")
            self.assertEqual(code, 0, a)
            self.assertEqual([l["key"] for l in a["links"]], ["sistema-b", "contrato-ab", "solicitacao"])
            self.assertEqual([b["key"] for b in a["backlinks"]], ["contrato-ab", "solicitacao"],
                             "[[sistemas/sistema-a.md|A]] also counts as a link to sistema-a")
            code, b = wt.aidw_json(root, "kb", "show", "sistema-b", "--json")
            self.assertEqual(b["meta"]["sistemas"], ["sistema-b"], "a block list, as Obsidian writes it")
            code, alias = wt.aidw_json(root, "kb", "show", "Protocolo", "--json")
            self.assertEqual(alias["key"], "solicitacao", "found by the alias, case-insensitive")
            code, miss = wt.aidw_json(root, "kb", "show", "does-not-exist", "--json")
            self.assertEqual(code, 1)

            code, found = wt.aidw_json(root, "kb", "search", "solicitacao", "--json")
            self.assertEqual(found["hits"][0]["key"], "solicitacao", "without the accent finds 'Solicitação'; the title weighs more")
            self.assertEqual({h["key"] for h in found["hits"]}, {"solicitacao", "sistema-a"})

            code, idx = wt.aidw_json(root, "kb", "index", "--json")
            index = (kb / "index.md").read_text(encoding="utf-8")
            self.assertIn("## Systems (2)", index)
            self.assertIn("| [[solicitacao\\|Solicitação]] | pedido, request |", index)
            code, chk = wt.aidw_json(root, "kb", "check", "--json")
            self.assertEqual(chk["errors"], [], "the generated index does not break the check")

            self.assertEqual(run_aidw(root, "apply").returncode, 0)
            gen = (root / ".claude" / "agents" / "coder.md").read_text(encoding="utf-8")
            self.assertIn(f"- Knowledge: `{(kb / 'sistemas' / 'sistema-a.md').as_posix()}`", gen)
            self.assertIn("kb show <system|note>", gen)
            self.assertIn("a fact, not a rule", gen, "the note describes; the team guide and the policies decide")

            long_note = kb / "integracoes" / "contrato-ab.md"
            long_note.write_text(long_note.read_text(encoding="utf-8").replace("atualizado: 2026-10-07", "atualizado: 2020-01-01")
                                 + "".join(f"- line {i}\n" for i in range(160)), encoding="utf-8")
            code, chk = wt.aidw_json(root, "kb", "check", "--json")
            self.assertEqual(chk["errors"], [], "size and age are warnings, not errors")
            warnings = "\n".join(chk["warnings"])
            self.assertIn("contrato-ab.md: 1", warnings)
            self.assertIn("split into linked notes", warnings)
            self.assertIn("last checked on 2020-01-01", warnings)
            self.assertNotIn("solicitacao.md: last checked", warnings)

            (kb / "sistemas" / "sistema-b.md").unlink()
            (kb / "integracoes" / "quebrada.md").write_text(
                "---\ntipo: integracao\nresumo: x\nsistemas: [sistema-z]\natualizado: 2026-10-07\n---\n\n"
                "See [[inexistente]]. Password=abc12345\n", encoding="utf-8")
            (kb / "conceitos" / "sistema-a.md").write_text("---\ntipo: conceito\nresumo: x\n---\n", encoding="utf-8")
            code, chk = wt.aidw_json(root, "kb", "check", "--json")
            self.assertEqual(code, 1)
            errors = "\n".join(chk["errors"])
            for expected in ("repeated name 'sistema-a'", "broken link [[sistema-b]]", "broken link [[inexistente]]",
                             "`fontes` is missing", "sistema-z", "looks like a secret"):
                self.assertIn(expected, errors)
            self.assertTrue(any("system 'sistema-b' has no note" in w for w in chk["warnings"]), chk["warnings"])
            code, ctx = wt.aidw_json(root, "context", "check", "exemplo", "--json")
            self.assertEqual(code, 1)
            self.assertTrue(any(e.startswith("knowledge base:") for e in ctx["errors"]), ctx)

            code, made = wt.aidw_json(root, "context", "create", "novo", "--description", "Novo", "--json")
            novo = root / "contexts" / "novo"
            self.assertIn('[knowledge]\ndir = "conhecimento"', (novo / "context.toml").read_text(encoding="utf-8"))
            self.assertIn("# Knowledge base — Novo", (novo / "conhecimento" / "README.md").read_text(encoding="utf-8"))
            self.assertTrue((novo / "conhecimento" / "demandas").is_dir())
            graph = json.loads((novo / ".obsidian" / "graph.json").read_text(encoding="utf-8"))
            self.assertIn("path:conhecimento/sistemas", [g["query"] for g in graph["colorGroups"]],
                          "the vault is the context folder: the colors point inside the base")

    def test_vault_in_the_context_upstream_and_harvest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "exemplo")
            wt = WorktreeTest()
            ctx_dir = root / "contexts" / "exemplo"
            kb = ctx_dir / "conhecimento"
            note = kb / "sistemas" / "sistema-b.md"
            note.write_text(note.read_text(encoding="utf-8") + "\nFollows the policy [[regra]].\n", encoding="utf-8")
            code, chk = wt.aidw_json(root, "kb", "check", "--json")
            self.assertEqual(chk["errors"], [], "[[regra]] finds policies/regra.md: the vault is the context folder")
            code, b = wt.aidw_json(root, "kb", "show", "sistema-b", "--json")
            self.assertTrue(b["links"][0]["outside"][0].endswith("policies/regra.md"), b["links"])

            (kb / "conceitos" / "guia.md").write_text(
                "---\ntipo: conceito\nresumo: x\natualizado: 2026-10-07\n---\n\n[[sistema-a]]\n", encoding="utf-8")
            wt.aidw_json(root, "kb", "index", "--json")
            code, chk = wt.aidw_json(root, "kb", "check", "--json")
            self.assertTrue(any("'guia' also exists in shared/guia.md" in w for w in chk["warnings"]), chk)
            self.assertFalse(any("index.md out of date" in w for w in chk["warnings"]))
            (kb / "conceitos" / "guia.md").unlink()
            code, chk = wt.aidw_json(root, "kb", "check", "--json")
            self.assertTrue(any("index.md out of date" in w for w in chk["warnings"]), chk)
            wt.aidw_json(root, "kb", "index", "--json")
            self.assertIn("[[conhecimento/README|README]]", (kb / "index.md").read_text(encoding="utf-8"))

            guide = tmp / "guideline"
            guide.mkdir()
            for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"],
                         ["commit", "-q", "--allow-empty", "-m", "first"]):
                subprocess.run(["git", "-C", str(guide), *args], check=True)
            first = subprocess.run(["git", "-C", str(guide), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
            toml = ctx_dir / "context.toml"
            toml.write_text(toml.read_text(encoding="utf-8") + f'\n[upstream.guia]\nrepo = "{guide.as_posix()}"\n'
                            f'synced = "{first}"\ncovers = ["shared/guia.md"]\n', encoding="utf-8")
            code, ctx = wt.aidw_json(root, "context", "check", "exemplo", "--json")
            self.assertFalse(any("upstream" in w for w in ctx["warnings"]), "up to date: no warning")
            subprocess.run(["git", "-C", str(guide), "commit", "-q", "--allow-empty", "-m", "AutoMapper forbidden"], check=True)
            code, ctx = wt.aidw_json(root, "context", "check", "exemplo", "--json")
            self.assertTrue(any("upstream guia" in w and "AutoMapper forbidden" in w for w in ctx["warnings"]), ctx)

            # a checkout with a remote: `context upstream` fetches and compares with the remote, not the checkout
            clone = tmp / "guideline-clone"
            subprocess.run(["git", "clone", "-q", str(guide), str(clone)], check=True, capture_output=True)
            head = subprocess.run(["git", "-C", str(guide), "rev-parse", "HEAD"], capture_output=True,
                                  text=True).stdout.strip()
            toml.write_text(toml.read_text(encoding="utf-8").replace(f'repo = "{guide.as_posix()}"\nsynced = "{first}"',
                            f'repo = "{clone.as_posix()}"\nsynced = "{head}"'), encoding="utf-8")
            code, up = wt.aidw_json(root, "context", "upstream", "--json")
            self.assertEqual((code, up["warnings"]), (0, []), "clone up to date")
            subprocess.run(["git", "-C", str(guide), "commit", "-q", "--allow-empty", "-m", "New rule"], check=True)
            code, up = wt.aidw_json(root, "context", "upstream", "--no-fetch", "--json")
            self.assertEqual(up["warnings"], [], "without fetch the remote ref is the old one")
            code, up = wt.aidw_json(root, "context", "upstream", "--json")
            self.assertTrue(any("after" in w and "New rule" in w for w in up["warnings"]), up)
            self.assertTrue(any("behind" in w and "pull" in w for w in up["warnings"]), up)

            wt.aidw_json(root, "demand", "set", "us-9", "--status", "done", "--json")
            demand_dir = root / "contexts" / "exemplo" / "demandas" / "us-9"
            (demand_dir / "learnings-us-9.md").write_text("- fact\n", encoding="utf-8")
            code, st = wt.aidw_json(root, "status", "--json")
            self.assertTrue(any("us-9" in a and "/aidw:done" in a for a in st["attention"]), st["attention"])
            (demand_dir / "learnings-us-9.md").unlink()
            (demand_dir / "aprendizados-us-9.md").write_text("- fato\n", encoding="utf-8")
            code, st = wt.aidw_json(root, "status", "--json")
            self.assertTrue(any("us-9" in a and "/aidw:done" in a for a in st["attention"]),
                            "the old learnings name counts too")
            (kb / "demandas").mkdir(exist_ok=True)
            (kb / "demandas" / "us-9.md").write_text("---\ntipo: demanda\nresumo: x\n---\n", encoding="utf-8")
            code, st = wt.aidw_json(root, "status", "--json")
            self.assertFalse(any("us-9" in a for a in st["attention"]), "harvested: no more warning")


class PluginMigrationTest(unittest.TestCase):
    """install replaces an old plugin (e.g. `aidw-<context>`) with `aidw`, with the CLI simulated."""

    def test_migrates_old_plugin(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "exemplo")
            home = tmp / "claude-home"
            home.mkdir()
            old_env = os.environ.get("CLAUDE_CONFIG_DIR")
            os.environ["CLAUDE_CONFIG_DIR"] = str(home)
            try:
                aidw = load_aidw(root)
            finally:
                if old_env is None:
                    os.environ.pop("CLAUDE_CONFIG_DIR")
                else:
                    os.environ["CLAUDE_CONFIG_DIR"] = old_env
            (root / ".aidw").mkdir(exist_ok=True)
            (root / ".aidw" / "install-manifest.json").write_text(json.dumps(
                {"plugin": "aidw-exemplo", "plugins": ["aidw-exemplo@aidw-local"], "marketplace": "aidw-local",
                 "files": {}, "settings": {}, "mcp_added": [], "cli": True}), encoding="utf-8")
            calls: list[list[str]] = []
            aidw.claude_cli = lambda args, rep, dry: calls.append(args) or True
            aidw.installed_plugins = lambda: {"aidw-exemplo@aidw-local": "1.0.0"}
            aidw.known_marketplaces = lambda: {"aidw-local"}
            aidw.user_mcp_servers = lambda: {}
            with contextlib.redirect_stdout(io.StringIO()):
                ok = aidw.install(aidw.load_config(), aidw.load_catalog(), dry=False, force=False, skip_cli=False)
            self.assertTrue(ok)
            self.assertIn(["plugin", "uninstall", "aidw-exemplo@aidw-local"], calls)
            self.assertIn(["plugin", "install", "aidw@aidw-local"], calls)
            self.assertIn(["plugin", "install", "aidw-mods@aidw-local"], calls, "the mods go along")
            manifest = json.loads((root / ".aidw" / "install-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual((manifest["plugins"], manifest["context"]),
                             (["aidw-mods@aidw-local", "aidw@aidw-local"], "exemplo"), "aidw comes last")


class CodexInstallTest(unittest.TestCase):
    """install/uninstall --provider codex: only agents and aidw-* skills; cleans the profile, rules and hooks of old
    installs."""

    def test_install_uninstall_codex(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "exemplo")
            home, skills = tmp / "codex-home", tmp / "agents-skills"
            home.mkdir()
            user_hook = {"hooks": [{"type": "command", "command": "echo my-hook"}]}
            guard = {"matcher": "apply_patch|Bash|mcp__.*",
                     "hooks": [{"type": "command", "command": f'python "{root.as_posix()}/aidw_guard.py"'}]}
            # leftovers of an old install: profile, rules and the AiDW group in hooks.json (with the old mark)
            (home / "hooks.json").write_text(json.dumps({"hooks": {"Stop": [user_hook], "PreToolUse": [guard]}}),
                                             encoding="utf-8")
            (home / "aidw.config.toml").write_text("# Gerado por aidw.py install — perfil antigo\n",
                                                   encoding="utf-8")

            proc = run_aidw(root, "install", "--provider", "codex")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue((home / "agents" / "aidw-coder.toml").is_file())
            orq = (skills / "aidw-go" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("name: aidw-go", orq)
            self.assertIn("$aidw-exit", orq)
            self.assertNotIn("`EnterWorktree` with the demand id", orq, "Codex has no EnterWorktree")
            self.assertNotIn("AskUserQuestion", orq)
            self.assertNotIn("--profile aidw", orq, "on Codex AiDW installs no profile")
            self.assertFalse((skills / "aidw-diff").exists(), "Codex has no EnterWorktree: no diff skill")
            self.assertNotIn("## Interactive mode", orq)
            self.assertIn("allow_implicit_invocation: false", (skills / "aidw-go" / "agents" / "openai.yaml").read_text())
            survey = (skills / "aidw-survey" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("name: aidw-survey", survey)
            self.assertIn("`$aidw-go <id>`", survey)
            self.assertNotIn("# WORKFLOW", survey)
            self.assertNotIn("disable-model-invocation", survey)
            self.assertIn("allow_implicit_invocation: false",
                          (skills / "aidw-survey" / "agents" / "openai.yaml").read_text())
            self.assertIn("name: aidw-exit", (skills / "aidw-exit" / "SKILL.md").read_text(encoding="utf-8"))
            to_spec = (skills / "aidw-to-spec" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("name: aidw-to-spec", to_spec)
            self.assertNotIn("user-invocable", to_spec, "a Claude key; Codex does not hide skills")
            done = (skills / "aidw-done" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("name: aidw-done", done)
            self.assertNotIn("disable-model-invocation", done, "a Claude key; on Codex openai.yaml applies")
            self.assertIn("allow_implicit_invocation: false", (skills / "aidw-done" / "agents" / "openai.yaml").read_text())
            self.assertFalse((skills / "aidw-to-spec" / "agents" / "openai.yaml").exists())

            # only agents and skills: no rules, no profile, and hooks.json keeps only what is the user's
            self.assertFalse((home / "rules" / "aidw.rules").exists(), "the Codex install writes no rules")
            self.assertFalse((home / "aidw.config.toml").exists(), "the old AiDW profile goes (old Portuguese mark)")
            self.assertEqual(json.loads((home / "hooks.json").read_text(encoding="utf-8")),
                             {"hooks": {"Stop": [user_hook]}}, "only the AiDW group goes; the user's hook stays")
            manifest_path = root / ".aidw" / "install-manifest.json"
            written = json.loads(manifest_path.read_text(encoding="utf-8"))["codex"]["files"]
            self.assertTrue(all(Path(k).is_relative_to(home / "agents") or Path(k).is_relative_to(skills) for k in written),
                            "the Codex manifest only has agents and skills")
            self.assertIn("multi_agent_v2", proc.stdout, "warns that spawn_agent needs multi_agent_v2")

            again = run_aidw(root, "install", "--provider", "codex")
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
            self.assertIn("0 file(s) changed", again.stdout, "idempotent")

            # renamed skill (aidw-lev → aidw-survey): the manifest's old file goes, and the folder with it
            old_skill = skills / "aidw-lev"
            (old_skill / "agents").mkdir(parents=True)
            old_files = {old_skill / "SKILL.md": b"---\nname: aidw-lev\n---\n",
                         old_skill / "agents" / "openai.yaml": b"policy:\n  allow_implicit_invocation: false\n"}
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            for f, content in old_files.items():
                f.write_bytes(content)
                data["codex"]["files"][str(f)] = hashlib.sha256(content).hexdigest()
            manifest_path.write_text(json.dumps(data), encoding="utf-8")
            renamed = run_aidw(root, "install", "--provider", "codex")
            self.assertEqual(renamed.returncode, 0, renamed.stdout + renamed.stderr)
            self.assertFalse(old_skill.exists(), "the old skill's folder does not stay empty")

            (home / "config.toml").write_text("[features]\nmulti_agent_v2 = true\n", encoding="utf-8")
            quiet = run_aidw(root, "install", "--provider", "codex")
            self.assertNotIn("turn on `multi_agent_v2`", quiet.stdout, "with the feature on, no warning")

            both = run_aidw(root, "install", "--skip-cli")  # no --provider: an installed Codex is updated too
            self.assertEqual(both.returncode, 0, both.stdout + both.stderr)
            self.assertIn("Global install in Codex", both.stdout)
            self.assertIn("codex", json.loads(manifest_path.read_text(encoding="utf-8")),
                          "the Claude install does not erase the Codex record")

            gone = run_aidw(root, "uninstall", "--provider", "codex")
            self.assertEqual(gone.returncode, 0, gone.stdout + gone.stderr)
            self.assertEqual(json.loads((home / "hooks.json").read_text(encoding="utf-8")), {"hooks": {"Stop": [user_hook]}})
            self.assertFalse((home / "agents" / "aidw-coder.toml").exists())
            self.assertFalse((skills / "aidw-go").exists())
            code = run_aidw(root, "open", "--provider", "codex", "--path", str(tmp), "--print")
            self.assertIn("--enable multi_agent_v2", code.stdout)
            self.assertNotIn("--profile", code.stdout)


class SetupDoctorTest(unittest.TestCase):
    """Setup creates the missing folders; doctor ends with the verdict and the right exit code."""

    def test_setup_creates_folders(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "")
            shutil.rmtree(root / "contexts", ignore_errors=True)
            proc = run_aidw(root, "setup", "--skip-tools")
            for path in (root / "contexts", root / "state", tmp / "wt"):
                self.assertTrue(path.is_dir(), f"setup should create {path}\n{proc.stdout}{proc.stderr}")
            self.assertIn("== Result ==", proc.stdout, proc.stderr)
            self.assertIn("up to date with the sources", proc.stdout, "doctor right after apply must say it is up to date")

    def test_doctor_not_ready_with_missing_context(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "inexistente", copy_context=False)
            proc = run_aidw(root, "doctor")
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("NOT READY", proc.stdout)
            self.assertIn("context 'inexistente' not found", proc.stdout)


if __name__ == "__main__":
    if "--update" in sys.argv:
        sys.argv.remove("--update")
        os.environ["AIDW_UPDATE_GOLDEN"] = "1"
        UPDATE = True
    unittest.main(verbosity=2)
