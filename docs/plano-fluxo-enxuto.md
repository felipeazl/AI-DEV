# Plano — AiDW enxuto (v3 do fluxo)

> Fases 0 a 2 implementadas em 2026-10-23 (branch `feature/fluxo-v3` no AiDW e no contexto safeweb); fases 3 a 5 a seguir.

Rascunho para o Felipe revisar e aprovar antes de qualquer mudança (2026-10-23). Nada foi alterado ainda.

## 1. Diagnóstico (o que os arquivos mostram)

| Fato | Evidência | O que significa |
|---|---|---|
| O chat do orquestrador é ~76% do custo | medição de 13–21/10 (memória `gasto-do-orquestrador`); m-144245: US$ 19 equiv., 23 turnos, 39M de cache lido (`metricas-orquestrador.md`) | **custo ≈ nº de chamadas de ferramenta do orquestrador × tamanho do contexto.** Cada `record`, `demand set`, triagem, cobertura, checklist e leitura de arquivo relê 200–340k tokens |
| O prompt do orquestrador tem 64 KB (~16k tokens) | `CLAUDE.md` = ORCHESTRATOR.md (23 KB) + contexto orquestrador (12 KB) + policies + tabelas | relido em toda chamada; metade descreve etapas que vão sair |
| Os prompts dos agentes são grandes | `contexts/safeweb/agents/`: documenter 19 KB, reviewer 17 KB, coder 15 KB | cada ferramenta do agente relê isso |
| Uma feature roda de 12 a 34 delegações | bug-146133: 12 delegações (simples); m-144245: 21; it-101662: 34 (3 rodadas do plano, segurança 2×, T1/T2 2×, ~10 só de ambiente E2E) | etapas demais e limites que não seguraram |
| Os tokens dos agentes em segundo plano estão inflados de 10 a 30× | correção ainda **não commitada** em `mods/aidw-mods/hooks/register.tsx` (diff local) | os 24% do qa e os 19% do bugs da análise anterior estão superestimados; os números antigos do `metricas.md` não servem para comparar |
| A base de conhecimento **não é o vilão**, mas soma | `kb show gedar-aci` imprime 28 KB (~7k tokens: a nota + 38 backlinks) direto no chat do orquestrador, que fica lá a demanda toda; `aprendizados-<id>.md` mantido a cada etapa (mais chamadas); `/aidw:done` (9 KB) roda no Opus | ~1–3% do custo, mas é custo fixo de toda demanda e fácil de cortar |

Conclusão: o ganho maior vem de **menos etapas e menos registro no chat do orquestrador**, e de um prompt menor. Cortar agentes ajuda, mas sozinho não resolve.

## 2. Fluxo novo (um só para feature, bug, melhoria, item técnico, dívida e hotfix)

