import { atom, read, update } from 'claude-code'
import type { BuiltinToolResults, EngineInterface, Register, TurnUsage } from 'claude-code'

import type { DiffView, ReviewFilter, Snapshot, VoteOption } from '../types'
import {
  CONTEXT_COMPACT,
  CONTEXT_WARN,
  LONG_WAIT,
  compact,
  demandIds,
  demandSetId,
  labelFor,
  parseDelegation,
  parseMaxRetries,
  parseState,
} from './aidw'
import { voteValue } from './artifacts'
import type { DemandFile, ExternalStep } from './artifacts'
import { diffSummary, splitDiff } from './diffs'
import type { DiffFile } from './diffs'
import { checkDelegation } from './guards'
import type { Runtime } from './guards'
import { redactBlocks } from './secrets'
import { buildSnapshot, stateNote, wanted } from './snapshot'
import { Band, Panel, diffSources, levantamentoText, prDecisionText, prTriageDecisionText, reviewDecisionText, tabFor } from './views'
import type { Actions, UI } from './views'

// Estado da sessão (o que a tela lê fica em $.state; uma recarga do módulo não o perde).
// Ligado só no modo orquestrador: a sessão está no state/sessions.json, que o guard do AiDW grava ao
// `/aidw:orquestrar` e `/aidw:levantamento` e apaga no `/aidw:sair` e no `/aidw:done`.
const active = atom({ plugin: 'aidw-mods', key: 'active' } as const, false)
const snap = atom({ plugin: 'aidw-mods', key: 'snap' } as const, null)
const running = atom({ plugin: 'aidw-mods', key: 'running' } as const, [])
const hidden = atom({ plugin: 'aidw-mods', key: 'hidden' } as const, false)
const tab = atom({ plugin: 'aidw-mods', key: 'tab' } as const, 'geral')
const tick = atom({ plugin: 'aidw-mods', key: 'tick' } as const, 0)
const extraRounds = atom({ plugin: 'aidw-mods', key: 'extraRounds' } as const, {})
const publish = atom({ plugin: 'aidw-mods', key: 'publish' } as const, {})
const vote = atom({ plugin: 'aidw-mods', key: 'vote' } as const, '')
const votes = atom({ plugin: 'aidw-mods', key: 'votes' } as const, {})
const drafts = atom({ plugin: 'aidw-mods', key: 'drafts' } as const, {})
const diff = atom({ plugin: 'aidw-mods', key: 'diff' } as const, null)
const reviewRound = atom({ plugin: 'aidw-mods', key: 'reviewRound' } as const, 0)
const usage = atom({ plugin: 'aidw-mods', key: 'usage' } as const, null)
const codeReads = atom({ plugin: 'aidw-mods', key: 'codeReads' } as const, 0)
const warned = atom({ plugin: 'aidw-mods', key: 'warned' } as const, {})
const lastStep = atom({ plugin: 'aidw-mods', key: 'lastStep' } as const, {})
const reviewFile = atom({ plugin: 'aidw-mods', key: 'reviewFile' } as const, '')
const decisionTab = atom({ plugin: 'aidw-mods', key: 'decisionTab' } as const, '')
const NO_FILTER: ReviewFilter = { severities: [], sources: [], statuses: [], open: false }
const reviewFilter = atom({ plugin: 'aidw-mods', key: 'reviewFilter' } as const, NO_FILTER)
const decisions = atom({ plugin: 'aidw-mods', key: 'decisions' } as const, {})
const expanded = atom({ plugin: 'aidw-mods', key: 'expanded' } as const, {})

const PANE = 'aidw'
// Etapas em que um ajuste de teste pode estar aplicado (ou já devia ter saído).
const MARK_STEPS = new Set(['TEST', 'TEST_ADJUST', 'ORCHESTRATOR_TEST', 'PREPARE_REVIEW', 'REVIEW', 'MANUAL_TEST', 'DOCS', 'FINAL_REVIEW'])
const CODE_FILE = /\.(cs|ts|tsx|js|jsx|mjs|vue|py|java|kt|go|rs|cpp|c|h|vb|sql|xaml|cshtml|razor|html|scss|css)$/i
const USER_ORIGINS = new Set(['composer', 'bridge', 'sdk'])

type Pending = { agent: string; level: string | null; label: string; demand: string; tools: number }

let root = 'C:/AiDW'
let python = 'python'
// Subagentes em segundo plano: a métrica chega no turn.complete deles, pelo agentId.
const background = new Map<string, Pending>()
// As últimas mensagens do usuário (a trava de `model` confere se ele pediu outro modelo).
const userPrompts: string[] = []
// Diffs já calculados, por fonte (o estado guarda só o arquivo aberto).
const diffCache = new Map<string, DiffFile[]>()
let kbCache: { name: string; folder: string; path: string }[] | null = null

