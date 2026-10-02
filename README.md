# AiDW

**AiDW** (AI Development Workflow) é uma camada de **desenvolvimento agêntico** para o Claude Code e o Codex.
Você conversa com **um único chat**, o **orquestrador**, como conversaria com um tech lead. Ele entende o pedido,
manda um agente barato ler o código, encomenda o plano, divide em tickets, delega cada ticket, revisa, corrige e só
te chama quando importa: uma dúvida real, uma ação de risco (commit, push, SQL de escrita) e **uma revisão final**
com tudo junto.

```text
 Você ─► /aidw:orquestrar 1234
            │
            ▼
      orquestrador ── entende ─► explorador lê o código ─► planejador escreve o plano ─► revisor confere o plano
            │                                                                                  │
            │  ◄────────────────────────── tickets ◄── planejador ◄────────────────────────────┘
            ▼
      codificador implementa (num worktree isolado) ─► revisor ⇄ codificador até zero problema grave
            │                                            (+ bugs / segurança quando vale o custo)
            ▼
      documentador ─► revisão final (você) ─► pronto
```

## Por que usar

| Sem AiDW | Com AiDW |
|---|---|
| Um chat faz tudo: lê centenas de linhas, planeja, codifica e se revisa. O contexto enche e a qualidade cai no fim da sessão. | Cada etapa roda num **agente novo**, com só o que precisa. O chat do orquestrador fica pequeno a demanda inteira. |
| O mesmo modelo caro para ler arquivo e para decidir arquitetura. | **Modelo e effort por etapa e por nível da demanda**: Haiku para ler código, Opus para planejar e codificar o que é difícil, nada acima de `high`. |
| Você revisa o que o modelo escreveu, sozinho. | Um **revisor** independente acha os problemas antes de você, com IDs, severidade e triagem por regra; você vê o pacote final. |
| Regras do time repetidas a cada prompt. | Um **contexto** guarda sistemas, comandos de build, convenções e políticas; todo agente já recebe. |
| O modelo decide o que é seguro. | **O modelo nunca é a última barreira**: permissões do CLI, hooks e validadores bloqueiam o que é de risco. |
| Fechou o chat, perdeu o fio. | Cada demanda tem pasta, estado e métricas: dá para **retomar** de onde parou e saber quanto cada etapa custou. |

---

## Sumário

