// As telas do painel e da faixa. Recebem a tabela de elementos da superfície (não o `$`), os dados e as ações; o
// register.tsx monta as ações (que gravam o estado ou mandam a decisão do Felipe ao orquestrador).

import type { Elements } from 'claude-code'

import type { Delegation, DemandKind, DiffView, Finding, RunningAgent, Snapshot, Usage } from '../types'
import { compact } from './aidw'
import { KIND_LABEL, VOTES } from './artifacts'
import { LOOP_STEPS, nextStep, phaseOf, stateLabel } from './snapshot'

export type UI = Pick<Elements['terminal'], 'Box' | 'Text' | 'Button' | 'Select' | 'Input' | 'Code' | 'Markdown'>

export type Actions = {
  tab: (tab: string) => void
  refresh: () => void
  extraRound: () => void
  reviewRound: (round: number) => void
  togglePublish: (id: string) => void
  vote: (value: string) => void
  sendPrDecision: () => void
  draft: (key: string, value: string) => void
  manualResult: (step: string, ok: boolean) => void
  answerDoubt: (n: number) => void
  postLevantamento: () => void
  diffSource: (source: string) => void
  diffFile: (path: string) => void
  appDiff: (repo: string) => void
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
  reviewRound: number
  usage: Usage | null
  codeReads: number
  extraRounds: number
  columns: number
  canAppDiff: boolean
}

export const TABS: Record<DemandKind, [string, string][]> = {
  desenvolvimento: [
    ['geral', 'Geral'],
    ['criterios', 'Critérios'],
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
    ['pontos', 'Pontos do card'],
    ['estimativa', 'Estimativa e dúvidas'],
    ['metricas', 'Métricas'],
  ],
}

/** Nomes antigos das abas (`/aidw-painel fluxo`) e apelidos. */
const TAB_ALIAS: Record<string, string> = { fluxo: 'geral', agentes: 'metricas', métricas: 'metricas', critérios: 'criterios', revisão: 'revisao' }

const cell = (s: string) => s.replace(/\|/g, '\\|').replace(/\n/g, ' ')
const pct = (n: number, of: number) => (of > 0 ? Math.round((n / of) * 100) : 0)
const secs = (s: number) =>
  s >= 3600
    ? `${Math.floor(s / 3600)}h${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}m`
    : s >= 60
      ? `${Math.floor(s / 60)}m${String(s % 60).padStart(2, '0')}s`
      : `${s}s`
const SEV_MARK: Record<string, string> = { CRITICO: '⛔', IMPORTANTE: '⚠', SUGESTAO: '💡', ELOGIO: '👍', DUVIDA: '❓' }
const testMarkCount = (s: Snapshot) => Object.values(s.testMarks ?? {}).reduce((a, b) => a + b, 0)
const isOpen = (f: Finding) => !/corrig|resolv|fixed|refutad/.test(`${f.status} ${f.triage.toLowerCase()}`)
const link = (label: string, path: string) => `[${label}](file:///${encodeURI(path)})`
const atLimit = (s: Snapshot, limit: number) =>
  s.kind === 'desenvolvimento' && s.roundKind !== null && s.round >= limit && LOOP_STEPS.has(s.step)

/** A tab pedida, ou a primeira do uso quando ela não existe nele. */
export function tabFor(kind: DemandKind, tab: string): string {
  const id = TAB_ALIAS[tab] ?? tab
  return TABS[kind].some(([t]) => t === id) ? id : (TABS[kind][0]?.[0] ?? 'geral')
}

// ---------------------------------------------------------------------------------------------------------------
// Faixa acima do prompt

