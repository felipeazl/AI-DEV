// As telas da faixa e do painel (V2, docs/painel.md). Recebem a tabela de elementos da superfície (não o `$`), os
// dados e as ações; o register.tsx monta as ações (que gravam o estado ou mandam a decisão do usuário ao orquestrador).

import type { Elements, ThemeKey } from 'claude-code'

import type { Delegation, DemandKind, DiffView, Doubt, Finding, PrComment, ReviewFilter, RunningAgent, Snapshot, Usage } from '../types'
import { CONTEXT_WARN, compact } from './aidw'
import { KIND_LABEL, VOTES, voteIn } from './artifacts'
import { LOOP_STEPS, stateLabel } from './snapshot'

type Desktop = Elements['desktop']
export type UI = Pick<Desktop, 'Box' | 'Text' | 'Button' | 'Select' | 'Input' | 'Code' | 'Markdown' | 'Link'> & {
  Svg?: Desktop['Svg']
}

export type Actions = {
  tab: (tab: string) => void
  refresh: () => void
  extraRound: () => void
  reviewFile: (file: string) => void
  decisionTab: (tab: string) => void
  decide: (id: string, value: string) => void
  toggleFilter: (kind: keyof Omit<ReviewFilter, 'open'>, value: string) => void
  toggleFilters: () => void
  sendReviewDecisions: () => void
  togglePublish: (id: string, value: boolean) => void
  vote: (value: string) => void
  votePr: (pr: string, value: string) => void
  sendPrDecision: () => void
  adjustInChat: (text: string) => void
  draft: (key: string, value: string) => void
  manualResult: (step: string, result: 'ok' | 'fail' | 'skip') => void
  answerDoubt: (id: string) => void
  postLevantamento: () => void
  diffSource: (source: string) => void
  diffFile: (path: string) => void
  appDiff: (repo: string) => void
  expand: (key: string) => void
}

export type ViewState = {
  snap: Snapshot
  running: RunningAgent[]
  now: number
  tab: string
  publish: Record<string, boolean>
  vote: string
  /** O voto escolhido por PR; sem escolha, vale a sugestão da triagem. */
  votes: Record<string, string>
  drafts: Record<string, string>
  diff: DiffView | null
  usage: Usage | null
  extraRounds: number
  columns: number
  /** `terminal` mostra a tecla de cada aba (`1: Geral`); no app as teclas funcionam sem aparecer. */
  surface: string
  canAppDiff: boolean
  /** A pasta da sessão: o painel de diff do app desktop mostra o repositório dela. */
  sessionCwd: string
  reviewFile: string
  decisionTab: string
  filter: ReviewFilter
  decisions: Record<string, string>
  expanded: Record<string, boolean>
}

export const TABS: Record<DemandKind, [string, string][]> = {
  desenvolvimento: [
    ['geral', 'Geral'],
    ['criterios', 'Critérios e Regras'],
    ['revisao', 'Revisão'],
    ['diffs', 'Diffs'],
    ['manual', 'Testes'],
    ['metricas', 'Métricas'],
  ],
  'pr-review': [
    ['geral', 'Geral'],
    ['comentarios', 'Comentários'],
    ['diffs', 'Diffs'],
    ['metricas', 'Métricas'],
  ],
  levantamento: [
    ['geral', 'Geral'],
    ['codigo', 'Card × código'],
    ['estimativa', 'Estimativa'],
    ['duvidas', 'Dúvidas'],
    ['metricas', 'Métricas'],
  ],
}

/** Nomes antigos das abas (`/aidw-painel fluxo`) e apelidos. */
const TAB_ALIAS: Record<string, string> = {
  fluxo: 'geral',
  agentes: 'metricas',
  métricas: 'metricas',
  critérios: 'criterios',
  revisão: 'revisao',
  pontos: 'codigo',
  card: 'codigo',
  dúvidas: 'duvidas',
  achados: 'comentarios',
  comentários: 'comentarios',
}

/** Uma aba só aparece quando tem o que mostrar; a Geral sempre. */
export function tabHasData(s: Snapshot, tab: string): boolean {
  switch (tab) {
    case 'criterios':
      return s.coverage.length > 0 || s.criteria.length > 0
    case 'revisao':
      return reviewRounds(s).length > 0
    case 'diffs':
      return diffSources(s).length > 0
    case 'manual':
      return s.manual.some(m => !m.removed)
    case 'metricas':
      return s.delegations.length > 0 || s.orchestrator.rows.length > 0
    case 'comentarios':
      return (s.prTriage?.comments.length ?? 0) > 0 || prList(s).length > 0
    case 'codigo':
      return !!s.cardAsk || s.cardPoints.length > 0 || s.points.length > 0
    case 'estimativa':
      return !!s.estimate
    case 'duvidas':
      return s.doubts.length > 0
    default:
      return true
  }
}

/** As abas do uso que têm dados. */
export function visibleTabs(s: Snapshot): [string, string][] {
  return TABS[s.kind].filter(([id]) => tabHasData(s, id))
}

/** Dúvida já respondida: o levantamento a põe num grupo "Respondidas …". */
const answered = (d: Doubt) => /respondid/i.test(d.group)

/** A tab pedida, ou a primeira do uso quando ela não existe nele. */
export function tabFor(kind: DemandKind, tab: string): string {
  const id = TAB_ALIAS[tab] ?? tab
  return TABS[kind].some(([t]) => t === id) ? id : (TABS[kind][0]?.[0] ?? 'geral')
}

// ---------------------------------------------------------------------------------------------------------------
// Cores e peças comuns

/**
 * As cores (docs/painel.md › Cores): chaves do tema do Claude, que o app pinta no tema claro ou escuro. Não há chave
 * de fundo neutro, então cartão é só borda e nada leva fundo.
 */
export const C = {
  text: 'text',
  strong: 'text',
  mid: 'text',
  dim: 'inactive',
  faint: 'subtle',
  line: 'promptBorder',
  claude: 'claude',
  blue: 'suggestion',
  amber: 'warning',
  green: 'success',
  red: 'error',
  purple: 'merged',
  done: 'subtle',
  bar: 'suggestion',
} as const satisfies Record<string, ThemeKey>

/**
 * O SVG é desenhado como imagem, fora do tema: cada chave usada nele ganha a cor do tema escuro e a do claro, e o
 * `prefers-color-scheme` do app escolhe (`[escuro, claro]`).
 */
const SVG_PAINT: Partial<Record<ThemeKey, [string, string]>> = {
  text: ['#e8e6e3', '#1f1e1d'],
  inactive: ['#8f8d87', '#6b6a64'],
  subtle: ['#6f6d68', '#b5b2a7'],
  promptBorder: ['#3a3937', '#e4e2da'],
  claude: ['#d97757', '#c15f3c'],
  suggestion: ['#7a9bd1', '#5b84c9'],
  warning: ['#e5a54b', '#a86400'],
  success: ['#8fd19e', '#2f7d45'],
  error: ['#f0a49c', '#b8402e'],
  merged: ['#c4a8e8', '#7a4fb5'],
}

const paintRules = (i: 0 | 1) =>
  Object.entries(SVG_PAINT)
    .map(([k, c]) => `.f-${k}{fill:${c[i]}}.s-${k}{stroke:${c[i]}}`)
    .join('')
const SVG_STYLE = `<style>${paintRules(1)}@media (prefers-color-scheme: dark){${paintRules(0)}}</style>`

/** Um documento SVG com as cores do tema; nos elementos, `fill(chave)` e `stroke(chave)`. */
export const svgDoc = (width: number, height: number, body: string) =>
  `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">${SVG_STYLE}${body}</svg>`
const fill = (key: string) => `class="f-${key}"`
const stroke = (key: string) => `class="s-${key}" fill="none"`

const pct = (n: number, of: number) => (of > 0 ? Math.round((n / of) * 100) : 0)
const secs = (s: number) =>
  s >= 3600
    ? `${Math.floor(s / 3600)}h${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}m`
    : s >= 60
      ? `${Math.floor(s / 60)}m${String(s % 60).padStart(2, '0')}s`
      : `${s}s`
const fileUrl = (p: string) => `file:///${encodeURI(p.replace(/\\/g, '/'))}`
const ddmm = (iso: string) => (/^\d{4}-(\d{2})-(\d{2})/.exec(iso) ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}` : iso)
const modelName = (m: string) => /opus|sonnet|haiku|fable/i.exec(m)?.[0]?.toLowerCase() ?? (m || '—')
const two = (n: number) => String(n).padStart(2, '0')
/** A hora local de um instante ISO (o `resetsAt` vem em UTC); com o dia quando não é hoje. */
export const localTime = (iso: string, now: number) => {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const hm = `${two(d.getHours())}:${two(d.getMinutes())}`
  return d.toDateString() === new Date(now).toDateString() ? hm : `${two(d.getDate())}/${two(d.getMonth() + 1)} ${hm}`
}

/** Uma barra fina de medição: SVG no app, blocos de texto onde não há SVG. */
function meter(ui: UI, key: string, percent: number, color: string, width = 64) {
  const p = Math.max(0, Math.min(100, percent))
  if (ui.Svg) {
    const w = Math.round((width * p) / 100)
    return (
      <ui.Svg
        key={key}
        alt={`${p}%`}
        width={width}
        height={6}
        source={svgDoc(width, 6, `<rect width="${width}" height="6" rx="3" ${fill(C.line)}/><rect width="${w}" height="6" rx="3" ${fill(color)}/>`)}
      />
    )
  }
  const full = Math.round(p / 10)
  return (
    <ui.Text key={key}>
      <ui.Text color={color}>{'▰'.repeat(full)}</ui.Text>
      <ui.Text color={C.line}>{'▱'.repeat(10 - full)}</ui.Text>
    </ui.Text>
  )
}

/** Uma seção, como os cartões do painel lateral do Claude: borda sutil, título em negrito, à direita um resumo. */
function card(ui: UI, key: string, label: string, children: unknown, right?: string) {
  const { Box, Text } = ui
  return (
    <Box key={key} flexDirection="column" borderStyle="round" borderColor={C.line} paddingX={2} paddingY={1} gap={1}>
      {(label || right) && (
        <Box justifyContent="space-between" gap={2}>
          <Text color={C.text} bold>
            {label}
          </Text>
          {right ? <Text color={C.dim}>{right}</Text> : <Text> </Text>}
        </Box>
      )}
      {children as never}
    </Box>
  )
}

function chip(ui: UI, key: string, text: string, color: string) {
  return (
    <ui.Text key={key} color={color} bold>
      {` ${text} `}
    </ui.Text>
  )
}

/** Texto dos artefatos: com `código` ou **negrito** vira Markdown; sem, Text. */
function rich(ui: UI, key: string, text: string, color: string = C.text) {
  if (/`|\*\*/.test(text) && ui.Markdown) return <ui.Markdown key={key} text={text} dimColor={color === C.dim} />
  return (
    <ui.Text key={key} color={color}>
      {text}
    </ui.Text>
  )
}

/** Uma linha de número: rótulo à esquerda, valor (e um medidor opcional) à direita. */
function stat(ui: UI, key: string, label: string, value: string, opts: { meter?: number; color?: string; missing?: boolean } = {}) {
  const { Box, Text } = ui
  return (
    <Box key={key} gap={2} alignItems="center">
      <Box flexGrow={1} flexShrink={1}>
        <Text color={C.dim}>{label}</Text>
      </Box>
      {opts.meter !== undefined && meter(ui, `${key}-m`, opts.meter, opts.color ?? C.green, 48)}
      <Text color={opts.missing ? C.faint : (opts.color ?? C.text)} bold={!opts.missing}>
        {value}
      </Text>
    </Box>
  )
}

/**
 * Escolher entre poucas opções (repositórios, PRs, rodadas): botões lado a lado, o escolhido com moldura; uma opção
 * só vira texto; mais de 4, o seletor do app.
 */
function choices(ui: UI, key: string, options: { value: string; label: string }[], value: string, onPick: (v: string) => void) {
  const { Box, Text, Button, Select } = ui
  if (options.length === 1) return <Text key={key} color={C.dim}>{options[0]?.label}</Text>
  if (options.length > 4) return <Select key={key} value={value} options={options} onSelect={onPick} />
  return (
    <Box key={key} gap={1} flexWrap="wrap">
      {options.map(o =>
        o.value === value ? (
          <Button key={`${key}-${o.value}`} label={o.label} onPress={() => onPick(o.value)} />
        ) : (
          <Button key={`${key}-${o.value}`} label={o.label} plain dimColor onPress={() => onPick(o.value)} />
        ),
      )}
    </Box>
  )
}

