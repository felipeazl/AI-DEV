# AiDW

Ambiente de **desenvolvimento agêntico**. Você conversa com um único chat — o **orquestrador** — e ele entende o
pedido, planeja, delega a agentes especializados (codificador, revisor, documentador…), tria as revisões, repete
até ficar pronto e para para você só nos pontos que importam: dúvida real, ação travada e a revisão final.

O AiDW é **independente de contexto**: o fluxo, os comandos, os agentes e as proteções são os mesmos em qualquer
máquina. Um **contexto** (as regras de uma empresa ou squad, num repositório Git privado) melhora as entregas —
sistemas, comandos de build, convenções, políticas — sem mudar o nome de nada.

---

## Sumário

1. [Como funciona](#1-como-funciona)
2. [Instalação](#2-instalação)
3. [Uso no dia a dia](#3-uso-no-dia-a-dia)
4. [Comandos](#4-comandos)
5. [Agentes](#5-agentes)
6. [Skills](#6-skills)
7. [Contextos](#7-contextos)
8. [Demandas e worktrees](#8-demandas-e-worktrees)
9. [Configuração](#9-configuração)
10. [O que é gerado](#10-o-que-é-gerado)
11. [Claude × Codex](#11-claude--codex)
12. [Segurança](#12-segurança)
13. [Estendendo](#13-estendendo)
14. [Solução de problemas](#14-solução-de-problemas)

---

## 1. Como funciona

```text
 Você ── /aidw:orquestrar <demanda> ──► orquestrador (Opus · effort high)
                                        │ detecta o projeto · abre ou retoma a demanda
                                        │ cria o worktree da demanda e entra nele
                                        ▼
   entender → plano (to-spec) → revisão do plano → tickets → implementação → preparar revisão
            → revisão ⇄ correção (+ bugs/segurança sob demanda) → documentação → revisão final (você)
                                        │
          ┌──────────────┬──────────────┼──────────────┬──────────────┬──────────────┐
          ▼              ▼              ▼              ▼              ▼              ▼
     codificador      revisor          api        documentador      bugs        seguranca
```

- **Um chat, vários agentes.** Os agentes são subagentes nativos do provedor (a ferramenta `Agent` no Claude,
  `spawn_agent` no Codex). Cada um recebe uma tarefa num arquivo, não vê a conversa e devolve um JSON com um
  `state`; o orquestrador decide o próximo passo pelas regras de `orchestrator/config/routing.toml`.
- **Effort por tarefa.** O orquestrador classifica a demanda num nível (`trivial`, `simples`, `padrao`,
  `complexa`, `critica`) e usa o effort — e, nos níveis altos, o modelo — da tabela para cada papel. O modelo de
  cada agente só muda quando você pede.
- **Você só entra quando precisa:** ações travadas (commit, push, SQL de escrita…), dúvida real ou mais de um
  caminho válido, algo fora do plano, e **uma** revisão final com tudo junto.
- **Cada demanda tem um worktree** em `C:\wt\<repo>\<demanda>` (configurável): o seu working copy nunca é tocado
  pelos agentes.
- **Tudo é medido.** Cada delegação vira uma linha no `metricas.md` da demanda (agente, nível, modelo, effort,
  tokens, duração) e o estado da demanda fica no `demand.json` — dá para fechar o chat e retomar depois.

---

## 2. Instalação

### Pré-requisitos

| Ferramenta | Para quê | Instalação (Windows) |
|---|---|---|
| **Python 3.11+** | o `aidw.py` (só biblioteca padrão) | `winget install Python.Python.3.13` (o `setup.ps1` oferece) |
| **Git** | repositórios, worktrees e o próprio AiDW | `winget install Git.Git` |
| **Node.js LTS** | MCPs locais via `npx` | `winget install OpenJS.NodeJS.LTS` |
| **Claude Code** e/ou **Codex CLI** | rodam o orquestrador e os agentes (o do provedor ativo é obrigatório) | `irm https://claude.ai/install.ps1 \| iex` · `npm i -g @openai/codex` |

Não é preciso API key: tudo roda com o login do CLI (assinatura Claude ou conta ChatGPT).

### Passo a passo

```powershell
cd C:\AiDW
.\setup.ps1                      # Linux/macOS: ./setup.sh
python aidw.py install           # Claude: AiDW disponível em qualquer pasta
.\doctor.ps1                     # confere tudo e diz se está PRONTO
```

O **setup** garante o Python, roda o wizard (se ainda não há `aidw.config.toml`), confere Git, Node, Claude
Code e Codex (e o login), cria as pastas que faltam (`contexts/`, estado das demandas, raiz dos worktrees), roda o
`apply`, oferece registrar os MCPs que o contexto exige e termina com o `doctor`.

O **install** (Claude) gera o plugin **`aidw`** e o instala no Claude Code — CLI e app desktop —, e acrescenta ao
`~/.claude/settings.json` as regras globais do AiDW (seção 12). Depois disso, em qualquer pasta, `/aidw:orquestrar`.

### Contexto

Clone o repositório privado do seu contexto em `contexts/<nome>/` antes do setup (ou crie um com
`/aidw:contexto-criar`) e ative com `/aidw:contexto-usar <nome>`. Sem contexto, o AiDW funciona com as regras
genéricas.

### Outra máquina

Clone o AiDW, clone o contexto e rode o setup e o install. A configuração (`aidw.config.toml`) e os arquivos
gerados não são versionados: cada máquina tem os seus — o setup cria a configuração pelo wizard, e o
`aidw.config.example.toml` versionado é o modelo genérico.

---

## 3. Uso no dia a dia

### Claude (qualquer pasta)

Abra um chat — de preferência na pasta do repositório — e chame:

```text
/aidw:orquestrar 1234              ← a demanda (id do card, link ou descrição)
/aidw:orquestrar                   ← sem argumento: retoma a demanda desta pasta (ou pergunta qual)
/aidw:sair                         ← grava onde parou e devolve o chat ao modo normal
```

O orquestrador detecta o projeto, abre a demanda (ou **retoma da etapa gravada**), cria o worktree, entra nele e
segue o fluxo. Para ver tudo o que está em andamento e voltar a uma demanda pelo terminal:

```text
python aidw.py status                  ← instalação, demandas ativas (etapa, worktree, alterações) e pendências
python aidw.py open --demand 1234      ← abre o Claude no worktree da demanda já chamando /aidw:orquestrar
```

Peça como pediria a um tech lead:

| Você quer | Diga |
|---|---|
| Saber onde está | "Em que etapa estamos?" |
| Outro modelo numa tarefa | "Use Sonnet no codificador para este ticket" |
| Mais ou menos effort | "Esse ticket é simples, use effort low" |
| Pular a orquestração | "Só me responda, sem delegar" |
| Mexer no próprio AiDW | "Manutenção do AiDW: …" |

Cada resultado de agente aparece com o cabeçalho e o resumo medidos:

```text
## Codificador - claude-opus-5-5 Medium
Codificador (padrao) | Claude Opus 5.5 | effort medium | 67.448 tokens | 156 s
```

### Codex (qualquer pasta)

Instale com `python aidw.py install --provider codex` e **aprove os hooks uma vez**: rode `codex --profile aidw`
num terminal e escolha "Trust all and continue" (o `doctor` mostra se falta). Depois:

```text
python aidw.py open --provider codex --demand us-1234   ← abre o Codex no worktree da demanda, com o perfil aidw
codex --profile aidw                                    ← ou abra você mesmo, na pasta do repositório
$aidw-orquestrar 1234                                   ← mesmo fluxo do Claude
$aidw-sair
```

O perfil `aidw` deixa a raiz dos worktrees gravável e liga o multi-agente. Como o Codex não tem `EnterWorktree`,
o orquestrador trabalha pelo caminho absoluto do worktree; o `worktree create` pede aprovação (o sandbox deixa o
`.git` só leitura).

### Modo projeto (Claude ou Codex)

O chat aberto na raiz do AiDW é o orquestrador (via `CLAUDE.md`/`AGENTS.md` gerados pelo `apply`), ou
`python aidw.py chat`. Continua funcionando como alternativa (seção 11).

---

## 4. Comandos

### No chat (skills do plugin `aidw`)

| Comando | O que faz |
|---|---|
| `/aidw:orquestrar [demanda]` | Assume o chat como orquestrador: detecta o projeto, abre ou retoma a demanda, cria o worktree e conduz o fluxo até a revisão final. Só roda quando você chama |
| `/aidw:sair` | Grava a etapa e o próximo passo da demanda (`paused`) e volta o chat ao normal |
| `/aidw:contexto-listar` | Mostra os contextos, qual está ativo, repositório (git próprio, remoto só pelo host), sistemas e se o plugin está instalado |
| `/aidw:contexto-usar <nome>` | Valida e ativa um contexto (regenera o ambiente e o plugin com as regras dele); avisa se há demanda ativa |
| `/aidw:contexto-criar` | Cria um contexto novo: análise criteriosa dos repositórios indicados e **no mínimo 10 perguntas**, gera e valida (seção 7) |

### Linha de comando (`python aidw.py …`)

| Comando | O que faz |
|---|---|
| `setup [--reconfigure] [--skip-tools]` | Pré-requisitos, wizard, pastas, apply, MCPs e doctor (é o que o `setup.ps1` chama) |
| `configure [--defaults --provider codex]` | Só o wizard; reescreve o `aidw.config.toml` |
| `apply [--dry-run]` | Gera o modo projeto a partir da config (idempotente) |
| `install [--provider claude\|codex\|all] [--dry-run] [--force] [--mcp]` | Claude (padrão): plugin `aidw` e regras globais; `--mcp` registra os MCPs do catálogo. Codex: skills `aidw-*` em `~/.agents/skills`, agentes `aidw-*` em `~/.codex/agents`, `aidw.rules`, hooks no `hooks.json` (merge) e o perfil `aidw` |
| `uninstall [--provider claude\|codex\|all] [--dry-run]` | Remove só o que o `install` acrescentou (padrão: os dois) |
| `status [--json]` | Visão rápida, sem chamar os CLIs: contexto, instalação (Claude e Codex), demandas ativas com etapa e situação do worktree, e o que pede atenção (worktree de demanda concluída, órfão, plugin de outro contexto) |
| `open [--provider claude\|codex] [--demand <id> \| --path <pasta>] [--no-orchestrate] [--print]` | Abre o CLI na pasta; com `--demand` (`1234` acha `us-1234`), no worktree dela, com a pasta da demanda liberada e já chamando o orquestrador (`/aidw:orquestrar <id>` ou `$aidw-orquestrar <id>`); o Codex com `--profile aidw` |
| `doctor` | Verifica núcleo, os dois CLIs e o login, contexto, variáveis, MCPs, pastas, instalação global e ambiente gerado; termina com **PRONTO** ou **NÃO PRONTO** |
| `show` | Nome, papel, modelo e effort de cada agente |
| `chat` | Abre o orquestrador do modo projeto no CLI do provedor |
| `context list` · `check <nome>` · `use [<nome>]` · `create <nome> --description d` | Contextos: lista, valida, ativa (troca só a linha `active`), cria a estrutura com git próprio |
| `project detect [--path p] [--json]` | Repositório principal, sistema do contexto e demanda de uma pasta |
| `demand set <id> [--step S] [--status active\|paused\|done] [--title t] [--note n]` · `show <id>` · `list [--active]` | Estado da demanda para retomar (`demand.json`, com histórico das etapas) |
| `worktree create --repo <pasta> --demand <id> [--slug s] [--base b]` | Worktree da demanda, branch `<prefixo><número>-<slug>`, junctions de `packages`/`node_modules` e das pastas vizinhas do `worktree_link` do sistema (idempotente) |
| `worktree list` · `inspect <id>` · `remove <id>` · `cleanup` | Situação dos worktrees; `remove` só com worktree limpo e publicado (mantém a branch); `cleanup` tira do registro o que sumiu |
| `record --agent <a> --level <n> --label <x> --demand <pasta> --state <s> (--tokens --tool-uses --duration-ms \| --codex-task <t>)` | Registra uma delegação nativa no `metricas.md` e imprime cabeçalho e resumo (usado pelo orquestrador) |
| `delegate --agent <a> --effort <e> --level <n> --task <arq> --demand <pasta>` | Roda um agente headless para uma tarefa (modo headless) |

Scripts: `.\setup.ps1`/`./setup.sh` (setup), `.\doctor.ps1`/`./doctor.sh` (doctor, sem alterar nada).
Testes: `python -m unittest discover -s tests` (`python tests/test_apply.py --update` regrava as referências
quando a mudança de saída é intencional). `AIDW_DEBUG=1` no `delegate` grava um log de depuração na demanda.

---

## 5. Agentes

No plugin, os agentes se chamam `aidw:<nome>`; cada um existe também em variantes de effort
(`aidw:codificador-low`, `aidw:codificador-high`…, e `-opus-` quando o nível usa outro modelo) — o orquestrador
escolhe a variante pela tabela *Effort per task*.

| Agente | Papel | Modelo padrão | O que faz |
|---|---|---|---|
| `orquestrador` | orchestrator | Opus · high | O chat principal: entende, planeja (`to-spec`), escolhe o effort, delega, tria as revisões pelas regras, pede só o que precisa e monta a revisão final. Não implementa |
| `codificador` | coder | Opus · medium | Implementa um ticket por vez no worktree: código, testes, build/lint/typecheck; aplica as correções de uma revisão e grava o diff |
| `revisor` | reviewer | Sonnet · high (Opus em complexa/crítica) | Revisa o plano e o diff contra spec, ticket e card; achados com IDs estáveis e severidade (CRITICO/IMPORTANTE/SUGESTAO); não altera código |
| `api` | api-db | Sonnet · medium | Consulta APIs, banco (leitura pelo validador do contexto) e logs; propõe qualquer escrita com o comando exato e só executa com OK |
| `documentador` | documenter | Haiku · medium (tier fast) | Atualiza README/ARCHITECTURE/changelog a partir do diff aprovado, gera o plano de testes e redige work items |
| `bugs` | bug-hunter | Sonnet · high | **Sob demanda:** caça defeitos de comportamento com cenário concreto, ou a causa-raiz de um bug reportado |
| `seguranca` | security | Sonnet · high | **Sob demanda:** vulnerabilidades exploráveis (authn/authz, segredos, cripto, injeção, dados pessoais) com caminho de ataque |
| `qa` | qa | Sonnet · medium | Desligado por padrão: testes e critérios de aceite de ponta a ponta; hoje o teste é o `validation` do codificador |

`bugs` e `seguranca` só entram quando um gatilho se aplica (concorrência, legado frágil, dados pessoais, auth,
dependências…), uma vez por demanda, em paralelo com a 1ª revisão. Os nomes, modelos e efforts padrão podem ser
trocados no `aidw.config.toml` (seção 9).

---

## 6. Skills

Procedimentos que o orquestrador e os agentes seguem (no plugin, `aidw:<skill>`).

| Skill | Quem usa | O que faz |
|---|---|---|
| `orquestrar` / `sair` | você | Entrar e sair do modo orquestrador (seção 3) |
| `contexto-listar` / `contexto-usar` / `contexto-criar` | você | Administração dos contextos (seção 7) |
| `to-spec` | orquestrador | Transforma o pedido num plano de execução persistente e depois em tickets autocontidos |
| `verificar-premissa` | orquestrador, revisor, especialistas | Exige evidência antes de aceitar "não dá para corrigir aqui", "cobre todos os casos", "é a convenção" |
| `preparar-worktree` | orquestrador, codificador | Cria, confere e remove o worktree da demanda com `aidw.py worktree` |
| `code-review` | revisor | Revisão de diff contra spec e ticket, com achados de IDs estáveis |
| `database-safe` | api | Classifica cada operação de banco: leitura só pelo validador, escrita sempre proposta para aprovação |
| `bug-hunt` | bugs | Caça de defeitos e causa-raiz com cenário de falha concreto |
| `security-audit` | seguranca | Auditoria de vulnerabilidades com caminho de ataque |

O contexto pode trazer skills próprias (ex.: ler e anexar arquivos no board do time, plano de testes para o QA,
redação de work item); elas entram no mesmo plugin.

---

## 7. Contextos

Um contexto é o pacote de regras de uma empresa ou squad, em `contexts/<nome>/` — um **repositório Git próprio e
privado**, ignorado pelo Git do AiDW:

```text
contexts/<nome>/
├── context.toml        sistemas (repos, stack, build, teste), permissões, worktree, MCPs, o que cada agente recebe
├── agents/             regras por papel (orchestrator.md, coder.md…)
├── policies/           políticas do time (aprovações, ambientes, segredos…)
├── shared/             guias comuns a vários agentes
├── reference/          referências lidas sob demanda (`when`) — o prompt fica pequeno
├── skills/             skills próprias do contexto
├── tools/              validadores e wrappers (ex.: SQL só leitura, build filtrado)
└── demandas/           estado de cada demanda (fora do Git do contexto)
```

- **Criar:** `/aidw:contexto-criar`. Ele pergunta o nome e os repositórios, analisa cada repositório em paralelo
  (stack, build/teste reais, dependências fora do Git, convenções, git e PR, integrações, ambientes, banco, riscos —
  sempre com evidência `arquivo:linha`), faz **no mínimo 10 perguntas** com opções e recomendação tiradas da
  análise, gera o contexto e roda `context check`. Commit e push do repositório do contexto pedem OK.
- **Ativar:** `/aidw:contexto-usar <nome>` — valida, grava no `aidw.config.toml` (só a linha `active`), regenera o
  ambiente e o plugin `aidw` com as regras do contexto. Abra um chat novo.
- **Validar:** `aidw.py context check <nome>` — build completo com o contexto, repositório próprio, ignorado pelo
  AiDW e pasta de estado exclusiva.
- Nas strings do `context.toml`, `{{context}}` é a pasta do contexto e `{{root}}` a raiz do AiDW; nos `.md`,
  `{{agent:<papel>}}` vira o nome do agente.

---

## 8. Demandas e worktrees

- **Demanda:** pasta `<state dir do contexto>/<tipo>-<id>/` com o `demand.json` (etapa, status, histórico,
  repositórios) e os artefatos do fluxo: `plano-<id>.md`, `revisao-plano-*`, `tarefa-<agente>-*.md`,
  `diff-*.patch`, `review-*`, `triagem-*`, `checklist-revisao.md`, `metricas.md`, `revisao-final.md`.
- **Worktree:** `<[worktree] root>/<repo>/<demanda>` (padrão `C:/wt`), branch `<prefixo do contexto><número>-<slug>`
  a partir da base do plano, com junctions de `packages/` e `node_modules/`. Registro em `state/worktrees.json`.
  Dois repositórios com o mesmo nome (ex.: `ProjetosLegados/Hope` e `ProjetosTFS/Hope`) não dividem a pasta: o
  que chegar depois fica em `<root>/<repo>.<pasta-mãe>/<demanda>`.
- **Pastas vizinhas:** o código às vezes alcança outro repositório por caminho relativo, como o HintPath
  `..\..\eCommerce\...\bin\x.dll`. Para isso, o sistema pode listar `worktree_link = ["../eCommerce"]` no `context.toml`.
  - O `worktree create` cria, ao lado do worktree, uma junction com o mesmo caminho relativo para o que ele resolve a
    partir do working copy principal (ex.: `C:/wt/Hope/eCommerce` → `C:/ProjetosLegados/eCommerce`).
  - Essas junctions ficam na raiz dos worktrees e são compartilhadas entre os worktrees do mesmo repositório.
  - O `remove` não mexe nelas.
- **Retomar:** `/aidw:orquestrar` sem argumento na pasta do worktree (ou do repositório) acha a demanda e continua
  da etapa gravada. Depois de uma compactação da conversa, um hook lembra o orquestrador de reler as regras.
- **Limpar:** `aidw.py worktree remove <id>` só remove worktree sem alteração local e com commits publicados;
  a branch fica (apagar branch é ação travada).

---

## 9. Configuração

Depois de editar qualquer fonte, rode `python aidw.py apply` (modo projeto) e `python aidw.py install` (plugin), e
abra um chat novo.

### `aidw.config.toml`

Local de cada máquina (não versionado); o modelo é o `aidw.config.example.toml`.

```toml
[provider]
name = "claude"            # "claude" | "codex" — um provedor por vez no modo projeto

[delegation]
mode = "native"            # "native" = subagentes do provedor · "headless" = aidw.py delegate

[workspace]
project_dirs = ["C:/Projetos"]   # liberadas para o orquestrador e os agentes

[worktree]
root = "C:/wt"             # worktrees das demandas: <root>/<repo>/<id>, fora de qualquer repositório

[mcp]
enabled = ["playwright", "chrome-devtools", "figma", "context7"]

[context]
active = "meu-contexto"    # pasta em contexts/ ("" = nenhum)

[policies]
deny = ["Bash(git push --force *)", "Read(**/.env)"]   # bloqueado sempre
ask = []                                                # sempre pede OK

[agents.reviewer]
name = "Zé Revisor"        # opcional (aceita acento e espaço)
enabled = true
# model = "opus"           # opcional; sem ele, vale o tier padrão do papel
effort = "high"
skills = ["code-review", "verificar-premissa"]
```

| Arquivo | Para quê |
|---|---|
| `config/models.toml` | Catálogo de modelos por provedor, com `tiers` (`top`/`mid`/`fast`) e `efforts` aceitos |
| `orchestrator/config/routing.toml` | `[rules]` (o que fazer com cada `state`), `[effort.levels]` (effort e modelo por nível e papel), `[effort.escalate]` |
| `config/mcp.toml` | Catálogo de MCPs com `use_when`, `triggers` e os papéis que podem usar cada um |
| `orchestrator/ORCHESTRATOR.md` e `orchestrator/reference/` | Núcleo do orquestrador e o que ele lê sob demanda |
| `orchestrator/policies/` | Políticas genéricas (git, banco, produção, segredos, permissões) |
| `agents/<papel>/AGENT.md`, `skills/<nome>/SKILL.md`, `workflows/*.yaml` | Definições genéricas de agentes, skills e fluxos |

---

## 10. O que é gerado

Nada disso é versionado.

| Arquivo | Gerado por | Conteúdo |
|---|---|---|
| `.aidw/marketplace/plugins/aidw/` | `install` | O plugin: agentes e variantes, skills, `orquestrar`/`sair`, referências do orquestrador, hooks |
| `.aidw/install-manifest.json` | `install` | O que o install acrescentou (para o `uninstall` remover só isso) |
| `~/.claude/settings.json` (merge) | `install` | Regras `deny`/`ask`/`allow`, pastas liberadas e `env` do AiDW, só os itens dele |
| `state/worktrees.json`, `state/sessions.json` | comandos e hooks | Registro dos worktrees e das sessões no modo orquestrador |
| `.aidw/agents/<nome>.md`, `.aidw/reference/`, `.aidw/runtime.json` | `apply` | Definição de cada agente, referências do orquestrador, configuração resolvida |
| `CLAUDE.md`, `.claude/agents/`, `.claude/settings.local.json`, `.claude/skills/`, `.mcp.json` | `apply` (Claude) | O modo projeto do Claude |
| `AGENTS.md`, `.codex/config.toml`, `.codex/agents/`, `.codex/rules/aidw.rules`, `.agents/skills/` | `apply` (Codex) | O modo projeto do Codex |

Garantias: valida tudo antes de gravar; sem mudança, nenhuma escrita; remove só o que foi gerado pelo AiDW;
arquivo gerado alterado à mão faz o `install` parar (a não ser com `--force`).

---

## 11. Claude × Codex

| | Claude | Codex |
|---|---|---|
| Em qualquer pasta | ✅ plugin `aidw` (`install`) | ✅ `install --provider codex` + perfil `aidw` |
| Chamar o orquestrador | `/aidw:orquestrar`, `/aidw:sair` | `$aidw-orquestrar`, `$aidw-sair` |
| Agentes | `aidw:<agente>`, uma variante por effort | `aidw-<agente>`, modelo e effort em cada `spawn_agent` |
| Abrir/retomar demanda | ✅ | ✅ |
| Entrar no worktree | ✅ `EnterWorktree` + hook | pelo caminho absoluto; `aidw open --provider codex --demand <id>` abre o Codex nele |
| Guard e lembrete depois de compactação | ✅ hooks do plugin | ✅ `hooks.json` (aprovação única no terminal) |
| Regras globais | `~/.claude/settings.json` | `~/.codex/rules/aidw.rules` |
| Pastas graváveis | as do settings | as do perfil `aidw` (AiDW, projetos, worktrees) |
| Modo projeto (chat na raiz do AiDW) | ✅ | ✅ |

**Detalhes do modo native:** no Claude o effort é fixado no arquivo do subagente (daí as variantes) e o
`omitClaudeMd` isola as regras do orquestrador; no Codex o `spawn_agent` exige `multi_agent_v2` (ligado pelo
`.codex/config.toml` e pelo `chat`) e o subagente recebe a definição pelo arquivo `.aidw/agents/<nome>.md`.

**Modo headless** (`[delegation] mode = "headless"`): um processo por tarefa pelo `aidw.py delegate` —
`claude -p --agents … --agent <nome>` ou `codex exec` com a definição no stdin; as ações travadas voltam como
`denials`. O plugin exige o modo native.

**Limites do Codex:** o sandbox deixa o `.git` só leitura — o `worktree create` pede aprovação e os agentes não
fazem commit (você faz); o app desktop do Codex não aprova hooks (só o terminal); no Windows o AiDW libera `safe.directory` só para as pastas do AiDW, dos projetos e dos
worktrees, por variáveis `GIT_CONFIG_*`, sem tocar no `.gitconfig`.

---

## 12. Segurança

O princípio: **o modelo nunca é a última barreira.**

| Camada | Como funciona |
|---|---|
| Regras globais (`install`) | `deny` sempre (force push, `reset --hard`, `clean -f`, `.env`); `ask` para commit, push, merge, rebase, checkout… — valem em **toda** sessão do Claude; `allow` só para a rotina (git de leitura, build, comandos do `aidw.py`) |
| Guard (hook) | Agente do AiDW não edita o working copy principal de um repositório que tem worktree ativo; a conversa principal fica livre. Comandos de shell não são verificados — com o chat no worktree, o isolamento do Claude cobre |
| Worktree | O código da demanda fica fora do seu working copy; `remove` recusa alteração local e commit não publicado |
| Escopo por agente | Ferramentas, MCPs e pastas graváveis por papel; ferramentas bloqueadas pelo contexto (ex.: só o orquestrador comenta no card, depois do seu OK) |
| Validadores | Operações com risco passam por scripts do contexto (ex.: SQL só leitura dentro de `ROLLBACK`) |
| Contextos | Repositório privado, ignorado pelo Git do AiDW; `doctor` e `context check` dão erro se deixar de estar |
| Segredos | Nunca em arquivo, log, plano ou review; o `doctor` só confere se as variáveis existem; o `context list` mostra o remoto só pelo host |

---

## 13. Estendendo

- **Skill:** `skills/<nome>/SKILL.md` (frontmatter `name`, `description`; `aidw: admin` para skill de uso direto,
  fora de uma demanda) e o nome em `skills = [...]` do agente. `apply` e `install`.
- **Agente:** `agents/<papel>/AGENT.md` (ROLE, INPUT, PROCESS, OUTPUT com `state`), `[agents.<papel>]` no
  `aidw.config.toml`, o papel em `DEFAULT_AGENTS`/`RUN_PROFILE` do `aidw.py` e o effort em cada nível do
  `routing.toml`.
- **Modelo:** uma tabela em `config/models.toml`.
- **Policy:** um `.md` em `orchestrator/policies/` (todos) ou em `contexts/<nome>/policies/`. Com frontmatter
  `orchestrator_when: <momento>`, o orquestrador a lê só nesse momento (os agentes continuam com ela inteira).
- **Referência do orquestrador:** `orchestrator/reference/<nome>.md` com `when:` no frontmatter.

---

## 14. Solução de problemas

| Sintoma | Causa provável | Solução |
|---|---|---|
| `/aidw:orquestrar` não aparece | Plugin não instalado ou chat aberto antes do install | `python aidw.py install` e chat novo; `doctor` mostra a situação |
| O Claude pede aprovação para um comando do `aidw.py` | Caminho escrito numa forma não liberada | Use `python "<raiz>/aidw.py" …`; rode `install` se as regras sumiram |
| Headless falha com "OAuth session expired" | Login do CLI expirou | `claude auth login` (o `doctor` mostra "sem login") |
| Ferramenta PowerShell do Claude falha com "Linha de comando muito longa" | Problema do ambiente, também fora do AiDW | O modelo cai para o Bash; nada a fazer no AiDW |
| No Codex, `npm`/`node` falham com `EPERM` em `C:\Users\<você>` | O `node` do PATH mora no perfil do usuário (ex.: nvm), que o sandbox do Codex não lê | O `install --provider codex` põe um Node de fora do perfil na frente do PATH do perfil `aidw`; se não houver, instale um (o `doctor` avisa) |
| O Codex não roda os hooks do AiDW | Confiança não aprovada, ou invalidada por mudança no hook | `codex --profile aidw` num terminal → "Trust all and continue"; o `doctor` mostra o estado |
| O agente segue regras do orquestrador | `CLAUDE.md` do modo projeto carregado no agente | Já tratado com `omitClaudeMd`/`claudeMdExcludes` |
| `dubious ownership` num agente Codex | Repositório fora das pastas liberadas | Acrescente a pasta à config e rode `apply` |
| `MCP figma precisa de autenticação` | OAuth não feito | Claude: `/mcp` → figma → Authenticate · Codex: `codex mcp login figma` |
| `modelo … não está liberado para esta conta` | Modelo do Codex fora do plano | Tire o `model` do agente (vale o tier) ou escolha um liberado |
| Nome de agente inválido/reservado | Colide com agente do CLI (`plan`, `explore`, `default`…) | Escolha outro `name` |
