import { atom, read, update } from 'claude-code'
import type { BuiltinToolResults, EngineInterface, Register, SessionContextUsage, SessionRateLimit, Timer, TurnUsage } from 'claude-code'

import type { Pending, ReviewFilter, Snapshot, TokenUsage } from '../types'
import {
  IDLE_MIN,
  IDLE_MS,
  agentSpec,
  demandSetId,
  labelFor,
  parseDelegation,
  parseState,
} from './aidw'
import type { AgentDef } from './aidw'
import type { DemandFile, ExternalStep } from './artifacts'
import { checkDelegation } from './guards'
import { parseUiLanguage, setLang, t } from './i18n'
import { DIR_NAME } from './names'
import type { Runtime } from './guards'
import { redact, redactValue } from './secrets'
import { buildSnapshot, stateNote, wanted } from './snapshot'
import { Band, Panel, pendingCount, tabHasData, viewFor, viewTitle, visibleTabs } from './views'
import type { Actions, BandNav, UI, View } from './views'

// Session state (what the screen reads lives in $.state; a module reload does not lose it).
// On only in orchestrator mode: the session is in state/sessions.json, which the AiDW guard writes on
// `/aidw:go` and `/aidw:survey` and removes on `/aidw:exit` and `/aidw:done`.
const active = atom({ plugin: 'aidw-mods', key: 'active' } as const, false)
const snap = atom({ plugin: 'aidw-mods', key: 'snap' } as const, null)
const running = atom({ plugin: 'aidw-mods', key: 'running' } as const, [])
// Background subagents: the metric arrives on their turn.complete, by agentId. It lives in the state, not in a
// module variable, because the agent often outlives a `/reload-plugins` or an `aidw.py install`.
const background = atom({ plugin: 'aidw-mods', key: 'background' } as const, {})
const hidden = atom({ plugin: 'aidw-mods', key: 'hidden' } as const, false)
const tabs = atom({ plugin: 'aidw-mods', key: 'tabs' } as const, {})
const tick = atom({ plugin: 'aidw-mods', key: 'tick' } as const, 0)
const reviewRound = atom({ plugin: 'aidw-mods', key: 'reviewRound' } as const, 0)
const usage = atom({ plugin: 'aidw-mods', key: 'usage' } as const, null)
// The largest context seen since your last message: with the live strip, `usage` already shows the context after
// compaction when the message arrives; the drop is measured against this peak (2026-11-04).
const contextPeak = atom({ plugin: 'aidw-mods', key: 'contextPeak' } as const, 0)
const codeReads = atom({ plugin: 'aidw-mods', key: 'codeReads' } as const, 0)
const reviewFile = atom({ plugin: 'aidw-mods', key: 'reviewFile' } as const, '')
const decisionTab = atom({ plugin: 'aidw-mods', key: 'decisionTab' } as const, '')
const NO_FILTER: ReviewFilter = { severities: [], sources: [], statuses: [], open: false }
const reviewFilter = atom({ plugin: 'aidw-mods', key: 'reviewFilter' } as const, NO_FILTER)
const expanded = atom({ plugin: 'aidw-mods', key: 'expanded' } as const, {})

// One pane per panel (panel v4), opened by the strip button or the command, never by itself.
const COMPACTED_FROM = 40_000
const PANE: Record<View, string> = { general: 'aidw-general', metrics: 'aidw-metrics', decide: 'aidw-decide' }
// Steps at which a test adjustment may be applied (or should already be gone).
const MARK_STEPS = new Set(['TEST', 'TEST_ADJUST', 'MANUAL_TEST', 'PR', 'ORCHESTRATOR_TEST', 'PREPARE_REVIEW', 'REVIEW', 'DOCS', 'FINAL_REVIEW'])
const CODE_FILE = /\.(cs|ts|tsx|js|jsx|mjs|vue|py|java|kt|go|rs|cpp|c|h|vb|sql|xaml|cshtml|razor|html|scss|css)$/i
const USER_ORIGINS = new Set(['composer', 'bridge', 'sdk'])

