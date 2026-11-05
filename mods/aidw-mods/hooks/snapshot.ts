// The picture of the demand that the panels and the strip show, built from the folder's files. Pure: `wanted` says
// which files to read, register.tsx reads and hands over the texts, `buildSnapshot` builds it.

import type { CoverageItem, Finding, ManualStep, PrTriage, Repo, Snapshot } from '../types'
import { budgetFor, parseDelegations, parseOrchestrator, roundFor } from './aidw'
import {
  decisionOf,
  kindOf,
  latest,
  parseCardAsk,
  parseCardPoints,
  parseCoverage,
  parseCriteria,
  parseDoubts,
  parseEffort,
  parseEstimate,
  parseFindings,
  parseItems,
  parsePlanMeta,
  parsePoints,
  parsePrTriage,
  parseTestScript,
  parseSection,
  parseSplit,
  parseTestMatrix,
  parseTriage,
  parseVerdicts,
  progress,
  timeline,
  waitingFor,
} from './artifacts'
import type { DemandFile, ExternalStep } from './artifacts'
import { isPlanFile } from './artifacts'
import { t, tk } from './i18n'
import { FILE_NAME, FILE_PREFIX, fam, pick, re as R } from './names'

// File families: the English names and the old Portuguese ones (names.ts).
const rx = (source: string) => new RegExp(source)
const REVIEW = /^review-.*-r(\d+)\.md$/
const PLAN_REVIEW = rx(`^${fam('planReview')}-.*-r(\\d+)\\.md$`)
const BUGS = rx(`^${fam('bugs')}-.*-r(\\d+)\\.md$`)
const SECURITY = rx(`^${fam('security')}-.*-r(\\d+)\\.md$`)
const TRIAGE = rx(`^${fam('triage')}-(?!${fam('planTag')}-).*-r(\\d+)\\.md$`)
const PLAN_TRIAGE = rx(`^${fam('triage')}-${fam('planTag')}-.*-r(\\d+)\\.md$`)
const REPORT = rx(`^${fam('report')}-.*-r(\\d+)\\.md$`)
const SUMMARY = rx(`^${fam('summary')}.*\\.md$`)
const TEST_SCRIPT = rx(`^${fam('testScript')}.*\\.md$`)
const TEST_PLAN = rx(`^${fam('testPlan')}-.*\\.md$`)
const SURVEY = rx(`^${fam('survey')}-.*\\.md$`)
const POINTS = rx(`^${fam('points')}-.*\\.md$`)
const COVERAGE = rx(`^${fam('coverage')}-.*\\.md$`)
const E2E = rx(`^${fam('e2e')}.*\\.md$`)

/** The current plan: `plan-<id>.md` (no `-vN`); without it, the highest version. */
function planFile(files: string[]): string | null {
  const plans = files.filter(isPlanFile)
  return plans.find(f => !/-v\d+(\.\d+)?\.md$/.test(f)) ?? latest(plans, /-v(\d+)(?:\.\d+)?\.md$/)?.file ?? null
}

/** The current test plan, with the same rule as the plan. */
function testPlanFile(files: string[]): string | null {
  const all = files.filter(f => TEST_PLAN.test(f))
  return all.find(f => !/-v\d+(\.\d+)?\.md$/.test(f)) ?? latest(all, /-v(\d+)(?:\.\d+)?\.md$/)?.file ?? null
}

/** A file that starts with the English prefix of its family (`summary-`, not `resumo-`). */
const ENGLISH = rx(`^(?:${Object.values(FILE_PREFIX).map(v => v[0]).join('|')})-`)

/** The last file of a family by name; when both exist (`summary-…` and `resumo-…`), the English one. */
const first = (files: string[], re: RegExp) => {
  const all = files.filter(f => re.test(f)).sort()
  return all.filter(f => ENGLISH.test(f)).at(-1) ?? all.at(-1) ?? null
}

/** The files `buildSnapshot` needs to read. */
export function wanted(files: string[]): string[] {
  const out = new Set<string>()
  const add = (f: string | null | undefined) => f && out.add(f)
  add(pick(files, FILE_NAME.metrics))
  add(pick(files, FILE_NAME.orchestratorMetrics))
  add(planFile(files))
  add(testPlanFile(files))
  add(first(files, SUMMARY))
  add(first(files, TEST_SCRIPT))
  add(first(files, SURVEY))
  add(first(files, POINTS))
  add(first(files, COVERAGE))
  add(latest(files, REPORT)?.file)
  for (const f of files) if (E2E.test(f)) add(f)
  for (const re of [REVIEW, PLAN_REVIEW, BUGS, SECURITY, TRIAGE, PLAN_TRIAGE]) for (const f of files) if (re.test(f)) add(f)
  return [...out]
}

