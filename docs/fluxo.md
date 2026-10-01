# O fluxo de uma demanda

Este documento explica o que acontece entre o `/aidw:orquestrar 1234` e a revisão final: as etapas, quem faz cada
uma, como o orquestrador decide o próximo passo, como escolhe modelo e effort, e o que fica gravado.

## A ideia central

Um chat único que faz tudo (lê o código, planeja, codifica, se revisa) acumula contexto: no fim da demanda ele
carrega centenas de linhas lidas no começo, fica caro a cada mensagem e erra mais. O AiDW separa os papéis:

- O **orquestrador** é o chat principal. Ele **decide e coordena**, mas não lê código para planejar nem implementa.
  O contexto dele fica pequeno a demanda inteira.
- Cada etapa roda num **agente novo** (um subagente nativo do provedor), que recebe **um arquivo de tarefa**
  autocontido, faz o trabalho, grava o resultado na pasta da demanda e devolve um JSON com um `state`.
- Os agentes não veem a conversa nem falam com você. Tudo que eles precisam está na tarefa; tudo que eles
  produzem está num arquivo que o próximo agente recebe **por caminho**, sem colar conteúdo.
- Cada agente roda no **modelo e effort que a etapa merece**: ler código é Haiku, planejar e codificar o difícil é
  Opus. Isso é o que mantém a qualidade alta e o custo baixo.

## Etapas

```text
Entender → Explorar → Planejar → Revisar o plano ⇄ Corrigir o plano → Tickets → Implementar → Testar
        → Preparar a revisão → Revisar ⇄ Corrigir (+ bugs/segurança) → Documentar → Revisão final → Concluir
```

| Etapa | Agente | Entrada | Saída |
|---|---|---|---|
| **Entender** | orquestrador | o card (id, link ou descrição) | `resumo-<id>.md`: campos e critérios de aceite, decisões dos comentários com autor e data, itens ligados que importam, trabalho já existente (tasks, branch, PR) |
| **Explorar** | explorador | perguntas numeradas que o plano precisa (onde a mudança vai, o comportamento atual, o contrato de cada dependência) | `exploracao-<assunto>.md`, com `arquivo:linha` em cada resposta |
| **Planejar** (modo spec) | planejador | resumo + exploração + nível provisório | `plano-<id>.md` v1: comportamento atual verificado, desejado, critérios de aceite, checklists, riscos, **nível**, passadas extras |
| **Revisar o plano** | revisor | o plano | `revisao-plano-<id>-r<N>.md`, achados `P<N>-<nn>`. Só do nível `padrao` para cima |
| **Corrigir o plano** (modo fix) | planejador | plano + revisão | nova versão do plano; um revisor **novo** revisa só as mudanças |
| **Tickets** (modo tickets) | planejador | plano aprovado | uma `tarefa-<agente>-<assunto>.md` por ticket |
| **Implementar** | codificador | uma tarefa | código e testes no worktree, build, `diff-<ticket>-r<N>.patch` |
| **Testar** | qa, ou o bloco `validation` do codificador | o diff | build, typecheck, testes, lint (`passed`/`failed`/`skipped`) |
| **Preparar a revisão** | orquestrador | o diff | `checklist-revisao.md` (o contexto pode definir o conteúdo) |
| **Revisar** | revisor (+ bugs, seguranca) | spec + ticket + diff + checklist | `review-<id>-r<N>.md`, achados `R<N>-<nn>` com severidade |
| **Triar** | orquestrador | a revisão | `triagem-<id>-r<N>.md`: o que corrige, o que registra, o que pergunta |
| **Corrigir** | codificador | a revisão + a triagem | novo diff `r<N+1>`; um revisor **novo** revisa só as correções |
| **Documentar** | documentador | o diff aprovado | docs atualizadas e plano de testes |
| **Revisão final** | **você** | `revisao-final.md` | um pacote só: o que mudou, a revisão final, as ações que esperam o seu OK |

### Atalhos por tamanho

- **`trivial`:** sem plano. O orquestrador vai direto para a tarefa.
- **`simples`:** sem revisão do plano. Se o card já aponta os arquivos, sem exploração: o planejador lê os arquivos.
- **Workflow por tipo:** `workflows/feature.yaml`, `bugfix.yaml`, `refactor.yaml` e `hotfix.yaml` listam as etapas de
  cada tipo de demanda. O hotfix, por exemplo, reproduz e corrige sem plano, mas mantém revisão e aprovação humana.
  Etapas de agente desligado são puladas (ou feitas pelo orquestrador).

