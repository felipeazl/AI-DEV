import { describe, expect, test } from 'claude-code/testing'

import { redact, redactBlocks } from '../hooks/secrets'

describe('filtro de segredos', () => {
  test('connection string mantém a chave e esconde o valor', async () => {
    // a senha vai em pedaços para o scanner de segredos do GitHub não tomar o exemplo por segredo real
    const r = redact('Server=sql01;Database=App;User Id=app;Pass' + 'word=S3nh@Forte!;Encrypt=true')
    expect(r.text).toContain('Password=«segredo ocultado: Password, 11 caracteres»')
    expect(r.text).toContain('Server=sql01;Database=App;User Id=app;')
    expect(r.text).not.toContain('S3nh@Forte!')
    expect(r.hits).toEqual(['Password (11)'])
  })

  test('idempotente: um texto já filtrado passa de novo igual', async () => {
    const once = redact('Server=sql01;Pass' + 'word=S3nh@Forte!;Encrypt=true').text
    const twice = redact(once)
    expect(twice.text).toBe(once)
    expect(twice.hits).toEqual([])
  })

  test('JSON, variável de ambiente, Bearer e JWT', async () => {
    const jwt = ['eyJhbGciOiJIUzI1NiJ9', 'eyJzdWIiOiIxMjM0NTY3ODkwIn0', 'dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U'].join('.') // em pedaços: é um JWT de teste, não um segredo
    const text = [
      '"stringConexao": "Data Source=x;Password=abcdef"',
      'PERSONAL_ACCESS_TOKEN=abcdefghijklmnopqrstuvwxyz123456',
      'Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789',
      `token ${jwt}`,
    ].join('\n')
    const r = redact(text)
    expect(r.text).not.toContain('abcdefghijklmnopqrstuvwxyz123456')
    expect(r.text).not.toContain('abcdefghijklmnopqrstuvwxyz0123456789')
    expect(r.text).not.toContain(jwt)
    expect(r.text).toContain('PERSONAL_ACCESS_TOKEN=«segredo ocultado: PERSONAL_ACCESS_TOKEN')
    expect(r.hits.length).toBeGreaterThan(3)
  })

  test('placeholders e código comum ficam', async () => {
    for (const text of [
      'Password=${DB_PASSWORD};',
      '"password": "<senha>"',
      'API_TOKEN=%API_TOKEN%',
      'var password = request.Password;',
      'git commit 3f2a9c1d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f',
    ]) {
      expect(redact(text).hits).toEqual([])
    }
  })

  test('blocos de conteúdo: texto e resultado de ferramenta', async () => {
    const content = [
      { type: 'text', text: 'ok' },
      { type: 'tool_result', tool_use_id: 't1', content: [{ type: 'text', text: 'Pwd=supersecreto;' }] },
    ]
    const r = redactBlocks(content)
    expect(JSON.stringify(r.content)).not.toContain('supersecreto')
    expect(JSON.stringify(r.content)).toContain('"tool_use_id":"t1"')
    expect(redactBlocks([{ type: 'text', text: 'nada aqui' }]).hits).toEqual([])
  })
})