export type SnapshotInput = {
  dir: string
  demand: DemandFile
  files: string[]
  texts: Record<string, string>
  /** Steps outside the context (`runtime.json` → `external_steps`). */
  externalSteps?: ExternalStep[]
}

/** The triage of the last round of a PR review, when it follows the *pr-triage* reference. */
function prTriageOf(kind: string, files: string[], text: (f: string) => string): PrTriage | null {
  if (kind !== 'pr-review') return null
  const last = files
    .map(f => ({ f, n: Number(TRIAGE.exec(f)?.[1] ?? NaN) }))
    .filter(x => !Number.isNaN(x.n))
    .sort((a, b) => a.n - b.n)
    .at(-1)
  return last ? parsePrTriage(text(last.f), last.f, last.n) : null
}

export function buildSnapshot(input: SnapshotInput): Snapshot {
  const { dir, demand, files, texts } = input
  const text = (f: string | null | undefined) => (f ? (texts[f] ?? '') : '')
  const kind = kindOf(demand, files)
  const step = demand.step ?? 'UNDERSTAND'
  const metricsFile = pick(files, FILE_NAME.metrics)
  const orchestratorFile = pick(files, FILE_NAME.orchestratorMetrics)
  const delegations = parseDelegations(text(metricsFile))
  const plan = parsePlanMeta(text(planFile(files)))
  const level = plan.level ?? delegations.at(-1)?.level ?? null
  const { round, kind: roundKind } = roundFor(step, files, demand.loop)

  // findings: every round, with each round's triage
  const findings: Finding[] = []
  // each round's triage applies to that round's findings (the same id comes back in later rounds)
  const decisions: Record<string, string> = {}
  const published = new Set<string>()
  for (const f of files) {
    for (const [re, source] of [[REVIEW, 'review'], [PLAN_REVIEW, 'plan'], [BUGS, 'bugs'], [SECURITY, 'security']] as const) {
      const m = re.exec(f)
      if (m) findings.push(...parseFindings(text(f), Number(m[1]), source, f))
    }
    const tri = TRIAGE.exec(f) ?? PLAN_TRIAGE.exec(f)
    if (tri) {
      const parsed = parseTriage(text(f))
      const plan = PLAN_TRIAGE.test(f) ? 'p' : 'c'
      for (const [id, d] of Object.entries(parsed.decisions)) {
        decisions[`${plan}${tri[1]}:${id}`] = d
        decisions[id] ??= d
      }
      for (const id of parsed.published) published.add(id)
    }
  }
  for (const f of findings) {
    f.triage = decisions[`${f.source === 'plan' ? 'p' : 'c'}${f.round}:${f.id}`] ?? decisions[f.id] ?? ''
    f.published = published.has(f.id)
    f.decision = decisionOf(f.triage)
    f.recommendation = f.triage || f.recommendation
  }
  // a finding the next round of the same review reports as fixed: "fixed in rN"
  const family = (f: Finding) => f.file.replace(/-r\d+\.md$/, '')
  for (const f of findings) {
    if (f.title) continue
    const earlier = findings.find(g => family(g) === family(f) && g.id === f.id && g.round < f.round && g.title)
    f.title = earlier?.title ?? (f.status ? t('finding.restated', { status: f.status }) : t('finding.noDescription'))
    if (!f.where) f.where = earlier?.where ?? ''
  }
  for (const f of findings) {
    if (/corrig|fixed|resolv/.test(f.status)) continue
    const later = findings.find(g => family(g) === family(f) && g.id === f.id && g.round > f.round && /corrig|fixed|resolv/.test(g.status))
    if (later) f.status = t('finding.fixedIn', { round: later.round })
  }
  findings.sort((a, b) => a.round - b.round || a.id.localeCompare(b.id))

  // criteria: from the plan (development) or the card summary; how to prove them and the result of the reports
  const criteria = parseCriteria(text(planFile(files))).length
    ? parseCriteria(text(planFile(files)))
    : parseCriteria(text(first(files, SUMMARY)))
  const how = parseTestMatrix(text(testPlanFile(files)))
  const verdicts = {
    ...Object.assign({}, ...files.filter(f => E2E.test(f)).sort().map(f => parseVerdicts(text(f)))),
    ...parseVerdicts(text(latest(files, REPORT)?.file)),
  } as Record<string, { result: string; evidence: string }>
  for (const c of criteria) {
    c.how = how[c.id] ?? []
    c.result = verdicts[c.id]?.result ?? ''
    c.evidence = verdicts[c.id]?.evidence ?? ''
  }

  // criteria, rules and scenarios (CA/RN/CN) with the coverage by our code and tests
  const planText = text(planFile(files))
  const testScript = first(files, TEST_SCRIPT) ?? ''
  const manual = parseTestScript(text(testScript))
  const coverageFile = first(files, COVERAGE)
  // demands from before flow v3 have the coverage file; in the new ones the status comes from the plan, the step and the test script
  const status = coverageFile ? parseCoverage(text(coverageFile)) : derivedCoverage(planText, demand, manual)
  const coverage: CoverageItem[] = []
  for (const kind of ['CA', 'RN', 'CN'] as const) {
    const items = parseItems(`${planText}\n${text(testPlanFile(files))}`, kind)
    const list = items.length || kind !== 'CA' ? items : criteria.map(c => ({ id: c.id, text: c.text }))
    for (const it of list) coverage.push({ id: it.id, kind, text: it.text, status: status[it.id] ?? 'missing' })
  }

  const surveyFile = first(files, SURVEY) ?? ''
  const lev = text(surveyFile)
  const repos: Repo[] = (demand.repos ?? []).map(r => ({
    name: (r.repo ?? r.path ?? '').replace(/\\/g, '/').split('/').pop() ?? '',
    path: (r.path ?? '').replace(/\\/g, '/'),
    branch: r.branch ?? '',
    base: r.base ?? '',
    pr: r.pr ?? '',
    source: r.source ?? '',
  }))

  return {
    dir,
    id: demand.id ?? dir.split('/').pop() ?? dir,
    title: demand.title ?? '',
    kind,
    step,
    status: demand.status ?? 'active',
    note: (demand.note ?? '').trim(),
    summary: (demand.summary ?? '').trim(),
    waiting: waitingFor(step),
    timeline: timeline(kind, demand),
    progress: progress(kind, demand, input.externalSteps),
    repos,
    level,
    passes: plan.passes,
    planVersion: plan.version,
    round,
    roundKind,
    delegations,
    tokens: delegations.reduce((n, d) => n + d.tokens, 0),
    orchestrator: parseOrchestrator(text(orchestratorFile)),
    budget: budgetFor(level),
    findings,
    prTriage: prTriageOf(kind, files, f => text(f)),
    criteria,
    coverage,
    coverageRecorded: !!coverageFile || !!planText,
    manual,
    testScript,
    points: parsePoints(lev, text(first(files, POINTS))),
    cardAsk: parseCardAsk(lev),
    cardPoints: parseCardPoints(lev),
    effort: parseEffort(lev),
    split: parseSplit(lev),
    estimate: lev ? parseEstimate(lev) : null,
    doubts: parseDoubts(lev),
    touches: parseSection(lev, R('{touches}')),
    surveyFile,
    testMarks: null,
  }
}