// ---------------------------------------------------------------------------------------------------------------
// Faixa acima do prompt

const WARN = 80

export function Band(ui: UI, s: Snapshot, running: RunningAgent[], usage: Usage | null, now: number) {
  const { Box, Text } = ui
  const parts: unknown[] = []
  const add = (key: string, label: string, percent: number, text: string, color: string) => {
    parts.push(
      <Box key={key} gap={1} alignItems="center">
        <Text color={color}>{label}</Text>
        {meter(ui, `${key}-m`, percent, color === C.dim ? C.dim : color)}
        <Text color={color}>{text}</Text>
      </Box>,
    )
  }
  if (usage) {
    // o contexto em tokens, com a barra cheia no ponto de compactar: cada ação relê a conversa inteira
    const ctx = Math.round((usage.tokens / CONTEXT_WARN) * 100)
    add('ctx', 'contexto', ctx, compact(usage.tokens), ctx >= 100 ? C.amber : C.dim)
    for (const kind of ['7d', '5h'] as const) {
      const l = usage.limits.find(x => x.kind === kind)
      if (!l) continue
      const p = Math.round(l.percent)
      const at = p >= WARN && l.resetsAt ? localTime(l.resetsAt, now) : ''
      if (p >= 100) add(kind, kind, 100, `limite${at ? ` · volta ${at}` : ''}`, C.red)
      else add(kind, kind, p, `${p}%${at ? ` · renova ${at}` : ''}`, p >= WARN ? C.amber : C.dim)
    }
  }
  // a etapa atual ao lado do id; o modelo quando não é desenvolvimento
  const where = [s.kind === 'desenvolvimento' ? '' : KIND_LABEL[s.kind], s.progress.current].filter(Boolean).join(' · ')
  return (
    <Box flexWrap="wrap" alignItems="center" gap={2}>
      <Box gap={1}>
        <Text color={C.claude} bold>
          AiDW
        </Text>
        <Text>{s.id}</Text>
        {where && <Text color={C.dim}>{where}</Text>}
      </Box>
      {running.map(a => (
        <Box key={`run-${a.key}`} gap={1}>
          <Text color={C.claude}>●</Text>
          <Text>{`${a.agent} · ${a.label} · ${secs(Math.max(0, Math.round((now - a.since) / 1000)))}`}</Text>
        </Box>
      ))}
      {parts as never}
    </Box>
  )
}

// ---------------------------------------------------------------------------------------------------------------
// Painel

/** A situação da demanda no cabeçalho: com o time, espera você, pausada, pronta, ou só a etapa. */
function situation(s: Snapshot): { text: string; color: string } {
  const outside = s.progress.stages.find(x => x.state === 'com-time')
  if (s.status === 'paused') return { text: 'Pausada', color: C.dim }
  if (s.step === 'DONE') return { text: 'Pronto', color: C.green }
  if (outside) return { text: `${outside.name} · com ${outside.who ?? 'o time'}`, color: C.blue }
  if (s.waiting) return { text: `${s.progress.current} · espera você`, color: C.amber }
  return { text: s.progress.current, color: C.dim }
}

/** O que espera você em cada aba (a contagem ao lado do nome). */
function tabCount(v: ViewState, tab: string): number {
  const s = v.snap
  switch (tab) {
    case 'revisao': {
      const file = defaultRound(s, v.reviewFile)
      return file ? roundFindings(s, file).filter(f => !(v.decisions[`${f.file}:${f.id}`] ?? (f.decision === 'pendente' ? '' : f.decision)) && !isFixed(f)).length : 0
    }
    case 'manual':
      return s.manual.filter(m => !m.removed && !m.result && !/prepara/i.test(m.section)).length
    case 'comentarios':
      return s.prTriage
        ? s.prTriage.comments.filter(c => !c.published && !c.declined && v.publish[c.id] === undefined).length
        : prList(s).filter(f => !f.published && v.publish[f.id] === undefined).length
    case 'duvidas':
      return s.doubts.filter(d => !answered(d)).length
    default:
      return 0
  }
}

export function Panel(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button } = ui
  const s = v.snap
  const tabs = visibleTabs(s)
  const wanted = tabFor(s.kind, v.tab)
  const tab = tabs.some(([id]) => id === wanted) ? wanted : 'geral'
  const terminal = v.surface === 'terminal'
  const sit = situation(s)
  const body =
    tab === 'metricas'
      ? Metrics(ui, v, act)
      : tab === 'criterios'
        ? Coverage(ui, v)
        : tab === 'revisao'
          ? Review(ui, v, act)
          : tab === 'diffs'
            ? Diffs(ui, v, act)
            : tab === 'manual'
              ? Manual(ui, v, act)
              : tab === 'comentarios'
                ? s.prTriage ? PrComments(ui, v, act) : PrFindings(ui, v, act)
                : tab === 'codigo'
                  ? CardCode(ui, v, act)
                  : tab === 'estimativa'
                    ? EstimateView(ui, v, act)
                    : tab === 'duvidas'
                      ? Doubts(ui, v, act)
                      : General(ui, v, act)
  return (
    <Box flexDirection="column" gap={1}>
      <Box key="hdr" flexDirection="column">
        <Box gap={2} flexWrap="wrap">
          <Text color={C.dim}>
            {s.id.toUpperCase().replace('-', ' ')} · {KIND_LABEL[s.kind]}
          </Text>
          <Text color={sit.color} bold>
            ● {sit.text}
          </Text>
        </Box>
        <Text bold color={C.strong}>
          {s.title || s.id}
        </Text>
      </Box>
      <Box flexWrap="wrap" gap={1} alignItems="center">
        {tabs.map(([id, label]) => {
          const n = tabCount(v, id)
          const hotkey = terminal ? String(TABS[s.kind].findIndex(([t]) => t === id) + 1) : undefined
          return id === tab ? (
            <Button key={`tab-${id}`} hotkey={hotkey} onPress={() => act.tab(id)}>
              {label}
              {n > 0 && <Text color={C.claude}> {n}</Text>}
            </Button>
          ) : (
            <Button key={`tab-${id}`} hotkey={hotkey} plain dimColor onPress={() => act.tab(id)}>
              {label}
              {n > 0 && <Text color={C.claude}> {n}</Text>}
            </Button>
          )
        })}
        <Button key="refresh" label="↻" hotkey={terminal ? 'r' : undefined} plain dimColor onPress={() => act.refresh()} />
      </Box>
      {body}
    </Box>
  )
}

// --- Geral -----------------------------------------------------------------------------------------------------

const STAGE_COLOR: Record<string, string> = {
  feito: C.done,
  atual: C.claude,
  'com-time': C.blue,
  voltou: C.amber,
  pendente: C.line,
}

/** A barra de progresso em dois grupos (AiDW · Time e QA): SVG no app, texto onde não há. */
function progressBar(ui: UI, s: Snapshot) {
  const { Box, Text } = ui
  const p = s.progress
  const groups = [
    { name: 'AiDW', stages: p.stages.filter(x => x.group === 'aidw') },
    { name: 'Time e QA', stages: p.stages.filter(x => x.group === 'fora') },
  ].filter(g => g.stages.length)
  if (ui.Svg) {
    const seg = 44
    const gap = 4
    const between = 18
    let x = 0
    const rects: string[] = []
    const labels: string[] = []
    for (const g of groups) {
      labels.push(`<text x="${x}" y="9" font-size="10" ${fill(C.dim)} font-family="system-ui,sans-serif">${g.name}</text>`)
      for (const st of g.stages) {
        // as etapas de fora ainda não alcançadas são pontos vazados, não segmentos: não parecem barra quebrada
        const hollow = g.name !== 'AiDW' && st.state === 'pendente'
        rects.push(
          hollow
            ? `<circle cx="${x + 6}" cy="18" r="4.25" ${stroke(C.faint)} stroke-width="1.5"><title>${st.name}</title></circle>`
            : `<rect x="${x}" y="15" width="${seg}" height="6" rx="3" ${fill(STAGE_COLOR[st.state] ?? C.line)}><title>${st.name}</title></rect>`,
        )
        x += (hollow ? 12 : seg) + gap
      }
      x += between - gap
    }
    const width = Math.max(1, x - between + gap)
    return (
      <ui.Svg
        key="progress"
        alt={`Etapa ${p.index} de ${p.total}: ${p.current}`}
        width={width}
        height={22}
        isInteractive
        source={svgDoc(width, 22, `${labels.join('')}${rects.join('')}`)}
      />
    )
  }
  return (
    <Box gap={2}>
      {groups.map(g => (
        <Text key={`pg-${g.name}`}>
          <Text color={C.dim}>{g.name} </Text>
          {g.stages.map(st => (
            <Text key={`ps-${st.name}`} color={STAGE_COLOR[st.state] ?? C.line}>
              {st.state === 'pendente' ? '▱' : '▰'}
            </Text>
          ))}
        </Text>
      ))}
    </Box>
  )
}

/** Os números da Geral: os do modelo da demanda e, em todos, o consumo. */
function numbers(ui: UI, s: Snapshot) {
  const seconds = s.delegations.reduce((n, d) => n + d.seconds, 0)
  const rows: unknown[] = []
  if (s.kind === 'desenvolvimento') {
    const ca = s.coverage.filter(c => c.kind === 'CA')
    const ok = ca.filter(c => c.status === 'coberto').length
    if (ca.length) rows.push(stat(ui, 'n-ca', 'Critérios de aceite cobertos', `${ok} de ${ca.length}`, { meter: pct(ok, ca.length) }))
    else if (s.criteria.length) rows.push(stat(ui, 'n-ca', 'Critérios de aceite', String(s.criteria.length)))
  } else if (s.kind === 'pr-review') {
    const list = s.prTriage ? s.prTriage.comments : prList(s)
    const published = list.filter(f => f.published).length
    rows.push(stat(ui, 'n-pr', 'PRs', String(prsOf(s).length || '—')))
    if (list.length) rows.push(stat(ui, 'n-pub', 'Comentários publicados', `${published} de ${list.length}`, { meter: pct(published, list.length) }))
  } else if (s.estimate) {
    const e = s.estimate
    const open = s.doubts.filter(d => !answered(d)).length
    rows.push(stat(ui, 'n-sp', 'Story points', e.sp || e.spCard || '—'))
    const hours = [e.devDays || e.hours, e.qaDays && `+ ${e.qaDays} QA`].filter(Boolean).join(' ')
    if (hours) rows.push(stat(ui, 'n-h', 'Horas', hours))
    const cc = [e.complexity, e.confidence].filter(Boolean).join(' · ')
    if (cc) rows.push(stat(ui, 'n-cc', 'Complexidade · confiança', cc))
    if (s.doubts.length) rows.push(stat(ui, 'n-d', 'Dúvidas abertas', `${open} de ${s.doubts.length}`, open ? { color: C.amber } : {}))
  }
  rows.push(stat(ui, 'n-tk', 'Tokens dos agentes', compact(s.tokens)))
  rows.push(
    s.orchestrator.rows.length
      ? stat(ui, 'n-or', 'Tokens do orquestrador', compact(s.orchestrator.tokens))
      : stat(ui, 'n-or', 'Tokens do orquestrador', 'sem registro', { missing: true }),
  )
  rows.push(stat(ui, 'n-tm', 'Agentes trabalhando', secs(seconds)))
  return rows
}

