// The strip and panel screens (v4, docs/panel.md). They get the surface's element table (not `$`), the
// data and the navigation actions (tabs, round, filters); the panels only inform: every decision is in the chat.

import type { Elements, ThemeKey } from 'claude-code'

import type { Delegation, DemandKind, Doubt, Finding, PrComment, OrchestratorStep, ReviewFilter, RunningAgent, Snapshot, Usage } from '../types'
import { agentModel, agentsLayout, agentTokens, compact } from './aidw'
import { isFixedStatus, kindLabel } from './artifacts'
import { t, tk } from './i18n'
import type { Key } from './i18n'
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
  /** Which of the panels is being drawn. */
  view: View
  snap: Snapshot
  running: RunningAgent[]
  now: number
  tab: string
  usage: Usage | null
  columns: number
  /** `terminal` shows each tab's key (`1: General`); in the app the keys work without showing. */
  surface: string
  reviewFile: string
  decisionTab: string
  filter: ReviewFilter
  expanded: Record<string, boolean>
}

export type View = 'general' | 'metrics' | 'decide'

/**
 * The panels (panel v4): each one is its own pane, opened by the strip button or the command, never by itself. Inside
 * each one, the tabs of the kind; with two or more panels open, the app shows tabs between them.
 */
// Titles and tab labels are i18n keys; `viewTitle` and `visibleTabs` give them in the UI language.
export const VIEWS: Record<View, { title: Key; command: string; tabs: Record<DemandKind, [string, Key][]> }> = {
  general: {
    title: 'view.general',
    command: 'panel',
    tabs: {
      development: [['general', 'view.general']],
      'pr-review': [['general', 'view.general']],
      survey: [['general', 'view.general']],
    },
  },
  metrics: {
    title: 'view.metrics',
    command: 'metrics',
    tabs: { development: [['metrics', 'view.metrics']], 'pr-review': [['metrics', 'view.metrics']], survey: [['metrics', 'view.metrics']] },
  },
  decide: {
    title: 'view.decide',
    command: 'review-tests',
    tabs: {
      development: [['review', 'tab.review'], ['manual', 'tab.tests']],
      'pr-review': [['comments', 'tab.comments']],
      survey: [['questions', 'tab.questions']],
    },
  },
}

/** The panel name for the demand kind: in a survey, the tests and review panel is the questions one. */
export function viewTitle(view: View, kind: DemandKind): string {
  return view === 'decide' && kind === 'survey' ? t('tab.questions') : t(VIEWS[view].title)
}

/** Old tab and panel ids (Portuguese, before the English rename), old names (`/panel fluxo`) and aliases → the tab id. */
const TAB_ALIAS: Record<string, string> = {
  tests: 'manual',
  script: 'manual',
  findings: 'comments',
  // old Portuguese ids
  geral: 'general',
  metricas: 'metrics',
  decidir: 'decide',
  revisao: 'review',
  comentarios: 'comments',
  duvidas: 'questions',
  criterios: 'criteria',
  estimativa: 'estimate',
  codigo: 'code',
  // old Portuguese names
  fluxo: 'general',
  agentes: 'metrics',
  métricas: 'metrics',
  critérios: 'criteria',
  revisão: 'review',
  roteiro: 'manual',
  testes: 'manual',
  pontos: 'code',
  card: 'code',
  dúvidas: 'questions',
  achados: 'comments',
  comentários: 'comments',
}

/** A tab only shows when it has something to show; General always. */
export function tabHasData(s: Snapshot, tab: string): boolean {
  switch (tab) {
    case 'criteria':
      return s.coverage.length > 0 || s.criteria.length > 0
    case 'review':
      return reviewRounds(s).length > 0
    case 'manual':
      return s.manual.some(m => !m.removed)
    case 'metrics':
      return s.delegations.length > 0 || s.orchestrator.rows.length > 0
    case 'comments':
      return (s.prTriage?.comments.length ?? 0) > 0 || prList(s).length > 0
    case 'code':
      return !!s.cardAsk || s.cardPoints.length > 0 || s.points.length > 0
    case 'estimate':
      return !!s.estimate
    case 'questions':
      return s.doubts.length > 0
    default:
      return true
  }
}

/** The panel tabs, for the demand kind, that have data. */
export function visibleTabs(s: Snapshot, view: View): [string, string][] {
  return VIEWS[view].tabs[s.kind].filter(([id]) => tabHasData(s, id)).map(([id, key]) => [id, t(key)])
}

/** An answered question: the survey puts it in an "Answered …" / "Respondidas …" group. */
const answered = (d: Doubt) => /respondid|answered/i.test(d.group)

/** The panel and tab of an argument (`/panel review`): a panel by name, or the panel that has the tab; otherwise General. */
export function viewFor(kind: DemandKind, arg: string): { view: View; tab: string } {
  const id = TAB_ALIAS[arg] ?? arg
  if (id === 'decide' || id === 'metrics') return { view: id, tab: '' }
  const view = (Object.keys(VIEWS) as View[]).find(v => VIEWS[v].tabs[kind].some(([t]) => t === id))
  if (view) return { view, tab: id }
  // the whole tests and review panel by its old names (`review` is also a tab, matched above when the kind has it)
  if (['decisoes', 'decisões', 'review-tests', 'testes-review', 'review'].includes(id)) return { view: 'decide', tab: '' }
  return { view: 'general', tab: '' }
}

// ---------------------------------------------------------------------------------------------------------------
// Colors and common pieces

/**
 * The colors (docs/panel.md › Colors): Claude theme keys, which the app paints in the light or dark theme. There is no
 * neutral background key, so a card is only a border and nothing gets a background.
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
 * The SVG is drawn as an image, outside the theme: each key used in it gets the dark and the light theme color, and the
 * app's `prefers-color-scheme` picks (`[dark, light]`).
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

/** An SVG document with the theme colors; on the elements, `fill(key)` and `stroke(key)`. */
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
/** The local time of an ISO instant (`resetsAt` comes in UTC); with the day when it is not today. */
export const localTime = (iso: string, now: number) => {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const hm = `${two(d.getHours())}:${two(d.getMinutes())}`
  return d.toDateString() === new Date(now).toDateString() ? hm : `${two(d.getDate())}/${two(d.getMonth() + 1)} ${hm}`
}

/** A thin meter bar: SVG in the app, text blocks where there is no SVG. */
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

/** A section, like the cards of Claude's side panel: subtle border, bold title, a summary on the right. */
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

