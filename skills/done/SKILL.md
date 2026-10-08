---
name: done
description: Fecha a tarefa: grava no contexto ativo o que a demanda descobriu e que vale para as próximas — na base de conhecimento (a nota da demanda e as notas de sistema, integração, conceito e decisão que ela tocou, ligadas sem duplicar) e, para build e ambiente, no context.toml —, valida, reinstala o AiDW e faz commit e push do repositório do contexto. Só quando o usuário chamar.
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
- **Base de conhecimento:** `status --json` não a mostra; leia `[knowledge] dir` no `context.toml` do contexto (a
  pasta é `<contexto>/<dir>`; convenções no `README.md` dela). Sem `[knowledge]`, tudo vai para o `context.toml`
  e o `reference/`, como na tabela da seção 2.
- **Fontes, da mais barata para a mais cara:**
  1. `aprendizados-<id>.md` na pasta da demanda (o orquestrador anota ali durante a demanda) e esta conversa;
  2. na pasta da demanda: as seções *Base de conhecimento* dos `exploracao-*.md`, `resumo-*.md` (o que o card
     pediu, as decisões com autor e data), `plano-*.md` (premissas verificadas, decisões), `triagem-*`, `review-*`,
     `levantamento-*.md`, `revisao-final.md` e `estado.md`;
  3. o diff do worktree (`git -C <worktree> diff <base>...HEAD --stat`, e o diff só dos trechos que importam).

## 2. O que vale guardar

Guarde só o que passar em **todos** os critérios:
- **Serve para a próxima demanda:** um fato do sistema ou do ambiente, e não um detalhe desta entrega.
- **Foi verificado:** comando que rodou, `arquivo:linha`, saída do build. Hipótese não entra.
- **É novo ou corrige o que está lá:** antes de escrever, procure onde o fato já mora (`kb search <palavras>`,
  `kb show <nota>`) e atualize aquela nota; não crie outra. O que a base dizia e se mostrou errado é corrigido na
  própria nota, com a fonte nova.
