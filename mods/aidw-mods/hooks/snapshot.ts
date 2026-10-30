// O retrato da demanda que os painéis e a faixa mostram, montado a partir dos arquivos da pasta. Puro: `wanted` diz
// quais arquivos ler, o register.tsx lê e entrega os textos, `buildSnapshot` monta.

import type { CoverageItem, Finding, ManualStep, PrTriage, Repo, Snapshot } from '../types'
import { budgetFor, parseDelegations, parseOrchestrator, roundFor } from './aidw'
import {
  decisionOf,
  groupArtifacts,
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
  parseRoteiro,
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

const REVIEW = /^review-.*-r(\d+)\.md$/
const PLAN_REVIEW = /^revisao-plano-.*-r(\d+)\.md$/
const BUGS = /^(?:bugs|bug-hunt)-.*-r(\d+)\.md$/
const SECURITY = /^(?:seguranca|auditoria-seguranca)-.*-r(\d+)\.md$/
const TRIAGE = /^triagem-(?!plano-).*-r(\d+)\.md$/
const PLAN_TRIAGE = /^triagem-plano-.*-r(\d+)\.md$/
const REPORT = /^(?:qa|teste-orquestrador)-.*-r(\d+)\.md$/

/** O plano vigente: `plano-<id>.md` (sem `-vN`); sem ele, a maior versão. */
function planFile(files: string[]): string | null {
  const plans = files.filter(f => /^plano-.*\.md$/.test(f) && !/^plano-testes-/.test(f))
  return plans.find(f => !/-v\d+(\.\d+)?\.md$/.test(f)) ?? latest(plans, /-v(\d+)(?:\.\d+)?\.md$/)?.file ?? null
}

/** O plano de testes vigente, com a mesma regra do plano. */
function testPlanFile(files: string[]): string | null {
  const all = files.filter(f => /^plano-testes-.*\.md$/.test(f))
  return all.find(f => !/-v\d+(\.\d+)?\.md$/.test(f)) ?? latest(all, /-v(\d+)(?:\.\d+)?\.md$/)?.file ?? null
}

const first = (files: string[], re: RegExp) => files.filter(f => re.test(f)).sort().at(-1) ?? null

/** Os arquivos que `buildSnapshot` precisa ler. */
export function wanted(files: string[]): string[] {
  const out = new Set<string>()
  const add = (f: string | null | undefined) => f && out.add(f)
  add(files.includes('metricas.md') ? 'metricas.md' : null)
  add(files.includes('metricas-orquestrador.md') ? 'metricas-orquestrador.md' : null)
  add(planFile(files))
  add(testPlanFile(files))
  add(first(files, /^resumo.*\.md$/))
  add(first(files, /^roteiro-testes.*\.md$/))
  add(first(files, /^levantamento-.*\.md$/))
  add(first(files, /^pontos-.*\.md$/))
  add(first(files, /^cobertura-.*\.md$/))
  add(latest(files, REPORT)?.file)
  for (const f of files) if (/^resultado-e2e.*\.md$/.test(f)) add(f)
  for (const re of [REVIEW, PLAN_REVIEW, BUGS, SECURITY, TRIAGE, PLAN_TRIAGE]) for (const f of files) if (re.test(f)) add(f)
  return [...out]
}

export type SnapshotInput = {
  dir: string
  demand: DemandFile
  files: string[]
  texts: Record<string, string>
  maxRetries: number
  /** Limite do laço revisão do plano ⇄ correção (routing.toml `max_retries_plan`); sem ele, o `maxRetries`. */
  maxRetriesPlan?: number
  /** Etapas de fora do contexto (`runtime.json` → `external_steps`). */
  externalSteps?: ExternalStep[]
}

/** A triagem da última rodada de uma revisão de PR, quando segue a referência *triagem-pr*. */
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
  const delegations = parseDelegations(text('metricas.md'))
  const plan = parsePlanMeta(text(planFile(files)))
  const level = plan.level ?? delegations.at(-1)?.level ?? null
  const { round, kind: roundKind } = roundFor(step, files, demand.loop)
  const maxRetries = roundKind === 'plano' ? (input.maxRetriesPlan ?? input.maxRetries) : input.maxRetries

  // achados: todas as rodadas, com a triagem de cada uma
  const findings: Finding[] = []
  // a triagem de cada rodada vale para os achados daquela rodada (o mesmo id volta nas rodadas seguintes)
  const decisions: Record<string, string> = {}
  const published = new Set<string>()
  for (const f of files) {
    for (const [re, source] of [[REVIEW, 'revisão'], [PLAN_REVIEW, 'plano'], [BUGS, 'bugs'], [SECURITY, 'segurança']] as const) {
      const m = re.exec(f)
      if (m) findings.push(...parseFindings(text(f), Number(m[1]), source, f))
    }
    const t = TRIAGE.exec(f) ?? PLAN_TRIAGE.exec(f)
    if (t) {
      const parsed = parseTriage(text(f))
      const plan = PLAN_TRIAGE.test(f) ? 'p' : 'c'
      for (const [id, d] of Object.entries(parsed.decisions)) {
        decisions[`${plan}${t[1]}:${id}`] = d
        decisions[id] ??= d
      }
      for (const id of parsed.published) published.add(id)
    }
  }
  for (const f of findings) {
    f.triage = decisions[`${f.source === 'plano' ? 'p' : 'c'}${f.round}:${f.id}`] ?? decisions[f.id] ?? ''
    f.published = published.has(f.id)
    f.decision = decisionOf(f.triage)
    f.recommendation = f.triage || f.recommendation
  }
  // um achado que a rodada seguinte da mesma revisão dá como corrigido: "corrigido na rN"
  const family = (f: Finding) => f.file.replace(/-r\d+\.md$/, '')
  for (const f of findings) {
    if (f.title) continue
    const earlier = findings.find(g => family(g) === family(f) && g.id === f.id && g.round < f.round && g.title)
    f.title = earlier?.title ?? (f.status ? `reapresentado (${f.status})` : 'sem descrição')
    if (!f.where) f.where = earlier?.where ?? ''
  }
  for (const f of findings) {
    if (/corrig|fixed|resolv/.test(f.status)) continue
    const later = findings.find(g => family(g) === family(f) && g.id === f.id && g.round > f.round && /corrig|fixed|resolv/.test(g.status))
    if (later) f.status = `corrigido na r${later.round}`
  }
  findings.sort((a, b) => a.round - b.round || a.id.localeCompare(b.id))

  // critérios: do plano (desenvolvimento) ou do resumo do card; como provar e o resultado dos relatórios
  const criteria = parseCriteria(text(planFile(files))).length
    ? parseCriteria(text(planFile(files)))
    : parseCriteria(text(first(files, /^resumo.*\.md$/)))
  const how = parseTestMatrix(text(testPlanFile(files)))
  const verdicts = {
    ...Object.assign({}, ...files.filter(f => /^resultado-e2e.*\.md$/.test(f)).sort().map(f => parseVerdicts(text(f)))),
    ...parseVerdicts(text(latest(files, REPORT)?.file)),
  } as Record<string, { result: string; evidence: string }>
  for (const c of criteria) {
    c.how = how[c.id] ?? []
    c.result = verdicts[c.id]?.result ?? ''
    c.evidence = verdicts[c.id]?.evidence ?? ''
  }

  // critérios, regras e cenários (CA/RN/CN) com a cobertura pelo nosso código e testes
  const planText = text(planFile(files))
  const roteiro = first(files, /^roteiro-testes.*\.md$/) ?? ''
  const manual = parseRoteiro(text(roteiro))
  const coverageFile = first(files, /^cobertura-.*\.md$/)
  // demandas de antes do fluxo v3 têm o cobertura-<id>.md; nas novas o status sai do plano, da etapa e do roteiro
  const status = coverageFile ? parseCoverage(text(coverageFile)) : derivedCoverage(planText, demand, manual)
  const coverage: CoverageItem[] = []
  for (const kind of ['CA', 'RN', 'CN'] as const) {
    const items = parseItems(`${planText}\n${text(testPlanFile(files))}`, kind)
    const list = items.length || kind !== 'CA' ? items : criteria.map(c => ({ id: c.id, text: c.text }))
    for (const it of list) coverage.push({ id: it.id, kind, text: it.text, status: status[it.id] ?? 'falta' })
  }

  const levantamento = first(files, /^levantamento-.*\.md$/) ?? ''
  const lev = text(levantamento)
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
    artifacts: groupArtifacts(files),
    patches: files.filter(f => f.endsWith('.patch')).sort(),
    level,
    passes: plan.passes,
    planVersion: plan.version,
    round,
    roundKind,
    maxRetries,
    delegations,
    tokens: delegations.reduce((n, d) => n + d.tokens, 0),
    orchestrator: parseOrchestrator(text('metricas-orquestrador.md')),
    budget: budgetFor(level),
    findings,
    prTriage: prTriageOf(kind, files, f => text(f)),
    criteria,
    coverage,
    coverageRecorded: !!coverageFile || !!planText,
    manual,
    roteiro,
    points: parsePoints(lev, text(first(files, /^pontos-.*\.md$/))),
    cardAsk: parseCardAsk(lev),
    cardPoints: parseCardPoints(lev),
    effort: parseEffort(lev),
    split: parseSplit(lev),
    estimate: lev ? parseEstimate(lev) : null,
    doubts: parseDoubts(lev),
    touches: parseSection(lev, /Onde a mudan[çc]a toca/i),
    levantamento,
    testMarks: null,
  }
}

