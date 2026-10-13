import { describe, expect, test } from 'claude-code/testing'

import { parseDelegations, usd } from '../hooks/aidw'
import { buildSnapshot, nextStep, phaseOf, stateLabel } from '../hooks/snapshot'

const snap = (demand: Record<string, unknown>, files: Record<string, string> = {}) =>
  buildSnapshot({ dir: 'C:/x/us-1', demand, files: Object.keys(files), texts: files, maxRetries: 3 })

describe('aba Geral', () => {
  test('próximo passo: o que você faz ou o que o AiDW está fazendo', async () => {
    const final = snap({ id: 'us-1', step: 'FINAL_REVIEW', history: [{ step: 'FINAL_REVIEW', at: '' }] })
    expect(nextStep(final, 3).you).toBe(true)
    expect(nextStep(final, 3).text).toContain('/aidw:done')
    expect(phaseOf(final)).toBe('Revisão final')
    const impl = nextStep(snap({ id: 'us-1', step: 'IMPLEMENT' }), 3)
    expect(impl.you).toBe(false)
    expect(impl.text).toContain('implementando')
    expect(nextStep(snap({ id: 'us-1', step: 'REVIEW', status: 'paused' }), 3).text).toContain('/aidw:orquestrar us-1')
    expect(nextStep(snap({ id: 'us-1', step: 'DONE' }), 3).text).toContain('Concluída')
  })

  test('limite de rodadas só trava nas etapas do laço', async () => {
    const files = { 'review-us-1-r3.md': '' }
    expect(nextStep(snap({ id: 'us-1', step: 'CODER_FIX' }, files), 3).text).toContain('chegou ao limite')
    expect(nextStep(snap({ id: 'us-1', step: 'CODER_FIX' }, files), 4).text).toContain('corrigindo')
    expect(nextStep(snap({ id: 'us-1', step: 'FINAL_REVIEW' }, files), 3).text).toContain('Confira a entrega')
  })

  test('nota do demand.json', async () => {
    expect(snap({ id: 'us-1', step: 'DONE', note: ' Aguardando revisão ' }).note).toBe('Aguardando revisão')
  })

  test('state do agente em palavras', async () => {
    expect(stateLabel('review_changes_requested')).toBe('pediu mudanças')
    expect(stateLabel('plan_review_approved')).toBe('aprovado')
    expect(stateLabel('audit_findings')).toBe('achou problemas')
    expect(stateLabel('audit_clean')).toBe('nada encontrado')
    expect(stateLabel('environment_blocked')).toBe('bloqueado')
    expect(stateLabel('policy_requires_approval')).toBe('precisa de você')
    expect(stateLabel('implementation_complete')).toBe('concluído')
    expect(stateLabel('algo_novo')).toBe('algo_novo')
  })
})

describe('aba Métricas', () => {
  test('custo em US$ quando o metricas.md traz', async () => {
    expect(usd('$0.42')).toBe(0.42)
    expect(usd('0,42')).toBe(0.42)
    expect(usd('1,234.50')).toBe(1234.5)
    expect(usd('—')).toBeNull()
    const rows = parseDelegations(
      '| 2026-10-08 | codificador | padrao | gpt-5 | high | rota | ok | 5 | 9s | 1,000 | 200 | 0.15 | — |\n' +
        '| 2026-10-08 | revisor | padrao | opus | high | r1 | ok | 5 | 9s | 117,050 | — | — | — |\n',
    )
    expect(rows.map(r => [r.tokens, r.cost])).toEqual([[1200, 0.15], [117050, null]])
  })
})
