export type DemandKind = 'development' | 'pr-review' | 'survey'

export type TimelineItem = { name: string; state: 'done' | 'current' | 'pending'; visits: number }

/** A step of the progress bar of the demand map (docs/painel.md). */
export type ProgressStage = {
  name: string
  /** `aidw`: the AiDW works; `outside`: the team (Code review) or QA. */
  group: 'aidw' | 'outside'
  /** `with-team`: the outside step the demand is in; `returned`: the outside step that sent the work back. */
  state: 'done' | 'current' | 'pending' | 'with-team' | 'returned'
  /** Who has the demand at an outside step ("the team", "QA", "UX"). */
  who?: string
}

export type Progress = {
  stages: ProgressStage[]
  /** Name of the current step and its position (1…total). */
  current: string
  index: number
  total: number
  /** The outside step that sent the work back and has not been resumed yet (null when there is none). */
  returnedFrom: string | null
  /** How many times each outside step sent the work back ("Code review" → 1). */
  returns: Record<string, number>
}

export type Delegation = {
  date: string
  agent: string
  level: string
  model: string
  effort: string
  label: string
  state: string
  tools: number
  seconds: number
  tokens: number
  /** Cost in USD when the metrics file has it (Codex and headless); Claude's native subagent does not report it. */
  cost: number | null
}

/** A line of the orchestrator metrics file: the main chat in one session, with one model. */
export type OrchestratorRow = {
  session: string
  updated: string
  model: string
  turns: number
  seconds: number
  /** Input, cache written, cache read and output, summed. */
  tokens: number
  cacheWrite: number
  cacheRead: number
  output: number
  /** API price equivalent (not the subscription bill). */
  cost: number | null
}
/** A line of the *Per step* section of the orchestrator metrics file: the main chat turns at one step of the demand. */
export type OrchestratorStep = { step: string; turns: number; tokens: number; cost: number | null }
export type OrchestratorUsage = {
  rows: OrchestratorRow[]
  /** The *Per step* section (2026-11-04); empty in older files. */
  steps: OrchestratorStep[]
  turns: number
  tokens: number
  cost: number | null
}

export type Finding = {
  id: string
  round: number
  source: 'review' | 'plan' | 'bugs' | 'security'
  /** The category in the finding title (flow v3: the reviewer covers quality, bugs and security in one pass). */
  category: 'quality' | 'bug' | 'security' | ''
  /** The round file (review-us-1-r2.md, review-optimization-…-r1.md): separates Code from Optimization. */
  file: string
  severity: 'CRITICO' | 'IMPORTANTE' | 'SUGESTAO' | 'ELOGIO' | 'DUVIDA' | null
  where: string
  title: string
  status: string
  triage: string
  comment: string
  /** The PR of the comment draft (PR review): "1234", "1234 and 5678". */
  target: string
  published: boolean
  /** Code before and after (the reviewer's `**Before:**` and `**After:**` blocks); empty when the finding proposes no code. */
  before: string
  after: string
  /** The options of a question (`(a) …`, `(b) …`). */
  options: string[]
  /** The AiDW recommendation: the triage, or the reviewer's recommendation when there is no triage yet. */
  recommendation: string
  /** Decision from the triage: with you (pending), kept or discarded. */
  decision: 'pending' | 'kept' | 'discarded'
}

export type Criterion = { id: string; text: string; how: string[]; result: string; evidence: string }
/** An acceptance criterion, business rule or scenario, with the coverage by our code and our tests. */
export type CoverageItem = { id: string; kind: 'CA' | 'RN' | 'CN'; text: string; status: 'missing' | 'implemented' | 'covered' }
export type ManualStep = {
  id: string
  step: string
  expected: string
  result: '✅' | '❌' | ''
  note: string
  /** Section of the test script (`## 1. Card criteria` → "Card criteria"). */
  section: string
  /** Step marked as removed in the test script: hidden. */
  removed: boolean
  /** The criteria and rules the step proves (`Criterion` column: CA1, RN2). */
  criteria: string[]
  /** Como prova (coluna `Como`): auto-api, auto-browser, auto-suite ou manual. */
  how: string
}
export type Point = { id: string; text: string; verdict: string; evidence: string }
/** A row of the survey's "Card × code"; `situation` is shown as is (translated when synthesized). */
export type CardPoint = { today: string; effect: string; situation: string }
export type EffortBlock = { name: string; min: number; max: number; label: string }
export type SplitItem = { n: string; text: string; sp: string }
export type Estimate = {
  sp: string
  hours: string
  complexity: string
  confidence: string
  /** New survey model: SP of the card as is, split SP, dev and QA days, level and passes. */
  spCard: string
  spSplit: string
  devDays: string
  qaDays: string
  level: string
  passes: string
  /** The estimate's `**Risks:**` bullet (or the old model's `## Risks` section), in Markdown. */
  risks: string
}
export type Doubt = {
  n: number
  id: string
  question: string
  why: string
  to: string
  /** Theme (Scope and product, Contract…) and how much it changes the estimate ("+3 SP if migrating"). */
  group: string
  affects: string
}
/** A comment of the triage of a PR review (`C1`…; *pr-triage* reference). */
export type PrComment = {
  id: string
  pr: string
  severity: string
  where: string
  /** The findings it groups (`R1-01`, `B1-02`…). */
  origins: string[]
  recommendation: string
  /** How the triage says it stands: `to decide`, `not published (r1)`, `published (thread 23720), resolved in r2`… */
  situation: string
  published: boolean
  /** Decided not to publish in an earlier round. */
  declined: boolean
  title: string
  draft: string
}
export type PrTriage = { file: string; round: number; comments: PrComment[]; outside: string }