/** Artifact text: with `code` or **bold** it becomes Markdown; without, Text. */
function rich(ui: UI, key: string, text: string, color: string = C.text) {
  if (/`|\*\*/.test(text) && ui.Markdown) return <ui.Markdown key={key} text={text} dimColor={color === C.dim} />
  return (
    <ui.Text key={key} color={color}>
      {text}
    </ui.Text>
  )
}

/** A number row: label on the left, value (and an optional meter) on the right. */
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
 * Choosing among a few options (repositories, PRs, rounds): buttons side by side, the chosen one framed; a single
 * option becomes text; more than 4, the app's selector.
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
// Strip above the prompt

// the context and usage bars: normal color, yellow from 75% and red from 90% (panel v4)
const WARN = 75
const HIGH = 90
const level = (p: number) => (p >= HIGH ? C.red : p >= WARN ? C.amber : C.dim)

/** The panel buttons in the strip; without them (panel off in the context), the strip only has the demand. */
export type BandNav = {
  open: (view: View) => void
  /** There are tests, review or questions in this demand (the button shows). */
  canDecide: boolean
  /** What waits for you on the decision screens (the orange count). */
  pending: number
  hasMetrics: boolean
  /** Runs `/aidw:diff` (the diff panel goes to the demand's next repository); absent when the demand has no worktree. */
  diff?: () => void
}

/**
 * A running agent, as a card: the name, model and effort on top, with the time; below the label and the tokens of the last
 * answer (they move at every step; before the first, `starting`).
 */
function agentCard(ui: UI, a: RunningAgent, now: number) {
  const { Box, Text } = ui
  const model = agentModel(a)
  return (
    <Box
      key={`run-${a.key}`}
      flexDirection="column"
      minWidth={30}
      rowGap="xs"
      borderStyle="round"
      borderColor={C.line}
      padding="sm"
    >
      <Box key="top" justifyContent="space-between" alignItems="center" columnGap="md">
        <Box alignItems="center" columnGap="xs">
          <Text size="footnote" color={C.claude}>●</Text>
          <Text size="footnote" weight="semibold">{a.display ?? a.agent}</Text>
          {model && <Text size="footnote" color={C.dim}>{model}</Text>}
        </Box>
        <Text size="footnote" color={C.dim} tabular>{secs(Math.max(0, Math.round((now - a.since) / 1000)))}</Text>
      </Box>
      <Box key="bottom" justifyContent="space-between" alignItems="center" columnGap="md">
        <Text size="footnote" color={C.dim}>{a.label}</Text>
        <Text size="footnote" color={C.dim} tabular>{agentTokens(a)}</Text>
      </Box>
    </Box>
  )
}

/**
 * The running agents when the cards do not fit on one line: one line per agent, columns aligned (name, model,
 * label, tokens, time); those that do not fit in the height become one summary line with the token total.
 */
function agentList(ui: UI, running: RunningAgent[], shown: number, now: number) {
  const { Box, Text } = ui
  const rows = running.slice(0, shown).map(a => ({
    key: a.key,
    cells: [a.display ?? a.agent, agentModel(a), a.label, a.tokens ? compact(a.tokens) : t('band.starting'),
      secs(Math.max(0, Math.round((now - a.since) / 1000)))],
  }))
  const widths = [0, 1, 2, 3, 4].map(i => Math.max(...rows.map(r => r.cells[i]?.length ?? 0)))
  const rest = running.slice(shown)
  const restTokens = rest.reduce((sum, a) => sum + (a.tokens ?? 0), 0)
  return (
    <Box key="running" flexDirection="column">
      {rows.map(r => (
        <Box key={`run-${r.key}`} columnGap={2} alignItems="center">
          <Text size="footnote" color={C.claude}>●</Text>
          {r.cells.map((cell, i) => (
            <Box key={`c${i}`} minWidth={widths[i]} justifyContent={i >= 3 ? 'flex-end' : 'flex-start'}>
              <Text size="footnote" weight={i === 0 ? 'semibold' : undefined} color={i === 0 ? undefined : C.dim} tabular={i >= 3}>
                {cell}
              </Text>
            </Box>
          ))}
        </Box>
      ))}
      {rest.length > 0 && (
        <Text key="rest" size="footnote" color={C.dim}>
          {`+${rest.length} ${rest.length === 1 ? t('band.agent') : t('band.agents')}${restTokens ? ` · ${compact(restTokens)} tokens` : ''}`}
        </Text>
      )}
    </Box>
  )
}

/** The space the engine gives the strip (columns and rows); without it, the strip does not know the width and shows up to 4 cards. */
export type BandSpace = { columns: number; rows: number }

export function Band(ui: UI, s: Snapshot, running: RunningAgent[], usage: Usage | null, now: number, nav?: BandNav,
  space: BandSpace = { columns: 0, rows: 0 }) {
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
    // the context in the model's real window, as Claude shows it (compaction is yours, or by idleness)
    add('ctx', t('band.context'), usage.percent, `${usage.percent}% · ${compact(usage.tokens)}`, level(usage.percent))
    for (const kind of ['7d', '5h'] as const) {
      const l = usage.limits.find(x => x.kind === kind)
      if (!l) continue
      const p = Math.round(l.percent)
      const at = p >= WARN && l.resetsAt ? localTime(l.resetsAt, now) : ''
      if (p >= 100) add(kind, kind, 100, `${t('band.limit')}${at ? t('band.backAt', { at }) : ''}`, C.red)
      else add(kind, kind, p, `${p}%${at ? t('band.renewsAt', { at }) : ''}`, level(p))
    }
  }
  // the current step next to the id; the model when it is not development
  const where = [s.kind === 'development' ? '' : kindLabel(s.kind), s.progress.current].filter(Boolean).join(' · ')
  // the agents: cards while they fit on one line; otherwise one line per agent, in the lines left by the demand, the
  // buttons and the gaps between them
  const layout = agentsLayout(running, space.columns, space.rows - (nav ? 4 : 2))
  // three lines (panel v4): the demand and the usage; the running agents, when any; the buttons, on one line, on the right
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
              {t('band.waitsForYou')}
            </Text>
          )}
        </Box>
        {/* the metrics together, with a fixed gap between them; loose in space-between, they spread across the line */}
        {parts.length > 0 && (
          <Box key="usage" gap={3} alignItems="center" flexWrap="wrap">
            {parts as never}
          </Box>
        )}
      </Box>
      {running.length > 0 &&
        (layout.mode === 'cards' ? (
          <Box key="running" flexWrap="wrap" gap={1}>
            {running.map(a => agentCard(ui, a, now))}
          </Box>
        ) : (
          agentList(ui, running, layout.shown, now)
        ))}
      {nav && (
        <Box key="nav" justifyContent="flex-end" gap={1} flexWrap="nowrap">
          {nav.diff && <Button key="run-diff" label={t('band.diff')} plain dimColor onPress={nav.diff} />}
          <Button key="open-general" label={t('view.general')} plain dimColor onPress={() => nav.open('general')} />
          {nav.hasMetrics && <Button key="open-metrics" label={t('view.metrics')} plain dimColor onPress={() => nav.open('metrics')} />}
          {nav.canDecide && (
            <Button key="open-decide" plain dimColor={!nav.pending} onPress={() => nav.open('decide')}>
              <Text>
                {viewTitle('decide', s.kind)}
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

/** The demand situation in the header: with the team, waiting for you, paused, done, or just the step. */
function situation(s: Snapshot): { text: string; color: string } {
  const outside = s.progress.stages.find(x => x.state === 'with-team')
  if (s.status === 'paused') return { text: t('sit.paused'), color: C.dim }
  if (s.step === 'DONE') return { text: t('sit.done'), color: C.green }
  if (outside) return { text: t('sit.with', { stage: outside.name, who: outside.who ?? t('who.team') }), color: C.blue }
  if (s.waiting) return { text: t('sit.waits', { stage: s.progress.current }), color: C.amber }
  return { text: s.progress.current, color: C.dim }
}

/** What the count reads: the demand and the decisions marked and not yet sent. */
export type Counted = Pick<ViewState, 'snap' | 'reviewFile'>

/** What waits for you in each tab (the count next to the name). */
function tabCount(v: Counted, tab: string): number {
  const s = v.snap
  switch (tab) {
    case 'review': {
      const file = defaultRound(s, v.reviewFile)
      return file ? roundFindings(s, file).filter(f => f.decision === 'pending' && !isFixed(f)).length : 0
    }
    case 'manual':
      // the steps not passed yet (no result or ❌), automatic and manual, only during the test: before it nothing runs,
      // after it the test is closed
      return TEST_STEPS.has(s.step)
        ? s.manual.filter(m => !m.removed && m.result !== '✅' && !PREP.test(m.section)).length
        : 0
    case 'comments':
      return s.prTriage ? s.prTriage.comments.filter(c => !c.published && !c.declined).length : prList(s).filter(f => !f.published).length
    case 'questions':
      return s.doubts.filter(d => !answered(d)).length
    default:
      return 0
  }
}

/** What waits for a decision (in the chat) in the Tests and Review panel, summed (the number on the strip button). */
export function pendingCount(v: Counted): number {
  return VIEWS.decide.tabs[v.snap.kind].reduce((n, [id]) => n + tabCount(v, id), 0)
}

export function Panel(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button } = ui
  const s = v.snap
  const tabs = visibleTabs(s, v.view)
  const terminal = v.surface === 'terminal'
  const sit = situation(s)
  // the saved tab; otherwise, in Tests and Review, the first one waiting for you; otherwise, the first
  const tab = tabs.some(([id]) => id === v.tab)
    ? v.tab
    : ((v.view === 'decide' ? tabs.find(([id]) => tabCount(v, id) > 0)?.[0] : undefined) ?? tabs[0]?.[0] ?? '')
  const body = !tab
    ? <Text color={C.dim}>{v.view === 'decide' ? (s.kind === 'survey' ? t('panel.noQuestions') : t('panel.noTestsOrReview')) : t('panel.noData')}</Text>
    : tab === 'metrics'
      ? Metrics(ui, v)
      : tab === 'review'
        ? Review(ui, v, act)
        : tab === 'manual'
          ? Manual(ui, v, act)
          : tab === 'comments'
            ? s.prTriage ? PrComments(ui, v, act) : PrFindings(ui, v, act)
            : tab === 'questions'
              ? Doubts(ui, v, act)
              : General(ui, v, act)
  return (
    <Box flexDirection="column" gap={1}>
      <Box key="hdr" flexDirection="column">
        <Box gap={2} flexWrap="wrap">
          <Text color={C.dim}>
            {s.id.toUpperCase().replace('-', ' ')} · {kindLabel(s.kind)}
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
  done: C.done,
  current: C.claude,
  'with-team': C.blue,
  returned: C.amber,
  pending: C.line,
}

/** The progress bar in two groups (AiDW · Team and QA): SVG in the app, text where there is none. */
function progressBar(ui: UI, s: Snapshot) {
  const { Box, Text } = ui
  const p = s.progress
  const groups = [
    { name: 'AiDW', stages: p.stages.filter(x => x.group === 'aidw') },
    { name: t('progress.teamQa'), stages: p.stages.filter(x => x.group === 'outside') },
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
        // outside steps not reached yet are hollow dots, not segments: they do not look like a broken bar
        const hollow = g.name !== 'AiDW' && st.state === 'pending'
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
        alt={t('progress.alt', { index: p.index, total: p.total, current: p.current })}
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
              {st.state === 'pending' ? '▱' : '▰'}
            </Text>
          ))}
        </Text>
      ))}
    </Box>
  )
}

/** The General numbers not in another block of it: the PRs and comments, the open questions. */
function numbers(ui: UI, s: Snapshot) {
  const rows: unknown[] = []
  if (s.kind === 'pr-review') {
    const list = s.prTriage ? s.prTriage.comments : prList(s)
    const published = list.filter(f => f.published).length
    rows.push(stat(ui, 'n-pr', t('num.prs'), String(prsOf(s).length || '—')))
    if (list.length) rows.push(stat(ui, 'n-pub', t('num.published'), t('num.of', { n: published, total: list.length }), { meter: pct(published, list.length) }))
  } else if (s.kind === 'survey' && s.doubts.length) {
    const open = s.doubts.filter(d => !answered(d)).length
    rows.push(stat(ui, 'n-d', t('num.openQuestions'), t('num.of', { n: open, total: s.doubts.length }), open ? { color: C.amber } : {}))
  }
  return rows
}

/**
 * General is a single page (panel v4): the map, the numbers and the next step, and the kind's block — criteria and rules in
 * development, card × code and estimate in a survey. The running agents stay in the strip; the usage, in Metrics.
 */
function General(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text } = ui
  const s = v.snap
  const p = s.progress
  const outside = p.stages.find(x => x.state === 'with-team')
  const returns = Object.entries(p.returns).map(([k, n]) => `${k} ${n}×`).join(' · ')
  const currentColor = outside ? C.blue : C.claude
  const nums = numbers(ui, s)
  return (
    <Box flexDirection="column" gap={1}>
      {card(
        ui,
        'mapa',
        t('general.map'),
        <Box flexDirection="column" gap={1}>
          {s.summary ? rich(ui, 'summary', s.summary) : <Text color={C.dim}>{t('general.noSummary')}</Text>}
          <Box flexDirection="column">
            {progressBar(ui, s)}
            <Box justifyContent="space-between" gap={2}>
              <Box gap={1}>
                <Text color={currentColor} bold>
                  {p.current}
                </Text>
                {p.returnedFrom && chip(ui, 'volta', t('general.returnedFrom', { stage: p.returnedFrom, n: p.returns[p.returnedFrom] ?? 1 }), C.amber)}
              </Box>
              <Text color={C.dim}>
                {`${returns && !p.returnedFrom ? t('general.returns', { list: returns }) : ''}${t('general.stepOf', { index: p.index, total: p.total })}`}
              </Text>
            </Box>
          </Box>
        </Box>,
      )}
      {nums.length > 0 && card(ui, 'numbers', t('general.numbers'), <Box flexDirection="column">{nums as never}</Box>)}
      {s.note && card(ui, 'next', t('general.next'), rich(ui, 'note', s.note), t('general.orchestratorNote'))}
      {s.kind === 'development' && tabHasData(s, 'criteria') && Coverage(ui, v)}
      {s.kind === 'survey' && tabHasData(s, 'code') && CardCode(ui, v, act)}
      {s.kind === 'survey' && s.estimate && EstimateView(ui, v, act)}
    </Box>
  )
}

// --- Criteria and Rules ----------------------------------------------------------------------------------------

const COVER_COLOR: Record<string, string> = { covered: C.green, implemented: C.amber, missing: C.dim }

function Coverage(ui: UI, v: ViewState) {
  const { Box, Text } = ui
  const s = v.snap
  const groups = (['CA', 'RN', 'CN'] as const)
    .map(kind => ({ kind, label: t(`cov.${kind}`), from: t(`cov.${kind}.from`), unit: t(`cov.${kind}.unit`), items: s.coverage.filter(c => c.kind === kind) }))
    .filter(g => g.items.length)
  if (!groups.length) {
    return <Text color={C.dim}>{t('cov.none')}</Text>
  }
  return (
    <Box flexDirection="column" gap={1}>
      {card(
        ui,
        'cob',
        t('cov.title'),
        <Box flexDirection="column" gap={1}>
          <Box gap={3}>
            {groups.map(g => {
              const ok = g.items.filter(i => i.status === 'covered').length
              const impl = g.items.filter(i => i.status === 'implemented').length
              return (
                <Box key={`cg-${g.kind}`} flexDirection="column" flexGrow={1}>
                  <Text>
                    <Text bold color={C.strong}>
                      {ok}
                    </Text>
                    <Text color={C.dim}>{t('cov.of', { n: g.items.length })}</Text>
                  </Text>
                  {meter(ui, `cm-${g.kind}`, pct(ok + impl, g.items.length), impl ? C.amber : C.green, 120)}
                  <Text color={C.dim}>
                    {g.unit}
                    {impl ? t('cov.implemented', { n: impl }) : ''}
                  </Text>
                </Box>
              )
            })}
          </Box>
          {!s.coverageRecorded && <Text color={C.amber}>{t('cov.noPlan')}</Text>}
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
                <Text color={COVER_COLOR[i.status] ?? C.dim}>{tk(`cover.${i.status}`, i.status)}</Text>
              </Box>
            ))}
          </Box>,
          g.from,
        ),
      )}
    </Box>
  )
}

// --- Review ----------------------------------------------------------------------------------------------------

const SEV_COLOR: Record<string, string> = {
  CRITICO: C.red,
  IMPORTANTE: C.amber,
  SUGESTAO: C.blue,
  DUVIDA: C.purple,
  ELOGIO: C.green,
}
/** A severity chip: the label in the UI language and its color. */
const sevOf = (severity: string | null, fallback = severity || '—') =>
  ({ label: tk(`sev.${severity ?? ''}`, fallback), color: SEV_COLOR[severity ?? ''] ?? C.dim })

/** The round names that come from the review file name (English and old Portuguese). */
const ROUND_KEY: Record<string, Key> = {
  otimizacao: 'round.optimization',
  optimization: 'round.optimization',
  seguranca: 'round.security',
  security: 'round.security',
  documentacao: 'round.documentation',
  documentation: 'round.documentation',
}

/** The name of a round by its file: Code, Optimization, Plan, Security, Bugs… */
export function roundName(f: Finding): string {
  if (f.source === 'plan') return t('round.plan')
  if (f.source === 'security') return t('round.security')
  if (f.source === 'bugs') return t('round.bugs')
  // review-<id>-rN → Code; review-optimization-<id>-rN → Optimization; review-T3-a3-rN → T3-a3
  const stem = f.file.replace(/^review-/, '').replace(/-r\d+\.md$/, '')
  if (/^(?:(?:us|it|bug|dt|pr|ft|lv|m)-)?\d+$/i.test(stem)) return t('round.code')
  const extra = stem.replace(/-(?:(?:us|it|bug|dt|pr|ft|lv|m)-\d+|\d{3,})$/i, '')
  const known = ROUND_KEY[extra.toLowerCase()]
  return known ? t(known) : extra.charAt(0).toUpperCase() + extra.slice(1)
}

/** The rounds for the selector: one per review file (bugs and security go with the code review). */
export function reviewRounds(s: Snapshot): { file: string; label: string }[] {
  const seen = new Map<string, { name: string; round: number }>()
  for (const f of s.findings) {
    if (f.source === 'bugs' || f.source === 'security' || !f.file) continue
    seen.set(f.file, { name: roundName(f), round: f.round })
  }
  const order = (n: string) => (n === t('round.plan') ? 0 : n === t('round.code') ? 1 : 2)
  return [...seen]
    .sort(([, a], [, b]) => order(a.name) - order(b.name) || a.name.localeCompare(b.name) || a.round - b.round)
    .map(([file, r]) => ({ file, label: `${r.name} r${r.round}` }))
}

const isFixed = (f: Finding) => isFixedStatus(f.status)
/** A preparation section of the test script (`## Preparação`, `## Preparation`). */
const PREP = /prepar/i
/** The steps in which the test script is being run (the Tests count only counts there). */
const TEST_STEPS = new Set(['TEST', 'TEST_ADJUST', 'MANUAL_TEST'])


/** The finding category: the title's (flow v3) or the source (the older bugs and security passes). */
export function categoryOf(f: Finding): 'quality' | 'bug' | 'security' {
  if (f.category === 'bug' || f.source === 'bugs') return 'bug'
  if (f.category === 'security' || f.source === 'security') return 'security'
  return 'quality'
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

/** The round the Review shows: the chosen one; otherwise the one with a finding waiting for you; otherwise the last code one. */
function defaultRound(s: Snapshot, chosen: string): string {
  const rounds = reviewRounds(s)
  if (rounds.some(r => r.file === chosen)) return chosen
  const waiting = [...rounds].reverse().find(r =>
    s.findings.some(f => f.file === r.file && f.severity !== 'ELOGIO' && f.decision === 'pending' && !isFixed(f)))
  const lastCode = [...rounds].reverse().find(r => r.label.startsWith(t('round.code')))
  return (waiting ?? lastCode ?? rounds.at(-1))?.file ?? ''
}

/** The findings of a round, with the bugs and security passes of the same code round (no praise). */
function roundFindings(s: Snapshot, file: string): Finding[] {
  const current = s.findings.find(f => f.file === file)
  return s.findings.filter(
    f => f.severity !== 'ELOGIO' &&
      (f.file === file || (current && f.source !== 'plan' && f.source !== 'review' && f.round === current.round && current.source === 'review')),
  )
}

function Review(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button } = ui
  const s = v.snap
  const rounds = reviewRounds(s)
  if (!rounds.length) return <Text color={C.dim}>{t('review.none')}</Text>
  const file = defaultRound(s, v.reviewFile)
  const inRound = roundFindings(s, file)
  const praise = s.findings.filter(f => f.file === file && f.severity === 'ELOGIO').length
  const decided = (f: Finding) => (f.decision === 'pending' ? '' : f.decision)
  const tabs = [
    { id: 'with-you', label: t('review.withYou'), has: (f: Finding) => !decided(f) && !isFixed(f) },
    { id: 'kept', label: t('review.kept'), has: (f: Finding) => decided(f) === 'kept' || (!decided(f) && isFixed(f)) },
    { id: 'discarded', label: t('review.discarded'), has: (f: Finding) => decided(f) === 'discarded' },
    { id: 'all', label: t('review.all'), has: () => true },
  ]
  const tab = tabs.find(x => x.id === v.decisionTab) ?? tabs[0]
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
        <Button key="filters" label={activeFilters ? t('review.filtersN', { n: activeFilters }) : t('review.filters')} plain dimColor onPress={() => act.toggleFilters()} />
      </Box>
      {f0.open && (
        <Box flexDirection="column" borderStyle="round" borderColor={C.line} paddingX={2}>
          <Box gap={1} flexWrap="wrap">
            <Text color={C.dim}>{t('review.severity')}</Text>
            {filterButton('severities', 'CRITICO', t('sev.CRITICO'))}
            {filterButton('severities', 'IMPORTANTE', t('sev.IMPORTANTE'))}
            {filterButton('severities', 'SUGESTAO', t('sev.SUGESTAO'))}
            {filterButton('severities', 'DUVIDA', t('sev.DUVIDA'))}
          </Box>
          <Box gap={1} flexWrap="wrap">
            <Text color={C.dim}>{t('review.category')}</Text>
            {filterButton('sources', 'quality', t('cat.quality'))}
            {filterButton('sources', 'bug', t('cat.bug'))}
            {filterButton('sources', 'security', t('cat.security'))}
            <Text color={C.dim}>{t('review.status')}</Text>
            {filterButton('statuses', 'aberto', t('status.open'))}
            {filterButton('statuses', 'corrigido', t('status.fixed'))}
          </Box>
        </Box>
      )}
      <Box gap={1} flexWrap="wrap">
        {tabs.map(tb =>
          tb.id === tab?.id ? (
            <Button key={`dt-${tb.id}`} label={`${tb.label} ${inRound.filter(f => tb.has(f)).length}`} onPress={() => act.decisionTab(tb.id)} />
          ) : (
            <Button key={`dt-${tb.id}`} label={`${tb.label} ${inRound.filter(f => tb.has(f)).length}`} plain dimColor onPress={() => act.decisionTab(tb.id)} />
          ),
        )}
      </Box>
      {shown.length === 0 && <Text color={C.dim}>{tab?.id === 'voce' ? t('review.nothingForYou') : t('review.nothing')}</Text>}
      {shown.map(f => findingCard(ui, f, decided(f)))}
      {praise > 0 && <Text color={C.dim}>{t('review.praise', { n: praise })}</Text>}
    </Box>
  )
}

function findingCard(ui: UI, f: Finding, decided: string) {
  const { Box, Text } = ui
  const sev = sevOf(f.severity)
  const pending = !decided && !isFixed(f)
  const decidedLabel = decided ? tk(`decision.${decided}`, decided) : ''
  return (
    <Box key={`fc-${f.file}-${f.id}`} flexDirection="column" borderStyle="round" borderColor={C.line} paddingX={2} paddingY={1} gap={1}>
      <Box gap={1}>
        {chip(ui, `sev-${f.id}`, sev.label, sev.color)}
        <Text color={C.dim}>{f.id}</Text>
        <Box flexGrow={1} flexShrink={1}>
          <Text color={C.dim}>{f.where || f.source}</Text>
        </Box>
        {isFixed(f) ? chip(ui, `st-${f.id}`, f.status, C.green) : pending ? chip(ui, `st-${f.id}`, t('review.toDecide'), C.amber) : chip(ui, `st-${f.id}`, decidedLabel, C.dim)}
      </Box>
      {rich(ui, `ft-${f.id}`, f.title)}
      {codeBlock(ui, `code-${f.id}`, f)}
      {f.recommendation && (
        <Box flexDirection="column">
          <Text color={C.dim}>{t('review.aidwRecommendation')}</Text>
          {rich(ui, `fr-${f.id}`, f.recommendation)}
        </Box>
      )}
      {f.options.length > 0 && pending && (
        <Box flexDirection="column">
          {f.options.slice(0, 4).map((o, i) => (
            <Box key={`fo-${f.id}-${i}`} gap={1}>
              <Text color={i === 0 ? C.claude : C.dim}>{i === 0 ? '●' : '○'}</Text>
              <Box flexShrink={1}>{rich(ui, `fot-${f.id}-${i}`, i === 0 ? t('review.recommended', { option: o }) : o)}</Box>
            </Box>
          ))}
        </Box>
      )}
      {!pending && <Text color={C.dim}>{`${t('review.decision', { decision: decidedLabel || t('decision.kept') })}${isFixed(f) ? ` · ${f.status}` : ''}`}</Text>}
    </Box>
  )
}

// --- Teste manual ----------------------------------------------------------------------------------------------

function Manual(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button } = ui
  const s = v.snap
  const all = s.manual.filter(m => !m.removed)
  if (!all.length) return <Text color={C.dim}>{t('manual.none')}</Text>
  const prep = all.filter(m => PREP.test(m.section))
  const tests = all.filter(m => !PREP.test(m.section))
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
        t('manual.script'),
        <Box flexDirection="column">
          <Box justifyContent="space-between">
            <Text>
              <Text bold color={C.strong}>
                {passed + failed}
              </Text>
              <Text color={C.dim}>{t('manual.ofSteps', { n: tests.length })}</Text>
            </Text>
            <Text>
              <Text color={C.green}>{t('manual.passed', { n: passed })}</Text>
              <Text color={C.dim}> · </Text>
              <Text color={C.red}>{t('manual.failed', { n: failed })}</Text>
              <Text color={C.dim}>{t('manual.left', { n: tests.length - passed - failed })}</Text>
            </Text>
          </Box>
          {meter(ui, 'mt-bar', pct(passed, tests.length), failed ? C.amber : C.green, 600)}
          <Text color={C.dim}>
            {sections.map(sec => t('manual.sectionOf', { section: sec, done: tests.filter(m => m.section === sec && m.result).length, total: tests.filter(m => m.section === sec).length })).join(' · ')}
            {prep.length ? t('manual.prepApart', { done: prep.filter(m => m.result).length, total: prep.length }) : ''}
          </Text>
        </Box>,
        s.testScript,
      )}
      {next && (
        <Box key="mt-now" flexDirection="column" borderStyle="round" borderColor={C.claude} paddingX={2} paddingY={1} gap={1}>
          <Box justifyContent="space-between">
            <Text color={C.claude} bold>
              {t('manual.next', { id: next.id })}
            </Text>
            <Text color={C.dim}>{next.section}</Text>
          </Box>
          <Text bold color={C.strong}>
            {next.step}
          </Text>
          {next.expected && (
            <Text>
              <Text color={C.dim}>{t('manual.expected')}</Text>
              {next.expected}
            </Text>
          )}
          <Text color={C.dim}>{t('manual.inChat')}</Text>
        </Box>
      )}
      {prep.length > 0 && (
        <Box justifyContent="space-between">
          <Text bold>{t('manual.preparation')}</Text>
          <Button key="mt-prep" label={`${t('num.of', { n: prep.filter(m => m.result).length, total: prep.length })} · ${v.expanded.prep ? t('manual.hide') : t('manual.show')}`} plain onPress={() => act.expand('prep')} />
        </Box>
      )}
      {v.expanded.prep && prep.map(m => stepRow(ui, m, false))}
      {sections.map(sec => (
        <Box key={`sec-${sec}`} flexDirection="column">
          <Box justifyContent="space-between">
            <Text bold>{sec}</Text>
            <Text color={C.dim}>
              {t('num.of', { n: tests.filter(m => m.section === sec && m.result).length, total: tests.filter(m => m.section === sec).length })}
            </Text>
          </Box>
          {tests.filter(m => m.section === sec).map(m => stepRow(ui, m, m === next))}
        </Box>
      ))}
      {removed.length > 0 && (
        <Button
          key="mt-removed"
          label={t('manual.removed', { n: removed.length, ids: removed.map(m => m.id).join(', '), toggle: v.expanded.removed ? t('manual.hide') : t('manual.show') })}
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
        {m.note && <Text color={C.dim}>{t('manual.evidence', { note: m.note })}</Text>}
      </Box>
    </Box>
  )
}

