import { atom, read, update } from 'claude-code'
import type { BuiltinToolResults, EngineInterface, Register } from 'claude-code'

import type { DemandInfo } from '../types'
import {
  compact,
  demandSetId,
  labelFor,
  parseDelegation,
  parseMaxRetries,
  parseMetricas,
  parseState,
  roundFor,
} from './aidw'

const info = atom({ plugin: 'aidw-mods', key: 'info' } as const, null)
const running = atom({ plugin: 'aidw-mods', key: 'running' } as const, [])
const hidden = atom({ plugin: 'aidw-mods', key: 'hidden' } as const, false)
// Ligado só no modo orquestrador: a sessão está no state/sessions.json, que o guard do AiDW grava ao
// `/aidw:orquestrar` e `/aidw:levantamento` e apaga no `/aidw:sair` e no `/aidw:done`.
const active = atom({ plugin: 'aidw-mods', key: 'active' } as const, false)

type Pending = { agent: string; level: string | null; label: string; demand: string; tools: number }

let root = 'C:/AiDW'
let python = 'python'
// Subagentes em segundo plano: a métrica chega no turn.complete deles, pelo agentId.
const background = new Map<string, Pending>()

const short = (agent: string) => agent.split(':').pop() ?? agent

async function stateDir($: EngineInterface): Promise<string | null> {
  try {
    const runtime = JSON.parse(await $.fs.read(`${root}/.aidw/runtime.json`))
    return typeof runtime.state_dir === 'string' ? runtime.state_dir.replace(/\\/g, '/') : null
  } catch {
    return null
  }
}

/** Relê a demanda do disco e redesenha a faixa. */
async function refresh($: EngineInterface, dir?: string): Promise<void> {
  const target = dir ?? (await read($, info))?.dir
  if (!target) return
  let demand: { id?: string; step?: string }
  try {
    demand = JSON.parse(await $.fs.read(`${target}/demand.json`))
  } catch {
    return
  }
  const files = (await $.fs.list(target).catch(() => [])).map(f => f.name)
  const metricas = files.includes('metricas.md')
    ? parseMetricas(await $.fs.read(`${target}/metricas.md`).catch(() => ''))
    : { rows: 0, tokens: 0, level: null }
  const routing = await $.fs.read(`${root}/orchestrator/config/routing.toml`).catch(() => '')
  const step = demand.step ?? '—'
  const { round, kind } = roundFor(step, files)
  const next: DemandInfo = {
    dir: target,
    id: demand.id ?? target.split('/').pop() ?? target,
    step,
    level: metricas.level,
    round,
    roundKind: kind,
    maxRetries: parseMaxRetries(routing),
    delegations: metricas.rows,
    tokens: metricas.tokens,
  }
  await update($, info, () => next)
}

/** A demanda da pasta da sessão: o primeiro trecho do caminho que é uma demanda do contexto ativo. */
async function fromCwd($: EngineInterface, cwd: string): Promise<string | null> {
  const dir = await stateDir($)
  if (!dir) return null
  for (const part of cwd.replace(/\\/g, '/').split('/')) {
    if (part && (await $.fs.exists(`${dir}/${part}/demand.json`))) return `${dir}/${part}`
  }
  return null
}

/** Confere se esta sessão está no modo orquestrador e, ao entrar, acha a demanda pela pasta da sessão. */
async function checkActive($: EngineInterface): Promise<boolean> {
  let on = false
  try {
    const sessions = JSON.parse(await $.fs.read(`${root}/state/sessions.json`))
    on = Object.prototype.hasOwnProperty.call(sessions, await $.session.id())
  } catch {
    on = false
  }
  const was = await read($, active)
  if (on !== was) await update($, active, () => on)
  if (on && !(await read($, info))) {
    const dir = await fromCwd($, await $.session.cwd())
    if (dir) await refresh($, dir)
  }
  return on
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
    const out = JSON.parse(ran.stdout)
    return out.header ? `${out.header}\n${out.resumo}` : null
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

export const register: Register = (on, options) => {
  root = String(options.aidwRoot ?? 'C:/AiDW').replace(/\\/g, '/').replace(/\/+$/, '')
  python = String(options.python ?? 'python')

  on('session.start', async ($, e, next) => {
    await checkActive($)
    await $.command
      .register({ name: 'aidw-faixa', description: 'Mostra ou esconde a faixa da demanda do AiDW' })
      .catch(() => undefined)
    return next(e)
  })

  on('prompt.submit', async ($, e, next) => {
    const ran = await next(e)
    await checkActive($)
    return ran
  })

  on('command.run', { command: 'aidw-faixa' }, async $ => {
    const now = !(await read($, hidden))
    await update($, hidden, () => now)
    return { text: now ? 'Faixa do AiDW escondida.' : 'Faixa do AiDW visível.' }
  })

  on('tool.call', { tool: 'Agent' }, async ($, e, next) => {
    const d = parseDelegation(e.prompt)
    if (!d || !(await read($, active))) return next(e)
    const agent = e.subagent_type ?? 'general-purpose'
    const p: Pending = { agent, level: d.level, label: labelFor(d.task, agent, e.description), demand: d.demand, tools: 0 }
    const key = e.tool_use_id
    await update($, running, list => [...list, { key, agent: short(agent), label: p.label }])
    if ((await read($, info))?.dir !== d.demand) await refresh($, d.demand)

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

  on('turn.complete', async ($, e, next) => {
    const id = e.agentId
    const p = id ? background.get(id) : undefined
    if (id && p) {
      background.delete(id)
      await update($, running, list => list.filter(r => r.key !== id))
      const u = e.usage
      const tokens = u ? u.input_tokens + u.output_tokens + u.cache_creation_input_tokens + u.cache_read_input_tokens : 0
      const header = await record($, p, parseState(e.answer), tokens, p.tools, e.durationMs)
      await $.session.append({ message: { type: 'user', content: [{ type: 'text', text: notice(header, p) }] } })
    } else if (!id && (await read($, active))) {
      await refresh($)
    }
    return next(e)
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

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const d = await read($, info)
    if (e.props.hasSurvey || !d || d.step === 'DONE' || !(await read($, active)) || (await read($, hidden))) {
      return next(e)
    }
    const agents = await read($, running)
    const { Box, Text } = $.ui.resolve(e)
    const over = d.roundKind !== null && d.round > d.maxRetries

    return (
      <Box>
        <Text color="claude" bold>
          AiDW{' '}
        </Text>
        <Text>
          {d.id} · {d.step}
        </Text>
        {d.roundKind && (
          <Text color={over ? 'warning' : 'text'}>
            {' '}
            · {d.roundKind} r{d.round}/{d.maxRetries}
            {over ? ' ⚠' : ''}
          </Text>
        )}
        {d.level && <Text dimColor> · {d.level}</Text>}
        <Text dimColor>
          {' '}
          · {d.delegations} delegações · {compact(d.tokens)} tokens
        </Text>
        {agents.length > 0 && (
          <Text color="suggestion"> · ▶ {agents.map(a => `${a.agent} (${a.label})`).join(', ')}</Text>
        )}
      </Box>
    )
  })
}
