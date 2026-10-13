// Diffs: divide um patch unificado (git diff, diff-<ticket>-r<N>.patch, diff-pr<n>-<repo>.patch) por arquivo.

export type DiffFile = {
  path: string
  /** `novo`, `apagado`, `renomeado` ou `alterado`. */
  change: 'novo' | 'apagado' | 'renomeado' | 'alterado'
  added: number
  removed: number
  /** Só os hunks (do primeiro `@@`), o que o elemento `Code` com `format: 'diff'` desenha. */
  hunks: string
  binary: boolean
}

export function splitDiff(patch: string): DiffFile[] {
  const files: DiffFile[] = []
  const parts = patch.replace(/\r\n/g, '\n').split(/^(?=diff --git )/m)
  for (const part of parts) {
    const head = /^diff --git a\/(.+?) b\/(.+)$/m.exec(part)
    if (!head) continue
    const lines = part.split('\n')
    const at = lines.findIndex(l => l.startsWith('@@'))
    const body = at >= 0 ? lines.slice(at) : []
    let added = 0
    let removed = 0
    for (const l of body) {
      if (l.startsWith('+') && !l.startsWith('+++')) added += 1
      else if (l.startsWith('-') && !l.startsWith('---')) removed += 1
    }
    const change = /^new file mode/m.test(part)
      ? 'novo'
      : /^deleted file mode/m.test(part)
        ? 'apagado'
        : /^rename from /m.test(part)
          ? 'renomeado'
          : 'alterado'
    files.push({
      path: head[2] ?? head[1] ?? '?',
      change,
      added,
      removed,
      hunks: body.join('\n').replace(/\n+$/, ''),
      binary: /^Binary files /m.test(part),
    })
  }
  return files
}

/** Linha de resumo: `12 arquivos · +340 −85`. */
export function diffSummary(files: DiffFile[]): string {
  const add = files.reduce((n, f) => n + f.added, 0)
  const del = files.reduce((n, f) => n + f.removed, 0)
  return `${files.length} arquivo${files.length === 1 ? '' : 's'} · +${add} −${del}`
}
