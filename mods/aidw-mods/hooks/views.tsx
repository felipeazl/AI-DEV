// As telas da faixa e do painel (V2, docs/painel.md). Recebem a tabela de elementos da superfície (não o `$`), os
// dados e as ações; o register.tsx monta as ações (que gravam o estado ou mandam a decisão do Felipe ao orquestrador).

import type { Elements } from 'claude-code'

import type { Delegation, DemandKind, DiffView, Finding, ReviewFilter, RunningAgent, Snapshot, Usage } from '../types'
import { CONTEXT_WARN, compact } from './aidw'
import { KIND_LABEL, VOTES } from './artifacts'
import { stateLabel } from './snapshot'

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
  drafts: Record<string, string>
  diff: DiffView | null
  usage: Usage | null
  extraRounds: number
  columns: number
  canAppDiff: boolean
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
    ['manual', 'Teste manual'],
    ['metricas', 'Métricas'],
  ],
  'pr-review': [
    ['geral', 'Geral'],
    ['achados', 'Achados e voto'],
    ['diffs', 'Diffs'],
    ['metricas', 'Métricas'],
  ],
  levantamento: [
    ['geral', 'Geral'],
    ['codigo', 'Card × código'],
    ['estimativa', 'Estimativa e dúvidas'],
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
}

/** A tab pedida, ou a primeira do uso quando ela não existe nele. */
export function tabFor(kind: DemandKind, tab: string): string {
  const id = TAB_ALIAS[tab] ?? tab
  return TABS[kind].some(([t]) => t === id) ? id : (TABS[kind][0]?.[0] ?? 'geral')
}

// ---------------------------------------------------------------------------------------------------------------
// Cores e peças comuns

/** As cores da V2 (docs/painel.md › Cores). */
export const C = {
  text: '#e8e6e3',
  strong: '#f0eee9',
  mid: '#bdbbb5',
  dim: '#8f8d87',
  line: '#3a3937',
  card: '#262624',
  claude: '#d97757',
  blue: '#8fb3f5',
  amber: '#e5a54b',
  green: '#8fd19e',
  red: '#f0a49c',
  purple: '#c4a8e8',
  done: '#7d7b75',
  bar: '#7a9bd1',
} as const

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
        source={`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="6"><rect width="${width}" height="6" rx="3" fill="${C.line}"/><rect width="${w}" height="6" rx="3" fill="${color}"/></svg>`}
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

