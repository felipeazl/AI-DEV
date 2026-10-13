// Leitura dos artefatos de uma demanda do AiDW para os painéis: o tipo de uso, a linha do tempo, os achados da
// revisão e a triagem, os critérios de aceite e o teste, o roteiro manual e o levantamento. Puro (sem `$`): o
// register.tsx lê os arquivos e entrega o texto. Os formatos reais variam entre demandas: as regras são tolerantes.

import type {
  Criterion,
  DemandKind,
  Doubt,
  Estimate,
  Finding,
  ManualStep,
  Point,
  TimelineItem,
} from '../types'

export type { Criterion, Doubt, Estimate, Finding, ManualStep, Point, TimelineItem }

// ---------------------------------------------------------------------------------------------------------------
// Tipo de uso e linha do tempo

export type DemandFile = { id?: string; title?: string; step?: string; status?: string; mode?: string; note?: string;
  repos?: { repo?: string; path?: string; branch?: string; base?: string; system?: string | null; pr?: string;
    head?: string; source?: string }[]; history?: { step: string; at: string }[] }

/** Desenvolvimento, revisão de PR ou levantamento — o demand.json não grava o workflow; os arquivos dizem. */
export function kindOf(demand: DemandFile, files: string[]): DemandKind {
  const plan = files.some(f => /^plano-.*\.md$/.test(f) && !/^plano-testes-/.test(f))
  if ((demand.repos ?? []).some(r => r.pr) || files.some(f => /^diff-pr\d+-/.test(f))) return plan ? 'desenvolvimento' : 'pr-review'
  if (!plan && (files.some(f => /^(levantamento|pontos)-.*\.md$/.test(f)) || /\(levantamento\)\s*$/i.test(demand.title ?? '') ||
    (demand.history ?? []).some(h => h.step === 'ESTIMATE'))) return 'levantamento'
  return 'desenvolvimento'
}

export const KIND_LABEL: Record<DemandKind, string> = {
  desenvolvimento: 'Desenvolvimento',
  'pr-review': 'Revisão de PR',
  levantamento: 'Levantamento',
}

type Phase = { name: string; steps: string[] }

const PHASES: Record<DemandKind, Phase[]> = {
  desenvolvimento: [
    { name: 'Entender', steps: ['UNDERSTAND'] },
    { name: 'Explorar', steps: ['EXPLORE'] },
    { name: 'Plano', steps: ['TEST_PLAN', 'PLAN_REVIEW', 'PLAN_FIX'] },
    { name: 'Tickets', steps: ['TICKETS'] },
    { name: 'Implementar', steps: ['IMPLEMENT', 'TEST_ADJUST'] },
    { name: 'Testar', steps: ['TEST', 'ORCHESTRATOR_TEST'] },
    { name: 'Revisar', steps: ['PREPARE_REVIEW', 'REVIEW', 'CODER_FIX'] },
    { name: 'Teste manual', steps: ['MANUAL_TEST'] },
    { name: 'Documentar', steps: ['DOCS'] },
    { name: 'Revisão final', steps: ['FINAL_REVIEW'] },
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

/** A demanda espera o Felipe: aprovação, dúvida, teste manual ou revisão final. */
export function waitingFor(step: string | undefined): string | null {
  switch (step) {
    case 'HUMAN_APPROVAL':
      return 'sua aprovação ou resposta'
    case 'MANUAL_TEST':
      return 'o teste manual'
    case 'FINAL_REVIEW':
      return 'a revisão final'
    default:
      return null
  }
}

// ---------------------------------------------------------------------------------------------------------------
// Revisão: achados e triagem

type Severity = NonNullable<Finding['severity']>

const SEVERITY: [RegExp, Severity][] = [
  [/CR[IÍ]TICO/i, 'CRITICO'],
  [/IMPORTANTE/i, 'IMPORTANTE'],
  [/SUGEST[AÃ]O/i, 'SUGESTAO'],
  [/ELOGIO/i, 'ELOGIO'],
]
const STATUS = /\b(corrigido|n[aã]o corrigido|resolvido|aberto|fixed|not_fixed|open|mantido|refutado)\b/i
const HEADING = /^###\s+([RPBS]\d+-D?\d+)(?:\s*=\s*[RPBS]\d+-D?\d+)?\s+[—–-]\s+(.*)$/

const clean = (s: string) => s.replace(/\*\*/g, '').replace(/\s+/g, ' ').trim()
const cut = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s)

/** Os achados de um review (`review-*-rN.md`, `revisao-plano-*-rN.md`, `bugs-*`, `seguranca-*`). */
export function parseFindings(text: string, round: number, source: Finding['source']): Finding[] {
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
    out.push({
      id,
      round,
      source,
      severity,
      where,
      title: cut(clean(what || segments.join(' — ')), 160),
      status: clean(status).toLowerCase(),
      triage: '',
      comment: draft.split('\n').map(l => l.replace(/^>\s?/, '')).join('\n').trim(),
      published: false,
    })
  }
  return out
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
    if (publishing) for (const id of line.match(/\b[RPBS]\d+-D?\d+\b/g) ?? []) published.add(id)
    if (line.startsWith('|')) {
      const cells = line.split('|').slice(1, -1).map(c => clean(c))
      if (cells[0] === 'ID') {
        header = cells.map(c => c.toLowerCase())
        continue
      }
      const id = /^([RPBS]\d+-D?\d+)/.exec(cells[0] ?? '')?.[1]
      if (!id) continue
      const col = header.findIndex(h => /triagem|decis/.test(h))
      const decision = col >= 0 ? cells[col] : cells.slice(1).join(' · ')
      const why = header.findIndex(h => /motivo|evid/.test(h))
      decisions[id] = cut([decision, why >= 0 ? cells[why] : ''].filter(Boolean).join(' — '), 200)
      continue
    }
    const bullet = /^\s*-\s+\**([RPBS]\d+-D?\d+)\**\s*[:—–-]\s*(.+)$/.exec(line)
    if (bullet?.[1] && !publishing) decisions[bullet[1]] = cut(clean(bullet[2] ?? ''), 200)
  }
  return { decisions, published: [...published] }
}

