// The single old→new name table of the mod (PR 2, English identifiers). Everything the AiDW writes now uses the English
// name; everything the mod globs, matches or parses accepts the English name AND the old Portuguese one, so demands
// opened before the rename (folders full of PT files and headings) keep working. Add an alias here, never inline.

/** Demand artifact file families: the new English prefix first, then the old ones. */
export const FILE_PREFIX = {
  summary: ['summary', 'resumo'],
  plan: ['plan', 'plano'],
  exploration: ['exploration', 'exploracao'],
  task: ['task', 'tarefa'],
  planReview: ['plan-review', 'revisao-plano'],
  triage: ['triage', 'triagem'],
  /** The plan marker inside a triage name (`triage-plan-…`, `triagem-plano-…`). */
  planTag: ['plan', 'plano'],
  testScript: ['test-script', 'roteiro-testes'],
  testPlan: ['test-plan', 'plano-testes'],
  learnings: ['learnings', 'aprendizados'],
  survey: ['survey', 'levantamento'],
  coverage: ['coverage', 'cobertura'],
  security: ['security', 'seguranca', 'auditoria-seguranca'],
  bugs: ['bugs', 'bug-hunt'],
  points: ['points', 'pontos'],
  report: ['qa', 'orchestrator-test', 'teste-orquestrador'],
  e2e: ['e2e-result', 'resultado-e2e'],
} as const

/** Whole file names: the new name first. */
export const FILE_NAME = {
  metrics: ['metrics.md', 'metricas.md'],
  orchestratorMetrics: ['orchestrator-metrics.md', 'metricas-orquestrador.md'],
  state: ['state.md', 'estado.md'],
} as const

/** Folders: the new name first. */
export const DIR_NAME = {
  uxScreenshots: ['ux-screenshots', 'prints-ux'],
  knowledge: ['knowledge', 'conhecimento'],
} as const

/** `(?:summary|resumo)`: one alternation group for a file prefix family. */
export const fam = (key: keyof typeof FILE_PREFIX): string => `(?:${FILE_PREFIX[key].map(esc).join('|')})`

/** The first of `names` present in `files` (new name wins when both exist). */
export const pick = (files: readonly string[], names: readonly string[]): string | null => names.find(n => files.includes(n)) ?? null