// --- Metrics ---------------------------------------------------------------------------------------------------

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

/** Columns per day (SVG with tooltip in the app; text bars where there is no SVG). */
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
        `<g><title>${ddmm(d.key)}: ${t('metrics.calls', { n: d.n, tokens: compact(d.tokens), time: secs(d.seconds) })}</title>` +
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
        // the orchestrator (seconds < 0): counts turns, not calls, and has no time (the chat stays open)
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
              <Text color={C.dim}>{chat ? t(g.n === 1 ? 'metrics.turn' : 'metrics.turns', { n: g.n }) : String(g.n)}</Text>
            </Box>
            <Box width={7} justifyContent="flex-end">
              <Text color={C.faint}>{chat ? '—' : secs(g.seconds)}</Text>
            </Box>
          </Box>
        )
      })}
    </Box>,
    t('metrics.barsRight'),
  )
}

/** The orchestrator per demand step: where the main chat spent (bar by cost, or by tokens without a price). */
function stepsCard(ui: UI, steps: OrchestratorStep[]) {
  const { Box, Text } = ui
  const priced = steps.some(x => x.cost !== null)
  const weight = (x: OrchestratorStep) => (priced ? (x.cost ?? 0) : x.tokens)
  const sorted = [...steps].sort((a, b) => weight(b) - weight(a))
  const max = Math.max(1e-9, ...sorted.map(weight))
  return card(
    ui,
    'etapas',
    t('metrics.byStep'),
    <Box flexDirection="column">
      {sorted.map(x => (
        <Box key={`et-${x.step}`} gap={2} alignItems="center">
          <Box width={18}>
            <Text>{x.step}</Text>
          </Box>
          <Box flexGrow={1}>{meter(ui, `et-${x.step}-m`, Math.round((weight(x) / max) * 100), C.claude, 260)}</Box>
          <Box width={7} justifyContent="flex-end">
            <Text color={C.text}>{compact(x.tokens)}</Text>
          </Box>
          <Box width={10} justifyContent="flex-end">
            <Text color={C.dim}>{t(x.turns === 1 ? 'metrics.turn' : 'metrics.turns', { n: x.turns })}</Text>
          </Box>
          <Box width={10} justifyContent="flex-end">
            <Text color={C.mid}>{x.cost !== null ? `US$ ${x.cost.toFixed(2)}` : '—'}</Text>
          </Box>
        </Box>
      ))}
    </Box>,
    t('metrics.byStepRight'),
  )
}

