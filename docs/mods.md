# Mods (só Claude Code)

Mods são plugins de *function hooks* do Claude Code: código que roda dentro da sessão, desenha na tela (faixa acima
do prompt, painel, status, toasts) e reage a eventos (uma ferramenta chamada, uma mensagem enviada, um subagente que
terminou). O AiDW traz os dele no plugin **`aidw-mods`**, que o `install` instala junto com o plugin `aidw`.

**Só existem no Claude Code.** O Codex não tem mods ([claude-e-codex.md](claude-e-codex.md)).

## Quando ficam ligados

Os mods do AiDW ficam ligados **só no modo orquestrador**:
- **Ligar:** `/aidw:orquestrar` ou `/aidw:levantamento` registram a sessão em `state/sessions.json` (o guard do AiDW grava), e o
  `aidw-mods` confere esse registro a cada mensagem.
- **Desligar:** `/aidw:sair` ou `/aidw:done` tiram a sessão do registro, e o painel fecha.

Fora do modo orquestrador eles não travam, não gravam, não filtram nem mostram nada.

**O painel vale em todo contexto.** Ele mostra os artefatos do fluxo do AiDW (cobertura de critérios, revisão em
cartões, roteiro manual, levantamento), e a aba sem dados some. Um contexto pode desligá-lo no `context.toml`:

```toml
[mods]
panel = false
```

Desligado, o painel não abre, o `/aidw-painel` não é registrado e a demanda fica só com a faixa acima do prompt
(demanda, contexto, 7d e 5h, agentes rodando). Todo o resto (métricas, travas, avisos, contexto enxuto, filtro de
segredos, notas no prompt, estado depois da compactação) vale em qualquer contexto.

## Visão geral