## Como o orquestrador decide o próximo passo

Todo agente termina com um bloco JSON e um `state`. O orquestrador procura esse `state` em `[rules]` de
`orchestrator/config/routing.toml` e aplica a ação. É **determinístico**: nenhum agente escolhe o próximo passo.

| `state` | Ação | Significado |
|---|---|---|
| `existing_work_found` | `HUMAN_APPROVAL` | já há trabalho no card: continuação, correção ou retrabalho? |
| `plan_has_open_questions` | `HUMAN_APPROVAL` | dúvida real ou mais de um caminho válido |
| `plan_needs_exploration` | `EXPLORE` | o planejador precisa de código que não conhece: explorador, depois um planejador novo |
| `spec_ready` | `PLAN_REVIEW` | plano pronto (trivial/simples pulam para `TICKETS`) |
| `plan_review_approved` · `plan_review_changes_requested` | `TICKETS` · `PLAN_FIX` | |
| `tickets_ready` | `IMPLEMENT` | |
| `implementation_complete` · `implementation_failed` | `TEST` · `CODER_FIX` | |
| `environment_blocked` | `HUMAN_APPROVAL` | ferramenta, pacote, permissão ou rede; só quando o orquestrador não consegue resolver |
| `ticket_has_open_questions` | `HUMAN_APPROVAL` | o plano não serve para o código |
| `tests_passed` · `tests_failed` | `PREPARE_REVIEW` · `CODER_FIX` | |
| `review_approved` · `review_changes_requested` | `DOCS` · `CODER_FIX` | |
| `task_complete` · `exploration_complete` · `audit_clean` · `audit_findings` | `RETURN` | agentes de apoio voltam para a etapa que os chamou |
| `docs_complete` | `FINAL_REVIEW` | |
| `policy_requires_approval` | `HUMAN_APPROVAL` | ação travada proposta (commit, push, SQL de escrita) |
| `max_retries_exceeded` | `HUMAN_APPROVAL` | o laço não convergiu |

- Um `state` ausente ou desconhecido é falha: o orquestrador delega de novo pedindo só o JSON.
- `max_retries` (padrão 3) conta as rodadas de cada laço: explorar ⇄ planejar, revisar plano ⇄ corrigir plano,
  revisar ⇄ corrigir. Esgotou, ele para e leva para você.
- `environment_blocked` **não é falha do agente**: o orquestrador não escala nem refaz. Ele resolve o ambiente
  quando consegue (ex.: uma junction faltando) ou para e pergunta.

## Níveis, modelo e effort

O orquestrador classifica a demanda no plano (`Nível: <nível> — <motivo>`). O nível que o planejador devolve vale
para a demanda dali em diante. Um ticket pode ter outro nível quando o escopo dele claramente cabe em outro.

| Nível | Quando |
|---|---|
| `trivial` | leitura ou consulta sem decisão: levantar arquivos, descobrir um id, ajuste de texto |
| `simples` | mudança pontual de baixo risco: 1–2 arquivos, sem contrato entre sistemas, banco, concorrência ou segurança |
| `padrao` | o caso comum: feature ou bug num sistema, alguns arquivos, regra de negócio |
| `complexa` | vários sistemas ou contrato entre eles, concorrência, polling, script de banco, segurança, legado frágil |
| `critica` | excepcional: falhou duas vezes em complexa, correção de segurança/produção, migração irreversível |

