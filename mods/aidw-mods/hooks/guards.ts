// Travas da delegação: as regras do orquestrador que o modelo pode esquecer, conferidas antes do `Agent` rodar.
// Puro (sem `$`): o register.tsx monta o `DelegationCheck` com o runtime.json, a demanda e a conversa.

import type { DemandKind } from '../types'

export type Runtime = {
  /** {nível: {agente: variante ou null quando não roda}} — a tabela Effort per task. */
  levels: Record<string, Record<string, string | null>>
  defaultLevel: string
  maxRetries: number
  /** Nomes dos agentes ligados (planejador, codificador…). */
  agents: string[]
}

export type DelegationCheck = {
  subagentType: string
  prompt: string
  model?: string
  runtime: Runtime
  /** As últimas mensagens do Felipe nesta sessão (a mais nova por último). */
  userPrompts: string[]
  /** Etapa gravada da demanda e a rodada do laço dela. */
  step: string | null
  round: number
  roundKind: 'plano' | 'revisão' | null
  /** Rodadas extras liberadas pelo Felipe (botão ou /aidw-rodada). */
  extraRounds: number
  /** pr-review e levantamento não têm laço de correção. */
  kind: DemandKind | null
}

export type { DemandKind }

const MAX_PROMPT = 6000
const MODEL_WORDS = /\b(opus|sonnet|haiku|fable|modelo)\b/i
const FIX_STEPS = new Set(['REVIEW', 'CODER_FIX'])
const PLAN_FIX_STEPS = new Set(['PLAN_REVIEW', 'PLAN_FIX'])

/** O agente da tabela a que a variante pertence (`aidw:codificador-sonnet-high` → `codificador`). */
export function agentOf(subagentType: string, runtime: Runtime): string | null {
  const bare = subagentType.split(':').pop() ?? subagentType
  const byPrefix = runtime.agents
    .filter(a => bare === a || bare.startsWith(`${a}-`))
    .sort((a, b) => b.length - a.length)[0]
  return byPrefix ?? null
}

const said = (check: DelegationCheck, re: RegExp) => check.userPrompts.some(p => re.test(p))

/**
 * O motivo para recusar a delegação, ou null quando ela segue as regras. Só julga agentes do AiDW: um
 * `general-purpose` ou outro subagente qualquer passa.
 */
export function checkDelegation(check: DelegationCheck): string | null {
  const { runtime, prompt } = check
  const agent = agentOf(check.subagentType, runtime)
  if (!agent) return null
  const bare = check.subagentType.split(':').pop() ?? check.subagentType
  const fix = (why: string) => `AiDW (trava da delegação): ${why}`

  if (check.model && !said(check, MODEL_WORDS)) {
    return fix(
      `não passe \`model\` (${check.model}): o modelo de cada agente vem da tabela Effort per task. ` +
        'Só passe outro modelo quando o Felipe pedir nesta conversa.',
    )
  }
  if (!/Pasta da demanda:/.test(prompt)) {
    return fix('o prompt precisa de `Tarefa: <arquivo>. Pasta da demanda: <pasta>. Nível: <nível>.` (falta a pasta).')
  }
  const level = /N[íi]vel:\s*`?([a-z]+)/.exec(prompt)?.[1]
  if (!level) {
    return fix('o prompt precisa do `Nível: <nível>.` da tarefa (é ele que escolhe a célula da tabela).')
  }
  const row = runtime.levels[level]
  if (!row) {
    return fix(`nível \`${level}\` não existe; use um de: ${Object.keys(runtime.levels).join(', ')}.`)
  }
  if (!(agent in row)) {
    return fix(`o agente \`${agent}\` está desligado nesta configuração; faça a etapa você mesmo ou ligue o agente.`)
  }
  const cell = row[agent]
  if (cell === null) {
    return fix(`\`${agent}\` não roda no nível \`${level}\` (célula "— (não roda)"); a etapa é sua nesse nível.`)
  }
  if (cell !== undefined && cell !== bare) {
    return fix(
      `no nível \`${level}\` o \`subagent_type\` de \`${agent}\` é \`${cell}\`, não \`${bare}\`. ` +
        'Se é um follow-up (um nível abaixo) ou um escalonamento (um acima), escreva no prompt o nível usado.',
    )
  }
  if (prompt.length > MAX_PROMPT) {
    return fix(
      `prompt de ${prompt.length} caracteres: insumos grandes (diff, plano, review) vão por caminho, ` +
        'num arquivo da pasta da demanda, nunca colados.',
    )
  }
  const limit = runtime.maxRetries + check.extraRounds
  if (check.kind === 'desenvolvimento' && check.round >= limit && check.step) {
    const codeLoop = check.roundKind === 'revisão' && FIX_STEPS.has(check.step) && ['revisor', 'codificador'].includes(agent)
    const planLoop = check.roundKind === 'plano' && PLAN_FIX_STEPS.has(check.step) && ['revisor', 'planejador'].includes(agent)
    if (codeLoop || planLoop) {
      return fix(
        `a ${check.roundKind === 'plano' ? 'revisão do plano' : 'revisão'} já está na rodada ${check.round} e o ` +
          `limite é ${limit} (max_retries${check.extraRounds ? ` + ${check.extraRounds} liberada(s)` : ''}). ` +
          'Pare e leve ao Felipe (HUMAN_APPROVAL) com o que ainda falta; só ele libera mais uma rodada, pelo ' +
          'botão "Liberar +1 rodada" do painel ou com /aidw-rodada.',
      )
    }
  }
  return null
}
