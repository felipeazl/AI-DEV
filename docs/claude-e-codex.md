# Claude e Codex

O AiDW é um plugin de desenvolvimento agêntico **para o Claude Code**. O Claude Code é a plataforma principal: é nele que
o AiDW roda inteiro e é para ele que se escreve toda funcionalidade nova.

> **No Codex, o AiDW é só agentes e skills.** O `install --provider codex` copia os agentes `aidw-*` e as skills
> `aidw-*` e mais nada: **sem regras de permissão, sem hooks (guard), sem perfil `aidw`, sem MCP por agente e sem mods.**
> O fluxo da demanda roda pelos agentes e pelas skills, mas as proteções e a configuração ficam com o seu Codex. A
> paridade entre os dois será revista depois; até lá, para trabalho de verdade, use o Claude Code.

## Comparação

| | Claude Code | Codex |
|---|---|---|
| O que o `install` instala | plugin `aidw` (agentes, skills, comandos, hooks), plugin `aidw-mods` e as regras do AiDW no `~/.claude/settings.json` | **só** agentes `aidw-*` (`~/.codex/agents`) e skills `aidw-*` (`~/.agents/skills`) |
| Chamar o orquestrador | `/aidw:orquestrar`, `/aidw:levantamento`, `/aidw:sair`, `/aidw:done` | `$aidw-orquestrar`, `$aidw-levantamento`, `$aidw-sair`, `$aidw-done` |
| Agentes | `aidw:<agente>`, uma variante por modelo e effort | `aidw-<agente>`, modelo e effort em cada `spawn_agent` |
| Modelos | apelidos `opus`, `sonnet`, `haiku` (sempre a versão mais nova) | IDs exatos, pelo tier equivalente, entre os liberados para a conta |
| Workflows (feature, bugfix, refactor, hotfix, `pr-review`, `levantamento`), QA, revisão | ✅ | ✅ (pelas skills) |
| Abrir e retomar demanda, modos auto e interativo | ✅ | ✅ |
| Worktree por demanda (inclusive `--pr`) | ✅ | ✅ (o sandbox pede aprovação no `worktree create`) |
| Regras de permissão do AiDW (force push, `reset --hard`, `.env`, commit/push/SQL pedem OK) | ✅ `~/.claude/settings.json` | — as do seu Codex (sandbox e aprovações dele) |
| Guard: agente fora do worktree, commit com `AIDW-TESTE` | ✅ hooks do plugin | — |
| MCP e ferramentas limitados por agente | ✅ `tools`/`disallowedTools` do subagente | — o agente vê os MCPs do seu `~/.codex/config.toml` |
| Lembrete depois de compactação, registro do modo orquestrador | ✅ hooks do plugin | — |
| Mods: faixa e painel da demanda, métricas sozinhas, travas da delegação, avisos, filtro de segredos | ✅ `aidw-mods` | — o orquestrador roda `record` à mão |
| Levar o chat ao worktree, painel de diff (`/aidw:diff`), *Session folders* | ✅ | — (`aidw open --provider codex --demand <id>` abre já no worktree) |
| Navegador | Claude in Chrome, navegador do app, Playwright | `@Chrome` e `@Browser` (app), Playwright (se estiver no seu Codex) |
| Modo projeto (chat na raiz do AiDW) | ✅ `CLAUDE.md` | ✅ `AGENTS.md` (gerado pelo `apply`) |

## O que é exclusivo do Claude Code

| Recurso | Por quê |
|---|---|
| Plugin `aidw` (marketplace, comandos `/aidw:*`, instalação em qualquer pasta) | o formato de plugin é do Claude Code |
| Regras de permissão e hooks do AiDW (guard, `AIDW-TESTE`, registro do modo orquestrador) | instalados só no Claude Code |
| **Mods** (`aidw-mods`): faixa e painel da demanda (com abas por uso), métricas sozinhas, travas da delegação, avisos, filtro de segredos | plugins de *function hooks* do Claude Code ([mods.md](mods.md)) |
| Painel de diff por repositório (`/aidw:diff`) e levar o chat ao worktree no meio da conversa | `change_directory` / `EnterWorktree` |
| *Session folders* (pasta do contexto aberta no app) | `request_directory` |
| Effort fixado por variante de agente e ferramentas/MCPs limitados no próprio subagente | subagentes do Claude Code |
| Navegador do app e Claude in Chrome | integrações do Claude |

### Regra para funcionalidade nova

Toda funcionalidade nova nasce no Claude Code. Ela vai para o Codex só se couber num agente ou numa skill, sem precisar
de recurso de sessão, de interface, de hook ou de configuração do Codex. Quando não couber, entra na tabela acima e o
Codex segue sem ela: não se cria um equivalente parcial só para manter paridade.

## Usar o AiDW no Codex

```powershell
python aidw.py install --provider codex          # agentes e skills aidw-*
python aidw.py open --provider codex --demand 1234
```

- **`multi_agent_v2`:** o orquestrador chama os agentes com `spawn_agent`, que precisa dessa feature. O `aidw open
  --provider codex` já passa `--enable multi_agent_v2`; abrindo o Codex de outro jeito, ligue no seu
  `~/.codex/config.toml` (`[features]` → `multi_agent_v2 = true`). O `install` e o `doctor` avisam quando falta.
- **Pastas:** o `aidw open` abre no worktree e libera a pasta do AiDW (`--add-dir`), onde ficam os artefatos da demanda.
  Escrever em qualquer outra pasta pede a aprovação do sandbox do Codex.
