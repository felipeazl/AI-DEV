import { describe, expect, test } from 'claude-code/testing'

import {
  decisionOf,
  parseCardAsk,
  parseCardPoints,
  parseCoverage,
  parseDoubts,
  parseEffort,
  parseEstimate,
  parseFindings,
  parseItems,
  parseRoteiro,
  parseSplit,
  progress,
} from '../hooks/artifacts'
import { buildSnapshot } from '../hooks/snapshot'
import { reviewRounds, roundName } from '../hooks/views'

const steps = (...s: string[]) => ({ step: s.at(-1), history: s.map(step => ({ step, at: '' })) })

describe('progresso do Mapa da demanda', () => {
  test('etapas do AiDW e de fora, com a atual', async () => {
    const p = progress('desenvolvimento', steps('UNDERSTAND', 'IMPLEMENT', 'REVIEW', 'FINAL_REVIEW'))
    expect([p.current, p.index, p.total]).toEqual(['Revisão final', 6, 9])
    expect(p.stages.map(s => s.state)).toEqual(['feito', 'feito', 'feito', 'feito', 'feito', 'atual', 'pendente', 'pendente', 'pendente'])
  })

  test('com o time e de volta do Code review', async () => {
    const withTeam = progress('desenvolvimento', steps('IMPLEMENT', 'FINAL_REVIEW', 'CODE_REVIEW'))
    expect(withTeam.stages.find(s => s.name === 'Code review')?.state).toBe('com-time')
    const back = progress('desenvolvimento', steps('IMPLEMENT', 'FINAL_REVIEW', 'CODE_REVIEW', 'CODER_FIX'))
    expect([back.current, back.returnedFrom, back.returns['Code review']]).toEqual(['Revisar', 'Code review', 1])
    expect(back.stages.find(s => s.name === 'Code review')?.state).toBe('voltou')
    const qa = progress('desenvolvimento', steps('FINAL_REVIEW', 'CODE_REVIEW', 'CODER_FIX', 'CODE_REVIEW', 'QA_TEST'))
    expect([qa.current, qa.returnedFrom, qa.returns['Code review']]).toEqual(['Testes QA', null, 1])
  })

  test('pronto marca tudo como feito', async () => {
    const p = progress('desenvolvimento', steps('FINAL_REVIEW', 'DONE'))
    expect(p.stages.every(s => s.state === 'feito')).toBe(true)
  })

  test('etapa de fora do contexto: só na demanda que passa por ela, antes da etapa indicada', async () => {
    const ux = [{ step: 'UX_VALIDATION', name: 'Validação UX', before: 'CODE_REVIEW', who: 'o UX' }]
    const names = (p: ReturnType<typeof progress>) => p.stages.map(s => s.name)
    expect(names(progress('desenvolvimento', steps('IMPLEMENT'), ux))).not.toContain('Validação UX')
    const marked = progress('desenvolvimento', { ...steps('IMPLEMENT'), extra_steps: ['UX_VALIDATION'] }, ux)
    expect(names(marked).slice(5, 8)).toEqual(['Revisão final', 'Validação UX', 'Code review'])
    expect(marked.total).toBe(10)
    const withUx = progress('desenvolvimento', steps('FINAL_REVIEW', 'UX_VALIDATION'), ux)
    expect(withUx.stages.find(s => s.name === 'Validação UX')).toEqual({ name: 'Validação UX', group: 'fora', who: 'o UX', state: 'com-time' })
    const back = progress('desenvolvimento', steps('FINAL_REVIEW', 'UX_VALIDATION', 'CODER_FIX'), ux)
    expect([back.current, back.returnedFrom, back.returns['Validação UX']]).toEqual(['Revisar', 'Validação UX', 1])
    expect(progress('pr-review', steps('UX_VALIDATION'), ux).stages.map(s => s.name)).not.toContain('Validação UX')
  })
})

describe('critérios, regras e cenários', () => {
  test('itens numerados e cobertura', async () => {
    const plan = ['## Critérios de aceite', '- CA1: abre a rota', '## Regras de negócio', '- RN1: IP na 3ª posição', '| CN1 | A1 pelo AVP | x |'].join('\n')
    expect(parseItems(plan, 'RN')).toEqual([{ id: 'RN1', text: 'IP na 3ª posição' }])
    expect(parseItems(plan, 'CN')).toEqual([{ id: 'CN1', text: 'A1 pelo AVP' }])
    const matrix = '| CA | Cenário | Passos |\n|---|---|---|\n| CA1 | CN2 — A1 online | 1. emitir |'
    expect(parseItems(matrix, 'CN')).toEqual([{ id: 'CN2', text: 'A1 online' }])
    const cov = parseCoverage('| ID | Status | Evidência |\n|---|---|---|\n| CA1 | coberto | E2E |\n| RN1 | Implementado | x.cs |\n')
    expect(cov).toEqual({ CA1: 'coberto', RN1: 'implementado' })
  })

  test('snapshot junta plano e cobertura; sem cobertura tudo é "falta"', async () => {
    const files = {
      'demand.json': JSON.stringify({ id: 'us-1', step: 'IMPLEMENT', summary: 'Resumo' }),
      'plano-us-1.md': '# Plano v1\n## Critérios de aceite\n- CA1: abre\n- CA2: fecha\n## Regras de negócio\n- RN1: regra\n',
    }
    const build = (extra: Record<string, string>) => {
      const all: Record<string, string> = { ...files, ...extra }
      return buildSnapshot({ dir: 'C:/x/us-1', demand: JSON.parse(all['demand.json'] ?? '{}'), files: Object.keys(all), texts: all, maxRetries: 3 })
    }
    const none = build({})
    expect([none.summary, none.coverageRecorded, none.coverage.map(c => c.status)]).toEqual(['Resumo', false, ['falta', 'falta', 'falta']])
    const some = build({ 'cobertura-us-1.md': '| CA1 | coberto | e2e |\n| RN1 | implementado | — |' })
    expect(some.coverage.map(c => `${c.id}:${c.status}`)).toEqual(['CA1:coberto', 'CA2:falta', 'RN1:implementado'])
  })
})

