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
  variants: {
    planejador: ['planejador', 'planejador-medium'],
    codificador: ['codificador', 'codificador-medium'],
    revisor: ['revisor', 'revisor-medium', 'revisor-low'],
  },
  agents: {
    orchestrator: { name: 'orchestrator', enabled: true },
    planner: { name: 'planejador', enabled: true },
    coder: { name: 'codificador', display: 'Codificador', enabled: true, model: 'opus', effort: 'medium' },
    reviewer: { name: 'revisor', enabled: true },
  },
}

/** The three sample demands, one per kind. */
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
      repos: [{ repo: 'C:/p/App', path: 'C:/wt/pr-7/App', branch: 'pr/7', base: 'abc', pr: '7', source: 'def' }],
    }),
    'diff-pr7-App-r2.patch': 'diff --git a/x.cs b/x.cs\n--- a/x.cs\n+++ b/x.cs\n@@ -1 +1 @@\n-a\n+b\n',
    'review-pr-7-r1.md': [
      '### R1-01 — IMPORTANTE — `x.cs:1`', '**O quê:** troca o contrato', '**Rascunho do comentário de PR (7):**', '> Isto quebra o contrato.', '',
      '### R1-02 — SUGESTAO — `x.cs:2`', '**O quê:** nome', '', 'Voto sugerido: aguardar autor (`-5`).',
    ].join('\n'),
  },
  'pr-8': {
    'demand.json': JSON.stringify({
      id: 'pr-8', step: 'FINAL_REVIEW',
      repos: [
        { repo: 'C:/p/Portal', path: 'C:/wt/pr-8/Portal', branch: 'pr/8', base: 'a', pr: '8', source: 'b' },
        { repo: 'C:/p/Api', path: 'C:/wt/pr-8/Api', branch: 'pr/9', base: 'a', pr: '9', source: 'b' },
      ],
    }),
    'review-pr-8-r1.md': '### R1-01 — IMPORTANTE — `a.cs:1`\n**O quê:** trava a tela\n',
    'triagem-pr-8-r2.md': [
      '# Triagem — pr-8, rodada 2', '', '## Comentários', '',
      '| C | PR | Sev. | Arquivo:linha | Origem | Recomendação | Situação |', '|---|---|---|---|---|---|---|',
      '| C1 | 8 | IMPORTANTE | `a.cs:1` | R1-01, B1-01 | publicar | publicado (thread 1), resolvido na r2 |',
      '| C2 | 8 | DUVIDA | geral | R1-D1 | publicar como pergunta | a decidir |',
      '| C3 | 9 | SUGESTAO | `b.cs:2` | R1-04 | não publicar | não publicado (r1) |', '',
      '### C1 — chamada síncrona na thread de UI', '> Tire o `Get` da thread de UI.', '',
      '### C2 — a modal reaparece a cada recarga', '> A modal deve reaparecer a cada recarga?', '',
      '### C3 — log duplicado', '> Um log só basta.', '',
      '## Votos', '', '| PR | Revisor | AiDW | Por quê |', '|---|---|---|---|', '| 8 | 5 | 10 | C1 resolvido |', '| 9 | 5 | sem voto | só o C3 |', '',
      '## Fora das PRs', '', '- **S1-01 (Tech Lead):** filtro por solicitação.', '',
      '## Publicado', '', '- C1: PR 8, thread 1.',
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
  // the same development demand written with the new English file names and headings
  'us-2': {
    'demand.json': JSON.stringify({
      id: 'us-2', title: 'Fast route', step: 'CODER_FIX',
      history: [{ step: 'UNDERSTAND', at: '' }, { step: 'IMPLEMENT', at: '' }, { step: 'REVIEW', at: '' }, { step: 'CODER_FIX', at: '' }],
      repos: [{ repo: 'C:/p/Front', path: 'C:/wt/us-2/Front', branch: 'feature/2-route', base: 'origin/dev' }],
    }),
    'metrics.md': METRICAS,
    'plan-us-2.md': '# Execution plan v2\nLevel: padrao — one system\n\n## Acceptance criteria\n- [ ] CA1: opens the route\n- [ ] CA2: shows the error\n',
    'test-plan-us-2.md': '## Coverage matrix\n| CA | Scenario | Steps | Expected | Evidence | Type |\n|---|---|---|---|---|---|\n| CA1 | T1 | a | b | c | auto-browser |\n| CA2 | T2 | a | b | c | manual |\n',
    'test-script-us-2.md': '| # | Step | Expected | Result |\n|---|---|---|---|\n| T1 | open the route | screen opens | ✅ ok |\n| T2 | force an error | message | |\n',
    'review-us-2-r1.md': '### R1-01 — IMPORTANT — `src/a.ts:10`\n**What:** bad name\n**Recommendation:** rename it\n',
    'triage-us-2-r1.md': '| ID | Decision | Reason |\n|---|---|---|\n| R1-01 | keep | clearer |\n',
  },
}

const norm = (path: string) => path.replace(/\\/g, '/')
const PROPS_BAND = { hasSurvey: false, isWorking: false, maxRows: 4, bodyColumns: 160, scroll: { offset: 0, bodyRows: 4 }, view: {} }
const PROPS_PANE = { title: 'AiDW', isFocused: true, bodyColumns: 160, placement: 'dock' as const, scroll: { offset: 0, bodyRows: 40 }, view: {} }

type Fake = {
  runs: (readonly string[])[]; fills: string[]; submits: string[]; contexts: string[]; toasts: string[]; opens: number; clock: ReturnType<typeof mock.clock>
  files: Record<string, string>
}

/** The fake disk, AiDW and engine; `demand` is the folder where the session opens. `panel: false` is a context without the panel. */
function fake(
  on: On,
  opts: { orchestrating: boolean; demand: string; folder?: string; cwd?: string; contextTokens?: number; panel?: boolean; background?: boolean; toolText?: string; toolError?: string; stdoutPrefix?: string; language?: string | null },
): Fake {
  const files: Record<string, string> = {
    'C:/AiDW/.aidw/runtime.json': JSON.stringify({ ...RUNTIME, panel: opts.panel ?? true }),
    // the UI language of aidw.config.toml: these tests keep the old Portuguese strings; `language: null` = no config (English)
    ...(opts.language === null ? {} : { 'C:/AiDW/aidw.config.toml': `[ui]\nlanguage = "${opts.language ?? 'pt-BR'}"\n` }),
    'C:/AiDW/state/sessions.json': JSON.stringify(
      opts.orchestrating ? { [SESSION]: { plugin: 'aidw', argument: '', ...(opts.folder ? { folder: opts.folder } : {}) } } : {},
    ),
  }
  for (const [id, entries] of Object.entries(DEMANDS)) {
    for (const [name, text] of Object.entries(entries)) files[`${STATE}/${id}/${name}`] = text
  }
  const out: Fake = { runs: [], fills: [], submits: [], contexts: [], toasts: [], opens: 0, clock: mock.clock(on), files }
  on('ui.toast', ($, e) => {
    out.toasts.push(e.text)
    return { value: undefined }
  })
  on('turn.complete', ($, e) => ({ text: e.answer }))
  on('session.measure', ($, e) => ({ changed: [...e.changed] }))
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('command.register', ($, e) => ({ value: { command: e.name } }))
  on('session.id', () => ({ value: SESSION }))
  on('session.cwd', () => ({ value: opts.cwd ?? `C:/wt/${opts.demand}/repo` }))
  on('session.usage', () => ({
    value: {
      startedAt: 0,
      context: { percent: 41, tokens: opts.contextTokens ?? 82_000 },
      rateLimits: [
        { kind: 'seven_day', percentUsed: 58 },
        { kind: 'five_hour', percentUsed: 91, resetsAt: '2026-10-14T16:40:00Z' },
      ],
    } as never,
  }))
  on('ui.open', () => {
    out.opens += 1
    return { value: { isPlaced: true } }
  })
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
        name, kind: rest.includes(name) ? ('file' as const) : ('dir' as const), size: files[`${dir}${name}`]?.length ?? 1, mtimeMs: 0, isLink: false,
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
    out.contexts.push((e.context ?? []).join('\n'))
    return { text: e.text }
  })
  on('process.run', ($, e) => {
    out.runs.push(e.argv)
    const header = { header: '## Codificador - claude-opus Medium', resumo: 'Codificador (padrao) | 1.000 tokens' }
    return { value: { exitCode: 0, stdout: (opts.stdoutPrefix ?? '') + JSON.stringify(header), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('tool.call', ($, e) => opts.toolError !== undefined && e.tool !== 'Agent' ? { isError: true as const, result: opts.toolError, text: opts.toolError } : ({
    result: opts.background ? {
      status: 'async_launched', agentId: 'bg1', description: 'Revisar plano', prompt: e.tool === 'Agent' ? e.prompt : '', outputFile: 'C:/tmp/bg1.output',
    } : {
      status: 'completed', agentId: 'a1', prompt: 'p',
      content: [{ type: 'text', text: opts.toolText ?? 'feito\n{"state": "implementation_complete"}' }],
      totalTokens: 1000, totalToolUseCount: 5, totalDurationMs: 9000,
      usage: { input_tokens: 1, output_tokens: 1, cache_creation_input_tokens: 0, cache_read_input_tokens: 0, server_tool_use: null, service_tier: null, cache_creation: null },
    },
  }))
  return out
}

/** Finds a Text by the pattern or fails saying which (find returns undefined without saying what). */
async function has(view: { find: (q: { type: 'Text'; text: RegExp }) => Promise<unknown> }, text: RegExp): Promise<void> {
  if ((await view.find({ type: 'Text', text })) === undefined) throw new Error(`não desenhou ${text}`)
}

/** The reason of a refusal: `deny` for the test's own `$.tool.call`, or the error text. */
const why = (r: { deny?: string; text?: string; isError?: boolean }) => r.deny ?? (r.isError ? (r.text ?? '') : '')

const START = (id: string) => ({ cwd: `C:/wt/${id}/repo`, surface: 'terminal' as const, isInteractive: true })
const delegation = (over: { subagent_type?: string } = {}) => ({
  tool: 'Agent' as const,
  description: 'Codificar rota',
  subagent_type: over.subagent_type ?? 'aidw:codificador',
  prompt: `Tarefa: ${STATE}/us-1/tarefa-codificador-rota.md. Pasta da demanda: ${STATE}/us-1.`,
})

test('desenvolvimento: a delegação vira métrica, a faixa e o painel mostram a demanda', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'us-1' })
  await $.session.start(START('us-1'))
  expect(f.opens).toBe(0) // panel v4: nothing opens by itself

  // the demand is at round 4: no round limit, the coder runs (panel v4)
  const ran = await $.tool.call(delegation())
  expect(f.runs.length).toBe(1)
  const argv = f.runs[0] ?? []
  expect(argv.slice(1, 3)).toEqual(['C:/AiDW/aidw.py', 'record'])
  for (const [flag, value] of [['--agent', 'aidw:codificador'], ['--label', 'rota'], ['--tokens', '1000'], ['--state', 'implementation_complete']] as const) {
    expect(argv[argv.indexOf(flag) + 1]).toBe(value)
  }
  expect((ran.context ?? []).join('\n')).toContain('## Codificador - claude-opus Medium')

  for (const surface of ['terminal', 'desktop'] as const) {
    // strip V2: demand, context, 7d and 5h (yellow from 75%, red from 90%, with the reset time)
    const band = await $.ui.mount({ plugin: 'aidw-mods', surface, component: 'AbovePrompt', props: PROPS_BAND })
    await has(band, /^us-1$/)
    await has(band, /contexto/)
    await has(band, /^41% · 82k$/) // the context in % of the real window, with the tokens
    await has(band, /^58%$/)
    // the time is local (resetsAt comes in UTC), with the day in front when it is not today
    const reset = new Date('2026-10-14T16:40:00Z')
    const hm = `${String(reset.getHours()).padStart(2, '0')}:${String(reset.getMinutes()).padStart(2, '0')}`
    await has(band, new RegExp(`91% · renova (\\d\\d/\\d\\d )?${hm}`))
    expect(await band.find({ type: 'Text', text: /orçamento/ })).toBeUndefined()
    expect(await band.find({ type: 'Text', text: /espera você/ })).toBeUndefined() // CODER_FIX: it is the agent's turn
    // the panel buttons: a click opens the panel
    expect(await band.find({ key: 'open-general' })).toBeDefined()
    expect(await band.find({ key: 'open-metrics' })).toBeDefined()
    const opened = f.opens
    await band.press({ key: 'open-decide' })
    expect(f.opens).toBe(opened + 1)
    await band.unmount()

    // General: a single page, no tabs — title, map (step) and the criteria block; no agents, links or tokens
    const general = await $.ui.mount({ plugin: 'aidw-mods', surface, component: 'Pane', requestId: 'aidw-general', props: PROPS_PANE })
    expect(await general.find({ key: 'tab-criteria' })).toBeUndefined()
    expect(await general.find({ key: 'tab-diffs' })).toBeUndefined()
    await has(general, /^Rota fast$/)
    await has(general, /etapa 5 de 11/)
    await has(general, /^abre a rota$/)
    expect(await general.find({ type: 'Text', text: /Ainda não há plano/ })).toBeUndefined()
    expect(await general.find({ type: 'Text', text: /último: codificador/ })).toBeUndefined()
    expect(await general.find({ type: 'Text', text: /^117k$/ })).toBeUndefined()
    await general.unmount()

    // Metrics: the usage, without the delegation list or the artifact list
    const metrics = await $.ui.mount({ plugin: 'aidw-mods', surface, component: 'Pane', requestId: 'aidw-metrics', props: PROPS_PANE })
    await has(metrics, /^opus · medium$/)
    await has(metrics, /^117k$/)
    expect(await metrics.find({ type: 'Text', text: /arquivos na pasta da demanda/ })).toBeUndefined()
    await metrics.unmount()

    // Decisions: round as a selector, decision tabs
    const decide = await $.ui.mount({ plugin: 'aidw-mods', surface, component: 'Pane', requestId: 'aidw-decide', props: PROPS_PANE })
    await decide.press({ key: 'tab-review' })
    await decide.press({ key: 'review-round-review-us-1-r4.md' })
    await decide.press({ key: 'dt-kept' })
    await has(decide, /quebra o login/)
    await decide.press({ key: 'review-round-review-us-1-r1.md' })
    await decide.press({ key: 'dt-with-you' })
    await has(decide, /nome ruim/)
    // only informs: no deciding and nothing sent to the prompt; the decision is in the chat
    expect(await decide.find({ key: 'dec-R1-01-0' })).toBeUndefined()
    expect(await decide.find({ key: 'review-send' })).toBeUndefined()
    await has(decide, /^ a decidir $/)
    await decide.press({ key: 'tab-manual' })
    await has(decide, /^Próximo · T2$/)
    expect(await decide.find({ key: 'manual-ok' })).toBeUndefined()
    expect(await decide.find({ key: 'evidencia-T2' })).toBeUndefined()
    await decide.unmount()
  }

  // /panel with a tab opens its panel
  const before = f.opens
  expect(JSON.stringify(await $.command.run({ command: 'panel', args: 'revisao' } as never))).toContain('painel Testes e Review aberto')
  expect(JSON.stringify(await $.command.run({ command: 'metrics', args: '' } as never))).toContain('Métricas aberto')
  expect(f.opens).toBe(before + 2)
})

