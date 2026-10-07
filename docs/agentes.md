# Agentes

Um agente é um **papel** com uma definição (`agents/<papel>/AGENT.md`), um modelo, um effort, ferramentas e skills.
O orquestrador é o chat principal; os outros são **subagentes nativos** do provedor (a ferramenta `Agent` no Claude,
`spawn_agent` no Codex), cada um num contexto novo a cada delegação.

## Papel × nome

O **papel** é fixo e é o que o AiDW usa internamente (`coder`, `reviewer`…). O **nome** é o que aparece para você
(`codificador`, `revisor`…) e pode ser trocado no `aidw.config.toml`. No plugin do Claude os agentes se chamam
`aidw:<nome>`; no Codex, `aidw-<nome>`.

| Nome padrão | Papel | Ferramentas | Escreve código? |
|---|---|---|---|
| `orquestrador` | `orchestrator` | as do chat | não (só quando você pede, ou em manutenção do AiDW) |
| `explorador` | `explorer` | leitura, shell, grava o relatório | não |
| `planejador` | `planner` | leitura, shell, grava o plano e as tarefas | não |
| `codificador` | `coder` | leitura, edição, shell | **sim**, só no worktree |
| `revisor` | `reviewer` | leitura, shell, grava a revisão | não |
| `api` | `api-db` | leitura, shell (sem gravar arquivos) | não |
| `documentador` | `documenter` | leitura, edição, shell | só documentação |
| `bugs` | `bug-hunter` | leitura, shell, grava o relatório | não |
| `seguranca` | `security` | leitura, shell, grava o relatório | não |
| `qa` | `qa` | leitura, shell, navegador (Claude in Chrome ou `@Chrome` no Codex, Playwright), grava o plano de testes, o relatório e o roteiro | não (pede ajustes ao codificador) |

Além disso, cada papel recebe os servidores MCP que `config/mcp.toml` libera para ele (Playwright para quem testa
tela, Figma para quem implementa layout, Context7 para todos…) e as ferramentas que o contexto bloqueia saem da
lista (`disallowed_tools`; por exemplo, só o orquestrador comenta no card, e só depois do seu OK).

## O que cada um faz

### Orquestrador
Conduz a demanda de ponta a ponta: entende o card, encomenda a exploração e o plano, escolhe nível e effort de cada
delegação, escreve as tarefas que não são do planejador, aplica as regras de `routing.toml`, tria as revisões,
resolve sozinho o que pode e junta numa pergunta o que precisa de você. Monta a revisão final. Usa o modelo
selecionado no chat (recomendado: Opus, effort high).

