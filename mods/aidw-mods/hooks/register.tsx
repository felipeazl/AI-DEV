import { atom, read, update } from 'claude-code'
import type { BuiltinToolResults, EngineInterface, Register, Timer, TurnUsage } from 'claude-code'

import type { Pending, ReviewFilter, Snapshot } from '../types'
import {
  IDLE_MIN,
  IDLE_MS,
  demandIds,
  demandSetId,
  labelFor,
  parseDelegation,
  parseState,
} from './aidw'
import type { DemandFile, ExternalStep } from './artifacts'
import { checkDelegation } from './guards'
import type { Runtime } from './guards'
import { redactBlocks, redactValue } from './secrets'
import { buildSnapshot, stateNote, wanted } from './snapshot'
import { Band, Panel, VIEWS, levantamentoText, pendingCount, prDecisionText, prTriageDecisionText, reviewDecisionText, tabHasData, viewFor, visibleTabs } from './views'
import type { Actions, BandNav, UI, View } from './views'

// Estado da sessão (o que a tela lê fica em $.state; uma recarga do módulo não o perde).
// Ligado só no modo orquestrador: a sessão está no state/sessions.json, que o guard do AiDW grava ao
// `/aidw:go` e `/aidw:lev` e apaga no `/aidw:sair` e no `/aidw:done`.
const active = atom({ plugin: 'aidw-mods', key: 'active' } as const, false)
const snap = atom({ plugin: 'aidw-mods', key: 'snap' } as const, null)
const running = atom({ plugin: 'aidw-mods', key: 'running' } as const, [])
// Subagentes em segundo plano: a métrica chega no turn.complete deles, pelo agentId. Fica no estado, e não numa
// variável do módulo, porque o agente costuma atravessar um `/reload-plugins` ou um `aidw.py install`.
const background = atom({ plugin: 'aidw-mods', key: 'background' } as const, {})
const hidden = atom({ plugin: 'aidw-mods', key: 'hidden' } as const, false)
const tabs = atom({ plugin: 'aidw-mods', key: 'tabs' } as const, {})
const tick = atom({ plugin: 'aidw-mods', key: 'tick' } as const, 0)
const publish = atom({ plugin: 'aidw-mods', key: 'publish' } as const, {})
const approvals = atom({ plugin: 'aidw-mods', key: 'approvals' } as const, {})
const drafts = atom({ plugin: 'aidw-mods', key: 'drafts' } as const, {})
const reviewRound = atom({ plugin: 'aidw-mods', key: 'reviewRound' } as const, 0)
const usage = atom({ plugin: 'aidw-mods', key: 'usage' } as const, null)
const codeReads = atom({ plugin: 'aidw-mods', key: 'codeReads' } as const, 0)
const reviewFile = atom({ plugin: 'aidw-mods', key: 'reviewFile' } as const, '')
const decisionTab = atom({ plugin: 'aidw-mods', key: 'decisionTab' } as const, '')
const NO_FILTER: ReviewFilter = { severities: [], sources: [], statuses: [], open: false }
const reviewFilter = atom({ plugin: 'aidw-mods', key: 'reviewFilter' } as const, NO_FILTER)
const decisions = atom({ plugin: 'aidw-mods', key: 'decisions' } as const, {})
const expanded = atom({ plugin: 'aidw-mods', key: 'expanded' } as const, {})

// Um pane por painel (painel v4), aberto pelo botão da faixa ou pelo comando, nunca sozinho.
const PANE: Record<View, string> = { geral: 'aidw-geral', metricas: 'aidw-metricas', decidir: 'aidw-decidir' }
// Etapas em que um ajuste de teste pode estar aplicado (ou já devia ter saído).
const MARK_STEPS = new Set(['TEST', 'TEST_ADJUST', 'MANUAL_TEST', 'PR', 'ORCHESTRATOR_TEST', 'PREPARE_REVIEW', 'REVIEW', 'DOCS', 'FINAL_REVIEW'])
const CODE_FILE = /\.(cs|ts|tsx|js|jsx|mjs|vue|py|java|kt|go|rs|cpp|c|h|vb|sql|xaml|cshtml|razor|html|scss|css)$/i
const USER_ORIGINS = new Set(['composer', 'bridge', 'sdk'])

