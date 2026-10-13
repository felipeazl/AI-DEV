export type DemandKind = 'desenvolvimento' | 'pr-review' | 'levantamento'

export type TimelineItem = { name: string; state: 'feito' | 'atual' | 'pendente'; visits: number }

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
  /** Custo em USD quando o metricas.md traz (Codex e headless); o subagente nativo do Claude não informa. */
  cost: number | null
}

export type Finding = {
  id: string
  round: number
  source: 'revisão' | 'plano' | 'bugs' | 'segurança'
  severity: 'CRITICO' | 'IMPORTANTE' | 'SUGESTAO' | 'ELOGIO' | 'DUVIDA' | null
  where: string
  title: string
  status: string
  triage: string
  comment: string
  published: boolean
}

export type Criterion = { id: string; text: string; how: string[]; result: string; evidence: string }
export type ManualStep = { id: string; step: string; expected: string; result: '✅' | '❌' | ''; note: string }
export type Point = { id: string; text: string; verdict: string; evidence: string }
export type Estimate = { sp: string; hours: string; complexity: string; confidence: string }
export type Doubt = { n: number; question: string; why: string; to: string }
export type Repo = { name: string; path: string; branch: string; base: string; pr: string; source: string }

/** Tudo o que os painéis e a faixa mostram de uma demanda, relido do disco a cada mudança. */
export type Snapshot = {
  dir: string
  id: string
  title: string
  kind: DemandKind
  step: string
  status: string
  mode: string
  /** A nota do demand.json (o próximo passo que o orquestrador gravou). */
  note: string
  waiting: string | null
  timeline: TimelineItem[]
  repos: Repo[]
  artifacts: Record<string, string[]>
  patches: string[]
  level: string | null
  passes: string
  planVersion: string
  round: number
  roundKind: 'plano' | 'revisão' | null
  maxRetries: number
  delegations: Delegation[]
  tokens: number
  budget: number
  findings: Finding[]
  vote: string
  criteria: Criterion[]
  manual: ManualStep[]
  roteiro: string
  points: Point[]
  estimate: Estimate | null
  doubts: Doubt[]
  levantamento: string
  /** Marcas AIDW-TESTE (ajustes temporários de teste) por repositório; null quando não foi conferido. */
  testMarks: Record<string, number> | null
}

export type RunningAgent = { key: string; agent: string; label: string; since: number }

export type DiffView = {
  source: string
  files: { path: string; change: string; added: number; removed: number }[]
  selected: string
  hunks: string
  summary: string
  error: string
}

export type Usage = { percent: number; tokens: number }

declare module 'claude-code' {
  interface PluginState {
    'aidw-mods': {
      active: boolean
      snap: Snapshot | null
      running: RunningAgent[]
      hidden: boolean
      tab: string
      tick: number
      extraRounds: Record<string, number>
      publish: Record<string, boolean>
      vote: string
      drafts: Record<string, string>
      diff: DiffView | null
      reviewRound: number
      usage: Usage | null
      codeReads: number
      warned: Record<string, boolean>
    }
  }
}
