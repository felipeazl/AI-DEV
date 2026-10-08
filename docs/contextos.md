# Contextos

O núcleo do AiDW sabe **como** trabalhar: o fluxo, os papéis, as proteções. Ele não sabe **onde**: quais são os
seus sistemas, como se compila cada um, o que o time considera código bom, o que exige aprovação. Isso é o
**contexto**: o pacote de regras de uma empresa ou squad, num **repositório Git privado** em `contexts/<nome>/`.

O contexto não muda o nome de nada. Os comandos, os agentes e o fluxo são os mesmos; o que muda é a qualidade da
entrega, porque cada agente já recebe o que o time sabe.

## Por que vale a pena

- **Menos exploração:** o agente já sabe onde o sistema mora, a stack e o comando de build pronto, com saída filtrada.
- **Menos retrabalho:** as convenções do time vão para o codificador e o revisor; o revisor cobra o guia do time, não
  a opinião do modelo.
- **Mais segurança:** as permissões e os validadores do time valem para todos os agentes.
- **Aprende com o uso:** o `/aidw:done` grava no contexto o que cada demanda descobriu.

## Estrutura

```text
contexts/<nome>/
├── context.toml      sistemas, permissões, worktree, MCPs e o que cada agente recebe
├── agents/           regras por papel (orchestrator.md, coder.md, reviewer.md…)
├── policies/         políticas do time (aprovações, ambientes, segredos, escopo)
├── shared/           guias usados por vários agentes (ex.: o guia de código do time)
├── reference/        referências lidas só quando o tema aparece
├── skills/           skills próprias do time
├── tools/            validadores e wrappers (SQL só leitura, build filtrado)
├── conhecimento/     base de conhecimento: notas ligadas por [[links]]
├── .obsidian/        o vault do Obsidian é a pasta do contexto (grafo e pastas excluídas versionados)
└── demandas/         estado das demandas (fora do Git do contexto)
```

O repositório do contexto é **separado** do AiDW: o `.gitignore` do AiDW ignora `contexts/`, e o `doctor` e o
`context check` dão erro se isso deixar de valer. Assim o núcleo pode ser público ou compartilhado entre empresas, e as
regras de cada uma ficam privadas.

## `context.toml`

### Identificação e pastas

```toml
name = "meu-time"
description = "Empresa X — Squad Pagamentos"

state_dir = "contexts/meu-time/demandas"     # onde ficam as pastas das demandas (relativo à raiz do AiDW)

additional_dirs = ["C:/Projetos", "C:/Legado"]   # liberadas para o chat e os agentes

required_env = ["MEU_TOKEN"]                 # o doctor confere se existem (nunca o valor)
required_mcp = ["board"]                     # o doctor confere se estão registrados

[env]
MCP_TIMEOUT = "60000"                        # variáveis passadas às sessões
```

### MCPs do time

```toml
[mcp.board]
add = "claude mcp add --scope user board -- npx -y @empresa/board-mcp"
add_codex = "codex mcp add board -- npx -y @empresa/board-mcp"
```

O `doctor` mostra o comando quando o servidor não está registrado, e o `setup` oferece rodar.

### Worktree

```toml
[worktree]
branch_prefix = "feature/"                   # branch: <prefixo><número>-<slug>
link = ["packages", "node_modules"]          # pastas que o git não versiona e entram por junction
```

### Permissões

```toml
[permissions]
allow = [                                    # rodam sem perguntar
    "Bash(git *)",
    'PowerShell({{context}}\tools\sql-consulta.ps1 *)',
    "Bash(dotnet build *)",
]
git_ask = ["commit", "push", "merge", "rebase", "reset", "checkout", "switch", "branch -D"]
ask = ["Bash(sqlcmd *)"]                     # sempre pedem OK
deny = []                                    # bloqueados sempre
```

- Precedência: **deny > ask > allow**.
- `git_ask` gera as regras para `git <sub>` e `git -C <pasta> <sub>`, no Bash e no PowerShell.
- A sintaxe é a do Claude Code; no Codex, as regras de comando viram `.codex/rules/aidw.rules`.

### Sistemas

```toml
[systems.pagamentos-api]
name = "API de Pagamentos"
repos = ["C:/Projetos/Pagamentos"]
stack = ".NET 8, Clean Architecture"
depends_on = ["cadastro-api"]                # o plano inspeciona o contrato desses antes de planejar
build = "dotnet build '<repo>' -v q -clp:ErrorsOnly"
test = "dotnet test '<repo>' -v q --nologo"
worktree_link = ["../Compartilhado"]         # pastas vizinhas que o código alcança por caminho relativo
notes = [
    "Fatos verificados que valem para toda demanda: armadilhas, ordem de build, padrões a seguir.",
]
```