test('sessão fora da pasta da demanda: acha a demanda pela pasta do registro da sessão', async ($, on) => {
  fake(on, { orchestrating: true, demand: 'us-1', folder: `${STATE}/us-1`, cwd: 'C:/AiDW/contexts/x' })
  await $.session.start({ ...START('us-1'), cwd: 'C:/AiDW/contexts/x' })
  const pane = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'Pane', requestId: 'aidw-general', props: PROPS_PANE })
  await has(pane, /^Rota fast$/)
  await pane.unmount()
})

test('o registro da sessão muda de demanda: o mod segue a pasta nova', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'us-1', folder: `${STATE}/us-1`, cwd: 'C:/AiDW/contexts/x' })
  await $.session.start({ ...START('us-1'), cwd: 'C:/AiDW/contexts/x' })
  f.files['C:/AiDW/state/sessions.json'] = JSON.stringify({ [SESSION]: { plugin: 'aidw', folder: `${STATE}/pr-7` } })
  await $.prompt.submit({ text: 'segue', origin: { kind: 'composer' } } as never)
  const band = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'AbovePrompt', props: PROPS_BAND })
  await has(band, /^pr-7$/)
  await band.unmount()
})

test('travas: variante fora da tabela e model sem pedido são recusados', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'us-1' })
  await $.session.start(START('us-1'))
  const wrong = await $.tool.call(delegation({ subagent_type: 'aidw:codificador-high' }))
  expect(why(wrong)).toContain('não está na tabela Agents and effort')
  const model = await $.tool.call({ ...delegation(), model: 'sonnet' })
  expect(why(model)).toContain('não passe `model`')
  expect(f.runs).toEqual([])
})

