# Painel e faixa do AiDW (V2)

Especificação da faixa acima do prompt e do painel do AiDW (mod `aidw-mods`, só Claude Code), desenhada tela por
tela com mocks em 14/10/2026. Os mods em geral estão em [mods.md](mods.md); aqui fica o que cada tela mostra, de onde
vem cada dado e o que os agentes passam a gravar para isso.

A faixa e o painel valem em todo contexto; o painel some só no contexto que o desliga (`[mods] panel = false` no
`context.toml`) e, dentro dele, cada aba só aparece quando há o arquivo que ela lê ([mods.md](mods.md#quando-ficam-ligados)).

## Princípios

- **Simples, limpo e no padrão do app do Claude:** cartões com borda sutil e cantos arredondados, rótulos pequenos em
  cinza, espaço entre os blocos. O laranja do Claude só aparece no que está acontecendo agora.
- **Feito para o app desktop.** O terminal recebe a mesma informação, num desenho mais simples.
- **Nada sai sem você:** publicar, votar, comentar no card e decidir achados vão para o prompt e só valem quando você
  envia a mensagem.
- **Sem orçamento de tokens** em nenhuma tela.
- **O que os mods desenham:** caixas (fundo, borda arredondada, cor), texto, botões, campos, seletor e SVG (gráficos,
  barras). Não há menu flutuante com caixas de seleção; os filtros são uma linha de botões que liga e desliga.

## Cores

A faixa e o painel usam as cores do tema do Claude (`C` em `hooks/views.tsx`), que o app pinta no tema claro ou escuro;
nenhuma cor é fixa. Não há cor de tema para fundo neutro, então cartão é só borda e nada leva fundo.

| Cor | Chave do tema | Significado |
|---|---|---|
| laranja (do Claude) | `claude` | o que está acontecendo agora: etapa atual, agente rodando, opção recomendada |
| azul | `suggestion` | com o time ou a QA (fora do AiDW); barras de tokens |
| amarelo | `warning` | atenção: voltou do time ou da QA, perto do limite, implementado sem teste, precisa mudar |
| verde | `success` | coberto, corrigido, passou, linha adicionada |
| vermelho | `error` | falhou, linha removida |
| roxo | `merged` | dúvida |
| texto | `text` | o conteúdo |
| cinza | `inactive` | rótulos e texto secundário |
| cinza claro | `subtle` | feito, etapas de fora pendentes |
| borda | `promptBorder` | cartões e trilhos das barras |

O SVG (barras, progresso, gráfico por dia) é desenhado como imagem, fora do tema: `svgDoc` leva, para cada chave, a cor
do tema escuro e a do claro, e o `prefers-color-scheme` do app escolhe. O tema do `/config` que o mod lê é o do CLI,
não o do app, por isso não serve para escolher a paleta.

## Faixa acima do prompt

```text
AiDW it-101662 Revisar   ● codificador · otimizacao-r2 · 2m10s   contexto ▬▬▬▭▭ 160k   7d ▬▬▬▬▭ 58%   5h ▬▬▭▭▭ 32%
```

- **O que mostra:** AiDW, o id da demanda e a etapa atual (com o modelo na frente quando não é desenvolvimento:
  "Revisão de PR · Revisão final"); os agentes rodando (nome, tarefa, tempo), com o ponto laranja, antes das medidas;
  o contexto em tokens e o 7d e o 5h em %, cada um com barra fina. Sem agente rodando, essa parte some.
- **Contexto:** em tokens, não em % da janela (1M): cada ação do orquestrador relê a conversa inteira, então o que
  pesa é o tamanho. A barra enche em 250k e fica amarela daí em diante (o ponto em que o mod sugere `/compact`).
- **7d e 5h a partir de 80%:** a barra e o número ficam amarelos, com a hora local em que a janela renova
  ("91% · renova 18:10"; com o dia, quando não é hoje). **No limite (100%)**, vermelho: "limite · volta 18:10".
- **Dados:** contexto e janelas de uso em `$.session.usage()` (`context`, `rateLimits` `five_hour`/`seven_day`, só em
  assinatura; sem leitura, o 7d e o 5h não aparecem); agentes rodando pelo próprio mod.
- **Saíram:** fase, "espera você", orçamento, rodada e laço travado, AIDW-TESTE e código lido no chat (estão na Geral).

## Painel

Abas por uso:

| Uso | Abas |
|---|---|
| Desenvolvimento | Geral · Critérios e Regras · Revisão · Diffs · Teste manual · Métricas |
| Revisão de PR | Geral · Comentários · Diffs · Métricas |
| Levantamento | Geral · Card × código · Estimativa · Dúvidas · Métricas |

O uso vem dos arquivos da demanda. Uma demanda que fechou o levantamento (`DONE` depois do `ESTIMATE`) e seguiu para
outra etapa já aparece como Desenvolvimento, mesmo antes de o plano ser gravado.

- **Cabeçalho único**, acima das abas: tipo e número (`IT 101662 · Desenvolvimento`), a situação
  (`● Revisão final · espera você`) e o título do card. As abas não repetem o cabeçalho.
- **Abas em texto:** a ativa com moldura, as outras apagadas; ao lado do nome, em laranja, o que espera você
  (achados da rodada, passos do roteiro, comentários a decidir, dúvidas abertas). **Aba sem dados fica oculta** e
  volta quando o arquivo aparece; a Geral fica sempre. Atualizar é o ícone ↻.
- **Teclas:** no terminal, `1` a `6` e `r` aparecem e funcionam; no app, onde a tecla apareceria no botão, as abas
  são só clique.
- **Escolher entre poucas opções** (rodadas, repositórios, PRs): botões lado a lado; uma opção só vira texto; mais de
  4, o seletor do app.
- **Texto dos artefatos** com `código` ou **negrito** é desenhado como Markdown (código em linha), não com crases.
- **Botão principal:** só o de levar ao prompt (ou o de marcar o passo do roteiro). A opção recomendada é um botão
  comum com "(recomendado)" no nome.

### Geral

1. **Mapa da demanda:** resumo de até 4 linhas e o **progresso** numa barra fina em dois grupos: **AiDW** (Entender,
   Plano, Sua aprovação, Implementar, Revisão, Sua revisão, Testes, PR) e **Time e QA** (Code review, Testes QA, Pronto),
   mais as etapas de fora que o contexto acrescenta, como a Validação UX antes da PR, só na demanda que passa por elas
   (as ainda não alcançadas são pontos vazados), com o nome da etapa atual e "etapa N de 11". As etapas de antes do
   fluxo v3 caem na fase equivalente. Quando o time ou a QA devolve, a etapa de fora
   fica amarela com "↩ voltou do Code review · 1ª vez" e a barra volta para onde o ajuste é feito; um contador
   discreto guarda as voltas ("voltas: Code review 1× · QA 1×").
2. **Números**, os do modelo e o consumo:
   - desenvolvimento: critérios de aceite cobertos (com medidor);
   - revisão de PR: PRs e comentários publicados;
   - levantamento: story points, horas, complexidade e confiança, dúvidas abertas;
   - em todos: tokens dos agentes, do orquestrador ("sem registro" quando não há `metricas-orquestrador.md`) e tempo
     de agentes trabalhando.
3. **Próximo passo:** a nota do `demand.json` (`demand set --note`), quando há.
4. **Agentes:** os rodando (nome, tarefa e tempo); sem nenhum, "último: …".
5. **Links:** pasta da demanda e, por repositório, a branch (ou "PR N · só leitura").

- **Tempo de agentes:** soma da duração de cada delegação no `metricas.md`. Revisão de PR e teste da QA não entram:
  nessas etapas nenhum agente roda.
- **Resumo:** `demand.json` → `summary`, gravado pelo orquestrador ao entender o card. Sem ele, só o título.
- **Etapas de fora:** `demand.json` → etapas `CODE_REVIEW` e `QA_TEST`, gravadas pelo orquestrador **quando você avisa**
  no chat (PR aberta, voltou do Code review com ajustes, foi para a QA, a QA devolveu um bug). O automático pelo Azure
  DevOps fica para depois.
- **PRs:** `demand.json` → `repos[].pr`.
- **Saíram:** bloco "Atenção" e contexto.

### Critérios e Regras

- Três cartões: **Critérios de aceite** (`CA1…`), **Regras de negócio** (`RN1…`) e **Cenários** (`CN1…`).
- Cada linha: identificador, texto e status. Não há "como provar".
- **Status pelo nosso código e pelos nossos testes** (Code review e QA não contam), derivado sem trabalho do
  orquestrador (fluxo v3):
  - **Falta:** a demanda ainda não passou da implementação, ou o item não está em nenhuma entrega do plano;
  - **Implementado** (amarelo): a demanda passou da implementação e o item está numa entrega (`Covers:` do plano);
  - **Coberto** (verde): um passo do roteiro que prova o item (coluna `Critério`) tem ✅.
- No topo, a cobertura por tipo com barra de duas cores (verde coberto, amarelo implementado).
- **Dados:** o plano numera os itens com o texto do card (`CA1`, `RN1`) e diz em cada entrega o que ela cobre
  (`Covers: CA1, RN2`); o roteiro do QA diz em cada passo o critério que ele prova (coluna `Critério`) e o resultado.
  Demandas de antes do fluxo v3 com `cobertura-<id>.md` continuam lidas por ele. Sem plano, os critérios vêm do resumo
  do card, todos em "Falta".

### Revisão

- **Rodada** em botões (seletor com mais de 4), por tipo: Código r1…, Otimização r1… (e Plano r1… nas demandas antigas).
- **Decisão** em abas de texto: Com você · Mantidos · Descartados · Todos. Abre em **Com você**; os decididos ficam
  escondidos.
- **Filtros:** botão que abre uma linha de botões liga/desliga por criticidade, categoria (qualidade, bug, segurança —
  do título do achado, ou da passada nas demandas antigas) e status.
- **Cada achado é um cartão:**
  - criticidade, ID, `arquivo:linha` e status (com você, corrigido na rN);
  - o que foi apontado;
  - o código **antes e depois** (vermelho e verde), quando o achado propõe mudança;
  - a **recomendação do AiDW**: manter ou descartar, e por quê;
  - a decisão: Manter e Descartar, a recomendada com "(recomendado)"; nas dúvidas, as opções do próprio achado com o
    texto inteiro numa lista ("(a) …", a primeira é a recomendada) e botões só com a letra.
- Rodapé: **Levar decisões ao prompt**.
- **Dados:** achados no `review-*-rN.md`, com a categoria no título (`R1-01 — IMPORTANTE — bug — `arquivo:linha``), os
  blocos `Antes:` e `Depois:` (cercas de código) e a `**Recomendação:**` do revisor; a decisão vem do `triagem-*-rN.md`,
  que o orquestrador grava a partir da mensagem do painel.

### Diffs

- A fonte em botões (worktrees da demanda e os `.patch`), e o diff da primeira **já abre carregado**; embaixo, a branch
  contra a base, os arquivos e o `+N −M`. Cada `.patch` tem nome legível ("PR 8197 · só a rodada 2", "131192-01 · r1 →
  r2", "ajustes de teste · front") e vem logo depois do worktree da sua PR; o patch inteiro de uma PR que tem worktree
  sai, porque é o mesmo diff. O arquivo escolhido ganha "›"; os outros ficam apagados.
- Duas colunas: a lista de arquivos (nome, pasta, `+/−`, etiqueta "N achados") e o diff do arquivo, com os números
  de linha de antes e de depois.
- Os achados da revisão aparecem abaixo da linha que apontam, com "ver na Revisão".
- Botão **Abrir no app**, o painel de diff do app, para apontar linha a linha.

### Testes

- Progresso no topo (passaram, falharam, faltam), só com os passos ativos; os removidos do roteiro ficam escondidos.
- Cartão **Agora** com o passo da vez: seção, o que fazer, esperado, evidência e **Passou / Falhou / Pular**.
- Lista pelas seções do roteiro, uma linha por passo com o esperado embaixo; a preparação fica recolhida.
- O resultado vai ao orquestrador como mensagem sua.

### Métricas

- **Resumo:** delegações, rodadas de revisão, tokens dos agentes e do orquestrador, tempo de agentes e o custo das
  delegações quando o `metricas.md` traz.
- **Por agente:** barras de tokens; o orquestrador entra como mais uma linha, em laranja, com os turnos e sem tempo
  (o chat fica aberto, o tempo não diz nada).
- **Orquestrador:** cache lido, cache escrito, saída, a parte dele no total da demanda, uma linha por sessão e modelo
  (turnos, a parte que foi cache lido, os tokens e o custo equivalente) e o total. Vem do `metricas-orquestrador.md`, que o mod soma a cada turno (`aidw.py
  record-orchestrator`). O custo é o preço de API (cache escrito a 2× a entrada, o TTL de 1h do chat): uma régua do
  peso no limite do plano, não a conta. O effort do chat não chega ao mod; para comparar efforts, use um chat novo
  para cada um (cada sessão é uma linha).
- Tokens por dia (colunas, com tooltip de chamadas e tempo), só com dois dias ou mais; por modelo/effort em barras.
- Resultado das chamadas e retrabalho como etiquetas com contagem (`missing_state` aparece como "sem state").
- As 8 delegações mais recentes, com "ver todas"; os artefatos em grupos recolhidos.
- Custo em US$ das delegações só quando o `metricas.md` traz.

### Revisão de PR · Comentários

- **Você decide sobre os comentários da triagem** (`C1`, `C2`…; referência *triagem-pr*), não sobre os achados soltos:
  cada comentário junta os achados que dizem a mesma coisa (revisor, bugs, segurança), mostrados como "junta R1-01 ·
  B1-01". Agrupados **por PR**.
- Filtros: A decidir · Publicados · Todos (abre em A decidir quando há o que decidir).
- **Cada comentário:** severidade (Pergunta para dúvida, Pendências QA), id, `arquivo:linha`, a situação da triagem
  ("a decidir", "não publicado (r1)", "publicado (thread 23720), resolvido na r2"), o título, o **texto que vai para a
  PR** com **editar** e **ajustar no chat**, a recomendação e **Publicar** / **Não publicar** (a recomendada com
  "(recomendado)"). Publicados e recusados ficam recolhidos em "Ver comentário".
- **Voto por PR:** a sugestão do revisor e a do AiDW lado a lado, com o porquê; vem marcada a do AiDW (senão a do
  revisor). Sem sugestão na triagem, **nada vem marcado** e o rodapé pede o voto. As opções seguem a escala do contexto
  (`[[mods.votes]]`, padrão Azure DevOps), mais **Sem voto**; Rejeitar fica em **Mais opções**.
- **Fora das PRs:** o que não vira comentário, recolhido.
- Rodapé: o resumo PR a PR ("8197: aprovar · 8208: sem voto · 1 comentário para publicar") e **Levar decisão ao
  prompt**, que manda, por PR, o que publicar, o que não, os textos editados e o voto.
- **Sem triagem no formato *triagem-pr*** (demandas antigas), a aba cai no modelo anterior: os achados da última rodada
  com o rascunho de cada um e um voto só, que também não vem marcado sem sugestão.

### Levantamento

- **Card × código:** o que o card pede; os pontos validados no código, uma linha cada com a situação na frente
  (precisa mudar, é a dor, não muda, nada a reaproveitar), o "hoje no código" e, apagado, o "para a demanda"; 5 à
  vista e "Mostrar mais"; e **Onde a mudança toca** (a seção do levantamento: sistemas, contratos, banco).
- **Estimativa:**
  - os números (SP do card como está, SP quebrado, horas de dev, de QA, complexidade e confiança); o nível e as
    passadas extras só aparecem nos levantamentos de antes do fluxo v3;
  - esforço por bloco em barras de intervalo (mínimo a máximo);
  - a recomendação de quebra em itens, com SP;
  - **Riscos** (o tópico `**Riscos:**` da estimativa, com os subtópicos);
  - rodapé: **Levar ao prompt: comentar no card**.
- **Dúvidas:** as abertas por tema, cada uma com para quem é, o que muda na estimativa, o campo de resposta e
  **ajustar no chat**; as de um grupo "Respondidas …" ficam numa linha cada, 3 à vista e "Mostrar mais".
- **Dados:** o `levantamento-<id>.md` passa a seguir um modelo fixo (ver a referência *levantamento* do contexto):
  tabela "Hoje no código | Para a demanda | Situação", blocos com dias mínimo e máximo, dúvidas com `Para:` e
  `Muda a estimativa:`.

## O que muda fora do painel

| Quem | Passa a gravar |
|---|---|
| `aidw.py demand set` | `--summary` (resumo de até 4 linhas), `--pr <repo>=<n>` e as etapas `CODE_REVIEW` e `QA_TEST` |
| Orquestrador | o resumo ao entender o card; as etapas de fora quando você avisa; as suas decisões dos achados no `triagem-*-rN.md` |
| Planejador | critérios e regras do card numerados como `CA1`, `RN1`, e o `Covers:` de cada entrega |
| Revisor | a categoria no título, `Antes:` e `Depois:` e a `Recomendação:` em cada achado |
| QA | as colunas `Critério` e `Como` e o `Resultado` de cada passo do roteiro |
| Explorador (levantamento) | o modelo novo do levantamento |