- `<repo>` é trocado pelo worktree da demanda.
- **Comandos de build e teste prontos e com saída filtrada** são uma das maiores economias: o agente não procura
  ferramenta de build nem lê mil linhas de log.
- `notes` ficam para o que **todo** agente precisa sempre que mexe no sistema: bloqueio de ambiente e como
  destravar, ordem de build. Como o sistema funciona, contratos e armadilhas do código vão para a base de
  conhecimento (abaixo), que o agente lê quando o sistema entra na tarefa.

### O que cada agente recebe

```toml
[agents.coder]
include = ["shared/guia-time.md", "agents/coder.md"]        # entra SEMPRE no prompt do agente
skills = ["anexar-arquivo"]                                 # skills do contexto liberadas para ele
preload = []                                                # skills do contexto pré-carregadas
disallowed_tools = ["mcp__board__comentar"]                 # ferramentas bloqueadas para ele
reference = [                                               # lidas SÓ quando o tema aparece
    { path = "reference/templates.md", when = "criar Repository/Service/Controller do zero" },
    { path = "reference/banco.md", when = "criar ou alterar tabela ou script SQL" },
]

[agents.orchestrator]
include = ["agents/orchestrator.md"]                        # entra no CLAUDE.md/AGENTS.md e no orquestrar
reference = [
    { path = "reference/revisao-final.md", when = "montar o pacote da revisão final (FINAL_REVIEW)" },
]
```

### `include` × `reference`

É a decisão de custo mais importante de um contexto:

| | `include` | `reference` |
|---|---|---|
| Entra no prompt | **sempre**, inteiro | só a linha com o caminho e o `when` |
| Custo | em toda delegação daquele papel | só quando o tema aparece |
| Use para | regras curtas que valem em toda tarefa | guias longos, templates, documentação de API |

Escreva o `when` como um gatilho concreto ("criar ou alterar endpoint"), não um assunto ("API").

### Variáveis

- Nas strings do `context.toml`: `{{context}}` é a pasta do contexto e `{{root}}` a raiz do AiDW.
- Nos `.md`: `{{agent:<papel>}}` vira o nome configurado do agente (ex.: `{{agent:reviewer}}` → `revisor`). Assim o
  texto continua certo quando alguém renomeia um agente.

## Políticas

Um `.md` em `policies/` vale para o orquestrador e para todos os agentes. Com frontmatter `orchestrator_when`, o
orquestrador lê a política só naquele momento (os agentes continuam recebendo inteira):

```markdown
---
orchestrator_when: preparar a revisão (PREPARE_REVIEW)
---

# Policy — Cards no board
...
```

As políticas do contexto **somam** às do núcleo (`orchestrator/policies/`: git, banco, produção, segredos,
permissões). Uma política diz o que fazer; a permissão do CLI garante. Para uma regra que não pode falhar, use as duas.

## Criar um contexto

```text
/aidw:contexto-criar
```

1. Pergunta o nome e os repositórios.
2. Analisa cada repositório em paralelo: stack, build e teste reais, dependências fora do Git, convenções, git e PR,
   integrações, ambientes, banco, riscos, sempre com evidência `arquivo:linha`.
3. Faz **no mínimo 10 perguntas**, com opções e recomendação tiradas da análise (o que pede aprovação, quais ambientes
   são permitidos, onde ficam as demandas, quais MCPs são obrigatórios…).
4. Gera o contexto, cria o repositório Git próprio e roda `context check`.
5. Commit e push do repositório do contexto pedem o seu OK.

Pela linha de comando, só a estrutura: `python aidw.py context create <nome> --description "..."`.

## Base de conhecimento

O que as demandas aprenderam sobre os sistemas, em notas Markdown ligadas por `[[links]]`. A **pasta do contexto** abre
como **vault no Obsidian**, com a visão em grafo: as notas aparecem junto das policies, dos agentes e dos guias, e podem
citá-los por `[[nome]]`. Liga-se no `context.toml`:

```toml
[knowledge]
dir = "conhecimento"      # relativo à pasta do contexto
```

A regra que vale mais: **cada fato mora numa nota só**; quem precisa dele aponta com `[[nome-da-nota]]`. As notas têm
frontmatter (`tipo`, `resumo`, `sistemas`, `fontes`, `atualizado` e, nas notas técnicas, `palavras-chave` — os
identificadores e sinônimos que a busca pesa como o título) e moram na pasta do tipo:

