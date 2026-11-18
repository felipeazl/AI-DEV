# Agentes

Um agente é um **papel** com uma definição (`agents/<papel>/AGENT.md`), um modelo, um effort, ferramentas e skills. O
orquestrador é o chat principal; os outros são **subagentes nativos** do provedor (a ferramenta `Agent` no Claude,
`spawn_agent` no Codex), cada um num contexto novo a cada delegação.

São sete: orchestrator, explorer, planner, coder, reviewer, qa e documenter.

## Papel e nome

O **papel** é fixo e é o que o AiDW usa internamente (`coder`, `reviewer`…). O **nome** é o que aparece para você e
pode ser trocado no `aidw.config.toml` (por padrão é igual ao papel). No plugin do Claude os agentes se chamam
`aidw:<nome>`; no Codex, `aidw-<nome>`.

| Papel | Ferramentas | Escreve código? |
|---|---|---|
| `orchestrator` | as do chat | não (só quando você pede, ou na manutenção do próprio AiDW) |
| `explorer` | leitura, shell (SELECT pelo validador do contexto), grava o relatório | não |
| `planner` | leitura, shell, grava o plano | não |
| `coder` | leitura, edição, shell | **sim**, só no worktree |
| `reviewer` | leitura, shell, grava a revisão | não |
| `qa` | leitura, shell, navegador (Playwright, Chrome DevTools; Claude in Chrome de reserva), grava o roteiro e o relatório | não (pede ajustes ao coder) |
| `documenter` | leitura, edição, shell, board | só texto (Tasks, PR) |

Cada papel recebe também os servidores MCP que o `config/mcp.toml` libera para ele, menos as ferramentas que o contexto
bloqueia para ele (`disallowed_tools`).

## O que cada um faz

**Orchestrator** — conduz a demanda de ponta a ponta: entende o card, encomenda a exploração e o plano, **lê o plano** e
o leva à sua aprovação, dispara em paralelo o código, as Tasks e o roteiro de testes, leva os achados da revisão a você,
roda os passos manuais do teste com você e, com o seu OK, faz o commit, o push e abre a PR. Ele nunca lê código nem
usa o navegador: achar uma causa é trabalho do explorer, e o navegador é do qa.

