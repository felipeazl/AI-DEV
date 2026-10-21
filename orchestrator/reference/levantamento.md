---
when: fazer o levantamento de uma demanda (workflow levantamento) — os pontos do card, a tarefa do explorador, a régua de estimativa, como escrever as dúvidas e o formato do levantamento-<id>.md
---

# Levantamento de demanda

Workflow `levantamento` (seção *Levantamento* do orquestrador): entender o card, validar cada ponto dele no código,
mapear o fluxo de ponta a ponta e estimar. **Só leitura:** sem worktree, plano, tickets, build ou código; nada de
escrita em ambiente nem no board sem o OK do usuário.

## 1. Os pontos do card

Depois do `resumo-<id>.md`, numere em `pontos-<id>.md` (na pasta da demanda) tudo o que o card pede ou afirma,
um ponto por linha, com a origem:

- cada comportamento pedido na descrição (uma frase que pede duas coisas vira dois pontos);
- cada critério de aceite;
- cada decisão dos comentários do card e das US/Dívidas ligadas (autor e data);
- cada afirmação sobre o sistema que o card toma como certa ("a tela X já mostra Y", "a API devolve Z");
- o que o card cita sem detalhar (tela, relatório, integração, perfil de usuário, ambiente).

Formato: `P01 — <o ponto, em uma frase> — origem: descrição | critério 2 | comentário de <autor> em <data>`.

Pedido sem card (só texto): os pontos saem do texto do usuário; tudo o que ele não disse e o código não responde
vira dúvida.

## 2. A tarefa do explorador

`tarefa-explorador-levantamento.md`, para o {{agent:explorer}} na célula do nível `critica` (`Nível: critica —
levantamento: a exploração do fluxo inteiro é a entrega`). Leva:

- os caminhos de `resumo-<id>.md` e `pontos-<id>.md` (não cole o conteúdo);
- os sistemas prováveis e os repositórios de *Systems* (e os que eles consomem, de *Depends on*); se não souber
  quais, as raízes de projeto do Runtime;
- **modo levantamento** e o relatório `exploracao-levantamento.md` na pasta da demanda;
- perguntas extras, numeradas, só se o card deixa um ponto técnico específico em aberto;
- "No MCP tools needed", salvo um gatilho claro da tabela *MCP tools*.

O modo levantamento do explorador já cobre: cada ponto confirmado, divergente ou não encontrado no código, o
fluxo de ponta a ponta com `arquivo:linha`, os sinais de tamanho e as dúvidas que o código não responde.

## 3. A régua

Use a régua do contexto ativo quando a lista *Reference* tiver *regua-estimativa*; ela vale sobre a padrão
abaixo.

**Régua padrão** — story points em Fibonacci; esforço em horas.

| SP | Quando | Horas (dev + teste + revisão) |
|---|---|---|
| 1 | Ajuste de texto ou configuração, um arquivo, sem regra nova | até 4 h |
| 2 | Mudança pontual com regra simples, 1–2 arquivos, um sistema | 4–8 h |
| 3 | Regra de negócio nova num sistema, alguns arquivos, teste direto | 8–16 h |
| 5 | Vários pontos de contato num sistema, ou um contrato simples com outro | 16–24 h |
| 8 | Dois ou mais sistemas, contrato entre eles, banco, ou legado frágil | 24–40 h |
| 13 | Vários sistemas e contratos, migração de dados, muita incerteza | 40–64 h |
| > 13 | Grande demais para um card | proponha a quebra |

**Complexidade** (independe do tamanho: um card pequeno pode ser de alta complexidade):
- **Baixa** — lógica direta, um sistema, comportamento atual claro.
- **Média** — regra de negócio com casos, ou um contrato com outro sistema já conhecido.
- **Alta** — vários sistemas, concorrência, UI thread, polling, banco, segurança, legado sem teste.
- **Muito alta** — o fluxo atual não está claro mesmo depois da exploração, ou depende de decisão ainda não tomada.

## 4. Estimar

Aplique a régua aos **sinais de tamanho** do relatório, nunca à impressão do card:

1. **Complexidade** com o porquê em uma linha (os sinais que pesaram).
2. **Esforço em horas por frente:** análise/ajuste do plano, desenvolvimento por sistema, testes (automáticos e
   manuais, com o ambiente que exigem), revisão e correções, e o que o contexto acrescenta (script SQL, pacote para
   QA, deploy coordenado). Dê uma **faixa** (mínimo–máximo), não um número só.
3. **Story points:** o valor da régua que corresponde à faixa total; entre dois, o maior quando a confiança é baixa.
4. **Confiança** (alta, média ou baixa) e **o que a mudaria**: normalmente as dúvidas abertas. Diga quais dúvidas,
   respondidas de um jeito ou de outro, sobem ou descem a estimativa.
5. **Acima de 13 SP:** proponha a quebra em cards menores, cada um com a sua estimativa e o que entrega sozinho.
6. **Riscos:** o que pode estourar a estimativa (legado sem teste, ambiente de QA, outro time, massa de dados).

