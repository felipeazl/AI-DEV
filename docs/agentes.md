# Agentes

Um agente é um **papel** com uma definição (`agents/<papel>/AGENT.md`), um modelo, um effort, ferramentas e skills.
O orquestrador é o chat principal; os outros são **subagentes nativos** do provedor (a ferramenta `Agent` no Claude,
`spawn_agent` no Codex), cada um num contexto novo a cada delegação.

No fluxo v3 (2026-10-23) são sete: orquestrador, explorador, planejador, codificador, revisor, qa e documentador. Os
antigos `api`, `bugs` e `seguranca` saíram: as consultas do api ficaram com o explorador e o qa, e o revisor cobre
qualidade, bugs e segurança numa passada.

## Papel × nome

O **papel** é fixo e é o que o AiDW usa internamente (`coder`, `reviewer`…). O **nome** é o que aparece para você
(`codificador`, `revisor`…) e pode ser trocado no `aidw.config.toml`. No plugin do Claude os agentes se chamam
`aidw:<nome>`; no Codex, `aidw-<nome>`.

| Nome padrão | Papel | Ferramentas | Escreve código? |
|---|---|---|---|
| `orquestrador` | `orchestrator` | as do chat | não (só quando você pede, ou em manutenção do AiDW) |
| `explorador` | `explorer` | leitura, shell (SELECT pelo validador do contexto), grava o relatório | não |
| `planejador` | `planner` | leitura, shell, grava o plano | não |
| `codificador` | `coder` | leitura, edição, shell | **sim**, só no worktree |
| `revisor` | `reviewer` | leitura, shell, grava a revisão | não |
| `qa` | `qa` | leitura, shell, navegador (Claude in Chrome, Playwright, Chrome DevTools; no Codex, `@Chrome`), grava o roteiro e o relatório | não (pede ajustes ao codificador) |
| `documentador` | `documenter` | leitura, edição, shell, board | só texto (Tasks, PR) |

Cada papel recebe também os servidores MCP que `config/mcp.toml` libera para ele, e as ferramentas que o contexto
bloqueia saem da lista (`disallowed_tools`; por exemplo, nenhum agente comenta no card).

## O que cada um faz

### Orquestrador
Conduz a demanda de ponta a ponta: entende o card, encomenda a exploração e o plano, **lê o plano** e o leva à sua
aprovação, dispara em paralelo o código, as Tasks e o roteiro de testes, leva os achados da revisão a você, pilota os
passos manuais do teste e, com o seu OK, faz o commit, o push e abre a PR. Usa o modelo selecionado no chat
(recomendado: Opus, effort medium). O contexto dele é o maior custo da demanda, então ele lê arquivo só quando precisa
decidir algo dele.