export function Band(ui: UI, s: Snapshot, running: RunningAgent[], usage: Usage | null, codeReads: number, extra: number) {
  const { Box, Text } = ui
  const limit = s.maxRetries + extra
  const over = atLimit(s, limit)
  const spent = pct(s.tokens, s.budget)
  const marks = testMarkCount(s)
  return (
    <Box flexWrap="wrap">
      <Text color="claude" bold>
        AiDW{' '}
      </Text>
      <Text>
        {s.id}
        {s.kind !== 'desenvolvimento' ? ` · ${KIND_LABEL[s.kind]}` : ''} · {phaseOf(s)}
      </Text>
      {s.waiting && <Text color="warning"> · ⏸ espera você</Text>}
      {s.roundKind && LOOP_STEPS.has(s.step) && (
        <Text color={over ? 'warning' : undefined}>
          {' '}
          · {s.roundKind} r{s.round}/{limit}
          {over ? ' ⚠ travado' : ''}
        </Text>
      )}
      <Text color={spent >= 80 ? 'warning' : undefined} dimColor={spent < 80}>
        {' '}
        · orçamento {spent}%
      </Text>
      {usage && (
        <Text color={usage.percent >= 70 ? 'warning' : undefined} dimColor={usage.percent < 70}>
          {' '}
          · contexto {usage.percent}%
        </Text>
      )}
      {codeReads > 0 && <Text color="warning"> · {codeReads}× código lido no chat</Text>}
      {marks > 0 && ['REVIEW', 'MANUAL_TEST', 'DOCS', 'FINAL_REVIEW'].includes(s.step) && (
        <Text color="warning"> · {marks} AIDW-TESTE aplicado(s)</Text>
      )}
      {running.length > 0 && (
        <Text color="suggestion"> · ▶ {running.map(a => `${a.agent} (${a.label})`).join(', ')}</Text>
      )}
    </Box>
  )
}

// ---------------------------------------------------------------------------------------------------------------
// Painel

export function Panel(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button } = ui
  const tab = tabFor(v.snap.kind, v.tab)
  const body =
    tab === 'metricas'
      ? Metrics(ui, v)
      : tab === 'criterios'
        ? Criteria(ui, v)
        : tab === 'revisao'
          ? Review(ui, v, act)
          : tab === 'diffs'
            ? Diffs(ui, v, act)
            : tab === 'manual'
              ? Manual(ui, v, act)
              : tab === 'achados'
                ? PrFindings(ui, v, act)
                : tab === 'pontos'
                  ? Points(ui, v)
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
            variant={id === tab ? 'primary' : 'secondary'}
            onPress={() => act.tab(id)}
          />
        ))}
        <Button key="refresh" label="Atualizar" hotkey="r" plain onPress={() => act.refresh()} />
      </Box>
      <Text bold>
        {v.snap.id} · {KIND_LABEL[v.snap.kind]}
        {v.snap.title ? ` — ${v.snap.title}` : ''}
      </Text>
      {body}
    </Box>
  )
}