/** As etapas em que a entrega já está implementada (o código existe, mesmo que ainda sem teste). */
const IMPLEMENTED_STEPS = new Set([
  'REVIEW', 'TRIAGE', 'CODER_FIX', 'USER_REVIEW', 'TEST', 'TEST_ADJUST', 'MANUAL_TEST', 'PR', 'CODE_REVIEW', 'QA_TEST',
  'UX_VALIDATION', 'DONE', 'PREPARE_REVIEW', 'ORCHESTRATOR_TEST', 'DOCS', 'FINAL_REVIEW',
])

/**
 * A cobertura sem arquivo (fluxo v3): *coberto* quando um passo do roteiro que prova o item tem ✅; *implementado*
 * quando a demanda já passou da implementação e o item está numa entrega do plano (`Covers:`/`Cobre:`), ou em
 * qualquer entrega quando o plano não diz; senão *falta*.
 */
export function derivedCoverage(plan: string, demand: DemandFile, manual: ManualStep[]): Record<string, CoverageItem['status']> {
  const out: Record<string, CoverageItem['status']> = {}
  const past = IMPLEMENTED_STEPS.has(demand.step ?? '') || (demand.history ?? []).some(h => IMPLEMENTED_STEPS.has(h.step))
  if (past) {
    const covered = [...plan.matchAll(/^[-*\s]*(?:\*\*)?(?:Covers|Cobre)(?:\*\*)?:?\s*(?:\*\*)?([^\n·]+)/gim)]
      .flatMap(m => [...(m[1] ?? '').matchAll(/\b(CA|RN|CN)\s*0*(\d+)\b/g)].map(x => `${x[1]}${x[2]}`))
    const ids = covered.length ? covered : [...plan.matchAll(/\b(CA|RN|CN)\s*0*(\d+)\b/g)].map(x => `${x[1]}${x[2]}`)
    for (const id of ids) out[id] = 'implementado'
  }
  for (const step of manual) {
    if (step.removed || step.result !== '✅') continue
    for (const id of step.criteria) out[id] = 'coberto'
  }
  return out
}

