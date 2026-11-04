# Análise de custo e desempenho do AiDW (dados até 2026-11-04)

Fontes: `demandas/*/metricas.md` (356 linhas; 271 de demandas reais, 85 de teste/simulação ignoradas), `metricas-orquestrador.md` (22 sessões reais + 1 de teste) e `demand.json`. O histórico antigo (`.claude/Agents/Orquestrador/demandas`) não tem métricas.

## 0. Como ler os números (limites dos dados)

- **Os agentes só têm tokens, sem US$.** A coluna "Custo" do `metricas.md` está vazia (exceto 4 linhas antigas). O orquestrador tem US$ "equivalente API" (`metricas-orquestrador.md`). Qualquer US$ de agente abaixo é **estimativa minha** e está marcado.
- **Corte de confiança dos tokens de agente: 2026-10-23.** Commit `b73d049` (2026-10-23 10:36, "tokens do agente em segundo plano iguais aos da notificação") em `register.tsx`. Antes dele, 201 linhas têm mediana 144k e média 1,04M, com máximo de 44,3M numa linha só; 57 de 202 passam de 800k. Depois: 69 linhas, mediana 98k, média 111k, máximo 367k. Uso "antes" só como ordem de grandeza.
- **As métricas do orquestrador só começam em 2026-10-21** (commit `25fb0c9`). Não existe "antes do v3" com US$ do orquestrador para US/bugs grandes: só 6 sessões (21–22/10), US$ 47,91.
- O v3 e o corte do mod caem no mesmo dia (23/10). **Não dá para separar o efeito do v3 do efeito da correção de medição** nos agentes. O que se compara de verdade é "depois do corte", por tipo de workflow.
- O orquestrador roda sempre em `claude-opus-5-5`; os agentes, em Sonnet/Haiku. Na tabela de tokens totais, o orquestrador é cache lido + escrito + entrada + saída.
- Sessões são atribuídas à pasta da demanda em que começaram. A sessão `75c0e386` (m-144245) começou em 22/10 e atravessa o corte.

## 1. Custo por demanda

### 1.1 Depois do corte (>= 2026-10-23): orquestrador (US$ equiv.) × agentes (tokens)

| Demanda | Workflow | Turnos orq. | Orq. US$ | Orq. tokens | Agentes (n) | Tokens agentes | Orq./agentes (tokens) |
|---|---|---|---|---|---|---|---|
| us-143351 | levantamento | 18 | 6,81 | 13,9M | 4 | 0,54M | 26× |
| us-143353 | levantamento | 9 | 3,53 | 5,8M | 1 | 0,20M | 29× |
| m-114795 | levantamento (4 análises, 3 sessões) | 33 | 11,84 | 25,1M | 6 | 1,05M | 24× |
| m-109644 | levantamento + desenvolvimento (até PR) | 40 | 13,87 | 26,1M | 15 | 1,27M | 21× |
| m-144245 (sessões pós-22/10) | desenvolvimento (CR, bug devolvido) | 21 | 5,93 | 10,6M | 28* | 2,52M* | — |
| m-144245 (sessão `75c0e386`, 22–23/10) | desenvolvimento | 58 | 37,76 | 77,9M | (ver acima) | | |
| dt-144571 | pr-review | 10 | 4,39 | 10,5M | 3 | 0,42M | 25× |
| dt-146694 | pr-review | 5 | 2,43 | 5,2M | 1 | 0,17M | 30× |
| dt-146697 | pr-review | 3 | 1,72 | 3,1M | 1 | 0,15M | 21× |
| m-144502 | pr-review (3 rodadas) | 16 | 5,84 | 12,0M | 4 | 0,78M | 15× |
| us-135162 | pr-review (2 rodadas) | 8 (2 sessões) | 4,78 | 8,2M | 2 | 0,18M | 46× |
| us-141808 | pr-review (4 rodadas) | 7 | 3,71 | 8,0M | 2 | 0,18M | 44× |
| us-97336 | pr-review | 4 | 2,24 | 4,2M | 1 | 0,16M | 26× |
| dt-144187 | pr-review (sessão 22/10–26/10) | 15 | 6,35 | 13,3M | 1 pós-corte | 0,08M | — |

