# AiDW — Plano v3: instalação global, orquestrador sob demanda e worktree por demanda

Versão 3, de 2026-09-26. Substitui o *Plano V2 (Global Worktree Orchestrator)*.

**O que mudou em relação à v2**
- O orquestrador deixa de ser global. Ele passa a ser uma skill que você chama quando quer.
- O contexto sai de dentro dos agentes e é lido na hora da execução.
- As permissões ficam em duas camadas: regras globais nas settings e um hook para o que depende do contexto.
- No Claude, a distribuição vira um plugin local, e o worktree nativo do Claude Code é reaproveitado.
- Saíram do plano: JEV/DecisionEngine, a quebra do código em pacotes, MCP em três escopos e as skills novas sem evidência de ganho.

## Objetivo

Chamar o AiDW em qualquer pasta, no Claude ou no Codex, e ter o mesmo fluxo que existe hoje em `C:\AiDW`:
spec, tickets, codificador, revisão, documentação e revisão final. Cada demanda de código roda no seu
próprio worktree, com o menor custo de tokens possível e sem abrir mão da qualidade (a revisão continua obrigatória).

O `C:\AiDW` passa a ser a **fonte da verdade e o registro** de três coisas:
- as fontes (agentes, skills, policies, contextos);
- o estado das demandas;
- o registro dos worktrees.

Nas pastas do usuário (`~/.claude`, `~/.codex`) ficam só os arquivos gerados pela instalação.

## Premissas verificadas

