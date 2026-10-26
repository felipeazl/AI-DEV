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
  variants: {
    planejador: ['planejador', 'planejador-medium'],
    codificador: ['codificador', 'codificador-medium'],
    revisor: ['revisor', 'revisor-medium', 'revisor-low'],
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
    'diff-pr7-Hope-r2.patch': 'diff --git a/x.cs b/x.cs\n--- a/x.cs\n+++ b/x.cs\n@@ -1 +1 @@\n-a\n+b\n',
    'review-pr-7-r1.md': [
      '### R1-01 — IMPORTANTE — `x.cs:1`', '**O quê:** troca o contrato', '**Rascunho do comentário de PR (7):**', '> Isto quebra o contrato.', '',
      '### R1-02 — SUGESTAO — `x.cs:2`', '**O quê:** nome', '', 'Voto sugerido: aguardar autor (`-5`).',
    ].join('\n'),
  },
  'pr-8': {
    'demand.json': JSON.stringify({
      id: 'pr-8', step: 'FINAL_REVIEW',
      repos: [
        { repo: 'C:/p/Gedar', path: 'C:/wt/pr-8/Gedar', branch: 'pr/8', base: 'a', pr: '8', source: 'b' },
        { repo: 'C:/p/Emissao', path: 'C:/wt/pr-8/Emissao', branch: 'pr/9', base: 'a', pr: '9', source: 'b' },
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
}

const norm = (path: string) => path.replace(/\\/g, '/')
const PROPS_BAND = { hasSurvey: false, isWorking: false, maxRows: 4, bodyColumns: 160, scroll: { offset: 0, bodyRows: 4 }, view: {} }
const PROPS_PANE = { title: 'AiDW', isFocused: true, bodyColumns: 160, placement: 'dock' as const, scroll: { offset: 0, bodyRows: 40 }, view: {} }

type Fake = {
  runs: (readonly string[])[]; fills: string[]; submits: string[]; toasts: string[]; opens: number; clock: ReturnType<typeof mock.clock>
  files: Record<string, string>
}

/** O disco, o AiDW e o engine de mentira; `demand` é a pasta onde a sessão abre. `panel: false` é um contexto sem painel. */
function fake(
  on: On,
  opts: { orchestrating: boolean; demand: string; argument?: string; cwd?: string; contextTokens?: number; panel?: boolean; background?: boolean },
): Fake {
  const files: Record<string, string> = {
    'C:/AiDW/.aidw/runtime.json': JSON.stringify({ ...RUNTIME, panel: opts.panel ?? true }),
    'C:/AiDW/state/sessions.json': JSON.stringify(opts.orchestrating ? { [SESSION]: { plugin: 'aidw', argument: opts.argument ?? '' } } : {}),
  }
  for (const [id, entries] of Object.entries(DEMANDS)) {
    for (const [name, text] of Object.entries(entries)) files[`${STATE}/${id}/${name}`] = text
  }
  const out: Fake = { runs: [], fills: [], submits: [], toasts: [], opens: 0, clock: mock.clock(on), files }
  on('ui.toast', ($, e) => {
    out.toasts.push(e.text)
    return { value: undefined }
  })
  on('turn.complete', ($, e) => ({ text: e.answer }))
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
  on('tool.call', ($, e) => ({
    result: opts.background ? {
      status: 'async_launched', agentId: 'bg1', description: 'Revisar plano', prompt: e.tool === 'Agent' ? e.prompt : '', outputFile: 'C:/tmp/bg1.output',
    } : {
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
const delegation = (over: { subagent_type?: string } = {}) => ({
  tool: 'Agent' as const,
  description: 'Codificar rota',
  subagent_type: over.subagent_type ?? 'aidw:codificador',
  prompt: `Tarefa: ${STATE}/us-1/tarefa-codificador-rota.md. Pasta da demanda: ${STATE}/us-1.`,
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
    await has(band, /^82k$/) // o contexto em tokens, não em % da janela
    await has(band, /^58%$/)
    // a hora é a local (o resetsAt vem em UTC), com o dia na frente quando não é hoje
    const reset = new Date('2026-10-14T16:40:00Z')
    const hm = `${String(reset.getHours()).padStart(2, '0')}:${String(reset.getMinutes()).padStart(2, '0')}`
    await has(band, new RegExp(`91% · renova (\\d\\d/\\d\\d )?${hm}`))
    expect(await band.find({ type: 'Text', text: /orçamento/ })).toBeUndefined()
    await band.unmount()

    const pane = await $.ui.mount({ plugin: 'aidw-mods', surface, component: 'Pane', requestId: 'aidw', props: PROPS_PANE })
    for (const key of ['tab-geral', 'tab-criterios', 'tab-revisao', 'tab-diffs', 'tab-manual', 'tab-metricas']) {
      expect(await pane.find({ key })).toBeDefined()
    }
    // Geral: título, mapa (critérios, tokens, tempo, etapa) e o último agente
    await has(pane, /^Rota fast$/)
    await has(pane, /etapa 5 de 11/)
    await has(pane, /^117k$/)
    await has(pane, /último: codificador \(rota\), concluído/)
    await pane.press({ key: 'tab-metricas' })
    await has(pane, /^opus · medium$/)
    await has(pane, /arquivos na pasta da demanda/)
    await pane.press({ key: 'tab-criterios' })
    await has(pane, /^abre a rota$/)
    expect(await pane.find({ type: 'Text', text: /Ainda não há plano/ })).toBeUndefined()
    // Revisão: rodada como seletor, abas de decisão; decidir leva ao prompt
    await pane.press({ key: 'tab-revisao' })
    await pane.press({ key: 'review-round-review-us-1-r4.md' })
    await pane.press({ key: 'dt-mantido' })
    await has(pane, /quebra o login/)
    await pane.press({ key: 'review-round-review-us-1-r1.md' })
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

test('travas: variante fora da tabela e model sem pedido são recusados', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'us-1' })
  await $.session.start(START('us-1'))
  const wrong = await $.tool.call(delegation({ subagent_type: 'aidw:codificador-high' }))
  expect(why(wrong)).toContain('não está na tabela Agents and effort')
  const model = await $.tool.call({ ...delegation(), model: 'sonnet' })
  expect(why(model)).toContain('não passe `model`')
  expect(f.runs).toEqual([])
})

test('revisão de PR: achados, aprovação e a decisão vai para o prompt', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'pr-7' })
  await $.session.start(START('pr-7'))
  const pane = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'Pane', requestId: 'aidw', props: PROPS_PANE })
  expect(await pane.find({ key: 'tab-comentarios' })).toBeDefined()
  expect(await pane.find({ key: 'tab-criterios' })).toBeUndefined()
  await pane.press({ key: 'tab-comentarios' })
  await has(pane, /^Isto quebra o contrato\.$/)
  await has(pane, /Comentário na PR 7/)
  await pane.press({ key: 'pa-R1-01' })
  expect(f.fills.at(-1)).toContain('Ajuste o comentário do achado R1-01')
  await pane.press({ key: 'pp-R1-01' })
  await pane.press({ key: 'pp-R1-02' })
  expect(await pane.find({ key: 'pt-publicar' })).toBeDefined()
  await pane.press({ key: 'pr-decision' })
  expect(f.fills.at(-1)).toContain('Publicar: R1-01, R1-02')
  expect(f.fills.at(-1)).toContain('Aprovar a PR: manual (não aprove; eu decido na ferramenta).')
  await pane.press({ key: 'ap-unica-sim' })
  await pane.press({ key: 'pr-decision' })
  expect(f.fills.at(-1)).toContain('Aprovar a PR: sim (aprove a PR).')
  await pane.press({ key: 'tab-diffs' })
  await pane.press({ key: 'diff-source-patch:diff-pr7-Hope-r2.patch' })
  await has(pane, /1 arquivo · \+1 −1/)
  await pane.unmount()
})

test('revisão de PR com triagem: comentários por PR, aprovação por PR e a decisão vai para o prompt', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'pr-8' })
  await $.session.start(START('pr-8'))
  const pane = await $.ui.mount({ plugin: 'aidw-mods', surface: 'desktop', component: 'Pane', requestId: 'aidw', props: PROPS_PANE })
  await pane.press({ key: 'tab-comentarios' })
  // abre em "A decidir": só o C2; o publicado aparece em Todos, com a situação da rodada 2
  await has(pane, /^a modal reaparece a cada recarga$/)
  expect(await pane.find({ type: 'Text', text: /resolvido na r2/ })).toBeUndefined()
  await pane.press({ key: 'pt-todos' })
  await has(pane, /^publicado \(thread 1\), resolvido na r2$/)
  await has(pane, /^junta R1-01 · B1-01$/)
  // "Aprovar a PR?" por PR, manual quando você não escolhe
  await has(pane, /^Aprovar a PR 8\?$/)
  await pane.press({ key: 'pp-C2' })
  await pane.press({ key: 'ap-8-sim' })
  await pane.press({ key: 'pr-decision' })
  expect(f.fills.at(-1)).toContain('PR 8: publicar C2; não publicar nenhum; aprovar: sim (aprove a PR).')
  expect(f.fills.at(-1)).toContain('PR 9: publicar nenhum; não publicar C3; aprovar: manual (não aprove; eu decido na ferramenta).')
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
  await pane.press({ key: 'tab-duvidas' })
  await pane.input({ key: 'duvida-D1', text: 'Só PF', kind: 'change' })
  await pane.input({ key: 'duvida-D1', text: 'Só PF' })
  expect(f.submits.at(-1)).toContain('Resposta à dúvida D1 do levantamento lv-9: Só PF')
  await pane.press({ key: 'tab-estimativa' })
  await pane.press({ key: 'post-levantamento' })
  expect(f.fills.at(-1)).toContain('publique no card lv-9')
  await pane.unmount()
})