| # | Etapa (`step`) | Quem | Modelo/effort | Saída | Para em você? |
|---|---|---|---|---|---|
| 1 | `UNDERSTAND` | orquestrador | Opus medium (chat) | `resumo-<id>.md` (card, critérios, decisões dos comentários, UX, notas da base que importam) | só se já houver trabalho (Tasks/PR/branch) |
| 2 | `EXPLORE` | explorador | Haiku | `exploracao-<id>.md`: perguntas numeradas, `arquivo:linha`, contratos, ids e consultas (SELECT pelo validador) | não |
| 3 | `PLAN` | planejador | Sonnet high | `plano-<id>.md`: SDD simples e autossuficiente (comportamento atual, desejado, `CA`/`RN` numerados, arquivos por entrega, build, riscos) | — |
| 4 | `PLAN_APPROVAL` | você + orquestrador | — | o orquestrador lê, aponta o que não fecha; você aprova ou pede ajuste → planejador (fix, Sonnet medium) | **sim — o plano só segue com o seu OK** |
| 5 | `BOARD` — **em paralelo com o 6** (dentro do `IMPLEMENT`) | documentador + orquestrador | Haiku | documentador: anexa o plano e cria as Tasks no padrão (texto simples). Orquestrador: worktree e branch | não |
| 6 | `IMPLEMENT` | codificador | Sonnet high | código + build; um codificador por entrega do plano (paralelo quando são arquivos diferentes) | não |
| 7 | `REVIEW` → `TRIAGE` (você decide) → `CODER_FIX` | revisor ⇄ codificador | revisor Sonnet high na 1ª; rodadas seguintes só das correções em medium (low se a correção é trivial); codificador medium nas correções | `review-<id>-rN.md` (qualidade + bugs + segurança numa passada) | **sim — cada rodada: os achados vão para você e para o orquestrador decidirem (aba Revisão)** |
| 8 | `USER_REVIEW` | você | — | sua revisão do código (aba Diffs); pediu ajuste → `CODER_FIX` e revisão só daquilo | **sim** |
| 6b | `TEST_PLAN` — **em paralelo com o 6** (Felipe, 2026-10-23) | qa | Sonnet medium | `roteiro-testes-<id>.md`: cada `CA`/`RN` → passos, esperado, evidência, **como prova** (`auto-api`, `auto-browser`/E2E ou `manual`) e a **massa de dados levantada** (SELECT; escrita só proposta, em blocos) | aprovações de escrita (um OK por bloco) |
| 9 | `TEST` | qa, depois você + orquestrador | Sonnet medium | o qa primeiro confere o roteiro contra o diff final e acerta só os passos que a revisão tocou; depois **roda sozinho** o que é automático (API, E2E/navegador pelo Claude in Chrome ou pelo Playwright) e marca o resultado no roteiro; o que sobra `manual` (desktop/WPF, ou o que o qa não conseguiu no navegador) é o teste assistido pela aba Testes. Falhou → `CODER_FIX` → revisão só da correção → reteste só dos passos afetados | **sim, nos passos manuais** |
| 10 | `PR` | documentador, depois o orquestrador | Haiku | o documentador escreve `pr-<id>.md` (mensagem de commit, título e descrição da PR, pendências para a QA); com o seu OK, o orquestrador faz **commit, push e abre a PR** (skill `ado-abrir-pr`) e anexa o que vai no card | **sim — OK único de commit, push e PR** |
| 11 | `DONE` | você roda `/aidw:done` | Opus (chat) | a base de conhecimento a partir do `kb collect` (seção F) e o commit do contexto | OK do commit do contexto |
| — | `UX_VALIDATION`, `CODE_REVIEW`, `QA_TEST` | você move | — | como hoje | — |

**O que sai do fluxo:**
- os níveis (trivial…critica);
- a revisão do plano por agente;
- o plano de testes antes da implementação (o qa entra depois da sua revisão);
- `ORCHESTRATOR_TEST`: o navegador é sempre do qa; o que ele não conseguir vira passo `manual` do roteiro, que você executa com o orquestrador pilotando;
- `TEST_ADJUST` como etapa (vira tarefa avulsa do codificador, só quando o roteiro exige um bypass ou flag);
- `PREPARE_REVIEW` e o `checklist-revisao.md` (o revisor recebe o plano, o diff e o build; as pendências para a QA e os anexos `.sql` vão para o `pr-<id>.md`);
- as passadas separadas de bugs e segurança;
- `DOCS` (a doc do repositório já vem no código);
- os `tarefa-*.md` escritos pelo planejador (o plano é a tarefa do codificador: `plano-<id>.md` + a entrega `E1`). O orquestrador só escreve uma tarefa curta quando ela tem algo que não está em outro arquivo: as perguntas do explorador, as decisões de uma correção;
- `cobertura-<id>.md` mantido à mão (a aba Critérios e Regras passa a ler o plano e o roteiro; seção E);
- o `aprendizados-<id>.md` atualizado pelo orquestrador a cada etapa (os aprendizados continuam, de outro jeito; seção F);
- `verificar-premissa` como obrigação em toda triagem (fica como skill, usada quando há dúvida real).

**Caminho curto (bug da QA, pedido da PR, ajuste):** `resumo-bug-<n>.md` → explorador só se a causa não estiver clara → codificador (medium) → revisor (medium, só da correção) → você → reteste só dos passos afetados. O plano ganha uma linha em *Adendos*.

**Regra de economia:** cada agente roda **uma vez por etapa**. Uma nova rodada só acontece por um motivo nomeado: o seu ajuste, um achado mantido, um teste que falhou ou o resultado não fazer sentido. Neste último caso, o orquestrador refaz uma vez com o effort acima e diz por quê.

**PR de outro dev** e **levantamento** continuam como fluxos próprios, com os agentes novos:
- PR de outro dev: um revisor Sonnet high, já com bugs e segurança;
- levantamento: explorador (ver a decisão D2).

## 3. Agentes e effort (sem níveis)