// Geral: o que importa agora, em poucas linhas — onde está, o próximo passo, o que pede atenção e quem está rodando.
function General(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Markdown, Button } = ui
  const s = v.snap
  const limit = s.maxRetries + v.extraRounds
  const next = nextStep(s, limit)
  const spent = pct(s.tokens, s.budget)
  const marks = testMarkCount(s)
  const headline =
    s.status === 'paused'
      ? '⏸ Pausada'
      : s.step === 'DONE' || s.status === 'done'
        ? '✓ Concluída'
        : s.waiting
          ? `⏸ Espera você: ${s.waiting}`
          : v.running.length
            ? `▶ Trabalhando: ${phaseOf(s)}`
            : `● Em andamento: ${phaseOf(s)}`
  const progress = s.timeline.map(t => `${t.state === 'feito' ? '✓' : t.state === 'atual' ? '●' : '○'} ${t.name}`).join('  ')

  // um número por linha, o essencial de cada uso
  const code = s.findings.filter(f => f.source === 'revisão' && f.severity !== 'ELOGIO')
  const lastRound = Math.max(0, ...code.map(f => f.round))
  const openNow = code.filter(f => f.round === lastRound && isOpen(f)).length
  const summary: string[] = []
  if (s.kind === 'desenvolvimento') {
    const c = s.criteria
    if (c.length && !c.some(x => x.result)) summary.push(`**Critérios de aceite:** ${c.length} · nenhum relatório de teste por critério ainda`)
    else if (c.length) {
      const failed = c.filter(x => x.result === 'falhou').length
      summary.push(`**Critérios de aceite:** ${c.filter(x => x.result === 'atendido').length} de ${c.length} atendidos${failed ? ` · ${failed} falharam` : ''}`)
    }
    if (lastRound) summary.push(`**Revisão do código:** rodada ${lastRound} · ${openNow ? `${openNow} achado(s) aberto(s)` : 'nenhum achado aberto'}`)
    if (s.manual.length) summary.push(`**Teste manual:** ${s.manual.filter(m => m.result).length} de ${s.manual.length} passos feitos`)
  } else if (s.kind === 'pr-review') {
    if (lastRound) summary.push(`**Achados:** ${code.filter(f => f.round === lastRound).length} na rodada ${lastRound}`)
    if (s.vote) summary.push(`**Voto sugerido:** ${s.vote}`)
  } else {
    if (s.points.length) summary.push(`**Pontos do card:** ${s.points.length} validados no código`)
    if (s.estimate) summary.push(`**Estimativa:** ${s.estimate.sp || '?'} SP · ${s.estimate.hours || '?'} h`)
    if (s.doubts.length) summary.push(`**Dúvidas:** ${s.doubts.length}`)
  }
  summary.push(`**Consumo:** ${spent}% do orçamento (${compact(s.tokens)} de ${compact(s.budget)} tokens)`)
  if (v.usage) summary.push(`**Contexto do orquestrador:** ${v.usage.percent}%`)

  const attention = [
    marks ? `${marks} ajuste(s) de teste (AIDW-TESTE) ainda aplicado(s): reverter antes da revisão final` : '',
    spent >= 100 ? 'Passou do orçamento de tokens do nível' : spent >= 80 ? 'Perto do orçamento de tokens do nível' : '',
    v.usage && v.usage.percent >= 80 ? `Contexto do orquestrador em ${v.usage.percent}%: a compactação está perto` : '',
    v.codeReads ? `Código lido ${v.codeReads}× no chat do orquestrador: delegar ao explorador sai mais barato` : '',
  ].filter(Boolean)

  const last = s.delegations.slice(-3).reverse()
  const where = [
    ...s.repos.map(r => `- ${link(r.name, r.path)} → \`${r.branch || '?'}\`${r.pr ? ` (PR ${r.pr})` : ''}`),
    `- ${link('Pasta da demanda', s.dir)}`,
  ]
  return (
    <Box flexDirection="column" gap={1}>
      <Box flexDirection="column">
        <Text bold color={next.you ? 'warning' : undefined}>
          {headline}
        </Text>
        <Markdown text={`**Próximo passo:** ${next.text}`} />
        {s.note && <Text dimColor>Nota do orquestrador: {s.note}</Text>}
      </Box>
      <Text>{progress}</Text>
      <Markdown text={summary.map(l => `- ${l}`).join('\n')} />
      {(attention.length > 0 || atLimit(s, limit)) && (
        <Box flexDirection="column">
          <Text bold color="warning">
            Atenção
          </Text>
          {attention.map(a => (
            <Text key={`att-${a}`} color="warning">
              ⚠ {a}
            </Text>
          ))}
          {atLimit(s, limit) && (
            <Box gap={1}>
              <Text color="warning">
                ⚠ O laço de {s.roundKind} chegou ao limite ({s.round} de {limit}).
              </Text>
              <Button key="extra-round" label="Liberar +1 rodada" onPress={() => act.extraRound()} />
            </Box>
          )}
        </Box>
      )}
      <Box flexDirection="column">
        <Text bold>Agentes</Text>
        {v.running.length === 0 && <Text dimColor>Nenhum rodando agora.</Text>}
        {v.running.map(r => (
          <Text key={`run-${r.key}`} color="suggestion">
            ▶ {r.agent} · {r.label} · {secs(Math.max(0, Math.round((v.now - r.since) / 1000)))}
          </Text>
        ))}
        {last.map((d, i) => (
          <Text key={`last-${i}`} dimColor>
            {i === 0 ? 'Último: ' : '        '}
            {d.agent} · {d.label} · {stateLabel(d.state)} · {secs(d.seconds)} · {compact(d.tokens)} tokens
          </Text>
        ))}
      </Box>
      <Markdown text={`**Onde está**\n${where.join('\n')}`} />
    </Box>
  )
}

