// Leitura dos artefatos de uma demanda do AiDW para os painéis: o tipo de uso, a linha do tempo, os achados da
// revisão e a triagem, os critérios de aceite e o teste, o roteiro manual e o levantamento. Puro (sem `$`): o
// register.tsx lê os arquivos e entrega o texto. Os formatos reais variam entre demandas: as regras são tolerantes.

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
  PrVote,
  Progress,
  ProgressStage,
  SplitItem,
  TimelineItem,
  VoteOption,
} from '../types'

export type { CardPoint, CoverageItem, Criterion, Doubt, EffortBlock, Estimate, Finding, ManualStep, Point, Progress, SplitItem, TimelineItem }

// ---------------------------------------------------------------------------------------------------------------
// Tipo de uso e linha do tempo

export type DemandFile = { id?: string; title?: string; step?: string; status?: string; note?: string; summary?: string;
  repos?: { repo?: string; path?: string; branch?: string; base?: string; system?: string | null; pr?: string;
    head?: string; source?: string }[]; history?: { step: string; at: string }[]
  /** Laço de correção depois da entrega (`demand set --loop`); as Tasks de cada ticket (`--task`). */
  loop?: string; tasks?: Record<string, string>
  /** Etapas de fora do contexto pelas quais a demanda passa (`demand set --extra-step`). */
  extra_steps?: string[] }

/** Desenvolvimento, revisão de PR ou levantamento — o demand.json não grava o workflow; os arquivos dizem. */
export function kindOf(demand: DemandFile, files: string[]): DemandKind {
  const plan = files.some(f => /^plano-.*\.md$/.test(f) && !/^plano-testes-/.test(f))
  if ((demand.repos ?? []).some(r => r.pr) || files.some(f => /^diff-pr\d+-/.test(f))) return plan ? 'desenvolvimento' : 'pr-review'
  if (!plan && !implementingAfterEstimate(demand.history ?? []) &&
    (files.some(f => /^(levantamento|pontos)-.*\.md$/.test(f)) || /\(levantamento\)\s*$/i.test(demand.title ?? '') ||
    (demand.history ?? []).some(h => h.step === 'ESTIMATE'))) return 'levantamento'
  return 'desenvolvimento'
}

/** O levantamento terminou (DONE depois do último ESTIMATE) e a demanda seguiu para a implementação, ainda sem plano. */
function implementingAfterEstimate(history: { step: string }[]): boolean {
  const estimate = history.map(h => h.step).lastIndexOf('ESTIMATE')
  if (estimate < 0) return false
  const done = history.findIndex((h, i) => i > estimate && h.step === 'DONE')
  return done > 0 && history.slice(done + 1).some(h => h.step !== 'DONE')
}

export const KIND_LABEL: Record<DemandKind, string> = {
  desenvolvimento: 'Desenvolvimento',
  'pr-review': 'Revisão de PR',
  levantamento: 'Levantamento',
}

type Phase = { name: string; steps: string[] }

const PHASES: Record<DemandKind, Phase[]> = {
  // fluxo v3 (2026-10-23); as etapas antigas ficam na fase equivalente, pelas demandas abertas antes dele
  desenvolvimento: [
    { name: 'Entender', steps: ['UNDERSTAND', 'EXPLORE'] },
    { name: 'Plano', steps: ['PLAN', 'SPEC', 'PLAN_FIX', 'PLAN_REVIEW'] },
    { name: 'Sua aprovação', steps: ['PLAN_APPROVAL', 'TICKETS'] },
    { name: 'Implementar', steps: ['IMPLEMENT', 'TEST_PLAN'] },
    { name: 'Revisão', steps: ['REVIEW', 'TRIAGE', 'CODER_FIX', 'PREPARE_REVIEW'] },
    { name: 'Sua revisão', steps: ['USER_REVIEW'] },
    { name: 'Testes', steps: ['TEST', 'TEST_ADJUST', 'MANUAL_TEST', 'ORCHESTRATOR_TEST'] },
    { name: 'PR', steps: ['PR', 'DOCS', 'FINAL_REVIEW'] },
    { name: 'Pronto', steps: ['DONE'] },
  ],
  'pr-review': [
    { name: 'Entender', steps: ['UNDERSTAND'] },
    { name: 'Preparar', steps: ['PREPARE_REVIEW'] },
    { name: 'Revisar', steps: ['REVIEW'] },
    { name: 'Revisão final', steps: ['FINAL_REVIEW'] },
    { name: 'Pronto', steps: ['DONE'] },
  ],
  levantamento: [
    { name: 'Entender', steps: ['UNDERSTAND'] },
    { name: 'Explorar', steps: ['EXPLORE'] },
    { name: 'Estimar', steps: ['ESTIMATE'] },
    { name: 'Revisão final', steps: ['FINAL_REVIEW'] },
    { name: 'Pronto', steps: ['DONE'] },
  ],
}

/** As fases do uso, com a atual pela etapa gravada (HUMAN_APPROVAL e RETURN ficam na fase anterior). */
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
    name: p.name,
    state: i < current ? 'feito' : i === current ? (demand.step === 'DONE' ? 'feito' : 'atual') : 'pendente',
    visits: history.filter(h => p.steps.includes(h.step)).length,
  }))
}

