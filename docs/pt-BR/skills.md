# Skills

Uma **skill** é um procedimento em Markdown (`SKILL.md`) que um agente segue quando a etapa pede: como escrever um
plano, como revisar um diff, como tratar uma operação de banco. Elas deixam o comportamento **repetível**: o mesmo passo
a passo em toda demanda, sem depender de o modelo lembrar.

## Tipos

| Tipo | Como se reconhece | Quem chama | Exemplos |
|---|---|---|---|
| **Administração (uso direto)** | frontmatter `aidw: admin` | você, a qualquer momento, também fora de uma demanda | `context`, `done`, `knowledge` |
| **Gerada pelo plugin** | escrita pelo `install` | você | `go`, `survey`, `exit`, `diff` |
| **De fluxo** | as demais (`user-invocable: false` no plugin: fora do menu `/`) | o orquestrador ou um agente, quando a etapa pede | `to-spec`, `code-review` |

Uma skill de fluxo **só vale dentro de uma demanda** conduzida pelo orquestrador; a descrição dela começa com
`[AiDW] Only inside a demand run by the AiDW orchestrator.` para o Claude não usá-la em outro lugar.
`disable-model-invocation: true` impede que o modelo chame a skill sozinho (`go`, `survey`, `exit` e `done` só rodam
quando você chama).

## As skills do núcleo

### Você chama

| Skill | O que faz |
|---|---|
| `go [demanda]` | Assume o chat como orquestrador: detecta o projeto, abre ou retoma a demanda, cria o worktree e conduz o fluxo. `pr <n>` revisa a PR de outra pessoa |
| `survey <card ou texto>` | Levantamento antes de implementar, só leitura ([workflow.md](workflow.md#levantamento-survey)) |
| `exit` | Grava a etapa e o próximo passo (`paused`) e devolve o chat ao normal |
| `diff [repo\|exit]` | Só no Claude. Leva a sessão para o worktree de um repositório da demanda; o painel de diff segue ([demands-and-worktrees.md](demands-and-worktrees.md#ver-o-diff-de-cada-repositório)) |
| `done` | Fecha a tarefa: a partir do `kb collect`, grava no contexto só o que foi verificado e vale para as próximas demandas — a nota da demanda e as notas da base que ela tocou, ligadas sem duplicar; build e ambiente no `context.toml` —, valida, reinstala, faz commit e push do repositório do contexto, marca a demanda como `done` e sai do modo orquestrador. Nunca grava segredo nem dado pessoal |
| `knowledge [tema]` | O que a base de conhecimento do contexto sabe sobre um sistema, contrato, conceito ou demanda (`kb show` + `kb search`), seguindo os links só até onde a pergunta pede; corrige ou completa uma nota quando você pede ([contexts.md](contexts.md#base-de-conhecimento)) |
| `context` (`list`, `use <nome>`, `create`) | Lista os contextos (também sem argumento), ativa um, ou cria um novo a partir da análise dos repositórios e de no mínimo 10 perguntas ([contexts.md](contexts.md#criar-um-contexto)) |

### O fluxo chama

| Skill | Quem usa | O que faz |
|---|---|---|
| `to-spec` | planner (pré-carregada) | Confere trabalho existente, parte dos relatórios de exploração, inspeciona as dependências, descreve o comportamento atual pelo código e grava o plano spec-driven com as entregas `E1…`, autossuficiente para o coder |
| `verify-premise` | orchestrator, planner, reviewer | Antes de aceitar "não dá para corrigir aqui", "cobre todos os casos", "é a convenção do repositório", "esse valor nunca acontece": evidência de primeira mão, ou a premissa cai |
| `prepare-worktree` | orchestrator, coder | Cria, confere e remove o worktree da demanda com `aidw.py worktree`: base certa, branch, junctions, registro; também o worktree só leitura da PR de outra pessoa |
| `code-review` | reviewer (pré-carregada) | Revisão contra o plano numa passada — qualidade, bugs com cenário de falha, segurança com caminho de ataque —, achados com IDs estáveis, severidade, categoria e a recomendação de manter ou descartar |
| `database-safe` | explorer, qa | Classifica cada operação de banco: leitura só pelo validador; escrita sempre proposta com a query exata, o `SELECT` de conferência e como reverter |

Os nomes antigos (`verificar-premissa`, `preparar-worktree`) numa config ou num contexto continuam virando os novos.

## `skills` × `preload`

Cada agente tem duas listas (no `aidw.config.toml` e no `context.toml`):

- **`skills`:** as que ele **pode** carregar. Aparecem como uma lista curta de nomes e caminhos; o conteúdo só entra
  quando ele usa a skill.
- **`preload`:** um subconjunto injetado **inteiro** no início de cada execução, para o que o agente usa sempre (o
  reviewer sempre revisa, então `code-review` vem carregada). Toda skill de `preload` precisa estar em `skills`.

Pré-carregar o que não é usado sempre só aumenta o custo de cada delegação.

## Skills do contexto

Um contexto pode trazer skills próprias em `contexts/<nome>/skills/<skill>/SKILL.md`: ler um card do board do time em
passos baratos, anexar um arquivo, montar o plano de testes do QA, redigir uma história no formato da empresa. Elas
entram no mesmo plugin e são ligadas a um agente pelo `skills = [...]` em `[agents.<papel>]` do `context.toml`. Uma skill
do contexto com o mesmo nome de uma do núcleo a substitui (com aviso).

## Escrever uma skill

```markdown
---
name: minha-skill
description: O que faz e QUANDO usar, numa frase. É o que o modelo lê para decidir.
---

# minha-skill

1. Passo concreto, com o comando ou a ferramenta exata.
2. Onde gravar o resultado.
3. Quando parar e devolver uma pergunta.

## Regras

- O que nunca fazer.
```

Boas práticas:
- **A `description` decide tudo:** diga o que a skill faz e o gatilho de uso.
- **Passos curtos e verificáveis**, com comandos exatos. Nada de "analise com cuidado".
- **Pare na primeira resposta suficiente:** procedimentos em camadas (leia o campo, só depois as relações, só depois os
  anexos) economizam tokens.
- Para uso direto, fora de uma demanda, acrescente `aidw: admin` ao frontmatter.

Para ativar:
1. Grave em `skills/<nome>/SKILL.md` (núcleo) ou `contexts/<ctx>/skills/<nome>/SKILL.md` (contexto).
2. Acrescente o nome em `skills = [...]` do agente (e em `preload`, se ele usa sempre).
3. `python aidw.py install` (e `apply` para o modo projeto), e um chat novo.