let root = 'C:/AiDW'
let python = 'python'
// O uso da última resposta de cada subagente (turn.step): é o tamanho do contexto no fim, o `totalTokens` do Agent e
// o `subagent_tokens` da notificação. O `usage` do turn.complete soma todas as respostas (o cache relido a cada uma).
const lastUsage = new Map<string, TurnUsage>()
// As últimas mensagens do usuário (a trava de `model` confere se ele pediu outro modelo).
const userPrompts: string[] = []
let kbCache: { name: string; folder: string; path: string }[] | null = null
// A compactação por ociosidade agendada no fim do último turno; uma mensagem nova a cancela.
let idleTimer: Timer | null = null

const norm = (p: string) => p.replace(/\\/g, '/').replace(/\/+$/, '')
const under = (path: string, dir: string) => norm(path).toLowerCase().startsWith(`${norm(dir).toLowerCase()}/`)

// ---------------------------------------------------------------------------------------------------------------
// Disco e AiDW

async function runtimeJson($: EngineInterface): Promise<Record<string, unknown>> {
  try {
    return JSON.parse(await $.fs.read(`${root}/.aidw/runtime.json`)) as Record<string, unknown>
  } catch {
    return {}
  }
}

async function stateDir($: EngineInterface): Promise<string | null> {
  const r = await runtimeJson($)
  return typeof r.state_dir === 'string' ? norm(r.state_dir) : null
}

/** A tabela de níveis e os agentes ligados, para as travas da delegação. */
async function loadRuntime($: EngineInterface): Promise<Runtime | null> {
  const r = await runtimeJson($)
  // sem `variants` (um runtime.json de antes do fluxo v3), a trava fica desligada até o próximo `aidw.py apply`
  const variants = r.variants as Runtime['variants'] | undefined
  if (!variants) return null
  const on = Object.entries((r.agents ?? {}) as Record<string, { name: string; enabled: boolean }>)
    .filter(([role, a]) => a.enabled && role !== 'orchestrator')
  const agents = on.map(([, a]) => a.name)
  const roles = Object.fromEntries(on.map(([role, a]) => [a.name, role]))
  return { variants, agents, roles }
}

/** Relê a demanda do disco e redesenha a faixa e o painel. */
async function refresh($: EngineInterface, dir?: string): Promise<void> {
  const target = dir ? norm(dir) : (await read($, snap))?.dir
  if (!target) return
  let demand: DemandFile
  try {
    demand = JSON.parse(await $.fs.read(`${target}/demand.json`)) as DemandFile
  } catch {
    return
  }
  const files = (await $.fs.list(target).catch(() => [])).filter(f => f.kind === 'file').map(f => f.name)
  const texts: Record<string, string> = {}
  for (const f of wanted(files)) texts[f] = await $.fs.read(`${target}/${f}`).catch(() => '')
  const r = await runtimeJson($)
  const externalSteps = Array.isArray(r.external_steps) ? (r.external_steps as ExternalStep[]) : []
  const next = buildSnapshot({ dir: target, demand, files, texts, externalSteps })
  if (next.kind === 'desenvolvimento' && MARK_STEPS.has(next.step)) next.testMarks = await testMarks($, next)
  const before = await read($, snap)
  await update($, snap, () => next)
  if (before?.id !== next.id) {
    await update($, approvals, () => ({}))
    await update($, publish, () => ({}))
    await update($, tabs, () => ({}))
    await update($, reviewRound, () => next.round)
    await update($, reviewFile, () => '')
    await update($, decisionTab, () => '')
    await update($, decisions, () => ({}))
  }
}

/** Diz no status quantos segredos o filtro ocultou (só o nome, nunca o valor). */
function hidSecrets($: EngineInterface, hits: string[]) {
  $.ui.status(`AiDW: ${hits.length} segredo(s) ocultado(s) na conversa (${hits.slice(0, 3).join(', ')})`)
}

