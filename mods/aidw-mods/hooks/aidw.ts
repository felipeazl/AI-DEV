// Pure reading of the AiDW artifacts: the prompt of a delegation, the agent's final JSON, the metrics file,
// the review rounds and routing.toml. No `$`, so the tests run without the engine.

import type { Delegation as MetricsRow, OrchestratorRow, OrchestratorStep, OrchestratorUsage, RunningAgent } from '../types'
import { t } from './i18n'
import { TERM, fam } from './names'

export type Delegation = { demand: string; level: string | null; task: string | null }

// `Demand folder:`, `Level:`, `Task:` (and the old `Pasta da demanda:`, `Nível:`, `Tarefa:`)
const DEMAND = new RegExp(`${TERM.demandFolder}:\\s*\`?([A-Za-z]:[\\\\/][^\`\\s]*?|\\/[^\`\\s]*?)\`?\\.?(?=\\s|$)`)
const LEVEL = new RegExp(`${TERM.level}:\\s*\`?([a-z]+)`)
const TASK = new RegExp(`${TERM.taskLabel}:\\s*\`?([^\`\\s]+?\\.md)`)

/** An AiDW delegation: the prompt carries the demand folder (without it, it is not AiDW's). */
export function parseDelegation(prompt: string): Delegation | null {
  const demand = DEMAND.exec(prompt)?.[1]
  if (!demand) return null
  return {
    demand: demand.replace(/\\/g, '/').replace(/\/+$/, ''),
    level: LEVEL.exec(prompt)?.[1] ?? null,
    task: TASK.exec(prompt)?.[1] ?? null,
  }
}

/** The last `"state": "<key>"` of the agent's final text. */
export function parseState(text: string): string | null {
  const all = [...text.matchAll(/"state"\s*:\s*"([a-z_]+)"/g)]
  return all.at(-1)?.[1] ?? null
}

/** Label of the metrics line: the task name without `task-`/`tarefa-` and without the agent; with no task, the description. */
export function labelFor(task: string | null, agent: string, description: string): string {
  const base = (agent.split(':').pop() ?? agent).split('-')[0] ?? agent
  if (task) {
    const stem = (task.replace(/\\/g, '/').split('/').pop() ?? '').replace(/\.md$/, '')
    const label = stem.replace(new RegExp(`^${fam('task')}-`), '').replace(/^aidw-/, '').replace(new RegExp(`^${base}-`), '')
    if (label) return label
  }
  return slug(description) || base
}

export function slug(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 40)
}

/** Delegations, summed tokens and the level of the last line of the metrics file. */
/**
 * Whether the metrics file has the old Level column (`| Date | Agent | Level | …`, before flow v3). New files
 * (`| Date | Agent | Model | …`) do not; a file without a header line is read as the old layout.
 */
export function metricsHasLevel(text: string): boolean {
  const head = text.split(/\r?\n/).find(l => /^\|\s*(?:Date|Data)\s*\|/i.test(l))
  return head ? /\|\s*(?:Level|N[ií]vel)\s*\|/i.test(head) : true
}

export function parseMetrics(text: string): { rows: number; tokens: number; level: string | null } {
  let rows = 0
  let tokens = 0
  let level: string | null = null
  const o = metricsHasLevel(text) ? 0 : -1 // the cells after Agent move one to the left without the Level column
  for (const line of text.split(/\r?\n/)) {
    const cells = line.split('|').map(c => c.trim())
    if (cells.length < 12 + o || !/^\d{4}-\d{2}-\d{2}$/.test(cells[1] ?? '')) continue
    rows += 1
    if (o === 0) level = cells[3] || level
    const n = Number((cells[10 + o] ?? '').replace(/[.,\s]/g, ''))
    if (Number.isFinite(n)) tokens += n
    const out = Number((cells[11 + o] ?? '').replace(/[.,\s]/g, ''))
    if (Number.isFinite(out)) tokens += out
  }
  return { rows, tokens, level }
}

/** "$0.42", "0,42", "1,234.50" → number; "—" or empty → null. */
export function usd(cell: string | undefined): number | null {
  let s = (cell ?? '').replace(/[^\d.,]/g, '')
  if (!/\d/.test(s)) return null
  s = s.includes('.') ? s.replace(/,/g, '') : s.replace(',', '.')
  const n = Number(s)
  return Number.isFinite(n) ? n : null
}