\* m-144245: as 28 linhas pós-23/10 cobrem as rodadas de ajuste, QA, CR e o bug 148183; as 15 anteriores (plano, implementação inicial) estão antes do corte.

Totais pós-corte (sessões iniciadas >= 23/10, 16 sessões): orquestrador **US$ 67,09**, 174 turnos, **132,8M tokens** (cache lido 133,8M tokens no total das 22 sessões; cache escrito 4,0M; saída 0,53M). Agentes (69 delegações em demandas reais): **7,69M tokens**. Em tokens, o orquestrador é **~95%** do total (132,8 / 140,5M).

### 1.2 Média por workflow (pós-corte; orquestrador em US$, agentes em tokens)

| Workflow | Demandas | Orq. US$ médio | Delegações médias | Tokens agentes médios | Duração de agentes (soma, min) |
|---|---|---|---|---|---|
| pr-review | 7 (sem dt-144187) | **3,59** (1,72–5,84) | 1,9 (1–4) | 0,28M | 5–39 |
| pr-review incluindo dt-144187 | 8 | 3,93 | — | — | — |
| levantamento | 3 | **7,39** (3,53–11,84) | 3,7 (1–6) | 0,60M | 10–48 |
| desenvolvimento (m-109644, até PR; PR aberta sem teste em QA) | 1 | 13,87 | 15 | 1,27M | 41 |
| desenvolvimento (m-144245, vida longa: 10 dias, 4 CRs/ajustes) | 1 | 43,69 em 3 sessões | 43 (28 pós-corte) | 12,55M no total (antes do corte inflado) | 224 |

Só há **1 demanda de desenvolvimento ponta a ponta** com dados confiáveis no v3 (m-109644), e ela ainda não passou pelo teste manual nem tem QA real (VPN). A amostra não permite generalizar.

### 1.3 Antes do corte (tokens de agentes inflados; ordem de grandeza)

| Demanda | Delegações | Tokens (inflados) | Tool uses | Duração soma |
|---|---|---|---|---|
| us-116332 (US 116332+135164, 13–16/10) | 70 | **160,1M** | 1.838 | 564 min |
| m-144245 (parte de 20–22/10) | 15 | ~10M | ~800 | ~150 min |
| us-131190 (28/9–15/10) | 46 | 9,2M | 777 | 196 min |
| dt-144187 (22/10, 4 linhas) | 4 | 9,4M | 116 | 20 min |
| bug-146134 | 9 | 6,7M | 159 | 21 min |
| it-101662 | 34 | 3,9M | 944 | 253 min |
| bug-146133 | 12 | 3,1M | 212 | 31 min |

Orquestrador pré-v3 (só 21–22/10): bug-146133 US$ 1,33 (3 turnos), bug-146134 US$ 2,47 (3 sessões), dt-144187 US$ 6,35, m-144245 `75c0e386` US$ 37,76 (58 turnos, 77,9M tokens).

## 2. Participação de cada agente e do orquestrador

### 2.1 Custo (pós-corte)

- Orquestrador: US$ 67,09 equiv. nas 16 sessões iniciadas pós-corte (US$ 112,5 somando todas as demandas reais desde 21/10, sem teste-mods).
- Agentes: 7,69M tokens. **Estimativa (não medida):** o orquestrador pagou em média ~US$ 0,50/M tokens (67,09 / 132,8M, mistura de cache lido, cache escrito e saída). Se os agentes custassem o mesmo por token, valeriam ~US$ 3,8; com Sonnet/Haiku mais baratos, ~US$ 1–3. Mesmo no pior caso (tudo a US$ 3/M, sem cache) seriam ~US$ 23. **Orquestrador entre ~74% e ~98% do custo; o mais provável fica perto do limite superior (≥ 95%).** O diagnóstico de 76% (medido com tokens de agentes inflados) vira ≥ 95% com os números corrigidos; o orquestrador domina ainda mais.
- Composição do custo do orquestrador, **inferida** ajustando os preços ao US$ de m-109644 (cache lido ≈ US$ 0,3/M, escrito ≈ US$ 6/M, saída ≈ US$ 15/M): cache lido ~55%, **cache escrito ~33%**, saída ~11%. O cache escrito (recriar o contexto depois de uma espera de mais de 5 min ou depois do `compact`) pesa um terço.

