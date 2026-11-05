// Delegation locks: the orchestrator rules the model may forget, checked before the `Agent` runs.
// Pure (no `$`): register.tsx builds the `DelegationCheck` from runtime.json, the demand and the conversation.

import type { DemandKind } from '../types'

export type Runtime = {
  /** {agent: [allowed subagent_type]} — the default and the exceptions of the Agents and effort table. */
  variants: Record<string, string[]>
  /** Names of the enabled agents (planner, coder…), as aidw.config.toml calls them. */
  agents: string[]
  /** The role of each enabled agent ({coder: 'coder'}): the name is configurable, the role is not. */
  roles: Record<string, string>
}

export type DelegationCheck = {
  subagentType: string
  prompt: string
  model?: string
  runtime: Runtime
  /** The user's latest messages in this session (newest last). */
  userPrompts: string[]
}

import { t } from './i18n'
import { TERM } from './names'

export type { DemandKind }

const MAX_PROMPT = 6000
const MODEL_WORDS = /\b(opus|sonnet|haiku|fable|modelo|model)\b/i


/** The table agent the variant belongs to (`aidw:coder-medium` → `coder`). */
export function agentOf(subagentType: string, runtime: Runtime): string | null {
  const bare = subagentType.split(':').pop() ?? subagentType
  const byPrefix = runtime.agents
    .filter(a => bare === a || bare.startsWith(`${a}-`))
    .sort((a, b) => b.length - a.length)[0]
  return byPrefix ?? null
}

const said = (check: DelegationCheck, re: RegExp) => check.userPrompts.some(p => re.test(p))

/**
 * The reason to refuse the delegation, or null when it follows the rules. It only judges AiDW agents: a
 * `general-purpose` or any other subagent passes.
 */
export function checkDelegation(check: DelegationCheck): string | null {
  const { runtime, prompt } = check
  const agent = agentOf(check.subagentType, runtime)
  if (!agent) return null
  const bare = check.subagentType.split(':').pop() ?? check.subagentType
  const fix = (why: string) => t('guard.prefix', { why })

  if (check.model && !said(check, MODEL_WORDS)) return fix(t('guard.model', { model: check.model }))
  if (!new RegExp(`${TERM.demandFolder}:`).test(prompt)) return fix(t('guard.folder'))
  const allowed = runtime.variants[agent]
  if (!allowed) return fix(t('guard.disabled', { agent }))
  if (!allowed.includes(bare)) {
    return fix(t('guard.variant', { variant: bare, agent, allowed: allowed.map(a => `\`${a}\``).join(', ') }))
  }
  if (prompt.length > MAX_PROMPT) return fix(t('guard.long', { n: prompt.length }))
  return null
}