type Group = { key: string; n: number; tokens: number; seconds: number; cost: number }

/** "claude-opus-5-5" e "opus" são o mesmo modelo na tabela; outros nomes (gpt-…) ficam como estão. */
const modelName = (m: string) => /opus|sonnet|haiku|fable/i.exec(m)?.[0]?.toLowerCase() ?? (m || '—')

function groupBy(list: Delegation[], key: (d: Delegation) => string): Group[] {
  const out = new Map<string, Group>()
  for (const d of list) {
    const k = key(d) || '—'
    const g = out.get(k) ?? { key: k, n: 0, tokens: 0, seconds: 0, cost: 0 }
    out.set(k, { key: k, n: g.n + 1, tokens: g.tokens + d.tokens, seconds: g.seconds + d.seconds, cost: g.cost + (d.cost ?? 0) })
  }
  return [...out.values()]
}

// Métricas: tudo o que foi medido, para análise — consumo por agente, modelo, nível e dia, retrabalho, cada
// delegação e todos os artefatos.
function Metrics(ui: UI, v: ViewState) {
  const { Box, Text, Markdown } = ui
  const s = v.snap
  const d = s.delegations
  const total = s.tokens
  const seconds = d.reduce((n, x) => n + x.seconds, 0)
  const priced = d.filter(x => x.cost !== null)
  const usd = (n: number) => `US$ ${n.toFixed(2)}`
  const withCost = priced.length > 0
  const table = (head: string[], rows: string[][]) =>
    `| ${head.join(' | ')} |\n|${head.map(() => '---').join('|')}|\n${rows.map(r => `| ${r.map(cell).join(' | ')} |`).join('\n')}`
  const byTokens = (a: Group, b: Group) => b.tokens - a.tokens

  const totals = [
    `**${d.length}** delegações`,
    `**${compact(total)}** tokens (${pct(total, s.budget)}% do orçamento de ${s.level ?? 'padrao'}, ${compact(s.budget)})`,
    `**${secs(seconds)}** de agente`,
    withCost
      ? `**${usd(priced.reduce((n, x) => n + (x.cost ?? 0), 0))}** em ${priced.length} de ${d.length} delegações`
      : 'custo em US$ não informado (o subagente nativo do Claude só mede tokens)',
  ].join(' · ')

  const agents = groupBy(d, x => x.agent)
    .sort(byTokens)
    .map(g => [g.key, String(g.n), compact(g.tokens), `${pct(g.tokens, total)}%`, secs(g.seconds), compact(Math.round(g.tokens / g.n)), ...(withCost ? [usd(g.cost)] : [])])
  const models = groupBy(d, x => `${modelName(x.model)} · ${x.effort}`)
    .sort(byTokens)
    .map(g => [g.key, String(g.n), compact(g.tokens), `${pct(g.tokens, total)}%`, secs(g.seconds)])
  const levels = groupBy(d, x => x.level)
    .sort(byTokens)
    .map(g => [g.key, String(g.n), compact(g.tokens), `${pct(g.tokens, total)}%`])
  const days = groupBy(d, x => x.date).map(g => [g.key, String(g.n), compact(g.tokens), secs(g.seconds)])
  const results = groupBy(d, x => stateLabel(x.state))
    .sort((a, b) => b.n - a.n)
    .map(g => [g.key, String(g.n)])

  const back = s.timeline.filter(t => t.visits > 1).map(t => `${t.name} ${t.visits}×`)
  const round = (src: string) => Math.max(0, ...s.findings.filter(f => f.source === src).map(f => f.round))
  const rework = [
    back.length ? `**Fases que voltaram:** ${back.join(', ')}` : '**Fases que voltaram:** nenhuma',
    `**Rodadas de revisão:** plano ${round('plano') || '—'} · código ${round('revisão') || '—'}`,
    v.usage ? `**Contexto do orquestrador:** ${v.usage.percent}% (${compact(v.usage.tokens)} tokens)` : '',
    `**Código lido no chat do orquestrador:** ${v.codeReads}×`,
  ].filter(Boolean)

  const all = d
    .map((x, i) => [
      String(i + 1),
      x.date,
      x.agent,
      x.label,
      x.level,
      `${modelName(x.model)} · ${x.effort}`,
      stateLabel(x.state),
      String(x.tools),
      secs(x.seconds),
      compact(x.tokens),
      ...(withCost ? [x.cost === null ? '—' : usd(x.cost)] : []),
    ])
    .reverse()
  const files = Object.values(s.artifacts).reduce((n, f) => n + f.length, 0)
  const artifacts = Object.entries(s.artifacts).map(
    ([group, list]) => `- **${group}** (${list.length}): ${list.map(f => link(f, `${s.dir}/${f}`)).join(', ')}`,
  )
  const cost = withCost ? ['Custo'] : []
  return (
    <Box flexDirection="column" gap={1}>
      <Markdown text={totals} />
      {d.length === 0 && <Text dimColor>Nenhuma delegação registrada ainda.</Text>}
      {d.length > 0 && (
        <>
          <Markdown text={`**Por agente**\n\n${table(['Agente', 'Chamadas', 'Tokens', '%', 'Tempo', 'Média por chamada', ...cost], agents)}`} />
          <Markdown text={`**Por modelo e effort**\n\n${table(['Modelo · effort', 'Chamadas', 'Tokens', '%', 'Tempo'], models)}`} />
          <Markdown text={`**Por nível**\n\n${table(['Nível', 'Chamadas', 'Tokens', '%'], levels)}`} />
          <Markdown text={`**Por dia**\n\n${table(['Dia', 'Chamadas', 'Tokens', 'Tempo'], days)}`} />
          <Markdown text={`**Resultado das chamadas**\n\n${table(['Resultado', 'Chamadas'], results)}`} />
        </>
      )}
      <Markdown text={`**Retrabalho e orquestrador**\n${rework.map(l => `- ${l}`).join('\n')}`} />
      {all.length > 0 && (
        <Markdown
          text={`**Todas as delegações** (mais recente primeiro)\n\n${table(['#', 'Data', 'Agente', 'Rótulo', 'Nível', 'Modelo · effort', 'Resultado', 'Ferramentas', 'Tempo', 'Tokens', ...cost], all)}`}
        />
      )}
      <Markdown text={`**Artefatos** (${files} arquivos)\n${artifacts.join('\n') || '_nenhum ainda_'}`} />
    </Box>
  )
}

