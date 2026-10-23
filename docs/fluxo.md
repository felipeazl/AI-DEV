# O fluxo de uma demanda

Este documento explica o que acontece entre o `/aidw:orquestrar 1234` e a PR aberta: as etapas, quem faz cada uma,
onde você decide, como o orquestrador escolhe o agente e o effort, e o que fica gravado. É o fluxo v3 (2026-10-23):
sem níveis de demanda, sete agentes e você nos pontos de decisão.

## A ideia central

Um chat único que faz tudo (lê o código, planeja, codifica, se revisa) acumula contexto: no fim da demanda ele
carrega centenas de linhas lidas no começo, fica caro a cada mensagem e erra mais. O AiDW separa os papéis, mas sem
multiplicar etapas:

- O **orquestrador** é o chat principal. Ele **lê, organiza e coordena**, mas não lê código para planejar nem
  implementa. O contexto dele é o maior custo da demanda (cada ação relê a conversa inteira), então ele lê arquivo só
  quando precisa decidir algo dele e não mantém registros que ninguém lê.
- Cada etapa roda num **agente novo** (um subagente nativo do provedor), que recebe **arquivos por caminho** — o
  plano é a tarefa do codificador —, grava o resultado na pasta da demanda e devolve um JSON com um `state`.
- **Cada agente roda uma vez por etapa.** Uma nova rodada só acontece por um motivo nomeado: o seu ajuste, um achado
  mantido, um teste que falhou ou um resultado que não fez sentido.
- **Você decide** o plano, os achados da revisão, a revisão de código e o OK da PR; o resto roda sozinho.

## Etapas

```text
Entender → Explorar → Plano → Sua aprovação
        → Implementar (em paralelo: as Tasks no board e o roteiro de testes com a massa)
        → Revisão → você decide os achados → Correção ⇄ Re-revisão
        → Sua revisão de código → Testes (o QA roda API e navegador; os passos manuais você roda com o orquestrador)
        → PR (commit, push e PR com um OK) → Code review e QA (fora do AiDW) → /aidw:done
```

| Etapa | Quem | Saída | Você |
|---|---|---|---|
| **Entender** | orquestrador | `resumo-<id>.md`: campos do card, critérios e regras com o texto do card, decisões dos comentários (autor e data), trabalho existente, as notas da base que importam | só se já houver trabalho (Tasks, PR, branch): continuação, correção ou retrabalho? |
| **Explorar** | explorador | `exploracao-<assunto>.md`: perguntas numeradas respondidas com `arquivo:linha`, contratos entre sistemas, ids e dados reais (SELECT pelo validador do contexto) | — |
| **Plano** | planejador | `plano-<id>.md`: spec-driven, curto e autossuficiente — premissas verificadas, comportamento atual e desejado, `CA`/`RN` do card, as entregas `E1…` com os arquivos, o que muda em cada um e o build | — |
| **Sua aprovação** | você + orquestrador | o orquestrador lê o plano e aponta o que não fecha; você aprova ou pede ajuste (planejador em modo fix) | **sim: nada vai para o código sem o seu OK** |
| **Implementar** | codificador (um por entrega), documentador, qa | o código no worktree e `diff-<id>-<E>-r1.patch`; as Tasks no board (uma por entrega); `roteiro-testes-<id>.md` com a massa de dados | os blocos de escrita da massa, de uma vez |
| **Revisão** | revisor | `review-<id>-r<N>.md`: qualidade, bugs e segurança numa passada, cada achado com a recomendação de manter ou descartar | **sim: você decide cada achado, a cada rodada** |
| **Correção** | codificador → revisor | só os achados mantidos; a re-revisão olha só as correções | — |
| **Sua revisão** | você | a revisão do código (aba Diffs do painel); um pedido seu vira correção e revisão só dela | **sim** |
| **Testes** | qa, depois você + orquestrador | o qa confere o roteiro contra o diff final, roda os passos automáticos e marca o resultado no roteiro; os manuais você executa, um por vez | **sim, nos passos manuais** |
| **PR** | documentador, depois o orquestrador | `pr-<id>.md` (commit, título, descrição, pendências para a QA); com o seu OK, commit, push, PR e o comentário de pendências | **sim: um OK único** |

