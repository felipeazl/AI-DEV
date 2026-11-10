# Painéis e faixa

O que a faixa acima do prompt e os painéis do AiDW mostram, de onde vem cada dado e o que os agentes gravam para isso (o
mod `aidw-mods`, só no Claude Code). Os mods em geral estão em [mods.md](mods.md).

A faixa vale em todo contexto. Os painéis e os botões da faixa somem no contexto que os desliga (`[mods] panel = false`
no `context.toml`); dentro deles, cada aba só aparece quando há o arquivo que ela lê.

## Princípios

- **Simples e no padrão do app do Claude:** cartões com borda sutil, rótulos pequenos em cinza, espaço entre os blocos.
  O laranja do Claude só marca o que está acontecendo agora ou espera você.
- **Nada abre sozinho:** os painéis abrem pelo botão da faixa ou pelo comando. Sem toasts nem notificações próprias.
- **Feito para o app desktop.** O terminal recebe a mesma informação num desenho mais simples (barras ▰▱, teclas).
- **Os painéis só informam:** toda decisão (manter ou descartar um achado, o resultado de um passo manual, o que
  publicar, aprovar uma PR, responder uma dúvida, comentar no card) é feita no chat, com o orquestrador e o agente da
  etapa. Nenhum painel tem botão de decisão nem campo de resposta.
- **Sem orçamento de tokens nem limite de rodadas** em nenhuma tela: a demanda itera até terminar.
- **Cores** vêm do tema do Claude, então acompanham o modo claro e o escuro: laranja = agora ou espera você; azul = com o
  time, a QA ou o UX; amarelo = atenção (barras a partir de 75%, voltou do time ou da QA, implementado sem teste);
  vermelho = a partir de 90%, falhou; verde = coberto, corrigido, passou, concluída; roxo = dúvida.

## Faixa

```text
AiDW us-1234 Revisão ● espera você        contexto ▰▰▰▱▱ 41% · 82k   7d ▰▰▰▰▱ 58%   5h ▰▰▰▰▰ 91% · renova 16:40
● Coder Sonnet medium · fix r1 · 2m10s
                                                                    Geral  Métricas  Testes e Review 4
```

1. **A demanda e o consumo:** AiDW, o id, a etapa atual (com o uso na frente quando não é desenvolvimento: "Revisão de
   PR · Revisão final") e **● espera você** quando a etapa é sua (`HUMAN_APPROVAL`, aprovação do plano, triagem, sua
   revisão de código, teste manual, PR, revisão final); do outro lado, o contexto em % da janela real do modelo com os
   tokens, e as janelas 7d e 5h.
2. **Os agentes rodando** (nome, modelo e effort, tarefa, tempo), com o ponto laranja. Sem agente, a linha não aparece.
3. **Os botões**, numa linha só à direita: **Geral**; **Métricas** (quando há delegação ou turno do orquestrador
   gravado); **Testes e Review** (quando a demanda tem revisão, roteiro ou comentários de PR; **Dúvidas** no
   levantamento), com o número do que ainda espera decisão.

- Barras: cor normal até 74%, amarela de 75% a 89%, vermelha a partir de 90%. A partir de 75%, o 7d e o 5h mostram a hora
  local em que a janela renova ("91% · renova 16:40"); em 100%, "limite · volta 16:40".
- Dados: contexto e janelas de uso vêm da sessão (as janelas só em conta de assinatura); agentes rodando, do próprio mod.
- A faixa some em `DONE`; **`/strip`** esconde e mostra.

## Painéis

| Painel | Botão / comando | Desenvolvimento | Revisão de PR | Levantamento |
|---|---|---|---|---|
| Geral | **Geral** · `/panel [aba]` | mapa, critérios e regras | mapa | mapa, card × código, estimativa |
| Métricas | **Métricas** · `/metrics` | consumo | consumo | consumo |
| Testes e Review | **Testes e Review** · `/review-tests` | abas Revisão · Testes | Comentários | vira **Dúvidas** |

O uso (desenvolvimento, revisão de PR, levantamento) vem dos arquivos da demanda. Uma demanda que fechou o levantamento e
seguiu já aparece como desenvolvimento, mesmo antes de o plano ser gravado.