| Agente | Padrão | Pode descer para | Pode subir para | Absorve |
|---|---|---|---|---|
| orquestrador | Opus medium (o chat) | — | — | — |
| explorador | Haiku; **Sonnet high no levantamento** | — | Sonnet medium, uma vez, quando o resultado do Haiku não fez sentido (com o motivo) | **api** (consultas, ids, contratos, SELECT pelo validador) |
| planejador | Sonnet high | Sonnet medium (ajuste do plano) | — | — |
| codificador | Sonnet high | Sonnet medium (correção pequena, ajuste de teste) | — | — |
| revisor | Sonnet high | Sonnet medium / low (re-revisão só das correções) | — | **bugs + segurança** (seções da skill `code-review`) |
| qa | Sonnet medium | — | Sonnet high (raro, com o motivo) | parte do **api** (massa de teste; escrita só proposta) |
| documentador | Haiku | — | — | board (Tasks) e o texto da PR |

- Opus nos agentes só quando você pedir.
- Saem os agentes `api`, `bugs` e `seguranca`, e todas as variantes por nível. Sobram 9 definições de subagente (hoje são ~40).

## 4. O que muda, por componente

### A. Configuração e gerador (`aidw.config.toml`, `orchestrator/config/routing.toml`, `aidw.py`)
- **`aidw.config.toml`:**
  - removo `api-db`, `bug-hunter` e `security`;
  - os modelos e efforts ficam os da tabela acima;
  - o qa mantém Claude in Chrome (o seu Chrome, já logado, o preferido para tela com login), Playwright (E2E sem sessão) e Chrome DevTools (console, rede).
- **`routing.toml`:**
  - sai `[effort.levels.*]`;
  - entra `[effort.variants]`: por papel, o padrão e as variantes permitidas, com o *quando* de cada uma;
  - os estados de `[rules]` passam a ser os das etapas novas (`plan_ready` → `PLAN_APPROVAL`, `review_ready` → `USER_REVIEW`…);
  - `max_retries = 3` fica como trava de segurança da revisão (você decide cada rodada) e `max_retries_plan` sai.
- **`aidw.py`:**
  - `attach_variants`, `effort_table`, `level_cells` e `levels_section` passam a gerar a tabela "Agentes e effort" a partir de `[effort.variants]`;
  - o `Nível:` sai do prompt de delegação;
  - `record` sem `--level`;
  - `demand set` com os steps novos e um alias dos antigos, para não quebrar as demandas abertas;
  - os testes `tests/test_apply.py` e os `golden` são atualizados;
  - **Codex (D6):** agentes, variantes, skills, workflows e o prompt do orquestrador continuam gerados para o Codex. As variantes usam o equivalente pelo tier (Sonnet → mid, Haiku → fast). Só o que é exclusivo do Claude Code fica de fora: o mod, o painel e a trava da delegação. A fase 1 roda `apply` com `provider = "codex"` num dry-run e confere os `golden` do Codex.

### B. Agentes (`agents/*/AGENT.md`, `contexts/safeweb/agents/*.md`, skills)
- **explorador:**
  - ganha a parte de consulta do `api-db`: o mapa `ambiente/apis-e-banco.md`, o SELECT pelo `sql-consulta.ps1`, descobrir ids e o contrato das APIs;
  - não escreve nada.
- **revisor:**
  - a skill `code-review` ganha duas seções curtas, *Bugs* (cenário de falha concreto) e *Segurança* (caminho de ataque concreto), com as armadilhas Safeweb que hoje estão em `bug-hunter.md`/`security.md`;
  - cada achado leva a categoria (qualidade/bug/segurança), a recomendação (manter/descartar e por quê) e o `Antes:`/`Depois:`.
- **planejador:**
  - o plano SDD enxuto, com entregas `E1`, `E2` (cada uma: arquivos `arquivo:linha`, o que fazer, os `CA`/`RN` cobertos e o comando de build), feito para o codificador trabalhar sem buscar;
  - sem tickets separados, sem nível e sem passadas extras;
  - modo fix só para o seu ajuste.
- **qa (reescrito):**
  - **modo plano**, em paralelo com o codificador, logo depois da sua aprovação do plano: lê o plano aprovado e a exploração (ainda não há diff) e escreve `roteiro-testes-<id>.md` no formato da aba Testes: seções, passo, `CA`/`RN` provado, esperado, evidência, como prova (`auto-api`/`auto-browser`/`manual`), a massa por cenário e os blocos de escrita que precisam de você;
  - **modo teste**, depois da sua revisão de código: confere o roteiro contra o diff final (acerta só o que a revisão mudou) e roda sozinho os passos `auto-*` (API e E2E/navegador pelo Claude in Chrome ou pelo Playwright) e grava ✅/❌ com a evidência no próprio roteiro; os `manual` ficam para o teste assistido;
  - um orçamento de cenários pequeno (os critérios do card e a regressão da área tocada), sem matriz exaustiva;
  - a skill `plano-testes-qa` é enxugada para esse modelo.
