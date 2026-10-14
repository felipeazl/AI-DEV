import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const STATE = 'C:/AiDW/contexts/x/demandas'
const SESSION = 's-orquestrador'
const METRICAS =
  '| Data | Agente | Nível | Modelo | Effort | Label | State | Turnos | Duração | Tokens entrada | Tokens saída | Custo | Limites |\n' +
  '|---|---|---|---|---|---|---|---|---|---|---|---|---|\n' +
  '| 2026-10-08 | codificador | padrao | opus | medium | rota | ok | 5 | 9s | 117,050 | — | — | — |\n'
const RUNTIME = {
  state_dir: STATE,
  context: 'x',
  max_retries: 3,
  default_level: 'padrao',
  levels: {
    padrao: { planejador: 'planejador', codificador: 'codificador', revisor: 'revisor' },
    complexa: { planejador: 'planejador-high', codificador: 'codificador-high', revisor: 'revisor-high' },
  },
  agents: {
    orchestrator: { name: 'orquestrador', enabled: true },
    planner: { name: 'planejador', enabled: true },
    coder: { name: 'codificador', enabled: true },
    reviewer: { name: 'revisor', enabled: true },
  },
}

/** As três demandas de exemplo, uma por uso. */
const DEMANDS: Record<string, Record<string, string>> = {
  'us-1': {
    'demand.json': JSON.stringify({
      id: 'us-1', title: 'Rota fast', step: 'CODER_FIX',
      history: [{ step: 'UNDERSTAND', at: '' }, { step: 'IMPLEMENT', at: '' }, { step: 'REVIEW', at: '' }, { step: 'CODER_FIX', at: '' }],
      repos: [{ repo: 'C:/p/Front', path: 'C:/wt/us-1/Front', branch: 'feature/1-rota', base: 'origin/dev' }],
    }),
    'metricas.md': METRICAS,
    'plano-us-1.md': '# Plano de Execução v2\nNível: padrao — um sistema\n\n## Critérios de aceite\n- [ ] CA1: abre a rota\n- [ ] CA2: mostra o erro\n',
    'plano-testes-us-1.md': '## Matriz de cobertura\n| CA | Cenário | Passos | Esperado | Evidência | Tipo |\n|---|---|---|---|---|---|\n| CA1 | T1 | a | b | c | auto-browser |\n| CA2 | T2 | a | b | c | manual |\n',
    'qa-us-1-r1.md': '| CA1 | ✅ atendido | print |\n',
    'roteiro-testes-us-1.md': '| # | Passo | Esperado | Resultado |\n|---|---|---|---|\n| T1 | abrir a rota | tela abre | ✅ ok |\n| T2 | forçar erro | mensagem | |\n',
    'review-us-1-r1.md': '### R1-01 — IMPORTANTE — `src/a.ts:10`\n**O quê:** nome ruim\n',
    'review-us-1-r4.md': '### R4-01 — CRITICO — `src/b.ts:3`\n**O quê:** quebra o login\n',
    'triagem-us-1-r4.md': '| ID | Sev. | Decisão |\n|---|---|---|\n| R4-01 | CRITICO | Corrigir |\n',
  },
  'pr-7': {
    'demand.json': JSON.stringify({
      id: 'pr-7', step: 'FINAL_REVIEW',
      repos: [{ repo: 'C:/p/Hope', path: 'C:/wt/pr-7/Hope', branch: 'pr/7', base: 'abc', pr: '7', source: 'def' }],
    }),
    'diff-pr7-Hope.patch': 'diff --git a/x.cs b/x.cs\n--- a/x.cs\n+++ b/x.cs\n@@ -1 +1 @@\n-a\n+b\n',
    'review-pr-7-r1.md': [
      '### R1-01 — IMPORTANTE — `x.cs:1`', '**O quê:** troca o contrato', '**Rascunho do comentário de PR (7):**', '> Isto quebra o contrato.', '',
      '### R1-02 — SUGESTAO — `x.cs:2`', '**O quê:** nome', '', 'Voto sugerido: aguardar autor (`-5`).',
    ].join('\n'),
  },
  'lv-9': {
    'demand.json': JSON.stringify({ id: 'lv-9', title: 'Algo (levantamento)', step: 'ESTIMATE', repos: [] }),
    'levantamento-lv-9.md': [
      '# Levantamento', '**Estimativa:** 5 SP · 9–14 h · complexidade Média · confiança média', '',
      '## Pontos do card', '| # | Ponto | No código | Evidência |', '|---|---|---|---|',
      '| P01 | aceitar CPF | ✅ confirmado | `a.cs:1` |', '| P02 | e-mail | ⚠️ diverge | `b.cs:2` |', '',
      '## Dúvidas', '1. **Vale para PJ?** *Por que importa:* muda a regra. *Para:* PO.',
    ].join('\n'),
  },
}

