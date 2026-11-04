# Auditoria do plugin aidw-mods (v0.2.0) — 2026-11-04

Base: `C:/AiDW/mods/aidw-mods` (~5,3k linhas: register.tsx 648, views.tsx 1650, artifacts.ts 812, snapshot.ts 339, aidw.ts 225,
secrets.ts 116, guards.ts 77; 79 testes passam em `claude plugin test`). Linhas abaixo = `hooks/register.tsx` salvo indicação.

## 0. O aviso "session.append hook was skipped"

- **Qual hook:** `on('session.append')` do filtro de segredos (l.572). O `cc-plugin-sec-default` é um plugin da organização em tier
  *prepend*: roda antes dos plugins do usuário e repassa o evento `session.append` sem chamar o `aidw-mods`. O app avisa isso
  a cada abertura. As memórias já registram o mesmo para `session.compact` e `classic.SessionStart`.
- **O que deixa de acontecer:** o mod não mascara mais as *linhas da conversa* (texto do usuário, do assistente, dos subagentes,
  nota de delegação). Segue valendo o `tool.call` genérico (l.579), que mascara o *resultado das ferramentas* antes de virar
  linha. Lacunas reais: (a) a linha 582 devolve sem filtrar quando `ran.isError` — stack trace/SqlException com connection string
  em erro de Bash/MCP passa; (b) texto digitado/colado pelo usuário e texto do modelo (ex.: o modelo repetindo um segredo lido)
  não passam por nada do mod; só a org filtra.
- **Como resolver (3 opções):**
  1. Aceitar: o filtro de linhas fica por conta do plugin da org; apagar o `on('session.append')` (l.572-577), o teste
     hooks.test.ts:460/506 e o texto de docs/mods.md "Filtro de segredos". O aviso some (o hook não existe mais). **Recomendado**:
     é código morto neste ambiente, e o aviso gera ruído.
  2. Pedir à TI da Safeweb que o `cc-plugin-sec-default` chame `next(e)` (ou rode em tier normal) — só assim o hook volta a valer.
  3. Fechar a lacuna em vez de depender do hook: filtrar também `isError` no `tool.call` (melhoria M1) e o `prompt.submit`
     (o texto do usuário pode ser redigido em `e.text` antes do `next`).
- O aviso em si não impede nenhum outro hook (`prompt.submit`, `tool.call`, `ui.render`, `turn.complete`, `session.start` chegam).

## 1. Mapa dos mods e custo em tokens no chat do orquestrador

| Hook / mod | Quando roda | Lê / escreve | Texto que volta ao chat |
|---|---|---|---|
| `session.start` (l.411) | abertura | `state/sessions.json`, `runtime.json`, demanda; registra `/faixa /painel /metricas /testes-review`; `clock.every(5s)` | 0 |
| `prompt.submit` (l.436) | cada mensagem | `sessions.json` (checkActive), `$.session.usage`, notas KB | nota de estado pós-compactação (~150-250 tok, 1x por compactação) + `[[nota]]` (até 3 × 6000 chars ≈ 1,5k tok cada, **repete a cada mensagem que cita**) |
| `tool.call Agent` (l.~455) | cada delegação | guards, `demand.json`+arquivos da demanda (refresh), `python aidw.py record` | recusa (~80-120 tok) ou `notice` (~100-130 tok: header+resumo+instrução) por delegação |
| `agent.spawn`, `turn.step` | subagente | só estado (atoms, `lastUsage`) | 0 |
| `turn.complete` agente bg (l.550) | fim do agente em 2º plano | `session.messages`, `record` | **mensagem de usuário injetada** via `$.session.append` (l.562, ~110 tok) — pode acordar um turno inteiro do orquestrador (releitura de cache) |
| `turn.complete` orquestrador (`endOfTurn`, l.345) | fim de cada turno | `refresh` 2x, `git grep` por repo, `python aidw.py record-orchestrator`, `session.usage`, agenda compactação 50 min | 0 |
| `tool.call Read` (l.~520) | cada Read de código fora de C:/AiDW | contador | aviso de ~75 tok **em toda leitura** (texto idêntico, repetido n vezes) |
| `tool.call Bash/PowerShell` | cada comando | regex `aidw.py demand set` → refresh | 0 |
| `tool.call` genérico (l.579) | **todo** resultado de ferramenta | `redactValue` percorre o resultado inteiro (regex) | 0, ou o resultado com máscaras |
| `session.append` (l.572) | **pulado** neste ambiente | — | — |
| `ui.render AbovePrompt` / `Pane` | cada render | `runtime.json` do disco a cada render (sem cache), atoms | 0 (faixa e painéis não entram no contexto do modelo) |
| `compactIdle` (l.322) | 50 min após o turno, ≥100k tok | `session.compact` com instruções | resumo da compactação (custo do próprio compact) |

