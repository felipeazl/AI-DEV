import { describe, expect, test } from 'claude-code/testing'

import {
  agentCardWidth,
  agentSpec,
  agentsLayout,
  compact,
  demandSetId,
  labelFor,
  parseDelegation,
  parseMetricas,
  parseOrchestrator,
  parseState,
  roundFor,
} from '../hooks/aidw'

describe('métricas do orquestrador', () => {
  test('soma as sessões do metricas-orquestrador.md', async () => {
    const md = [
      '# Métricas do orquestrador', '',
      '| Sessão | Início | Atualizado | Modelo | Turnos | Duração | Entrada | Cache escrito | Cache lido | Saída | Custo equiv. (USD) |',
      '|---|---|---|---|---|---|---|---|---|---|---|',
      '| 79aafeb8 | 2026-10-21 08:43 | 2026-10-21 09:10 | claude-opus-5-5 | 2 | 50s | 15 | 302,000 | 300,000 | 1,500 | 2.51 |',
      '| dcc0d767 | 2026-10-21 10:00 | 2026-10-21 10:05 | claude-opus-5-5 | 1 | 9s | 5 | 1,000 | 1,000 | 100 | — |',
    ].join('\n')
    const o = parseOrchestrator(md)
    expect(o.rows.map(r => [r.session, r.turns, r.seconds, r.tokens, r.cacheRead, r.cost])).toEqual([
      ['79aafeb8', 2, 50, 603_515, 300_000, 2.51],
      ['dcc0d767', 1, 9, 2_105, 1_000, null],
    ])
    expect([o.turns, o.tokens, o.cost]).toEqual([3, 605_620, 2.51])
    expect(parseOrchestrator('')).toEqual({ rows: [], steps: [], turns: 0, tokens: 0, cost: null })
  })

  test('seção Por etapa: os turnos do chat principal por etapa da demanda', async () => {
    const md = [
      '| Sessão | Início | Atualizado | Modelo | Turnos | Duração | Entrada | Cache escrito | Cache lido | Saída | Custo equiv. (USD) |',
      '|---|---|---|---|---|---|---|---|---|---|---|',
      '| 79aafeb8 | 2026-11-04 08:43 | 2026-11-04 09:10 | claude-opus-5-5 | 3 | 9s | 30 | 3,000 | 600,000 | 1,500 | 0.17 |',
      '', '## Por etapa', '',
      '| Etapa | Turnos | Duração | Entrada | Cache escrito | Cache lido | Saída | Custo equiv. (USD) |',
      '|---|---|---|---|---|---|---|---|',
      '| PLAN | 2 | 6s | 20 | 2,000 | 400,000 | 1,000 | 0.1160 |',
      '| PLAN_APPROVAL | 1 | 3s | 10 | 1,000 | 200,000 | 500 | — |',
    ].join('\n')
    const o = parseOrchestrator(md)
    expect(o.rows.length).toBe(1)
    expect(o.steps).toEqual([
      { step: 'PLAN', turns: 2, tokens: 403_020, cost: 0.116 },
      { step: 'PLAN_APPROVAL', turns: 1, tokens: 201_510, cost: null },
    ])
  })
})

describe('delegação do AiDW', () => {
  test('lê pasta da demanda, nível e tarefa do prompt', async () => {
    const d = parseDelegation(
      'Tarefa: C:/AiDW/contexts/acme/demandas/us-1/tarefa-codificador-rota.md. ' +
        'Pasta da demanda: C:/AiDW/contexts/acme/demandas/us-1. Nível: padrao. No MCP tools needed.',
    )
    expect(d).toEqual({
      demand: 'C:/AiDW/contexts/acme/demandas/us-1',
      level: 'padrao',
      task: 'C:/AiDW/contexts/acme/demandas/us-1/tarefa-codificador-rota.md',
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

  test('com um laço depois da entrega, só as revisões dele contam', async () => {
    const files = ['review-9001-r4.md', 'review-9001-bug-1234-r1.md', 'review-9001-bug-1235-r2.md']
    expect(roundFor('CODER_FIX', files, 'bug-1234')).toEqual({ round: 1, kind: 'revisão' })
    expect(roundFor('CODER_FIX', files, 'bug-1')).toEqual({ round: 0, kind: null })
    expect(roundFor('CODER_FIX', files)).toEqual({ round: 4, kind: 'revisão' })
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

describe('agentes rodando na faixa', () => {
  const agent = (i: number) => ({ key: `k${i}`, agent: 'revisao', display: 'Revisão', model: 'Sonnet', effort: 'high', label: 'smoke', since: 0, tokens: 51_000 })
  const six = [1, 2, 3, 4, 5, 6].map(agent)

  test('card com no mínimo 30 colunas e o texto mais largo', () => {
    expect(agentCardWidth({ ...agent(1), display: 'Busca', model: 'Haiku', effort: undefined })).toBe(30)
    expect(agentCardWidth({ ...agent(1), label: 'revisão da entrega E3 do front' })).toBeGreaterThan(30)
  })

  test('cards enquanto cabem numa linha; senão uma linha por agente', () => {
    expect(agentsLayout(six.slice(0, 2), 160, 8)).toEqual({ mode: 'cards', shown: 2 })
    expect(agentsLayout(six, 160, 8)).toEqual({ mode: 'list', shown: 6 })
    expect(agentsLayout(six, 200, 8)).toEqual({ mode: 'cards', shown: 6 })
  })

  test('sem altura para todos: os primeiros e a linha de resumo', () => {
    expect(agentsLayout(six, 120, 4)).toEqual({ mode: 'list', shown: 3 })
    expect(agentsLayout(six, 120, 0)).toEqual({ mode: 'list', shown: 1 })
  })

  test('sem a largura (0): até 4 cards', () => {
    expect(agentsLayout(six.slice(0, 4), 0, 8).mode).toBe('cards')
    expect(agentsLayout(six.slice(0, 5), 0, 8).mode).toBe('list')
  })
})

test('agentSpec: o modelo e o effort vêm da variante e do agente base', () => {
  const agents = [
    { name: 'busca', display: 'Busca', model: 'haiku', effort: '' },
    { name: 'dev', display: 'Dev', model: 'sonnet', effort: 'high' },
  ]
  expect(agentSpec('busca', agents)).toEqual({ display: 'Busca', model: 'Haiku', effort: '' })
  expect(agentSpec('aidw:busca-sonnet-medium', agents)).toEqual({ display: 'Busca', model: 'Sonnet', effort: 'medium' })
  expect(agentSpec('dev-medium', agents)).toEqual({ display: 'Dev', model: 'Sonnet', effort: 'medium' })
  expect(agentSpec('general-purpose', agents)).toEqual({ display: 'general-purpose', model: '', effort: '' })
})