test('revisão de PR: os achados só informam', async ($, on) => {
  fake(on, { orchestrating: true, demand: 'pr-7' })
  await $.session.start(START('pr-7'))
  // FINAL_REVIEW waits for you: the strip says so
  const band = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'AbovePrompt', props: PROPS_BAND })
  await has(band, /^● espera você$/)
  await band.unmount()
  // in a PR review, Tests and Review only has the comments: it opens on them, with no tab row
  const pane = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'Pane', requestId: 'aidw-decide', props: PROPS_PANE })
  expect(await pane.find({ key: 'tab-comments' })).toBeUndefined()
  await has(pane, /^Isto quebra o contrato\.$/)
  await has(pane, /Comentário na PR 7/)
  for (const key of ['pa-R1-01', 'pp-R1-01', 'pr-decision', 'ap-unica-sim']) expect(await pane.find({ key })).toBeUndefined()
  await pane.unmount()
})

test('revisão de PR com triagem: comentários por PR, só informativos', async ($, on) => {
  fake(on, { orchestrating: true, demand: 'pr-8' })
  await $.session.start(START('pr-8'))
  const pane = await $.ui.mount({ plugin: 'aidw-mods', surface: 'desktop', component: 'Pane', requestId: 'aidw-decide', props: PROPS_PANE })
  // opens on "To decide": only C2; the published one shows under All, with the round 2 situation
  await has(pane, /^a modal reaparece a cada recarga$/)
  expect(await pane.find({ type: 'Text', text: /resolvido na r2/ })).toBeUndefined()
  await pane.press({ key: 'pt-all' })
  await has(pane, /^publicado \(thread 1\), resolvido na r2$/)
  await has(pane, /^junta R1-01 · B1-01$/)
  // publishing and approving the PR are decided in the chat
  expect(await pane.find({ type: 'Text', text: /^Aprovar a PR/ })).toBeUndefined()
  for (const key of ['pp-C2', 'ap-8-sim', 'pr-decision']) expect(await pane.find({ key })).toBeUndefined()
  await pane.unmount()
})