### Explorador
O "leitor barato". Recebe perguntas numeradas ("onde a validação do CPF acontece?", "qual o contrato do endpoint
X?", "qual protocolo de QA está no status 2?") e responde com `arquivo:linha` ou com a consulta que prova. Faz as
consultas de leitura que eram do api: ids, enums, dado real por SELECT pelo validador do contexto, chamada de API que
não muda estado. Não desenha a solução, não altera código nem dado. O relatório `exploracao-<assunto>.md` é reusado
pelo plano. Haiku; Sonnet só nas exceções (refazer quando o Haiku errou, o levantamento).

No **modo levantamento**, recebe o resumo e os pontos numerados do card: valida cada ponto no código, mapeia o fluxo
de ponta a ponta e devolve os sinais de tamanho e as dúvidas que o código não responde.

### Planejador
Escreve o `plano-<id>.md` (skill `to-spec`, pré-carregada): um plano **spec-driven, simples e autossuficiente** —
premissas verificadas, comportamento atual e desejado, os critérios de aceite e as regras de negócio do card (`CA1`,
`RN1`, com o texto do card), e as **entregas** `E1`, `E2`… Cada entrega é o que um codificador termina numa passada
e vira uma Task: os arquivos com `arquivo:linha` e o que muda em cada um, os critérios que cobre, os testes de código
que precisa, a doc do repositório que fica desatualizada, o worktree e o build. O plano é a tarefa do codificador.

No **modo fix**, aplica os ajustes que você pediu na aprovação e grava a versão nova. Se precisa de código que não
conhece, devolve `plan_needs_exploration` com as perguntas. Sonnet high.

### Codificador
Implementa **uma entrega por vez** no worktree: lê o plano e os arquivos da entrega, implementa seguindo as convenções
do projeto, atualiza a doc do repositório que a entrega cita, roda **só** os comandos de build e teste do plano,
revisa o próprio diff e grava o patch. Num bloqueio de ambiente, reporta o comando e o erro exatos e para. Não faz
commit: a entrega fica no worktree até a etapa PR. Sonnet high; medium nas correções pequenas.

**Testes no código só onde o ponta a ponta não enxerga:** um cálculo, um mapeamento, uma transição de estado, um
retry/timer, um dado gravado e não exibido, um erro engolido no log. O plano diz quais.

**Ajuste de teste** (a pedido do QA): mudança temporária para testar, marcada com `AIDW-TESTE`, num patch só
(`ambiente-teste-<id>.patch`). O orquestrador aplica para testar e reverte depois; a revisão e o commit nunca o veem.

### Revisor
Revisa o **diff** de cada entrega contra o plano numa passada (skill `code-review`, pré-carregada):
- **qualidade**: os padrões do time (no safeweb, o Guideline) e as convenções do repositório;
- **bugs**: defeitos reais, cada um com o cenário de falha rastreável no código;
- **segurança**: vulnerabilidades exploráveis, cada uma com o caminho de ataque.

Cada achado tem ID estável, severidade, categoria, a correção mínima dentro do escopo, o código antes e depois e a
**recomendação** (manter ou descartar, e por quê): você decide cada um. Na re-revisão, confere só os achados mantidos e
as regressões. Não altera código. Sonnet high; medium/low na re-revisão.

No **modo PR** (a PR de outra pessoa), cada achado que vale contar ao autor vem com o rascunho do comentário; ele não
sugere voto (aprovar a PR é escolha sua). Ele nunca comenta, aprova nem conclui a PR.

### QA
Entra em dois momentos:

1. **Roteiro e massa** (modo `plan`, em paralelo com o codificador, logo depois da sua aprovação do plano): grava
   `roteiro-testes-<id>.md` com cada `CA`/`RN`, os passos, o resultado esperado, a evidência e como provar —
   `auto-api`, `auto-browser` (Claude in Chrome para tela com login, Playwright para E2E sem sessão), `auto-suite` ou
   `manual`. Levanta a massa: acha os registros que já existem e lista em *Aprovações* o que precisa ser criado ou
   alterado, para você aprovar enquanto o código é escrito.
2. **Teste da entrega** (modo `test`, depois da sua revisão de código): confere o roteiro contra o diff final, roda as
   escritas aprovadas e os passos automáticos e marca ✅/❌ com a evidência no roteiro. Os passos manuais ficam para você
   executar com o orquestrador; um passo que precisa de ajuste no código volta como `test_adjustment_needed`.

Não corrige nem edita código. Sonnet medium.

### Documentador
- **Board** (depois da sua aprovação do plano): anexa o plano ao card e cria uma Task por entrega, em texto simples e
  direto, sem jargão técnico.
- **PR** (depois dos testes): escreve `pr-<id>.md` com a mensagem de commit, o título e a descrição da PR, os work
  items e as pendências para a QA. Quem faz o commit, o push e abre a PR é o orquestrador, com o seu OK.
- **US e Dívida técnica**, quando pedido (skill `redigir-work-item`).

Haiku.

## Modelo e effort

Não há nível de demanda. Cada agente tem um **padrão** (`aidw.config.toml`) e só as **exceções** de
`[effort.variants]` em `orchestrator/config/routing.toml`, cada uma com o motivo que a permite:

| Agente | Padrão | Exceções (só pelo motivo) |
|---|---|---|
| orquestrador | o chat (recomendado Opus medium) | — |
| explorador | Haiku | Sonnet medium — refazer uma vez quando o resultado não fez sentido; Sonnet high — levantamento |
| planejador | Sonnet high | medium — ajuste do plano que você pediu |
| codificador | Sonnet high | medium — correção pequena ou ajuste temporário de teste |
| revisor | Sonnet high | medium — re-revisão só das correções; low — re-revisão de uma correção trivial |
| qa | Sonnet medium | high — refazer uma vez quando o resultado não fez sentido |
| documentador | Haiku | — |

Por que assim:
- **Ler é barato, decidir é caro.** Explorador e documentador ficam no Haiku; o raciocínio vai para quem planeja,
  codifica e revisa.
- **Uma rodada bem feita custa menos que três rápidas.** Planejador, codificador e revisor rodam em high por padrão; o
  effort desce só no que é pequeno por natureza (a re-revisão de uma correção).
- **Opus só quando você pede.** Nada acima de `high`.
- **Modelos sem effort** (Haiku) ignoram o valor; ele continua valendo para o equivalente do Codex.

Uma exceção nova é uma entrada a mais em `[effort.variants.<papel>]`, com `effort`, `model` (opcional) e `when`. O
contexto pode redefinir a lista de um papel no `contexts/<nome>/routing.toml`.

### Equivalência no Codex

A mesma tabela serve aos dois provedores pelo **tier** de cada modelo (`config/models.toml`):

| Claude | Tier | Codex |
|---|---|---|
| Opus | `top` | o modelo top liberado para a conta |
| Sonnet | `mid` | o intermediário |
| Haiku | `fast` | o leve |

### Versões

No Claude, o `model_id` é o **apelido** (`opus`, `sonnet`, `haiku`), que o Claude Code resolve para o modelo mais
novo da família que a versão instalada conhece. No Codex, o `model_id` é o ID exato, e o `metricas.md` grava o modelo
que a sessão realmente usou.

### Variantes

No Claude, o modelo e o effort são fixados no arquivo do subagente. Por isso cada exceção vira uma **variante**:

```text
aidw:codificador                  ← o padrão (Sonnet high)
aidw:codificador-medium           ← mesmo modelo, effort medium (correção pequena)
aidw:explorador-sonnet-high       ← outro modelo, effort high (levantamento)
```

A tabela *Agents and effort* do orquestrador traz o `subagent_type` de cada uma, e o mod recusa uma variante fora
dela. No Codex, modelo e effort vão em cada `spawn_agent`, sem variantes.

## O contrato de saída

Todo agente termina com **um** bloco JSON. Os campos comuns:

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

- `state` decide o próximo passo ([fluxo.md](fluxo.md#como-o-orquestrador-decide-o-próximo-passo)). Um valor fora da
  lista é falha.
- `questions`: o que bloqueia, com opções. `approvals`: ações travadas propostas (comando ou texto exato) para o
  orquestrador pedir o seu OK.

| Agente | Estados |
|---|---|
| explorador | `exploration_complete`, `environment_blocked` |
| planejador | `plan_ready`, `plan_has_open_questions`, `plan_needs_exploration` |
| codificador | `implementation_complete`, `implementation_failed`, `environment_blocked`, `implementation_has_open_questions`, `policy_requires_approval` |
| revisor | `review_findings`, `review_approved`, `pr_review_done` (modo PR) |
| qa | `test_plan_ready`, `test_plan_has_open_questions` (plan); `tests_passed`, `tests_failed`, `manual_test_required`, `test_adjustment_needed`, `environment_blocked`, `policy_requires_approval` (test) |
| documentador | `task_complete` (board, work item), `pr_ready` (pr), `environment_blocked`, `policy_requires_approval` |

## O que um agente recebe

A definição final de cada agente é montada pelo `apply`/`install`, em camadas:

1. `agents/<papel>/AGENT.md` do núcleo: ROLE, INPUT, PROCESS, OUTPUT e RULES.
2. As políticas do núcleo (`orchestrator/policies/`) e do contexto (`contexts/<nome>/policies/`).
3. O que o contexto inclui para o papel (`[agents.<papel>] include`): regras do time, guias.
4. A lista de referências do papel (`reference`), com o momento de ler cada uma; o conteúdo **não** entra no prompt.
5. *Systems* do contexto: repositórios, stack, build e teste de cada sistema.
6. As skills do papel (do núcleo e do contexto); as de `preload` já vêm carregadas.

E na hora da delegação, os caminhos: o plano e a entrega, o relatório anterior, a tarefa curta quando há uma. **Quanto
menos um agente precisa procurar, menos ele gasta.**

## Ligar, desligar e trocar

No `aidw.config.toml` ([configuracao.md](configuracao.md)):

```toml
[agents.qa]
enabled = false           # desliga o qa (o teste volta a ser o `validation` do codificador)

[agents.coder]
name = "dev"              # passa a se chamar aidw:dev
model = "sonnet"          # modelo padrão do papel
effort = "high"
```

Com o explorador ou o planejador desligados, o orquestrador faz a etapa ele mesmo (skill `to-spec`, a exploração mais
barata disponível). O orquestrador não pode ser desligado. Uma config antiga com `[agents.api-db]`,
`[agents.bug-hunter]` ou `[agents.security]` é aceita com aviso, e esses papéis não são gerados. Depois de mudar:
`python aidw.py install` e um chat novo.

## Criar um agente

1. `agents/<papel>/AGENT.md` com frontmatter `tools` e `description`, e as seções ROLE, INPUT, PROCESS, OUTPUT (com os
   valores de `state`) e RULES.
2. Os estados novos em `[rules]` de `orchestrator/config/routing.toml`, com a ação de cada um.
3. O papel em `DEFAULT_AGENTS`, `DEFAULT_NAMES` e `RUN_PROFILE` do `aidw.py` (tier padrão, nome, ferramentas).
4. As exceções de modelo e effort, se houver, em `[effort.variants.<papel>]`.
5. `[agents.<papel>]` no `aidw.config.example.toml` e, se fizer sentido, os MCPs em `config/mcp.toml`.
6. `python -m unittest discover -s tests` e `python aidw.py install`.

Nomes que colidem com agentes do CLI (`plan`, `explore`, `default`…) são recusados.