function Criteria(ui: UI, v: ViewState) {
  const { Box, Text, Markdown } = ui
  const c = v.snap.criteria
  if (!c.length) return <Text dimColor>Sem critérios de aceite ainda (eles vêm do plano ou do resumo do card).</Text>
  const mark = (r: string) =>
    r === 'atendido' ? '✅' : r === 'falhou' ? '❌' : r === 'pendente' ? '⏳ manual' : r === 'orquestrador' ? '🧭 orquestrador' : r === 'dúvida' ? '❓' : '—'
  const done = c.filter(x => x.result === 'atendido').length
  const rows = c.map(x => `| ${x.id} | ${cell(x.text)} | ${x.how.join(', ') || '—'} | ${mark(x.result)} | ${cell(x.evidence)} |`)
  return (
    <Box flexDirection="column" gap={1}>
      <Text>
        {done} de {c.length} critérios atendidos
      </Text>
      <Markdown text={`| CA | Critério | Como provar | Resultado | Evidência |\n|---|---|---|---|---|\n${rows.join('\n')}`} />
    </Box>
  )
}

function findingRows(list: Finding[]): string {
  return list
    .map(
      f =>
        `| ${SEV_MARK[f.severity ?? ''] ?? '·'} ${f.id} | ${f.severity ?? '—'} | ${cell(f.where || '—')} | ${cell(f.title)} | ${cell(f.status || '—')} | ${cell(f.triage || '—')} |`,
    )
    .join('\n')
}