const norm = (p: string) => p.replace(/\\/g, '/').replace(/\/+$/, '')
const under = (path: string, dir: string) => norm(path).toLowerCase().startsWith(`${norm(dir).toLowerCase()}/`)

// ---------------------------------------------------------------------------------------------------------------
// Disco e AiDW

async function runtimeJson($: EngineInterface): Promise<Record<string, unknown>> {
  try {
    return JSON.parse(await $.fs.read(`${root}/.aidw/runtime.json`)) as Record<string, unknown>
  } catch {
    return {}
  }
}

async function stateDir($: EngineInterface): Promise<string | null> {
  const r = await runtimeJson($)
  return typeof r.state_dir === 'string' ? norm(r.state_dir) : null
}

/** A tabela de níveis e os agentes ligados, para as travas da delegação. */
async function loadRuntime($: EngineInterface): Promise<Runtime | null> {
  const r = await runtimeJson($)
  const levels = r.levels as Runtime['levels'] | undefined
  if (!levels) return null
  const agents = Object.values((r.agents ?? {}) as Record<string, { name: string; enabled: boolean }>)
    .filter(a => a.enabled && a.name !== 'orquestrador')
    .map(a => a.name)
  return {
    levels,
    defaultLevel: String(r.default_level ?? 'padrao'),
    maxRetries: Number(r.max_retries ?? 3),
    maxRetriesPlan: Number(r.max_retries_plan ?? r.max_retries ?? 3),
    agents,
  }
}

/** Relê a demanda do disco e redesenha a faixa e o painel. */
async function refresh($: EngineInterface, dir?: string): Promise<void> {
  const target = dir ? norm(dir) : (await read($, snap))?.dir
  if (!target) return
  let demand: DemandFile
  try {
    demand = JSON.parse(await $.fs.read(`${target}/demand.json`)) as DemandFile
  } catch {
    return
  }
  const files = (await $.fs.list(target).catch(() => [])).filter(f => f.kind === 'file').map(f => f.name)
  const texts: Record<string, string> = {}
  for (const f of wanted(files)) texts[f] = await $.fs.read(`${target}/${f}`).catch(() => '')
  const r = await runtimeJson($)
  const maxRetries =
    typeof r.max_retries === 'number'
      ? r.max_retries
      : parseMaxRetries(await $.fs.read(`${root}/orchestrator/config/routing.toml`).catch(() => ''))
  const maxRetriesPlan = typeof r.max_retries_plan === 'number' ? r.max_retries_plan : maxRetries
  const externalSteps = Array.isArray(r.external_steps) ? (r.external_steps as ExternalStep[]) : []
  const scale = Array.isArray(r.votes) ? (r.votes as VoteOption[]) : []
  const next = buildSnapshot({ dir: target, demand, files, texts, maxRetries, maxRetriesPlan, externalSteps, votes: scale })
  if (next.kind === 'desenvolvimento' && MARK_STEPS.has(next.step)) next.testMarks = await testMarks($, next)
  const before = await read($, snap)
  await update($, snap, () => next)
  if (before?.id !== next.id) {
    await update($, vote, () => voteValue(next.vote))
    await update($, votes, () => ({}))
    await update($, publish, () => ({}))
    await update($, diff, () => null)
    await update($, reviewRound, () => next.round)
    await update($, reviewFile, () => '')
    await update($, decisionTab, () => '')
    await update($, decisions, () => ({}))
  }
  if (tabFor(next.kind, await read($, tab)) === 'diffs') await ensureDiff($, next)
}

/** Diffs abre com o diff da primeira fonte já carregado; o guardado só vale se a fonte é desta demanda. */
async function ensureDiff($: EngineInterface, s: Snapshot): Promise<void> {
  const sources = diffSources(s)
  const current = await read($, diff)
  if (sources[0] && !sources.some(x => x.value === current?.source)) await showDiff($, sources[0].value)
}

/** As marcas AIDW-TESTE de cada worktree: ajustes de teste que ainda precisam sair antes da revisão final. */
async function testMarks($: EngineInterface, s: Snapshot): Promise<Record<string, number>> {
  const out: Record<string, number> = {}
  for (const repo of s.repos) {
    const ran = await $.process
      .run(['git', '-C', repo.path, 'grep', '-c', '-I', '-F', '--untracked', 'AIDW-TESTE'], { timeoutMs: 15_000 })
      .catch(() => null)
    if (!ran) continue
    out[repo.name] = ran.exitCode === 0
      ? ran.stdout.split('\n').reduce((n, line) => n + Number(/:(\d+)$/.exec(line.trim())?.[1] ?? 0), 0)
      : 0
  }
  return out
}

