export type DemandKind = 'desenvolvimento' | 'pr-review' | 'levantamento'

export type TimelineItem = { name: string; state: 'feito' | 'atual' | 'pendente'; visits: number }

/** Uma etapa da barra de progresso do Mapa da demanda (docs/painel.md). */
export type ProgressStage = {
  name: string
  /** `aidw`: o AiDW trabalha; `fora`: o time (Code review) ou a QA. */
  group: 'aidw' | 'fora'
  /** `com-time`: a etapa de fora em que a demanda está; `voltou`: a etapa de fora que devolveu o trabalho. */
  state: 'feito' | 'atual' | 'pendente' | 'com-time' | 'voltou'
  /** Com quem a demanda fica numa etapa de fora ("o time", "a QA", "o UX"). */
  who?: string
}

export type Progress = {
  stages: ProgressStage[]
  /** Nome da etapa atual e a posição dela (1…total). */
  current: string
  index: number
  total: number
  /** A etapa de fora que devolveu o trabalho e ainda não foi retomada (null quando não há). */
  returnedFrom: string | null
  /** Quantas vezes cada etapa de fora devolveu ("Code review" → 1). */
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
  /** Custo em USD quando o metricas.md traz (Codex e headless); o subagente nativo do Claude não informa. */
  cost: number | null
}

/** Uma linha do metricas-orquestrador.md: o chat principal numa sessão, com um modelo. */
export type OrchestratorRow = {
  session: string
  updated: string
  model: string
  turns: number
  seconds: number
  /** Entrada, cache escrito, cache lido e saída somados. */
  tokens: number
  cacheWrite: number
  cacheRead: number
  output: number
  /** Equivalente em preço de API (não é a conta da assinatura). */
  cost: number | null
}
export type OrchestratorUsage = { rows: OrchestratorRow[]; turns: number; tokens: number; cost: number | null }

export type Finding = {
  id: string
  round: number
  source: 'revisão' | 'plano' | 'bugs' | 'segurança'
  /** Arquivo da rodada (review-us-1-r2.md, review-otimizacao-…-r1.md): separa Código de Otimização. */
  file: string
  severity: 'CRITICO' | 'IMPORTANTE' | 'SUGESTAO' | 'ELOGIO' | 'DUVIDA' | null
  where: string
  title: string
  status: string
  triage: string
  comment: string
  /** A PR do rascunho de comentário (revisão de PR): "7639", "7639 e 7640". */
  target: string
  published: boolean
  /** Código antes e depois (blocos `**Antes:**` e `**Depois:**` do revisor); vazios quando o achado não propõe código. */
  before: string
  after: string
  /** As opções de uma dúvida (`(a) …`, `(b) …`). */
  options: string[]
  /** A recomendação do AiDW: a triagem, ou a recomendação do revisor quando ainda não há triagem. */
  recommendation: string
  /** Decisão a partir da triagem: com você (pendente), mantido ou descartado. */
  decision: 'pendente' | 'mantido' | 'descartado'
}