/** A fase em que a demanda está, pelo nome da linha do tempo (Revisar, Revisão final…). */
export function phaseOf(s: Snapshot): string {
  return s.timeline.find(t => t.state === 'atual')?.name ?? s.timeline.filter(t => t.state === 'feito').at(-1)?.name ?? s.step
}

const DOING: [string[], string][] = [
  [['UNDERSTAND'], 'O orquestrador está entendendo o card; se tiver dúvida, ele pergunta no chat.'],
  [['EXPLORE'], 'O explorador está mapeando o código.'],
  [['SPEC', 'PLAN'], 'O plano está sendo escrito.'],
  [['PLAN_REVIEW'], 'O plano está em revisão.'],
  [['PLAN_FIX'], 'O plano está sendo ajustado.'],
  [['TICKETS'], 'O plano está sendo dividido em tarefas.'],
  [['IMPLEMENT', 'TEST_PLAN'], 'O codificador está implementando; o QA monta o roteiro e a massa em paralelo.'],
  [['TEST_ADJUST'], 'O codificador está aplicando um ajuste temporário de teste.'],
  [['TEST', 'ORCHESTRATOR_TEST'], 'O QA está rodando os testes automáticos (API e navegador).'],
  [['PREPARE_REVIEW', 'REVIEW'], 'O código está em revisão.'],
  [['CODER_FIX'], 'O codificador está corrigindo o que foi mantido.'],
  [['DOCS'], 'A documentação está sendo atualizada.'],
  [['ESTIMATE'], 'A estimativa está sendo montada.'],
  [['RETURN'], 'O orquestrador está voltando a uma etapa anterior.'],
]

/** As etapas do laço de revisão: só nelas o limite de rodadas trava (as antigas ficam pelas demandas abertas). */
export const LOOP_STEPS = new Set(['REVIEW', 'TRIAGE', 'CODER_FIX', 'PLAN_REVIEW', 'PLAN_FIX', 'PREPARE_REVIEW'])

