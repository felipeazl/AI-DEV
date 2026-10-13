// Filtro de segredos: mascara o valor de senhas, tokens, chaves e connection strings antes de a linha entrar na
// conversa (do orquestrador e dos agentes), mostrando só o nome e o tamanho, como a policy de segredos pede.

export type Redaction = { text: string; hits: string[] }

const mask = (name: string, value: string) => `«segredo ocultado: ${name}, ${value.length} caracteres»`

/** Placeholders e referências não são segredo: `${VAR}`, `%VAR%`, `$(VAR)`, `<senha>`, `***`, `xxx`. */
function isPlaceholder(value: string, keyed: boolean): boolean {
  const v = value.replace(/^["']|["']$/g, '')
  return (
    v.length < 4 ||
    /^\$\{.*\}$|^%[^%]+%$|^\$\(.*\)$|^<.*>$|^\{\{.*\}\}$|^\*+$|^x+$|^«segredo ocultado/i.test(v) ||
    /^(true|false|null|none|undefined|sim|não|string|password|senha|changeme|\.\.\.)$/i.test(v) ||
    // código, não valor, depois de uma chave: `Password = request.Password`, `config.Get(...)`
    (keyed && (/^[A-Za-z_]\w*(\.[A-Za-z_]\w*)+;?$/.test(v) || /^[A-Za-z_][\w.]*\(/.test(v)))
  )
}

type Rule = { name: string; re: RegExp; group: number; label?: (m: RegExpExecArray) => string }

// A ordem importa: blocos inteiros (chave privada, connection string) antes das chaves soltas.
const RULES: Rule[] = [
  { name: 'chave privada', re: /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----/g, group: 0 },
  // Password=…;  Pwd=…;  AccountKey=…;  SharedAccessKey=…  (connection strings do .NET, Azure Storage, Service Bus)
  {
    name: 'connection string',
    re: /\b(Password|Pwd|User Password|AccountKey|SharedAccessKey|Client ?Secret)\s*=\s*("[^"]*"|'[^']*'|[^;"'\s<]+)/gi,
    group: 2,
    label: m => m[1] ?? 'senha',
  },
  // "password": "…", "segredo": "…", "stringConexao": "…" (JSON e appsettings)
  {
    name: 'campo',
    re: /"((?:[\w.]*?)(?:password|passwd|senha|secret|segredo|token|apikey|api_key|clientsecret|accesskey|connectionstring|stringconexao))"\s*:\s*"((?:[^"\\]|\\.){4,})"/gi,
    group: 2,
    label: m => m[1] ?? 'campo',
  },
  // NOME_TOKEN=…  PERSONAL_ACCESS_TOKEN: …  (variáveis de ambiente e .env)
  {
    name: 'variável',
    re: /\b([A-Z][A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|APIKEY|ACCESS_KEY|PAT))\s*[=:]\s*["']?([^\s"';,]{6,})/g,
    group: 2,
    label: m => m[1] ?? 'variável',
  },
  { name: 'Bearer', re: /\bBearer\s+([A-Za-z0-9\-._~+/]{20,}=*)/g, group: 1 },
  { name: 'JWT', re: /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/g, group: 0 },
  { name: 'chave de API', re: /\b(?:sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{32,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})\b/g, group: 0 },
]

/** Mascara os segredos de um texto. `hits` diz o que foi mascarado (nome e tamanho), nunca o valor. */
export function redact(text: string): Redaction {
  if (text.length < 8) return { text, hits: [] }
  const hits: string[] = []
  let out = text
  for (const rule of RULES) {
    out = out.replace(rule.re, (...args: unknown[]) => {
      const groups = args.slice(0, -2).filter((a): a is string => typeof a === 'string' || a === undefined) as string[]
      const whole = groups[0] ?? ''
      const value = rule.group === 0 ? whole : groups[rule.group]
      if (!value || isPlaceholder(value, rule.group !== 0)) return whole
      const m = groups as unknown as RegExpExecArray
      const name = rule.label ? rule.label(m) : rule.name
      hits.push(`${name} (${value.length})`)
      return rule.group === 0 ? mask(name, value) : whole.replace(value, mask(name, value))
    })
  }
  return { text: out, hits }
}

/** Mascara os segredos de cada texto de um bloco de conteúdo (texto, resultado de ferramenta). */
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
      // só os campos de texto: ids, tipos e imagens ficam como estão
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