test('levantamento: pontos, estimativa e dúvidas', async ($, on) => {
  fake(on, { orchestrating: true, demand: 'lv-9' })
  await $.session.start(START('lv-9'))
  const pane = await $.ui.mount({ plugin: 'aidw-mods', surface: 'desktop', component: 'Pane', requestId: 'aidw-general', props: PROPS_PANE })
  // card × code and estimate are General blocks
  expect(await pane.find({ key: 'tab-code' })).toBeUndefined()
  await has(pane, /^aceitar CPF$/)
  await has(pane, /^5$/)
  expect(await pane.find({ key: 'post-levantamento' })).toBeUndefined()
  await pane.unmount()
  // in a survey the panel is the Questions one: it only informs, the answer is in the chat
  const band = await $.ui.mount({ plugin: 'aidw-mods', surface: 'desktop', component: 'AbovePrompt', props: PROPS_BAND })
  await has(band, /^Dúvidas/)
  await band.unmount()
  expect(JSON.stringify(await $.command.run({ command: 'review-tests', args: '' } as never))).toContain('painel Dúvidas aberto')
  const questions = await $.ui.mount({ plugin: 'aidw-mods', surface: 'desktop', component: 'Pane', requestId: 'aidw-decide', props: PROPS_PANE })
  await has(questions, /^Vale para PJ\?$/)
  expect(await questions.find({ key: 'duvida-D1' })).toBeUndefined()
  await questions.unmount()
})

