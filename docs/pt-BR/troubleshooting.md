# Solução de problemas

Problemas comuns e como resolvê-los. Comece sempre pelo `.\doctor.ps1` (`./doctor.sh` no Linux/macOS): ele confere
tudo, não altera nada e termina com **READY** ou **NOT READY** e a lista do que corrigir. O `.\setup.ps1`
(`./setup.sh`) corrige a maior parte do que ele aponta e pode ser rodado de novo a qualquer momento.

## Primeira instalação

| Sintoma | Causa provável | Solução |
|---|---|---|
| `Python 3.11+ not found` | Sem Python, ou com uma versão anterior à 3.11 | Instale o Python 3.11+ (o `setup.ps1` oferece o `winget`), reabra o terminal e rode o setup de novo |
| `aidw.config.toml not found` | O setup ainda não rodou nesta máquina | `.\setup.ps1` (`./setup.sh`): o wizard cria o arquivo |
| `doctor`: `git not found`, `` CLI `claude` not found `` ou `npx not found` | Falta um pré-requisito (o Node.js é usado pelos MCPs locais) | Instale com o comando que o `doctor` mostra (o setup oferece instalar), reabra o terminal e rode o setup de novo |
| `doctor`: `not logged in`, ou uma execução headless falha com login expirado | O CLI do Claude Code não está autenticado | Rode `claude` uma vez e faça login (Codex: `codex login`) |
| `` context '<nome>' not found `` | A config aponta para um contexto cuja pasta não está em `contexts/` (um contexto é um repositório Git próprio) | Clone o repositório de contexto do time em `contexts/<nome>/`, ou rode o `setup` para escolher outro, criar um ou seguir sem contexto |
| `doctor`: `` MCP '<nome>' not registered in claude (required by the context) `` | O contexto exige um servidor MCP que você não adicionou | Rode o comando que o `doctor` mostra (o `setup` oferece rodá-lo) |
| `doctor`: `MCP <nome> needs authentication` | OAuth não feito (ex.: Figma) | Claude: `/mcp` → o servidor → Authenticate · Codex: `codex mcp login <nome>` |
| `doctor`: `MCP <nome> with status 'Pending approval'` | O Claude Code ainda não aprovou os MCPs de projeto do AiDW | Não afeta o plugin; para limpar, rode `claude` uma vez na pasta do AiDW e aprove |
| `doctor`: `could not confirm the login` | O `claude auth status` não respondeu (é aviso, não erro) | Se um chat abre normalmente, nada a fazer; senão rode `claude` e faça login |
| `doctor`: `allowed folder … does not exist` | Um caminho do `[workspace] project_dirs` (ou do contexto) não existe | Clone os repositórios ou corrija o caminho no `aidw.config.toml` |
| `doctor`: `the worktree root (…) is inside a Git repository` | O `[worktree] root` aponta para dentro de um repositório | Use uma pasta curta fora de qualquer repositório, ex.: `C:/wt` |
| `doctor`: `environment not generated yet` ou `file(s) out of date` | O `apply` não rodou desde a última mudança | `python aidw.py apply` e um chat novo |
| `install`: `the plugin install is Claude's` | `[provider] name = "codex"` | `python aidw.py install --provider codex` ([claude-and-codex.md](claude-and-codex.md)) |
| `install`: `the global install uses native subagents` | `[delegation] mode = "headless"` | Ponha `mode = "native"`; o headless só funciona no modo projeto |
| `install`: `settings.json is not valid JSON` | O `~/.claude/settings.json` quebrou numa edição manual | Corrija o JSON e rode o `install` de novo |
| `/aidw:go` não aparece, ou o `doctor` diz que o plugin falta ou está desatualizado | Plugin não instalado, ou o chat (ou o app desktop) aberto antes do install | `python aidw.py install` e um chat novo |

## Dia a dia