/** Um cartão: borda arredondada e sutil, rótulo pequeno em cinza. */
function card(ui: UI, key: string, label: string, children: unknown, right?: string) {
  const { Box, Text } = ui
  return (
    <Box key={key} flexDirection="column" borderStyle="round" borderColor={C.line} paddingX={2} paddingY={1} gap={1}>
      {(label || right) && (
        <Box justifyContent="space-between">
          <Text color={C.dim} bold>
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

function header(ui: UI, s: Snapshot, title: string, extra?: string) {
  const { Box, Text } = ui
  return (
    <Box key="hdr" flexDirection="column">
      <Text color={C.dim}>
        {s.id.toUpperCase().replace('-', ' ')} · {KIND_LABEL[s.kind]}
        {extra ? ` · ${extra}` : ''}
      </Text>
      <Text bold color={C.strong}>
        {title}
      </Text>
    </Box>
  )
}

// ---------------------------------------------------------------------------------------------------------------
// Faixa acima do prompt

const WARN = 80

export function Band(ui: UI, s: Snapshot, running: RunningAgent[], usage: Usage | null, now: number) {
  const { Box, Text } = ui
  const parts: unknown[] = []
  const add = (key: string, label: string, percent: number, text: string, warn = WARN) => {
    const color = percent >= warn ? C.amber : C.mid
    parts.push(
      <Box key={key} gap={1} alignItems="center">
        <Text color={percent >= warn ? C.amber : C.dim}> · {label}</Text>
        {meter(ui, `${key}-m`, percent, color)}
        <Text color={percent >= warn ? C.amber : C.dim}>{text}</Text>
      </Box>,
    )
  }
  if (usage) {
    // o contexto em tokens, com a barra cheia no ponto de compactar: cada ação relê a conversa inteira
    add('ctx', 'contexto', Math.round((usage.tokens / CONTEXT_WARN) * 100), compact(usage.tokens), 100)
    for (const kind of ['7d', '5h'] as const) {
      const l = usage.limits.find(x => x.kind === kind)
      if (!l) continue
      const at = l.percent >= WARN && l.resetsAt ? localTime(l.resetsAt, now) : ''
      const reset = at ? ` (renova ${at})` : ''
      add(kind, kind, Math.round(l.percent), `${Math.round(l.percent)}%${reset}`)
    }
  }
  return (
    <Box flexWrap="wrap" alignItems="center">
      <Text color={C.claude} bold>
        AiDW{' '}
      </Text>
      <Text>{s.id}</Text>
      {parts as never}
      {running.length > 0 && (
        <Text color={C.blue}>
          {' '}
          · ▶ {running.map(a => `${a.agent} (${a.label}) ${secs(Math.max(0, Math.round((now - a.since) / 1000)))}`).join(' · ')}
        </Text>
      )}
    </Box>
  )
}

// ---------------------------------------------------------------------------------------------------------------
// Painel

export function Panel(ui: UI, v: ViewState, act: Actions) {
  const { Box, Button } = ui
  const tab = tabFor(v.snap.kind, v.tab)
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
              : tab === 'achados'
                ? PrFindings(ui, v, act)
                : tab === 'codigo'
                  ? CardCode(ui, v)
                  : tab === 'estimativa'
                    ? EstimateView(ui, v, act)
                    : General(ui, v, act)
  return (
    <Box flexDirection="column" gap={1}>
      <Box flexWrap="wrap" gap={1}>
        {TABS[v.snap.kind].map(([id, label], i) => (
          <Button
            key={`tab-${id}`}
            label={label}
            hotkey={String(i + 1)}
            variant={id === tab ? 'primary' : undefined}
            plain={id === tab ? undefined : true}
            onPress={() => act.tab(id)}
          />
        ))}
        <Button key="refresh" label="Atualizar" hotkey="r" plain dimColor onPress={() => act.refresh()} />
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
      labels.push(`<text x="${x}" y="9" font-size="10" fill="${C.dim}" font-family="system-ui,sans-serif">${g.name}</text>`)
      for (const st of g.stages) {
        const dashed = g.name !== 'AiDW' && st.state === 'pendente'
        rects.push(
          dashed
            ? `<rect x="${x + 0.5}" y="15.5" width="${seg - 1}" height="5" rx="2.5" fill="none" stroke="#5f5d58" stroke-dasharray="3 2"><title>${st.name}</title></rect>`
            : `<rect x="${x}" y="15" width="${seg}" height="6" rx="3" fill="${STAGE_COLOR[st.state] ?? C.line}"><title>${st.name}</title></rect>`,
        )
        x += seg + gap
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
        source={`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="22">${labels.join('')}${rects.join('')}</svg>`}
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

function General(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Link } = ui
  const s = v.snap
  const p = s.progress
  const outside = p.stages.find(x => x.state === 'com-time')
  const situation = s.status === 'paused'
    ? 'Pausada'
    : s.step === 'DONE'
      ? 'Pronto'
      : outside
        ? `${outside.name} · com ${outside.who ?? 'o time'}`
        : `${p.current}${s.waiting ? ' · espera você' : ''}`
  const situationColor = outside ? C.blue : s.waiting ? C.amber : C.mid
  const seconds = s.delegations.reduce((n, d) => n + d.seconds, 0)
  const criteria = s.coverage.filter(c => c.kind === 'CA').length || s.criteria.length
  const returns = Object.entries(p.returns).map(([k, n]) => `${k} ${n}×`).join(' · ')
  const last = s.delegations.at(-1)
  const prs = s.repos.filter(r => r.pr)
  const stat = (key: string, n: string, label: string) => (
    <Box key={key} flexDirection="column" flexGrow={1}>
      <Text bold color={C.strong}>
        {n}
      </Text>
      <Text color={C.dim}>{label}</Text>
    </Box>
  )
  const currentColor = outside ? C.blue : C.claude
  return (
    <Box flexDirection="column" gap={1}>
      <Box key="hdr" flexDirection="column">
        <Box gap={1}>
          <Text color={C.dim}>
            {s.id.toUpperCase().replace('-', ' ')} · {KIND_LABEL[s.kind]}
          </Text>
          {chip(ui, 'sit', situation, situationColor)}
        </Box>
        <Text bold color={C.strong}>
          {s.title || s.id}
        </Text>
      </Box>
      {card(
        ui,
        'mapa',
        'Mapa da demanda',
        <Box flexDirection="column" gap={1}>
          {s.summary ? <Text color={C.text}>{s.summary}</Text> : <Text color={C.dim}>Sem resumo gravado (o orquestrador grava ao entender o card).</Text>}
          <Box gap={2}>
            {stat('st-ca', String(criteria), 'critérios de aceite')}
            {stat('st-tk', compact(s.tokens), 'tokens dos agentes')}
            {stat('st-or', compact(s.orchestrator.tokens), 'tokens do orquestrador')}
            {stat('st-tm', secs(seconds), 'de agentes trabalhando')}
          </Box>
          <Box flexDirection="column">
            {progressBar(ui, s)}
            <Box justifyContent="space-between">
              <Box gap={1}>
                <Text color={currentColor}>{p.current}</Text>
                {p.returnedFrom && chip(ui, 'volta', `↩ voltou do ${p.returnedFrom} · ${p.returns[p.returnedFrom] ?? 1}ª vez`, C.amber)}
              </Box>
              <Text color={C.dim}>
                {returns && !p.returnedFrom ? `voltas: ${returns} · ` : ''}etapa {p.index} de {p.total}
              </Text>
            </Box>
          </Box>
          {s.roundKind && s.round >= s.maxRetries + v.extraRounds && ['PLAN_REVIEW', 'PLAN_FIX', 'PREPARE_REVIEW', 'REVIEW', 'CODER_FIX'].includes(s.step) && (
            <Box gap={1}>
              <Text color={C.amber}>
                O laço de {s.roundKind} chegou ao limite ({s.round} de {s.maxRetries + v.extraRounds}).
              </Text>
              <ui.Button key="extra-round" label="Liberar +1 rodada" onPress={() => act.extraRound()} />
            </Box>
          )}
        </Box>,
      )}
      {card(
        ui,
        'agentes',
        'Agentes rodando',
        <Box flexDirection="column">
          {v.running.length === 0 && (
            <Text color={C.dim}>
              Nenhum agente rodando{last ? ` · último: ${last.agent} (${last.label}), ${stateLabel(last.state)}` : ''}
            </Text>
          )}
          {v.running.map(r => (
            <Box key={`run-${r.key}`} gap={2}>
              <Text color={C.claude}>●</Text>
              <Text bold color={C.strong}>
                {r.agent}
              </Text>
              <Box flexGrow={1}>
                <Text color={C.mid}>{r.label}</Text>
              </Box>
              <Text color={C.dim}>{secs(Math.max(0, Math.round((v.now - r.since) / 1000)))}</Text>
            </Box>
          ))}
        </Box>,
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
          {s.repos.length > 0 && (
            <Box gap={2}>
              <Box width={10}>
                <Text color={C.dim}>Branches</Text>
              </Box>
              <Box flexDirection="column">
                {s.repos.map(r => (
                  <Box key={`br-${r.path}`} gap={1}>
                    <Link key={`lk-${r.path}`} href={fileUrl(r.path)} label={r.name} />
                    <Text color={C.dim}>{r.branch || '?'}</Text>
                  </Box>
                ))}
              </Box>
            </Box>
          )}
          {prs.length > 0 && (
            <Box gap={2}>
              <Box width={10}>
                <Text color={C.dim}>PRs</Text>
              </Box>
              <Box gap={2} flexWrap="wrap">
                {prs.map(r => (
                  <Text key={`pr-${r.path}`} color={C.blue}>
                    PR {r.pr} · {r.name}
                  </Text>
                ))}
              </Box>
            </Box>
          )}
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
    return (
      <Box flexDirection="column" gap={1}>
        {header(ui, s, 'Critérios e Regras')}
        <Text color={C.dim}>Sem critérios, regras ou cenários numerados no plano (CA1, RN1, CN1).</Text>
      </Box>
    )
  }
  return (
    <Box flexDirection="column" gap={1}>
      {header(ui, s, 'Critérios e Regras')}
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
          {!s.coverageRecorded && <Text color={C.amber}>A cobertura ainda não foi registrada (cobertura-{s.id}.md): tudo aparece como "Falta".</Text>}
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
                  <Text color={C.text}>{i.text}</Text>
                </Box>
                {chip(ui, `cs-${i.id}`, COVER[i.status]?.label ?? i.status, COVER[i.status]?.color ?? C.dim)}
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

function Review(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button, Select } = ui
  const s = v.snap
  const rounds = reviewRounds(s)
  if (!rounds.length) {
    return (
      <Box flexDirection="column" gap={1}>
        {header(ui, s, 'Revisão')}
        <Text color={C.dim}>Ainda não houve revisão.</Text>
      </Box>
    )
  }
  // sem escolha: a rodada com achado esperando você; senão a última do código
  const waiting = [...rounds].reverse().find(r =>
    s.findings.some(f => f.file === r.file && f.severity !== 'ELOGIO' && f.decision === 'pendente' && !isFixed(f)))
  const lastCode = [...rounds].reverse().find(r => r.label.startsWith('Código'))
  const file = rounds.some(r => r.file === v.reviewFile) ? v.reviewFile : (waiting ?? lastCode ?? rounds.at(-1))?.file ?? ''
  const current = s.findings.find(f => f.file === file)
  const inRound = s.findings.filter(
    f => f.severity !== 'ELOGIO' &&
      (f.file === file || (current && f.source !== 'plano' && f.source !== 'revisão' && f.round === current.round && current.source === 'revisão')),
  )
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
    .filter(f => !f0.sources.length || f0.sources.includes(f.source))
    .filter(f => !f0.statuses.length || f0.statuses.includes(isFixed(f) ? 'corrigido' : 'aberto'))
  const marked = Object.keys(v.decisions).filter(k => k.startsWith(`${file}:`)).length
  const filterButton = (kind: keyof Omit<ReviewFilter, 'open'>, value: string, label: string) => {
    const on = f0[kind].includes(value)
    return (
      <Button key={`flt-${kind}-${value}`} label={`${on ? '✓ ' : ''}${label}`} plain={on ? undefined : true} onPress={() => act.toggleFilter(kind, value)} />
    )
  }
  const activeFilters = f0.severities.length + f0.sources.length + f0.statuses.length
  return (
    <Box flexDirection="column" gap={1}>
      {header(ui, s, 'Revisão')}
      <Box justifyContent="space-between" alignItems="center">
        <Select key="review-round" value={file} options={rounds.map(r => ({ value: r.file, label: r.label }))} onSelect={value => act.reviewFile(value)} />
        <Button key="filters" label={activeFilters ? `Filtros · ${activeFilters}` : 'Filtros'} plain onPress={() => act.toggleFilters()} />
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
            <Text color={C.dim}>Origem</Text>
            {filterButton('sources', 'revisão', 'Revisor')}
            {filterButton('sources', 'segurança', 'Segurança')}
            {filterButton('sources', 'bugs', 'Bugs')}
            <Text color={C.dim}> Status</Text>
            {filterButton('statuses', 'aberto', 'Aberto')}
            {filterButton('statuses', 'corrigido', 'Corrigido')}
          </Box>
        </Box>
      )}
      <Box gap={2}>
        {tabs.map(t => (
          <Button
            key={`dt-${t.id}`}
            label={`${t.label} ${inRound.filter(f => t.has(f)).length}`}
            plain={t.id === tab?.id ? undefined : true}
            variant={t.id === tab?.id ? 'secondary' : undefined}
            onPress={() => act.decisionTab(t.id)}
          />
        ))}
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
  const options = f.options.length ? f.options.slice(0, 3) : ['Manter', 'Descartar']
  return (
    <Box key={`fc-${f.file}-${f.id}`} flexDirection="column" borderStyle="round" borderColor={C.line} paddingX={2} paddingY={1} gap={1}>
      <Box gap={1}>
        {chip(ui, `sev-${f.id}`, sev.label, sev.color)}
        <Text color={C.dim}>{f.id}</Text>
        <Box flexGrow={1}>
          <Text color={C.dim}>{f.where || f.source}</Text>
        </Box>
        {isFixed(f) ? chip(ui, `st-${f.id}`, f.status, C.green) : pending ? chip(ui, `st-${f.id}`, 'com você', C.amber) : chip(ui, `st-${f.id}`, decided, C.dim)}
      </Box>
      <Text color={C.text}>{f.title}</Text>
      {codeBlock(ui, `code-${f.id}`, f)}
      {f.recommendation && (
        <Box gap={1}>
          <Text color={C.claude} bold>
            Recomendação do AiDW
          </Text>
          <Box flexShrink={1}>
            <Text color={C.text}>{f.recommendation}</Text>
          </Box>
        </Box>
      )}
      {pending ? (
        <Box gap={1} flexWrap="wrap">
          {options.map((o, i) => {
            const value = f.options.length ? o : i === 0 ? 'mantido' : 'descartado'
            const recommended = f.options.length ? i === 0 : (i === 1) === recommendsDrop
            return (
              <Button
                key={`dec-${f.id}-${i}`}
                label={`${marked === value ? '✓ ' : ''}${o}`}
                variant={recommended || marked === value ? 'primary' : undefined}
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

function Diffs(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Select, Code, Button } = ui
  const s = v.snap
  const sources = [
    ...s.repos.map(r => ({ value: `repo:${r.path}`, label: `${r.name}${r.pr ? ` · PR ${r.pr}` : ''}` })),
    ...s.patches.map(p => ({ value: `patch:${p}`, label: p })),
  ]
  if (!sources.length) {
    return (
      <Box flexDirection="column" gap={1}>
        {header(ui, s, 'Diffs')}
        <Text color={C.dim}>Sem worktree nem patch nesta demanda.</Text>
      </Box>
    )
  }
  const d = v.diff
  const repo = d?.source.startsWith('repo:') ? s.repos.find(r => `repo:${r.path}` === d.source) : undefined
  const fileFindings = (path: string) =>
    s.findings.filter(f => f.severity !== 'ELOGIO' && !isFixed(f) && f.where && path.endsWith(f.where.replace(/:\d.*$/, '').split('/').pop() ?? '#'))
  const notes = d ? fileFindings(d.selected) : []
  return (
    <Box flexDirection="column" gap={1}>
      {header(ui, s, 'Diffs')}
      <Box justifyContent="space-between" alignItems="center">
        <Box flexDirection="column">
          <Select key="diff-source" value={d?.source ?? ''} options={sources} onSelect={value => act.diffSource(value)} />
          {d && !d.error && (
            <Text color={C.dim}>
              {repo ? `${repo.branch || '?'} contra ${repo.base || 'a base'} · ` : ''}
              {d.summary}
            </Text>
          )}
        </Box>
        {repo && v.canAppDiff && <Button key="app-diff" label="Abrir no painel de diff do app ↗" plain onPress={() => act.appDiff(repo.name)} />}
      </Box>
      {!d && <Text color={C.dim}>Escolha de onde vem o diff.</Text>}
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
                <Box key={`df-${f.path}`} flexDirection="column" paddingX={1} backgroundColor={on ? C.card : undefined}>
                  <Box justifyContent="space-between">
                    <Button key={`dfb-${f.path}`} label={name} plain onPress={() => act.diffFile(f.path)} />
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
                  <Text>
                    <Text bold>{f.id}</Text>
                    <Text color={C.dim}> {f.where} · </Text>
                    {f.title}
                  </Text>
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
  if (!all.length) {
    return (
      <Box flexDirection="column" gap={1}>
        {header(ui, s, 'Teste manual')}
        <Text color={C.dim}>Sem roteiro de teste manual (o QA grava roteiro-testes-&lt;id&gt;.md quando há passo manual).</Text>
      </Box>
    )
  }
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
      {header(ui, s, 'Teste manual', s.roteiro)}
      {card(
        ui,
        'mt-prog',
        '',
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
    <Box key={`step-${m.section}-${m.id}`} gap={2} paddingX={1} backgroundColor={current ? C.card : undefined}>
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
        `<rect x="${x}" y="${y}" width="${colW}" height="${bh}" rx="4" fill="${C.bar}"/>` +
        `<text x="${x + colW / 2}" y="${y - 5}" text-anchor="middle" font-size="11" fill="${C.mid}" font-family="system-ui,sans-serif">${compact(d.tokens)}</text>` +
        `<text x="${x + colW / 2}" y="${height - 3}" text-anchor="middle" font-size="11" fill="${C.dim}" font-family="system-ui,sans-serif">${ddmm(d.key)}</text></g>`
      )
    })
    return (
      <ui.Svg
        key="days"
        alt={days.map(d => `${ddmm(d.key)} ${compact(d.tokens)}`).join(', ')}
        width={width}
        height={height}
        isInteractive
        source={`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><line x1="0" y1="${height - 18}" x2="${width}" y2="${height - 18}" stroke="${C.line}"/>${bars.join('')}</svg>`}
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
      {groups.map(g => (
        <Box key={`${key}-${g.key}`} gap={2} alignItems="center">
          <Box width={18}>
            <Text>{g.key}</Text>
          </Box>
          <Box flexGrow={1}>{meter(ui, `${key}-${g.key}-m`, pct(g.tokens, max), C.bar, 260)}</Box>
          <Box width={7} justifyContent="flex-end">
            <Text color={C.text}>{compact(g.tokens)}</Text>
          </Box>
          <Box width={4} justifyContent="flex-end">
            <Text color={C.dim}>{g.n}</Text>
          </Box>
          <Box width={7} justifyContent="flex-end">
            <Text color={C.dim}>{secs(g.seconds)}</Text>
          </Box>
        </Box>
      ))}
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
  const kpi = (key: string, n: string, label: string) => (
    <Box key={key} flexDirection="column" flexGrow={1} borderStyle="round" borderColor={C.line} paddingX={2}>
      <Text bold color={C.strong}>
        {n}
      </Text>
      <Text color={C.dim}>{label}</Text>
    </Box>
  )
  const results = groupBy(d, x => stateLabel(x.state)).sort((a, b) => b.n - a.n)
  const back = s.timeline.filter(t => t.visits > 1)
  const recent = [...d].reverse().slice(0, v.expanded.delegations ? d.length : 8)
  const artifacts = Object.entries(s.artifacts)
  const files = artifacts.reduce((n, [, f]) => n + f.length, 0)
  return (
    <Box flexDirection="column" gap={1}>
      {header(ui, s, 'Métricas', period)}
      <Box gap={1}>
        {kpi('k-del', String(d.length), 'delegações')}
        {kpi('k-tok', compact(s.tokens), 'tokens dos agentes')}
        {kpi('k-orc', compact(o.tokens), 'tokens do orquestrador')}
        {kpi('k-tim', secs(seconds), 'de agentes trabalhando')}
        {kpi('k-rnd', String(rounds), 'rodadas de revisão')}
      </Box>
      {priced.length > 0 && <Text color={C.dim}>Custo: US$ {priced.reduce((n, x) => n + (x.cost ?? 0), 0).toFixed(2)} em {priced.length} de {d.length} delegações</Text>}
      {o.rows.length > 0 &&
        card(
          ui,
          'orc',
          'Orquestrador (chat principal)',
          <Box flexDirection="column">
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
          'uma linha por sessão e modelo',
        )}
      {d.length > 0 && card(ui, 'dias', 'Tokens por dia', dayChart(ui, groupBy(d, x => x.date)), ui.Svg ? 'passe o mouse para ver chamadas e tempo' : '')}
      {d.length > 0 && hbars(ui, 'ag', 'Por agente', groupBy(d, x => x.agent).sort((a, b) => b.tokens - a.tokens))}
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

// --- Revisão de PR · Achados e voto ----------------------------------------------------------------------------

function PrFindings(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button, Input } = ui
  const s = v.snap
  const list = s.findings.filter(f => f.source !== 'plano' && f.severity !== 'ELOGIO')
  const round = Math.max(0, ...list.map(f => f.round))
  const inRound = list.filter(f => f.round === round)
  if (!inRound.length) {
    return (
      <Box flexDirection="column" gap={1}>
        {header(ui, s, 'Achados e voto')}
        <Text color={C.dim}>A revisão ainda não terminou.</Text>
      </Box>
    )
  }
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
      {header(ui, s, 'Achados e voto', [...new Set(s.repos.filter(r => r.pr).map(r => `PR ${r.pr} (${r.name})`))].join(' e '))}
      <Box gap={2}>
        {tabs.map(t => (
          <Button
            key={`pt-${t.id}`}
            label={`${t.label} ${inRound.filter(f => t.has(f)).length}`}
            plain={t.id === tab?.id ? undefined : true}
            variant={t.id === tab?.id ? 'secondary' : undefined}
            onPress={() => act.decisionTab(t.id)}
          />
        ))}
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
            <Text color={C.text}>{f.title}</Text>
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
              <Box gap={1}>
                <Text color={C.claude} bold>
                  Recomendação do AiDW
                </Text>
                <Box flexShrink={1}>
                  <Text>{f.recommendation}</Text>
                </Box>
              </Box>
            )}
            {!f.published && (
              <Box gap={1}>
                <Button
                  key={`pp-${f.id}`}
                  label={`${choice(f) === true ? '✓ ' : ''}Publicar`}
                  variant={recommendsPublish || choice(f) === true ? 'primary' : undefined}
                  onPress={() => act.togglePublish(f.id, true)}
                />
                <Button
                  key={`pn-${f.id}`}
                  label={`${choice(f) === false ? '✓ ' : ''}${doubt ? 'Perguntar ao time' : 'Não publicar'}`}
                  variant={!recommendsPublish || choice(f) === false ? 'primary' : undefined}
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
            {VOTES.map(o => (
              <Button
                key={`vote-${o.value}`}
                label={`${o.value === v.vote ? '● ' : ''}${o.label}`}
                variant={o.value === v.vote ? 'primary' : undefined}
                onPress={() => act.vote(o.value)}
              />
            ))}
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
          {toPublish} comentário(s) para publicar · voto: {suggested?.label ?? '—'} · nada sai até você enviar
        </Text>
        <Button key="pr-decision" label="Levar decisão ao prompt" variant="primary" onPress={() => act.sendPrDecision()} />
      </Box>
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

function CardCode(ui: UI, v: ViewState) {
  const { Box, Text } = ui
  const s = v.snap
  const pts = s.cardPoints
  const counts = Object.entries(pts.reduce<Record<string, number>>((acc, p) => ({ ...acc, [p.situation]: (acc[p.situation] ?? 0) + 1 }), {}))
  return (
    <Box flexDirection="column" gap={1}>
      {header(ui, s, 'Card × código', s.title)}
      {s.cardAsk && card(ui, 'ask', 'O que o card pede', <Text>{s.cardAsk}</Text>)}
      {pts.length === 0 && s.points.length === 0 && <Text color={C.dim}>Os pontos aparecem quando o explorador validar o card no código.</Text>}
      {pts.length > 0 &&
        card(
          ui,
          'pts',
          'Validado no código',
          <Box flexDirection="column">
            <Box gap={2}>
              <Box width="42%">
                <Text color={C.dim}>Hoje no código</Text>
              </Box>
              <Box width="42%">
                <Text color={C.dim}>Para a demanda</Text>
              </Box>
              <Box width={20}>
                <Text> </Text>
              </Box>
            </Box>
            {pts.map((p, i) => (
              <Box key={`pt-${i}`} gap={2}>
                <Box width="42%" flexShrink={1}>
                  <Text>{p.today}</Text>
                </Box>
                <Box width="42%" flexShrink={1}>
                  <Text color={C.mid}>{p.effect}</Text>
                </Box>
                <Box width={20} justifyContent="flex-end">
                  {chip(ui, `pts-${i}`, p.situation, SITUATION[p.situation] ?? C.dim)}
                </Box>
              </Box>
            ))}
          </Box>,
          `${pts.length} pontos · ${counts.map(([k, n]) => `${n} ${k}`).join(' · ')}`,
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
                  <Text>{p.text}</Text>
                </Box>
                <Text color={C.mid}>{p.verdict}</Text>
              </Box>
            ))}
          </Box>,
        )}
    </Box>
  )
}

function EstimateView(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Input, Button } = ui
  const s = v.snap
  const e = s.estimate
  if (!e) {
    return (
      <Box flexDirection="column" gap={1}>
        {header(ui, s, 'Estimativa e dúvidas')}
        <Text color={C.dim}>A estimativa aparece quando o levantamento-&lt;id&gt;.md for gravado.</Text>
      </Box>
    )
  }
  const kpis = [
    [e.spCard || e.sp, e.spCard ? 'o card como está' : 'story points'],
    [e.spSplit, 'quebrado em itens'],
    [e.devDays || e.hours, e.devDays ? 'de desenvolvimento' : 'horas'],
    [e.qaDays ? `+${e.qaDays}` : '', 'de QA integrado'],
  ].filter(([n]) => n)
  const maxDays = Math.max(1, ...s.effort.map(b => b.max))
  const groups = [...new Set(s.doubts.map(d => d.group || 'Dúvidas'))]
  const affecting = s.doubts.filter(d => d.affects).length
  const firstGroup = groups[0]
  return (
    <Box flexDirection="column" gap={1}>
      {header(ui, s, 'Estimativa e dúvidas', [e.level && `nível AiDW ${e.level}`, e.passes && `passadas extras: ${e.passes}`].filter(Boolean).join(' · '))}
      <Box gap={1}>
        {kpis.map(([n, label]) => (
          <Box key={`ek-${label}`} flexDirection="column" flexGrow={1} borderStyle="round" borderColor={C.line} paddingX={2}>
            <Text bold color={C.strong}>
              {n}
            </Text>
            <Text color={C.dim}>{label}</Text>
          </Box>
        ))}
      </Box>
      {s.effort.length > 0 &&
        card(
          ui,
          'eff',
          'Esforço por bloco',
          <Box flexDirection="column">
            {s.effort.map(b => (
              <Box key={`eb-${b.name}`} gap={2} alignItems="center">
                <Box width={36}>
                  <Text>{b.name}</Text>
                </Box>
                <Box flexGrow={1}>{rangeBar(ui, `ebr-${b.name}`, b.min / maxDays, b.max / maxDays)}</Box>
                <Box width={7} justifyContent="flex-end">
                  <Text>{b.label}</Text>
                </Box>
              </Box>
            ))}
          </Box>,
          'desenvolvimento · mínimo a máximo',
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
                  <Text>{it.text}</Text>
                </Box>
                <Text bold>{it.sp}</Text>
              </Box>
            ))}
          </Box>,
          e.spSplit,
        )}
      {s.doubts.length > 0 && (
        <Box justifyContent="space-between">
          <Text bold color={C.strong}>
            Dúvidas
          </Text>
          <Text color={C.dim}>
            {s.doubts.length}
            {affecting ? ` · ${affecting} mudam a estimativa` : ''}
          </Text>
        </Box>
      )}
      {groups.map(g => {
        const items = s.doubts.filter(d => (d.group || 'Dúvidas') === g)
        const open = v.expanded[`dg:${g}`] ?? g === firstGroup
        return (
          <Box key={`dg-${g}`} flexDirection="column" gap={1}>
            <Box justifyContent="space-between">
              <Text bold>{g}</Text>
              <Button key={`dgb-${g}`} label={`${items.length} · ${items.map(d => d.id).join(', ')} ${open ? '⌃' : '⌄'}`} plain onPress={() => act.expand(`dg:${g}`)} />
            </Box>
            {open &&
              items.map(d => {
                const key = `duvida-${d.id}`
                return (
                  <Box key={`dq-${d.id}`} flexDirection="column" borderStyle="round" borderColor={C.line} paddingX={2} paddingY={1}>
                    <Box gap={1}>
                      <Text color={C.dim}>{d.id}</Text>
                      <Box flexGrow={1} flexShrink={1}>
                        <Text bold>{d.question}</Text>
                      </Box>
                      {d.affects && chip(ui, `da-${d.id}`, d.affects, C.amber)}
                      {d.to && chip(ui, `dt-${d.id}`, `para ${d.to}`, C.dim)}
                    </Box>
                    {d.why && <Text color={C.dim}>{d.why}</Text>}
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
                        onPress={() => act.adjustInChat(`Sobre a dúvida ${d.id} do levantamento ${s.id} ("${d.question}"): `)}
                      />
                    </Box>
                  </Box>
                )
              })}
          </Box>
        )
      })}
      <Box justifyContent="space-between" alignItems="center">
        <Text color={C.dim}>Comentar no card é ação travada: vai para o prompt e só vale quando você enviar.</Text>
        <Button key="post-levantamento" label="Levar ao prompt: comentar no card" variant="primary" onPress={() => act.postLevantamento()} />
      </Box>
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
        source={`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="8"><rect width="${width}" height="8" rx="4" fill="${C.line}"/><rect x="${Math.min(x, width - w)}" width="${w}" height="8" rx="4" fill="${C.bar}"/></svg>`}
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
  const label = VOTES.find(o => o.value === vote)?.label ?? vote
  return [
    `Revisão final da PR (${s.id}, rodada ${round}):`,
    `- Publicar: ${yes.map(f => f.id).join(', ') || 'nenhum'} (com o texto dos rascunhos${edited.length ? ', exceto os editados abaixo' : ' como está'}).`,
    ...edited.map(f => `  - ${f.id}, texto editado: ${drafts[`comentario-${f.id}`]}`),
    `- Não publicar: ${no.join(', ') || 'nenhum'}.`,
    `- Voto: ${label}.`,
    'Pode publicar e votar exatamente isso.',
  ].join('\n')
}

export function levantamentoText(s: Snapshot): string {
  return `OK: publique no card ${s.id} o comentário do levantamento (${s.levantamento}), como está no arquivo.`
}