/** As marcas AIDW-TESTE de cada worktree: ajustes de teste que ainda precisam sair antes do commit da PR. */
async function testMarks($: EngineInterface, s: Snapshot): Promise<Record<string, number>> {
  const out: Record<string, number> = {}
  for (const repo of s.repos) {
    const ran = await $.process
      .run(['git', '-C', repo.path, 'grep', '-c', '-I', '-F', '--untracked', 'AIDW-TESTE'], { timeoutMs: 15_000 })
      .catch(() => null)
    if (!ran) continue
    out[repo.name] = ran.exitCode === 0
      ? ran.stdout.split('\n').reduce((n, line) => n + Number(/:(\d+)$/.exec(line.trim())?.[1] ?? 0), 0)
      : 0
  }
  return out
}

/** A demanda da pasta da sessão: o primeiro trecho do caminho que é uma demanda do contexto ativo. */
async function fromCwd($: EngineInterface, cwd: string): Promise<string | null> {
  const dir = await stateDir($)
  if (!dir) return null
  for (const part of norm(cwd).split('/')) {
    if (part && (await $.fs.exists(`${dir}/${part}/demand.json`))) return `${dir}/${part}`
  }
  return null
}

/**
 * A demanda pelo que foi passado ao `/aidw:go` (`us-116332`, ou só o número), para a sessão aberta fora da
 * pasta da demanda (chat sem pasta, ou na pasta do contexto).
 */
async function fromArgument($: EngineInterface, argument: string): Promise<string | null> {
  const dir = await stateDir($)
  if (!dir) return null
  const ids = demandIds(argument)
  for (const id of ids.named) if (await $.fs.exists(`${dir}/${id}/demand.json`)) return `${dir}/${id}`
  if (!ids.numbers.length) return null
  const folders = (await $.fs.list(dir).catch(() => [])).filter(f => f.kind === 'dir').map(f => f.name)
  for (const n of ids.numbers) {
    const hit = folders.find(f => f.endsWith(`-${n}`))
    if (hit && (await $.fs.exists(`${dir}/${hit}/demand.json`))) return `${dir}/${hit}`
  }
  return null
}

/** Confere se esta sessão está no modo orquestrador; ao entrar, acha a demanda (os painéis só abrem pelo botão ou comando). */
async function checkActive($: EngineInterface): Promise<boolean> {
  let on = false
  let argument = ''
  try {
    const sessions = JSON.parse(await $.fs.read(`${root}/state/sessions.json`)) as Record<string, { argument?: string }>
    const id = await $.session.id()
    on = Object.prototype.hasOwnProperty.call(sessions, id)
    argument = String(sessions[id]?.argument ?? '')
  } catch {
    on = false
  }
  const was = await read($, active)
  if (on !== was) await update($, active, () => on)
  if (on && !(await read($, snap))) {
    const dir = (await fromCwd($, await $.session.cwd())) ?? (await fromArgument($, argument))
    if (dir) await refresh($, dir)
  }
  if (on && !was) await measure($)
  if (!on && was) for (const id of Object.values(PANE)) await $.ui.close({ id }).catch(() => undefined)
  return on
}

/** O painel vale em todo contexto, menos no que o desliga (`[mods] panel = false`); a faixa e o resto do mod, sempre. */
async function panelOn($: EngineInterface): Promise<boolean> {
  return (await runtimeJson($)).panel !== false
}

/** Abre um painel; devolve o motivo quando ele não coube na janela. */
async function openPanel($: EngineInterface, view: View): Promise<string | null> {
  const opened = await $.ui.open({ id: PANE[view], title: `AiDW · ${VIEWS[view].title}` })
  return opened.isPlaced ? null : (opened.reason ?? 'sem espaço')
}

/** `/painel [aba]`, `/metricas`, `/decisoes`: abre o painel (e a aba pedida) e diz o que aconteceu. */
async function openFromCommand($: EngineInterface, arg: string): Promise<{ text: string }> {
  if (!(await panelOn($))) return { text: 'AiDW: o painel está desligado neste contexto (`[mods] panel = false` no context.toml; tire a linha para ligar).' }
  const s = await read($, snap)
  if (!s) return { text: 'AiDW: nenhuma demanda nesta sessão (chame /aidw:go).' }
  const { view, tab } = viewFor(s.kind, arg.trim().toLowerCase())
  if (tab) await update($, tabs, x => ({ ...x, [view]: tab }))
  const missing = await openPanel($, view)
  return { text: missing ? `AiDW: o painel não coube (${missing}); alargue a janela.` : `AiDW: painel ${VIEWS[view].title} aberto (${s.id}).` }
}