function Metrics(ui: UI, v: ViewState) {
  const { Box, Text } = ui
  const s = v.snap
  const d = s.delegations
  const o = s.orchestrator
  const seconds = d.reduce((n, x) => n + x.seconds, 0)
  const priced = d.filter(x => x.cost !== null)
  const rounds = new Set(s.findings.filter(f => f.source !== 'bugs' && f.source !== 'security').map(f => f.file)).size
  const period = d.length ? t('metrics.period', { from: ddmm(d[0]?.date ?? ''), to: ddmm(d.at(-1)?.date ?? '') }) : ''
  const days = groupBy(d, x => x.date)
  const agents = groupBy(d, x => x.agent)
  if (o.rows.length) agents.push({ key: t('metrics.orchestratorKey'), n: o.turns, tokens: o.tokens, seconds: -1, cost: o.cost ?? 0 })
  const cacheRead = o.rows.reduce((n, r) => n + r.cacheRead, 0)
  const cacheWrite = o.rows.reduce((n, r) => n + r.cacheWrite, 0)
  const output = o.rows.reduce((n, r) => n + r.output, 0)
  const results = groupBy(d, x => stateLabel(x.state)).sort((a, b) => b.n - a.n)
  const back = s.timeline.filter(x => x.visits > 1)
  return (
    <Box flexDirection="column" gap={1}>
      {card(
        ui,
        'summary',
        t('metrics.summary'),
        <Box flexDirection="column">
          {stat(ui, 'k-del', t('metrics.delegations'), String(d.length))}
          {rounds > 0 && stat(ui, 'k-rnd', t('metrics.reviewRounds'), String(rounds))}
          {stat(ui, 'k-tok', t('metrics.agentTokens'), compact(s.tokens))}
          {o.rows.length
            ? stat(ui, 'k-orc', t('metrics.orchestratorTokens'), compact(o.tokens))
            : stat(ui, 'k-orc', t('metrics.orchestratorTokens'), t('metrics.noRecord'), { missing: true })}
          {stat(ui, 'k-tim', t('metrics.agentsWorking'), secs(seconds))}
          {priced.length > 0 && stat(ui, 'k-usd', t('metrics.cost', { n: priced.length, total: d.length }), `US$ ${priced.reduce((n, x) => n + (x.cost ?? 0), 0).toFixed(2)}`)}
        </Box>,
        period,
      )}
      {agents.length > 0 && hbars(ui, 'ag', t('metrics.byAgent'), agents.sort((a, b) => b.tokens - a.tokens))}
      {o.rows.length > 0 &&
        card(
          ui,
          'orc',
          t('metrics.orchestrator'),
          <Box flexDirection="column">
            {stat(ui, 'o-cr', t('metrics.cacheRead'), compact(cacheRead))}
            {stat(ui, 'o-cw', t('metrics.cacheWrite'), compact(cacheWrite))}
            {stat(ui, 'o-out', t('metrics.output'), compact(output))}
            {stat(ui, 'o-share', t('metrics.share'), `${pct(o.tokens, o.tokens + s.tokens)}%`, { meter: pct(o.tokens, o.tokens + s.tokens), color: C.claude })}
            {o.rows.map((r, i) => (
              <Box key={`or-${i}`} gap={2}>
                <Box width={10}>
                  <Text color={C.dim}>{r.session}</Text>
                </Box>
                <Box flexGrow={1} flexShrink={1}>
                  <Text>{modelName(r.model)}</Text>
                </Box>
                <Box width={10} justifyContent="flex-end">
                  <Text color={C.dim}>{t(r.turns === 1 ? 'metrics.turn' : 'metrics.turns', { n: r.turns })}</Text>
                </Box>
                <Box width={14} justifyContent="flex-end">
                  <Text color={C.dim}>{t('metrics.cacheReadPct', { n: pct(r.cacheRead, r.tokens) })}</Text>
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
              <Text color={C.dim}>{t('metrics.apiEquivalent', { cost: o.cost.toFixed(2), turns: o.turns })}</Text>
            )}
          </Box>,
          t('metrics.orchestratorRight'),
        )}
      {o.steps.length > 0 && stepsCard(ui, o.steps)}
      {days.length > 1 && card(ui, 'days', t('metrics.perDay'), dayChart(ui, days), ui.Svg ? t('metrics.hover') : '')}
      {d.length > 0 && hbars(ui, 'md', t('metrics.byModel'), groupBy(d, x => `${modelName(x.model)} · ${x.effort}`).sort((a, b) => b.tokens - a.tokens))}
      {d.length > 0 &&
        card(
          ui,
          'res',
          t('metrics.results'),
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
              <Text color={C.dim}>{t('metrics.returns', { list: back.map(x => `${x.name} ${x.visits}×`).join(' · ') })}</Text>
            )}
          </Box>,
        )}
    </Box>
  )
}