let root = 'C:/AiDW'
let python = 'python'
// Usage of each subagent (turn.step), in the state to survive reloads: `last` is the last answer (the context size
// at the end, the Agent's `totalTokens` and the notification's `subagent_tokens`); `sum` adds up all answers, what
// the API charges (the delegation's US$ cost, 2026-11-04).
const agentUsage = atom({ plugin: 'aidw-mods', key: 'agentUsage' } as const, {})

async function addUsage($: EngineInterface, id: string, r: TurnUsage): Promise<void> {
  const u: TokenUsage = {
    model: r.model,
    input_tokens: r.input_tokens,
    cache_creation_input_tokens: r.cache_creation_input_tokens,
    cache_read_input_tokens: r.cache_read_input_tokens,
    output_tokens: r.output_tokens,
  }
  await update($, agentUsage, all => {
    const s = all[id]?.sum
    const sum = s
      ? {
          ...u,
          input_tokens: s.input_tokens + u.input_tokens,
          cache_creation_input_tokens: s.cache_creation_input_tokens + u.cache_creation_input_tokens,
          cache_read_input_tokens: s.cache_read_input_tokens + u.cache_read_input_tokens,
          output_tokens: s.output_tokens + u.output_tokens,
        }
      : u
    return { ...all, [id]: { last: u, sum } }
  })
}

/** Takes a subagent's usage out of the state and returns it (undefined when the mod did not see its answers). */
async function takeUsage($: EngineInterface, id: string | undefined): Promise<{ last: TokenUsage; sum: TokenUsage } | undefined> {
  if (!id) return undefined
  const u = (await read($, agentUsage))[id]
  if (u) await update($, agentUsage, all => Object.fromEntries(Object.entries(all).filter(([k]) => k !== id)))
  return u
}

/** The cost arguments for `aidw.py record` (empty when the mod did not see the subagent's answers). */
function costArgs(u: TokenUsage | undefined): string[] {
  return u
    ? ['--usage-model', u.model, '--input', String(u.input_tokens), '--cache-write', String(u.cache_creation_input_tokens),
        '--cache-read', String(u.cache_read_input_tokens), '--output', String(u.output_tokens)]
    : []
}
// The user's latest messages (the `model` lock checks whether they asked for another model).
const userPrompts: string[] = []
let kbCache: { name: string; folder: string; path: string }[] | null = null
// The idle compaction scheduled at the end of the last turn; a new message cancels it.
let idleTimer: Timer | null = null
// The mod's own idle compaction: the demand state note goes with the next message.
let compactedByIdle = false

// UI language: `[ui] language` of the AiDW aidw.config.toml, read once per session (and again on session.start).
let langSession: string | null = null

/** Sets the UI language from aidw.config.toml (pt* → pt-BR, anything else or nothing → en); cached per session. */
async function loadLanguage($: EngineInterface, force = false): Promise<void> {
  let id = ''
  try {
    id = await $.session.id()
  } catch {
    id = ''
  }
  if (!force && langSession === id) return
  langSession = id
  let tag: string | null = null
  try {
    tag = parseUiLanguage(await $.fs.read(`${root}/aidw.config.toml`))
  } catch {
    tag = null // no config: English
  }
  setLang(tag)
}

const norm = (p: string) => p.replace(/\\/g, '/').replace(/\/+$/, '')
const under = (path: string, dir: string) => norm(path).toLowerCase().startsWith(`${norm(dir).toLowerCase()}/`)

// ---------------------------------------------------------------------------------------------------------------
// Disco e AiDW

// runtime.json only changes on `aidw.py apply`: read again at most once a minute, not on every refresh (2026-11-04).
const RUNTIME_TTL = 60_000
let runtimeCache: { at: number; value: Record<string, unknown> } | null = null

async function runtimeJson($: EngineInterface): Promise<Record<string, unknown>> {
  const now = await $.clock.now()
  if (runtimeCache && now - runtimeCache.at < RUNTIME_TTL) return runtimeCache.value
  let value: Record<string, unknown> = {}
  try {
    value = JSON.parse(await $.fs.read(`${root}/.aidw/runtime.json`)) as Record<string, unknown>
  } catch {
    // no runtime.json: the locks and the panel stay at the default
  }
  runtimeCache = { at: now, value }
  return value
}