/** `aidw.py demand set <id> --step X`: a etapa mudou (ou a demanda é outra). */
async function afterShell($: EngineInterface, command: string): Promise<void> {
  const id = demandSetId(command)
  if (!id) return
  const dir = await stateDir($)
  if (dir) await refresh($, `${dir}/${id}`)
}

/** Grava a linha no metricas.md pelo próprio `aidw.py record` e devolve o header + resumo que ele imprime. */
async function record(
  $: EngineInterface,
  p: Pending,
  state: string | null,
  tokens: number,
  tools: number,
  ms: number,
): Promise<string | null> {
  const argv = [
    python, `${root}/aidw.py`, 'record',
    '--agent', p.agent, '--label', p.label, '--demand', p.demand,
    '--tokens', String(tokens), '--tool-uses', String(tools), '--duration-ms', String(Math.round(ms)),
    ...(p.level ? ['--level', p.level] : []),
    ...(state ? ['--state', state] : []),
  ]
  try {
    const ran = await $.process.run(argv, { cwd: root, timeoutMs: 60_000 })
    await refresh($, p.demand)
    const out = JSON.parse(ran.stdout) as { header?: string; resumo?: string }
    return out.header ? `${out.header}\n${out.resumo ?? ''}` : null
  } catch {
    return null
  }
}

/** Os quatro números de uma resposta somados: o contexto que ela leu mais o que escreveu. */
const totalTokens = (u: TurnUsage) => u.input_tokens + u.cache_creation_input_tokens + u.cache_read_input_tokens + u.output_tokens

/** Quantas ferramentas o agente chamou: os tool_use do transcript dele, como o `tool_uses` da notificação. */
async function toolUses($: EngineInterface, agentId: string): Promise<number> {
  const found = await $.session.messages({ agentId }).catch(() => null)
  return Array.isArray(found) ? found.reduce((n, m) => n + (m.role === 'assistant' ? m.toolUses.length : 0), 0) : 0
}

function notice(header: string | null, p: Pending): string {
  return header
    ? 'AiDW: delegação registrada no metricas.md pelo mod aidw-mods (não rode `aidw.py record` para ela). ' +
        `Abra o resultado com estas duas linhas, ao pé da letra:\n${header}`
    : `AiDW: o mod aidw-mods não conseguiu registrar esta delegação (${p.label}); rode \`aidw.py record\` você mesmo.`
}

/** O contexto (em tokens) e as janelas de uso do plano (5h, 7d) para a faixa. */
async function measure($: EngineInterface): Promise<number | null> {
  try {
    const u = await $.session.usage()
    const tokens = u.context.tokens ?? 0
    const limits = (u.rateLimits ?? [])
      .filter(l => l.kind === 'five_hour' || l.kind === 'seven_day')
      .map(l => ({ kind: l.kind === 'five_hour' ? ('5h' as const) : ('7d' as const), percent: l.percentUsed, resetsAt: l.resetsAt ?? '' }))
    await update($, usage, () => ({ percent: Math.round(u.context.percent ?? 0), tokens, limits }))
    return tokens
  } catch {
    return null // sem uso medido nesta superfície
  }
}

/** Soma o turno do chat principal ao metricas-orquestrador.md da demanda (`aidw.py record-orchestrator`). */
async function recordTurn($: EngineInterface, s: Snapshot, u: TurnUsage, ms: number): Promise<void> {
  const argv = [
    python, `${root}/aidw.py`, 'record-orchestrator', '--demand', s.dir, '--session', await $.session.id(),
    '--model', u.model, '--input', String(u.input_tokens), '--cache-write', String(u.cache_creation_input_tokens),
    '--cache-read', String(u.cache_read_input_tokens), '--output', String(u.output_tokens), '--duration-ms', String(Math.round(ms)),
  ]
  await $.process.run(argv, { cwd: root, timeoutMs: 30_000 }).catch(() => null)
}