test('contexto sem painel: a faixa aparece, o painel não abre e /painel explica', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'us-1', panel: false })
  await $.session.start(START('us-1'))
  expect(f.opens).toBe(0)
  const band = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'AbovePrompt', props: PROPS_BAND })
  await has(band, /^us-1$/)
  await has(band, /^41% · 82k$/)
  expect(await band.find({ key: 'open-general' })).toBeUndefined() // no panel, no buttons
  await band.unmount()
  const r = await $.command.run({ command: 'panel', args: '' } as never)
  expect(JSON.stringify(r)).toContain('painel está desligado')
  expect(f.opens).toBe(0)
  // the locks remain: a variant outside the table is refused
  expect(why(await $.tool.call(delegation({ subagent_type: 'aidw:codificador-high' })))).toContain('não está na tabela')
})

test('fora do modo orquestrador, o mod não trava, não grava nem mostra nada', async ($, on) => {
  const f = fake(on, { orchestrating: false, demand: 'us-1' })
  await $.session.start(START('us-1'))
  const ran = await $.tool.call(delegation({ subagent_type: 'aidw:codificador-high' }))
  expect(why(ran)).toBe('')
  expect(f.runs).toEqual([])
  // the band hands the render to `next`: nothing of the AiDW is drawn (the harness's own default may draw, or throw
  // "no implementation for ui.render" in older Claude Code versions)
  const band = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'AbovePrompt', props: PROPS_BAND })
    .catch((err: Error) => {
      expect(err.message).toMatch(/no implementation for ui.render/)
      return null
    })
  if (band) {
    expect(await band.find({ type: 'Text', text: /^us-1$/ })).toBeUndefined()
    expect(await band.find({ type: 'Text', text: /contexto/ })).toBeUndefined()
    expect(await band.find({ key: 'open-general' })).toBeUndefined()
    await band.unmount()
  }
})

test('um Agent fora do AiDW passa direto', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'us-1' })
  await $.session.start(START('us-1'))
  const ran = await $.tool.call({ tool: 'Agent', description: 'x', prompt: 'Find the config loader' })
  expect(f.runs).toEqual([])
  expect(ran.context ?? []).toEqual([])
})

const TURN = (cacheRead: number) => ({
  answer: 'ok', durationMs: 5_000, isAborted: false, turnId: 't1', reason: 'answer' as const,
  usage: { model: 'claude-opus-5-5', input_tokens: 3, output_tokens: 700, cache_read_input_tokens: cacheRead, cache_creation_input_tokens: 10_000 },
})

const IDLE = 50 * 60_000

