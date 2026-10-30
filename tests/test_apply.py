"""Testes de referência do `aidw.py apply` (F0 do plano v3).

Cada cenário copia as fontes do AiDW para uma pasta temporária, grava um aidw.config.toml,
roda `apply` e compara os arquivos gerados com tests/golden/<cenário>/. A referência só muda
de propósito:

    python -m unittest discover -s tests -v          # roda
    python tests/test_apply.py --update              # regrava as referências (revise o diff no git)

As referências são geradas no Windows (caminhos, junctions e `cmd /c` do npx dependem do SO);
em outro SO os testes de referência são pulados.
"""
from __future__ import annotations

import contextlib
import difflib
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
from pathlib import Path

# ignore_cleanup_errors: o doctor roda `claude mcp list`, que pode deixar servidores MCP segurando a
# pasta temporária no Windows; a pasta é descartável.
REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"
GOLDEN = TESTS / "golden"
FIXTURE_CONTEXT = TESTS / "fixtures" / "contexts" / "exemplo"
SOURCES = ["aidw.py", "aidw_guard.py", "config", "agents", "skills", "orchestrator", "workflows", "mods"]
# Tudo o que o apply gera, relativo à raiz.
GENERATED = ["CLAUDE.md", "AGENTS.md", ".mcp.json", ".aidw", ".claude", ".codex", ".agents"]
UPDATE = os.environ.get("AIDW_UPDATE_GOLDEN") == "1"

# nome: (provedor, delegação, contexto)
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
    cfg["worktree"]["root"] = (tmp / "wt").as_posix()  # nunca a raiz real da máquina
    (root / "aidw.config.toml").write_text(aidw.render_config(cfg), encoding="utf-8", newline="\n")
    return root


def run_aidw(root: Path, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "CODEX_HOME": str(root.parent / "codex-home"), "PYTHONIOENCODING": "utf-8",
           "CLAUDE_CONFIG_DIR": str(root.parent / "claude-home"),  # nunca o ~/.claude real
           "AIDW_CODEX_SKILLS_DIR": str(root.parent / "agents-skills"), **(env_extra or {})}  # nem o ~/.agents
    return subprocess.run([sys.executable, str(root / "aidw.py"), *args], cwd=root, env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)


def normalize(text: str, root: Path) -> str:
    """Troca o caminho da pasta temporária por <ROOT> (e a pasta acima dela, onde fica a raiz dos worktrees do
    teste, por <TMP>) em todas as grafias que o apply usa."""
    for path, mark in ((root.resolve(), "<ROOT>"), (root.resolve().parent, "<TMP>")):
        win = str(path)
        for form in (json.dumps(win)[1:-1], win, win.replace("\\", "/"), json.dumps(win.lower())[1:-1],
                     win.lower(), win.lower().replace("\\", "/")):
            text = text.replace(form, mark)
    return text


def is_link(p: Path) -> bool:
    return p.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(p))


def snapshot(root: Path) -> dict[str, str]:
    """{caminho relativo: conteúdo normalizado}. Links viram `-> <alvo relativo>`."""
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
        out.append(f"- faltou: {key}")
    for key in sorted(set(actual) - set(expected)):
        out.append(f"+ novo:   {key}")
    for key in sorted(set(expected) & set(actual)):
        if expected[key] != actual[key]:
            out.append(f"~ mudou:  {key}")
            out += list(difflib.unified_diff(expected[key].splitlines(), actual[key].splitlines(),
                                             "referência", "gerado", lineterm="", n=1))[:limit]
    return "\n".join(out)


@unittest.skipUnless(os.name == "nt", "referências geradas no Windows")
class ApplyGoldenTest(unittest.TestCase):
    maxDiff = None

    def check_scenario(self, name: str) -> None:
        provider, mode, context = SCENARIOS[name]
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), provider, mode, context)

            dry = run_aidw(root, "apply", "--dry-run")
            self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)
            self.assertEqual(snapshot(root), {}, "dry-run não pode gravar nada")

            first = run_aidw(root, "apply")
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            actual = snapshot(root)
            state = "contexts/exemplo/demandas" if context else "state"
            self.assertTrue((root / state).is_dir(), f"apply deveria criar {state}/")

            second = run_aidw(root, "apply")
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(snapshot(root), actual, "apply não é idempotente")
            for word in ("criado", "atualizado", "removido", "linkado"):
                self.assertNotIn(f"[ok]    {word}", second.stdout, "o 2º apply não deveria alterar nada")

        if UPDATE:
            write_golden(name, actual)
            return
        expected = read_golden(name)
        self.assertTrue(expected, f"sem referência para {name}: rode `python tests/test_apply.py --update`")
        if expected != actual:
            self.fail(f"saída do apply mudou em {name}:\n{diff_report(expected, actual)}\n\n"
                      "Se a mudança é intencional: python tests/test_apply.py --update")

    def test_claude_native_contexto(self) -> None:
        self.check_scenario("claude-native-contexto")

    def test_claude_headless_sem_contexto(self) -> None:
        self.check_scenario("claude-headless-sem-contexto")

    def test_codex_native_contexto(self) -> None:
        self.check_scenario("codex-native-contexto")


