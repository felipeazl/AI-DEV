# Claude e Codex

O AiDW roda nos dois. O fluxo, os agentes, a tabela de níveis e as proteções são os mesmos; o que muda é como cada
CLI chama subagentes, muda de pasta e aplica permissões.

## Comparação

| | Claude Code | Codex CLI |
|---|---|---|
| Instalação | `install` → plugin `aidw` | `install --provider codex` + perfil `aidw` |
| Chamar o orquestrador | `/aidw:orquestrar`, `/aidw:sair`, `/aidw:done` | `$aidw-orquestrar`, `$aidw-sair`, `$aidw-done` |
| Agentes | `aidw:<agente>`, uma variante por modelo e effort | `aidw-<agente>`, modelo e effort em cada `spawn_agent` |
| Modelos | apelidos `opus`, `sonnet`, `haiku` (sempre a versão mais nova) | IDs exatos, pelo tier equivalente, entre os liberados para a conta |
| Abrir e retomar demanda | ✅ | ✅ |
| Levar o chat ao worktree | ✅ `change_directory` (app) ou `EnterWorktree` (terminal) | pelo caminho absoluto; `aidw open --provider codex --demand <id>` abre o Codex nele |
| Diff de cada repositório | ✅ `/aidw:diff` | — |
| Guard e lembrete depois de compactação | ✅ hooks do plugin | ✅ `hooks.json` (aprovação única no terminal) |
| Regras globais | `~/.claude/settings.json` (merge) | `~/.codex/rules/aidw.rules` |
| Pastas graváveis | as do settings | as do perfil `aidw` (AiDW, projetos, worktrees) |
| Modo projeto (chat na raiz do AiDW) | ✅ `CLAUDE.md` | ✅ `AGENTS.md` |

## Modo native

O padrão. Os agentes são subagentes do próprio CLI:

- **Claude:** a ferramenta `Agent` com o `subagent_type` da tabela. O effort fica fixado no arquivo do subagente, daí
  as variantes (`codificador-high`, `codificador-sonnet-high`). O `omitClaudeMd` impede que o agente carregue as regras
  do orquestrador.
- **Codex:** `spawn_agent` com modelo e effort, que exige `multi_agent_v2` (ligado pelo `.codex/config.toml` e pelo
  `chat`). O subagente recebe a definição pelo arquivo `.aidw/agents/<nome>.md`.

Depois de cada subagente, o orquestrador roda `aidw.py record` com os números reais (no Codex, `--codex-task` lê o
consumo da sessão).

## Modo headless

`[delegation] mode = "headless"`: um processo por tarefa pelo `aidw.py delegate`, com `claude -p --agents … --agent
<nome>` ou `codex exec` com a definição no stdin. As ações travadas voltam como `denials`. Serve para automação; o
plugin exige o native.

## Limites do Codex

- O sandbox deixa o `.git` só leitura: o `worktree create` pede aprovação e os agentes não fazem commit (você faz).
- O app desktop do Codex não aprova hooks: aprove uma vez no terminal (`codex --profile aidw` → "Trust all and
  continue"). O `doctor` mostra se falta.
- No Windows, o AiDW libera `safe.directory` só para as pastas do AiDW, dos projetos e dos worktrees, por variáveis
  `GIT_CONFIG_*`, sem tocar no `.gitconfig`.
- Se o `node` do PATH mora no perfil do usuário (ex.: nvm), o sandbox não o lê: o `install --provider codex` põe um
  Node de fora do perfil na frente do PATH do perfil `aidw`.

## O que é gerado

Nada disso é versionado.

| Arquivo | Gerado por | Conteúdo |
|---|---|---|
| `.aidw/marketplace/plugins/aidw/` | `install` | O plugin: agentes e variantes, skills, `orquestrar`/`sair`/`diff`, referências, hooks |
| `.aidw/install-manifest.json` | `install` | O que o install acrescentou (para o `uninstall` remover só isso) |
| `~/.claude/settings.json` (merge) | `install` | Regras `deny`/`ask`/`allow`, pastas liberadas e `env`, só os itens do AiDW |
| `state/worktrees.json`, `state/sessions.json` | comandos e hooks | Registro dos worktrees e das sessões no modo orquestrador |
| `.aidw/agents/<nome>.md`, `.aidw/reference/`, `.aidw/runtime.json` | `apply` | Definição de cada agente, referências do orquestrador, configuração resolvida |
| `CLAUDE.md`, `.claude/agents/`, `.claude/settings.local.json`, `.claude/skills/`, `.mcp.json` | `apply` (Claude) | O modo projeto do Claude |
| `AGENTS.md`, `.codex/config.toml`, `.codex/agents/`, `.codex/rules/aidw.rules`, `.agents/skills/` | `apply` (Codex) | O modo projeto do Codex |

Garantias: valida tudo antes de gravar; sem mudança, nenhuma escrita; remove só o que foi gerado pelo AiDW; um arquivo
gerado alterado à mão faz o `install` parar (a não ser com `--force`).