async function stateDir($: EngineInterface): Promise<string | null> {
  const r = await runtimeJson($)
  return typeof r.state_dir === 'string' ? norm(r.state_dir) : null
}

/** The name, model and effort of the variant, for the agent card in the strip. */
async function specOf($: EngineInterface, variant: string) {
  const agents = Object.values(((await runtimeJson($)).agents ?? {}) as Record<string, AgentDef>)
  return agentSpec(variant, agents)
}

/** The level table and the enabled agents, for the delegation locks. */
async function loadRuntime($: EngineInterface): Promise<Runtime | null> {
  const r = await runtimeJson($)
  // without `variants` (a runtime.json from before flow v3), the lock is off until the next `aidw.py apply`
  const variants = r.variants as Runtime['variants'] | undefined
  if (!variants) return null
  const on = Object.entries((r.agents ?? {}) as Record<string, { name: string; enabled: boolean }>)
    .filter(([role, a]) => a.enabled && role !== 'orchestrator')
  const agents = on.map(([, a]) => a.name)
  const roles = Object.fromEntries(on.map(([role, a]) => [a.name, role]))
  return { variants, agents, roles }
}

// The folder picture at the last refresh (name, size and date of each file): the clock compares with it and only re-reads
// the demand when something changed, even outside the tools (you in the editor, another chat, a script).
let seen: { dir: string; sig: string } | null = null
const signature = (entries: readonly { name: string; kind: string; size: number; mtimeMs: number }[]) =>
  entries.filter(f => f.kind === 'file').map(f => `${f.name}:${f.size}:${f.mtimeMs}`).sort().join('|')

/** Re-reads the demand when a folder file changed since the last refresh (the clock, every WATCH_MS). */
async function watchDemand($: EngineInterface): Promise<void> {
  if (!(await read($, active))) return
  const dir = (await read($, snap))?.dir
  if (!dir) return
  const entries = await $.fs.list(dir).catch(() => null)
  if (entries && !(seen?.dir === dir && seen.sig === signature(entries))) await refresh($, dir)
}

/** A Write or Edit (yours or an agent's) on a demand folder file: the strip and the panels show it right away. */
async function afterWrite($: EngineInterface, path: string | undefined): Promise<void> {
  if (!path || !(await read($, active))) return
  const dir = (await read($, snap))?.dir
  if (dir && under(path, dir)) await refresh($, dir)
}

/** Re-reads the demand from disk and redraws the strip and the panel. */
async function refresh($: EngineInterface, dir?: string): Promise<void> {
  const target = dir ? norm(dir) : (await read($, snap))?.dir
  if (!target) return
  let demand: DemandFile
  try {
    demand = JSON.parse(await $.fs.read(`${target}/demand.json`)) as DemandFile
  } catch {
    return
  }
  const entries = await $.fs.list(target).catch(() => [])
  seen = { dir: target, sig: signature(entries) }
  const files = entries.filter(f => f.kind === 'file').map(f => f.name)
  const texts: Record<string, string> = {}
  for (const f of wanted(files)) texts[f] = await $.fs.read(`${target}/${f}`).catch(() => '')
  const r = await runtimeJson($)
  const externalSteps = Array.isArray(r.external_steps) ? (r.external_steps as ExternalStep[]) : []
  const next = buildSnapshot({ dir: target, demand, files, texts, externalSteps })
  if (next.kind === 'development' && MARK_STEPS.has(next.step)) next.testMarks = await testMarks($, next)
  const before = await read($, snap)
  await update($, snap, () => next)
  if (before?.id !== next.id) {
    await update($, tabs, () => ({}))
    await update($, reviewRound, () => next.round)
    await update($, reviewFile, () => '')
    await update($, decisionTab, () => '')
  }
}

/** Says in the status how many secrets the filter hid (only the name, never the value). */
function hidSecrets($: EngineInterface, hits: string[]) {
  $.ui.status(t('msg.secretsHidden', { n: hits.length, names: hits.slice(0, 3).join(', ') }))
}

