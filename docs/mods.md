# Mods (só Claude Code)

Mods são plugins de *function hooks* do Claude Code: código que roda dentro da sessão, desenha na tela (faixa acima
do prompt, painel, status) e reage a eventos (uma ferramenta chamada, uma mensagem enviada, um subagente que
terminou). O AiDW traz os dele no plugin **`aidw-mods`**, que o `install` instala junto com o plugin `aidw`.

**Só existem no Claude Code.** O Codex não tem mods ([claude-e-codex.md](claude-e-codex.md)).

## Quando ficam ligados

Os mods do AiDW ficam ligados **só no modo orquestrador**:
- **Ligar:** `/aidw:go` ou `/aidw:lev` registram a sessão em `state/sessions.json`, e o `aidw-mods` confere esse
  registro a cada mensagem. Quem grava é a skill `go`, com `aidw.py session bind` (lê `CLAUDE_CODE_SESSION_ID`), e
  o hook do guard, onde o cliente manda o comando de barra a ele (o app sim, o terminal não).
- **Qual demanda:** o registro guarda o contexto, o id e a pasta da demanda (`session bind --demand <id>`, e todo
  `demand set` numa sessão já registrada). O mod lê a pasta dali, sem deduzir a demanda do texto: vale para qualquer
  id, com card de qualquer plataforma ou livre (`feat-<slug>`, `fix-<slug>`…). Sem demanda no registro, vale a pasta
  do chat quando ele abriu na demanda ou num worktree dela.
- **Desligar:** `/aidw:sair` ou `/aidw:done` tiram a sessão do registro, e o painel fecha.

Fora do modo orquestrador eles não travam, não gravam, não filtram nem mostram nada.

**Os painéis valem em todo contexto.** Eles mostram os artefatos do fluxo do AiDW (cobertura de critérios, revisão
em cartões, roteiro manual, levantamento), e a aba sem dados some. Um contexto pode desligá-lo no `context.toml`:

```toml
[mods]
panel = false
```

Desligado, os painéis não abrem, `/painel`, `/metricas` e `/testes-review` não são registrados e a faixa acima do prompt
fica sem os botões (demanda, contexto, 7d e 5h, agentes rodando). Todo o resto (métricas, travas, avisos, contexto enxuto, filtro de
segredos, notas no prompt, estado depois da compactação) vale em qualquer contexto.

## Visão geral

