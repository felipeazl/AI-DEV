# Segurança

O princípio: **o modelo nunca é a última barreira.** Uma instrução no prompt pode ser esquecida, mal interpretada ou
contornada por um texto no código ou num card. Por isso o que tem risco é bloqueado por mecanismos que o modelo não
controla.

## Camadas

| Camada | Como funciona |
|---|---|
| **Regras globais do CLI** | O `install` grava no `~/.claude/settings.json` (ou nas `aidw.rules` do Codex): `deny` sempre para force push, `reset --hard`, `clean -f` e leitura de `.env`; `ask` para commit, push, merge, rebase, checkout e o que o contexto marcar. Valem em **toda** sessão, com ou sem orquestrador. `allow` só para a rotina (git de leitura, build, comandos do `aidw.py`) |
| **Guard (hook)** | Um agente do AiDW não edita o working copy principal de um repositório que tem worktree ativo. A conversa principal fica livre. Comandos de shell não são verificados (as tarefas apontam só para o worktree), com uma exceção: `git commit` num worktree de demanda que ainda tem ajuste de teste (`AIDW-TESTE`) é recusado, para qualquer sessão. No Codex, que não limita MCP por agente, o guard também recusa a ferramenta MCP fora do papel do agente ou bloqueada pelo contexto (ex.: comentar no card) |
| **Worktree** | O código da demanda fica fora do seu working copy; o `remove` recusa worktree com alteração local ou commit não publicado |
| **Escopo por agente** | Cada papel tem só as ferramentas, MCPs e pastas graváveis que precisa. O contexto pode bloquear ferramentas por papel (ex.: só o orquestrador comenta no card, depois do seu OK) |
| **Validadores do contexto** | Operações de risco passam por scripts que recusam o que não é permitido (ex.: SQL só leitura, executado dentro de `ROLLBACK`) |
| **Ação travada vira proposta** | O agente que precisa de uma ação travada devolve o comando ou texto exato com `policy_requires_approval`; o orquestrador junta as propostas e pede o OK uma vez. Uma recusa nunca é contornada com outra ferramenta, script ou comando |
| **Contextos privados** | O repositório do contexto é próprio e ignorado pelo Git do AiDW; o `doctor` e o `context check` dão erro se deixar de estar |
| **Segredos** | Nunca em arquivo, log, plano, revisão ou comentário. O `doctor` só confere se as variáveis existem; o `context list` mostra o remoto só pelo host |

## Políticas do núcleo

Em `orchestrator/policies/`, valem para o orquestrador e para todos os agentes:

| Política | Resumo |
|---|---|
| `git.md` | Nunca force push; nunca apagar branch protegida; nunca merge sem revisão e aprovação humana; branch por spec |
| `database.md` | Produção só leitura; operações destrutivas com aprovação; migração validada fora de produção; SQL gerado passa pelo `database-safe` |
| `production.md` | Nada de deploy, restart ou mudança de dado em produção sem aprovação; ambiente desconhecido é tratado como produção |
| `secrets.md` | Nunca imprimir segredo; nunca ler `.env`; referência só pelo nome da variável |
| `permissions.md` | O CLI aplica as regras geradas pelo `apply`; o que precisa de aprovação volta como recusa e é proposto |

O contexto acrescenta as do time (aprovações, ambientes permitidos, escrita no board, escopo).

## Quando você aprova

O fluxo roda sozinho na rotina (ler código, planejar, delegar, triar, build, testes, git local). Você aprova:

- git `commit`, `push`, `pull`, `merge`, `rebase`, `reset`, `checkout`/`switch`, `cherry-pick`, `revert`, `tag`, apagar branch;
- SQL de escrita e o que o contexto marcar;
- chamadas de API que mudam estado;
- comentários em card ou PR, todos juntos na revisão final;
- qualquer coisa que o contexto coloque em `ask`.

O prompt de permissão do CLI é o ponto de aprovação.