/** A demanda da pasta da sessão: o primeiro trecho do caminho que é uma demanda do contexto ativo. */
async function fromCwd($: EngineInterface, cwd: string): Promise<string | null> {
  const dir = await stateDir($)
  if (!dir) return null
  for (const part of norm(cwd).split('/')) {
    if (part && (await $.fs.exists(`${dir}/${part}/demand.json`))) return `${dir}/${part}`
  }
  return null
}

/**
 * A demanda pelo que foi passado ao `/aidw:orquestrar` (`us-116332`, ou só o número), para a sessão aberta fora da
 * pasta da demanda (chat sem pasta, ou na pasta do contexto).
 */
async function fromArgument($: EngineInterface, argument: string): Promise<string | null> {
  const dir = await stateDir($)
  if (!dir) return null
  const ids = demandIds(argument)
  for (const id of ids.named) if (await $.fs.exists(`${dir}/${id}/demand.json`)) return `${dir}/${id}`
  if (!ids.numbers.length) return null
  const folders = (await $.fs.list(dir).catch(() => [])).filter(f => f.kind === 'dir').map(f => f.name)
  for (const n of ids.numbers) {
    const hit = folders.find(f => f.endsWith(`-${n}`))
    if (hit && (await $.fs.exists(`${dir}/${hit}/demand.json`))) return `${dir}/${hit}`
  }
  return null
}

/** Confere se esta sessão está no modo orquestrador; ao entrar, acha a demanda e abre o painel. */
async function checkActive($: EngineInterface): Promise<boolean> {
  let on = false
  let argument = ''
  try {
    const sessions = JSON.parse(await $.fs.read(`${root}/state/sessions.json`)) as Record<string, { argument?: string }>
    const id = await $.session.id()
    on = Object.prototype.hasOwnProperty.call(sessions, id)
    argument = String(sessions[id]?.argument ?? '')
  } catch {
    on = false
  }
  const was = await read($, active)
  if (on !== was) await update($, active, () => on)
  if (on && !(await read($, snap))) {
    const dir = (await fromCwd($, await $.session.cwd())) ?? (await fromArgument($, argument))
    if (dir) await refresh($, dir)
  }
  if (on && !was) {
    await measure($)
    if (await panelOn($)) await openPanel($, false)
  }
  if (!on && was) await $.ui.close({ id: PANE }).catch(() => undefined)
  return on
}

/** O painel vale em todo contexto, menos no que o desliga (`[mods] panel = false`); a faixa e o resto do mod, sempre. */
async function panelOn($: EngineInterface): Promise<boolean> {
  return (await runtimeJson($)).panel !== false
}

async function openPanel($: EngineInterface, asked: boolean): Promise<void> {
  const s = await read($, snap)
  const opened = await $.ui.open({ id: PANE, title: s ? `AiDW — ${s.id}` : 'AiDW' })
  if (asked && !opened.isPlaced) $.ui.toast(`AiDW: o painel não coube (${opened.reason}); alargue a janela`)
}

/** `aidw.py demand set <id> --step X`: a etapa mudou (ou a demanda é outra). */
async function afterShell($: EngineInterface, command: string): Promise<void> {
  const id = demandSetId(command)
  if (!id) return
  const dir = await stateDir($)
  if (dir) await refresh($, `${dir}/${id}`)
}

/** Grava a linha no metricas.md pelo próprio `aidw.py record` e devolve o header + resumo que ele imprime. */
async function record(
  $: EngineInterface,
  p: Pending,
  state: string | null,
  tokens: number,
  tools: number,
  ms: number,
): Promise<string | null> {
  const argv = [
    python, `${root}/aidw.py`, 'record',
    '--agent', p.agent, '--label', p.label, '--demand', p.demand,
    '--tokens', String(tokens), '--tool-uses', String(tools), '--duration-ms', String(Math.round(ms)),
    ...(p.level ? ['--level', p.level] : []),
    ...(state ? ['--state', state] : []),
  ]
  try {
    const ran = await $.process.run(argv, { cwd: root, timeoutMs: 60_000 })
    await refresh($, p.demand)
    const out = JSON.parse(ran.stdout) as { header?: string; resumo?: string }
    return out.header ? `${out.header}\n${out.resumo ?? ''}` : null
  } catch {
    return null
  }
}

