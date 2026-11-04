# Levantamento de melhorias do AiDW — 2026-11-04

Base: 24 demandas reais em `contexts/safeweb/demandas` (as de teste e simulação ficaram de fora), métricas dos agentes e
do orquestrador, as definições dos agentes e do orquestrador, e o código e o git log do `aidw-mods`. Os detalhes e as
evidências com `arquivo:linha` estão nos quatro relatórios desta pasta: `analise-metricas.md`, `analise-fluxo.md`,
`analise-agentes.md` e `analise-mods.md`.

**Limite da amostra:** só **uma** demanda de desenvolvimento rodou o v3 de ponta a ponta (m-109644). Os números de
tokens dos agentes só são confiáveis a partir de 2026-10-23 (commit b73d049), o mesmo dia do v3, então não dá para
separar o efeito do v3 do efeito da correção da medição.

## 1. O que os números dizem

| Fato | Valor |
|---|---|
| Participação do orquestrador no custo (depois da correção da medição) | **≥ 95 % dos tokens** (132,8M contra 7,7M dos agentes). O diagnóstico de outubro dizia 76 %, mas usava números inflados |
| Custo do orquestrador por demanda | pr-review US$ 3,59 em média · levantamento US$ 7,39 · desenvolvimento US$ 13,87 (m-109644, v3) contra US$ 43,69 (m-144245, pré-v3) |
| Delegações por demanda de desenvolvimento | 15 (m-109644, v3) contra 43 (m-144245) |
| Agentes depois da correção | revisao 33 % · busca 32 % · qa 15 % · dev 11 %; mediana de 98k tokens por delegação; piso de ~46k (o prompt) |
| Replanejamentos | 8 (us-131190) → 0 (m-109644) |
| Achados de revisão (≈190) | SUGESTAO ~107 (~60 % mantidas), IMPORTANTE ~56, CRITICO 4 |
| Bugs devolvidos pela QA | ~14; 3 sobre o Voltar do navegador (us-131190) |

**Conclusão:** o v3 acertou o alvo: menos delegações, nenhum replanejamento e um terço do custo. Agora o custo é
quase todo do chat do orquestrador. Cada chamada de ferramenta relê o contexto, e cada reabertura do cache escreve de
100k a 125k tokens. A próxima economia vem de: **(a)** um prompt menor, **(b)** menos voltas do orquestrador e
**(c)** sessões que não ficam abertas esperando.

## 2. Melhorias priorizadas

Impacto: **A** alto, **M** médio, **B** baixo. Esforço: **P** pequeno (< 1 h), **M** médio (meio dia), **G** grande.

### Custo e desempenho (o orquestrador)

| # | Melhoria | Evidência | Imp. | Esf. |
|---|---|---|---|---|
| C1 | **Enxugar o prompt do orquestrador**: `CLAUDE.md`/skill go tem 42 KB (meta 25 KB). Tirar dele o que é de agente (tabela *Systems* inteira, MCP por agente) e o que já está em referência | analise-agentes §1; plano-fluxo-enxuto | A | M |
| C2 | **Systems e Policies por papel nos agentes**: hoje são 13,9 KB + 10,7 KB repetidos nos 6 agentes, 70–80 % do prompt de busca, docs, plano e qa. Systems só para busca e plano; policies de banco e de ambiente só para quem as usa | analise-agentes §1 | A | M |
| C3 | **Enxugar `reviewer.md` (18 KB → ~9) e `coder.md` (13,6 KB → ~6)**: exemplos velhos do Hope, duplicação com a skill code-review | analise-agentes §1–2 | M | M |
| C4 | **Fechar a sessão nas esperas longas** (QA, VPN, UX, code review do time) e retomar com `/aidw:go`. A sessão de 4,5 dias de m-109644 escreveu 929k de cache; a de m-144245 custou US$ 37,76 em 58 turnos | analise-metricas §4 | A | P (regra + aviso na faixa) |
| C5 | **pr-review com menos chamadas do orquestrador**: um comando `aidw.py` que prepara worktree, diff, build e tarefa do revisor de uma vez. Estimativa: de US$ 3,6 para ~2,2 | analise-metricas §5 | M | M |
| C6 | **Testar o orquestrador em Sonnet** para pr-review e levantamento, como piloto medido (a premissa de ~40 % de ganho não está medida). Liga com o teste Opus High × Medium em andamento | analise-metricas §5; memória gasto-do-orquestrador | M | P |
| C7 | **Enxugar o texto que os mods injetam**: o aviso de leitura de código (~75 tokens a cada Read), as notas `[[x]]` (até 1,5k, repetidas a cada mensagem) e o `session.append` do agente em segundo plano, que acorda um turno inteiro | analise-mods §1 | M | P |

### Qualidade do resultado (fluxo e agentes)