/**
 * After a compaction, the demand state comes back with your next message. Not through session.compact nor
 * SessionStart: an organization security plugin, when installed, passes both along without calling the
 * user's plugins; prompt.submit does reach here. Compaction is seen by the mod's own or by the context dropping
 * below half (from COMPACTED_FROM tokens); a fixed section in the system prompt would change at every step
 * and rewrite the cache of the whole conversation.
 */
async function stateAfterCompaction($: EngineInterface): Promise<string[]> {
  const before = Math.max(await read($, contextPeak), (await read($, usage))?.tokens ?? 0)
  const now = await measure($)
  if (now !== null) await update($, contextPeak, () => now)
  const compacted = compactedByIdle || (now !== null && before >= COMPACTED_FROM && now < before / 2)
  compactedByIdle = false
  if (!compacted) return []
  await refresh($)
  const s = await read($, snap)
  return s ? [stateNote(s)] : []
}

// The marks git grep runs at most once per MARKS_TTL per demand and step; a delegation that ends redoes it.
const MARKS_TTL = 30_000
let marksCache: { key: string; at: number; value: Record<string, number> } | null = null

/** The AIDW-TESTE marks of each worktree: test adjustments that still have to go before the PR commit. */
async function testMarks($: EngineInterface, s: Snapshot): Promise<Record<string, number>> {
  const key = `${s.dir}|${s.step}`
  const now = await $.clock.now()
  if (marksCache && marksCache.key === key && now - marksCache.at < MARKS_TTL) return marksCache.value
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
  marksCache = { key, at: now, value: out }
  return out
}

/** The demand of the session folder: the first path segment that is a demand of the active context. */
async function fromCwd($: EngineInterface, cwd: string): Promise<string | null> {
  const dir = await stateDir($)
  if (!dir) return null
  for (const part of norm(cwd).split('/')) {
    if (part && (await $.fs.exists(`${dir}/${part}/demand.json`))) return `${dir}/${part}`
  }
  return null
}

/**
 * Checks whether this session is in orchestrator mode and which demand it drives (the panels only open by the button or
 * command). The demand is the folder the session record carries (`aidw.py session bind` or `demand set`, in any
 * context and platform); without it, the chat folder when it opened in the demand or in one of its worktrees.
 */
async function checkActive($: EngineInterface): Promise<boolean> {
  let on = false
  let folder = ''
  try {
    const sessions = JSON.parse(await $.fs.read(`${root}/state/sessions.json`)) as Record<string, { folder?: string }>
    const id = await $.session.id()
    on = Object.prototype.hasOwnProperty.call(sessions, id)
    folder = String(sessions[id]?.folder ?? '')
  } catch {
    on = false
  }
  const was = await read($, active)
  if (on !== was) await update($, active, () => on)
  if (on) {
    const bound = folder && (await $.fs.exists(`${norm(folder)}/demand.json`)) ? norm(folder) : null
    const current = (await read($, snap))?.dir
    const dir = bound ?? (current ? null : await fromCwd($, await $.session.cwd()))
    if (dir && dir !== current) await refresh($, dir)
  }
  if (on && !was) await measure($)
  if (!on && was) for (const id of Object.values(PANE)) await $.ui.close({ id }).catch(() => undefined)
  return on
}

/** The panel applies in every context except one that turns it off (`[mods] panel = false`); the strip and the rest of the mod, always. */
async function panelOn($: EngineInterface): Promise<boolean> {
  return (await runtimeJson($)).panel !== false
}

/** Opens a panel; returns the reason when it did not fit in the window. */
async function openPanel($: EngineInterface, view: View): Promise<string | null> {
  const s = await read($, snap)
  const opened = await $.ui.open({ id: PANE[view], title: `AiDW · ${viewTitle(view, s?.kind ?? 'development')}` })
  return opened.isPlaced ? null : (opened.reason ?? t('msg.noRoom'))
}