/** A demanda espera o usuário: aprovação, dúvida, teste manual ou revisão final. */
export function waitingFor(step: string | undefined): string | null {
  switch (step) {
    case 'HUMAN_APPROVAL':
      return 'sua aprovação ou resposta'
    case 'PLAN_APPROVAL':
      return 'a aprovação do plano'
    case 'TRIAGE':
      return 'a decisão dos achados'
    case 'USER_REVIEW':
      return 'a sua revisão de código'
    case 'MANUAL_TEST':
      return 'os passos manuais do teste'
    case 'PR':
      return 'o OK do commit e da PR'
    case 'FINAL_REVIEW':
      return 'a revisão final'
    default:
      return null
  }
}

/** Uma etapa de fora que o contexto acrescenta (`runtime.json` → `external_steps`), antes de `before`. */
export type ExternalStep = { step: string; name: string; before: string; who?: string }

type Stage = { name: string; group: ProgressStage['group']; steps: string[]; who?: string }

/** As etapas da barra de progresso do Mapa da demanda: as do AiDW e, no desenvolvimento, as de fora (time e QA). */
const STAGES: Record<DemandKind, Stage[]> = {
  desenvolvimento: [
    { name: 'Entender', group: 'aidw', steps: ['UNDERSTAND', 'EXPLORE'] },
    { name: 'Plano', group: 'aidw', steps: ['PLAN', 'SPEC', 'PLAN_FIX', 'PLAN_REVIEW'] },
    { name: 'Sua aprovação', group: 'aidw', steps: ['PLAN_APPROVAL', 'TICKETS'] },
    { name: 'Implementar', group: 'aidw', steps: ['IMPLEMENT', 'TEST_PLAN'] },
    { name: 'Revisão', group: 'aidw', steps: ['REVIEW', 'TRIAGE', 'CODER_FIX', 'PREPARE_REVIEW'] },
    { name: 'Sua revisão', group: 'aidw', steps: ['USER_REVIEW'] },
    { name: 'Testes', group: 'aidw', steps: ['TEST', 'TEST_ADJUST', 'MANUAL_TEST', 'ORCHESTRATOR_TEST'] },
    { name: 'PR', group: 'aidw', steps: ['PR', 'DOCS', 'FINAL_REVIEW'] },
    { name: 'Code review', group: 'fora', steps: ['CODE_REVIEW'], who: 'o time' },
    { name: 'Testes QA', group: 'fora', steps: ['QA_TEST'], who: 'a QA' },
    { name: 'Pronto', group: 'fora', steps: ['DONE'] },
  ],
  'pr-review': [
    { name: 'Entender', group: 'aidw', steps: ['UNDERSTAND'] },
    { name: 'Preparar', group: 'aidw', steps: ['PREPARE_REVIEW'] },
    { name: 'Revisar', group: 'aidw', steps: ['REVIEW'] },
    { name: 'Revisão final', group: 'aidw', steps: ['FINAL_REVIEW'] },
    { name: 'Pronto', group: 'aidw', steps: ['DONE'] },
  ],
  levantamento: [
    { name: 'Entender', group: 'aidw', steps: ['UNDERSTAND'] },
    { name: 'Explorar', group: 'aidw', steps: ['EXPLORE'] },
    { name: 'Estimar', group: 'aidw', steps: ['ESTIMATE'] },
    { name: 'Revisão final', group: 'aidw', steps: ['FINAL_REVIEW'] },
    { name: 'Pronto', group: 'aidw', steps: ['DONE'] },
  ],
}

/**
 * O progresso pelo histórico do demand.json. Uma etapa do AiDW logo depois de uma de fora (CODE_REVIEW, QA_TEST) é
 * uma volta: conta para aquela etapa de fora e, enquanto a demanda não voltar a ela, a etapa fica "voltou".
 * HUMAN_APPROVAL e RETURN ficam na etapa anterior.
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
    if (st.group === 'fora' && st.name !== 'Pronto') {
      lastOutside = st.name
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
      name: s.name,
      group: s.group,
      ...(s.who ? { who: s.who } : {}),
      state: done || i < current
        ? 'feito'
        : i === current
          ? (s.group === 'fora' ? 'com-time' : 'atual')
          : s.name === returnedFrom
            ? 'voltou'
            : 'pendente',
    })),
    current: stages[current]?.name ?? '',
    index: current + 1,
    total: stages.length,
    returnedFrom,
    returns,
  }
}

/**
 * As etapas de fora do contexto entram no desenvolvimento só para a demanda que passa por elas: marcada com
 * `demand set --extra-step` ou com a etapa no histórico. Cada uma fica logo antes da etapa `before`.
 */
function withExternal(base: Stage[], kind: DemandKind, demand: DemandFile, extra: ExternalStep[]): Stage[] {
  if (kind !== 'desenvolvimento') return base
  const used = new Set([...(demand.extra_steps ?? []), ...(demand.history ?? []).map(h => h.step), demand.step ?? ''])
  const out = [...base]
  for (const e of extra) {
    if (!used.has(e.step)) continue
    const at = out.findIndex(s => s.steps.includes(e.before))
    out.splice(at < 0 ? out.length - 1 : at, 0, { name: e.name, group: 'fora', steps: [e.step], ...(e.who ? { who: e.who } : {}) })
  }
  return out
}

