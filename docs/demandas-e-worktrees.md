# Demandas e worktrees

Toda demanda que muda código ganha **o próprio git worktree**: uma cópia de trabalho separada, numa branch própria,
ligada ao mesmo repositório. Os agentes trabalham ali; o seu working copy principal nunca é tocado. Pedidos só de
leitura não precisam de worktree.

## Por que worktree

- **Isolamento:** você continua trabalhando (ou com outra demanda aberta) no working copy, sem o agente mexer nos seus
  arquivos.
- **Várias demandas ao mesmo tempo:** cada uma no seu worktree, na sua branch.
- **Diff limpo:** o que o agente mudou é exatamente o diff do worktree contra a base.
- **Proteção:** um hook impede que um agente do AiDW edite o working copy principal de um repositório com worktree
  ativo.

## A pasta da demanda

```text
C:\wt\                                   ← [worktree] root
└── us-1234\                             ← a pasta da demanda: o chat fica aqui quando há mais de um repositório
    ├── Pagamentos\                      ← worktree do back (branch feature/1234-ajuste-taxa)
    ├── Pagamentos.Front\                ← worktree do front (mesma demanda, mesma branch)
    └── Compartilhado\                   ← junction de uma pasta vizinha (worktree_link)
```

- Branch `<branch_prefix do contexto><número>-<slug>`, criada a partir da base que o plano define (inclusive uma
  branch não mergeada de outra pessoa, quando a demanda depende dela).
- `packages/` e `node_modules/` entram por **junction** a partir do working copy principal: o build roda sem
  restaurar tudo de novo.
- O registro fica em `state/worktrees.json`; os repositórios da demanda, no `demand.json`.

### Repositórios com o mesmo nome

Dois repositórios com o mesmo nome (ex.: `C:/Novos/Portal` e `C:/Legado/Portal`) não dividem a pasta: o que chegar
depois fica em `<root>/<demanda>/<repo>.<pasta-mãe>`.

### Pastas vizinhas (`worktree_link`)

Código legado às vezes alcança outro repositório por caminho relativo (ex.: um HintPath
`..\..\Compartilhado\bin\x.dll`). Num worktree, esse caminho não existiria. Por isso o sistema pode listar
`worktree_link = ["../Compartilhado"]` no `context.toml`:

- O `worktree create` cria, ao lado do worktree, uma junction com o mesmo caminho relativo, apontando para o que ele
  resolve a partir do working copy principal.
- Se a demanda também tem worktree desse repositório, ele já está ali, e o build usa a versão da demanda. Se a
  junction veio antes, ela vira o worktree quando ele é criado.
- O `remove` do último worktree da demanda tira as junctions, sem apagar nada através delas.
- Caminhos que sobem além da pasta da demanda (`../../Outra`) ficam na raiz, compartilhados.

### Formato antigo

Worktrees criados antes da pasta por demanda, em `<root>/<repo>/<demanda>`, continuam funcionando onde estão.

## Onde o chat fica

| Situação | Para onde o chat vai |
|---|---|
| Demanda com um repositório, app desktop do Claude | o worktree (`change_directory` do app; o painel de diff segue) |
| Demanda com vários repositórios, app desktop | a pasta da demanda |
| Terminal do Claude | `EnterWorktree` com o nome `<demanda>` |
| Codex | não muda de pasta: todo comando e toda tarefa usam o caminho absoluto do worktree |
| Chat já aberto na pasta da demanda ou num worktree dela | fica onde está |
| Chat aberto na raiz do AiDW | entra no worktree da demanda (com vários, no primeiro criado) |
| Chat aberto em outro repositório | cria o worktree desse repositório para a mesma demanda |

Se o working copy principal tem alterações locais, o `worktree create` avisa e o orquestrador pergunta uma vez.

No app desktop, depois de mudar (ou quando o chat já abriu na pasta da demanda), o orquestrador também adiciona à
sessão a **pasta do contexto ativo** (ex.: `contexts/safeweb`, que tem a pasta `demandas/`) com o
`request_directory` do app, uma vez por sessão. Assim o plano, o plano de testes, os relatórios e a documentação
gerada na demanda abrem no app, que só abre arquivos das pastas da sessão. Se o estado das demandas (`state_dir`)
ficar fora da pasta do contexto, ele entra também. O `aidw open --demand` faz o mesmo com `--add-dir`.