- **documentador:** dois modos:
  - **board:** anexar o plano e criar as Tasks pelo padrão atual, títulos e descrição simples (`redigir-work-item`, `ado-anexar-arquivo`);
  - **PR:** `pr-<id>.md` com a mensagem de commit, o título e a descrição da PR e as pendências para a QA (ConfigManager, scripts `.sql` na ordem). Quem executa é o orquestrador, com o seu OK.
- **codificador:**
  - recebe `plano-<id>.md` + a entrega;
  - continua com a doc do repositório;
  - sai a parte de ajustes de teste por etapa.
- **Cortar texto:** os `contexts/safeweb/agents/*.md` perdem o que fala de níveis, passadas, cobertura, plano de testes antecipado e E2E. Meta: nenhum acima de ~8 KB.
  - `api-db.md` → dividido entre `explorer.md` e `qa.md`;
  - `bug-hunter.md` e `security.md` → resumidos no `reviewer.md`;
  - os diretórios `agents/api-db`, `agents/bug-hunter` e `agents/security` e as skills `bug-hunt`/`security-audit` saem.

### C. Orquestrador (`orchestrator/ORCHESTRATOR.md`, `contexts/safeweb/agents/orchestrator.md`, referências)
- Reescrever o `ORCHESTRATOR.md`, de 23 KB para ~8 KB, com o fluxo da seção 2, as regras de autonomia e a apresentação dos resultados.
- O contexto do orquestrador, de 12 KB para ~5 KB.
- As referências `passadas-extras`, `preparar-revisao` e `plano-execucao` saem.
- As referências `revisao-final` e `cards-azure-devops` são enxugadas para o novo `USER_REVIEW`/`PR`.
- **Meta: `CLAUDE.md` gerado ≤ 25 KB** (hoje 64 KB).
- **Menos registro no chat:**
  - sem `cobertura`, sem `aprendizados` e sem checklist;
  - o `record` só pelo mod;
  - um `demand set --step` por etapa (não por ação);
  - a triagem vira só as suas decisões, gravadas a partir da mensagem do painel;
  - o resultado do agente chega curto: só o `resumo` e o caminho do relatório, e o orquestrador lê o relatório só quando precisa decidir algo nele.

### D. Workflows (`workflows/*.yaml`, mapa do contexto)
- `feature`, `bugfix`, `refactor` e `hotfix` viram um só: `desenvolvimento.yaml`, com as etapas da seção 2.
- No bug, a pergunta da causa-raiz vai para o explorador.
- No refactor, o plano diz "sem mudança de comportamento" e o roteiro de testes cobre a regressão.
- `pr-review.yaml` e `levantamento.yaml` ficam, com os agentes novos.
- O mapa de tipo de card → workflow no `context.toml` é atualizado.

### E. Mod e painel (`mods/aidw-mods`)
- **Trava da delegação (`guards.ts`):**
  - sai a checagem de `Nível`/célula;
  - entra: o `subagent_type` precisa ser uma das variantes de `[effort.variants]`, e o prompt precisa da `Tarefa`/plano e da pasta;
  - a trava do loop fica só para a revisão.
- **Etapas (`artifacts.ts`, `snapshot.ts`, `register.tsx`):**
  - o progresso novo: AiDW = Entender · Explorar · Plano · Sua aprovação · Implementar · Revisão · Sua revisão · Testes · PR; Time e QA = Code review · QA · Pronto;
  - os textos de status mudam junto;
  - alias dos steps antigos, para as demandas abertas.
- **Abas:**
  - **Geral:** fica, com o progresso novo;
  - **Revisão:** fica, e passa a ser central; sem as rodadas "Plano rN"; o filtro de origem vira filtro de categoria (qualidade/bug/segurança);
  - **Diffs:** fica (a sua revisão de código);
  - **Teste manual:** fica, e vira **Testes**; lê o roteiro do qa, com a massa de cada passo à vista;
  - **Métricas:** fica, sem "nível";
  - **Critérios e Regras (D4):** fica, simplificada e sem trabalho para o orquestrador:
    - os `CA`/`RN` vêm do plano, e o planejador copia os do card com o texto do card;
    - o status é derivado: *falta* até a entrega `E<n>` que cobre o item sair do `IMPLEMENT`, *implementado* depois, *coberto* quando um passo do roteiro que prova o item tem ✅;
    - sai o `cobertura-<id>.md` e sai o cartão Cenários (`CN`);
  - **PR de outro dev** e **Levantamento:** ficam.
- Os testes do mod são atualizados.