// ---------------------------------------------------------------------------------------------------------------
// Revisão: achados e triagem

type Severity = NonNullable<Finding['severity']>

const SEVERITY: [RegExp, Severity][] = [
  [/CR[IÍ]TICO/i, 'CRITICO'],
  [/IMPORTANTE/i, 'IMPORTANTE'],
  [/SUGEST[AÃ]O|REDUZIR|OPCIONAL/i, 'SUGESTAO'],
  [/ELOGIO/i, 'ELOGIO'],
]
const STATUS = /\b(corrigido|n[aã]o corrigido|resolvido|aberto|fixed|not_fixed|open|mantido|refutado)\b/i
const HEADING = /^###\s+([RPBSO]\d+-D?\d+)(?:\s*=\s*[RPBSO]\d+-D?\d+)?\s+[—–-]\s+(.*)$/

const clean = (s: string) => s.replace(/\*\*/g, '').replace(/\s+/g, ' ').trim()
const cut = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s)

/** Os achados de um review (`review-*-rN.md`, `revisao-plano-*-rN.md`, `bugs-*`, `seguranca-*`). */
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
    // a categoria no título (`R1-01 — IMPORTANTE — bug — \`arquivo:linha\``), do revisor do fluxo v3
    const catIdx = segments.findIndex(s => CATEGORY.test(s))
    const category = catIdx < 0 ? '' : categoryOf(segments[catIdx] ?? '')
    if (catIdx >= 0) segments.splice(catIdx, 1)
    let status = segments.map(s => STATUS.exec(s)?.[1]).find(Boolean) ?? ''
    // o corpo, até o próximo achado ou seção
    const body: string[] = []
    for (let j = i + 1; j < lines.length && !/^#{2,3}\s/.test(lines[j] ?? ''); j++) body.push(lines[j] ?? '')
    const bodyText = body.join('\n')
    status = status || (/\*\*Status:\*\*\s*([^\n]+)/.exec(bodyText)?.[1] ?? '')
    const what =
      /\*\*O qu[eê]:\*\*\s*([^\n]+)/.exec(bodyText)?.[1] ??
      /^-\s*Problema:\s*([^\n]+)/m.exec(bodyText)?.[1] ??
      segments.filter(s => !SEVERITY.some(([re]) => re.test(s)) && !/`/.test(s) && !STATUS.test(s)).join(' — ')
    const draft = /Rascunho do coment[aá]rio[^\n]*\n((?:>[^\n]*\n?)+)/.exec(bodyText)?.[1] ?? ''
    const target = /Rascunho do coment[aá]rio de PR\s*\(([^)]+)\)/i.exec(bodyText)?.[1] ?? ''
    // sem "O quê": o resto do cabeçalho, nunca a própria severidade ("IMPORTANTE — status: fixed")
    const fromHeading = segments.filter(s => !SEVERITY.some(([re]) => re.test(s)) && !STATUS.test(s)).join(' — ')
    out.push({
      id,
      round,
      source,
      file,
      severity,
      where,
      // vazio quando a rodada só reapresenta o achado ("— status: fixed"): o snapshot herda o título da rodada anterior
      title: cut(clean(what || fromHeading), 220),
      status: clean(status).toLowerCase(),
      triage: '',
      comment: draft.split('\n').map(l => l.replace(/^>\s?/, '')).join('\n').trim(),
      target: clean(target),
      published: false,
      before: fenced(bodyText, /\*\*Antes:?\*\*:?/i),
      after: fenced(bodyText, /\*\*Depois:?\*\*:?/i),
      options: [...bodyText.matchAll(/^\s*-?\s*\(([a-z])\)\s+(.+)$/gm)].slice(0, 4).map(o => `(${o[1]}) ${cut(clean(o[2] ?? ''), 400)}`),
      recommendation: cut(
        clean(/\*\*Recomenda[çc][aã]o:\*\*\s*([^\n]+)/i.exec(bodyText)?.[1] ?? /\*\*Corre[çc][aã]o sugerida:\*\*\s*([^\n]+)/i.exec(bodyText)?.[1] ?? ''),
        240,
      ),
      decision: 'pendente',
      category,
    })
  }
  return out
}

const CATEGORY = /^(qualidade|bugs?|seguran[cç]a)$/i

function categoryOf(s: string): Finding['category'] {
  const v = s.toLowerCase()
  return v.startsWith('bug') ? 'bug' : v.startsWith('segur') ? 'seguranca' : 'qualidade'
}

/** O bloco de código cercado (```) logo depois de um rótulo (`**Antes:**`), sem as cercas. */
function fenced(body: string, label: RegExp): string {
  const at = body.search(label)
  if (at < 0) return ''
  const m = /```[^\n]*\n([\s\S]*?)```/.exec(body.slice(at))
  return m ? (m[1] ?? '').replace(/\n$/, '') : ''
}

/** A decisão que a triagem registrou: mantido, descartado ou com você (pendente, inclusive "vai ao usuário"; "Felipe" fica pelas triagens antigas do safeweb). */
export function decisionOf(triage: string): Finding['decision'] {
  const t = triage.toLowerCase()
  if (!t || /felipe|usu[aá]rio|pergunta|com voc[eê]|pendente|aguarda/.test(t)) return 'pendente'
  if (/^\W*(descart|cai\b|n[aã]o corrig|recusad|refutad|n[aã]o public|fora do escopo)/.test(t)) return 'descartado'
  if (/^\W*(corrig|mantid|aceit|publica|sim\b|aplica)/.test(t)) return 'mantido'
  return 'pendente'
}

/** Decisão da triagem por id, e os ids já publicados (seção `## Publica…`). */
export function parseTriage(text: string): { decisions: Record<string, string>; published: string[] } {
  const decisions: Record<string, string> = {}
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  let header: string[] = []
  let publishing = false
  const published = new Set<string>()
  for (const line of lines) {
    if (/^#{1,3}\s/.test(line)) publishing = /^#{1,3}\s+Publica/i.test(line)
    if (publishing) for (const id of line.match(/\b[RPBSO]\d+-D?\d+\b/g) ?? []) published.add(id)
    if (line.startsWith('|')) {
      const cells = line.split('|').slice(1, -1).map(c => clean(c))
      if (cells[0] === 'ID') {
        header = cells.map(c => c.toLowerCase())
        continue
      }
      const id = /^([RPBSO]\d+-D?\d+)/.exec(cells[0] ?? '')?.[1]
      if (!id) continue
      const col = header.findIndex(h => /triagem|decis/.test(h))
      const decision = col >= 0 ? cells[col] : cells.slice(1).join(' · ')
      const why = header.findIndex(h => /motivo|evid/.test(h))
      decisions[id] = cut([decision, why >= 0 ? cells[why] : ''].filter(Boolean).join(' — '), 200)
      continue
    }
    const bullet = /^\s*-\s+\**([RPBSO]\d+-D?\d+)\**\s*[:—–-]\s*(.+)$/.exec(line)
    if (bullet?.[1] && !publishing) decisions[bullet[1]] = cut(clean(bullet[2] ?? ''), 200)
  }
  return { decisions, published: [...published] }
}

/** O voto sugerido de um review de PR. */
export function parseVote(text: string): string {
  return clean(/Voto sugerido:\s*([^\n]+)/i.exec(text)?.[1] ?? /\*\*Veredito[^\n]*\n((?:-[^\n]*\n?)+)/i.exec(text)?.[1] ?? '')
}

/** O voto único das revisões de PR sem triagem no formato *triagem-pr* (demandas antigas). */
export const VOTES = [
  { value: 'approve', label: 'Aprovar (10)' },
  { value: 'approve_with_suggestions', label: 'Aprovar com sugestões (5)' },
  { value: 'wait_for_author', label: 'Aguardar o autor (−5)' },
  { value: 'reject', label: 'Rejeitar (−10)' },
  { value: 'none', label: 'Sem voto' },
] as const

/** O voto sugerido como valor; vazio quando o revisor não sugeriu: nada vem marcado sem sugestão. */
export function voteValue(suggested: string): string {
  const s = suggested.toLowerCase()
  if (/sem voto/.test(s)) return 'none'
  if (/rejeit|-10/.test(s)) return 'reject'
  if (/aguard|-5|wait/.test(s)) return 'wait_for_author'
  if (/sugest|ajuste|\b5\b/.test(s)) return 'approve_with_suggestions'
  if (/aprov|approve|10/.test(s)) return 'approve'
  return ''
}

/** A escala de voto do Azure DevOps, quando o contexto não declara outra (`[[mods.votes]]`). */
export const DEFAULT_VOTES: VoteOption[] = [
  { value: '10', label: 'Aprovar' },
  { value: '5', label: 'Aprovar com sugestões' },
  { value: '-5', label: 'Aguardar o autor' },
  { value: '-10', label: 'Rejeitar', more: true },
]

/** Uma célula de voto da triagem ("5", "-5 (aguardar o autor)", "Aprovar", "sem voto") como valor da escala. */
export function voteIn(cell: string, votes: VoteOption[]): string {
  const c = clean(cell).toLowerCase().replace(/[−–]/g, '-')
  if (!c || /^[-—]$/.test(c)) return ''
  if (/sem voto|n[aã]o votar|nenhum/.test(c)) return 'none'
  const n = /^[+]?(-?\d+)\b/.exec(c)?.[1]
  const byValue = votes.find(v => v.value.toLowerCase() === (n ?? c))
  if (byValue) return byValue.value
  // pela palavra: o rótulo mais longo que aparece (Aprovar com sugestões antes de Aprovar)
  return [...votes].sort((a, b) => b.label.length - a.label.length).find(v => c.includes(v.label.toLowerCase()))?.value ?? ''
}

/** As linhas de uma tabela Markdown, cada uma como {coluna: célula} pelo cabeçalho (em minúsculas). */
function tableRows(section: string): Record<string, string>[] {
  const rows = section.split('\n').filter(l => l.trim().startsWith('|'))
  const cells = (l: string) => l.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim())
  const head = rows[0] ? cells(rows[0]).map(h => clean(h).toLowerCase()) : []
  return rows.slice(2).map(r => Object.fromEntries(cells(r).map((c, i) => [head[i] ?? String(i), c])))
}
const col = (row: Record<string, string>, re: RegExp) => Object.entries(row).find(([k]) => re.test(k))?.[1] ?? ''

const PR_SEVERITY: [RegExp, string][] = [
  [/cr[ií]tic/i, 'CRITICO'],
  [/importante/i, 'IMPORTANTE'],
  [/sugest/i, 'SUGESTAO'],
  [/d[uú]vida|pergunta/i, 'DUVIDA'],
  [/pend[eê]ncia/i, 'PENDENCIA'],
]

/** A triagem de uma revisão de PR no formato da referência *triagem-pr*; null sem a tabela de comentários. */
export function parsePrTriage(text: string, file = '', round = 0): PrTriage | null {
  const t = text.replace(/\r\n/g, '\n')
  const rows = tableRows(parseSection(t, /Coment[aá]rios/i)).filter(r => /^C\d+$/.test(clean(col(r, /^c$/))))
  if (!rows.length) return null
  const published = parseSection(t, /^##\s+Publicad/i)
  const comments: PrComment[] = rows.map(r => {
    const id = clean(col(r, /^c$/))
    const situation = clean(col(r, /situa/))
    // o rascunho: `### C1 — título` seguido do bloco `> …`
    const at = t.search(new RegExp(`^###\\s+${id}\\b`, 'm'))
    const lines = at < 0 ? [] : t.slice(at).split('\n')
    const heading = lines[0] ?? ''
    const body = lines.slice(1)
    const end = body.findIndex(l => /^#{1,3}\s/.test(l))
    const quote = (end < 0 ? body : body.slice(0, end)).filter(l => l.startsWith('>')).map(l => l.replace(/^>\s?/, ''))
    const sev = col(r, /^sev/)
    const declined = /n[aã]o publica/i.test(situation)
    return {
      id,
      pr: clean(col(r, /^pr$/)),
      severity: PR_SEVERITY.find(([re]) => re.test(sev))?.[1] ?? clean(sev).toUpperCase(),
      where: clean(col(r, /arquivo/)).replace(/`/g, ''),
      origins: clean(col(r, /origem/)).split(/\s*(?:,|\+| e )\s*/).filter(Boolean),
      recommendation: clean(col(r, /recomenda/)),
      situation,
      published: (!declined && /publicad/i.test(situation)) || new RegExp(`(^|\\W)${id}:`, 'm').test(published),
      declined,
      title: clean(heading.replace(new RegExp(`^###\\s+${id}\\s*[—–-]?\\s*`), '')),
      draft: quote.join('\n').trim(),
    }
  })
  const votes: PrVote[] = tableRows(parseSection(t, /^##\s+Votos/i))
    .filter(r => clean(col(r, /^pr$/)))
    .map(r => ({ pr: clean(col(r, /^pr$/)), reviewer: clean(col(r, /revisor/)), aidw: clean(col(r, /aidw|orquestrador/)), why: clean(col(r, /por qu/)) }))
  return { file, round, comments, votes, outside: parseSection(t, /Fora das PRs/i) }
}

// ---------------------------------------------------------------------------------------------------------------
// Critérios de aceite, plano de testes e resultados

/** Os critérios de aceite de `## Critérios de aceite…` (plano ou resumo do card). */
export function parseCriteria(text: string): Criterion[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const start = lines.findIndex(l => /^#{2,3}\s+Crit[eé]rios de aceite/i.test(l))
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
 * Itens numerados de um prefixo (`CA`, `RN`, `CN`) em qualquer seção do plano: tópicos `- RN1: texto` ou linhas de
 * tabela `| RN1 | texto |`. O primeiro de cada id vale.
 */
export function parseItems(text: string, prefix: 'CA' | 'RN' | 'CN'): { id: string; text: string }[] {
  const out = new Map<string, string>()
  const item = new RegExp(`^\\s*(?:[-*]\\s+(?:\\[[ xX]\\]\\s+)?|\\d+[.)]\\s+)?\\**(${prefix}\\d+[a-z]?)\\**\\s*[:.)—–-]\\s*(.+)$`, 'i')
  const row = new RegExp(`^\\|\\s*\\**(${prefix}\\d+[a-z]?)\\**\\s*\\|\\s*([^|]+)\\|`, 'i')
  // a matriz do plano de testes: `| CA1 | CN1 — nome | …`
  const cell = new RegExp(`^\\|.*?\\|\\s*\\**(${prefix}\\d+[a-z]?)\\**\\s*[—–-]\\s*([^|]+)\\|`, 'i')
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    const m = item.exec(line) ?? row.exec(line) ?? cell.exec(line)
    const id = m?.[1]?.toUpperCase()
    if (!id || out.has(id)) continue
    out.set(id, cut(clean(m?.[2] ?? ''), 220))
  }
  return [...out].map(([id, t]) => ({ id, text: t }))
}

/** O status de cada id no `cobertura-<id>.md` (`| CA1 | coberto | evidência |`). */
export function parseCoverage(text: string): Record<string, CoverageItem['status']> {
  const out: Record<string, CoverageItem['status']> = {}
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    const cells = line.startsWith('|') ? line.split('|').slice(1, -1).map(c => clean(c).toLowerCase()) : []
    const id = /^((?:ca|rn|cn)\d+[a-z]?)$/.exec(cells[0] ?? '')?.[1]
    if (!id) continue
    const st = cells[1] ?? ''
    out[id.toUpperCase()] = /cobert/.test(st) ? 'coberto' : /implement/.test(st) ? 'implementado' : 'falta'
  }
  return out
}

const HOW = /\b(auto-api|auto-browser|auto-suite|manual|automatizado(?: \(build\))?|removido)(?![\w-])/i

/** Como cada critério é provado, pela matriz do plano de testes (coluna `Tipo` ou `Como`). */
export function parseTestMatrix(text: string): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  let inMatrix = false
  let howCol = -1
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    if (/^#{2,3}\s/.test(line)) inMatrix = /matriz/i.test(line)
    if (!inMatrix || !line.startsWith('|')) continue
    const cells = line.split('|').slice(1, -1).map(c => clean(c))
    if (/^(CA|Crit)/i.test(cells[0] ?? '') && cells.some(c => /^(tipo|como)$/i.test(c))) {
      howCol = cells.findIndex(c => /^(tipo|como)$/i.test(c))
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

/** Vereditos por critério num relatório de teste (qa-*, teste-orquestrador-*, resultado-*): o último vale. */
export function parseVerdicts(text: string): Record<string, { result: string; evidence: string }> {
  const out: Record<string, { result: string; evidence: string }> = {}
  const verdict = (s: string) =>
    /✅|\bmet\b|\bpassou\b|\bok\b/i.test(s) && !/not_met|não passou/i.test(s)
      ? 'atendido'
      : /❌|not_met|falhou|não passou/i.test(s)
        ? 'falhou'
        : /pending_manual|⏳|pendente/i.test(s)
          ? 'pendente'
          : /needs_orchestrator/i.test(s)
            ? 'orquestrador'
            : /doubt|dúvida/i.test(s)
              ? 'dúvida'
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
// Roteiro de teste manual

export function parseRoteiro(text: string): ManualStep[] {
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
    if (lower.some(c => c === 'passo' || c === 'o que fazer') && lower.some(c => /esperado|^quem$/.test(c))) {
      cols = lower
      continue
    }
    if (!cols.length || /^-+$/.test((cells[0] ?? '').replace(/[:\s]/g, ''))) continue
    const at = (re: RegExp) => cells[cols.findIndex(c => re.test(c))] ?? ''
    const result = at(/^resultado/)
    out.push({
      id: clean(cells[0] ?? ''),
      step: cut(clean(at(/^(passo|o que fazer)$/)), 200),
      expected: cut(clean(at(/esperado/)), 200),
      result: result.includes('✅') ? '✅' : result.includes('❌') ? '❌' : '',
      note: cut(clean(result.replace(/[✅❌]/g, '')), 120),
      section,
      removed: cells.some(c => /\bremovid[oa]\b/i.test(c)),
      criteria: [...at(/^crit[ée]rio/).matchAll(/\b(CA|RN|CN)\s*0*(\d+)\b/g)].map(m => `${m[1]}${m[2]}`),
      how: clean(at(/^como$/)).toLowerCase(),
    })
  }
  return out
}

// ---------------------------------------------------------------------------------------------------------------
// Levantamento


/** Pontos do card: a tabela do levantamento (`| P01 | ponto | ✅ confirmado | evidência |`) ou o pontos-<id>.md. */
export function parsePoints(levantamento: string, pontos: string): Point[] {
  const out: Point[] = []
  for (const line of levantamento.replace(/\r\n/g, '\n').split('\n')) {
    if (!/^\|\s*P\d+/.test(line)) continue
    const cells = line.split('|').slice(1, -1).map(c => clean(c))
    out.push({ id: cells[0] ?? '', text: cut(cells[1] ?? '', 200), verdict: cells[2] ?? '', evidence: cut(cells[3] ?? '', 120) })
  }
  if (out.length) return out
  for (const line of pontos.replace(/\r\n/g, '\n').split('\n')) {
    const m = /^\s*[-*]?\s*(P\d+)\s*[—–-]\s*(.+?)(?:\s+[—–-]\s+origem:.*)?$/.exec(line)
    if (m) out.push({ id: m[1] ?? '', text: cut(clean(m[2] ?? ''), 200), verdict: '', evidence: '' })
  }
  return out
}

/** `**Story points sugeridos:**` seguido de tópicos `- **13** se…` / `- **8** se…` → `8–13`. */
function pointsFromList(text: string): string {
  const list = /Story points[^\n]*:\**\s*\n((?:\s*-[^\n]*\n?)+)/i.exec(text)?.[1] ?? ''
  const values = [...list.matchAll(/^\s*-\s*\*\*(\d+)\*\*/gm)].map(m => Number(m[1])).sort((a, b) => a - b)
  if (!values.length) return ''
  const lo = values[0]
  const hi = values.at(-1)
  return lo === hi ? String(lo) : `${lo}–${hi}`
}

export function parseEstimate(text: string): Estimate {
  const line = /\*\*Estimativa:\*\*\s*([^\n]+)/.exec(text)?.[1] ?? ''
  const pick = (re: RegExp, src = text) => clean(re.exec(src)?.[1] ?? '')
  const total = /\|\s*\**Total dev\**\s*\|\s*\**([^|*\n]+)/i.exec(text)?.[1] ?? ''
  const qa = /\|\s*QA[^|]*\|\s*\**([^|*\n]+)/i.exec(text)?.[1] ?? ''
  const card = /card (?:é|e|fica em)\s*\**(\d+)\s*SP(\s*ou mais)?/i.exec(text)
  const split = pick(/Total\s*\**\s*≈?\s*(\d+\s*SP)/i)
  return {
    sp: pick(/(\d+(?:\s*[-–]\s*\d+)?|>\s*13)\s*SP\b/i, line) || pick(/Recomenda[çc][aã]o:\s*(\d+(?:\s*[-–]\s*\d+)?)\s*SP/i) ||
      pointsFromList(text) || pick(/\bStory points:\**\s*([^\n—]+)/i) || pick(/(\d+(?:\s*[-–]\s*\d+)?)\s*SP\b/),
    hours: pick(/·\s*([\d,.]+\s*[-–]\s*[\d,.]+\s*h)\b/, line) || pick(/\*\*Total[^|]*\*\*\s*\|\s*\**([^|*\n]+)/i),
    complexity: pick(/complexidade\s*:?\s*\**([A-Za-zÀ-ú ]+?)\**\s*(?:[·—,\n]|$)/i, line) ||
      pick(/\*\*Complexidade:\*\*\s*([^—\n]+)/i),
    confidence: pick(/confian[çc]a\s*:?\s*\**([A-Za-zÀ-ú]+)/i, line) || pick(/\*\*Confian[çc]a:\*\*\s*([^—\n]+)/i),
    spCard: card ? `${card[1]}${card[2] ? '+' : ''} SP` : '',
    spSplit: split ? `≈ ${split}` : '',
    devDays: clean(total.replace(/≈\s*/, '')),
    qaDays: clean(qa.replace(/≈\s*/, '')),
    level: pick(/N[íi]vel AiDW:\**\s*\**([a-zçã]+)/i),
    passes: cut(pick(/Passadas extras:\**\s*([^\n]+)/i), 160),
    risks: parseRisks(text),
  }
}

/** `- **Riscos:**` com o texto na linha e/ou os subtópicos recuados; no modelo antigo, a seção `## Riscos`. */
function parseRisks(text: string): string {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const head = /^\s*[-*]\s*\*\*Riscos:?\*\*:?\s*/i
  const i = lines.findIndex(l => head.test(l))
  if (i < 0) return parseSection(text, /^##\s+(?:\d+\.\s*)?Riscos/i)
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

/** O corpo de uma seção `## <título>` até a próxima de mesmo nível ou acima, sem linhas vazias nas pontas. */
export function parseSection(text: string, title: RegExp): string {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const start = lines.findIndex(l => /^##\s/.test(l) && title.test(l))
  if (start < 0) return ''
  const end = lines.findIndex((l, i) => i > start && /^#{1,2}\s/.test(l))
  return lines.slice(start + 1, end < 0 ? undefined : end).join('\n').trim()
}

/** O que o card pede: o parágrafo do `**Card:**` do levantamento. */
export function parseCardAsk(text: string): string {
  const m = /\*\*Card:\*\*\s*([\s\S]*?)(?:\n\s*\n|\n\|)/.exec(text.replace(/\r\n/g, '\n'))
  return cut(clean(m?.[1] ?? ''), 600)
}

/**
 * As linhas "Hoje no código | Para a demanda | Situação" do levantamento. Sem a coluna de situação (modelo
 * antigo), ela sai do texto: "não muda", "nada a reaproveitar", "a dor", senão "precisa mudar".
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
    if (lower.some(c => /^hoje no c[oó]digo/.test(c))) {
      cols = lower
      continue
    }
    if (!cols.length || /^-+$/.test((cells[0] ?? '').replace(/[:\s]/g, ''))) continue
    const effect = clean(cells[1] ?? '')
    const col = cols.findIndex(c => /situa/.test(c))
    const given = col >= 0 ? clean(cells[col] ?? '').toLowerCase() : ''
    const e = effect.toLowerCase()
    const situation = given ||
      (/n[aã]o mud/.test(e) ? 'não muda' : /nada a reaproveitar/.test(e) ? 'nada a reaproveitar' : /\bdor\b/.test(e) ? 'é a dor' : 'precisa mudar')
    out.push({ today: cut(clean(cells[0] ?? ''), 260), effect: cut(effect, 200), situation })
  }
  return out
}

/** Os blocos de esforço (`| Bloco | Dev (dias) |`), sem o total e sem o QA. */
export function parseEffort(text: string): EffortBlock[] {
  const out: EffortBlock[] = []
  let inTable = false
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    if (!line.startsWith('|')) {
      inTable = false
      continue
    }
    const cells = line.split('|').slice(1, -1).map(c => clean(c))
    if (/^bloco$/i.test(cells[0] ?? '') && /dias|\(h\)|horas/i.test(cells[1] ?? '')) {
      inTable = true
      continue
    }
    if (!inTable || /^-+$/.test((cells[0] ?? '').replace(/[:\s]/g, '')) || /^total|^qa\b/i.test(cells[0] ?? '')) continue
    const r = range(cells[1] ?? '')
    if (r) out.push({ name: cut(cells[0] ?? '', 60), min: r[0], max: r[1], label: (cells[1] ?? '').replace(/\s/g, '') })
  }
  return out
}

/** A recomendação de quebra (`| # | Item | SP |`). */
export function parseSplit(text: string): SplitItem[] {
  const out: SplitItem[] = []
  let inTable = false
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    const t = line.trim()
    if (!t.startsWith('|')) {
      if (t) inTable = false
      continue
    }
    const cells = t.split('|').slice(1, -1).map(c => clean(c))
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
 * As dúvidas da seção `## Dúvidas…`: `- **D1. pergunta** contexto` (as linhas recuadas seguintes também são
 * contexto), em grupos `**Tema**`, com `*Para:*` e `*Muda a estimativa:*` quando o levantamento traz; ou o modelo
 * antigo numerado (`1. pergunta *Por que importa:* … *Para:* …`).
 */
export function parseDoubts(text: string): Doubt[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const start = lines.findIndex(l => /^#{2,3}\s+(\d+\.\s*)?D[uú]vidas/i.test(l))
  if (start < 0) return []
  const out: Doubt[] = []
  let group = ''
  const tail = (s: string, re: RegExp) => clean(re.exec(s)?.[1] ?? '')
  const TO = /\*Para:\*\s*([^*\n]+?)(?:\s*\*|$)/i
  const AFFECTS = /\*Muda a estimativa:\*\s*([^*\n]+?)(?:\s*\*|$)/i
  for (let i = start + 1; i < lines.length && !/^#{1,2}\s/.test(lines[i] ?? ''); i++) {
    const line = lines[i] ?? ''
    const g = /^\s*\*\*([^*]+)\*\*\s*$/.exec(line)
    if (g) {
      group = clean(g[1] ?? '')
      continue
    }
    const d = /^\s*[-*]\s+\*\*D(\d+)\.\s*(.+?)\*\*\s*(.*)$/.exec(line)
    if (d) {
      let rest = d[3] ?? ''
      while (i + 1 < lines.length && /^\s{2,}\S/.test(lines[i + 1] ?? '') && !/^\s*[-*]\s+\*\*D\d+/.test(lines[i + 1] ?? '')) {
        i += 1
        rest += ` ${(lines[i] ?? '').trim()}`
      }
      out.push({
        n: Number(d[1]),
        id: `D${d[1]}`,
        question: cut(clean(d[2] ?? ''), 240),
        why: cut(clean(rest.replace(/\*Para:\*.*$/i, '').replace(/\*Muda a estimativa:\*.*$/i, '')), 320),
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
      question: cut(clean(rest.replace(/\*Por que importa:\*.*$/i, '').replace(/\*Para:\*.*$/i, '')), 240),
      why: cut(clean(/\*Por que importa:\*\s*([^*]+)/i.exec(rest)?.[1] ?? ''), 200),
      to: clean(/\*Para:\*\s*([^.*\n]+)/i.exec(rest)?.[1] ?? /\(([^)]*(?:PO|Tech Lead|time|QA)[^)]*)\)\s*$/i.exec(rest)?.[1] ?? ''),
      group,
      affects: tail(rest, AFFECTS),
    })
  }
  return out
}

// ---------------------------------------------------------------------------------------------------------------
// Plano e arquivos

/** `Nível:` e `Passadas extras:` do plano. */
export function parsePlanMeta(text: string): { level: string | null; passes: string; version: string } {
  const h1 = /^#\s+(.+)$/m.exec(text)?.[1] ?? ''
  return {
    level: /N[íi]vel:\**\s*\**\s*(trivial|simples|padrao|complexa|critica)/i.exec(text)?.[1]?.toLowerCase() ?? null,
    passes: cut(clean(/Passadas extras:\**\s*([^\n]+)/i.exec(text)?.[1] ?? ''), 160),
    version: /\bv(\d+(?:\.\d+)?)\b/.exec(h1)?.[1] ?? '',
  }
}

/** O arquivo mais recente de uma família (`review-*-rN.md` → maior N). */
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

const GROUPS: [RegExp, string][] = [
  [/^resumo|^pontos-/, 'Card'],
  [/^exploracao-/, 'Exploração'],
  [/^plano-testes|^roteiro-|^qa-|^teste-orquestrador|^resultado-|^ambiente-teste/, 'Testes'],
  [/^plano-|^revisao-plano|^triagem-plano/, 'Plano'],
  [/^tarefa-/, 'Tarefas'],
  [/\.patch$/, 'Diffs'],
  [/^review-|^triagem-|^checklist-|^bugs?-|^bug-hunt|^seguranca|^auditoria/, 'Revisão'],
  [/^levantamento-/, 'Levantamento'],
  [/^revisao-final|^rascunho-/, 'Revisão final'],
  [/^aprendizados-|^metricas|^estado|^cobertura-/, 'Registro'],
]

/** Os arquivos da demanda, agrupados por etapa (o resto em "Outros"). */
export function groupArtifacts(files: string[]): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  for (const f of files.filter(f => /\.(md|patch|txt|json)$/.test(f) && f !== 'demand.json').sort()) {
    const group = GROUPS.find(([re]) => re.test(f))?.[1] ?? 'Outros'
    ;(out[group] ??= []).push(f)
  }
  return out
}