Total típico por demanda de 15-25 delegações: ~2-3k tokens de `notice` + 75 tok × leituras de código + notas KB; o grande custo
**não é o texto do mod**, é o que ele permite (cache relido a cada turno) e o `session.append` bg que gera turno extra.

## 2. Bugs, fragilidades, retrabalho, testes que faltam

**Bugs / fragilidades confirmados ou prováveis**
1. **Redação não idempotente** (`secrets.ts` l.13 e regra "connection string" l.28-33). A máscara `Password=«segredo ocultado: Password, 11 caracteres»`
   passando de novo pelo filtro tem o valor casado como `«segredo` (para no espaço) e é mascarada outra vez; o regex de placeholder
   `^«segredo ocultado` não casa com `«segredo` sozinho. Prova: minha leitura de `docs/mods.md:157` e `tests/secrets.test.ts:9` chegou
   aqui como `...caracteres» ocultado: Password, 8 caracteres» ocultado:...` (no disco os bytes estão certos; o texto estragou por duplo filtro:
   resultado do subagente + linha). Qualquer máscara que o modelo copie de volta num Write/Edit/comentário de card vira lixo.
2. **`record()` falso-negativo → linha duplicada** (l.252-283): `JSON.parse(ran.stdout)` falha se o `aidw.py` imprimir uma linha a mais
   (aviso, encoding) → `null` → `notice` manda o orquestrador rodar `record` "à mão" embora a linha já tenha sido gravada. `recorded_by_mod`
   (aidw.py:4509) só evita duplicata se o `record` manual vier sem números.
3. **Agente em 2º plano + recarga:** `lastUsage` é `Map` de módulo (l.57), perdido num `/reload-plugins`/`aidw.py install`; o `turn.complete`
   do agente cai em `header = null` (l.558) e o `pending` já foi apagado → a delegação **não é registrada** e o orquestrador recebe
   "não conseguiu registrar". O doc diz que o pendente sobrevive à recarga, mas os tokens não.
4. **Guard de modelo fraco** (`guards.ts` l.27): `MODEL_WORDS` inclui "modelo" — palavra comum em PT ("modelo de plano", "modelo do roteiro"); basta
   citá-la nas últimas 8 mensagens para liberar `model`. `userPrompts` também é variável de módulo (zera em recarga).
5. **`parseDelegation`** (aidw.ts:8): exige drive `X:` ou `/` e para no primeiro espaço — pasta com espaço (o `C:\Users\felipe.louzada\.claude\Agents\Orquestrador\demandas`
   não tem, mas qualquer outra) não é reconhecida → sem trava, sem métrica, **sem aviso**.
6. **`testMarks` caro** (l.155): `git grep --untracked` por worktree em todo `refresh`, e `refresh` roda 2x por turno + a cada `demand set` +
   a cada delegação, nas etapas de MARK_STEPS; timeout 15 s por repo, sequencial. Em repo grande (Emissão, eCommerce) trava o fim do turno.
7. **Escritas de métrica sem trava:** `record_orchestrator` (aidw.py:4547) lê o arquivo inteiro e reescreve; duas sessões na mesma demanda
   (ou um `record` manual) perdem linhas. `append_metrics` usa append (ok) mas a conferência de `\n` final é corrida.