### 2.2 Tokens por agente (pós-corte, 69 delegações; nomes antigos fundidos: explorador=busca, revisor=revisao, codificador=dev, planejador=plano, documentador=docs)

| Agente | Delegações | Tokens | % dos tokens de agentes | Tokens/del. | Tool uses/del. | Duração/del. |
|---|---|---|---|---|---|---|
| revisao | 23 | 2,57M | 33% | 112k | 19,5 | 213 s |
| busca | 16 | 2,45M | 32% | 153k | 46,8 | 418 s |
| qa | 8 | 1,12M | 15% | 140k | 63,4 | 694 s |
| dev | 14 | 0,83M | 11% | 59k | 11,6 | 152 s |
| api (massa/escrita) | 3 | 0,24M | 3% | 81k | 28,7 | 297 s |
| docs | 4 | 0,29M | 4% | 72k | 10,5 | 43 s |
| plano | 1 | 0,11M | 1% | 109k | 30 | 212 s |
| bugs (agente antigo) | 1 | 0,15M | 2% | 153k | 2 | 61 s |

### 2.3 Tokens por agente × modelo × effort (pós-corte)

| Agente / modelo / effort | n | Tokens médio | Mediana | Tool uses | Duração média |
|---|---|---|---|---|---|
| busca haiku | 11 | 146k | 143k | 42,5 | 373 s |
| busca sonnet high (levantamento) | 5 | 169k | 174k | 56,2 | 517 s |
| plano sonnet high | 1 | 109k | — | 30 | 212 s |
| dev sonnet high | 4 | 65k | 61k | 13,2 | 132 s |
| dev sonnet medium | 8 | 59k | 50k | 12,0 | 174 s |
| dev sonnet low | 2 | 51k | — | 6,5 | 77 s |
| revisao sonnet high | 11 | 157k | 148k | 33,5 | 378 s |
| revisao sonnet medium | 9 | 76k | 75k | 9,9 | 84 s |
| revisao sonnet low | 3 | 51k | 51k | 5,0 | 14 s |
| qa sonnet medium | 6 | 103k | 102k | 34,0 | 351 s |
| qa sonnet high | 2 | 250k | — | 151,5 | 1.721 s |
| docs haiku | 3–4 | 72k | 72k | 10 | 43 s |
| api sonnet high/low | 3 | 99k / 46k | — | 37 / 12 | 356 / 180 s |

**Piso por delegação: ~46k tokens** (mínimo medido 45.853; mediana 55k nas 30 delegações com ≤13 tool uses). Uma delegação com 4–6 tool uses custa quase o mesmo em tokens que uma com 13 (carga fixa de prompt + definição das ferramentas). Essas 30 delegações "pequenas" (ajuste-teste, fix-rN, re-revisão low) somam 1,95M tokens, 25% dos tokens de agentes.

## 3. Rodadas, repetições e exceções de effort

Contagem pelo `history` do `demand.json` (todas as demandas, incluindo pré-v3) e pelas linhas pós-corte.

| Demanda | REVIEW | CODER_FIX | PLAN_FIX | TEST | Observação |
|---|---|---|---|---|---|
| us-131190 (pré-v3) | 11 | 7 | **8** | 4 | 64 etapas no histórico; 46 delegações |
| it-101662 | 5 | 4 | 2 | 2 | 32 etapas |
| us-116332 | 1 | 2 | 1 | 2 | 70 delegações pelas linhas (agentes bugs/segurança em paralelo) |
| m-144245 | **7** | **8** | 1 | 3 | 57 etapas; 10 `dev` e 7–10 `revisao` pós-corte; 2 rodadas de QA-high |
| m-109644 (v3) | 2 | 1 | 0 | 1 | 1 plano, 0 replanejamento |
| pr-review: us-141808 | 4 rodadas | — | — | — | bug-148293 como `loop` |
| pr-review: m-144502 | 3 rodadas | — | — | — | r2 custou mais que r1 (336k × 228k) |
| pr-review: dt-144571 | 2 | — | — | — | |
| pr-review: us-135162 | 2 | — | — | — | |
| demais pr-review | 1 | — | — | — | |

Replanejamentos: no v3 há **1 plano e 0 PLAN_FIX** (m-109644); antes eram 8 (us-131190), 2 (it-101662), 1 (us-116332, m-144245). Explorações: m-114795 usou **6 `busca`** (levantamento) e 4 análises sucessivas (5 no histórico, "4ª análise D19-D23"); us-143351 usou 4.