function notice(header: string | null, p: Pending): string {
  return header
    ? 'AiDW: delegação registrada no metricas.md pelo mod aidw-mods (não rode `aidw.py record` para ela). ' +
        `Abra o resultado com estas duas linhas, ao pé da letra:\n${header}`
    : `AiDW: o mod aidw-mods não conseguiu registrar esta delegação (${p.label}); rode \`aidw.py record\` você mesmo.`
}

/** Um aviso só uma vez por chave (orçamento, contexto, espera). */
async function warnOnce($: EngineInterface, key: string, text: string): Promise<void> {
  const seen = await read($, warned)
  if (seen[key]) return
  await update($, warned, w => ({ ...w, [key]: true }))
  $.ui.toast(text, { timeoutMs: 10_000 })
}

/** O contexto (em tokens) e as janelas de uso do plano (5h, 7d) para a faixa. */
async function measure($: EngineInterface): Promise<number | null> {
  try {
    const u = await $.session.usage()
    const tokens = u.context.tokens ?? 0
    const limits = (u.rateLimits ?? [])
      .filter(l => l.kind === 'five_hour' || l.kind === 'seven_day')
      .map(l => ({ kind: l.kind === 'five_hour' ? ('5h' as const) : ('7d' as const), percent: l.percentUsed, resetsAt: l.resetsAt ?? '' }))
    await update($, usage, () => ({ percent: Math.round(u.context.percent ?? 0), tokens, limits }))
    return tokens
  } catch {
    return null // sem uso medido nesta superfície
  }
}

/** Soma o turno do chat principal ao metricas-orquestrador.md da demanda (`aidw.py record-orchestrator`). */
async function recordTurn($: EngineInterface, s: Snapshot, u: TurnUsage, ms: number): Promise<void> {
  const argv = [
    python, `${root}/aidw.py`, 'record-orchestrator', '--demand', s.dir, '--session', await $.session.id(),
    '--model', u.model, '--input', String(u.input_tokens), '--cache-write', String(u.cache_creation_input_tokens),
    '--cache-read', String(u.cache_read_input_tokens), '--output', String(u.output_tokens), '--duration-ms', String(Math.round(ms)),
  ]
  await $.process.run(argv, { cwd: root, timeoutMs: 30_000 }).catch(() => null)
}

/**
 * Compacta a conversa entre turnos: antes de uma espera longa por você (na volta, depois de 1h, o cache expirou e o
 * contexto inteiro seria regravado) ou na troca de etapa (cada ação relê a conversa inteira; o que passou está nos
 * arquivos). Se você já mandou outra mensagem, não compacta.
 */
async function compactBetweenTurns($: EngineInterface, id: string, step: string, before: number, wait: boolean): Promise<void> {
  try {
    const r = await $.session.compact({
      instructions: wait
        ? `Compactação do AiDW antes de esperar o usuário na etapa ${step} da demanda ${id}. Mantenha o que está com ele ` +
          '(a pergunta, a aprovação ou o pacote, com as opções e a recomendação) e as decisões ainda não gravadas; o resto ' +
          'está nos arquivos da pasta da demanda.'
        : `Compactação do AiDW na troca de etapa da demanda ${id} (agora ${step}). Mantenha a próxima ação, os agentes ` +
          'em andamento (o que cada um faz e o arquivo da tarefa) e as decisões ainda não gravadas; o resto está nos ' +
          'arquivos da pasta da demanda.',
    })
    if (r.skip !== undefined) return
    const after = r.tokensAfter ? ` → ${compact(r.tokensAfter)}` : ''
    const why = wait ? 'antes de esperar você' : `na troca de etapa (${step})`
    $.ui.toast(`AiDW: contexto compactado ${why} (${compact(before)}${after} tokens)`, { timeoutMs: 8_000 })
  } catch {
    // um turno começou antes: a compactação fica para a próxima espera ou troca de etapa
  }
}