class OrchestratorReferenceTest(unittest.TestCase):
    """Referências e policies `orchestrator_when` ficam fora do prompt do orquestrador, só listadas;
    os agentes continuam com a policy inteira; o frontmatter nunca vaza."""

    def test_referencias_sob_demanda(self) -> None:
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
            self.assertIn("orquestrador", refs["etapa"]["content"], "placeholder {{agent:}} renderizado")
            for g in b["agents"].values():
                self.assertIn("TEXTO-POLICY-SOB-DEMANDA", g["prompt"])
            for text in (orch, *[g["prompt"] for g in b["agents"].values()], *[r["content"] for r in refs.values()]):
                self.assertNotIn("orchestrator_when", text)
    def test_nome_repetido_e_erro(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            (root / "orchestrator" / "reference" / "etapa.md").write_text(
                "---\nwhen: x\n---\n\nGenérica.\n", encoding="utf-8")
            aidw = load_aidw(root)
            rep = aidw.Report(quiet=True)
            self.assertIsNone(aidw.build(aidw.load_config(), aidw.load_catalog(), rep))
            self.assertTrue(any("nome repetido 'etapa'" in e for e in rep.errors), rep.errors)

    def test_agentes_e_variantes(self) -> None:
        """Fluxo v3 (Felipe, 2026-10-23): sem níveis; cada agente no seu padrão e só as exceções do routing.toml
        (descer na re-revisão, subir quando o resultado não fez sentido, o explorador do levantamento); nada acima de
        high; os agentes api, bugs e segurança saíram; no Codex, o equivalente de cada modelo pelo tier."""
        esperado = {  # papel: {variante: modelo/effort}
            "planner": {"planejador": "sonnet/high", "planejador-medium": "sonnet/medium"},
            "explorer": {"explorador": "haiku/", "explorador-sonnet-medium": "sonnet/medium",
                         "explorador-sonnet-high": "sonnet/high"},
            "coder": {"codificador": "sonnet/high", "codificador-medium": "sonnet/medium"},
            "reviewer": {"revisor": "sonnet/high", "revisor-medium": "sonnet/medium", "revisor-low": "sonnet/low"},
            "qa": {"qa": "sonnet/medium", "qa-high": "sonnet/high"},
            "documenter": {"documentador": "haiku/"},
        }
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            aidw = load_aidw(root)
            rep = aidw.Report(quiet=True)
            b = aidw.build(aidw.load_config(), aidw.load_catalog(), rep)
            self.assertEqual(rep.errors, [])
            self.assertEqual(set(b["resolved"]) - {"orchestrator"}, set(esperado), "api, bugs e segurança saíram")
            for role, variants in esperado.items():
                got = {n: f"{v['model']['key']}/{v['effort']}" for n, v in b["resolved"][role]["variants"].items()}
                self.assertEqual(got, variants, role)
                for n, v in b["resolved"][role]["variants"].items():
                    if n != b["resolved"][role]["name"]:
                        self.assertTrue(v["when"], f"{n}: a exceção diz quando vale")
            efforts = {v["effort"] for a in b["resolved"].values() for v in a.get("variants", {}).values()}
            self.assertFalse(efforts & {"xhigh", "max"}, "nada acima de high")
            orq = b["orchestrator_md"]
            self.assertIn("## Agents and effort", orq)
            self.assertIn("`revisor-medium` — re-revisão só das correções", orq)
            self.assertNotIn("Effort per task", orq)
            self.assertNotIn("Nível:", orq)
            cat = aidw.load_catalog()
            tiers = {t: aidw.tier_model(cat, "codex", t) for t in ("top", "mid", "fast")}
            self.assertEqual(len(set(tiers.values())), 3, f"três degraus no Codex: {tiers}")

    def test_config_com_agentes_que_sairam(self) -> None:
        """Uma config de antes do fluxo v3 com [agents.api-db] e [agents.bug-hunter]: aviso, não erro, e eles não são
        gerados."""
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

    def test_settings_so_perde_o_que_o_aidw_gravou(self) -> None:
        """O modelo do orquestrador é o do chat: o apply tira `model`/`effortLevel` só quando são o valor que ele
        mesmo gravou antes; a escolha do usuário e as outras chaves ficam."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            aidw = load_aidw(root)
            managed = {"allow": ["Read"], "ask": [], "deny": [], "additionalDirectories": [],
                       "enabledMcpjsonServers": [], "env": {}}
            previous = {"model": "opus", "effortLevel": "high"}
            for model, fica in (("opus", False), ("sonnet", True)):
                aidw.CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
                aidw.CLAUDE_SETTINGS.write_text(json.dumps({"model": model, "effortLevel": "high",
                                                            "env": {"MINHA": "1"}}), encoding="utf-8")
                aidw.sync_claude_settings(managed, previous, False, aidw.Report(quiet=True))
                data = json.loads(aidw.CLAUDE_SETTINGS.read_text(encoding="utf-8"))
                self.assertEqual("model" in data, fica, model)
                self.assertNotIn("effortLevel", data)
                self.assertEqual(data["env"], {"MINHA": "1"})
                self.assertEqual(data["permissions"]["allow"], ["Read"])
            data["model"] = "opus"  # depois disso o AiDW não grava mais nada: um `opus` escolhido fica
            aidw.CLAUDE_SETTINGS.write_text(json.dumps(data), encoding="utf-8")
            aidw.sync_claude_settings(managed, {**managed}, False, aidw.Report(quiet=True))
            self.assertEqual(json.loads(aidw.CLAUDE_SETTINGS.read_text(encoding="utf-8"))["model"], "opus")

    def test_config_antiga_ganha_os_agentes_novos(self) -> None:
        """Uma config com [agents.*] de antes do planejador e do explorador: os dois entram com o padrão e o
        orquestrador delega a exploração ao explorador."""
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
            self.assertIn("the `explorador` agent", b["orchestrator_md"])
            self.assertIn("`codificador-medium`", b["orchestrator_md"], "a exceção da correção pequena")
            cat = aidw.load_catalog()
            self.assertEqual(aidw.equivalent_model(cat, "opus", "codex"), aidw.tier_model(cat, "codex", "top"))
            self.assertEqual(aidw.equivalent_model(cat, "haiku", "codex"), aidw.tier_model(cat, "codex", "fast"))
            self.assertEqual(aidw.equivalent_model(cat, "sonnet", "claude"), "sonnet")


class InstallTest(unittest.TestCase):
    """install/uninstall no Claude (sem o CLI): plugin gerado, merge das settings do usuário, idempotência,
    conflito com arquivo alterado à mão e remoção só do que o AiDW acrescentou."""

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
            self.assertIn(f"{base}/agents/codificador.md", files)
            self.assertIn(f"{base}/skills/skill-exemplo/SKILL.md", files)
            orq = files[f"{base}/skills/go/SKILL.md"].decode("utf-8")
            self.assertIn("disable-model-invocation: true", orq)
            self.assertIn("`aidw:codificador", orq, "tabela de effort com o nome do plugin")
            self.assertIn(f'python "{root.as_posix()}/aidw.py" record', orq, "aidw.py por caminho absoluto")
            self.assertIn(f"{(root / '.aidw' / 'marketplace' / base / 'reference').as_posix()}/etapa.md", orq)
            self.assertIn("[AiDW]", files[f"{base}/agents/codificador.md"].decode("utf-8"))
            self.assertIn("[AiDW]", files[f"{base}/skills/skill-exemplo/SKILL.md"].decode("utf-8"))
            done = files[f"{base}/skills/done/SKILL.md"].decode("utf-8")
            self.assertIn("disable-model-invocation: true", done, "/aidw:done só quando o usuário chamar")
            self.assertIn(f'python "{root.as_posix()}/aidw.py" context check', done)
            self.assertNotIn("aidw: admin", done)
            data = json.loads(settings.read_text(encoding="utf-8"))
            self.assertEqual(data["theme"], "dark")
            self.assertIn("Bash(rm -rf *)", data["permissions"]["deny"])
            self.assertIn("Bash(git commit *)", data["permissions"]["ask"])
            for sub in ("record *", "demand *", "worktree *", "project *", "context *"):
                self.assertIn(f'PowerShell(python "{root.as_posix()}/aidw.py" {sub})', data["permissions"]["allow"])
            self.assertEqual(data["env"]["MCP_TIMEOUT"], "123", "valor do usuário vence")

            before = (self.marketplace(root), settings.read_text(encoding="utf-8"))
            again = run_aidw(root, "install", "--skip-cli")
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
            self.assertEqual((self.marketplace(root), settings.read_text(encoding="utf-8")), before,
                             "install não é idempotente")

            edited = root / ".aidw" / "marketplace" / base / "agents" / "codificador.md"
            edited.write_text("editado à mão\n", encoding="utf-8")
            conflict = run_aidw(root, "install", "--skip-cli")
            self.assertEqual(conflict.returncode, 1)
            self.assertIn("alterado fora do AiDW", conflict.stdout)
            self.assertEqual(run_aidw(root, "install", "--skip-cli", "--force").returncode, 0)

            gone = run_aidw(root, "uninstall", "--skip-cli")
            self.assertEqual(gone.returncode, 0, gone.stdout + gone.stderr)
            self.assertEqual(json.loads(settings.read_text(encoding="utf-8")), self.USER_SETTINGS,
                             "uninstall deve devolver as settings do usuário como estavam")
            self.assertFalse((root / ".aidw" / "marketplace").exists())
            self.assertFalse((root / ".aidw" / "install-manifest.json").exists())


    def sandbox_with_settings(self, tmp: str, mode: str = "native") -> tuple[Path, Path]:
        root = make_sandbox(Path(tmp).resolve(), "claude", mode, "exemplo")
        settings = root.parent / "claude-home" / "settings.json"
        settings.parent.mkdir()
        settings.write_text(json.dumps(self.USER_SETTINGS, indent=2) + "\n", encoding="utf-8")
        return root, settings

    def test_falha_do_cli_nao_perde_o_dono_das_regras(self) -> None:
        """R1-01: o CLI falha depois das settings gravadas; o manifest já registra o que é do AiDW."""
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

    def test_headless_recusado(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root, _ = self.sandbox_with_settings(tmp, mode="headless")
            proc = run_aidw(root, "install", "--skip-cli")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("subagentes nativos", proc.stdout)

    def test_uninstall_sem_manifest_avisa(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root, _ = self.sandbox_with_settings(tmp)
            self.assertEqual(run_aidw(root, "install", "--skip-cli").returncode, 0)
            (root / ".aidw" / "install-manifest.json").unlink()
            proc = run_aidw(root, "uninstall", "--skip-cli")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("manifest ausente", proc.stdout)


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), "-c", "user.name=teste", "-c", "user.email=teste@example.invalid",
                           *args], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


class WorktreeTest(unittest.TestCase):
    """worktree create/list/inspect/remove/cleanup, project detect, hook WorktreeCreate e o guard."""

    def make_repo(self, tmp: Path) -> Path:
        repo = tmp / "repos" / "Aplicação"  # acento no caminho: o hook tem de ler o stdin em UTF-8
        repo.mkdir(parents=True)
        git(repo, "init", "-q", "-b", "main")
        (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        (repo / "app.txt").write_text("v1\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "inicial")
        (repo / "node_modules" / "lib").mkdir(parents=True)
        (repo / "node_modules" / "lib" / "index.js").write_text("// dependência\n", encoding="utf-8")
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
        # como o Claude Code: JSON em UTF-8 sem escapar os acentos
        proc = subprocess.run([sys.executable, str(root / "aidw_guard.py")],
                              input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                              capture_output=True, timeout=30)
        proc.stdout = proc.stdout.decode("utf-8")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_ciclo_do_worktree(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "exemplo")
            repo = self.make_repo(tmp)

            code, wt = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-1",
                                      "--slug", "Teste de slug", "--json")
            self.assertEqual(code, 0, wt)
            path = Path(wt["path"])
            self.assertEqual(path, tmp / "wt" / "us-1" / "Aplicação")
            self.assertEqual(wt["branch"], "feature/1-teste-de-slug")
            self.assertEqual(wt["base"], "main")
            self.assertEqual(wt["links"], ["node_modules"])
            self.assertTrue((path / "node_modules" / "lib" / "index.js").is_file())
            demand = json.loads((root / "contexts" / "exemplo" / "demandas" / "us-1" / "demand.json").read_text(encoding="utf-8"))
            self.assertEqual(demand["repos"][0]["branch"], "feature/1-teste-de-slug")

            code, again = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-1", "--json")
            self.assertEqual((code, again["created"], again["path"]), (0, False, wt["path"]), "create não é idempotente")

            code, det = self.aidw_json(root, "project", "detect", "--path", str(path), "--json")
            self.assertEqual((det["demand"], det["is_worktree"], det["name"]), ("us-1", True, "Aplicação"))

            code, hook = self.aidw_json(root, "worktree", "hook-create",
                                        stdin=json.dumps({"name": "us-1", "cwd": str(tmp)}))
            self.assertEqual((code, hook.strip() if isinstance(hook, str) else hook), (0, str(path)))

            coder = {"hook_event_name": "PreToolUse", "agent_type": "aidw:codificador-low", "tool_name": "Write",
                     "cwd": str(repo)}
            self.assertIn('"deny"', self.guard(root, {**coder, "tool_input": {"file_path": str(repo / "app.txt")}}))
            self.assertEqual(self.guard(root, {**coder, "tool_input": {"file_path": str(path / "app.txt")}}), "")
            nested = repo / "contexts" / "ctx"
            (nested / ".git").mkdir(parents=True)
            self.assertEqual(self.guard(root, {**coder, "tool_input": {"file_path": str(nested / "demandas" / "x.md")}}), "",
                             "outro repositório git aninhado no repo não é o working copy dele")
            self.assertIn('"deny"', self.guard(root, {**coder, "tool_input": {"file_path": str(repo / "contexts" / "x.md")}}))
            codex = {"hook_event_name": "PreToolUse", "agent_type": "aidw-codificador", "tool_name": "apply_patch",
                     "cwd": str(repo)}
            patch = lambda f: "*** Begin Patch\n*** Update File: " + f + "\n@@\n-v1\n+v2\n*** End Patch"  # noqa: E731
            self.assertIn('"deny"', self.guard(root, {**codex, "tool_input": {"command": patch("app.txt")}}),
                          "caminho relativo do patch, resolvido pelo cwd (working copy principal)")
            self.assertEqual(self.guard(root, {**codex, "tool_input": {"command": patch(str(path / "app.txt"))}}), "")
            self.assertEqual(self.guard(root, {"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": str(repo),
                                               "tool_input": {"file_path": str(repo / "app.txt")}}), "",
                             "a conversa principal não tem regra")
            self.assertEqual(self.guard(root, {"hook_event_name": "PreToolUse", "agent_type": "Explore", "tool_name": "Write",
                                               "tool_input": {"file_path": str(repo / "app.txt")}}), "")

            commit = {"hook_event_name": "PreToolUse", "tool_name": "PowerShell", "cwd": str(tmp),
                      "tool_input": {"command": f'git -C "{path}" add -A && git -C "{path}" commit -m x'}}
            (path / "Mock.cs").write_text("// AIDW-TESTE A1\n", encoding="utf-8")
            self.assertIn("AIDW-TESTE", self.guard(root, commit), "commit com ajuste de teste no worktree")
            self.assertEqual(self.guard(root, {**commit, "tool_input": {"command": f'git -C "{path}" status'}}), "")
            (path / "Mock.cs").unlink()
            self.assertEqual(self.guard(root, commit), "", "sem a marca, o commit segue para o prompt de permissão")

            (path / "app.txt").write_text("v2\n", encoding="utf-8")
            code, err = self.aidw_json(root, "worktree", "remove", "us-1", "--json")
            self.assertEqual(code, 1)
            self.assertIn("não commitadas", err["error"])
            git(path, "commit", "-q", "-am", "mudança")
            code, err = self.aidw_json(root, "worktree", "remove", "us-1", "--json")
            self.assertEqual(code, 1)
            self.assertIn("não publicados", err["error"])
            git(path, "reset", "-q", "--keep", "main")  # descarta o commit de teste (worktree descartável)
            code, done = self.aidw_json(root, "worktree", "remove", "us-1", "--json")
            self.assertEqual(code, 0, done)
            self.assertFalse(path.exists())
            self.assertTrue((repo / "node_modules" / "lib" / "index.js").is_file(), "a junction não pode apagar a origem")
            self.assertIn("feature/1-teste-de-slug", git(repo, "branch"), "a branch é mantida")

            code, wt2 = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-2", "--json")
            self.assertEqual(code, 0, wt2)
            os.rmdir(Path(wt2["path"]) / "node_modules")  # remove só a junction
            shutil.rmtree(wt2["path"])
            code, clean = self.aidw_json(root, "worktree", "cleanup", "--json")
            self.assertEqual(clean["removed_from_registry"], [wt2["path"]])
            code, listed = self.aidw_json(root, "worktree", "list", "--json")
            self.assertEqual(listed["worktrees"], [])

    def test_worktree_de_pr(self) -> None:
        """`worktree create --pr`: worktree destacado na PR mesclada no destino (refs/pull/<n>/merge), diff na pasta
        da demanda, atualização quando o autor muda a PR (só o que mudou) e remoção sem branch."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "exemplo")
            origin = tmp / "origem"
            origin.mkdir()
            git(origin, "init", "-q", "-b", "main")
            (origin / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
            (origin / "app.txt").write_text("v1\n", encoding="utf-8")
            git(origin, "add", ".")
            git(origin, "commit", "-q", "-m", "inicial")

            def publish_pr(content: str) -> None:  # o servidor gera o merge da PR com o destino
                git(origin, "checkout", "-q", "-B", "feature/autor")
                (origin / "app.txt").write_text(content, encoding="utf-8")
                git(origin, "commit", "-q", "-am", f"autor: {content.strip()}")
                git(origin, "checkout", "-q", "--detach", "main")
                git(origin, "merge", "-q", "--no-ff", "-m", "merge da PR", "feature/autor")
                git(origin, "update-ref", "refs/pull/1/merge", "HEAD")
                git(origin, "checkout", "-q", "main")

            publish_pr("v2\n")
            repo = tmp / "repos" / "Aplicação"
            repo.parent.mkdir(parents=True)
            subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True, capture_output=True)
            (repo / "node_modules" / "lib").mkdir(parents=True)
            (repo / "node_modules" / "lib" / "index.js").write_text("// dependência\n", encoding="utf-8")
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
            self.assertEqual(git(path, "rev-parse", "--abbrev-ref", "HEAD").strip(), "HEAD", "destacado, sem branch")
            self.assertEqual((path / "app.txt").read_text(encoding="utf-8"), "v2\n")
            self.assertTrue((path / "node_modules" / "lib" / "index.js").is_file())
            self.assertNotIn("feature/", git(repo, "branch"), "não cria branch local")
            diff = (folder / "diff-pr1-Aplicação.patch").read_text(encoding="utf-8")
            self.assertIn("+v2", diff)
            self.assertEqual(json.loads((folder / "demand.json").read_text(encoding="utf-8"))["repos"][0]["pr"], "1")

            code, same = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-7",
                                        "--pr", "1", "--json")
            self.assertEqual((code, same["updated"]), (0, False))
            code, other = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-7", "--json")
            self.assertEqual(code, 1, "a demanda já tem a PR nesse repositório")

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
            self.assertTrue((repo / "node_modules" / "lib" / "index.js").is_file(), "a junction não pode apagar a origem")
            self.assertEqual(git(repo, "for-each-ref", "refs/aidw").strip(), "", "a ref da PR sai junto")

    def test_guard_mcp_por_agente(self) -> None:
        """O Codex não limita MCP por agente: o guard recusa o servidor fora do papel e a ferramenta bloqueada pelo
        contexto; MCP do próprio CLI e a conversa principal passam."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "codex", "native", "exemplo")
            proc = run_aidw(root, "apply")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            def call(agent: str | None, tool: str) -> str:
                return self.guard(root, {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {},
                                         **({"agent_type": agent} if agent else {})})

            self.assertIn('"deny"', call("aidw-codificador", "mcp__servidor-exemplo__escrever"), "bloqueada pelo contexto")
            self.assertIn('"deny"', call("aidw:codificador-high", "mcp__servidor-exemplo__escrever"), "variante do Claude")
            self.assertEqual(call("aidw-codificador", "mcp__servidor-exemplo__ler"), "")
            self.assertIn('"deny"', call("aidw-explorador", "mcp__playwright__browser_click"), "não é do papel")
            self.assertEqual(call("aidw-qa", "mcp__playwright__browser_click"), "")
            self.assertEqual(call("aidw-explorador", "mcp__node_repl__js"), "", "MCP do próprio Codex")
            self.assertEqual(call(None, "mcp__servidor-exemplo__escrever"), "", "a conversa principal")

    def test_worktree_link_de_pastas_vizinhas(self) -> None:
        """`worktree_link` do sistema: o caminho relativo que o código usa (HintPath `..\\..\\X`) vira junction ao
        lado do worktree; fora da raiz dos worktrees é recusado; o remove não apaga a junction compartilhada."""
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
            vizinho = tmp / "wt" / "us-5" / "Vizinho"
            self.assertTrue((vizinho / "bin" / "lib.dll").is_file(), "o HintPath ..\\Vizinho resolve a partir do worktree")
            self.assertTrue(any("não existe" in w for w in wt["warnings"]), wt["warnings"])
            self.assertTrue(any("ignorado" in w for w in wt["warnings"]), wt["warnings"])
            self.assertFalse((tmp / "escapa").exists(), "nunca cria junction fora da raiz dos worktrees")
            code, wt2 = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-6", "--json")
            self.assertEqual(wt2["outside_links"], ["../Vizinho"], "cada demanda tem a sua, na pasta dela")
            self.assertTrue((tmp / "wt" / "us-6" / "Vizinho" / "bin" / "lib.dll").is_file())
            (tmp / "outra").mkdir()
            (tmp / "wt" / "us-7").mkdir()
            load_aidw(root).make_link(tmp / "wt" / "us-7" / "Vizinho", tmp / "outra")
            code, wt3 = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-7", "--json")
            self.assertEqual(wt3["outside_links"], [], "junction para outro lugar não é reaproveitada")
            self.assertTrue(any("outro lugar" in w for w in wt3["warnings"]), wt3["warnings"])

            homonimo = tmp / "outros" / "Aplicação"  # mesmo nome, outro repositório (ex.: ProjetosTFS/Hope x Legados/Hope)
            homonimo.mkdir(parents=True)
            git(homonimo, "init", "-q", "-b", "main")
            (homonimo / "b.txt").write_text("b\n", encoding="utf-8")
            git(homonimo, "add", ".")
            git(homonimo, "commit", "-q", "-m", "inicial")
            code, wt4 = self.aidw_json(root, "worktree", "create", "--repo", str(homonimo), "--demand", "us-5", "--json")
            self.assertEqual(code, 0, wt4)
            self.assertEqual(Path(wt4["path"]), tmp / "wt" / "us-5" / "Aplicação.outros", "não invade a pasta do homônimo")
            code, done = self.aidw_json(root, "worktree", "remove", "us-5", "--repo", str(repo), "--json")
            self.assertEqual(code, 0, done)
            self.assertTrue((vizinho / "bin" / "lib.dll").is_file(), "a demanda ainda tem worktree: a junction fica")
            code, done = self.aidw_json(root, "worktree", "remove", "us-5", "--repo", str(homonimo), "--json")
            self.assertEqual(code, 0, done)
            self.assertFalse((tmp / "wt" / "us-5").exists(), "sem worktrees, a pasta da demanda sai com as junctions")
            self.assertTrue((tmp / "repos" / "Vizinho" / "bin" / "lib.dll").is_file(), "nunca apaga através da junction")

            # a demanda também mexe no vizinho: a junction dele vira o worktree da demanda
            aidw = load_aidw(root)
            viz = tmp / "repos" / "Vizinho"
            git(viz, "init", "-q", "-b", "main")
            git(viz, "add", ".")
            git(viz, "commit", "-q", "-m", "inicial")
            code, w8 = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-8", "--json")
            self.assertEqual(code, 0, w8)
            junction = tmp / "wt" / "us-8" / "Vizinho"
            self.assertTrue(aidw.is_link(junction))
            code, err = self.aidw_json(root, "worktree", "create", "--repo", str(viz), "--demand", "us-8",
                                       "--base", "nao-existe", "--json")
            self.assertEqual(code, 1, err)
            self.assertTrue(aidw.is_link(junction), "um erro no create não tira a junction de que o build depende")
            code, w8v = self.aidw_json(root, "worktree", "create", "--repo", str(viz), "--demand", "us-8", "--json")
            self.assertEqual((code, Path(w8v["path"])), (0, junction), w8v)
            self.assertFalse(aidw.is_link(junction))
            self.assertTrue(any("era junction" in w for w in w8v["warnings"]), w8v["warnings"])
            self.assertTrue((viz / "bin" / "lib.dll").is_file())
            (tmp / "wt" / "us-8" / "notas.txt").write_text("x\n", encoding="utf-8")
            for r in (repo, viz):
                code, rm = self.aidw_json(root, "worktree", "remove", "us-8", "--repo", str(r), "--json")
                self.assertEqual(code, 0, rm)
            self.assertTrue((tmp / "wt" / "us-8" / "notas.txt").is_file(), "com outro arquivo, a pasta da demanda fica")

    def test_worktree_no_formato_antigo(self) -> None:
        """Worktrees criados antes da pasta por demanda (`<raiz>/<repo>/<demanda>`, sem `layout` no registro)
        continuam valendo: list, hook `<demanda>/<pasta>`, open e remove."""
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
            self.assertIn(f"Abrindo claude em {old}", out)
            code, rm = self.aidw_json(root, "worktree", "remove", "us-40", "--json")
            self.assertEqual(code, 0, rm)
            self.assertFalse(old.exists())

    def test_status_e_open(self) -> None:
        """F7: `status` junta demanda ativa e worktree e aponta o que pede atenção; `open --demand` abre no worktree
        chamando o orquestrador (só se o AiDW está instalado naquele provedor)."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "exemplo")
            repo = self.make_repo(tmp)
            code, wt = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-1", "--json")
            self.assertEqual(code, 0, wt)
            self.aidw_json(root, "demand", "set", "us-1", "--step", "IMPLEMENT", "--title", "Teste")
            code, st = self.aidw_json(root, "status", "--json")
            self.assertEqual(code, 0, st)
            self.assertEqual([(d["id"], d["step"]) for d in st["demands"]], [("us-1", "IMPLEMENT")])
            w = st["demands"][0]["worktrees"][0]
            self.assertEqual((w["path"], w["dirty"], w["ahead"]), (wt["path"], False, 0))
            self.assertFalse(st["claude"]["installed"])
            self.assertEqual(st["attention"], [])

            code, out = self.aidw_json(root, "open", "--demand", "1", "--print")
            self.assertEqual(code, 0, out)
            self.assertIn(f"Abrindo claude em {Path(wt['path'])}", out)
            self.assertIn("não está instalado", out)
            self.assertNotRegex(out.strip().splitlines()[-1], r"(:|aidw-)go\b", "sem o plugin, o comando não existe")
            manifest = root / ".aidw" / "install-manifest.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"plugins": ["aidw@aidw-local"], "context": "exemplo", "codex": {"files": {}}}),
                                encoding="utf-8")
            code, out = self.aidw_json(root, "open", "--demand", "us-1", "--print")
            self.assertIn('"/aidw:go us-1"', out)
            self.assertIn("--add-dir", out)
            code, out = self.aidw_json(root, "open", "--demand", "us-1", "--provider", "codex", "--print")
            self.assertIn("--enable multi_agent_v2", out)
            self.assertNotIn("--profile", out, "no Codex o AiDW não instala perfil")
            self.assertIn('"$aidw-go us-1"', out)
            code, out = self.aidw_json(root, "open", "--demand", "us-1", "--no-orchestrate", "--print")
            self.assertNotRegex(out, r"(:|aidw-)go\b")
            code, out = self.aidw_json(root, "open", "--demand", "us-9", "--print")
            self.assertEqual(code, 1)

            # back e front na mesma demanda: abre no primeiro worktree criado e o outro entra por --add-dir
            front = tmp / "repos" / "Front"
            front.mkdir(parents=True)
            git(front, "init", "-q", "-b", "main")
            (front / "a.txt").write_text("a\n", encoding="utf-8")
            git(front, "add", ".")
            git(front, "commit", "-q", "-m", "inicial")
            code, wtf = self.aidw_json(root, "worktree", "create", "--repo", str(front), "--demand", "us-1", "--json")
            self.assertEqual(code, 0, wtf)
            code, out = self.aidw_json(root, "open", "--demand", "us-1", "--print")
            self.assertEqual(code, 0, out)
            self.assertIn(f"Abrindo claude em {Path(wt['path']).parent}", out, "abre na pasta da demanda")
            self.assertNotIn(f"--add-dir {Path(wtf['path'])}", out, "os worktrees já estão dentro dela")
            code, out = self.aidw_json(root, "open", "--demand", "us-1", "--repo", "Front", "--print")
            self.assertIn(f"Abrindo claude em {Path(wtf['path'])}", out)
            self.assertIn(f"--add-dir {Path(wt['path'])}", out)
            code, out = self.aidw_json(root, "open", "--demand", "us-1", "--repo", "Nenhum", "--print")
            self.assertEqual(code, 1, out)
            code, wtb = self.aidw_json(root, "worktree", "create", "--repo", str(front), "--demand", "bug-1",
                                       "--slug", "outro", "--json")
            self.assertEqual(code, 0, wtb)
            code, out = self.aidw_json(root, "open", "--demand", "1", "--print")
            self.assertEqual(code, 1, "1 casa us-1 e bug-1: não escolhe")
            self.assertIn("mais de uma demanda", out)
            for demand in ("us-1", "bug-1"):
                code, rm = self.aidw_json(root, "worktree", "remove", demand, "--repo", str(front), "--json")
                self.assertEqual(code, 0, rm)
            self.aidw_json(root, "demand", "set", "bug-1", "--status", "done")

            self.aidw_json(root, "demand", "set", "us-1", "--status", "done")
            (Path(wt["path"]) / "app.txt").write_text("v2\n", encoding="utf-8")
            code, st = self.aidw_json(root, "status", "--json")
            self.assertEqual(st["demands"], [])
            self.assertEqual(len(st["attention"]), 1, st["attention"])
            self.assertIn("não commitadas", st["attention"][0])
            git(Path(wt["path"]), "checkout", "--", "app.txt")
            code, st = self.aidw_json(root, "status", "--json")
            self.assertIn("worktree remove us-1", st["attention"][0])
            code, text = self.aidw_json(root, "status")
            self.assertEqual(code, 0, text)
            self.assertIn("Demandas ativas (0)", text)
            (root / "contexts" / "exemplo" / "demandas" / "us-1" / "demand.json").unlink()
            code, st = self.aidw_json(root, "status", "--json")
            self.assertIn("sem demand.json", st["attention"][0], "worktree sem demand.json não pode sumir do status")
            manifest.write_text(json.dumps({"plugins": ["aidw@aidw-local"], "context": "exemplo", "cli_done": False}),
                                encoding="utf-8")
            code, text = self.aidw_json(root, "status")
            self.assertIn("a última instalação parou", text, "instalação incompleta não é 'em dia'")

    def test_cenarios_de_criacao_e_deteccao(self) -> None:
        """Critérios de saída da F4: subpasta, fora do git, branch existente, branch usada por outro worktree,
        falha do git no remove (fail-safe) e hook filtrando pelo repositório."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "exemplo")
            repo = self.make_repo(tmp)
            (repo / "src").mkdir()
            code, det = self.aidw_json(root, "project", "detect", "--path", str(repo / "src"), "--json")
            self.assertEqual((det["git"], det["main"], det["is_worktree"]), (True, repo.as_posix(), False))
            code, det = self.aidw_json(root, "project", "detect", "--path", str(tmp), "--json")
            self.assertFalse(det["git"])

            git(repo, "branch", "feature/7-existente")
            code, wt = self.aidw_json(root, "worktree", "create", "--repo", str(repo / "src"), "--demand", "us-7",
                                      "--slug", "existente", "--json")
            self.assertEqual((code, wt["branch"]), (0, "feature/7-existente"), wt)
            git(repo, "branch", "feature/8")
            git(repo, "worktree", "add", str(tmp / "manual"), "feature/8")
            code, err = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-8", "--json")
            self.assertEqual(code, 1)
            self.assertIn("git worktree add falhou", err["error"])

            other = tmp / "repos" / "Outro"
            other.mkdir(parents=True)
            git(other, "init", "-q", "-b", "main")
            (other / "a.txt").write_text("a\n", encoding="utf-8")
            git(other, "add", ".")
            git(other, "commit", "-q", "-m", "inicial")
            code, hook = self.aidw_json(root, "worktree", "hook-create", stdin=json.dumps({"name": "us-7", "cwd": str(other)}))
            self.assertEqual(code, 0, hook)
            self.assertEqual(Path(hook.strip()), tmp / "wt" / "us-7" / "Outro", "o hook não pode levar a outro repositório")

            # chat aberto na raiz do AiDW (também um repositório): entra no worktree que a demanda já tem
            git(root, "init", "-q", "-b", "main")
            code, hook = self.aidw_json(root, "worktree", "hook-create", stdin=json.dumps({"name": "us-7", "cwd": str(root)}))
            self.assertEqual((code, Path(hook.strip())), (0, Path(wt["path"])),
                             "us-7 tem worktree em dois repositórios: a raiz entra no primeiro criado")
            # skill diff: `<demanda>/<pasta>` leva ao worktree daquele repositório, de qualquer pasta
            code, hook = self.aidw_json(root, "worktree", "hook-create",
                                        stdin=json.dumps({"name": "us-7/outro", "cwd": str(repo)}))
            self.assertEqual((code, Path(hook.strip())), (0, tmp / "wt" / "us-7" / "Outro"))
            code, det = self.aidw_json(root, "project", "detect", "--path", str(tmp / "wt" / "us-7"), "--json")
            self.assertEqual((det["demand"], [w["folder"] for w in det["worktrees"]]), ("us-7", ["Aplicação", "Outro"]),
                             "a pasta da demanda (não é git) é reconhecida")
            code, err = self.aidw_json(root, "worktree", "hook-create",
                                       stdin=json.dumps({"name": "us-7/Nenhum", "cwd": str(repo)}))
            self.assertEqual(code, 1, err)
            code, wt9 = self.aidw_json(root, "worktree", "create", "--repo", str(repo), "--demand", "us-9", "--json")
            self.assertEqual(code, 0, wt9)
            code, hook = self.aidw_json(root, "worktree", "hook-create", stdin=json.dumps({"name": "us-9", "cwd": str(root)}))
            self.assertEqual((code, Path(hook.strip())), (0, Path(wt9["path"])), "sem worktree do próprio AiDW")
            self.assertFalse((tmp / "wt" / "us-9" / root.name).exists())
            self.aidw_json(root, "demand", "set", "us-10", "--status", "active", "--json")
            code, err = self.aidw_json(root, "worktree", "hook-create", stdin=json.dumps({"name": "us-10", "cwd": str(root)}))
            self.assertEqual(code, 1, "demanda sem worktree: a raiz do AiDW não vira worktree dela")
            self.assertIn("worktree create --repo", err)
            self.assertFalse((tmp / "wt" / "us-10").exists())

            path = Path(wt["path"])
            (path / "novo.txt").write_text("x\n", encoding="utf-8")
            git(path, "add", ".")
            git(path, "commit", "-q", "-m", "não publicado")
            git(repo, "branch", "-m", "main", "principal")  # a base some: o git falha ao contar os commits
            code, err = self.aidw_json(root, "worktree", "remove", "us-7", "--repo", str(repo), "--json")
            self.assertEqual(code, 1, err)
            self.assertIn("não foi possível conferir", err["error"])
            self.assertTrue(path.is_dir(), "falha do git nunca remove o worktree")


class SessionModeTest(unittest.TestCase):
    """F5: demand set/show/list e os hooks de sessão (UserPromptSubmit registra o modo; SessionStart lembra)."""

    def test_demanda_e_modo_orquestrador(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "exemplo")
            wt = WorktreeTest()
            code, d = wt.aidw_json(root, "demand", "set", "us-5", "--status", "active", "--step", "UNDERSTAND",
                                   "--title", "Teste", "--json")
            self.assertEqual((code, d["step"], d["status"]), (0, "UNDERSTAND", "active"), d)
            code, d = wt.aidw_json(root, "demand", "set", "us-5", "--step", "IMPLEMENT", "--json")
            self.assertEqual([h["step"] for h in d["history"]], ["UNDERSTAND", "IMPLEMENT"])
            code, bad = wt.aidw_json(root, "demand", "set", "us-5", "--step", "QUALQUER", "--json")
            self.assertEqual(code, 1)
            wt.aidw_json(root, "demand", "set", "us-6", "--status", "done", "--json")
            code, lst = wt.aidw_json(root, "demand", "list", "--active", "--json")
            self.assertEqual([x["id"] for x in lst["demands"]], ["us-5"])
            code, show = wt.aidw_json(root, "demand", "show", "us-5")
            self.assertEqual(show["title"], "Teste")
            self.assertNotIn("mode", lst["demands"][0], "o modo da sessão saiu no fluxo v3")
            proc = run_aidw(root, "demand", "set", "us-5", "--note", "esperando")
            self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "us-5: IMPLEMENT (active)"),
                             "sem --json, uma linha: o demand.json inteiro só pesaria no chat do orquestrador")
            proc = run_aidw(root, "demand", "set", "us-5", "--step", "QUALQUER")
            self.assertEqual(proc.returncode, 1)
            self.assertTrue(proc.stdout.startswith("erro: etapa desconhecida"), proc.stdout)
            # painel V2: resumo, etapas de fora do AiDW e PR por repositório
            code, d = wt.aidw_json(root, "demand", "set", "us-5", "--summary", "Linha 1\nLinha 2", "--step",
                                   "CODE_REVIEW", "--json")
            self.assertEqual((code, d["summary"], d["step"]), (0, "Linha 1\nLinha 2", "CODE_REVIEW"), d)
            code, bad = wt.aidw_json(root, "demand", "set", "us-5", "--summary", "1\n2\n3\n4\n5", "--json")
            self.assertEqual(code, 1, "resumo passa de 4 linhas")
            code, bad = wt.aidw_json(root, "demand", "set", "us-5", "--pr", "Front=7789", "--json")
            self.assertEqual(code, 1, "repositório que a demanda não tem")
            code, bad = wt.aidw_json(root, "demand", "set", "us-5", "--pr", "Front", "--json")
            self.assertEqual(code, 1, "--pr sem número")
            code, d = wt.aidw_json(root, "demand", "set", "us-5", "--step", "QA_TEST", "--json")
            self.assertEqual(d["history"][-1]["step"], "QA_TEST")
            demand_file = Path(d["folder"]) / "demand.json"
            data = json.loads(demand_file.read_text(encoding="utf-8"))
            data["repos"] = [{"repo": "C:/p/Assistente.Front", "path": "C:/wt/us-5/Assistente.Front", "branch": "b"}]
            demand_file.write_text(json.dumps(data), encoding="utf-8")
            code, d = wt.aidw_json(root, "demand", "set", "us-5", "--pr", "assistente.front=7789", "--json")
            self.assertEqual((code, d["repos"][0]["pr"]), (0, "7789"), d)

            hook = lambda payload: subprocess.run([sys.executable, str(root / "aidw_guard.py")],  # noqa: E731
                                                  input=json.dumps(payload), capture_output=True, text=True,
                                                  encoding="utf-8", timeout=30).stdout
            base = {"session_id": "s1", "cwd": str(tmp)}
            self.assertEqual(hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "oi, tudo bem?"}), "")
            self.assertFalse((root / "state" / "sessions.json").exists(), "mensagem comum não grava nada")
            self.assertEqual(hook({**base, "hook_event_name": "SessionStart", "source": "compact"}), "")
            hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "/aidw:go us-5 continuar"})
            out = json.loads(hook({**base, "hook_event_name": "SessionStart", "source": "compact"}))
            ctx = out["hookSpecificOutput"]["additionalContext"]
            self.assertIn("modo orquestrador", ctx)
            self.assertIn("aidw/skills/go/SKILL.md", ctx)
            self.assertIn("us-5 continuar", ctx)
            self.assertLess(len(ctx.encode()), 2000, "o hook só injeta ~2 KB")
            self.assertEqual(hook({"session_id": "s2", "hook_event_name": "SessionStart", "source": "compact"}), "")
            hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "/aidw:sair"})
            cx = {"session_id": "c1", "cwd": str(tmp)}
            hook({**cx, "hook_event_name": "UserPromptSubmit", "prompt": "$aidw-go us-7"})
            out = json.loads(hook({**cx, "hook_event_name": "SessionStart", "source": "compact"}))
            ctx_codex = out["hookSpecificOutput"]["additionalContext"]
            self.assertIn("aidw-go/SKILL.md", ctx_codex)
            self.assertIn("$aidw-sair", ctx_codex)
            self.assertEqual(hook({**base, "hook_event_name": "SessionStart", "source": "resume"}), "")
            hook({**cx, "hook_event_name": "UserPromptSubmit", "prompt": "$aidw-done"})
            self.assertEqual(hook({**cx, "hook_event_name": "SessionStart", "source": "compact"}), "",
                             "o done fecha a tarefa e encerra o modo orquestrador, como o sair")
            lv = {"session_id": "l1", "cwd": str(tmp)}
            hook({**lv, "hook_event_name": "UserPromptSubmit", "prompt": "/aidw:lev us-8"})
            out = json.loads(hook({**lv, "hook_event_name": "SessionStart", "source": "compact"}))
            ctx_lev = out["hookSpecificOutput"]["additionalContext"]
            self.assertIn("aidw/skills/go/SKILL.md", ctx_lev, "a go entende o pedido de levantamento")
            self.assertIn('"levantamento us-8"', ctx_lev)
            code, d = wt.aidw_json(root, "demand", "set", "us-8", "--step", "ESTIMATE", "--json")
            self.assertEqual((code, d["step"]), (0, "ESTIMATE"), d)


    def test_contexto_e_arquivo_corrompido(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            wt = WorktreeTest()
            folder = root / "contexts" / "exemplo" / "demandas"
            (folder / "us-8").mkdir(parents=True)
            (folder / "us-8" / "demand.json").write_text(json.dumps({"id": "us-8", "context": "outro"}), encoding="utf-8")
            code, lst = wt.aidw_json(root, "demand", "list", "--json")
            self.assertEqual(lst["demands"], [], "demanda de outro contexto não aparece")
            code, err = wt.aidw_json(root, "demand", "set", "us-8", "--step", "IMPLEMENT", "--json")
            self.assertEqual(code, 1)
            self.assertIn("contexto", err["error"])
            (folder / "us-9").mkdir()
            (folder / "us-9" / "demand.json").write_text("{quebrado", encoding="utf-8")
            code, d = wt.aidw_json(root, "demand", "set", "us-9", "--step", "IMPLEMENT", "--json")
            self.assertEqual(code, 0, d)
            self.assertIn("ilegível", d["warning"])
            self.assertTrue(list((folder / "us-9").glob("demand.json.*.bak")), "o arquivo ilegível é guardado")

    def test_plugin_leva_hooks_e_protocolo(self) -> None:
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
            # mods do Claude Code: plugin próprio no marketplace, sem os testes, com a raiz do AiDW desta máquina
            self.assertEqual(plug["mods"]["plugin"], "aidw-mods")
            self.assertIn("plugins/aidw-mods/hooks/register.tsx", files)
            self.assertFalse([k for k in files if k.startswith("plugins/aidw-mods/tests/")], "os testes não vão")
            mods_meta = json.loads(files["plugins/aidw-mods/.claude-plugin/plugin.json"])
            self.assertEqual(mods_meta["userConfig"]["aidwRoot"]["default"], root.as_posix())
            self.assertEqual(mods_meta["version"], plug["mods"]["version"])
            market = json.loads(files[".claude-plugin/marketplace.json"])
            self.assertEqual([p["name"] for p in market["plugins"]], ["aidw-mods", "aidw"])
            orq = files["plugins/aidw/skills/go/SKILL.md"].decode("utf-8")
            for step in ("project detect --json", "demand list --active --json", "não recomece",
                         "demand set <id> --step <AÇÃO>", "EnterWorktree"):
                self.assertIn(step, orq)
            for gone in ("--mode", "AskUserQuestion", "## Modo interativo"):
                self.assertNotIn(gone, orq, "sem a escolha de modo da sessão")
            self.assertLess(orq.index("Ao ser chamado"), orq.index("# ROLE"), "o protocolo vem antes do resto")
            sair = files["plugins/aidw/skills/sair/SKILL.md"].decode("utf-8")
            diff = files["plugins/aidw/skills/diff/SKILL.md"].decode("utf-8")
            for step in ("ExitWorktree", 'action: "keep"', 'name: "<demanda>/<folder>"', "worktree list --json",
                         "**seguinte**", "`sair`: a pasta da demanda"):
                self.assertIn(step, diff)
            self.assertIn("/aidw:diff sair", orq)
            self.assertIn("workflow `levantamento`", orq)
            lev = files["plugins/aidw/skills/lev/SKILL.md"].decode("utf-8")
            self.assertIn("name: lev", lev)
            self.assertIn("disable-model-invocation: true", lev)
            self.assertIn("**Levantamento:**", lev)
            # o orquestrador enxuto do levantamento: só o explorador, o procedimento já dentro, sem o desenvolvimento
            self.assertLess(lev.index("**Levantamento:**"), lev.index("# ROLE"))
            for part in ("# STEPS", "`UNDERSTAND` → `EXPLORE` → `ESTIMATE` → `DONE`", "## 4. Estimar",
                         "/aidw:go <id>", "`aidw:explorador`"):
                self.assertIn(part, lev)
            for gone in ("# WORKFLOW", "## Workflows", "**Panel**", "`aidw:codificador`", "EnterWorktree",
                         "*levantamento* `"):
                self.assertNotIn(gone, lev)
            self.assertLess(len(lev), len(orq), "menor que a skill orquestrar, mesmo com o procedimento dentro")
            self.assertIn("plugins/aidw/reference/levantamento.md", files)
            self.assertIn("--status paused", sair)
            self.assertIn("disable-model-invocation: true", sair)


class ContextTest(unittest.TestCase):
    """aidw.py context list / check / create / use (skills contexto-listar, contexto-usar, contexto-criar)."""

    def test_contexto_sobrescreve_routing_e_workflows(self) -> None:
        """contexts/<nome>/routing.toml vai por cima do núcleo; workflows/ do contexto substituem os de mesmo nome; o
        mapa tipo de card → workflow aparece no orquestrador e um workflow inexistente no mapa é erro."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            ctx_dir = root / "contexts" / "exemplo"
            (ctx_dir / "routing.toml").write_text('max_retries = 2\n\n[[effort.variants.reviewer]]\neffort = "low"\n'
                                                  'when = "só a do contexto"\n', encoding="utf-8")
            (ctx_dir / "workflows").mkdir()
            (ctx_dir / "workflows" / "bugfix.yaml").write_text(
                "name: bugfix\ndescription: Bug do contexto.\nsteps:\n  - id: implement\n    agent: coder\n",
                encoding="utf-8")
            toml = ctx_dir / "context.toml"
            toml.write_text(toml.read_text(encoding="utf-8") + '\n[workflows]\nby_type = { "Bug" = "bugfix" }\n',
                            encoding="utf-8")
            aidw = load_aidw(root)
            rep = aidw.Report(quiet=True)
            b = aidw.build(aidw.load_config(), aidw.load_catalog(), rep)
            self.assertEqual(rep.errors, [])
            self.assertEqual(b["routing"]["max_retries"], 2)
            self.assertEqual(list(b["resolved"]["reviewer"]["variants"]), ["revisor", "revisor-low"],
                             "a lista do contexto substitui a do núcleo")
            self.assertIn("codificador-medium", b["resolved"]["coder"]["variants"], "o resto vem do núcleo")
            orq = b["orchestrator_md"]
            self.assertIn("## Workflows", orq)
            self.assertIn("Bug do contexto.", orq)
            self.assertIn("contexts/exemplo/workflows/bugfix.yaml", orq)
            self.assertIn("- Bug → `bugfix`", orq)
            self.assertIn("workflows/desenvolvimento.yaml", orq)

            toml.write_text(toml.read_text(encoding="utf-8").replace('"bugfix" }', '"nao-existe" }'), encoding="utf-8")
            rep = aidw.Report(quiet=True)
            aidw.build(aidw.load_config(), aidw.load_catalog(), rep)
            self.assertTrue(any("nao-existe" in e for e in rep.errors), rep.errors)

    def test_demanda_guarda_tasks_dos_tickets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            wt = WorktreeTest()
            code, d = wt.aidw_json(root, "demand", "set", "us-9", "--task", "front=5001", "--json")
            self.assertEqual((code, d["tasks"]), (0, {"front": "5001"}), d)
            code, d = wt.aidw_json(root, "demand", "set", "us-9", "--task", "api=#5002", "--json")
            self.assertEqual(d["tasks"], {"front": "5001", "api": "5002"}, "soma às que já estavam")
            code, err = wt.aidw_json(root, "demand", "set", "us-9", "--task", "api", "--json")
            self.assertEqual(code, 1, err)
            code, d = wt.aidw_json(root, "demand", "set", "us-9", "--loop", "bug-1234", "--json")
            self.assertEqual(d["loop"], "bug-1234")
            code, d = wt.aidw_json(root, "demand", "set", "us-9", "--loop", "-", "--json")
            self.assertNotIn("loop", d)
            code, err = wt.aidw_json(root, "demand", "set", "us-9", "--loop", "Bug 1", "--json")
            self.assertEqual(code, 1, err)

    def test_etapa_de_fora_do_contexto(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            wt = WorktreeTest()
            code, err = wt.aidw_json(root, "demand", "set", "us-9", "--step", "UX_VALIDATION", "--json")
            self.assertEqual(code, 1, "sem o contexto declarar, a etapa não existe")
            toml = root / "contexts" / "exemplo" / "context.toml"
            toml.write_text(toml.read_text(encoding="utf-8") + (
                '\n[[workflows.external_steps]]\nstep = "UX_VALIDATION"\nname = "Validação UX"\nbefore = "CODE_REVIEW"\n'
                'who = "o UX"\nwhen = "o card tem UX Owner"\n'), encoding="utf-8")
            code, d = wt.aidw_json(root, "demand", "set", "us-9", "--extra-step", "UX_VALIDATION", "--json")
            self.assertEqual((code, d["extra_steps"]), (0, ["UX_VALIDATION"]), d)
            code, d = wt.aidw_json(root, "demand", "set", "us-9", "--step", "UX_VALIDATION", "--json")
            self.assertEqual((code, d["step"]), (0, "UX_VALIDATION"), d)
            code, d = wt.aidw_json(root, "demand", "set", "us-9", "--extra-step", "-UX_VALIDATION", "--json")
            self.assertNotIn("extra_steps", d)
            code, err = wt.aidw_json(root, "demand", "set", "us-9", "--extra-step", "QA_TEST", "--json")
            self.assertEqual(code, 1, "só etapa declarada pelo contexto")

            aidw = load_aidw(root)
            rep = aidw.Report(quiet=True)
            aidw.check_external_steps({"name": "x", "workflows": {"external_steps": [
                {"step": "REVIEW", "name": "a", "before": "CODE_REVIEW", "when": "b"},
                {"step": "UX", "name": "a", "before": "DONE", "when": "b"},
                {"step": "ux-val", "name": "a", "before": "CODE_REVIEW", "when": "b"},
                {"step": "SEM_NOME", "before": "QA_TEST", "when": "b"}]}}, rep)
            self.assertEqual(len(rep.errors), 4, rep.errors)

            # a escala de voto de PR saiu: um contexto que ainda declara [[mods.votes]] recebe um aviso, não um erro
            rep = aidw.Report(quiet=True)
            aidw.check_votes({"name": "x", "mods": {"votes": [{"value": "10", "label": "Aprovar"}]}}, rep)
            self.assertEqual((len(rep.errors), len(rep.warnings)), (0, 1))

    def test_pasta_da_demanda_exclui_o_claude_md_da_raiz(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            wt = WorktreeTest()
            code, d = wt.aidw_json(root, "demand", "set", "us-9", "--step", "UNDERSTAND", "--json")
            settings = Path(d["folder"]) / ".claude" / "settings.json"
            pattern = "**/" + root.as_posix().split(":", 1)[-1].lstrip("/") + "/CLAUDE.md"
            self.assertEqual(json.loads(settings.read_text(encoding="utf-8")), {"claudeMdExcludes": [pattern]},
                             "chat aberto na pasta da demanda não carrega o CLAUDE.md da raiz junto com a skill")
            settings.write_text(json.dumps({"claudeMdExcludes": ["**/outro/CLAUDE.md"], "model": "x"}), encoding="utf-8")
            wt.aidw_json(root, "demand", "set", "us-9", "--step", "EXPLORE", "--json")
            self.assertEqual(json.loads(settings.read_text(encoding="utf-8")),
                             {"claudeMdExcludes": ["**/outro/CLAUDE.md", pattern], "model": "x"}, "o que já havia fica")

    def test_metricas_do_orquestrador_somam_por_sessao_e_modelo(self) -> None:
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
                                   msg="cache escrito a 2× a entrada")
            code, r = wt.aidw_json(root, *turn, "--model", "claude-opus-5-5")
            self.assertEqual(r["turns"], 2, "a mesma sessão e modelo somam na mesma linha")
            code, r = wt.aidw_json(root, *turn, "--model", "claude-sonnet-5-5")
            self.assertEqual(r["turns"], 1, "outro modelo é outra linha")
            text = (demand / "metricas-orquestrador.md").read_text(encoding="utf-8")
            rows = [line for line in text.splitlines() if line.startswith("| 79aafeb8 |")]
            self.assertEqual(len(rows), 2, text)
            self.assertIn("| claude-opus-5-5 | 2 | 60s | 20 | 600,000 | 0 | 1,600 |", rows[0])

    def test_record_nao_repete_a_delegacao_que_o_mod_gravou(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            wt = WorktreeTest()
            demand = Path(tmp) / "us-9"
            base = ["record", "--agent", "explorer", "--demand", str(demand), "--state", "exploration_complete"]
            code, r = wt.aidw_json(root, *base, "--label", "lev", "--tokens", "1000", "--tool-uses", "5",
                                   "--duration-ms", "60000")
            self.assertEqual((code, r["tokens_in"]), (0, 1000), r)
            f = demand / "metricas.md"
            f.write_text(f.read_text(encoding="utf-8").rstrip("\n"), encoding="utf-8")  # editado à mão, sem a quebra
            code, r = wt.aidw_json(root, *base, "--label", "lev")
            self.assertEqual((code, r["tokens_in"], r["turns"], r["duration_s"]), (0, 1000, 5, 60), r)
            self.assertIn("1.000 tokens", r["resumo"])
            self.assertTrue(any("já registrou" in w for w in r["warnings"]), r)
            wt.aidw_json(root, *base, "--label", "outra", "--tokens", "50")
            rows = [x for x in f.read_text(encoding="utf-8").splitlines() if x.startswith("| 2")]
            self.assertEqual([x.split(" | ")[5] for x in rows], ["lev", "outra"], "sem linha repetida nem colada")

    def test_ciclo_de_contextos(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            wt = WorktreeTest()
            code, lst = wt.aidw_json(root, "context", "list", "--json")
            self.assertEqual((lst["active"], [c["name"] for c in lst["contexts"]]), ("exemplo", ["exemplo"]))

            code, made = wt.aidw_json(root, "context", "create", "novo", "--description", "Empresa — Squad", "--json")
            self.assertEqual(code, 0, made)
            novo = root / "contexts" / "novo"
            self.assertTrue((novo / ".git").exists(), "contexto novo tem repositório git próprio")
            self.assertIn("[worktree]", (novo / "context.toml").read_text(encoding="utf-8"))
            code, dup = wt.aidw_json(root, "context", "create", "novo", "--json")
            self.assertEqual(code, 1)
            code, chk = wt.aidw_json(root, "context", "check", "novo", "--json")
            self.assertEqual(code, 0, chk)

            code, err = wt.aidw_json(root, "context", "use", "nao-existe", "--skip-cli", "--json")
            self.assertEqual(code, 1)
            before = (root / "aidw.config.toml").read_text(encoding="utf-8")
            code, used = wt.aidw_json(root, "context", "use", "novo", "--skip-cli", "--json")
            self.assertEqual(code, 0, used)
            after = (root / "aidw.config.toml").read_text(encoding="utf-8")
            self.assertIn('active = "novo"', after)
            self.assertEqual(before.replace('active = "exemplo"', 'active = "novo"'), after,
                             "só a linha active muda; comentários e o resto ficam")
            code, lst = wt.aidw_json(root, "context", "list", "--json")
            self.assertEqual(lst["active"], "novo")
            wt.aidw_json(root, "demand", "set", "us-3", "--status", "active", "--json")
            code, none = wt.aidw_json(root, "context", "use", "", "--skip-cli", "--json")
            self.assertEqual(code, 0, none)
            self.assertIn('active = ""', (root / "aidw.config.toml").read_text(encoding="utf-8"))
            self.assertTrue(any("us-3" in w for w in none["warnings"]), "avisa da demanda ativa que fica pausada")
            code, back = wt.aidw_json(root, "context", "use", "novo", "--skip-cli", "--json")
            self.assertEqual(code, 0, back)

            toml = novo / "context.toml"
            toml.write_text(toml.read_text(encoding="utf-8").replace(
                'state_dir = "contexts/novo/demandas"', 'state_dir = "contexts/exemplo/demandas"'), encoding="utf-8")
            code, chk = wt.aidw_json(root, "context", "check", "novo", "--json")
            self.assertEqual(code, 1)
            self.assertTrue(any("state_dir" in e for e in chk["errors"]), chk)


class KnowledgeTest(unittest.TestCase):
    """`aidw.py kb`: a base de conhecimento do contexto (notas ligadas por [[links]])."""

    def test_show_brief_e_collect(self) -> None:
        """Fluxo v3: `kb show --brief` sem a lista de quem cita a nota, e `kb collect <id>` juntando o que a demanda
        aprendeu (seções *Base de conhecimento*, aprendizados, notas do resumo e decisões do plano) para o /aidw:done."""
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "exemplo")
            full = run_aidw(root, "kb", "show", "sistema-a")
            brief = run_aidw(root, "kb", "show", "sistema-a", "--brief")
            self.assertEqual(brief.returncode, 0, brief.stderr)
            self.assertIn("## Citada por", full.stdout)
            self.assertNotIn("## Citada por", brief.stdout)
            self.assertIn("citada por 2 nota(s)", brief.stdout)

            demand = root / "contexts" / "exemplo" / "demandas" / "us-9"
            demand.mkdir(parents=True)
            (demand / "exploracao-rota.md").write_text(
                "# Exploração\n\n## Q1 onde\n- fato\n\n## Base de conhecimento\n- novo → [[sistema-a]]: rota X — `a.cs:1`\n",
                encoding="utf-8")
            (demand / "plano-us-9.md").write_text(
                "# Plano v1\n\n## Decisões tomadas\n| 1 | Tema | Decisão | Felipe, 2026-10-23 |\n\n## Objetivo\nx\n",
                encoding="utf-8")
            (demand / "plano-us-9-v1.md").write_text("## Decisões tomadas\nvelha\n", encoding="utf-8")
            (demand / "review-us-9-r1.md").write_text("### R1-01 — SUGESTAO — `a.cs:2`\n", encoding="utf-8")
            (demand / "aprendizados-us-9.md").write_text("- decisão do Felipe → [[sistema-a]]\n", encoding="utf-8")
            out = run_aidw(root, "kb", "collect", "us-9")
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            text = (demand / "collect-us-9.md").read_text(encoding="utf-8")
            self.assertIn("## exploracao-rota.md", text)
            self.assertIn("rota X", text)
            self.assertNotIn("## Q1", text, "só a seção Base de conhecimento do relatório")
            self.assertIn("Felipe, 2026-10-23", text)
            self.assertNotIn("velha", text, "a versão antiga do plano não entra")
            self.assertNotIn("review-us-9-r1.md", text, "relatório sem a seção não entra")
            self.assertIn("decisão do Felipe", text)
            self.assertNotEqual(run_aidw(root, "kb", "collect", "nao-existe").returncode, 0)

    def test_base_de_conhecimento(self) -> None:
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
                             "[[sistemas/sistema-a.md|A]] também conta como link para o sistema-a")
            code, b = wt.aidw_json(root, "kb", "show", "sistema-b", "--json")
            self.assertEqual(b["meta"]["sistemas"], ["sistema-b"], "lista em bloco, como o Obsidian grava")
            code, alias = wt.aidw_json(root, "kb", "show", "Protocolo", "--json")
            self.assertEqual(alias["key"], "solicitacao", "acha pelo alias, sem caixa")
            code, miss = wt.aidw_json(root, "kb", "show", "nao-existe", "--json")
            self.assertEqual(code, 1)

            code, found = wt.aidw_json(root, "kb", "search", "solicitacao", "--json")
            self.assertEqual(found["hits"][0]["key"], "solicitacao", "sem acento acha 'Solicitação'; o título pesa mais")
            self.assertEqual({h["key"] for h in found["hits"]}, {"solicitacao", "sistema-a"})

            code, idx = wt.aidw_json(root, "kb", "index", "--json")
            index = (kb / "index.md").read_text(encoding="utf-8")
            self.assertIn("## Sistemas (2)", index)
            self.assertIn("| [[solicitacao\\|Solicitação]] | pedido, request |", index)
            code, chk = wt.aidw_json(root, "kb", "check", "--json")
            self.assertEqual(chk["errors"], [], "o índice gerado não quebra o check")

            self.assertEqual(run_aidw(root, "apply").returncode, 0)
            gen = (root / ".claude" / "agents" / "codificador.md").read_text(encoding="utf-8")
            self.assertIn(f"- Knowledge: `{(kb / 'sistemas' / 'sistema-a.md').as_posix()}`", gen)
            self.assertIn("kb show <system|note>", gen)
            self.assertIn("a fact, not a rule", gen, "a nota descreve; o guia do time e as policies decidem")

            longa = kb / "integracoes" / "contrato-ab.md"
            longa.write_text(longa.read_text(encoding="utf-8").replace("atualizado: 2026-10-07", "atualizado: 2020-01-01")
                             + "".join(f"- linha {i}\n" for i in range(160)), encoding="utf-8")
            code, chk = wt.aidw_json(root, "kb", "check", "--json")
            self.assertEqual(chk["errors"], [], "tamanho e idade são avisos, não erros")
            avisos = "\n".join(chk["warnings"])
            self.assertIn("contrato-ab.md: 1", avisos)
            self.assertIn("divida em notas ligadas", avisos)
            self.assertIn("conferida pela última vez em 2020-01-01", avisos)
            self.assertNotIn("solicitacao.md: conferida", avisos)

            (kb / "sistemas" / "sistema-b.md").unlink()
            (kb / "integracoes" / "quebrada.md").write_text(
                "---\ntipo: integracao\nresumo: x\nsistemas: [sistema-z]\natualizado: 2026-10-07\n---\n\n"
                "Ver [[inexistente]]. Password=abc12345\n", encoding="utf-8")
            (kb / "conceitos" / "sistema-a.md").write_text("---\ntipo: conceito\nresumo: x\n---\n", encoding="utf-8")
            code, chk = wt.aidw_json(root, "kb", "check", "--json")
            self.assertEqual(code, 1)
            errors = "\n".join(chk["errors"])
            for expected in ("nome repetido 'sistema-a'", "link quebrado [[sistema-b]]", "link quebrado [[inexistente]]",
                             "falta `fontes`", "sistema-z", "parece segredo"):
                self.assertIn(expected, errors)
            self.assertTrue(any("sistema 'sistema-b' sem nota" in w for w in chk["warnings"]), chk["warnings"])
            code, ctx = wt.aidw_json(root, "context", "check", "exemplo", "--json")
            self.assertEqual(code, 1)
            self.assertTrue(any(e.startswith("base de conhecimento:") for e in ctx["errors"]), ctx)

            code, made = wt.aidw_json(root, "context", "create", "novo", "--description", "Novo", "--json")
            novo = root / "contexts" / "novo"
            self.assertIn('[knowledge]\ndir = "conhecimento"', (novo / "context.toml").read_text(encoding="utf-8"))
            self.assertIn("# Base de conhecimento — Novo", (novo / "conhecimento" / "README.md").read_text(encoding="utf-8"))
            self.assertTrue((novo / "conhecimento" / "demandas").is_dir())
            graph = json.loads((novo / ".obsidian" / "graph.json").read_text(encoding="utf-8"))
            self.assertIn("path:conhecimento/sistemas", [g["query"] for g in graph["colorGroups"]],
                          "o vault é a pasta do contexto: as cores apontam para dentro da base")


    def test_vault_no_contexto_upstream_e_colheita(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "exemplo")
            wt = WorktreeTest()
            ctx_dir = root / "contexts" / "exemplo"
            kb = ctx_dir / "conhecimento"
            nota = kb / "sistemas" / "sistema-b.md"
            nota.write_text(nota.read_text(encoding="utf-8") + "\nSegue a policy [[regra]].\n", encoding="utf-8")
            code, chk = wt.aidw_json(root, "kb", "check", "--json")
            self.assertEqual(chk["errors"], [], "[[regra]] acha policies/regra.md: o vault é a pasta do contexto")
            code, b = wt.aidw_json(root, "kb", "show", "sistema-b", "--json")
            self.assertTrue(b["links"][0]["outside"][0].endswith("policies/regra.md"), b["links"])

            (kb / "conceitos" / "guia.md").write_text(
                "---\ntipo: conceito\nresumo: x\natualizado: 2026-10-07\n---\n\n[[sistema-a]]\n", encoding="utf-8")
            wt.aidw_json(root, "kb", "index", "--json")
            code, chk = wt.aidw_json(root, "kb", "check", "--json")
            self.assertTrue(any("'guia' também existe em shared/guia.md" in w for w in chk["warnings"]), chk)
            self.assertFalse(any("index.md desatualizado" in w for w in chk["warnings"]))
            (kb / "conceitos" / "guia.md").unlink()
            code, chk = wt.aidw_json(root, "kb", "check", "--json")
            self.assertTrue(any("index.md desatualizado" in w for w in chk["warnings"]), chk)
            wt.aidw_json(root, "kb", "index", "--json")
            self.assertIn("[[conhecimento/README|README]]", (kb / "index.md").read_text(encoding="utf-8"))

            guide = tmp / "guideline"
            guide.mkdir()
            for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"],
                         ["commit", "-q", "--allow-empty", "-m", "primeiro"]):
                subprocess.run(["git", "-C", str(guide), *args], check=True)
            first = subprocess.run(["git", "-C", str(guide), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
            toml = ctx_dir / "context.toml"
            toml.write_text(toml.read_text(encoding="utf-8") + f'\n[upstream.guia]\nrepo = "{guide.as_posix()}"\n'
                            f'synced = "{first}"\ncovers = ["shared/guia.md"]\n', encoding="utf-8")
            code, ctx = wt.aidw_json(root, "context", "check", "exemplo", "--json")
            self.assertFalse(any("upstream" in w for w in ctx["warnings"]), "em dia: sem aviso")
            subprocess.run(["git", "-C", str(guide), "commit", "-q", "--allow-empty", "-m", "AutoMapper proibido"], check=True)
            code, ctx = wt.aidw_json(root, "context", "check", "exemplo", "--json")
            self.assertTrue(any("upstream guia" in w and "AutoMapper proibido" in w for w in ctx["warnings"]), ctx)

            wt.aidw_json(root, "demand", "set", "us-9", "--status", "done", "--json")
            demand_dir = root / "contexts" / "exemplo" / "demandas" / "us-9"
            (demand_dir / "aprendizados-us-9.md").write_text("- fato\n", encoding="utf-8")
            code, st = wt.aidw_json(root, "status", "--json")
            self.assertTrue(any("us-9" in a and "/aidw:done" in a for a in st["attention"]), st["attention"])
            (kb / "demandas").mkdir(exist_ok=True)
            (kb / "demandas" / "us-9.md").write_text("---\ntipo: demanda\nresumo: x\n---\n", encoding="utf-8")
            code, st = wt.aidw_json(root, "status", "--json")
            self.assertFalse(any("us-9" in a for a in st["attention"]), "colhida: não avisa mais")


class PluginMigrationTest(unittest.TestCase):
    """O install troca um plugin antigo (ex.: `aidw-<contexto>`) pelo `aidw`, com o CLI simulado."""

    def test_migra_plugin_antigo(self) -> None:
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
            self.assertIn(["plugin", "install", "aidw-mods@aidw-local"], calls, "os mods vão junto")
            manifest = json.loads((root / ".aidw" / "install-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual((manifest["plugins"], manifest["context"]),
                             (["aidw-mods@aidw-local", "aidw@aidw-local"], "exemplo"), "o aidw fica por último")


class CodexInstallTest(unittest.TestCase):
    """install/uninstall --provider codex: só agentes e skills aidw-*; limpa perfil, regras e hooks de installs antigos."""

    def test_install_uninstall_codex(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "exemplo")
            home, skills = tmp / "codex-home", tmp / "agents-skills"
            home.mkdir()
            user_hook = {"hooks": [{"type": "command", "command": "echo meu-hook"}]}
            guard = {"matcher": "apply_patch|Bash|mcp__.*",
                     "hooks": [{"type": "command", "command": f'python "{root.as_posix()}/aidw_guard.py"'}]}
            # sobras de uma instalação antiga: perfil, regras e o grupo do AiDW no hooks.json
            (home / "hooks.json").write_text(json.dumps({"hooks": {"Stop": [user_hook], "PreToolUse": [guard]}}),
                                             encoding="utf-8")
            (home / "aidw.config.toml").write_text("# Gerado por aidw.py install — perfil antigo\n",
                                                   encoding="utf-8")

            proc = run_aidw(root, "install", "--provider", "codex")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue((home / "agents" / "aidw-codificador.toml").is_file())
            orq = (skills / "aidw-go" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("name: aidw-go", orq)
            self.assertIn("$aidw-sair", orq)
            self.assertNotIn("EnterWorktree` com o id", orq, "no Codex não há EnterWorktree")
            self.assertNotIn("AskUserQuestion", orq)
            self.assertNotIn("perfil `aidw`", orq, "no Codex o AiDW não instala perfil")
            self.assertFalse((skills / "aidw-diff").exists(), "no Codex não há EnterWorktree: sem a skill diff")
            self.assertNotIn("## Modo interativo", orq)
            self.assertIn("allow_implicit_invocation: false", (skills / "aidw-go" / "agents" / "openai.yaml").read_text())
            lev = (skills / "aidw-lev" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("name: aidw-lev", lev)
            self.assertIn("`$aidw-go <id>`", lev)
            self.assertNotIn("# WORKFLOW", lev)
            self.assertNotIn("disable-model-invocation", lev)
            self.assertIn("allow_implicit_invocation: false",
                          (skills / "aidw-lev" / "agents" / "openai.yaml").read_text())
            self.assertIn("name: aidw-to-spec", (skills / "aidw-to-spec" / "SKILL.md").read_text(encoding="utf-8"))
            done = (skills / "aidw-done" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("name: aidw-done", done)
            self.assertNotIn("disable-model-invocation", done, "chave do Claude; no Codex vale o openai.yaml")
            self.assertIn("allow_implicit_invocation: false", (skills / "aidw-done" / "agents" / "openai.yaml").read_text())
            self.assertFalse((skills / "aidw-to-spec" / "agents" / "openai.yaml").exists())

            # só agentes e skills: sem regras, sem perfil, e o hooks.json fica só com o que é do usuário
            self.assertFalse((home / "rules" / "aidw.rules").exists(), "o install do Codex não grava regras")
            self.assertFalse((home / "aidw.config.toml").exists(), "o perfil antigo do AiDW sai")
            self.assertEqual(json.loads((home / "hooks.json").read_text(encoding="utf-8")),
                             {"hooks": {"Stop": [user_hook]}}, "sai só o grupo do AiDW; o hook do usuário fica")
            manifest_path = root / ".aidw" / "install-manifest.json"
            written = json.loads(manifest_path.read_text(encoding="utf-8"))["codex"]["files"]
            self.assertTrue(all(Path(k).is_relative_to(home / "agents") or Path(k).is_relative_to(skills) for k in written),
                            "o manifesto do Codex só tem agentes e skills")
            self.assertIn("multi_agent_v2", proc.stdout, "avisa que o spawn_agent precisa de multi_agent_v2")

            again = run_aidw(root, "install", "--provider", "codex")
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
            self.assertIn("0 arquivo(s) mudaram", again.stdout, "idempotente")

            (home / "config.toml").write_text("[features]\nmulti_agent_v2 = true\n", encoding="utf-8")
            quiet = run_aidw(root, "install", "--provider", "codex")
            self.assertNotIn("ligue `multi_agent_v2`", quiet.stdout, "com a feature ligada, sem aviso")

            both = run_aidw(root, "install", "--skip-cli")  # sem --provider: o Codex já instalado é atualizado junto
            self.assertEqual(both.returncode, 0, both.stdout + both.stderr)
            self.assertIn("Instalação global no Codex", both.stdout)
            self.assertIn("codex", json.loads(manifest_path.read_text(encoding="utf-8")),
                          "o install do Claude não apaga o registro do Codex")

            gone = run_aidw(root, "uninstall", "--provider", "codex")
            self.assertEqual(gone.returncode, 0, gone.stdout + gone.stderr)
            self.assertEqual(json.loads((home / "hooks.json").read_text(encoding="utf-8")), {"hooks": {"Stop": [user_hook]}})
            self.assertFalse((home / "agents" / "aidw-codificador.toml").exists())
            self.assertFalse((skills / "aidw-go").exists())
            code = run_aidw(root, "open", "--provider", "codex", "--path", str(tmp), "--print")
            self.assertIn("--enable multi_agent_v2", code.stdout)
            self.assertNotIn("--profile", code.stdout)


class SetupDoctorTest(unittest.TestCase):
    """Setup cria as pastas que faltam; doctor termina com o veredito e o código de saída certo."""

    def test_setup_cria_pastas(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "")
            shutil.rmtree(root / "contexts", ignore_errors=True)
            proc = run_aidw(root, "setup", "--skip-tools")
            for path in (root / "contexts", root / "state", tmp / "wt"):
                self.assertTrue(path.is_dir(), f"setup deveria criar {path}\n{proc.stdout}{proc.stderr}")
            self.assertIn("== Resultado ==", proc.stdout, proc.stderr)
            self.assertIn("em dia com as fontes", proc.stdout, "doctor logo após o apply deve dizer que está em dia")

    def test_doctor_nao_pronto_com_contexto_ausente(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            root = make_sandbox(Path(tmp).resolve(), "claude", "native", "inexistente", copy_context=False)
            proc = run_aidw(root, "doctor")
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("NÃO PRONTO", proc.stdout)
            self.assertIn("contexto 'inexistente' não encontrado", proc.stdout)


if __name__ == "__main__":
    if "--update" in sys.argv:
        sys.argv.remove("--update")
        os.environ["AIDW_UPDATE_GOLDEN"] = "1"
        UPDATE = True
    unittest.main(verbosity=2)
