import { describe, expect, test } from 'claude-code/testing'

import {
  groupArtifacts,
  kindOf,
  parseCriteria,
  parseDoubts,
  parseEstimate,
  parseFindings,
  parsePlanMeta,
  parsePoints,
  parseRoteiro,
  parseTestMatrix,
  parseTriage,
  parseVerdicts,
  timeline,
} from '../hooks/artifacts'

describe('tipo de uso e linha do tempo', () => {
  test('o tipo vem dos arquivos e dos repositórios', async () => {
    expect(kindOf({ repos: [{ pr: '7586' }] }, ['diff-pr7586-Front.patch'])).toBe('pr-review')
    expect(kindOf({ title: 'Algo (levantamento)' }, ['resumo-1.md'])).toBe('levantamento')
    expect(kindOf({}, ['levantamento-us-1.md'])).toBe('levantamento')
    expect(kindOf({}, ['plano-131190.md', 'plano-testes-131190.md'])).toBe('desenvolvimento')
    expect(kindOf({ repos: [{ pr: '7' }] }, ['plano-1.md'])).toBe('desenvolvimento')
  })

  test('levantamento concluído e implementação iniciada vira desenvolvimento antes do plano', async () => {
    const files = ['levantamento-m-1.md', 'pontos-m-1.md']
    const h = (...steps: string[]) => ({ history: steps.map(step => ({ step, at: '' })) })
    expect(kindOf(h('UNDERSTAND', 'ESTIMATE'), files)).toBe('levantamento')
    expect(kindOf(h('ESTIMATE', 'DONE'), files)).toBe('levantamento')
    expect(kindOf(h('ESTIMATE', 'DONE', 'EXPLORE'), files)).toBe('desenvolvimento')
    expect(kindOf(h('ESTIMATE', 'DONE', 'EXPLORE', 'ESTIMATE'), files)).toBe('levantamento')
  })

  test('fase atual pela etapa; HUMAN_APPROVAL fica na fase anterior', async () => {
    const t = timeline('desenvolvimento', {
      step: 'HUMAN_APPROVAL',
      history: [{ step: 'REVIEW', at: '' }, { step: 'CODER_FIX', at: '' }, { step: 'REVIEW', at: '' }, { step: 'HUMAN_APPROVAL', at: '' }],
    })
    expect(t.find(x => x.state === 'atual')?.name).toBe('Revisão')
    expect(t.find(x => x.name === 'Revisão')?.visits).toBe(3)
    expect(timeline('pr-review', { step: 'DONE' }).every(x => x.state === 'feito')).toBe(true)
  })
})

