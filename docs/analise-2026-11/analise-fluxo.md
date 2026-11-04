# Análise da qualidade do fluxo AiDW (demandas reais, 2026-09 a 2026-11-04)

Base: `C:/AiDW/contexts/safeweb/demandas/` (24 demandas reais, 7 de desenvolvimento, o resto revisão de PR e levantamento).
Ressalvas: (1) quase tudo anterior ao fluxo v3 (2026-10-23); só **m-109644** é um piloto v3 de desenvolvimento completo
(bug-146133 e m-144245 cruzam a data). (2) Contagens por parser de cabeçalhos/tabelas (`review-*`, `bugs-*`, `seguranca-*`,
`triagem-*`): são aproximadas (+/- 10%). Caminhos abaixo são relativos à pasta das demandas.

## Volume (delegações por demanda, de `*/metricas.md`)

| Demanda | Tipo | Delegações | Observação |
|---|---|---|---|
| bug-146133 | Bug (código) | 12 | 1 plano, 0 achados na revisão |
| bug-146134 | Bug (sem mudança de código) | 9 | premissa do card falsa |
| it-101662 | PoC | 34 | tentativa 1 descartada; 2,16M tokens (`it-101662/revisao-final-101662.md:74`) |
| m-144245 | Melhoria 2 repos | 43 | orquestrador US$ 43,7 em 3 sessões (`m-144245/metricas-orquestrador.md`) |
| us-116332 | US + ~10 bugs | 70 | codificador 25, bugs 9, revisor 12 |
| us-131190 | US + 3 bugs da QA | 46 | 11 versões do plano, 17 diffs, 10 rodadas de revisão (`us-131190/demand.json`: 64 mudanças de etapa) |
| m-109644 (v3) | Melhoria 2 arquivos | 15 | orquestrador US$ 13,87, 40 turnos; alvo do plano enxuto era ~9 |

## 1. Revisão

**Achados por rodada** (headings dos relatórios, sem simulações): ~190 achados ao todo: SUGESTAO ~107, IMPORTANTE ~56,
ELOGIO ~22, CRITICO 4 (+13 do `review-otimizacao`). Quase todo CRITICO/IMPORTANTE vem na r1; depois cai: us-131190 r1..r10 =
1,2,4,4,0,2,0,2,0,1 (`us-131190/review-131190-r*.md`); us-131192 r1..r4 = 5,3,5,1; dt-144187 r1 = 9 (revisor) + 4 (bugs) + 3
(segurança) = 16, r2 = 1. No piloto v3 (m-109644) e bug-146133: **zero achados** (só elogios).

**Mantido × descartado** (tabelas de triagem do código, sem plano; aproximado): IMPORTANTE ~21 mantidos × 2 descartados;
SUGESTAO ~43 × 28; dúvidas ~20 × 8; CRITICO 3 (2 rebaixados na triagem: `us-131192/triagem-131192-r1.md` R1-01 e R1-02; 1
mantido, `us-131190/triagem-131190-r4.md`). Ou seja, **o usuário/orquestrador mantém ~60% das sugestões**, a maioria "barata, em
escopo". Na revisão de PR de terceiro a taxa de publicação é baixa: dt-144187 r1 publicou 5 de 15 comentários
(`dt-144187/triagem-dt-144187-r1.md`, "Publicado"); r2 0 de 1.

**Motivos recorrentes de descarte:** sugestão sem cenário de falha (bug-146134 R1-01..03, "decisão do Felipe: não implementar sem
falha real"); fora de escopo/da PR (dt-144187 C1, C7, C9, C10, C12–C15 "descartados"); padrão do repositório (dt-144187 R1-D1,
us-131192 R3-01 "premissa falsa: o repo usa os dois estilos"); premissa do revisor errada porque o `desenvolvimento` **local** estava
atrás do `origin` (us-141808 B1-D3 refutado, `us-141808/triagem-us-141808-r1.md`); decisão já tomada no plano (m-144245 R1-02/03).