/** O voto sugerido de um review de PR. */
export function parseVote(text: string): string {
  return clean(/Voto sugerido:\s*([^\n]+)/i.exec(text)?.[1] ?? /\*\*Veredito[^\n]*\n((?:-[^\n]*\n?)+)/i.exec(text)?.[1] ?? '')
}

export const VOTES = [
  { value: 'approve', label: 'Aprovar (10)' },
  { value: 'approve_with_suggestions', label: 'Aprovar com sugestões (5)' },
  { value: 'wait_for_author', label: 'Aguardar o autor (−5)' },
  { value: 'reject', label: 'Rejeitar (−10)' },
] as const

/** O voto sugerido como valor do Select. */
export function voteValue(suggested: string): string {
  const s = suggested.toLowerCase()
  if (/rejeit|-10/.test(s)) return 'reject'
  if (/aguard|-5|wait/.test(s)) return 'wait_for_author'
  if (/sugest|ajuste|\b5\b/.test(s)) return 'approve_with_suggestions'
  if (/aprov|approve|10/.test(s)) return 'approve'
  return 'wait_for_author'
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
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    if (!line.startsWith('|')) continue
    const cells = line.split('|').slice(1, -1).map(c => c.trim())
    const lower = cells.map(c => clean(c).toLowerCase())
    if (lower.some(c => c === 'passo' || c === 'o que fazer') && lower.some(c => /esperado/.test(c))) {
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
  return {
    sp: pick(/(\d+(?:\s*[-–]\s*\d+)?|>\s*13)\s*SP\b/i, line) || pick(/Recomenda[çc][aã]o:\s*(\d+(?:\s*[-–]\s*\d+)?)\s*SP/i) ||
      pointsFromList(text) || pick(/\bStory points:\**\s*([^\n—]+)/i) || pick(/(\d+(?:\s*[-–]\s*\d+)?)\s*SP\b/),
    hours: pick(/·\s*([\d,.]+\s*[-–]\s*[\d,.]+\s*h)\b/, line) || pick(/\*\*Total[^|]*\*\*\s*\|\s*\**([^|*\n]+)/i),
    complexity: pick(/complexidade\s*:?\s*\**([A-Za-zÀ-ú ]+?)\**\s*(?:[·—,\n]|$)/i, line) ||
      pick(/\*\*Complexidade:\*\*\s*([^—\n]+)/i),
    confidence: pick(/confian[çc]a\s*:?\s*\**([A-Za-zÀ-ú]+)/i, line) || pick(/\*\*Confian[çc]a:\*\*\s*([^—\n]+)/i),
  }
}

/** As dúvidas da seção `## Dúvidas…` (numeradas), com por que importa e para quem. */
export function parseDoubts(text: string): Doubt[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const start = lines.findIndex(l => /^#{2,3}\s+(\d+\.\s*)?D[uú]vidas/i.test(l))
  if (start < 0) return []
  const out: Doubt[] = []
  for (let i = start + 1; i < lines.length && !/^#{1,2}\s/.test(lines[i] ?? ''); i++) {
    // `- **D1. Qual é o produto?** contexto…` (formato dos levantamentos antigos)
    const d = /^\s*[-*]\s+\*\*D(\d+)\.\s*(.+?)\*\*\s*(.*)$/.exec(lines[i] ?? '')
    if (d) {
      out.push({ n: Number(d[1]), question: cut(clean(d[2] ?? ''), 240), why: cut(clean(d[3] ?? ''), 200), to: '' })
      continue
    }
    const m = /^\s*(\d+)[.)]\s+(.+)$/.exec(lines[i] ?? '')
    if (!m) continue
    const rest = m[2] ?? ''
    out.push({
      n: Number(m[1]),
      question: cut(clean(rest.replace(/\*Por que importa:\*.*$/i, '').replace(/\*Para:\*.*$/i, '')), 240),
      why: cut(clean(/\*Por que importa:\*\s*([^*]+)/i.exec(rest)?.[1] ?? ''), 200),
      to: clean(/\*Para:\*\s*([^.*\n]+)/i.exec(rest)?.[1] ?? /\(([^)]*(?:PO|Tech Lead|time|QA)[^)]*)\)\s*$/i.exec(rest)?.[1] ?? ''),
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
  [/^aprendizados-|^metricas|^estado/, 'Registro'],
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