test('fim de turno parado: grava o turno do orquestrador e compacta uma vez depois de 50 min', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'pr-7', contextTokens: 300_000 })
  const compactions: string[] = []
  on('session.compact', ($, e) => {
    compactions.push(e.instructions ?? '')
    return { messages: [{ role: 'user', text: 'resumo da conversa', toolUses: [] }] as never, tokensBefore: 300_000, tokensAfter: 40_000 }
  })
  await $.session.start(START('pr-7'))
  await $.turn.complete(TURN(290_000))
  const rec = f.runs.find(a => a.includes('record-orchestrator')) ?? []
  for (const [flag, value] of [['--demand', `${STATE}/pr-7`], ['--session', SESSION], ['--model', 'claude-opus-5-5'], ['--cache-read', '290000'], ['--cache-write', '10000'], ['--output', '700'], ['--step', 'FINAL_REVIEW']] as const) {
    expect(rec[rec.indexOf(flag) + 1]).toBe(value)
  }
  await f.clock.advance(IDLE - 1_000)
  expect(compactions).toEqual([]) // the time has not passed yet
  await f.clock.advance(1_000)
  expect(compactions.length).toBe(1)
  expect(compactions[0]).toContain('FINAL_REVIEW')
  expect(f.toasts).toEqual([]) // compacts silently: no notice
  await f.clock.advance(IDLE)
  expect(compactions.length).toBe(1) // only once per pause
})

test('mensagem nova antes dos 50 min: não compacta', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'us-1', contextTokens: 300_000 })
  const compactions: string[] = []
  on('session.compact', ($, e) => {
    compactions.push(e.instructions ?? '')
    return { messages: [] }
  })
  await $.session.start(START('us-1'))
  await $.turn.complete(TURN(290_000))
  await f.clock.advance(IDLE / 2)
  await $.prompt.submit({ text: 'segue', origin: { kind: 'composer' } } as never)
  await f.clock.advance(IDLE)
  expect(compactions).toEqual([])
})

test('contexto pequeno parado: não compacta', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'us-1', contextTokens: 60_000 })
  const compactions: string[] = []
  on('session.compact', ($, e) => {
    compactions.push(e.instructions ?? '')
    return { messages: [] }
  })
  await $.session.start(START('us-1'))
  await $.turn.complete(TURN(55_000))
  await f.clock.advance(IDLE)
  expect(compactions).toEqual([])
})

test('agente em segundo plano: grava o contexto da última resposta, não a soma do turno', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'us-1', background: true })
  // three subagent answers; the cache read grows with each one (real case of m-144245: plan reviewer r1)
  const steps = [
    { input_tokens: 3, cache_creation_input_tokens: 10_000, cache_read_input_tokens: 20_000, output_tokens: 500 },
    { input_tokens: 2, cache_creation_input_tokens: 5_000, cache_read_input_tokens: 120_000, output_tokens: 800 },
    { input_tokens: 1, cache_creation_input_tokens: 1_500, cache_read_input_tokens: 240_000, output_tokens: 596 },
  ]
  on('turn.step', async function* ($, e) {
    return { turnId: e.turnId, index: e.index, answer: '', toolUses: [], stopReason: 'tool_use' as const, usage: { model: 'claude-sonnet-5-5', ...steps[e.index]! } }
  })
  const read = { tool_use_id: 'r', tool: 'Read', input: {} }
  on('session.messages', ($, e) => ({
    value: e.agentId === 'bg1'
      ? [
          { role: 'user' as const, text: 'Tarefa', toolUses: [] },
          { role: 'assistant' as const, text: '', toolUses: [read, read] },
          { role: 'assistant' as const, text: '', toolUses: [read] },
          { role: 'assistant' as const, text: 'pronto', toolUses: [] },
        ]
      : [],
  }))
  const rows: string[] = []
  on('session.append', ($, e, next) => {
    rows.push(JSON.stringify(e.message.content))
    return next(e)
  })
  await $.session.start(START('us-1'))
  await $.tool.call(delegation()) // the Agent answers async_launched (fake with background)
  expect(f.runs).toEqual([]) // only records when the agent ends

  for (const [index] of steps.entries()) {
    const stream = $.turn.step({ turnId: 'bt', index, model: 'claude-sonnet-5-5', messageCount: 1 + index, agentId: 'bg1' })
    for await (const _ of stream) void _
    await stream.result
  }
  // the strip shows the agent as a card: name, model and effort, label and the tokens of the last answer
  const band = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'AbovePrompt', props: PROPS_BAND })
  await has(band, /^Codificador$/)
  await has(band, /^Opus medium$/)
  await has(band, /^rota$/)
  await has(band, /^242k tokens$/)
  await band.unmount()
  const sum = steps.reduce((n, u) => n + u.input_tokens + u.cache_creation_input_tokens + u.cache_read_input_tokens + u.output_tokens, 0)
  await $.turn.complete({
    answer: 'pronto\n{"state": "plan_review_changes_requested"}', durationMs: 508_448, isAborted: false, turnId: 'bt', reason: 'answer',
    agentId: 'bg1', usage: { model: 'claude-sonnet-5-5', input_tokens: 6, output_tokens: 1_896, cache_read_input_tokens: 380_000, cache_creation_input_tokens: 16_500 },
  })
  expect(f.runs.length).toBe(1)
  const argv = f.runs[0] ?? []
  for (const [flag, value] of [
    ['--agent', 'aidw:codificador'], ['--label', 'rota'], ['--tokens', '242097'], ['--tool-uses', '3'],
    ['--duration-ms', '508448'], ['--state', 'plan_review_changes_requested'],
    // the US$ cost: the sum of the three subagent answers, at their model
    ['--usage-model', 'claude-sonnet-5-5'], ['--input', '6'], ['--cache-write', '16500'], ['--cache-read', '380000'],
    ['--output', '1896'],
  ] as const) {
    expect(argv[argv.indexOf(flag) + 1]).toBe(value)
  }
  expect(argv).not.toContain(String(sum))
  expect(rows.some(r => r.includes('delegação registrada') && r.includes('## Codificador - claude-opus Medium'))).toBe(true)

  // the same agent resumed (SendMessage) does not record again
  await $.turn.complete({ answer: 'ok', durationMs: 1_000, isAborted: false, turnId: 'bt2', reason: 'answer', agentId: 'bg1' })
  expect(f.runs.length).toBe(1)
})

