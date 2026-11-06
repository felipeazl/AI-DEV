# AiDW

[English](README.md)

**AiDW** (AI Development Workflow) é um plugin de **desenvolvimento agêntico** para o **Claude Code**: um workflow, um
time de agentes e um conjunto de skills. Você conversa com **um único chat**, o **orquestrador**, como conversaria com
um tech lead. Ele entende o pedido, manda um agente barato ler o código, encomenda um plano curto e autossuficiente,
leva o plano à sua aprovação, delega o código, a revisão e os testes, e te chama nos pontos que são seus: o plano, os
achados da revisão, a sua revisão de código, os passos manuais do teste e o OK da PR.

```text
 Você ─► /aidw:go 1234
            │
            ▼
      orquestrador ── entende ─► explorer lê o código ─► planner escreve o plano ─► você aprova
            │
            ▼
      coder implementa (worktree isolado)  ‖  documenter cria as Tasks  ‖  qa monta o roteiro e a massa
            │
            ▼
      reviewer (qualidade, bugs, segurança) ─► você decide os achados ─► coder corrige ⇄ reviewer
            │
            ▼
      sua revisão de código ─► qa testa (API, navegador) + você os passos manuais ─► PR com um OK ─► pronto
```

> **Feito para o Claude Code.** É nele que o AiDW roda inteiro e onde nasce toda funcionalidade nova. **No Codex, o
> AiDW é só agentes e skills:** o `install --provider codex` copia os agentes e as skills `aidw-*` e nada mais — sem
> regras de permissão, hooks, guard, perfil, MCP por agente nem mods. Veja [docs/pt-BR/claude-and-codex.md](docs/pt-BR/claude-and-codex.md).

## Por que usar

| Sem AiDW | Com AiDW |
|---|---|
| Um chat faz tudo: lê centenas de linhas, planeja, codifica e se revisa. O contexto enche e a qualidade cai. | Cada etapa roda num **agente novo**, só com o que precisa. O chat do orquestrador fica pequeno a demanda inteira. |
| O mesmo modelo caro para ler arquivo e para decidir arquitetura. | **Modelo e effort por papel**: Haiku lê código e escreve no board, Sonnet planeja, codifica e revisa. Opus só quando você pede. |
| Você revisa sozinho o que o modelo escreveu. | Um **revisor** independente cobre qualidade, bugs e segurança numa passada, com IDs, severidade e a recomendação de manter ou descartar; **você decide** cada achado. |
| Regras do time repetidas a cada prompt. | Um **contexto** guarda sistemas, comandos de build, convenções e políticas; todo agente já recebe. |
| O modelo decide o que é seguro. | **O modelo nunca é a última barreira**: permissões do CLI, hooks e validadores bloqueiam o que é de risco. |
| Fechou o chat, perdeu o fio. | Cada demanda tem pasta, estado e métricas: dá para **retomar** de onde parou e ver quanto cada etapa custou. |

## Sumário