test('contexto sem painel: a faixa aparece, o painel não abre e /aidw-painel explica', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'us-1', panel: false })
  await $.session.start(START('us-1'))
  expect(f.opens).toBe(0)
  const band = await $.ui.mount({ plugin: 'aidw-mods', surface: 'terminal', component: 'AbovePrompt', props: PROPS_BAND })
  await has(band, /^us-1$/)
  await has(band, /^82k$/)
  await band.unmount()
  const r = await $.command.run({ command: 'aidw-painel', args: '' } as never)
  expect(JSON.stringify(r)).toContain('painel está desligado')
  expect(f.opens).toBe(0)
  // as travas continuam: a us-1 está no limite de rodadas
  expect(why(await $.tool.call(delegation()))).toContain('Liberar +1 rodada')
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

const TURN = (cacheRead: number) => ({
  answer: 'ok', durationMs: 5_000, isAborted: false, turnId: 't1', reason: 'answer' as const,
  usage: { model: 'claude-opus-5-5', input_tokens: 3, output_tokens: 700, cache_read_input_tokens: cacheRead, cache_creation_input_tokens: 10_000 },
})

test('fim de turno numa espera longa: grava o turno do orquestrador e compacta uma vez', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'pr-7', contextTokens: 300_000 })
  const compactions: string[] = []
  on('session.compact', ($, e) => {
    compactions.push(e.instructions ?? '')
    return { messages: [{ role: 'user', text: 'resumo da conversa', toolUses: [] }] as never, tokensBefore: 300_000, tokensAfter: 40_000 }
  })
  await $.session.start(START('pr-7'))
  await $.turn.complete(TURN(290_000))
  const rec = f.runs.find(a => a.includes('record-orchestrator')) ?? []
  for (const [flag, value] of [['--demand', `${STATE}/pr-7`], ['--session', SESSION], ['--model', 'claude-opus-5-5'], ['--cache-read', '290000'], ['--cache-write', '10000'], ['--output', '700']] as const) {
    expect(rec[rec.indexOf(flag) + 1]).toBe(value)
  }
  expect(compactions).toEqual([]) // só entre turnos, logo depois deste
  await f.clock.advance(1_000)
  expect(compactions.length).toBe(1)
  expect(compactions[0]).toContain('FINAL_REVIEW')
  await $.turn.complete(TURN(295_000))
  await f.clock.advance(1_000)
  expect(compactions.length).toBe(1) // a mesma espera não compacta de novo
})

