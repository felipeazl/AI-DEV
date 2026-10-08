import { expect, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const DIR = 'C:/AiDW/contexts/x/demandas/us-1'
const SESSION = 's-orquestrador'
const BASE: Record<string, string> = {
  'C:/AiDW/.aidw/runtime.json': JSON.stringify({ state_dir: 'C:/AiDW/contexts/x/demandas' }),
  'C:/AiDW/orchestrator/config/routing.toml': '[rules]\nmax_retries = 3\n',
  [`${DIR}/demand.json`]: JSON.stringify({ id: 'us-1', step: 'CODER_FIX' }),
  [`${DIR}/metricas.md`]:
    '| Data | Agente | Nível | Modelo | Effort | Label | State | Turnos | Duração | Tokens entrada | Tokens saída | Custo | Limites |\n' +
    '|---|---|---|---|---|---|---|---|---|---|---|---|---|\n' +
    '| 2026-10-08 | codificador | padrao | opus | medium | rota | ok | 5 | 9s | 117,050 | — | — | — |\n',
}
const LIST = ['demand.json', 'metricas.md', 'review-1-r1.md', 'review-1-r4.md']
const norm = (path: string) => path.replace(/\\/g, '/')
const START = { cwd: 'C:/wt/us-1/repo', surface: 'terminal', isInteractive: true } as const
const PROPS = {
  hasSurvey: false,
  isWorking: false,
  maxRows: 4,
  bodyColumns: 160,
  scroll: { offset: 0, bodyRows: 4 },
  view: {},
}

/** O disco e o AiDW de mentira; `orchestrating` põe a sessão no state/sessions.json. */
function fake(on: On, orchestrating: boolean): (readonly string[])[] {
  const files: Record<string, string> = {
    ...BASE,
    'C:/AiDW/state/sessions.json': JSON.stringify(orchestrating ? { [SESSION]: { plugin: 'aidw' } } : {}),
  }
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('command.register', ($, e) => ({ value: { command: e.name } }))
  on('session.id', () => ({ value: SESSION }))
  on('session.cwd', () => ({ value: START.cwd }))
  on('fs.read', ($, e) => {
    const text = files[norm(e.path)]
    return text === undefined ? { deny: `não existe: ${e.path}` } : { value: text }
  })
  on('fs.list', () => ({ value: LIST.map(name => ({ name, kind: 'file' as const, size: 1, mtimeMs: 0, isLink: false })) }))
  on('fs.exists', ($, e) => ({ value: norm(e.path) in files }))
  const runs: (readonly string[])[] = []
  on('process.run', ($, e) => {
    runs.push(e.argv)
    const out = { header: '## Codificador - claude-opus Medium', resumo: 'Codificador (padrao) | 1.000 tokens' }
    return {
      value: { exitCode: 0, stdout: JSON.stringify(out), stderr: '', isStdoutTruncated: false, isStderrTruncated: false },
    }
  })
  on('tool.call', () => ({
    result: {
      status: 'completed',
      agentId: 'a1',
      prompt: 'p',
      content: [{ type: 'text', text: 'feito\n{"state": "implementation_complete"}' }],
      totalTokens: 1000,
      totalToolUseCount: 5,
      totalDurationMs: 9000,
      usage: {
        input_tokens: 1, output_tokens: 1, cache_creation_input_tokens: 0, cache_read_input_tokens: 0,
        server_tool_use: null, service_tier: null, cache_creation: null,
      },
    },
  }))
  return runs
}

const DELEGATION = {
  tool: 'Agent',
  description: 'Codificar rota',
  subagent_type: 'aidw:codificador',
  prompt: `Tarefa: ${DIR}/tarefa-codificador-rota.md. Pasta da demanda: ${DIR}. Nível: padrao. No MCP tools needed.`,
} as const

test('no modo orquestrador, a delegação vira linha do metricas.md e a faixa mostra a demanda', async ($, on) => {
  const runs = fake(on, true)
  await $.session.start(START)

  const ran = await $.tool.call(DELEGATION)

  expect(runs.length).toBe(1)
  const argv = runs[0] ?? []
  expect(argv.slice(1, 3)).toEqual(['C:/AiDW/aidw.py', 'record'])
  for (const [flag, value] of [
    ['--agent', 'aidw:codificador'], ['--label', 'rota'], ['--demand', DIR], ['--tokens', '1000'],
    ['--tool-uses', '5'], ['--duration-ms', '9000'], ['--level', 'padrao'], ['--state', 'implementation_complete'],
  ] as const) {
    expect(argv[argv.indexOf(flag) + 1]).toBe(value)
  }
  expect((ran.context ?? []).join('\n')).toContain('## Codificador - claude-opus Medium')

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'aidw-mods', surface, component: 'AbovePrompt', props: PROPS })
    expect(await ui.find({ type: 'Text', text: /us-1 · CODER_FIX/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /revisão r4\/3 ⚠/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /1 delegações · 117k tokens/ })).toBeDefined()
    await ui.unmount()
  }
})

test('fora do modo orquestrador, o mod não grava nem mostra nada', async ($, on) => {
  const runs = fake(on, false)
  await $.session.start(START)

  const ran = await $.tool.call(DELEGATION)

  expect(runs).toEqual([])
  expect(ran.context ?? []).toEqual([])
  // a faixa fica com o engine: o mod chama next, e no teste não há nada abaixo para desenhar
  await expect($.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'AbovePrompt', props: PROPS }))
    .rejects.toThrow(/no implementation for ui.render/)
})

test('um Agent fora do AiDW passa direto, sem gravar nada', async ($, on) => {
  const runs = fake(on, true)
  await $.session.start(START)
  const ran = await $.tool.call({ tool: 'Agent', description: 'x', prompt: 'Find the config loader' })
  expect(runs).toEqual([])
  expect(ran.context ?? []).toEqual([])
})
