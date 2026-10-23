# AiDW

**AiDW** (AI Development Workflow) é um plugin de **desenvolvimento agêntico** para o **Claude Code**: um workflow, um time
de agentes e um conjunto de skills.
Você conversa com **um único chat**, o **orquestrador**, como conversaria com um tech lead. Ele entende o pedido,
manda um agente barato ler o código, encomenda um plano simples e autossuficiente, leva o plano à sua aprovação,
delega o código, a revisão e os testes, e te chama nos pontos que são seus: o plano, os achados da revisão, a sua
revisão de código, os passos manuais do teste e o OK da PR.

```text
 Você ─► /aidw:orquestrar 1234
            │
            ▼
      orquestrador ── entende ─► explorador lê o código ─► planejador escreve o plano ─► você aprova
            │
            ▼
      codificador implementa (worktree isolado)  ‖  documentador cria as Tasks  ‖  qa monta o roteiro e a massa
            │
            ▼
      revisor (qualidade, bugs, segurança) ─► você decide os achados ─► codificador corrige ⇄ revisor
            │
            ▼
      sua revisão de código ─► qa testa (API, navegador) + você os passos manuais ─► PR com um OK ─► pronto
```

> **Feito para o Claude Code.** É nele que o AiDW roda inteiro e onde nasce toda funcionalidade nova. **No Codex, o
> AiDW é só agentes e skills:** o `install --provider codex` copia os agentes e as skills `aidw-*` e nada mais, sem
> regras de permissão, hooks (guard), perfil, MCP por agente nem mods. O fluxo da demanda roda, mas as proteções ficam
> com o seu Codex. Detalhes em [docs/claude-e-codex.md](docs/claude-e-codex.md).

## Por que usar