/** `/panel [tab]`, `/metrics`, `/review-tests`: opens the panel (and the requested tab) and says what happened. */
async function openFromCommand($: EngineInterface, arg: string): Promise<{ text: string }> {
  await loadLanguage($)
  if (!(await panelOn($))) return { text: t('msg.panelOff') }
  const s = await read($, snap)
  if (!s) return { text: t('msg.noDemand') }
  const { view, tab } = viewFor(s.kind, arg.trim().toLowerCase())
  if (tab) await update($, tabs, x => ({ ...x, [view]: tab }))
  const missing = await openPanel($, view)
  return { text: missing ? t('msg.panelNoRoom', { why: missing }) : t('msg.panelOpened', { view: viewTitle(view, s.kind), id: s.id }) }
}

/** `aidw.py demand set <id> --step X`: the step changed (or the demand is another one). */
async function afterShell($: EngineInterface, command: string): Promise<void> {
  const id = demandSetId(command)
  if (!id) return
  const dir = await stateDir($)
  if (dir) await refresh($, `${dir}/${id}`)
}

const RECORDED = '\u0000gravado'

/** Writes the line to the metrics file through `aidw.py record` itself and returns the header + summary it prints. */
async function record(
  $: EngineInterface,
  p: Pending,
  state: string | null,
  tokens: number,
  tools: number,
  ms: number,
  sum?: TokenUsage,
): Promise<string | null> {
  const argv = [
    python, `${root}/aidw.py`, 'record',
    '--agent', p.agent, '--label', p.label, '--demand', p.demand,
    '--tokens', String(tokens), '--tool-uses', String(tools), '--duration-ms', String(Math.round(ms)),
    ...(p.level ? ['--level', p.level] : []),
    ...(state ? ['--state', state] : []),
    ...costArgs(sum),
  ]
  try {
    const ran = await $.process.run(argv, { cwd: root, timeoutMs: 60_000 })
    marksCache = null
    await refresh($, p.demand)
    // the last JSON line of the output: a warning printed before it does not break the record (2026-11-04)
    const line = ran.stdout.split(/\r?\n/).reverse().find(l => l.trimStart().startsWith('{'))
    const out = (line ? JSON.parse(line) : {}) as { header?: string; resumo?: string; error?: string }
    if (out.header) return `${out.header}\n${out.resumo ?? ''}`
    // written (code 0) but without the header: do not ask the orchestrator to record again (the line would duplicate)
    return ran.exitCode === 0 && !out.error ? RECORDED : null
  } catch {
    return null
  }
}

/** The four numbers of an answer summed: the context it read plus what it wrote. */
const totalTokens = (u: TokenUsage) => u.input_tokens + u.cache_creation_input_tokens + u.cache_read_input_tokens + u.output_tokens

/** How many tools the agent called: the tool_use blocks of its transcript, like the notification's `tool_uses`. */
async function toolUses($: EngineInterface, agentId: string): Promise<number> {
  const found = await $.session.messages({ agentId }).catch(() => null)
  return Array.isArray(found) ? found.reduce((n, m) => n + (m.role === 'assistant' ? m.toolUses.length : 0), 0) : 0
}

function notice(header: string | null, p: Pending): string {
  if (header === RECORDED) return t('notice.recordedNoHeader', { label: p.label })
  return header ? t('notice.recorded', { header }) : t('notice.failed', { label: p.label })
}

/**
 * Stores the context and the plan usage windows (5h, 7d) for the strip, only when something it shows changed (the % or the
 * thousand of tokens, a window): each write redraws it. Returns the context tokens.
 */
async function setUsage($: EngineInterface, u: { context: SessionContextUsage; rateLimits?: readonly SessionRateLimit[] }): Promise<number> {
  const tokens = u.context.tokens ?? 0
  const limits = (u.rateLimits ?? [])
    .filter(l => l.kind === 'five_hour' || l.kind === 'seven_day')
    .map(l => ({ kind: l.kind === 'five_hour' ? ('5h' as const) : ('7d' as const), percent: l.percentUsed, resetsAt: l.resetsAt ?? '' }))
  const next = { percent: Math.round(u.context.percent ?? 0), tokens, limits }
  const before = await read($, usage)
  const same = before !== null && before.percent === next.percent && Math.round(before.tokens / 1000) === Math.round(tokens / 1000) &&
    JSON.stringify(before.limits) === JSON.stringify(limits)
  if (!same) await update($, usage, () => next)
  if (tokens > (await read($, contextPeak))) await update($, contextPeak, () => tokens)
  return tokens
}