/** The lines of the metrics file, oldest first. */
export function parseDelegations(text: string): MetricsRow[] {
  const num = (s: string | undefined) => {
    const n = Number((s ?? '').replace(/[.,\s]/g, ''))
    return Number.isFinite(n) ? n : 0
  }
  const out: MetricsRow[] = []
  const o = metricsHasLevel(text) ? 0 : -1 // new files have no Level column
  for (const line of text.split(/\r?\n/)) {
    const c = line.split('|').map(x => x.trim())
    if (c.length < 12 + o || !/^\d{4}-\d{2}-\d{2}$/.test(c[1] ?? '')) continue
    out.push({
      date: c[1] ?? '',
      agent: c[2] ?? '',
      level: o === 0 ? (c[3] ?? '') : '',
      model: c[4 + o] ?? '',
      effort: c[5 + o] ?? '',
      label: c[6 + o] ?? '',
      state: c[7 + o] ?? '',
      tools: num(c[8 + o]),
      seconds: num((c[9 + o] ?? '').replace(/s$/, '')),
      tokens: num(c[10 + o]) + num(c[11 + o]),
      cost: usd(c[12 + o]),
    })
  }
  return out
}

/**
 * Idle compaction: IDLE_MS after the end of an orchestrator turn with no new message, with the context at
 * IDLE_MIN tokens or more, it compacts by itself — before the 1h cache expires, so coming back does not rewrite the whole
 * conversation (decision, 2026-10-30: the old rule, by step and wait, never fired).
 */
export const IDLE_MS = 50 * 60_000
export const IDLE_MIN = 100_000

/** The lines of the orchestrator metrics file (`aidw.py record-orchestrator`): the main chat per session and model. */
export function parseOrchestrator(text: string): OrchestratorUsage {
  const num = (s: string | undefined) => {
    const n = Number((s ?? '').replace(/[.,\s]|s$/g, ''))
    return Number.isFinite(n) ? n : 0
  }
  const rows: OrchestratorRow[] = []
  const steps: OrchestratorStep[] = []
  for (const line of text.split(/\r?\n/)) {
    const c = line.split('|').map(x => x.trim())
    // | Step | Turns | Duration | Input | Cache written | Cache read | Output | Cost | (or the old Portuguese header)
    if (c.length === 10 && /^[A-Z][A-Z_]*$/.test(c[1] ?? '')) {
      steps.push({
        step: c[1] ?? '',
        turns: num(c[2]),
        tokens: num(c[4]) + num(c[5]) + num(c[6]) + num(c[7]),
        cost: usd(c[8]),
      })
      continue
    }
    if (c.length < 13 || !/^[0-9a-f-]{4,}$/.test(c[1] ?? '')) continue
    const [input, cacheWrite, cacheRead, output] = [num(c[7]), num(c[8]), num(c[9]), num(c[10])]
    rows.push({
      session: c[1] ?? '',
      updated: c[3] ?? '',
      model: c[4] ?? '',
      turns: num(c[5]),
      seconds: num(c[6]),
      tokens: input + cacheWrite + cacheRead + output,
      cacheWrite,
      cacheRead,
      output,
      cost: usd(c[11]),
    })
  }
  return {
    rows,
    steps,
    turns: rows.reduce((n, r) => n + r.turns, 0),
    tokens: rows.reduce((n, r) => n + r.tokens, 0),
    cost: rows.some(r => r.cost !== null) ? rows.reduce((n, r) => n + (r.cost ?? 0), 0) : null,
  }
}

/** Token budget of the demand (sum of the delegations) per level: going over it warns, it does not block. */
export const BUDGET: Record<string, number> = {
  trivial: 300_000,
  simples: 800_000,
  padrao: 2_000_000,
  complexa: 4_000_000,
  critica: 6_000_000,
}

export function budgetFor(level: string | null): number {
  return BUDGET[level ?? 'padrao'] ?? BUDGET.padrao ?? 2_000_000
}

const PLAN_STEPS = new Set(['PLAN', 'SPEC', 'TEST_PLAN', 'PLAN_REVIEW', 'PLAN_FIX', 'EXPLORE'])

