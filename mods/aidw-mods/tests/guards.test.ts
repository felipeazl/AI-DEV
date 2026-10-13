import { describe, expect, test } from 'claude-code/testing'

import { agentOf, checkDelegation } from '../hooks/guards'
import type { DelegationCheck, Runtime } from '../hooks/guards'

const RUNTIME: Runtime = {
  levels: {
    trivial: { planejador: null, codificador: 'codificador-sonnet-high', revisor: 'revisor-sonnet-high' },
    padrao: { planejador: 'planejador', codificador: 'codificador', revisor: 'revisor' },
    complexa: { planejador: 'planejador-high', codificador: 'codificador-high', revisor: 'revisor-high' },
  },
  defaultLevel: 'padrao',
  maxRetries: 3,
  agents: ['planejador', 'codificador', 'revisor'],
}
const PROMPT = 'Tarefa: C:/d/us-1/tarefa-codificador-rota.md. Pasta da demanda: C:/d/us-1. Nível: padrao.'
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
  })

  test('agente fora do AiDW passa', async () => {
    expect(checkDelegation(base({ subagentType: 'general-purpose', prompt: 'x' }))).toBe(null)
  })

  test('variante pertence ao agente', async () => {
    expect(agentOf('aidw:codificador-sonnet-high', RUNTIME)).toBe('codificador')
    expect(agentOf('revisor-high', RUNTIME)).toBe('revisor')
    expect(agentOf('Explore', RUNTIME)).toBe(null)
  })

  test('model sem o Felipe pedir é recusado; com o pedido passa', async () => {
    expect(checkDelegation(base({ model: 'sonnet' }))).toContain('não passe `model`')
    expect(checkDelegation(base({ model: 'sonnet', userPrompts: ['use Sonnet no codificador'] }))).toBe(null)
  })

  test('sem pasta da demanda ou sem nível', async () => {
    expect(checkDelegation(base({ prompt: 'Tarefa: x.md. Nível: padrao.' }))).toContain('falta a pasta')
    expect(checkDelegation(base({ prompt: 'Tarefa: x.md. Pasta da demanda: C:/d/us-1.' }))).toContain('Nível')
  })

  test('célula da tabela', async () => {
    expect(checkDelegation(base({ subagentType: 'aidw:codificador-high' }))).toContain('é `codificador`')
    expect(checkDelegation(base({ subagentType: 'aidw:codificador-high', prompt: PROMPT.replace('padrao', 'complexa') }))).toBe(null)
    expect(checkDelegation(base({ subagentType: 'aidw:planejador', prompt: PROMPT.replace('padrao', 'trivial') }))).toContain('não roda')
    expect(checkDelegation(base({ prompt: PROMPT.replace('padrao', 'enorme') }))).toContain('não existe')
  })

  test('prompt grande', async () => {
    expect(checkDelegation(base({ prompt: PROMPT + ' x'.repeat(4000) }))).toContain('por caminho')
  })

  test('limite de rodadas da revisão', async () => {
    const at = (round: number, extra = 0, subagentType = 'aidw:codificador') =>
      checkDelegation(base({ step: 'CODER_FIX', round, roundKind: 'revisão', extraRounds: extra, subagentType }))
    expect(at(2)).toBe(null)
    expect(at(3)).toContain('Liberar +1 rodada')
    expect(at(3, 0, 'aidw:revisor')).toContain('rodada 3')
    expect(at(3, 1)).toBe(null)
    expect(checkDelegation(base({ step: 'CODER_FIX', round: 5, roundKind: 'revisão', kind: 'pr-review' }))).toBe(null)
  })

  test('limite de rodadas do plano', async () => {
    const plan = base({ subagentType: 'aidw:planejador', step: 'PLAN_FIX', round: 3, roundKind: 'plano' })
    expect(checkDelegation(plan)).toContain('revisão do plano')
  })
})