8. **Custo do orquestrador atribuído à demanda do `snap`:** turnos antes de existir `demand.json`/snapshot (UNDERSTAND de card novo)
   não são gravados (`before` nulo, l.348) → subestima justamente o início (leitura de card, KB). *Verificar com um card novo.*
9. **Ociosa sem checar agentes rodando:** `compactIdle` (l.322) não olha `running`/`background`; compactar com agente em 2º plano e esperando
   resposta do usuário depende só do texto de `instructions`.
10. **Cache de KB nunca invalida** (`kbCache`, l.60/360): nota criada no `/aidw:done` não aparece até recarregar; regex `[[nota]]` não aceita acento.
11. **`runtimeJson` sem cache** (l.72): lido do disco em cada render da faixa/painel (a cada 5 s com agente rodando), em `panelOn`, `specOf`, `loadRuntime`...
12. `session.start` cria `clock.every(5000)` sem guardar o handle: cada recarga soma um intervalo.
13. Dead code do fluxo v2: `BUDGET`/`budgetFor` (aidw.ts:145, snapshot.ts:208) mesmo com "sem orçamento"; `--level` no `record`; `PLAN_STEPS`
    com `PLAN_REVIEW`/`TICKETS`, `bugs-`/`seguranca-`; `parseMetricas` sem uso.
14. **Parsing de markdown por regex posicional:** `parseMetricas`/`parseDelegations` exigem ≥12 células e data `^\d{4}`; formato `Tokens entrada` com
    `117,050` (vírgula = milhar) vs `usd()` aceita "0,42" decimal — duas convenções no mesmo arquivo; coluna nova no `aidw.py` quebra tudo em silêncio.
    Mesmo para triagem (`| ID | Decisão | Motivo |`), roteiro e levantamento: um título diferente = aba vazia, sem aviso (o painel só "some").

**Retrabalho visível no git (80 commits, 23 em `mods/`)**
- `views.tsx` e `register.tsx`: 17 commits cada em ~3 semanas. Faixa refeita 8x (V2 → v3 tema → v4 → espaçamento → métricas à direita →
  cards → cards compactos); painéis: aba Diffs criada e removida, "Decidir" com botões → "Decisões" → "Testes e Review" só informativo.
- Compactação: 4 políticas em 11 dias (troca de etapa 150k → espera → ociosidade 50 min/100k → nota pós-compactação por `prompt.submit`
  porque `session.append`/`session.compact`/`SessionStart` não chegam), cada uma com doc e teste.
- Níveis de demanda (opus-só-crítica, orçamento por nível) criados em V2 e removidos no fluxo v3; toasts criados em 943e33d e removidos no v4;
  limite de rodadas criado e removido (F7).
- Causa comum: decisão de desenho sem medir antes. Falta um "simulador"/fixture visual e uma medição de uso real do painel para decidir.

**Testes que faltam**
- Idempotência do `redact` (máscara dupla) e `redactValue` com `isError`; PEM grande/backtracking; resultado de MCP com imagem base64.
- `turn.complete` bg depois de recarga (sem `lastUsage`); duas delegações paralelas (`running` e `record` concorrentes).
- `compactIdle` (agente rodando, <100k, skip), `stateAfterCompaction` (heurística 40k/metade), `testMarks` com `git` falhando.
- `checkActive` (sessions.json corrompido, `fromArgument` por número), `parseDelegation` com espaço/UNC.
- **Contrato real com o `aidw.py`:** os testes simulam `process.run`; nenhum roda `aidw.py record` de verdade e confere o JSON (header/resumo) — a
  fonte mais provável de quebra silenciosa quando o Python muda.
- `views.tsx` (1650 linhas) tem 1 teste de cores; nada de renderização (largura estreita, tema, terminal vs app).
- Guard: casos `aidw:` vs nome nu, agente desligado, `general-purpose` passando, `model` com e sem "modelo" no texto.

## 3. Lacunas de valor

