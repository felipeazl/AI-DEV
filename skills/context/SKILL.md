---
name: context
description: Administra os contextos de trabalho do AiDW (contexts/<nome>, cada um um repositório Git privado) — `list` mostra os contextos e qual está ativo; `use <nome>` valida, ativa e regenera o ambiente e o plugin aidw; `create` monta um contexto novo a partir da análise dos repositórios e de no mínimo 10 perguntas ao usuário. Use quando o usuário pedir para listar, trocar, ativar ou criar um contexto, ou chamar /context.
aidw: admin
---

# context

`aidw.py` fica em `{{root}}` (raiz do AiDW). Pedido do usuário (pode estar vazio): $ARGUMENTS

## Qual subcomando

Pela primeira palavra do pedido (sem diferenciar maiúsculas):

| Pedido | Subcomando | Procedimento (leia o arquivo inteiro e siga) |
|---|---|---|
| vazio, `list`, `listar`, "ver os contextos" | `list` | `references/list.md` |
| `use <nome>`, `usar <nome>`, "trocar para", "ativar" | `use` | `references/use.md` |
| `create`, `criar`, "montar um contexto" | `create` | `references/create.md` |

Os arquivos ficam na pasta desta skill (ao lado deste `SKILL.md`). Sem subcomando claro, faça o `list` e termine
dizendo que `use <nome>` troca o contexto ativo e `create` monta um novo.