| Premissa | O que a verificação apontou | Situação |
|---|---|---|
| O orquestrador pode ficar global | Hoje ele é o `CLAUDE.md` da raiz, com 40,7 KB, cerca de 10 mil tokens (`aidw.py` `apply`, linha 1643). Um `~/.claude/CLAUDE.md` global o carregaria em todo chat da máquina. | ⚠️ divergente, resolvido com uma skill |
| Agente global serve para qualquer projeto | O `apply` embute *Systems*, policies e a tabela de effort do contexto no prompt de cada agente (`systems_section` na linha 944, `render_agent` na linha 1032) | ⚠️ divergente, resolvido lendo o contexto na execução |
| As permissões valem em qualquer pasta | Elas vivem em `.claude/settings.local.json` da pasta do AiDW. O subagente herda as regras da **sessão**, e o `settings.json` de um plugin só aceita `agent` e `subagentStatusLine` (docs do Claude Code, *plugins/components*). | ⚠️ divergente, resolvido com as camadas da D3 |
| O app desktop carrega plugins instalados na máquina | O `chrome-devtools-mcp` foi instalado com `scope: user` (`~/.claude/plugins/installed_plugins.json`) e aparece nesta sessão do app. A pesquisa dizia o contrário, e a evidência local contradiz. | ✅ confirmada |
| Agente de plugin aceita o frontmatter que usamos | `model`, `effort`, `tools`, `disallowedTools`, `skills` e `omitClaudeMd` são aceitos. `hooks`, `mcpServers`, `permissionMode` e `initialPrompt` são ignorados (docs). Nenhum agente atual usa esses campos ignorados. | ✅ confirmada pela doc; testar no spike (F1) |
| O hook enxerga as chamadas dos subagentes | O `PreToolUse` dispara dentro de subagentes, e a entrada traz `agent_type` e `agent_id` (docs, *hooks*) | ✅ confirmada pela doc; testar no F1 |
| Uma sessão não muda de pasta | No Claude, o `EnterWorktree` troca a pasta da sessão para o worktree, e o hook `WorktreeCreate` permite escolher onde ele é criado (docs, *worktrees*). No Codex não existe equivalente. | ⚠️ divergente só para o Claude |
| A skill sobrevive à compactação | Só os primeiros 5 mil tokens de cada skill são recolocados, com teto de 25 mil no total (docs, *skills*) | ⚠️ restrição: o núcleo do orquestrador precisa ter ≤ 4,5 mil tokens |
| O Codex tem plugin | Tem, com skills, MCP e hooks, mas **sem agentes** (issue openai/codex#18988 aberta). Hooks dentro de plugin podem não rodar (issue #16430). Agentes globais ficam em `~/.codex/agents/*.toml`. O `spawn_agent` aceita `model` e `reasoning_effort` por chamada. | ⚠️ parcial: plugin mais instalação manual |
| Há testes para garantir o refactor | Não existe pasta `tests/` | ⚠️ divergente, resolvido com a Fase 0 |
| O estado precisa ser reestruturado | O contexto já define os artefatos (`plano-<id>.md`, `review-<id>-r<N>.md`…) em `contexts/<contexto>/demandas`, que é um repositório privado | ✅ basta acrescentar o `demand.json` |
| É preciso um registry de projetos | O `[systems]` do `context.toml` já lista os repositórios de cada sistema | ✅ reaproveitar |

## Decisões tomadas

| # | Tema | Decisão | Quem decidiu, quando |
|---|---|---|---|
| D1 | Como chamar o orquestrador | Skill `/aidw:orquestrar [demanda]` (no Codex, `$aidw-orquestrar`). Ela assume a sessão até `/aidw:sair`. Mantém o prompt padrão do Claude Code, funciona no app desktop e no CLI, e é igual nos dois provedores. `claude --agent aidw:orquestrador` fica como opção só do CLI, dentro do `aidw open`. | usuário deixou a escolha ao orquestrador, 2026-09-26 |
| D2 | Contexto | **Revista na F2:** um plugin por contexto, com os agentes já contendo o contexto no próprio prompt, como hoje (ex.: `aidw:codificador`). O hook `SubagentStart` só injeta ~2 KB e o contexto de um papel tem ~20 KB; ler de arquivo daria menos autoridade às policies. | usuário, 2026-09-26 (revista com a evidência da F2) |
| D3 | Permissões | Três camadas, detalhadas na §4 | usuário, 2026-09-26 (global + hook) |
| D4 | Provedor principal | Claude primeiro. O Codex chega à paridade de resultado na F6 e pode ter instalação mais manual. | usuário, 2026-09-26 |
| D5 | Distribuição no Claude | Plugin local `aidw`, gerado por máquina pelo `aidw install` num marketplace local dentro de `.aidw/`. A viabilidade é confirmada no spike F1. | usuário aceitou testar, 2026-09-26 |
| D6 | Pasta dos worktrees | Raiz curta e configurável no contexto, `C:\wt\<repo>\<id>`, criada pelo hook `WorktreeCreate`. Nunca dentro do repositório: o MSBuild herdaria o `Directory.Build.props` do repositório principal. | usuário, 2026-09-26 |
| D7 | Branch | Prefixo definido no contexto: `feature/<id>-<slug>` no contexto em uso; `aidw/<id>-<slug>` quando não há contexto | Orquestrador, seguindo a convenção do time |
| D8 | Estado | Os artefatos atuais continuam como estão, com o `demand.json` a mais. Registro dos worktrees em `state/worktrees.json`, dentro do AiDW. | Orquestrador |
| D9 | Manifest | Evoluir o `.aidw/runtime.json` e o `merge_list(previously_managed)` com um hash por arquivo, em vez de criar outro mecanismo | Orquestrador |
| D10 | Fora do plano | JEV/DecisionEngine, a quebra em `adapters/`, `core/`, `project/`, `worktree/`, MCP em três escopos e as skills novas do §25 da v2 | usuário concordou, 2026-09-26 |

## 1. Arquitetura

```text
C:\AiDW (fontes + estado + registro)
 │  python aidw.py install  ──►  Claude: plugin "aidw" (marketplace local) + deny/ask universais em ~/.claude/settings.json
 │                          ──►  Codex:  ~/.agents/skills, ~/.codex/agents/*.toml, ~/.codex/hooks.json, ~/.codex/rules/aidw.rules
 │
 ├─ .aidw/contexts/<ctx>/<papel>.md   contexto compilado por papel (só o que o papel usa)
 ├─ contexts/<ctx>/demandas/<tipo>-<id>/demand.json + artefatos de hoje
 └─ state/worktrees.json              registro (o git continua sendo a verdade: `git worktree list`)

Qualquer pasta ─► /aidw:orquestrar 123 ─► aidw.py project detect --json
                                          (repo, sistema, contexto, demanda existente)
                                       ─► demanda nova ou retomada (demand.json)
                                       ─► código? EnterWorktree (Claude) | aidw open (Codex)
                                       ─► fluxo atual: spec → revisão do plano → tickets → codificador ⇄ revisor → docs → revisão final
```

## 2. O orquestrador como skill (D1)

- **`/aidw:orquestrar [id]`**
  1. Roda `aidw.py project detect --json`.
  2. Lê `.aidw/contexts/<ctx>/orchestrator.md`.
  3. Abre ou retoma a demanda.
  4. Assume a sessão até `/aidw:sair`.
- **`/aidw:sair`** grava a etapa atual no `demand.json` e devolve a sessão ao modo normal.
- **Núcleo com ≤ 4,5 mil tokens**, para caber no que a compactação recoloca. Hoje o orquestrador tem cerca de 10 mil tokens.
  - O núcleo guarda o papel, a autonomia, a delegação, o `NEXT ACTION` e a triagem.
  - Vão para arquivos de referência, lidos só na etapa que precisa: as passadas extras, a revisão final e o checklist de preparação.
  - O fluxo aparece duas vezes (em `ORCHESTRATOR.md` e em `contexts/<contexto>/agents/orchestrator.md`) e deve ser unificado.
- **Depois da compactação:** um hook `SessionStart` com `source=compact` vê se a pasta atual pertence a uma demanda ativa. Se sim, injeta uma linha: "releia `aidw:orquestrar` e o `demand.json`".
- **Retomada:** `/aidw:orquestrar` sem argumento acha a demanda pela pasta, pela branch ou pelo registro. Se houver mais de uma candidata, pergunta.

## 3. Agentes genéricos e o contexto na execução (D2)

- Os agentes do plugin ficam com o nome `aidw:codificador`, `aidw:revisor-opus-high` etc. O prompt deles não tem mais nada do contexto.
- O `aidw install` compila o que hoje é embutido: os `include` e a lista de `reference` do `context.toml`, as policies e os *Systems*. O resultado vai para `.aidw/contexts/<ctx>/<papel>.md`.
- O arquivo de tarefa traz `Contexto: <caminho>`. A primeira ação do agente é lê-lo.
- **A avaliar no F1:** injetar esse arquivo pelo hook `SubagentStart`. Isso tira a leitura do controle do modelo.
- **Variantes por effort continuam no Claude.** A ferramenta Agent não aceita effort por chamada, então cada effort precisa de um agente próprio.
  - As descrições das variantes ficam numa linha só: "Codificador, effort low — mesmo papel de aidw:codificador".
  - Hoje as 24 variantes somam 8,3 KB de descrição, que o plugin global colocaria em todas as sessões.
  - Meta: menos de 3 KB.
- **No Codex não há variantes:** o `spawn_agent` recebe `model` e `reasoning_effort` por chamada, com `fork_turns: "none"`.

## 4. Permissões em três camadas (D3)

1. **Globais, em `~/.claude/settings.json`**, com merge controlado pelo manifest:
   - `deny` universais: force push, `reset --hard`, `clean -f`, `.env`.
   - `ask` do `git_ask`: commit, push, merge, rebase, reset, checkout/switch…
   - `allow` de leitura: `git *` e `dotnet build/test`.
   - No Codex, o equivalente vai em `~/.codex/rules/aidw.rules`.
   - Continuam valendo mesmo se o hook falhar.
2. **Hook `aidw guard` (`PreToolUse`)**, no plugin do Claude e em `~/.codex/hooks.json`, com o mesmo script nos dois:
   - **Não faz nada fora de uma demanda ativa:** se a pasta não pertence a nenhuma, sai logo com código 0.
   - **Dentro de uma demanda:**
     - o codificador e o documentador só escrevem nos worktrees e na pasta da demanda;
     - o que o contexto proíbe vira `deny` (ex.: a ferramenta de comentário do ADO nos subagentes);
     - o que o contexto libera vira `allow` restrito (ex.: `sql-consulta.ps1`, `msbuild.ps1`).
   - O hook **só nega ou pede OK**. Ele libera (`allow`) apenas o que está na lista do contexto. Falta confirmar no F1 como `allow` do hook e `deny` das settings se combinam.
   - É um script pequeno, só com a biblioteca padrão, e com `matcher` limitado a `Bash|PowerShell|Edit|Write|mcp__ado.*`, para não pesar nas outras sessões.
3. **Isolamento nativo:** com a sessão dentro do worktree (`EnterWorktree`), o próprio Claude Code bloqueia edições e comandos no checkout principal.

## 5. Worktree por demanda (D6, D7, D8)

- **`aidw.py worktree create|list|inspect|remove|cleanup`** nasce da skill `preparar-worktree` e mantém tudo dela:
  - a base certa, inclusive a branch não mergeada de outra demanda;
  - a junction de `packages/`;
  - a limpeza que remove a junction antes de remover o worktree.
- **O hook `WorktreeCreate`** chama o `aidw.py worktree create`, para que o `EnterWorktree` nativo use a nossa pasta, o nosso nome e a junction.
- **Demanda com mais de um repositório** (ex.: um app desktop + a API que ele consome): um worktree por repositório, todos listados no `demand.json`. A sessão entra no worktree principal; o outro é acessado pelo caminho absoluto.
- **Working tree principal com alterações:** avisa que o worktree nasce da base sem essas alterações, e pergunta uma vez.
- **Nunca remover** um worktree com alteração não integrada. Apagar a branch continua sendo uma ação travada.
- **Tarefas só de leitura** (explicar, analisar) não criam worktree.

```json
{ "id": "us-123456", "context": "meu-contexto", "status": "review", "step": "REVIEW",
  "repos": [{ "repo": "C:/Projetos/MeuApp", "worktree": "C:/wt/MeuApp/us-123456",
              "branch": "feature/123456-slug", "base": "develop" }] }
```

## 6. Custo de tokens

| Onde | Hoje | Meta v3 |
|---|---|---|
| Sessão comum, fora do AiDW, com o plugin ligado | 0 | Descrições dos agentes (< 3 KB) e das skills. Sem orquestrador. |
| Sessão orquestrando | Cerca de 10 mil tokens do `CLAUDE.md` sempre carregados | Núcleo com ≤ 4,5 mil tokens, mais o contexto do orquestrador e as referências por etapa |
| Agente | Contexto embutido no prompt | Os mesmos tokens, mas só do papel dele e só do contexto da demanda |
| Revisão | Sem mudança: revisor novo por rodada, só com o diff das correções | Igual |

O ganho real é medido no `metricas.md` de uma demanda de verdade, antes (F0) e depois (F2).

## Resultado do spike F1 (2026-09-26)

Plugin mínimo `aidw-spike` (2 agentes, 1 skill e 1 hook em Python para `PreToolUse`,
`SubagentStart`, `SessionStart`, `WorktreeCreate` e `WorktreeRemove`), testado no Claude Code 2.1.282
por `claude -p` (com `--plugin-dir` e instalado por marketplace local) e no Codex 0.157.0 por `codex exec`.
Veredito: **segue**. O plugin atende o lado Claude; o Codex fica com instalação por arquivos.

### Claude Code

| # | Teste | Resultado |
|---|---|---|
| C1 | Agentes do plugin pelo nome com prefixo (`aidw-spike:eco`) no `subagent_type` | ✅ |
| C2 | `omitClaudeMd: true` | ✅ O agente com o campo não vê o `CLAUDE.md`; o agente sem ele vê |
| C3 | `skills:` pré-carregada, pelo nome curto (`ola`) e com prefixo (`aidw-spike:ola`) | ✅ os dois funcionam (a pesquisa dizia que só com prefixo) |
| C4 | `SubagentStart` injetando `additionalContext` no subagente | ✅ Resolve a D2: o contexto do papel entra por hook, sem depender do agente ler o arquivo |
| C5 | O `PreToolUse` dispara dentro do subagente e traz `agent_type` e `agent_id` | ✅ O hook bloqueou o `Write` do subagente num caminho proibido e deixou passar o outro |
| C6 | `allow` do hook em comando que pediria aprovação | ✅ Roda sem prompt; o comando de controle, sem decisão do hook, foi negado |
| C7 | `allow` do hook contra `deny` das settings | ✅ O `deny` vence. Pela doc, o `ask` das settings também vence o `allow` do hook: a camada 1 da D3 continua valendo mesmo com o hook |
| C8 | `SessionStart` com `source=compact` (compactação real, de 50 mil para 4 mil tokens) | ✅ dispara; `startup` e `resume` também |
| C9 | `WorktreeCreate` do plugin com o `EnterWorktree` no meio da sessão | ✅ Worktree em `C:\wt\...`, branch nossa, sessão dentro dele (a pesquisa dizia que o `EnterWorktree` não chamava o hook) |
| C10 | `WorktreeCreate` do plugin com `claude --worktree` na abertura | ❌ Não é chamado: o plugin carrega depois. Declarado nas settings, funciona. |
| C11 | Instalação: `claude plugin validate`, `marketplace add`, `install` (escopo usuário) | ✅ |
| C12 | Atualização depois de mudar a fonte | ⚠️ Não é uniforme. O `claude -p` leu o plugin **da pasta de origem** e viu a mudança sem `update`. O chat novo do app desktop leu **o cache** (`~/.claude/plugins/cache/<marketplace>/<plugin>/<versão>`), que ainda tinha a versão antiga. Conclusão: a cada mudança, o `install`/`apply` troca a versão e roda `claude plugin update`. |
| C13 | O `init` do `claude -p --output-format stream-json` lista plugins, agentes e skills | ✅ Útil para testes automatizados |
| C14 | App desktop carrega o plugin instalado | ✅ Chat novo do usuário, aberto fora do AiDW: `SessionStart` e `SubagentStart` com `agent_type` `aidw-spike:eco`, rodando a partir do cache (ver C12). A sessão já aberta também recebeu os agentes e as skills do plugin sem reiniciar. |

### Codex

| # | Teste | Resultado |
|---|---|---|
| X1 | Skill global em `~/.agents/skills/<nome>/SKILL.md`, chamada com `$nome` | ✅ |
| X2 | Rules em `~/.codex/rules/aidw.rules` (nome próprio, não só `default.rules`) | ✅ carregado; `forbidden` recusou o comando |
| X3 | Agente global em `~/.codex/agents/<nome>.toml`, chamado por `spawn_agent` com `agent_type` | ✅ |
| X4 | Hooks em `~/.codex/hooks.json` | ⚠️ Só rodam depois que o usuário confia neles uma vez (o Codex guarda essa confiança). Hooks dentro de plugin foram removidos (`plugin_hooks removed`). |
| X5 | O mesmo `guard.py` no Codex: `deny` pelo JSON, `agent_type`/`agent_id` no subagente, `SubagentStart` | ✅ Testado uma vez com `--dangerously-bypass-hook-trust`, num repositório descartável |

### O que muda no plano

- **D5:** confirmada. No Claude, um plugin local num marketplace local em `C:\AiDW\.aidw\`. O `install` roda `marketplace add` e `install` uma vez. A cada mudança, o `apply` grava a versão no `plugin.json` a partir do hash do conteúdo e roda `claude plugin update`, para o cache (usado pelo app desktop) ficar igual às fontes.
- **D6 e F4:** o `WorktreeCreate` fica no plugin, porque é o que o `/aidw:orquestrar` usa (o `EnterWorktree` no meio da sessão). O `aidw open` não depende do `--worktree`: cria o worktree com `aidw.py worktree create` e abre o `claude` já dentro dele.
- **D2:** o contexto do papel é injetado pelo hook `SubagentStart`. O caminho no arquivo de tarefa fica como reserva, para o modo headless.
- **F6, Codex:**
  - a instalação é por arquivos: skills em `~/.agents/skills`, agentes em `~/.codex/agents`, `~/.codex/rules/aidw.rules` e `~/.codex/hooks.json`;
  - no primeiro uso, o usuário aprova uma vez a confiança nos hooks;
  - no Codex os nomes das ferramentas são outros (`Bash`, `collaborationspawn_agent`…), e o `guard.py` precisa tratar os dois provedores.
- **F3, `uninstall`:** o `claude plugin uninstall` seguido de `marketplace remove` deixa `extraKnownMarketplaces: {}` no `~/.claude/settings.json` e a pasta `~/.claude/plugins/cache/<marketplace>`. O `aidw uninstall` remove as duas, e só se forem do AiDW (manifest).
- **Risco confirmado (C12):** o app desktop usa o cache. O `doctor` compara a versão instalada (`installed_plugins.json`) com o hash das fontes e manda rodar o `apply` quando divergem.

## Resultado da F2 (2026-09-26)

**Entregue.**
- Núcleo genérico (`orchestrator/ORCHESTRATOR.md`) e fluxo do contexto (`contexts/<contexto>/agents/orchestrator.md`) sem repetição.
- Cinco referências lidas sob demanda, renderizadas em `.aidw/reference/`: passadas extras, itens do plano, preparar a revisão, revisão final, e a policy de cards (pelo frontmatter `orchestrator_when`; os agentes continuam com ela inteira).
- `CLAUDE.md` de **40,7 KB para 26,5 KB (−35%)**.
- Revisão da F2: nenhuma regra perdida; três achados, todos corrigidos.
- 7 testes.

**A/B numa melhoria real de front-end Vue** (pré-preenchimento de campos pela URL; simulação sem escrita no board e sem commit; mesmo prompt, mesmos bloqueios, worktree na base anterior à entrega do time):

| | Baseline (AiDW antes da F2) | F2 |
|---|---|---|
| Custo total (preço de lista) | US$ 7,08 | **US$ 5,27 (−26%)** |
| Mensagens do orquestrador | 98 | 73 |
| Cache lido pelo Opus (orquestrador + codificador) | 5,90 M | 3,61 M (−39%) |
| Cache lido por mensagem do orquestrador | ~60 k | ~49 k (−18%) |
| Caminho | nível simples; 2 rodadas de revisão; 2 passadas de segurança | nível padrao; revisão do plano; 1 rodada |
| Duração | 26 min | 27 min |
| Qualidade (comparação às cegas, nota 0–10) | 6,5 | **8** |

**Leitura honesta.**
- O **custo por mensagem** caiu 18%, e isso é efeito direto do prompt menor.
- A queda total de 26% também inclui um caminho diferente: o nível escolhido mudou (simples × padrao) para o mesmo card, e isso mudou os passos.
- Com n = 1, a diferença de qualidade **não** prova que a F2 melhora o código. Prova que o prompt enxuto **não piorou**: o orquestrador leu as referências no momento certo (plano, passadas, preparação da revisão, cards) e o pacote final saiu com todos os itens.

**Achados do A/B:**
- **Nível instável:** o mesmo card virou simples numa execução e padrao na outra. Os critérios da tabela se sobrepõem ("regra de negócio" é padrao; "1–2 arquivos, lógica direta" é simples). Vale desempatar na tabela `[effort.levels]`.
- **Maior custo restante: as personas dos agentes.** O prompt do codificador tem 44 KB e o do revisor 40 KB, dos quais 18 KB e 17 KB vêm da persona do contexto. A do codificador tem muita orientação .NET que não serve a Vue. É candidata a passar para referências por tema, com um A/B igual a este.
- **A implementação da F2 não limpa a URL** depois do pré-preenchimento (dado pessoal na barra e no histórico); o baseline e a referência limpam. Ela registrou o risco como nota para a PO. Isso é assunto de regra de revisão (privacidade), não da F2.

## Resultado da F3 (2026-09-26)

**Entregue: `python aidw.py install [--dry-run] [--force] [--mcp]` e `uninstall [--dry-run]`.**
- **Plugin `aidw-<contexto>`** num marketplace local em `.aidw/marketplace/`, com:
  - os 24 subagentes, com nomes com prefixo e o contexto no prompt;
  - 13 skills, com o aviso "[AiDW]" na descrição;
  - a skill `orquestrar` (`disable-model-invocation`) e a `sair`;
  - as referências do orquestrador.
- **Versão do plugin = hash do conteúdo.** Mudou, o `install` roda `marketplace update` e `plugin update`. Testado na máquina: a versão nova foi para o cache.
- **Merge no `~/.claude/settings.json`** de deny, ask (`git_ask`), allow (o que o contexto libera mais `record`, `show` e `doctor` pelo caminho absoluto), pastas liberadas (AiDW, projetos, `C:/wt`) e env.
- **Só é do AiDW o que ele acrescentou** (`merge_owned`), registrado em `.aidw/install-manifest.json`, que é gravado **antes** de chamar o CLI; uma falha no meio não perde o registro de quais regras são do AiDW.
- **Rodar de novo não muda nada.** Arquivo gerado alterado à mão dá erro, a não ser com `--force`.
- **O `uninstall` remove:** plugin, marketplace, cache, a chave `extraKnownMarketplaces` vazia, os MCPs que ele registrou e as regras dele. Devolve as settings exatamente como estavam (teste).
- **MCPs do catálogo no escopo do usuário só com `--mcp`,** porque sobem em toda sessão do Claude.
- **O `install` recusa o modo `headless`:** o plugin leva só subagentes nativos.
- **Doctor:** seção "Instalação global" (versão instalada × fontes, regras presentes, instalação que parou no CLI).
- **Validação na máquina:** chat headless aberto em `C:\Projetos`. Carregou os 24 agentes `aidw:*`, as 13 skills e a `/aidw:orquestrar`, com a tabela de effort usando os nomes com prefixo e o `record` pelo caminho absoluto. O `record` aceita o nome com prefixo.
- **Revisão:** rodada 1 com 1 CRITICO (manifest gravado depois do CLI) e 5 IMPORTANTES; rodada 2 aprovada. 11 testes.

**Limitações que ficam para as próximas fases:**
- A skill `orquestrar` tem o prompt inteiro (~26 KB). Depois de uma compactação, o Claude recoloca só ~5 mil tokens dela; a skill manda reler o arquivo, e o hook de compactação vem na F5.
- Ainda não há hook de guarda nem worktree automático (F4).

## Resultado da F4 (2026-09-26)

**Entregue.**
- **`aidw.py worktree create|list|inspect|remove|cleanup`** e **`project detect`**.
  - O worktree nasce em `C:\wt\<repo>\<tipo-id>`, na branch `feature/<número>-<slug>` (prefixo em `[worktree]` do contexto).
  - A base padrão é `origin/HEAD`, com `fetch` antes; a branch é reaproveitada se já existir.
  - Junctions de `packages/` e `node_modules/`.
  - Registro em `state/worktrees.json` e `demand.json` na pasta da demanda.
  - Avisa quando o working copy principal tem alterações.
- **`remove` estrito:** recusa alteração local e commit não publicado; qualquer falha do git também recusa, porque dá erro em vez de supor que está limpo. Remove as junctions antes e mantém a branch.
- **Hooks no plugin:**
  - `WorktreeCreate`: o `EnterWorktree` com o id da demanda cai no worktree registrado do mesmo repositório.
  - `WorktreeRemove`: não apaga.
  - `PreToolUse` → `aidw_guard.py` (biblioteca padrão, falha libera): agente do AiDW não faz Edit/Write no working copy principal de repositório com worktree ativo; a conversa principal não tem regra.
- **Instruções:**
  - `ORCHESTRATOR.md` ganhou a seção *Workspace*, que diz o limite do hook: comandos de shell não são verificados.
  - A skill `preparar-worktree` foi reescrita sobre o comando.
  - O passo 4 do contexto aponta para `C:\wt`.
- **Teste de ponta a ponta no Claude real:**
  - o `EnterWorktree` levou a sessão ao worktree registrado;
  - com a sessão no worktree, o Claude bloqueou nativamente a escrita no principal;
  - com a sessão fora dele, **o guard do AiDW** bloqueou o Write do `aidw:codificador-low` no principal e deixou a conversa principal escrever.
- **Revisão:** rodada 1 com 1 CRITICO, reproduzido de verdade: git falhando fazia o `remove` apagar um worktree com 3 commits não publicados. Mais 2 IMPORTANTES: junction que falha deixava um worktree órfão, e o hook ignorava o repositório. Rodada 2 aprovada. 13 testes.

**Limite conhecido:** o guard vê Edit/Write, não comandos de shell. Com a sessão no worktree, o isolamento nativo do Claude cobre o shell; fora dele, vale a tarefa apontar só para o worktree.

## Resultado da F5 (2026-09-27)

**Entregue.**
- **`/aidw-<contexto>:orquestrar` com protocolo de abertura** (vem antes do resto da skill):
  - roda `project detect` e `demand list --active`;
  - escolhe a demanda nesta ordem: a do pedido, a da pasta (worktree), a única ativa do repositório; se não der, pergunta;
  - se o `demand.json` já existe, **retoma** da etapa gravada.
- **`aidw.py demand set|show|list`:** grava etapa, status, título, nota e histórico. Filtra por contexto, grava de forma atômica e, se o arquivo estiver ilegível, guarda como `.bak` com aviso.
- **`/sair`:** grava `paused` e o próximo passo.
- **Hooks de sessão no `aidw_guard.py`:**
  - `UserPromptSubmit` registra a entrada e a saída do modo orquestrador em `state/sessions.json`, com trava leve e descarte após 14 dias. Mensagem comum só compara o texto.
  - `SessionStart` (`compact|resume`) injeta um lembrete de menos de 2 KB.
  - Os hooks leem o stdin em UTF-8. Antes liam na página do console, e o guard deixaria passar caminho com acento.
- **Regras `allow` globais:** passam a incluir `project`, `demand` e `worktree`, para não pedir aprovação a cada etapa.

**Critérios de aceite (§8), verificados no Claude real:**

| # | Critério | Resultado |
|---|---|---|
| 1 | Chat aberto em `C:\Projetos\MeuFront` com `/aidw:orquestrar`: detecta, cria demanda e worktree, segue o fluxo | ✅ a mesma melhoria em simulação, 34 min, US$ 7,42, 0 ações bloqueadas. 11 etapas no `demand.json` (UNDERSTAND → PLAN_REVIEW → PLAN_FIX → TICKETS → IMPLEMENT → PREPARE_REVIEW → REVIEW → CODER_FIX → REVIEW → DOCS → FINAL_REVIEW) |
| 2 | Codificador só escreve no worktree | ✅ Working copy principal limpo ao fim; diff só no worktree (2 arquivos, +70) |
| 3 | Diff do app mostra o worktree | ✅ A sessão entrou no worktree (`EnterWorktree`). No app desktop falta só conferir o painel. |
| 4 | Fechar o chat e chamar `/orquestrar` na mesma pasta retoma da etapa gravada | ✅ Sessão nova no worktree, sem argumento: achou `us-<id>-sim5` em `FINAL_REVIEW` e o próximo passo certo; comandos do AiDW sem pedir aprovação |
| 5 | Sessão sem demanda ativa não sente o hook nem carrega o orquestrador | ✅ Por construção: mensagem comum só compara o texto (teste); a skill só roda quando chamada |
| — | Lembrete depois de compactação real | ✅ A sessão compactada recebeu o lembrete, com o pedido literal entre aspas |

**Qualidade da demanda:**
- A revisão do plano achou um CRITICO: a v1 mandaria um dado pessoal para um domínio externo por um parâmetro de retorno de um componente de terceiros. Foi corrigido na v2.
- A passada de segurança achou uma ferramenta de analytics gravando a URL com o dado pessoal. Ficou como rascunho de Dívida técnica.

**Observações:**
- **Custo:** o caminho mudou de novo (2 rodadas de revisão do plano mais passada de segurança). O custo de uma demanda simples ficou entre US$ 5 e 7,50 nas três execuções.
- **PowerShell:** a ferramenta PowerShell do Claude Code nesta máquina falha às vezes com "Linha de comando muito longa", também fora do AiDW (F1). O modelo cai para o Bash sozinho.
- **Revisão:** rodada 1 com 1 CRITICO (demanda de outro contexto dividindo a pasta `state/`) e 4 IMPORTANTES; rodada 2 aprovada. 16 testes.

## Resultado da F6 (2026-09-28)

**Entregue: `install --provider codex|all` e `uninstall --provider …`, com nomes `aidw-*`.**
- **Arquivos instalados no Codex:**
  - skills em `~/.agents/skills/aidw-*`; a `aidw-orquestrar` e a `aidw-sair` com `allow_implicit_invocation: false`;
  - agentes em `~/.codex/agents/aidw-*.toml`;
  - `~/.codex/rules/aidw.rules`;
  - `~/.codex/hooks.json` por merge, mantendo os hooks do usuário;
  - perfil próprio `~/.codex/aidw.config.toml`.
- **O que o perfil faz:** libera escrita no AiDW, nos projetos e nos worktrees, liga o multi-agente, os MCPs e o `safe.directory`. O `config.toml` do usuário não é tocado.
- **`aidw.py open --provider codex --demand <id>`:** abre o Codex com o perfil, já no worktree da demanda.
- **Guard único para os dois provedores:** o `aidw_guard.py` entende o `apply_patch` (caminhos dos cabeçalhos `*** Add/Update/Delete File:`) e o `$aidw-orquestrar`.
- **Confiança dos hooks:**
  - o Codex exige aprovação única no terminal; ela fica em `[hooks.state]` do `config.toml` e é invalidada se o comando ou o matcher do hook mudar;
  - o manifest guarda a assinatura dos hooks, e o `doctor` só diz "aprovados" com um hash válido.
- **`record` com `--codex-task`:** usa o Codex (modelo e tokens reais da sessão do subagente), mesmo numa máquina com a config do Claude.
- **Revisão:** rodada 1 com 1 CRITICO (confiança "aprovada" mesmo depois de invalidada) e 2 IMPORTANTES; rodada 2 aprovada. 20 testes.

**Teste de ponta a ponta no Codex** (a mesma melhoria de front da F2/F5, em simulação, com o MCP do board desligado):
- ✅ **O fluxo completo funcionou:** `$aidw-orquestrar`, abertura da demanda, trabalho no worktree pelo caminho absoluto, agentes `aidw-*` com `spawn_agent`, revisões, passadas extras, documentação e revisão final. O working copy principal continuou limpo, e os hooks rodaram depois da aprovação.
- ❌ **O resultado não foi equivalente ao do Claude:** 110 min, contra 34; 33 etapas, contra 11; o plano revisado 8 vezes; diff com 6 arquivos, contra 2.
- **Causas, todas corrigidas:**
  1. **Build impossível no sandbox:** o `node` da máquina é um link do nvm dentro do perfil do usuário, que o sandbox do Codex não lê, e o `npm` nem iniciava. O perfil `aidw` passa a pôr na frente do PATH um Node fora do perfil (o `install` mostra qual e a versão; o `doctor` avisa se não houver).
  2. **O orquestrador tratou o bloqueio de ambiente como falha do agente:** subiu o effort até crítica e ficou em laço. O núcleo agora diz que `environment_blocked` não é falha, e que o `max_retries` vale também para a revisão do plano. Isso vale para os dois provedores.
  3. **Métricas com modelos do Claude e sem tokens:** corrigido pelo `record` acima.
- **Reteste com as correções (2026-09-28, `us-131192-cx2`): equivalente ao Claude — critério 7 atendido.**
  Instalação real: hooks aprovados, sem `--dangerously-bypass-hook-trust`.

  | | Claude (F5) | Codex antes | Codex depois |
  |---|---|---|---|
  | Tempo | 34 min | 110 min | 44 min |
  | Etapas | 11 | 33 | 11 (mesma sequência) |
  | Plano revisado | 2× | 8× | 2× |
  | Diff | 2 arquivos, +70 (código + README) | 6 arquivos, +151 | 1 arquivo, +40 (o mesmo `LoginView.vue`) |
  | Build/type-check | validado | nunca rodou | validado (exit 0) |
  | Revisão de código | 2 rodadas | — | 1 rodada, sem achado |
  | Passada de segurança | risco da URL → rascunho de dívida | — | mesmo risco (CPF na query antes da limpeza) → rascunho de dívida |

  - A única diferença de conteúdo: o documentador do Claude também atualizou o README; o do Codex só gerou o plano de testes.
  - As métricas saíram com o modelo e os tokens reais do Codex.
  - Cota: o plano do Codex desta máquina foi de 80% para 87% do mês nessa execução.

## Resultado da F7 (2026-09-28)

- **`aidw status`:** um retrato em menos de 1 s, sem chamar os CLIs:
  - o contexto ativo;
  - a instalação no Claude (versão do plugin contra as fontes e contra o que o Claude tem) e no Codex (arquivos e aprovação dos hooks);
  - as demandas ativas, com etapa, nota e a situação de cada worktree (alterações, commits à frente, publicado);
  - o que pede atenção: worktree de demanda concluída (pronto para remover, ou com trabalho não publicado), worktree órfão, plugin instalado com outro contexto.

  O `--json` serve ao orquestrador. O diagnóstico completo continua no `doctor`.
- **`aidw open --demand <id>`:** abre o CLI no worktree da demanda, libera a pasta dela e já manda a primeira mensagem:
  - `/aidw:orquestrar <id>` no Claude;
  - `$aidw-orquestrar <id>` no Codex, com `--profile aidw`.

  O orquestrador retoma da etapa gravada. `1234` acha `us-1234`. `--no-orchestrate` abre sem chamar o orquestrador. Sem o AiDW instalado naquele provedor, abre sem chamar e avisa.
- **Por que não `claude --agent`:** o orquestrador é uma skill (D1) com saída (`/aidw:sair`). O `--agent` fixaria a sessão inteira como orquestrador, sem saída, e trocaria o prompt de sistema. Já a primeira mensagem passa pelo mesmo hook de modo que o texto digitado, então a retomada depois de compactação continua valendo.
- **A skill do Claude** não chama `EnterWorktree` quando a sessão já abriu dentro do worktree da demanda (o `project detect` mostra `demand`).

## 7. Fases

Cada fase tem critério de saída. O modo atual (`apply` em `C:\AiDW`) continua funcionando até a F5 ser aceita.

| Fase | Entrega | Critério de saída |
|---|---|---|
| **F0 — Rede de segurança** | Testes que comparam a saída do `apply --dry-run` com uma referência (arquivos gerados), para um contexto de exemplo e "sem contexto". Depois, num commit separado, as descrições curtas das variantes. | Testes passando; a referência só muda de propósito |
| **F1 — Spike (vai ou não vai)** | Plugin mínimo num marketplace local: 1 agente, 1 skill, `PreToolUse`, `SubagentStart`, `WorktreeCreate`. No Codex: 1 skill em `~/.agents/skills` e 1 arquivo em `~/.codex/rules/`. | Confirmar no app desktop e no CLI: o `subagent_type` `aidw:x`; o `effort`, os `skills` e o `omitClaudeMd` respeitados; o hook vendo o `agent_type`; como `allow` e `deny` se combinam; o `EnterWorktree` na pasta do hook; o fluxo de atualização do plugin depois de regerar (bump de versão). Resultado registrado aqui. |
| **F2 — Orquestrador enxuto e contexto na execução** | Núcleo mais referências; contexto compilado por papel; agentes genéricos. Ainda no escopo projeto. | Uma demanda real de ponta a ponta com resultado igual ao de hoje; tokens comparados no `metricas.md` |
| **F3 — `aidw install` / `uninstall` no Claude** | Plugin gerado e instalado; merge das settings globais com hash no manifest; `doctor` ampliado | Instalar duas vezes não muda nada; arquivo alterado por fora gera aviso em vez de ser sobrescrito; o `uninstall` remove só o que é do AiDW |
| **F4 — Projetos e worktrees** | `project detect`, `demand.json`, `worktree *`, `WorktreeCreate`, `aidw guard` | Testes: raiz, subpasta, fora do git, base com alterações, branch existente, branch usada por outro worktree, worktree órfão |
| **F5 — `/aidw:orquestrar` global** | A skill, o `/aidw:sair`, a retomada, o hook de compactação | Critérios de aceite abaixo; depois disso o `scope=project` vira alternativa |
| **F6 — Paridade no Codex** | Plugin de skills, `~/.codex/agents`, hooks e rules pelo `install`, e `aidw open --provider codex` (`codex -C <wt> --add-dir <demanda>`) | A mesma demanda de teste com resultado equivalente |
| **F7 — `open` / `status`** | `aidw open --demand` (retoma chamando o orquestrador; ver o resultado da F7 sobre o `claude --agent`) e `aidw status` | Uso real |

**Código:** o `aidw.py` continua sendo a entrada. Só o que precisa ser rápido ou isolado vira módulo:
- `aidw_guard.py` (hook, só biblioteca padrão);
- a lógica de worktree.

Extrair mais código só quando o Codex exigir uma camada de adaptação.

## 8. Critérios de aceite

1. Um chat aberto em `C:\Projetos\MeuApp`, com `/aidw:orquestrar 123456`, detecta o sistema e o contexto, cria a demanda e o worktree, e segue o fluxo sem que `C:\AiDW` seja aberto.
2. O codificador só escreve no worktree. Uma tentativa no checkout principal é bloqueada pelo hook ou pelo isolamento nativo.
3. O painel de diff do app mostra o worktree da demanda (a sessão está nele).
4. Fechar o chat e rodar `/aidw:orquestrar` na mesma pasta retoma da etapa gravada.
5. Uma sessão sem demanda ativa não sente o hook e não carrega o orquestrador.
6. O `uninstall` não mexe em nenhuma configuração que não é do AiDW.
7. No Codex, a mesma demanda de teste chega a um resultado equivalente (F6).

## 9. Riscos

| Risco | Mitigação |
|---|---|
| O app desktop usa a cópia em cache do plugin (C12) | Versão = hash do conteúdo; o `apply` roda `claude plugin update`; o `doctor` compara a versão instalada com as fontes |
| Um hook lento em toda chamada de ferramenta | `matcher` restrito, saída imediata fora de demanda, sem dependências |
| O núcleo do orquestrador se perde na compactação | Núcleo ≤ 4,5 mil tokens mais o hook de compactação |
| No Codex, hooks exigem confiança e não existem em plugin (X4) | Instalar em `~/.codex/hooks.json`; o `setup` explica a aprovação única e o `doctor` avisa se ainda não foi aprovada |
| O `EnterWorktree` só vale para o repositório da pasta atual | Abrir o chat na pasta do repositório (ou `aidw open`); fora disso, o caminho absoluto vai para os agentes, como hoje |

## Perguntas pendentes

Nenhuma. P1 (D3) e P2 (D6) foram respondidas pelo usuário em 2026-09-26.

## Branch e PR

Trabalho na branch `feature/aidw-v3`, a partir de `main`, com um commit por fase. O PR abre ao fim da F5, ou antes, por fase, se preferir.
