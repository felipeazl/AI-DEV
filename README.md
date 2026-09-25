# AiDW

Ambiente de **desenvolvimento agêntico**: você conversa com um único chat, o orquestrador, e ele
planeja o trabalho, delega a agentes especializados (codificador, revisor, API, documentador…),
consolida os resultados e só para para pedir sua aprovação nos pontos críticos.

O AiDW junta o que funcionava melhor em dois projetos anteriores:

| Veio do **Orquestrador/Agents** (`~/.claude/Agents`) | Veio do **AI-DEV** (`C:\AI-DEV`) |
|---|---|
| Cada agente roda **headless, um processo por tarefa**, com as instruções dele e nada da conversa | Configuração **declarativa** (`aidw.config.toml`) e um script que gera todo o resto |
| **Modelo e effort passados a cada chamada**, com o cabeçalho `## Agente - modelo Effort` na resposta | **Contextos** de trabalho (regras da empresa num repositório Git separado) |
| Tarefa entregue por arquivo/stdin, imune a aspas e tamanho | Skills, policies, workflows, contratos de saída em JSON e `metricas.md` |
| Personas ricas por agente (hoje num contexto privado) | Wizard, `apply` idempotente, `doctor`, MCPs com gatilhos |

O que muda em relação ao AI-DEV: **não é mais multimodelo**. Uma instalação roda **só no Claude**
ou **só no Codex** — o orquestrador e todos os agentes no mesmo provedor.

> **O AiDW substitui o AI-DEV** neste repositório; o histórico do AI-DEV foi preservado. Quem vem
> do AI-DEV: clone de novo (ou `git pull`), mova o contexto para `contexts/<nome>/`, troque os
> caminhos `C:\AI-DEV\contexts\<nome>` do `context.toml` por `{{context}}` e rode o setup — o
> `aidev.config.toml` virou `aidw.config.toml`.

---

## Sumário