const norm = (path: string) => path.replace(/\\/g, '/')
const PROPS_BAND = { hasSurvey: false, isWorking: false, maxRows: 4, bodyColumns: 160, scroll: { offset: 0, bodyRows: 4 }, view: {} }
const PROPS_PANE = { title: 'AiDW', isFocused: true, bodyColumns: 160, placement: 'dock' as const, scroll: { offset: 0, bodyRows: 40 }, view: {} }

type Fake = { runs: (readonly string[])[]; fills: string[]; submits: string[] }

/** O disco, o AiDW e o engine de mentira; `demand` é a pasta onde a sessão abre. */
function fake(on: On, opts: { orchestrating: boolean; demand: string; argument?: string; cwd?: string }): Fake {
  const files: Record<string, string> = {
    'C:/AiDW/.aidw/runtime.json': JSON.stringify(RUNTIME),
    'C:/AiDW/state/sessions.json': JSON.stringify(opts.orchestrating ? { [SESSION]: { plugin: 'aidw', argument: opts.argument ?? '' } } : {}),
  }
  for (const [id, entries] of Object.entries(DEMANDS)) {
    for (const [name, text] of Object.entries(entries)) files[`${STATE}/${id}/${name}`] = text
  }
  const out: Fake = { runs: [], fills: [], submits: [] }
  mock.clock(on)
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('command.register', ($, e) => ({ value: { command: e.name } }))
  on('session.id', () => ({ value: SESSION }))
  on('session.cwd', () => ({ value: opts.cwd ?? `C:/wt/${opts.demand}/repo` }))
  on('session.usage', () => ({
    value: {
      startedAt: 0,
      context: { percent: 41, tokens: 82_000 },
      rateLimits: [
        { kind: 'seven_day', percentUsed: 58 },
        { kind: 'five_hour', percentUsed: 91, resetsAt: '2026-10-14T16:40:00Z' },
      ],
    } as never,
  }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.close', () => ({ value: undefined }))
  on('fs.read', ($, e) => {
    const text = files[norm(e.path)]
    return text === undefined ? { deny: `não existe: ${e.path}` } : { value: text }
  })
  on('fs.list', ($, e) => {
    const dir = `${norm(e.path)}/`
    const rest = Object.keys(files).filter(f => f.startsWith(dir)).map(f => f.slice(dir.length))
    const names = [...new Set(rest.map(r => r.split('/')[0] ?? ''))]
    return {
      value: names.map(name => ({
        name, kind: rest.includes(name) ? ('file' as const) : ('dir' as const), size: 1, mtimeMs: 0, isLink: false,
      })),
    }
  })
  on('fs.exists', ($, e) => ({ value: norm(e.path) in files }))
  on('prompt.fill', ($, e) => {
    out.fills.push(e.text)
    return { isFilled: true }
  })
  on('prompt.submit', ($, e) => {
    out.submits.push(e.text)
    return { text: e.text }
  })
  on('process.run', ($, e) => {
    out.runs.push(e.argv)
    const header = { header: '## Codificador - claude-opus Medium', resumo: 'Codificador (padrao) | 1.000 tokens' }
    return { value: { exitCode: 0, stdout: JSON.stringify(header), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('tool.call', () => ({
    result: {
      status: 'completed', agentId: 'a1', prompt: 'p',
      content: [{ type: 'text', text: 'feito\n{"state": "implementation_complete"}' }],
      totalTokens: 1000, totalToolUseCount: 5, totalDurationMs: 9000,
      usage: { input_tokens: 1, output_tokens: 1, cache_creation_input_tokens: 0, cache_read_input_tokens: 0, server_tool_use: null, service_tier: null, cache_creation: null },
    },
  }))
  return out
}

/** Acha um Text pelo padrão ou falha dizendo qual (o find devolve undefined sem dizer o quê). */
async function has(view: { find: (q: { type: 'Text'; text: RegExp }) => Promise<unknown> }, text: RegExp): Promise<void> {
  if ((await view.find({ type: 'Text', text })) === undefined) throw new Error(`não desenhou ${text}`)
}

/** O motivo de uma recusa: `deny` para o `$.tool.call` do próprio teste, ou o texto do erro. */
const why = (r: { deny?: string; text?: string; isError?: boolean }) => r.deny ?? (r.isError ? (r.text ?? '') : '')

const START = (id: string) => ({ cwd: `C:/wt/${id}/repo`, surface: 'terminal' as const, isInteractive: true })
const delegation = (over: { subagent_type?: string; level?: string } = {}) => ({
  tool: 'Agent' as const,
  description: 'Codificar rota',
  subagent_type: over.subagent_type ?? 'aidw:codificador',
  prompt: `Tarefa: ${STATE}/us-1/tarefa-codificador-rota.md. Pasta da demanda: ${STATE}/us-1. Nível: ${over.level ?? 'padrao'}.`,
})

test('desenvolvimento: a delegação vira métrica, a faixa e o painel mostram a demanda', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'us-1' })
  await $.session.start(START('us-1'))

  // a demanda está na rodada 4 de 3: o codificador está travado até o Felipe liberar
  const blocked = await $.tool.call(delegation())
  expect(why(blocked)).toContain('Liberar +1 rodada')
  expect(f.runs).toEqual([])
  const extra = { command: 'aidw-rodada', args: '' } as never
  await $.command.run(extra)
  await $.command.run(extra)

  const ran = await $.tool.call(delegation())
  expect(f.runs.length).toBe(1)
  const argv = f.runs[0] ?? []
  expect(argv.slice(1, 3)).toEqual(['C:/AiDW/aidw.py', 'record'])
  for (const [flag, value] of [['--agent', 'aidw:codificador'], ['--label', 'rota'], ['--tokens', '1000'], ['--state', 'implementation_complete']] as const) {
    expect(argv[argv.indexOf(flag) + 1]).toBe(value)
  }
  expect((ran.context ?? []).join('\n')).toContain('## Codificador - claude-opus Medium')

  for (const surface of ['terminal', 'desktop'] as const) {
    // faixa V2: demanda, contexto, 7d e 5h (amarelo a partir de 80%, com a hora de renovar)
    const band = await $.ui.mount({ plugin: 'aidw-mods', surface, component: 'AbovePrompt', props: PROPS_BAND })
    await has(band, /^us-1$/)
    await has(band, /contexto/)
    await has(band, /^58%$/)
    await has(band, /91% \(renova 16:40\)/)
    expect(await band.find({ type: 'Text', text: /orçamento/ })).toBeUndefined()
    await band.unmount()

    const pane = await $.ui.mount({ plugin: 'aidw-mods', surface, component: 'Pane', requestId: 'aidw', props: PROPS_PANE })
    for (const key of ['tab-geral', 'tab-criterios', 'tab-revisao', 'tab-diffs', 'tab-manual', 'tab-metricas']) {
      expect(await pane.find({ key })).toBeDefined()
    }
    // Geral: título, mapa (critérios, tokens, tempo, etapa) e o último agente
    await has(pane, /^Rota fast$/)
    await has(pane, /etapa 5 de 9/)
    await has(pane, /^117k$/)
    await has(pane, /último: codificador \(rota\), concluído/)
    await pane.press({ key: 'tab-metricas' })
    await has(pane, /^opus · medium$/)
    await has(pane, /arquivos na pasta da demanda/)
    await pane.press({ key: 'tab-criterios' })
    await has(pane, /^abre a rota$/)
    await has(pane, /A cobertura ainda não foi registrada/)
    // Revisão: rodada como seletor, abas de decisão; decidir leva ao prompt
    await pane.press({ key: 'tab-revisao' })
    await pane.select({ key: 'review-round', value: 'review-us-1-r4.md' })
    await pane.press({ key: 'dt-mantido' })
    await has(pane, /quebra o login/)
    await pane.select({ key: 'review-round', value: 'review-us-1-r1.md' })
    await pane.press({ key: 'dt-voce' })
    await has(pane, /nome ruim/)
    await pane.press({ key: 'dec-R1-01-0' })
    await pane.press({ key: 'review-send' })
    expect(f.fills.at(-1)).toContain('R1-01 (Código r1): mantido')
    await pane.press({ key: 'tab-manual' })
    await pane.input({ key: 'evidencia-T2', text: 'mensagem apareceu', kind: 'change' })
    await pane.press({ key: 'manual-ok' })
    expect(f.submits.at(-1)).toContain('passo T2: ✅ passou — evidência: mensagem apareceu')
    await pane.press({ key: 'tab-geral' })
    await pane.unmount()
  }
})

test('sessão fora da pasta da demanda: acha a demanda pelo argumento do /aidw:orquestrar', async ($, on) => {
  fake(on, { orchestrating: true, demand: 'us-1', argument: 'us-1', cwd: 'C:/AiDW/contexts/x' })
  await $.session.start({ ...START('us-1'), cwd: 'C:/AiDW/contexts/x' })
  const pane = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'Pane', requestId: 'aidw', props: PROPS_PANE })
  await has(pane, /^Rota fast$/)
  await pane.unmount()
})

test('travas: célula errada da tabela e model sem pedido são recusados', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'us-1' })
  await $.session.start(START('us-1'))
  const wrong = await $.tool.call(delegation({ subagent_type: 'aidw:codificador-high' }))
  expect(why(wrong)).toContain('é `codificador`')
  const model = await $.tool.call({ ...delegation(), model: 'sonnet' })
  expect(why(model)).toContain('não passe `model`')
  expect(f.runs).toEqual([])
})