function General(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Link } = ui
  const s = v.snap
  const p = s.progress
  const outside = p.stages.find(x => x.state === 'com-time')
  const returns = Object.entries(p.returns).map(([k, n]) => `${k} ${n}×`).join(' · ')
  const last = s.delegations.at(-1)
  const currentColor = outside ? C.blue : C.claude
  return (
    <Box flexDirection="column" gap={1}>
      {card(
        ui,
        'mapa',
        'Mapa da demanda',
        <Box flexDirection="column" gap={1}>
          {s.summary ? rich(ui, 'summary', s.summary) : <Text color={C.dim}>Sem resumo gravado (o orquestrador grava ao entender o card).</Text>}
          <Box flexDirection="column">
            {progressBar(ui, s)}
            <Box justifyContent="space-between" gap={2}>
              <Box gap={1}>
                <Text color={currentColor} bold>
                  {p.current}
                </Text>
                {p.returnedFrom && chip(ui, 'volta', `↩ voltou do ${p.returnedFrom} · ${p.returns[p.returnedFrom] ?? 1}ª vez`, C.amber)}
              </Box>
              <Text color={C.dim}>
                {returns && !p.returnedFrom ? `voltas: ${returns} · ` : ''}etapa {p.index} de {p.total}
              </Text>
            </Box>
          </Box>
          {s.roundKind && s.round >= s.maxRetries + v.extraRounds && LOOP_STEPS.has(s.step) && (
            <Box gap={1}>
              <Text color={C.amber}>
                O laço de {s.roundKind} chegou ao limite ({s.round} de {s.maxRetries + v.extraRounds}).
              </Text>
              <ui.Button key="extra-round" label="Liberar +1 rodada" onPress={() => act.extraRound()} />
            </Box>
          )}
        </Box>,
      )}
      {card(ui, 'numeros', 'Números', <Box flexDirection="column">{numbers(ui, s) as never}</Box>)}
      {s.note && card(ui, 'proximo', 'Próximo passo', rich(ui, 'note', s.note), 'nota do orquestrador')}
      {card(
        ui,
        'agentes',
        'Agentes',
        <Box flexDirection="column">
          {v.running.length === 0 && (
            <Text color={C.dim}>{last ? `último: ${last.agent} (${last.label}), ${stateLabel(last.state)}` : 'nenhuma delegação ainda'}</Text>
          )}
          {v.running.map(r => (
            <Box key={`run-${r.key}`} gap={2}>
              <Text color={C.claude}>●</Text>
              <Text bold color={C.strong}>
                {r.agent}
              </Text>
              <Box flexGrow={1} flexShrink={1}>
                <Text color={C.mid}>{r.label}</Text>
              </Box>
              <Text color={C.dim}>{secs(Math.max(0, Math.round((v.now - r.since) / 1000)))}</Text>
            </Box>
          ))}
        </Box>,
        v.running.length ? `${v.running.length} rodando` : 'nenhum rodando',
      )}
      {card(
        ui,
        'links',
        'Links',
        <Box flexDirection="column">
          <Box gap={2}>
            <Box width={10}>
              <Text color={C.dim}>Pasta</Text>
            </Box>
            <Link key="lk-dir" href={fileUrl(s.dir)} label={`demandas/${s.id}`} />
          </Box>
          {s.repos.map(r => (
            <Box key={`br-${r.path}`} gap={2}>
              <Box width={10}>
                <Text color={C.dim}>{r.pr ? `PR ${r.pr}` : 'Branch'}</Text>
              </Box>
              <Link key={`lk-${r.path}`} href={fileUrl(r.path)} label={r.name} />
              <Box flexShrink={1}>
                <Text color={C.dim}>{r.pr ? 'só leitura' : r.branch || '?'}</Text>
              </Box>
            </Box>
          ))}
        </Box>,
      )}
    </Box>
  )
}

// --- Critérios e Regras ----------------------------------------------------------------------------------------

const COVER: Record<string, { label: string; color: string }> = {
  coberto: { label: 'Coberto', color: C.green },
  implementado: { label: 'Implementado', color: C.amber },
  falta: { label: 'Falta', color: C.dim },
}

function Coverage(ui: UI, v: ViewState) {
  const { Box, Text } = ui
  const s = v.snap
  const groups = [
    { kind: 'CA', label: 'Critérios de aceite', from: 'do card e do plano', unit: 'critérios de aceite' },
    { kind: 'RN', label: 'Regras de negócio', from: 'das decisões do plano', unit: 'regras de negócio' },
    { kind: 'CN', label: 'Cenários', from: 'do plano de testes', unit: 'cenários' },
  ].map(g => ({ ...g, items: s.coverage.filter(c => c.kind === g.kind) })).filter(g => g.items.length)
  if (!groups.length) {
    return <Text color={C.dim}>Sem critérios, regras ou cenários numerados no plano (CA1, RN1, CN1).</Text>
  }
  return (
    <Box flexDirection="column" gap={1}>
      {card(
        ui,
        'cob',
        'Cobertura no nosso código e nos nossos testes',
        <Box flexDirection="column" gap={1}>
          <Box gap={3}>
            {groups.map(g => {
              const ok = g.items.filter(i => i.status === 'coberto').length
              const impl = g.items.filter(i => i.status === 'implementado').length
              return (
                <Box key={`cg-${g.kind}`} flexDirection="column" flexGrow={1}>
                  <Text>
                    <Text bold color={C.strong}>
                      {ok}
                    </Text>
                    <Text color={C.dim}> de {g.items.length}</Text>
                  </Text>
                  {meter(ui, `cm-${g.kind}`, pct(ok + impl, g.items.length), impl ? C.amber : C.green, 120)}
                  <Text color={C.dim}>
                    {g.unit}
                    {impl ? ` · ${impl} implementado(s)` : ''}
                  </Text>
                </Box>
              )
            })}
          </Box>
          {!s.coverageRecorded && <Text color={C.amber}>Ainda não há plano: os critérios vêm do card e tudo aparece como "Falta".</Text>}
        </Box>,
      )}
      {groups.map(g =>
        card(
          ui,
          `cov-${g.kind}`,
          g.label,
          <Box flexDirection="column">
            {g.items.map(i => (
              <Box key={`ci-${i.id}`} gap={2}>
                <Box width={5}>
                  <Text color={C.dim}>{i.id}</Text>
                </Box>
                <Box flexGrow={1} flexShrink={1}>
                  {rich(ui, `ct-${i.id}`, i.text)}
                </Box>
                <Text color={COVER[i.status]?.color ?? C.dim}>{COVER[i.status]?.label ?? i.status}</Text>
              </Box>
            ))}
          </Box>,
          g.from,
        ),
      )}
    </Box>
  )
}

// --- Revisão ---------------------------------------------------------------------------------------------------

const SEV: Record<string, { label: string; color: string }> = {
  CRITICO: { label: 'Crítico', color: C.red },
  IMPORTANTE: { label: 'Importante', color: C.amber },
  SUGESTAO: { label: 'Sugestão', color: C.blue },
  DUVIDA: { label: 'Dúvida', color: C.purple },
  ELOGIO: { label: 'Elogio', color: C.green },
}

/** O nome de uma rodada pelo arquivo: Código, Otimização, Plano, Segurança, Bugs… */
export function roundName(f: Finding): string {
  if (f.source === 'plano') return 'Plano'
  if (f.source === 'segurança') return 'Segurança'
  if (f.source === 'bugs') return 'Bugs'
  // review-<id>-rN → Código; review-otimizacao-<id>-rN → Otimização; review-T3-a3-rN → T3-a3
  const stem = f.file.replace(/^review-/, '').replace(/-r\d+\.md$/, '')
  if (/^(?:(?:us|it|bug|dt|pr|ft|lv)-)?\d+$/i.test(stem)) return 'Código'
  const extra = stem.replace(/-(?:(?:us|it|bug|dt|pr|ft|lv)-\d+|\d{3,})$/i, '')
  const known: Record<string, string> = { otimizacao: 'Otimização', seguranca: 'Segurança', documentacao: 'Documentação' }
  return known[extra.toLowerCase()] ?? extra.charAt(0).toUpperCase() + extra.slice(1)
}

/** As rodadas para o seletor: uma por arquivo de revisão (bugs e segurança entram junto da revisão de código). */
export function reviewRounds(s: Snapshot): { file: string; label: string }[] {
  const seen = new Map<string, { name: string; round: number }>()
  for (const f of s.findings) {
    if (f.source === 'bugs' || f.source === 'segurança' || !f.file) continue
    seen.set(f.file, { name: roundName(f), round: f.round })
  }
  const order = (n: string) => (n === 'Plano' ? 0 : n === 'Código' ? 1 : 2)
  return [...seen]
    .sort(([, a], [, b]) => order(a.name) - order(b.name) || a.name.localeCompare(b.name) || a.round - b.round)
    .map(([file, r]) => ({ file, label: `${r.name} r${r.round}` }))
}

const isFixed = (f: Finding) => /corrig|fixed|resolv/.test(f.status)

/** Duas pastas iguais, sem diferenciar barra nem caixa (Windows). */
export const samePath = (a: string, b: string) =>
  a.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase() === b.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()

/** A categoria do achado: a do título (fluxo v3) ou a origem (as passadas de bugs e segurança de antes). */
export function categoryOf(f: Finding): 'qualidade' | 'bug' | 'seguranca' {
  if (f.category === 'bug' || f.source === 'bugs') return 'bug'
  if (f.category === 'seguranca' || f.source === 'segurança') return 'seguranca'
  return 'qualidade'
}

function codeBlock(ui: UI, key: string, f: Finding) {
  if (!f.before && !f.after) return null
  const lines = [
    ...f.before.split('\n').filter(Boolean).map(l => `-${l}`),
    ...f.after.split('\n').filter(Boolean).map(l => `+${l}`),
  ]
  const removed = lines.filter(l => l.startsWith('-')).length
  const added = lines.length - removed
  const source = `@@ -1,${removed} +1,${added} @@\n${lines.join('\n')}\n`
  return <ui.Code key={key} source={source} format="diff" path={f.where || undefined} />
}

/** A rodada que a Revisão mostra: a escolhida; senão a com achado esperando você; senão a última do código. */
function defaultRound(s: Snapshot, chosen: string): string {
  const rounds = reviewRounds(s)
  if (rounds.some(r => r.file === chosen)) return chosen
  const waiting = [...rounds].reverse().find(r =>
    s.findings.some(f => f.file === r.file && f.severity !== 'ELOGIO' && f.decision === 'pendente' && !isFixed(f)))
  const lastCode = [...rounds].reverse().find(r => r.label.startsWith('Código'))
  return (waiting ?? lastCode ?? rounds.at(-1))?.file ?? ''
}

/** Os achados de uma rodada, com as passadas de bugs e segurança da mesma rodada do código (sem elogios). */
function roundFindings(s: Snapshot, file: string): Finding[] {
  const current = s.findings.find(f => f.file === file)
  return s.findings.filter(
    f => f.severity !== 'ELOGIO' &&
      (f.file === file || (current && f.source !== 'plano' && f.source !== 'revisão' && f.round === current.round && current.source === 'revisão')),
  )
}