function Review(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Markdown, Select, Button } = ui
  const all = v.snap.findings.filter(f => f.source !== 'plano')
  const plan = v.snap.findings.filter(f => f.source === 'plano')
  const rounds = [...new Set(all.map(f => f.round))].sort((a, b) => a - b)
  if (!rounds.length && !plan.length) return <Text dimColor>Ainda não houve revisão.</Text>
  const round = rounds.includes(v.reviewRound) ? v.reviewRound : (rounds.at(-1) ?? 0)
  const summary = rounds.map(r => {
    const of = all.filter(f => f.round === r)
    const count = (sev: string) => of.filter(f => f.severity === sev).length
    return `r${r}: ${count('CRITICO')} crít · ${count('IMPORTANTE')} imp · ${count('SUGESTAO')} sug`
  })
  const shown = all.filter(f => f.round === round && f.severity !== 'ELOGIO')
  const limit = v.snap.maxRetries + v.extraRounds
  return (
    <Box flexDirection="column" gap={1}>
      <Text dimColor>{summary.join('   ')}</Text>
      {rounds.length > 1 && (
        <Select
          key="review-round"
          label="Rodada"
          value={String(round)}
          options={rounds.map(r => ({ value: String(r), label: `Rodada ${r}` }))}
          onSelect={value => act.reviewRound(Number(value))}
        />
      )}
      <Text>
        Rodada {round}: {shown.filter(isOpen).length} aberto(s) de {shown.length}
      </Text>
      {shown.length > 0 && (
        <Markdown text={`| ID | Sev. | Onde | O quê | Status | Triagem |\n|---|---|---|---|---|---|\n${findingRows(shown)}`} />
      )}
      {plan.length > 0 && (
        <Markdown
          text={`**Revisão do plano**\n\n| ID | Sev. | Onde | O quê | Status | Triagem |\n|---|---|---|---|---|---|\n${findingRows(plan.filter(f => f.round === Math.max(...plan.map(p => p.round))))}`}
        />
      )}
      {v.snap.roundKind === 'revisão' && v.snap.round >= limit && (
        <Box gap={1}>
          <Text color="warning">
            Rodada {v.snap.round} de {limit}: novas rodadas estão travadas.
          </Text>
          <Button key="extra-round" label="Liberar +1 rodada" onPress={() => act.extraRound()} />
        </Box>
      )}
    </Box>
  )
}

function Diffs(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Select, Code, Button } = ui
  const s = v.snap
  const sources = [
    ...s.repos.map(r => ({ value: `repo:${r.path}`, label: `${r.name} — worktree${r.pr ? ` (PR ${r.pr})` : ''}` })),
    ...s.patches.map(p => ({ value: `patch:${p}`, label: p })),
  ]
  if (!sources.length) return <Text dimColor>Sem worktree nem patch nesta demanda.</Text>
  const d = v.diff
  const repoOf = d?.source.startsWith('repo:') ? s.repos.find(r => `repo:${r.path}` === d.source) : undefined
  return (
    <Box flexDirection="column" gap={1}>
      <Select
        key="diff-source"
        label="Diff de"
        value={d?.source ?? ''}
        options={sources}
        onSelect={value => act.diffSource(value)}
      />
      {d?.error && <Text color="error">{d.error}</Text>}
      {d && !d.error && (
        <>
          <Box gap={1}>
            <Text dimColor>{d.summary}</Text>
            {repoOf && v.canAppDiff && (
              <Button key="app-diff" label="Abrir no painel de diff do app" plain onPress={() => act.appDiff(repoOf.name)} />
            )}
          </Box>
          {d.files.length > 0 && (
            <Select
              key="diff-file"
              label="Arquivo"
              value={d.selected}
              options={d.files.map(f => ({
                value: f.path,
                label: `${f.change === 'novo' ? '+' : f.change === 'apagado' ? '−' : '~'} ${f.path}  (+${f.added} −${f.removed})`,
              }))}
              onSelect={value => act.diffFile(value)}
            />
          )}
          {d.hunks ? <Code source={d.hunks} format="diff" path={d.selected} /> : <Text dimColor>Escolha um arquivo.</Text>}
        </>
      )}
      {!d && <Text dimColor>Escolha de onde vem o diff.</Text>}
    </Box>
  )
}

