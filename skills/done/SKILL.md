---
name: done
description: Fecha a tarefa: grava no contexto ativo o que a demanda descobriu e que vale para as próximas (build, bloqueios de ambiente e como destravar, dependências, armadilhas do código, convenções), valida, reinstala o AiDW e faz commit e push do repositório do contexto. Só quando o usuário chamar.
aidw: admin
disable-model-invocation: true
---

# done

`aidw.py` fica em `{{root}}` (raiz do AiDW). Rode os comandos exatamente na forma `python "{{root}}/aidw.py" ...`, com as
aspas: é a que as regras de permissão liberam.

O usuário chama esta skill ao terminar uma tarefa. **Chamar é a autorização** para fazer commit e push do repositório do
**contexto** (e só dele) na branch atual, mesmo que seja a `main`: é o repositório privado de conhecimento do usuário, e
não código de produto, por decisão dele. Nada de commit, push ou merge nos repositórios do produto. O pedido do usuário,
se houver, está na mensagem que chamou esta skill.

## 1. O que foi a tarefa

- **Contexto ativo:** `python "{{root}}/aidw.py" status --json` → `context.name`. A pasta é `{{root}}/contexts/<nome>`.
  Sem contexto ativo: diga que não há onde gravar e pare.
- **Demanda:** a desta sessão, ou a do pedido. Se não estiver claro, use `project detect --json` (o campo `demand`) e
  `demand list --active --json`. Uma tarefa sem demanda (manutenção, investigação) também vale: use a conversa.
- **Fontes, da mais barata para a mais cara:**
  1. esta conversa;
  2. na pasta da demanda: `plano-*.md` (premissas verificadas, decisões), `triagem-*`, `review-*`, `revisao-final.md` e
     `estado.md`;
  3. o diff do worktree (`git -C <worktree> diff <base>...HEAD --stat`, e o diff só dos trechos que importam).

## 2. O que vale guardar

Guarde só o que passar em **todos** os critérios:
- **Serve para a próxima demanda:** um fato do sistema ou do ambiente, e não um detalhe desta entrega.
- **Foi verificado:** comando que rodou, `arquivo:linha`, saída do build. Hipótese não entra.
- **É novo ou corrige o que está lá:** leia antes o que o contexto já diz, atualize a entrada existente e não duplique.
  O que o contexto dizia e se mostrou errado sai ou é corrigido.
- **É curto:** a seção *Systems* vai no prompt de toda mensagem. Uma linha por fato; detalhe longo vai para `reference/`.
- **Nunca** segredo, token, senha, connection string, PIN, dado pessoal ou dado de cliente. Isso vale também para o
  conteúdo do card: nome, e-mail e CPF não entram.

Para cada fato, o lugar certo:

| Fato | Onde |
|---|---|
| Repositório, stack, build, teste ou dependência de um sistema | `context.toml`, `[systems.<chave>]` (`repos`, `stack`, `build`, `test`, `depends_on`) |
| Bloqueio de ambiente e como destravar (clone, restore, flag, ordem de build) | `notes` do sistema, com a data `(conferido em AAAA-MM-DD)` |
| Pasta vizinha que o código alcança por caminho relativo (HintPath `..\X`) | `worktree_link` do sistema |
| Armadilha ou padrão do código de um sistema | `notes` do sistema (uma linha) ou o arquivo de `reference/` do tema |
| Convenção do time ou decisão durável da PO/Tech Lead (com autor e data) | `shared/` ou `policies/` do contexto, no arquivo do tema |
| Procedimento que vai se repetir | proponha uma skill do contexto (`skills/<nome>/SKILL.md`) e pergunte antes de criar |
| Melhoria do próprio AiDW (`aidw.py`, agentes e skills genéricos) | não edite: liste como sugestão no relatório |

## 3. Gravar e validar

1. Edite os arquivos do contexto. No `context.toml`, preserve os comentários e o estilo das entradas vizinhas.
2. Se o contexto mudou nada, diga isso e pule para o passo 5.
3. Rode `python "{{root}}/aidw.py" context check <nome>`. Com erro, corrija e rode de novo. Não faça commit de contexto
   quebrado.
4. Regenere e reinstale:
   - `python "{{root}}/aidw.py" apply`;
   - `python "{{root}}/aidw.py" status --json`: com `claude.installed`, rode `install`; com `codex.installed`, rode
     `install --provider codex`.

## 4. Commit e push do contexto

- `git -C "<pasta do contexto>" status --short`, depois `git add` **só dos arquivos que você alterou** neste passo.
  Nunca adicione a pasta de estado das demandas (`demandas/` ou a `state_dir` do contexto), nem arquivo que você não
  editou.
- Commit com uma mensagem curta: o que foi aprendido e em qual demanda. Termine com a linha de coautoria da sessão.
- `git -C "<pasta do contexto>" push` na branch atual. Se falhar (sem remoto, sem permissão, branch protegida que exige
  PR, branch atrás do remoto), mostre a mensagem e pare. Não force, não faça rebase, não crie outra branch para
  contornar: o usuário decide.

## 5. Fechar a demanda

- Com demanda: `python "{{root}}/aidw.py" demand set <id> --status done --note "<uma linha do que foi entregue>"`.
- Mostre a situação do worktree (`worktree inspect <id>`). Se estiver limpo e publicado, sugira
  `worktree remove <id>`. Não remova sem o usuário pedir: a branch ou o PR podem ainda estar em revisão.
- Esta skill também encerra o modo orquestrador desta sessão, como o `sair`.

## 6. Relatório

- O que entrou no contexto, arquivo por arquivo, uma linha por fato.
- O que você deixou de fora e por quê: não verificado, só desta demanda ou sensível.
- O commit (hash) e o resultado do push.
- As sugestões para o AiDW, se houver.
- Que o plugin foi reinstalado e que as regras novas valem num **chat novo**.