test('filtro de segredos no resultado das ferramentas (o session.append pode não chegar: plugin da organização acima)', async ($, on) => {
  fake(on, { orchestrating: true, demand: 'pr-7', toolText: 'appsettings: Server=a;Password=SuperSecreta1;' })
  on('ui.status', () => ({ value: undefined }))
  await $.session.start(START('pr-7'))
  const ran = await $.tool.call({ tool: 'Bash', command: 'type appsettings.json' } as never)
  const out = JSON.stringify(ran)
  expect(out).not.toContain('SuperSecreta1')
  expect(out).toContain('segredo ocultado: Password, 13 caracteres')
})

test('filtro de segredos também no resultado com erro: volta como erro, filtrado', async ($, on) => {
  fake(on, { orchestrating: true, demand: 'pr-7', toolError: 'Exception: Server=a;Pass' + 'word=SuperSecreta1;' })
  on('ui.status', () => ({ value: undefined }))
  await $.session.start(START('pr-7'))
  const ran = await $.tool.call({ tool: 'Bash', command: 'dotnet run' } as never)
  const out = JSON.stringify(ran)
  expect(out).not.toContain('SuperSecreta1')
  expect(ran.deny).toContain('segredo ocultado: Password, 13 caracteres')
})

test('record: um aviso antes do JSON não perde o header nem pede registro de novo', async ($, on) => {
  fake(on, { orchestrating: true, demand: 'us-1', stdoutPrefix: 'aviso: algo\n' })
  await $.session.start(START('us-1'))
  const ran = await $.tool.call(delegation())
  const context = (ran.context ?? []).join('\n')
  expect(context).toContain('## Codificador - claude-opus Medium')
  expect(context).not.toContain('não conseguiu registrar')
})

test('depois de uma compactação, o estado da demanda vai com a próxima mensagem', async ($, on) => {
  const opts = { orchestrating: true, demand: 'pr-7', contextTokens: 180_000 }
  const f = fake(on, opts)
  await $.session.start(START('pr-7'))
  const say = (text: string) => $.prompt.submit({ text, origin: { kind: 'composer' } } as never)
  await say('segue')
  expect(f.contexts.at(-1)).not.toContain('Pasta da demanda')
  // /compact (or the native one): the context drops below half, and the note goes once
  opts.contextTokens = 30_000
  await say('continua')
  expect(f.contexts.at(-1)).toContain('Pasta da demanda')
  await say('e agora?')
  expect(f.contexts.at(-1)).not.toContain('Pasta da demanda')
})

