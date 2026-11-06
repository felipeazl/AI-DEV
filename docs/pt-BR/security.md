# Segurança

O princípio: **o modelo nunca é a última barreira.** Uma instrução no prompt pode ser esquecida, mal interpretada ou
contornada por um texto no código ou num card. Por isso o que tem risco é bloqueado por mecanismos que o modelo não
controla.

## Camadas

Todas as camadas abaixo são do **Claude Code**. No Codex o AiDW instala só agentes e skills: sem regras, sem guard, e
valem só as aprovações e o sandbox do próprio Codex ([claude-and-codex.md](claude-and-codex.md)).

| Camada | Como funciona |
|---|---|
| **Regras globais do CLI** | O `install` grava no `~/.claude/settings.json`: `deny` para force push, `reset --hard`, `clean -f` e leitura de `.env` (o `[policies] deny` padrão); `ask` para o que o seu `[policies] ask` e o `ask`/`git_ask` do contexto listam (em geral commit, push, merge, rebase, checkout, SQL de escrita); `allow` só para a rotina (os comandos do `aidw.py`, o `allow` do contexto). Valem em **toda** sessão, com ou sem orquestrador |
| **Guard (hook)** | Um agente do AiDW não edita o working copy principal de um repositório com worktree de demanda ativo; a conversa principal fica livre. Comandos de shell não são verificados (as tarefas apontam só para o worktree), com uma exceção: `git commit` num worktree de demanda que ainda tem ajuste de teste (`AIDW-TEST`) é recusado, em qualquer sessão |
| **Worktree** | O código da demanda fica fora do seu working copy; o `worktree remove` recusa worktree com alteração local ou commit não publicado |
| **Escopo por agente** | Cada papel tem só as ferramentas e os MCPs que precisa (`tools`/`disallowedTools` do subagente). O contexto pode bloquear ferramentas por papel (ex.: só o orquestrador comenta no card, depois do seu OK) |
| **Validadores do contexto** | Operações de risco passam por scripts que recusam o que não é permitido (ex.: SQL só leitura, executado dentro de `ROLLBACK`) |
| **Ação travada → proposta** | O agente que precisa de uma ação travada devolve o comando ou texto exato com `policy_requires_approval`; o orquestrador junta as propostas e pede o seu OK uma vez. Uma recusa nunca é contornada com outra ferramenta, script ou comando |
| **Travas da delegação (mod)** | O `aidw-mods` recusa uma delegação com `subagent_type` inesperado, um `model` que você não pediu, sem a pasta da demanda ou com insumo colado ([mods.md](mods.md#travas-da-delegação)) |
| **Filtro de segredos (mod)** | O resultado das ferramentas é mascarado antes de entrar na conversa: ficam só o nome e o tamanho do segredo ([mods.md](mods.md#filtro-de-segredos)) |
| **Contextos privados** | O repositório do contexto é próprio e ignorado pelo Git do AiDW; o `doctor` e o `context check` dão erro se deixar de ser |
| **Segredos** | Nunca em arquivo, log, plano, revisão ou comentário. O `doctor` só confere se as variáveis existem; o `context list` mostra o remoto só pelo host |

## Políticas do núcleo

Em `orchestrator/policies/`, para o orquestrador e todos os agentes:

| Política | Resumo |
|---|---|
| `git.md` | Nunca force push; nunca apagar branch protegida; nunca merge sem revisão e aprovação humana; nunca reescrever histórico publicado; uma branch por spec |
| `database.md` | Produção só leitura; operações destrutivas com aprovação; migração validada fora de produção; SQL gerado passa pelo `database-safe` |
| `production.md` | Nada de deploy, restart, mudança de configuração ou de dado em produção sem aprovação; ambiente desconhecido é tratado como produção |
| `secrets.md` | Nunca imprimir segredo; nunca ler `.env`; referência só pelo nome da variável |
| `permissions.md` | O CLI aplica as regras geradas pelo `apply`/`install`; o que precisa de aprovação volta como recusa e é proposto |

O contexto acrescenta as do time (aprovações, ambientes permitidos, escrita no board, escopo).

## Quando você aprova

O fluxo roda sozinho na rotina (ler código, planejar, delegar, build, testes, git local). Você aprova:

- as operações git que o contexto marca como `ask` (em geral `commit`, `push`, `pull`, `merge`, `rebase`, `reset`,
  `checkout`/`switch`, `cherry-pick`, `revert`, `tag`, apagar branch);
- SQL de escrita e o que mais o contexto marcar;
- chamadas de API que mudam estado;
- comentários em card ou PR (as pendências para a QA no OK da PR; na PR de outro dev, na revisão final);
- o que estiver na sua lista `ask` ou na do contexto.

O prompt de permissão do CLI é o ponto de aprovação.