### Explorador
O "leitor barato". Recebe perguntas numeradas ("onde a validação do CPF acontece?", "qual o contrato do endpoint
X?") e responde cada uma com `arquivo:linha`. Não desenha a solução nem altera código. O relatório
`exploracao-<assunto>.md` fica na pasta da demanda e é reusado pelo plano, pelas tarefas e pelas correções: **uma
exploração por assunto, nunca repetida**. Haiku na maioria dos níveis: ler e citar é barato e não precisa de um
modelo grande.

No **modo levantamento** (workflow `levantamento`), recebe o resumo e os pontos numerados do card em vez de perguntas:
valida cada ponto no código, mapeia o fluxo de ponta a ponta e devolve os sinais de tamanho e as dúvidas que o código
não responde. Continua só levantando fatos: quem estima é o orquestrador.

### Planejador
Três modos, sempre num agente novo:
- **spec:** escreve o `plano-<id>.md` a partir do resumo e da exploração (skill `to-spec`, pré-carregada): comportamento
  atual verificado, desejado, critérios de aceite, checklists, riscos, nível e passadas extras.
- **fix:** recebe o plano e a revisão dele e grava a nova versão.
- **tickets:** corta o plano aprovado em tarefas autocontidas, uma por ticket, com arquivos em escopo e `arquivo:linha`,
  o comando de build e as regras do projeto.

Se precisa de código que não conhece, devolve `plan_needs_exploration` com as perguntas; o orquestrador manda ao
explorador e chama um planejador novo. Opus: o plano decide o custo de todas as etapas seguintes.

### Codificador
Implementa **um ticket por vez** no worktree: entende, planeja dentro do escopo, implementa seguindo as convenções do
projeto, roda **só** os comandos de build e teste que a tarefa dá, revisa o próprio diff e grava o patch. Num
bloqueio de ambiente, reporta o comando e o erro exatos e para, sem gambiarra. Se o `qa` estiver desligado, o bloco
`validation` do resultado é a etapa de teste.

**Testes no código só onde o ponta a ponta não enxerga.** Um fluxo cuja falha aparece na tela ou na resposta da API
não ganha teste unitário: o QA já pega. Ganha teste o passo interno que nunca chega ao cliente: um cálculo, um
mapeamento, uma transição de estado, um retry/timer, um dado gravado e não exibido, um erro engolido no log. O plano
de testes lista esses passos (*Testes no código*) e o ticket diz quais são dele.

**Ajuste de teste** (a pedido do QA): mudança temporária para testar, como pular uma validação, forçar uma flag,
mockar uma dependência ou apontar o front para QA. Cada bloco leva a marca `AIDW-TESTE` e todos ficam num patch só,
`ambiente-teste-<id>.patch`, registrado em `ambiente-teste-<id>.md`. O orquestrador aplica o patch para testar e o
reverte ao fim de cada teste; a revisão e o commit nunca o veem.

### Revisor
Revisa o **plano** e o plano de testes (confere cada `arquivo:linha`, o comportamento atual e o card) e o **diff** (contra spec, ticket,
checklist e as convenções do contexto). Devolve achados com IDs estáveis e severidade (CRITICO, IMPORTANTE,
SUGESTAO). Não altera código. Usa a skill `code-review` (pré-carregada) e `verificar-premissa`.

No **modo PR** (a PR de outra pessoa, workflow `pr-review`), cada achado que vale contar ao autor vem com o rascunho do
comentário (arquivo, linha, lado do diff e texto de até ~5 linhas), e a revisão traz um voto sugerido. Ele nunca
comenta, vota nem conclui a PR: isso é do orquestrador, com o seu OK.

### API
Opera os ambientes de desenvolvimento e qualidade: consulta APIs, banco (só leitura, pelo validador do contexto) e
logs; gera ou ajusta dados de teste, descobre ids, investiga integrações. **Toda escrita é proposta** com o comando
exato e só executa depois do seu OK (skill `database-safe`).

### Documentador
Atualiza README, ARCHITECTURE, changelog e docs de API a partir do diff **aprovado** e redige work items (US,
dívida técnica) para você confirmar. Com o `qa` desligado, também gera o plano de testes.

### Bugs e Segurança (sob demanda)
- **bugs:** procura defeitos de comportamento reais, cada um com um cenário de falha concreto, ou acha a causa-raiz de
  um bug reportado (skill `bug-hunt`).
- **seguranca:** procura vulnerabilidades exploráveis (injeção, autenticação/autorização, segredos, criptografia,
  dados pessoais, dependências), cada uma com o caminho de ataque (skill `security-audit`).

Só entram quando um gatilho se aplica, uma vez por demanda, em paralelo com a 1ª revisão ([fluxo.md](fluxo.md#passadas-extras)).

### QA
Entra **sempre que a demanda é testada**, em dois momentos:

1. **Plano de testes** (modo `plan`, logo depois do plano do planejador): grava `plano-testes-<id>.md` com a forma
   de provar cada critério de aceite:
   - `auto-api`: chamadas na API local ou de DEV/QA;
   - `auto-browser`: a tela de ponta a ponta, pelo seu Chrome já logado (Claude in Chrome; no Codex, `@Chrome`) ou pelo
     Playwright;
   - `auto-suite`: um teste que já existe;
   - `manual`: o que não dá para rodar aqui, como desktop/WPF.

   Ele lista também os **testes no código** (o que o ponta a ponta não pega) e os **ajustes de teste**. O revisor
   confere o plano de testes junto com o plano, e o planejador usa os dois para cortar os tickets.
2. **Teste da entrega** (modo `test`, depois da implementação):
   - roda a suíte e os critérios automáticos com evidência;
   - quando precisa de um ajuste no código, devolve `test_adjustment_needed` e o codificador aplica;
   - se o subagente não consegue usar o navegador, ele devolve `orchestrator_test_needed`: o orquestrador executa
     esses critérios no navegador dele, seguindo o plano de testes, e um QA novo (modo `verify`) confere a
     evidência. Os dois vereditos vão para você numa tabela, e cada divergência ou dúvida é debatida com você, que
     dá a palavra final;
   - o que é manual vira `roteiro-testes-<id>.md`.

   Depois da revisão aprovada, o orquestrador mostra o roteiro **um passo por vez**: o que fazer, o resultado
   esperado e a evidência a mandar. Você executa e manda a evidência, ele confere e registra, e segue até o fim. Um
   passo que falha vira correção do codificador, revisão só da correção e um novo teste só daquele passo.

Não corrige nem edita código. Uma chamada que muda estado no ambiente continua passando pela sua aprovação, uma por
vez.

## Modelo e effort por nível

A tabela vem de `[effort.levels]` em `orchestrator/config/routing.toml` (Claude; no Codex, o equivalente):

| Agente | trivial | simples | padrao | complexa | critica |
|---|---|---|---|---|---|
| planejador | não roda | Sonnet high | Opus medium | Opus high | Opus high |
| explorador | Haiku | Haiku | Haiku | Sonnet medium | Sonnet high |
| codificador | Sonnet high | Sonnet high | Opus medium | Opus high | Opus high |
| revisor | Sonnet high | Sonnet high | Opus medium | Opus high | Opus high |
| bugs · seguranca | Sonnet low | Sonnet medium | Sonnet high | Opus high | Opus high |
| api | Haiku | Sonnet low | Sonnet medium | Sonnet high | Sonnet high |
| documentador | Haiku | Haiku | Haiku | Sonnet medium | Sonnet medium |
| qa | Sonnet low | Sonnet low | Sonnet medium | Sonnet high | Sonnet high |

Por que assim:
- **Ler é barato, decidir é caro.** Explorador e documentador ficam no Haiku; o raciocínio vai para quem planeja,
  codifica e revisa.
- **Sonnet high nas demandas pequenas** custa menos que Opus e acerta mudanças pontuais.
- **Opus medium no padrão** é o ponto de equilíbrio: qualidade de Opus sem o custo do effort alto.
- **Nada acima de `high`:** acima disso o ganho é pequeno e a sessão do plano se esgota rápido.
- **Modelos sem effort** (Haiku) ignoram o valor; ele continua valendo para o equivalente do Codex.

### Equivalência no Codex

A mesma tabela serve aos dois provedores pelo **tier** de cada modelo (`config/models.toml`):

| Claude | Tier | Codex |
|---|---|---|
| Opus | `top` | o modelo top liberado para a conta |
| Sonnet | `mid` | o intermediário |
| Haiku | `fast` | o leve |

O modelo é escolhido entre os liberados para a conta. Um modelo novo liberado no tier passa a ser usado sozinho.

### Versões

No Claude, o `model_id` é o **apelido** (`opus`, `sonnet`, `haiku`), que o Claude Code resolve para o modelo mais
novo da família que a versão instalada conhece. Por isso os nomes aparecem sem versão (`claude-sonnet`): é sempre o
mais recente. No Codex, o `model_id` é o ID exato, e o `metricas.md` grava o modelo que a sessão realmente usou.

### Variantes

No Claude, o effort é fixado no arquivo do subagente. Por isso cada agente existe em **variantes**, uma por
combinação usada na tabela:

```text
aidw:codificador                 ← o modelo e effort padrão do agente
aidw:codificador-high            ← mesmo modelo, effort high
aidw:codificador-sonnet-high     ← outro modelo naquele nível, effort high
```

A tabela *Effort per task* do orquestrador já traz em cada célula o `subagent_type` certo. No Codex, modelo e effort
vão em cada `spawn_agent`, sem variantes.

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
  "mcp_used": [],
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
| planejador | `spec_ready`, `plan_has_open_questions`, `plan_needs_exploration`, `tickets_ready` |
| codificador | `implementation_complete`, `implementation_failed`, `environment_blocked`, `ticket_has_open_questions`, `policy_requires_approval` |
| revisor | `review_approved`, `review_changes_requested`, `review_has_open_questions`, `plan_review_approved`, `plan_review_changes_requested`, `plan_review_has_open_questions`, `pr_review_done` (modo PR) |
| api | `task_complete`, `policy_requires_approval`, `environment_blocked` |
| documentador | `docs_complete`, `environment_blocked`, `policy_requires_approval` |
| bugs · seguranca | `audit_clean`, `audit_findings`, `audit_has_open_questions` |
| qa | `test_plan_ready`, `test_plan_has_open_questions` (plan); `tests_passed`, `tests_failed`, `manual_test_required`, `test_adjustment_needed`, `orchestrator_test_needed`, `environment_blocked`, `policy_requires_approval` (test e verify) |

## O que um agente recebe

A definição final de cada agente é montada pelo `apply`/`install`, em camadas:

1. `agents/<papel>/AGENT.md` do núcleo: ROLE, INPUT, PROCESS, OUTPUT e RULES.
2. As políticas do núcleo (`orchestrator/policies/`) e do contexto (`contexts/<nome>/policies/`).
3. O que o contexto inclui para o papel (`[agents.<papel>] include`): regras do time, guias.
4. A lista de referências do papel (`reference`), com o momento de ler cada uma; o conteúdo **não** entra no prompt.
5. *Systems* do contexto: repositórios, stack, build e teste de cada sistema.
6. As skills do papel (do núcleo e do contexto); as de `preload` já vêm carregadas.

E na hora da delegação, o arquivo de tarefa: spec, ticket, arquivos com `arquivo:linha`, o comando de build e as
regras. **Quanto menos um agente precisa procurar, menos ele gasta.**

## Ligar, desligar e trocar

No `aidw.config.toml` ([configuracao.md](configuracao.md)):

```toml
[agents.qa]
enabled = false           # desliga o qa (o teste volta a ser o `validation` do codificador)

[agents.bug-hunter]
enabled = false           # o orquestrador nunca delega a ele

[agents.coder]
name = "dev"              # passa a se chamar aidw:dev
model = "sonnet"          # modelo padrão do papel (a tabela por nível continua valendo onde dá outro modelo)
effort = "medium"
```

Com o explorador ou o planejador desligados, o orquestrador faz a etapa ele mesmo (skill `to-spec`, a exploração mais
barata disponível). O orquestrador não pode ser desligado. Depois de mudar: `python aidw.py install` e um chat novo.

## Criar um agente

1. `agents/<papel>/AGENT.md` com frontmatter `tools` e `description`, e as seções ROLE, INPUT, PROCESS, OUTPUT (com os
   valores de `state`) e RULES.
2. Os estados novos em `[rules]` de `orchestrator/config/routing.toml`, com a ação de cada um.
3. O papel em `DEFAULT_AGENTS`, `DEFAULT_NAMES` e `RUN_PROFILE` do `aidw.py` (tier padrão, nome, ferramentas).
4. O modelo e effort em cada nível de `[effort.levels]`, ou `"none"` onde ele não roda.
5. `[agents.<papel>]` no `aidw.config.example.toml` e, se fizer sentido, os MCPs em `config/mcp.toml`.
6. `python aidw.py apply`, `python -m unittest discover -s tests` e `python aidw.py install`.

Nomes que colidem com agentes do CLI (`plan`, `explore`, `default`…) são recusados.
