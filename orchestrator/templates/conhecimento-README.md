# Base de conhecimento — {description}

O que o AiDW aprendeu sobre os sistemas deste contexto, em notas ligadas entre si. Abra a **pasta do contexto** como
**vault no Obsidian** para navegar pelo grafo (as notas aparecem junto das policies e dos guias, que elas podem citar
por `[[nome]]`); no chat e nos agentes, use `python aidw.py kb show|search`.

Mapa de tudo: [[index]] (gerado por `python aidw.py kb index`; não edite à mão).

## A regra que vale mais

**Cada fato mora numa nota só.** Quem precisa dele aponta com `[[nome-da-nota]]`; não copia. Se duas notas dizem
coisas diferentes, uma está errada: confira no código e corrija a errada.

## A base descreve, a regra decide

Uma nota diz **como o código é hoje**, inclusive o legado fora do padrão — é fato, não regra. Que padrão o código
novo segue quem decide é o guia de código do time e as `policies/` (incluindo como o guia se compara ao padrão já
estabelecido em cada repositório), nunca uma nota sozinha. Convenção do time e regra de trabalho não entram na base:
vão para `shared/` ou `policies/`.

## Tipos de nota

| Pasta | `tipo` | Uma nota por |
|---|---|---|
| `sistemas/` | `sistema` | sistema do `context.toml` (o nome do arquivo é a chave: `[systems.pagamentos]` → `sistemas/pagamentos.md`) |
| `componentes/` | `componente` | biblioteca, projeto ou pacote compartilhado entre sistemas |
| `integracoes/` | `integracao` | contrato entre dois lados: endpoint, mensagem, enum, evento, configuração compartilhada, serviço externo |
| `conceitos/` | `conceito` | termo do domínio (o que é, regras de negócio, o termo certo) |
| `ambiente/` | `ambiente` | como operar: hosts por ambiente, autenticação, banco, receitas, ferramentas |
| `decisoes/` | `decisao` | decisão durável de negócio ou de arquitetura, com autor e data |
| `demandas/` | `demanda` | demanda fechada (desenvolvimento, revisão de PR, levantamento) |

## Formato

```markdown
---
tipo: sistema
resumo: Uma linha que diz o que é — aparece no índice e nas listas do `kb show`.
sistemas: [pagamentos]
palavras-chave: [URL_API_PAGAMENTO, PagamentoController, dbo.Pedido]
fontes: ["C:/Projetos/Pagamentos/ARCHITECTURE.md", "us-1234"]
atualizado: AAAA-MM-DD
---

# Pagamentos

Texto curto, com [[links]] para o que já tem nota.
```

- **Nome do arquivo:** minúsculas, hífen, sem acento, único no vault inteiro (inclusive fora da base).
- **`resumo`:** obrigatório. **`fontes`:** obrigatório, menos em `conceito` e `demanda` (`caminho:linha`, documento,
  demanda ou pessoa com data). **`atualizado`:** a data da última conferência. **`sistemas`:** chaves do
  `context.toml`. **`evitar`** (conceito): termos que não se usam — viram o glossário. **`aliases`:** outros nomes.
  **`palavras-chave`** (sistema, componente, integração, ambiente): identificadores, chaves de config, rotas, tabelas e
  sinônimos que alguém digitaria para achar a nota (5 a 15, exatos como no código); pesam no `kb search`.

## O que entra e o que não entra

- **Entra:** fato verificado que serve para a próxima demanda — como funciona, onde fica, contratos, armadilhas,
  decisões. Uma linha por fato, com a fonte.
- **Não entra:** hipótese, detalhe de uma entrega só, segredo, credencial, dado pessoal ou de cliente.
- **Build, teste e bloqueio de ambiente** ficam no `context.toml`; a nota do sistema aponta para lá.
- **Documentação do repositório:** cite o caminho e resuma; não copie.
- **Listas que o grafo já dá** (demandas que tocaram um sistema): não mantenha à mão — os backlinks mostram.

## Validar

`python aidw.py kb check` (também roda no `context check`). Ele também avisa nota com mais de 150 linhas (divida em
notas ligadas) e nota sem conferência há mais de 6 meses (reconfira no código).