| Mod | Para quê | Onde aparece |
|---|---|---|
| [Faixa da demanda](#faixa-da-demanda) | Demanda, contexto, 7d e 5h com barras, e os agentes rodando | acima do prompt |
| [Painéis do AiDW](#painéis-do-aidw) | Geral, Métricas e Testes e Review, só informativos ([painel.md](painel.md)); desligados só no contexto com `[mods] panel = false` | ao lado do chat, pelo botão da faixa ou pelo comando |
| [Métricas sozinhas](#métricas-sozinhas) | Cada delegação vira linha do `metricas.md`; cada turno do orquestrador soma no `metricas-orquestrador.md` | resultado do agente, fim do turno |
| [Travas da delegação](#travas-da-delegação) | Regras do orquestrador que o modelo pode esquecer, conferidas antes do agente rodar | recusa da chamada |
| [Contexto enxuto](#contexto-enxuto) | Compacta sozinho a conversa parada há 50 min (a partir de 100k tokens), antes de o cache expirar | fim do turno |
| [Economia do orquestrador](#economia-do-orquestrador) | Código lido no chat do orquestrador | aviso ao modelo |
| [Filtro de segredos](#filtro-de-segredos) | Nenhuma linha da conversa leva o valor de um segredo | status |
| [Notas no prompt](#notas-da-base-de-conhecimento) | `[[nota]]` numa mensagem leva a nota junto | contexto da mensagem |
| [Estado depois da compactação](#estado-depois-da-compactação) | O orquestrador não perde o fio | linha na conversa |

## Faixa da demanda

```text
AiDW us-128734 Revisão ● espera você        contexto ▰▰▰▱▱ 41% · 82k   7d ▰▰▰▰▱ 58%   5h ▰▰▰▰▰ 91% · renova 16:40
╭──────────────────────────────────╮
│ ● Dev Sonnet medium        2m10s │
│ correção r1          184k tokens │
╰──────────────────────────────────╯
                                                                          Geral  Métricas  Testes e Review 4
```

Três linhas (painel v4):
1. **A demanda e o consumo:** o id, a etapa, **● espera você** em laranja quando a etapa é sua (aprovação, triagem,
   revisão de código, teste manual, PR, revisão final) e, do outro lado, o contexto deste chat em % da janela do
   modelo, com os tokens, e as janelas de uso do plano (7d e 5h) em %, cada um com barra fina.
2. **Os agentes rodando**, um card por agente: nome, modelo e effort (da variante), o tempo, o label e os tokens da última
   resposta (andam a cada passo; antes do primeiro, `começando`); sem agente, a linha não aparece. Quando os cards não
   cabem numa linha (a largura que o engine dá à faixa), vira uma lista, uma linha por agente com as colunas
   alinhadas; se nem a lista cabe na altura, os primeiros e `+N agentes · Xk tokens`.
3. **Os botões** **Geral**, **Métricas** e **Testes e Review** (**Dúvidas** no levantamento; com o número do que espera decisão, em laranja), numa linha só,
   à direita, que abrem os painéis. As barras ficam na cor normal, amarelas a partir de 75% e vermelhas a partir de 90%; o 7d e o 5h,
a partir de 75%, mostram a hora local em que a janela renova (com o dia, quando não é hoje). As janelas só aparecem em conta de assinatura. A faixa some em
`DONE`. **`/faixa`** esconde e mostra.

**Ao vivo, sem esperar o fim do turno** (2026-11-04): o contexto anda a cada resposta do orquestrador (`turn.step`), e o
contexto e as janelas 5h/7d também quando o engine os empurra (`session.measure`); a demanda é relida quando um `Write`
ou `Edit` (seu ou de um agente) grava na pasta dela e, a cada 5 s, quando um arquivo da pasta mudou de tamanho ou data
(você no editor, outro chat, um script). Nada disso gasta token: roda no mod, fora do contexto do modelo. Só o custo do
chat principal no `metricas-orquestrador.md` segue por turno.

## Painéis do AiDW

Três painéis, cada um ao lado do chat, abertos só quando você pede: pelo botão na faixa ou pelo comando (painel v4,
Felipe, 2026-11-03). Com dois ou mais abertos, o app mostra as abas entre eles. O que cada um mostra, de onde vem cada
dado e o que os agentes gravam para isso está em **[painel.md](painel.md)**:

| Painel | Comando | Desenvolvimento | Revisão de PR | Levantamento |
|---|---|---|---|---|
| Geral | `/painel [aba]` | mapa e critérios e regras | mapa | mapa, card × código e estimativa |
| Métricas | `/metricas` | consumo | consumo | consumo |
| Testes e Review (Dúvidas no levantamento) | `/testes-review` | Revisão · Testes | Comentários | Dúvidas |

A Geral e as Métricas são uma página só; em Testes e Review, aba sem dados fica oculta, e a linha de abas só aparece com duas ou mais. Testes e Review abre na primeira aba que espera
você. `/painel <aba>` abre o painel da aba (`/painel revisao` abre Testes e Review). Os painéis só informam: toda decisão é no chat. No terminal, as teclas `1`, `2`… trocam
de aba; no app, as abas são só clique. O diff fica com o app (*Alterações* na barra lateral e o painel de diff dele).

Os painéis só informam (Felipe, 2026-11-03): manter ou descartar um achado, o resultado de um passo do teste manual, o
que publicar e se o AiDW aprova uma PR, comentar no card e responder uma dúvida são decididos no chat, com o
orquestrador e o agente da etapa.

## Métricas sozinhas

Toda delegação do AiDW (um `Agent` cujo prompt traz `Pasta da demanda:`) vira uma linha no `metricas.md` quando o
agente termina. O mod chama o próprio `aidw.py record` com os números medidos pelo Claude Code: tokens, chamadas de
ferramenta, duração e o `state` lido do JSON final do agente.
- **Rótulo:** vem do nome da tarefa (`tarefa-codificador-rota.md` → `rota`); sem tarefa, da descrição da chamada.
- **O que o orquestrador recebe:** o resultado volta com a linha `AiDW: delegação registrada…` e o `header` e o
  `resumo` para mostrar. Com ela, o orquestrador **não** roda o `record`. Sem ela, ou se o mod disser que não
  conseguiu, ele roda à mão.
- **Agente em segundo plano:** a linha é gravada quando ele termina, e o aviso chega como uma nota na conversa. Os
  números são os mesmos da notificação do agente (`subagent_tokens`, `tool_uses`): os tokens são o uso da
  última resposta dele (o contexto no fim, como o `totalTokens` de um agente em primeiro plano), não a soma do turno,
  que conta o cache relido a cada resposta e sai de 10 a 30 vezes maior; as ferramentas são contadas no transcript do
  agente. O agente pendente fica no estado da sessão, então um `/reload-plugins` ou um `aidw.py install` no meio do
  caminho não perde o registro.
- **Robustez:** o uso de cada subagente fica no estado da sessão (atravessa um `/reload-plugins`); o mod lê a última
  linha JSON da saída do `record`, e quando o `record` gravou mas não devolveu o header, o aviso diz que a linha já
  está lá (o orquestrador não registra de novo).
- **O custo da delegação:** o mod soma o uso de todas as respostas do subagente (entrada, cache escrito, cache lido e
  saída, no modelo delas) e passa ao `record`, que grava na coluna *Custo (USD)* o equivalente em preço de API. A
  coluna de tokens continua sendo o contexto no fim; o custo é o que a API cobra pela soma. Sem as respostas (o
  agente atravessou uma recarga do mod), o custo fica —.
- **O orquestrador:** no fim de cada turno do chat principal, o mod soma o uso do turno (entrada, cache escrito, cache
  lido e saída, como a API informou) no `metricas-orquestrador.md` da demanda, pelo `aidw.py record-orchestrator`: uma
  linha por sessão e modelo, com o custo equivalente em preço de API, e a seção *Por etapa* com os mesmos turnos
  somados pela etapa da demanda (`step` do `demand.json` no começo do turno). É o que o `metricas.md` não mostra e
  costuma ser a maior parte do gasto (≥ 95 % na medição de 2026-11-04).

## Travas da delegação

Antes de um agente do AiDW rodar, o mod confere a chamada pela tabela *Agents and effort*, que o `apply` grava em
`.aidw/runtime.json` (`variants`: o padrão e as exceções de cada agente). Ele recusa, com o motivo, quando:

| Regra | Recusa quando |
|---|---|
| Modelo | a chamada passa `model` e o Felipe não falou de modelo nas últimas mensagens |
| Formato | falta `Pasta da demanda:` no prompt |
| Tabela | o `subagent_type` não é o padrão nem uma exceção do agente, ou o agente está desligado |
| Insumo colado | o prompt passa de 6.000 caracteres (diff, plano e review vão por caminho) |

Um `runtime.json` de antes do fluxo v3 (sem `variants`) desliga a trava até o próximo `aidw.py apply`.

Não há trava de rodadas: a demanda itera até terminar (painel v4).

## Sem avisos próprios

O mod não levanta toast nem notificação (painel v4, Felipe, 2026-11-03): o app do Claude já avisa quando o turno
acaba. O agente em segundo plano que termina chega como nota na conversa (*Métricas sozinhas*), e o resultado de um
`/painel` que não coube volta no próprio comando.

## Contexto enxuto

Uma volta depois de 1h parado regrava a conversa inteira no cache, ao preço cheio. Por isso, no fim de cada turno do
orquestrador, o mod agenda uma compactação para **50 minutos** depois (antes de o cache expirar):
- Se você mandar qualquer mensagem antes, o agendamento cai e um novo começa no fim do próximo turno.
- Quando o tempo passa, ele mede o contexto de novo e só compacta com **100k tokens ou mais**; o resumo guarda o que
  está com você (a pergunta, a aprovação ou o pacote), a próxima ação, os agentes em andamento e as decisões não
  gravadas, e o estado da demanda volta em seguida (*Estado depois da compactação*).
- Fora disso, a compactação é sua (`/compact`) ou a nativa do Claude, perto do limite da janela. Uma demanda pode ser
  retomada num chat novo: o estado está nos arquivos e o conhecimento na base.
- Os limites ficam em `hooks/aidw.ts` (`IDLE_MS`, `IDLE_MIN`). A regra antiga (espera longa e troca de etapa, a partir
  de 150k) saiu em 2026-10-30: não disparava.

## Economia do orquestrador

A regra mais cara de quebrar é o orquestrador ler código no próprio chat, porque esse texto fica no contexto até o
fim da demanda.
- **Aviso:** quando o orquestrador lê um arquivo de código fora da pasta do AiDW, o mod conta a leitura e acrescenta ao
  resultado um aviso para delegar ao explorador. Uma verificação pontual de premissa (skill `verificar-premissa`)
  continua valendo.
- **Onde aparece:** só no aviso ao modelo; o painel não mostra a contagem.

## Filtro de segredos

O resultado de cada ferramenta do orquestrador e dos agentes passa pelo filtro antes de virar linha da conversa,
inclusive o que volta com erro (uma connection string numa exceção): esse volta como erro, com o texto filtrado. O
texto do modelo e o que você digita, o plugin de segurança da organização (`cc-plugin-sec-default`) cuida: ele fica
acima dos plugins do usuário e não chama os de baixo nas linhas, por isso o mod não tem hook de `session.append`
(2026-11-04). O filtro é idempotente: um texto já mascarado passa de novo igual.
Ele mascara o valor e mostra só o nome e o tamanho, como pede a policy de segredos:
`Password=«segredo ocultado: Password, 11 caracteres»`.
- **O que ele pega:**
  - senha de connection string (`Password`, `Pwd`, `AccountKey`, `SharedAccessKey`, `Client Secret`);
  - campos JSON de senha, segredo, token, `apiKey`, `connectionString` e `stringConexao`;
  - variáveis de ambiente `*_TOKEN`, `*_SECRET`, `*_PASSWORD`, `*_API_KEY` e `*_PAT`;
  - `Bearer`, JWT, chave privada PEM e chaves de API conhecidas.
- **O que ele não pega:** placeholders (`${VAR}`, `%VAR%`, `<senha>`) e código (`Password = request.Password`).
- **No status:** quantos segredos foram ocultados.

## Notas da base de conhecimento

Numa mensagem sua, `[[nome-da-nota]]` leva o texto da nota da base de conhecimento do contexto junto da mensagem (até
três notas por mensagem).

## Estado depois da compactação

Quando a conversa do orquestrador é compactada, o mod relê a demanda do disco e põe na conversa um resumo do estado:
- o uso, a etapa e o modo;
- a pasta e os worktrees;
- a rodada do laço e os achados abertos;
- o lembrete de reler a skill e os artefatos.

O resumo vai junto da **sua primeira mensagem depois da compactação**, uma vez só. O mod percebe a compactação pela
dele mesmo (a ociosa) ou pelo contexto que caiu para menos da metade, a partir de 40k tokens. Não vai pelo evento da
compactação nem pelo `SessionStart`: o plugin de segurança da organização (`cc-plugin-sec-default`) passa os dois
adiante sem chamar os plugins do usuário. Uma seção fixa no prompt de sistema mudaria a cada etapa e regravaria o
cache da conversa inteira.

## Configuração

O `install` grava a raiz do AiDW desta máquina no plugin. Dois campos podem ser trocados no menu de configuração do
Claude Code (`pluginConfigs`): `aidwRoot` (a pasta do `aidw.py`) e `python` (o comando do Python, padrão `python`).

## Desenvolver um mod

- **Fonte:** `mods/aidw-mods/` é o plugin e a fonte da verdade. O `install` copia tudo, menos `tests/`, para
  `.aidw/marketplace/plugins/aidw-mods/`, onde o Claude Code o lê. Depois de mudar a fonte: `python aidw.py install` e
  `/reload-plugins` (ou um chat novo).
- **Arquivos:**

| Arquivo | O que tem |
|---|---|
| `hooks/register.tsx` | **o único arquivo que toca o engine (`$`)**: hooks, leitura do disco, `git`, `aidw.py record`. O `$` não atravessa `import` |
| `hooks/views.tsx` | as telas da faixa e dos painéis; recebem a tabela de elementos e as ações de navegação, nunca o `$` |
| `hooks/snapshot.ts` | o retrato da demanda (`wanted` diz o que ler, `buildSnapshot` monta) |
| `hooks/artifacts.ts` | os parsers dos artefatos (achados, triagem, critérios, roteiro, levantamento…) |
| `hooks/guards.ts` | as travas da delegação |
| `hooks/secrets.ts` | o filtro de segredos |
| `hooks/aidw.ts` | prompt da delegação, `metricas.md`, `metricas-orquestrador.md`, `routing.toml`, limites do contexto |
| `types/index.d.ts` | o contrato do estado (`PluginState['aidw-mods']`) e os tipos do retrato |

- **Um mod novo:** entra como mais hooks no `register.tsx`. A lógica pura vai num arquivo próprio, com teste. O mod
  liga só no modo orquestrador (o atom `active`).
- **Conferir:**

```powershell
claude plugin validate mods/aidw-mods
claude plugin test mods/aidw-mods
```

O primeiro lê o manifesto e o módulo como o engine vai ler. O segundo roda `tests/*.test.ts` contra o engine: os
hooks do teste fazem o papel do disco, do `aidw.py`, do relógio e das ferramentas, com as três demandas de exemplo,
uma por uso.
