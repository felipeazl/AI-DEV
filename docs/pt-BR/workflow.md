# O fluxo

O que acontece entre o `/aidw:go 1234` e a PR aberta: as etapas, quem faz cada uma, onde você decide, como o
orquestrador escolhe o próximo passo e o que fica gravado.

## A ideia

Um chat único que faz tudo (lê o código, planeja, codifica, se revisa) acumula contexto: no fim da demanda ele carrega
centenas de linhas lidas no começo, fica mais caro a cada mensagem e erra mais. O AiDW separa os papéis sem multiplicar
etapas:

- O **orquestrador** é o chat principal. Ele lê, organiza e coordena, mas não lê código para planejar nem implementa.
  O contexto dele é o maior custo da demanda, então ele lê arquivo só quando precisa decidir algo dele.
- Cada etapa roda num **agente novo** (um subagente nativo), que recebe **arquivos por caminho** — o plano é a tarefa
  do coder —, grava o resultado na pasta da demanda e devolve um JSON com um `state`.
- **Cada agente roda uma vez por etapa.** Uma rodada nova precisa de um motivo nomeado: o seu ajuste, um achado
  mantido, um teste que falhou ou um resultado que não fez sentido.
- **Você decide** o plano, os achados da revisão, a sua revisão de código, os passos manuais do teste e a PR; o resto
  roda sozinho.

## Etapas (`development`)

```text
Entender → Explorar → Plano → Sua aprovação
        → Implementar (em paralelo: as Tasks no board, o roteiro de testes e a massa)
        → Revisão → você decide os achados → Correção ⇄ Re-revisão
        → Sua revisão de código → Testes (o qa roda API e navegador; os passos manuais você roda com o orquestrador)
        → PR (commit, push e PR com um OK) → Code review e QA (fora do AiDW) → /aidw:done
```

| Etapa | Quem | Saída | Você |
|---|---|---|---|
| **Entender** | orquestrador | `summary-<id>.md`: campos do card, critérios de aceite e regras de negócio (o texto do card), decisões dos comentários (autor e data), trabalho existente, as notas da base que importam | só se já houver trabalho (Tasks, PR, branch): continuação, correção ou retrabalho? |
| **Explorar** | explorer | `exploration-<assunto>.md`: perguntas numeradas respondidas com `arquivo:linha`, contratos entre sistemas, ids e dados reais | — |
| **Plano** | planner | `plan-<id>.md`: spec-driven, curto e autossuficiente — premissas verificadas, comportamento atual e desejado, os `CA`/`RN` do card, as entregas `E1…` com os arquivos e o build | — |
| **Sua aprovação** | você + orquestrador | o orquestrador lê o plano e aponta o que não fecha; você aprova ou pede ajuste (planner em modo fix) | **sim: nada vai para o código sem o seu OK** |
| **Implementar** | coder (um por entrega), documenter, qa | o código no worktree; uma Task por entrega no board; `test-script-<id>.md` com a massa | as escritas da massa, de uma vez |
| **Revisão** | reviewer | `review-<id>-r<N>.md`: qualidade, bugs e segurança numa passada, cada achado com a recomendação de manter ou descartar | **sim: você decide cada achado, a cada rodada** |
| **Correção** | coder → reviewer | só os achados mantidos; a re-revisão olha só as correções | — |
| **Sua revisão de código** | você | um pedido seu vira correção e revisão só dela | **sim** |
| **Testes** | qa, depois você + orquestrador | o qa confere o roteiro contra o diff final, roda os passos automáticos e marca o resultado; os manuais você executa, um por vez | **sim, nos passos manuais** |
| **PR** | documenter, depois o orquestrador | `pr-<id>.md` (mensagem de commit, título, descrição, pendências para a QA); com o seu OK: commit, push, PR | **sim: um OK** |