// --- PR review without a triage in the pr-triage format (old demands): findings and one approval -----------------

/** The findings of the last round of a PR review (no plan, no praise). */
function prList(s: Snapshot): Finding[] {
  const list = s.findings.filter(f => f.source !== 'plan' && f.severity !== 'ELOGIO')
  const round = Math.max(0, ...list.map(f => f.round))
  return list.filter(f => f.round === round)
}

function PrFindings(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button } = ui
  const s = v.snap
  const inRound = prList(s)
  if (!inRound.length) return <Text color={C.dim}>{t('pr.notFinished')}</Text>
  const tabs = [
    { id: 'decide', label: t('pr.toDecide'), has: (f: Finding) => !f.published },
    { id: 'published', label: t('pr.alreadyPublished'), has: (f: Finding) => f.published },
  ]
  const tab = tabs.find(x => x.id === v.decisionTab) ?? tabs[0]
  const shown = inRound.filter(f => tab?.has(f))
  return (
    <Box flexDirection="column" gap={1}>
      <Box gap={1} flexWrap="wrap">
        {tabs.map(tb =>
          tb.id === tab?.id ? (
            <Button key={`pt-${tb.id}`} label={`${tb.label} ${inRound.filter(f => tb.has(f)).length}`} onPress={() => act.decisionTab(tb.id)} />
          ) : (
            <Button key={`pt-${tb.id}`} label={`${tb.label} ${inRound.filter(f => tb.has(f)).length}`} plain dimColor onPress={() => act.decisionTab(tb.id)} />
          ),
        )}
      </Box>
      {shown.length === 0 && <Text color={C.dim}>{t('review.nothing')}</Text>}
      {shown.map(f => {
        const sev = sevOf(f.severity, '—')
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
                <Text color={C.dim}>{f.target ? t('pr.commentOn', { pr: f.target }) : t('pr.comment')}</Text>
                <Text>{f.comment}</Text>
              </Box>
            )}
            {f.recommendation && (
              <Box flexDirection="column">
                <Text color={C.dim}>{t('review.aidwRecommendation')}</Text>
                {rich(ui, `pr-${f.id}`, f.recommendation)}
              </Box>
            )}
          </Box>
        )
      })}
    </Box>
  )
}