function Review(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button } = ui
  const s = v.snap
  const rounds = reviewRounds(s)
  if (!rounds.length) return <Text color={C.dim}>Ainda não houve revisão.</Text>
  const file = defaultRound(s, v.reviewFile)
  const inRound = roundFindings(s, file)
  const praise = s.findings.filter(f => f.file === file && f.severity === 'ELOGIO').length
  const decided = (f: Finding) => v.decisions[`${f.file}:${f.id}`] ?? (f.decision === 'pendente' ? '' : f.decision)
  const tabs = [
    { id: 'voce', label: 'Com você', has: (f: Finding) => !decided(f) && !isFixed(f) },
    { id: 'mantido', label: 'Mantidos', has: (f: Finding) => decided(f) === 'mantido' || (!decided(f) && isFixed(f)) },
    { id: 'descartado', label: 'Descartados', has: (f: Finding) => decided(f) === 'descartado' },
    { id: 'todos', label: 'Todos', has: () => true },
  ]
  const tab = tabs.find(t => t.id === v.decisionTab) ?? tabs[0]
  const f0 = v.filter
  const shown = inRound
    .filter(f => tab?.has(f))
    .filter(f => !f0.severities.length || f0.severities.includes(f.severity ?? ''))
    .filter(f => !f0.sources.length || f0.sources.includes(categoryOf(f)))
    .filter(f => !f0.statuses.length || f0.statuses.includes(isFixed(f) ? 'corrigido' : 'aberto'))
  const marked = Object.keys(v.decisions).filter(k => k.startsWith(`${file}:`)).length
  const filterButton = (kind: keyof Omit<ReviewFilter, 'open'>, value: string, label: string) => {
    const on = f0[kind].includes(value)
    return on ? (
      <Button key={`flt-${kind}-${value}`} label={`✓ ${label}`} onPress={() => act.toggleFilter(kind, value)} />
    ) : (
      <Button key={`flt-${kind}-${value}`} label={label} plain dimColor onPress={() => act.toggleFilter(kind, value)} />
    )
  }
  const activeFilters = f0.severities.length + f0.sources.length + f0.statuses.length
  return (
    <Box flexDirection="column" gap={1}>
      <Box justifyContent="space-between" alignItems="center" gap={2}>
        {choices(ui, 'review-round', rounds.map(r => ({ value: r.file, label: r.label })), file, value => act.reviewFile(value))}
        <Button key="filters" label={activeFilters ? `Filtros · ${activeFilters}` : 'Filtros'} plain dimColor onPress={() => act.toggleFilters()} />
      </Box>
      {f0.open && (
        <Box flexDirection="column" borderStyle="round" borderColor={C.line} paddingX={2}>
          <Box gap={1} flexWrap="wrap">
            <Text color={C.dim}>Criticidade</Text>
            {filterButton('severities', 'CRITICO', 'Crítico')}
            {filterButton('severities', 'IMPORTANTE', 'Importante')}
            {filterButton('severities', 'SUGESTAO', 'Sugestão')}
            {filterButton('severities', 'DUVIDA', 'Dúvida')}
          </Box>
          <Box gap={1} flexWrap="wrap">
            <Text color={C.dim}>Categoria</Text>
            {filterButton('sources', 'qualidade', 'Qualidade')}
            {filterButton('sources', 'bug', 'Bug')}
            {filterButton('sources', 'seguranca', 'Segurança')}
            <Text color={C.dim}> Status</Text>
            {filterButton('statuses', 'aberto', 'Aberto')}
            {filterButton('statuses', 'corrigido', 'Corrigido')}
          </Box>
        </Box>
      )}
      <Box gap={1} flexWrap="wrap">
        {tabs.map(t =>
          t.id === tab?.id ? (
            <Button key={`dt-${t.id}`} label={`${t.label} ${inRound.filter(f => t.has(f)).length}`} onPress={() => act.decisionTab(t.id)} />
          ) : (
            <Button key={`dt-${t.id}`} label={`${t.label} ${inRound.filter(f => t.has(f)).length}`} plain dimColor onPress={() => act.decisionTab(t.id)} />
          ),
        )}
      </Box>
      {shown.length === 0 && <Text color={C.dim}>Nada aqui{tab?.id === 'voce' ? ': nenhum achado espera você nesta rodada.' : '.'}</Text>}
      {shown.map(f => findingCard(ui, v, act, f, decided(f), file))}
      {praise > 0 && <Text color={C.dim}>{praise} elogio(s) nesta rodada</Text>}
      {marked > 0 && (
        <Box justifyContent="space-between" alignItems="center">
          <Text color={C.dim}>{marked} decisão(ões) marcada(s) · vão para o prompt; nada muda até você enviar</Text>
          <Button key="review-send" label="Levar decisões ao prompt" variant="primary" onPress={() => act.sendReviewDecisions()} />
        </Box>
      )}
    </Box>
  )
}

function findingCard(ui: UI, v: ViewState, act: Actions, f: Finding, decided: string, file: string) {
  const { Box, Text, Button } = ui
  const sev = SEV[f.severity ?? ''] ?? { label: f.severity ?? '—', color: C.dim }
  const pending = !decided && !isFixed(f)
  const marked = v.decisions[`${file}:${f.id}`]
  const recommendsDrop = /^\W*(descart|cai\b|n[aã]o)/i.test(f.recommendation)
  // uma dúvida traz opções (a), (b)…: o texto inteiro numa lista e, nos botões, só a letra
  const letter = (o: string) => /^\(([a-z])\)/.exec(o)?.[1] ?? ''
  const options = f.options.length ? f.options.slice(0, 4) : ['Manter', 'Descartar']
  return (
    <Box key={`fc-${f.file}-${f.id}`} flexDirection="column" borderStyle="round" borderColor={C.line} paddingX={2} paddingY={1} gap={1}>
      <Box gap={1}>
        {chip(ui, `sev-${f.id}`, sev.label, sev.color)}
        <Text color={C.dim}>{f.id}</Text>
        <Box flexGrow={1} flexShrink={1}>
          <Text color={C.dim}>{f.where || f.source}</Text>
        </Box>
        {isFixed(f) ? chip(ui, `st-${f.id}`, f.status, C.green) : pending ? chip(ui, `st-${f.id}`, 'com você', C.amber) : chip(ui, `st-${f.id}`, decided, C.dim)}
      </Box>
      {rich(ui, `ft-${f.id}`, f.title)}
      {codeBlock(ui, `code-${f.id}`, f)}
      {f.recommendation && (
        <Box flexDirection="column">
          <Text color={C.dim}>Recomendação do AiDW</Text>
          {rich(ui, `fr-${f.id}`, f.recommendation)}
        </Box>
      )}
      {f.options.length > 0 && pending && (
        <Box flexDirection="column">
          {f.options.slice(0, 4).map((o, i) => (
            <Box key={`fo-${f.id}-${i}`} gap={1}>
              <Text color={i === 0 ? C.claude : C.dim}>{i === 0 ? '●' : '○'}</Text>
              <Box flexShrink={1}>{rich(ui, `fot-${f.id}-${i}`, i === 0 ? `${o} (recomendado)` : o)}</Box>
            </Box>
          ))}
        </Box>
      )}
      {pending ? (
        <Box gap={1} flexWrap="wrap">
          {options.map((o, i) => {
            const value = f.options.length ? o : i === 0 ? 'mantido' : 'descartado'
            const recommended = f.options.length ? i === 0 : (i === 1) === recommendsDrop
            const name = f.options.length ? `(${letter(o) || i + 1})` : o
            return (
              <Button
                key={`dec-${f.id}-${i}`}
                label={`${marked === value ? '✓ ' : ''}${name}${recommended && !f.options.length ? ' (recomendado)' : ''}`}
                onPress={() => act.decide(`${file}:${f.id}`, value)}
              />
            )
          })}
        </Box>
      ) : (
        <Text color={C.dim}>Decisão: {decided || 'mantido'}{isFixed(f) ? ` · ${f.status}` : ''}</Text>
      )}
    </Box>
  )
}

export function reviewDecisionText(s: Snapshot, decisions: Record<string, string>): string {
  const lines = Object.entries(decisions).map(([key, value]) => {
    const [file, id] = [key.slice(0, key.lastIndexOf(':')), key.slice(key.lastIndexOf(':') + 1)]
    const f = s.findings.find(x => x.file === file && x.id === id)
    return `- ${id} (${f ? `${roundName(f)} r${f.round}` : file}): ${value}`
  })
  return [`Decisões da revisão (${s.id}):`, ...lines, 'Registre na triagem e siga com o que foi mantido.'].join('\n')
}

// --- Diffs -----------------------------------------------------------------------------------------------------

/** O nome legível de um .patch da pasta: `diff-pr8197-GedarAC-r2.patch` → "PR 8197 · só a rodada 2". */
export function patchLabel(name: string): string {
  const base = name.replace(/\.patch$/, '')
  const pr = /^diff-pr(\d+)-(.+?)(?:-r(\d+))?$/.exec(base)
  if (pr) return pr[3] ? `PR ${pr[1]} · só a rodada ${pr[3]}` : `PR ${pr[1]} · ${pr[2]}`
  if (base.startsWith('ambiente-teste')) return `ajustes de teste${base.slice('ambiente-teste'.length).replace(/^-/, ' · ')}`
  const round = /^diff-(.+?)-r(\d+)(?:-(?:para-)?r(\d+))?$/.exec(base)
  if (round) return round[3] ? `${round[1]} · r${round[2]} → r${round[3]}` : `${round[1]} · rodada ${round[2]}`
  return base.replace(/^diff-/, '')
}

/**
 * De onde vem o diff: cada worktree da demanda, seguido dos .patch da sua PR, e os outros .patch da pasta. O patch
 * inteiro de uma PR que tem worktree sai: é o mesmo diff (o `worktree create --pr` o regrava a cada versão).
 */
export function diffSources(s: Snapshot): { value: string; label: string }[] {
  const prOf = (p: string) => /^diff-pr(\d+)-/.exec(p)?.[1] ?? ''
  const withTree = new Set(s.repos.map(r => String(r.pr ?? '')).filter(Boolean))
  const patches = s.patches.filter(p => !(withTree.has(prOf(p)) && !/-r\d+\.patch$/.test(p)))
  const patch = (p: string) => ({ value: `patch:${p}`, label: patchLabel(p) })
  return [
    ...s.repos.flatMap(r => [
      { value: `repo:${r.path}`, label: r.pr ? `PR ${r.pr} · ${r.name}` : r.name },
      ...(r.pr ? patches.filter(p => prOf(p) === String(r.pr)).map(patch) : []),
    ]),
    ...patches.filter(p => !withTree.has(prOf(p))).map(patch),
  ]
}

function Diffs(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Code, Button } = ui
  const s = v.snap
  const sources = diffSources(s)
  if (!sources.length) return <Text color={C.dim}>Sem worktree nem patch nesta demanda.</Text>
  // o diff guardado pode ser de outra demanda: só vale se a fonte é desta (o register carrega a primeira)
  const d = v.diff && sources.some(x => x.value === v.diff?.source) ? v.diff : null
  const repo = d?.source.startsWith('repo:') ? s.repos.find(r => `repo:${r.path}` === d.source) : undefined
  const fileFindings = (path: string) =>
    s.findings.filter(f => f.severity !== 'ELOGIO' && !isFixed(f) && f.where && path.endsWith(f.where.replace(/:\d.*$/, '').split('/').pop() ?? '#'))
  const notes = d ? fileFindings(d.selected) : []
  return (
    <Box flexDirection="column" gap={1}>
      <Box justifyContent="space-between" alignItems="center" gap={2}>
        {choices(ui, 'diff-source', sources, d?.source ?? sources[0]?.value ?? '', value => act.diffSource(value))}
        {repo && v.canAppDiff && (samePath(repo.path, v.sessionCwd) ? (
          // o mod não abre o painel de diff do app (não há API para isso): ele segue a pasta da sessão, que já é esta
          <Text key="app-diff-here" color={C.dim}>No app: ícone de diff no topo da janela</Text>
        ) : (
          // leva a sessão para o worktree deste repositório (/aidw:diff), e o painel de diff do app vai junto
          <Button key="app-diff" label="Levar o diff do app para cá ↗" plain dimColor onPress={() => act.appDiff(repo.name)} />
        ))}
      </Box>
      {d && !d.error && (
        <Text color={C.dim}>
          {repo ? `${repo.pr ? 'só leitura' : repo.branch || '?'} · contra ${repo.base ? repo.base.slice(0, 12) : 'a base'} · ` : ''}
          {d.summary}
        </Text>
      )}
      {!d && <Text color={C.dim}>Carregando o diff…</Text>}
      {d?.error && <Text color={C.red}>{d.error}</Text>}
      {d && !d.error && (
        <Box gap={2} alignItems="flex-start">
          <Box flexDirection="column" width={34} flexShrink={0}>
            {d.files.map(f => {
              const on = f.path === d.selected
              const name = f.path.split('/').pop() ?? f.path
              const dir = f.path.slice(0, f.path.length - name.length).replace(/\/$/, '')
              const n = fileFindings(f.path).length
              return (
                <Box key={`df-${f.path}`} flexDirection="column" paddingX={1}>
                  <Box justifyContent="space-between">
                    <Button key={`dfb-${f.path}`} label={on ? `› ${name}` : name} plain dimColor={!on} onPress={() => act.diffFile(f.path)} />
                    <Text>
                      <Text color={C.green}>+{f.added}</Text>
                      {f.removed ? <Text color={C.red}> −{f.removed}</Text> : ''}
                    </Text>
                  </Box>
                  <Box justifyContent="space-between">
                    <Text color={C.dim}>{dir}</Text>
                    {n > 0 && chip(ui, `dfn-${f.path}`, `${n} achado(s)`, C.blue)}
                  </Box>
                </Box>
              )
            })}
          </Box>
          <Box flexDirection="column" flexGrow={1} flexShrink={1} gap={1}>
            {notes.map(f => (
              <Box key={`dn-${f.id}`} gap={1} borderStyle="round" borderColor={C.line} paddingX={1}>
                {chip(ui, `dns-${f.id}`, SEV[f.severity ?? '']?.label ?? '', SEV[f.severity ?? '']?.color ?? C.dim)}
                <Box flexShrink={1}>
                  {rich(ui, `dnt-${f.id}`, `**${f.id}** · ${f.title}`)}
                </Box>
                <Button key={`dnl-${f.id}`} label="ver na Revisão" plain onPress={() => act.tab('revisao')} />
              </Box>
            ))}
            {d.hunks ? <Code key="diff-code" source={d.hunks} format="diff" path={d.selected} /> : <Text color={C.dim}>Escolha um arquivo.</Text>}
          </Box>
        </Box>
      )}
    </Box>
  )
}