/** O fim de um turno do orquestrador: métrica do turno, contexto e espera por você. */
async function endOfTurn($: EngineInterface, e: { usage?: TurnUsage; durationMs: number }): Promise<void> {
  await refresh($)
  const before = await read($, snap)
  if (before && e.usage) {
    await recordTurn($, before, e.usage, e.durationMs)
    await refresh($)
  }
  const s = await read($, snap)
  const tokens = await measure($)
  if (!s) return
  const previous = (await read($, lastStep))[s.id]
  if (previous !== s.step) await update($, lastStep, m => ({ ...m, [s.id]: s.step }))
  const stepChanged = previous !== undefined && previous !== s.step
  if (tokens !== null) {
    const key = `ctx:${s.id}`
    const wait = LONG_WAIT.has(s.step) || s.progress.stages.some(x => x.state === 'com-time')
    if (tokens < CONTEXT_COMPACT) {
      if ((await read($, warned))[key]) await update($, warned, w => ({ ...w, [key]: false })) // compactou: avisa de novo
    } else if (wait || stepChanged) {
      const once = `compact:${s.id}:${s.step}:${s.delegations.length}` // uma vez por espera ou troca de etapa
      if (!(await read($, warned))[once]) {
        await update($, warned, w => ({ ...w, [once]: true }))
        $.clock.after(1_000, () => void compactBetweenTurns($, s.id, s.step, tokens, wait))
      }
    } else if (tokens >= CONTEXT_WARN) {
      await warnOnce(
        $,
        key,
        `AiDW: o contexto do orquestrador está em ${compact(tokens)} tokens e cada ação relê tudo — ao virar de etapa, ` +
          'rode /compact (o estado da demanda está nos arquivos)',
      )
    }
  }
  if (s.waiting) await warnOnce($, `wait:${s.id}:${s.step}:${s.delegations.length}`, `AiDW: ${s.id} espera você — ${s.waiting}`)
}

/** Calcula (ou pega do cache) o diff de uma fonte: o worktree contra a base, ou um .patch da pasta. */
async function diffFiles($: EngineInterface, s: Snapshot, source: string): Promise<{ files: DiffFile[]; error: string }> {
  const cached = diffCache.get(source)
  if (cached) return { files: cached, error: '' }
  let text = ''
  if (source.startsWith('patch:')) {
    text = await $.fs.read(`${s.dir}/${source.slice(6)}`).catch(() => '')
    if (!text) return { files: [], error: `não consegui ler ${source.slice(6)}` }
  } else {
    const repo = s.repos.find(r => `repo:${r.path}` === source)
    if (!repo) return { files: [], error: 'repositório não encontrado na demanda' }
    const range = repo.pr && repo.source ? [`${repo.base}...${repo.source}`] : [repo.base || 'HEAD']
    const ran = await $.process
      .run(['git', '-C', repo.path, 'diff', '--no-color', '--no-ext-diff', ...range], { timeoutMs: 30_000 })
      .catch((err: unknown) => ({ exitCode: 1, stdout: '', stderr: String(err) }))
    if (ran.exitCode !== 0) return { files: [], error: `git diff falhou: ${ran.stderr.slice(0, 200)}` }
    text = ran.stdout
  }
  const files = splitDiff(text)
  diffCache.set(source, files)
  return { files, error: '' }
}

async function showDiff($: EngineInterface, source: string, file?: string): Promise<void> {
  const s = await read($, snap)
  if (!s) return
  if (!file) diffCache.delete(source) // escolher a fonte de novo relê o diff
  const { files, error } = await diffFiles($, s, source)
  const selected = file ?? files[0]?.path ?? ''
  const view: DiffView = {
    source,
    files: files.map(f => ({ path: f.path, change: f.change, added: f.added, removed: f.removed })),
    selected,
    hunks: files.find(f => f.path === selected)?.hunks ?? '',
    summary: error ? '' : diffSummary(files),
    error,
  }
  await update($, diff, () => view)
}

/** As notas da base de conhecimento do contexto ativo (para `[[nota]]` no prompt). */
async function kbNotes($: EngineInterface): Promise<{ name: string; folder: string; path: string }[]> {
  if (kbCache) return kbCache
  const r = await runtimeJson($)
  const base = `${root}/contexts/${String(r.context ?? '')}/conhecimento`
  const out: { name: string; folder: string; path: string }[] = []
  for (const dir of await $.fs.list(base).catch(() => [])) {
    if (dir.kind !== 'dir') continue
    for (const f of await $.fs.list(`${base}/${dir.name}`).catch(() => [])) {
      if (f.kind === 'file' && f.name.endsWith('.md')) {
        out.push({ name: f.name.slice(0, -3), folder: dir.name, path: `${base}/${dir.name}/${f.name}` })
      }
    }
  }
  kbCache = out
  return out
}

/** O texto das notas citadas como `[[nome]]`, para ir junto da mensagem. */
async function kbContext($: EngineInterface, text: string): Promise<string[]> {
  const names = [...new Set([...text.matchAll(/\[\[([a-z0-9][\w-]*)\]\]/gi)].map(m => (m[1] ?? '').toLowerCase()))].slice(0, 3)
  if (!names.length) return []
  const notes = await kbNotes($)
  const out: string[] = []
  for (const name of names) {
    const note = notes.find(n => n.name.toLowerCase() === name)
    if (!note) continue
    const body = await $.fs.read(note.path).catch(() => '')
    if (body) out.push(`Nota [[${note.name}]] da base de conhecimento (${note.path}):\n${body.slice(0, 6000)}`)
  }
  return out
}