**Sugestões "baratas" que depois viraram dívida:** it-101662 aceitou R1-02 (enum no lugar de `bool` no saneador) e a PoC
cresceu para 23 arquivos/+1115 linhas; uma rodada inteira de "enxugamento" (`it-101662/review-otimizacao-101662-r1.md`:
5 REDUZIR) mandou apagar o enum, a classe `DadosEquipamentoCliente` e 17 testes (critério do Felipe de 05/10). Três rodadas de revisão
do plano (9+5+4 achados) e duas passadas de segurança empurraram o escopo para cima antes.

**Padrões que o revisor deixou passar e o Felipe ou o time pegaram depois (mesmo erro, 4 demandas):**
- Regra do CLAUDE.md do repositório "sem comentário explicativo / sem XML-doc": m-109644 (o revisor elogiou o `/// <summary>`
  "como o plano pediu", `m-109644/review-m-109644-E1-r1.md`; o Felipe mandou remover e desfazer o `ARCHITECTURE.md`,
  `m-109644/tarefa-codificador-ajuste-usuario.md`); m-144245 (Felipe pediu remover comentários e reaproveitar ícone/estilos,
  `m-144245/resumo-ajuste-reuso-portal.md`; o time reabriu o mesmo ponto no code review, thread 24140); it-101662 R1-01.
- Code review do time depois de 10 rodadas internas: PR 7691 (us-131190) teve 12 comentários, 9 viraram correção, incluindo erro
  engolido, flag sem efeito e `await` ausente (`us-131190/triagem-pr-7691.md`); m-144245: 24136 é bug real (nome:false sem
  observação lançava exceção) que revisão + bugs não viram (`m-144245/resumo-ajuste-code-review.md`); condição duplicada 3x (24142).
- Bugs devolvidos pela QA (dev, todos pós-entrega): us-131190 144749, 144798, 144844 (tema único: Voltar do navegador, risco que o
  plano já apontava em P1-01 e "aceitou testar na QA"); us-131192 143341, 143344, 143560; us-116332 144183, 144712, 144727, 144805,
  144808, 145145; m-144245 148183 (texto trocado pela PO). it-101662 147704 não era código: deploy de QA com branch velha.

## 2. Plano

- **Ajustes (fluxo antigo):** us-131190 11 versões e 5 rodadas de revisão do plano (`us-131190/plano-131190-v1..v11.md`), motivo
  principal: bugs devolvidos da QA e hipóteses sobre histórico do navegador; it-101662 v1→v4.1 (3 rodadas, 18 achados); m-144245 v1→v2
  (r1: 1 CRITICO + 3 IMPORTANTE + 6 SUG, `m-144245/triagem-plano-m-144245-r1.md`); us-116332 145145 2 rodadas.
- **v3:** m-109644 e bug-146133 tiveram **um plano só, aprovado sem PLAN_FIX**; a revisão do plano por agente saiu. Custo: o plano
  de m-109644 tem 18 KB para uma mudança de ~15 linhas, e m-144245 tem plano de 39 KB + plano de testes de 41 KB (19 cenários).
- **Premissas erradas que só apareceram depois:**
  - bug-146134: "o AVP não manda o nome" era falso (já mandava desde a PR 6732); descoberto no `review-r1`, depois do plano de testes e de
    ajustes de ambiente (`bug-146134/aprendizados-bug-146134.md`, `demand.json` TEST_PLAN antes de REVIEW).
  - us-131192: o plano/triagem r1 manteve "protocolo pode ter 9 dígitos" (`us-131192/triagem-131192-r1.md` R1-02); a QA devolveu o bug 143560 exigindo
    10 (`bug-143560/resumo-143560.md`).
  - m-144245: `.Result` embrulhando `AggregateException` só apareceu na revisão do plano (P1-01, CRITICO); "serviço ConsultasCnh não está
    em nenhum repositório local" foi gravado e depois corrigido (`m-144245/aprendizados-m-144245.md`); o `desenvolvimento` local do
    Hope/Portal estava atrás (+193 linhas) e as linhas da exploração mudaram.
  - m-109644: o plano mandava XML-doc e editar `ARCHITECTURE.md`, contra o CLAUDE.md do Hope (ver acima).
  - us-131190: Voltar do navegador previsto no plano, mas o risco foi "aceito e testado na QA" e voltou como 3 bugs.