// --- Teste manual ----------------------------------------------------------------------------------------------

function Manual(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Input, Button } = ui
  const s = v.snap
  const all = s.manual.filter(m => !m.removed)
  if (!all.length) return <Text color={C.dim}>Sem roteiro de teste manual (o QA grava roteiro-testes-&lt;id&gt;.md quando há passo manual).</Text>
  const prep = all.filter(m => /prepara/i.test(m.section))
  const tests = all.filter(m => !/prepara/i.test(m.section))
  const removed = s.manual.filter(m => m.removed)
  const passed = tests.filter(m => m.result === '✅').length
  const failed = tests.filter(m => m.result === '❌').length
  const next = tests.find(m => !m.result)
  const sections = [...new Set(tests.map(m => m.section))]
  const key = next ? `evidencia-${next.id}` : ''
  return (
    <Box flexDirection="column" gap={1}>
      {card(
        ui,
        'mt-prog',
        'Roteiro',
        <Box flexDirection="column">
          <Box justifyContent="space-between">
            <Text>
              <Text bold color={C.strong}>
                {passed + failed}
              </Text>
              <Text color={C.dim}> de {tests.length} passos</Text>
            </Text>
            <Text>
              <Text color={C.green}>{passed} passaram</Text>
              <Text color={C.dim}> · </Text>
              <Text color={C.red}>{failed} falharam</Text>
              <Text color={C.dim}> · {tests.length - passed - failed} faltam</Text>
            </Text>
          </Box>
          {meter(ui, 'mt-bar', pct(passed, tests.length), failed ? C.amber : C.green, 600)}
          <Text color={C.dim}>
            {sections.map(sec => `${sec} ${tests.filter(m => m.section === sec && m.result).length} de ${tests.filter(m => m.section === sec).length}`).join(' · ')}
            {prep.length ? ` · preparação à parte (${prep.filter(m => m.result).length} de ${prep.length})` : ''}
          </Text>
        </Box>,
        s.roteiro,
      )}
      {next && (
        <Box key="mt-now" flexDirection="column" borderStyle="round" borderColor={C.claude} paddingX={2} paddingY={1} gap={1}>
          <Box justifyContent="space-between">
            <Text color={C.claude} bold>
              Agora · {next.id}
            </Text>
            <Text color={C.dim}>{next.section}</Text>
          </Box>
          <Text bold color={C.strong}>
            {next.step}
          </Text>
          {next.expected && (
            <Text>
              <Text color={C.dim}>Esperado </Text>
              {next.expected}
            </Text>
          )}
          <Input
            key={key}
            label="Evidência"
            placeholder="o que aconteceu (sem segredo nem dado pessoal)"
            value={v.drafts[key] ?? ''}
            onInput={value => act.draft(key, value)}
            onSubmit={value => act.draft(key, value)}
          />
          <Box gap={1}>
            <Button key="manual-ok" label="✓ Passou" variant="primary" onPress={() => act.manualResult(next.id, 'ok')} />
            <Button key="manual-fail" label="✕ Falhou" onPress={() => act.manualResult(next.id, 'fail')} />
            <Button key="manual-skip" label="Pular" plain onPress={() => act.manualResult(next.id, 'skip')} />
          </Box>
        </Box>
      )}
      {prep.length > 0 && (
        <Box justifyContent="space-between">
          <Text bold>Preparação</Text>
          <Button key="mt-prep" label={`${prep.filter(m => m.result).length} de ${prep.length} · ${v.expanded.prep ? 'esconder' : 'mostrar'}`} plain onPress={() => act.expand('prep')} />
        </Box>
      )}
      {v.expanded.prep && prep.map(m => stepRow(ui, m, false))}
      {sections.map(sec => (
        <Box key={`sec-${sec}`} flexDirection="column">
          <Box justifyContent="space-between">
            <Text bold>{sec}</Text>
            <Text color={C.dim}>
              {tests.filter(m => m.section === sec && m.result).length} de {tests.filter(m => m.section === sec).length}
            </Text>
          </Box>
          {tests.filter(m => m.section === sec).map(m => stepRow(ui, m, m === next))}
        </Box>
      ))}
      {removed.length > 0 && (
        <Button
          key="mt-removed"
          label={`${removed.length} passo(s) removido(s) do roteiro (${removed.map(m => m.id).join(', ')}) · ${v.expanded.removed ? 'esconder' : 'mostrar'}`}
          plain
          dimColor
          onPress={() => act.expand('removed')}
        />
      )}
      {v.expanded.removed && removed.map(m => stepRow(ui, m, false))}
    </Box>
  )
}

function stepRow(ui: UI, m: Snapshot['manual'][number], current: boolean) {
  const { Box, Text } = ui
  const mark = m.result === '✅' ? <Text color={C.green}>✓</Text> : m.result === '❌' ? <Text color={C.red}>✕</Text> : <Text color={current ? C.claude : C.dim}>{current ? '●' : '○'}</Text>
  return (
    <Box key={`step-${m.section}-${m.id}`} gap={2} paddingX={1}>
      {mark}
      <Box width={5}>
        <Text color={C.dim}>{m.id}</Text>
      </Box>
      <Box flexDirection="column" flexShrink={1}>
        <Text color={m.removed ? C.dim : C.text}>{m.step}</Text>
        {m.expected && m.expected !== '—' && <Text color={C.dim}>{m.expected}</Text>}
        {m.note && <Text color={C.dim}>Evidência: {m.note}</Text>}
      </Box>
    </Box>
  )
}

// --- Métricas --------------------------------------------------------------------------------------------------

type Group = { key: string; n: number; tokens: number; seconds: number; cost: number }

function groupBy(list: Delegation[], key: (d: Delegation) => string): Group[] {
  const out = new Map<string, Group>()
  for (const d of list) {
    const k = key(d) || '—'
    const g = out.get(k) ?? { key: k, n: 0, tokens: 0, seconds: 0, cost: 0 }
    out.set(k, { key: k, n: g.n + 1, tokens: g.tokens + d.tokens, seconds: g.seconds + d.seconds, cost: g.cost + (d.cost ?? 0) })
  }
  return [...out.values()]
}

/** Colunas por dia (SVG com tooltip no app; barras de texto onde não há SVG). */
function dayChart(ui: UI, days: Group[]) {
  const max = Math.max(1, ...days.map(d => d.tokens))
  if (ui.Svg) {
    const colW = 56
    const gap = 24
    const height = 150
    const width = days.length * (colW + gap)
    const bars = days.map((d, i) => {
      const bh = Math.max(2, Math.round((d.tokens / max) * (height - 34)))
      const x = i * (colW + gap)
      const y = height - 18 - bh
      return (
        `<g><title>${ddmm(d.key)}: ${d.n} chamada(s), ${compact(d.tokens)} tokens, ${secs(d.seconds)}</title>` +
        `<rect x="${x}" y="${y}" width="${colW}" height="${bh}" rx="4" ${fill(C.bar)}/>` +
        `<text x="${x + colW / 2}" y="${y - 5}" text-anchor="middle" font-size="11" ${fill(C.mid)} font-family="system-ui,sans-serif">${compact(d.tokens)}</text>` +
        `<text x="${x + colW / 2}" y="${height - 3}" text-anchor="middle" font-size="11" ${fill(C.dim)} font-family="system-ui,sans-serif">${ddmm(d.key)}</text></g>`
      )
    })
    return (
      <ui.Svg
        key="days"
        alt={days.map(d => `${ddmm(d.key)} ${compact(d.tokens)}`).join(', ')}
        width={width}
        height={height}
        isInteractive
        source={svgDoc(width, height, `<line x1="0" y1="${height - 18}" x2="${width}" y2="${height - 18}" ${stroke(C.line)}/>${bars.join('')}`)}
      />
    )
  }
  return (
    <ui.Box flexDirection="column">
      {days.map(d => (
        <ui.Text key={`day-${d.key}`}>
          {ddmm(d.key)} <ui.Text color={C.bar}>{'█'.repeat(Math.max(1, Math.round((d.tokens / max) * 30)))}</ui.Text> {compact(d.tokens)}
        </ui.Text>
      ))}
    </ui.Box>
  )
}

function hbars(ui: UI, key: string, label: string, groups: Group[]) {
  const { Box, Text } = ui
  const max = Math.max(1, ...groups.map(g => g.tokens))
  return card(
    ui,
    key,
    label,
    <Box flexDirection="column">
      {groups.map(g => {
        // o orquestrador (seconds < 0): conta turnos, não chamadas, e não tem tempo (o chat fica aberto)
        const chat = g.seconds < 0
        return (
          <Box key={`${key}-${g.key}`} gap={2} alignItems="center">
            <Box width={18}>
              <Text>{g.key}</Text>
            </Box>
            <Box flexGrow={1}>{meter(ui, `${key}-${g.key}-m`, pct(g.tokens, max), chat ? C.claude : C.bar, 260)}</Box>
            <Box width={7} justifyContent="flex-end">
              <Text color={C.text}>{compact(g.tokens)}</Text>
            </Box>
            <Box width={10} justifyContent="flex-end">
              <Text color={C.dim}>{chat ? `${g.n} turno${g.n === 1 ? '' : 's'}` : String(g.n)}</Text>
            </Box>
            <Box width={7} justifyContent="flex-end">
              <Text color={C.faint}>{chat ? '—' : secs(g.seconds)}</Text>
            </Box>
          </Box>
        )
      })}
    </Box>,
    'tokens · chamadas · tempo',
  )
}

