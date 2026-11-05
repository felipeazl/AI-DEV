# Solução de problemas

Comece sempre pelo `.\doctor.ps1` (`./doctor.sh`): ele mostra o que falta e termina com **READY** ou **NOT READY**.

| Sintoma | Causa provável | Solução |
|---|---|---|
| `/aidw:go` não aparece | Plugin não instalado, ou chat aberto antes do install | `python aidw.py install` e um chat novo |
| Mudei a config e nada mudou | O chat carrega as definições ao abrir | `python aidw.py install` (e `apply` para o modo projeto), e um chat novo |
| O chat responde no idioma errado | `[ui] language` sem valor, ou chat aberto antes da mudança | Defina `[ui] language` no `aidw.config.toml`, `install`, chat novo ([configuration.md](configuration.md#idioma)) |
| O Claude pede aprovação para um comando do `aidw.py` | O caminho foi escrito numa forma não liberada | Use `python "<raiz>/aidw.py" …`; rode o `install` se as regras sumiram |
| O painel de diff está vazio numa demanda com vários repositórios | O chat está na pasta da demanda, que não é um repositório | `/aidw:diff` para ir a um repositório |
| Headless falha com "OAuth session expired" | O login do CLI expirou | `claude auth login` (o `doctor` mostra "no login") |
| No Codex, `npm`/`node` falham com `EPERM` na sua pasta de usuário | O `node` do PATH mora no perfil do usuário (ex.: nvm), que o sandbox não lê | Instale o Node fora do perfil (ex.: em Program Files) e ponha-o na frente do PATH |
| No Codex, o orquestrador não consegue chamar os agentes | `multi_agent_v2` desligado | Abra com `python aidw.py open --provider codex`, ou ponha `[features] multi_agent_v2 = true` no `~/.codex/config.toml` |
| O `doctor` fala em sobras de instalação antiga no Codex | Perfil `aidw`, `aidw.rules` ou hooks do AiDW de um install anterior | `python aidw.py install --provider codex` remove |
| Uma delegação volta recusada com `AiDW (trava da delegação)` (em inglês, `AiDW (delegation lock)`) | O `Agent` quebrou uma regra (célula da tabela, `model`, formato do prompt, insumo colado) | O motivo diz o que corrigir ([mods.md](mods.md#travas-da-delegação)) |
| A faixa do AiDW não aparece acima do prompt | Sessão fora do modo orquestrador, demanda em `DONE`, faixa escondida ou `aidw-mods` não instalado | `/aidw:go`; `/strip`; `python aidw.py install` e um chat novo ([mods.md](mods.md)) |
| Um botão da faixa não abre o painel, ou a faixa está sem botões | A janela está estreita demais para o painel, ou o contexto tem `[mods] panel = false` | Alargue a janela (`/panel`, `/metrics` e `/review-tests` dizem o motivo); tire a linha do `context.toml` e rode o `install` ([panel.md](panel.md)) |
| O agente segue as regras do orquestrador | O `CLAUDE.md` do modo projeto carregado no agente | Já tratado com `omitClaudeMd`/`claudeMdExcludes`; reinstale |
| Chat na pasta de estado da demanda recebe as regras do orquestrador duas vezes | A pasta fica dentro da raiz do AiDW: o `CLAUDE.md` do modo projeto entrava junto com a skill `go` | O `demand set` grava `.claude/settings.json` com `claudeMdExcludes` na pasta da demanda; vale no próximo chat aberto nela |
| `dubious ownership` num agente do Codex | O AiDW não configura o Git do Codex (só agentes e skills) | `git config --global --add safe.directory <pasta>` para a pasta do repositório ou do worktree |
| `MCP figma` precisa de autenticação | OAuth não feito | Claude: `/mcp` → figma → Authenticate · Codex: `codex mcp login figma` |
| Modelo do Codex "não liberado para esta conta" | Modelo fora do seu plano | Tire o `model` do agente (vale o tier) ou escolha um liberado |
| Nome de agente inválido ou reservado | Colide com agente do CLI (`plan`, `explore`, `default`…) | Escolha outro `name` |
| O `worktree remove` recusa | Alteração local ou commit não publicado | Faça commit e push (com o seu OK) ou descarte, e tente de novo |
| O build falha no worktree e funciona no working copy | Uma dependência fora do Git não veio | `[worktree] link` ou o `worktree_link` do sistema no contexto |
| O `install` para dizendo que um arquivo foi alterado | Um arquivo gerado foi editado à mão | Leve a mudança para a fonte (config, contexto, núcleo) ou use `--force` |