/** The context (in tokens) and the plan usage windows (5h, 7d) for the strip, read now. */
async function measure($: EngineInterface): Promise<number | null> {
  try {
    return await setUsage($, await $.session.usage())
  } catch {
    return null // no usage measured on this surface
  }
}

/** Adds the main chat turn to the demand's orchestrator metrics file (`aidw.py record-orchestrator`). */
async function recordTurn($: EngineInterface, s: Snapshot, u: TurnUsage, ms: number): Promise<void> {
  const argv = [
    python, `${root}/aidw.py`, 'record-orchestrator', '--demand', s.dir, '--session', await $.session.id(),
    '--model', u.model, '--input', String(u.input_tokens), '--cache-write', String(u.cache_creation_input_tokens),
    '--cache-read', String(u.cache_read_input_tokens), '--output', String(u.output_tokens), '--duration-ms', String(Math.round(ms)),
    '--step', s.step,
  ]
  await $.process.run(argv, { cwd: root, timeoutMs: 30_000 }).catch(() => null)
}

/**
 * Compacts the conversation idle for IDLE_MS (scheduled at the end of the turn; a new message cancels it). Measures
 * again: below IDLE_MIN it is not worth it.
 */
async function compactIdle($: EngineInterface): Promise<void> {
  idleTimer = null
  if (!(await read($, active))) return
  const before = await measure($)
  if (before === null || before < IDLE_MIN) return
  const s = await read($, snap)
  try {
    const r = await $.session.compact({
      instructions: t('compact.instructions', { where: s ? t('compact.where', { step: s.step, id: s.id }) : '' }),
    })
    if (r.skip !== undefined) return
    compactedByIdle = true
    await measure($)
  } catch {
    // a turn started before: the compaction waits for the next pause
  }
}

/** The end of an orchestrator turn: turn metric, context and idle compaction. */
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