## 3. Testes

- **Falhas reais em TEST:** praticamente nenhuma. m-144245 TEST r1: "nenhum critério reprovado; 3 em doubt" (`m-144245/teste-m-144245-r1.md`); m-109644 e bug-146133 sem
  falha. Os defeitos foram achados antes (revisão) ou depois (QA/time), não no TEST.
- **O que travou:**
  - Massa/aprovação: m-144245 CN8a, CN8b, CN19 "doubt" por falta de massa (histórico de CNH com limite/só validade), QA anterior "parado" e refeito
    (`teste-m-144245-r1.md` §0), `start_videoconference` recusado (status 8) obrigando a abrir a sala por stub no console; m-109644 passos
    P01–P07 bloqueados "por falta de OK do B4" no 1º TEST (`m-109644/relatorio-testes-m-109644.md`), roteiro com B1–B4 sem OK ao abrir a PR.
  - Ambiente: VPN fora → PRs abertas em 30/10 e teste só em 03/11 (`m-109644/aprendizados-m-109644.md`); o protocolo injetado nasce em status 1, não 3.
  - Ajustes AIDW-TESTE: m-109644 A1 (1 linha, 1 delegação de 26 s); bug-146133 6 ajustes em 2 repos
    (`bug-146133/ambiente-teste-bug-146133.md`); bug-146134 3 ajustes (`ajuste-teste-1..3`) e 2 massas por API para provar um negativo; it-101662 ~10
    delegações só de ambiente E2E (exploração ×2, api ×5, scripts de protocolo/titular, hardcode e2e).
- **Manual × automático:** m-109644 roteiro 11 passos, 7 manuais (P03, P04, P07, P08/P09, P11…) e P10 só era build; m-144245 19 cenários
  automáticos via Claude in Chrome + M1 manual e e-mail confirmado por print do Felipe; bug-146134: só API local + harness.

## 4. Retrabalho e atrito

- **Refeito:** it-101662 tentativa 1 inteira (stash, `tentativa-1/`, 2 PoCs); m-144245 QA retomado; us-131190 plano 11 versões; mods:
  token de agente inflado 10–30x (m-144245 revisor 7,1M vs 242k) corrigido depois.
- **Bloqueios de ambiente:** VPN (m-109644); hook do AiDW bloqueou Write do explorador na pasta da demanda (`us-131190/aprendizados-us-131190.md`);
  MCP `ado` não conectou (`us-131190/resumo-bug-144798.md`); `aidw.py record --agent api` "agente desconhecido" (m-144245); `desenvolvimento`
  local atrasado (3 demandas); deploy de QA com branch velha (bug 147704, `it-101662/bug-147704/resumo.md`) e pipeline de DEV parado desde julho (`us-131192/situacao-entrega-2026-10-20.md`).
- **Perguntas evitáveis:** D4 do m-109644 (GTM/Hotjar, "seguir sem depender", virou só pendência); 14 decisões D1–D14 no m-144245 (várias
  só se fecharam com PO/TL depois: D11, 24137, 24141); bug-148016 aberto por engano (`bug-148016/demand.json`); na revisão de PR o
  usuário reescreveu os textos dos comentários (dt-144187) — rascunhos do agente vão para o lixo.
- **Artefatos pouco usados:** m-109644: levantamento + `pontos` + 2 explorações (31 KB) para uma mudança de ~15 linhas; `plano-testes`
  41 KB no m-144245 enquanto o executado foi o roteiro de 8 KB; `checklist-revisao.md`/`cobertura-*.md` em 14 pastas (somem no v3);
  17 diffs numerados no us-131190, 3 variantes de diff por rodada em PR review (`-r2`, `-so-144502`, `-ultimo-commit`), 14 `US-116332-*.md` do
  orquestrador antigo.

## 5. Conhecimento

