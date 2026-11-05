# Claude Code e Codex

O AiDW é um plugin de desenvolvimento agêntico **para o Claude Code**. O Claude Code é a plataforma principal: é nele que
o AiDW roda inteiro, e é para ele que se escreve toda funcionalidade nova.

> **No Codex, o AiDW é só agentes e skills.** O `install --provider codex` entrega os agentes `aidw-*` e as skills
> `aidw-*` e mais nada: **sem regras de permissão, sem hooks (guard), sem perfil, sem MCP por agente e sem mods.** O
> fluxo da demanda roda pelos agentes e pelas skills, mas a proteção e a configuração ficam com o seu Codex. Para
> trabalho de verdade, use o Claude Code.

## Comparação

| | Claude Code | Codex |
|---|---|---|
| O que o `install` entrega | o plugin `aidw` (agentes e variantes, skills, comandos, hooks), o plugin `aidw-mods` e as regras do AiDW no `~/.claude/settings.json` | **só** os agentes `aidw-*` (`~/.codex/agents/aidw-<nome>.toml`) e as skills `aidw-*` (`~/.agents/skills`) |
| Chamar o orquestrador | `/aidw:go`, `/aidw:survey`, `/aidw:exit`, `/aidw:done` | `$aidw-go`, `$aidw-survey`, `$aidw-exit`, `$aidw-done` |
| Comandos do usuário | só `go`, `survey`, `exit`, `diff`, `done`, `knowledge`, `context` no menu `/`; as skills de fluxo ficam ocultas (`user-invocable: false`) | toda skill `$aidw-*` aparece (o Codex não esconde skill); `go`, `survey`, `exit` e `done` só rodam quando chamadas (`agents/openai.yaml`) |
| Agentes | `aidw:<nome>`, mais uma variante por exceção (modelo e effort fixos) | `aidw-<nome>`, mais um papel por exceção (`aidw-<nome>-<effort>`), com o modelo e o effort fixados em cada TOML |
| Modelos | apelidos `opus`, `sonnet`, `haiku` (sempre a versão mais nova) | IDs exatos, pelo tier equivalente, entre os liberados para a conta |
| Workflows (`development`, `pr-review`, `survey`), QA, revisão | ✅ | ✅ (pelas skills) |
| Abrir e retomar demanda | ✅ | ✅ |
| Worktree por demanda (inclusive `--pr`) | ✅ | ✅ (o sandbox pede aprovação no `worktree create`) |
| Regras de permissão do AiDW (force push, `reset --hard`, `.env`; a lista `ask` do contexto) | ✅ `~/.claude/settings.json` | — as do seu Codex (sandbox e aprovações dele) |
| Guard: agente fora do worktree, commit com `AIDW-TEST` | ✅ hooks do plugin | — |
| MCP e ferramentas limitados por agente | ✅ `tools`/`disallowedTools` do subagente | — todo agente vê os MCPs do seu `~/.codex/config.toml` |
| Lembrete depois de compactação, registro do modo orquestrador | ✅ hooks do plugin | — |
| Mods: faixa e painéis, métricas sozinhas, travas da delegação, filtro de segredos | ✅ `aidw-mods` | — o orquestrador roda o `record` |
| Levar o chat ao worktree, painel de diff (`/aidw:diff`), pastas da sessão | ✅ | — (`aidw open --provider codex --demand <id>` abre já no worktree) |
| Navegador | Claude in Chrome, navegador do app, Playwright | `@Chrome` e `@Browser` (app), Playwright (se estiver no seu Codex) |
| Modo projeto (chat na raiz do AiDW) | ✅ `CLAUDE.md` | ✅ `AGENTS.md` (gerado pelo `apply`) |

### Regra para funcionalidade nova

Toda funcionalidade nova nasce no Claude Code. Ela vai para o Codex só se couber num agente ou numa skill, sem precisar
de recurso de sessão, de interface, de hook ou de configuração do Codex. Quando não couber, entra na tabela acima e o
Codex segue sem ela: não se cria um equivalente parcial só para manter paridade.

## Usar o AiDW no Codex

```powershell
python aidw.py install --provider codex              # agentes e skills aidw-*
python aidw.py open --provider codex --demand 1234   # a sessão no worktree da demanda
```

- **`multi_agent_v2`:** o orquestrador chama os agentes com `spawn_agent`, que precisa dessa feature. O
  `aidw open --provider codex` passa `--enable multi_agent_v2`; abrindo o Codex de outro jeito, ligue no seu
  `~/.codex/config.toml` (`[features]` → `multi_agent_v2 = true`). O `install` e o `doctor` avisam quando falta.
- **Pastas:** o `aidw open` inicia o Codex no worktree da demanda (`-C`) e acrescenta a pasta do AiDW (`--add-dir`),
  onde ficam os artefatos da demanda. Escrever em qualquer outra pasta pede a aprovação do sandbox.
- **Worktree:** o `worktree create` grava no `.git` do repositório, que o sandbox do Codex deixa só leitura: aprove esse
  comando. Os agentes não fazem commit (você faz).
- **Proteção:** sem as regras e os hooks do AiDW, valem só as aprovações do Codex. Confira com cuidado commit, push, SQL
  de escrita e toda ação travada antes de aprovar.
- **MCPs:** os agentes usam os MCPs que você registrou no Codex (`codex mcp add …`), sem limite por agente.
- **Métricas:** o orquestrador roda `aidw.py record --codex-task <task_name>`, que lê o consumo real da sessão do
  subagente.

