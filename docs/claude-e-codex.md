# Claude e Codex

O AiDW roda nos dois. O fluxo, os agentes, a tabela de níveis, as policies e o estado da demanda são os mesmos; o que
muda é como cada CLI chama subagentes, muda de pasta, abre o navegador e aplica permissões.

## Comparação

| | Claude Code | Codex |
|---|---|---|
| Instalação | `install` → plugin `aidw` | `install --provider codex` + perfil `aidw`; depois, o `install` atualiza os dois |
| Chamar o orquestrador | `/aidw:orquestrar`, `/aidw:levantamento`, `/aidw:sair`, `/aidw:done` | `$aidw-orquestrar`, `$aidw-levantamento`, `$aidw-sair`, `$aidw-done` |
| Agentes | `aidw:<agente>`, uma variante por modelo e effort | `aidw-<agente>`, modelo e effort em cada `spawn_agent` |
| Modelos | apelidos `opus`, `sonnet`, `haiku` (sempre a versão mais nova) | IDs exatos, pelo tier equivalente, entre os liberados para a conta |
| Workflows (feature, bugfix, refactor, hotfix, `pr-review`, `levantamento`), QA, revisão | ✅ | ✅ |
| Abrir e retomar demanda, modos auto e interativo | ✅ | ✅ |
| Worktree por demanda (inclusive `--pr`) | ✅ | ✅ (o sandbox pede aprovação no `worktree create`) |
| Levar o chat ao worktree | ✅ `change_directory` (app) ou `EnterWorktree` (terminal) | na abertura: `aidw open --provider codex --demand <id>` (terminal) ou `--app` (app desktop); depois, pelo caminho absoluto |
| Pasta do contexto na sessão | ✅ *Session folders* (`request_directory`) | ✅ o perfil `aidw` já libera o AiDW, os projetos e os worktrees |
| Diff de cada repositório | ✅ `/aidw:diff` | — (o app mostra o workspace aberto) |
| Navegador | Claude in Chrome, navegador do app, Playwright | `@Chrome` e `@Browser` (app), Playwright |
| Guard: agente fora do worktree | ✅ hook de `Edit`/`Write` | ✅ hook de `apply_patch` |
| Guard: commit com `AIDW-TESTE` | ✅ hook de `Bash`/`PowerShell` | ✅ hook de `Bash` |
| MCP e ferramentas por agente | ✅ `tools`/`disallowedTools` do subagente | ✅ pelo guard (hook de `mcp__*`): o Codex não limita MCP por agente |
| Lembrete depois de compactação | ✅ hooks do plugin | ✅ `hooks.json` (aprovação no terminal) |
| Regras globais | `~/.claude/settings.json` (merge) | `~/.codex/rules/aidw.rules` |
| Pastas graváveis | as do settings | as do perfil `aidw` (AiDW, projetos, worktrees) |
| Modo projeto (chat na raiz do AiDW) | ✅ `CLAUDE.md` | ✅ `AGENTS.md` |

## Modo native

O padrão. Os agentes são subagentes do próprio CLI:

- **Claude:** a ferramenta `Agent` com o `subagent_type` da tabela. O effort fica fixado no arquivo do subagente, daí
  as variantes (`codificador-high`, `codificador-sonnet-high`). O `omitClaudeMd` impede que o agente carregue as regras
  do orquestrador. As ferramentas e os MCPs de cada papel ficam no próprio subagente.
- **Codex:** `spawn_agent` com modelo e effort, que exige `multi_agent_v2` (ligado pelo perfil `aidw` e pelo `chat`).
  Os agentes ficam em `~/.codex/agents/aidw-<agente>.toml`. O Codex não limita MCP por agente: um `mcp_servers`
  parcial invalida o arquivo do agente, e `disabled_tools` nele não bloqueia a ferramenta (conferido no Codex 0.157).
  Por isso o guard recebe toda chamada MCP de um agente do AiDW e recusa o que não é do papel dele, pela política que o
  `apply` grava em `.aidw/runtime.json`. Os MCPs do próprio Codex (ex.: `node_repl`) não são julgados. Os hooks rodam
  dentro dos subagentes, e o payload traz `agent_type` (`aidw-<agente>`), `agent_id`, `tool_name` e `cwd`: conferido
  com um `aidw-explorador` real, que teve a chamada MCP bloqueada e o shell liberado.