/** O código que o orquestrador leu no próprio chat (fora da pasta do AiDW): conta e devolve o aviso. */
async function codeRead($: EngineInterface, path: string): Promise<string | null> {
  if (!path || under(path, root) || !CODE_FILE.test(path)) return null
  const n = (await read($, codeReads)) + 1
  await update($, codeReads, () => n)
  return (
    `AiDW: o orquestrador leu código no próprio chat (${n}ª vez nesta sessão). Esse texto fica no contexto até o ` +
    'fim da demanda: para planejar ou entender, delegue ao explorador. Se é uma verificação pontual de premissa ' +
    '(skill verificar-premissa), siga.'
  )
}

/** Anda o relógio do painel enquanto há agente rodando. */
async function tickRunning($: EngineInterface): Promise<void> {
  if ((await read($, running)).length) await update($, tick, n => n + 1)
}

// ---------------------------------------------------------------------------------------------------------------

export const register: Register = (on, options) => {
  root = norm(String(options.aidwRoot ?? 'C:/AiDW'))
  python = String(options.python ?? 'python')

  on('session.start', async ($, e, next) => {
    await checkActive($)
    const panel = await panelOn($)
    for (const command of [
      { name: 'aidw-faixa', description: 'Mostra ou esconde a faixa da demanda do AiDW' },
      ...(panel ? [{ name: 'aidw-painel', description: 'Abre o painel do AiDW (geral, critérios, revisão, diffs, métricas…)', argumentHint: '[aba]' }] : []),
      { name: 'aidw-rodada', description: 'Libera mais uma rodada no laço de revisão travado pelo max_retries' },
    ]) {
      await $.command.register(command).catch(() => undefined)
    }
    // o tempo dos agentes rodando anda a cada 5 s
    $.clock.every(5_000, () => {
      void tickRunning($)
    })
    return next(e)
  })

  on('prompt.submit', async ($, e, next) => {
    if (USER_ORIGINS.has(e.origin.kind)) {
      userPrompts.push(e.text)
      if (userPrompts.length > 8) userPrompts.shift()
    }
    const notes = (await read($, active)) ? await kbContext($, e.text) : []
    const ran = await next(notes.length ? { ...e, context: [...(e.context ?? []), ...notes] } : e)
    await checkActive($)
    return ran
  })

  on('command.run', { command: 'aidw-faixa' }, async $ => {
    const now = !(await read($, hidden))
    await update($, hidden, () => now)
    return { text: now ? 'Faixa do AiDW escondida.' : 'Faixa do AiDW visível.' }
  })

  on('command.run', { command: 'aidw-painel' }, async ($, e) => {
    if (!(await panelOn($))) return { text: 'AiDW: o painel está desligado neste contexto (`[mods] panel = false` no context.toml; tire a linha para ligar).' }
    const s = await read($, snap)
    if (!s) return { text: 'AiDW: nenhuma demanda nesta sessão (chame /aidw:orquestrar).' }
    if (e.args.trim()) await update($, tab, () => tabFor(s.kind, e.args.trim().toLowerCase()))
    await openPanel($, true)
    return { text: `Painel do AiDW aberto (${s.id}).` }
  })

  on('command.run', { command: 'aidw-rodada' }, async $ => {
    const s = await read($, snap)
    if (!s) return { text: 'AiDW: nenhuma demanda nesta sessão.' }
    const n = ((await read($, extraRounds))[s.id] ?? 0) + 1
    await update($, extraRounds, x => ({ ...x, [s.id]: n }))
    return { text: `AiDW: ${n} rodada(s) extra(s) liberada(s) para ${s.id} (limite agora ${s.maxRetries + n}).` }
  })

  // Travas da delegação e registro da métrica.
  on('tool.call', { tool: 'Agent' }, async ($, e, next) => {
    const d = parseDelegation(e.prompt)
    const isOn = await read($, active)
    if (isOn) {
      const rt = await loadRuntime($)
      const s = await read($, snap)
      if (rt) {
        const why = checkDelegation({
          subagentType: e.subagent_type ?? 'general-purpose',
          prompt: e.prompt,
          model: e.model,
          runtime: rt,
          userPrompts,
          step: s?.step ?? null,
          round: s?.round ?? 0,
          roundKind: s?.roundKind ?? null,
          extraRounds: s ? ((await read($, extraRounds))[s.id] ?? 0) : 0,
          kind: s?.kind ?? null,
        })
        if (why) return { deny: why }
      }
    }
    if (!d || !isOn) return next(e)
    const agent = e.subagent_type ?? 'general-purpose'
    const p: Pending = { agent, level: d.level, label: labelFor(d.task, agent, e.description), demand: d.demand, tools: 0 }
    const key = e.tool_use_id
    const since = await $.clock.now()
    await update($, running, list => [...list, { key, agent: agent.split(':').pop() ?? agent, label: p.label, since }])
    if ((await read($, snap))?.dir !== norm(d.demand)) await refresh($, d.demand)

    const ran = await next(e)
    const result = ran.result as BuiltinToolResults['Agent'] | undefined
    if (ran.deny !== undefined || ran.isError || !result) {
      await update($, running, list => list.filter(r => r.key !== key))
      return ran
    }
    if (result.status === 'async_launched') {
      const id = result.agentId
      background.set(id, p)
      await update($, running, list => list.map(r => (r.key === key ? { ...r, key: id } : r)))
      return ran
    }
    await update($, running, list => list.filter(r => r.key !== key))
    if (result.status !== 'completed') return ran

    const text = result.content.map(c => c.text).join('\n')
    const header = await record($, p, parseState(text), result.totalTokens, result.totalToolUseCount, result.totalDurationMs)
    return { ...ran, context: [...(ran.context ?? []), notice(header, p)] }
  })

  // Ferramentas de um subagente em segundo plano, para a coluna de chamadas do metricas.md.
  on('tool.call', async ($, e, next) => {
    const p = e.agentId ? background.get(e.agentId) : undefined
    if (p) p.tools += 1
    return next(e)
  })

  // Economia: o orquestrador lendo código no próprio chat.
  on('tool.call', { tool: 'Read' }, async ($, e, next) => {
    const ran = await next(e)
    if (ran.deny !== undefined || e.agentId || !(await read($, active))) return ran
    const warn = await codeRead($, e.file_path)
    return warn ? { ...ran, context: [...(ran.context ?? []), warn] } : ran
  })

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const ran = await next(e)
    await afterShell($, e.command)
    return ran
  })

  on('tool.call', { tool: 'PowerShell' }, async ($, e, next) => {
    const ran = await next(e)
    await afterShell($, e.command)
    return ran
  })

  on('turn.complete', async ($, e, next) => {
    const id = e.agentId
    const p = id ? background.get(id) : undefined
    if (id && p) {
      background.delete(id)
      await update($, running, list => list.filter(r => r.key !== id))
      const u = e.usage
      const tokens = u ? u.input_tokens + u.output_tokens + u.cache_creation_input_tokens + u.cache_read_input_tokens : 0
      const state = parseState(e.answer)
      const header = await record($, p, state, tokens, p.tools, e.durationMs)
      await $.session.append({ message: { type: 'user', content: [{ type: 'text', text: notice(header, p) }] } })
      $.ui.toast(`AiDW: ${p.agent.split(':').pop()} (${p.label}) terminou${state ? ` — ${state}` : ''}`, { timeoutMs: 8_000 })
    } else if (!id && (await read($, active))) {
      await endOfTurn($, e)
    }
    return next(e)
  })

  // Depois de uma compactação, o estado da demanda volta ao contexto.
  on('session.compact', async ($, e, next) => {
    const ran = await next(e)
    if (e.agentId || !(await read($, active))) return ran
    await refresh($)
    const s = await read($, snap)
    if (s) await $.session.append({ message: { type: 'user', content: [{ type: 'text', text: stateNote(s) }] } })
    return ran
  })

  // Filtro de segredos: nenhuma linha da conversa (do orquestrador ou dos agentes) leva o valor de um segredo.
  on('session.append', async ($, e, next) => {
    if (!(await read($, active))) return next(e)
    const r = redactBlocks(e.message.content)
    if (!r.hits.length) return next(e)
    $.ui.status(`AiDW: ${r.hits.length} segredo(s) ocultado(s) na conversa (${r.hits.slice(0, 3).join(', ')})`)
    return next({ ...e, message: { ...e.message, content: r.content } })
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const s = await read($, snap)
    if (e.props.hasSurvey || !s || s.step === 'DONE' || !(await read($, active)) || (await read($, hidden))) {
      return next(e)
    }
    const ui = $.ui.resolve(e) as unknown as UI
    await read($, tick)
    return Band(ui, s, await read($, running), await read($, usage), await $.clock.now())
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const ui = $.ui.resolve(e) as unknown as UI
    const s = await read($, snap)
    if (!(await panelOn($))) {
      const { Text } = ui
      return <Text dimColor>O painel do AiDW está desligado neste contexto.</Text>
    }
    if (!s) {
      const { Text } = ui
      return <Text dimColor>Nenhuma demanda nesta sessão. Chame /aidw:orquestrar ou /aidw:levantamento.</Text>
    }
    await read($, tick)
    const fill = async (text: string, toast: string) => {
      await $.prompt.fill({ text })
      $.ui.toast(toast)
    }
    const toggle = (list: string[], value: string) => (list.includes(value) ? list.filter(x => x !== value) : [...list, value])
    const act: Actions = {
      tab: t =>
        void (async () => {
          await update($, tab, () => t)
          if (t === 'diffs') await ensureDiff($, s)
        })(),
      refresh: () => void refresh($),
      extraRound: () => void update($, extraRounds, x => ({ ...x, [s.id]: (x[s.id] ?? 0) + 1 })),
      reviewFile: f => void update($, reviewFile, () => f),
      decisionTab: t => void update($, decisionTab, () => t),
      decide: (key, value) =>
        void update($, decisions, x => {
          const out = { ...x }
          if (out[key] === value) delete out[key]
          else out[key] = value
          return out
        }),
      toggleFilter: (kind, value) => void update($, reviewFilter, f => ({ ...f, [kind]: toggle(f[kind], value) })),
      toggleFilters: () => void update($, reviewFilter, f => ({ ...f, open: !f.open })),
      sendReviewDecisions: () =>
        void (async () => {
          await fill(reviewDecisionText(s, await read($, decisions)), 'AiDW: as decisões estão no prompt; revise e envie')
          await update($, decisions, () => ({}))
        })(),
      togglePublish: (id, value) =>
        void update($, publish, x => {
          const out = { ...x }
          if (out[id] === value) delete out[id]
          else out[id] = value
          return out
        }),
      vote: value => void update($, vote, () => value),
      votePr: (pr, value) => void update($, votes, x => ({ ...x, [pr]: value })),
      sendPrDecision: () =>
        void (async () => {
          const text = s.prTriage
            ? prTriageDecisionText(s, await read($, publish), await read($, votes), await read($, drafts))
            : prDecisionText(s, await read($, publish), await read($, vote), await read($, drafts))
          await fill(text, 'AiDW: a decisão está no prompt; revise e envie')
        })(),
      adjustInChat: text => void fill(text, 'AiDW: o texto está no prompt; diga o que ajustar e envie'),
      draft: (key, value) => void update($, drafts, x => ({ ...x, [key]: value })),
      manualResult: (step, result) =>
        void (async () => {
          const evidence = (await read($, drafts))[`evidencia-${step}`] ?? ''
          const what = result === 'ok' ? '✅ passou' : result === 'fail' ? '❌ falhou' : '⏭ pulado'
          await $.prompt.submit({
            text: `Roteiro ${s.roteiro}, passo ${step}: ${what}${evidence ? ` — evidência: ${evidence}` : ''}`,
            asUser: true,
          })
          await update($, drafts, x => ({ ...x, [`evidencia-${step}`]: '' }))
        })(),
      answerDoubt: id =>
        void (async () => {
          const answer = (await read($, drafts))[`duvida-${id}`] ?? ''
          if (!answer.trim()) return
          await $.prompt.submit({ text: `Resposta à dúvida ${id} do levantamento ${s.id}: ${answer}`, asUser: true })
          await update($, drafts, x => ({ ...x, [`duvida-${id}`]: '' }))
        })(),
      postLevantamento: () => void fill(levantamentoText(s), 'AiDW: o pedido está no prompt; revise e envie'),
      diffSource: source => void showDiff($, source),
      diffFile: path =>
        void (async () => {
          const d = await read($, diff)
          if (d) await showDiff($, d.source, path)
        })(),
      appDiff: repo => void $.prompt.submit({ text: `/aidw:diff ${repo}`, asUser: true }),
      expand: key => void update($, expanded, x => ({ ...x, [key]: !x[key] })),
    }
    return Panel(
      ui,
      {
        snap: s,
        running: await read($, running),
        now: await $.clock.now(),
        tab: await read($, tab),
        publish: await read($, publish),
        vote: await read($, vote),
        votes: await read($, votes),
        drafts: await read($, drafts),
        diff: await read($, diff),
        usage: await read($, usage),
        extraRounds: (await read($, extraRounds))[s.id] ?? 0,
        columns: e.props.bodyColumns,
        surface: e.surface,
        canAppDiff: e.surface === 'desktop',
        reviewFile: await read($, reviewFile),
        decisionTab: await read($, decisionTab),
        filter: await read($, reviewFilter),
        decisions: await read($, decisions),
        expanded: await read($, expanded),
      },
      act,
    )
  })
}