Bug, melhoria, item técnico, dívida e correção urgente seguem o mesmo workflow (`desenvolvimento`): num bug, a
causa-raiz é pergunta do explorador; numa dívida sem mudança de comportamento, o plano diz isso e o roteiro cobre a
regressão. O contexto pode acrescentar etapas de fora (no safeweb, a **Validação de UX**, antes da PR).

## Como o orquestrador decide o próximo passo

Cada agente termina com `"state": "<chave>"`, e `orchestrator/config/routing.toml` diz a próxima ação de cada chave
(`plan_ready` → `PLAN_APPROVAL`, `review_findings` → `TRIAGE`, `tests_passed` → `PR`…). O orquestrador aplica a regra;
os agentes não escolhem o próximo passo. Um `state` ausente é falha: ele pede só o JSON de novo.

`max_retries` (3) conta as rodadas do mesmo laço (explorar ⇄ planejar, revisar ⇄ corrigir); esgotou, ele para e
traz para você. No Claude Code, o mod trava a delegação que passaria do limite até você liberar uma rodada
([mods.md](mods.md)).

## Agentes e effort

Não há nível de demanda. Cada agente roda no seu padrão e o orquestrador só usa uma **exceção** da tabela *Agents and
effort* pelo motivo escrito nela ([agentes.md](agentes.md#modelo-e-effort)):

| Agente | Padrão | Exceções |
|---|---|---|
| orquestrador | o chat (recomendado Opus medium) | — |
| explorador | Haiku | Sonnet medium para refazer uma vez quando o resultado não fez sentido; Sonnet high no levantamento |
| planejador | Sonnet high | medium no ajuste do plano |
| codificador | Sonnet high | medium na correção pequena e no ajuste de teste |
| revisor | Sonnet high | medium na re-revisão das correções; low na de uma correção trivial |
| qa | Sonnet medium | high para refazer uma vez quando o resultado não fez sentido |
| documentador | Haiku | — |

Opus nos agentes só quando você pede.

## Revisão e triagem

O revisor revisa a entrega contra o plano numa passada: padrões do time, **bugs** (cada um com o cenário de falha
`arquivo:linha` → `arquivo:linha`) e **segurança** (cada falha com o caminho de ataque). Cada achado traz a categoria,
a severidade, a correção mínima dentro do escopo, o código antes e depois e a recomendação (manter ou descartar, e por
quê). Dúvidas de regra ou de arquitetura vêm como dúvida, não como achado.

Os achados vão para **você** e para o orquestrador a cada rodada: no painel, a aba Revisão mostra cada um com a
recomendação e os botões Manter/Descartar, e o botão do rodapé leva as decisões ao prompt. Antes de recomendar
descartar um CRITICO/IMPORTANTE, o orquestrador confere a premissa (skill `verificar-premissa`). As decisões ficam em
`triagem-<id>-r<N>.md`; os mantidos vão para o codificador, e um revisor novo confere só as correções. Sem achado a
decidir, a demanda vai para a sua revisão de código.

## Testes

- **Roteiro e massa, em paralelo com o código:** logo depois da sua aprovação do plano, o qa escreve
  `roteiro-testes-<id>.md` — cada `CA`/`RN` com passos, resultado esperado, evidência e como provar (`auto-api`,
  `auto-browser`, `auto-suite` ou `manual`) — e levanta a massa: acha os registros que já existem (SELECT pelo
  validador) e lista em *Aprovações* o que precisa ser criado ou alterado. Você aprova os blocos de escrita de uma vez,
  enquanto o código é escrito.
- **Depois da sua revisão:** o qa confere o roteiro contra o diff final (acerta só o que a revisão mudou), roda as
  escritas aprovadas, os passos automáticos — API e navegador, pelo Claude in Chrome (o seu Chrome, logado) ou pelo
  Playwright — e a regressão da área, e escreve ✅/❌ e a evidência no próprio roteiro.
- **Passos manuais** (desktop/WPF, ou o que o qa não conseguiu no navegador): o orquestrador mostra um passo por vez,
  você executa e manda a evidência (pela aba Testes do painel ou no chat), e ele marca o resultado.
- **Ajustes de teste:** mudança de código só para testar (bypass, flag, mock, apontar para QA) é feita pelo
  codificador, marcada com `AIDW-TESTE`, num patch separado; sai antes do commit, e o hook recusa um commit com a
  marca.
- Falhou → correção, revisão só dela e reteste só dos passos afetados.

## PR

O documentador escreve `pr-<id>.md`: a mensagem de commit (cita o pai e as Tasks), o título e a descrição da PR em
linguagem simples, os work items e as pendências para a QA (ConfigManager, scripts `.sql`, o que versionar). O
orquestrador confere que os ajustes de teste saíram, te mostra tudo com os comandos exatos e, com **um OK**, faz o
commit, o push, abre a PR (no safeweb, pela skill `ado-abrir-pr`) e publica o comentário de pendências. A partir daí a
demanda está com o time (`CODE_REVIEW`) e depois com a QA (`QA_TEST`); você avisa o orquestrador quando ela muda.

**Depois da entrega** (um bug da QA, um pedido de mudança na PR, um ajuste seu): é o caminho curto, sem plano novo —
o resumo do item, o explorador só se a causa não estiver clara, o codificador, a revisão só da correção (os achados
vão para você), o reteste dos passos afetados e uma linha em *Adendos* no fim do plano.

## Revisar a PR de outra pessoa

Workflow `pr-review`: o orquestrador revisa a PR que outra pessoa abriu, sem plano nem correção. Quem corrige é o
autor; você escolhe o que é publicado. O procedimento completo está na referência *pr-review* do orquestrador.

```text
/aidw:orquestrar us-127508 pr 7639 7640     ← o card e as PRs (podem ser de repositórios diferentes)
```

1. **Entender:** o `resumo-<id>.md` traz o card e, por PR, autor, descrição, destino, itens ligados e o que já foi
   comentado.
2. **Worktree da PR:** `aidw.py worktree create --repo <repo> --demand <id> --pr <n>` busca a PR já mesclada no destino,
   cria um worktree só leitura e grava `diff-pr<n>-<repo>.patch`. O orquestrador roda o build nele uma vez.
3. **Revisão:** um revisor no modo PR (qualidade, bugs e segurança), com todas as PRs da demanda; cada achado vem com o
   rascunho do comentário e a revisão traz um voto sugerido.
4. **Revisão final:** por PR, os comentários propostos e o voto. Você escolhe, ajusta o texto e decide o voto; publicar
   e votar são ações travadas. O estado do card nunca muda.
5. **O autor atualizou a PR:** o mesmo `worktree create --pr <n>` grava o diff só do que mudou, e um revisor novo
   confere com os mesmos IDs.

## Levantamento de demanda

Workflow `levantamento`: entender e estimar um card **antes** de implementar. Só leitura.

```text
/aidw:levantamento 1234                  ← o card (id ou link)
/aidw:levantamento "<texto da demanda>"   ← sem card: os pontos saem do texto
```

O orquestrador numera o que o card pede em `pontos-<id>.md`; o explorador, na exceção do levantamento (Sonnet high),
confirma cada ponto no código e mapeia o fluxo de ponta a ponta; o orquestrador estima pela régua (referência
*levantamento*) e grava `levantamento-<id>.md` com horas, story points, complexidade, confiança, riscos e as dúvidas.
O comentário no card só sai com o seu OK. Se o card for implementado depois (`/aidw:orquestrar <id>`), o fluxo começa
pelo plano reaproveitando o levantamento.

A skill `/aidw:levantamento` carrega um orquestrador enxuto (`orchestrator/LEVANTAMENTO.md`): só o explorador, sem os
workflows de desenvolvimento, com o procedimento e a régua já dentro. Assim o orquestrador não lê referência nenhuma e
cada chamada dele relê um contexto menor.

## Quando você é chamado

1. **Pontos fixos:** a aprovação do plano, os achados de cada rodada de revisão, a sua revisão de código, os passos
   manuais do teste e o OK da PR.
2. **Ação travada:** SQL de escrita, chamada de API que muda estado, e-mail/OTP — o agente propõe, o orquestrador junta
   e pede o OK.
3. **Dúvida real ou mais de um caminho válido:** uma pergunta, com opções, a recomendação e o porquê.
4. **Algo fora do plano:** escopo maior, ambiente bloqueado, voltas esgotadas.

## O que fica gravado

Tudo da demanda fica na pasta `<pasta de estado>/<tipo>-<id>/`:

| Arquivo | Conteúdo |
|---|---|
| `demand.json` | etapa, status (`active`/`paused`/`done`), modo, repositórios, Tasks, PRs, histórico das etapas |
| `resumo-<id>.md` | o card resumido, para nenhum agente reler o card |
| `exploracao-<assunto>.md` | as respostas do explorador, reusadas pelo plano |
| `plano-<id>.md` (e `plano-<id>-v<N>.md`) | o plano versionado: a fonte da verdade e a tarefa do codificador |
| `tarefa-<agente>-<assunto>.md` | só quando há algo que não está em outro arquivo: as perguntas do explorador, os ajustes do plano, os achados mantidos |
| `diff-<id>-<E>-r<N>.patch` · `review-<id>-r<N>.md` · `triagem-<id>-r<N>.md` | cada rodada da revisão, com as suas decisões |
| `roteiro-testes-<id>.md` · `qa-<id>-r<N>.md` | o roteiro com a massa e o resultado de cada passo, e o relatório do qa |
| `ambiente-teste-<id>.patch` · `ambiente-teste-<id>.md` | os ajustes temporários de teste |
| `pr-<id>.md` | o commit, a PR e as pendências para a QA |
| `aprendizados-<id>.md` | o que nasceu no chat e vale para as próximas demandas |
| `metricas.md` · `metricas-orquestrador.md` | uma linha por delegação (agente, modelo, effort, tokens, ferramentas, duração) e o consumo do chat principal |

### Métricas

Depois de cada subagente, a linha vai para o `metricas.md` pelo `aidw.py record`, com os números reais do resultado.
No Claude Code, o mod `aidw-mods` roda o `record` sozinho e soma o chat do orquestrador no `metricas-orquestrador.md`
([mods.md](mods.md)); sem ele, e no Codex, o orquestrador roda o `record` à mão. Os números **nunca são estimados**.

### Retomar

`/aidw:sair` grava a etapa e o próximo passo (`paused`). Depois, `/aidw:orquestrar` sem argumento na pasta do worktree
ou do repositório acha a demanda e continua da etapa gravada. `python aidw.py open --demand <id>` faz o mesmo pelo
terminal.

### Concluir

`/aidw:done` fecha a tarefa: parte do `aidw.py kb collect <id>`, grava no contexto só o que foi **verificado** e vale
para as próximas demandas, valida, reinstala e faz commit e push **só do repositório do contexto**.

## A base de conhecimento no fluxo

Quando o contexto tem uma base de conhecimento ([contextos.md](contextos.md#base-de-conhecimento)):

- **No começo**, o orquestrador roda `kb search` dos termos do card e lista no `resumo-<id>.md` os **caminhos** das
  notas que importam; ele não carrega notas inteiras no chat. Toda tarefa leva esses caminhos: os agentes leem as notas
  antes do código.
- **Durante**, cada agente anota o que aprendeu no próprio relatório (seção *Base de conhecimento*: o que uma nota tinha
  de errado, fatos novos com `arquivo:linha`). O `aprendizados-<id>.md` fica só para o que nasce no chat: as suas
  decisões e as do negócio, os bloqueios que o orquestrador resolveu.
- **No fim**, `/aidw:done` roda `kb collect <id>` (junta tudo isso num arquivo só), leva para a base e faz o commit do
  contexto.