export type Repo ={ name: string; path: string; branch: string; base: string; pr: string; source: string }

/** Everything the panels and the strip show of a demand, re-read from disk on every change. */
export type Snapshot = {
  dir: string
  id: string
  title: string
  kind: DemandKind
  step: string
  status: string
  /** The demand.json note (the next step the orchestrator recorded). */
  note: string
  /** The up-to-4-line summary of demand.json (`demand set --summary`). */
  summary: string
  waiting: string | null
  timeline: TimelineItem[]
  progress: Progress
  repos: Repo[]
  level: string | null
  passes: string
  planVersion: string
  round: number
  roundKind: 'plan' | 'review' | null
  delegations: Delegation[]
  tokens: number
  /** The orchestrator itself (main chat), from the orchestrator metrics file. */
  orchestrator: OrchestratorUsage
  budget: number
  findings: Finding[]
  /** The triage of the last round of a PR review in the *pr-triage* format; null without it (the panel falls back to the findings). */
  prTriage: PrTriage | null
  criteria: Criterion[]
  coverage: CoverageItem[]
  /** There is a coverage file or a plan: without them, everything shows as "missing" with a warning. */
  coverageRecorded: boolean
  manual: ManualStep[]
  testScript: string
  points: Point[]
  cardAsk: string
  cardPoints: CardPoint[]
  effort: EffortBlock[]
  split: SplitItem[]
  estimate: Estimate | null
  doubts: Doubt[]
  /** The survey's "Where the change touches" section, in Markdown (systems, contracts, database). */
  touches: string
  surveyFile: string
  /** AIDW-TESTE marks (temporary test adjustments) per repository; null when not checked. */
  testMarks: Record<string, number> | null
}

/**
 * A running agent, in the strip: the name, model and effort (from the variant and runtime.json), the label, since when and the
 * tokens of its last answer (the same count as the metrics file), which move at every step.
 */
export type RunningAgent = {
  key: string
  agent: string
  label: string
  since: number
  display?: string
  model?: string
  effort?: string
  /** The subagent loop id (`agent.spawn`), to match its steps with the card. */
  agentId?: string
  tokens?: number
}

/** An AiDW delegation waiting to be recorded in the metrics file (a background agent's, until it ends). */
export type Pending = { agent: string; level: string | null; label: string; demand: string }

/** A plan usage window (5h, 7d), from `$.session.usage().rateLimits`. */
/** The four usage numbers of an answer (or the sum of several) and the model that answered. */
export type TokenUsage = {
  model: string
  input_tokens: number
  cache_creation_input_tokens: number
  cache_read_input_tokens: number
  output_tokens: number
}

export type Limit = { kind: '5h' | '7d'; percent: number; resetsAt: string }
export type Usage = { percent: number; tokens: number; limits: Limit[] }

/** The Review filters: what is switched off leaves the list. */
export type ReviewFilter = { severities: string[]; sources: string[]; statuses: string[]; open: boolean }

declare module 'claude-code' {
  interface PluginState {
    'aidw-mods': {
      active: boolean
      snap: Snapshot | null
      running: RunningAgent[]
      /** AiDW agents in the background, by agentId: the record goes out when each one ends. */
      background: Record<string, Pending>
      /**
       * Usage of each subagent by agentId: the last answer (the record's tokens) and the sum of all (the cost).
       * In the state, not in the module, to survive a `/reload-plugins` or an `aidw.py install` (2026-11-04).
       */
      agentUsage: Record<string, { last: TokenUsage; sum: TokenUsage }>
      hidden: boolean
      /** The open tab of each panel (`general`, `metrics`, `decide`). */
      tabs: Record<string, string>
      tick: number
      reviewRound: number
      usage: Usage | null
      /** The largest context (tokens) seen since your last message: compaction is measured against it. */
      contextPeak: number
      codeReads: number
      /** The round (review file), the tab and the filters of the Review; the panel only informs, the decision is in the chat. */
      reviewFile: string
      decisionTab: string
      reviewFilter: ReviewFilter
      /** Collapsed groups you opened (questions, artifacts, preparation, delegations). */
      expanded: Record<string, boolean>
    }
  }
}