test('revisão de PR: achados, voto e a decisão vai para o prompt', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'pr-7' })
  await $.session.start(START('pr-7'))
  const pane = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'Pane', requestId: 'aidw', props: PROPS_PANE })
  expect(await pane.find({ key: 'tab-achados' })).toBeDefined()
  expect(await pane.find({ key: 'tab-criterios' })).toBeUndefined()
  await pane.press({ key: 'tab-achados' })
  await has(pane, /^Isto quebra o contrato\.$/)
  await has(pane, /Comentário na PR 7/)
  await pane.press({ key: 'pa-R1-01' })
  expect(f.fills.at(-1)).toContain('Ajuste o comentário do achado R1-01')
  await pane.press({ key: 'pp-R1-01' })
  await pane.press({ key: 'pp-R1-02' })
  expect(await pane.find({ key: 'pt-publicar' })).toBeDefined()
  await pane.press({ key: 'vote-approve_with_suggestions' })
  await pane.press({ key: 'pr-decision' })
  expect(f.fills.at(-1)).toContain('Publicar: R1-01, R1-02')
  expect(f.fills.at(-1)).toContain('Voto: Aprovar com sugestões (5)')
  await pane.press({ key: 'tab-diffs' })
  await pane.select({ key: 'diff-source', value: 'patch:diff-pr7-Hope.patch' })
  await has(pane, /1 arquivo · \+1 −1/)
  await pane.unmount()
})