### F. Base de conhecimento
- **Início:**
  - o orquestrador não roda mais `kb show` no chat;
  - roda `kb search` (lista curta) e põe só os **caminhos** das notas no `resumo`, e o explorador lê as notas;
  - novo `kb show --brief` (a nota sem os backlinks), para quando o orquestrador precisar ver uma.
- **Durante a demanda:** os aprendizados continuam, mas quem anota é quem descobre, no próprio relatório, sem custo extra para o orquestrador:
  - o explorador já tem a seção `## Base de conhecimento` (corrige `[[nota]]` / novo → `[[nota]]`, com `arquivo:linha`), e ela passa a valer também para o planejador, o revisor (armadilhas do sistema), o qa (massa, ambiente) e o codificador (bloqueio de ambiente resolvido);
  - o `aprendizados-<id>.md` fica só para o que nasce no chat: as suas decisões e as do negócio, os bloqueios que o orquestrador resolveu. Uma linha cada, quando acontece; não é mais uma tarefa de toda etapa.
- **Fim:** você continua rodando `/aidw:done`. Para ele não precisar reler todos os artefatos no Opus:
  - um comando novo `aidw.py kb collect <id>` junta numa lista só as seções `## Base de conhecimento` dos relatórios, o `aprendizados-<id>.md`, o resumo e as decisões do plano (`collect-<id>.md`);
  - o `/aidw:done` parte dessa lista, abre só as notas que vai tocar, escreve, valida e faz o commit do contexto com o seu OK;
  - a skill `done` (9 KB) é enxugada junto.
- **Medição:** a Fase 5 compara uma demanda piloto com e sem essas mudanças nas métricas do orquestrador (as do agente já corrigidas).

### G. Documentação
`docs/fluxo.md`, `agentes.md`, `painel.md`, `mods.md`, `configuracao.md`, `skills.md` e `README.md` reescritos para o fluxo novo. Este arquivo sai no fim.

## 5. Ordem de execução

Uma branch `feature/fluxo-enxuto`, em fases. Cada fase termina com `python aidw.py apply`, os testes (`tests/test_apply.py`, os testes do mod) e um commit (com o seu OK).

0. **Antes de tudo:** commitar à parte a correção pendente das métricas dos agentes em segundo plano (o diff local do mod), para os números novos serem comparáveis.
1. **Núcleo:** config, `routing.toml` e gerador (A), mais os agentes e skills (B).
2. **Orquestrador e workflows** (C, D) e o `CLAUDE.md` gerado ≤ 25 KB.
3. **Mod e painel** (E).
4. **Base de conhecimento** (F).
5. **Docs** (G) e uma **demanda piloto** de ponta a ponta no fluxo novo, comparando delegações, tempo e o custo do orquestrador com a m-144245 e a bug-146133.

Depois do `apply` de cada fase: um chat novo.

**Demandas abertas:** o alias dos steps antigos as mantém visíveis no painel. Uma demanda no meio do fluxo antigo segue pelo fluxo novo a partir da etapa equivalente.

**Ganho esperado** (a medir no piloto): uma feature comum cai para **~9 delegações**:
- explorador;
- planejador;
- documentador (board);
- codificador;
- revisor r1, codificador fix e revisor r2 em medium;
- qa plano e qa teste;
- documentador (PR).

O chat do orquestrador cai pela metade do prompt e por bem menos chamadas de registro.

## 6. Decisões (Felipe, 2026-10-23)

- **D1:** o explorador pode subir uma vez para Sonnet medium quando o resultado do Haiku não fizer sentido, com o motivo.
- **D2:** no levantamento, o explorador roda em Sonnet high.
- **D3:** a PR é aberta pela skill `ado-abrir-pr` (REST, como a `ado-anexar-arquivo`), com o seu OK.
- **D4:** a aba Critérios e Regras fica, simplificada: os `CA`/`RN` do card ficam no plano e o status é derivado, sem arquivo de cobertura.
- **D5:** commit, push e PR só no fim, na etapa PR, com um OK único. Até lá, a entrega fica no worktree sem commit; o guard do `AIDW-TESTE` continua barrando o commit com ajuste de teste.
- **D6:** os agentes e as skills continuam funcionando no Codex; só o que é exclusivo do Claude Code (mod, painel, trava) fica de fora.
- **D7:** os cards do board são as Tasks filhas do card, uma por entrega `E<n>` do plano.
- **E2E e navegador:** ficam, feitos pelo qa (Claude in Chrome ou Playwright, o que servir melhor ao caso); nunca pelo orquestrador.
- **Aprendizados e `/aidw:done`:** ficam, otimizados pela seção F.