**O que o Felipe ainda precisa perguntar no chat e um mod poderia mostrar**
- "Quanto já gastou esta demanda **por etapa**?" — `metricas-orquestrador.md` é por sessão×modelo; sem etapa. A faixa só mostra o contexto atual e 5h/7d.
- "O que está rodando/bloqueado e há quanto tempo?" — agente em 2º plano sem retorno há >N min não alerta.
- "Qual a próxima ação / o que falta para a PR?" — `nextStep` existe no painel, mas não na faixa; falta o checklist da PR (marcas AIDW-TESTE = 0?,
  roteiro sem pendência, triagem fechada, plano aprovado, Tasks criadas) num lugar só.
- "Quantos achados abertos/mantidos faltam corrigir?" — só no painel, e só se o painel estiver aberto; o botão mostra contagem de "decisão pendente",
  não "mantidos aguardando fix".
- "Qual worktree/branch/base está ativo e se há alteração local não commitada?" — só `repos` no demand.json; sem `git status` resumido.
- "Esse orquestrador está lendo muito código?" — contagem `codeReads` não aparece na faixa.
- Custo do dia/semana do **orquestrador** versus agentes (Opus High × Medium é teste em andamento segundo a memória) — nenhuma tela compara.

**Travas que evitariam erros que aparecem nas demandas**
- Delegar `dev` antes de `PLAN_APPROVAL` aprovado (regra "nada vai ao coder sem OK") — o guard não lê `demand.json`.
- Delegar o mesmo agente na mesma etapa mais de uma vez sem motivo (regra "cada agente roda uma vez por etapa"); hoje o doc proíbe, nada trava.
- Prompt sem linha de MCP ("No MCP tools needed" / servidor+objetivo) — regra de CLAUDE.md, não conferida.
- Tarefa (`Tarefa: x.md`) inexistente na pasta da demanda, ou worktree citado fora de `C:/wt/<demanda>`; dev/qa apontando para o repo principal
  (o hook do AiDW pega só Edit/Write).
- `demand set --step` pulando etapas (ex.: IMPLEMENT sem PLAN_APPROVAL no histórico; PR sem USER_REVIEW/TEST) e `--step DONE/CODE_REVIEW/QA_TEST` (só o usuário move).
- `git commit/push` antes de `grep AIDW-TESTE` vazio (hoje é o orquestrador que lembra; o mod já calcula `testMarks`).
- Escrita no ADO (state change) por agentes — policy diz "nunca"; hoje só permissão do CLI.

**Medições que faltam**
- Custo do orquestrador **por etapa** (ver M2) e por tipo de ação (leitura de arquivo, resultado de agente, resposta ao usuário).
- Custo real em USD por delegação: `metricas.md` grava "—" para agentes nativos (só `totalTokens`). O mod já recebe, via `turn.step`, o uso por resposta
  (input/cache_write/cache_read/output): somar por agente dá o custo equivalente exato (como o `api_cost` já faz para o orquestrador).
- Cache hit/miss e quantas vezes a conversa foi regravada (cache_creation do turno depois de >1h parado): mostra se a compactação ociosa vale.
- Tamanho do contexto injetado pelo mod (soma dos `context` adicionados) — hoje invisível.
- Latência que o mod adiciona ao fim do turno (python record-orchestrator + git grep + refresh) — não medida.
- Tempo de espera do usuário por etapa (quanto a demanda ficou em "espera você").

## 4. Melhorias concretas (ordenadas por valor/esforço)

