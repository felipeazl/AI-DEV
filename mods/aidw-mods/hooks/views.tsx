// As telas da faixa e dos painéis (v4, docs/painel.md). Recebem a tabela de elementos da superfície (não o `$`), os
// dados e as ações de navegação (abas, rodada, filtros); os painéis só informam: toda decisão é no chat.

import type { Elements, ThemeKey } from 'claude-code'

import type { Delegation, DemandKind, Doubt, Finding, PrComment, ReviewFilter, RunningAgent, Snapshot, Usage } from '../types'
import { compact } from './aidw'
import { KIND_LABEL } from './artifacts'
import { stateLabel } from './snapshot'

type Desktop = Elements['desktop']
export type UI = Pick<Desktop, 'Box' | 'Text' | 'Button' | 'Select' | 'Input' | 'Code' | 'Markdown' | 'Link'> & {
  Svg?: Desktop['Svg']
}

export type Actions = {
  tab: (tab: string) => void
  refresh: () => void
  reviewFile: (file: string) => void
  decisionTab: (tab: string) => void
  toggleFilter: (kind: keyof Omit<ReviewFilter, 'open'>, value: string) => void
  toggleFilters: () => void
  expand: (key: string) => void
}

export type ViewState = {
  /** Qual dos painéis está sendo desenhado. */
  view: View
  snap: Snapshot
  running: RunningAgent[]
  now: number
  tab: string
  usage: Usage | null
  columns: number
  /** `terminal` mostra a tecla de cada aba (`1: Geral`); no app as teclas funcionam sem aparecer. */
  surface: string
  reviewFile: string
  decisionTab: string
  filter: ReviewFilter
  expanded: Record<string, boolean>
}

export type View = 'geral' | 'metricas' | 'decidir'

/**
 * Os painéis (painel v4): cada um é um pane próprio, aberto pelo botão da faixa ou pelo comando, nunca sozinho. Dentro
 * de cada um, as abas do uso; com dois ou mais painéis abertos, o app mostra as abas entre eles.
 */
export const VIEWS: Record<View, { title: string; command: string; tabs: Record<DemandKind, [string, string][]> }> = {
  geral: {
    title: 'Geral',
    command: 'painel',
    tabs: {
      desenvolvimento: [['geral', 'Geral']],
      'pr-review': [['geral', 'Geral']],
      levantamento: [['geral', 'Geral']],
    },
  },
  metricas: {
    title: 'Métricas',
    command: 'metricas',
    tabs: { desenvolvimento: [['metricas', 'Métricas']], 'pr-review': [['metricas', 'Métricas']], levantamento: [['metricas', 'Métricas']] },
  },
  decidir: {
    title: 'Testes e Review',
    command: 'testes-review',
    tabs: {
      desenvolvimento: [['revisao', 'Revisão'], ['manual', 'Testes']],
      'pr-review': [['comentarios', 'Comentários']],
      levantamento: [['duvidas', 'Dúvidas']],
    },
  },
}

/** O nome do painel no uso da demanda: no levantamento, o de testes e review é o das dúvidas. */
export function viewTitle(view: View, kind: DemandKind): string {
  return view === 'decidir' && kind === 'levantamento' ? 'Dúvidas' : VIEWS[view].title
}

