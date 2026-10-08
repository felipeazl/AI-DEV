// Leitura pura dos artefatos do AiDW: o prompt de uma delegação, o JSON final do agente, o metricas.md,
// as rodadas de revisão e o routing.toml. Sem `$`, para os testes rodarem sem o engine.

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

const PLAN_STEPS = new Set(['PLAN', 'SPEC', 'TEST_PLAN', 'PLAN_REVIEW', 'PLAN_FIX', 'EXPLORE'])

/** A rodada que importa na etapa: a da revisão do plano ou a da revisão do código. */
export function roundFor(step: string, files: string[]): { round: number; kind: 'plano' | 'revisão' | null } {
  const max = (re: RegExp) =>
    files.reduce((m, f) => Math.max(m, Number(re.exec(f)?.[1] ?? 0)), 0)
  if (PLAN_STEPS.has(step)) {
    const round = max(/^revisao-plano-.*-r(\d+)\.md$/)
    return { round, kind: round ? 'plano' : null }
  }
  const round = max(/^review-.*-r(\d+)\.md$/)
  return { round, kind: round ? 'revisão' : null }
}

export function parseMaxRetries(toml: string): number {
  return Number(/^\s*max_retries\s*=\s*(\d+)/m.exec(toml)?.[1] ?? 3)
}

/** `aidw.py demand set <id>` num comando de shell: o id da demanda. */
export function demandSetId(command: string): string | null {
  return /aidw\.py["']?\s+demand\s+set\s+["']?([A-Za-z0-9._-]+)/.exec(command)?.[1] ?? null
}

/** 1234567 → "1,2M"; 117050 → "117k". */
export function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace('.', ',')}M`
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`
  return String(n)
}
