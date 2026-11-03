# Painéis e faixa do AiDW (V4)

Especificação da faixa acima do prompt e dos painéis do AiDW (mod `aidw-mods`, só Claude Code). A V4 (Felipe,
2026-11-03) parte de que o app do Claude já tem barra lateral própria (Ambiente, Contexto, Saídas, Alterações) e o
diff: o AiDW fica com a faixa e três painéis que só abrem quando você pede. Os mods em geral estão em
[mods.md](mods.md); aqui fica o que cada tela mostra, de onde vem cada dado e o que os agentes gravam para isso.

A faixa vale em todo contexto. Os painéis e os botões da faixa somem no contexto que os desliga (`[mods] panel = false`
no `context.toml`); dentro deles, cada aba só aparece quando há o arquivo que ela lê
([mods.md](mods.md#quando-ficam-ligados)).

## Princípios

- **Simples, limpo e no padrão do app do Claude:** cartões com borda sutil e cantos arredondados, rótulos pequenos em
  cinza, espaço entre os blocos. O laranja do Claude só aparece no que está acontecendo agora ou espera você.
- **Nada abre sozinho:** os painéis abrem pelo botão da faixa ou pelo comando. Sem toasts nem notificações próprias.
- **Feito para o app desktop.** O terminal recebe a mesma informação, num desenho mais simples (barras ▰▱, teclas).
- **Os painéis só informam:** toda decisão (manter ou descartar um achado, o resultado de um passo manual, o que
  publicar, aprovar uma PR, responder uma dúvida, comentar no card) é feita no chat, com o orquestrador e o agente da
  etapa (revisor, QA). Nenhum painel tem botão de decisão nem campo de resposta (Felipe, 2026-11-03).
- **Sem orçamento de tokens nem limite de rodadas** em nenhuma tela: a demanda itera até terminar.
- **O que os mods desenham:** caixas (borda, cor), texto, botões, campos, seletor e SVG. Não há menu flutuante; os
  filtros são uma linha de botões que liga e desliga.

## Cores

A faixa e os painéis usam as cores do tema do Claude (`C` em `hooks/views.tsx`), que o app pinta no tema claro ou
escuro; nenhuma cor é fixa. Não há cor de tema para fundo neutro, então cartão é só borda.

| Cor | Chave do tema | Significado |
|---|---|---|
| laranja (do Claude) | `claude` | o que está acontecendo agora ou espera você: etapa atual, agente rodando, "● espera você", contagens, opção recomendada |
| azul | `suggestion` | com o time, a QA ou o UX (fora do AiDW); barras de tokens |
| amarelo | `warning` | atenção: barra de 75% a 89%, voltou do time ou da QA, implementado sem teste, precisa mudar |
| vermelho | `error` | barra a partir de 90%, limite, falhou, linha removida |
| verde | `success` | coberto, corrigido, passou, concluída, linha adicionada |
| roxo | `merged` | dúvida |
| texto | `text` | o conteúdo |
| cinza | `inactive` | rótulos, texto secundário e as barras abaixo de 75% |
| cinza claro | `subtle` | feito, etapas de fora pendentes |
| borda | `promptBorder` | cartões e trilhos das barras |

O SVG (barras, progresso, gráfico por dia) é desenhado como imagem, fora do tema: `svgDoc` leva, para cada chave, a cor
do tema escuro e a do claro, e o `prefers-color-scheme` do app escolhe.

## Faixa acima do prompt

```text
AiDW us-128734 Revisão ● espera você        contexto ▰▰▰▱▱ 41% · 82k   7d ▰▰▰▰▱ 58%   5h ▰▰▰▰▰ 91% · renova 16:40
● dev-medium · correção r1 · 2m10s
                                                                          Geral  Métricas  Testes e Review 4
```

Três linhas:

1. **A demanda e o consumo:** AiDW, o id, a etapa atual (com o uso na frente quando não é desenvolvimento: "Revisão de
   PR · Revisão final") e **● espera você** em laranja quando a etapa é sua (`HUMAN_APPROVAL`, aprovação do plano,
   triagem, sua revisão de código, teste manual, PR, revisão final); do outro lado, o contexto em % da janela real do
   modelo com os tokens, e o 7d e o 5h em %, cada um com barra fina.
2. **Os agentes rodando** (nome, tarefa, tempo), com o ponto laranja. Sem agente, a linha não aparece.
3. **Os botões**, numa linha só e à direita: **Geral**; **Métricas** (quando há delegação ou turno do orquestrador
   gravado); **Testes e Review** (quando a demanda tem revisão, roteiro ou comentários de PR; no levantamento,
   **Dúvidas**), com o número do que ainda espera decisão em laranja e apagado quando não há nada.

- **Cores das barras:** cor normal até 74%, amarela de 75% a 89%, vermelha a partir de 90%. O 7d e o 5h, a partir de
  75%, mostram a hora local em que a janela renova ("91% · renova 16:40"; com o dia, quando não é hoje); **no limite
  (100%)**: "limite · volta 16:40".
- **Dados:** contexto e janelas de uso em `$.session.usage()` (`rateLimits` `five_hour`/`seven_day`, só em
  assinatura; sem leitura, o 7d e o 5h não aparecem); agentes rodando pelo próprio mod.
- A faixa some em `DONE`; **`/faixa`** esconde e mostra.

## Painéis

| Painel | Botão / comando | Desenvolvimento | Revisão de PR | Levantamento |
|---|---|---|---|---|
| Geral | **Geral** · `/painel [aba]` | mapa e critérios e regras | mapa | mapa, card × código e estimativa |
| Métricas | **Métricas** · `/metricas` | consumo | consumo | consumo |
| Testes e Review | **Testes e Review** · `/testes-review` | abas Revisão · Testes | Comentários | — (vira **Dúvidas**) |

O uso vem dos arquivos da demanda. Uma demanda que fechou o levantamento (`DONE` depois do `ESTIMATE`) e seguiu para
outra etapa já aparece como Desenvolvimento, mesmo antes de o plano ser gravado.

- **Cada painel é um pane próprio** ("AiDW · Geral", "AiDW · Métricas", "AiDW · Testes e Review" ou "AiDW · Dúvidas"); com dois ou mais abertos,
  o app mostra as abas entre eles. Ao sair do modo orquestrador, os três fecham. Numa janela estreita demais o painel
  não abre e o comando diz por quê.
- **`/painel <aba>`** abre o painel que tem a aba (`/painel revisao`, `/painel roteiro` e `/painel duvidas` abrem
  Testes e Review, ou Dúvidas; `/painel criterios`, `estimativa` e `codigo` abrem a Geral).
- **Cabeçalho único:** tipo e número (`US 128734 · Desenvolvimento`), a situação (`● Revisão · espera você`, ou
  `Code review · com o time` em azul, `Pausada`, `Concluída` em verde) e o título do card.
- **Abas** (só em Testes e Review, e só com duas ou mais): a ativa com moldura, as outras apagadas; ao lado do nome,
  em laranja, o que ainda espera decisão. Aba sem dados fica oculta. O painel abre na primeira aba com pendência. No
  terminal, as teclas `1`, `2`… e `r` (↻, atualizar) aparecem e funcionam; no app, são só clique.
- **Escolher entre poucas opções** (rodadas): botões lado a lado; uma opção só vira texto; mais de 4, o seletor do app.
- **Texto dos artefatos** com `código` ou **negrito** é desenhado como Markdown.
- **Botões** só de navegação: abas, rodada, filtros, "Mostrar mais" e ↻. A opção recomendada aparece marcada com
  "(recomendado)" no texto.

### Etapas

O progresso tem dois grupos: **AiDW** e **Time e QA**. Os nomes são substantivos (painel v4):

| Uso | AiDW | Time e QA |
|---|---|---|
| Desenvolvimento | Entendimento · Plano · Sua aprovação · Implementação · Revisão · Sua revisão · Testes · PR | as do contexto (ex.: Validação UX) · Code review · Testes QA · Concluída |
| Revisão de PR | Entendimento · Preparação · Revisão · Revisão final · Concluída | — |
| Levantamento | Entendimento · Exploração · Estimativa · Revisão final · Concluída | — |

As etapas de fora que o contexto acrescenta (`[[workflows.external_steps]]`) entram só na demanda que passa por elas
(`demand set --extra-step`). As etapas de antes do fluxo v3 caem na fase equivalente.

## Geral

Uma página só, sem abas:

1. **Mapa da demanda:** o resumo de até 4 linhas e o **progresso** numa barra fina nos dois grupos (as etapas de fora
   ainda não alcançadas são pontos vazados), com o nome da etapa atual e "etapa N de 11". Quando o time ou a QA
   devolve, a etapa de fora fica amarela com "↩ voltou do Testes QA · 1ª vez"; um contador discreto guarda as voltas
   ("voltas: Plano 2× · Revisão 2×").
2. **Números**, só o que não está em outro bloco: na revisão de PR, as PRs e os comentários publicados; no
   levantamento, as dúvidas abertas. No desenvolvimento não há (a cobertura está no bloco dos critérios).
3. **Próximo passo:** a nota do `demand.json` (`demand set --note`), quando há.
4. **O bloco do uso:**
   - desenvolvimento: **Critérios e regras** (abaixo);
   - levantamento: **Card × código** e **Estimativa** (abaixo).

Saíram na V4: os agentes (estão na faixa), os links da pasta e das branches (o app mostra) e os tokens e o tempo (estão
em Métricas).

- **Resumo:** `demand.json` → `summary`, gravado pelo orquestrador ao entender o card. Sem ele: "Sem resumo gravado".
- **Etapas de fora:** `demand.json` → `CODE_REVIEW`, `QA_TEST` e as do contexto, gravadas pelo orquestrador **quando
  você avisa** no chat.

### Critérios e regras (desenvolvimento)

- A cobertura por tipo no topo, com barra de duas cores (verde coberto, amarelo implementado), e três cartões:
  **Critérios de aceite** (`CA1…`), **Regras de negócio** (`RN1…`) e **Cenários** (`CN1…`), uma linha por item com o
  identificador, o texto e o status.
- **Status pelo nosso código e pelos nossos testes** (Code review e QA não contam):
  - **Falta:** a demanda ainda não passou da implementação, ou o item não está em nenhuma entrega do plano;
  - **Implementado** (amarelo): a demanda passou da implementação e o item está numa entrega (`Covers:` do plano);
  - **Coberto** (verde): um passo do roteiro que prova o item (coluna `Critério`) tem ✅.
- **Dados:** o plano numera os itens com o texto do card e diz em cada entrega o que ela cobre (`Covers: CA1, RN2`); o
  roteiro do QA diz em cada passo o critério que ele prova. Sem plano, os critérios vêm do resumo do card, todos em
  "Falta", com o aviso "Ainda não há plano".

### Card × código e Estimativa (levantamento)

- **Card × código:** o que o card pede; os pontos validados no código, uma linha cada com a situação na frente
  (precisa mudar, é a dor, não muda, nada a reaproveitar), o "hoje no código" e, apagado, o "para a demanda"; 5 à
  vista e "Mostrar mais"; e **Onde a mudança toca**.
- **Estimativa:** os números (SP do card como está, SP quebrado, dias de dev, de QA, complexidade e confiança); o
  esforço por bloco em barras de intervalo (mínimo a máximo); a recomendação de quebra em itens; e **Riscos**.
  Comentar no card é pedido no chat.
- **Dados:** o `levantamento-<id>.md` no modelo fixo da referência *levantamento*.

## Métricas

- **Resumo:** delegações, rodadas de revisão, tokens dos agentes e do orquestrador ("sem registro" quando não há
  `metricas-orquestrador.md`), tempo de agentes trabalhando e o custo das delegações quando o `metricas.md` traz.
- **Por agente:** barras de tokens; o orquestrador entra como mais uma linha, em laranja, com os turnos e sem tempo.
- **Orquestrador:** cache lido, cache escrito, saída, a parte dele no total da demanda e uma linha por sessão e modelo
  (turnos, cache lido, tokens, custo equivalente). Vem do `metricas-orquestrador.md`, que o mod soma a cada turno
  (`aidw.py record-orchestrator`). O custo é o preço de API: uma régua do peso no limite do plano, não a conta.
- **Tokens por dia** (colunas, com tooltip de chamadas e tempo), só com dois dias ou mais; **por modelo e effort** em
  barras.
- **Resultado das chamadas e retrabalho:** etiquetas com contagem e as voltas.

Saíram na V4: a lista das delegações recentes e a dos artefatos (o app mostra os arquivos em Saídas).

## Testes e Review (Dúvidas no levantamento)

Só para consulta: os achados da revisão, o teste manual e os comentários de PR; no levantamento, as dúvidas. O número no
botão da faixa soma o que ainda espera decisão em cada aba; a decisão é no chat. Sem nada (pelo `/testes-review`):
"Ainda sem testes nem revisão nesta demanda." ou, no levantamento, "Nenhuma dúvida por enquanto."

### Revisão (desenvolvimento)

- **Rodada** em botões, por tipo: Plano r1, Código r1, Código r2… Abre na rodada com achado a decidir; senão, na
  última do código.
- **Situação** em abas de texto: Com você (a decidir) · Mantidos · Descartados · Todos. Abre em **Com você**.
- **Filtros:** um botão que abre uma linha de botões liga/desliga por criticidade, categoria (qualidade, bug,
  segurança) e status.
- **Cada achado é um cartão:** criticidade, ID, `arquivo:linha` e situação (a decidir, mantido, descartado,
  corrigido); o que foi apontado; o código **antes e depois**, quando o achado propõe mudança; a **recomendação do
  AiDW**; nas dúvidas, as opções do próprio achado ("(a) …", a primeira é a recomendada); e, depois de decidido, a
  decisão gravada na triagem.
- **Dados:** achados no `review-*-rN.md` (categoria no título, `Antes:` e `Depois:`, `**Recomendação:**`); a decisão
  vem do `triagem-*-rN.md`, que o orquestrador grava a partir do que você disse no chat.

### Testes (desenvolvimento)

- Progresso no topo (passaram, falharam, faltam), só com os passos ativos.
- Cartão **Próximo** com o passo da vez: seção, o que fazer e o esperado. O resultado e a evidência vão no chat, com o
  orquestrador, que marca o roteiro.
- Lista pelas seções do roteiro, com a evidência de cada passo feito; a preparação fica recolhida; os removidos do
  roteiro, escondidos.

### Comentários (revisão de PR)

- **Os comentários da triagem** (`C1`, `C2`…; referência *triagem-pr*): cada um junta os achados que dizem a mesma
  coisa ("junta R1-01 · B1-01"). Agrupados **por PR**.
- Filtros: A decidir · Publicados · Todos (abre em A decidir quando há o que decidir).
- **Cada comentário:** severidade (Pergunta para dúvida, Pendências QA), id, `arquivo:linha`, a situação, o título, o
  **texto que vai para a PR** e a recomendação. Publicados e recusados ficam recolhidos em "Ver comentário".
- O que publicar, os ajustes de texto e se o AiDW aprova cada PR (manual, o padrão; sim; não) são decididos no chat,
  na revisão final.
- **Fora das PRs:** o que não vira comentário, recolhido.
- **Sem triagem no formato *triagem-pr*** (demandas antigas): os achados da última rodada, com abas A decidir · Já
  publicados.

### Dúvidas (levantamento)

- As abertas por tema, cada uma com para quem é, o que muda na estimativa e por que importa; as de um grupo
  "Respondidas …" ficam numa linha cada. A resposta vai no chat; o orquestrador atualiza o levantamento.

## O que muda fora do painel

| Quem | Grava |
|---|---|
| `aidw.py demand set` | `--summary`, `--note`, `--pr <repo>=<n>`, `--extra-step` e as etapas `CODE_REVIEW` e `QA_TEST` |
| Orquestrador | o resumo ao entender o card; as etapas de fora quando você avisa; as suas decisões dos achados no `triagem-*-rN.md` |
| Planejador | critérios e regras do card numerados como `CA1`, `RN1`, e o `Covers:` de cada entrega |
| Revisor | a categoria no título, `Antes:` e `Depois:` e a `Recomendação:` em cada achado |
| QA | as colunas `Critério` e `Como` e o `Resultado` de cada passo do roteiro |
| Explorador (levantamento) | o modelo do levantamento |