**Explorer** — o leitor barato. Recebe perguntas numeradas ("onde fica a validação?", "qual o contrato do endpoint
X?") e responde com `arquivo:linha` ou com a consulta que prova: ids, enums, dado real pelo validador de SELECT do
contexto, chamada de API que só lê. Não desenha a solução nem altera nada. O relatório `exploration-<assunto>.md` é
reusado pelo plano. No **modo levantamento**, valida cada ponto do card e mapeia o fluxo de ponta a ponta. É também o agente por trás do
`/aidw:ask`, `/aidw:investigate`, `/aidw:card` e `/aidw:kb-review`.

**Planner** — escreve o `plan-<id>.md` (skill `to-spec`, pré-carregada): um plano **spec-driven, curto e
autossuficiente** — premissas verificadas, comportamento atual e desejado, os critérios de aceite e as regras de negócio
do card (`CA1`, `RN1`) e as **entregas** `E1`, `E2`… Cada entrega é o que um coder termina numa passada: os arquivos e o
que muda em cada um, os critérios que cobre, os testes de código que precisa, a doc do repositório que fica
desatualizada e o build. No **modo fix**, aplica os ajustes que você pediu. Se precisa de código que não conhece,
devolve `plan_needs_exploration`.

**Coder** — implementa **uma entrega por vez** no worktree, segue as convenções do projeto, roda só os comandos de build
e teste do plano, revisa o próprio diff e grava o patch. Num bloqueio de ambiente, reporta o comando e o erro exatos e
para. Nunca faz commit: o trabalho fica no worktree até a etapa PR. Testes de código só onde o ponta a ponta não
enxerga (um cálculo, um mapeamento, uma transição de estado…). **Ajuste de teste** (a pedido do qa): mudança temporária
marcada com `AIDW-TEST`, num patch só; a revisão e o commit nunca o veem.

**Reviewer** — revisa o **diff** de cada entrega contra o plano numa passada (skill `code-review`, pré-carregada):
qualidade (o guia do time e as convenções do repositório), **bugs** (cada um com o cenário de falha) e **segurança**
(cada falha com o caminho de ataque). Cada achado tem ID estável, severidade, categoria, a correção mínima, o código antes
e depois e a **recomendação** (manter ou descartar, e por quê). Quando o contexto tem um checklist de revisão, roda só
os itens cujo gatilho aparece no diff. Ao revisar a correção de um **escape** (um bug devolvido pela QA, um pedido de
mudança da revisão do time), também redige um *candidato ao checklist* para o `/aidw:done`. No **modo PR** (a PR de outra pessoa), cada achado que
vale contar ao autor vem com o rascunho do comentário; ele nunca comenta, aprova nem conclui a PR.

**QA** — dois momentos:
1. **Roteiro e massa** (modo `plan`, em paralelo com o coder): `test-script-<id>.md` com cada `CA`/`RN`, passos,
   resultado esperado, evidência e como provar (`auto-api`, `auto-browser`, `auto-suite` ou `manual`), e a massa,
   listando em *Approvals* o que precisa ser criado ou alterado.
2. **Teste** (modo `test`, depois da sua revisão de código): confere o roteiro contra o diff final, roda as escritas
   aprovadas e os passos automáticos e marca ✅/❌ com a evidência. Os passos manuais ficam para você e o orquestrador.
   Um passo de navegador que ele não consegue rodar porque nenhum navegador conecta vira `manual` com a nota
   `browser_unavailable`, para um qa novo rodá-lo assim que você conectar o navegador.

**Documenter** — depois da aprovação do plano, escreve o README da demanda (`readme-<id>.md`: o que o card entrega, em
palavras simples, sem o detalhe técnico do plano nem as suas decisões), anexa ao card quando o contexto pede e cria uma Task por
entrega; o
plano fica na pasta da demanda como a spec dos agentes. Depois dos testes, atualiza o README com o que foi feito e
testado e escreve o `pr-<id>.md` (mensagem de commit, título, descrição, work items, pendências para a QA). Quem faz o
commit, o push, abre a PR e troca o README no card é o orquestrador, com o seu OK. No modo **work item**
(`/aidw:investigate`, `/aidw:card`), redige uma User Story ou dívida técnica, criada só com o seu OK dos campos.

## Modelos e effort

Não há nível de demanda. Cada agente tem um **padrão** de modelo e effort e só as **exceções** listadas para ele, cada
uma com o motivo que a permite:

| Agente | Padrão | Exceções (só pelo motivo) |
|---|---|---|
| orchestrator | o do chat (veja abaixo) | — |
| explorer | Haiku low | Sonnet medium — refazer uma vez quando o resultado não fez sentido; Sonnet high — levantamento |
| planner | Sonnet high | medium — ajuste do plano que você pediu na aprovação |
| coder | Sonnet high | medium — correção pequena (achado mantido, teste que falhou, seu ajuste) ou ajuste temporário de teste; Opus medium — entrega que o plano marca como complexa (migração, concorrência, performance, contrato entre sistemas), ou correção que falhou duas vezes |
| reviewer | Sonnet high | medium — re-revisão só das correções; low — re-revisão de uma correção trivial |
| qa | Sonnet medium | high — refazer uma vez quando o resultado não fez sentido |
| documenter | Haiku medium | — |

**O orquestrador roda com o modelo e o effort do chat em que é aberto — o valor da configuração é só a recomendação
mostrada na seção Runtime.** (Recomendação padrão: Opus, medium.)

### Onde ficam os padrões

| O quê | Onde |
|---|---|
| O **tier** de modelo (`top`/`mid`/`fast`) e o effort padrão de cada papel | `DEFAULT_AGENTS` no `aidw.py` — orchestrator `top`/medium (só a recomendação), planner, coder e reviewer `mid`/high, qa `mid`/medium, explorer `fast`/low, documenter `fast`/medium |
| Qual modelo é cada tier, e os efforts que ele aceita | `config/models.toml` — Claude: `top` = Opus, `mid` = Sonnet, `fast` = Haiku (o Haiku aceita só `low`, `medium` e `high`) |
| As exceções | `[[effort.variants.<papel>]]` no `orchestrator/config/routing.toml` (`effort`, `model` opcional e `when`, o motivo) |
| As suas sobreposições | `[agents.<papel>]` no `aidw.config.toml` |
| As exceções de um time | `contexts/<nome>/routing.toml` (mesclado sobre o arquivo do núcleo) |

`python aidw.py show` mostra o nome, o modelo e o effort resolvidos de cada agente.

### Trocar modelo e effort

**De vez** — no `aidw.config.toml`, depois `python aidw.py install` (e `apply` para o modo projeto) e um chat novo:

```toml
[agents.coder]
model = "opus"            # chave do config/models.toml; sem ela, vale o tier do papel
effort = "medium"         # um dos efforts do modelo: low, medium, high, xhigh, max

[agents.reviewer]
effort = "medium"
```

Ou refaça o wizard (`python aidw.py configure`, passo 2). Um modelo do outro provedor vira o equivalente pelo tier.

**O orquestrador** — escolha o modelo e o effort no próprio chat (o seletor de modelo do Claude Code ou `/model`). O
`[agents.orchestrator] effort` só muda a recomendação impressa na seção Runtime dele.

**Numa tarefa** — peça ao orquestrador ("use Opus no coder neste ticket"). Ele passa `model` só naquela delegação,
porque você pediu; a trava do `aidw-mods` recusa um `model` que ninguém pediu.

**Uma exceção nova** — uma entrada a mais no `routing.toml` (núcleo, por PR) ou no `routing.toml` do contexto:

```toml
[[effort.variants.coder]]
effort = "medium"
when = "small fix (kept finding, failed test, user adjustment) or temporary test adjustment"

[[effort.variants.explorer]]
model = "sonnet"          # chave do Claude; no Codex vale o equivalente pelo tier
effort = "high"
when = "survey: the end-to-end flow map is the deliverable"
```

Toda exceção precisa de `when`. Rode os testes (`python tests/run.py`) ao mudar o arquivo do núcleo.

### Variantes

No Claude o modelo e o effort são fixados no arquivo do subagente, por isso cada exceção vira uma **variante**:

```text
aidw:coder                    ← o padrão (Sonnet high)
aidw:coder-medium             ← mesmo modelo, effort medium
aidw:explorer-sonnet-high     ← outro modelo: <nome>-<alias>-<effort>
```

A tabela *Agents and effort* do orquestrador traz o `subagent_type` de cada uma, e a trava do `aidw-mods` recusa uma
variante fora dela. No Codex cada variante também é um papel (`aidw-coder-medium`): veja [claude-and-codex.md](claude-and-codex.md#agentes-e-effort).

### Equivalência no Codex

A mesma tabela serve aos dois provedores pelo **tier** de cada modelo (`config/models.toml`):

| Claude | Tier | Codex |
|---|---|---|
| Opus | `top` | o modelo top liberado para a conta |
| Sonnet | `mid` | o intermediário |
| Haiku | `fast` | o leve |

No Claude, o `model_id` é o **apelido** (`opus`, `sonnet`, `haiku`), que o Claude Code resolve para o modelo mais novo
da família. No Codex é o ID exato, e o `metrics.md` grava o modelo que a sessão realmente usou.

## Contrato de saída

Todo agente termina com **um** bloco JSON:

```json
{
  "state": "<um dos estados do agente>",
  "files_changed": [],
  "commands": ["<comandos exatos que rodou>"],
  "errors": [],
  "questions": [],
  "approvals": [],
  "notes": []
}
```

O `state` decide o próximo passo ([workflow.md](workflow.md#como-o-próximo-passo-é-escolhido)). `questions`: o que
bloqueia, com opções. `approvals`: ações travadas propostas (comando ou texto exato) para o orquestrador pedir o seu OK.

| Agente | Estados |
|---|---|
| explorer | `exploration_complete`, `environment_blocked` |
| planner | `plan_ready`, `plan_has_open_questions`, `plan_needs_exploration` |
| coder | `implementation_complete`, `implementation_failed`, `environment_blocked`, `implementation_has_open_questions`, `policy_requires_approval` |
| reviewer | `review_findings`, `review_approved`, `pr_review_done` (modo PR) |
| qa | `test_plan_ready`, `test_plan_has_open_questions` (plan); `tests_passed`, `tests_failed`, `manual_test_required`, `test_adjustment_needed`, `environment_blocked`, `policy_requires_approval` (test) |
| documenter | `task_complete`, `pr_ready`, `environment_blocked`, `policy_requires_approval` |

## O que um agente recebe

O `apply`/`install` monta a definição de cada agente em camadas:

1. `agents/<papel>/AGENT.md` do núcleo: ROLE, INPUT, PROCESS, OUTPUT e RULES.
2. As políticas do núcleo (`orchestrator/policies/`) e as do contexto (`contexts/<nome>/policies/`).
3. O que o contexto inclui para o papel (`[agents.<papel>] include`).
4. A lista de referências do papel (`reference`), com o momento de ler cada uma; o conteúdo **não** entra no prompt.
5. Os *Systems* do contexto: repositórios, stack, comandos de build e teste.
6. As skills do papel (núcleo e contexto); as de `preload` já vêm carregadas.
7. A regra de idioma: os relatórios saem no idioma do contexto.

Na delegação, o orquestrador passa só caminhos: o plano e a entrega, o relatório anterior, uma tarefa curta quando há.
Quanto menos um agente precisa procurar, menos ele gasta.

## Ligar e desligar agentes

```toml
[agents.qa]
enabled = false           # o orquestrador nunca delega a ele e faz a etapa ele mesmo, barato, ou pula
```

Com o explorer ou o planner desligados, o orquestrador faz a etapa ele mesmo. O orquestrador não pode ser desligado. Uma
config antiga com `[agents.api-db]`, `[agents.bug-hunter]` ou `[agents.security]` (papéis que saíram) é aceita com
aviso. Nomes que colidem com agentes do CLI (`plan`, `explore`, `default`, `general-purpose`…) são recusados.

## Criar um agente

1. `agents/<papel>/AGENT.md` com frontmatter `tools` e `description`, e as seções ROLE, INPUT, PROCESS, OUTPUT (com os
   valores de `state`) e RULES.
2. Os estados novos em `[rules]` do `orchestrator/config/routing.toml`.
3. O papel em `DEFAULT_AGENTS`, `DEFAULT_NAMES` e `RUN_PROFILE` do `aidw.py` (tier e effort, nome, perfil headless).
4. As exceções, se houver, em `[[effort.variants.<papel>]]`.
5. `[agents.<papel>]` no `aidw.config.example.toml` e, se fizer sentido, os MCPs no `config/mcp.toml`.
6. `python tests/run.py` e `python aidw.py install`.