| Sintoma | Causa provável | Solução |
|---|---|---|
| Mudei a config e nada mudou | O chat carrega as definições ao abrir | `python aidw.py install` (e `apply` para o modo projeto), e um chat novo |
| O chat responde no idioma errado | `[ui] language` sem valor, ou chat aberto antes da mudança | Defina `[ui] language` no `aidw.config.toml`, `install`, chat novo ([configuration.md](configuration.md#idioma)) |
| O Claude pede aprovação para um comando do `aidw.py` | O caminho foi escrito numa forma não liberada | Use `python "<raiz>/aidw.py" …`; rode o `install` se as regras sumiram |
| O painel de diff está vazio numa demanda com vários repositórios | O chat está na pasta da demanda, que não é um repositório | `/aidw:diff` para ir a um repositório |
| Uma delegação volta recusada com `AiDW (trava da delegação)` (em inglês, `AiDW (delegation lock)`) | O `Agent` quebrou uma regra (célula da tabela, `model`, formato do prompt, insumo colado) | O motivo diz o que corrigir ([mods.md](mods.md#travas-da-delegação)) |
| A faixa do AiDW não aparece acima do prompt | Sessão fora do modo orquestrador, demanda em `DONE`, faixa escondida ou `aidw-mods` não instalado | `/aidw:go`; `/strip`; `python aidw.py install` e um chat novo ([mods.md](mods.md)) |
| Um botão da faixa não abre o painel, ou a faixa está sem botões | A janela está estreita demais para o painel, ou o contexto tem `[mods] panel = false` | Alargue a janela (`/panel`, `/metrics` e `/review-tests` dizem o motivo); tire a linha do `context.toml` e rode o `install` ([panel.md](panel.md)) |
| O agente segue as regras do orquestrador | O `CLAUDE.md` do modo projeto carregado no agente | Já tratado com `omitClaudeMd`/`claudeMdExcludes`; reinstale |
| Chat na pasta de estado da demanda recebe as regras do orquestrador duas vezes | A pasta fica dentro da raiz do AiDW: o `CLAUDE.md` do modo projeto entrava junto com a skill `go` | O `demand set` grava `.claude/settings.json` com `claudeMdExcludes` na pasta da demanda; vale no próximo chat aberto nela |
| Nome de agente inválido ou reservado | Colide com agente do CLI (`plan`, `explore`, `default`…) | Escolha outro `name` |
| O `worktree remove` recusa | Alteração local ou commit não publicado | Faça commit e push (com o seu OK) ou descarte, e tente de novo |
| O build falha no worktree e funciona no working copy | Uma dependência fora do Git não veio | No `context.toml`: `[worktree] link` (pastas ligadas em todo worktree; padrão `packages`, `node_modules`) ou o `worktree_link` do sistema |
| O `install` para dizendo que um arquivo `was changed outside AiDW` | Um arquivo gerado foi editado à mão | Leve a mudança para a fonte (config, contexto, núcleo) ou use `--force` |

## Só no Codex

| Sintoma | Causa provável | Solução |
|---|---|---|
| `npm`/`node` falham com `EPERM` na sua pasta de usuário | O `node` do PATH mora no perfil do usuário (ex.: nvm), que o sandbox não lê | Instale o Node fora do perfil (ex.: em Program Files) e ponha-o na frente do PATH |
| O orquestrador não consegue chamar os agentes | `multi_agent_v2` desligado | Abra com `python aidw.py open --provider codex`, ou ponha `[features] multi_agent_v2 = true` no `~/.codex/config.toml` |
| O `doctor` fala em sobras de instalação antiga | Perfil `aidw`, `aidw.rules` ou hooks do AiDW de um install anterior | `python aidw.py install --provider codex` remove |
| `dubious ownership` num agente | O AiDW não configura o Git do Codex (só agentes e skills) | `git config --global --add safe.directory <pasta>` para a pasta do repositório ou do worktree |
| `model … is not enabled for this account` | Modelo do Codex fora do seu plano | Tire o `model` do agente (vale o tier) ou escolha um liberado |