/** The knowledge base notes of the active context (for `[[note]]` in the prompt). */
async function kbNotes($: EngineInterface): Promise<{ name: string; folder: string; path: string }[]> {
  if (kbCache) return kbCache
  const r = await runtimeJson($)
  const ctx = `${root}/contexts/${String(r.context ?? '')}`
  // the knowledge folder: `knowledge/` (new) or `conhecimento/` (old)
  let base = `${ctx}/${DIR_NAME.knowledge[0]}`
  for (const name of DIR_NAME.knowledge) {
    if (await $.fs.exists(`${ctx}/${name}`).catch(() => false)) {
      base = `${ctx}/${name}`
      break
    }
  }
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

/** The text of the notes cited as `[[name]]`, to go with the message. */
async function kbContext($: EngineInterface, text: string): Promise<string[]> {
  const names = [...new Set([...text.matchAll(/\[\[([a-z0-9][\w-]*)\]\]/gi)].map(m => (m[1] ?? '').toLowerCase()))].slice(0, 3)
  if (!names.length) return []
  const notes = await kbNotes($)
  const out: string[] = []
  for (const name of names) {
    const note = notes.find(n => n.name.toLowerCase() === name)
    if (!note) continue
    const body = await $.fs.read(note.path).catch(() => '')
    if (body) out.push(t('kb.note', { name: note.name, path: note.path, body: body.slice(0, 6000) }))
  }
  return out
}

/** The code the orchestrator read in its own chat (outside the AiDW folder): counts it and returns the warning. */
async function codeRead($: EngineInterface, path: string): Promise<string | null> {
  if (!path || under(path, root) || !CODE_FILE.test(path)) return null
  const n = (await read($, codeReads)) + 1
  await update($, codeReads, () => n)
  return t('codeRead.warn', { n })
}

/** Moves the panel clock while an agent is running. */
async function tickRunning($: EngineInterface): Promise<void> {
  if ((await read($, running)).length) await update($, tick, n => n + 1)
}

// ---------------------------------------------------------------------------------------------------------------

export const register: Register = (on, options) => {
  root = norm(String(options.aidwRoot ?? 'C:/AiDW'))
  python = String(options.python ?? 'python')

  on('session.start', async ($, e, next) => {
    await loadLanguage($, true)
    await checkActive($)
    const panel = await panelOn($)
    for (const command of [
      { name: 'strip', description: t('cmd.strip') },
      ...(panel
        ? [
            { name: 'panel', description: t('cmd.panel'), argumentHint: t('cmd.panelArg') },
            { name: 'metrics', description: t('cmd.metrics') },
            { name: 'review-tests', description: t('cmd.reviewTests') },
          ]
        : []),
    ]) {
      await $.command.register(command).catch(() => undefined)
    }
    // every 5 s: the running agents' time moves, and the demand is re-read if a folder file changed
    $.clock.every(5_000, () => {
      void tickRunning($)
      void watchDemand($)
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
    const isOn = await read($, active)
    if (isOn) await loadLanguage($)
    const notes = isOn ? [...(await stateAfterCompaction($)), ...(await kbContext($, e.text))] : []
    const ran = await next(notes.length ? { ...e, context: [...(e.context ?? []), ...notes] } : e)
    await checkActive($)
    return ran
  })

  on('command.run', { command: 'strip' }, async $ => {
    const now = !(await read($, hidden))
    await update($, hidden, () => now)
    await loadLanguage($)
    return { text: now ? t('msg.stripHidden') : t('msg.stripVisible') }
  })

  on('command.run', { command: 'panel' }, ($, e) => openFromCommand($, e.args))
  on('command.run', { command: 'metrics' }, $ => openFromCommand($, 'metrics'))
  on('command.run', { command: 'review-tests' }, $ => openFromCommand($, 'decide'))

  // Delegation locks and metric recording.
  on('tool.call', { tool: 'Agent' }, async ($, e, next) => {
    const d = parseDelegation(e.prompt)
    const isOn = await read($, active)
    if (isOn) {
      await loadLanguage($)
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
    const spec = await specOf($, agent)
    await update($, running, list => [...list, { key, agent: agent.split(':').pop() ?? agent, label: p.label, since, ...spec }])
    if ((await read($, snap))?.dir !== norm(d.demand)) await refresh($, d.demand)

    const ran = await next(e)
    const result = ran.result as BuiltinToolResults['Agent'] | undefined
    const agentId = (await read($, running)).find(r => r.key === key)?.agentId
    if (ran.deny !== undefined || ran.isError || !result) {
      await update($, running, list => list.filter(r => r.key !== key))
      await takeUsage($, agentId)
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
    const header = await record($, p, parseState(text), result.totalTokens, result.totalToolUseCount, result.totalDurationMs, (await takeUsage($, agentId))?.sum)
    return { ...ran, context: [...(ran.context ?? []), notice(header, p)] }
  })

  // The subagent id of each Agent: its steps carry that id, and the strip card sums the tokens by it.
  on('agent.spawn', async ($, e, next) => {
    const r = await next(e)
    if ('agentId' in r && r.agentId) {
      const id = r.agentId
      await update($, running, list => list.map(x => (x.key === e.tool_use_id ? { ...x, agentId: id } : x)))
    }
    return r
  })

  // The context and the plan windows, pushed by the engine when they change (even mid-turn).
  on('session.measure', async ($, e, next) => {
    if (await read($, active)) await setUsage($, e)
    return next(e)
  })

  // A demand folder file written by you or by an agent: the strip and the panels show it right away.
  on('tool.call', { tool: 'Write' }, async ($, e, next) => {
    const ran = await next(e)
    if (ran.deny === undefined && !ran.isError) await afterWrite($, e.file_path)
    return ran
  })

  on('tool.call', { tool: 'Edit' }, async ($, e, next) => {
    const ran = await next(e)
    if (ran.deny === undefined && !ran.isError) await afterWrite($, e.file_path)
    return ran
  })

  // The usage of each subagent answer: the background record writes the last one's; the card shows the tokens.
  // For the main chat, the strip context moves at every answer, without waiting for the end of the turn.
  on('turn.step', async function* ($, e, next) {
    const r = yield* next(e)
    const id = e.agentId
    if (!id && r.usage && (await read($, active))) await measure($)
    if (id && r.usage) {
      await addUsage($, id, r.usage)
      const tokens = totalTokens(r.usage)
      if ((await read($, running)).some(x => x.agentId === id || x.key === id)) {
        await update($, running, list => list.map(x => (x.agentId === id || x.key === id ? { ...x, tokens } : x)))
      }
    }
    return r
  })

  // Savings: the orchestrator reading code in its own chat.
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
    const used = await takeUsage($, id)
    const last = used?.last
    const p = id ? (await read($, background))[id] : undefined
    if (id && p) {
      await loadLanguage($)
      await update($, background, b => Object.fromEntries(Object.entries(b).filter(([k]) => k !== id)))
      await update($, running, list => list.filter(r => r.key !== id))
      const state = parseState(e.answer)
      const header = last
        ? await record($, p, state, totalTokens(last), await toolUses($, id), e.durationMs, used?.sum)
        : null
      await $.session.append({ message: { type: 'user', content: [{ type: 'text', text: notice(header, p) }] } })
    } else if (!id && (await read($, active))) {
      await endOfTurn($, e)
    }
    return next(e)
  })

  // Secrets filter: the result of each tool (the orchestrator's or the agents') is filtered before it becomes a
  // conversation line. There is no session.append hook: an organization security plugin, when installed,
  // ran before and skipped it, and the app warned about it on every session (removed on 2026-11-04).
  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    // a denied one stays as is; the rest goes as its own result (the core maps it again)
    if (ran.deny !== undefined || !(await read($, active))) return ran
    if (ran.isError) {
      // the error also carries secrets (a connection string in an exception): it comes back as an error, with the text filtered
      const r = redact(ran.text ?? (typeof ran.result === 'string' ? ran.result : ''))
      if (!r.hits.length) return ran
      hidSecrets($, r.hits)
      return { deny: r.text }
    }
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
    await loadLanguage($)
    const nav: BandNav | undefined = (await panelOn($))
      ? {
          open: view => void openPanel($, view),
          canDecide: visibleTabs(s, 'decide').length > 0,
          pending: pendingCount({ snap: s, reviewFile: await read($, reviewFile) }),
          hasMetrics: tabHasData(s, 'metrics'),
          // the same as typing /aidw:diff: queued and run once the session is idle
          ...(s.repos.length ? { diff: () => void $.command.run({ command: 'aidw:diff' }).catch(() => undefined) } : {}),
        }
      : undefined
    return Band(ui, s, await read($, running), await read($, usage), await $.clock.now(), nav,
      { columns: e.props.bodyColumns ?? 0, rows: e.props.maxRows ?? 0 })
  })

  for (const view of Object.keys(PANE) as View[]) on('ui.render', { component: 'Pane', requestId: PANE[view] }, async ($, e) => {
    const ui = $.ui.resolve(e) as unknown as UI
    const s = await read($, snap)
    await loadLanguage($)
    if (!(await panelOn($))) {
      const { Text } = ui
      return <Text dimColor>{t('msg.paneOff')}</Text>
    }
    if (!s) {
      const { Text } = ui
      return <Text dimColor>{t('msg.paneNoDemand')}</Text>
    }

    await read($, tick)
    const toggle = (list: string[], value: string) => (list.includes(value) ? list.filter(x => x !== value) : [...list, value])
    const act: Actions = {
      tab: id => void update($, tabs, x => ({ ...x, [view]: id })),
      refresh: () => void refresh($),
      reviewFile: f => void update($, reviewFile, () => f),
      decisionTab: id => void update($, decisionTab, () => id),
      toggleFilter: (kind, value) => void update($, reviewFilter, f => ({ ...f, [kind]: toggle(f[kind], value) })),
      toggleFilters: () => void update($, reviewFilter, f => ({ ...f, open: !f.open })),
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
        usage: await read($, usage),
        columns: e.props.bodyColumns,
        surface: e.surface,
        reviewFile: await read($, reviewFile),
        decisionTab: await read($, decisionTab),
        filter: await read($, reviewFilter),
        expanded: await read($, expanded),
      },
      act,
    )
  })
}