// --- PR review · Comments (triage in the pr-triage format) ----------------------------------------------------

/** PR comment severities: a question is a question to the author; PENDENCIA lists QA pending items. */
const prSevOf = (severity: string) =>
  severity === 'DUVIDA'
    ? { label: t('sev.DUVIDA'), color: C.purple }
    : severity === 'PENDENCIA'
      ? { label: t('sev.PENDENCIA'), color: C.dim }
      : sevOf(severity || null, severity || '—')


/** The demand PRs: the triage's and demand.json's, without repeating. */
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
  if (!tri) return <Text color={C.dim}>{t('pr.notFinished')}</Text>
  const filters = [
    { id: 'decide', label: t('pr.toDecide'), has: (c: PrComment) => !c.published && !c.declined },
    { id: 'published', label: t('pr.published'), has: (c: PrComment) => c.published },
    { id: 'all', label: t('pr.all'), has: () => true },
  ]
  const pending = tri.comments.filter(c => filters[0]?.has(c)).length
  const filter = filters.find(f => f.id === v.decisionTab) ?? (pending ? filters[0] : filters[2])
  const prs = prsOf(s)
  return (
    <Box flexDirection="column" gap={1}>
      <Box justifyContent="space-between" alignItems="center" gap={2} flexWrap="wrap">
        <Text color={C.dim}>{t('pr.round', { n: tri.round })}</Text>
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
                {[repo, t(all === 1 ? 'pr.comment1' : 'pr.commentN', { n: all })].filter(Boolean).join(' · ')}
              </Text>
            </Box>
            {list.map(c => prCommentCard(ui, v, act, c))}
          </Box>
        )
      })}
      {tri.comments.some(c => !c.pr) && (
        <Box flexDirection="column" gap={1}>
          <Text bold color={C.strong}>
            {t('pr.noPr')}
          </Text>
          {tri.comments.filter(c => !c.pr && filter?.has(c)).map(c => prCommentCard(ui, v, act, c))}
        </Box>
      )}
      {tri.outside &&
        card(
          ui,
          'outside',
          t('pr.outside'),
          v.expanded.outside ? (
            <Box flexDirection="column">
              {ui.Markdown ? <ui.Markdown key="outside-md" text={tri.outside} /> : <Text>{tri.outside}</Text>}
              <Button key="outside-less" label={t('common.showLess')} plain dimColor onPress={() => act.expand('outside')} />
            </Box>
          ) : (
            <Button key="outside-more" label={t('common.show')} plain dimColor onPress={() => act.expand('outside')} />
          ),
          t('pr.outsideRight', { n: tri.outside.split('\n').filter(l => /^\s*-\s/.test(l) && !/^\s{2,}/.test(l)).length }),
        )}
    </Box>
  )
}