### Agentes e effort

Como no Claude, cada variante é um papel próprio: `~/.codex/agents/aidw-<nome>.toml` é o padrão e
`aidw-<nome>-<effort>.toml` (ou `aidw-<nome>-<modelo>-<effort>.toml`) cada exceção, todos com o modelo (`model`, o
equivalente do tier no Codex) e o effort (`model_reasoning_effort`) fixados, mais as instruções do agente. O orquestrador
chama o papel que está na célula da tabela *Agents and effort* e nunca passa `model` nem `reasoning_effort` (outro
modelo só quando você pede). O orquestrador do modo projeto (`aidw.py chat`) abre com o modelo e o effort configurados
para ele.

### Instalação antiga

Instalações anteriores punham no Codex o perfil `aidw` (`~/.codex/aidw.config.toml`), as regras
(`~/.codex/rules/aidw.rules`) e hooks do AiDW no `~/.codex/hooks.json`. O `install --provider codex` de hoje remove os
três (no `hooks.json`, só os grupos do AiDW), e o `doctor` avisa se sobrou algum.

## Modo native

O padrão (`[delegation] mode = "native"`). Os agentes são subagentes do próprio CLI:

- **Claude:** a ferramenta `Agent` com o `subagent_type` da tabela. O modelo e o effort ficam fixados no arquivo do
  subagente, daí as variantes (`aidw:coder-medium`, `aidw:explorer-sonnet-high`). O `omitClaudeMd` impede que o agente
  carregue as regras do orquestrador. As ferramentas e os MCPs de cada papel ficam no próprio subagente.
- **Codex:** `spawn_agent` com o tipo de agente da tabela (`aidw-coder`, `aidw-coder-medium`…), que exige `multi_agent_v2`.

Depois de cada subagente, a métrica vai para o `metrics.md`: no Claude o mod `aidw-mods` grava sozinho (sem ele, o
orquestrador roda `aidw.py record`); no Codex o orquestrador roda `record --codex-task`.

## Modo headless

`[delegation] mode = "headless"`, só no modo projeto: um processo por tarefa pelo `aidw.py delegate`, com
`claude -p --agents … --agent <nome>` ou `codex exec` com a definição no stdin (lá, os MCPs do papel e as ferramentas
bloqueadas vão por `-c`). As ações travadas voltam como `denials`. Serve para automação; o plugin exige o native.

## Navegador

- **Claude:** Claude in Chrome (o seu Chrome, já logado) ou o navegador do app desktop; Playwright pelo MCP.
- **Codex:** no app desktop, `@Chrome` (a extensão do Codex no seu Chrome, logado) e `@Browser` (o navegador do app,
  para páginas locais e públicas); no CLI, o Playwright, se estiver no seu Codex.
- O qa usa o que tiver; se o subagente não conseguir usar nenhum, devolve o critério ao orquestrador, que testa no
  navegador dele e debate o resultado com você.

## Limites do Codex

Além do que é exclusivo do Claude Code (acima):

- Não há ferramenta para mudar a pasta da sessão nem acrescentar uma no meio da conversa: o `/aidw:diff` e as pastas da
  sessão não existem lá. O `aidw open --provider codex` abre já no worktree (com `--app`, no app desktop).
- Os worktrees que o app do Codex cria são dele (`$CODEX_HOME/worktrees`); os da demanda são do AiDW e abrem pelo
  `aidw open`.
- Se o `node` do PATH mora no perfil do usuário (ex.: nvm), o sandbox do Codex não o lê: instale o Node fora do perfil
  (ex.: em Program Files) para os builds.

## O que é gerado

Nada disso é versionado.

| Arquivo | Gerado por | Conteúdo |
|---|---|---|
| `.aidw/marketplace/plugins/aidw/` | `install` | O plugin: agentes e variantes, skills, `go`/`survey`/`exit`/`diff`, referências, hooks |
| `.aidw/marketplace/plugins/aidw-mods/` | `install` | Os mods do Claude Code, copiados de `mods/aidw-mods` (sem os testes) com a raiz do AiDW desta máquina |
| `.aidw/install-manifest.json` | `install` | O que o install acrescentou no Claude e no Codex (para o `uninstall` remover só isso) |
| `~/.claude/settings.json` (merge) | `install` | Regras `deny`/`ask`/`allow`, pastas liberadas e `env`, só os itens do AiDW |
| `~/.codex/agents/aidw-*.toml`, `~/.agents/skills/aidw-*` | `install --provider codex` | Agentes e skills — e só isso |
| `state/worktrees.json`, `state/sessions.json` | comandos e hooks | O registro dos worktrees e das sessões no modo orquestrador |
| `.aidw/agents/<nome>.md`, `.aidw/reference/`, `.aidw/runtime.json` | `apply` | A definição de cada agente, as referências do orquestrador, a configuração resolvida |
| `CLAUDE.md`, `.claude/agents/`, `.claude/settings.local.json`, `.claude/skills/`, `.mcp.json` | `apply` (Claude) | O modo projeto do Claude |
| `AGENTS.md`, `.codex/config.toml`, `.codex/agents/`, `.codex/rules/aidw.rules`, `.agents/skills/` | `apply` (Codex) | O modo projeto do Codex (só com `provider = "codex"`, na raiz do AiDW) |

Garantias: tudo é validado antes de gravar; sem mudança, nada é gravado; só arquivos gerados pelo AiDW são removidos; um
arquivo gerado editado à mão faz o `install` parar (a não ser com `--force`).
