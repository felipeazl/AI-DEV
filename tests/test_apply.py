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
SOURCES = ["aidw.py", "aidw_guard.py", "config", "agents", "skills", "orchestrator", "workflows"]
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
            orq = files[f"{base}/skills/orquestrar/SKILL.md"].decode("utf-8")
            self.assertIn("disable-model-invocation: true", orq)
            self.assertIn("`aidw:codificador", orq, "tabela de effort com o nome do plugin")
            self.assertIn(f'python "{root.as_posix()}/aidw.py" record', orq, "aidw.py por caminho absoluto")
            self.assertIn(f"{(root / '.aidw' / 'marketplace' / base / 'reference').as_posix()}/etapa.md", orq)
            self.assertIn("[AiDW]", files[f"{base}/agents/codificador.md"].decode("utf-8"))
            self.assertIn("[AiDW]", files[f"{base}/skills/skill-exemplo/SKILL.md"].decode("utf-8"))
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
            self.assertEqual(path, tmp / "wt" / "Aplicação" / "us-1")
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
            self.assertEqual(Path(hook.strip()), tmp / "wt" / "Outro" / "us-7", "o hook não pode levar a outro repositório")

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

            hook = lambda payload: subprocess.run([sys.executable, str(root / "aidw_guard.py")],  # noqa: E731
                                                  input=json.dumps(payload), capture_output=True, text=True,
                                                  encoding="utf-8", timeout=30).stdout
            base = {"session_id": "s1", "cwd": str(tmp)}
            self.assertEqual(hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "oi, tudo bem?"}), "")
            self.assertFalse((root / "state" / "sessions.json").exists(), "mensagem comum não grava nada")
            self.assertEqual(hook({**base, "hook_event_name": "SessionStart", "source": "compact"}), "")
            hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "/aidw:orquestrar us-5 continuar"})
            out = json.loads(hook({**base, "hook_event_name": "SessionStart", "source": "compact"}))
            ctx = out["hookSpecificOutput"]["additionalContext"]
            self.assertIn("modo orquestrador", ctx)
            self.assertIn("aidw/skills/orquestrar/SKILL.md", ctx)
            self.assertIn("us-5 continuar", ctx)
            self.assertLess(len(ctx.encode()), 2000, "o hook só injeta ~2 KB")
            self.assertEqual(hook({"session_id": "s2", "hook_event_name": "SessionStart", "source": "compact"}), "")
            hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "/aidw:sair"})
            cx = {"session_id": "c1", "cwd": str(tmp)}
            hook({**cx, "hook_event_name": "UserPromptSubmit", "prompt": "$aidw-orquestrar us-7"})
            out = json.loads(hook({**cx, "hook_event_name": "SessionStart", "source": "compact"}))
            ctx_codex = out["hookSpecificOutput"]["additionalContext"]
            self.assertIn("aidw-orquestrar/SKILL.md", ctx_codex)
            self.assertIn("$aidw-sair", ctx_codex)
            self.assertEqual(hook({**base, "hook_event_name": "SessionStart", "source": "resume"}), "")


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
            orq = files["plugins/aidw/skills/orquestrar/SKILL.md"].decode("utf-8")
            for step in ("project detect --json", "demand list --active --json", "não recomece",
                         "demand set <id> --step <AÇÃO>", "EnterWorktree"):
                self.assertIn(step, orq)
            self.assertLess(orq.index("Ao ser chamado"), orq.index("# ROLE"), "o protocolo vem antes do resto")
            sair = files["plugins/aidw/skills/sair/SKILL.md"].decode("utf-8")
            self.assertIn("--status paused", sair)
            self.assertIn("disable-model-invocation: true", sair)


