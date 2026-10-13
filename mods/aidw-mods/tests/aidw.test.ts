import { describe, expect, test } from 'claude-code/testing'

import {
  compact,
  demandIds,
  demandSetId,
  labelFor,
  parseDelegation,
  parseMaxRetries,
  parseMetricas,
  parseState,
  roundFor,
} from '../hooks/aidw'

describe('delegação do AiDW', () => {
  test('lê pasta da demanda, nível e tarefa do prompt', async () => {
    const d = parseDelegation(
      'Tarefa: C:/AiDW/contexts/safeweb/demandas/us-1/tarefa-codificador-rota.md. ' +
        'Pasta da demanda: C:/AiDW/contexts/safeweb/demandas/us-1. Nível: padrao. No MCP tools needed.',
    )
    expect(d).toEqual({
      demand: 'C:/AiDW/contexts/safeweb/demandas/us-1',
      level: 'padrao',
      task: 'C:/AiDW/contexts/safeweb/demandas/us-1/tarefa-codificador-rota.md',
    })
  })

  test('aceita barra invertida e crase', async () => {
    const d = parseDelegation('Pasta da demanda: `C:\\AiDW\\demandas\\bug-2`\nNível: simples')
    expect(d?.demand).toBe('C:/AiDW/demandas/bug-2')
    expect(d?.level).toBe('simples')
  })

  test('sem pasta da demanda não é delegação do AiDW', async () => {
    expect(parseDelegation('Find the config loader')).toBe(null)
  })
})

describe('resultado do agente', () => {
  test('o state é o último do texto', async () => {
    expect(parseState('{"state": "implementation_complete"} ... {"state": "review_changes_requested"}')).toBe(
      'review_changes_requested',
    )
    expect(parseState('sem json')).toBe(null)
  })

  test('rótulo vem da tarefa, sem tarefa- e sem o agente', async () => {
    expect(labelFor('C:/d/tarefa-codificador-rota-fast.md', 'aidw:codificador-high', 'x')).toBe('rota-fast')
    expect(labelFor('tarefa-aidw-revisor-pr7586.md', 'revisor', 'x')).toBe('pr7586')
    expect(labelFor(null, 'explorador', 'Explorar fluxo de emissão')).toBe('explorar-fluxo-de-emissao')
  })
})

describe('estado da demanda', () => {
  test('soma as linhas do metricas.md', async () => {
    const md = [
      '| Data | Agente | Nível | Modelo | Effort | Label | State | Turnos | Duração | Tokens entrada | Tokens saída | Custo | Limites |',
      '|---|---|---|---|---|---|---|---|---|---|---|---|---|',
      '| 2026-09-28 | revisor | padrao | sonnet | high | plano-r1 | ok | — | 0s | — | — | — | — |',
      '| 2026-09-28 | revisor | simples | sonnet | medium | plano-r2 | ok | 17 | 278s | 103,974 | — | — | — |',
      '| 2026-09-29 | codificador | padrao | gpt | high | t1 | ok | 3 | 10s | 1,000 | 500 | 0.1 | — |',
    ].join('\n')
    expect(parseMetricas(md)).toEqual({ rows: 3, tokens: 105_474, level: 'padrao' })
  })

  test('rodada da revisão do código e do plano', async () => {
    const files = ['review-131190-r1.md', 'review-131190-r4.md', 'revisao-plano-131190-r2.md', 'plano-131190.md']
    expect(roundFor('CODER_FIX', files)).toEqual({ round: 4, kind: 'revisão' })
    expect(roundFor('PLAN_FIX', files)).toEqual({ round: 2, kind: 'plano' })
    expect(roundFor('IMPLEMENT', ['plano.md'])).toEqual({ round: 0, kind: null })
  })

  test('max_retries do routing.toml', async () => {
    expect(parseMaxRetries('[rules]\nmax_retries = 3\n')).toBe(3)
    expect(parseMaxRetries('')).toBe(3)
  })

  test('demand set no shell', async () => {
    expect(demandSetId('python "C:/AiDW/aidw.py" demand set us-131190 --step REVIEW')).toBe('us-131190')
    expect(demandSetId('python aidw.py demand show us-1')).toBe(null)
  })

  test('tokens compactos', async () => {
    expect(compact(1_234_567)).toBe('1,2M')
    expect(compact(117_050)).toBe('117k')
    expect(compact(950)).toBe('950')
  })
})

describe('demanda pelo argumento do /aidw:orquestrar', () => {
  test('id com prefixo, número solto e link de work item', async () => {
    expect(demandIds('us-116332')).toEqual({ named: ['us-116332'], numbers: ['116332'] })
    expect(demandIds('retome a IT 101662 e veja https://dev.azure.com/x/_workitems/edit/101662/').numbers).toEqual(['101662'])
    expect(demandIds('feature/pipeline-liveness-front').named).toEqual([])
  })
})