function prCommentCard(ui: UI, v: ViewState, act: Actions, c: PrComment) {
  const { Box, Text, Button } = ui
  const sev = prSevOf(c.severity)
  const open = v.expanded[`c:${c.id}`] ?? (!c.published && !c.declined)
  const status = c.published
    ? { text: c.situation || t('pr.publishedWord'), color: C.green }
    : c.declined
      ? { text: c.situation, color: C.faint }
      : { text: t('review.toDecide'), color: C.amber }
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
      {c.origins.length > 0 && <Text color={C.faint}>{t('pr.joins', { list: c.origins.join(' · ') })}</Text>}
      {!open && (
        <Button key={`pco-${c.id}`} label={t('pr.viewComment')} plain dimColor onPress={() => act.expand(`c:${c.id}`)} />
      )}
      {open && c.draft && (
        <Box flexDirection="column" borderStyle="round" borderColor={C.line} paddingX={1}>
          <Text color={C.dim}>{t('pr.commentOn', { pr: c.pr })}</Text>
          {rich(ui, `pcd-${c.id}`, c.draft)}
        </Box>
      )}
      {open && c.recommendation && !c.published && (
        <Box flexDirection="column">
          <Text color={C.dim}>{t('review.aidwRecommendation')}</Text>
          {rich(ui, `pcr-${c.id}`, c.recommendation)}
        </Box>
      )}
    </Box>
  )
}