/**
 * The round that matters at the step: the plan review's or the code review's. With a loop (`demand set --loop
 * bug-1234`, the short path after delivery), only its reviews count: `review-<id>-<loop>-r<N>.md`.
 */
export function roundFor(step: string, files: string[], loop?: string | null): { round: number; kind: 'plan' | 'review' | null } {
  const max = (re: RegExp) =>
    files.reduce((m, f) => Math.max(m, Number(re.exec(f)?.[1] ?? 0)), 0)
  if (PLAN_STEPS.has(step)) {
    const round = max(new RegExp(`^${fam('planReview')}-.*-r(\\d+)\\.md$`))
    return { round, kind: round ? 'plan' : null }
  }
  const tag = loop ? loop.replace(/[^a-z0-9-]/gi, '') : ''
  const round = max(tag ? new RegExp(`^review-.*-${tag}-r(\\d+)\\.md$`) : /^review-.*-r(\d+)\.md$/)
  return { round, kind: round ? 'review' : null }
}

/** `aidw.py demand set <id>` in a shell command: the demand id. */
export function demandSetId(command: string): string | null {
  return /aidw\.py["']?\s+demand\s+set\s+["']?([A-Za-z0-9._-]+)/.exec(command)?.[1] ?? null
}

/** The agent's model and effort, as the strip shows them (`Sonnet high`). */
export function agentModel(a: RunningAgent): string {
  return [a.model, a.effort].filter(Boolean).join(' ')
}

/** The agent's tokens, as the strip shows them (`42k tokens`; before the first answer, `starting`). */
export function agentTokens(a: RunningAgent): string {
  return a.tokens ? `${compact(a.tokens)} tokens` : t('band.starting')
}

/** Columns of an agent card in the strip: the widest text of the two lines, at least 30, with border and padding. */
export function agentCardWidth(a: RunningAgent): number {
  const model = agentModel(a)
  const top = 2 + (a.display ?? a.agent).length + (model ? model.length + 1 : 0) + 2 + 5
  const bottom = a.label.length + 2 + agentTokens(a).length
  return Math.max(30, Math.max(top, bottom) + 4)
}

/**
 * How the strip shows the running agents in the space the engine gives: cards, while they fit on one line; otherwise one
 * line per agent. If not even the lines fit in the height, the first ones and a summary of the rest (`shown` < total). With no
 * width (0), up to 4 cards.
 */
export function agentsLayout(running: RunningAgent[], columns: number, rows: number): { mode: 'cards' | 'list'; shown: number } {
  const width = running.reduce((sum, a) => sum + agentCardWidth(a), 0) + Math.max(0, running.length - 1)
  if (columns > 0 ? width <= columns : running.length <= 4) return { mode: 'cards', shown: running.length }
  const budget = Math.max(2, rows)
  return { mode: 'list', shown: running.length <= budget ? running.length : budget - 1 }
}

/** 1234567 → "1,2M"; 117050 → "117k". */
export function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace('.', ',')}M`
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`
  return String(n)
}

const MODELS = new Set(['haiku', 'sonnet', 'opus', 'fable'])
const EFFORTS = new Set(['low', 'medium', 'high', 'xhigh', 'max'])
const cap = (x: string) => (x ? x[0]!.toUpperCase() + x.slice(1) : x)

/** The runtime.json agent, in what the strip shows. */
export type AgentDef = { name: string; display?: string; model?: string; effort?: string }

/**
 * The name, model and effort of a variant (`busca`, `busca-sonnet-medium`, `dev-medium`): what the name does not say
 * comes from the base agent in runtime.json; a model swapped without effort in the name has no effort.
 */
export function agentSpec(variant: string, agents: AgentDef[]): { display: string; model: string; effort: string } {
  const v = variant.split(':').pop() ?? variant
  const base = agents
    .filter(a => v === a.name || v.startsWith(`${a.name}-`))
    .sort((a, b) => b.name.length - a.name.length)[0]
  if (!base) return { display: v, model: '', effort: '' }
  let model = base.model ?? ''
  let effort = base.effort ?? ''
  const rest = v.slice(base.name.length).split('-').filter(Boolean)
  const m = rest.find(x => MODELS.has(x))
  if (m) {
    model = m
    effort = ''
  }
  effort = rest.find(x => EFFORTS.has(x)) ?? effort
  return { display: base.display || cap(base.name), model: cap(model), effort }
}
