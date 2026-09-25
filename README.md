# AI-DEV

Sistema pessoal de **desenvolvimento agêntico multi-agente** sobre o Claude Code.

Você conversa com **um único chat** — o orquestrador — e ele planeja o trabalho, delega para
agentes especializados (codificador, revisor, documentador…), consolida os resultados e para
para pedir sua aprovação nos pontos críticos. Tudo roda com o **login do Claude Code**, sem
API key.

O plano de arquitetura que originou o projeto está em
[docs/plano-arquitetura.md](docs/plano-arquitetura.md).

---

## Sumário

1. [O que o AI-DEV faz](#1-o-que-o-ai-dev-faz)
2. [Conceitos](#2-conceitos)
3. [Pré-requisitos](#3-pré-requisitos)
4. [Instalação](#4-instalação)
5. [Configuração](#5-configuração)
6. [Como usar](#6-como-usar)
7. [Comandos](#7-comandos)
8. [O que o `apply` gera](#8-o-que-o-apply-gera)
9. [Estendendo o sistema](#9-estendendo-o-sistema)
10. [Estrutura de pastas](#10-estrutura-de-pastas)
11. [Segurança](#11-segurança)
12. [Solução de problemas](#12-solução-de-problemas)
13. [Limitações e próximos passos](#13-limitações-e-próximos-passos)

---

## 1. O que o AI-DEV faz

```text
                       ┌──────────────────────────────┐
  Você  ─── chat ────► │  orquestrador (Opus)         │  o chat do Claude Code aberto
                       │  entende · planeja · delega  │  na pasta do AI-DEV
                       └──────────────┬───────────────┘
                                      │  ferramenta Agent (mesma sessão)
          ┌───────────────┬───────────┼──────────────┬────────────────┐
          ▼               ▼           ▼              ▼                ▼
    codificador       revisor        api           qa          documentador
     (Sonnet)         (Sonnet)     (Sonnet)     (desligado)       (Sonnet)
     implementa        revisa     opera DEV/QA    testa         documenta
```

- **Um chat, vários agentes.** Os agentes são *subagentes nativos* do Claude Code: cada um tem
  suas próprias instruções, modelo e skills, e trabalha num contexto isolado. Eles não veem a
  sua conversa e não falam com você — perguntas e aprovações voltam para o orquestrador, que
  pergunta no chat.
- **Fluxo com especificação.** Pedido → spec → tickets → implementação → testes → revisão →
  correção → documentação. A spec é a fonte de verdade; cada ticket é pequeno o bastante para
  um agente executar sem conhecer a conversa original.
- **Aprovação humana onde importa.** Plano de execução, triagem da revisão, correções e
  qualquer escrita em ambiente (API, banco, work items) passam por você.
- **Regras de trabalho separadas.** Guias do time, referências e permissões de um emprego
  ficam num *contexto* — um repositório Git privado à parte, que nunca é versionado aqui.
- **Configuração declarativa.** Um arquivo (`aidev.config.toml`) define modelos, agentes,
  nomes e contexto; um script (`aidev.py`) gera todo o resto. Rodar de novo não muda nada se
  a config não mudou.

---

## 2. Conceitos

O sistema separa cinco coisas que costumam ficar misturadas num `CLAUDE.md` gigante:

| Conceito | O que é | Onde fica |
|---|---|---|
| **Agente** | Um papel: o que faz, o que recebe, o que devolve | `agents/<papel>/AGENT.md` |
| **Modelo** | Qual LLM executa o agente | `config/models.toml` + `aidev.config.toml` |
| **Skill** | Procedimento reutilizável (ex.: transformar pedido em spec) | `skills/<nome>/SKILL.md` |
| **Policy** | Regra que não depende da opinião do modelo | `orchestrator/policies/*.md` |
| **Contexto** | Pacote de regras de um ambiente de trabalho | `contexts/<nome>/` |

### Papel × nome

Cada agente tem um **papel** fixo, usado internamente, e um **nome**, pelo qual o orquestrador o
chama e que aparece nas respostas. O nome é opcional; sem ele vale o padrão:

| Papel | Nome padrão | Função |
|---|---|---|
| `orchestrator` | `orquestrador` | O chat principal. Planeja, delega, consolida, pede aprovação |
| `coder` | `codificador` | Implementa um ticket por vez; testes, build, lint, typecheck |
| `reviewer` | `revisor` | Revisa o diff contra spec/ticket; devolve achados com severidade; não altera código |
| `api-db` | `api` | Consulta APIs, banco e logs; propõe escritas e só executa após aprovação |
| `qa` | `qa` | Roda testes e verifica critérios de aceite (desligado por padrão) |
| `documenter` | `documentador` | README, ARCHITECTURE, changelog, docs de API, work items |

### Skills incluídas

| Skill | Usada por | Para quê |
|---|---|---|
| `to-spec` | orquestrador | Transforma o pedido numa especificação persistente |
| `to-tickets` | orquestrador | Quebra a spec em tickets autocontidos |
| `codebase-context` | orquestrador, codificador | Levanta stack, arquitetura e convenções de um projeto |
| `implement-ticket` | codificador | Entender → planejar → implementar → testar → lint → typecheck → diff |
| `debug` | codificador, api | Diagnosticar falhas e decidir entre corrigir, tentar de novo ou escalar |
| `testing` | codificador, qa | Rodar a suíte de validação do projeto de forma padronizada |
| `code-review` | revisor | Revisão com severidade (high/medium/low) contra spec e ticket |
| `database-safe` | api | Classificar e barrar operações de banco perigosas |
| `documentation` | documentador | Documentar só o que está no diff aprovado |

Contextos podem trazer skills próprias (ex.: anexar arquivo a um work item).

### MCPs padrão

Quatro servidores MCP vêm configurados por padrão, no escopo do projeto (`.mcp.json`):

| MCP | Para quê | Agentes |
|---|---|---|
| **Playwright** | Exercitar a aplicação no navegador: fluxos E2E, formulários, critérios de aceite de UI | codificador, qa, revisor |
| **Chrome DevTools** | Depurar num Chrome real: console, rede, performance, DOM/CSS | codificador, qa |
| **Figma** | Ler o design (frames, componentes, variáveis) para implementar ou conferir telas | codificador, revisor, documentador |
| **Context7** | Documentação atualizada de bibliotecas, na versão do projeto | todos |

**Quem decide quando usar cada um é o orquestrador.** Antes de delegar, ele compara a tarefa com
os *gatilhos* de cada MCP (`config/mcp.toml`), escolhe só entre os liberados para o agente que vai
receber a tarefa e nomeia o MCP explicitamente na tarefa ("Use o Playwright para percorrer o
fluxo…") — ou escreve "nenhum MCP necessário". Os agentes usam o que a tarefa nomear e reportam
o que usaram. Com o JEV ligado, a escolha passa a ser dele, com os gatilhos como fallback.

### Camada de decisão

Depois de cada resultado, o orquestrador decide a próxima ação (`TEST`, `REVIEW`, `CODER_FIX`,
`DOCS`, `DONE`, `HUMAN_APPROVAL`…). Hoje isso segue **regras determinísticas** de
`orchestrator/config/routing.toml`. O **JEV** — um modelo dedicado a essas decisões — está
previsto, mas **desligado**: a ideia é primeiro medir o fluxo com regras fixas e só depois
comparar.

---

## 3. Pré-requisitos

| Ferramenta | Versão | Observação |
|---|---|---|
| **Claude Code** | 2.1.280+ para Opus 5.5 | App desktop (aba Code) ou CLI `claude`. Login com a sua conta |
| **Python** | 3.11+ | Só para o script de setup; nenhuma biblioteca extra |
| **Git** | qualquer recente | |
| **Node.js** | LTS | Para os MCPs locais (Playwright, Chrome DevTools, Context7), que rodam via `npx` |

Não é preciso API key: os agentes rodam dentro da sua sessão do Claude Code e consomem o limite
do seu plano.

---

## 4. Instalação

### 4.1 Passo a passo

**1. Clone o AI-DEV**

```bash
git clone https://github.com/felipeazl/AI-DEV.git C:/AI-DEV      # Windows
git clone https://github.com/felipeazl/AI-DEV.git ~/AI-DEV       # Linux / macOS
```

**2. (Opcional) Clone um contexto de trabalho**

Se você tem um repositório de contexto (regras de trabalho de uma empresa ou projeto), clone-o
**dentro de `contexts/`**, com o nome que ele deve ter no AI-DEV:

```bash
git clone <url-do-repositorio-de-contexto> C:/AI-DEV/contexts/<nome>
```

Faça isso **antes** do setup. Sem contexto, o AI-DEV funciona só com as regras genéricas; se a
config apontar para um contexto que não foi clonado, o setup pergunta se você quer seguir sem
contexto, escolher outro ou criar um novo na hora. Contextos são repositórios **privados** e
separados — o AI-DEV nunca os versiona.

**3. Rode o setup**

```powershell
cd C:\AI-DEV
.\setup.ps1                  # Windows
```

```bash
cd ~/AI-DEV
./setup.sh                   # Linux / macOS  (ou: bash setup.sh)
```

Os dois atalhos só localizam um Python 3.11+ e chamam `python aidev.py setup`, repassando os
argumentos. O setup roda o `apply` (gera o ambiente) e o `doctor` (verifica tudo).

**4. Abra o Claude Code na pasta do AI-DEV** e autentique os MCPs que pedirem (ex.: Figma:
`/mcp` → figma → Authenticate). Pronto — esse chat é o orquestrador (seção 6).

### 4.2 O wizard

Se não houver `aidev.config.toml` (ou com `setup --reconfigure`), o setup abre o **wizard**:

| Pergunta | Opções | Padrão |
|---|---|---|
| 1. Como distribuir os modelos? | `multi` (um por agente) · `single` (um para todos) | `multi` |
| 2. Modelo de cada agente | Opus 5.5 High/Medium, Sonnet 5, Haiku 4.5 | Opus no orquestrador, Sonnet nos demais |
| 3. Agentes a desabilitar / personalizar nomes | lista separada por vírgula · s/n | `qa` desligado · nomes padrão |
| 4. Pastas dos projetos *(opcional)* | caminhos separados por `;` | nenhuma |
| 5. Servidores MCP | lista do catálogo `config/mcp.toml` | Playwright, Chrome DevTools, Figma, Context7 |
| 6. Contexto de trabalho *(opcional)* | nenhum · um existente em `contexts/` · **criar um novo agora** | nenhum |
| 7. Usar o JEV? | s/n | não |

- **Pastas dos projetos** ficam liberadas para o chat e todos os subagentes, e o orquestrador
  as usa para procurar repositórios. Caminho inexistente pede confirmação antes de ser mantido.
- **Criar um novo contexto** pergunta nome, descrição, variáveis de ambiente exigidas e MCPs
  exigidos, e gera `contexts/<nome>/` com a estrutura mínima e um **repositório Git próprio**.
  Para cada MCP já registrado, o comando de registro é preenchido a partir do `claude mcp list`.

Depois do wizard, o setup roda o `apply` e o `doctor`.

### 4.3 Adicionando um contexto depois

Um contexto pode ser clonado a qualquer momento; depois é só selecioná-lo:

```bash
git clone <url-do-repositorio-de-contexto> C:/AI-DEV/contexts/<nome>
python aidev.py setup --reconfigure      # escolha o contexto na pergunta 6
```

### 4.4 Outra máquina

Repita os passos 1 a 4. O `aidev.config.toml` vem no clone, então **o wizard não roda**: o setup
aplica a mesma config direto. Os arquivos gerados não são versionados — cada máquina gera os
seus. Para mudar as escolhas nessa máquina, use `setup --reconfigure`.

---

## 5. Configuração

Toda a configuração fica em arquivos de texto. Depois de editar qualquer um deles, rode
`python aidev.py apply` e **abra um chat novo** para o Claude Code carregar as mudanças.

### 5.1 `aidev.config.toml` — sua configuração

```toml
[models]
mode = "multi"          # "multi": cada agente usa o seu | "single": todos usam `default`
default = "opus-high"   # usado no modo single

[workspace]
project_dirs = ["C:/Projetos"]   # opcional; liberadas para todos os agentes

[mcp]
enabled = ["playwright", "chrome-devtools", "figma", "context7"]   # chaves de config/mcp.toml

[context]
active = "meu-trabalho" # pasta em contexts/ ("" = nenhum)

[jev]
enabled = false         # camada de decisão por modelo (futuro)
model = "jev"

[policies]
deny = [                # bloqueado sempre — chat e todos os subagentes
    "Bash(git push --force *)",
    "Read(**/.env)",
    # ...
]
ask = []                # sempre pede sua confirmação, mesmo se liberado em outro lugar

[agents.coder]
# name = "codificador"  # opcional; minúsculas, dígitos e hífen
enabled = true
model = "sonnet"        # chave de config/models.toml
skills = ["implement-ticket", "debug", "testing", "codebase-context"]
```

- **Modelo do orquestrador** é o do chat: vai para `.claude/settings.local.json` com o ID
  completo e o effort (ex.: `claude-opus-5-5`, `high`).
- **Modelo dos subagentes** é passado por apelido (`opus`, `sonnet`, `haiku`) — é o que o
  Claude Code aceita — e o **effort é herdado do chat**. Chat em High ⇒ subagentes em High.
- `python aidev.py configure` reescreve o arquivo inteiro (comentários próprios se perdem);
  para ajustes pontuais, edite à mão.

### 5.2 `config/models.toml` — catálogo de modelos

```toml
[models.sonnet]
name = "Claude Sonnet 5"
provider = "anthropic"
model_id = "claude-sonnet-5"   # usado quando é o modelo do chat
alias = "sonnet"               # usado quando é modelo de subagente
effort = "high"                # effort do chat quando é o orquestrador
```

Campos opcionais: `min_claude_code` (versão mínima do CLI, checada pelo `doctor`) e
`router_only` (só pode ser usado pelo JEV). Modelos com `provider` diferente de `anthropic`
(GPT, JEV) ficam catalogados, mas o `apply` recusa usá-los enquanto não houver suporte a API key.

### 5.3 `config/mcp.toml` — catálogo de MCPs

```toml
[servers.playwright]
name = "Playwright"
type = "stdio"                       # stdio (processo local) | http (remoto)
command = "npx"
args = ["-y", "@playwright/mcp@latest"]
allow = false                        # true = ferramentas liberadas sem prompt
agents = ["coder", "qa", "reviewer"] # papéis que podem usar ([] = todos)
use_when = "Exercitar a aplicação no navegador de ponta a ponta…"
triggers = ["teste E2E de uma tela ou fluxo", "validar critério de aceite de interface"]
```

- `use_when` e `triggers` viram as instruções de decisão do orquestrador e a tabela de MCPs de
  cada agente. Ajustar os gatilhos é a forma de calibrar quando cada MCP é chamado.
- Servidores com `auth = "oauth"` (Figma) precisam de autenticação uma vez: no Claude Code,
  `/mcp` → servidor → **Authenticate**.
- Por padrão, Figma e Context7 (só leitura) são liberados sem prompt; Playwright e Chrome
  DevTools (controlam o navegador) pedem permissão.

### 5.4 `orchestrator/config/routing.toml` — regras de decisão

```toml
max_retries = 3

[rules]
implementation_complete = "TEST"
tests_failed = "CODER_FIX"
tests_passed = "REVIEW"
review_changes_requested = "CODER_FIX"
review_approved = "DOCS"
max_retries_exceeded = "HUMAN_APPROVAL"
```

### 5.5 `contexts/<nome>/context.toml` — um contexto de trabalho

```toml
name = "meu-trabalho"
description = "Empresa X — Squad Y"
state_dir = "contexts/meu-trabalho/demandas"   # onde ficam specs, planos e reviews

additional_dirs = ["C:/ProjetosEmpresa"]       # pastas extras só com este contexto
required_env = ["PERSONAL_ACCESS_TOKEN"]       # o doctor verifica só a presença
required_mcp = ["ado"]                         # o doctor confere em `claude mcp list`

[env]
MCP_TIMEOUT = "60000"                          # variáveis para a sessão

[mcp.ado]                                       # dica mostrada quando o MCP não está registrado
add = "claude mcp add --scope user ado -- npx -y @azure-devops/mcp <org> -d core work work-items -a pat"

[permissions]
allow = ["mcp__ado", "Bash(git *)", "PowerShell(git *)",
         'PowerShell(C:\AI-DEV\contexts\meu-trabalho\tools\meu-script.ps1 *)']
git_ask = ["commit", "push", "merge"]          # gera ask para `git X` e `git -C <pasta> X`
ask = ["PowerShell(sqlcmd *)"]                 # sempre pedem confirmação (vencem o allow)
deny = []

[systems.meu-sistema]                           # mapa de sistemas (vai para todos os agentes)
name = "Meu Sistema"
repos = ["C:/Projetos/MeuSistema"]
stack = ".NET 8, Clean Architecture"
depends_on = ["outra-api"]                     # o plano inspeciona o contrato das dependências
build = "dotnet build 'C:\\Projetos\\MeuSistema' -v q -clp:ErrorsOnly"   # pronto e filtrado
test = "dotnet test 'C:\\Projetos\\MeuSistema' -v q --nologo"
notes = ["armadilha conhecida: ..."]

[agents.coder]                                  # por papel
include = ["shared/guia-time.md", "agents/coder.md"]   # sempre nas instruções do agente
skills = ["minha-skill-do-contexto"]                  # somado às skills do agente
disallowed_tools = ["mcp__ado__wit_work_item_comment_write"]   # bloqueado neste agente
reference = [                                          # lido só quando o tema aparece
    { path = "reference/guia-integracoes.md", when = "integrar com os serviços SOAP legados" },
]

[agents.orchestrator]
include = ["agents/orchestrator.md"]
```

- Todo `*.md` em `contexts/<nome>/policies/` entra automaticamente em todos os agentes.
- As pastas liberadas são a soma de `[workspace].project_dirs` com `additional_dirs` do contexto.
- **Economia de tokens:** o que entra em `include` é carregado em toda chamada do agente; guias
  longos que só às vezes importam vão em `reference` (o agente lê quando o tema aparece).
- **Scripts liberados** precisam ser chamados pelo **caminho direto, sem espaços**: o Claude Code
  sempre pede aprovação para chamadas com `&` ou `pwsh -File`, mesmo com regra `allow`. Por isso
  ferramentas como um validador de SQL ou um wrapper de build ficam em `contexts/<nome>/tools/`.

### 5.6 Citando agentes nas instruções

Nos arquivos de instruções (agentes, policies, contextos), escreva `{{agent:<papel>}}` em vez
do nome. O `apply` troca pelo nome configurado — assim renomear um agente não quebra nenhum texto:

```markdown
2. **Revisar PR/diff** → `{{agent:reviewer}}` (não altera código).
```

Um marcador com papel inexistente faz o `apply` falhar sem gravar nada.

---

## 6. Como usar

### 6.1 Abrindo o orquestrador

Abra o Claude Code **na pasta do AI-DEV**:

- **App desktop:** aba Code → abrir pasta `C:\AI-DEV`.
- **Terminal:** `cd C:\AI-DEV` e `claude`.

Esse chat já é o orquestrador: ele carrega o `CLAUDE.md` gerado, com as regras, as policies,
o contexto e a tabela do time.

### 6.2 Pedindo uma demanda

Escreva como pediria a um tech lead:

```text
Implementar a US https://dev.azure.com/<org>/<projeto>/_workitems/edit/1234
Corrigir o bug 5678 — o login falha em QA quando o token expira
Revisar a branch feature/novo-relatorio contra a US 1234
Gerar um dado de teste em QA para o cenário de cancelamento
Redigir uma dívida técnica para remover o cliente HTTP duplicado
```

### 6.3 O que acontece

O fluxo é **autônomo**. Você entra só em dúvidas, ações travadas e na revisão final:

```text
Você: "Implementar a US 1234"
  │
  ├─ orquestrador  lê a US (trabalho já existente? MCPs necessários?) · explora o código
  ├─ to-spec       plano com checklists ........ ⏸ só se houver dúvida ou mais de um caminho
  ├─ to-tickets    Tasks no board, branch/worktree da demanda
  ├─ codificador   implementa ticket a ticket (build pronto, saída filtrada)
  ├─ preparação    checklist: anexos, tag, pendências para QA, build
  ├─ revisor ⇄ codificador   loop automático, triagem por regras, até zero CRITICO/IMPORTANTE
  ├─ documentador  documenta o que foi entregue
  └─ revisão final ............................. ⏸ você: resultado, decisões tomadas,
                                                   comentários a publicar, commit/push
```

- **Triagem por regras:** CRITICO/IMPORTANTE são corrigidos dentro do escopo; SUGESTAO é
  aplicada se for barata; dúvidas e decisões de Tech Lead vão para você numa pergunta só.
- **Ações travadas** (definidas pelas policies do contexto, ex.: commit, push, SQL de escrita)
  pedem sua aprovação pelo prompt de permissão — nunca são contornadas.
- Cada resultado vem identificado com o agente e o modelo (ex.: `## codificador — sonnet`).
- Tickets independentes podem rodar em paralelo.

### 6.4 Pedidos úteis ao orquestrador

| Você quer | Diga |
|---|---|
| Saber onde está o fluxo | "Em que etapa estamos?" |
| Um agente com modelo mais forte | "Use Opus no codificador para este ticket" |
| Pular a orquestração | "Só me responda, sem delegar" |
| Mexer no próprio AI-DEV | "Manutenção do AI-DEV: …" — ele trabalha direto, sem o fluxo |
| Retomar uma demanda | "Retome a US 1234" — specs e planos ficam no state dir |

### 6.5 Mudando a configuração

```text
editar aidev.config.toml / agents/ / skills/ / contexto
        ↓
python aidev.py apply
        ↓
abrir um chat novo
```

---

## 7. Comandos

| Comando | O que faz |
|---|---|
| `.\setup.ps1` / `./setup.sh` | Atalho para `python aidev.py setup` |
| `python aidev.py setup` | Wizard (se não houver config) → apply → doctor |
| `python aidev.py setup --reconfigure` | Refaz o wizard partindo da config atual |
| `python aidev.py configure` | Só o wizard; grava a config |
| `python aidev.py configure --defaults` | Grava a config padrão sem perguntar |
| `python aidev.py apply` | Gera o ambiente a partir da config (idempotente) |
| `python aidev.py apply --dry-run` | Mostra o que mudaria, sem alterar nada |
| `python aidev.py doctor` | Verifica CLI, versão, contexto, pastas, variáveis e MCPs (padrão e do contexto), inclusive duplicados |
| `python aidev.py show` | Mostra nome, papel, modelo e tipo de cada agente |

Exemplo de `show`:

```text
== AI-DEV · modo multi · contexto meu-trabalho ==
  NOME           PAPEL         MODELO                     TIPO
  orquestrador   orchestrator  Claude Opus 5.5 (High)     chat
  codificador    coder         Claude Sonnet 5            subagente (sonnet)
  revisor        reviewer      Claude Sonnet 5            subagente (sonnet)
  api            api-db        Claude Sonnet 5            subagente (sonnet)
  qa             qa            Claude Sonnet 5            subagente (sonnet)  (desabilitado)
  documentador   documenter    Claude Sonnet 5            subagente (sonnet)
```

---

## 8. O que o `apply` gera

Nada disso é versionado; é sempre regenerado a partir das fontes.

| Arquivo | Conteúdo |
|---|---|
| `CLAUDE.md` | O orquestrador: `orchestrator/CLAUDE.md` + tabela do time + policies + contexto, com os marcadores já trocados |
| `.claude/agents/<nome>.md` | Um subagente por agente habilitado: `AGENT.md` + policies + arquivos do contexto; frontmatter com nome, descrição, modelo e skills |
| `.claude/skills/<skill>` | Links para `skills/` e para as skills do contexto |
| `.claude/settings.local.json` | Modelo e effort do chat, `deny`/`allow`, pastas liberadas, variáveis, MCPs pré-aprovados. Chaves que você adicionar à mão são preservadas |
| `.mcp.json` | Os MCPs habilitados, no escopo do projeto. Servidores que você adicionar à mão são preservados |
| `orchestrator/config/runtime.json` | Configuração resolvida (agentes, modelos, regras), para o futuro orquestrador próprio |

Garantias do `apply`:

- **Valida antes de gravar.** Modelo inexistente, skill ausente, nome inválido ou duplicado,
  marcador errado: erro, e nada é alterado.
- **Idempotente.** Sem mudança na config, nenhuma escrita.
- **Limpa o que sobrou.** Agente renomeado ou desligado tem o arquivo antigo removido; só
  arquivos marcados como gerados são apagados.

---

## 9. Estendendo o sistema

### Nova skill

1. Crie `skills/<nome>/SKILL.md` com frontmatter `name` e `description` (a descrição diz ao
   Claude *quando* usar).
2. Adicione o nome em `skills = [...]` dos agentes que devem pré-carregá-la.
3. `python aidev.py apply`.

### Novo agente

1. Crie `agents/<papel>/AGENT.md`:

   ```markdown
   ---
   description: Analista de bugs. Investiga causa-raiz a partir de logs e código. Use para diagnosticar falhas.
   ---

   # ROLE
   ...
   # OUTPUT
   ...
   ```

   Campos extras do frontmatter (ex.: `tools`, `disallowedTools`, `permissionMode`) são
   repassados ao subagente.
2. Adicione `[agents.<papel>]` no `aidev.config.toml` (com `name` opcional).
3. Opcional: `[agents.<papel>]` no `context.toml` do contexto, com os arquivos a incluir.
4. `python aidev.py apply` e um chat novo.

### Novo modelo

Adicione uma tabela em `config/models.toml` e referencie a chave no `aidev.config.toml`.

### Nova policy

Crie um `.md` em `orchestrator/policies/` (vale para qualquer contexto) ou em
`contexts/<nome>/policies/` (só naquele contexto). Para bloqueios que o modelo não pode
contornar, acrescente também uma regra em `[policies].deny`.

### Novo contexto

```powershell
python aidev.py setup --reconfigure      # pergunta 6 → "criar um novo contexto agora"
```

O setup gera `contexts/<nome>/` (`context.toml` comentado, `README.md`, `agents/orchestrator.md`
e as pastas `policies/`, `shared/`, `reference/`, `skills/`, `demandas/`) e roda `git init`.
Depois é só escrever as regras e rodar `python aidev.py apply`.

---

## 10. Estrutura de pastas

```text
AI-DEV/
├── aidev.py                    script de setup (apply, doctor, wizard…)
├── setup.ps1 / setup.sh        atalhos por sistema operacional
├── aidev.config.toml           sua configuração
├── config/models.toml          catálogo de modelos
├── orchestrator/
│   ├── CLAUDE.md               instruções genéricas do orquestrador
│   ├── policies/               git, database, secrets, production, permissions
│   ├── config/routing.toml     regras determinísticas de decisão
│   └── prompts/
├── agents/<papel>/AGENT.md     definição genérica de cada subagente
├── skills/<nome>/SKILL.md      skills genéricas
├── workflows/*.yaml            feature, bugfix, refactor, hotfix
├── state/                      specs, tickets, reviews e runs (sem contexto ativo)
├── docs/                       plano de arquitetura
└── contexts/<nome>/            (fora do Git) cada contexto é um repositório próprio
    ├── context.toml
    ├── policies/  shared/  agents/  reference/  skills/
    └── demandas/               state dir do contexto
```

---

## 11. Segurança

O princípio é **nunca deixar o modelo ser a última barreira**:

| Camada | Como funciona |
|---|---|
| **Confirmação obrigatória** | Regras `ask` (em `[policies]` ou no `context.toml`) sempre pedem sua aprovação — vencem qualquer `allow`. Ex.: um contexto pode exigir aprovação para todo `git`, todo SQL e todo comentário em card |
| **Bloqueios reais** | `[policies].deny` vira regra de permissão do Claude Code: force push, `reset --hard`, `clean -f` e leitura de `.env` são negados para o chat e para todos os subagentes |
| **Aprovação humana pontual** | O fluxo roda sozinho; as ações que o contexto trava (ex.: commit, push, SQL de escrita, escrita em ambiente) são propostas pelo agente e só executadas com o seu OK |
| **Validadores** | Operações liberadas com risco (ex.: SQL de leitura) passam por um script em `contexts/<nome>/tools/` que recusa o que não for permitido e registra log — o LLM nunca é a última barreira |
| **Ferramentas por agente** | `disallowed_tools` remove ferramentas de um subagente (ex.: só o orquestrador comenta em cards) |
| **Prompts de permissão** | O que não está em `allow` segue o modo de permissão do chat (no modo padrão, pede confirmação). Os subagentes compartilham as permissões da sessão |
| **Policies nas instruções** | Todo agente recebe as policies genéricas e as do contexto |
| **Contextos fora do Git** | `contexts/*/` é ignorado; o `doctor` dá **erro** se um contexto ativo deixar de estar no `.gitignore` |
| **Segredos** | Nunca em arquivo, log, spec ou review; o `doctor` só verifica se as variáveis existem, sem ler o valor |

---

## 12. Solução de problemas

| Sintoma | Causa provável | Solução |
|---|---|---|
| `does not support this model; version 2.1.280 or newer is required` | CLI `claude` desatualizado | `claude update` (o app desktop atualiza sozinho). O `doctor` avisa |
| O orquestrador não encontra um agente | Chat aberto antes do `apply` | Abra um chat novo na pasta do AI-DEV |
| Agente com nome antigo | Idem | `python aidev.py apply` + chat novo |
| `nome ... inválido` / `reservado` | Nome com maiúscula/espaço, ou igual a um agente do Claude Code (`plan`, `explore`…) | Ajuste `name` no `aidev.config.toml` |
| `marcador {{agent:x}} usa papel desconhecido` | Erro de digitação no papel | Use um dos papéis listados na mensagem |
| `exige API key, que ainda não é suportada` | Agente configurado com GPT/JEV | Escolha um modelo `anthropic` |
| `settings.local.json não é JSON válido` | Edição manual quebrou o arquivo | Corrija ou apague o arquivo e rode `apply` |
| `variável ... não definida` | Variável exigida pelo contexto não existe | Defina como variável de usuário e reabra o Claude Code |
| `MCP figma precisa de autenticação` | OAuth do Figma ainda não feito | No Claude Code: `/mcp` → figma → Authenticate |
| `MCP x também está registrado como 'y'` | O mesmo servidor existe em outro escopo (ex.: conector do claude.ai, plugin) | Mantenha um só para as ferramentas não aparecerem em dobro |
| `npx não encontrado` | Node.js ausente — os MCPs locais rodam via `npx` | Instale o Node.js LTS |
| `MCP 'x' não registrado` | Servidor exigido pelo contexto não está no Claude Code | Rode o comando que o `doctor` mostra (vem de `[mcp.x].add` no `context.toml`) |
| `MCP x registrado, mas com status ...` | Servidor com falha ou pedindo autenticação | `claude mcp list` para ver o detalhe; autentique ou corrija o registro |
| `contexto 'x' não encontrado` | Config aponta para um contexto não clonado nesta máquina | Clone em `contexts/x/`, ou rode `setup` e escolha outro/nenhum/novo |
| Subagente não lê um repositório | Pasta fora das pastas liberadas | Adicione em `[workspace].project_dirs` (ou `additional_dirs` do contexto) e rode `apply` |

---

## 13. Limitações e próximos passos

**Limitações atuais**

- Subagentes escolhem o modelo só por apelido e **herdam o effort do chat** — não dá para ter
  "Sonnet High no codificador e Opus Medium no revisor" ao mesmo tempo.
- O orquestrador recebe apenas a **mensagem final** de cada subagente; por isso os agentes
  devem colocar todo o resultado nela.
- Modelos não-Anthropic (GPT, JEV) exigem API key e ainda não são suportados.
- Os workflows em `workflows/*.yaml` orientam o orquestrador, mas ainda não são executados
  por um motor próprio.

**Fases do plano**

| Fase | Status |
|---|---|
| 1. Organizar agentes, skills, specs e tickets | ✅ |
| 2. Comunicação estruturada (JSON em cada agente) | ✅ nas instruções |
| 3. Orquestração automática num chat só | ✅ via subagentes nativos |
| 4. Decisão determinística → JEV | regras determinísticas ativas; JEV desligado |
| 5. Interface visual | a fazer |
| 6. Observabilidade (tokens, custo, retries, taxa de aprovação) | a fazer |