/** Nomes antigos das abas (`/painel fluxo`) e apelidos. */
const TAB_ALIAS: Record<string, string> = {
  fluxo: 'geral',
  agentes: 'metricas',
  métricas: 'metricas',
  critérios: 'criterios',
  revisão: 'revisao',
  roteiro: 'manual',
  testes: 'manual',
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

/** As abas do painel, no uso da demanda, que têm dados. */
export function visibleTabs(s: Snapshot, view: View): [string, string][] {
  return VIEWS[view].tabs[s.kind].filter(([id]) => tabHasData(s, id))
}

/** Dúvida já respondida: o levantamento a põe num grupo "Respondidas …". */
const answered = (d: Doubt) => /respondid/i.test(d.group)

/** O painel e a aba de um argumento (`/painel revisao`): um painel pelo nome, ou o painel que tem a aba; senão, a Geral. */
export function viewFor(kind: DemandKind, arg: string): { view: View; tab: string } {
  const id = TAB_ALIAS[arg] ?? arg
  if (id === 'decidir' || id === 'metricas') return { view: id, tab: '' }
  if (['decisoes', 'decisões', 'testes-review', 'review'].includes(id)) return { view: 'decidir', tab: '' }
  const view = (Object.keys(VIEWS) as View[]).find(v => VIEWS[v].tabs[kind].some(([t]) => t === id))
  return view ? { view, tab: id } : { view: 'geral', tab: '' }
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

// as barras do contexto e do uso: cor normal, amarela a partir de 75% e vermelha a partir de 90% (painel v4)
const WARN = 75
const HIGH = 90
const level = (p: number) => (p >= HIGH ? C.red : p >= WARN ? C.amber : C.dim)

/** Os botões dos painéis na faixa; sem eles (painel desligado no contexto), a faixa fica só com a demanda. */
export type BandNav = {
  open: (view: View) => void
  /** Há testes, revisão ou dúvidas nesta demanda (o botão aparece). */
  canDecide: boolean
  /** O que espera você nas telas de decisão (a contagem em laranja). */
  pending: number
  hasMetrics: boolean
}

export function Band(ui: UI, s: Snapshot, running: RunningAgent[], usage: Usage | null, now: number, nav?: BandNav) {
  const { Box, Text, Button } = ui
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
    // o contexto na janela real do modelo, como o Claude mostra (a compactação é sua, ou por ociosidade)
    add('ctx', 'contexto', usage.percent, `${usage.percent}% · ${compact(usage.tokens)}`, level(usage.percent))
    for (const kind of ['7d', '5h'] as const) {
      const l = usage.limits.find(x => x.kind === kind)
      if (!l) continue
      const p = Math.round(l.percent)
      const at = p >= WARN && l.resetsAt ? localTime(l.resetsAt, now) : ''
      if (p >= 100) add(kind, kind, 100, `limite${at ? ` · volta ${at}` : ''}`, C.red)
      else add(kind, kind, p, `${p}%${at ? ` · renova ${at}` : ''}`, level(p))
    }
  }
  // a etapa atual ao lado do id; o modelo quando não é desenvolvimento
  const where = [s.kind === 'desenvolvimento' ? '' : KIND_LABEL[s.kind], s.progress.current].filter(Boolean).join(' · ')
  // três linhas (painel v4): a demanda e o consumo; os agentes rodando, quando há; os botões, numa linha só, à direita
  return (
    <Box flexDirection="column" rowGap={1}>
      <Box key="info" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={2}>
        <Box gap={1}>
          <Text color={C.claude} bold>
            AiDW
          </Text>
          <Text>{s.id}</Text>
          {where && <Text color={C.dim}>{where}</Text>}
          {s.waiting && (
            <Text key="waiting" color={C.claude} bold>
              ● espera você
            </Text>
          )}
        </Box>
        {parts as never}
      </Box>
      {running.length > 0 && (
        <Box key="running" flexWrap="wrap" columnGap={2}>
          {running.map(a => (
            <Box key={`run-${a.key}`} gap={1}>
              <Text color={C.claude}>●</Text>
              <Text>{`${a.agent} · ${a.label} · ${secs(Math.max(0, Math.round((now - a.since) / 1000)))}`}</Text>
            </Box>
          ))}
        </Box>
      )}
      {nav && (
        <Box key="nav" justifyContent="flex-end" gap={1} flexWrap="nowrap">
          <Button key="open-geral" label="Geral" plain dimColor onPress={() => nav.open('geral')} />
          {nav.hasMetrics && <Button key="open-metricas" label="Métricas" plain dimColor onPress={() => nav.open('metricas')} />}
          {nav.canDecide && (
            <Button key="open-decidir" plain dimColor={!nav.pending} onPress={() => nav.open('decidir')}>
              <Text>
                {viewTitle('decidir', s.kind)}
                {nav.pending > 0 && <Text color={C.claude}>{` ${nav.pending}`}</Text>}
              </Text>
            </Button>
          )}
        </Box>
      )}
    </Box>
  )
}

// ---------------------------------------------------------------------------------------------------------------
// Painel

/** A situação da demanda no cabeçalho: com o time, espera você, pausada, pronta, ou só a etapa. */
function situation(s: Snapshot): { text: string; color: string } {
  const outside = s.progress.stages.find(x => x.state === 'com-time')
  if (s.status === 'paused') return { text: 'Pausada', color: C.dim }
  if (s.step === 'DONE') return { text: 'Concluída', color: C.green }
  if (outside) return { text: `${outside.name} · com ${outside.who ?? 'o time'}`, color: C.blue }
  if (s.waiting) return { text: `${s.progress.current} · espera você`, color: C.amber }
  return { text: s.progress.current, color: C.dim }
}

/** O que a contagem lê: a demanda e as decisões marcadas e ainda não enviadas. */
export type Counted = Pick<ViewState, 'snap' | 'reviewFile'>

/** O que espera você em cada aba (a contagem ao lado do nome). */
function tabCount(v: Counted, tab: string): number {
  const s = v.snap
  switch (tab) {
    case 'revisao': {
      const file = defaultRound(s, v.reviewFile)
      return file ? roundFindings(s, file).filter(f => f.decision === 'pendente' && !isFixed(f)).length : 0
    }
    case 'manual':
      return s.manual.filter(m => !m.removed && !m.result && !/prepara/i.test(m.section)).length
    case 'comentarios':
      return s.prTriage ? s.prTriage.comments.filter(c => !c.published && !c.declined).length : prList(s).filter(f => !f.published).length
    case 'duvidas':
      return s.doubts.filter(d => !answered(d)).length
    default:
      return 0
  }
}

/** O que espera decisão (no chat) no painel Testes e Review, somado (o número do botão na faixa). */
export function pendingCount(v: Counted): number {
  return VIEWS.decidir.tabs[v.snap.kind].reduce((n, [id]) => n + tabCount(v, id), 0)
}

export function Panel(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button } = ui
  const s = v.snap
  const tabs = visibleTabs(s, v.view)
  const terminal = v.surface === 'terminal'
  const sit = situation(s)
  // a aba guardada; senão, em Testes e Review, a primeira que espera você; senão, a primeira
  const tab = tabs.some(([id]) => id === v.tab)
    ? v.tab
    : ((v.view === 'decidir' ? tabs.find(([id]) => tabCount(v, id) > 0)?.[0] : undefined) ?? tabs[0]?.[0] ?? '')
  const body = !tab
    ? <Text color={C.dim}>{v.view === 'decidir' ? (s.kind === 'levantamento' ? 'Nenhuma dúvida por enquanto.' : 'Ainda sem testes nem revisão nesta demanda.') : 'Ainda sem dados.'}</Text>
    : tab === 'metricas'
      ? Metrics(ui, v)
      : tab === 'revisao'
        ? Review(ui, v, act)
        : tab === 'manual'
          ? Manual(ui, v, act)
          : tab === 'comentarios'
            ? s.prTriage ? PrComments(ui, v, act) : PrFindings(ui, v, act)
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
        {tabs.length > 1 && tabs.map(([id, label], i) => {
          const n = tabCount(v, id)
          const hotkey = terminal ? String(i + 1) : undefined
          return id === tab ? (
            <Button key={`tab-${id}`} hotkey={hotkey} onPress={() => act.tab(id)}>
              <Text>
                {label}
                {n > 0 && <Text color={C.claude}>{` ${n}`}</Text>}
              </Text>
            </Button>
          ) : (
            <Button key={`tab-${id}`} hotkey={hotkey} plain dimColor onPress={() => act.tab(id)}>
              <Text>
                {label}
                {n > 0 && <Text color={C.claude}>{` ${n}`}</Text>}
              </Text>
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

/** Os números da Geral que não estão em outro bloco dela: as PRs e os comentários, as dúvidas abertas. */
function numbers(ui: UI, s: Snapshot) {
  const rows: unknown[] = []
  if (s.kind === 'pr-review') {
    const list = s.prTriage ? s.prTriage.comments : prList(s)
    const published = list.filter(f => f.published).length
    rows.push(stat(ui, 'n-pr', 'PRs', String(prsOf(s).length || '—')))
    if (list.length) rows.push(stat(ui, 'n-pub', 'Comentários publicados', `${published} de ${list.length}`, { meter: pct(published, list.length) }))
  } else if (s.kind === 'levantamento' && s.doubts.length) {
    const open = s.doubts.filter(d => !answered(d)).length
    rows.push(stat(ui, 'n-d', 'Dúvidas abertas', `${open} de ${s.doubts.length}`, open ? { color: C.amber } : {}))
  }
  return rows
}

/**
 * A Geral é uma página só (painel v4): o mapa, os números e o próximo passo, e o bloco do uso — critérios e regras no
 * desenvolvimento, card × código e estimativa no levantamento. Os agentes rodando ficam na faixa; o consumo, em Métricas.
 */
function General(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text } = ui
  const s = v.snap
  const p = s.progress
  const outside = p.stages.find(x => x.state === 'com-time')
  const returns = Object.entries(p.returns).map(([k, n]) => `${k} ${n}×`).join(' · ')
  const currentColor = outside ? C.blue : C.claude
  const nums = numbers(ui, s)
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
        </Box>,
      )}
      {nums.length > 0 && card(ui, 'numeros', 'Números', <Box flexDirection="column">{nums as never}</Box>)}
      {s.note && card(ui, 'proximo', 'Próximo passo', rich(ui, 'note', s.note), 'nota do orquestrador')}
      {s.kind === 'desenvolvimento' && tabHasData(s, 'criterios') && Coverage(ui, v)}
      {s.kind === 'levantamento' && tabHasData(s, 'codigo') && CardCode(ui, v, act)}
      {s.kind === 'levantamento' && s.estimate && EstimateView(ui, v, act)}
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
  const decided = (f: Finding) => (f.decision === 'pendente' ? '' : f.decision)
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
      {shown.map(f => findingCard(ui, f, decided(f)))}
      {praise > 0 && <Text color={C.dim}>{praise} elogio(s) nesta rodada</Text>}
    </Box>
  )
}

function findingCard(ui: UI, f: Finding, decided: string) {
  const { Box, Text } = ui
  const sev = SEV[f.severity ?? ''] ?? { label: f.severity ?? '—', color: C.dim }
  const pending = !decided && !isFixed(f)
  return (
    <Box key={`fc-${f.file}-${f.id}`} flexDirection="column" borderStyle="round" borderColor={C.line} paddingX={2} paddingY={1} gap={1}>
      <Box gap={1}>
        {chip(ui, `sev-${f.id}`, sev.label, sev.color)}
        <Text color={C.dim}>{f.id}</Text>
        <Box flexGrow={1} flexShrink={1}>
          <Text color={C.dim}>{f.where || f.source}</Text>
        </Box>
        {isFixed(f) ? chip(ui, `st-${f.id}`, f.status, C.green) : pending ? chip(ui, `st-${f.id}`, 'a decidir', C.amber) : chip(ui, `st-${f.id}`, decided, C.dim)}
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
      {!pending && <Text color={C.dim}>Decisão: {decided || 'mantido'}{isFixed(f) ? ` · ${f.status}` : ''}</Text>}
    </Box>
  )
}

// --- Teste manual ----------------------------------------------------------------------------------------------

function Manual(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button } = ui
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
              Próximo · {next.id}
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
          <Text color={C.dim}>O resultado e a evidência vão no chat, com o orquestrador.</Text>
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

function Metrics(ui: UI, v: ViewState) {
  const { Box, Text } = ui
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
    </Box>
  )
}

