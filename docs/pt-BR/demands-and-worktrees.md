# Demandas e worktrees

Toda demanda que muda código ganha **o próprio git worktree**: uma cópia de trabalho separada, numa branch própria,
ligada ao mesmo repositório. Os agentes trabalham ali; o seu working copy principal nunca é tocado. Pedidos só de
leitura não precisam de worktree.

## Por que worktree

- **Isolamento:** você continua trabalhando (ou com outra demanda aberta) no working copy enquanto o agente trabalha em
  outro lugar.
- **Várias demandas ao mesmo tempo:** cada uma no seu worktree, na sua branch.
- **Diff limpo:** o que o agente mudou é exatamente o diff do worktree contra a base.
- **Proteção:** um hook impede que um agente do AiDW edite o working copy principal de um repositório com worktree de
  demanda ativo.

## A pasta da demanda

```text
C:\wt\                                   ← [worktree] root
└── us-1234\                             ← a pasta da demanda: o chat fica aqui quando há mais de um repositório
    ├── App\                             ← worktree do back (branch feature/1234-ajuste-taxa)
    ├── App.Front\                       ← worktree do front (mesma demanda, mesma branch)
    └── Compartilhado\                   ← junction para uma pasta vizinha (worktree_link)
```

- Branch `<branch_prefix do contexto><número>-<slug>` (prefixo `aidw/` sem contexto), criada a partir da base que o
  plano define (por padrão a branch padrão do origin; pode ser a branch não mergeada de outra pessoa da qual a demanda
  depende).
- `packages/` e `node_modules/` entram por **junction** a partir do working copy principal (o `[worktree] link` do
  contexto muda a lista): o build roda sem restaurar tudo de novo.
- O registro fica em `state/worktrees.json`; os repositórios da demanda, no `demand.json` dela.

### Repositórios com o mesmo nome

Dois repositórios com o mesmo nome (ex.: `C:/Novos/Portal` e `C:/Legado/Portal`) não dividem a pasta: o segundo fica em
`<root>/<demanda>/<repo>.<pasta-mãe>`.

### Pastas vizinhas (`worktree_link`)

Código legado às vezes alcança outro repositório por caminho relativo (ex.: um HintPath
`..\..\Compartilhado\bin\x.dll`). Num worktree esse caminho não existiria. Por isso um sistema pode listar
`worktree_link = ["../Compartilhado"]` no `context.toml`:

- O `worktree create` cria, ao lado do worktree, uma junction com o mesmo caminho relativo, apontando para o que ele
  resolve a partir do working copy principal.
- Se a demanda também tem worktree desse repositório, ele já está ali, e o build usa a versão da demanda. Se a junction
  veio antes, ela vira o worktree quando ele é criado.
- O `remove` do último worktree da demanda tira as junctions, sem apagar nada através delas.
- Caminhos que sobem além da pasta da demanda (`../../Outra`) ficam na raiz, compartilhados.

Worktrees criados antes da pasta por demanda, em `<root>/<repo>/<demanda>`, continuam funcionando onde estão.

## Para onde o chat vai

| Situação | O chat vai para |
|---|---|
| Um repositório, app desktop do Claude | o worktree (`change_directory` do app; o painel de diff segue) |
| Vários repositórios, app desktop | a pasta da demanda |
| Sem worktree (só leitura, ou repositórios usados no lugar, como numa demanda importada), app desktop | a pasta de estado da demanda (`<state_dir>/<id>`), que toda demanda tem |
| Terminal do Claude | `EnterWorktree` com o id da demanda |
| Codex | não muda de pasta: todo comando e toda tarefa usam o caminho absoluto do worktree |
| Chat já na pasta da demanda ou num worktree dela | fica onde está |
| Chat aberto na raiz do AiDW | entra no worktree da demanda (com vários, no primeiro criado) |
| Chat aberto em outro repositório | cria o worktree desse repositório para a mesma demanda |

Se o working copy principal tem alterações locais, o `worktree create` avisa e o orquestrador pergunta uma vez.

No app desktop, depois de mudar (ou quando o chat já abriu na pasta da demanda), o orquestrador também adiciona à sessão
a **pasta do contexto ativo** (e a pasta de estado, quando ela fica fora do contexto) com o `request_directory` do app,
uma vez por sessão, para que o plano, o roteiro de testes e os relatórios abram no app. O `aidw open --demand` faz o
mesmo com `--add-dir`.

