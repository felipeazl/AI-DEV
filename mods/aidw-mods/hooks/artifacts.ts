// Reading the artifacts of an AiDW demand for the panels: the kind, the timeline, the review findings
// and the triage, the acceptance criteria and the test, the manual test script and the survey. Pure (no `$`):
// register.tsx reads the files and hands over the text. Real formats vary between demands: the rules are lenient.

import type {
  CardPoint,
  CoverageItem,
  Criterion,
  DemandKind,
  Doubt,
  EffortBlock,
  Estimate,
  Finding,
  ManualStep,
  Point,
  PrComment,
  PrTriage,
  Progress,
  ProgressStage,
  SplitItem,
  TimelineItem,
} from '../types'

import { t, tk } from './i18n'
import { fam, re as R } from './names'

export type { CardPoint, CoverageItem, Criterion, Doubt, EffortBlock, Estimate, Finding, ManualStep, Point, Progress, SplitItem, TimelineItem }

/** The plan file family (`plan-<id>.md`, `plano-<id>.md`), without the test plan and the plan review. */
export const isPlanFile = (f: string) =>
  new RegExp(`^${fam('plan')}-.*\\.md$`).test(f) && !new RegExp(`^(?:${fam('testPlan')}|${fam('planReview')})-`).test(f)

// ---------------------------------------------------------------------------------------------------------------
// Kind and timeline

export type DemandFile = { id?: string; title?: string; step?: string; status?: string; note?: string; summary?: string;
  repos?: { repo?: string; path?: string; branch?: string; base?: string; system?: string | null; pr?: string;
    head?: string; source?: string }[]; history?: { step: string; at: string }[]
  /** Fix loop after delivery (`demand set --loop`); the Tasks of each ticket (`--task`). */
  loop?: string; tasks?: Record<string, string>
  /** Steps outside the context the demand goes through (`demand set --extra-step`). */
  extra_steps?: string[] }

/** The lean modes (`/aidw:ask`, `investigate`, `card`, `kb-review`) open their demand with their own id prefix. */
const LEAN_PREFIX: [string, DemandKind][] = [['ask-', 'ask'], ['inv-', 'investigate'], ['card-', 'card'],
  ['kb-review-', 'kb-review']]

/** Development, PR review, survey or a lean mode — demand.json does not record the workflow; the id and files tell. */
export function kindOf(demand: DemandFile, files: string[]): DemandKind {
  const lean = LEAN_PREFIX.find(([prefix]) => (demand.id ?? '').startsWith(prefix))?.[1]
  if (lean) return lean
  const plan = files.some(isPlanFile)
  if ((demand.repos ?? []).some(r => r.pr) || files.some(f => /^diff-pr\d+-/.test(f))) return plan ? 'development' : 'pr-review'
  if (!plan && !implementingAfterEstimate(demand.history ?? []) &&
    (files.some(f => new RegExp(`^(?:${fam('survey')}|${fam('points')})-.*\\.md$`).test(f)) ||
      R('{surveyTitle}\\s*$').test(demand.title ?? '') ||
    (demand.history ?? []).some(h => h.step === 'ESTIMATE'))) return 'survey'
  return 'development'
}

/** The survey ended (DONE after the last ESTIMATE) and the demand went on to implementation, still without a plan. */
function implementingAfterEstimate(history: { step: string }[]): boolean {
  const estimate = history.map(h => h.step).lastIndexOf('ESTIMATE')
  if (estimate < 0) return false
  const done = history.findIndex((h, i) => i > estimate && h.step === 'DONE')
  return done > 0 && history.slice(done + 1).some(h => h.step !== 'DONE')
}

/** The display name of a demand kind, in the UI language. */
export function kindLabel(kind: DemandKind): string {
  return tk(`kind.${kind}`, kind)
}

/** Phase and stage names are i18n keys (`phase.*`); a context's external step brings its own name. */
type Phase = { name: string; steps: string[] }

/** The lean modes: understand, explore, the answer with the user (it stays there until `/aidw:done`). */
const LEAN_PHASES: Phase[] = [
  { name: 'phase.understanding', steps: ['UNDERSTAND'] },
  { name: 'phase.exploration', steps: ['EXPLORE'] },
  { name: 'phase.answer', steps: ['ANSWER'] },
  { name: 'phase.done', steps: ['DONE'] },
]

const PHASES: Record<DemandKind, Phase[]> = {
  // flow v3 (2026-10-23); older steps sit in the equivalent phase, for demands opened before it
  development: [
    { name: 'phase.understanding', steps: ['UNDERSTAND', 'EXPLORE'] },
    { name: 'phase.plan', steps: ['PLAN', 'SPEC', 'PLAN_FIX', 'PLAN_REVIEW'] },
    { name: 'phase.yourApproval', steps: ['PLAN_APPROVAL', 'TICKETS'] },
    { name: 'phase.implementation', steps: ['IMPLEMENT', 'TEST_PLAN'] },
    { name: 'phase.review', steps: ['REVIEW', 'TRIAGE', 'CODER_FIX', 'PREPARE_REVIEW'] },
    { name: 'phase.yourReview', steps: ['USER_REVIEW'] },
    { name: 'phase.tests', steps: ['TEST', 'TEST_ADJUST', 'MANUAL_TEST', 'ORCHESTRATOR_TEST'] },
    { name: 'phase.pr', steps: ['PR', 'DOCS', 'FINAL_REVIEW'] },
    { name: 'phase.done', steps: ['DONE'] },
  ],
  'pr-review': [
    { name: 'phase.understanding', steps: ['UNDERSTAND'] },
    { name: 'phase.preparation', steps: ['PREPARE_REVIEW'] },
    { name: 'phase.review', steps: ['REVIEW'] },
    { name: 'phase.finalReview', steps: ['FINAL_REVIEW'] },
    { name: 'phase.done', steps: ['DONE'] },
  ],
  survey: [
    { name: 'phase.understanding', steps: ['UNDERSTAND'] },
    { name: 'phase.exploration', steps: ['EXPLORE'] },
    { name: 'phase.estimate', steps: ['ESTIMATE'] },
    { name: 'phase.finalReview', steps: ['FINAL_REVIEW'] },
    { name: 'phase.done', steps: ['DONE'] },
  ],
  ask: LEAN_PHASES,
  investigate: LEAN_PHASES,
  card: LEAN_PHASES,
  'kb-review': LEAN_PHASES,
}

