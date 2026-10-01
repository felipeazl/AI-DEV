# Skills

Uma **skill** é um procedimento em Markdown (`SKILL.md`) que um agente segue quando a etapa pede: como escrever um
plano, como revisar um diff, como tratar uma operação de banco. Elas deixam o comportamento **repetível**: o mesmo
passo a passo em toda demanda, sem depender de o modelo lembrar.

## Tipos

| Tipo | Como se reconhece | Quem chama | Exemplo |
|---|---|---|---|
| **De uso direto** | frontmatter `aidw: admin` | você, a qualquer momento, fora de uma demanda | `contexto-usar`, `done` |
| **Do plugin** | geradas pelo `install` | você | `orquestrar`, `sair`, `diff` |
| **De fluxo** | as demais | o orquestrador ou um agente, quando a etapa pede | `to-spec`, `code-review` |

Uma skill de fluxo **só vale dentro de uma demanda** conduzida pelo orquestrador. `disable-model-invocation: true`
impede que o modelo chame a skill sozinho (o `done` só roda quando você chama).

## As skills do núcleo

### Você chama

| Skill | O que faz |
|---|---|
| `orquestrar [demanda] [modo]` | Assume o chat como orquestrador: detecta o projeto, abre ou retoma a demanda, pergunta o modo, cria o worktree e conduz o fluxo |
| `sair` | Grava a etapa e o próximo passo (`paused`) e devolve o chat ao normal |
| `diff [repo\|sair]` | Só no Claude. Leva a sessão para o worktree de um repositório da demanda; o painel de diff segue. Sem argumento, vai para o próximo em círculo; `sair` volta para a pasta da demanda ([demandas-e-worktrees.md](demandas-e-worktrees.md#ver-o-diff-de-cada-repositório)) |
| `done` | Fecha a tarefa: grava no contexto só o que foi verificado e vale para as próximas demandas (build, bloqueios e como destravar, dependências, armadilhas, convenções), valida, reinstala, faz commit e push do repositório do contexto, marca a demanda como `done` e sai do modo orquestrador. Nunca grava segredo nem dado pessoal |
| `contexto-listar` | Mostra os contextos, qual está ativo, o repositório de cada um (remoto só pelo host), os sistemas e se o plugin está instalado |
| `contexto-usar <nome>` | Valida e ativa um contexto, regenera o ambiente e o plugin; avisa se há demanda ativa |
| `contexto-criar` | Cria um contexto novo a partir da análise dos repositórios e de no mínimo 10 perguntas ([contextos.md](contextos.md#criar-um-contexto)) |

### O fluxo chama

| Skill | Quem usa | O que faz |
|---|---|---|
| `to-spec` | planejador (pré-carregada) | Confere trabalho existente, parte dos relatórios de exploração, inspeciona as dependências, descreve o comportamento atual pelo código, roda os checklists e grava o plano; depois corta os tickets autocontidos |
| `verificar-premissa` | orquestrador, planejador, revisor, especialistas | Antes de aceitar "não dá para corrigir aqui", "cobre todos os casos", "é a convenção do repositório", "esse valor nunca acontece", "o outro sistema já faz X": evidência de primeira mão ou a premissa cai |
| `preparar-worktree` | orquestrador, codificador | Cria, confere e remove o worktree com `aidw.py worktree`: base certa (inclusive branch não mergeada de que a demanda depende), branch, junctions, registro |
| `code-review` | revisor (pré-carregada) | Revisão contra spec e ticket, achados com IDs estáveis e severidade |
| `database-safe` | api | Classifica cada operação de banco: leitura só pelo validador; escrita sempre proposta com a query exata, o `SELECT` de conferência e como reverter |
| `bug-hunt` | bugs (pré-carregada) | Caça de defeitos com cenário de falha concreto, ou causa-raiz de um bug reportado |
| `security-audit` | seguranca (pré-carregada) | Auditoria de vulnerabilidades com caminho de ataque |

## `skills` × `preload`

Cada agente tem duas listas (no `aidw.config.toml` e no `context.toml`):

- **`skills`:** as que ele **pode** carregar. Aparecem como uma lista curta de nomes e caminhos; o conteúdo só entra
  quando ele usa a skill.
- **`preload`:** um subconjunto injetado **inteiro** no início de cada execução, para o que o agente usa sempre (o
  revisor sempre revisa, então `code-review` vem carregada). Toda skill de `preload` precisa estar em `skills`.

Pré-carregar o que não é usado sempre só aumenta o custo de cada delegação.

## Skills do contexto

Um contexto pode trazer skills próprias em `contexts/<nome>/skills/<skill>/SKILL.md`: ler um card do board do time
em passos baratos, anexar um arquivo, montar o plano de testes do QA, redigir uma US no formato da empresa. Elas
entram no mesmo plugin e são ligadas ao agente pelo `skills = [...]` em `[agents.<papel>]` do `context.toml`.

## Escrever uma skill

```markdown
---
name: minha-skill
description: O que faz e QUANDO usar, numa frase. É o que o modelo lê para decidir se a skill se aplica.
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
- **Pare na primeira resposta suficiente:** procedimentos em camadas (leia o campo, só depois as relações, só depois
  os anexos) economizam tokens.
- Para uso direto, fora de uma demanda, acrescente `aidw: admin` no frontmatter.

Para ativar:
1. Grave em `skills/<nome>/SKILL.md` (núcleo) ou `contexts/<ctx>/skills/<nome>/SKILL.md` (contexto).
2. Acrescente o nome em `skills = [...]` do agente (e em `preload`, se ele usa sempre).
3. `python aidw.py apply` e `python aidw.py install`, e um chat novo.