function Metrics(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button, Link } = ui
  const s = v.snap
  const d = s.delegations
  const o = s.orchestrator
  const seconds = d.reduce((n, x) => n + x.seconds, 0)
  const priced = d.filter(x => x.cost !== null)
  const rounds = new Set(s.findings.filter(f => f.source !== 'bugs' && f.source !== 'segurança').map(f => f.file)).size
  const period = d.length ? `${ddmm(d[0]?.date ?? '')} a ${ddmm(d.at(-1)?.date ?? '')}` : ''
  const days = groupBy(d, x => x.date)
  const agents = groupBy(d, x => x.agent)
  if (o.rows.length) agents.push({ key: 'orquestrador', n: o.turns, tokens: o.tokens, seconds: -1, cost: o.cost ?? 0 })
  const cacheRead = o.rows.reduce((n, r) => n + r.cacheRead, 0)
  const cacheWrite = o.rows.reduce((n, r) => n + r.cacheWrite, 0)
  const output = o.rows.reduce((n, r) => n + r.output, 0)
  const results = groupBy(d, x => stateLabel(x.state)).sort((a, b) => b.n - a.n)
  const back = s.timeline.filter(t => t.visits > 1)
  const recent = [...d].reverse().slice(0, v.expanded.delegations ? d.length : 8)
  const artifacts = Object.entries(s.artifacts)
  const files = artifacts.reduce((n, [, f]) => n + f.length, 0)
  return (
    <Box flexDirection="column" gap={1}>
      {card(
        ui,
        'resumo',
        'Resumo',
        <Box flexDirection="column">
          {stat(ui, 'k-del', 'Delegações', String(d.length))}
          {rounds > 0 && stat(ui, 'k-rnd', 'Rodadas de revisão', String(rounds))}
          {stat(ui, 'k-tok', 'Tokens dos agentes', compact(s.tokens))}
          {o.rows.length
            ? stat(ui, 'k-orc', 'Tokens do orquestrador', compact(o.tokens))
            : stat(ui, 'k-orc', 'Tokens do orquestrador', 'sem registro', { missing: true })}
          {stat(ui, 'k-tim', 'Agentes trabalhando', secs(seconds))}
          {priced.length > 0 && stat(ui, 'k-usd', `Custo (${priced.length} de ${d.length} delegações)`, `US$ ${priced.reduce((n, x) => n + (x.cost ?? 0), 0).toFixed(2)}`)}
        </Box>,
        period,
      )}
      {agents.length > 0 && hbars(ui, 'ag', 'Por agente', agents.sort((a, b) => b.tokens - a.tokens))}
      {o.rows.length > 0 &&
        card(
          ui,
          'orc',
          'Orquestrador',
          <Box flexDirection="column">
            {stat(ui, 'o-cr', 'Cache lido', compact(cacheRead))}
            {stat(ui, 'o-cw', 'Cache escrito', compact(cacheWrite))}
            {stat(ui, 'o-out', 'Saída', compact(output))}
            {stat(ui, 'o-share', 'Parte do orquestrador no total', `${pct(o.tokens, o.tokens + s.tokens)}%`, { meter: pct(o.tokens, o.tokens + s.tokens), color: C.claude })}
            {o.rows.map((r, i) => (
              <Box key={`or-${i}`} gap={2}>
                <Box width={10}>
                  <Text color={C.dim}>{r.session}</Text>
                </Box>
                <Box flexGrow={1} flexShrink={1}>
                  <Text>{modelName(r.model)}</Text>
                </Box>
                <Box width={10} justifyContent="flex-end">
                  <Text color={C.dim}>{`${r.turns} turnos`}</Text>
                </Box>
                <Box width={14} justifyContent="flex-end">
                  <Text color={C.dim}>{`${pct(r.cacheRead, r.tokens)}% cache lido`}</Text>
                </Box>
                <Box width={6} justifyContent="flex-end">
                  <Text>{compact(r.tokens)}</Text>
                </Box>
                <Box width={10} justifyContent="flex-end">
                  <Text color={C.mid}>{r.cost !== null ? `US$ ${r.cost.toFixed(2)}` : '—'}</Text>
                </Box>
              </Box>
            ))}
            {o.cost !== null && (
              <Text color={C.dim}>
                Equivalente em preço de API: US$ {o.cost.toFixed(2)} em {o.turns} turnos (régua do peso no limite do plano, não a conta)
              </Text>
            )}
          </Box>,
          'chat principal · uma linha por sessão e modelo',
        )}
      {days.length > 1 && card(ui, 'dias', 'Tokens por dia', dayChart(ui, days), ui.Svg ? 'passe o mouse para ver chamadas e tempo' : '')}
      {d.length > 0 && hbars(ui, 'md', 'Por modelo e effort', groupBy(d, x => `${modelName(x.model)} · ${x.effort}`).sort((a, b) => b.tokens - a.tokens))}
      {d.length > 0 &&
        card(
          ui,
          'res',
          'Resultado das chamadas e retrabalho',
          <Box flexDirection="column">
            <Box gap={1} flexWrap="wrap">
              {results.map(r => (
                <Text key={`r-${r.key}`}>
                  {r.key} <Text bold>{r.n}</Text>
                  <Text color={C.dim}> ·</Text>
                </Text>
              ))}
            </Box>
            {back.length > 0 && (
              <Text color={C.dim}>
                Voltas: {back.map(t => `${t.name} ${t.visits}×`).join(' · ')}
              </Text>
            )}
          </Box>,
        )}
      {d.length > 0 &&
        card(
          ui,
          'dl',
          'Delegações',
          <Box flexDirection="column">
            {recent.map((x, i) => (
              <Box key={`dl-${i}`} gap={2}>
                <Box width={6}>
                  <Text color={C.dim}>{ddmm(x.date)}</Text>
                </Box>
                <Box width={13}>
                  <Text>{x.agent}</Text>
                </Box>
                <Box flexGrow={1} flexShrink={1}>
                  <Text color={C.mid}>{x.label}</Text>
                </Box>
                <Box width={16}>
                  <Text color={C.dim}>{`${modelName(x.model)} · ${x.effort}`}</Text>
                </Box>
                <Box width={16}>
                  <Text>{stateLabel(x.state)}</Text>
                </Box>
                <Box width={7} justifyContent="flex-end">
                  <Text color={C.dim}>{secs(x.seconds)}</Text>
                </Box>
                <Box width={6} justifyContent="flex-end">
                  <Text>{compact(x.tokens)}</Text>
                </Box>
              </Box>
            ))}
            {d.length > 8 && (
              <Button key="dl-more" label={v.expanded.delegations ? 'ver só as 8 mais recentes' : `ver todas as ${d.length}`} plain onPress={() => act.expand('delegations')} />
            )}
          </Box>,
          'mais recentes primeiro',
        )}
      {card(
        ui,
        'art',
        'Artefatos',
        <Box flexDirection="column">
          {artifacts.map(([group, list]) => (
            <Box key={`ag-${group}`} flexDirection="column">
              <Box justifyContent="space-between">
                <Text>{group}</Text>
                <Button key={`agb-${group}`} label={`${list.length} ${v.expanded[`art:${group}`] ? '⌃' : '⌄'}`} plain onPress={() => act.expand(`art:${group}`)} />
              </Box>
              {v.expanded[`art:${group}`] && (
                <Box flexWrap="wrap" gap={2} paddingX={2}>
                  {list.map(f => (
                    <Link key={`af-${f}`} href={fileUrl(`${s.dir}/${f}`)} label={f} />
                  ))}
                </Box>
              )}
            </Box>
          ))}
        </Box>,
        `${files} arquivos na pasta da demanda`,
      )}
    </Box>
  )
}

// --- Revisão de PR sem triagem no formato triagem-pr (demandas antigas): achados e um voto ---------------------

/** Os achados da última rodada de uma revisão de PR (sem plano nem elogio). */
function prList(s: Snapshot): Finding[] {
  const list = s.findings.filter(f => f.source !== 'plano' && f.severity !== 'ELOGIO')
  const round = Math.max(0, ...list.map(f => f.round))
  return list.filter(f => f.round === round)
}

function PrFindings(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button, Input } = ui
  const s = v.snap
  const inRound = prList(s)
  if (!inRound.length) return <Text color={C.dim}>A revisão ainda não terminou.</Text>
  const choice = (f: Finding) => v.publish[f.id]
  const tabs = [
    { id: 'decidir', label: 'A decidir', has: (f: Finding) => !f.published && choice(f) === undefined },
    { id: 'publicar', label: 'Publicar', has: (f: Finding) => !f.published && choice(f) === true },
    { id: 'nao', label: 'Não publicar', has: (f: Finding) => !f.published && choice(f) === false },
    { id: 'publicados', label: 'Já publicados', has: (f: Finding) => f.published },
  ]
  const tab = tabs.find(t => t.id === v.decisionTab) ?? tabs[0]
  const shown = inRound.filter(f => tab?.has(f))
  const toPublish = inRound.filter(f => choice(f) === true).length
  const suggested = VOTES.find(o => o.value === v.vote)
  return (
    <Box flexDirection="column" gap={1}>
      <Box gap={1} flexWrap="wrap">
        {tabs.map(t =>
          t.id === tab?.id ? (
            <Button key={`pt-${t.id}`} label={`${t.label} ${inRound.filter(f => t.has(f)).length}`} onPress={() => act.decisionTab(t.id)} />
          ) : (
            <Button key={`pt-${t.id}`} label={`${t.label} ${inRound.filter(f => t.has(f)).length}`} plain dimColor onPress={() => act.decisionTab(t.id)} />
          ),
        )}
      </Box>
      {shown.length === 0 && <Text color={C.dim}>Nada aqui.</Text>}
      {shown.map(f => {
        const sev = SEV[f.severity ?? ''] ?? { label: '—', color: C.dim }
        const doubt = f.severity === 'DUVIDA'
        const key = `comentario-${f.id}`
        const editing = v.expanded[`edit:${f.id}`]
        const text = v.drafts[key] ?? f.comment
        const recommendsPublish = !/^\W*(n[aã]o|cai\b|descart|mantida, vai)/i.test(f.recommendation) && !doubt
        return (
          <Box key={`pf-${f.id}`} flexDirection="column" borderStyle="round" borderColor={C.line} paddingX={2} paddingY={1} gap={1}>
            <Box gap={1}>
              {chip(ui, `ps-${f.id}`, sev.label, sev.color)}
              <Text color={C.dim}>{f.id}</Text>
              <Text color={C.dim}>{f.where}</Text>
            </Box>
            {rich(ui, `pt-${f.id}`, f.title)}
            {codeBlock(ui, `pcode-${f.id}`, f)}
            {f.comment && (
              <Box flexDirection="column" borderStyle="round" borderColor={C.line} paddingX={1}>
                <Box justifyContent="space-between">
                  <Text color={C.dim}>Comentário{f.target ? ` na PR ${f.target}` : ''}</Text>
                  <Box gap={1}>
                    <Button key={`pe-${f.id}`} label={editing ? 'pronto' : 'editar'} plain onPress={() => act.expand(`edit:${f.id}`)} />
                    <Button
                      key={`pa-${f.id}`}
                      label="ajustar no chat ↗"
                      plain
                      onPress={() => act.adjustInChat(`Ajuste o comentário do achado ${f.id} (PR ${f.target || '?'}) antes de publicar. Texto atual:\n\n${text}\n\nO que mudar: `)}
                    />
                  </Box>
                </Box>
                {editing ? (
                  <Input key={key} value={text} onInput={value => act.draft(key, value)} onSubmit={value => act.draft(key, value)} />
                ) : (
                  <Text>{text}</Text>
                )}
              </Box>
            )}
            {f.recommendation && (
              <Box flexDirection="column">
                <Text color={C.dim}>Recomendação do AiDW</Text>
                {rich(ui, `pr-${f.id}`, f.recommendation)}
              </Box>
            )}
            {!f.published && (
              <Box gap={1}>
                <Button
                  key={`pp-${f.id}`}
                  label={`${choice(f) === true ? '✓ ' : ''}Publicar${recommendsPublish ? ' (recomendado)' : ''}`}
                  onPress={() => act.togglePublish(f.id, true)}
                />
                <Button
                  key={`pn-${f.id}`}
                  label={`${choice(f) === false ? '✓ ' : ''}${doubt ? 'Perguntar ao time' : 'Não publicar'}${recommendsPublish ? '' : ' (recomendado)'}`}
                  onPress={() => act.togglePublish(f.id, false)}
                />
              </Box>
            )}
          </Box>
        )
      })}
      {card(
        ui,
        'vote',
        'Voto',
        <Box flexDirection="column" gap={1}>
          <Box gap={1}>
            {VOTES.map(o =>
              o.value === v.vote ? (
                <Button key={`vote-${o.value}`} label={`● ${o.label}`} onPress={() => act.vote(o.value)} />
              ) : (
                <Button key={`vote-${o.value}`} label={o.label} plain dimColor onPress={() => act.vote(o.value)} />
              ),
            )}
          </Box>
          {s.vote && (
            <Text>
              <Text color={C.claude} bold>
                Sugerido pelo revisor{' '}
              </Text>
              {s.vote}
            </Text>
          )}
        </Box>,
      )}
      <Box justifyContent="space-between" alignItems="center">
        <Text color={C.dim}>
          {toPublish} comentário(s) para publicar · voto: {suggested?.label ?? 'escolha um'} · nada sai até você enviar
        </Text>
        <Button key="pr-decision" label="Levar decisão ao prompt" variant="primary" onPress={() => act.sendPrDecision()} />
      </Box>
    </Box>
  )
}

// --- Revisão de PR · Comentários (triagem no formato triagem-pr) ----------------------------------------------

const PR_SEV: Record<string, { label: string; color: string }> = {
  ...SEV,
  DUVIDA: { label: 'Pergunta', color: C.purple },
  PENDENCIA: { label: 'Pendências QA', color: C.dim },
}

/** O voto de uma PR: o escolhido; sem escolha, a sugestão do AiDW, senão a do revisor; sem nenhuma, vazio. */
export function prVoteOf(s: Snapshot, chosen: Record<string, string>, pr: string): string {
  if (chosen[pr] !== undefined) return chosen[pr] ?? ''
  const v = s.prTriage?.votes.find(x => x.pr === pr)
  return v ? voteIn(v.aidw, s.votes) || voteIn(v.reviewer, s.votes) : ''
}