/** A phase/stage name in the UI language (an external step's own name passes through). */
const nameOf = (name: string) => tk(name, name)

/** The phases of the kind, the current one by the recorded step (HUMAN_APPROVAL and RETURN stay in the previous one). */
export function timeline(kind: DemandKind, demand: DemandFile): TimelineItem[] {
  const phases = PHASES[kind]
  const history = demand.history ?? []
  const phaseOf = (step: string) => phases.findIndex(p => p.steps.includes(step))
  let current = phaseOf(demand.step ?? '')
  if (current < 0) {
    const last = [...history].reverse().find(h => phaseOf(h.step) >= 0)
    current = last ? phaseOf(last.step) : 0
  }
  return phases.map((p, i) => ({
    name: nameOf(p.name),
    state: i < current ? 'done' : i === current ? (demand.step === 'DONE' ? 'done' : 'current') : 'pending',
    visits: history.filter(h => p.steps.includes(h.step)).length,
  }))
}

const WAITING_STEPS = new Set(['HUMAN_APPROVAL', 'PLAN_APPROVAL', 'TRIAGE', 'USER_REVIEW', 'MANUAL_TEST', 'PR', 'FINAL_REVIEW'])

/** What the demand waits from the user (approval, question, manual test, final review), or null. */
export function waitingFor(step: string | undefined): string | null {
  return step && WAITING_STEPS.has(step) ? tk(`waiting.${step}`, step) : null
}

/** An outside step the context adds (`runtime.json` → `external_steps`), placed before `before`. */
export type ExternalStep = { step: string; name: string; before: string; who?: string }

type Stage = { name: string; group: ProgressStage['group']; steps: string[]; who?: string }

/** The progress bar stages of the demand map: the AiDW ones and, in development, the outside ones (team and QA). */
const STAGES: Record<DemandKind, Stage[]> = {
  development: [
    ...PHASES.development.slice(0, -1).map(p => ({ ...p, group: 'aidw' as const })),
    { name: 'phase.codeReview', group: 'outside', steps: ['CODE_REVIEW'], who: 'who.team' },
    { name: 'phase.qaTests', group: 'outside', steps: ['QA_TEST'], who: 'who.qa' },
    { name: 'phase.done', group: 'outside', steps: ['DONE'] },
  ],
  'pr-review': PHASES['pr-review'].map(p => ({ ...p, group: 'aidw' as const })),
  survey: PHASES.survey.map(p => ({ ...p, group: 'aidw' as const })),
  ask: LEAN_PHASES.map(p => ({ ...p, group: 'aidw' as const })),
  investigate: LEAN_PHASES.map(p => ({ ...p, group: 'aidw' as const })),
  card: LEAN_PHASES.map(p => ({ ...p, group: 'aidw' as const })),
  'kb-review': LEAN_PHASES.map(p => ({ ...p, group: 'aidw' as const })),
}

/**
 * Progress from the demand.json history. An AiDW step right after an outside one (CODE_REVIEW, QA_TEST) is a return:
 * it counts for that outside stage and, until the demand goes back to it, the stage shows "voltou" (returned).
 * HUMAN_APPROVAL and RETURN stay in the previous stage. Names come out in the UI language.
 */
export function progress(kind: DemandKind, demand: DemandFile, extra: ExternalStep[] = []): Progress {
  const stages = withExternal(STAGES[kind], kind, demand, extra)
  const stageOf = (step: string) => stages.findIndex(s => s.steps.includes(step))
  const history = (demand.history ?? []).map(h => h.step).filter(s => stageOf(s) >= 0)
  const step = demand.step ?? ''
  if (stageOf(step) >= 0 && history.at(-1) !== step) history.push(step)
  const returns: Record<string, number> = {}
  let returnedFrom: string | null = null
  let lastOutside: string | null = null
  for (const s of history) {
    const st = stages[stageOf(s)]
    if (!st) continue
    if (st.group === 'outside' && !st.steps.includes('DONE')) {
      lastOutside = nameOf(st.name)
      returnedFrom = null
    } else if (st.group === 'aidw' && lastOutside) {
      returns[lastOutside] = (returns[lastOutside] ?? 0) + 1
      returnedFrom = lastOutside
      lastOutside = null
    }
  }
  const at = history.length ? stageOf(history.at(-1) ?? '') : 0
  const current = Math.max(0, at)
  const done = demand.step === 'DONE'
  return {
    stages: stages.map((s, i) => ({
      name: nameOf(s.name),
      group: s.group,
      ...(s.who ? { who: nameOf(s.who) } : {}),
      state: done || i < current
        ? 'done'
        : i === current
          ? (s.group === 'outside' ? 'with-team' : 'current')
          : nameOf(s.name) === returnedFrom
            ? 'returned'
            : 'pending',
    })),
    current: nameOf(stages[current]?.name ?? ''),
    index: current + 1,
    total: stages.length,
    returnedFrom,
    returns,
  }
}