## Ver o diff de cada repositório

O painel de diff do app mostra o repositório da pasta atual da sessão. Numa demanda com vários repositórios:

```text
/aidw:diff            ← vai para o próximo repositório da demanda, em círculo
/aidw:diff front      ← vai direto para um (pelo nome da pasta; um pedaço do nome basta)
/aidw:diff exit       ← volta para a pasta da demanda
```

O chat, o contexto da conversa e o modo orquestrador continuam: você aponta algo no front, troca para o back, aponta
outra coisa, tudo na mesma sessão. O orquestrador também troca quando você pede ("mostra o diff do back").

- **App desktop:** usa o `change_directory` do app, e o painel segue.
- **Terminal:** `ExitWorktree` e `EnterWorktree` com `<demanda>/<pasta>`; `exit` volta para onde a sessão abriu.
- **Codex:** não disponível (não há como mudar a pasta da sessão).

Sem worktrees (repositórios usados no lugar), o `/aidw:diff` percorre os `repos` do `demand.json` e o `exit` volta para
a pasta de estado da demanda. As pastas extras do app (o botão de pasta com +) liberam acesso a outra pasta, mas o
painel de diff não as mostra: use o `/aidw:diff`.

## Abrir e retomar

```powershell
python aidw.py open --demand 1234                    # abre o Claude na demanda já chamando /aidw:go
python aidw.py open --demand 1234 --repo App.Front   # num repositório; os outros entram por --add-dir
python aidw.py open --provider codex --demand 1234   # o Codex no worktree, com multi_agent_v2 e a pasta do AiDW
python aidw.py open --demand 1234 --no-orchestrate   # só abre, sem chamar o orquestrador
```

`1234` acha `us-1234`. No chat, `/aidw:go` sem argumento numa pasta de worktree acha a demanda e continua da etapa
gravada.

## Consultar e limpar

```powershell
python aidw.py worktree list            # todos (pasta, branch, alterações, commits não publicados)
python aidw.py worktree inspect us-1234
python aidw.py worktree remove us-1234  # só com worktree limpo e commits publicados; a branch fica
python aidw.py worktree cleanup         # tira do registro o que sumiu do disco
python aidw.py status                   # inclui worktrees de demandas concluídas e órfãos
```

Apagar a branch é ação travada: peça ao orquestrador, que pede o seu OK.

## Worktree da PR de outra pessoa

Para revisar a PR que outra pessoa abriu (workflow `pr-review`):

```powershell
python aidw.py worktree create --repo C:\Repos\App --demand us-1234 --pr 5678
```

- Busca `refs/pull/<n>/merge` no `origin`: a PR já mesclada no destino, como ficaria depois do merge. Funciona no Azure
  Repos e no GitHub. Se a ref não existe, a PR é de outro repositório, já foi concluída ou tem conflito com o destino.
- Cria o worktree em `<root>/<demanda>/<repo>`, **destacado e sem branch**, com as junctions de dependências e as pastas
  vizinhas, e grava `diff-pr<n>-<repo>.patch` na pasta da demanda. No registro, `base` é o commit do destino, `source` a
  ponta da PR e `head` o merge.
- Rodar de novo depois que o autor atualiza a PR leva o worktree à versão nova (recusa se houver alteração local) e grava
  `diff-pr<n>-<repo>-r<N>.patch` só com o que mudou, nos arquivos da PR.
- Um repositório por demanda: a mesma demanda não pode ter a PR e uma branch de trabalho no mesmo repositório.
- O `worktree remove` tira as junctions antes e remove o worktree e a ref da PR; não há branch para manter.

## Estado da demanda

```powershell
python aidw.py demand list --active
python aidw.py demand show us-1234
python aidw.py demand set us-1234 --step REVIEW --status paused --note "esperando o QA"
```

O `demand.json` guarda a etapa, o status (`active`, `paused`, `done`), o resumo, os repositórios, Tasks, PRs e o
histórico das etapas. É o que permite fechar o chat e voltar depois. Todas as opções do `demand set`:
[commands.md](commands.md#dia-a-dia).