Cada nível define, por agente, o **modelo e o effort** (tabela em [agentes.md](agentes.md#modelo-e-effort-por-nível)).
As regras de ajuste:

- **Na dúvida entre dois níveis, o menor.** Subir depois custa menos que gastar demais sempre.
- **Sobe um nível** na próxima tentativa quando: o agente falhou duas vezes na mesma etapa, a revisão achou
  CRITICO, ou o resultado mostra que a tarefa é mais difícil que o nível.
- **Desce um nível** nos acompanhamentos: re-revisão só das correções, nova rodada de build/teste, pergunta pontual.
  Nunca abaixo do menor nível em que o agente roda.
- **Nada acima de `high`.** Acima disso o ganho é pequeno e a sessão se gasta rápido.
- O orquestrador **nunca troca o modelo sozinho**: só quando você pede ou a tabela dá outro modelo ao nível.

## Revisão e triagem

A revisão é o que segura a qualidade. Ela segue regras fixas:

- O revisor recebe spec, ticket, diff (arquivo) e checklist, e devolve achados com **IDs estáveis** (`R1-01`…) e
  severidade: **CRITICO**, **IMPORTANTE** ou **SUGESTAO**.
- **CRITICO/IMPORTANTE:** corrigir dentro do escopo sempre que houver correção possível no código em escopo. Só sai
  do escopo se exigir outro sistema ou contrato, e aí vira um rascunho de dívida técnica.
- **SUGESTAO:** aplicar se for barata e nos arquivos em escopo; senão, registrar.
- **Dúvida, mais de um caminho, decisão do tech lead:** uma pergunta só a você; o resto do ciclo segue.
- Antes de aceitar "não dá para corrigir aqui", "cobre todos os casos", "não é regressão" ou de rebaixar um
  CRITICO/IMPORTANTE, o orquestrador usa a skill `verificar-premissa`, com a evidência na triagem.
- Cada rodada nova é um **revisor novo** com só a revisão anterior e o diff das correções: ele não herda o viés de
  quem revisou antes, e o custo cai porque o escopo é menor.
- O ciclo termina com zero CRITICO/IMPORTANTE, ou quando `max_retries` acaba (aí é "fora do plano").

### Passadas extras

`bugs` (defeitos de comportamento, causa-raiz) e `seguranca` (vulnerabilidades exploráveis) não rodam em toda
demanda. O plano registra `Passadas extras: bugs sim/não — <motivo>; segurança sim/não — <motivo>`, com os gatilhos
de `orchestrator/reference/passadas-extras.md` (concorrência, timers, legado frágil, autenticação, dados pessoais,
dependências…). Quando decididas, rodam **em paralelo com a 1ª revisão**, e os achados entram na mesma triagem.

## Quando você é chamado

O orquestrador interrompe **só** para:

1. **Ação travada:** commit, push, merge, SQL de escrita, chamada de API que muda estado. O agente propõe o comando
   exato; o orquestrador junta as propostas e pede o OK uma vez.
2. **Dúvida real ou mais de um caminho válido:** uma pergunta, com opções, a recomendação e o porquê.
3. **Algo fora do plano:** escopo maior, ambiente bloqueado, voltas esgotadas.
4. **A revisão final**, uma vez.

Decisões pendentes vão juntas numa pergunta só. No modo `interativo`, ele também para antes dos tickets e antes de
cada delegação.

## O que fica gravado

Tudo da demanda fica na pasta `<pasta de estado>/<tipo>-<id>/` (a pasta de estado vem do contexto):

| Arquivo | Conteúdo |
|---|---|
| `demand.json` | etapa, status (`active`/`paused`/`done`), modo, repositórios, histórico das etapas |
| `resumo-<id>.md` | o card resumido, para nenhum agente reler o card |
| `exploracao-<assunto>.md` | as respostas do explorador, reusadas pelo plano e pelas tarefas |
| `plano-<id>.md` · `revisao-plano-<id>-r<N>.md` | o plano versionado e as revisões dele |
| `tarefa-<agente>-<assunto>.md` | cada delegação |
| `diff-<ticket>-r<N>.patch` · `review-<id>-r<N>.md` · `triagem-<id>-r<N>.md` | cada rodada do ciclo |
| `checklist-revisao.md` · `revisao-final.md` | preparação e pacote final |
| `metricas.md` | uma linha por delegação: agente, nível, modelo, effort, tokens, ferramentas, duração |

### Métricas

Depois de cada subagente, o orquestrador roda `aidw.py record` com os números reais do resultado (tokens, chamadas de
ferramenta, duração). Isso grava a linha no `metricas.md` e imprime o cabeçalho e o resumo que aparecem no chat. Os
números **nunca são estimados**: são a base para ajustar a tabela de níveis com dados.

### Retomar

`/aidw:sair` grava a etapa e o próximo passo (`paused`). Depois, `/aidw:orquestrar` sem argumento na pasta do worktree
ou do repositório acha a demanda e continua da etapa gravada. `python aidw.py open --demand <id>` faz o mesmo pelo
terminal. Depois de uma compactação da conversa, um hook lembra o orquestrador de reler as regras.

### Concluir

`/aidw:done` fecha a tarefa: grava no contexto só o que foi **verificado** e vale para as próximas demandas (comando de
build que funcionou, bloqueio de ambiente e como destravar, armadilha do código, convenção), valida, reinstala e faz
commit e push **só do repositório do contexto**. É assim que o contexto melhora a cada demanda.