export type Criterion = { id: string; text: string; how: string[]; result: string; evidence: string }
/** Um critério de aceite, regra de negócio ou cenário, com a cobertura pelo nosso código e pelos nossos testes. */
export type CoverageItem = { id: string; kind: 'CA' | 'RN' | 'CN'; text: string; status: 'falta' | 'implementado' | 'coberto' }
export type ManualStep = {
  id: string
  step: string
  expected: string
  result: '✅' | '❌' | ''
  note: string
  /** Seção do roteiro (`## 1. Critérios do card` → "Critérios do card"). */
  section: string
  /** Passo marcado como removido no roteiro: fica escondido. */
  removed: boolean
}
export type Point = { id: string; text: string; verdict: string; evidence: string }
/** Uma linha do "Card × código" do levantamento. */
export type CardPoint = { today: string; effect: string; situation: 'precisa mudar' | 'é a dor' | 'não muda' | 'nada a reaproveitar' | string }
export type EffortBlock = { name: string; min: number; max: number; label: string }
export type SplitItem = { n: string; text: string; sp: string }
export type Estimate = {
  sp: string
  hours: string
  complexity: string
  confidence: string
  /** Modelo novo do levantamento: SP do card como está, SP quebrado, dias de dev e de QA, nível e passadas. */
  spCard: string
  spSplit: string
  devDays: string
  qaDays: string
  level: string
  passes: string
  /** O tópico `**Riscos:**` da estimativa (ou a seção `## Riscos` do modelo antigo), em Markdown. */
  risks: string
}
export type Doubt = {
  n: number
  id: string
  question: string
  why: string
  to: string
  /** Tema (Escopo e produto, Contrato…) e quanto muda a estimativa ("+3 SP se migrar"). */
  group: string
  affects: string
}
/** Um comentário da triagem de uma revisão de PR (`C1`…; referência *triagem-pr*). */
export type PrComment = {
  id: string
  pr: string
  severity: string
  where: string
  /** Os achados que ele junta (`R1-01`, `B1-02`…). */
  origins: string[]
  recommendation: string
  /** Como a triagem diz que está: `a decidir`, `não publicado (r1)`, `publicado (thread 23720), resolvido na r2`… */
  situation: string
  published: boolean
  /** Decidido não publicar numa rodada anterior. */
  declined: boolean
  title: string
  draft: string
}
/** O voto de uma PR: o que o revisor e o AiDW sugerem (o valor da escala, ou `none` para sem voto). */
export type PrVote = { pr: string; reviewer: string; aidw: string; why: string }
export type PrTriage = { file: string; round: number; comments: PrComment[]; votes: PrVote[]; outside: string }
/** Uma opção de voto do contexto (`[[mods.votes]]`); `more` fica em "Mais opções". */
export type VoteOption = { value: string; label: string; more?: boolean }

export type Repo ={ name: string; path: string; branch: string; base: string; pr: string; source: string }

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
  /** O resumo de até 4 linhas do demand.json (`demand set --summary`). */
  summary: string
  waiting: string | null
  timeline: TimelineItem[]
  progress: Progress
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
  /** O próprio orquestrador (chat principal), do metricas-orquestrador.md. */
  orchestrator: OrchestratorUsage
  budget: number
  findings: Finding[]
  vote: string
  /** A triagem da última rodada de uma revisão de PR no formato *triagem-pr*; null sem ela (o painel cai nos achados). */
  prTriage: PrTriage | null
  /** A escala de voto do contexto (`runtime.json` → `votes`), ou a do Azure DevOps. */
  votes: VoteOption[]
  criteria: Criterion[]
  coverage: CoverageItem[]
  /** Há `cobertura-<id>.md`: sem ele, tudo aparece como "falta" com um aviso. */
  coverageRecorded: boolean
  manual: ManualStep[]
  roteiro: string
  points: Point[]
  cardAsk: string
  cardPoints: CardPoint[]
  effort: EffortBlock[]
  split: SplitItem[]
  estimate: Estimate | null
  doubts: Doubt[]
  /** A seção "Onde a mudança toca" do levantamento, em Markdown (sistemas, contratos, banco). */
  touches: string
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

/** Uma janela de uso do plano (5h, 7d), da `$.session.usage().rateLimits`. */
export type Limit = { kind: '5h' | '7d'; percent: number; resetsAt: string }
export type Usage = { percent: number; tokens: number; limits: Limit[] }

/** Os filtros da Revisão: o que está desligado sai da lista. */
export type ReviewFilter = { severities: string[]; sources: string[]; statuses: string[]; open: boolean }

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
      /** O voto escolhido por PR (revisão de PR com triagem *triagem-pr*). */
      votes: Record<string, string>
      drafts: Record<string, string>
      diff: DiffView | null
      reviewRound: number
      usage: Usage | null
      codeReads: number
      warned: Record<string, boolean>
      /** A etapa de cada demanda no fim do turno anterior: a troca de etapa dispara a compactação. */
      lastStep: Record<string, string>
      /** Revisão V2: a rodada (arquivo do review), a aba de decisão, os filtros e as decisões marcadas. */
      reviewFile: string
      decisionTab: string
      reviewFilter: ReviewFilter
      decisions: Record<string, string>
      /** Grupos recolhidos que você abriu (dúvidas, artefatos, preparação, delegações). */
      expanded: Record<string, boolean>
    }
  }
}
