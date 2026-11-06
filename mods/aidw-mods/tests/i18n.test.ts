import { describe, expect, test } from 'claude-code/testing'

import { labelFor, parseDelegation, roundFor } from '../hooks/aidw'
import {
  decisionOf,
  kindOf,
  parseCriteria,
  parseDoubts,
  parseFindings,
  parsePrTriage,
  parseTestScript,
  parseTestMatrix,
  parseTriage,
  progress,
} from '../hooks/artifacts'
import { checkDelegation } from '../hooks/guards'
import { getLang, normalizeLang, parseUiLanguage, setLang, t } from '../hooks/i18n'
import { redact } from '../hooks/secrets'
import { buildSnapshot, nextStep, stateLabel, wanted } from '../hooks/snapshot'
import { viewFor, viewTitle, visibleTabs } from '../hooks/views'

describe('UI language', () => {
  test('any pt tag is pt-BR; anything else (or nothing) is English', () => {
    expect(normalizeLang('pt-BR')).toBe('pt-BR')
    expect(normalizeLang('pt')).toBe('pt-BR')
    expect(normalizeLang('pt_PT')).toBe('pt-BR')
    expect(normalizeLang('PT-br')).toBe('pt-BR')
    expect(normalizeLang('en')).toBe('en')
    expect(normalizeLang('es')).toBe('en')
    expect(normalizeLang('')).toBe('en')
    expect(normalizeLang(null)).toBe('en')
    expect(normalizeLang('ptx')).toBe('en')
  })

  test('[ui] language from aidw.config.toml', () => {
    const toml = [
      '[provider]', 'name = "claude"', 'language = "fr"', '',
      '[ui]', '# the chat language', 'language = "pt-BR"  # BCP-47', '',
      '[context]', 'active = "x"',
    ].join('\n')
    expect(parseUiLanguage(toml)).toBe('pt-BR')
    expect(parseUiLanguage("[ui]\r\nlanguage = 'en'\r\n")).toBe('en')
    expect(parseUiLanguage('[provider]\nlanguage = "pt"\n')).toBeNull() // only the [ui] section counts
    expect(parseUiLanguage('')).toBeNull()
  })

  test('English is the default; pt-BR switches the strings; placeholders are filled', () => {
    setLang(null)
    expect(getLang()).toBe('en')
    expect(t('band.waitsForYou')).toBe('● waits for you')
    expect(t('next.paused', { id: 'us-1' })).toContain('/aidw:go us-1')
    expect(stateLabel('review_changes_requested')).toBe('requested changes')
    setLang('pt-BR')
    expect(t('band.waitsForYou')).toBe('● espera você')
    expect(stateLabel('review_changes_requested')).toBe('pediu mudanças')
    setLang('en')
  })
})

describe('English UI strings', () => {
  test('views, steps and progress', () => {
    setLang('en')
    expect(viewTitle('decide', 'development')).toBe('Tests and Review')
    expect(viewTitle('decide', 'survey')).toBe('Questions')
    const s = buildSnapshot({ dir: 'C:/x/us-1', demand: { id: 'us-1', step: 'PLAN_APPROVAL' }, files: [], texts: {} })
    expect(nextStep(s).text).toContain('Read the plan')
    expect(s.waiting).toBe('the plan approval')
    expect(progress('development', { step: 'CODE_REVIEW', history: [{ step: 'PR', at: '' }, { step: 'CODE_REVIEW', at: '' }] }).current).toBe('Code review')
    expect(progress('development', { step: 'DONE' }).stages.at(-1)?.name).toBe('Done')
    expect(viewFor('development', 'tests')).toEqual({ view: 'decide', tab: 'manual' })
    expect(viewFor('survey', 'questions')).toEqual({ view: 'decide', tab: 'questions' })
  })

  test('delegation lock and secret mask', () => {
    setLang('en')
    const runtime = { variants: { coder: ['coder', 'coder-medium'] }, agents: ['coder'], roles: { coder: 'coder' } }
    const why = checkDelegation({ subagentType: 'aidw:coder-high', prompt: 'Task: a.md. Demand folder: C:/d/us-1.', runtime, userPrompts: [] })
    expect(why).toContain('AiDW (delegation lock)')
    expect(why).toContain('is not in the Agents and effort table')
    const r = redact('Server=a;Pass' + 'word=S3nh@Forte!;')
    expect(r.text).toContain('«secret hidden: Password, 11 characters»')
    // an old Portuguese mask is already masked: it passes through unchanged
    expect(redact('Password=«segredo ocultado: Password, 11 caracteres»;').hits).toEqual([])
    // rule names are translated too
    const key = 'gh' + 'p_' + 'a'.repeat(36)
    expect(redact(`token ${key}`).hits).toEqual(['API key (40)'])
    setLang('pt-BR')
    expect(redact(`token ${key}`).hits).toEqual(['chave de API (40)'])
    setLang('en')
  })
})