// --- Revisão de PR sem triagem no formato triagem-pr (demandas antigas): achados e uma aprovação ---------------

/** Os achados da última rodada de uma revisão de PR (sem plano nem elogio). */
function prList(s: Snapshot): Finding[] {
  const list = s.findings.filter(f => f.source !== 'plano' && f.severity !== 'ELOGIO')
  const round = Math.max(0, ...list.map(f => f.round))
  return list.filter(f => f.round === round)
}

function PrFindings(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button } = ui
  const s = v.snap
  const inRound = prList(s)
  if (!inRound.length) return <Text color={C.dim}>A revisão ainda não terminou.</Text>
  const tabs = [
    { id: 'decidir', label: 'A decidir', has: (f: Finding) => !f.published },
    { id: 'publicados', label: 'Já publicados', has: (f: Finding) => f.published },
  ]
  const tab = tabs.find(t => t.id === v.decisionTab) ?? tabs[0]
  const shown = inRound.filter(f => tab?.has(f))
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
                <Text color={C.dim}>Comentário{f.target ? ` na PR ${f.target}` : ''}</Text>
                <Text>{f.comment}</Text>
              </Box>
            )}
            {f.recommendation && (
              <Box flexDirection="column">
                <Text color={C.dim}>Recomendação do AiDW</Text>
                {rich(ui, `pr-${f.id}`, f.recommendation)}
              </Box>
            )}
          </Box>
        )
      })}
    </Box>
  )
}

