# Solução de problemas

Comece sempre pelo `.\doctor.ps1`: ele mostra o que falta e termina com **PRONTO** ou **NÃO PRONTO**.

| Sintoma | Causa provável | Solução |
|---|---|---|
| `/aidw:orquestrar` não aparece | Plugin não instalado, ou chat aberto antes do install | `python aidw.py install` e um chat novo |
| Mudei a config e nada mudou | O chat carrega a definição ao abrir | `python aidw.py apply` e `install`, e um chat novo |
| O Claude pede aprovação para um comando do `aidw.py` | Caminho escrito numa forma não liberada | Use `python "<raiz>/aidw.py" …`; rode `install` se as regras sumiram |
| O painel de diff está vazio numa demanda com vários repositórios | O chat está na pasta da demanda, que não é um repositório | `/aidw:diff` para ir a um repositório |
| Headless falha com "OAuth session expired" | Login do CLI expirou | `claude auth login` (o `doctor` mostra "sem login") |
| Ferramenta PowerShell do Claude falha com "Linha de comando muito longa" | Problema do ambiente, também fora do AiDW | O modelo cai para o Bash; nada a fazer no AiDW |
| No Codex, `npm`/`node` falham com `EPERM` em `C:\Users\<você>` | O `node` do PATH mora no perfil do usuário (ex.: nvm), que o sandbox não lê | O `install --provider codex` põe um Node de fora do perfil na frente do PATH do perfil `aidw`; se não houver, instale um |
| O Codex não roda os hooks do AiDW | Confiança não aprovada, ou invalidada por mudança no hook | `codex --profile aidw` num terminal → "Trust all and continue" |
| O agente segue regras do orquestrador | `CLAUDE.md` do modo projeto carregado no agente | Já tratado com `omitClaudeMd`/`claudeMdExcludes`; reinstale |
| `dubious ownership` num agente Codex | Repositório fora das pastas liberadas | Acrescente a pasta em `project_dirs` e rode `apply` |
| `MCP figma precisa de autenticação` | OAuth não feito | Claude: `/mcp` → figma → Authenticate · Codex: `codex mcp login figma` |
| `modelo … não está liberado para esta conta` | Modelo do Codex fora do plano | Tire o `model` do agente (vale o tier) ou escolha um liberado |
| Nome de agente inválido ou reservado | Colide com agente do CLI (`plan`, `explore`, `default`…) | Escolha outro `name` |
| `worktree remove` recusa | Alteração local ou commit não publicado | Faça commit e push (com o seu OK) ou descarte, e tente de novo |
| Build falha no worktree e funciona no working copy | Dependência fora do Git que não veio | `[worktree] link` ou `worktree_link` do sistema no contexto |
| `install` para dizendo que um arquivo foi alterado | Um arquivo gerado foi editado à mão | Leve a mudança para a fonte (config, contexto, núcleo) ou use `--force` |