test('fim de turno com contexto alto fora de espera: sugere /compact uma vez, sem compactar', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'us-1', contextTokens: 300_000 })
  const compactions: string[] = []
  on('session.compact', ($, e) => {
    compactions.push(e.instructions ?? '')
    return { messages: [] }
  })
  await $.session.start(START('us-1'))
  await $.turn.complete(TURN(290_000))
  await $.turn.complete(TURN(295_000))
  await f.clock.advance(1_000)
  expect(f.toasts.filter(t => t.includes('/compact')).length).toBe(1)
  expect(f.toasts.find(t => t.includes('/compact'))).toContain('300k tokens')
  expect(compactions).toEqual([])
})

test('troca de etapa com contexto alto: compacta uma vez entre turnos', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'us-1', contextTokens: 300_000 })
  const compactions: string[] = []
  on('session.compact', ($, e) => {
    compactions.push(e.instructions ?? '')
    return { messages: [{ role: 'user', text: 'resumo da conversa', toolUses: [] }] as never, tokensBefore: 300_000, tokensAfter: 40_000 }
  })
  await $.session.start(START('us-1'))
  await $.turn.complete(TURN(290_000)) // CODER_FIX: a primeira etapa vista não é troca
  await f.clock.advance(1_000)
  expect(compactions).toEqual([])
  const file = `${STATE}/us-1/demand.json`
  f.files[file] = JSON.stringify({ ...JSON.parse(f.files[file] ?? '{}'), step: 'REVIEW' })
  await $.turn.complete(TURN(295_000))
  await f.clock.advance(1_000)
  expect(compactions.length).toBe(1)
  expect(compactions[0]).toContain('troca de etapa')
  expect(compactions[0]).toContain('REVIEW')
  expect(f.toasts.some(t => t.includes('compactado na troca de etapa (REVIEW)'))).toBe(true)
  await $.turn.complete(TURN(296_000))
  await f.clock.advance(1_000)
  expect(compactions.length).toBe(1) // a mesma etapa não compacta de novo
})