Depois de cada subagente, o orquestrador roda `aidw.py record` com os números reais (no Codex, `--codex-task` lê o
consumo da sessão).

## Modo headless

`[delegation] mode = "headless"`: um processo por tarefa pelo `aidw.py delegate`, com `claude -p --agents … --agent
<nome>` ou `codex exec` com a definição no stdin (lá, os MCPs do papel e as ferramentas bloqueadas vão por `-c`). As
ações travadas voltam como `denials`. Serve para automação; o plugin exige o native.

## Navegador

- **Claude:** Claude in Chrome (o seu Chrome, já logado) ou o navegador do app desktop; Playwright pelo MCP.
- **Codex:** no app desktop, `@Chrome` (a extensão do Codex no seu Chrome, já logado) e `@Browser` (o navegador do
  app, para páginas locais e públicas, com perfil próprio); no CLI, o Playwright pelo MCP.
- O QA usa o que tiver; se o subagente não conseguir usar nenhum, devolve o critério ao orquestrador, que testa no
  navegador dele e debate o resultado com você (*Testes* em [fluxo.md](fluxo.md)).

## Limites do Codex

- Não há ferramenta para mudar a pasta da sessão nem acrescentar uma no meio da conversa: o `/aidw:diff` e as
  *Session folders* não existem lá. O `aidw open --provider codex` abre já no worktree (com `--app`, no app desktop).
- Os worktrees que o app do Codex cria são dele (`$CODEX_HOME/worktrees`); os da demanda são do AiDW e abrem pelo
  `aidw open`.
- O sandbox deixa o `.git` só leitura: o `worktree create` pede aprovação e os agentes não fazem commit (você faz).
- Hooks: o Codex só roda hook aprovado, e qualquer mudança no grupo (comando ou matcher) pede nova aprovação. Aprove
  no terminal (`codex --profile aidw` → "Trust all and continue"); aberto com o perfil, o Codex grava a aprovação no
  próprio `aidw.config.toml`, e o `install` mantém essa parte quando regenera o perfil. O `doctor` lê o `config.toml` e
  o perfil e avisa quando falta aprovar.
- No Windows, o AiDW libera `safe.directory` só para as pastas do AiDW, dos projetos e dos worktrees, por variáveis
  `GIT_CONFIG_*`, sem tocar no `.gitconfig`.
- Se o `node` do PATH mora no perfil do usuário (ex.: nvm), o sandbox não o lê: o `install --provider codex` põe um
  Node de fora do perfil na frente do PATH do perfil `aidw`.

## O que é gerado

Nada disso é versionado.

| Arquivo | Gerado por | Conteúdo |
|---|---|---|
| `.aidw/marketplace/plugins/aidw/` | `install` | O plugin: agentes e variantes, skills, `orquestrar`/`sair`/`diff`, referências, hooks |
| `.aidw/install-manifest.json` | `install` | O que o install acrescentou no Claude e no Codex (para o `uninstall` remover só isso) |
| `~/.claude/settings.json` (merge) | `install` | Regras `deny`/`ask`/`allow`, pastas liberadas e `env`, só os itens do AiDW |
| `~/.codex/agents/aidw-*.toml`, `~/.agents/skills/aidw-*`, `~/.codex/rules/aidw.rules`, `~/.codex/hooks.json` (merge), `~/.codex/aidw.config.toml` | `install --provider codex` | Agentes, skills, regras, hooks e o perfil `aidw` |
| `state/worktrees.json`, `state/sessions.json` | comandos e hooks | Registro dos worktrees e das sessões no modo orquestrador |
| `.aidw/agents/<nome>.md`, `.aidw/reference/`, `.aidw/runtime.json` | `apply` | Definição de cada agente, referências do orquestrador, configuração resolvida (inclusive a política de MCP por agente que o guard aplica) |
| `CLAUDE.md`, `.claude/agents/`, `.claude/settings.local.json`, `.claude/skills/`, `.mcp.json` | `apply` (Claude) | O modo projeto do Claude |
| `AGENTS.md`, `.codex/config.toml`, `.codex/agents/`, `.codex/rules/aidw.rules`, `.agents/skills/` | `apply` (Codex) | O modo projeto do Codex |

Garantias: valida tudo antes de gravar; sem mudança, nenhuma escrita; remove só o que foi gerado pelo AiDW; um arquivo
gerado alterado à mão faz o `install` parar (a não ser com `--force`).