// --- Levantamento ----------------------------------------------------------------------------------------------

/** The color of a card × code situation (the survey text may be English or Portuguese). */
const situationColor = (situation: string) =>
  /precisa|must|needs/i.test(situation)
    ? C.amber
    : /\bdor\b|pain/i.test(situation)
      ? C.purple
      : /n[aã]o mud|no change|unchanged/i.test(situation)
        ? C.green
        : C.dim

function CardCode(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button } = ui
  const s = v.snap
  const pts = s.cardPoints
  const counts = Object.entries(pts.reduce<Record<string, number>>((acc, p) => ({ ...acc, [p.situation]: (acc[p.situation] ?? 0) + 1 }), {}))
  const all = v.expanded.cardPoints
  const shown = all ? pts : pts.slice(0, 5)
  return (
    <Box flexDirection="column" gap={1}>
      {s.cardAsk && card(ui, 'ask', t('survey.ask'), rich(ui, 'ask-t', s.cardAsk))}
      {pts.length === 0 && s.points.length === 0 && <Text color={C.dim}>{t('survey.pointsLater')}</Text>}
      {pts.length > 0 &&
        card(
          ui,
          'pts',
          t('survey.validated'),
          <Box flexDirection="column" gap={1}>
            {shown.map((p, i) => (
              <Box key={`pt-${i}`} gap={2} alignItems="flex-start">
                <Box width={20} flexShrink={0}>
                  <Text color={situationColor(p.situation)} bold>
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
              <Button key="pts-more" label={all ? t('common.showLess') : t('common.showMore', { n: pts.length - 5 })} plain dimColor onPress={() => act.expand('cardPoints')} />
            )}
          </Box>,
          counts.map(([k, n]) => `${n} ${k}`).join(' · '),
        )}
      {pts.length === 0 &&
        s.points.length > 0 &&
        card(
          ui,
          'pts-old',
          t('survey.cardPoints'),
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
          t('survey.nPoints', { n: s.points.length }),
        )}
      {s.touches && card(ui, 'touches', t('survey.touches'), ui.Markdown ? <ui.Markdown key="touches-md" text={s.touches} /> : <Text>{s.touches}</Text>)}
    </Box>
  )
}

function EstimateView(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button } = ui
  const s = v.snap
  const e = s.estimate
  if (!e) return <Text color={C.dim}>{t('survey.estimateLater')}</Text>
  const kpis = [
    [e.spCard || e.sp, e.spCard ? t('survey.cardAsIs') : t('survey.storyPoints')],
    [e.spSplit, t('survey.split')],
    [e.devDays || e.hours, e.devDays ? t('survey.development') : t('survey.hours')],
    [e.qaDays ? `+${e.qaDays}` : '', t('survey.qa')],
    [[e.complexity, e.confidence].filter(Boolean).join(' · '), t('survey.complexityConfidence')],
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
      {(e.level || e.passes) && <Text color={C.dim}>{[e.level && t('survey.level', { level: e.level }), e.passes && t('survey.passes', { passes: e.passes })].filter(Boolean).join(' · ')}</Text>}
      {s.effort.length > 0 &&
        card(
          ui,
          'eff',
          t('survey.effort'),
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
          t('survey.minMax'),
        )}
      {s.split.length > 0 &&
        card(
          ui,
          'split',
          t('survey.splitRec'),
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
      {e.risks && card(ui, 'risks', t('survey.risks'), ui.Markdown ? <ui.Markdown key="risks-md" text={e.risks} /> : <Text>{e.risks}</Text>)}
    </Box>
  )
}

/** The survey questions: the open ones with the answer field; the answered ones one line each, collapsed. */
function Doubts(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button } = ui
  const s = v.snap
  const open = s.doubts.filter(d => !answered(d))
  const done = s.doubts.filter(d => answered(d))
  const groups = [...new Set(open.map(d => d.group || t('doubts.group')))]
  const doneGroups = [...new Set(done.map(d => d.group))]
  const affecting = open.filter(d => d.affects).length
  return (
    <Box flexDirection="column" gap={1}>
      {open.length === 0 && <Text color={C.dim}>{t('doubts.noneOpen')}</Text>}
      {open.length > 0 && (
        <Box justifyContent="space-between" gap={2}>
          <Text bold color={C.strong}>
            {t('doubts.open')}
          </Text>
          <Text color={C.dim}>
            {open.length}
            {affecting ? t('doubts.affecting', { n: affecting }) : ''}
          </Text>
        </Box>
      )}
      {groups.map(g => (
        <Box key={`dg-${g}`} flexDirection="column" gap={1}>
          {groups.length > 1 && <Text color={C.dim}>{g}</Text>}
          {open
            .filter(d => (d.group || t('doubts.group')) === g)
            .map(d => {
              return (
                <Box key={`dq-${d.id}`} flexDirection="column" borderStyle="round" borderColor={C.line} paddingX={2} paddingY={1} gap={1}>
                  <Box gap={1} flexWrap="wrap">
                    <Text color={C.dim}>{d.id}</Text>
                    {d.to && <Text color={C.dim}>{t('doubts.to', { to: d.to })}</Text>}
                    {d.affects && <Text color={C.amber}>{t('doubts.changes', { what: d.affects })}</Text>}
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
              <Button key={`ddm-${g}`} label={shown ? t('common.showLess') : t('common.showMore', { n: items.length - 3 })} plain dimColor onPress={() => act.expand(`dg:${g}`)} />
            )}
          </Box>,
          String(items.length),
        )
      })}
    </Box>
  )
}

/** A range bar (minimum to maximum) on the 0…1 scale. */
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