describe('achados e triagem', () => {
  const review = [
    '## Achados',
    '### R1-01 — IMPORTANTE — `src/views/login/LoginView.vue:39-40,267-283`',
    '',
    '**O quê:** os dois novos flags booleanos do fluxo fast não seguem o padrão de nomenclatura.',
    '**Correção sugerida:** renomear.',
    '',
    '### R1-02 — SUGESTAO — PR 7639 — `async` sem `await` em `ValidateFacialRequirements`',
    '**Rascunho do comentário de PR (7639):**',
    '> A resposta perdeu `livenessResult`.',
    '> Pode conferir?',
    '',
    '### R4-01 = B2-01 — CRITICO — `src/services/aut.ts:20-59` (exposto por',
    '- Problema: token vai para o log.',
    '### R1-03 — IMPORTANTE — aberto',
    '- Arquivo/linha: `src/views/login/LoginView.vue:107`.',
    '- Problema: `ehProtocoloValido` considera válido protocolo curto.',
    '### R1-D1 — Critério 4: a validação de foto ainda vai para a T4',
    '## Resumo final',
    'Voto sugerido: aguardar autor (`-5`) enquanto R1-01 permanecer aberto.',
  ].join('\n')

  test('variações reais de cabeçalho', async () => {
    const f = parseFindings(review, 1, 'revisão')
    expect(f.map(x => [x.id, x.severity])).toEqual([
      ['R1-01', 'IMPORTANTE'],
      ['R1-02', 'SUGESTAO'],
      ['R4-01', 'CRITICO'],
      ['R1-03', 'IMPORTANTE'],
      ['R1-D1', 'DUVIDA'],
    ])
    expect(f[0]?.where).toBe('src/views/login/LoginView.vue:39-40,267-283')
    expect(f[0]?.title).toContain('flags booleanos')
    expect(f[1]?.comment).toBe('A resposta perdeu `livenessResult`.\nPode conferir?')
    expect(f[2]?.title).toBe('token vai para o log.')
    expect(f[3]?.status).toBe('aberto')
    expect(f[4]?.title).toContain('Critério 4')
  })

  test('triagem em tabela, em lista e o que já foi publicado', async () => {
    const t = parseTriage(
      [
        '# Triagem — review-131192-r1 (PR 7586)',
        '| ID | Revisor | Triagem | Motivo |',
        '|---|---|---|---|',
        '| R1-01 | CRITICO | **IMPORTANTE** | Bug real (confirmado em `LoginView.vue:102`) |',
        '| R1-D1 | DÚVIDA | Não comentar | fora do escopo da PR. |',
        '- R1-03: manter aberto como IMPORTANTE; vira comentário.',
        '## Publicado (2026-10-06, com OK do Felipe)',
        '- PR 7639: thread 22996, R1-01, ordem de deploy.',
      ].join('\n'),
    )
    expect(t.decisions['R1-01']).toBe('IMPORTANTE — Bug real (confirmado em `LoginView.vue:102`)')
    expect(t.decisions['R1-D1']).toContain('Não comentar')
    expect(t.decisions['R1-03']).toContain('manter aberto')
    expect(t.published).toEqual(['R1-01'])
  })
})

describe('critérios, testes e roteiro', () => {
  test('critérios em lista com caixa, numerados e com negrito', async () => {
    expect(parseCriteria('## Critérios de aceite (verificáveis pelo QA)\n- [ ] CA1: `/fast` abre o fluxo\n- [x] C2: CPF\n## Riscos\n- x')
      .map(c => [c.id, c.text])).toEqual([['CA1', '`/fast` abre o fluxo'], ['C2', 'CPF']])
    expect(parseCriteria('### Critérios de aceite\n1. **Captura (FaceTec):** na videoconferência\n2. outro\n').map(c => c.id))
      .toEqual(['CA1', 'CA2'])
  })

  test('matriz do plano de testes (coluna Tipo) e vereditos', async () => {
    const how = parseTestMatrix([
      '## 2. Matriz de cobertura',
      '| CA | Cenário | Passos | Resultado esperado | Evidência | Tipo |',
      '|---|---|---|---|---|---|',
      '| CA1 | T1 — acesso direto | 1. Acessar | ok | Tela | manual |',
      '| CA1 | T1b | x | y | z | auto-browser |',
      '| CA9 (regressão) | T9 | x | y | z | automatizado (build) |',
    ].join('\n'))
    expect(how).toEqual({ CA1: ['manual', 'auto-browser'], CA9: ['automatizado (build)'] })
    const v = parseVerdicts('| CA1 | ✅ atendido | print |\n- CA2 ❌ falhou no Safari\n| CA3 | pending_manual | — |')
    expect([v.CA1?.result, v.CA2?.result, v.CA3?.result]).toEqual(['atendido', 'falhou', 'pendente'])
  })

  test('roteiro de teste manual', async () => {
    const steps = parseRoteiro([
      '| # | CA do card | Passo | Esperado | Resultado |',
      '|---|---|---|---|---|',
      '| T1 | Rota | Aba nova → `localhost:5173/fast` | Login visível | ✅ abriu |',
      '| T2 | Erro | Forçar 500 | Mensagem | |',
    ].join('\n'))
    expect(steps.map(s => [s.id, s.result])).toEqual([['T1', '✅'], ['T2', '']])
    expect(steps[0]?.note).toBe('abriu')
  })
})