| Pasta | `tipo` | Uma nota por |
|---|---|---|
| `sistemas/` | `sistema` | sistema do `context.toml` — o nome do arquivo é a chave (`[systems.hope]` → `sistemas/hope.md`) |
| `componentes/` | `componente` | biblioteca ou projeto compartilhado |
| `integracoes/` | `integracao` | contrato entre dois lados: endpoint, SOAP, enum, evento, configuração compartilhada, serviço externo |
| `conceitos/` | `conceito` | termo do domínio; `evitar:` lista os termos que não se usam (vira o glossário do índice) |
| `ambiente/` | `ambiente` | como operar: hosts, autenticação, banco, receitas |
| `decisoes/` | `decisao` | decisão durável, com autor e data |
| `demandas/` | `demanda` | demanda fechada — desenvolvimento, revisão de PR ou levantamento |

O `README.md` da pasta traz as convenções do time; `index.md` é gerado (`kb index`).

**Como o AiDW usa:**

- A seção *Systems* do prompt de cada agente aponta a nota do sistema (`Knowledge:`), e o Runtime ensina o `kb show`
  e o `kb search`. Os agentes leem a nota antes do código; quando o código discorda, vale o código, e a diferença
  volta no relatório.
- O orquestrador consulta a base no começo da demanda, passa os caminhos nas tarefas e anota em
  `aprendizados-<id>.md` o que foi verificado durante ([fluxo.md](fluxo.md#a-base-de-conhecimento-no-fluxo)).
- O `/aidw:done` cria a nota da demanda e atualiza as notas que ela tocou, sem duplicar.
- O `/aidw:conhecimento <tema>` responde o que a base sabe, fora de uma demanda.
- O `kb check` (também dentro do `context check`) aponta link quebrado, nome repetido, frontmatter faltando,
  `sistemas` que não existem, sistema sem nota, nota órfã e texto com cara de segredo ou CPF; avisa nota com mais de
  150 linhas (divida: quem lê paga por linha) e nota sem conferência há mais de 6 meses.

**A base descreve, a regra decide.** Uma nota registra como o código é hoje, inclusive o legado fora do padrão: é
fato, não regra. Que padrão o código novo segue quem decide é o guia do time e as políticas do contexto (inclusive
como o guia se compara ao padrão já estabelecido em cada repositório), nunca uma nota sozinha. A instrução que todo
agente recebe na seção *Systems* diz isso, e convenção do time não entra na base (vai para `shared/` ou `policies/`).

Versione a configuração do Obsidian (`.obsidian/graph.json`, com as cores por tipo, e `app.json`, que exclui do grafo o
estado das demandas e pastas sem links), não o layout de cada máquina. O `kb check` avisa quando o nome de uma nota
coincide com outro `.md` do contexto — no vault o `[[link]]` ficaria ambíguo — e quando o `index.md` está velho.

### Upstream

Quando o contexto resume um repositório de fora (ex.: o guia de código do time), registre o commit que ele reflete:

```toml
[upstream.guideline]
repo = "C:/Projetos/Guideline"
synced = "<hash>"                     # git -C <repo> log -1 --format=%H
covers = ["reference/guia/", "shared/guia-time.md"]
```

O `context check` avisa quando o repositório tem commits depois do `synced`: as cópias podem ter ficado para trás.
Reconfira o que `covers` lista e atualize o `synced`.

## Ativar, validar, listar

```text
/aidw:contexto-usar <nome>                  ← valida, grava [context] active, regenera; abra um chat novo
python aidw.py context check <nome>          ← build completo com o contexto, repositório próprio, pasta de estado exclusiva
python aidw.py context list                  ← (ou /aidw:contexto-listar)
```

Só um contexto fica ativo por vez. A pasta de estado de cada contexto é exclusiva: dois contextos não dividem demandas.

## Boas práticas

- **Fatos, não opiniões:** cada regra com o arquivo, o commit ou a decisão de onde veio. Sem exemplos inventados.
- **Curto no `include`, completo no `reference`.**
- **Comandos prontos:** build e teste exatos, com a saída já filtrada.
- **Uma regra de risco é permissão, não texto:** o que nunca pode acontecer vai em `deny`/`ask`.
- **Segredo não se escreve:** só o nome da variável. O `doctor` confere a presença, nunca o valor.
- **Deixe o contexto aprender:** rode `/aidw:done` no fim de cada tarefa.
- **Um fato, um lugar:** na base de conhecimento, ligue com `[[link]]` em vez de copiar; quando duas notas
  divergem, confira no código e corrija a errada.