Delegações repetidas / a refazer (pós-corte):
- m-144245, QA: `teste-r1` rodou 2 vezes em `qa high` (1ª `missing_state`, 134k, 37 tool uses; 2ª 367k, **266 tool uses, 2.578 s**). É a exceção "refazer uma vez" da tabela, mas a 2ª custou 2,7× a 1ª.
- m-144245: 3 `api` seguidos para o mesmo e-mail de pendência (proposta, execução, rollback `environment_blocked`).
- m-114795: `explorador-banco` + "complemento Q1" (2 chamadas da mesma pergunta).
- Estados que não são sucesso: `missing_state` 1 (qa), `environment_blocked` 1, `policy_requires_approval` 1, `review_changes_requested` 1 de 23 revisões (**22 das 23 revisões aprovaram ou terminaram**; só 1 gerou correção na janela pós-corte). Antes do corte, `missing_state` era a regra (linhas de 20/10 do bug-146133/146134), reflexo do formato antigo.

Exceções de effort usadas pós-corte (a tabela autoriza `revisao-medium/low`, `dev-medium`, `busca-sonnet-high` só no levantamento, `qa-high` refazer):
- `revisao medium` ×9, `revisao low` ×3, `dev medium` ×8, `dev low` ×2 (10/23, antes da tabela v3; `dev-low` não existe na tabela atual), `busca-sonnet-high` ×5 (4 de levantamento + `fluxos-email-otp` do us-143351, também levantamento, ok), `qa-high` ×2 (mesma tarefa), `plano-medium` ×0, `busca-sonnet-medium` ×0.
- Revisão a `high` ×11 (todas de pr-review ou primeira revisão); a `medium` ×9: 8 delas são r2/r3 de pr-review, ou seja, a regra "re-revisão desce um nível" está sendo seguida.

## 4. Outliers e causa provável

| Item | Número | Causa provável (arquivos da pasta) |
|---|---|---|
| us-116332, `qa high` `145145-test-r1` (16/10) | 44,3M tokens, 153 tool uses, 8.884 s (2h28), estado `policy_requires_approval` | Teste de prova de vida com vários passos de E2E/browser e escritas; terminou pedindo aprovação. Em parte inflado (antes do corte), mas as 2h28 e 153 tool uses são reais. Sem orçamento de QA nem de passos. |
| us-116332 inteira | 160M tokens, 70 delegações, 564 min | 4 agentes de auditoria em paralelo (`bugs` 9, `segurança` 3, ~40M + 2,6M), 25 `dev`, 12 revisões, 6 planos, 8 QAs, duas US juntas (116332+135164), 2 revisões de plano (`PLAN_REVIEW`+`PLAN_FIX`). Fluxo v1/v2 com todos os revisores em paralelo. |
| m-144245, sessão do orquestrador `75c0e386` | US$ 37,76, 58 turnos, 77,9M tokens, 1.273k cache lido/turno | Demanda com 2 repositórios, planos e ajustes repetidos em 1 dia (CODER_FIX 8×, REVIEW 7×), QA com prints, a sessão atravessou a compactação de 22/10 e a mudança de fluxo. Cache escrito 2,4M tokens (US$ ~14 só nisso). Depois das mudanças (sessões `ea5d78cd`, `f1603b9e`) o custo/turno caiu para US$ 0,27–0,29. |
| m-144245, `qa high` teste-r1 | 266 tool uses, 2.578 s, 367k | Roteiro grande (CN1–CN15 do e-mail de pendência + modal) numa só delegação, com `manual_test_required`. Mistura passos automáticos e manuais. |
| m-109644, sessão do orquestrador | US$ 13,87, 40 turnos em 4,5 dias, cache escrito 929k tokens | Sessão aberta de 30/10 a 04/11 com esperas (VPN/QA, PR sem teste). Cada volta de espera recria o contexto (cache escrito); 40 turnos cabem em 15 delegações + checagens. |
| m-114795 (levantamento) | US$ 11,84, 33 turnos, 6 `busca` | 4 análises do mesmo card (D19–D23 novas, Liveness secundário); cada nova pergunta do Felipe reabriu a exploração. 3 sessões. |
| m-144502 `prs-r2` | 336k tokens, 59 tool uses, 1.007 s | Re-revisão de 2 PRs dependentes de outras 2 PRs abertas (8138/8139); a r2 relê o diff inteiro. |
| dt-144187 `pr8243` (22/10) | 6,0M (antes do corte), 49 tool uses | Inflado; o r2 pós-corte custou 75k. |
| us-135162 / us-141808 / us-97336 | orq. 44–46× os agentes | Demandas de pr-review com 1–2 delegações onde o orquestrador gasta US$ 2–5 contra poucos centavos de agente (UNDERSTAND + worktree + triagem + FINAL_REVIEW + done). |