## Ver o diff de cada repositório

O painel de diff do app mostra o repositório da pasta atual da sessão. Numa demanda com vários repositórios:

```text
/aidw:diff            ← vai para o próximo repositório da demanda, em círculo
/aidw:diff front      ← vai direto para um repositório (pelo nome da pasta)
/aidw:diff sair       ← volta para a pasta da demanda
```

O chat, o contexto da conversa e o modo orquestrador continuam: você aponta algo no front, troca para o back, aponta
outra coisa, tudo na mesma sessão. O orquestrador também troca quando você pede "mostra o diff do back".

- **App desktop:** usa o `change_directory` do app, e o painel segue.
- **Terminal:** `ExitWorktree` e `EnterWorktree` com `<demanda>/<pasta>`; `sair` volta para a pasta onde a sessão abriu.
- **Codex:** não disponível (não há como mudar a pasta da sessão).

As pastas extras do app (o botão de pasta com +) liberam acesso a outra pasta, mas o painel de diff não as mostra:
para o diff, use o `/aidw:diff`.

## Abrir e retomar

```powershell
python aidw.py open --demand 1234                    # abre o Claude na demanda já chamando /aidw:orquestrar
python aidw.py open --demand 1234 --repo Front       # num repositório específico; os outros entram por --add-dir
python aidw.py open --provider codex --demand 1234   # o Codex no worktree, com o perfil aidw
python aidw.py open --demand 1234 --no-orchestrate   # só abre, sem chamar o orquestrador
```

`1234` acha `us-1234`. No chat, `/aidw:orquestrar` sem argumento numa pasta de worktree acha a demanda e continua da
etapa gravada.

## Consultar e limpar

```powershell
python aidw.py worktree list            # situação de todos (pasta, branch, alterações, commits não publicados)
python aidw.py worktree inspect us-1234
python aidw.py worktree remove us-1234  # só com worktree limpo e commits publicados; a branch fica
python aidw.py worktree cleanup         # tira do registro o que sumiu do disco
python aidw.py status                   # inclui worktrees de demandas concluídas e órfãos
```

Apagar a branch é ação travada: peça ao orquestrador, que pede o seu OK.

## Worktree de PR de outra pessoa

Para revisar a PR que outra pessoa abriu (workflow `pr-review`):

```powershell
python aidw.py worktree create --repo C:\ProjetosLegados\Hope --demand us-127508 --pr 7639
```

- Busca `refs/pull/<n>/merge` no `origin`: a PR já mesclada no destino, como ficaria depois do merge. Funciona no
  Azure Repos e no GitHub. Se a ref não existe, a PR é de outro repositório, já foi concluída ou tem conflito com o
  destino.
- Cria o worktree em `<raiz>/<demanda>/<repo>`, **destacado e sem branch**, com as junctions de dependências e as
  pastas vizinhas (`worktree_link`), e grava `diff-pr<n>-<repo>.patch` na pasta da demanda. No registro, `base` é o
  commit do destino, `source` a ponta da PR e `head` o merge.
- Rodar de novo depois que o autor atualiza a PR leva o worktree à versão nova (recusa se houver alteração local) e
  grava `diff-pr<n>-<repo>-r<N>.patch` só com o que mudou, nos arquivos da PR.
- Um repositório por demanda: a mesma demanda não pode ter a PR e uma branch de trabalho no mesmo repositório.
- `worktree remove` tira as junctions antes e remove o worktree e a ref da PR; não há branch para manter.

## Estado da demanda

```powershell
python aidw.py demand list --active
python aidw.py demand show us-1234
python aidw.py demand set us-1234 --step REVIEW --status paused --mode interativo --note "esperando o QA"
```

O `demand.json` guarda a etapa, o status (`active`, `paused`, `done`), o modo, os repositórios e o histórico das
etapas. É o que permite fechar o chat e voltar depois.