/** The steps at which the delivery is already implemented (the code exists, even if not tested yet). */
const IMPLEMENTED_STEPS = new Set([
  'REVIEW', 'TRIAGE', 'CODER_FIX', 'USER_REVIEW', 'TEST', 'TEST_ADJUST', 'MANUAL_TEST', 'PR', 'CODE_REVIEW', 'QA_TEST',
  'UX_VALIDATION', 'DONE', 'PREPARE_REVIEW', 'ORCHESTRATOR_TEST', 'DOCS', 'FINAL_REVIEW',
])

/**
 * Coverage without a file (flow v3): *covered* when a test script step that proves the item has ✅; *implemented*
 * when the demand is past implementation and the item is in a plan delivery (`Covers:`/`Cobre:`), or in
 * any delivery when the plan does not say; otherwise *missing*.
 */
export function derivedCoverage(plan: string, demand: DemandFile, manual: ManualStep[]): Record<string, CoverageItem['status']> {
  const out: Record<string, CoverageItem['status']> = {}
  const past = IMPLEMENTED_STEPS.has(demand.step ?? '') || (demand.history ?? []).some(h => IMPLEMENTED_STEPS.has(h.step))
  if (past) {
    const covered = [...plan.matchAll(R('^[-*\\s]*(?:\\*\\*)?{covers}(?:\\*\\*)?:?\\s*(?:\\*\\*)?([^\\n·]+)', 'gim'))]
      .flatMap(m => [...(m[1] ?? '').matchAll(/\b(CA|RN|CN)\s*0*(\d+)\b/g)].map(x => `${x[1]}${x[2]}`))
    const ids = covered.length ? covered : [...plan.matchAll(/\b(CA|RN|CN)\s*0*(\d+)\b/g)].map(x => `${x[1]}${x[2]}`)
    for (const id of ids) out[id] = 'implemented'
  }
  for (const step of manual) {
    if (step.removed || step.result !== '✅') continue
    for (const id of step.criteria) out[id] = 'covered'
  }
  return out
}

