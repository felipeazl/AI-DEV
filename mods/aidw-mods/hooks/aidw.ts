// Leitura pura dos artefatos do AiDW: o prompt de uma delegação, o JSON final do agente, o metricas.md,
// as rodadas de revisão e o routing.toml. Sem `$`, para os testes rodarem sem o engine.

import type { Delegation as MetricsRow, OrchestratorRow, OrchestratorUsage } from '../types'

export type Delegation = { demand: string; level: string | null; task: string | null }

const DEMAND = /Pasta da demanda:\s*`?([A-Za-z]:[\\/][^`\s]*?|\/[^`\s]*?)`?\.?(?=\s|$)/
const LEVEL = /N[íi]vel:\s*`?([a-z]+)/
const TASK = /Tarefa:\s*`?([^`\s]+?\.md)/

/** A delegação do AiDW: o prompt traz a pasta da demanda (sem ela, não é do AiDW). */
export function parseDelegation(prompt: string): Delegation | null {
  const demand = DEMAND.exec(prompt)?.[1]
  if (!demand) return null
  return {
    demand: demand.replace(/\\/g, '/').replace(/\/+$/, ''),
    level: LEVEL.exec(prompt)?.[1] ?? null,
    task: TASK.exec(prompt)?.[1] ?? null,
  }
}

/** O último `"state": "<key>"` do texto final do agente. */
export function parseState(text: string): string | null {
  const all = [...text.matchAll(/"state"\s*:\s*"([a-z_]+)"/g)]
  return all.at(-1)?.[1] ?? null
}

/** Rótulo da linha do metricas.md: o nome da tarefa sem `tarefa-` e sem o agente; sem tarefa, a descrição. */
export function labelFor(task: string | null, agent: string, description: string): string {
  const base = (agent.split(':').pop() ?? agent).split('-')[0] ?? agent
  if (task) {
    const stem = (task.replace(/\\/g, '/').split('/').pop() ?? '').replace(/\.md$/, '')
    const label = stem.replace(/^tarefa-/, '').replace(/^aidw-/, '').replace(new RegExp(`^${base}-`), '')
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

/** Delegações, tokens somados e o nível da última linha do metricas.md. */
export function parseMetricas(text: string): { rows: number; tokens: number; level: string | null } {
  let rows = 0
  let tokens = 0
  let level: string | null = null
  for (const line of text.split(/\r?\n/)) {
    const cells = line.split('|').map(c => c.trim())
    if (cells.length < 12 || !/^\d{4}-\d{2}-\d{2}$/.test(cells[1] ?? '')) continue
    rows += 1
    level = cells[3] || level
    const n = Number((cells[10] ?? '').replace(/[.,\s]/g, ''))
    if (Number.isFinite(n)) tokens += n
    const out = Number((cells[11] ?? '').replace(/[.,\s]/g, ''))
    if (Number.isFinite(out)) tokens += out
  }
  return { rows, tokens, level }
}

/** "$0.42", "0,42", "1,234.50" → número; "—" ou vazio → null. */
export function usd(cell: string | undefined): number | null {
  let s = (cell ?? '').replace(/[^\d.,]/g, '')
  if (!/\d/.test(s)) return null
  s = s.includes('.') ? s.replace(/,/g, '') : s.replace(',', '.')
  const n = Number(s)
  return Number.isFinite(n) ? n : null
}

/** As linhas do metricas.md, mais antiga primeiro. */
export function parseDelegations(text: string): MetricsRow[] {
  const num = (s: string | undefined) => {
    const n = Number((s ?? '').replace(/[.,\s]/g, ''))
    return Number.isFinite(n) ? n : 0
  }
  const out: MetricsRow[] = []
  for (const line of text.split(/\r?\n/)) {
    const c = line.split('|').map(x => x.trim())
    if (c.length < 12 || !/^\d{4}-\d{2}-\d{2}$/.test(c[1] ?? '')) continue
    out.push({
      date: c[1] ?? '',
      agent: c[2] ?? '',
      level: c[3] ?? '',
      model: c[4] ?? '',
      effort: c[5] ?? '',
      label: c[6] ?? '',
      state: c[7] ?? '',
      tools: num(c[8]),
      seconds: num((c[9] ?? '').replace(/s$/, '')),
      tokens: num(c[10]) + num(c[11]),
      cost: usd(c[12]),
    })
  }
  return out
}

/**
 * O contexto do orquestrador em tokens: cada ação relê a conversa inteira, então o que pesa é o tamanho, não a
 * fração da janela (1M). A partir de CONTEXT_WARN o mod sugere /compact; numa espera longa por você, a partir de
 * CONTEXT_COMPACT ele compacta sozinho (a volta depois de 1h regravaria o contexto inteiro no cache).
 */
export const CONTEXT_WARN = 250_000
export const CONTEXT_COMPACT = 150_000
/** Etapas em que a demanda fica parada com você ou com o time (o teste manual, passo a passo, não conta). */
export const LONG_WAIT = new Set(['HUMAN_APPROVAL', 'FINAL_REVIEW', 'CODE_REVIEW', 'QA_TEST'])

/** As linhas do metricas-orquestrador.md (`aidw.py record-orchestrator`): o chat principal por sessão e modelo. */
export function parseOrchestrator(text: string): OrchestratorUsage {
  const num = (s: string | undefined) => {
    const n = Number((s ?? '').replace(/[.,\s]|s$/g, ''))
    return Number.isFinite(n) ? n : 0
  }
  const rows: OrchestratorRow[] = []
  for (const line of text.split(/\r?\n/)) {
    const c = line.split('|').map(x => x.trim())
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
    turns: rows.reduce((n, r) => n + r.turns, 0),
    tokens: rows.reduce((n, r) => n + r.tokens, 0),
    cost: rows.some(r => r.cost !== null) ? rows.reduce((n, r) => n + (r.cost ?? 0), 0) : null,
  }
}

/** Orçamento de tokens da demanda (soma das delegações) por nível: passar dele avisa, não trava. */
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
 * A rodada que importa na etapa: a da revisão do plano ou a da revisão do código. Com um laço (`demand set --loop
 * bug-1234`, o caminho curto depois da entrega), só contam as revisões dele: `review-<id>-<laço>-r<N>.md`.
 */
export function roundFor(step: string, files: string[], loop?: string | null): { round: number; kind: 'plano' | 'revisão' | null } {
  const max = (re: RegExp) =>
    files.reduce((m, f) => Math.max(m, Number(re.exec(f)?.[1] ?? 0)), 0)
  if (PLAN_STEPS.has(step)) {
    const round = max(/^revisao-plano-.*-r(\d+)\.md$/)
    return { round, kind: round ? 'plano' : null }
  }
  const tag = loop ? loop.replace(/[^a-z0-9-]/gi, '') : ''
  const round = max(tag ? new RegExp(`^review-.*-${tag}-r(\\d+)\\.md$`) : /^review-.*-r(\d+)\.md$/)
  return { round, kind: round ? 'revisão' : null }
}

export function parseMaxRetries(toml: string): number {
  return Number(/^\s*max_retries\s*=\s*(\d+)/m.exec(toml)?.[1] ?? 3)
}

/** `aidw.py demand set <id>` num comando de shell: o id da demanda. */
export function demandSetId(command: string): string | null {
  return /aidw\.py["']?\s+demand\s+set\s+["']?([A-Za-z0-9._-]+)/.exec(command)?.[1] ?? null
}

/**
 * Os ids de demanda num texto (o argumento do `/aidw:orquestrar`): `us-116332`, `bug-143560`, e os números de work
 * item soltos ou num link (`.../edit/101662`), que acham a pasta `<tipo>-<número>`.
 */
export function demandIds(text: string): { named: string[]; numbers: string[] } {
  const lower = text.toLowerCase()
  const named = [...new Set(lower.match(/\b[a-z]{1,6}-[a-z0-9]+(?:-[a-z0-9]+)*\b/g) ?? [])].filter(id => /\d/.test(id))
  const numbers = [...new Set(lower.match(/\b\d{4,}\b/g) ?? [])]
  return { named, numbers }
}

/** 1234567 → "1,2M"; 117050 → "117k". */
export function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace('.', ',')}M`
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`
  return String(n)
}
