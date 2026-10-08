export type DemandInfo = {
  dir: string
  id: string
  step: string
  level: string | null
  round: number
  roundKind: 'plano' | 'revisão' | null
  maxRetries: number
  delegations: number
  tokens: number
}

export type RunningAgent = { key: string; agent: string; label: string }

declare module 'claude-code' {
  interface PluginState {
    'aidw-mods': { active: boolean; info: DemandInfo | null; running: RunningAgent[]; hidden: boolean }
  }
}