- **Cada painel é um pane próprio** ("AiDW · Geral", "AiDW · Métricas", "AiDW · Testes e Review" ou "AiDW · Dúvidas");
  com dois ou mais abertos, o app mostra abas entre eles. Ao sair do modo orquestrador, todos fecham. Numa janela estreita
  demais o painel não abre e o comando diz por quê.
- **`/panel <aba>`** abre o painel que tem a aba: `review`, `tests`, `comments`, `questions` (ou `revisao`, `testes`,
  `comentarios`, `duvidas`) abrem Testes e Review; qualquer outra coisa abre a Geral.
- **Cabeçalho único:** tipo e número, a situação (`● Revisão · espera você`, `Code review · com o time` em azul,
  `Pausada`, `Concluída` em verde) e o título do card.
- **Abas** (só em Testes e Review, e só com duas ou mais): ao lado do nome, em laranja, o que ainda espera decisão. Aba
  sem dados fica oculta. O painel abre na primeira aba com pendência. No terminal, as teclas `1`, `2`… e `r` (atualizar)
  funcionam; no app, as abas são só clique.

### Etapas

O progresso tem dois grupos: **AiDW** e **Time e QA**.

| Uso | AiDW | Time e QA |
|---|---|---|
| Desenvolvimento | Entendimento · Plano · Sua aprovação · Implementação · Revisão · Sua revisão · Testes · PR | as do contexto (ex.: Validação UX) · Code review · Testes QA · Concluída |
| Revisão de PR | Entendimento · Preparação · Revisão · Revisão final · Concluída | — |
| Levantamento | Entendimento · Exploração · Estimativa · Revisão final · Concluída | — |

As etapas de fora que o contexto acrescenta (`[[workflows.external_steps]]`) entram só na demanda que passa por elas
(`demand set --extra-step`). As etapas do fluxo antigo caem na fase equivalente.

## Geral

Uma página só, sem abas:

1. **Mapa da demanda:** o resumo (até 4 linhas) e o **progresso** nos dois grupos, com o nome da etapa atual. Quando o
   time ou a QA devolve, a etapa de fora fica amarela com "voltou do Testes QA"; um contador guarda as voltas por etapa.
2. **Números**, só o que não está em outro bloco: na revisão de PR, as PRs e os comentários publicados; no levantamento,
   as dúvidas abertas.
3. **Próximo passo:** a nota do `demand.json` (`demand set --note`), quando há.
4. **O bloco do uso:** desenvolvimento → **Critérios e regras**; levantamento → **Card × código** e **Estimativa**.

Dados: o resumo é o `demand.json` → `summary`, gravado pelo orquestrador ao entender o card; as etapas de fora são
gravadas pelo orquestrador **quando você avisa** no chat.

### Critérios e regras (desenvolvimento)

- A cobertura por tipo no topo, e três cartões: **Critérios de aceite** (`CA1…`), **Regras de negócio** (`RN1…`) e
  **Cenários** (`CN1…`), uma linha por item com o identificador, o texto e o status.
- **Status pelo nosso código e pelos nossos testes** (code review e QA não contam):
  - **Falta:** a demanda ainda não passou da implementação, ou o item não está em nenhuma entrega do plano;
  - **Implementado** (amarelo): passou da implementação e o item está numa entrega (`Covers:` do plano);
  - **Coberto** (verde): um passo do roteiro que prova o item (coluna `Criterion`) tem ✅.
- Dados: o plano numera os itens com o texto do card e diz em cada entrega o que ela cobre (`Covers: CA1, RN2`); o
  roteiro do qa diz em cada passo o critério que ele prova. Sem plano, os critérios vêm do resumo do card, todos em
  "Falta".

### Card × código e Estimativa (levantamento)

- **Card × código:** o que o card pede; os pontos validados no código, cada um com a situação (precisa mudar, é a dor,
  não muda, nada a reaproveitar), o "hoje no código" e o "para a demanda"; e **Onde a mudança toca**.
- **Estimativa:** os números (story points do card como está, story points quebrados, dias de dev e de QA, complexidade,
  confiança), o esforço por bloco em barras de mínimo a máximo, a recomendação de quebra em itens e os **Riscos**.
  Comentar no card é pedido no chat.
- Dados: o `survey-<id>.md` no formato fixo da referência *survey*.

## Métricas