const voteLabel = (s: Snapshot, value: string) => (value === 'none' ? 'Sem voto' : s.votes.find(o => o.value === value)?.label ?? value)

/** As PRs da demanda: as da triagem e as do demand.json, sem repetir. */
function prsOf(s: Snapshot): { pr: string; repo: string }[] {
  const out = new Map<string, string>()
  for (const r of s.repos) if (r.pr) out.set(r.pr, r.name)
  for (const c of s.prTriage?.comments ?? []) if (c.pr && !out.has(c.pr)) out.set(c.pr, '')
  for (const v of s.prTriage?.votes ?? []) if (v.pr && !out.has(v.pr)) out.set(v.pr, '')
  return [...out].map(([pr, repo]) => ({ pr, repo }))
}

function PrComments(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button, Input } = ui
  const s = v.snap
  const tri = s.prTriage
  if (!tri) return <Text color={C.dim}>A revisão ainda não terminou.</Text>
  const choice = (id: string) => v.publish[id]
  const filters = [
    { id: 'decidir', label: 'A decidir', has: (c: PrComment) => !c.published && choice(c.id) === undefined && !c.declined },
    { id: 'publicados', label: 'Publicados', has: (c: PrComment) => c.published },
    { id: 'todos', label: 'Todos', has: () => true },
  ]
  const pending = tri.comments.filter(c => filters[0]?.has(c)).length
  const filter = filters.find(f => f.id === v.decisionTab) ?? (pending ? filters[0] : filters[2])
  const prs = prsOf(s)
  const missingVote = prs.filter(p => !prVoteOf(s, v.votes, p.pr))
  const toPublish = tri.comments.filter(c => !c.published && (choice(c.id) ?? false))
  return (
    <Box flexDirection="column" gap={1}>
      <Box justifyContent="space-between" alignItems="center" gap={2} flexWrap="wrap">
        <Text color={C.dim}>rodada {tri.round}</Text>
        <Box gap={1}>
          {filters.map(f =>
            f.id === filter?.id ? (
              <Button key={`pt-${f.id}`} label={`${f.label} ${tri.comments.filter(c => f.has(c)).length}`} onPress={() => act.decisionTab(f.id)} />
            ) : (
              <Button key={`pt-${f.id}`} label={`${f.label} ${tri.comments.filter(c => f.has(c)).length}`} plain dimColor onPress={() => act.decisionTab(f.id)} />
            ),
          )}
        </Box>
      </Box>
      {prs.map(({ pr, repo }) => {
        const list = tri.comments.filter(c => c.pr === pr && filter?.has(c))
        const all = tri.comments.filter(c => c.pr === pr).length
        return (
          <Box key={`prg-${pr}`} flexDirection="column" gap={1}>
            <Box gap={2}>
              <Text bold color={C.strong}>
                PR {pr}
              </Text>
              <Text color={C.dim}>
                {[repo, `${all} comentário${all === 1 ? '' : 's'}`].filter(Boolean).join(' · ')}
              </Text>
            </Box>
            {list.map(c => prCommentCard(ui, v, act, c))}
            {prVoteCard(ui, v, act, pr)}
          </Box>
        )
      })}
      {tri.comments.some(c => !c.pr) && (
        <Box flexDirection="column" gap={1}>
          <Text bold color={C.strong}>
            Sem PR na triagem
          </Text>
          {tri.comments.filter(c => !c.pr && filter?.has(c)).map(c => prCommentCard(ui, v, act, c))}
        </Box>
      )}
      {tri.outside &&
        card(
          ui,
          'fora',
          'Fora das PRs',
          v.expanded.outside ? (
            <Box flexDirection="column">
              {ui.Markdown ? <ui.Markdown key="fora-md" text={tri.outside} /> : <Text>{tri.outside}</Text>}
              <Button key="fora-less" label="Mostrar menos" plain dimColor onPress={() => act.expand('outside')} />
            </Box>
          ) : (
            <Button key="fora-more" label="Mostrar" plain dimColor onPress={() => act.expand('outside')} />
          ),
          `${tri.outside.split('\n').filter(l => /^\s*-\s/.test(l) && !/^\s{2,}/.test(l)).length} · não viram comentário`,
        )}
      <Box justifyContent="space-between" alignItems="center" gap={2}>
        <Box flexShrink={1}>
          <Text color={missingVote.length ? C.amber : C.dim}>
            {missingVote.length
              ? `Escolha o voto da PR ${missingVote.map(p => p.pr).join(' e da PR ')}.`
              : `${prs.map(p => `${p.pr}: ${voteLabel(s, prVoteOf(s, v.votes, p.pr)).toLowerCase()}`).join(' · ')} · ${toPublish.length} comentário(s) para publicar · nada sai até você enviar`}
          </Text>
        </Box>
        {!missingVote.length && <Button key="pr-decision" label="Levar decisão ao prompt" variant="primary" onPress={() => act.sendPrDecision()} />}
      </Box>
    </Box>
  )
}

function prCommentCard(ui: UI, v: ViewState, act: Actions, c: PrComment) {
  const { Box, Text, Button, Input } = ui
  const sev = PR_SEV[c.severity] ?? { label: c.severity || '—', color: C.dim }
  const key = `comentario-${c.id}`
  const editing = v.expanded[`edit:${c.id}`]
  const open = v.expanded[`c:${c.id}`] ?? (!c.published && !c.declined)
  const text = v.drafts[key] ?? c.draft
  const chosen = v.publish[c.id]
  const recommendsPublish = /^\W*publicar/i.test(c.recommendation)
  const status = c.published ? { text: c.situation || 'publicado', color: C.green } : c.declined ? { text: c.situation, color: C.faint } : { text: 'a decidir', color: C.amber }
  return (
    <Box key={`pc-${c.id}`} flexDirection="column" borderStyle="round" borderColor={C.line} paddingX={2} paddingY={1} gap={1}>
      <Box gap={1} flexWrap="wrap">
        {chip(ui, `pcs-${c.id}`, sev.label, sev.color)}
        <Text color={C.dim}>{c.id}</Text>
        <Box flexGrow={1} flexShrink={1}>
          <Text color={C.dim}>{c.where}</Text>
        </Box>
        <Text color={status.color}>{status.text}</Text>
      </Box>
      {rich(ui, `pct-${c.id}`, c.title || c.id)}
      {c.origins.length > 0 && <Text color={C.faint}>junta {c.origins.join(' · ')}</Text>}
      {!open && (
        <Button key={`pco-${c.id}`} label="Ver comentário" plain dimColor onPress={() => act.expand(`c:${c.id}`)} />
      )}
      {open && text && (
        <Box flexDirection="column" borderStyle="round" borderColor={C.line} paddingX={1}>
          <Box justifyContent="space-between" gap={1}>
            <Text color={C.dim}>Comentário na PR {c.pr}</Text>
            {!c.published && (
              <Box gap={1}>
                <Button key={`pe-${c.id}`} label={editing ? 'pronto' : 'editar'} plain dimColor onPress={() => act.expand(`edit:${c.id}`)} />
                <Button
                  key={`pa-${c.id}`}
                  label="ajustar no chat ↗"
                  plain
                  dimColor
                  onPress={() => act.adjustInChat(`Ajuste o comentário ${c.id} (PR ${c.pr}) antes de publicar. Texto atual:\n\n${text}\n\nO que mudar: `)}
                />
              </Box>
            )}
          </Box>
          {editing ? <Input key={key} value={text} onInput={value => act.draft(key, value)} onSubmit={value => act.draft(key, value)} /> : rich(ui, `pcd-${c.id}`, text)}
        </Box>
      )}
      {open && c.recommendation && !c.published && (
        <Box flexDirection="column">
          <Text color={C.dim}>Recomendação do AiDW</Text>
          {rich(ui, `pcr-${c.id}`, c.recommendation)}
        </Box>
      )}
      {!c.published && (
        <Box gap={1}>
          <Button
            key={`pp-${c.id}`}
            label={`${chosen === true ? '✓ ' : ''}${c.severity === 'DUVIDA' ? 'Perguntar ao time' : 'Publicar'}${recommendsPublish ? ' (recomendado)' : ''}`}
            onPress={() => act.togglePublish(c.id, true)}
          />
          <Button
            key={`pn-${c.id}`}
            label={`${chosen === false || (chosen === undefined && c.declined) ? '✓ ' : ''}Não publicar${recommendsPublish ? '' : ' (recomendado)'}`}
            onPress={() => act.togglePublish(c.id, false)}
          />
        </Box>
      )}
    </Box>
  )
}

function prVoteCard(ui: UI, v: ViewState, act: Actions, pr: string) {
  const { Box, Text, Button } = ui
  const s = v.snap
  const sug = s.prTriage?.votes.find(x => x.pr === pr)
  const reviewer = sug ? voteIn(sug.reviewer, s.votes) : ''
  const aidw = sug ? voteIn(sug.aidw, s.votes) : ''
  const current = prVoteOf(s, v.votes, pr)
  const more = v.expanded[`more:${pr}`] || s.votes.some(o => o.more && o.value === current)
  const options = [...s.votes.filter(o => !o.more || more), { value: 'none', label: 'Sem voto' }]
  const tag = (value: string) => [aidw === value && 'AiDW', reviewer === value && 'revisor'].filter(Boolean).join(' e ')
  return card(
    ui,
    `pv-${pr}`,
    `Voto na PR ${pr}`,
    <Box flexDirection="column" gap={1}>
      {sug ? (
        <Text color={C.dim}>
          {[reviewer && `Revisor: ${voteLabel(s, reviewer)}`, aidw && `AiDW: ${voteLabel(s, aidw)}`, sug.why].filter(Boolean).join(' · ')}
        </Text>
      ) : (
        <Text color={C.amber}>A triagem não sugere voto para esta PR: escolha um.</Text>
      )}
      <Box gap={1} flexWrap="wrap">
        {options.map(o => {
          const t = tag(o.value)
          const label = `${o.value === current ? '● ' : ''}${o.label}${t ? ` (${t})` : ''}`
          return o.value === current ? (
            <Button key={`vote-${pr}-${o.value}`} label={label} onPress={() => act.votePr(pr, o.value)} />
          ) : (
            <Button key={`vote-${pr}-${o.value}`} label={label} plain dimColor onPress={() => act.votePr(pr, o.value)} />
          )
        })}
        {!more && s.votes.some(o => o.more) && (
          <Button key={`vote-more-${pr}`} label="Mais opções" plain dimColor onPress={() => act.expand(`more:${pr}`)} />
        )}
      </Box>
    </Box>,
  )
}

// --- Levantamento ----------------------------------------------------------------------------------------------

const SITUATION: Record<string, string> = {
  'precisa mudar': C.amber,
  'é a dor': C.purple,
  'não muda': C.green,
  'nada a reaproveitar': C.dim,
}

function CardCode(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button } = ui
  const s = v.snap
  const pts = s.cardPoints
  const counts = Object.entries(pts.reduce<Record<string, number>>((acc, p) => ({ ...acc, [p.situation]: (acc[p.situation] ?? 0) + 1 }), {}))
  const all = v.expanded.cardPoints
  const shown = all ? pts : pts.slice(0, 5)
  return (
    <Box flexDirection="column" gap={1}>
      {s.cardAsk && card(ui, 'ask', 'O que o card pede', rich(ui, 'ask-t', s.cardAsk))}
      {pts.length === 0 && s.points.length === 0 && <Text color={C.dim}>Os pontos aparecem quando o explorador validar o card no código.</Text>}
      {pts.length > 0 &&
        card(
          ui,
          'pts',
          'Validado no código',
          <Box flexDirection="column" gap={1}>
            {shown.map((p, i) => (
              <Box key={`pt-${i}`} gap={2} alignItems="flex-start">
                <Box width={20} flexShrink={0}>
                  <Text color={SITUATION[p.situation] ?? C.dim} bold>
                    {p.situation}
                  </Text>
                </Box>
                <Box flexDirection="column" flexGrow={1} flexShrink={1}>
                  {rich(ui, `ptt-${i}`, p.today)}
                  {rich(ui, `pte-${i}`, p.effect, C.dim)}
                </Box>
              </Box>
            ))}
            {pts.length > 5 && (
              <Button key="pts-more" label={all ? 'Mostrar menos' : `Mostrar mais ${pts.length - 5}`} plain dimColor onPress={() => act.expand('cardPoints')} />
            )}
          </Box>,
          counts.map(([k, n]) => `${n} ${k}`).join(' · '),
        )}
      {pts.length === 0 &&
        s.points.length > 0 &&
        card(
          ui,
          'pts-old',
          'Pontos do card',
          <Box flexDirection="column">
            {s.points.map(p => (
              <Box key={`po-${p.id}`} gap={2}>
                <Box width={5}>
                  <Text color={C.dim}>{p.id}</Text>
                </Box>
                <Box flexGrow={1} flexShrink={1}>
                  {rich(ui, `pot-${p.id}`, p.text)}
                </Box>
                <Text color={C.mid}>{p.verdict}</Text>
              </Box>
            ))}
          </Box>,
          `${s.points.length} pontos`,
        )}
      {s.touches && card(ui, 'touches', 'Onde a mudança toca', ui.Markdown ? <ui.Markdown key="touches-md" text={s.touches} /> : <Text>{s.touches}</Text>)}
    </Box>
  )
}