Bug, melhoria, dívida técnica e correção urgente usam este workflow. Num bug, a causa-raiz é a primeira pergunta do
explorer (reproduzir ou mostrar a causa); numa dívida sem mudança de comportamento, o plano diz isso e o roteiro cobre a
regressão. O contexto pode acrescentar etapas de fora (ex.: uma validação de UX antes da PR,
[contexts.md](contexts.md#etapas-de-fora)).

## Como o próximo passo é escolhido

Cada agente termina com `"state": "<chave>"`, e o `[rules]` do `orchestrator/config/routing.toml` dá a próxima ação
(`plan_ready` → `PLAN_APPROVAL`, `review_findings` → `TRIAGE`, `tests_passed` → `PR`…). O orquestrador aplica a regra;
os agentes não escolhem o próximo passo. Um `state` ausente ou desconhecido é falha: o orquestrador pede de novo só o
JSON. O contexto pode sobrepor regras em `contexts/<nome>/routing.toml`.

Não há limite de rodadas: um laço (explorar ⇄ planejar, revisar ⇄ corrigir) roda até a etapa terminar, e cada rodada
nova precisa de um motivo nomeado.

## Agentes e effort

Não há nível de demanda. Cada agente roda no seu padrão; o orquestrador só usa uma **exceção** pelo motivo escrito na
tabela *Agents and effort*. Padrões, exceções e como trocar: [agents.md](agents.md#modelos-e-effort).

## Revisão e triagem

O reviewer revisa cada entrega contra o plano numa passada: os padrões do time, **bugs** (cada um com o cenário de
falha rastreado no código) e **segurança** (cada falha com o caminho de ataque). Cada achado tem ID, severidade,
categoria, a correção mínima dentro do escopo, o código antes e depois e a recomendação (manter ou descartar, e por
quê). Dúvidas de regra ou de arquitetura vêm como dúvida, não como achado.

Os achados vão para **você** a cada rodada, e você decide no chat. Antes de recomendar descartar um achado crítico ou
importante, o orquestrador confere a premissa (skill `verify-premise`). As decisões ficam em `triage-<id>-r<N>.md`; os
mantidos vão para o coder, e um reviewer novo confere só as correções. Sem nada a decidir, a demanda vai para a sua
revisão de código.

## Testes

- **Roteiro e massa, em paralelo com o código:** logo depois da sua aprovação do plano, o qa escreve
  `test-script-<id>.md` — cada `CA`/`RN` com passos, resultado esperado, evidência e como provar (`auto-api`,
  `auto-browser`, `auto-suite` ou `manual`) — e levanta a massa: acha os registros que já existem e lista em
  *Approvals* o que precisa ser criado ou alterado. Você aprova os blocos de escrita de uma vez, enquanto o código é
  escrito.
- **Depois da sua revisão:** o qa confere o roteiro contra o diff final, roda as escritas aprovadas, os passos
  automáticos (API e navegador — Claude in Chrome, o seu Chrome logado, ou Playwright) e a regressão da área, e escreve
  ✅/❌ e a evidência no roteiro.
- **Passos manuais** (aplicativos desktop, ou o que o qa não conseguiu no navegador): o orquestrador mostra um passo
  por vez, você executa e manda a evidência no chat, e ele marca o resultado.
- **Ajustes de teste:** mudança de código só para testar (bypass, flag, mock) é feita pelo coder, marcada com
  `AIDW-TEST`, num patch separado (`test-env-<id>.patch`); sai antes do commit, e um hook recusa o commit que ainda tem
  a marca.
- Falhou → correção, revisão só dela e reteste só dos passos afetados.

## PR

O documenter escreve `pr-<id>.md`: a mensagem de commit, o título e a descrição da PR em linguagem simples, os work
items ligados e as pendências para a QA. O orquestrador confere que os ajustes de teste saíram, te mostra tudo com os
comandos exatos e, com **um OK**, faz o commit, o push e abre a PR (pela skill do contexto, quando ele tem uma). A partir
daí a demanda está com o time (`CODE_REVIEW`) e depois com a QA (`QA_TEST`); você avisa o orquestrador quando ela muda.

**Depois da entrega** (um bug devolvido pela QA, um pedido de mudança na PR, um ajuste pequeno): o caminho curto, sem
plano novo — o resumo do item, o explorer só se a causa não estiver clara, o coder, a revisão só da correção (os achados
vão para você), o reteste dos passos afetados e uma linha em *Addenda* no fim do plano. O
`demand set <id> --loop bug-<n>` numera as rodadas de revisão desse laço a partir de 1.

## Revisar a PR de outra pessoa (`pr-review`)

O orquestrador revisa a PR que outra pessoa abriu, sem plano nem correção: quem corrige é o autor, você escolhe o que é
publicado.

```text
/aidw:go us-1234 pr 5678 5679      ← o card e as PRs (podem ser de repositórios diferentes)
```

1. **Entender:** `summary-<id>.md` com o card e, por PR, autor, descrição, destino, itens ligados e o que já foi
   comentado.
2. **Worktree da PR:** `aidw.py worktree create --repo <repo> --demand <id> --pr <n>` busca a PR já mesclada no
   destino, cria um worktree só leitura e grava `diff-pr<n>-<repo>.patch`. O orquestrador roda o build nele.
3. **Revisão:** um reviewer no modo PR (qualidade, bugs e segurança), com todas as PRs da demanda; cada achado vem com o
   rascunho do comentário.
4. **Revisão final:** por PR, os comentários propostos. Você escolhe o que publicar, ajusta o texto e responde "Aprovar
   a PR?": **manual** (o padrão: você aprova na ferramenta), **sim** (o AiDW aprova) ou **não**. Publicar e aprovar são
   ações travadas. O estado do card nunca muda.
5. **O autor atualizou a PR:** o mesmo `worktree create --pr <n>` grava o diff só do que mudou, e um reviewer novo
   confere com os mesmos IDs.

## Levantamento (`survey`)

Entender e estimar um card **antes** de implementar. Só leitura: sem worktree, plano nem código.

```text
/aidw:survey 1234                  ← o card (id ou link)
/aidw:survey "<texto da demanda>"  ← sem card: a demanda é survey-<slug>
```

O orquestrador numera o que o card pede em `points-<id>.md`; o explorer, na exceção do levantamento (Sonnet high),
confirma cada ponto no código e mapeia o fluxo de ponta a ponta; o orquestrador estima pela régua da referência
*survey* e grava `survey-<id>.md` com horas, story points, complexidade, confiança, riscos e as dúvidas. O comentário no
card só sai com o seu OK. Se o card for implementado depois (`/aidw:go <id>`), o fluxo começa no `EXPLORE`,
reaproveitando o levantamento.

O `/aidw:survey` carrega um orquestrador enxuto (`orchestrator/SURVEY.md`): só o explorer, sem os workflows de
desenvolvimento, com o procedimento e a régua já dentro, para cada turno do orquestrador reler um contexto menor.

## Quando você é chamado

1. **Pontos fixos:** a aprovação do plano, os achados de cada rodada de revisão, a sua revisão de código, os passos
   manuais do teste e o OK da PR.
2. **Ações travadas:** SQL de escrita, chamada de API que muda estado, e-mail/OTP — o agente propõe, o orquestrador
   junta e pede o seu OK.
3. **Dúvida real ou mais de um caminho válido:** uma pergunta, com opções, a recomendação e o porquê.
4. **Algo fora do plano:** escopo maior, ambiente bloqueado.

## O que fica gravado

Tudo da demanda fica em `<pasta de estado>/<id>/`:

| Arquivo | Conteúdo |
|---|---|
| `demand.json` | etapa, status (`active`/`paused`/`done`), resumo, repositórios, Tasks, PRs, laço, histórico das etapas |
| `summary-<id>.md` | o card resumido, para nenhum agente reler o card |
| `exploration-<assunto>.md` | as respostas do explorer, reusadas pelo plano |
| `plan-<id>.md` (e `plan-<id>-v<N>.md`) | o plano versionado: a fonte da verdade e a tarefa do coder |
| `task-<agente>-<assunto>.md` | só quando há algo que não está em outro arquivo: as perguntas do explorer, os ajustes do plano, os achados mantidos |
| `diff-<id>-<E>-r<N>.patch` · `review-<id>-r<N>.md` · `triage-<id>-r<N>.md` | cada rodada da revisão, com as suas decisões |
| `test-script-<id>.md` · `qa-<id>-r<N>.md` | o roteiro com a massa e o resultado de cada passo, e o relatório do qa |
| `test-env-<id>.patch` · `test-env-<id>.md` | os ajustes temporários de teste |
| `pr-<id>.md` | commit, PR e pendências para a QA |
| `learnings-<id>.md` | o que nasceu no chat e vale para as próximas demandas |
| `metrics.md` · `orchestrator-metrics.md` | uma linha por delegação (agente, modelo, effort, tokens, ferramentas, duração) e o consumo do chat principal |

Os nomes de arquivo são sempre em inglês; o conteúdo segue o idioma do contexto
([configuration.md](configuration.md#idioma)). Demandas criadas antes da troca para o inglês mantêm os nomes antigos
(`resumo-`, `plano-`, `metricas.md`…) e continuam sendo lidas.

### Métricas

Depois de cada subagente, a linha vai para o `metrics.md` pelo `aidw.py record`, com os números reais. No Claude Code o
plugin `aidw-mods` roda o `record` sozinho e soma o consumo do chat principal no `orchestrator-metrics.md`
([mods.md](mods.md)); sem ele, e no Codex, o orquestrador roda o `record`. Os números **nunca são estimados**.

### Retomar

`/aidw:exit` grava a etapa e o próximo passo (`paused`). Depois, `/aidw:go` sem argumento no worktree ou no repositório
acha a demanda e continua da etapa gravada; `python aidw.py open --demand <id>` faz o mesmo pelo terminal. Em esperas
longas (o review do time, a QA), feche o chat e retome num novo: a pasta da demanda tem tudo.

### Concluir

`/aidw:done` fecha a tarefa: parte do `aidw.py kb collect <id>`, grava no contexto só o que foi **verificado** e vale
para as próximas demandas, valida, reinstala e faz commit e push **só do repositório do contexto**.

## A base de conhecimento no fluxo

Quando o contexto tem uma base de conhecimento ([contexts.md](contexts.md#base-de-conhecimento)):

- **No começo**, o orquestrador roda `kb search` com os termos do card e lista no `summary-<id>.md` os **caminhos** das
  notas que importam; toda tarefa leva esses caminhos, e os agentes leem as notas antes do código.
- **Durante**, cada agente anota o que aprendeu no próprio relatório (seção *Knowledge base*). O `learnings-<id>.md`
  fica só para o que nasce no chat: as suas decisões, as do negócio, os bloqueios de ambiente que o orquestrador
  resolveu.
- **No fim**, o `/aidw:done` roda `kb collect <id>` (junta tudo no `collect-<id>.md`), atualiza a base e faz o commit do
  contexto.