1. [Como funciona](#1-como-funciona)
2. [Instalação](#2-instalação)
3. [Configuração](#3-configuração)
4. [Como usar](#4-como-usar)
5. [Comandos](#5-comandos)
6. [O que o `apply` gera](#6-o-que-o-apply-gera)
7. [Claude × Codex](#7-claude--codex)
8. [Estendendo](#8-estendendo)
9. [Segurança](#9-segurança)
10. [Solução de problemas](#10-solução-de-problemas)

---

## 1. Como funciona

```text
                         ┌──────────────────────────────────┐
  Você ──── chat ──────► │ orquestrador (Opus · effort high) │  o chat aberto na pasta do AiDW
                         │ entende · planeja · decide effort │
                         └───────────────┬──────────────────┘
                                         │ subagente nativo (Agent / spawn_agent) — ou aidw.py delegate
         ┌──────────────┬────────────────┼───────────────┬──────────────┐
         ▼              ▼                ▼               ▼              ▼
    codificador      revisor            api             qa        documentador
      (Opus)        (Sonnet)          (Sonnet)     (desligado)       (Haiku)
```

- **Um chat, vários agentes — nativos nos dois provedores.** Por padrão
  (`[delegation] mode = "native"`) os agentes são **subagentes nativos**: no Claude, a ferramenta
  `Agent` com os arquivos de `.claude/agents/`; no Codex, o `spawn_agent` do multi-agente. Cada um
  roda com a definição dele, o modelo dele e o **effort que o orquestrador escolheu para a
  tarefa**. O agente não vê a conversa e não fala com você; perguntas e aprovações voltam para o
  orquestrador. O modo `headless` (um processo `claude -p`/`codex exec` por tarefa, via
  `aidw.py delegate`) continua disponível — seção 7.
- **Effort por tarefa.** O orquestrador classifica cada tarefa num nível (`trivial`, `simples`,
  `padrao`, `complexa`, `critica`) e passa o effort da tabela para o papel que vai executar. Sobe
  um nível quando o agente falha duas vezes ou a revisão acha CRITICO; desce um nível em tarefas
  de acompanhamento. O **modelo** de cada agente é fixo e só muda quando você pede.
- **Modelos padrão:** Opus no orquestrador e no codificador, Sonnet no revisor e no api, Haiku
  no documentador. No Codex valem os equivalentes por tier (seção 3.2).
- **Nomes customizáveis.** Cada papel tem um nome padrão; você pode dar outro (com acento e
  espaço, ex.: `"Zé Revisor"`). O nome aparece nas respostas; o identificador (`ze-revisor`) é o
  que vai nos comandos.
- **Fluxo com especificação e aprovação humana onde importa.** Pedido → spec → tickets →
  implementação → testes → revisão ⇄ correção → documentação → revisão final. Ações travadas
  (commit, push, SQL de escrita, escrita em ambiente) passam por você.
- **Cada delegação é medida.** Depois de cada subagente, o orquestrador roda
  `python aidw.py record`, que grava uma linha no `metricas.md` da demanda (tokens, duração,
  limites do plano) e imprime o cabeçalho e o resumo que ele mostra. No modo headless, o
  `delegate` faz isso sozinho e ainda guarda a resposta completa e o custo.

### Papéis

| Papel | Nome padrão | Modelo padrão | Effort padrão | Função |
|---|---|---|---|---|
| `orchestrator` | `orquestrador` | Opus / top | high | O chat principal. Planeja, delega, decide o effort, consolida, pede aprovação |
| `coder` | `codificador` | Opus / top | medium | Implementa um ticket por vez; build, testes, lint |
| `reviewer` | `revisor` | Sonnet / mid | high | Revisa o diff contra spec/ticket; achados com severidade; não altera código |
| `api-db` | `api` | Sonnet / mid | medium | Consulta APIs, banco e logs; propõe escritas e só executa com OK |
| `qa` | `qa` | Sonnet / mid | medium | Testes e critérios de aceite (desligado por padrão) |
| `documenter` | `documentador` | Haiku / fast | — | README, ARCHITECTURE, changelog, work items |

---

## 2. Instalação

### Pré-requisitos

O setup verifica e oferece instalar o que faltar:

| Ferramenta | Para quê | Instalação (Windows) |
|---|---|---|
| **Python 3.11+** | o `aidw.py` (só biblioteca padrão) | `winget install Python.Python.3.13` (o `setup.ps1` oferece) |
| **Git** | repositórios e o próprio AiDW | `winget install Git.Git` |
| **Node.js LTS** | MCPs locais via `npx` | `winget install OpenJS.NodeJS.LTS` |
| **Claude Code** *ou* **Codex CLI** | roda o orquestrador e os agentes | `irm https://claude.ai/install.ps1 \| iex` · `npm i -g @openai/codex` |

Não é preciso API key: tudo roda com o login do CLI (assinatura Claude ou conta ChatGPT).

### Passo a passo

```powershell
cd C:\AiDW
.\setup.ps1                      # Windows  (Linux/macOS: ./setup.sh)
```

O setup, em ordem:

1. garante o Python (o `setup.ps1` instala pelo winget se faltar);
2. roda o **wizard**, se ainda não houver `aidw.config.toml` (seção 3.1);
3. verifica **Git, Node e o CLI do provedor** e oferece instalar o que faltar;
4. roda o **`apply`**, que gera todo o ambiente;
5. oferece registrar os **MCPs exigidos pelo contexto** (ex.: `ado`);
6. no Codex, oferece marcar a pasta como **projeto confiável**;
7. roda o **`doctor`**.

Depois abra o orquestrador:

- **Claude:** app desktop (aba Code) na pasta `C:\AiDW`, ou `python aidw.py chat`.
- **Codex:** `python aidw.py chat`, ou o app do Codex na pasta `C:\AiDW` com o projeto confiável.

No primeiro uso, autentique os MCPs com OAuth (Figma): no Claude, `/mcp` → figma → Authenticate;
no Codex, `codex mcp login figma`.

### Contexto de trabalho

Regras de uma empresa ou squad ficam num **contexto**: `contexts/<nome>/`, um repositório Git
**próprio e privado**, ignorado pelo Git do AiDW. Clone o seu antes do setup:

```bash
git clone <url-do-contexto> C:/AiDW/contexts/<nome>
```

Sem contexto, o AiDW funciona com as regras genéricas. O wizard também cria um contexto novo.

### Outra máquina

Clone o AiDW, clone o contexto e rode o setup. O `aidw.config.toml` vem no clone, então o wizard
não roda; os arquivos gerados não são versionados — cada máquina gera os seus.

---

## 3. Configuração

Depois de editar qualquer fonte, rode `python aidw.py apply` e **abra um chat novo**.

### 3.1 `aidw.config.toml`

```toml
[provider]
name = "claude"            # "claude" | "codex" — um provedor por vez

[delegation]
mode = "native"            # "native" = subagentes do provedor · "headless" = aidw.py delegate

[workspace]
project_dirs = ["C:/Projetos"]   # liberadas para o orquestrador e todos os agentes

[mcp]
enabled = ["playwright", "chrome-devtools", "figma", "context7"]

[context]
active = "meu-trabalho"    # pasta em contexts/ ("" = nenhum)

[policies]
deny = ["Bash(git push --force *)", "Read(**/.env)"]   # bloqueado sempre
ask = []                                                # sempre pede OK

[agents.reviewer]
name = "Zé Revisor"        # opcional; sem ele, vale o nome padrão
enabled = true
# model = "opus"           # opcional; sem ele, vale o tier padrão do papel
effort = "high"            # effort padrão; o orquestrador escolhe o de cada tarefa
skills = ["code-review"]
```

- **Trocar de provedor** é mudar `name` e rodar `apply`: os arquivos do provedor anterior são
  removidos e os do novo, gerados. Um `model` de outro provedor é ignorado com aviso (vale o
  tier padrão do papel).
- `python aidw.py configure` reescreve o arquivo inteiro; para ajustes pontuais, edite à mão.

### 3.2 `config/models.toml` — catálogo

Cada modelo tem `provider`, `model_id`, `tiers` (`top`/`mid`/`fast`) e os `efforts` aceitos. O
padrão de cada papel vem do tier: no Claude, top = Opus, mid = Sonnet, fast = Haiku. No Codex,
vale o primeiro modelo do tier **liberado para a sua conta** (o `doctor` confere em
`~/.codex/models_cache.json`). Na conta atual: top e mid = `gpt-6-luna` (o `gpt-6-sol` não está
liberado), fast = `gpt-5.6-luna`.

### 3.3 `orchestrator/config/routing.toml` — decisões

- **`[rules]`**: cada agente termina com `"state": "<chave>"`; o orquestrador aplica a ação.
- **`[effort.levels.<nível>]`**: quando usar o nível (`when`) e o effort de cada papel nele.
  É aqui que se calibra custo × qualidade; o `metricas.md` de cada demanda traz os números reais.
- **`[effort.escalate]`**: quando subir e quando descer um nível.

### 3.4 `config/mcp.toml` — MCPs

Catálogo com `use_when`, `triggers` e os papéis que podem usar cada servidor. O orquestrador
escolhe os MCPs de cada tarefa pelos gatilhos, e **cada agente só recebe os servidores do papel
dele**.

### 3.5 `contexts/<nome>/context.toml`

Mesmo formato do AI-DEV: `state_dir`, `additional_dirs`, `required_env`, `required_mcp`
(`add` para Claude e `add_codex` para Codex), `[permissions]` (`allow`, `ask`, `git_ask`, `deny`),
`[systems.*]` com build/teste prontos e `[agents.<papel>]` com `include`, `reference`, `skills` e
`disallowed_tools`. Nas strings, `{{context}}` é a pasta do contexto e `{{root}}` a raiz do AiDW
— assim o contexto funciona em qualquer pasta. Nos `.md`, `{{agent:<papel>}}` vira o nome
configurado do agente.

---

## 4. Como usar

Peça como pediria a um tech lead:

```text
Implementar a US https://dev.azure.com/<org>/<projeto>/_workitems/edit/1234
Corrigir o bug 5678 — o login falha em QA quando o token expira
Revisar a branch feature/novo-relatorio contra a US 1234
Gerar um dado de teste em QA para o cenário de cancelamento
```

Cada resultado aparece com o cabeçalho e o resumo do `delegate`:

```text
## Codificador - claude-opus-5-5 Medium
Codificador (padrao) | Claude Opus 5.5 | effort medium | 412.330 tokens entrada + 9.802 saída | 184 s | US$ 1,12 | Claude 5h 31% (reinicia 15:40) · semana 9% (reinicia 29/09 12:00)
```

| Você quer | Diga |
|---|---|
| Saber onde está o fluxo | "Em que etapa estamos?" |
| Outro modelo numa tarefa | "Use Sonnet no codificador para este ticket" |
| Mais ou menos effort | "Esse ticket é simples, use effort low" |
| Pular a orquestração | "Só me responda, sem delegar" |
| Mexer no próprio AiDW | "Manutenção do AiDW: …" |

---

## 5. Comandos

| Comando | O que faz |
|---|---|
| `.\setup.ps1` / `./setup.sh` | Python + `python aidw.py setup` |
| `python aidw.py setup [--reconfigure] [--skip-tools]` | Pré-requisitos, wizard, apply, MCPs, doctor |
| `python aidw.py configure [--defaults --provider codex]` | Só o wizard (ou a config padrão) |
| `python aidw.py apply [--dry-run]` | Gera o ambiente a partir da config (idempotente) |
| `python aidw.py doctor` | Verifica CLI, login, modelos da conta, contexto, variáveis, MCPs e pastas |
| `python aidw.py show` | Nome, exibição, papel, modelo e effort de cada agente |
| `python aidw.py chat` | Abre o orquestrador no CLI do provedor |
| `python aidw.py record --agent <subagente> --level <nível> --label <x> --demand <pasta> --state <s> (--tokens N --tool-uses N --duration-ms N \| --codex-task <task_name>)` | Registra uma delegação nativa no `metricas.md` e imprime cabeçalho e resumo (usado pelo orquestrador) |
| `python aidw.py delegate --agent <nome> --effort <e> --level <nível> --task <arq> --demand <pasta> [--label x] [--model k]` | Roda um agente headless para uma tarefa (modo headless, ou fallback) |

`AIDW_DEBUG=1` no `delegate` grava o comando, os eventos e o stderr em `debug-<agente>-<hora>.log`
na pasta da demanda.

---

## 6. O que o `apply` gera

Nada disso é versionado.

| Arquivo | Provedor | Conteúdo |
|---|---|---|
| `.aidw/agents/<nome>.md` | ambos | Definição de cada agente: `AGENT.md` + runtime + skills + MCPs + systems + referências + policies + contexto |
| `.aidw/runtime.json` | ambos | Configuração resolvida |
| `CLAUDE.md` | Claude | O orquestrador |
| `.claude/agents/<nome>[-<effort>].md` | Claude, native | Subagentes nativos: um por agente e por effort usado na tabela de níveis (`codificador-low`, `codificador`, `codificador-high`…), com modelo, effort, `omitClaudeMd`, ferramentas e skills |
| `.aidw/claude-agents.json` | Claude | Os agentes para `claude -p --agents … --agent <nome>` (modo headless e fallback) |
| `.claude/settings.local.json` | Claude | Modelo/effort do chat, allow/ask/deny, pastas, variáveis, MCPs aprovados. Chaves manuais são preservadas |
| `.claude/skills/`, `.mcp.json` | Claude | Links das skills; MCPs do projeto |
| `AGENTS.md` | Codex | O orquestrador |
| `.codex/config.toml` | Codex | Modelo/effort, sandbox com rede, pastas graváveis, MCPs, variáveis; no native, `multi_agent_v2` |
| `.codex/agents/<nome>.toml` | Codex, native | Papéis nativos (`developer_instructions`, modelo, effort) — usados quando a ferramenta de spawn aceita papel |
| `.codex/rules/aidw.rules` | Codex | `deny` → `forbidden`, `ask`/`git_ask` → `prompt`, delegate liberado |
| `.agents/skills/` | Codex | Links das skills |

Garantias: valida tudo antes de gravar; sem mudança na config, nenhuma escrita; remove o que
sobrou (agente renomeado, provedor trocado) — só arquivos marcados como gerados.

---

## 7. Claude × Codex

### Modo native (padrão)

| | Claude | Codex |
|---|---|---|
| Como o orquestrador aciona | ferramenta `Agent`, `subagent_type` = variante da tabela de effort | `spawn_agent(task_name, model, reasoning_effort, message)` (multi-agente v2) |
| Effort por tarefa | o Claude fixa o effort no arquivo do subagente, então há uma variante por effort (`revisor-low`, `revisor`…) e o orquestrador escolhe a variante | passado no próprio spawn |
| Instruções do agente | o arquivo do subagente; `omitClaudeMd` isola o CLAUDE.md do orquestrador | o spawn não aceita papel: a mensagem aponta para `.aidw/agents/<nome>.md`. O subagente **herda o AGENTS.md** do orquestrador; um aviso no topo manda ignorá-lo (funciona, mas custa ~8 mil tokens por spawn) |
| Ferramentas, sandbox e MCPs | por papel (`tools`, `disallowedTools`) | herdados do orquestrador; a regra de cada papel vem da definição |
| Permissões | as do chat; os prompts chegam a você | as do chat e as rules do projeto |
| Métricas (`record`) | `subagent_tokens`, `tool_uses`, `duration_ms` do resultado (sem custo, sem entrada × saída) | tokens reais de entrada e saída lidos da sessão do subagente (`--codex-task`) |

No Codex, o `spawn_agent` exige `multi_agent_v2` (ligado pelo `.codex/config.toml` e pelo
`python aidw.py chat`). O `doctor` avisa se a versão instalada não tiver.

### Modo headless

| | Claude | Codex |
|---|---|---|
| Agente headless | `claude -p --agents .aidw/claude-agents.json --agent <nome> --model … --effort …` | `codex exec -m … -c model_reasoning_effort=…` com a definição do agente no stdin |
| Instruções do orquestrador fora do agente | `claudeMdExcludes` com glob (`**/AiDW/CLAUDE.md`) | `project_doc_max_bytes=0` |
| Ferramentas por papel | lista `tools`/`disallowedTools` do agente | sandbox `workspace-write`: grava só na demanda (revisor, api) ou também nos projetos (codificador, documentador); MCPs só do papel; `disabled_tools` do contexto |
| Ações travadas | `ask` do settings → negadas no headless, voltam em `denials` | `prompt` nas rules → recusadas, voltam em `denials`; o sandbox também protege o `.git` |
| Custo na métrica | US$ por chamada | "assinatura" (sem custo por chamada) |
| Limites no resumo | janelas de 5 h e semana da assinatura | janelas do plano ChatGPT (sessões em `~/.codex`) |

Limitações do Codex, em comparação com o Claude:

- O sandbox deixa o `.git` só leitura: os agentes Codex **não fazem `git add`, `worktree add` nem
  commit**. Esses passos ficam com o orquestrador ou com você.
- Regras de prefixo não aceitam curinga no meio: `git -C <pasta> commit` não casa com a regra
  `git commit` (o sandbox bloqueia do mesmo jeito, pelo `.git` só leitura).
- O sandbox do Windows roda os comandos com outra identidade (`CodexSandboxOnline`), e o git
  recusaria os repositórios ("dubious ownership"). O AiDW libera `safe.directory` **só para as
  pastas do AiDW e dos projetos**, por variáveis `GIT_CONFIG_*` nos comandos do Codex — o
  `.gitconfig` não é alterado.
- Na primeira execução, os MCPs via `npx` baixam pacotes e a chamada demora mais.

---

## 8. Estendendo

- **Nova skill:** `skills/<nome>/SKILL.md` (frontmatter `name` e `description`) e o nome em
  `skills = [...]` do agente. `apply`.
- **Novo agente:** `agents/<papel>/AGENT.md` (frontmatter `description`, opcional `tools` e
  `disallowedTools`; corpo com ROLE, INPUT, PROCESS, OUTPUT com `state`), um bloco
  `[agents.<papel>]` no `aidw.config.toml`, a entrada do papel em `DEFAULT_AGENTS`/`RUN_PROFILE`
  do `aidw.py` e o effort do papel em cada nível do `routing.toml`. `apply`.
- **Novo modelo:** uma tabela em `config/models.toml` com provider, `model_id`, tiers e efforts.
- **Nova policy:** um `.md` em `orchestrator/policies/` (todos os contextos) ou em
  `contexts/<nome>/policies/`. Para bloqueio real, acrescente a regra em `[policies].deny`.

---

## 9. Segurança

O princípio: **o modelo nunca é a última barreira.**

| Camada | Como funciona |
|---|---|
| Bloqueios | `deny` vira regra do CLI (Claude) ou `forbidden` (Codex): force push, `reset --hard`, `clean -f`, leitura de `.env` |
| Confirmação | `ask`/`git_ask` sempre pedem OK no chat e são recusados nos agentes headless; o agente propõe e o orquestrador pergunta |
| Escopo por agente | Ferramentas, MCPs e pastas graváveis por papel; ferramentas bloqueadas por contexto (ex.: só o orquestrador comenta em card) |
| Validadores | Operações liberadas com risco passam por scripts do contexto (ex.: SQL só leitura com `ROLLBACK`) |
| Contextos fora do Git | `contexts/*/` ignorado; o `doctor` dá erro se deixar de estar |
| Segredos | Nunca em arquivo, log, spec ou review; o `doctor` só verifica se as variáveis existem |

---

## 10. Solução de problemas

| Sintoma | Causa provável | Solução |
|---|---|---|
| O agente segue regras do orquestrador | CLAUDE.md da raiz carregado no agente | Já tratado com `claudeMdExcludes` em glob; caminho absoluto não funciona no Claude Code |
| `dubious ownership` num agente Codex | Repositório fora de `project_dirs`/`additional_dirs` | Adicione a pasta à config e rode `apply` |
| MCP "Pending approval" no `doctor` (Claude) | Projeto ainda não aberto no Claude Code | Abra o Claude Code na raiz e aprove, ou ignore: `enabledMcpjsonServers` já aprova para os agentes |
| `MCP figma precisa de autenticação` | OAuth não feito | Claude: `/mcp` → figma → Authenticate · Codex: `codex mcp login figma` |
| O orquestrador Codex não mostra o resultado | O comando ainda rodava quando ele respondeu | Leia `resultado-<agente>-<label>.json` na demanda (a instrução já manda esperar) |
| `modelo … não está liberado para esta conta` | Modelo do Codex fora do plano | Tire o `model` do agente (vale o tier) ou escolha um liberado |
| Nome de agente inválido/reservado | Colide com agente do CLI (`plan`, `explore`, `default`…) | Escolha outro `name` |
| Agente com nome antigo | Chat aberto antes do `apply` | `apply` + chat novo |