function esc(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Words and headings the parsers read from artifact text, as regex fragments (case-insensitive, accents optional).
 * Each entry lists the English form and the old Portuguese form(s).
 */
export const TERM = {
  // delegation prompt
  demandFolder: '(?:Demand folder|Pasta da demanda)',
  taskLabel: '(?:Task|Tarefa)',
  level: '(?:Level|N[íi]vel)',
  // headings (contract)
  acceptanceCriteria: '(?:Acceptance criteria|Crit[eé]rios de aceite)',
  risks: '(?:Risks|Riscos)',
  openQuestions: '(?:Open questions|Questions|D[uú]vidas)',
  published: '(?:Published|Publica)',
  matrix: '(?:matrix|matriz)',
  knowledge: '(?:Knowledge base|Knowledge|Base de conhecimento|Conhecimento)',
  decisionsMade: '(?:Decisions made|Decis[õo]es tomadas)',
  // triage table and words (contract)
  decisionCol: '(?:decision|triage|triagem|decis)',
  reasonCol: '(?:reason|motivo|evid)',
  triageKeep: '(?:keep|kept|fix|fixed|accept|publish|yes\\b|apply|corrig|mantid|manter|aceit|publica|sim\\b|aplica)',
  triageDiscard: '(?:discard|drop|won\'?t fix|not fixed|rejected|refuted|do not publish|don\'?t publish|out of scope|descart|cai\\b|n[aã]o corrig|recusad|refutad|n[aã]o public|fora do escopo)',
  triagePending: '(?:pending|^\\W*user\\b|(?:to|ask|with) the user|with you|to decide|waiting|usu[aá]rio|pergunta|com voc[eê]|pendente|aguarda)',
  // finding fields
  what: '(?:What|O qu[eê])',
  problem: '(?:Problem|Problema)',
  status: 'Status',
  before: '(?:Before|Antes)',
  after: '(?:After|Depois)',
  recommendation: '(?:Recommendation|Recomenda[çc][aã]o)',
  suggestedFix: '(?:Suggested fix|Corre[çc][aã]o sugerida)',
  commentDraft: '(?:Comment draft|Draft comment|Rascunho do coment[aá]rio)',
  prCommentDraft: '(?:PR comment draft|Draft PR comment|Rascunho do coment[aá]rio de PR)',
  findingStatus: '(?:corrigido|n[aã]o corrigido|resolvido|aberto|fixed|not_fixed|not fixed|resolved|open|mantido|kept|refutado|refuted)',
  fixed: '(?:corrig|fixed|resolv)',
  category: '(?:quality|qualidade|bugs?|security|seguran[cç]a)',
  // severities (stored values stay CRITICO/IMPORTANTE/SUGESTAO/ELOGIO)
  sevCritical: '(?:CR[IÍ]TICO|CRITICAL)',
  sevImportant: '(?:IMPORTANTE|IMPORTANT|MAJOR)',
  sevSuggestion: '(?:SUGEST[AÃ]O|SUGGESTION|REDUZIR|REDUCE|OPCIONAL|OPTIONAL)',
  sevPraise: '(?:ELOGIO|PRAISE)',
  // PR triage
  comments: '(?:Comments|Coment[aá]rios)',
  outsidePrs: '(?:Outside the PRs|Fora das PRs)',
  situationCol: '(?:situation|status|situa)',
  fileCol: '(?:file|arquivo)',
  originCol: '(?:origin|origem)',
  recommendationCol: '(?:recommend|recomenda)',
  declined: '(?:not published|do not publish|n[aã]o publica)',
  publishedWord: '(?:published|publicad)',
  // test plan and script
  howCol: '(?:type|how|tipo|como)',
  stepCol: '(?:step|what to do|passo|o que fazer)',
  expectedCol: '(?:expected|esperado)',
  whoCol: '(?:who|quem)',
  resultCol: '(?:result|resultado)',
  criterionCol: '(?:criteri|crit[ée]rio)',
  removed: '(?:removed|removid[oa])',
  preparation: '(?:prepar)',
  covers: '(?:Covers|Cobre)',
  covered: '(?:covered|cobert)',
  implemented: 'implement',
  // survey
  estimate: '(?:Estimate|Estimativa)',
  card: 'Card',
  storyPoints: 'Story points',
  totalDev: '(?:Total dev)',
  cardIs: '(?:card (?:is|stays at|é|e|fica em))',
  orMore: '(?:or more|ou mais)',
  complexity: '(?:complexity|complexidade)',
  confidence: '(?:confidence|confian[çc]a)',
  aidwLevel: '(?:AiDW level|N[íi]vel AiDW)',
  extraPasses: '(?:Extra passes|Passadas extras)',
  cardPoints: '(?:Card points|Pontos do card)',
  todayInCode: '(?:today in (?:the )?code|hoje no c[oó]digo)',
  block: '(?:block|bloco)',
  days: '(?:days|dias|\\(h\\)|hours|horas)',
  touches: '(?:Where the change touches|Onde a mudan[çc]a toca)',
  for: '(?:For|Para)',
  changesEstimate: '(?:Changes the estimate|Muda a estimativa)',
  whyItMatters: '(?:Why it matters|Por que importa)',
  answered: '(?:answered|respondid)',
  surveyTitle: '\\((?:survey|levantamento)\\)',
} as const

/** A case-insensitive regex from a template where `{term}` is replaced by the TERM fragment. */
export function re(template: string, flags = 'i'): RegExp {
  return new RegExp(template.replace(/\{([a-zA-Z]\w*)\}/g, (m, k: string) => (TERM as Record<string, string>)[k] ?? m), flags)
}