| Mod | Para quê | Onde aparece |
|---|---|---|
| [Faixa da demanda](#faixa-da-demanda) | Demanda, contexto, 7d e 5h com barras, e os agentes rodando | acima do prompt |
| [Painel do AiDW](#painel-do-aidw) | Acompanhar e decidir: mapa da demanda, critérios e regras, revisão em cartões, diffs, teste manual, métricas ([painel.md](painel.md)); desligado só no contexto com `[mods] panel = false` | painel lateral (`/aidw-painel`) |
| [Métricas sozinhas](#métricas-sozinhas) | Cada delegação vira linha do `metricas.md`; cada turno do orquestrador soma no `metricas-orquestrador.md` | resultado do agente, fim do turno |
| [Travas da delegação](#travas-da-delegação) | Regras do orquestrador que o modelo pode esquecer, conferidas antes do agente rodar | recusa da chamada |
| [Avisos](#avisos) | Quando a demanda precisa de você, um agente terminou ou o contexto cresceu | toasts |
| [Contexto enxuto](#contexto-enxuto) | Compacta sozinho antes de uma espera longa; sugere `/compact` a partir de 250k tokens | fim do turno |
| [Economia do orquestrador](#economia-do-orquestrador) | Código lido no chat do orquestrador | aviso ao modelo |
| [Filtro de segredos](#filtro-de-segredos) | Nenhuma linha da conversa leva o valor de um segredo | status |
| [Notas no prompt](#notas-da-base-de-conhecimento) | `[[nota]]` numa mensagem leva a nota junto | contexto da mensagem |
| [Estado depois da compactação](#estado-depois-da-compactação) | O orquestrador não perde o fio | linha na conversa |

## Faixa da demanda

```text
AiDW it-101662 · contexto ▬▬▬▭▭ 160k · 7d ▬▬▬▬▭ 58% · 5h ▬▬▬▬▬ 91% (renova 16:40) · ▶ codificador (otimizacao-r2) 2m10s
```

O id da demanda, o contexto deste chat em tokens (a barra enche em 250k) e as janelas de uso do plano (7d e 5h) em %,
cada um com barra fina, e os agentes rodando. O 7d e o 5h ficam amarelos a partir de 80% e mostram a hora local em
que a janela renova (com o dia, quando não é hoje). As janelas só aparecem em conta de assinatura. A faixa some em
`DONE`. **`/aidw-faixa`** esconde e mostra.

## Painel do AiDW

Abre sozinho quando o modo orquestrador liga (numa janela larga o bastante) e com **`/aidw-painel [aba]`**; no
terminal, as teclas `1`…`6` trocam de aba e `r` atualiza. O que cada aba mostra, de onde vem cada dado e o que os agentes gravam para
isso está em **[painel.md](painel.md)**:

| Uso | Abas |
|---|---|
| Desenvolvimento | Geral · Critérios e Regras · Revisão · Diffs · Teste manual · Métricas |
| Revisão de PR | Geral · Comentários · Diffs · Métricas |
| Levantamento | Geral · Card × código · Estimativa · Dúvidas · Métricas |

Aba sem dados fica oculta. No app, as abas são só clique; no terminal, as teclas aparecem e funcionam.

Tudo o que o painel decide por você vai para o **prompt** (decisões da revisão, publicar e votar numa PR, comentar
no card, ajustar um texto no chat) e só vale quando você envia. O resultado de um passo do teste manual e a resposta
a uma dúvida vão como mensagem sua. `/aidw-painel fluxo`, `agentes` e `pontos` (nomes antigos) abrem Geral,
Métricas e Card × código.

## Métricas sozinhas

Toda delegação do AiDW (um `Agent` cujo prompt traz `Pasta da demanda:`) vira uma linha no `metricas.md` quando o
agente termina. O mod chama o próprio `aidw.py record` com os números medidos pelo Claude Code: tokens, chamadas de
ferramenta, duração e o `state` lido do JSON final do agente.
- **Nível e rótulo:** o nível vem do `Nível:` do prompt; o rótulo vem do nome da tarefa (`tarefa-codificador-rota.md` →
  `rota`).
- **O que o orquestrador recebe:** o resultado volta com a linha `AiDW: delegação registrada…` e o `header` e o
  `resumo` para mostrar. Com ela, o orquestrador **não** roda o `record`. Sem ela, ou se o mod disser que não
  conseguiu, ele roda à mão.
- **Agente em segundo plano:** a linha é gravada quando ele termina, e o aviso chega como uma nota na conversa e um
  toast.
- **O orquestrador:** no fim de cada turno do chat principal, o mod soma o uso do turno (entrada, cache escrito, cache
  lido e saída, como a API informou) no `metricas-orquestrador.md` da demanda, pelo `aidw.py record-orchestrator`: uma
  linha por sessão e modelo, com o custo equivalente em preço de API. É o que o `metricas.md` não mostra e costuma ser
  a maior parte do gasto.

## Travas da delegação

Antes de um agente do AiDW rodar, o mod confere a chamada pela tabela *Effort per task*, que o `apply` grava em
`.aidw/runtime.json` (`levels`). Ele recusa, com o motivo, quando:

| Regra | Recusa quando |
|---|---|
| Modelo | a chamada passa `model` e o Felipe não falou de modelo nas últimas mensagens |
| Formato | falta `Pasta da demanda:` ou `Nível:` no prompt, ou o nível não existe |
| Tabela | o `subagent_type` não é a célula do agente naquele nível, o agente está desligado ou não roda naquele nível |
| Insumo colado | o prompt passa de 6.000 caracteres (diff, plano e review vão por caminho) |
| Limite de rodadas | num desenvolvimento, a revisão (ou a revisão do plano) chegou ao `max_retries` e a chamada é do revisor, do codificador ou do planejador do laço |

O limite de rodadas é uma trava de verdade: o orquestrador tem de parar e te perguntar. Só você libera mais uma
rodada, pelo botão **Liberar +1 rodada** do painel ou com **`/aidw-rodada`**. Revisão de PR e levantamento não têm
esse laço.

## Avisos

Toasts, cada um uma vez:
- **A demanda espera você:** aprovação, teste manual ou revisão final.
- **Agente terminou:** um agente em segundo plano terminou, com o `state` dele.
- **Contexto:** o contexto do orquestrador passou de 250k tokens fora de uma espera longa (ver *Contexto enxuto*).
- **Compactou:** o mod compactou a conversa antes de uma espera longa, com o tamanho antes e depois.

## Contexto enxuto

Cada ação do orquestrador relê a conversa inteira, e uma volta depois de 1h parado regrava tudo no cache, ao preço
cheio. Por isso o mod mede o contexto em tokens no fim de cada turno:
- **Espera longa** (`HUMAN_APPROVAL`, `FINAL_REVIEW`, `CODE_REVIEW`, `QA_TEST`) com 150k tokens ou mais: compacta
  sozinho, logo depois do turno, uma vez por espera, pedindo ao resumo que guarde o que está com você (a pergunta, a
  aprovação ou o pacote) e as decisões não gravadas; o estado da demanda volta em seguida (*Estado depois da
  compactação*). Se você responder antes, a compactação não roda. O teste manual não conta: é passo a passo.
- **Fora de espera**, a partir de 250k tokens: um toast sugere `/compact` na próxima virada de etapa. Depois que o
  contexto cai abaixo de 150k, o aviso pode voltar.
- Os limites ficam em `hooks/aidw.ts` (`CONTEXT_WARN`, `CONTEXT_COMPACT`, `LONG_WAIT`).

## Economia do orquestrador

A regra mais cara de quebrar é o orquestrador ler código no próprio chat, porque esse texto fica no contexto até o
fim da demanda.
- **Aviso:** quando o orquestrador lê um arquivo de código fora da pasta do AiDW, o mod conta a leitura e acrescenta ao
  resultado um aviso para delegar ao explorador. Uma verificação pontual de premissa (skill `verificar-premissa`)
  continua valendo.
- **Onde aparece:** só no aviso ao modelo; o painel não mostra a contagem.

## Filtro de segredos

Toda linha da conversa do orquestrador e dos agentes passa pelo filtro antes de entrar no contexto e no transcript.
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
- o uso, a etapa e o nível;
- a pasta e os worktrees;
- a rodada do laço e os achados abertos;
- o lembrete de reler a skill e os artefatos.

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
| `hooks/views.tsx` | as telas da faixa e do painel; recebem a tabela de elementos e as ações, nunca o `$` |
| `hooks/snapshot.ts` | o retrato da demanda (`wanted` diz o que ler, `buildSnapshot` monta) |
| `hooks/artifacts.ts` | os parsers dos artefatos (achados, triagem, critérios, roteiro, levantamento…) |
| `hooks/guards.ts` | as travas da delegação |
| `hooks/secrets.ts` | o filtro de segredos |
| `hooks/diffs.ts` | o diff dividido por arquivo |
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