test('agente em segundo plano: grava o contexto da última resposta, não a soma do turno', async ($, on) => {
  const f = fake(on, { orchestrating: true, demand: 'us-1', background: true })
  // três respostas do subagente; o cache relido cresce a cada uma (caso real da m-144245: revisor plano-r1)
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
  const extra = { command: 'aidw-rodada', args: '' } as never
  await $.command.run(extra)
  await $.command.run(extra)

  await $.tool.call(delegation()) // o Agent responde async_launched (fake com background)
  expect(f.runs).toEqual([]) // só grava quando o agente termina

  for (const [index] of steps.entries()) {
    const stream = $.turn.step({ turnId: 'bt', index, model: 'claude-sonnet-5-5', messageCount: 1 + index, agentId: 'bg1' })
    for await (const _ of stream) void _
    await stream.result
  }
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
  ] as const) {
    expect(argv[argv.indexOf(flag) + 1]).toBe(value)
  }
  expect(argv).not.toContain(String(sum))
  expect(rows.some(r => r.includes('delegação registrada') && r.includes('## Codificador - claude-opus Medium'))).toBe(true)

  // o mesmo agente retomado (SendMessage) não grava de novo
  await $.turn.complete({ answer: 'ok', durationMs: 1_000, isAborted: false, turnId: 'bt2', reason: 'answer', agentId: 'bg1' })
  expect(f.runs.length).toBe(1)
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

test('desktop: o botão leva o diff do app para o repositório, ou diz onde abrir quando já está nele', async ($, on) => {
  fake(on, { orchestrating: true, demand: 'us-1' })
  const ran: string[] = []
  on('command.run', { command: 'aidw:diff' }, ($, e) => {
    ran.push(`/${e.command} ${e.args}`)
    return { text: '' }
  })
  await $.session.start({ ...START('us-1'), surface: 'desktop' })
  const pane = await $.ui.mount({ plugin: 'aidw-mods', surface: 'desktop', component: 'Pane', requestId: 'aidw', props: PROPS_PANE })
  await pane.press({ key: 'tab-diffs' })
  // a sessão está em outra pasta: o botão leva a sessão (e o painel de diff do app) para o worktree do Front
  expect(await pane.find({ key: 'app-diff' })).toBeDefined()
  await pane.press({ key: 'app-diff' })
  expect(ran).toEqual(['/aidw:diff Front'])
  await pane.unmount()
})

test('desktop: com a sessão já no worktree, não há o que trocar', async ($, on) => {
  fake(on, { orchestrating: true, demand: 'us-1', cwd: 'C:/wt/us-1/Front' })
  await $.session.start({ ...START('us-1'), cwd: 'C:/wt/us-1/Front', surface: 'desktop' })
  const pane = await $.ui.mount({ plugin: 'aidw-mods', surface: 'desktop', component: 'Pane', requestId: 'aidw', props: PROPS_PANE })
  await pane.press({ key: 'tab-diffs' })
  expect(await pane.find({ key: 'app-diff' })).toBeUndefined()
  await has(pane, /ícone de diff no topo da janela/)
  await pane.unmount()
})