/** O próximo passo em uma frase: o que você faz, ou o que o AiDW está fazendo. */
export function nextStep(s: Snapshot, limit: number): { you: boolean; text: string } {
  if (s.status === 'paused') return { you: true, text: `Pausada. \`/aidw:go ${s.id}\` retoma de onde parou.` }
  if (s.step === 'DONE' || s.status === 'done')
    return { you: false, text: 'Concluída. Se ainda não rodou, `/aidw:done` grava o que ela ensinou na base de conhecimento.' }
  if (s.kind === 'desenvolvimento' && s.roundKind && s.round >= limit && LOOP_STEPS.has(s.step))
    return { you: true, text: `O laço de ${s.roundKind} chegou ao limite (${s.round} de ${limit}): libere +1 rodada ou decida no chat.` }
  switch (s.step) {
    case 'HUMAN_APPROVAL':
      return { you: true, text: 'Responda no chat: o orquestrador espera sua aprovação ou resposta.' }
    case 'PLAN_APPROVAL':
      return { you: true, text: 'Leia o plano e diga no chat se aprova ou o que ajustar; nada vai para o código antes disso.' }
    case 'TRIAGE':
      return { you: true, text: 'Decida cada achado na aba Revisão (manter ou descartar) e leve as decisões ao prompt.' }
    case 'USER_REVIEW':
      return { you: true, text: 'Revise o código na aba Diffs e diga no chat se aprova ou o que mudar.' }
    case 'MANUAL_TEST':
      return { you: true, text: 'Siga os passos manuais na aba Testes e marque cada um.' }
    case 'PR':
      return { you: true, text: 'Confira o commit, o texto da PR e as pendências para a QA e dê o OK no chat.' }
    case 'FINAL_REVIEW':
      return {
        you: true,
        text:
          s.kind === 'pr-review'
            ? 'Escolha o que publicar e se o AiDW aprova cada PR na aba Comentários.'
            : s.kind === 'levantamento'
              ? 'Confira a estimativa e as dúvidas e diga se publica o comentário no card.'
              : 'Confira a entrega (abas Critérios e Diffs) e diga no chat se aprova; depois, `/aidw:done` fecha a demanda.',
      }
  }
  const doing = DOING.find(([steps]) => steps.includes(s.step))?.[1]
  return { you: false, text: doing ?? `Etapa ${s.step}: o orquestrador segue sozinho.` }
}

/** O `state` do agente em palavras: "review_changes_requested" → "pediu mudanças". */
export function stateLabel(state: string): string {
  const s = state.toLowerCase()
  if (!s || s === '—') return '—'
  if (s === 'missing_state') return 'sem state'
  if (/changes_requested|findings/.test(s)) return /audit/.test(s) ? 'achou problemas' : 'pediu mudanças'
  if (/approved/.test(s)) return 'aprovado'
  if (/clean/.test(s)) return 'nada encontrado'
  if (/blocked/.test(s)) return 'bloqueado'
  if (/requires_approval|needs_input|question/.test(s)) return 'precisa de você'
  if (/fail|error/.test(s)) return 'falhou'
  if (/complete|done|ok$/.test(s)) return 'concluído'
  return state
}

/** Resumo de uma linha da demanda para recolocar no contexto depois de uma compactação. */
export function stateNote(s: Snapshot): string {
  const open = s.findings.filter(f => f.round === s.round && /CRITICO|IMPORTANTE/.test(f.severity ?? '') && !/corrig|resolv|fixed/.test(f.status))
  return [
    `AiDW (mod aidw-mods): estado da demanda ${s.id} relido do disco depois da compactação.`,
    `- Uso: ${s.kind}; etapa gravada: ${s.step}${s.waiting ? ` (espera o usuário: ${s.waiting})` : ''}.`,
    `- Pasta da demanda: ${s.dir}${s.repos.length ? `; worktrees: ${s.repos.map(r => `${r.name} → ${r.path}`).join(', ')}` : ''}.`,
    s.roundKind ? `- Laço de ${s.roundKind}: rodada ${s.round} de ${s.maxRetries}.` : '',
    open.length ? `- Achados abertos da última rodada: ${open.map(f => `${f.id} ${f.severity}`).join(', ')}.` : '',
    `- Delegações: ${s.delegations.length} (${s.tokens} tokens). Releia a skill do orquestrador, o demand.json e os artefatos da etapa antes de seguir.`,
  ]
    .filter(Boolean)
    .join('\n')
}