describe('revisão V2', () => {
  test('antes e depois, opções e recomendação do revisor', async () => {
    const review = [
      '### R1-02 — SUGESTAO — `Utils/Saneador.cs:23`',
      '**O quê:** dois bool de controle.',
      '**Antes:**',
      '```csharp',
      'Sanear(ip, false, false);',
      '```',
      '**Depois:**',
      '```csharp',
      'Sanear(ip, TipoDado.EnderecoIp);',
      '```',
      '### R1-D1 — Estrutura do projeto de teste',
      '- (a) Manter a convenção do repositório',
      '- (b) Alinhar ao Guideline',
      '**Recomendação:** (a).',
    ].join('\n')
    const [f, d] = parseFindings(review, 1, 'revisão', 'review-us-1-r1.md')
    expect([f?.before, f?.after, f?.file]).toEqual(['Sanear(ip, false, false);', 'Sanear(ip, TipoDado.EnderecoIp);', 'review-us-1-r1.md'])
    expect(d?.options).toEqual(['(a) Manter a convenção do repositório', '(b) Alinhar ao Guideline'])
    expect(d?.recommendation).toBe('(a).')
  })

  test('decisão pela triagem', async () => {
    expect(decisionOf('Corrigir: summary na classe')).toBe('mantido')
    expect(decisionOf('Cai — o card já tem as PRs')).toBe('descartado')
    expect(decisionOf('Mantida, vai ao Felipe/Pedro')).toBe('pendente')
    expect(decisionOf('')).toBe('pendente')
  })

  test('rodadas por arquivo e "corrigido na rN"', async () => {
    const all: Record<string, string> = {
      'demand.json': JSON.stringify({ id: 'it-9', step: 'REVIEW' }),
      'review-it-9-r1.md': '### R1-01 — IMPORTANTE — `a.cs:1`\n**O quê:** falta summary\n',
      'review-it-9-r2.md': '### R1-01 — IMPORTANTE — status: fixed\n',
      'review-otimizacao-it-9-r1.md': '### R1-01 — SUGESTAO — `b.cs:2`\n**O quê:** duplicado\n',
      'triagem-it-9-r1.md': '| ID | Sev. | Decisão |\n|---|---|---|\n| R1-01 | IMPORTANTE | Corrigir |\n',
    }
    const s = buildSnapshot({ dir: 'C:/x/it-9', demand: JSON.parse(all['demand.json'] ?? '{}'), files: Object.keys(all), texts: all, maxRetries: 3 })
    expect(reviewRounds(s).map(r => r.label)).toEqual(['Código r1', 'Código r2', 'Otimização r1'])
    const r1 = s.findings.find(f => f.file === 'review-it-9-r1.md')
    expect([r1?.status, r1?.decision, r1?.title]).toEqual(['corrigido na r2', 'mantido', 'falta summary'])
    const fixed = s.findings.find(f => f.file === 'review-it-9-r2.md')
    expect(fixed?.title).not.toContain('IMPORTANTE')
    expect(roundName(s.findings.find(f => f.file.startsWith('review-otim')) ?? r1!)).toBe('Otimização')
    const named = (file: string) => roundName({ ...r1!, file })
    expect([named('review-T3-a3-r1.md'), named('review-us-131190-r2.md'), named('review-otimizacao-101662-r1.md')])
      .toEqual(['T3-a3', 'Código', 'Otimização'])
    const [o] = parseFindings('### O1-02 — REDUZIR — `Utils/Saneador.cs:1-110`\n**O quê:** enxugar', 1, 'revisão', 'review-otimizacao-x-r1.md')
    expect([o?.id, o?.severity, o?.where]).toEqual(['O1-02', 'SUGESTAO', 'Utils/Saneador.cs:1-110'])
  })
})