- **Funciona:** 16 `resumo-*.md` já têm `## Conhecimento` com caminhos; KB com 135 notas; `kb collect` gera `collect-*.md` nos DONE;
  a nota do Figma/cota (m-144245) foi reaproveitada.
- **Não fecha o ciclo:** sem nota `conhecimento/demandas/<id>.md`: m-144245, m-109644, m-114795, bug-143560. O que a demanda aprendeu fica só em
  `aprendizados-*.md`.
- **Redescobertas:**
  - AGR de teste de DEV 6278 / local 3 usado em m-144245 (CN15, 23/10) e **re-levantado** pelo QA no m-109644 (488 s, 143k tokens,
    `m-109644/relatorio-testes-m-109644.md`); `grep 6278` na KB = vazio. O mesmo vale para "`Add/3` exige token cru no Authorization" e
    "API.Client local lê `C:\out\ConfigManagerArgs.json`" (só no relatório).
  - `desenvolvimento` local atrás do `origin` aparece em 3 demandas (us-141808 20/10, m-144245 22/10, tarefa do m-109644) e não está na KB.
  - ConsultasCnh "não localizado" gravado e corrigido no mesmo `aprendizados` (m-144245).
  - Tema OpenVidu: dt-144571 corrige nota de dt-144187 (`collect-dt-144571.md`), sinal de que `/aidw:done` roda por demanda, não por feature.

## 6. Pendências do `docs/plano-fluxo-enxuto.md`

O arquivo ainda diz "fases 3 a 5 a seguir", mas estão feitas: mod/painel (`5962b72`), KB enxuta `kb collect`/`kb show --brief` (`61ed68f`), docs (`7e56ae1`),
tudo na PR #23, e o painel evoluiu até a #35. Pendente de fato:
- **Metas de tamanho não atingidas:** `CLAUDE.md` gerado 42 KB (meta ≤25 KB); `reviewer.md` 18,4 KB e `coder.md` 13,6 KB (meta ≤8 KB cada);
  `reviewer.md:148,344` ainda tem checklist e log do Hope de fev/2026.
- **Piloto medido de desenvolvimento:** m-109644 serve, mas ninguém registrou a comparação: 15 delegações (meta ~9), US$ 13,87/40 turnos contra
  m-144245 US$ 43,7 e 43 delegações; bug-146133 12 delegações/US$ 1,33.
- Dry-run Codex (D6): não verificável pelas pastas de demanda.
- O próprio arquivo diz "Este arquivo sai no fim": arquivar.

## 7. Melhorias propostas (ordem por impacto/esforço)

