# Contextos

Esta página explica o que é um contexto, cada configuração do `context.toml`, como funcionam as políticas e a base de
conhecimento, e como criar, ativar e conferir um contexto.

O núcleo do AiDW sabe **como** trabalhar: o fluxo, os papéis, as proteções. Ele não sabe **onde**: quais são os seus
sistemas, como cada um compila, o que o time considera código bom, o que exige aprovação. Isso é o **contexto**: o
pacote de regras de uma empresa ou time, guardado num **repositório Git privado** em `contexts/<nome>/`.

O contexto não muda o nome de nada. Os comandos, os agentes e o fluxo são os mesmos; o que muda é a qualidade da
entrega, porque cada agente já recebe o que o time sabe.

## Por que vale a pena

- **Menos exploração:** o agente já sabe onde cada sistema mora, a stack e o comando de build pronto.
- **Menos retrabalho:** as convenções do time chegam ao coder e ao reviewer; o reviewer cobra o guia do time, não a
  opinião do modelo.
- **Mais segurança:** as permissões e os validadores do time valem para todos os agentes.
- **Aprende com o uso:** o `/aidw:done` grava no contexto o que cada demanda descobriu.

## Estrutura

```text
contexts/<nome>/
├── context.toml      sistemas, permissões, worktree, MCPs, idioma e o que cada agente recebe
├── agents/           regras por papel (orchestrator.md, coder.md, reviewer.md…)
├── policies/         políticas do time (aprovações, ambientes, segredos, escopo)
├── shared/           guias usados por vários agentes (ex.: o guia de código do time)
├── reference/        referências lidas só quando o tema aparece
├── skills/           skills próprias do time
├── tools/            validadores e wrappers (SQL só leitura, build filtrado)
├── workflows/        opcional: workflows que substituem ou somam aos do núcleo
├── routing.toml      opcional: sobreposições das regras e das exceções de effort do núcleo
├── conhecimento/     base de conhecimento: notas ligadas por [[links]]
├── .obsidian/        o vault do Obsidian é a pasta do contexto (grafo e pastas excluídas versionados)
└── demandas/         estado das demandas (ignorado pelo Git do contexto)
```

O `context create` monta essa estrutura. A pasta da base (`conhecimento/`) e a de estado (`demandas/`) são o padrão; as
duas são configuráveis. O repositório do contexto é **separado** do AiDW: o `.gitignore` do AiDW ignora `contexts/`, e
o `doctor` e o `context check` dão erro se isso deixar de valer. Assim o núcleo pode ser público ou compartilhado entre
empresas, e as regras de cada uma ficam privadas.

## `context.toml`

Toda seção é opcional, menos a identificação. Num relance:

| Seção | O que define |
|---|---|
| [identificação, idioma e pastas](#identificação-idioma-e-pastas) | nome, idioma, onde ficam as demandas, pastas extras, variáveis e MCPs obrigatórios |
| [`[mcp.<nome>]`](#mcps-do-time) | o comando que registra cada servidor MCP de que o time precisa |
| [`[worktree]`](#worktree) | prefixo da branch e as pastas ligadas em cada worktree |
| [`[environments]`](#ambientes) | ordem dos ambientes, onde os testes rodam, onde o explorador lê |
| [`[permissions]`](#permissões) | o que roda sem perguntar, o que sempre pergunta, o que é bloqueado |
| [`[systems.<chave>]`](#sistemas) | cada sistema: repositórios, stack, comandos de build e teste, dependências |
| [`[workflows]`](#workflows-por-tipo-de-card) | qual workflow cada tipo de card usa, e as [etapas de fora](#etapas-de-fora) |
| [`[mods]`](#painéis) | desliga os painéis |
| [`[agents.<papel>]`](#o-que-cada-agente-recebe) | o que cada agente sempre lê, lê sob demanda, pode ou não pode usar |
| [`[knowledge]`](#base-de-conhecimento) | a pasta da base de conhecimento |
| [`[upstream.<nome>]`](#upstream) | um repositório de fora que o contexto resume, para saber quando ele mudou |

Depois de editar o `context.toml` (ou qualquer arquivo do contexto), rode `python aidw.py apply` e abra um chat novo.

### Identificação, idioma e pastas

```toml
name = "meu-time"
description = "Empresa X — Time de Pagamentos"
language = "pt-BR"                           # conteúdo do contexto e dos artefatos da demanda (tag BCP-47,
                                             # ex.: "en", "pt-BR"); sem ele, vale o [ui] language do AiDW

state_dir = "contexts/meu-time/demandas"     # onde ficam as pastas das demandas (relativo à raiz do AiDW)
additional_dirs = ["C:/Repos", "C:/Legado"]  # pastas que o chat e os agentes podem usar com este contexto

required_env = ["BOARD_TOKEN"]               # o doctor confere se existem (nunca o valor)
required_mcp = ["board"]                     # o doctor confere se estão registrados

[env]
MCP_TIMEOUT = "60000"                        # variáveis passadas às sessões
```

Os nomes de arquivo são sempre em inglês; o `language` muda só o que vai escrito dentro deles
([configuration.md](configuration.md#idioma)).

### MCPs do time

```toml
[mcp.board]
add = "claude mcp add --scope user board -- npx -y @empresa/board-mcp"
add_codex = "codex mcp add board -- npx -y @empresa/board-mcp"
```

O `doctor` mostra o comando quando o servidor não está registrado, e o `setup` oferece rodar.

### Worktree

Cada demanda que muda código ganha o próprio git worktree ([demands-and-worktrees.md](demands-and-worktrees.md)).

```toml
[worktree]
branch_prefix = "feature/"                   # branch <prefixo><número>-<slug>; padrão "aidw/"
link = ["packages", "node_modules"]          # pastas que o git não versiona, ligadas no worktree (este é o padrão)
```

As pastas de `link` entram por **junction** (um link de pasta do Windows): o worktree usa o `packages/` ou o
`node_modules/` do working copy principal em vez de restaurar tudo de novo.

### Ambientes

```toml
[environments]
order = ["DEV", "QA", "HML", "PROD"]   # do mais longe ao mais perto de produção
test = "DEV"                           # onde o qa testa por padrão
test_fallback = "QA"                   # só para o passo que o padrão não prova; você aprova, só para aquela demanda
explore = ["DEV", "QA"]                # o explorador consulta todos; se divergirem: mais dados, depois mais perto de produção
```

O `test`, o `test_fallback` e cada item do `explore` precisam estar no `order`. Todo agente recebe essas linhas na seção
*Runtime* do seu prompt. Em quais ambientes uma escrita pode mexer continua sendo decidido pelas políticas.

### Permissões

```toml
[permissions]
allow = [                                    # rodam sem perguntar
    "Bash(git *)",
    'PowerShell({{context}}\tools\sql-leitura.ps1 *)',
    "Bash(dotnet build *)",
]
git_ask = ["commit", "push", "merge", "rebase", "reset", "checkout", "switch", "branch -D"]
ask = ["Bash(sqlcmd *)"]                     # sempre pedem OK
deny = []                                    # bloqueados sempre
```

- Precedência: **deny > ask > allow**.
- O `git_ask` gera as regras para `git <sub>` e `git -C <pasta> <sub>`, no Bash e no PowerShell.
- A sintaxe é a do Claude Code e as regras valem no Claude Code. No Codex, só o modo projeto (`apply` com
  `provider = "codex"`) as converte em `.codex/rules/aidw.rules`; a instalação global no Codex não leva regras.

### Sistemas

```toml
[systems.pagamentos-api]
name = "API de Pagamentos"
repos = ["C:/Repos/Pagamentos"]
stack = ".NET 8, Clean Architecture"
depends_on = ["clientes-api"]                # o plano inspeciona esses contratos antes de planejar
build = "dotnet build '<repo>' -v q -clp:ErrorsOnly"
test = "dotnet test '<repo>' -v q --nologo"
worktree_link = ["../Compartilhado"]         # pastas vizinhas que o código alcança por caminho relativo
notes = [
    "Fatos verificados que todo agente precisa sempre que mexe no sistema: ordem de build, bloqueios de ambiente.",
]
```

- `<repo>` é trocado pelo worktree da demanda.
- **Comandos de build e teste prontos e com saída filtrada** estão entre as maiores economias: o agente não procura
  ferramenta de build nem lê mil linhas de log.
- O `depends_on` precisa citar outras chaves de `[systems]`; senão o `apply` avisa.
- `worktree_link`: veja [pastas vizinhas](demands-and-worktrees.md#pastas-vizinhas-worktree_link).
- `notes` ficam para o que **todo** agente precisa sempre que mexe no sistema. Como o sistema funciona, contratos e
  armadilhas do código vão para a [base de conhecimento](#base-de-conhecimento), que o agente lê quando o sistema entra
  na tarefa.

### Workflows por tipo de card

```toml
[workflows]
by_type = { "User Story" = "development", "Bug" = "development" }
notes = ["Uma linha que o orquestrador lê junto da tabela de workflows."]
```

Um arquivo em `contexts/<nome>/workflows/<nome>.yaml` substitui o workflow do núcleo com o mesmo nome, ou acrescenta um
novo.

### Etapas de fora

O núcleo tem duas etapas em que a demanda fica com outras pessoas: `CODE_REVIEW` (o time revisa a PR) e `QA_TEST` (a QA
testa). O contexto pode acrescentar outras antes delas ou antes da PR, por exemplo uma validação de UX:

```toml
[[workflows.external_steps]]
step = "UX_VALIDATION"            # MAIÚSCULAS_COM_SUBLINHADO; vira valor do `demand set --step`
name = "Validação UX"             # o nome na barra de progresso do painel (obrigatório)
before = "PR"                     # PR, CODE_REVIEW ou QA_TEST
who = "UX"                        # aparece como "com UX" na etiqueta de situação
when = "quando a demanda passa por ela e o que acontece antes e depois"   # vai para o orquestrador (obrigatório)
```

- O `apply` confere a declaração (nome de etapa novo, `before` válido, `name` e `when` preenchidos) e põe a etapa na
  seção *Workflows* do orquestrador e no `runtime.json`.
- Como `CODE_REVIEW` e `QA_TEST`, só você move a demanda para dentro ou para fora dela. Um ajuste pedido ali é tratado
  como correção (o caminho curto: sem plano novo, revisão só da mudança).
- A barra de progresso só mostra a etapa na demanda que passa por ela: marcada com
  `demand set <id> --extra-step UX_VALIDATION` (o orquestrador marca quando o plano diz) ou que já está nela.

### Painéis

```toml
[mods]
panel = false                     # desliga os painéis do aidw-mods e os botões da faixa (padrão: ligado)
```

Os painéis ficam ligados em todo contexto; cada aba só aparece quando há o dado dela. Com `panel = false`, o contexto
fica com a faixa e o resto dos mods ([mods.md](mods.md#quando-ficam-ligados)).

Não há escala de voto para declarar: na revisão de PR a pergunta é só "Aprovar a PR?" (manual, sim, não); como aprovar
na sua ferramenta fica na referência de revisão de PR do contexto. Um `[[mods.votes]]` que sobrou só gera um aviso.

### O que cada agente recebe

```toml
[agents.coder]
include = ["shared/guia-time.md", "agents/coder.md"]       # entra SEMPRE no prompt do agente
skills = ["anexar-arquivo"]                                # skills do contexto liberadas para ele
preload = []                                               # skills do contexto pré-carregadas
disallowed_tools = ["mcp__board__comment"]                 # ferramentas bloqueadas para ele
systems = "full"                                           # quanto de [systems] ele recebe: full | short | none
reference = [                                              # lidas SÓ quando o tema aparece
    { path = "reference/templates.md", when = "criar Repository/Service/Controller do zero" },
    { path = "reference/banco.md", when = "criar ou alterar tabela ou script SQL" },
]

[agents.orchestrator]
include = ["agents/orchestrator.md"]                       # entra na skill go e no CLAUDE.md/AGENTS.md
reference = [
    { path = "reference/validacao-ux.md", when = "o plano diz `Validação UX: sim`" },
]
```

Os papéis são `orchestrator`, `explorer`, `planner`, `coder`, `reviewer`, `qa` e `documenter`. Um arquivo de `include`
ou `reference` que não existe é erro no `apply`.

`systems`: `full` é a tabela `[systems]` inteira, com build, teste e notas; `short` é uma linha por sistema (repos,
depende de, nota de conhecimento); `none` tira a seção. O padrão é `full` no explorador, no planejador e no codificador
e `short` nos demais.

#### `include` × `reference`

É a decisão de custo mais importante de um contexto:

| | `include` | `reference` |
|---|---|---|
| No prompt | **sempre**, inteiro | só uma linha com o caminho e o `when` |
| Custo | em toda delegação daquele papel | só quando o tema aparece |
| Use para | regras curtas que valem em toda tarefa | guias longos, templates, documentação de API |

Escreva o `when` como um gatilho concreto ("criar ou alterar endpoint"), não um assunto ("API").

### Variáveis

- Nas strings do `context.toml` e nos `.md` do contexto: `{{context}}` é a pasta do contexto e `{{root}}` a raiz do
  AiDW.
- Nos `.md`: `{{agent:<papel>}}` vira o nome configurado do agente (ex.: `{{agent:reviewer}}` → `reviewer`), para o
  texto continuar certo quando alguém renomeia um agente. Um papel desconhecido é erro.

### Upstream

Quando o contexto resume um repositório de fora (ex.: o guia de código do time), registre o commit que ele reflete:

```toml
[upstream.guia-codigo]
repo = "C:/Repos/GuiaCodigo"
synced = "<hash>"                     # git -C <repo> log -1 --format=%H
covers = ["reference/guia/", "shared/guia-time.md"]
branch = "main"                       # opcional: compara com origin/<branch>; padrão: a branch rastreada do checkout
```

O `python aidw.py context upstream` faz o fetch de cada upstream e avisa quando:

- o remoto tem commits depois do `synced`: as cópias do contexto ficaram para trás. Reconfira o que o `covers` lista e
  atualize o `synced`.
- o checkout local está atrás do remoto: quem lê os arquivos dele lê regra velha. Faça o pull.

O orquestrador roda no início de todo workflow; o `doctor` e o `context check` fazem a mesma conferência.

## Políticas

Um `.md` em `policies/` vale para o orquestrador e para todos os agentes. Duas chaves opcionais do frontmatter
restringem:

- `roles`: só esses papéis recebem. Cada agente paga cada política que recebe em toda execução, então dê a política só
  a quem age sobre ela.
- `orchestrator_when`: o orquestrador lê a política só naquele momento, em vez de sempre (os agentes de `roles`
  continuam recebendo inteira).

```markdown
---
roles: documenter, orchestrator
orchestrator_when: a etapa PR (commit, push e o comentário de pendências)
---

# Policy — Cards no board
...
```

As políticas do contexto **somam** às do núcleo, em `orchestrator/policies/`: git (codificador e orquestrador), banco e
produção (explorador, codificador, qa e orquestrador), segredos e permissões (todos).

Uma política diz o que fazer; a permissão do CLI ([`[permissions]`](#permissões)) garante. Para uma regra que não pode
falhar, use as duas.

## Base de conhecimento

O que as demandas aprenderam sobre os sistemas, em notas Markdown ligadas por `[[links]]`. Liga-se no `context.toml`:

```toml
[knowledge]
dir = "conhecimento"      # relativo à pasta do contexto
```

A **pasta do contexto** abre como **vault no Obsidian**, com a visão em grafo: as notas aparecem junto das políticas,
dos agentes e dos guias, e podem citá-los por `[[nome]]`.

A regra que vale mais: **cada fato mora numa nota só**; quem precisa dele aponta com `[[nome-da-nota]]`. As notas têm
frontmatter (`tipo`, `resumo`, `sistemas`, `fontes`, `atualizado` e, nas notas técnicas, `palavras-chave` — os
identificadores e sinônimos que a busca pesa como o título) e moram na pasta do tipo. Os nomes de pasta e de chave são
fixos:

| Pasta | `tipo` | Uma nota por |
|---|---|---|
| `sistemas/` | `sistema` | sistema do `context.toml` — o nome do arquivo é a chave (`[systems.portal]` → `sistemas/portal.md`) |
| `componentes/` | `componente` | biblioteca ou projeto compartilhado |
| `integracoes/` | `integracao` | contrato entre dois lados: endpoint, SOAP, enum, evento, configuração compartilhada, serviço externo |
| `conceitos/` | `conceito` | termo do domínio; `evitar:` lista os termos que não se usam (vira o glossário do índice) |
| `normas/` | `norma` | lei, norma ou padrão que o domínio segue: versão vigente, o que exige, qual sistema cumpre |
| `ambiente/` | `ambiente` | como operar: hosts, autenticação, banco, receitas |
| `decisoes/` | `decisao` | decisão durável, com autor e data |
| `demandas/` | `demanda` | demanda fechada — desenvolvimento, revisão de PR ou levantamento |

O `README.md` da pasta traz as convenções do time; o `index.md` é gerado (`python aidw.py kb index`).

**Como o AiDW usa:**

- A seção *Systems* do prompt de cada agente aponta a nota do sistema (`Knowledge:`), e a seção *Runtime* ensina o
  `kb show` e o `kb search`. Os agentes leem a nota antes do código; quando o código discorda, vale o código, e a
  diferença volta no relatório.
- O orquestrador consulta a base no começo, passa os caminhos nas tarefas e guarda no `learnings-<id>.md` o que foi
  verificado durante a demanda ([workflow.md](workflow.md#a-base-de-conhecimento-no-fluxo)).
- O `/aidw:done` cria a nota da demanda e atualiza as notas que ela tocou, sem duplicar.
- O `/aidw:knowledge <tema>` responde o que a base sabe, fora de uma demanda.
- O `kb check` (que o `context check` também roda) aponta link quebrado, nome repetido, frontmatter faltando, sistema
  desconhecido, sistema sem nota, nota órfã e texto com cara de segredo ou de documento pessoal; avisa nota com mais de
  150 linhas e nota sem conferência há mais de 6 meses.

**A base descreve, a regra decide.** Uma nota registra como o código é hoje, inclusive o legado fora do padrão: é fato,
não regra. Que padrão o código novo segue quem decide é o guia do time e as políticas do contexto, nunca uma nota
sozinha. Convenção do time não entra na base (vai para `shared/` ou `policies/`).

Versione a configuração do Obsidian (`.obsidian/graph.json`, com as cores por tipo, e `app.json`, que exclui do grafo o
estado das demandas), não o layout de cada máquina.

## Criar um contexto

```text
/aidw:context create
```

1. Pergunta o nome, a descrição, o idioma e os repositórios.
2. Analisa cada repositório em paralelo: stack, build e teste reais, dependências fora do Git, convenções, git e PR,
   integrações, ambientes, banco, riscos — sempre com evidência `arquivo:linha`.
3. Faz **no mínimo 10 perguntas**, com opções e recomendação tiradas da análise (o que pede aprovação, quais ambientes
   são permitidos, onde ficam as demandas, quais MCPs são obrigatórios…).
4. Gera o contexto, cria o repositório Git próprio e roda o `context check`.
5. O commit e o push do repositório do contexto pedem o seu OK.

Pela linha de comando, só o esqueleto:
`python aidw.py context create <nome> --description "..." [--language <tag>] [--mcp a,b] [--env X,Y]`.

## Ativar, validar, listar

```text
/aidw:context use <nome>                ← valida, grava [context] active, regenera; abra um chat novo
python aidw.py context check <nome>     ← build completo com o contexto, repositório próprio, pasta de estado exclusiva, kb check
python aidw.py context list             ← (ou /aidw:context list)
```

Só um contexto fica ativo por vez. A pasta de estado de cada contexto é exclusiva: dois contextos nunca dividem demandas.

## Boas práticas

- **Fatos, não opiniões:** cada regra com o arquivo, o commit ou a decisão de onde veio. Sem exemplos inventados.
- **Curto no `include`, completo no `reference`.**
- **Comandos prontos:** build e teste exatos, com a saída já filtrada.
- **Uma regra de risco é permissão, não texto:** o que nunca pode acontecer vai em `deny`/`ask`.
- **Segredo não se escreve:** só o nome da variável. O `doctor` confere a presença, nunca o valor.
- **Deixe o contexto aprender:** rode `/aidw:done` no fim de cada tarefa.
- **Um fato, um lugar:** na base de conhecimento, ligue com `[[link]]` em vez de copiar.