/** The phase the demand is in, by the timeline name (Review, Final review…). */
export function phaseOf(s: Snapshot): string {
  return s.timeline.find(x => x.state === 'current')?.name ?? s.timeline.filter(x => x.state === 'done').at(-1)?.name ?? s.step
}

/** What the AiDW is doing at each step (i18n key `doing.<first step>`). */
const DOING: string[][] = [
  ['UNDERSTAND'],
  ['EXPLORE'],
  ['PLAN', 'SPEC'],
  ['PLAN_REVIEW'],
  ['PLAN_FIX'],
  ['TICKETS'],
  ['IMPLEMENT', 'TEST_PLAN'],
  ['TEST_ADJUST'],
  ['TEST', 'ORCHESTRATOR_TEST'],
  ['REVIEW', 'PREPARE_REVIEW'],
  ['CODER_FIX'],
  ['DOCS'],
  ['ESTIMATE'],
  ['RETURN'],
]

const YOUR_STEPS = new Set(['HUMAN_APPROVAL', 'PLAN_APPROVAL', 'TRIAGE', 'USER_REVIEW', 'MANUAL_TEST', 'PR'])

/** The next step in one sentence: what you do, or what the AiDW is doing. */
export function nextStep(s: Snapshot): { you: boolean; text: string } {
  if (s.status === 'paused') return { you: true, text: t('next.paused', { id: s.id }) }
  if (s.step === 'DONE' || s.status === 'done') return { you: false, text: t('next.done') }
  if (YOUR_STEPS.has(s.step)) return { you: true, text: tk(`next.${s.step}`) }
  if (s.step === 'FINAL_REVIEW') {
    return { you: true, text: t(s.kind === 'pr-review' ? 'next.FINAL_REVIEW.pr' : s.kind === 'survey' ? 'next.FINAL_REVIEW.survey' : 'next.FINAL_REVIEW.dev') }
  }
  const doing = DOING.find(steps => steps.includes(s.step))?.[0]
  return { you: false, text: doing ? tk(`doing.${doing}`) : t('next.step', { step: s.step }) }
}

/** The agent `state` in words: "review_changes_requested" → "requested changes". */
export function stateLabel(state: string): string {
  const s = state.toLowerCase()
  if (!s || s === '—') return '—'
  if (s === 'missing_state') return t('state.missing')
  if (/changes_requested|findings/.test(s)) return /audit/.test(s) ? t('state.foundProblems') : t('state.changesRequested')
  if (/approved/.test(s)) return t('state.approved')
  if (/clean/.test(s)) return t('state.clean')
  if (/blocked/.test(s)) return t('state.blocked')
  if (/requires_approval|needs_input|question/.test(s)) return t('state.needsYou')
  if (/fail|error/.test(s)) return t('state.failed')
  if (/complete|done|ok$/.test(s)) return t('state.complete')
  return state
}

/** A short note about the demand, put back in the context after a compaction (in the chat language). */
export function stateNote(s: Snapshot): string {
  const open = s.findings.filter(f => f.round === s.round && /CRITICO|IMPORTANTE/.test(f.severity ?? '') && !/corrig|resolv|fixed/.test(f.status))
  return [
    t('note.title', { id: s.id }),
    t('note.use', { kind: s.kind, step: s.step, waiting: s.waiting ? t('note.waiting', { what: s.waiting }) : '' }),
    t('note.folder', { dir: s.dir, worktrees: s.repos.length ? t('note.worktrees', { list: s.repos.map(r => `${r.name} → ${r.path}`).join(', ') }) : '' }),
    s.roundKind ? t('note.loop', { kind: tk(`roundKind.${s.roundKind}`, s.roundKind), round: s.round }) : '',
    open.length ? t('note.open', { list: open.map(f => `${f.id} ${f.severity}`).join(', ') }) : '',
    t('note.delegations', { n: s.delegations.length, tokens: s.tokens }),
  ]
    .filter(Boolean)
    .join('\n')
}