test('levantamento: pontos, estimativa e dúvidas', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'lv-9' })
  await $.session.start(START('lv-9'))
  const pane = await $.ui.mount({ plugin: 'aidw-mods', surface: 'desktop', component: 'Pane', requestId: 'aidw', props: PROPS_PANE })
  await pane.press({ key: 'tab-codigo' })
  await has(pane, /^aceitar CPF$/)
  await pane.press({ key: 'tab-estimativa' })
  await has(pane, /^5$/)
  await pane.input({ key: 'duvida-D1', text: 'Só PF', kind: 'change' })
  await pane.input({ key: 'duvida-D1', text: 'Só PF' })
  expect(f.submits.at(-1)).toContain('Resposta à dúvida D1 do levantamento lv-9: Só PF')
  await pane.press({ key: 'post-levantamento' })
  expect(f.fills.at(-1)).toContain('publique no card lv-9')
  await pane.unmount()
})

test('fora do modo orquestrador, o mod não trava, não grava nem mostra nada', async ($, on) => {
  const f = fake(on, { orchestrating: false, demand: 'us-1' })
  await $.session.start(START('us-1'))
  const ran = await $.tool.call(delegation({ subagent_type: 'aidw:codificador-high' }))
  expect(why(ran)).toBe('')
  expect(f.runs).toEqual([])
  await expect($.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'AbovePrompt', props: PROPS_BAND }))
    .rejects.toThrow(/no implementation for ui.render/)
})

test('um Agent fora do AiDW passa direto', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'us-1' })
  await $.session.start(START('us-1'))
  const ran = await $.tool.call({ tool: 'Agent', description: 'x', prompt: 'Find the config loader' })
  expect(f.runs).toEqual([])
  expect(ran.context ?? []).toEqual([])
})

test('filtro de segredos nas linhas da conversa', async ($, on) => {
  fake(on, { orchestrating: true, demand: 'us-1' })
  const rows: unknown[] = []
  on('ui.status', () => ({ value: undefined }))
  // o hook do teste fica abaixo do mod: vê a linha já filtrada (no kit não há nada abaixo para gravá-la)
  on('session.append', ($, e, next) => {
    rows.push(e.message.content)
    return next(e)
  })
  await $.session.start(START('us-1'))
  const row0 = { message: { type: 'user', content: [{ type: 'text', text: 'Server=a;Password=SuperSecreta1;' }] } }
  await $.session.append(row0 as never).catch(() => undefined)
  const row = JSON.stringify(rows.at(-1))
  expect(row).not.toContain('SuperSecreta1')
  expect(row).toContain('segredo ocultado: Password, 13 caracteres')
})