## 5. Onde está o desperdício

1. **O orquestrador é ~95% do custo (tokens) e o custo é por chamada, não por trabalho.** Ele lê 460k–1,3M de cache por turno (≈ 3–5 chamadas a ~250k). O custo por demanda de pr-review (US$ 1,7–5,8) é quase todo do chat, não dos agentes (US$ centavos).
2. **Cache escrito ≈ 1/3 do custo do orquestrador (inferido).** Sessões longas com espera (m-109644: 4,5 dias, m-114795: 3 sessões, us-135162: 2 sessões) pagam o contexto de novo. O mínimo de cache escrito por sessão é ~100–125k tokens (dt-146697: 3 turnos, 102,8k; bug-146133: 123,8k): o prompt de base já é grande.
3. **Piso fixo de ~46k tokens por delegação**, e 30 de 69 delegações (25% dos tokens de agentes) são pequenas: ajustes, re-revisões, `docs`, 1 `bugs` de 2 tool uses (152k tokens para auditar 2 chamadas: o agente `bugs` já foi absorvido pela `revisao`).
4. **Exploração com muitos agentes para a mesma pergunta** (m-114795: 6 `busca`; us-143351: 4; us-143351 `levantamento` + 2 haiku + 1 sonnet high), com 42–56 tool uses cada.
5. **QA com orçamento aberto**: 2 delegações `qa high` pós-corte com 151 tool uses em média e 1.721 s (28 min), 18% dos tokens de agentes pós-corte em 2 linhas de 8.
6. **Revisões repetidas em pr-review**: 4 rodadas (us-141808), 3 (m-144502); a r2 pode custar mais que a r1 porque relê o diff inteiro.
7. **Esperas e trabalhos longos que atravessam a compactação**: custo por turno de US$ 0,65 na maior sessão contra US$ 0,27–0,40 nas sessões seguintes.

## 6. Hipóteses de melhoria (ganhos estimados, com premissas)

