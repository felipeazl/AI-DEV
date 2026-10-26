---
when: escrever a triagem de uma revisão de PR (workflow pr-review), em toda rodada, e registrar o que foi publicado e votado
---

# Triagem de uma revisão de PR

A triagem de cada rodada (`triagem-<id>-r<N>.md`) é o que você leva à revisão final **e o que o painel do AiDW mostra**
na aba Comentários: você decide sobre os comentários daqui, não sobre os achados soltos. Mantenha as seções, as colunas
e as palavras abaixo como estão.

- **Comentário** (`C1`, `C2`…): o que vai, ou iria, para a PR. Junta os achados que dizem a mesma coisa (`R1-01`,
  `B1-02`, `S1-01`…), que ficam na coluna *Origem*. O id não muda entre rodadas.
- **Toda rodada traz a tabela inteira**, os comentários das rodadas anteriores inclusive, com a situação de agora. O
  painel lê só a triagem da última rodada.

## Modelo

```markdown
# Triagem — <id>, rodada <N> (PRs <n> e <m>)

<Fontes, premissas conferidas e o que mudou desde a rodada anterior, como numa triagem de código.>

## Comentários

| C | PR | Sev. | Arquivo:linha | Origem | Recomendação | Situação |
|---|---|---|---|---|---|---|
| C1 | 8197 | IMPORTANTE | `src/Tela.cs:5183` | R1-01, B1-01 | publicar | publicado (thread 23720), resolvido na r2 |
| C2 | 8197 | DUVIDA | geral | R1-D1 | publicar como pergunta | a decidir |
| C3 | 8208 | SUGESTAO | `src/Repo.cs:61` | R1-04, S1-02 | não publicar | não publicado (r1) |

### C1 — <o que o comentário aponta, numa linha>
> <o texto que vai para a PR: português, até ~5 linhas, sem saudação e sem os ids internos>

### C2 — <…>
> <…>

## Fora das PRs

- **S1-01 (Tech Lead):** <o que é e por que não vira comentário: padrão antigo, outro sistema, decisão de outra pessoa>

## Publicado

- C1: PR 8197, thread 23720 (<quem aprovou, data>).
- Aprovar PR 8197: sim, aprovada (<quem aprovou, data>). PR 8208: manual.
```

## As colunas

- **Sev.:** `CRITICO`, `IMPORTANTE`, `SUGESTAO` ou `DUVIDA` (pergunta ao time); `PENDENCIA` para o comentário geral de
  pendências para a QA.
- **Arquivo:linha:** o caminho no repositório, entre crases; `geral` para comentário sem arquivo.
- **Recomendação:** `publicar`, `publicar como pergunta`, `não publicar` ou `opcional`, e o porquê depois de ` — `,
  quando ajudar.
- **Situação:** `a decidir`; `não publicado (rN)`, quando a decisão foi não publicar; `publicado (thread <id>)`; e, em
  rodada seguinte, `resolvido na rN` ou `continua aberto na rN` depois do publicado. Comentário novo de uma rodada
  seguinte entra com o próximo id livre.

Não há voto nem escala de voto na triagem. A única pergunta além dos comentários é, por PR, **"Aprovar a PR?"**:
`manual` (o padrão: o AiDW não aprova e o usuário decide na ferramenta), `sim` (o AiDW aprova) ou `não` (o AiDW não
aprova). O painel pergunta; a triagem não sugere.

## Depois da revisão final

Com o OK, publique exatamente o que foi aprovado e aprove só as PRs com `sim` (a referência do contexto diz como em
cada ferramenta). Depois atualize a triagem: a *Situação* de cada comentário e a seção *Publicado*, com o id de cada
thread e a aprovação de cada PR. O painel conta como publicado o que esta tabela disser.
