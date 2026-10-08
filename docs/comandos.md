# Comandos

## No chat

| Claude | Codex | O que faz |
|---|---|---|
| `/aidw:orquestrar [demanda] [auto\|interativo]` | `$aidw-orquestrar` | Assume o chat como orquestrador: detecta o projeto, abre ou retoma a demanda, cria o worktree e conduz o fluxo até a revisão final. Só roda quando você chama |
| `/aidw:levantamento <card ou texto>` | `$aidw-levantamento` | Levantamento antes de implementar (workflow `levantamento`, só leitura): valida cada ponto do card no código, mapeia o fluxo e grava `levantamento-<id>.md` com horas, story points, complexidade e dúvidas ([fluxo.md](fluxo.md#levantamento-de-demanda)) |
| `/aidw:sair` | `$aidw-sair` | Grava a etapa e o próximo passo (`paused`) e volta o chat ao normal |
| `/aidw:diff [repo\|sair]` | — | Leva a sessão para o worktree de um repositório da demanda; o painel de diff segue ([demandas-e-worktrees.md](demandas-e-worktrees.md#ver-o-diff-de-cada-repositório)) |
| `/aidw:done` | `$aidw-done` | Fecha a tarefa: grava no contexto o que ela ensinou (a nota da demanda e as notas da base de conhecimento que ela tocou; build e ambiente no `context.toml`), valida, reinstala, faz commit e push só do repositório do contexto e marca a demanda como `done` |
| `/aidw:conhecimento [tema]` | `$aidw-conhecimento` | Consulta a base de conhecimento do contexto: a nota de um sistema, contrato, conceito ou demanda, com os links e quem a cita; corrige uma nota quando você pede ([contextos.md](contextos.md#base-de-conhecimento)) |
| `/aidw:contexto-listar` | `$aidw-contexto-listar` | Contextos, qual está ativo, repositório, sistemas, situação do plugin |
| `/aidw:contexto-usar <nome>` | `$aidw-contexto-usar` | Valida e ativa um contexto e regenera o ambiente |
| `/aidw:contexto-criar` | `$aidw-contexto-criar` | Cria um contexto novo (análise + no mínimo 10 perguntas) |

## Linha de comando (`python aidw.py …`)

### Instalação e diagnóstico

| Comando | O que faz |
|---|---|
| `setup [--reconfigure] [--skip-tools]` | Pré-requisitos, wizard, pastas, `apply`, MCPs e `doctor` (é o que o `setup.ps1` chama) |
| `configure [--defaults --provider codex]` | Só o wizard; reescreve o `aidw.config.toml` |
| `apply [--dry-run]` | Gera o modo projeto a partir da config (idempotente) |
| `install [--provider claude\|codex\|all] [--dry-run] [--force] [--mcp]` | Claude (padrão): plugin `aidw` e regras globais; `--mcp` registra os MCPs do catálogo. Codex: skills `aidw-*` em `~/.agents/skills`, agentes `aidw-*` em `~/.codex/agents`, `aidw.rules`, hooks (merge) e o perfil `aidw` |
| `uninstall [--provider claude\|codex\|all] [--dry-run]` | Remove só o que o `install` acrescentou |
| `doctor` | Núcleo, CLIs e login, contexto, variáveis, MCPs, pastas, instalação e ambiente gerado; termina com **PRONTO** ou **NÃO PRONTO** |
| `status [--json]` | Visão rápida, sem chamar os CLIs: contexto, instalação, demandas ativas com etapa e worktree, e o que pede atenção (inclusive demanda concluída com aprendizados que não foram para a base de conhecimento) |
| `show` | Nome, papel, modelo e effort de cada agente |

### Dia a dia

| Comando | O que faz |
|---|---|
| `open [--provider claude\|codex] [--demand <id> [--repo <repo>] \| --path <pasta>] [--no-orchestrate] [--print]` | Abre o CLI na demanda (ou na pasta), já chamando o orquestrador. `--print` só mostra o comando |
| `chat` | Abre o orquestrador do modo projeto (chat na raiz do AiDW) |
| `project detect [--path p] [--json]` | Repositório principal, sistema do contexto e demanda de uma pasta |
| `demand set <id> [--step S] [--status active\|paused\|done] [--mode auto\|interativo] [--title t] [--note n]` | Grava o estado da demanda |
| `demand show <id>` · `demand list [--active]` | Consulta |
| `worktree create --repo <pasta> --demand <id> [--slug s] [--base b]` | Worktree da demanda, branch, junctions (idempotente) |
| `worktree list` · `inspect <id>` · `remove <id>` · `cleanup` | Situação, remoção segura e limpeza do registro |

### Contextos

| Comando | O que faz |
|---|---|
| `context list` | Lista |
| `context check <nome>` | Valida (build completo com o contexto, repositório próprio, pasta de estado exclusiva, base de conhecimento) |
| `context use [<nome>]` | Ativa (troca só a linha `active`) |
| `context create <nome> --description d` | Cria a estrutura com git próprio |

### Base de conhecimento

| Comando | O que faz |
|---|---|
| `kb show <sistema\|nota> [--json]` | Uma nota, os links dela e quem a cita (aceita a chave do sistema, o nome, um alias ou o título) |
| `kb search <palavras> [--limit n] [--json]` | Notas com todas as palavras, sem acento nem caixa; título e alias pesam mais |
| `kb check [--json]` | Links quebrados, nomes repetidos, frontmatter, `sistemas` inexistentes, sistema sem nota, órfãs e texto com cara de segredo; avisa nota com mais de 150 linhas e sem conferência há mais de 6 meses (também roda no `context check`) |
| `kb index` | Regenera o `index.md`: as notas por tipo e o glossário dos conceitos |

### Usados pelo orquestrador

| Comando | O que faz |
|---|---|
| `record --agent <a> --level <n> --label <x> --demand <pasta> --state <s> (--tokens --tool-uses --duration-ms \| --codex-task <t>)` | Registra uma delegação nativa no `metricas.md` e imprime cabeçalho e resumo |
| `delegate --agent <a> --effort <e> --level <n> --task <arq> --demand <pasta>` | Roda um agente headless para uma tarefa. `AIDW_DEBUG=1` grava um log de depuração na demanda |

## Scripts e testes

```powershell
.\setup.ps1          # ./setup.sh no Linux/macOS
.\doctor.ps1         # ./doctor.sh — só verifica, não altera nada
python -m unittest discover -s tests
python tests/test_apply.py --update     # regrava as referências quando a mudança de saída é intencional
```