describe('teste manual V2', () => {
  test('seções, preparação e passos removidos', async () => {
    const text = [
      '## 0. Preparação',
      '| # | Passo | Quem | Resultado |',
      '|---|---|---|---|',
      '| P0 | VPN conectada | Felipe | |',
      '## 1. Critérios do card',
      '| # | Cenário | Passo | Esperado | Resultado |',
      '|---|---|---|---|---|',
      '| T1 | rota | abrir /fast | máscara | ✅ ok |',
      '| T5 | removido na v5 | fora do escopo | — | |',
    ].join('\n')
    const steps2 = parseRoteiro(text)
    expect(steps2.map(s => [s.id, s.section, s.removed, s.result])).toEqual([
      ['P0', 'Preparação', false, ''],
      ['T1', 'Critérios do card', false, '✅'],
      ['T5', 'Critérios do card', true, ''],
    ])
  })
})

describe('levantamento V2', () => {
  const lev = [
    '## 1. O que o card pede × o que existe',
    '**Card:** integrar o Assistente ao Hub. **Sem critérios de aceite.**',
    '',
    '| Hoje no código | Efeito para a demanda |',
    '|---|---|',
    '| Nuvem só pelo SafeID | Nenhum outro PSC entra |',
    '| Emissão em si | **Não mudam**: a origem é que muda. |',
    '| Plurio só como tipo | Nada a reaproveitar. |',
    '',
    '## 3. Esforço e story points',
    '| Bloco | Dev (dias) |',
    '|---|---|',
    '| PoC no Hub | 1–2 |',
    '| Banco | 0,5–1 |',
    '| **Total dev** | **≈ 12–18 dias** |',
    '| QA integrado (por PSC) | 3–5 |',
    '',
    '- **Como está, o card é 21 SP ou mais**, grande demais.',
    '| # | Item | SP |',
    '|---|---|---|',
    '| 1 | Spike do Hub | 3 |',
    '| 2 | Back | 13 |',
    '  Total **≈ 29 SP**.',
    '- **Nível AiDW: complexa** (externo).',
    '## 4. Dúvidas sobre o card',
    '**Escopo e produto**',
    '- **D1. Qual é o produto?** O título fala em A3,',
    '  e a Feature em SafeID. *Para:* PO',
    '- **D3. SafeID passa pelo Hub?** Migrar padroniza. *Muda a estimativa:* +3 SP se migrar',
    '**Regras**',
    '- **D14. Critérios de aceite:** o card não tem nenhum.',
    '## 5. Riscos',
  ].join('\n')

  test('card × código, esforço, quebra e números', async () => {
    expect(parseCardAsk(lev)).toBe('integrar o Assistente ao Hub. Sem critérios de aceite.')
    expect(parseCardPoints(lev).map(p => p.situation)).toEqual(['precisa mudar', 'não muda', 'nada a reaproveitar'])
    expect(parseEffort(lev)).toEqual([
      { name: 'PoC no Hub', min: 1, max: 2, label: '1–2' },
      { name: 'Banco', min: 0.5, max: 1, label: '0,5–1' },
    ])
    expect(parseSplit(lev).map(i => [i.n, i.sp])).toEqual([['1', '3'], ['2', '13']])
    const e = parseEstimate(lev)
    expect([e.spCard, e.spSplit, e.devDays, e.qaDays, e.level]).toEqual(['21+ SP', '≈ 29 SP', '12–18 dias', '3–5', 'complexa'])
  })

  test('modelo da referência: esforço em horas e situação explícita', async () => {
    const ref = [
      '## Card × código',
      '| Hoje no código | Para a demanda | Situação |',
      '|---|---|---|',
      '| Usa sempre `Certificados[0]` | O Hub usa slot_alias | precisa mudar |',
      '## Estimativa',
      '| Bloco | Dev (h) |',
      '|---|---|',
      '| Back | 16–24 |',
      '| **Total dev** | **24–40 h** |',
      '| QA integrado | 8–12 h |',
      '- **Story points:** 8 — dois sistemas',
      '- **Nível AiDW:** padrao · **Passadas extras:** segurança',
    ].join('\n')
    expect(parseCardPoints(ref)).toEqual([{ today: 'Usa sempre `Certificados[0]`', effect: 'O Hub usa slot_alias', situation: 'precisa mudar' }])
    expect(parseEffort(ref)).toEqual([{ name: 'Back', min: 16, max: 24, label: '16–24' }])
    const e = parseEstimate(ref)
    expect([e.sp, e.devDays, e.qaDays, e.level, e.passes]).toEqual(['8', '24–40 h', '8–12 h', 'padrao', 'segurança'])
  })

  test('dúvidas em grupos, com contexto de várias linhas, para quem e o que muda', async () => {
    const d = parseDoubts(lev)
    expect(d.map(x => [x.id, x.group, x.to, x.affects])).toEqual([
      ['D1', 'Escopo e produto', 'PO', ''],
      ['D3', 'Escopo e produto', '', '+3 SP se migrar'],
      ['D14', 'Regras', '', ''],
    ])
    expect(d[0]?.why).toBe('O título fala em A3, e a Feature em SafeID.')
  })
})
