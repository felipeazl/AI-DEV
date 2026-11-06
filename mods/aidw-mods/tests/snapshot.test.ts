import { describe, expect, test } from 'claude-code/testing'

import { parseDelegations, usd } from '../hooks/aidw'
import { buildSnapshot, nextStep, phaseOf, stateLabel } from '../hooks/snapshot'
import { setLang } from '../hooks/i18n'

// These tests keep the old Portuguese UI strings and artifacts (compatibility); the English ones are in i18n.test.ts.
setLang('pt-BR')

const snap = (demand: Record<string, unknown>, files: Record<string, string> = {}) =>
  buildSnapshot({ dir: 'C:/x/us-1', demand, files: Object.keys(files), texts: files })

describe('aba Geral', () => {
  test('próximo passo: o que você faz ou o que o AiDW está fazendo', async () => {
    const final = snap({ id: 'us-1', step: 'FINAL_REVIEW', history: [{ step: 'FINAL_REVIEW', at: '' }] })
    expect(nextStep(final).you).toBe(true)
    expect(nextStep(final).text).toContain('/aidw:done')
    expect(phaseOf(final)).toBe('PR')
    const plan = nextStep(snap({ id: 'us-1', step: 'PLAN_APPROVAL' }))
    expect([plan.you, plan.text]).toEqual([true, expect.stringContaining('aprova')])
    expect(nextStep(snap({ id: 'us-1', step: 'TRIAGE' })).text).toContain('no chat')
    expect(nextStep(snap({ id: 'us-1', step: 'USER_REVIEW' })).text).toContain('Alterações')
    expect(nextStep(snap({ id: 'us-1', step: 'PR' })).text).toContain('OK')
    const impl = nextStep(snap({ id: 'us-1', step: 'IMPLEMENT' }))
    expect(impl.you).toBe(false)
    expect(impl.text).toContain('implementando')
    expect(nextStep(snap({ id: 'us-1', step: 'REVIEW', status: 'paused' })).text).toContain('/aidw:go us-1')
    expect(nextStep(snap({ id: 'us-1', step: 'DONE' })).text).toContain('Concluída')
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
