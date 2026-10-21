# Painel e faixa do AiDW (V2)

Especificação da faixa acima do prompt e do painel do AiDW (mod `aidw-mods`, só Claude Code), desenhada tela por
tela com mocks em 14/10/2026. Os mods em geral estão em [mods.md](mods.md); aqui fica o que cada tela mostra, de onde
vem cada dado e o que os agentes passam a gravar para isso.

A faixa vale em todo contexto. O painel só existe no contexto que o liga (`[mods] panel = true` no `context.toml`;
hoje, o safeweb), porque segue os artefatos daquele jeito de trabalhar ([mods.md](mods.md#quando-ficam-ligados)).

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

| Cor | Significado |
|---|---|
| laranja (do Claude) | o que está acontecendo agora: etapa atual, agente rodando, opção recomendada, sublinhado da aba de decisão |
| azul | com o time ou a QA (fora do AiDW) |
| amarelo | atenção: voltou do time ou da QA, perto do limite, implementado sem teste, precisa mudar |
| verde | coberto, corrigido, passou, linha adicionada |
| vermelho | falhou, linha removida |
| cinza | feito, neutro |

## Faixa acima do prompt

```text
AiDW it-101662 · contexto ▬▬▬▭▭ 160k · 7d ▬▬▬▬▭ 58% · 5h ▬▬▭▭▭ 32% · ▶ codificador (otimizacao-r2) 2m10s
```

- **O que mostra:** AiDW, o id da demanda, o contexto em tokens, o 7d e o 5h em %, cada um com barra fina, e os
  agentes rodando (nome, tarefa, tempo). Sem agente rodando, essa parte some.
- **Contexto:** em tokens, não em % da janela (1M): cada ação do orquestrador relê a conversa inteira, então o que
  pesa é o tamanho. A barra enche em 250k e fica amarela daí em diante (o ponto em que o mod sugere `/compact`).
- **7d e 5h a partir de 80%:** a barra e o número ficam amarelos e entra a hora local em que a janela renova (com o
  dia, quando não é hoje).
- **Dados:** contexto e janelas de uso em `$.session.usage()` (`context`, `rateLimits` `five_hour`/`seven_day`, só em
  assinatura; sem leitura, o 7d e o 5h não aparecem); agentes rodando pelo próprio mod.
- **Saíram:** fase, "espera você", orçamento, rodada e laço travado, AIDW-TESTE e código lido no chat (estão na Geral).

## Painel

Abas por uso:

| Uso | Abas |
|---|---|
| Desenvolvimento | Geral · Critérios e Regras · Revisão · Diffs · Teste manual · Métricas |
| Revisão de PR | Geral · Achados e voto · Diffs · Métricas |
| Levantamento | Geral · Card × código · Estimativa e dúvidas · Métricas |

As abas ficam discretas, com fundo só na ativa; as teclas `1` a `6` e `r` (atualizar) continuam. Toda aba abre com o
tipo e o número da demanda pequenos em cima e o título em destaque.

### Geral

1. **Título:** tipo e número (`IT 101662 · Desenvolvimento`), etiqueta de situação (`Revisão final · espera você`) e
   o título do card.
2. **Mapa da demanda:**
   - resumo de até 4 linhas sobre o que a demanda trata;
   - quatro números: critérios de aceite, tokens dos agentes, tokens do orquestrador e tempo de agentes trabalhando;
   - **progresso** numa barra fina em dois grupos: **AiDW** (Entender, Plano, Implementar, Testar, Revisar, Revisão
     final) e **Time e QA** (Code review, Testes QA, Pronto, mais as etapas de fora que o contexto acrescenta, como a
     Validação UX, só na demanda que passa por elas), com o nome da etapa atual e "etapa N de 9". Quando o time
     ou a QA devolve, a etapa de fora fica amarela com "↩ voltou do Code review · 1ª vez" e a barra volta para onde o
     ajuste é feito; um contador discreto guarda as voltas ("voltas: Code review 1× · QA 1×").
3. **Agentes rodando:** nome, tarefa e tempo; sem nenhum, "Nenhum agente rodando · último: …".
4. **Links:** pasta da demanda, branches por repositório e PRs (abrem no Azure DevOps).

- **Tempo de agentes:** soma da duração de cada delegação no `metricas.md`. Revisão de PR e teste da QA não entram:
  nessas etapas nenhum agente roda.
- **Resumo:** `demand.json` → `summary`, gravado pelo orquestrador ao entender o card. Sem ele, só o título.
- **Etapas de fora:** `demand.json` → etapas `CODE_REVIEW` e `QA_TEST`, gravadas pelo orquestrador **quando você avisa**
  no chat (PR aberta, voltou do Code review com ajustes, foi para a QA, a QA devolveu um bug). O automático pelo Azure
  DevOps fica para depois.
- **PRs:** `demand.json` → `repos[].pr`.
- **Saíram:** próximo passo, nota, bloco "Atenção", consumo e contexto.

### Critérios e Regras

- Três cartões: **Critérios de aceite** (`CA1…`), **Regras de negócio** (`RN1…`) e **Cenários** (`CN1…`).
- Cada linha: identificador, texto e status. Não há "como provar".
- **Status pelo nosso código e pelos nossos testes** (Code review e QA não contam):
  - **Falta:** ainda não está no código;
  - **Implementado** (amarelo): o codificador entregou, nenhum teste nosso provou;
  - **Coberto** (verde): um teste nosso prova (unitário, E2E ou do agente QA).
- No topo, a cobertura por tipo com barra de duas cores (verde coberto, amarelo implementado).
- **Dados:** o plano numera os itens (`CA1`, `RN1`, `CN1`); o orquestrador mantém `cobertura-<id>.md` a partir dos
  relatórios do codificador e do QA:

```text
| ID | Status | Evidência |
|---|---|---|
| CA1 | coberto | E2E r2 (resultado-e2e-101662-r2.md) |
| RN3 | implementado | SaneadorDadosEquipamento.cs |
| CN7 | falta | — |
```

  Sem esse arquivo, os critérios do plano aparecem com status "Falta" e um aviso de que a cobertura ainda não foi
  registrada.

### Revisão

- **Rodada** num seletor que agrupa por tipo: Plano r1…, Código r1…, Otimização r1…, com o resultado de cada uma.
- **Decisão** em abas de texto: Com você · Mantidos · Descartados · Todos. Abre em **Com você**; os decididos ficam
  escondidos.
- **Filtros:** botão que abre uma linha de botões liga/desliga por criticidade, origem (revisor, segurança, bugs) e status.
- **Cada achado é um cartão:**
  - criticidade, ID, `arquivo:linha` e status (com você, corrigido na rN);
  - o que foi apontado;
  - o código **antes e depois** (vermelho e verde), quando o achado propõe mudança;
  - a **recomendação do AiDW**: manter ou descartar, e por quê;
  - a decisão: botões com a opção recomendada em destaque (nas dúvidas, as opções do próprio achado, "(a) …", "(b) …").
- Rodapé: **Levar decisões ao prompt**.
- **Dados:** achados no `review-*-rN.md`; o revisor passa a gravar, por achado, os blocos `Antes:` e `Depois:` (cercas
  de código); a recomendação e a decisão vêm do `triagem-*-rN.md`.

### Diffs

- O repositório é o título, com seletor (worktrees da demanda e os `.patch`); embaixo, a branch contra a base, os
  arquivos e o `+N −M`.
- Duas colunas: a lista de arquivos (nome, pasta, `+/−`, etiqueta "N achados") e o diff do arquivo, com os números
  de linha de antes e de depois.
- Os achados da revisão aparecem abaixo da linha que apontam, com "ver na Revisão".
- Botão **Abrir no painel de diff do app**, para apontar linha a linha.

### Teste manual

- Progresso no topo (passaram, falharam, faltam), só com os passos ativos; os removidos do roteiro ficam escondidos.
- Cartão **Agora** com o passo da vez: seção, o que fazer, esperado, evidência e **Passou / Falhou / Pular**.
- Lista pelas seções do roteiro, uma linha por passo com o esperado embaixo; a preparação fica recolhida.
- O resultado vai ao orquestrador como mensagem sua.

### Métricas

- Cinco números: delegações, tokens dos agentes, tokens do orquestrador, tempo de agentes e rodadas de revisão.
- **Orquestrador (chat principal):** uma linha por sessão e modelo, com turnos, a parte que foi cache lido, os tokens
  e o custo equivalente; embaixo, o total. Vem do `metricas-orquestrador.md`, que o mod soma a cada turno (`aidw.py
  record-orchestrator`). O custo é o preço de API (cache escrito a 2× a entrada, o TTL de 1h do chat): uma régua do
  peso no limite do plano, não a conta. O effort do chat não chega ao mod; para comparar efforts, use um chat novo
  para cada um (cada sessão é uma linha).
- Tokens por dia (colunas, com tooltip de chamadas e tempo); por agente e por modelo/effort em barras horizontais.
- Resultado das chamadas e retrabalho como etiquetas com contagem.
- As 8 delegações mais recentes, com "ver todas"; os artefatos em grupos recolhidos.
- Custo em US$ das delegações só quando o `metricas.md` traz.

### Revisão de PR · Achados e voto

- O mesmo cartão da Revisão, mais o **comentário que vai para a PR** (e qual PR), com **editar** e **ajustar no chat**
  (leva o texto ao prompt para refinar com o orquestrador).
- Abas: A decidir · Publicar · Não publicar · Já publicados. Dúvidas viram **Perguntar ao time**.
- Voto em quatro opções lado a lado, com a recomendada destacada e o porquê.
- Rodapé: **Levar decisão ao prompt**.

### Levantamento

- **Card × código:** o que o card pede (com aviso quando não tem critérios); os pontos validados no código, cada um
  com "hoje no código", "para a demanda" e uma etiqueta (precisa mudar, é a dor, não muda, nada a reaproveitar); e o
  que o sistema externo cobre, quando há.
- **Estimativa e dúvidas:**
  - quatro números (SP do card como está, SP quebrado, dias de dev, dias de QA), nível e passadas extras;
  - esforço por bloco em barras de intervalo (mínimo a máximo);
  - a recomendação de quebra em itens, com SP;
  - as dúvidas agrupadas por tema, cada uma com para quem é, a etiqueta "muda a estimativa" quando é o caso, o campo
    de resposta e **ajustar no chat**;
  - rodapé: **Levar ao prompt: comentar no card**.
- **Dados:** o `levantamento-<id>.md` passa a seguir um modelo fixo (ver a referência *levantamento* do contexto):
  tabela "Hoje no código | Para a demanda | Situação", blocos com dias mínimo e máximo, dúvidas com `Para:` e
  `Muda a estimativa:`.

## O que muda fora do painel

| Quem | Passa a gravar |
|---|---|
| `aidw.py demand set` | `--summary` (resumo de até 4 linhas), `--pr <repo>=<n>` e as etapas `CODE_REVIEW` e `QA_TEST` |
| Orquestrador | o resumo ao entender o card; as etapas de fora quando você avisa; o `cobertura-<id>.md` depois de cada entrega do codificador e de cada relatório do QA |
| Planejador | critérios, regras e cenários numerados como `CA1`, `RN1`, `CN1` |
| Revisor | `Antes:` e `Depois:` em cada achado que propõe mudança |
| Explorador (levantamento) | o modelo novo do levantamento |