describe('new English artifact names and headings (the old ones are covered by the other test files)', () => {
  test('delegation prompt and labels', () => {
    const d = parseDelegation('Task: `C:/d/us-1/task-coder-route.md`. Demand folder: `C:/d/us-1`.\nLevel: simples')
    expect(d).toEqual({ demand: 'C:/d/us-1', level: 'simples', task: 'C:/d/us-1/task-coder-route.md' })
    expect(labelFor('task-coder-route.md', 'aidw:coder', '')).toBe('route')
    expect(roundFor('PLAN', ['plan-review-us-1-r2.md'])).toEqual({ round: 2, kind: 'plan' })
  })

  test('file families: English names are read, and preferred when both exist', () => {
    const files = ['summary-us-1.md', 'resumo-us-1.md', 'plan-us-1.md', 'test-plan-us-1.md', 'test-script-us-1.md', 'metrics.md',
      'orchestrator-metrics.md', 'triage-us-1-r1.md', 'triage-plan-us-1-r1.md', 'plan-review-us-1-r1.md', 'coverage-us-1.md', 'security-us-1-r1.md']
    const w = wanted(files)
    for (const f of files.filter(x => x !== 'resumo-us-1.md')) expect(w).toContain(f)
    expect(w).not.toContain('resumo-us-1.md')
    expect(kindOf({}, ['survey-x.md'])).toBe('survey')
    expect(kindOf({ title: 'Something (survey)' }, [])).toBe('survey')
    expect(kindOf({}, ['plan-us-1.md', 'survey-x.md'])).toBe('development')
    expect(kindOf({}, ['test-plan-us-1.md', 'survey-x.md'])).toBe('survey') // a test plan is not the plan
  })

  test('snapshot from English files: criteria, triage, coverage and metrics', () => {
    setLang('en')
    const texts: Record<string, string> = {
      'plan-us-1.md': '# Plan v1\nLevel: padrao\n\n## Acceptance criteria\n- CA1: opens\n- CA2: errors\n',
      'review-us-1-r1.md': '### R1-01 — IMPORTANT — quality — `a.ts:1`\n**What:** bad name\n',
      'review-us-1-r2.md': '### R1-01 — status: fixed\n',
      'triage-us-1-r1.md': '| ID | Decision | Reason |\n|---|---|---|\n| R1-01 | keep | clearer |\n',
      'metrics.md': '| 2026-10-08 | coder | padrao | opus | medium | route | ok | 5 | 9s | 1,000 | — | — | — |\n',
    }
    const s = buildSnapshot({ dir: 'C:/x/us-1', demand: { id: 'us-1', step: 'REVIEW' }, files: Object.keys(texts), texts })
    expect(s.criteria.map(c => c.id)).toEqual(['CA1', 'CA2'])
    expect(s.level).toBe('padrao')
    expect(s.tokens).toBe(1000)
    const f = s.findings.find(x => x.round === 1)
    expect([f?.severity, f?.category, f?.decision, f?.status]).toEqual(['IMPORTANTE', 'quality', 'kept', 'fixed in r2'])
  })

  test('findings, triage words and table headers', () => {
    const [f] = parseFindings(
      '### R1-02 — CRITICAL — security — `b.ts:3`\n**What:** leaks the token\n**Before:**\n```ts\nlog(token)\n```\n**After:**\n```ts\nlog(mask(token))\n```\n**Recommendation:** mask it\n',
      1, 'review')
    expect([f?.severity, f?.category, f?.title, f?.before, f?.after, f?.recommendation]).toEqual(
      ['CRITICO', 'security', 'leaks the token', 'log(token)', 'log(mask(token))', 'mask it'])
    expect(decisionOf('keep — clearer')).toBe('kept')
    expect(decisionOf('discard — out of scope')).toBe('discarded')
    expect(decisionOf('pending')).toBe('pending')
    expect(decisionOf('user decides')).toBe('pending')
    const tri = parseTriage('| ID | Decision | Reason |\n|---|---|---|\n| R1-01 | discard | duplicate |\n\n## Published\n- R1-02: thread 9\n')
    expect(tri.decisions['R1-01']).toBe('discard — duplicate')
    expect(tri.published).toEqual(['R1-02'])
  })

  test('PR triage, test matrix, test script, criteria and open questions', () => {
    const pr = parsePrTriage([
      '## Comments', '| C | PR | Sev. | File:line | Origin | Recommendation | Situation |', '|---|---|---|---|---|---|---|',
      '| C1 | 8 | IMPORTANT | `a.cs:1` | R1-01 and B1-01 | publish | published (thread 1) |',
      '| C2 | 8 | QUESTION | general | R1-D1 | ask | to decide |', '',
      '### C1 — sync call', '> Move it off the UI thread.', '',
      '## Outside the PRs', '- S1: filter.',
    ].join('\n'))
    expect(pr?.comments.map(c => [c.id, c.severity, c.where, c.origins.join('+'), c.published])).toEqual([
      ['C1', 'IMPORTANTE', 'a.cs:1', 'R1-01+B1-01', true],
      ['C2', 'DUVIDA', 'general', 'R1-D1', false],
    ])
    expect(pr?.outside).toBe('- S1: filter.')
    expect(parseTestMatrix('## Coverage matrix\n| CA | Scenario | Type |\n|---|---|---|\n| CA1 | T1 | auto-api |\n')).toEqual({ CA1: ['auto-api'] })
    const steps = parseTestScript('## Card criteria\n| # | Step | Expected | Result | Criterion | How |\n|---|---|---|---|---|---|\n| T1 | open | opens | ✅ ok | CA1 | manual |\n')
    expect(steps.map(m => [m.id, m.step, m.result, m.criteria.join(), m.how])).toEqual([['T1', 'open', '✅', 'CA1', 'manual']])
    expect(parseCriteria('## Acceptance criteria\n- CA1: works\n').map(c => c.text)).toEqual(['works'])
    const doubts = parseDoubts('## Open questions\n- **D1. Does PJ count?** it doubles the scope. *For:* PO *Changes the estimate:* +3 SP\n')
    expect(doubts.map(d => [d.id, d.question, d.to, d.affects])).toEqual([['D1', 'Does PJ count?', 'PO', '+3 SP']])
  })

  test('visible tab labels follow the language', () => {
    setLang('en')
    const s = buildSnapshot({ dir: 'C:/x/us-1', demand: { id: 'us-1', step: 'REVIEW' }, files: ['review-us-1-r1.md'],
      texts: { 'review-us-1-r1.md': '### R1-01 — IMPORTANT — `a.ts:1`\n**What:** x\n' } })
    expect(visibleTabs(s, 'decide')).toEqual([['review', 'Review']])
  })
})