function Manual(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Markdown, Input, Button } = ui
  const steps = v.snap.manual
  if (!steps.length) return <Text dimColor>Sem roteiro de teste manual (o QA grava roteiro-testes-&lt;id&gt;.md quando há passo manual).</Text>
  const next = steps.find(s => !s.result)
  const rows = steps.map(s => `| ${s.result || (s === next ? '▶' : '·')} ${s.id} | ${cell(s.step)} | ${cell(s.expected)} | ${cell(s.note)} |`)
  const key = next ? `evidencia-${next.id}` : ''
  return (
    <Box flexDirection="column" gap={1}>
      <Text>
        {steps.filter(s => s.result === '✅').length} ✅ · {steps.filter(s => s.result === '❌').length} ❌ ·{' '}
        {steps.filter(s => !s.result).length} pendente(s) — {v.snap.roteiro}
      </Text>
      <Markdown text={`| Passo | O que fazer | Esperado | Evidência |\n|---|---|---|---|\n${rows.join('\n')}`} />
      {next && (
        <Box flexDirection="column" gap={1}>
          <Text bold>
            Passo {next.id}: {next.step}
          </Text>
          <Text dimColor>Esperado: {next.expected}</Text>
          <Input
            key={key}
            label="Evidência"
            placeholder="o que aconteceu (sem segredo nem dado pessoal)"
            value={v.drafts[key] ?? ''}
            onInput={value => act.draft(key, value)}
            onSubmit={value => act.draft(key, value)}
          />
          <Box gap={1}>
            <Button key="manual-ok" label="✅ Passou" variant="primary" onPress={() => act.manualResult(next.id, true)} />
            <Button key="manual-fail" label="❌ Falhou" onPress={() => act.manualResult(next.id, false)} />
          </Box>
        </Box>
      )}
    </Box>
  )
}

function PrFindings(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Button, Select } = ui
  const list = v.snap.findings.filter(f => f.source !== 'plano' && f.severity !== 'ELOGIO')
  const round = Math.max(0, ...list.map(f => f.round))
  const shown = list.filter(f => f.round === round)
  if (!shown.length) return <Text dimColor>A revisão ainda não terminou.</Text>
  const chosen = shown.filter(f => v.publish[f.id] ?? (!f.published && f.severity !== 'DUVIDA' && f.severity !== 'SUGESTAO'))
  return (
    <Box flexDirection="column" gap={1}>
      <Text>
        Rodada {round}: {shown.length} achado(s) · {chosen.length} marcado(s) para publicar
      </Text>
      {shown.map(f => {
        const on = v.publish[f.id] ?? (!f.published && f.severity !== 'DUVIDA' && f.severity !== 'SUGESTAO')
        return (
          <Box key={`f-${f.id}`} flexDirection="column">
            <Box gap={1}>
              <Button
                key={`pub-${f.id}`}
                label={on ? '☑ publicar' : '☐ publicar'}
                plain
                onPress={() => act.togglePublish(f.id)}
              />
              <Text bold>
                {SEV_MARK[f.severity ?? ''] ?? '·'} {f.id} {f.severity ?? ''}
              </Text>
              <Text dimColor>{f.where}</Text>
              {f.published && <Text color="success">já publicado</Text>}
            </Box>
            <Text>{f.title}</Text>
            {f.triage && <Text dimColor>Triagem: {f.triage}</Text>}
            {f.comment && <Text dimColor>Comentário: {f.comment}</Text>}
          </Box>
        )
      })}
      <Select
        key="vote"
        label="Voto"
        value={v.vote}
        options={VOTES.map(o => ({ value: o.value, label: o.label }))}
        onSelect={value => act.vote(value)}
      />
      {v.snap.vote && <Text dimColor>Sugerido pelo revisor: {v.snap.vote}</Text>}
      <Button
        key="pr-decision"
        label="Levar a decisão ao prompt"
        variant="primary"
        onPress={() => act.sendPrDecision()}
      />
      <Text dimColor>A decisão vai para o prompt; publicar e votar só acontecem quando você enviar a mensagem.</Text>
    </Box>
  )
}