class ContextTest(unittest.TestCase):
    """aidw.py context list / check / create / use (skills contexto-listar, contexto-usar, contexto-criar)."""

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
            manifest = json.loads((root / ".aidw" / "install-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual((manifest["plugins"], manifest["context"]), (["aidw@aidw-local"], "exemplo"))


class CodexInstallTest(unittest.TestCase):
    """install/uninstall --provider codex: arquivos aidw-*, perfil aidw, hooks.json por merge, confiança preservada."""

    def test_install_uninstall_codex(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "exemplo")
            home, skills = tmp / "codex-home", tmp / "agents-skills"
            home.mkdir()
            user_hook = {"hooks": [{"type": "command", "command": "echo meu-hook"}]}
            (home / "hooks.json").write_text(json.dumps({"hooks": {"Stop": [user_hook]}}), encoding="utf-8")

            proc = run_aidw(root, "install", "--provider", "codex")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue((home / "agents" / "aidw-codificador.toml").is_file())
            orq = (skills / "aidw-orquestrar" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("name: aidw-orquestrar", orq)
            self.assertIn("$aidw-sair", orq)
            self.assertNotIn("EnterWorktree` com o id", orq, "no Codex não há EnterWorktree")
            self.assertIn("allow_implicit_invocation: false", (skills / "aidw-orquestrar" / "agents" / "openai.yaml").read_text())
            self.assertIn("name: aidw-to-spec", (skills / "aidw-to-spec" / "SKILL.md").read_text(encoding="utf-8"))
            self.assertIn("forbidden", (home / "rules" / "aidw.rules").read_text(encoding="utf-8"))
            profile = (home / "aidw.config.toml").read_text(encoding="utf-8")
            self.assertIn("multi_agent_v2 = true", profile)
            self.assertIn(str(tmp / "wt").replace("\\", "\\\\"), profile, "raiz dos worktrees gravável no perfil")
            hooks = json.loads((home / "hooks.json").read_text(encoding="utf-8"))["hooks"]
            self.assertEqual(hooks["Stop"], [user_hook], "o hook do usuário fica")
            self.assertEqual(hooks["PreToolUse"][0]["matcher"], "apply_patch")

            before = (home / "hooks.json").read_text(encoding="utf-8")
            again = run_aidw(root, "install", "--provider", "codex")
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
            self.assertEqual((home / "hooks.json").read_text(encoding="utf-8"), before, "hooks.json idempotente")

            # confiança: o Codex grava no config.toml do usuário (nunca no perfil); o AiDW não toca nele
            os.environ["CODEX_HOME"], os.environ["AIDW_CODEX_SKILLS_DIR"] = str(home), str(skills)
            try:
                aidw = load_aidw(root)
            finally:
                os.environ.pop("CODEX_HOME"), os.environ.pop("AIDW_CODEX_SKILLS_DIR")
            keys = aidw.aidw_hook_keys()
            self.assertEqual(len(keys), 3)
            self.assertIsNotNone(aidw.codex_hooks_trusted())
            self.assertFalse(aidw.codex_hooks_trusted(), "sem confiança gravada")
            trust = lambda h: "\n".join(f"[hooks.state.{json.dumps(k)}]\ntrusted_hash = {json.dumps(h)}\n"  # noqa: E731
                                        for k in keys)
            (home / "config.toml").write_text(trust("sha256:abc"), encoding="utf-8")
            self.assertTrue(aidw.codex_hooks_trusted())
            manifest_path = root / ".aidw" / "install-manifest.json"
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            m["codex"]["hooks_signature"] = "assinatura-antiga"  # como se os hooks tivessem mudado neste install
            manifest_path.write_text(json.dumps(m), encoding="utf-8")
            self.assertEqual(run_aidw(root, "install", "--provider", "codex").returncode, 0)
            self.assertFalse(aidw.codex_hooks_trusted(), "hash de antes da mudança não vale mais")
            (home / "config.toml").write_text(trust("sha256:novo"), encoding="utf-8")  # o usuário reaprovou
            self.assertTrue(aidw.codex_hooks_trusted())
            self.assertIn("sha256:novo", (home / "config.toml").read_text(encoding="utf-8"), "config.toml intocado")

            gone = run_aidw(root, "uninstall", "--provider", "codex")
            self.assertEqual(gone.returncode, 0, gone.stdout + gone.stderr)
            self.assertEqual(json.loads((home / "hooks.json").read_text(encoding="utf-8")), {"hooks": {"Stop": [user_hook]}})
            self.assertFalse((home / "aidw.config.toml").exists())
            self.assertFalse((home / "agents" / "aidw-codificador.toml").exists())
            self.assertFalse((skills / "aidw-orquestrar").exists())
            code = run_aidw(root, "open", "--provider", "codex", "--path", str(tmp), "--print")
            self.assertIn("--profile aidw", code.stdout)


class CodexNodeTest(unittest.TestCase):
    """O sandbox do Codex não lê o perfil do usuário: um node do PATH que mora lá (nvm) é trocado por um de fora."""

    def test_node_fora_do_perfil(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aidw-test-", ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp).resolve()
            root = make_sandbox(tmp, "claude", "native", "")
            aidw = load_aidw(root)
            home, pf = tmp / "home", tmp / "pf"
            for d in (home / "nvm", pf):
                d.mkdir(parents=True)
                (d / "node.exe").write_bytes(b"")
            aidw.Path.home = staticmethod(lambda: home)
            old_path = os.environ["PATH"]
            try:
                os.environ["PATH"] = os.pathsep.join([str(home / "nvm"), str(pf)])
                self.assertEqual(aidw.codex_node_path()[0], str(pf))
                os.environ["PATH"] = str(home / "nvm")
                node_dir, note = aidw.codex_node_path()
                self.assertIsNone(node_dir)
                self.assertIn("instale um Node", note)
                os.environ["PATH"] = str(pf)
                self.assertEqual(aidw.codex_node_path(), (None, ""), "node fora do perfil: nada a fazer")
            finally:
                os.environ["PATH"] = old_path


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