/**
 * Compacta a conversa parada há IDLE_MS (o agendamento do fim do turno; uma mensagem nova o cancela). Mede de novo:
 * abaixo de IDLE_MIN não compensa.
 */
async function compactIdle($: EngineInterface): Promise<void> {
  idleTimer = null
  if (!(await read($, active))) return
  const before = await measure($)
  if (before === null || before < IDLE_MIN) return
  const s = await read($, snap)
  try {
    const r = await $.session.compact({
      instructions:
        'Compactação do AiDW depois de um tempo parado' + (s ? `, na etapa ${s.step} da demanda ${s.id}` : '') + '. ' +
        'Mantenha o que está com o usuário (a pergunta, a aprovação ou o pacote, com as opções e a recomendação), a ' +
        'próxima ação, os agentes em andamento (o que cada um faz e o arquivo da tarefa) e as decisões ainda não ' +
        'gravadas; o resto está nos arquivos da pasta da demanda.',
    })
    if (r.skip !== undefined) return
    await measure($)
  } catch {
    // um turno começou antes: a compactação fica para a próxima pausa
  }
}

/** O fim de um turno do orquestrador: métrica do turno, contexto e a compactação por ociosidade. */
async function endOfTurn($: EngineInterface, e: { usage?: TurnUsage; durationMs: number }): Promise<void> {
  await refresh($)
  const before = await read($, snap)
  if (before && e.usage) {
    await recordTurn($, before, e.usage, e.durationMs)
    await refresh($)
  }
  const s = await read($, snap)
  await measure($)
  idleTimer?.cancel()
  idleTimer = $.clock.after(IDLE_MS, () => void compactIdle($))
}

/** As notas da base de conhecimento do contexto ativo (para `[[nota]]` no prompt). */
async function kbNotes($: EngineInterface): Promise<{ name: string; folder: string; path: string }[]> {
  if (kbCache) return kbCache
  const r = await runtimeJson($)
  const base = `${root}/contexts/${String(r.context ?? '')}/conhecimento`
  const out: { name: string; folder: string; path: string }[] = []
  for (const dir of await $.fs.list(base).catch(() => [])) {
    if (dir.kind !== 'dir') continue
    for (const f of await $.fs.list(`${base}/${dir.name}`).catch(() => [])) {
      if (f.kind === 'file' && f.name.endsWith('.md')) {
        out.push({ name: f.name.slice(0, -3), folder: dir.name, path: `${base}/${dir.name}/${f.name}` })
      }
    }
  }
  kbCache = out
  return out
}

/** O texto das notas citadas como `[[nome]]`, para ir junto da mensagem. */
async function kbContext($: EngineInterface, text: string): Promise<string[]> {
  const names = [...new Set([...text.matchAll(/\[\[([a-z0-9][\w-]*)\]\]/gi)].map(m => (m[1] ?? '').toLowerCase()))].slice(0, 3)
  if (!names.length) return []
  const notes = await kbNotes($)
  const out: string[] = []
  for (const name of names) {
    const note = notes.find(n => n.name.toLowerCase() === name)
    if (!note) continue
    const body = await $.fs.read(note.path).catch(() => '')
    if (body) out.push(`Nota [[${note.name}]] da base de conhecimento (${note.path}):\n${body.slice(0, 6000)}`)
  }
  return out
}

/** O código que o orquestrador leu no próprio chat (fora da pasta do AiDW): conta e devolve o aviso. */
async function codeRead($: EngineInterface, path: string): Promise<string | null> {
  if (!path || under(path, root) || !CODE_FILE.test(path)) return null
  const n = (await read($, codeReads)) + 1
  await update($, codeReads, () => n)
  return (
    `AiDW: o orquestrador leu código no próprio chat (${n}ª vez nesta sessão). Esse texto fica no contexto até o ` +
    'fim da demanda: para planejar ou entender, delegue ao explorador. Se é uma verificação pontual de premissa ' +
    '(skill verificar-premissa), siga.'
  )
}

