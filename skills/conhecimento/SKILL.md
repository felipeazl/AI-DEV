---
name: conhecimento
description: Consulta a base de conhecimento do contexto ativo — o que o AiDW já aprendeu sobre um sistema, contrato, conceito, decisão ou demanda — e responde com as notas e os links entre elas; também corrige ou completa uma nota quando o usuário pedir. Use quando o usuário perguntar o que se sabe sobre um projeto, sistema ou tema, ou chamar /conhecimento.
aidw: admin
---

# conhecimento

`aidw.py` fica em `{{root}}` (raiz do AiDW). Rode os comandos exatamente na forma `python "{{root}}/aidw.py" ...`, com as
aspas: é a que as regras de permissão liberam. O pedido do usuário está na mensagem que chamou esta skill.

## Responder

1. **Achar a nota:** `python "{{root}}/aidw.py" kb show <tema>` aceita a chave do sistema (`hope`), o nome da nota, um
   alias ou o título. Sem nota com esse nome, ele sugere parecidas; para um assunto, use
   `python "{{root}}/aidw.py" kb search <palavras>` (sem acento nem caixa).
2. **Seguir os links** só até onde a pergunta pede: o `kb show` lista os links da nota e quem a cita (as demandas que
   mexeram ali, os contratos que a usam). Abra as que respondem, um nível por vez.
3. **Responder curto:** o que a base diz, com o caminho de cada nota usada (link clicável), e o que ela **não**
   diz. Diga a data `atualizado` quando ela pesar (nota antiga sobre código que muda muito). Não leia código para
   completar a resposta, a não ser que o usuário peça; se ler, diga o que confirmou e onde (`arquivo:linha`).
4. Se a pergunta vier sem tema ("o que temos?"), mostre o `index.md` da base resumido: quantas notas por tipo e as
   mais citadas.

## Corrigir ou completar (só quando o usuário pedir)

- Siga o `README.md` da base: o fato vai na nota onde ele mora (não crie outra), com a fonte e `atualizado` com a
  data de hoje; uma nota nova só quando nenhuma cabe, com tipo, `resumo`, `fontes` e pelo menos um link.
- Depois: `python "{{root}}/aidw.py" kb index` e `python "{{root}}/aidw.py" kb check`; corrija o que ele apontar.
- Não faça commit: o `/aidw:done` (ou o usuário) leva as mudanças para o repositório do contexto. Diga quais
  arquivos mudaram.

## Sem base

Se o `kb` responder que não há base de conhecimento no contexto ativo, diga isso e que ela se liga com
`[knowledge] dir = "<pasta>"` no `context.toml` (convenções num `README.md` dessa pasta).