function Points(ui: UI, v: ViewState) {
  const { Box, Text, Markdown } = ui
  const p = v.snap.points
  if (!p.length) return <Text dimColor>Os pontos do card aparecem quando o explorador validar o card no código.</Text>
  const count = (re: RegExp) => p.filter(x => re.test(x.verdict)).length
  return (
    <Box flexDirection="column" gap={1}>
      <Text>
        {p.length} pontos · {count(/✅|confirm/i)} confirmados · {count(/⚠|diverg/i)} divergem · {count(/❓|não encontr/i)} não
        encontrados · {count(/🔗|outro sistema/i)} em outro sistema
      </Text>
      <Markdown
        text={`| # | Ponto | No código | Evidência |\n|---|---|---|---|\n${p.map(x => `| ${x.id} | ${cell(x.text)} | ${cell(x.verdict || '—')} | ${cell(x.evidence || '—')} |`).join('\n')}`}
      />
    </Box>
  )
}

function EstimateView(ui: UI, v: ViewState, act: Actions) {
  const { Box, Text, Markdown, Input, Button } = ui
  const e = v.snap.estimate
  if (!e) return <Text dimColor>A estimativa aparece quando o levantamento-&lt;id&gt;.md for gravado.</Text>
  return (
    <Box flexDirection="column" gap={1}>
      <Markdown
        text={[
          `**Story points:** ${e.sp || '?'}`,
          `**Horas:** ${e.hours || '?'}`,
          `**Complexidade:** ${e.complexity || '?'}`,
          `**Confiança:** ${e.confidence || '?'}`,
        ].join(' · ')}
      />
      <Text bold>Dúvidas ({v.snap.doubts.length})</Text>
      {v.snap.doubts.map(d => {
        const key = `duvida-${d.n}`
        return (
          <Box key={`d-${d.n}`} flexDirection="column">
            <Text>
              {d.n}. {d.question}
              {d.to ? ` (para: ${d.to})` : ''}
            </Text>
            {d.why && <Text dimColor>Por que importa: {d.why}</Text>}
            <Input
              key={key}
              label="Resposta"
              placeholder="se você já sabe a resposta, escreva e envie"
              value={v.drafts[key] ?? ''}
              onInput={value => act.draft(key, value)}
              onSubmit={() => act.answerDoubt(d.n)}
              submitLabel="Responder"
            />
          </Box>
        )
      })}
      <Button
        key="post-levantamento"
        label="Levar ao prompt: publicar o comentário no card"
        variant="primary"
        onPress={() => act.postLevantamento()}
      />
      <Text dimColor>Comentar no card é ação travada: a mensagem vai para o prompt e só vale quando você enviar.</Text>
    </Box>
  )
}

// ---------------------------------------------------------------------------------------------------------------
// Textos que os botões mandam ao orquestrador

export function prDecisionText(s: Snapshot, publish: Record<string, boolean>, vote: string): string {
  const list = s.findings.filter(f => f.source !== 'plano' && f.severity !== 'ELOGIO')
  const round = Math.max(0, ...list.map(f => f.round))
  const shown = list.filter(f => f.round === round)
  const on = (f: Finding) => publish[f.id] ?? (!f.published && f.severity !== 'DUVIDA' && f.severity !== 'SUGESTAO')
  const yes = shown.filter(on).map(f => f.id)
  const no = shown.filter(f => !on(f)).map(f => f.id)
  const label = VOTES.find(o => o.value === vote)?.label ?? vote
  return [
    `Revisão final da PR (${s.id}, rodada ${round}):`,
    `- Publicar: ${yes.join(', ') || 'nenhum'} (com o texto dos rascunhos como está).`,
    `- Não publicar: ${no.join(', ') || 'nenhum'}.`,
    `- Voto: ${label}.`,
    'Pode publicar e votar exatamente isso.',
  ].join('\n')
}

export function levantamentoText(s: Snapshot): string {
  return `OK: publique no card ${s.id} o comentário do levantamento (${s.levantamento}), como está no arquivo.`
}