// --- Revisão de PR · Comentários (triagem no formato triagem-pr) ----------------------------------------------

const PR_SEV: Record<string, { label: string; color: string }> = {
  ...SEV,
  DUVIDA: { label: 'Pergunta', color: C.purple },
  PENDENCIA: { label: 'Pendências QA', color: C.dim },
}


/** As PRs da demanda: as da triagem e as do demand.json, sem repetir. */
function prsOf(s: Snapshot): { pr: string; repo: string }[] {
  const out = new Map<string, string>()
  for (const r of s.repos) if (r.pr) out.set(r.pr, r.name)
  for (const c of s.prTriage?.comments ?? []) if (c.pr && !out.has(c.pr)) out.set(c.pr, '')
  return [...out].map(([pr, repo]) => ({ pr, repo }))
}

function PrComments(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button } = ui
  const s = v.snap
  const tri = s.prTriage
  if (!tri) return <Text color={C.dim}>A revisão ainda não terminou.</Text>
  const filters = [
    { id: 'decidir', label: 'A decidir', has: (c: PrComment) => !c.published && !c.declined },
    { id: 'publicados', label: 'Publicados', has: (c: PrComment) => c.published },
    { id: 'todos', label: 'Todos', has: () => true },
  ]
  const pending = tri.comments.filter(c => filters[0]?.has(c)).length
  const filter = filters.find(f => f.id === v.decisionTab) ?? (pending ? filters[0] : filters[2])
  const prs = prsOf(s)
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
    </Box>
  )
}