function EstimateView(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button } = ui
  const s = v.snap
  const e = s.estimate
  if (!e) return <Text color={C.dim}>A estimativa aparece quando o levantamento-&lt;id&gt;.md for gravado.</Text>
  const kpis = [
    [e.spCard || e.sp, e.spCard ? 'o card como está' : 'story points'],
    [e.spSplit, 'quebrado em itens'],
    [e.devDays || e.hours, e.devDays ? 'desenvolvimento' : 'horas'],
    [e.qaDays ? `+${e.qaDays}` : '', 'QA integrado'],
    [[e.complexity, e.confidence].filter(Boolean).join(' · '), 'complexidade · confiança'],
  ].filter(([n]) => n)
  const maxDays = Math.max(1, ...s.effort.map(b => b.max))
  return (
    <Box flexDirection="column" gap={1}>
      <Box gap={1} flexWrap="wrap">
        {kpis.map(([n, label]) => (
          <Box key={`ek-${label}`} flexDirection="column" flexGrow={1} borderStyle="round" borderColor={C.line} paddingX={2}>
            <Text bold color={C.strong}>
              {n}
            </Text>
            <Text color={C.dim}>{label}</Text>
          </Box>
        ))}
      </Box>
      {(e.level || e.passes) && <Text color={C.dim}>{[e.level && `nível AiDW ${e.level}`, e.passes && `passadas extras: ${e.passes}`].filter(Boolean).join(' · ')}</Text>}
      {s.effort.length > 0 &&
        card(
          ui,
          'eff',
          'Esforço por bloco',
          <Box flexDirection="column">
            {s.effort.map(b => (
              <Box key={`eb-${b.name}`} gap={2} alignItems="center">
                <Box width={36} flexShrink={1}>
                  {rich(ui, `ebn-${b.name}`, b.name)}
                </Box>
                <Box flexGrow={1}>{rangeBar(ui, `ebr-${b.name}`, b.min / maxDays, b.max / maxDays)}</Box>
                <Box width={7} justifyContent="flex-end">
                  <Text>{b.label}</Text>
                </Box>
              </Box>
            ))}
          </Box>,
          'mínimo a máximo',
        )}
      {s.split.length > 0 &&
        card(
          ui,
          'split',
          'Recomendação: quebrar em itens',
          <Box flexDirection="column">
            {s.split.map(it => (
              <Box key={`sp-${it.n}`} gap={2}>
                <Text color={C.dim}>{it.n}</Text>
                <Box flexGrow={1} flexShrink={1}>
                  {rich(ui, `spt-${it.n}`, it.text)}
                </Box>
                <Text bold>{it.sp}</Text>
              </Box>
            ))}
          </Box>,
          e.spSplit,
        )}
      {e.risks && card(ui, 'risks', 'Riscos', ui.Markdown ? <ui.Markdown key="risks-md" text={e.risks} /> : <Text>{e.risks}</Text>)}
      <Box justifyContent="space-between" alignItems="center" gap={2}>
        <Text color={C.dim}>Comentar no card é ação travada: vai para o prompt e só vale quando você enviar.</Text>
        <Button key="post-levantamento" label="Levar ao prompt: comentar no card" variant="primary" onPress={() => act.postLevantamento()} />
      </Box>
    </Box>
  )
}

/** As dúvidas do levantamento: as abertas com o campo de resposta; as respondidas numa linha cada, recolhidas. */
function Doubts(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Input, Button } = ui
  const s = v.snap
  const open = s.doubts.filter(d => !answered(d))
  const done = s.doubts.filter(d => answered(d))
  const groups = [...new Set(open.map(d => d.group || 'Dúvidas'))]
  const doneGroups = [...new Set(done.map(d => d.group))]
  const affecting = open.filter(d => d.affects).length
  return (
    <Box flexDirection="column" gap={1}>
      {open.length === 0 && <Text color={C.dim}>Nenhuma dúvida aberta.</Text>}
      {open.length > 0 && (
        <Box justifyContent="space-between" gap={2}>
          <Text bold color={C.strong}>
            Abertas
          </Text>
          <Text color={C.dim}>
            {open.length}
            {affecting ? ` · ${affecting} mudam a estimativa` : ''}
          </Text>
        </Box>
      )}
      {groups.map(g => (
        <Box key={`dg-${g}`} flexDirection="column" gap={1}>
          {groups.length > 1 && <Text color={C.dim}>{g}</Text>}
          {open
            .filter(d => (d.group || 'Dúvidas') === g)
            .map(d => {
              const key = `duvida-${d.id}`
              return (
                <Box key={`dq-${d.id}`} flexDirection="column" borderStyle="round" borderColor={C.line} paddingX={2} paddingY={1} gap={1}>
                  <Box gap={1} flexWrap="wrap">
                    <Text color={C.dim}>{d.id}</Text>
                    {d.to && <Text color={C.dim}>· para {d.to}</Text>}
                    {d.affects && <Text color={C.amber}>· muda: {d.affects}</Text>}
                  </Box>
                  <Text bold>{d.question}</Text>
                  {d.why && rich(ui, `dw-${d.id}`, d.why, C.dim)}
                  <Box gap={1} alignItems="center">
                    <Box flexGrow={1}>
                      <Input
                        key={key}
                        placeholder="sua resposta, se já souber"
                        value={v.drafts[key] ?? ''}
                        onInput={value => act.draft(key, value)}
                        onSubmit={() => act.answerDoubt(d.id)}
                        submitLabel="Responder"
                      />
                    </Box>
                    <Button
                      key={`dc-${d.id}`}
                      label="ajustar no chat ↗"
                      plain
                      dimColor
                      onPress={() => act.adjustInChat(`Sobre a dúvida ${d.id} do levantamento ${s.id} ("${d.question}"): `)}
                    />
                  </Box>
                </Box>
              )
            })}
        </Box>
      ))}
      {doneGroups.map(g => {
        const items = done.filter(d => d.group === g)
        const shown = v.expanded[`dg:${g}`]
        return card(
          ui,
          `dd-${g}`,
          g,
          <Box flexDirection="column">
            {(shown ? items : items.slice(0, 3)).map(d => (
              <Box key={`dd-${d.id}`} gap={2}>
                <Box width={5} flexShrink={0}>
                  <Text color={C.dim}>{d.id}</Text>
                </Box>
                <Box flexGrow={1} flexShrink={1}>
                  {rich(ui, `ddq-${d.id}`, d.question)}
                </Box>
                {d.to && <Text color={C.dim}>{d.to}</Text>}
              </Box>
            ))}
            {items.length > 3 && (
              <Button key={`ddm-${g}`} label={shown ? 'Mostrar menos' : `Mostrar mais ${items.length - 3}`} plain dimColor onPress={() => act.expand(`dg:${g}`)} />
            )}
          </Box>,
          String(items.length),
        )
      })}
    </Box>
  )
}

/** Uma barra de intervalo (mínimo a máximo) na escala 0…1. */
function rangeBar(ui: UI, key: string, from: number, to: number) {
  const width = 260
  if (ui.Svg) {
    const x = Math.round(from * width * 0.999)
    const w = Math.max(4, Math.round((to - from) * width) || 4)
    return (
      <ui.Svg
        key={key}
        alt={`${Math.round(from * 100)}–${Math.round(to * 100)}%`}
        width={width}
        height={8}
        source={svgDoc(width, 8, `<rect width="${width}" height="8" rx="4" ${fill(C.line)}/><rect x="${Math.min(x, width - w)}" width="${w}" height="8" rx="4" ${fill(C.bar)}/>`)}
      />
    )
  }
  const a = Math.round(from * 20)
  const b = Math.max(a + 1, Math.round(to * 20))
  return (
    <ui.Text key={key}>
      <ui.Text color={C.line}>{'·'.repeat(a)}</ui.Text>
      <ui.Text color={C.bar}>{'█'.repeat(b - a)}</ui.Text>
      <ui.Text color={C.line}>{'·'.repeat(20 - b)}</ui.Text>
    </ui.Text>
  )
}

// ---------------------------------------------------------------------------------------------------------------
// Textos que os botões mandam ao orquestrador

export function prDecisionText(s: Snapshot, publish: Record<string, boolean>, vote: string, drafts: Record<string, string> = {}): string {
  const list = s.findings.filter(f => f.source !== 'plano' && f.severity !== 'ELOGIO')
  const round = Math.max(0, ...list.map(f => f.round))
  const shown = list.filter(f => f.round === round && !f.published)
  const yes = shown.filter(f => publish[f.id] === true)
  const no = shown.filter(f => publish[f.id] === false).map(f => f.id)
  const edited = yes.filter(f => drafts[`comentario-${f.id}`] && drafts[`comentario-${f.id}`] !== f.comment)
  const label = VOTES.find(o => o.value === vote)?.label ?? 'nenhum escolhido (não vote)'
  return [
    `Revisão final da PR (${s.id}, rodada ${round}):`,
    `- Publicar: ${yes.map(f => f.id).join(', ') || 'nenhum'} (com o texto dos rascunhos${edited.length ? ', exceto os editados abaixo' : ' como está'}).`,
    ...edited.map(f => `  - ${f.id}, texto editado: ${drafts[`comentario-${f.id}`]}`),
    `- Não publicar: ${no.join(', ') || 'nenhum'}.`,
    `- Voto: ${label}.`,
    'Pode publicar e votar exatamente isso.',
  ].join('\n')
}

/** A decisão da revisão de PR, PR por PR: o que publicar (com os textos editados) e o voto. */
export function prTriageDecisionText(s: Snapshot, publish: Record<string, boolean>, chosen: Record<string, string>, drafts: Record<string, string> = {}): string {
  const tri = s.prTriage
  if (!tri) return ''
  const lines = [`Revisão final da PR (${s.id}, rodada ${tri.round}):`]
  for (const { pr } of prsOf(s)) {
    const open = tri.comments.filter(c => c.pr === pr && !c.published)
    const yes = open.filter(c => publish[c.id] === true)
    const no = open.filter(c => publish[c.id] === false || (publish[c.id] === undefined && c.declined)).map(c => c.id)
    const undecided = open.filter(c => publish[c.id] === undefined && !c.declined).map(c => c.id)
    const vote = prVoteOf(s, chosen, pr)
    const voteText = vote === 'none' ? 'sem voto' : `${voteLabel(s, vote)} (${vote})`
    lines.push(
      `- PR ${pr}: publicar ${yes.map(c => c.id).join(', ') || 'nenhum'}; não publicar ${no.join(', ') || 'nenhum'}` +
        `${undecided.length ? `; sem decisão, não publicar: ${undecided.join(', ')}` : ''}; voto: ${voteText}.`,
    )
    for (const c of yes) {
      const text = drafts[`comentario-${c.id}`]
      if (text && text !== c.draft) lines.push(`  - ${c.id}, texto editado: ${text}`)
    }
  }
  lines.push('Publique e vote exatamente isso; depois atualize a Situação e o Publicado na triagem.')
  return lines.join('\n')
}

export function levantamentoText(s: Snapshot): string {
  return `OK: publique no card ${s.id} o comentário do levantamento (${s.levantamento}), como está no arquivo.`
}