| # | Melhoria | Evidência | Imp. | Esf. |
|---|---|---|---|---|
| Q1 | **Checklist das regras do repositório alvo** (CLAUDE.md do repo: "sem comentário/XML-doc", reuso de componente) no plano, no dev e no revisor. Foi o que mais escapou: o plano de m-109644 pediu XML-doc e o revisor elogiou. A PR 7691 teve 9 de 12 comentários do time viraram correção | analise-fluxo §1 | A | P |
| Q2 | **Validar a premissa do card antes de montar QA e ambiente** (bug: reproduzir ou provar a causa primeiro). bug-146134 gastou 9 delegações e não mudou código (o AVP já mandava o nome); us-131192 errou o protocolo de 9 ou 10 dígitos | analise-fluxo §2 | A | P |
| Q3 | **`git fetch` automático e tarefas apontando `origin/<base>`**: `desenvolvimento` local estava atrasado em 3 demandas | analise-fluxo §4 | M | P (no `worktree create`) |
| Q4 | **Regra de corte para SUGESTAO na triagem**: 60 % são mantidas "porque é barato", e em it-101662 um enum aceito foi apagado depois numa rodada de enxugamento (com 17 testes). Proposta: sugestão só entra se o revisor marcar `no escopo` e `≤ N linhas`; o resto vai a uma lista "depois" sem rodada | analise-fluxo §1 | M | P |
| Q5 | **Plano proporcional à mudança**: o de m-109644 tem 18 KB para ~15 linhas. Um teto por tamanho de entrega no planner | analise-fluxo §2 | M | P |
| Q6 | **Teto e divisão do QA**: duas delegações `qa high` tiveram 151 tool uses e 29 min de média; us-116332 teve um qa de 44M tokens. Dividir por bloco do roteiro, com um teto de tool uses | analise-metricas §4 | M | M |
| Q7 | **Busca: uma por tema e Sonnet para causa-raiz de bug**: m-114795 teve 6 buscas em 4 análises. O Haiku é arriscado em contrato entre sistemas | analise-metricas §5; analise-agentes §4 | M | P |
| Q8 | **Fechar o ciclo do conhecimento**: m-144245, m-109644, m-114795 e bug-143560 não têm nota em `conhecimento/demandas`. O AGR de teste 6278 foi redescoberto (488 s de QA). Um lembrete de `/aidw:done` quando a demanda vai para CODE_REVIEW/DONE, e `kb search` também pelo QA | analise-fluxo §5 | M | P |

### Coerência das regras (bugs de prompt)

| # | Correção | Onde |
|---|---|---|
| R1 | O revisor manda `git -C C:\ProjetosTFS\Guideline pull`, mas `pull` é ação travada | `contexts/safeweb/agents/reviewer.md:33` (confirmado) |
| R2 | "Max retries: 3 attempts" ainda injetado em todos os agentes (o limite de rodadas saiu no painel v4) | `aidw.py:1277` (confirmado) |
| R3 | O documentador usa `wit_add_child_work_items`, mas o MCP agora expõe `wit_work_item_write` | `contexts/safeweb/agents/documenter.md:16` (confirmado) |
| R4 | `HUMAN_APPROVAL` × `policy_requires_approval`: dois nomes para a mesma volta | `policies/ambientes-e-escrita.md:7` |
| R5 | Guideline "vale" × "vale o padrão do repositório" | guia do time:9 × `escopo-squad-emissao.md:14` |
| R6 | `plano-testes-<id>` obsoleto (hoje é `roteiro-testes-<id>`); "agente api" em explorer e qa; dois modelos de plano (to-spec × plano-execucao) | coder.md:217, explorer.md:10, qa.md:28 |
| R7 | `ambiente-local-qa` citado pelo orquestrador mas não registrado como referência; `claude-in-chrome` (principal do QA) fora da tabela de MCP | ctx orchestrator.md:29, context.toml:411 |
| R8 | Lacunas: revisão de várias entregas (nome do arquivo, quando ir a USER_REVIEW); Bug e Dívida sem CA; Figma lido antes do plano; `existing_work_found` e `final_review_approved` sem agente que os devolva | analise-agentes §3–6 |

### Mods

| # | Melhoria | Evidência | Imp. | Esf. |
|---|---|---|---|---|
| M1 | **Filtro de segredos idempotente**: uma máscara que passa duas vezes vira lixo. Cobrir também `isError` e o texto digitado | `mods/aidw-mods/.../secrets.ts:13`; `register.tsx:582` | A (segurança) | P |
| M2 | **Remover o hook `session.append` morto**: o plugin da organização (`cc-plugin-sec-default`) roda antes e o pula. Esse é o aviso que apareceu ao abrir esta sessão. Ou pedir à TI que o plugin repasse o evento | `register.tsx:570-572` | M | P |
| M3 | **`record` robusto**: o `JSON.parse` do stdout pode duplicar uma linha, e o `lastUsage` em memória perde o agente em segundo plano depois de uma recarga | analise-mods §2 | M | M |
| M4 | **Custo do orquestrador por etapa** (hoje é por sessão) e **US$ por delegação** (hoje grava "—"): sem isso C4 e C6 não se medem | analise-mods §3; analise-metricas §1 | A | M |
| M5 | **Travas novas no guard**: dev antes do PLAN_APPROVAL, o mesmo agente repetido na etapa sem motivo, a tarefa sem a linha de MCP e o `demand set` pulando etapas | analise-mods §3 | M | M |
| M6 | **Estabilizar a faixa e o views.tsx** (1650 linhas, 17 commits em 3 semanas, a faixa refeita ~8 vezes): separar em componentes e criar testes de renderização antes da próxima mudança | analise-mods §2 | M | G |
| M7 | Desempenho: o `git grep` dos marcadores de teste roda em todo refresh, e o `runtime.json` é lido sem cache | analise-mods §2 | B | P |

## 3. Ordem sugerida

1. **Rodada rápida (1 PR, ~meio dia):** R1–R7, M1, M2, Q3, Q1, Q2 e C4. São correções de regra, segurança e as duas
   maiores fontes de retrabalho, todas de esforço pequeno.
2. **Medir antes de cortar mais:** M4 (custo por etapa e US$ por delegação). Sem isso, C1, C2 e C6 não têm baseline.
3. **Enxugar prompts:** C1, C2, C3 e C7. Medir na próxima demanda de desenvolvimento.
4. **Piloto de modelo:** C6, com a medição do M4.
5. **Depois:** C5, Q4–Q8, M3, M5, M6 e M7.

Também: `docs/plano-fluxo-enxuto.md` está desatualizado (as fases 3–5 já entraram na PR #23). Atualizar o documento
com a medição do piloto m-109644.