1. [Instalação](#1-instalação)
2. [Como usar](#2-como-usar)
3. [Como o fluxo funciona](#3-como-o-fluxo-funciona)
4. [Agentes](#4-agentes)
5. [Skills](#5-skills)
6. [Contextos](#6-contextos)
7. [Configuração por usuário](#7-configuração-por-usuário)
8. [Segurança](#8-segurança)
9. [Documentação completa](#9-documentação-completa)

---

## 1. Instalação

### Pré-requisitos

| Ferramenta | Para quê | Instalação (Windows) |
|---|---|---|
| **Python 3.11+** | o `aidw.py` (só biblioteca padrão, nada de `pip install`) | `winget install Python.Python.3.13` (o `setup.ps1` oferece) |
| **Git** | repositórios, worktrees e o próprio AiDW | `winget install Git.Git` |
| **Node.js LTS** | servidores MCP locais via `npx` | `winget install OpenJS.NodeJS.LTS` |
| **Claude Code** e/ou **Codex CLI** | rodam o orquestrador e os agentes | `irm https://claude.ai/install.ps1 \| iex` · `npm i -g @openai/codex` |

Não é preciso API key: tudo roda com o login do CLI (assinatura do Claude ou conta do ChatGPT).

### Passo a passo

```powershell
git clone <url do AiDW> C:\AiDW
cd C:\AiDW
git clone <url do seu contexto> contexts\<nome>    # opcional: as regras do seu time (seção 6)
.\setup.ps1                                       # Linux/macOS: ./setup.sh
python aidw.py install                            # Claude: o AiDW passa a existir em qualquer pasta
.\doctor.ps1                                      # confere tudo e termina com PRONTO ou NÃO PRONTO
```

| Etapa | O que faz |
|---|---|
| `setup` | Garante o Python, roda o **wizard** (provedor, pastas dos projetos, raiz dos worktrees, contexto, MCPs, nome e modelo dos agentes) e grava o `aidw.config.toml`. Confere Git, Node, os CLIs e o login, cria as pastas que faltam, roda o `apply`, oferece registrar os MCPs que o contexto exige e termina com o `doctor`. |
| `install` | Gera o plugin **`aidw`** e o instala no Claude Code (CLI e app desktop). Acrescenta ao `~/.claude/settings.json` as regras de segurança do AiDW, só os itens dele. |
| `install --provider codex` | O mesmo para o Codex: skills `aidw-*`, agentes `aidw-*`, regras, hooks e o perfil `aidw`. Depois rode `codex --profile aidw` num terminal uma vez e escolha **Trust all and continue** para aprovar os hooks. |
| `doctor` | Verifica núcleo, CLIs, login, contexto, variáveis de ambiente, MCPs, pastas e instalação. Não altera nada. |

Depois do `install`, **abra um chat novo**. O comando `/aidw:orquestrar` aparece em qualquer pasta.

### Atualizar e outra máquina

- **Atualizar:** `git pull` no AiDW (e no contexto), depois `python aidw.py install` e um chat novo.
- **Outra máquina:** clone o AiDW e o contexto, rode `setup` e `install`. O `aidw.config.toml` e os arquivos gerados
  não são versionados: cada máquina tem os seus. O `aidw.config.example.toml` é o modelo.
- **Desinstalar:** `python aidw.py uninstall` remove só o que o `install` acrescentou.

---

## 2. Como usar

### Começar uma demanda

Abra um chat do Claude Code, de preferência na pasta do repositório, e chame:

```text
/aidw:orquestrar 1234                 ← id do card, link ou uma descrição do que fazer
/aidw:orquestrar 1234 interativo      ← pede o seu OK antes de cada delegação
/aidw:orquestrar                      ← sem argumento: retoma a demanda desta pasta
```

O orquestrador detecta o projeto, abre a demanda (ou **retoma da etapa gravada**), cria o worktree, leva o chat
para ele e conduz o fluxo até a revisão final.

### Modos da sessão

| Modo | Comportamento |
|---|---|
| `auto` (padrão) | Segue sozinho. Para só em ação travada, dúvida real, algo fora do plano e na revisão final. |
| `interativo` | Também para antes dos tickets (com o resumo do plano) e antes de cada delegação (agente, effort, nível, ticket, arquivos, build). Você responde *aprovar*, *ajustar* ou *pular*. |

Sem o modo no pedido, o orquestrador pergunta. O modo fica gravado e vale na retomada; para trocar no meio, diga
"modo automático" ou "modo interativo".

### Comandos do chat

| Claude | Codex | O que faz |
|---|---|---|
| `/aidw:orquestrar [demanda] [modo]` | `$aidw-orquestrar` | Assume o chat como orquestrador e conduz a demanda |
| `/aidw:sair` | `$aidw-sair` | Grava onde parou e devolve o chat ao modo normal |
| `/aidw:diff [repo\|sair]` | — | Leva o painel de diff para o próximo repositório da demanda (em círculo); `sair` volta para a pasta da demanda |
| `/aidw:done` | `$aidw-done` | Fecha a tarefa: grava no contexto o que ela ensinou (build, armadilhas, convenções) e faz commit e push do contexto |
| `/aidw:contexto-listar` · `contexto-usar <nome>` · `contexto-criar` | `$aidw-contexto-*` | Administram os contextos (seção 6) |

### Conversar com o orquestrador

Peça como pediria a um tech lead:

| Você quer | Diga |
|---|---|
| Saber onde está | "Em que etapa estamos?" |
| Outro modelo numa tarefa | "Use Sonnet no codificador para este ticket" |
| Menos custo | "Esse ticket é simples, use effort low" |
| Ver o diff de outro repositório | "Mostra o diff do front" |
| Só uma resposta, sem fluxo | "Só me responda, sem delegar" |
| Mexer no próprio AiDW | "Manutenção do AiDW: …" |

Cada resultado de agente aparece com o cabeçalho e o resumo **medidos** (nunca estimados):

```text
## Codificador - claude-opus Medium
Codificador (padrao) | Claude Opus | effort medium | 67.448 tokens | 156 s
```

### Onde as coisas ficam

- **Worktrees:** `C:\wt\<demanda>\<repo>` — um por repositório, com branch própria. O seu working copy nunca é tocado.
  Uma demanda que mexe no back e no front tem os dois na mesma pasta, e o chat fica nela.
- **Artefatos:** `<pasta de estado do contexto>\<demanda>\` — resumo do card, exploração, plano, tarefas, diffs,
  revisões, triagens, `metricas.md` e `demand.json` (o estado para retomar).

### Pelo terminal

```powershell
python aidw.py status                       # instalação, demandas ativas (etapa, worktree, alterações) e pendências
python aidw.py open --demand 1234           # abre o Claude na demanda já chamando /aidw:orquestrar
python aidw.py open --provider codex --demand 1234
python aidw.py show                         # nome, modelo e effort de cada agente
```

Referência completa de comandos: [docs/comandos.md](docs/comandos.md).

---

## 3. Como o fluxo funciona

| # | Etapa | Quem | Resultado |
|---|---|---|---|
| 1 | Entender | orquestrador | `resumo-<id>.md`: card, critérios de aceite, decisões dos comentários, trabalho existente |
| 2 | Explorar | explorador | `exploracao-<assunto>.md`: respostas numeradas com `arquivo:linha` |
| 3 | Planejar | planejador | `plano-<id>.md` versionado, com **nível** da demanda e passadas extras |
| 4 | Plano de testes | qa | `plano-testes-<id>.md`: como provar cada critério (API, navegador, suíte ou manual), testes no código e ajustes de teste |
| 5 | Revisar o plano | revisor ⇄ planejador | plano e plano de testes; só do nível `padrao` para cima |
| 6 | Tickets | planejador | uma `tarefa-<agente>-<assunto>.md` autocontida por ticket |
| 7 | Implementar | codificador | código, os testes que o ponta a ponta não pega, build e `diff-<ticket>-r<N>.patch`, no worktree |
| 8 | Testar | qa (⇄ codificador nos ajustes de teste) | evidência de cada critério automático; roteiro do que é manual |
| 9 | Revisar | revisor ⇄ codificador | achados `R1-01`… com severidade; triagem por regra até zero CRITICO/IMPORTANTE |
| 10 | Teste manual | **você**, com o orquestrador | o roteiro um passo por vez: você executa e manda a evidência (só se houver passo manual) |
| 11 | Documentar | documentador | docs do diff aprovado |
| 12 | Revisão final | **você** | um pacote só, sem nenhum ajuste de teste no diff; com o seu OK, o orquestrador publica e executa o que foi aprovado |

- **Cada agente termina com um `state`** (ex.: `implementation_complete`, `review_changes_requested`), e o
  orquestrador aplica a regra fixa de `orchestrator/config/routing.toml`. Os agentes não escolhem o próximo passo.
- **Nível da demanda** (`trivial`, `simples`, `padrao`, `complexa`, `critica`): define modelo e effort de cada
  agente. Na dúvida, o menor; escala quando um agente falha duas vezes ou a revisão acha CRITICO.
- **Passadas extras:** `bugs` e `seguranca` só entram quando um gatilho se aplica (concorrência, legado frágil,
  autenticação, dados pessoais…), em paralelo com a 1ª revisão.
- **Limite de voltas:** cada laço (explorar ⇄ planejar, revisar ⇄ corrigir) tem `max_retries`; esgotou, o
  orquestrador para e pergunta.

Detalhes, estados e regras de triagem: [docs/fluxo.md](docs/fluxo.md). Worktrees e demandas com vários
repositórios: [docs/demandas-e-worktrees.md](docs/demandas-e-worktrees.md).

---

## 4. Agentes

| Agente | Faz | Modelo (padrão → complexa/crítica) |
|---|---|---|
| `orquestrador` | O chat principal: conduz, escolhe o effort, delega, tria e monta a revisão final. Não lê código para planejar nem implementa | o modelo do chat (Opus · high recomendado) |
| `explorador` | Lê código e responde perguntas numeradas com `arquivo:linha`. Não altera nada | Haiku → Sonnet |
| `planejador` | Escreve o plano, corrige depois da revisão e corta os tickets | Opus medium → Opus high (Sonnet em simples; não roda em trivial) |
| `codificador` | Implementa um ticket por vez: código, testes, build | Opus medium → Opus high (Sonnet em trivial/simples) |
| `revisor` | Revisa plano e diff contra spec, ticket e card; achados com severidade | Opus medium → Opus high (Sonnet em trivial/simples) |
| `api` | Consulta APIs, banco (só leitura pelo validador) e logs; propõe escritas | Sonnet |
| `documentador` | Docs do diff aprovado, redação de work items | Haiku → Sonnet |
| `bugs` | **Sob demanda:** defeitos com cenário de falha concreto, causa-raiz | Sonnet → Opus high |
| `seguranca` | **Sob demanda:** vulnerabilidades com caminho de ataque | Sonnet → Opus high |
| `qa` | Plano de testes com o planejador e teste da entrega: web/API sozinho, desktop por roteiro passo a passo com você | Sonnet |

Nenhum agente passa de effort `high`. No Codex vale a mesma tabela pelo equivalente de cada modelo (Opus → top,
Sonnet → intermediário, Haiku → leve). Nomes, modelos e efforts são configuráveis, e qualquer agente pode ser
desligado.

Tabela completa por nível, contrato de cada agente e como criar um: [docs/agentes.md](docs/agentes.md).

---

## 5. Skills

Skills são procedimentos em Markdown que um agente carrega quando a etapa pede.

| Skill | Quem usa | Para quê |
|---|---|---|
| `orquestrar` · `sair` · `diff` · `done` | você | Entrar e sair do modo orquestrador, trocar o diff, fechar a tarefa |
| `contexto-listar` · `contexto-usar` · `contexto-criar` | você | Administrar contextos |
| `to-spec` | planejador | Pedido → plano persistente → tickets autocontidos |
| `verificar-premissa` | orquestrador, revisor, especialistas | Exige evidência antes de aceitar "não dá para corrigir aqui", "cobre todos os casos" |
| `preparar-worktree` | orquestrador, codificador | Criar, conferir e remover o worktree da demanda |
| `code-review` | revisor | Revisão com IDs estáveis e severidade |
| `database-safe` | api | Leitura só pelo validador; escrita sempre proposta para aprovação |
| `bug-hunt` · `security-audit` | bugs · seguranca | Caça de defeitos e auditoria de segurança |

O contexto pode trazer skills próprias (ler o board do time, anexar arquivo, plano de testes…). Como escrever uma
skill: [docs/skills.md](docs/skills.md).

---

## 6. Contextos

O AiDW é **independente de contexto**: o fluxo, os comandos e as proteções são iguais em qualquer máquina. Um
**contexto** é o pacote de regras de uma empresa ou squad, num **repositório Git privado** em `contexts/<nome>/`, e
deixa as entregas melhores sem mudar o nome de nada:

- **Sistemas:** onde cada repositório mora, stack, comando de build e de teste prontos, dependências entre sistemas.
- **Regras por agente:** o que cada papel recebe sempre (`include`) e o que lê só quando o tema aparece (`reference`).
- **Políticas:** aprovações, ambientes, segredos, escopo do time.
- **Permissões, MCPs, worktree:** o que roda sem perguntar, o que sempre pede OK, servidores obrigatórios, prefixo de branch.
- **Skills e ferramentas:** procedimentos e validadores do time (ex.: SQL só leitura dentro de `ROLLBACK`).

```text
/aidw:contexto-criar          ← analisa os repositórios, faz no mínimo 10 perguntas e gera o contexto
/aidw:contexto-usar <nome>    ← valida, ativa e regenera o plugin (abra um chat novo)
/aidw:done                    ← no fim de cada tarefa, o contexto aprende o que ela descobriu
```

Sem contexto, o AiDW funciona com as regras genéricas. Estrutura, `context.toml` campo a campo e boas práticas:
[docs/contextos.md](docs/contextos.md).

---

## 7. Configuração por usuário

O AiDW tem três camadas. Cada uma sobrepõe a anterior:

| Camada | Onde | Versionado | Quem muda |
|---|---|---|---|
| **Núcleo** | o repositório do AiDW: agentes, skills, fluxo, tabela de níveis, políticas genéricas | sim (AiDW) | quem mantém o AiDW |
| **Contexto** | `contexts/<nome>/`: sistemas, regras do time, permissões, MCPs | sim (repo do time) | o time |
| **Máquina** | `aidw.config.toml`: o **seu** perfil | não | você |

No `aidw.config.toml` cada pessoa escolhe:

```toml
[provider]
name = "claude"                     # ou "codex"

[workspace]
project_dirs = ["C:/Projetos"]      # onde ficam os seus repositórios

[worktree]
root = "C:/wt"                      # onde nascem os worktrees das demandas

[context]
active = "meu-time"                 # qual contexto usar

[mcp]
enabled = ["playwright", "context7"]

[agents.coder]
name = "codificador"                # nome que aparece no chat
model = "sonnet"                    # trocar o modelo padrão do papel
effort = "medium"

[agents.qa]
enabled = false                     # desligar um agente
```

Rode `python aidw.py configure` para refazer pelo wizard, ou edite à mão e rode `python aidw.py apply` e
`python aidw.py install`, e abra um chat novo. Exemplos de
perfis (plano menor, só Codex, front-end, quem não quer passadas extras): [docs/configuracao.md](docs/configuracao.md).

---

## 8. Segurança

O princípio: **o modelo nunca é a última barreira.**

- **Permissões do CLI:** force push, `reset --hard`, `clean -f` e leitura de `.env` são bloqueados sempre; commit,
  push, merge, checkout e SQL de escrita sempre pedem o seu OK, em qualquer sessão.
- **Worktree e guard:** os agentes trabalham no worktree; um hook impede que editem o working copy principal.
- **Escopo por agente:** cada papel tem só as ferramentas, MCPs e pastas que precisa.
- **Validadores do contexto:** operações de risco passam por scripts que recusam o que não é permitido.
- **Ação travada vira proposta:** o agente devolve o comando exato, o orquestrador junta e pede o OK uma vez.

Detalhes: [docs/seguranca.md](docs/seguranca.md).

---

## 9. Documentação completa

| Documento | Conteúdo |
|---|---|
| [docs/fluxo.md](docs/fluxo.md) | O fluxo etapa por etapa, estados e regras, níveis e escalonamento, triagem, artefatos, métricas e retomada |
| [docs/agentes.md](docs/agentes.md) | Cada agente, tabela de modelo e effort por nível, contrato de saída, variantes, como criar um |
| [docs/skills.md](docs/skills.md) | Cada skill, skills de uso direto × de fluxo, `preload`, skills do contexto, como escrever uma |
| [docs/contextos.md](docs/contextos.md) | Estrutura de um contexto, `context.toml` campo a campo, `include` × `reference`, políticas, criar e validar |
| [docs/configuracao.md](docs/configuracao.md) | `aidw.config.toml` campo a campo, perfis de exemplo, modelos, roteamento e MCPs |
| [docs/demandas-e-worktrees.md](docs/demandas-e-worktrees.md) | Pasta da demanda, worktrees, vários repositórios, `/aidw:diff`, retomar e limpar |
| [docs/comandos.md](docs/comandos.md) | Todos os comandos do chat e do `aidw.py` |
| [docs/claude-e-codex.md](docs/claude-e-codex.md) | Diferenças entre os provedores, modo native × headless, arquivos gerados |
| [docs/seguranca.md](docs/seguranca.md) | As camadas de proteção |
| [docs/solucao-de-problemas.md](docs/solucao-de-problemas.md) | Sintomas comuns e como resolver |