| # | Melhoria | Evidência | Impacto | Esforço |
|---|---|---|---|---|
| 1 | **Regras do repositório alvo viram checklist curto no plano, na tarefa do dev e no revisor** (CLAUDE.md do repo: sem comentário/XML-doc, `id` em botão, reuso de componente/estilo). O explorador extrai as 5–8 regras que valem para os arquivos tocados; o planejador não pode contradizê-las; o revisor confere uma a uma. | m-109644 (plano mandou XML-doc, revisor elogiou, Felipe reverteu); m-144245 (reuso, comentários, 24140); it-101662 R1-01; P1-08/R3-01 (`id` no botão) | Alto: tira o ajuste do usuário no USER_REVIEW e comentário do time | Baixo |
| 2 | **Gate de premissa antes de QA/ambiente:** para Bug, pergunta obrigatória ao explorador "reproduz no código atual? o que o card afirma é verdade?"; `TEST_PLAN` só depois. Para valores/limites do card, o plano cita a fonte (ex.: 9×10 dígitos). | bug-146134 (9 delegações, 3 ajustes, sem código); 143560; ConsultasCnh (m-144245) | Alto: evita demanda inteira inútil | Baixo |
| 3 | **Base sempre fresca:** `aidw.py` faz `git fetch` e avisa "local atrás do origin" ao criar worktree/tarefa; todas as tarefas citam `origin/<base>`; nota na KB. | m-144245 (+193 linhas), us-141808 B1-D3 refutado, m-109644 tarefa | Médio (falso positivo + linhas erradas) | Baixo |
| 4 | **Triagem com regra de corte:** SUGESTAO só entra se evitar falha real ou se uma regra do repo exige; revisor limita a ≤5 achados e marca "barata" só com custo medido; não pedir rodada de "enxugamento" depois. Em PR de terceiro, o agente entrega só os comentários que recomenda publicar (5 de 15 hoje). | SUGESTAO 43 mantidas/28 descartadas; it-101662 enum→removido; dt-144187 5/15 | Médio: menos código, menos rodadas, menos leitura do Felipe | Baixo |
| 5 | **Orçamento de tamanho por mudança** (sem voltar aos níveis): se o explorador estima ≤2 arquivos/≤30 linhas, o plano tem teto de ~5 KB, uma exploração só, sem `levantamento+pontos` duplicados, revisão em medium, QA plano e teste na mesma delegação. | m-109644: 80 KB de artefatos e US$ 13,87 para ~16 linhas; plano 18 KB | Alto no custo do orquestrador | Médio |
| 6 | **Pré-voo de teste durante o IMPLEMENT:** o QA em modo plano confirma VPN, ambiente e massa (SELECT), lista as aprovações B* e o orquestrador pede o OK **antes** do código terminar; o orquestrador sobe API/portal locais uma vez; o `qa test` roda uma vez só. Não abrir PR antes do teste sem decisão explícita. | m-109644 (2 execuções de QA, 1º TEST bloqueado por B4, PR antes do teste); m-144245 (QA parado, 3 doubts por massa) | Médio/alto | Médio |
| 7 | **Ajuste temporário de teste sem agente:** `aidw.py test-adjust apply <patch>/revert` + preferir variável de ambiente/launch profile ao patch de código; patch por repo guardado na KB (`environment.desenv.ts`, `PepConsultService`…). | m-109644 A1; bug-146133 6 ajustes/2 repos; bug-146134 3 ajustes; it-101662 ~10 delegações de ambiente | Médio | Médio |
| 8 | **Padrões do time na revisão:** montar `decisoes/padroes-do-time.md` a partir dos code reviews reais (await ausente, flag morta, nome em inglês, erro engolido, condição repetida 3x, `.Result` embrulhando exceção, Voltar do navegador/histórico) e carregar no `reviewer`; todo comentário do time vira linha ali (hoje só vira `respostas-code-review.md`). | PR 7691 (9 de 12 corrigidos), m-144245 24136/24138/24142, us-131190 3 bugs de histórico | Alto: ataca o que escapa para a QA e o time | Médio |
| 9 | **Fechar o ciclo da KB:** o orquestrador oferece `/aidw:done` ao abrir a PR; `qa` grava em `ambiente/massa-de-teste.md` (AGR 6278, `Add/3` token cru, status 1→3); `kb search` obrigatório inclui `ambiente/`; registrar a lição "fetch antes". | 4 demandas sem nota; 6278 redescoberto; ConsultasCnh corrigido | Médio | Baixo |
| 10 | **Automatizar diff por commit/rodada:** `aidw.py pr diff --since <sha> [--only <task>]` + build; elimina as 3 variantes manuais por rodada. | `diff-pr8262-…-r2/-so-144502`, `diff-pr8263-…`, `diff-131190-r1..r17` | Baixo/médio | Baixo |
| 11 | **Emagrecer o `reviewer.md` e o `coder.md`** (18 KB / 13,6 KB) movendo o checklist por repositório para a KB e carregando só o do repo da demanda; `CLAUDE.md` gerado ≤25 KB. | `wc -c` dos agentes; `reviewer.md:148,344` | Médio (relido a cada ferramenta) | Médio |
| 12 | **Arquivar `plano-fluxo-enxuto.md` e registrar o piloto** (m-109644 × m-144245 × bug-146133: delegações, turnos, US$) em `docs/`. | seção 6 | Baixo, mas fecha o ciclo | Baixo |

Prioridade sugerida: 1, 2, 3 (baratas e atacam o retrabalho mais visível), depois 4, 8 e 6; 5 e 7 pedem desenho.