/** Anda o relógio do painel enquanto há agente rodando. */
async function tickRunning($: EngineInterface): Promise<void> {
  if ((await read($, running)).length) await update($, tick, n => n + 1)
}

// ---------------------------------------------------------------------------------------------------------------

export const register: Register = (on, options) => {
  root = norm(String(options.aidwRoot ?? 'C:/AiDW'))
  python = String(options.python ?? 'python')

  on('session.start', async ($, e, next) => {
    await checkActive($)
    const panel = await panelOn($)
    for (const command of [
      { name: 'faixa', description: 'Mostra ou esconde a faixa da demanda do AiDW' },
      ...(panel
        ? [
            { name: 'painel', description: 'Abre o painel Geral da demanda do AiDW (ou o painel da aba pedida)', argumentHint: '[aba]' },
            { name: 'metricas', description: 'Abre o painel de métricas da demanda do AiDW' },
            { name: 'decisoes', description: 'Abre o painel Decisões: achados, roteiro, comentários de PR, dúvidas' },
          ]
        : []),
    ]) {
      await $.command.register(command).catch(() => undefined)
    }
    // o tempo dos agentes rodando anda a cada 5 s
    $.clock.every(5_000, () => {
      void tickRunning($)
    })
    return next(e)
  })

  on('prompt.submit', async ($, e, next) => {
    idleTimer?.cancel()
    idleTimer = null
    if (USER_ORIGINS.has(e.origin.kind)) {
      userPrompts.push(e.text)
      if (userPrompts.length > 8) userPrompts.shift()
    }
    const notes = (await read($, active)) ? await kbContext($, e.text) : []
    const ran = await next(notes.length ? { ...e, context: [...(e.context ?? []), ...notes] } : e)
    await checkActive($)
    return ran
  })

  on('command.run', { command: 'faixa' }, async $ => {
    const now = !(await read($, hidden))
    await update($, hidden, () => now)
    return { text: now ? 'Faixa do AiDW escondida.' : 'Faixa do AiDW visível.' }
  })

  on('command.run', { command: 'painel' }, ($, e) => openFromCommand($, e.args))
  on('command.run', { command: 'metricas' }, $ => openFromCommand($, 'metricas'))
  on('command.run', { command: 'decisoes' }, $ => openFromCommand($, 'decidir'))

  // Travas da delegação e registro da métrica.
  on('tool.call', { tool: 'Agent' }, async ($, e, next) => {
    const d = parseDelegation(e.prompt)
    const isOn = await read($, active)
    if (isOn) {
      const rt = await loadRuntime($)
      if (rt) {
        const why = checkDelegation({
          subagentType: e.subagent_type ?? 'general-purpose',
          prompt: e.prompt,
          model: e.model,
          runtime: rt,
          userPrompts,
        })
        if (why) return { deny: why }
      }
    }
    if (!d || !isOn) return next(e)
    const agent = e.subagent_type ?? 'general-purpose'
    const p: Pending = { agent, level: d.level, label: labelFor(d.task, agent, e.description), demand: d.demand }
    const key = e.tool_use_id
    const since = await $.clock.now()
    await update($, running, list => [...list, { key, agent: agent.split(':').pop() ?? agent, label: p.label, since }])
    if ((await read($, snap))?.dir !== norm(d.demand)) await refresh($, d.demand)

    const ran = await next(e)
    const result = ran.result as BuiltinToolResults['Agent'] | undefined
    if (ran.deny !== undefined || ran.isError || !result) {
      await update($, running, list => list.filter(r => r.key !== key))
      return ran
    }
    if (result.status === 'async_launched') {
      const id = result.agentId
      await update($, background, b => ({ ...b, [id]: p }))
      await update($, running, list => list.map(r => (r.key === key ? { ...r, key: id } : r)))
      return ran
    }
    await update($, running, list => list.filter(r => r.key !== key))
    if (result.status !== 'completed') return ran

    const text = result.content.map(c => c.text).join('\n')
    const header = await record($, p, parseState(text), result.totalTokens, result.totalToolUseCount, result.totalDurationMs)
    return { ...ran, context: [...(ran.context ?? []), notice(header, p)] }
  })

  // O uso de cada resposta de um subagente: o registro em segundo plano grava o da última.
  on('turn.step', async function* ($, e, next) {
    const r = yield* next(e)
    if (e.agentId && r.usage) lastUsage.set(e.agentId, r.usage)
    return r
  })

  // Economia: o orquestrador lendo código no próprio chat.
  on('tool.call', { tool: 'Read' }, async ($, e, next) => {
    const ran = await next(e)
    if (ran.deny !== undefined || e.agentId || !(await read($, active))) return ran
    const warn = await codeRead($, e.file_path)
    return warn ? { ...ran, context: [...(ran.context ?? []), warn] } : ran
  })

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const ran = await next(e)
    await afterShell($, e.command)
    return ran
  })

  on('tool.call', { tool: 'PowerShell' }, async ($, e, next) => {
    const ran = await next(e)
    await afterShell($, e.command)
    return ran
  })

  on('turn.complete', async ($, e, next) => {
    const id = e.agentId
    const last = id ? lastUsage.get(id) : undefined
    if (id) lastUsage.delete(id)
    const p = id ? (await read($, background))[id] : undefined
    if (id && p) {
      await update($, background, b => Object.fromEntries(Object.entries(b).filter(([k]) => k !== id)))
      await update($, running, list => list.filter(r => r.key !== id))
      const state = parseState(e.answer)
      const header = last
        ? await record($, p, state, totalTokens(last), await toolUses($, id), e.durationMs)
        : null
      await $.session.append({ message: { type: 'user', content: [{ type: 'text', text: notice(header, p) }] } })
    } else if (!id && (await read($, active))) {
      await endOfTurn($, e)
    }
    return next(e)
  })

  // Depois de uma compactação, o estado da demanda volta ao contexto. Pelo SessionStart de origem `compact`, não pelo
  // session.compact: onde a organização assenta um plugin de segurança acima (cc-plugin-sec-default), ele passa o
  // session.compact adiante e o hook daqui não roda.
  on('classic.SessionStart', async ($, e, next) => {
    const ran = await next(e)
    if (e.source !== 'compact' || e.agent_type || !(await read($, active))) return ran
    await refresh($)
    const s = await read($, snap)
    return s ? { ...ran, additionalContext: [...(ran.additionalContext ?? []), stateNote(s)] } : ran
  })

  // Filtro de segredos: nenhuma linha da conversa (do orquestrador ou dos agentes) leva o valor de um segredo.
  // Onde a organização assenta um plugin de segurança acima (cc-plugin-sec-default), o session.append não chega
  // aqui; o resultado de cada ferramenta, sim: o filtro roda nele também, antes de virar linha.
  on('session.append', async ($, e, next) => {
    if (!(await read($, active))) return next(e)
    const r = redactBlocks(e.message.content)
    if (!r.hits.length) return next(e)
    hidSecrets($, r.hits)
    return next({ ...e, message: { ...e.message, content: r.content } })
  })
  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    // um resultado com erro e um negado ficam como estão; o resto vai como resultado próprio (o core o mapeia de novo)
    if (ran.deny !== undefined || ran.isError || !(await read($, active))) return ran
    const r = redactValue(ran.result)
    if (!r.hits.length) return ran
    hidSecrets($, r.hits)
    return { result: r.value, ...(ran.context ? { context: ran.context } : {}) } as typeof ran
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const s = await read($, snap)
    if (e.props.hasSurvey || !s || s.step === 'DONE' || !(await read($, active)) || (await read($, hidden))) {
      return next(e)
    }
    const ui = $.ui.resolve(e) as unknown as UI
    await read($, tick)
    const nav: BandNav | undefined = (await panelOn($))
      ? {
          open: view => void openPanel($, view),
          canDecide: visibleTabs(s, 'decidir').length > 0,
          pending: pendingCount({ snap: s, reviewFile: await read($, reviewFile), decisions: await read($, decisions), publish: await read($, publish) }),
          hasMetrics: tabHasData(s, 'metricas'),
        }
      : undefined
    return Band(ui, s, await read($, running), await read($, usage), await $.clock.now(), nav)
  })

  for (const view of Object.keys(PANE) as View[]) on('ui.render', { component: 'Pane', requestId: PANE[view] }, async ($, e) => {
    const ui = $.ui.resolve(e) as unknown as UI
    const s = await read($, snap)
    if (!(await panelOn($))) {
      const { Text } = ui
      return <Text dimColor>O painel do AiDW está desligado neste contexto.</Text>
    }
    if (!s) {
      const { Text } = ui
      return <Text dimColor>Nenhuma demanda nesta sessão. Chame /aidw:go ou /aidw:lev.</Text>
    }
    await read($, tick)
    const fill = (text: string) => $.prompt.fill({ text })
    const toggle = (list: string[], value: string) => (list.includes(value) ? list.filter(x => x !== value) : [...list, value])
    const act: Actions = {
      tab: t => void update($, tabs, x => ({ ...x, [view]: t })),
      refresh: () => void refresh($),
      reviewFile: f => void update($, reviewFile, () => f),
      decisionTab: t => void update($, decisionTab, () => t),
      decide: (key, value) =>
        void update($, decisions, x => {
          const out = { ...x }
          if (out[key] === value) delete out[key]
          else out[key] = value
          return out
        }),
      toggleFilter: (kind, value) => void update($, reviewFilter, f => ({ ...f, [kind]: toggle(f[kind], value) })),
      toggleFilters: () => void update($, reviewFilter, f => ({ ...f, open: !f.open })),
      sendReviewDecisions: () =>
        void (async () => {
          await fill(reviewDecisionText(s, await read($, decisions)))
          await update($, decisions, () => ({}))
        })(),
      togglePublish: (id, value) =>
        void update($, publish, x => {
          const out = { ...x }
          if (out[id] === value) delete out[id]
          else out[id] = value
          return out
        }),
      approve: (pr, value) => void update($, approvals, x => ({ ...x, [pr]: value })),
      sendPrDecision: () =>
        void (async () => {
          const text = s.prTriage
            ? prTriageDecisionText(s, await read($, publish), await read($, approvals), await read($, drafts))
            : prDecisionText(s, await read($, publish), await read($, approvals), await read($, drafts))
          await fill(text)
        })(),
      adjustInChat: text => void fill(text),
      draft: (key, value) => void update($, drafts, x => ({ ...x, [key]: value })),
      manualResult: (step, result) =>
        void (async () => {
          const evidence = (await read($, drafts))[`evidencia-${step}`] ?? ''
          const what = result === 'ok' ? '✅ passou' : result === 'fail' ? '❌ falhou' : '⏭ pulado'
          await $.prompt.submit({
            text: `Roteiro ${s.roteiro}, passo ${step}: ${what}${evidence ? ` — evidência: ${evidence}` : ''}`,
            asUser: true,
          })
          await update($, drafts, x => ({ ...x, [`evidencia-${step}`]: '' }))
        })(),
      answerDoubt: id =>
        void (async () => {
          const answer = (await read($, drafts))[`duvida-${id}`] ?? ''
          if (!answer.trim()) return
          await $.prompt.submit({ text: `Resposta à dúvida ${id} do levantamento ${s.id}: ${answer}`, asUser: true })
          await update($, drafts, x => ({ ...x, [`duvida-${id}`]: '' }))
        })(),
      postLevantamento: () => void fill(levantamentoText(s)),
      expand: key => void update($, expanded, x => ({ ...x, [key]: !x[key] })),
    }
    return Panel(
      ui,
      {
        view,
        snap: s,
        running: await read($, running),
        now: await $.clock.now(),
        tab: (await read($, tabs))[view] ?? '',
        publish: await read($, publish),
        approvals: await read($, approvals),
        drafts: await read($, drafts),
        usage: await read($, usage),
        columns: e.props.bodyColumns,
        surface: e.surface,
        reviewFile: await read($, reviewFile),
        decisionTab: await read($, decisionTab),
        filter: await read($, reviewFilter),
        decisions: await read($, decisions),
        expanded: await read($, expanded),
      },
      act,
    )
  })
}
