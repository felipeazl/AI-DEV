import { describe, expect, test } from 'claude-code/testing'

import { agentOf, checkDelegation } from '../hooks/guards'
import type { DelegationCheck, Runtime } from '../hooks/guards'
import { setLang } from '../hooks/i18n'

// These tests keep the old Portuguese UI strings and artifacts (compatibility); the English ones are in i18n.test.ts.
setLang('pt-BR')

const RUNTIME: Runtime = {
  variants: {
    planejador: ['planejador', 'planejador-medium'],
    codificador: ['codificador', 'codificador-medium'],
    revisor: ['revisor', 'revisor-medium', 'revisor-low'],
  },
  agents: ['planejador', 'codificador', 'revisor'],
  roles: { planejador: 'planner', codificador: 'coder', revisor: 'reviewer' },
}
const PROMPT = 'Tarefa: C:/d/us-1/plano-us-1.md, entrega E1. Pasta da demanda: C:/d/us-1.'
const base = (over: Partial<DelegationCheck> = {}): DelegationCheck => ({
  subagentType: 'aidw:codificador',
  prompt: PROMPT,
  runtime: RUNTIME,
  userPrompts: ['/aidw:go 1'],
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

  test('model sem o usuário pedir é recusado; com o pedido passa', async () => {
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

  test('sem limite de rodadas: a demanda itera até terminar (painel v4)', async () => {
    expect(checkDelegation(base({ subagentType: 'aidw:codificador-medium', prompt: PROMPT + ' Rodada 9 da revisão.' }))).toBe(null)
  })
})