test('faixa ao vivo: o contexto anda a cada resposta do orquestrador e com o session.measure', async ($, on) => {
  const opts = { orchestrating: true, demand: 'us-1', contextTokens: 82_000 }
  fake(on, opts)
  on('turn.step', async function* ($, e) {
    return {
      turnId: e.turnId, index: e.index, answer: '', toolUses: [], stopReason: 'tool_use' as const,
      usage: { model: 'claude-opus-5-5', input_tokens: 1, cache_creation_input_tokens: 0, cache_read_input_tokens: 120_000, output_tokens: 10 },
    }
  })
  await $.session.start(START('us-1'))
  // a main chat answer mid-turn: the strip already shows the new context
  opts.contextTokens = 120_000
  const stream = $.turn.step({ turnId: 't', index: 0, model: 'claude-opus-5-5', messageCount: 1 })
  for await (const _ of stream) void _
  await stream.result
  let band = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'AbovePrompt', props: PROPS_BAND })
  await has(band, /^41% · 120k$/)
  await band.unmount()
  // the engine pushes the usage (a plan window went up one point): the strip follows without reading anything
  await $.session.measure({
    context: { window: 200_000, tokens: 150_000, percent: 75 },
    rateLimits: [{ kind: 'seven_day', percentUsed: 59 }, { kind: 'five_hour', percentUsed: 92, resetsAt: '2026-10-14T16:40:00Z' }],
    changed: ['context', 'rateLimits'],
  } as never)
  band = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'AbovePrompt', props: PROPS_BAND })
  await has(band, /^75% · 150k$/)
  await has(band, /^59%$/)
  await band.unmount()
})

test('faixa ao vivo: o Write de um agente e um arquivo mudado no disco relêem a demanda', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'us-1' })
  const DEMAND = `${STATE}/us-1/demand.json`
  const withStep = (step: string) => JSON.stringify({ ...JSON.parse(f.files[DEMAND] ?? '{}'), step })
  const waiting = async () => {
    const band = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'AbovePrompt', props: PROPS_BAND })
    const found = (await band.find({ type: 'Text', text: /espera você/ })) !== undefined
    await band.unmount()
    return found
  }
  await $.session.start(START('us-1'))
  expect(await waiting()).toBe(false) // CODER_FIX: it is the agent's turn

  // an agent writes in the demand folder: re-read right away
  f.files[DEMAND] = withStep('USER_REVIEW')
  await $.tool.call({ tool: 'Write', file_path: DEMAND, content: f.files[DEMAND] } as never)
  expect(await waiting()).toBe(true)

  // a Write outside the demand folder does not re-read
  f.files[DEMAND] = withStep('CODER_FIX')
  await $.tool.call({ tool: 'Write', file_path: 'C:/wt/us-1/repo/a.ts', content: 'x' } as never)
  expect(await waiting()).toBe(true)

  // the clock sees the file changed (outside the tools) and re-reads
  await f.clock.advance(5_000)
  expect(await waiting()).toBe(false)
})

test('language: without [ui] language the strip, the panel and the messages are in English', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'pr-7', language: null })
  await $.session.start(START('pr-7'))
  const band = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'AbovePrompt', props: PROPS_BAND })
  await has(band, /^context$/)
  await has(band, /^● waits for you$/)
  expect(await band.find({ type: 'Text', text: /espera você/ })).toBeUndefined()
  await band.unmount()
  expect(JSON.stringify(await $.command.run({ command: 'panel', args: 'comments' } as never))).toContain('Tests and Review panel opened')
  // the delegation lock speaks English too
  expect(why(await $.tool.call(delegation({ subagent_type: 'aidw:codificador-high' })))).toContain('is not in the Agents and effort table')
  expect(f.runs).toEqual([])
})

test('language: [ui] language = "pt" (any pt tag) gives pt-BR', async ($, on) => {
  fake(on, { orchestrating: true, demand: 'pr-7', language: 'pt' })
  await $.session.start(START('pr-7'))
  const band = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'AbovePrompt', props: PROPS_BAND })
  await has(band, /^● espera você$/)
  await band.unmount()
})

test('new English file names and headings: plan, metrics, review, triage and test script', async ($, on) => {
  fake(on, { orchestrating: true, demand: 'us-2', language: 'en' })
  await $.session.start(START('us-2'))
  // an English delegation prompt (`Task:` / `Demand folder:`) is recorded with the label from `task-<agent>-<topic>.md`
  const ran = await $.tool.call({
    tool: 'Agent', description: 'Code the route', subagent_type: 'aidw:codificador',
    prompt: `Task: ${STATE}/us-2/task-codificador-route.md. Demand folder: ${STATE}/us-2.`,
  })
  expect((ran.context ?? []).join('\n')).toContain('delegation recorded')
  const general = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'Pane', requestId: 'aidw-general', props: PROPS_PANE })
  await has(general, /^Fast route$/)
  await has(general, /^opens the route$/)
  await has(general, /step 5 of 11/)
  await general.unmount()
  const metrics = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'Pane', requestId: 'aidw-metrics', props: PROPS_PANE })
  await has(metrics, /^117k$/)
  await metrics.unmount()
  const decide = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'Pane', requestId: 'aidw-decide', props: PROPS_PANE })
  await decide.press({ key: 'tab-review' })
  await decide.press({ key: 'dt-kept' })
  await has(decide, /^bad name$/)
  await has(decide, /^Decision: kept$/)
  await decide.press({ key: 'tab-manual' })
  await has(decide, /^Next · T2$/)
  await decide.unmount()
})
