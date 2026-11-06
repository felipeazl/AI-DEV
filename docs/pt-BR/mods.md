# Mods (só Claude Code)

Mods são plugins de *function hooks* do Claude Code: código que roda dentro da sessão, desenha na tela (faixa acima do
prompt, painéis, status) e reage a eventos (uma ferramenta chamada, uma mensagem enviada, um subagente que terminou). O
AiDW traz os dele no plugin **`aidw-mods`**, que o `install` instala junto com o plugin `aidw`.

**Só existem no Claude Code.** O Codex não tem mods ([claude-and-codex.md](claude-and-codex.md)).

Os mods falam o `[ui] language` do `aidw.config.toml` (uma tag `pt*` mostra em português, o resto em inglês;
[configuration.md](configuration.md#idioma)).

## Quando ficam ligados

Os mods do AiDW ficam ligados **só no modo orquestrador**:

- **Ligar:** `/aidw:go` ou `/aidw:survey` registram a sessão em `state/sessions.json`, e o `aidw-mods` confere esse
  registro a cada mensagem. Quem grava é a skill `go`, com `aidw.py session bind` (lê `CLAUDE_CODE_SESSION_ID`), e o
  hook do guard, onde o cliente manda o comando de barra para ele (o app desktop manda, o terminal não).
- **Qual demanda:** o registro guarda o contexto, o id e a pasta da demanda (`session bind --demand <id>`, e todo
  `demand set` numa sessão registrada). O mod lê a pasta dali, sem deduzir a demanda do texto, então qualquer id
  funciona. Sem demanda no registro, vale a pasta do chat quando ele abriu na demanda ou num worktree dela.
- **Desligar:** `/aidw:exit` ou `/aidw:done` tiram a sessão do registro, e os painéis fecham.

Fora do modo orquestrador eles não travam, não gravam, não filtram nem mostram nada.

**Os painéis ficam ligados em todo contexto.** Um contexto pode desligá-los no `context.toml`:

```toml
[mods]
panel = false
```

Aí os painéis não abrem, `/panel`, `/metrics` e `/review-tests` não são registrados e a faixa fica sem os botões. Todo o
resto (métricas, travas, filtro de segredos, notas no prompt, estado depois da compactação) vale em qualquer contexto.

## Visão geral

| Mod | Para quê | Onde |
|---|---|---|
| [Faixa da demanda](#faixa-da-demanda) | Demanda, etapa, barras de contexto e de uso do plano, agentes rodando, botões dos painéis | acima do prompt |
| [Painéis](#painéis) | Geral, Métricas e Testes e Review, só informativos ([panel.md](panel.md)) | ao lado do chat, pelo botão ou pelo comando |
| [Métricas sozinhas](#métricas-sozinhas) | Cada delegação vira linha do `metrics.md`; cada turno do orquestrador soma no `orchestrator-metrics.md` | resultado do agente, fim do turno |
| [Travas da delegação](#travas-da-delegação) | Regras do orquestrador que o modelo pode esquecer, conferidas antes de o agente rodar | a chamada é recusada |
| [Contexto enxuto](#contexto-enxuto) | Compacta a conversa parada antes de o cache expirar | fim do turno |
| [Economia do orquestrador](#economia-do-orquestrador) | Código lido no chat do orquestrador | aviso ao modelo |
| [Filtro de segredos](#filtro-de-segredos) | Nenhuma linha da conversa leva o valor de um segredo | status |
| [Notas no prompt](#notas-no-prompt) | `[[nota]]` numa mensagem leva a nota junto | contexto da mensagem |
| [Estado depois da compactação](#estado-depois-da-compactação) | O orquestrador não perde o fio | linha na conversa |

## Faixa da demanda

```text
AiDW us-1234 Revisão ● espera você        contexto ▰▰▰▱▱ 41% · 82k   7d ▰▰▰▰▱ 58%   5h ▰▰▰▰▰ 91% · renova 16:40
╭──────────────────────────────────╮
│ ● Coder Sonnet medium      2m10s │
│ fix r1               184k tokens │
╰──────────────────────────────────╯
                                                                    Geral  Métricas  Testes e Review 4
```

1. **A demanda e o consumo:** o id, a etapa, **● espera você** quando a etapa é sua (aprovação, triagem, sua revisão de
   código, teste manual, PR, revisão final) e, do outro lado, o contexto deste chat em % da janela do modelo e as
   janelas de uso do plano (7d e 5h), cada um com uma barra fina.
2. **Os agentes rodando**, um card por agente: nome, modelo e effort, tempo, label e os tokens da última resposta. Sem
   agente, a linha não aparece. Quando os cards não cabem numa linha, viram uma lista.
3. **Os botões** **Geral**, **Métricas** e **Testes e Review** (**Dúvidas** no levantamento), com o número do que espera
   decisão.

As barras ficam amarelas a partir de 75% e vermelhas a partir de 90%; a partir de 75%, o 7d e o 5h mostram a hora local
em que a janela renova. As janelas de uso só aparecem em conta de assinatura. A faixa some em `DONE`; **`/strip`** esconde
e mostra. Ela atualiza ao vivo: o contexto a cada resposta, a demanda quando um arquivo da pasta dela muda.

## Painéis

Três painéis, cada um ao lado do chat, abertos só quando você pede, pelo botão da faixa ou pelo comando:

| Painel | Comando | Desenvolvimento | Revisão de PR | Levantamento |
|---|---|---|---|---|
| Geral | `/panel [aba]` | mapa da demanda, critérios e regras | mapa | mapa, card × código, estimativa |
| Métricas | `/metrics` | consumo | consumo | consumo |
| Testes e Review | `/review-tests` | Revisão · Testes | Comentários | Dúvidas |

`/panel <aba>` abre o painel que tem a aba (`/panel review`, `/panel tests`, `/panel comments`, `/panel questions` — ou
os nomes em português `revisao`, `testes`, `comentarios`, `duvidas` — abrem Testes e Review). **Os painéis só informam:**
manter ou descartar um achado, o resultado de um passo manual, o que publicar, aprovar uma PR e responder uma dúvida são
decididos no chat. O que cada painel mostra e de onde vem cada dado: [panel.md](panel.md).

## Métricas sozinhas

Toda delegação do AiDW (um `Agent` cujo prompt traz `Demand folder:`) vira uma linha no `metrics.md` quando o agente
termina. O mod roda o `aidw.py record` com os números medidos pelo Claude Code: tokens, chamadas de ferramenta, duração e
o `state` lido do JSON final do agente.

- **Label:** vem do nome do arquivo da tarefa (`task-coder-taxa.md` → `taxa`); sem tarefa, da descrição da chamada.
- **O que o orquestrador recebe:** o resultado volta com `AiDW: delegation recorded…` e o cabeçalho e o resumo para
  mostrar. Com ela, o orquestrador **não** roda o `record`; sem ela, ou se o mod disser que não conseguiu, ele roda.
- **Agente em segundo plano:** a linha é gravada quando ele termina, e o aviso chega como nota na conversa. O agente
  pendente fica no estado da sessão, então um `/reload-plugins` ou um `install` no meio do caminho não o perde.
- **Custo:** o mod soma o uso de todas as respostas do subagente (entrada, cache escrito, cache lido, saída) e o `record`
  grava o equivalente em preço de API na coluna *Cost (USD)*.
- **O orquestrador:** no fim de cada turno do chat principal, o mod soma o uso do turno no `orchestrator-metrics.md` da
  demanda pelo `aidw.py record-orchestrator`: uma linha por sessão e modelo, com o custo equivalente, e uma seção por
  etapa. É o que o `metrics.md` não mostra e costuma ser a maior parte do gasto.

## Travas da delegação

Antes de um agente do AiDW rodar, o mod confere a chamada pela tabela *Agents and effort*, que o `apply`/`install` grava
em `.aidw/runtime.json`. Ele recusa, com o motivo (`AiDW (trava da delegação): …` em português,
`AiDW (delegation lock): …` em inglês), quando:

| Regra | Recusa quando |
|---|---|
| Modelo | a chamada passa `model` e você não falou de modelo nas mensagens recentes |
| Formato | falta `Demand folder:` no prompt |
| Tabela | o `subagent_type` não é o padrão nem uma exceção do agente, ou o agente está desligado |
| Insumo colado | o prompt passa de 6.000 caracteres (diff, plano e revisão vão por caminho) |

Não há trava de rodadas: a demanda itera até terminar.

## Contexto enxuto

Voltar depois de uma hora parado regrava a conversa inteira no cache, a preço cheio. Por isso, no fim de cada turno do
orquestrador, o mod agenda uma compactação para **50 minutos** depois (antes de o cache expirar):

- Qualquer mensagem antes disso cancela o agendamento; um novo começa no fim do próximo turno.
- Quando o tempo passa, ele mede o contexto de novo e só compacta com **100k tokens ou mais**; o resumo guarda o que está
  com você (a pergunta, a aprovação), a próxima ação, os agentes em andamento e as decisões não gravadas, e o estado da
  demanda volta logo em seguida.
- Os limites são `IDLE_MS` e `IDLE_MIN` em `hooks/aidw.ts`.

## Economia do orquestrador

A regra mais cara de quebrar é o orquestrador ler código no próprio chat, porque esse texto fica no contexto até o fim da
demanda. Quando o orquestrador lê um arquivo de código fora da pasta do AiDW, o mod conta a leitura e acrescenta ao
resultado um aviso para delegar ao explorer. Uma verificação pontual de premissa (skill `verify-premise`) continua
valendo.

## Filtro de segredos

O resultado de cada ferramenta do orquestrador e dos agentes passa pelo filtro antes de virar linha da conversa,
inclusive o que volta com erro (uma connection string numa exceção). Ele mascara o valor e deixa só o nome e o tamanho,
como pede a política de segredos: `Password=«segredo ocultado: Password, 5 caracteres»`.

- **Pega:** senha de connection string (`Password`, `Pwd`, `AccountKey`, `SharedAccessKey`, `Client Secret`); campos
  JSON de senha, segredo, token, `apiKey`, `connectionString`; variáveis de ambiente `*_TOKEN`, `*_SECRET`,
  `*_PASSWORD`, `*_API_KEY`, `*_PAT`; tokens `Bearer`, JWT, chave privada PEM e formatos conhecidos de chave de API.
- **Não pega:** placeholders (`${VAR}`, `%VAR%`, `<senha>`) e código.
- **Status:** quantos segredos foram ocultados. O filtro é idempotente.

## Notas no prompt

Numa mensagem sua, `[[nome-da-nota]]` leva o texto daquela nota da base de conhecimento junto da mensagem (até três notas
por mensagem).

## Estado depois da compactação

Quando a conversa do orquestrador é compactada, o mod relê a demanda do disco e acrescenta um resumo do estado à **sua
primeira mensagem depois da compactação**, uma vez só: a etapa, a pasta e os worktrees, a rodada do laço e os achados
abertos, e o lembrete de reler a skill e os artefatos.

## Configuração

O `install` grava a raiz do AiDW desta máquina no plugin. Dois campos podem ser trocados nas configurações de plugin do
Claude Code: `aidwRoot` (a pasta do `aidw.py`) e `python` (o comando do Python, padrão `python`).

## Desenvolver um mod

- **Fonte:** `mods/aidw-mods/` é o plugin e a fonte da verdade. O `install` copia tudo, menos `tests/`, para
  `.aidw/marketplace/plugins/aidw-mods/`, onde o Claude Code o lê. Depois de mudar a fonte: `python aidw.py install` e
  `/reload-plugins` (ou um chat novo).

| Arquivo | O que tem |
|---|---|
| `hooks/register.tsx` | **o único arquivo que toca o engine (`$`)**: hooks, leitura do disco, `git`, `aidw.py record`. O `$` não atravessa `import` |
| `hooks/views.tsx` | as telas da faixa e dos painéis; recebem a tabela de elementos e as ações de navegação, nunca o `$` |
| `hooks/snapshot.ts` | o retrato da demanda (`wanted` diz o que ler, `buildSnapshot` monta) |
| `hooks/artifacts.ts` | os parsers dos artefatos (achados, triagem, critérios, roteiro, levantamento…) |
| `hooks/guards.ts` | as travas da delegação |
| `hooks/secrets.ts` | o filtro de segredos |
| `hooks/i18n.ts` | todo texto visível ao usuário, em inglês e português |
| `hooks/names.ts` | os nomes novos e antigos (em português) de artefato que o mod aceita |
| `hooks/aidw.ts` | prompt da delegação, `metrics.md`, `orchestrator-metrics.md`, `routing.toml`, limites do contexto |
| `types/index.d.ts` | o contrato do estado (`PluginState['aidw-mods']`) e os tipos do retrato |

- **Um mod novo** entra como mais hooks no `register.tsx`; a lógica pura vai num arquivo próprio, com teste. Os mods
  ligam só no modo orquestrador (o atom `active`).
- **Conferir:**

```powershell
claude plugin validate mods/aidw-mods
claude plugin test mods/aidw-mods
```

O primeiro lê o manifesto e o módulo como o engine vai ler. O segundo roda `tests/*.test.ts` contra o engine, com
demandas de exemplo para cada uso.