| # | Melhoria | Onde | Impacto | Esforço |
|---|---|---|---|---|
| M1 | **Filtro idempotente e cobrindo erros:** tratar `«segredo ocultado` como placeholder (`secrets.ts:13`: regex `^«segredo`), parar a regra de connection string em `»`; filtrar também quando `ran.isError` (`register.tsx:582`) e o `e.text` do `prompt.submit`; teste de máscara dupla | secrets.ts:13,28-33; register.tsx:436,579-583; tests/secrets.test.ts | Segurança (policy de segredos) + fim do lixo em docs/cards | P (1-2 h) |
| M2 | **Custo do orquestrador por etapa:** gravar `Etapa` (snapshot.step) na linha do `metricas-orquestrador.md` (chave sessão×modelo×etapa) e mostrar tabela por etapa em Métricas; passar `--step` do `recordTurn` | register.tsx:309-318,345-355; aidw.py:4547-4590; views.tsx (Métricas); aidw.ts parseOrchestrator | Responde o "onde gasta?" que o Felipe mede à mão (76% do custo está no chat) | M (3-4 h) |
| M3 | **Custo USD por delegação nativa:** somar `turn.step` por agente (`lastUsage` → soma input/cache_w/cache_r/out) e passar ao `record` para calcular com `api_cost` em vez de "—"; guardar em atom, não Map de módulo (corrige também o item 3) | register.tsx:57,523-535,558; aidw.py:4509+ (record aceita `--cache-*`) | Custo real por agente/etapa, comparativo Haiku/Sonnet/Opus | M (3 h) |
| M4 | **Trava "plano aprovado antes do dev/qa/docs board":** o guard lê `demand.json` (step/history) e recusa `dev*` se `PLAN_APPROVAL` não está no histórico; recusa o mesmo agente 2x na mesma etapa sem a exceção no prompt (`motivo:`); exige linha de MCP no prompt | guards.ts:41-76 (+ campo `demand` em DelegationCheck); register.tsx:~457 (carregar demand.json) | Evita o erro mais caro (código sem aprovação/rodada repetida) | M (3 h) |
| M5 | **Dedup e teto do texto injetado:** o aviso de Read só na 1ª e a cada 5ª leitura (ou só texto curto "AiDW: Nª leitura de código, delegue ao explorador"); `[[nota]]` só na 1ª menção da sessão, resumo do `--brief` em vez de 6000 chars; `notice` encurtado (~40 tok) | register.tsx:286-292,377-389,392-402,~520 | −1 a −5k tok/demanda, a custo de cache relido | P (1-2 h) |
| M6 | **Trocar `session.append` bg por notificação sem turno** e remover o hook morto: o aviso do agente em 2º plano via `$.session.append` (l.562) acorda o orquestrador; avaliar `context` no próximo `prompt.submit`/ `tool.call` e remover `on('session.append')` (l.572) para tirar o aviso da abertura | register.tsx:550-577; docs/mods.md "Filtro de segredos" | Menos ruído, menos turnos extras, menos código inalcançável | P-M (2 h) |
| M7 | **Reduzir custo do `refresh`:** cachear `runtimeJson` (invalidar por mtime), rodar `testMarks` só em `PR`/`TEST*` e só se o arquivo mudou, um único `refresh` por turno, `git grep` com `--max-count` e timeout curto | register.tsx:72,105-130,155,221,345-355 | Fim do turno mais rápido, menos I/O a cada 5 s | P (2 h) |
| M8 | **Contrato do `record` robusto:** parsear a última linha JSON do stdout (ou `--json` no aidw.py), distinguir "gravou" de "falhou" pelo `exitCode`, e só pedir ao orquestrador o `record` manual quando de fato falhou; teste que roda o `aidw.py` real | register.tsx:252-283; tests/hooks.test.ts; aidw.py record | Elimina linha duplicada/ausente, base das métricas | P (1-2 h) |
| M9 | **Faixa mostra o que o Felipe pergunta:** `próxima ação` (do `nextStep`), idade do agente em 2º plano ("há 8 min"), mantidos aguardando fix, `AIDW-TESTE` pendente antes do PR, tokens injetados pelo mod | views.tsx (Band); snapshot.ts nextStep; register.tsx ui.render | Menos perguntas no chat; evita commit com ajuste de teste | M (4 h) |
| M10 | **Testes de contrato do formato dos artefatos + validação:** `claude plugin test` com fixtures reais copiadas (anonimizadas) de `demandas/*` (metricas, triagem, roteiro); no painel, um "formato não reconhecido: <arquivo>" em vez de aba sumida; remover dead code (BUDGET, level, PLAN_REVIEW) | tests/; artifacts.ts:251-420,531-570,732-790; aidw.ts:145-154 | Quebra silenciosa vira visível; menos manutenção | M (4-6 h) |

Ordem sugerida: M1 → M8 → M6 → M5 → M3 → M2 → M4 → M7 → M9 → M10.