function prCommentCard(ui: UI, v: ViewState, act: Actions, c: PrComment) {
  const { Box, Text, Button } = ui
  const sev = PR_SEV[c.severity] ?? { label: c.severity || '—', color: C.dim }
  const open = v.expanded[`c:${c.id}`] ?? (!c.published && !c.declined)
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
      {open && c.draft && (
        <Box flexDirection="column" borderStyle="round" borderColor={C.line} paddingX={1}>
          <Text color={C.dim}>Comentário na PR {c.pr}</Text>
          {rich(ui, `pcd-${c.id}`, c.draft)}
        </Box>
      )}
      {open && c.recommendation && !c.published && (
        <Box flexDirection="column">
          <Text color={C.dim}>Recomendação do AiDW</Text>
          {rich(ui, `pcr-${c.id}`, c.recommendation)}
        </Box>
      )}
    </Box>
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
    </Box>
  )
}

/** As dúvidas do levantamento: as abertas com o campo de resposta; as respondidas numa linha cada, recolhidas. */
function Doubts(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button } = ui
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
              return (
                <Box key={`dq-${d.id}`} flexDirection="column" borderStyle="round" borderColor={C.line} paddingX={2} paddingY={1} gap={1}>
                  <Box gap={1} flexWrap="wrap">
                    <Text color={C.dim}>{d.id}</Text>
                    {d.to && <Text color={C.dim}>· para {d.to}</Text>}
                    {d.affects && <Text color={C.amber}>· muda: {d.affects}</Text>}
                  </Box>
                  <Text bold>{d.question}</Text>
                  {d.why && rich(ui, `dw-${d.id}`, d.why, C.dim)}
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
