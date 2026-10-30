// Travas da delegação: as regras do orquestrador que o modelo pode esquecer, conferidas antes do `Agent` rodar.
// Puro (sem `$`): o register.tsx monta o `DelegationCheck` com o runtime.json, a demanda e a conversa.

import type { DemandKind } from '../types'

export type Runtime = {
  /** {agente: [subagent_type permitidos]} — o padrão e as exceções da tabela Agents and effort (fluxo v3). */
  variants: Record<string, string[]>
  maxRetries: number
  /** Nomes dos agentes ligados (planejador, codificador…), como o aidw.config.toml os chama. */
  agents: string[]
  /** O papel de cada agente ligado ({codificador: 'coder'}): o nome é configurável, o papel não. */
  roles: Record<string, string>
}

export type DelegationCheck = {
  subagentType: string
  prompt: string
  model?: string
  runtime: Runtime
  /** As últimas mensagens do usuário nesta sessão (a mais nova por último). */
  userPrompts: string[]
  /** Etapa gravada da demanda e a rodada do laço dela. */
  step: string | null
  round: number
  roundKind: 'plano' | 'revisão' | null
  /** Rodadas extras liberadas pelo usuário (botão ou /rodada). */
  extraRounds: number
  /** pr-review e levantamento não têm laço de correção. */
  kind: DemandKind | null
}

export type { DemandKind }

const MAX_PROMPT = 6000
const MODEL_WORDS = /\b(opus|sonnet|haiku|fable|modelo)\b/i
/** As etapas do laço revisão ⇄ correção (as antigas ficam pelas demandas abertas antes do fluxo v3). */
const FIX_STEPS = new Set(['REVIEW', 'TRIAGE', 'CODER_FIX'])

/** O agente da tabela a que a variante pertence (`aidw:codificador-medium` → `codificador`). */
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
      `não passe \`model\` (${check.model}): o modelo de cada agente vem da tabela Agents and effort. ` +
        'Só passe outro modelo quando o usuário pedir nesta conversa.',
    )
  }
  if (!/Pasta da demanda:/.test(prompt)) {
    return fix('o prompt precisa de `Tarefa: <arquivo>. Pasta da demanda: <pasta>.` (falta a pasta).')
  }
  const allowed = runtime.variants[agent]
  if (!allowed) {
    return fix(`o agente \`${agent}\` está desligado nesta configuração; faça a etapa você mesmo ou ligue o agente.`)
  }
  if (!allowed.includes(bare)) {
    return fix(
      `\`${bare}\` não está na tabela Agents and effort; para \`${agent}\` use ${allowed.map(a => `\`${a}\``).join(', ')} ` +
        '(o padrão, ou a exceção cujo motivo vale para esta tarefa).',
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
    if (check.roundKind === 'revisão' && FIX_STEPS.has(check.step) && ['reviewer', 'coder'].includes(runtime.roles[agent] ?? '')) {
      return fix(
        `a revisão já está na rodada ${check.round} e o limite é ${limit} (max_retries` +
          `${check.extraRounds ? ` + ${check.extraRounds} liberada(s)` : ''}). ` +
          'Pare e leve ao usuário (HUMAN_APPROVAL) com o que ainda falta; só ele libera mais uma rodada, pelo ' +
          'botão "Liberar +1 rodada" do painel ou com /rodada.',
      )
    }
  }
  return null
}