- **Resumo:** delegações, rodadas de revisão, tokens dos agentes e do orquestrador ("sem registro" sem o
  `orchestrator-metrics.md`), tempo de agentes trabalhando e o custo das delegações quando o `metrics.md` traz.
- **Por agente:** barras de tokens; o orquestrador entra como mais uma linha, em laranja, com os turnos.
- **Orquestrador:** cache lido, cache escrito, saída, a parte dele no total da demanda e uma linha por sessão e modelo,
  do `orchestrator-metrics.md`. O custo é o equivalente em preço de API: uma régua do peso no limite do plano, não a
  conta.
- **Orquestrador por etapa:** a seção por etapa do `orchestrator-metrics.md`, da etapa mais cara para a mais barata.
- **Tokens por dia** (com dois dias ou mais) e **por modelo e effort**.
- **Resultado das chamadas e retrabalho:** etiquetas com contagem e as voltas.

## Testes e Review (Dúvidas no levantamento)

Só para consulta: os achados da revisão, o teste manual e os comentários de PR; no levantamento, as dúvidas. O número no
botão da faixa soma o que ainda espera você em cada aba: achados sem decisão que a rodada seguinte não deu como
corrigidos ou fechados, e os passos do roteiro (automáticos e manuais) que ainda não passaram (sem `Result` ou `❌`),
só nas etapas de teste (`TEST`, `TEST_ADJUST`, `MANUAL_TEST`): antes delas nada roda, depois o teste está fechado.

### Revisão (desenvolvimento)

- **Rodada** em botões, por tipo: Plano r1, Código r1, Código r2… Abre na rodada com achado a decidir; senão, na última do
  código.
- **Situação** em abas: Com você (a decidir) · Mantidos · Descartados · Todos.
- **Filtros** por severidade, categoria (qualidade, bug, segurança) e status.
- **Cada achado é um cartão:** severidade, ID, `arquivo:linha` e situação; o que foi apontado; o código **antes e
  depois** quando o achado propõe mudança; a **recomendação do AiDW**; nas dúvidas, as opções do próprio achado; e,
  depois de decidido, a decisão gravada na triagem.
- Dados: os achados no `review-*-rN.md` (categoria no título, `Before:` e `After:`, `**Recommendation:**`); a decisão
  vem do `triage-*-rN.md`, que o orquestrador grava a partir do que você disse no chat.

### Testes (desenvolvimento)

- Progresso no topo (passaram, falharam, faltam), só com os passos ativos.
- Cartão **Próximo** com o passo da vez: seção, o que fazer e o esperado. O resultado e a evidência vão no chat, com o
  orquestrador, que marca o roteiro.
- A lista pelas seções do roteiro, com a evidência de cada passo feito; a preparação fica recolhida; os passos removidos,
  escondidos.

### Comentários (revisão de PR)

- **Os comentários da triagem** (`C1`, `C2`…; referência *pr-triage*): cada um junta os achados que dizem a mesma coisa,
  agrupados **por PR**. Filtros: A decidir · Publicados · Todos.
- **Cada comentário:** severidade, id, `arquivo:linha`, situação, título, o **texto que vai para a PR** e a recomendação.
  Publicados e recusados ficam recolhidos.
- O que publicar, os ajustes de texto e se o AiDW aprova cada PR (manual, o padrão; sim; não) são decididos no chat, na
  revisão final.

### Dúvidas (levantamento)

- As abertas por tema, cada uma com para quem é, o que muda na estimativa e por que importa; as respondidas, uma linha
  cada. A resposta vai no chat; o orquestrador atualiza o levantamento.

## O que alimenta o painel

| Quem | Grava |
|---|---|
| `aidw.py demand set` | `--summary`, `--note`, `--pr <repo>=<n>`, `--extra-step` e as etapas `CODE_REVIEW` e `QA_TEST` |
| Orquestrador | o resumo ao entender o card; as etapas de fora quando você avisa; as suas decisões dos achados no `triage-*-rN.md` |
| Planner | os critérios e as regras do card numerados como `CA1`, `RN1`, e o `Covers:` de cada entrega |
| Reviewer | a categoria no título, `Before:` e `After:` e a `Recommendation:` de cada achado |
| qa | as colunas `Criterion` e `How` e o `Result` de cada passo do roteiro |
| Explorer (levantamento) | o formato do levantamento |