| # | Hipótese | Evidência | Ganho estimado |
|---|---|---|---|
| 1 | **Rodar o orquestrador em Sonnet (ou Opus medium) nas demandas de pr-review e levantamento.** Só o chat custa; os agentes já são Sonnet/Haiku. O teste Opus High × Medium já está no plano da memória. | Orq. = ~95% dos tokens; US$ 67 em 16 sessões; pr-review: US$ 3,59 médio, 1,9 delegações, nada de código | **Premissa não medida: se o preço de Sonnet for ~0,6× o do Opus, -40% do custo total (≈ US$ 27 das 16 sessões). Medir em 3–4 demandas de pr-review antes de adotar.** |
| 2 | **Reduzir o prompt base do orquestrador (CLAUDE.md ~64 KB + contexto + lista de ferramentas MCP).** Cada reabertura de cache escreve ≥100–125k tokens. | cache escrito mínimo 102,8k–123,8k por sessão de 1–3 turnos; cache escrito ≈ 33% do custo (inferido) | Cortar 30% do prompt reduz ~10% do custo total (cache escrito + cache lido em cada chamada). Premissa: o prompt é metade do contexto inicial. |
| 3 | **Fechar a sessão em vez de esperar** (VPN, QA, revisão do Felipe) e retomar com `resumo`+`demand.json`; ou compactar antes da espera. | m-109644: 4,5 dias, 40 turnos, US$ 13,87, cache escrito 929k; m-114795: 3 sessões de US$ 2,8/5,5/3,6 | Evita 1–2 recargas de contexto por espera, ~US$ 0,6–1,2 cada (125–200k × US$ 6/M): ~US$ 3–5 por demanda longa. |
| 4 | **pr-review "leve": 1 chamada do orquestrador para entender, 1 para delegar, 1 para triagem**, sem `aprendizados`, sem `demand set` por etapa, sem `kb` no chat. | pr-review é metade das demandas (7 de 14); orq. 21–46× os agentes; US$ 1,72 com 3 turnos (dt-146697) vs US$ 5,84 com 16 turnos (m-144502) | Levar a média de US$ 3,59 para ~US$ 2,2 (a de dt-146697, o mais enxuto) = **-38% por pr-review**. |
| 5 | **Teto de tool uses/tempo e divisão do QA**: automáticos num QA medium separado dos manuais; `qa-high` só uma vez e com teto. | `qa high` pós-corte: 2 linhas, 500k tokens, 151 tool uses médios, 1.721 s; 1ª rodada 134k em 37 usos terminou em `missing_state`; us-116332 `qa high` com 44M/2h28 | ~0,5M tokens e ~50 min por demanda com QA grande; menor risco de `missing_state` e de refazer. |
| 6 | **Uma `busca` por tema, com todas as perguntas numeradas na mesma tarefa**; levantamento com `busca-sonnet-high` só para o mapa, haiku para perguntas pontuais (já é a regra). | m-114795: 6 `busca` (1,05M), 2 delas sobre o mesmo banco; us-143351: 4 | ~0,3–0,5M tokens de agente e ~3 chamadas do orquestrador (~US$ 1–1,5) por levantamento grande. |
| 7 | **Juntar a correção pequena e a re-revisão numa única delegação quando for trivial** (ajuste de texto, 1 linha) ou aplicar o ajuste direto pelo orquestrador. | 30 delegações ≤13 tool uses somam 1,95M tokens (25% dos agentes), todas com piso de ~46k; ex.: m-144245 `fix-r1`+`codigo-r2`+`ajuste-teste-1` em sequência | Cada par fix+re-revisão evitado poupa ~100k tokens de agente e 2–3 chamadas do orquestrador (~US$ 0,5–1,0). |
| 8 | **Em pr-review, r2+ olha só o diff dos commits novos** e recebe os IDs dos achados da r1; r3+ em `medium` por padrão (já acontece de fato). | m-144502: r1 228k, r2 336k, r3 72k; us-141808 r3/r4 104k/77k; dt-144571 r1 225k → r2 73k | Evita casos tipo r2=336k: ~150k tokens por rodada; não pesa em US$ (agentes ~4%), só em tempo (1.007 s). |
| 9 | **Padronizar o `state` e o JSON de retorno** para o fim do `missing_state` (e retorno curto). | pré-corte, `missing_state` era a maioria das linhas; pós-corte, 1 de 69 (qa) | Evita nova delegação "só para o JSON" (~50k tokens + 1 chamada do orquestrador). Ganho pequeno, risco baixo. |
| 10 | **Instrumentar o que falta**: US$ por agente no `metricas.md`, separar tokens de entrada/saída/cache, gravar o `demand.json` com `workflow` e `loops`; marcar sessão que atravessa várias demandas. | coluna Custo vazia; `workflow`/`loops` ausentes; sessões atribuídas à pasta onde começam | Necessário para fechar as contas (hoje o US$ de agentes é estimativa) e para medir o ganho das hipóteses 1–4. |

## 7. Resumo das conclusões

- Depois de 23/10 (dados confiáveis de agentes): **orquestrador ≈ 95% dos tokens**, 16 sessões a US$ 67 equiv.; **agentes 7,7M tokens em 69 delegações** (média 111k, piso ~46k).
- US$ por demanda: pr-review ~US$ 3,6 (1,7–5,8), levantamento ~US$ 7,4 (3,5–11,8), desenvolvimento US$ 13,9 (até a PR) a US$ 43,7 (m-144245, 3 sessões, 10 dias).
- Antes do corte os tokens de agentes estavam inflados: mediana 144k, média 1,04M, 57 de 202 linhas > 800k, us-116332 sozinha com 160M. O v3 e o corte entraram no mesmo dia, então a queda dos agentes não se atribui ao v3.
- Rodadas: replanejamentos caíram de 8 (us-131190) para 0 (m-109644); pr-review tem até 4 rodadas; 22 de 23 revisões pós-corte terminaram aprovadas ou concluídas.
