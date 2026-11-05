// Secrets filter: masks the value of passwords, tokens, keys and connection strings before the line enters the
// conversation (the orchestrator's and the agents'), showing only the name and the length, as the secrets policy asks.

import { t, tk, type Key } from './i18n'

export type Redaction = { text: string; hits: string[] }

// The mask is written in the UI language; both the English and the old Portuguese masks are recognized as masked.
const mask = (name: string, value: string) => t('secret.mask', { name, n: value.length })

/** Placeholders and references are not secrets: `${VAR}`, `%VAR%`, `$(VAR)`, `<password>`, `***`, `xxx`. */
function isPlaceholder(value: string, keyed: boolean): boolean {
  const v = value.replace(/^["']|["']$/g, '')
  return (
    v.length < 4 ||
    /^\$\{.*\}$|^%[^%]+%$|^\$\(.*\)$|^<.*>$|^\{\{.*\}\}$|^\*+$|^x+$|^«(?:segredo ocultado|secret hidden)/i.test(v) ||
    /^(true|false|null|none|undefined|sim|não|string|password|senha|changeme|\.\.\.)$/i.test(v) ||
    // code, not a value, after a key: `Password = request.Password`, `config.Get(...)`
    (keyed && (/^[A-Za-z_]\w*(\.[A-Za-z_]\w*)+;?$/.test(v) || /^[A-Za-z_][\w.]*\(/.test(v)))
  )
}

const MASKED = /«(?:segredo ocultado|secret hidden): [^»]*»/g


// `name` is an i18n key (the label shown in the mask), or a literal technical name (`Bearer`, `JWT`).
type Rule = { name: Key | string; re: RegExp; group: number; label?: (m: RegExpExecArray) => string }

// Order matters: whole blocks (private key, connection string) before loose keys.
const RULES: Rule[] = [
  { name: 'secret.privateKey', re: /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----/g, group: 0 },
  // Password=…;  Pwd=…;  AccountKey=…;  SharedAccessKey=…  (.NET, Azure Storage, Service Bus connection strings)
  {
    name: 'connection string',
    re: /\b(Password|Pwd|User Password|AccountKey|SharedAccessKey|Client ?Secret)\s*=\s*("[^"]*"|'[^']*'|[^;"'\s<]+)/gi,
    group: 2,
    label: m => m[1] ?? t('secret.password'),
  },
  // "password": "…", "segredo": "…", "stringConexao": "…" (JSON and appsettings)
  {
    name: 'secret.field',
    re: /"((?:[\w.]*?)(?:password|passwd|senha|secret|segredo|token|apikey|api_key|clientsecret|accesskey|connectionstring|stringconexao))"\s*:\s*"((?:[^"\\]|\\.){4,})"/gi,
    group: 2,
    label: m => m[1] ?? t('secret.field'),
  },
  // NAME_TOKEN=…  PERSONAL_ACCESS_TOKEN: …  (environment variables and .env)
  {
    name: 'secret.variable',
    re: /\b([A-Z][A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|APIKEY|ACCESS_KEY|PAT))\s*[=:]\s*["']?([^\s"';,]{6,})/g,
    group: 2,
    label: m => m[1] ?? t('secret.variable'),
  },
  { name: 'Bearer', re: /\bBearer\s+([A-Za-z0-9\-._~+/]{20,}=*)/g, group: 1 },
  { name: 'JWT', re: /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/g, group: 0 },
  { name: 'secret.apiKey', re: /\b(?:sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{32,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})\b/g, group: 0 },
]

/** Masks the secrets of a text. `hits` says what was masked (name and length), never the value. */
export function redact(text: string): Redaction {
  if (text.length < 8) return { text, hits: [] }
  const hits: string[] = []
  // Idempotent: a mask already in the text (a result filtered again) is kept aside and comes back unchanged at the end;
  // without it the connection string rule masked its own «secret hidden…» (2026-11-04).
  const kept: string[] = []
  let out = text.replace(MASKED, m => `\u0000${kept.push(m) - 1}\u0000`)
  for (const rule of RULES) {
    out = out.replace(rule.re, (...args: unknown[]) => {
      const groups = args.slice(0, -2).filter((a): a is string => typeof a === 'string' || a === undefined) as string[]
      const whole = groups[0] ?? ''
      const value = rule.group === 0 ? whole : groups[rule.group]
      if (!value || isPlaceholder(value, rule.group !== 0)) return whole
      const m = groups as unknown as RegExpExecArray
      const name = rule.label ? rule.label(m) : tk(rule.name, rule.name)
      hits.push(`${name} (${value.length})`)
      return rule.group === 0 ? mask(name, value) : whole.replace(value, mask(name, value))
    })
  }
  if (kept.length) out = out.replace(/\u0000(\d+)\u0000/g, (_, i: string) => kept[Number(i)] ?? '')
  return { text: out, hits }
}

/** Masks the secrets of each text of a content block (text, tool result). */
export function redactBlocks<T>(content: T): { content: T; hits: string[] } {
  const hits: string[] = []
  const walk = (node: unknown): unknown => {
    if (typeof node === 'string') {
      const r = redact(node)
      hits.push(...r.hits)
      return r.text
    }
    if (Array.isArray(node)) return node.map(walk)
    if (node && typeof node === 'object') {
      const obj = node as Record<string, unknown>
      // only the text fields: ids, types and images stay as they are
      const out: Record<string, unknown> = { ...obj }
      if (typeof obj.text === 'string' || Array.isArray(obj.text)) out.text = walk(obj.text)
      if (obj.type === 'tool_result' && obj.content !== undefined) out.content = walk(obj.content)
      return out
    }
    return node
  }
  const next = walk(content) as T
  return { content: hits.length ? next : content, hits }
}

/**
 * Masks the secrets of every text of a tool result (the tool record, before it becomes a conversation
 * line): each string, in any field, except base64 images and PDFs.
 */
export function redactValue<T>(value: T): { value: T; hits: string[] } {
  const hits: string[] = []
  const walk = (node: unknown, key = ''): unknown => {
    if (typeof node === 'string') {
      if (key === 'base64') return node
      const r = redact(node)
      hits.push(...r.hits)
      return r.text
    }
    if (Array.isArray(node)) return node.map(x => walk(x))
    if (node && typeof node === 'object') {
      return Object.fromEntries(Object.entries(node as Record<string, unknown>).map(([k, v]) => [k, walk(v, k)]))
    }
    return node
  }
  const next = walk(value) as T
  return { value: hits.length ? next : value, hits }
}