## 5. As dúvidas

Para quem vai responder (PO, Tech Lead, outro time), não para quem leu o código:

- **Uma pergunta por item**, em uma ou duas frases, terminando em `?`.
- **Linguagem do negócio:** o que a pessoa vê ou decide (tela, mensagem, regra, status), não nome de classe,
  método, enum ou tabela. O detalhe técnico, se ajudar, vai no contexto, curto.
- **Com opções** quando houver caminhos claros ("A ou B?"), e a sua recomendação quando tiver uma.
- **Contexto:** logo depois da pergunta, o que levou a ela e o que muda na entrega.
- **Para:** quem responde, em cada dúvida (PO, Tech Lead, outro time ou QA).
- **Muda a estimativa:** só nas que mudam o tamanho, com quanto (`+3 SP se migrar`, `+8 h`).
- **Agrupadas por tema** (`**Escopo e produto**`, `**Contrato com <sistema>**`, `**Experiência**`, `**Regras**`…),
  numeradas `D1`, `D2`… na ordem do documento.
- Ordem dentro do tema: as que bloqueiam o início primeiro; depois as que mudam a estimativa; por último as de detalhe.
- Não pergunte o que o código já respondeu; isso vai como fato no levantamento.
- **Respondida:** sai do tema e vai para o grupo `**Respondidas em <dd/mm>**`, no fim, em uma linha com a resposta e
  quem decidiu (`- **D3.** Só os 5 campos do card têm tratamento (PO e TL, 20/10). *Para:* PO`); o painel mostra
  esse grupo recolhido e conta só as abertas.

Exemplo de tom:

> ❌ "Como tratar o valor 0 do enum de status no fluxo de reemissão?"
> ✅ "- **D4. Quando o pedido ainda não tem status, o sistema deve deixar reemitir ou bloquear?** Bloquear exige
> mensagem nova na tela. *Para:* PO *Muda a estimativa:* +4 h se bloquear"

## 6. `levantamento-<id>.md`

Na pasta da demanda:

```markdown
# Levantamento — <tipo> <id>: <título>

**Estimativa:** <SP> SP · <min>–<max> h · complexidade <nível> · confiança <alta|média|baixa>

## O que o card pede

**Card:** <3 a 6 linhas, em linguagem do negócio; diga se o card não tem critérios de aceite>

## Card × código
| Hoje no código | Para a demanda | Situação |
|---|---|---|
| <o que existe, com `arquivo:linha`> | <o que isso significa para a demanda> | precisa mudar / é a dor / não muda / nada a reaproveitar |

## Fluxo atual (ponta a ponta)
<os passos, do início ao fim, com sistema e `arquivo:linha`>

## Onde a mudança toca
<sistemas, repositórios e pontos de contato; contratos entre sistemas; banco; telas>

## Estimativa
| Bloco | Dev (h) |
|---|---|
| <bloco de trabalho> | <min>–<max> |
| **Total dev** | **<min>–<max> h** |
| QA integrado | <min>–<max> h |

- **Story points:** <SP> — <por quê, pela régua>
- **Complexidade:** <nível> — <os sinais que pesaram>
- **Confiança:** <nível> — <o que a mudaria>
- **Nível AiDW:** <trivial|simples|padrao|complexa|critica> · **Passadas extras:** <segurança, bugs, ou nenhuma>
- **Riscos:** <...>

<só acima de 13 SP: a quebra>
| # | Item | SP |
|---|---|---|
| 1 | <item> | <SP> |

Total **≈ <soma> SP**.

## Dúvidas

**<Tema>**
- **D1. <pergunta>?** <contexto> *Para:* <PO | Tech Lead | outro time | QA> *Muda a estimativa:* <só quando muda>

## Fontes
resumo-<id>.md · pontos-<id>.md · exploracao-levantamento.md
```

O painel do AiDW (abas *Card × código*, *Estimativa* e *Dúvidas*) lê exatamente essas tabelas e marcações: mantenha os
cabeçalhos, as colunas e os rótulos `*Para:*` e `*Muda a estimativa:*` como estão.

## 7. Fechar

1. No chat: a linha da **Estimativa**, a tabela da estimativa, as dúvidas na íntegra e o caminho do arquivo.
2. **Ofereça** publicar no card um comentário com a estimativa e as dúvidas, curto e no padrão do contexto ativo.
   Publicar é ação travada: só com o OK explícito do usuário, com o texto que ele aprovou. Nunca mude o estado nem
   os campos do card (story points inclusive) sem ele pedir.
3. `demand set <id> --step DONE --status done --note "levantamento: <SP> SP, <min>–<max> h"`.

Se a demanda for implementada depois, o `/orquestrar` reaproveita `resumo-<id>.md`, `pontos-<id>.md` e
`exploracao-levantamento.md` (seção *Levantamento*).
