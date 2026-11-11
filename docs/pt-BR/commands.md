# Comandos

## No chat

| Claude | Codex | O que faz |
|---|---|---|
| `/aidw:go [demanda]` | `$aidw-go` | Assume o chat como orquestrador: detecta o projeto, abre ou retoma a demanda, cria o worktree e conduz o fluxo. `pr <n>` depois da demanda revisa a PR de outra pessoa. Só roda quando você chama |
| `/aidw:survey <card ou texto>` | `$aidw-survey` | Levantamento antes de implementar (workflow `survey`, só leitura): valida cada ponto do card no código, mapeia o fluxo e grava `survey-<id>.md` com horas, story points, complexidade e dúvidas ([workflow.md](workflow.md#levantamento-survey)) |
| `/aidw:fix <demanda> <o quê>` | `$aidw-fix` | Correção depois da entrega numa demanda que já tem código (caminho curto): `bug <n>` (um Bug que a QA devolveu), `pr` (os comentários na PR da demanda) ou o texto do ajuste; a correção, a revisão só da correção e o reteste dos passos afetados, sem plano nem Task nova |
| `/aidw:ask <pergunta>` | `$aidw-ask` | Uma pergunta sobre o código, um contrato ou o ambiente, fora de uma demanda: o explorador responde com `arquivo:linha` em `answer-<id>.md` (demanda `ask-<slug>`); só leitura |
| `/aidw:investigate <erro, log ou registro>` | `$aidw-investigate` | Investiga um problema antes de haver card: o explorador prova a causa-raiz, o `investigation-<id>.md` traz o diagnóstico e as opções e, se for defeito, o documentador redige o Bug ou a dívida técnica (demanda `inv-<slug>`); criar só com o seu OK |
| `/aidw:card <ideia ou problema>` | `$aidw-card` | Redige uma User Story ou uma dívida técnica com base no código (`workitem-<id>.md`, demanda `card-<slug>`); criada no board só com o seu OK dos campos |
| `/aidw:kb-review [sistema, nota ou número]` | `$aidw-kb-review` | Revisa a base de conhecimento contra o código: `kb check`, as notas mais antigas (ou as pedidas), cada fato confirmado ou corrigido com `arquivo:linha`; as notas só mudam com o seu OK (demanda `kb-review-<data>`) |
| `/aidw:exit` | `$aidw-exit` | Grava a etapa e o próximo passo (`paused`) e devolve o chat ao normal |
| `/aidw:diff [repo\|exit]` | — | Leva a sessão para o worktree de um repositório da demanda; o painel de diff segue ([demands-and-worktrees.md](demands-and-worktrees.md#ver-o-diff-de-cada-repositório)) |
| `/aidw:done` | `$aidw-done` | Fecha a tarefa: grava no contexto o que ela ensinou (a nota da demanda e as notas da base que ela tocou; build e ambiente no `context.toml`), valida, reinstala, faz commit e push só do repositório do contexto e marca a demanda como `done` |
| `/aidw:knowledge [tema]` | `$aidw-knowledge` | Consulta a base de conhecimento do contexto: a nota de um sistema, contrato, conceito ou demanda, com os links e quem a cita; corrige uma nota quando você pede ([contexts.md](contexts.md#base-de-conhecimento)) |
| `/aidw:context [list]` | `$aidw-context` | Contextos, qual está ativo, repositório, sistemas, situação do plugin |
| `/aidw:context use <nome>` | `$aidw-context use <nome>` | Valida e ativa um contexto e regenera o ambiente |
| `/aidw:context create` | `$aidw-context create` | Cria um contexto novo (análise dos repositórios + no mínimo 10 perguntas) |
| `/strip` | — | Esconde ou mostra a faixa da demanda acima do prompt (mod, [mods.md](mods.md)) |
| `/panel [aba]` | — | Abre o painel Geral, ou o painel que tem a aba pedida ([panel.md](panel.md)) |
| `/metrics` | — | Abre o painel Métricas |
| `/review-tests` | — | Abre o painel Testes e Review (Dúvidas no levantamento); só informativo |

`/aidw:go`, `/aidw:survey`, `/aidw:fix`, `/aidw:ask`, `/aidw:investigate`, `/aidw:card`, `/aidw:kb-review`, `/aidw:exit` e `/aidw:done` só rodam quando você chama. As skills que os agentes usam ficam
fora do menu `/` no Claude (`user-invocable: false`); o Codex mostra toda skill `$aidw-*`.

## Linha de comando (`python aidw.py …`)

Sem comando, o `aidw.py` roda o `setup`. Os comandos com `--json` imprimem a saída em JSON.

### Instalação e diagnóstico

| Comando | O que faz |
|---|---|
| `setup [--reconfigure] [--skip-tools]` | Pré-requisitos, wizard (só sem config, ou com `--reconfigure`), pastas, `apply`, registro dos MCPs, `doctor`. É o que o `setup.ps1`/`setup.sh` chamam |
| `configure [--defaults [--provider claude\|codex] [--language <tag>]]` | Só o wizard; reescreve o `aidw.config.toml`. `--defaults` grava a configuração padrão sem perguntar |
| `apply [--dry-run]` | Gera o modo projeto a partir da config (idempotente) |
| `install [--provider claude\|codex\|all] [--dry-run] [--force] [--mcp]` | Claude (padrão): os plugins `aidw` e `aidw-mods` e as regras do AiDW no `~/.claude/settings.json`; `--mcp` também registra os MCPs do catálogo no escopo do usuário. Codex: **só** os agentes e as skills `aidw-*`. Sem `--provider`: o Claude, e o Codex quando ele já foi instalado. `--force` sobrescreve um arquivo gerado editado à mão |
| `uninstall [--provider claude\|codex\|all] [--dry-run]` | Remove só o que o `install` acrescentou (padrão `all`) |
| `doctor` | Núcleo, CLIs e login, contexto, variáveis, MCPs, pastas, instalação e ambiente gerado; termina com **READY** ou **NOT READY** |
| `status [--json]` | Visão rápida, sem chamar os CLIs: contexto, instalação, demandas ativas com etapa e worktree, e o que pede atenção |
| `show` | Nome, nome de exibição, papel, modelo, effort e tipo de cada agente, a pasta de estado e os idiomas |

### Dia a dia

| Comando | O que faz |
|---|---|
| `open [--provider claude\|codex] [--demand <id> [--repo <repo>] \| --path <pasta>] [--no-orchestrate] [--print] [--app]` | Abre o CLI no worktree da demanda (ou numa pasta), já chamando o orquestrador. `--print` só mostra o comando; `--app` (Codex) abre o app desktop do Codex |
| `chat` | Abre o orquestrador no modo projeto (chat na raiz do AiDW) |
| `project detect [--path <pasta>] [--json]` | Repositório, sistema do contexto e demanda de uma pasta |
| `demand set <id> [--step S] [--status active\|paused\|done] [--title t] [--note n] [--summary s] [--pr REPO=N] [--task TICKET=ID] [--loop ID\|-] [--extra-step STEP]` | Grava o estado da demanda (abaixo) |
| `demand show <id>` · `demand list [--active]` | Consulta o estado |
| `session bind [--demand <id>]` · `session unbind` | Põe esta sessão do Claude Code no (ou tira do) modo orquestrador e liga a demanda que ela conduz; `--session` substitui o `$CLAUDE_CODE_SESSION_ID` |
| `worktree create --repo <pasta> --demand <id> [--slug s] [--base b] [--pr n]` | Worktree da demanda, branch e junctions (idempotente); `--pr` cria o worktree só leitura da PR de outra pessoa |
| `worktree list` · `inspect <id>` · `remove <id>` · `cleanup` | Situação, remoção segura (`--repo` quando a demanda tem vários) e limpeza do registro |

Opções do `demand set`:

| Opção | Efeito |
|---|---|
| `--step` | Etapa atual: `UNDERSTAND`, uma ação do roteamento (`PLAN`, `REVIEW`, `TEST`, `PR`, `DONE`…), `CODE_REVIEW`/`QA_TEST` ou uma etapa de fora declarada pelo contexto |
| `--status` | `active`, `paused` ou `done` |
| `--title`, `--note` | Título do card; onde parou / próximo passo (o painel mostra a nota) |
| `--summary` | Do que se trata a demanda, até 4 linhas (o mapa da demanda no painel) |
| `--pr REPO=N` | A PR aberta de um dos repositórios da demanda (repetível) |
| `--task TICKET=ID` | O work item criado para uma entrega, ex.: `E1=5001` (repetível) |
| `--loop ID` | Um laço de correção depois da entrega (ex.: `bug-1234`): as rodadas de revisão dele contam a partir de 1; `-` limpa |
| `--extra-step STEP` | Uma etapa de fora do contexto pela qual a demanda passa (repetível; `-STEP` tira) |

### Contextos

| Comando | O que faz |
|---|---|
| `context list` | Lista os contextos |
| `context check <nome>` | Valida um contexto como se estivesse ativo: build completo, repositório Git próprio, ignorado pelo AiDW, pasta de estado exclusiva, base de conhecimento, upstream |
| `context upstream [--no-fetch]` | Faz o fetch dos upstreams do contexto ativo e avisa quando as cópias (`synced`) ou o checkout local ficaram atrás do remoto; roda no início de todo workflow |
| `context use [<nome>] [--skip-install]` | Ativa (nome vazio = nenhum), roda o `apply` e, se instalado, o `install` |
| `context create <nome> [--description d] [--mcp a,b] [--env A,B] [--language <tag>]` | Cria `contexts/<nome>/` com a estrutura mínima e repositório Git próprio |

### Base de conhecimento

| Comando | O que faz |
|---|---|
| `kb show <sistema\|nota> [--brief] [--json]` | Uma nota, os links dela e quem a cita (chave do sistema, nome, alias ou título). `--brief`: só a nota |
| `kb search <palavras> [--limit n] [--json]` | Notas com todas as palavras, sem acento nem caixa; título e palavras-chave pesam mais |
| `kb check [--json]` | Links quebrados, nomes repetidos, frontmatter, sistemas inexistentes, sistema sem nota, órfãs, texto com cara de segredo; avisa nota com mais de 150 linhas ou sem conferência há 6 meses (também roda no `context check`) |
| `kb index` | Regenera o `index.md`: as notas por tipo e o glossário dos conceitos |
| `kb collect <demanda> [--json]` | Junta o que a demanda aprendeu (as seções *Knowledge base* dos relatórios, o `learnings-<id>.md`, as notas do resumo, as decisões do plano) no `collect-<id>.md`, para o `/aidw:done` |

### Usados pelo orquestrador e pelos mods

| Comando | O que faz |
|---|---|
| `record --agent <nome> [--effort e] --label <x> --demand <pasta> [--state s] (--tokens N --tool-uses N --duration-ms N \| --codex-task <t>)` | Registra uma delegação nativa no `metrics.md` e imprime o cabeçalho e o resumo |
| `record-orchestrator --demand <pasta> --session <id> …` | Soma um turno do chat principal no `orchestrator-metrics.md` (rodado pelo mod) |
| `delegate --agent <a> --task <arquivo> --demand <pasta> [--effort e] [--model m] [--label x] [--max-turns n] [--timeout s]` | Roda um agente headless para uma tarefa (modo headless). `AIDW_DEBUG=1` grava um log de depuração na demanda |

## Scripts e testes

```powershell
.\setup.ps1          # ./setup.sh no Linux/macOS
.\doctor.ps1         # ./doctor.sh — só verifica, não altera nada
python -m unittest discover -s tests
python tests/test_apply.py --update     # regrava as referências quando a mudança de saída é intencional
```
