import { describe, expect, test } from 'claude-code/testing'

import { agentOf, checkDelegation } from '../hooks/guards'
import type { DelegationCheck, Runtime } from '../hooks/guards'

const RUNTIME: Runtime = {
  variants: {
    planejador: ['planejador', 'planejador-medium'],
    codificador: ['codificador', 'codificador-medium'],
    revisor: ['revisor', 'revisor-medium', 'revisor-low'],
  },
  maxRetries: 3,
  agents: ['planejador', 'codificador', 'revisor'],
}
const PROMPT = 'Tarefa: C:/d/us-1/plano-us-1.md, entrega E1. Pasta da demanda: C:/d/us-1.'
const base = (over: Partial<DelegationCheck> = {}): DelegationCheck => ({
  subagentType: 'aidw:codificador',
  prompt: PROMPT,
  runtime: RUNTIME,
  userPrompts: ['/aidw:orquestrar 1'],
  step: 'IMPLEMENT',
  round: 0,
  roundKind: null,
  extraRounds: 0,
  kind: 'desenvolvimento',
  ...over,
})

describe('travas da delegação', () => {
  test('delegação certa passa', async () => {
    expect(checkDelegation(base())).toBe(null)
    expect(checkDelegation(base({ subagentType: 'aidw:revisor-medium' }))).toBe(null)
  })

  test('agente fora do AiDW passa', async () => {
    expect(checkDelegation(base({ subagentType: 'general-purpose', prompt: 'x' }))).toBe(null)
  })

  test('variante pertence ao agente', async () => {
    expect(agentOf('aidw:codificador-medium', RUNTIME)).toBe('codificador')
    expect(agentOf('revisor-low', RUNTIME)).toBe('revisor')
    expect(agentOf('Explore', RUNTIME)).toBe(null)
  })

  test('model sem o Felipe pedir é recusado; com o pedido passa', async () => {
    expect(checkDelegation(base({ model: 'sonnet' }))).toContain('não passe `model`')
    expect(checkDelegation(base({ model: 'sonnet', userPrompts: ['use Sonnet no codificador'] }))).toBe(null)
  })

  test('sem pasta da demanda; o nível não é mais pedido', async () => {
    expect(checkDelegation(base({ prompt: 'Tarefa: x.md.' }))).toContain('falta a pasta')
    expect(checkDelegation(base({ prompt: 'Tarefa: x.md. Pasta da demanda: C:/d/us-1.' }))).toBe(null)
  })

  test('variante fora da tabela Agents and effort', async () => {
    const why = checkDelegation(base({ subagentType: 'aidw:codificador-high' }))
    expect(why).toContain('não está na tabela Agents and effort')
    expect(why).toContain('`codificador-medium`')
    expect(checkDelegation(base({ subagentType: 'aidw:planejador-medium' }))).toBe(null)
  })

  test('agente desligado', async () => {
    const runtime = { ...RUNTIME, agents: [...RUNTIME.agents, 'qa'] }
    expect(checkDelegation(base({ runtime, subagentType: 'aidw:qa' }))).toContain('desligado')
  })

  test('prompt grande', async () => {
    expect(checkDelegation(base({ prompt: PROMPT + ' x'.repeat(4000) }))).toContain('por caminho')
  })

  test('limite de rodadas da revisão', async () => {
    const at = (round: number, extra = 0, subagentType = 'aidw:codificador-medium', step = 'CODER_FIX') =>
      checkDelegation(base({ step, round, roundKind: 'revisão', extraRounds: extra, subagentType }))
    expect(at(2)).toBe(null)
    expect(at(3)).toContain('Liberar +1 rodada')
    expect(at(3, 0, 'aidw:revisor-medium', 'TRIAGE')).toContain('rodada 3')
    expect(at(3, 1)).toBe(null)
    expect(checkDelegation(base({ step: 'CODER_FIX', round: 5, roundKind: 'revisão', kind: 'pr-review' }))).toBe(null)
  })

  test('sem laço do plano: o ajuste do plano não trava por rodada', async () => {
    const plan = base({ subagentType: 'aidw:planejador-medium', step: 'PLAN_FIX', round: 3, roundKind: 'plano' })
    expect(checkDelegation(plan)).toBe(null)
  })
})