| Sem AiDW | Com AiDW |
|---|---|
| Um chat faz tudo: lê centenas de linhas, planeja, codifica e se revisa. O contexto enche e a qualidade cai no fim da sessão. | Cada etapa roda num **agente novo**, com só o que precisa. O chat do orquestrador fica pequeno a demanda inteira. |
| O mesmo modelo caro para ler arquivo e para decidir arquitetura. | **Modelo e effort por papel**: Haiku para ler código e escrever no board, Sonnet high para planejar, codificar e revisar, Sonnet medium para testar; nada acima de `high`, Opus só quando você pede. |
| Você revisa o que o modelo escreveu, sozinho. | Um **revisor** independente cobre qualidade, bugs e segurança numa passada, com IDs, severidade e a recomendação de manter ou descartar; **você decide** cada achado. |
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
| **Claude Code** | roda o orquestrador e os agentes | `irm https://claude.ai/install.ps1 \| iex` |
| **Codex CLI** (opcional) | uso limitado: agentes e skills | `npm i -g @openai/codex` |

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
| `install` | Gera os plugins **`aidw`** (agentes, skills, comandos e hooks) e **`aidw-mods`** (os [mods](docs/mods.md)) e os instala no Claude Code (CLI e app desktop). Acrescenta ao `~/.claude/settings.json` as regras de segurança do AiDW, só os itens dele. Se o Codex já foi instalado, atualiza ele junto. |
| `install --provider codex` | Opcional. **Só** os agentes `aidw-*` (`~/.codex/agents`) e as skills `aidw-*` (`~/.agents/skills`): sem regras, hooks, perfil nem mods. O orquestrador precisa de `multi_agent_v2` (o `aidw open --provider codex` já liga). |
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
/aidw:orquestrar 1234 pr 7639         ← revisa a PR de outra pessoa (sem implementar)
/aidw:levantamento 1234               ← levantamento: valida o card no código e estima (sem implementar)
/aidw:orquestrar                      ← sem argumento: retoma a demanda desta pasta
```

O orquestrador detecta o projeto, abre a demanda (ou **retoma da etapa gravada**), cria o worktree, leva o chat
para ele e conduz o fluxo até a PR.

Ele segue sozinho entre os seus pontos fixos (plano, achados da revisão, sua revisão de código, passos manuais,
PR), as ações travadas, as dúvidas reais e o que sair do plano. Não há modo a escolher: as paradas são essas.

### Comandos do chat

| Claude | Codex | O que faz |
|---|---|---|
| `/aidw:orquestrar [demanda] [modo]` | `$aidw-orquestrar` | Assume o chat como orquestrador e conduz a demanda |
| `/aidw:levantamento <card ou texto>` | `$aidw-levantamento` | Levantamento antes de implementar: valida cada ponto do card no código, mapeia o fluxo e estima esforço (horas), story points e complexidade, com as dúvidas |
| `/aidw:sair` | `$aidw-sair` | Grava onde parou e devolve o chat ao modo normal |
| `/aidw:diff [repo\|sair]` | — | Leva o painel de diff para o próximo repositório da demanda (em círculo); `sair` volta para a pasta da demanda |
| `/aidw:done` | `$aidw-done` | Fecha a tarefa: grava no contexto o que ela ensinou (a nota da demanda e as notas da base de conhecimento que ela tocou; build e ambiente no `context.toml`) e faz commit e push do contexto |
| `/aidw:conhecimento [tema]` | `$aidw-conhecimento` | O que a base de conhecimento do contexto sabe sobre um sistema, contrato, conceito ou demanda |
| `/aidw:contexto-listar` · `contexto-usar <nome>` · `contexto-criar` | `$aidw-contexto-*` | Administram os contextos (seção 6) |
| `/aidw-faixa` | — | Esconde ou mostra a faixa da demanda acima do prompt ([mods](docs/mods.md)) |
| `/aidw-painel [aba]` | — | Abre o painel do AiDW: Geral (mapa da demanda), as abas de cada uso e Métricas ([painel](docs/painel.md)) |
| `/aidw-rodada` | — | Libera mais uma rodada no laço de revisão travado pelo `max_retries` |

### Mods (só Claude Code)

No modo orquestrador, o plugin `aidw-mods` trabalha junto com o chat:

- **Faixa acima do prompt:** a demanda, o contexto e as janelas de 7d e 5h do plano, com barras, e os agentes rodando.
- **Painel do AiDW** (`/aidw-painel`, [painel.md](docs/painel.md)): Geral (título, mapa da demanda com resumo, números e
  progresso, inclusive Code review e QA, agentes rodando e links), as abas de cada uso e Métricas.
  - **Desenvolver:** critérios, regras e cenários com a cobertura; revisão em cartões (antes e depois do código,
    recomendação do AiDW, decisão); diffs por arquivo com os achados; teste manual passo a passo.
  - **Revisar PR:** achados com o comentário de cada um, o que publicar e o voto.
  - **Levantamento:** card × código, estimativa e dúvidas.
- **Métricas sozinhas:** cada delegação vira linha do `metricas.md` quando o agente termina.
- **Travas da delegação:** a célula da tabela, o `model` sem pedido e o insumo colado são recusados; o laço de revisão
  para no `max_retries` até você liberar mais uma rodada.
- **Avisos e proteções:** toasts quando a demanda espera você ou um agente termina, aviso quando o orquestrador lê
  código no chat, filtro de segredos na conversa e o estado da demanda de volta depois de uma compactação.

Eles ligam com `/aidw:orquestrar` ou `/aidw:levantamento` e desligam com `/aidw:sair` ou `/aidw:done`. Detalhes e como
escrever um mod: [docs/mods.md](docs/mods.md).

### Conversar com o orquestrador

Peça como pediria a um tech lead:

| Você quer | Diga |
|---|---|
| Saber onde está | "Em que etapa estamos?" |
| Outro modelo numa tarefa | "Use Sonnet no codificador para este ticket" |
| Menos custo | "Essa correção é pequena, use o codificador medium" |
| Ver o diff de outro repositório | "Mostra o diff do front" |
| Só uma resposta, sem fluxo | "Só me responda, sem delegar" |
| Mexer no próprio AiDW | "Manutenção do AiDW: …" |

Cada resultado de agente aparece com o cabeçalho e o resumo **medidos** (nunca estimados):

```text
## Codificador - claude-sonnet High
Codificador (rota) | Claude Sonnet | effort high | 67.448 tokens | 156 s
```

### Onde as coisas ficam

- **Worktrees:** `C:\wt\<demanda>\<repo>` — um por repositório, com branch própria. O seu working copy nunca é tocado.
  Uma demanda que mexe no back e no front tem os dois na mesma pasta, e o chat fica nela.
- **Artefatos:** `<pasta de estado do contexto>\<demanda>\` — resumo do card, exploração, plano, diffs, revisões,
  as suas decisões, o roteiro de testes, o texto da PR, `metricas.md` e `demand.json` (o estado para retomar).

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
| 1 | Entender | orquestrador | `resumo-<id>.md`: card, critérios e regras com o texto do card, decisões dos comentários, trabalho existente |
| 2 | Explorar | explorador | `exploracao-<assunto>.md`: respostas numeradas com `arquivo:linha`, contratos, ids e dados reais |
| 3 | Plano | planejador | `plano-<id>.md`: spec-driven, curto e autossuficiente, com `CA`/`RN` e as entregas `E1…` |
| 4 | Sua aprovação | **você** | o orquestrador lê o plano e aponta o que não fecha; nada vai para o código sem o seu OK |
| 5 | Implementar | codificador ‖ documentador ‖ qa | o código no worktree; uma Task por entrega no board; `roteiro-testes-<id>.md` com a massa |
| 6 | Revisão | revisor ⇄ codificador | achados `R1-01`… (qualidade, bugs, segurança) com a recomendação; **você decide** cada um, a cada rodada |
| 7 | Sua revisão | **você** | a revisão do código; o que você pedir vira correção e revisão só dela |
| 8 | Testes | qa, depois **você** | o qa roda API e navegador e marca o roteiro; os passos manuais você roda com o orquestrador |
| 9 | PR | documentador, depois o orquestrador | `pr-<id>.md`; com **um OK**, commit, push, PR e o comentário de pendências para a QA |

- **Cada agente termina com um `state`** (ex.: `plan_ready`, `review_findings`), e o orquestrador aplica a regra fixa
  de `orchestrator/config/routing.toml`. Os agentes não escolhem o próximo passo.
- **Sem níveis de demanda:** cada agente roda no seu padrão; as únicas exceções (descer na re-revisão, subir quando o
  resultado não fez sentido) estão na tabela *Agents and effort*, com o motivo de cada uma.
- **Cada agente roda uma vez por etapa:** uma nova rodada precisa de um motivo nomeado (o seu ajuste, um achado
  mantido, um teste que falhou).
- **Limite de voltas:** o laço revisar ⇄ corrigir tem `max_retries`; esgotou, o orquestrador para e pergunta.

Para revisar a PR de outra pessoa, o fluxo é mais curto: worktree só leitura da PR, revisão com o rascunho de cada
comentário e um voto sugerido, e você escolhe o que é publicado ([docs/fluxo.md](docs/fluxo.md#revisar-a-pr-de-outra-pessoa)).

Para estimar um card antes de implementar, `/aidw:levantamento 1234`: um explorador valida cada ponto do card no código e
mapeia o fluxo, e o orquestrador estima horas, story points e complexidade e lista as dúvidas em linguagem simples
([docs/fluxo.md](docs/fluxo.md#levantamento-de-demanda)).

Detalhes, estados e regras de triagem: [docs/fluxo.md](docs/fluxo.md). Worktrees e demandas com vários
repositórios: [docs/demandas-e-worktrees.md](docs/demandas-e-worktrees.md).

---

## 4. Agentes

| Agente | Faz | Modelo |
|---|---|---|
| `orquestrador` | O chat principal: conduz, lê o plano, delega, leva os achados e os passos manuais a você e abre a PR com o seu OK. Não lê código para planejar nem implementa | o modelo do chat (Opus · medium recomendado) |
| `explorador` | Lê código e o ambiente (SELECT pelo validador) e responde perguntas numeradas com `arquivo:linha`. Não altera nada | Haiku (Sonnet no levantamento e para refazer) |
| `planejador` | Escreve o plano SDD com as entregas e ajusta quando você pede | Sonnet high |
| `codificador` | Implementa uma entrega por vez: código, testes, build | Sonnet high (medium nas correções pequenas) |
| `revisor` | Revisa o diff contra o plano: qualidade, bugs e segurança numa passada | Sonnet high (medium/low na re-revisão) |
| `qa` | Roteiro e massa em paralelo com o código; depois, o teste: API e navegador sozinho, o resto com você | Sonnet medium |
| `documentador` | As Tasks no board e o texto da PR; redação de US e Dívida | Haiku |

Nenhum agente passa de effort `high`. No Codex (só agentes e skills) vale a mesma tabela pelo equivalente de cada modelo (Opus → top,
Sonnet → intermediário, Haiku → leve). Nomes, modelos e efforts são configuráveis, e qualquer agente pode ser
desligado.

Exceções de effort, contrato de cada agente e como criar um: [docs/agentes.md](docs/agentes.md).

---

## 5. Skills

Skills são procedimentos em Markdown que um agente carrega quando a etapa pede.

| Skill | Quem usa | Para quê |
|---|---|---|
| `orquestrar` · `sair` · `diff` · `done` | você | Entrar e sair do modo orquestrador, trocar o diff, fechar a tarefa |
| `contexto-listar` · `contexto-usar` · `contexto-criar` | você | Administrar contextos |
| `to-spec` | planejador | Pedido → plano spec-driven com as entregas, autossuficiente para o codificador |
| `verificar-premissa` | orquestrador, revisor | Exige evidência antes de aceitar "não dá para corrigir aqui", "cobre todos os casos" |
| `preparar-worktree` | orquestrador, codificador | Criar, conferir e remover o worktree da demanda |
| `code-review` | revisor | Revisão numa passada (qualidade, bugs com cenário de falha, segurança com caminho de ataque), com IDs estáveis, severidade e recomendação |
| `database-safe` | explorador, qa | Leitura só pelo validador; escrita sempre proposta para aprovação |

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
- **Base de conhecimento:** o que as demandas aprenderam sobre cada sistema, em notas ligadas por `[[links]]` (um vault
  do Obsidian), sem fato repetido; os agentes leem a nota do sistema antes do código e o `/aidw:done` a atualiza.

```text
/aidw:contexto-criar          ← analisa os repositórios, faz no mínimo 10 perguntas e gera o contexto
/aidw:contexto-usar <nome>    ← valida, ativa e regenera o plugin (abra um chat novo)
/aidw:done                    ← no fim de cada tarefa, o contexto aprende o que ela descobriu
/aidw:conhecimento <tema>     ← o que a base já sabe sobre um sistema, contrato ou conceito
```

Sem contexto, o AiDW funciona com as regras genéricas. Estrutura, `context.toml` campo a campo e boas práticas:
[docs/contextos.md](docs/contextos.md).

---

## 7. Configuração por usuário

O AiDW tem três camadas. Cada uma sobrepõe a anterior:

| Camada | Onde | Versionado | Quem muda |
|---|---|---|---|
| **Núcleo** | o repositório do AiDW: agentes, skills, fluxo, tabela de agentes e effort, políticas genéricas | sim (AiDW) | quem mantém o AiDW |
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
perfis (plano menor, só Codex, front-end): [docs/configuracao.md](docs/configuracao.md).

---

## 8. Segurança

O princípio: **o modelo nunca é a última barreira.** As camadas abaixo são do Claude Code; no Codex, o AiDW não
instala regras nem hooks, e valem só as aprovações do próprio Codex.

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
| [docs/fluxo.md](docs/fluxo.md) | O fluxo etapa por etapa, onde você decide, estados e regras, revisão e testes, artefatos, métricas e retomada |
| [docs/agentes.md](docs/agentes.md) | Cada agente, modelo e effort com as exceções, contrato de saída, variantes, como criar um |
| [docs/skills.md](docs/skills.md) | Cada skill, skills de uso direto × de fluxo, `preload`, skills do contexto, como escrever uma |
| [docs/contextos.md](docs/contextos.md) | Estrutura de um contexto, `context.toml` campo a campo, `include` × `reference`, políticas, criar e validar |
| [docs/configuracao.md](docs/configuracao.md) | `aidw.config.toml` campo a campo, perfis de exemplo, modelos, roteamento e MCPs |
| [docs/demandas-e-worktrees.md](docs/demandas-e-worktrees.md) | Pasta da demanda, worktrees, vários repositórios, `/aidw:diff`, retomar e limpar |
| [docs/comandos.md](docs/comandos.md) | Todos os comandos do chat e do `aidw.py` |
| [docs/claude-e-codex.md](docs/claude-e-codex.md) | Claude Code primeiro: no Codex só agentes e skills, o que é exclusivo do Claude, modo native × headless, arquivos gerados |
| [docs/mods.md](docs/mods.md) | Os mods do Claude Code (`aidw-mods`): métricas sozinhas, faixa da demanda, como escrever um mod |
| [docs/seguranca.md](docs/seguranca.md) | As camadas de proteção |
| [docs/solucao-de-problemas.md](docs/solucao-de-problemas.md) | Sintomas comuns e como resolver |