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
Entender → Explorar → Planejar → Plano de testes → Revisar o plano ⇄ Corrigir o plano → Tickets → Implementar
        → Testar (⇄ ajustes de teste) → Preparar a revisão → Revisar ⇄ Corrigir (+ bugs/segurança)
        → Teste manual (se houver roteiro) → Documentar → Revisão final → Concluir
```

| Etapa | Agente | Entrada | Saída |
|---|---|---|---|
| **Entender** | orquestrador | o card (id, link ou descrição) | `resumo-<id>.md`: campos e critérios de aceite, decisões dos comentários com autor e data, itens ligados que importam, trabalho já existente (tasks, branch, PR) |
| **Explorar** | explorador | perguntas numeradas que o plano precisa (onde a mudança vai, o comportamento atual, o contrato de cada dependência) | `exploracao-<assunto>.md`, com `arquivo:linha` em cada resposta |
| **Planejar** (modo spec) | planejador | resumo + exploração + nível provisório | `plano-<id>.md` v1: comportamento atual verificado, desejado, critérios de aceite, checklists, riscos, **nível**, passadas extras |
| **Plano de testes** (modo plan) | qa | resumo + plano | `plano-testes-<id>.md`: como provar cada critério (`auto-api`, `auto-browser`, `auto-suite`, `manual`), os testes no código e os ajustes de teste |
| **Revisar o plano** | revisor | o plano e o plano de testes | `revisao-plano-<id>-r<N>.md`, achados `P<N>-<nn>`. Só do nível `padrao` para cima |
| **Corrigir o plano** (modo fix) | planejador | plano + revisão | nova versão do plano; um revisor **novo** revisa só as mudanças |
| **Tickets** (modo tickets) | planejador | plano aprovado + plano de testes | uma `tarefa-<agente>-<assunto>.md` por ticket, com só os testes de *Testes no código* |
| **Implementar** | codificador | uma tarefa | código e testes no worktree, build, `diff-<ticket>-r<N>.patch` |
| **Testar** (modo test) | qa (desligado: o bloco `validation` do codificador) | plano de testes + diff | `qa-<id>-r<N>.md` com a evidência de cada critério; `roteiro-testes-<id>.md` para o que é manual |
| **Ajustes de teste** | codificador, a pedido do qa | os ajustes | `ambiente-teste-<id>.patch` (marca `AIDW-TESTE`) e `ambiente-teste-<id>.md`; nunca chega ao commit |
| **Preparar a revisão** | orquestrador | o diff | `checklist-revisao.md` (o contexto pode definir o conteúdo) |
| **Revisar** | revisor (+ bugs, seguranca) | spec + ticket + diff + checklist | `review-<id>-r<N>.md`, achados `R<N>-<nn>` com severidade |
| **Triar** | orquestrador | a revisão | `triagem-<id>-r<N>.md`: o que corrige, o que registra, o que pergunta |
| **Corrigir** | codificador | a revisão + a triagem | novo diff `r<N+1>`; um revisor **novo** revisa só as correções |
| **Teste manual** | **você**, com o orquestrador | `roteiro-testes-<id>.md` | um passo por vez: você executa e manda a evidência; ele confere e registra ✅/❌ no roteiro |
| **Documentar** | documentador | o diff aprovado | docs atualizadas (com o qa desligado, também o plano de testes) |
| **Revisão final** | **você** | `revisao-final.md` | um pacote só: o que mudou, a revisão final, as ações que esperam o seu OK |

### Atalhos por tamanho

- **`trivial`:** sem plano. O orquestrador vai direto para a tarefa.
- **`simples`:** sem revisão do plano. Se o card já aponta os arquivos, sem exploração: o planejador lê os arquivos.
- **Workflow por tipo:** `workflows/feature.yaml`, `bugfix.yaml`, `refactor.yaml`, `hotfix.yaml`, `pr-review.yaml` e
  `levantamento.yaml`
  listam as etapas de cada tipo de demanda. O hotfix, por exemplo, reproduz e corrige sem plano, mas mantém revisão e
  aprovação humana; o `pr-review` revisa a PR de outra pessoa ([Revisar a PR de outra pessoa](#revisar-a-pr-de-outra-pessoa))
  e o `levantamento` estima um card antes de implementar ([Levantamento de demanda](#levantamento-de-demanda)).
  Etapas de agente desligado são puladas (ou feitas pelo orquestrador).

## Como o orquestrador decide o próximo passo

Todo agente termina com um bloco JSON e um `state`. O orquestrador procura esse `state` em `[rules]` de
`orchestrator/config/routing.toml` e aplica a ação. É **determinístico**: nenhum agente escolhe o próximo passo.

| `state` | Ação | Significado |
|---|---|---|
| `existing_work_found` | `HUMAN_APPROVAL` | já há trabalho no card: continuação, correção ou retrabalho? |
| `plan_has_open_questions` | `HUMAN_APPROVAL` | dúvida real ou mais de um caminho válido |
| `plan_needs_exploration` | `EXPLORE` | o planejador precisa de código que não conhece: explorador, depois um planejador novo |
| `spec_ready` | `TEST_PLAN` | plano pronto: o qa monta o plano de testes (qa desligado: `PLAN_REVIEW`) |
| `test_plan_ready` · `test_plan_has_open_questions` | `PLAN_REVIEW` · `HUMAN_APPROVAL` | trivial/simples pulam a revisão do plano e vão para `TICKETS` |
| `plan_review_approved` · `plan_review_changes_requested` | `TICKETS` · `PLAN_FIX` | |
| `tickets_ready` | `IMPLEMENT` | |
| `implementation_complete` · `implementation_failed` | `TEST` · `CODER_FIX` | |
| `environment_blocked` | `HUMAN_APPROVAL` | ferramenta, pacote, permissão ou rede; só quando o orquestrador não consegue resolver |
| `ticket_has_open_questions` | `HUMAN_APPROVAL` | o plano não serve para o código |
| `tests_passed` · `tests_failed` | `PREPARE_REVIEW` · `CODER_FIX` | |
| `manual_test_required` | `PREPARE_REVIEW` | a parte automática passou; o roteiro manual roda depois da revisão |
| `test_adjustment_needed` | `TEST_ADJUST` | o codificador aplica o ajuste temporário e um qa novo continua |
| `orchestrator_test_needed` | `ORCHESTRATOR_TEST` | o qa não conseguiu usar o navegador: o orquestrador testa pelo plano, um qa novo confere e as divergências são debatidas com você |
| `review_approved` · `review_changes_requested` | `MANUAL_TEST` · `CODER_FIX` | sem roteiro manual pendente, `MANUAL_TEST` vai direto para `DOCS` |
| `pr_review_done` | `FINAL_REVIEW` | revisão da PR de outra pessoa: triagem e você escolhe o que publicar; nada vai ao codificador |
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

## Testes

O `qa` entra sempre que a demanda é testada ([agentes.md](agentes.md#qa)):

- **Antes dos tickets**, o plano de testes diz como provar cada critério de aceite. Web e API são testados sozinhos:
  por chamadas na API ou pela tela no navegador. Desktop/WPF, e o que mais não dá para rodar aqui, vira roteiro manual.
- **O código só ganha teste onde o ponta a ponta não enxerga:** passos internos que não chegam ao cliente. O plano
  de testes lista esses passos e o ticket diz quais são dele.
- **Ajustes de teste** (pular uma validação, forçar uma flag, mockar, apontar para QA) são pedidos pelo qa e feitos
  pelo codificador, todos num patch marcado com `AIDW-TESTE`:
  - o orquestrador aplica o patch para testar e o reverte ao fim de cada teste;
  - a revisão e o commit sempre veem a entrega sem ele;
  - antes da revisão final, o orquestrador prova que não sobrou nada: a busca pela marca vem vazia e o diff bate com
    o último patch revisado;
  - o hook do AiDW recusa um `git commit` num worktree de demanda que ainda tenha a marca.
- **Sem navegador no subagente:** quando o qa não consegue usar nenhum navegador (Claude in Chrome, `@Chrome` do Codex ou Playwright), o orquestrador
  executa esses critérios no navegador dele, seguindo o plano de testes, e grava a evidência. Um qa novo confere
  cada uma contra o plano. Você recebe uma tabela com os dois vereditos; o que diverge ou ficou em dúvida é debatido
  com você, que fecha cada ponto.
- **Teste manual**, depois da revisão aprovada: o orquestrador mostra o roteiro **um passo por vez**, com o que
  fazer, o que deve acontecer e a evidência a mandar. Você executa e manda a evidência; ele confere, registra no
  roteiro e mostra o próximo. Um passo que falha volta para o codificador e, depois da correção revisada, só esse
  passo (e os que dependem dele) é testado de novo.

## Revisar a PR de outra pessoa

Workflow `pr-review`: o orquestrador revisa a PR que outra pessoa abriu, sem plano, tickets nem correção. Quem corrige
é o autor; você escolhe o que é publicado.

```text
/aidw:orquestrar us-127508 pr 7639 7640     ← o card e as PRs (podem ser de repositórios diferentes)
```

1. **Entender:** o `resumo-<id>.md` traz o card e, por PR, autor, descrição, destino, itens ligados e o que já foi
   comentado.
2. **Worktree da PR:** `aidw.py worktree create --repo <repo> --demand <id> --pr <n>` busca a PR já mesclada no destino
   (`refs/pull/<n>/merge`, no Azure Repos e no GitHub), cria um worktree só leitura e sem branch, com as junctions de
   dependências, e grava `diff-pr<n>-<repo>.patch` na pasta da demanda. O orquestrador roda o build nele uma vez.
3. **Revisão:** um revisor no modo PR, com todas as PRs da demanda. Cada achado vem com o rascunho do comentário
   (arquivo, linha, lado do diff e texto curto) e a revisão traz um voto sugerido (aprovar, aprovar com sugestões ou
   aguardar o autor). Bugs e segurança só quando um gatilho se aplica.
4. **Triagem e revisão final:** o orquestrador confere as premissas e te mostra uma tabela por PR (achado, severidade,
   comentário proposto, se recomenda publicar) e o voto sugerido. Você escolhe os comentários, ajusta o texto e decide o
   voto. Comentar, votar e concluir a PR são ações travadas: saem só com o seu OK. O estado do card nunca muda.
5. **O autor atualizou a PR:** o mesmo `worktree create --pr <n>` leva o worktree à versão nova e grava
   `diff-pr<n>-<repo>-r<N>.patch` só com o que mudou. Um revisor novo recebe o review anterior e esse diff, com os
   mesmos IDs.
6. **Fim:** `aidw.py worktree remove <id>` tira as junctions primeiro e remove o worktree; não há branch para manter.

## Levantamento de demanda

Workflow `levantamento`: entender e estimar um card **antes** de implementar. Só leitura: sem worktree, plano, tickets,
build nem código.

```text
/aidw:levantamento 1234                  ← o card (id ou link)
/aidw:levantamento "<texto da demanda>"   ← sem card: os pontos saem do texto
```

1. **Entender:** o orquestrador lê o card (campos, critérios, comentários e itens ligados), grava `resumo-<id>.md` e
   numera tudo o que o card pede ou afirma em `pontos-<id>.md` (`P01`, `P02`…, com a origem de cada um).
2. **Explorar:** um explorador na célula do nível `critica` (no contexto safeweb, Sonnet high) no **modo
   levantamento**: diz se cada ponto está confirmado, diverge, não foi encontrado ou mora em outro sistema, sempre com
   `arquivo:linha`; mapeia o fluxo de ponta a ponta; junta os sinais de tamanho (sistemas, pontos de contato,
   contratos, banco, telas, testes existentes, trechos frágeis, o que o teste exige) e as dúvidas que o código não
   responde. Relatório: `exploracao-levantamento.md`.
3. **Estimar:** o orquestrador aplica a régua aos sinais (referência *levantamento*; a do contexto, *regua-estimativa*,
   vale sobre a padrão) e grava `levantamento-<id>.md`: horas por frente numa faixa mínimo–máximo, story points em
   Fibonacci, complexidade, confiança e o que a mudaria, riscos, a quebra sugerida acima de 13 SP e as **dúvidas**:
   uma pergunta por item, em linguagem do negócio, com o porquê e para quem.
4. **Fim:** a estimativa e as dúvidas aparecem no chat, e o orquestrador oferece publicar um comentário curto no card
   (ação travada: só com o seu OK). Story points e estado do card ele nunca muda.

Se o card for implementado depois, `/aidw:orquestrar 1234` reaproveita o resumo, os pontos e a exploração do
levantamento e começa pelo plano.

## Quando você é chamado

O orquestrador interrompe **só** para:

1. **Ação travada:** commit, push, merge, SQL de escrita, chamada de API que muda estado. O agente propõe o comando
   exato; o orquestrador junta as propostas e pede o OK uma vez.
2. **Dúvida real ou mais de um caminho válido:** uma pergunta, com opções, a recomendação e o porquê.
3. **Algo fora do plano:** escopo maior, ambiente bloqueado, voltas esgotadas.
4. **O teste manual**, quando o plano de testes tem passos que só você pode executar.
5. **A revisão final**, uma vez.

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
| `plano-testes-<id>.md` · `qa-<id>-r<N>.md` · `roteiro-testes-<id>.md` | o plano de testes, os relatórios do qa e o roteiro manual com o resultado de cada passo |
| `teste-orquestrador-<id>-r<N>.md` | os critérios que o orquestrador testou no navegador dele, com os vereditos dele e do qa |
| `ambiente-teste-<id>.patch` · `ambiente-teste-<id>.md` | os ajustes temporários de teste e o registro deles |
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