- **Proteções:** sem as regras e os hooks do AiDW, valem só as aprovações do Codex. Confira com cuidado commit, push,
  SQL de escrita e qualquer ação travada antes de aprovar.
- **MCPs:** os agentes usam os MCPs que você registrou no Codex (`codex mcp add …`), sem limite por agente.
- **Métricas:** o orquestrador roda `aidw.py record --codex-task <t>`, que lê o consumo real da sessão do subagente.

### Instalação antiga

Instalações anteriores punham no Codex o perfil `aidw` (`~/.codex/aidw.config.toml`), as regras
(`~/.codex/rules/aidw.rules`) e os hooks do AiDW no `~/.codex/hooks.json`. O `install --provider codex` de hoje remove
os três (no `hooks.json`, só os grupos do AiDW), e o `doctor` avisa se sobrou algum.

## Modo native

O padrão. Os agentes são subagentes do próprio CLI:

- **Claude:** a ferramenta `Agent` com o `subagent_type` da tabela. O effort fica fixado no arquivo do subagente, daí
  as variantes (`codificador-high`, `codificador-sonnet-high`). O `omitClaudeMd` impede que o agente carregue as regras
  do orquestrador. As ferramentas e os MCPs de cada papel ficam no próprio subagente.
- **Codex:** `spawn_agent` com modelo e effort, que exige `multi_agent_v2`. Os agentes ficam em
  `~/.codex/agents/aidw-<agente>.toml`.

Depois de cada subagente, a métrica vai para o `metricas.md`: no Claude, o mod `aidw-mods` grava sozinho (sem ele, o
orquestrador roda `aidw.py record`); no Codex, o orquestrador roda `record --codex-task`.

## Modo headless

`[delegation] mode = "headless"`: um processo por tarefa pelo `aidw.py delegate`, com `claude -p --agents … --agent
<nome>` ou `codex exec` com a definição no stdin (lá, os MCPs do papel e as ferramentas bloqueadas vão por `-c`). As
ações travadas voltam como `denials`. Serve para automação; o plugin exige o native.

## Navegador

- **Claude:** Claude in Chrome (o seu Chrome, já logado) ou o navegador do app desktop; Playwright pelo MCP.
- **Codex:** no app desktop, `@Chrome` (a extensão do Codex no seu Chrome, já logado) e `@Browser` (o navegador do
  app, para páginas locais e públicas, com perfil próprio); no CLI, o Playwright, se estiver no seu Codex.
- O QA usa o que tiver; se o subagente não conseguir usar nenhum, devolve o critério ao orquestrador, que testa no
  navegador dele e debate o resultado com você (*Testes* em [fluxo.md](fluxo.md)).

## Limites do Codex

Além do que é exclusivo do Claude Code (acima):

- Não há ferramenta para mudar a pasta da sessão nem acrescentar uma no meio da conversa: o `/aidw:diff` e as
  *Session folders* não existem lá. O `aidw open --provider codex` abre já no worktree (com `--app`, no app desktop).
- Os worktrees que o app do Codex cria são dele (`$CODEX_HOME/worktrees`); os da demanda são do AiDW e abrem pelo
  `aidw open`.
- O sandbox deixa o `.git` só leitura: o `worktree create` pede aprovação e os agentes não fazem commit (você faz).
- Se o `node` do PATH mora no perfil do usuário (ex.: nvm), o sandbox do Codex não o lê: instale um Node fora do
  perfil (ex.: em Program Files) para os builds.

## O que é gerado

Nada disso é versionado.

| Arquivo | Gerado por | Conteúdo |
|---|---|---|
| `.aidw/marketplace/plugins/aidw/` | `install` | O plugin: agentes e variantes, skills, `orquestrar`/`sair`/`diff`, referências, hooks |
| `.aidw/marketplace/plugins/aidw-mods/` | `install` | Os mods do Claude Code, copiados de `mods/aidw-mods` (sem os testes) com a raiz do AiDW desta máquina |
| `.aidw/install-manifest.json` | `install` | O que o install acrescentou no Claude e no Codex (para o `uninstall` remover só isso) |
| `~/.claude/settings.json` (merge) | `install` | Regras `deny`/`ask`/`allow`, pastas liberadas e `env`, só os itens do AiDW |
| `~/.codex/agents/aidw-*.toml`, `~/.agents/skills/aidw-*` | `install --provider codex` | Agentes e skills — e só isso |
| `state/worktrees.json`, `state/sessions.json` | comandos e hooks | Registro dos worktrees e das sessões no modo orquestrador |
| `.aidw/agents/<nome>.md`, `.aidw/reference/`, `.aidw/runtime.json` | `apply` | Definição de cada agente, referências do orquestrador, configuração resolvida |
| `CLAUDE.md`, `.claude/agents/`, `.claude/settings.local.json`, `.claude/skills/`, `.mcp.json` | `apply` (Claude) | O modo projeto do Claude |
| `AGENTS.md`, `.codex/config.toml`, `.codex/agents/`, `.codex/rules/aidw.rules`, `.agents/skills/` | `apply` (Codex) | O modo projeto do Codex (só com `provider = "codex"`, na raiz do AiDW) |

Garantias: valida tudo antes de gravar; sem mudança, nenhuma escrita; remove só o que foi gerado pelo AiDW; um arquivo
gerado alterado à mão faz o `install` parar (a não ser com `--force`).