- **É fato, não regra:** a base descreve como o código **é** (inclusive o legado fora do padrão); como ele **deve** ser
  é do guia do time e das `policies/`. Um padrão legado vai para a nota como fato ("o Hope usa ADO.NET com procedure
  em X"), nunca como recomendação; convenção do time e regra de trabalho vão para `shared/` ou `policies/`.
- **É curto:** uma linha por fato, com a fonte quando não é óbvia. A seção *Systems* do `context.toml` vai no prompt
  de toda mensagem: lá só o que todo agente precisa sempre (build, teste, bloqueio de ambiente).
- **Nunca** segredo, token, senha, connection string, PIN, dado pessoal ou dado de cliente. Isso vale também para o
  conteúdo do card: nome, e-mail e CPF não entram.

Para cada fato, o lugar certo:

| Fato | Onde |
|---|---|
| Repositório, stack, build, teste ou dependência de um sistema | `context.toml`, `[systems.<chave>]` (`repos`, `stack`, `build`, `test`, `depends_on`) |
| Bloqueio de ambiente e como destravar (clone, restore, flag, ordem de build) | `notes` do sistema, com a data `(conferido em AAAA-MM-DD)` |
| Pasta vizinha que o código alcança por caminho relativo (HintPath `..\X`) | `worktree_link` do sistema |
| Como o sistema funciona, onde fica cada coisa, armadilha do código | a nota do sistema (`sistemas/<chave>.md`) ou do componente |
| Contrato entre dois lados (endpoint, SOAP, enum, evento, chave de configuração compartilhada, serviço externo) | nota de `integracoes/`, ligada aos dois sistemas |
| Regra de negócio, termo do domínio | nota de `conceitos/` |
| Como operar o ambiente (host, autenticação, banco, receita de API) | nota de `ambiente/` |
| Decisão durável da PO, do Tech Lead ou do usuário (com autor e data) | nota de `decisoes/`; se virou regra de trabalho, `policies/` ou `shared/` |
| O que a demanda foi | a nota da demanda, `demandas/<id>.md` (seção 2.1) |
| Procedimento que vai se repetir | proponha uma skill do contexto (`skills/<nome>/SKILL.md`) e pergunte antes de criar |
| Melhoria do próprio AiDW (`aidw.py`, agentes e skills genéricos) | não edite: liste como sugestão no relatório |

Sem base de conhecimento no contexto, as linhas das notas viram `notes` do sistema ou o arquivo de `reference/` do
tema.

### 2.1 A nota da demanda e os links

Toda demanda fechada ganha `demandas/<id>.md` — desenvolvimento, revisão de PR ou levantamento —, curta (até ~20
linhas), no formato do `README.md` da base: o que o card pediu (uma linha), o que mudou e onde (`[[sistema]]`,
arquivos principais), as decisões, o que se aprendeu com o link da nota que recebeu cada fato, a PR. Revisão de PR:
o que a PR fazia, os achados que importam para o sistema e o voto. Levantamento: a estimativa e as dúvidas.

- **Ligue, não copie:** a nota da demanda aponta para as notas que tocou; cada nota atualizada ganha a fonte
  (`fontes:` com o id da demanda) e `atualizado:` com a data. Um fato novo vai numa nota só; as outras citam com
  `[[link]]`.
- **Nota nova** só quando o fato não cabe numa existente: tipo e pasta certos, nome único, `resumo`, `fontes`,
  `palavras-chave` (nota técnica) e pelo menos um link de ou para outra nota.
- **Palavras-chave:** quando um fato novo traz um identificador que alguém vai procurar (classe, chave de config, rota,
  tabela, enum), acrescente-o às `palavras-chave` da nota; ao dividir uma nota grande, cada parte leva as suas.

## 3. Gravar e validar

1. Edite os arquivos do contexto. No `context.toml`, preserve os comentários e o estilo das entradas vizinhas.
2. Se o contexto mudou nada, diga isso e pule para a seção 5.
3. Com base de conhecimento: `python "{{root}}/aidw.py" kb index` (regenera o mapa) e
   `python "{{root}}/aidw.py" kb check` — corrija link quebrado, nome repetido, frontmatter e segredo; nota órfã
   que você criou ganha um link. Nos avisos das notas que você tocou: a que passou de 150 linhas, divida em notas
   ligadas (uma parte vira integração, componente ou ambiente); a que estava sem conferência há mais de 6 meses e
   esta demanda conferiu, atualize o `atualizado`. As outras, só liste no relatório.
4. Rode `python "{{root}}/aidw.py" context check <nome>`. Com erro, corrija e rode de novo. Não faça commit de contexto
   quebrado.
5. Regenere e reinstale:
   - `python "{{root}}/aidw.py" apply`;
   - `python "{{root}}/aidw.py" status --json`: com `claude.installed`, rode `install`; com `codex.installed`, rode
     `install --provider codex`.

## 4. Commit e push do contexto

- `git -C "<pasta do contexto>" status --short`, depois `git add` **só dos arquivos que você alterou** neste passo.
  Nunca adicione a pasta de estado das demandas (a `state_dir` do contexto, ex.: `<contexto>/demandas/`), nem arquivo
  que você não editou. As notas da base (inclusive `<base>/demandas/<id>.md`) entram.
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

- O que entrou no contexto, arquivo por arquivo, uma linha por fato; com base de conhecimento, a nota da demanda e
  as notas que ela tocou (o usuário vê o grafo abrindo a pasta do contexto no Obsidian).
- O que você deixou de fora e por quê: não verificado, só desta demanda ou sensível.
- O commit (hash) e o resultado do push.
- As sugestões para o AiDW, se houver.
- Que o plugin foi reinstalado e que as regras novas valem num **chat novo**.