/**
 * The context's outside steps enter development only for the demand that goes through them: marked with
 * `demand set --extra-step` or with the step in the history. Each one sits right before its `before` step.
 */
function withExternal(base: Stage[], kind: DemandKind, demand: DemandFile, extra: ExternalStep[]): Stage[] {
  if (kind !== 'development') return base
  const used = new Set([...(demand.extra_steps ?? []), ...(demand.history ?? []).map(h => h.step), demand.step ?? ''])
  const out = [...base]
  for (const e of extra) {
    if (!used.has(e.step)) continue
    const at = out.findIndex(s => s.steps.includes(e.before))
    out.splice(at < 0 ? out.length - 1 : at, 0, { name: e.name, group: 'outside', steps: [e.step], ...(e.who ? { who: e.who } : {}) })
  }
  return out
}

/** "must change" etc.: the situation of a card × code line when the survey has no column for it. */
const situationOf = (effect: string): string => {
  const e = effect.toLowerCase()
  return /n[aã]o mud|no change|unchanged/.test(e)
    ? t('situation.noChange')
    : /nada a reaproveitar|nothing to reuse/.test(e)
      ? t('situation.nothingToReuse')
      : /\bdor\b|\bpain\b/.test(e)
        ? t('situation.pain')
        : t('situation.mustChange')
}

// ---------------------------------------------------------------------------------------------------------------
// Review: findings and triage

type Severity = NonNullable<Finding['severity']>

// Stored severities keep their historical values (CRITICO…); the text may bring either language.
const SEVERITY: [RegExp, Severity][] = [
  [R('{sevCritical}'), 'CRITICO'],
  [R('{sevImportant}'), 'IMPORTANTE'],
  [R('{sevSuggestion}'), 'SUGESTAO'],
  [R('{sevPraise}'), 'ELOGIO'],
]
const STATUS = R('\\b({findingStatus})\\b')
const HEADING = /^###\s+([RPBSO]\d+-D?\d+)(?:\s*=\s*[RPBSO]\d+-D?\d+)?\s+[—–-]\s+(.*)$/

const clean = (s: string) => s.replace(/\*\*/g, '').replace(/\s+/g, ' ').trim()
const cut = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s)