1. [Instalação](#1-instalação)
2. [Como usar](#2-como-usar)
3. [O que vem incluído](#3-o-que-vem-incluído)
4. [Configuração](#4-configuração)
5. [Segurança](#5-segurança)
6. [Documentação](#6-documentação)

## 1. Instalação

### Pré-requisitos

| Ferramenta | Para quê | Instalação (Windows) |
|---|---|---|
| **Python 3.11+** | o `aidw.py` (só biblioteca padrão, nada de `pip install`) | `winget install Python.Python.3.13` (o `setup.ps1` oferece) |
| **Git** | repositórios, worktrees e o próprio AiDW | `winget install Git.Git` |
| **Node.js LTS** | servidores MCP locais via `npx` | `winget install OpenJS.NodeJS.LTS` |
| **Claude Code** | roda o orquestrador e os agentes | `irm https://claude.ai/install.ps1 \| iex` |
| **Codex CLI** (opcional) | uso limitado: agentes e skills | `npm i -g @openai/codex` |

Não é preciso API key: tudo roda com o login do CLI (assinatura do Claude ou conta do ChatGPT).

### Passo a passo

```powershell
git clone <url do AiDW> C:\AiDW
cd C:\AiDW
git clone <url do seu contexto> contexts\<nome>    # opcional: as regras do seu time (docs/pt-BR/contexts.md)
.\setup.ps1                                       # Linux/macOS: ./setup.sh
python aidw.py install                            # Claude: o AiDW passa a existir em qualquer pasta
.\doctor.ps1                                      # confere tudo e termina com READY ou NOT READY
```

| Etapa | O que faz |
|---|---|
| `setup` | Garante o Python, roda o **wizard** (provedor, modo de delegação, modelo e effort de cada agente, agentes a desligar, nomes, pastas dos projetos, MCPs, idioma, contexto) e grava o `aidw.config.toml`. Confere Git, Node, os CLIs e o login, cria as pastas que faltam, roda o `apply`, oferece registrar os MCPs e termina com o `doctor`. |
| `install` | Gera o plugin **`aidw`** (agentes, skills, comandos, hooks) e o plugin **`aidw-mods`** ([mods](docs/pt-BR/mods.md)) e instala os dois no Claude Code (CLI e app desktop). Acrescenta ao `~/.claude/settings.json` só as regras do AiDW. Se o Codex já foi instalado, atualiza ele junto. |
| `install --provider codex` | Opcional. **Só** os agentes `aidw-*` (`~/.codex/agents`) e as skills (`~/.agents/skills`). |
| `doctor` | Verifica núcleo, CLIs, login, contexto, variáveis de ambiente, MCPs, pastas e instalação. Não altera nada. |

Depois do `install`, **abra um chat novo**. O `/aidw:go` aparece em qualquer pasta.

- **Atualizar:** `git pull` no AiDW (e no contexto), depois `python aidw.py install` e um chat novo.
- **Outra máquina:** clone o AiDW e o contexto, rode `setup` e `install`. O `aidw.config.toml` e os arquivos gerados
  não são versionados; o `aidw.config.example.toml` é o modelo.
- **Desinstalar:** `python aidw.py uninstall` remove só o que o `install` acrescentou.

## 2. Como usar

Abra um chat do Claude Code, de preferência na pasta do repositório, e chame:

```text
/aidw:go 1234                 ← id do card, link ou uma descrição do que fazer
/aidw:go 1234 pr 5678         ← revisa a PR de outra pessoa (sem implementar)
/aidw:survey 1234             ← levantamento: valida o card no código e estima (sem implementar)
/aidw:go                      ← sem argumento: retoma a demanda desta pasta
```

O orquestrador detecta o projeto, abre a demanda (ou **retoma da etapa gravada**), cria o worktree, leva o chat para
ele e conduz o fluxo até a PR. Ele segue sozinho entre os seus pontos fixos (plano, achados da revisão, sua revisão de
código, passos manuais, PR), as ações travadas, as dúvidas reais e o que sair do plano.

### Comandos do chat

| Claude | Codex | O que faz |
|---|---|---|
| `/aidw:go [demanda]` | `$aidw-go` | Assume o chat como orquestrador e conduz a demanda |
| `/aidw:survey <card ou texto>` | `$aidw-survey` | Levantamento antes de implementar: valida cada ponto do card no código, mapeia o fluxo, estima esforço, story points e complexidade |
| `/aidw:exit` | `$aidw-exit` | Grava onde parou e devolve o chat ao modo normal |
| `/aidw:diff [repo\|exit]` | — | Leva o painel de diff para o próximo repositório da demanda; `exit` volta para a pasta da demanda |
| `/aidw:done` | `$aidw-done` | Fecha a tarefa: grava no contexto o que ela ensinou e faz commit do contexto |
| `/aidw:knowledge [tema]` | `$aidw-knowledge` | O que a base de conhecimento do contexto sabe sobre um sistema, contrato, conceito ou demanda |
| `/aidw:context [list\|use <nome>\|create]` | `$aidw-context` | Administra os contextos |
| `/strip` · `/panel [aba]` · `/metrics` · `/review-tests` | — | Mods: esconder/mostrar a faixa da demanda; abrir os painéis Geral, Métricas e Testes e Review |

Todos os comandos e opções: [docs/pt-BR/commands.md](docs/pt-BR/commands.md).

### Conversar com o orquestrador

| Você quer | Diga |
|---|---|
| Saber onde está | "Em que etapa estamos?" |
| Outro modelo numa tarefa | "Use Opus no coder neste ticket" |
| Menos custo | "Essa correção é pequena, use o coder medium" |
| Ver o diff de outro repositório | "Mostra o diff do front" |
| Só uma resposta, sem fluxo | "Só me responda, sem delegar" |

Cada resultado de agente aparece com o cabeçalho e o resumo **medidos** (nunca estimados):

```text
## Coder - claude-sonnet High
Coder (e1-r1) | Claude Sonnet | effort high | 67,448 tokens | 156 s
```

### Onde as coisas ficam

- **Worktrees:** `<raiz dos worktrees>/<demanda>/<repo>` (padrão `C:/wt` no Windows, `~/wt` nos outros), um por
  repositório, cada um na sua branch. O seu working copy nunca é tocado.
- **Artefatos:** `<pasta de estado>/<demanda>/` — resumo do card, exploração, plano, diffs, revisões, as suas decisões,
  o roteiro de testes, o texto da PR, `metrics.md` e `demand.json` (o estado para retomar).

## 3. O que vem incluído

### Workflows

| Workflow | Para | Arquivo |
|---|---|---|
| `development` | Feature, melhoria, bug, dívida técnica ou correção urgente, do card até a PR | `workflows/development.yaml` |
| `pr-review` | Revisar a PR de outra pessoa; quem corrige é o autor, você escolhe o que é publicado | `workflows/pr-review.yaml` |
| `survey` | Levantamento: estimar uma demanda antes de alguém implementar; só leitura | `workflows/survey.yaml` |

Etapa por etapa: [docs/pt-BR/workflow.md](docs/pt-BR/workflow.md).

### Agentes e os padrões

| Agente | Faz | Modelo · effort padrão | Exceções |
|---|---|---|---|
| `orchestrator` | O chat principal: conduz, lê o plano, delega, leva as decisões a você, abre a PR com o seu OK | o do chat (veja abaixo) | — |
| `explorer` | Lê código e ambiente e responde perguntas numeradas com `arquivo:linha` | Haiku | Sonnet medium (refazer uma vez), Sonnet high (levantamento) |
| `planner` | Escreve o plano com as entregas; ajusta quando você pede | Sonnet · high | medium (ajuste do plano) |
| `coder` | Implementa uma entrega por vez: código, testes, build | Sonnet · high | medium (correção pequena, ajuste de teste) |
| `reviewer` | Revisa o diff contra o plano: qualidade, bugs, segurança | Sonnet · high | medium (re-revisão), low (correção trivial) |
| `qa` | Roteiro e massa em paralelo com o código; depois, o teste | Sonnet · medium | high (refazer uma vez) |
| `documenter` | As Tasks no board e o texto da PR | Haiku | — |

- Os padrões ficam em `DEFAULT_AGENTS` no `aidw.py` (o **tier** de modelo e o effort de cada papel) e no
  `config/models.toml` (qual modelo é cada tier); as exceções, em `[effort.variants]` do
  `orchestrator/config/routing.toml`. O seu `aidw.config.toml` sobrepõe os padrões.
- **O orquestrador roda com o modelo e o effort do chat em que é aberto — o valor da configuração é só a
  recomendação mostrada na seção Runtime.**
- O Haiku não aceita effort; no Claude, o effort do explorer e do documenter é ignorado.

Trocar modelo e effort: [docs/pt-BR/agents.md](docs/pt-BR/agents.md#trocar-modelo-e-effort).

### Skills

`to-spec` (planner), `code-review` (reviewer), `verify-premise`, `prepare-worktree`, `database-safe`, mais os comandos
`go`, `survey`, `exit`, `diff`, `done`, `knowledge`, `context`. Veja [docs/pt-BR/skills.md](docs/pt-BR/skills.md).

### Contextos

O AiDW é **independente de contexto**. Um **contexto** é o pacote de regras de um time, num repositório Git privado em
`contexts/<nome>/`: sistemas e os comandos de build e teste, regras por agente, políticas, permissões, MCPs, skills,
validadores e uma base de conhecimento. Sem contexto, o AiDW roda com as regras genéricas. Veja
[docs/pt-BR/contexts.md](docs/pt-BR/contexts.md).

## 4. Configuração

Três camadas, cada uma sobre a anterior:

| Camada | Onde | Versionado | Quem muda |
|---|---|---|---|
| **Núcleo** | este repositório: agentes, skills, fluxo, roteamento, catálogo de modelos, políticas genéricas | sim | quem mantém o AiDW |
| **Contexto** | `contexts/<nome>/`: sistemas, regras do time, permissões, MCPs | sim (repo do time) | o time |
| **Máquina** | `aidw.config.toml`: o seu perfil | não | você |

```toml
[provider]
name = "claude"                     # ou "codex"

[workspace]
project_dirs = ["C:/Repos"]         # onde ficam os seus repositórios

[worktree]
root = "C:/wt"                      # onde nascem os worktrees das demandas

[context]
active = "meu-time"                 # qual contexto usar ("" = nenhum)

[ui]
language = "pt-BR"                  # idioma do chat e dos mods (BCP-47: "en", "pt-BR"…); padrão "en"

[agents.coder]
model = "opus"                      # uma chave de config/models.toml
effort = "high"

[agents.qa]
enabled = false                     # desligar um agente
```

`python aidw.py configure` refaz pelo wizard; ou edite à mão, rode `python aidw.py install` (e `apply` para o modo
projeto) e abra um chat novo. Campo a campo, o idioma e perfis de exemplo:
[docs/pt-BR/configuration.md](docs/pt-BR/configuration.md).

## 5. Segurança

**O modelo nunca é a última barreira.** No Claude Code:

- **Regras do CLI:** force push, `reset --hard`, `clean -f` e leitura de `.env` são bloqueados sempre; o que o contexto
  ou a sua configuração marcam como `ask` (commit, push, SQL de escrita…) sempre pede o seu OK.
- **Worktree e guard:** os agentes trabalham no worktree; um hook impede que editem o working copy principal, e um
  commit com ajuste de teste esquecido é recusado.
- **Escopo por agente:** cada papel tem só as ferramentas e os MCPs que precisa.
- **Validadores do contexto:** operações de risco passam por scripts que recusam o que não é permitido.
- **Ação travada vira proposta:** o agente devolve o comando exato, o orquestrador pede o seu OK uma vez.

No Codex o AiDW não instala nada disso: valem só as aprovações do próprio Codex. Detalhes:
[docs/pt-BR/security.md](docs/pt-BR/security.md).

## 6. Documentação

| Documento | Conteúdo |
|---|---|
| [workflow.md](docs/pt-BR/workflow.md) | O fluxo etapa por etapa, onde você decide, estados, revisão, testes, PR, revisão de PR, levantamento, artefatos |
| [agents.md](docs/pt-BR/agents.md) | Cada agente, padrões, como trocar modelo e effort, variantes, contrato de saída, criar um agente |
| [configuration.md](docs/pt-BR/configuration.md) | `aidw.config.toml` campo a campo, idioma, perfis, arquivos de configuração do núcleo |
| [commands.md](docs/pt-BR/commands.md) | Todos os comandos do chat e do `aidw.py` |
| [contexts.md](docs/pt-BR/contexts.md) | Estrutura de um contexto, `context.toml`, políticas, base de conhecimento, criar um |
| [demands-and-worktrees.md](docs/pt-BR/demands-and-worktrees.md) | Pasta da demanda, worktrees, vários repositórios, `/aidw:diff`, retomar e limpar |
| [skills.md](docs/pt-BR/skills.md) | Cada skill, `skills` × `preload`, skills do contexto, escrever uma |
| [mods.md](docs/pt-BR/mods.md) | Os mods do Claude Code (`aidw-mods`): faixa, métricas, travas da delegação, filtro de segredos |
| [panel.md](docs/pt-BR/panel.md) | O que cada painel mostra e de onde vem cada dado |
| [security.md](docs/pt-BR/security.md) | As camadas de proteção e as políticas do núcleo |
| [claude-and-codex.md](docs/pt-BR/claude-and-codex.md) | Claude Code primeiro; o que o Codex recebe, modos native e headless, arquivos gerados |
| [troubleshooting.md](docs/pt-BR/troubleshooting.md) | Sintomas comuns e como resolver |