describe('levantamento', () => {
  test('modelo da referência', async () => {
    const text = [
      '**Estimativa:** 8 SP · 11–16 h · complexidade Alta · confiança baixa',
      '## Pontos do card',
      '| # | Ponto | No código | Evidência |',
      '|---|---|---|---|',
      '| P01 | aceitar PJ | 🔗 outro sistema | `x.cs:1` |',
      '## Dúvidas',
      '1. **O PJ entra?** *Por que importa:* dobra o escopo. *Para:* PO.',
      '2. **Qual ambiente?** *Para:* Tech Lead.',
      '## Fontes',
    ].join('\n')
    const e = parseEstimate(text)
    expect([e.sp, e.hours, e.complexity, e.confidence]).toEqual(['8', '11–16 h', 'Alta', 'baixa'])
    expect(parsePoints(text, '').map(p => [p.id, p.verdict])).toEqual([['P01', '🔗 outro sistema']])
    expect(parseDoubts(text).map(d => [d.n, d.question, d.to])).toEqual([[1, 'O PJ entra?', 'PO'], [2, 'Qual ambiente?', 'Tech Lead']])
  })

  test('formato antigo (seções numeradas) e pontos-<id>.md', async () => {
    const old = [
      '## 3. Esforço e story points',
      '| Bloco | Dev (h) |',
      '| **Total dev** | **≈ 9–14 h (1,5–2 dias)** |',
      '- **Recomendação: 5 SP**',
      '## 4. Dúvidas sobre o card (para PO / Tech Lead)',
      '1. Vale para A3? (PO)',
    ].join('\n')
    const e = parseEstimate(old)
    expect(e.sp).toBe('5')
    expect(e.hours).toContain('9–14 h')
    expect(parseDoubts(old).map(d => [d.question, d.to])).toEqual([['Vale para A3? (PO)', 'PO']])
    expect(parsePoints('', 'P01 — aceitar CPF — origem: descrição\nP02 — e-mail — origem: critério 2').map(p => p.text))
      .toEqual(['aceitar CPF', 'e-mail'])
  })
})

describe('plano e arquivos', () => {
  test('nível, passadas e versão', async () => {
    expect(parsePlanMeta('# Rota única — Plano de Execução v7\n**Nível: complexa** — dois sistemas\nPassadas extras: bugs sim — UI thread; segurança não'))
      .toEqual({ level: 'complexa', passes: 'bugs sim — UI thread; segurança não', version: '7' })
  })

  test('artefatos agrupados', async () => {
    const g = groupArtifacts(['resumo-1.md', 'plano-1.md', 'plano-testes-1.md', 'review-1-r1.md', 'diff-1-r1.patch', 'demand.json', 'x.png'])
    expect(g).toEqual({
      Card: ['resumo-1.md'],
      Plano: ['plano-1.md'],
      Testes: ['plano-testes-1.md'],
      Revisão: ['review-1-r1.md'],
      Diffs: ['diff-1-r1.patch'],
    })
  })
})

describe('revisão do fluxo v3: uma passada com categoria', () => {
  test('a categoria sai do título e não entra no texto do achado', async () => {
    const review = [
      '### R1-01 — IMPORTANTE — bug — `src/a.ts:10`',
      '**O quê:** o flag de salvando não volta no erro',
      '**Recomendação:** manter — o botão fica travado',
      '',
      '### R1-02 — CRITICO — seguranca — `src/b.ts:3`',
      '**O quê:** token no log',
      '',
      '### R1-03 — SUGESTAO — `src/c.ts:1`',
      '**O quê:** nome',
    ].join('\n')
    const f = parseFindings(review, 1, 'revisão', 'review-us-1-r1.md')
    expect(f.map(x => `${x.id}:${x.severity}:${x.category}:${x.where}`)).toEqual([
      'R1-01:IMPORTANTE:bug:src/a.ts:10',
      'R1-02:CRITICO:seguranca:src/b.ts:3',
      'R1-03:SUGESTAO::src/c.ts:1',
    ])
    expect(f[0]?.recommendation).toContain('manter')
  })
})