/** The findings of a review (`review-*-rN.md`, `plan-review-*-rN.md`/`revisao-plano-*`, `bugs-*`, `security-*`/`seguranca-*`). */
export function parseFindings(text: string, round: number, source: Finding['source'], file = ''): Finding[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const out: Finding[] = []
  for (let i = 0; i < lines.length; i++) {
    const m = HEADING.exec(lines[i] ?? '')
    if (!m) continue
    const id = m[1] ?? ''
    const segments = (m[2] ?? '').split(/\s+[—–]\s+/).map(s => s.trim())
    const severity: Severity | null = /-D\d+$/.test(id)
      ? 'DUVIDA'
      : (SEVERITY.find(([re]) => segments.some(s => re.test(s)))?.[1] ?? null)
    const where = segments.find(s => /`[^`]+`/.test(s))?.match(/`([^`]+)`/)?.[1] ?? ''
    // the category in the title (`R1-01 — IMPORTANTE — bug — \`file:line\``), from the flow v3 reviewer
    const catIdx = segments.findIndex(s => CATEGORY.test(s))
    const category = catIdx < 0 ? '' : categoryOf(segments[catIdx] ?? '')
    if (catIdx >= 0) segments.splice(catIdx, 1)
    let status = segments.map(s => STATUS.exec(s)?.[1]).find(Boolean) ?? ''
    // the body, up to the next finding or section
    const body: string[] = []
    for (let j = i + 1; j < lines.length && !/^#{2,3}\s/.test(lines[j] ?? ''); j++) body.push(lines[j] ?? '')
    const bodyText = body.join('\n')
    status = status || (R('\\*\\*{status}:\\*\\*\\s*([^\\n]+)', '').exec(bodyText)?.[1] ?? '')
    const what =
      R('\\*\\*{what}:\\*\\*\\s*([^\\n]+)', '').exec(bodyText)?.[1] ??
      R('^-\\s*{problem}:\\s*([^\\n]+)', 'm').exec(bodyText)?.[1] ??
      segments.filter(s => !SEVERITY.some(([re]) => re.test(s)) && !/`/.test(s) && !STATUS.test(s)).join(' — ')
    const draft = R('{commentDraft}[^\\n]*\\n((?:>[^\\n]*\\n?)+)').exec(bodyText)?.[1] ?? ''
    const target = R('{prCommentDraft}\\s*\\(([^)]+)\\)').exec(bodyText)?.[1] ?? ''
    // no "What": the rest of the header, never the severity itself ("IMPORTANTE — status: fixed")
    const fromHeading = segments.filter(s => !SEVERITY.some(([re]) => re.test(s)) && !STATUS.test(s)).join(' — ')
    out.push({
      id,
      round,
      source,
      file,
      severity,
      where,
      // empty when the round only restates the finding ("— status: fixed"): the snapshot inherits the previous round's title
      title: cut(clean(what || fromHeading), 220),
      status: clean(status).toLowerCase(),
      triage: '',
      comment: draft.split('\n').map(l => l.replace(/^>\s?/, '')).join('\n').trim(),
      target: clean(target),
      published: false,
      before: fenced(bodyText, R('\\*\\*{before}:?\\*\\*:?')),
      after: fenced(bodyText, R('\\*\\*{after}:?\\*\\*:?')),
      options: [...bodyText.matchAll(/^\s*-?\s*\(([a-z])\)\s+(.+)$/gm)].slice(0, 4).map(o => `(${o[1]}) ${cut(clean(o[2] ?? ''), 400)}`),
      recommendation: cut(
        clean(R('\\*\\*{recommendation}:\\*\\*\\s*([^\\n]+)').exec(bodyText)?.[1] ?? R('\\*\\*{suggestedFix}:\\*\\*\\s*([^\\n]+)').exec(bodyText)?.[1] ?? ''),
        240,
      ),
      decision: 'pending',
      category,
    })
  }
  return out
}

const CATEGORY = R('^{category}$')

function categoryOf(s: string): Finding['category'] {
  const v = s.toLowerCase()
  return v.startsWith('bug') ? 'bug' : /^(segur|secur)/.test(v) ? 'security' : 'quality'
}

/** The fenced code block (```) right after a label (`**Before:**`), without the fences. */
function fenced(body: string, label: RegExp): string {
  const at = body.search(label)
  if (at < 0) return ''
  const m = /```[^\n]*\n([\s\S]*?)```/.exec(body.slice(at))
  return m ? (m[1] ?? '').replace(/\n$/, '') : ''
}

const FIXED = R('{fixed}')
/** A finding status that says it was fixed or closed ("corrigido", "fechado", "fixed in r2"), never "não corrigido". */
export function isFixedStatus(status: string): boolean {
  return FIXED.test(status) && !/(^|\s)(n[aã]o|not)[\s_]/i.test(status)
}

const PENDING = R('{triagePending}')
const DISCARD = R('^\\W*{triageDiscard}')
const KEEP = R('^\\W*{triageKeep}')

/** The decision the triage recorded: kept, discarded or with you (pending, including "goes to the user"). */
export function decisionOf(triage: string): Finding['decision'] {
  const text = triage.toLowerCase()
  if (!text || PENDING.test(text)) return 'pending'
  if (DISCARD.test(text)) return 'discarded'
  if (KEEP.test(text)) return 'kept'
  return 'pending'
}

/** Triage decision by id, and the ids already published (`## Published…` section). */
export function parseTriage(text: string): { decisions: Record<string, string>; published: string[] } {
  const decisions: Record<string, string> = {}
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  let header: string[] = []
  let publishing = false
  const published = new Set<string>()
  for (const line of lines) {
    if (/^#{1,3}\s/.test(line)) publishing = R('^#{1,3}\\s+{published}').test(line)
    if (publishing) for (const id of line.match(/\b[RPBSO]\d+-D?\d+\b/g) ?? []) published.add(id)
    if (line.startsWith('|')) {
      const cells = line.split('|').slice(1, -1).map(c => clean(c))
      if (cells[0] === 'ID') {
        header = cells.map(c => c.toLowerCase())
        continue
      }
      const id = /^([RPBSO]\d+-D?\d+)/.exec(cells[0] ?? '')?.[1]
      if (!id) continue
      const col = header.findIndex(h => R('{decisionCol}').test(h))
      const decision = col >= 0 ? cells[col] : cells.slice(1).join(' · ')
      const why = header.findIndex(h => R('{reasonCol}').test(h))
      decisions[id] = cut([decision, why >= 0 ? cells[why] : ''].filter(Boolean).join(' — '), 200)
      continue
    }
    const bullet = /^\s*-\s+\**([RPBSO]\d+-D?\d+)\**\s*[:—–-]\s*(.+)$/.exec(line)
    if (bullet?.[1] && !publishing) decisions[bullet[1]] = cut(clean(bullet[2] ?? ''), 200)
  }
  return { decisions, published: [...published] }
}

/** The rows of a Markdown table, each as {column: cell} by the header (lowercase). */
function tableRows(section: string): Record<string, string>[] {
  const rows = section.split('\n').filter(l => l.trim().startsWith('|'))
  const cells = (l: string) => l.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim())
  const head = rows[0] ? cells(rows[0]).map(h => clean(h).toLowerCase()) : []
  return rows.slice(2).map(r => Object.fromEntries(cells(r).map((c, i) => [head[i] ?? String(i), c])))
}
const col = (row: Record<string, string>, re: RegExp) => Object.entries(row).find(([k]) => re.test(k))?.[1] ?? ''

const PR_SEVERITY: [RegExp, string][] = [
  [/cr[ií]tic/i, 'CRITICO'],
  [/important/i, 'IMPORTANTE'],
  [/sugest|suggest/i, 'SUGESTAO'],
  [/d[uú]vida|pergunta|question/i, 'DUVIDA'],
  [/pend[eê]ncia|pending/i, 'PENDENCIA'],
]

/** The triage of a PR review in the *pr-triage* reference format; null without the comments table. */
export function parsePrTriage(text: string, file = '', round = 0): PrTriage | null {
  const src = text.replace(/\r\n/g, '\n')
  const rows = tableRows(parseSection(src, R('{comments}'))).filter(r => /^C\d+$/.test(clean(col(r, /^c$/))))
  if (!rows.length) return null
  const published = parseSection(src, R('^##\\s+{published}'))
  const comments: PrComment[] = rows.map(r => {
    const id = clean(col(r, /^c$/))
    const situation = clean(col(r, R('{situationCol}')))
    // the draft: `### C1 — title` followed by the `> …` block
    const at = src.search(new RegExp(`^###\\s+${id}\\b`, 'm'))
    const lines = at < 0 ? [] : src.slice(at).split('\n')
    const heading = lines[0] ?? ''
    const body = lines.slice(1)
    const end = body.findIndex(l => /^#{1,3}\s/.test(l))
    const quote = (end < 0 ? body : body.slice(0, end)).filter(l => l.startsWith('>')).map(l => l.replace(/^>\s?/, ''))
    const sev = col(r, /^sev/)
    const declined = R('{declined}').test(situation)
    return {
      id,
      pr: clean(col(r, /^pr$/)),
      severity: PR_SEVERITY.find(([re]) => re.test(sev))?.[1] ?? clean(sev).toUpperCase(),
      where: clean(col(r, R('{fileCol}'))).replace(/`/g, ''),
      origins: clean(col(r, R('{originCol}'))).split(/\s*(?:,|\+| e | and )\s*/).filter(Boolean),
      recommendation: clean(col(r, R('{recommendationCol}'))),
      situation,
      published: (!declined && R('{publishedWord}').test(situation)) || new RegExp(`(^|\\W)${id}:`, 'm').test(published),
      declined,
      title: clean(heading.replace(new RegExp(`^###\\s+${id}\\s*[—–-]?\\s*`), '')),
      draft: quote.join('\n').trim(),
    }
  })
  return { file, round, comments, outside: parseSection(src, R('{outsidePrs}')) }
}

// ---------------------------------------------------------------------------------------------------------------
// Acceptance criteria, test plan and results

/** The acceptance criteria of `## Acceptance criteria…` (plan or card summary). */
export function parseCriteria(text: string): Criterion[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const start = lines.findIndex(l => R('^#{2,3}\\s+{acceptanceCriteria}').test(l))
  if (start < 0) return []
  const level = (/^(#+)/.exec(lines[start] ?? '')?.[1] ?? '##').length
  const out: Criterion[] = []
  for (let i = start + 1; i < lines.length; i++) {
    const line = lines[i] ?? ''
    const h = /^(#+)\s/.exec(line)
    if (h && (h[1] ?? '').length <= level) break
    const item = /^\s*(?:[-*]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)(.+)$/.exec(line)
    if (!item?.[1] || /^\s{2,}/.test(line)) continue
    const raw = clean(item[1])
    const id = /^(CA?\d+[a-z]?)\b[:.)\s—–-]*/i.exec(raw)
    out.push({
      id: id?.[1]?.toUpperCase() ?? `CA${out.length + 1}`,
      text: cut(id ? raw.slice(id[0].length) : raw, 220),
      how: [],
      result: '',
      evidence: '',
    })
  }
  return out
}

/**
 * Numbered items of a prefix (`CA`, `RN`, `CN`) in any section of the plan: bullets `- RN1: text` or table
 * rows `| RN1 | text |`. The first of each id wins.
 */
export function parseItems(text: string, prefix: 'CA' | 'RN' | 'CN'): { id: string; text: string }[] {
  const out = new Map<string, string>()
  const item = new RegExp(`^\\s*(?:[-*]\\s+(?:\\[[ xX]\\]\\s+)?|\\d+[.)]\\s+)?\\**(${prefix}\\d+[a-z]?)\\**\\s*[:.)—–-]\\s*(.+)$`, 'i')
  const row = new RegExp(`^\\|\\s*\\**(${prefix}\\d+[a-z]?)\\**\\s*\\|\\s*([^|]+)\\|`, 'i')
  // the test plan matrix: `| CA1 | CN1 — name | …`
  const cell = new RegExp(`^\\|.*?\\|\\s*\\**(${prefix}\\d+[a-z]?)\\**\\s*[—–-]\\s*([^|]+)\\|`, 'i')
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    const m = item.exec(line) ?? row.exec(line) ?? cell.exec(line)
    const id = m?.[1]?.toUpperCase()
    if (!id || out.has(id)) continue
    out.set(id, cut(clean(m?.[2] ?? ''), 220))
  }
  return [...out].map(([id, t]) => ({ id, text: t }))
}

/** The status of each id in the coverage file (`| CA1 | covered | evidence |`). */
export function parseCoverage(text: string): Record<string, CoverageItem['status']> {
  const out: Record<string, CoverageItem['status']> = {}
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    const cells = line.startsWith('|') ? line.split('|').slice(1, -1).map(c => clean(c).toLowerCase()) : []
    const id = /^((?:ca|rn|cn)\d+[a-z]?)$/.exec(cells[0] ?? '')?.[1]
    if (!id) continue
    const st = cells[1] ?? ''
    out[id.toUpperCase()] = R('{covered}').test(st) ? 'covered' : R('{implemented}').test(st) ? 'implemented' : 'missing'
  }
  return out
}

const HOW = /\b(auto-api|auto-browser|auto-suite|manual|automatizado(?: \(build\))?|removido)(?![\w-])/i

/** How each criterion is proved, by the test plan matrix (`Type` or `How` column). */
export function parseTestMatrix(text: string): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  let inMatrix = false
  let howCol = -1
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    if (/^#{2,3}\s/.test(line)) inMatrix = R('{matrix}').test(line)
    if (!inMatrix || !line.startsWith('|')) continue
    const cells = line.split('|').slice(1, -1).map(c => clean(c))
    if (/^(CA|Crit)/i.test(cells[0] ?? '') && cells.some(c => R('^{howCol}$').test(c))) {
      howCol = cells.findIndex(c => R('^{howCol}$').test(c))
      continue
    }
    for (const id of (cells[0] ?? '').match(/\bCA?\d+[a-z]?\b/gi) ?? []) {
      const how = (howCol >= 0 ? cells[howCol] : cells.at(-1)) ?? ''
      const v = HOW.exec(how)?.[1]?.toLowerCase()
      if (!v) continue
      const key = id.toUpperCase()
      out[key] = [...new Set([...(out[key] ?? []), v])]
    }
  }
  return out
}

/** Verdicts per criterion in a test report (qa-*, orchestrator-test-*, e2e-result-*): the last one wins. */
export function parseVerdicts(text: string): Record<string, { result: string; evidence: string }> {
  const out: Record<string, { result: string; evidence: string }> = {}
  const verdict = (s: string) =>
    /✅|\bmet\b|\bpassou\b|\bpassed\b|\bok\b/i.test(s) && !/not_met|não passou|not passed/i.test(s)
      ? 'met'
      : /❌|not_met|falhou|não passou|\bfailed\b|not passed/i.test(s)
        ? 'failed'
        : /pending_manual|⏳|pendente|\bpending\b/i.test(s)
          ? 'pending'
          : /needs_orchestrator/i.test(s)
            ? 'orchestrator'
            : /doubt|dúvida|question/i.test(s)
              ? 'doubt'
              : ''
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    const ids = line.match(/\bCA?\d+[a-z]?\b/gi)
    if (!ids || !/^\s*[|-]/.test(line)) continue
    const result = verdict(line)
    if (!result) continue
    const evidence = cut(clean(line.replace(/^\s*[-|]\s*/, '').replace(/\|/g, ' · ')), 160)
    for (const id of ids) out[id.toUpperCase()] = { result, evidence }
  }
  return out
}

// ---------------------------------------------------------------------------------------------------------------
// Manual test script

export function parseTestScript(text: string): ManualStep[] {
  const out: ManualStep[] = []
  let cols: string[] = []
  let section = ''
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    const h = /^#{2,3}\s+(?:\d+[.)]\s*)?(.+)$/.exec(line)
    if (h) {
      section = clean(h[1] ?? '')
      cols = []
      continue
    }
    if (!line.startsWith('|')) continue
    const cells = line.split('|').slice(1, -1).map(c => c.trim())
    const lower = cells.map(c => clean(c).toLowerCase())
    if (lower.some(c => R('^{stepCol}$').test(c)) && lower.some(c => R('{expectedCol}|^{whoCol}$').test(c))) {
      cols = lower
      continue
    }
    if (!cols.length || /^-+$/.test((cells[0] ?? '').replace(/[:\s]/g, ''))) continue
    const at = (re: RegExp) => cells[cols.findIndex(c => re.test(c))] ?? ''
    const result = at(R('^{resultCol}'))
    out.push({
      id: clean(cells[0] ?? ''),
      step: cut(clean(at(R('^{stepCol}$'))), 200),
      expected: cut(clean(at(R('{expectedCol}'))), 200),
      result: result.includes('✅') ? '✅' : result.includes('❌') ? '❌' : '',
      note: cut(clean(result.replace(/[✅❌]/g, '')), 120),
      section,
      removed: cells.some(c => R('\\b{removed}\\b').test(c)),
      criteria: [...at(R('^{criterionCol}')).matchAll(/\b(CA|RN|CN)\s*0*(\d+)\b/g)].map(m => `${m[1]}${m[2]}`),
      how: clean(at(/^(como|how)$/i)).toLowerCase(),
    })
  }
  return out
}

// ---------------------------------------------------------------------------------------------------------------
// Levantamento


/** Card points: the survey table (`| P01 | point | ✅ confirmed | evidence |`) or the points file. */
export function parsePoints(survey: string, pontos: string): Point[] {
  const out: Point[] = []
  for (const line of survey.replace(/\r\n/g, '\n').split('\n')) {
    if (!/^\|\s*P\d+/.test(line)) continue
    const cells = line.split('|').slice(1, -1).map(c => clean(c))
    out.push({ id: cells[0] ?? '', text: cut(cells[1] ?? '', 200), verdict: cells[2] ?? '', evidence: cut(cells[3] ?? '', 120) })
  }
  if (out.length) return out
  for (const line of pontos.replace(/\r\n/g, '\n').split('\n')) {
    const m = /^\s*[-*]?\s*(P\d+)\s*[—–-]\s*(.+?)(?:\s+[—–-]\s+(?:origem|origin):.*)?$/.exec(line)
    if (m) out.push({ id: m[1] ?? '', text: cut(clean(m[2] ?? ''), 200), verdict: '', evidence: '' })
  }
  return out
}

/** `**Suggested story points:**` followed by bullets `- **13** if…` / `- **8** if…` → `8–13`. */
function pointsFromList(text: string): string {
  const list = /Story points[^\n]*:\**\s*\n((?:\s*-[^\n]*\n?)+)/i.exec(text)?.[1] ?? ''
  const values = [...list.matchAll(/^\s*-\s*\*\*(\d+)\*\*/gm)].map(m => Number(m[1])).sort((a, b) => a - b)
  if (!values.length) return ''
  const lo = values[0]
  const hi = values.at(-1)
  return lo === hi ? String(lo) : `${lo}–${hi}`
}

export function parseEstimate(text: string): Estimate {
  const line = R('\\*\\*{estimate}:\\*\\*\\s*([^\\n]+)', '').exec(text)?.[1] ?? ''
  const pick = (re: RegExp, src = text) => clean(re.exec(src)?.[1] ?? '')
  const total = /\|\s*\**Total dev\**\s*\|\s*\**([^|*\n]+)/i.exec(text)?.[1] ?? ''
  const qa = /\|\s*QA[^|]*\|\s*\**([^|*\n]+)/i.exec(text)?.[1] ?? ''
  const card = R('{cardIs}\\s*\\**(\\d+)\\s*SP(\\s*{orMore})?').exec(text)
  const split = pick(/Total\s*\**\s*≈?\s*(\d+\s*SP)/i)
  return {
    sp: pick(/(\d+(?:\s*[-–]\s*\d+)?|>\s*13)\s*SP\b/i, line) || pick(R('{recommendation}:\\s*(\\d+(?:\\s*[-–]\\s*\\d+)?)\\s*SP')) ||
      pointsFromList(text) || pick(/\bStory points:\**\s*([^\n—]+)/i) || pick(/(\d+(?:\s*[-–]\s*\d+)?)\s*SP\b/),
    hours: pick(/·\s*([\d,.]+\s*[-–]\s*[\d,.]+\s*h)\b/, line) || pick(/\*\*Total[^|]*\*\*\s*\|\s*\**([^|*\n]+)/i),
    complexity: pick(R('{complexity}\\s*:?\\s*\\**([A-Za-zÀ-ú ]+?)\\**\\s*(?:[·—,\\n]|$)'), line) ||
      pick(R('\\*\\*{complexity}:\\*\\*\\s*([^—\\n]+)')),
    confidence: pick(R('{confidence}\\s*:?\\s*\\**([A-Za-zÀ-ú]+)'), line) || pick(R('\\*\\*{confidence}:\\*\\*\\s*([^—\\n]+)')),
    spCard: card ? `${card[1]}${card[2] ? '+' : ''} SP` : '',
    spSplit: split ? `≈ ${split}` : '',
    devDays: clean(total.replace(/≈\s*/, '')),
    qaDays: clean(qa.replace(/≈\s*/, '')),
    level: pick(R('{aidwLevel}:\\**\\s*\\**([a-zçã]+)')),
    passes: cut(pick(R('{extraPasses}:\\**\\s*([^\\n]+)')), 160),
    risks: parseRisks(text),
  }
}

/** `- **Risks:**` with the text on the line and/or the indented sub-bullets; in the old model, the `## Risks` section. */
function parseRisks(text: string): string {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const head = R('^\\s*[-*]\\s*\\*\\*{risks}:?\\*\\*:?\\s*')
  const i = lines.findIndex(l => head.test(l))
  if (i < 0) return parseSection(text, R('^##\\s+(?:\\d+\\.\\s*)?{risks}'))
  const sub: string[] = []
  for (let j = i + 1; j < lines.length && /^\s+\S/.test(lines[j] ?? ''); j++) sub.push(lines[j] ?? '')
  const indent = Math.min(...sub.map(l => /^\s*/.exec(l)?.[0].length ?? 0))
  return [(lines[i] ?? '').replace(head, '').trim(), ...sub.map(l => l.slice(indent))].filter(Boolean).join('\n')
}

/** "1,5–2" → [1.5, 2]; "3" → [3, 3]. */
function range(s: string): [number, number] | null {
  const nums = [...s.matchAll(/\d+(?:,\d+)?/g)].map(m => Number((m[0] ?? '').replace(',', '.')))
  if (!nums.length) return null
  return [nums[0] ?? 0, nums.at(-1) ?? 0]
}

/** The body of a `## <title>` section up to the next one of the same level or above, without blank lines at the ends. */
export function parseSection(text: string, title: RegExp): string {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const start = lines.findIndex(l => /^##\s/.test(l) && title.test(l))
  if (start < 0) return ''
  const end = lines.findIndex((l, i) => i > start && /^#{1,2}\s/.test(l))
  return lines.slice(start + 1, end < 0 ? undefined : end).join('\n').trim()
}

/** What the card asks: the `**Card:**` paragraph of the survey. */
export function parseCardAsk(text: string): string {
  const m = /\*\*Card:\*\*\s*([\s\S]*?)(?:\n\s*\n|\n\|)/.exec(text.replace(/\r\n/g, '\n'))
  return cut(clean(m?.[1] ?? ''), 600)
}

/**
 * The "Today in code | For the demand | Situation" rows of the survey. Without the situation column (old
 * model), it comes from the text: "no change", "nothing to reuse", "the pain", otherwise "must change".
 */
export function parseCardPoints(text: string): CardPoint[] {
  const out: CardPoint[] = []
  let cols: string[] = []
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    if (!line.startsWith('|')) {
      if (cols.length && line.trim()) cols = []
      continue
    }
    const cells = line.split('|').slice(1, -1).map(c => c.trim())
    const lower = cells.map(c => clean(c).toLowerCase())
    if (lower.some(c => R('^{todayInCode}').test(c))) {
      cols = lower
      continue
    }
    if (!cols.length || /^-+$/.test((cells[0] ?? '').replace(/[:\s]/g, ''))) continue
    const effect = clean(cells[1] ?? '')
    const col = cols.findIndex(c => R('{situationCol}').test(c))
    const given = col >= 0 ? clean(cells[col] ?? '').toLowerCase() : ''
    const situation = given || situationOf(effect)
    out.push({ today: cut(clean(cells[0] ?? ''), 260), effect: cut(effect, 200), situation })
  }
  return out
}

/** The effort blocks (`| Block | Dev (days) |`), without the total and without QA. */
export function parseEffort(text: string): EffortBlock[] {
  const out: EffortBlock[] = []
  let inTable = false
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    if (!line.startsWith('|')) {
      inTable = false
      continue
    }
    const cells = line.split('|').slice(1, -1).map(c => clean(c))
    if (R('^{block}$').test(cells[0] ?? '') && R('{days}').test(cells[1] ?? '')) {
      inTable = true
      continue
    }
    if (!inTable || /^-+$/.test((cells[0] ?? '').replace(/[:\s]/g, '')) || /^total|^qa\b/i.test(cells[0] ?? '')) continue
    const r = range(cells[1] ?? '')
    if (r) out.push({ name: cut(cells[0] ?? '', 60), min: r[0], max: r[1], label: (cells[1] ?? '').replace(/\s/g, '') })
  }
  return out
}

/** The split recommendation (`| # | Item | SP |`). */
export function parseSplit(text: string): SplitItem[] {
  const out: SplitItem[] = []
  let inTable = false
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    const row = line.trim()
    if (!row.startsWith('|')) {
      if (row) inTable = false
      continue
    }
    const cells = row.split('|').slice(1, -1).map(c => clean(c))
    if (cells[0] === '#' && /^sp$/i.test(cells.at(-1) ?? '')) {
      inTable = true
      continue
    }
    if (!inTable || !/^\d+$/.test(cells[0] ?? '')) continue
    out.push({ n: cells[0] ?? '', text: cut(cells[1] ?? '', 160), sp: cells.at(-1) ?? '' })
  }
  return out
}

/**
 * The questions of the `## Open questions…` section: `- **D1. question** context` (the following indented lines are also
 * context), in `**Theme**` groups, with `*For:*` and `*Changes the estimate:*` when the survey has them; or the old
 * numbered model (`1. question *Why it matters:* … *For:* …`).
 */
export function parseDoubts(text: string): Doubt[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const start = lines.findIndex(l => R('^#{2,3}\\s+(\\d+\\.\\s*)?{openQuestions}').test(l))
  if (start < 0) return []
  const out: Doubt[] = []
  let group = ''
  const tail = (s: string, re: RegExp) => clean(re.exec(s)?.[1] ?? '')
  const TO = R('\\*{for}:\\*\\s*([^*\\n]+?)(?:\\s*\\*|$)')
  const AFFECTS = R('\\*{changesEstimate}:\\*\\s*([^*\\n]+?)(?:\\s*\\*|$)')
  const WHY = R('\\*{whyItMatters}:\\*')
  for (let i = start + 1; i < lines.length && !/^#{1,2}\s/.test(lines[i] ?? ''); i++) {
    const line = lines[i] ?? ''
    const g = /^\s*\*\*([^*]+)\*\*\s*$/.exec(line)
    if (g) {
      group = clean(g[1] ?? '')
      continue
    }
    if (/^\s*[-*]\s+\*\*D\d+\./.test(line)) {
      // The bold question may wrap: join the indented lines before looking for the `**` that closes it.
      let item = line.trim()
      while (i + 1 < lines.length && /^\s{2,}\S/.test(lines[i + 1] ?? '') && !/^\s*[-*]\s+\*\*D\d+/.test(lines[i + 1] ?? '')) {
        i += 1
        item += ` ${(lines[i] ?? '').trim()}`
      }
      const d = /^[-*]\s+\*\*D(\d+)\.\s*(.*?)\*\*\s*(.*)$/.exec(item)
      if (!d) continue
      const rest = d[3] ?? ''
      const why = clean(rest.replace(R('\\*{for}:\\*.*$'), '').replace(R('\\*{changesEstimate}:\\*.*$'), ''))
      out.push({
        n: Number(d[1]),
        id: `D${d[1]}`,
        // Answered (`**D3.** answer`): the bold only has the number, and the answer is the text of the line.
        question: cut(clean(d[2] ?? '') || why, 240),
        why: d[2] ? cut(why, 320) : '',
        to: tail(rest, TO),
        group,
        affects: tail(rest, AFFECTS),
      })
      continue
    }
    const m = /^\s*(\d+)[.)]\s+(.+)$/.exec(line)
    if (!m) continue
    const rest = m[2] ?? ''
    out.push({
      n: Number(m[1]),
      id: `D${m[1]}`,
      question: cut(clean(rest.replace(new RegExp(`${WHY.source}.*$`, 'i'), '').replace(R('\\*{for}:\\*.*$'), '')), 240),
      why: cut(clean(new RegExp(`${WHY.source}\\s*([^*]+)`, 'i').exec(rest)?.[1] ?? ''), 200),
      to: clean(R('\\*{for}:\\*\\s*([^.*\\n]+)').exec(rest)?.[1] ?? /\(([^)]*(?:PO|Tech Lead|time|team|QA)[^)]*)\)\s*$/i.exec(rest)?.[1] ?? ''),
      group,
      affects: tail(rest, AFFECTS),
    })
  }
  return out
}

// ---------------------------------------------------------------------------------------------------------------
// Plano e arquivos

/** `Level:` and `Extra passes:` of the plan. */
export function parsePlanMeta(text: string): { level: string | null; passes: string; version: string } {
  const h1 = /^#\s+(.+)$/m.exec(text)?.[1] ?? ''
  return {
    level: R('{level}:\\**\\s*\\**\\s*(trivial|simples|padrao|complexa|critica)').exec(text)?.[1]?.toLowerCase() ?? null,
    passes: cut(clean(R('{extraPasses}:\\**\\s*([^\\n]+)').exec(text)?.[1] ?? ''), 160),

    version: /\bv(\d+(?:\.\d+)?)\b/.exec(h1)?.[1] ?? '',
  }
}

/** The latest file of a family (`review-*-rN.md` → highest N). */
export function latest(files: string[], re: RegExp): { file: string; n: number } | null {
  let best: { file: string; n: number } | null = null
  for (const f of files) {
    const m = re.exec(f)
    if (!m) continue
    const n = Number(m[1] ?? 0)
    if (!best || n > best.n) best = { file: f, n }
  }
  return best
}

export type Artifact = { file: string; group: string }
