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

## Visão geral

| Mod | Para quê | Onde aparece |
|---|---|---|
| [Faixa da demanda](#faixa-da-demanda) | Onde a demanda está, sem perguntar | acima do prompt |
| [Painel do AiDW](#painel-do-aidw) | Acompanhar e decidir: a visão geral e o próximo passo, critérios, revisão, diffs, o que é de cada uso e as métricas completas | painel lateral (`/aidw-painel`) |
| [Métricas sozinhas](#métricas-sozinhas) | Cada delegação vira linha do `metricas.md` | resultado do agente |
| [Travas da delegação](#travas-da-delegação) | Regras do orquestrador que o modelo pode esquecer, conferidas antes do agente rodar | recusa da chamada |
| [Avisos](#avisos) | Quando a demanda precisa de você, passou do orçamento ou o contexto encheu | toasts |
| [Economia do orquestrador](#economia-do-orquestrador) | Contexto do orquestrador e código lido no chat | faixa e aviso ao modelo |
| [Filtro de segredos](#filtro-de-segredos) | Nenhuma linha da conversa leva o valor de um segredo | status |
| [Notas no prompt](#notas-da-base-de-conhecimento) | `[[nota]]` numa mensagem leva a nota junto | contexto da mensagem |
| [Estado depois da compactação](#estado-depois-da-compactação) | O orquestrador não perde o fio | linha na conversa |

## Faixa da demanda

```text
AiDW us-131190 · Revisar · revisão r4/3 ⚠ travado · orçamento 60% · contexto 41% · ▶ codificador (rota)
```

| Parte | De onde vem |
|---|---|
| fase | a fase da linha do tempo pela etapa do `demand.json`; o uso aparece só quando não é desenvolvimento |
| ⏸ espera você | etapa `HUMAN_APPROVAL`, `MANUAL_TEST` ou `FINAL_REVIEW` |
| rodada | só nas etapas do laço: o maior `review-*-r<N>.md` (ou `revisao-plano-*-r<N>.md`) contra o `max_retries` mais as rodadas liberadas |
| orçamento | soma do `metricas.md` contra o orçamento do nível (amarelo a partir de 80%) |
| contexto | uso do contexto do próprio orquestrador |
| AIDW-TESTE | ajustes de teste ainda aplicados, a partir da revisão |
| ▶ | os agentes do AiDW rodando agora |

A faixa some em `DONE`. **`/aidw-faixa`** esconde e mostra.

## Painel do AiDW

Abre sozinho quando o modo orquestrador liga (numa janela larga o bastante) e com **`/aidw-painel [aba]`**. As abas
mudam com o uso da demanda; as teclas `1`…`6` trocam de aba e `r` atualiza. A primeira é sempre **Geral** e a última,
**Métricas**: a Geral responde "onde estamos e o que eu faço agora" em poucas linhas; a Métricas guarda os números
completos para análise.

### Abas comuns aos três usos

- **Geral:**
  - a situação em uma linha (⏸ espera você, ▶ trabalhando, ● em andamento, ✓ concluída, ⏸ pausada);
  - o **próximo passo**: o que você faz (aprovar, testar, revisar, liberar rodada) ou o que o AiDW está fazendo, e a
    nota que o orquestrador gravou no `demand.json`;
  - o progresso pelas fases (✓ feito, ● atual, ○ pendente);
  - um número por linha: critérios atendidos, achados abertos, passos do teste manual (ou achados e voto, ou pontos,
    estimativa e dúvidas), consumo do orçamento e contexto do orquestrador;
  - **Atenção**, só quando há: AIDW-TESTE aplicado, orçamento perto do fim ou estourado, contexto acima de 80%, código
    lido no chat, laço travado (com o botão **Liberar +1 rodada**);
  - os agentes rodando agora, com o tempo correndo, e os três últimos, com o resultado em palavras;
  - os worktrees com a branch e a pasta da demanda, com link.
- **Métricas:**
  - os totais: delegações, tokens contra o orçamento, tempo de agente e custo em US$ quando o `metricas.md` traz (o
    subagente nativo do Claude só mede tokens; o Codex e o headless trazem custo);
  - consumo por agente (com a média por chamada), por modelo e effort, por nível e por dia;
  - o resultado das chamadas (concluído, pediu mudanças, bloqueado…);
  - retrabalho: as fases que voltaram e quantas vezes, as rodadas de revisão do plano e do código, o contexto do
    orquestrador e o código lido no chat;
  - todas as delegações, a mais recente primeiro;
  - todos os artefatos da pasta, agrupados por etapa, com link para abrir cada um.

`/aidw-painel fluxo` e `/aidw-painel agentes` (os nomes antigos) abrem a Geral e a Métricas.

### Desenvolver uma demanda (feature, bugfix, refactor, hotfix)

| Aba | O que mostra | O que você faz nela |
|---|---|---|
| **Critérios** | cada critério de aceite do plano, como vai ser provado (do plano de testes) e o resultado dos relatórios de teste | — |
| **Revisão** | achados por rodada (severidade, `arquivo:linha`, status, triagem), o resumo de todas as rodadas e a revisão do plano | **Liberar +1 rodada** quando o laço trava |
| **Diffs** | o diff de cada worktree contra a base, ou de qualquer `.patch` da pasta, arquivo por arquivo | escolher a fonte e o arquivo; no app desktop, **Abrir no painel de diff do app** |
| **Teste manual** | o `roteiro-testes` com ✅/❌ por passo e o próximo passo em destaque | escrever a evidência e apertar **✅ Passou** ou **❌ Falhou**: vai ao orquestrador como mensagem sua |

### Revisar a PR de outra pessoa (pr-review)

| Aba | O que mostra | O que você faz nela |
|---|---|---|
| **Achados e voto** | os achados da última rodada, com a triagem e o rascunho do comentário; o que já foi publicado; o voto sugerido pelo revisor | marcar o que publicar, escolher o voto e **Levar a decisão ao prompt** |
| **Diffs** | o diff da PR (o `.patch` ou o worktree da PR, da base ao head) | escolher a fonte e o arquivo |

A decisão vai para o **prompt**, não é enviada: publicar comentário e votar são ações travadas, e só valem quando você
manda a mensagem.

### Analisar uma demanda (levantamento)

| Aba | O que mostra | O que você faz nela |
|---|---|---|
| **Pontos do card** | cada ponto do card validado no código (confirmado, diverge, não encontrado, outro sistema) com a evidência | — |
| **Estimativa e dúvidas** | story points, horas, complexidade e confiança; as dúvidas com por que importam e para quem | responder uma dúvida (vai como mensagem sua) e **Levar ao prompt: publicar o comentário no card** |

Os parsers aceitam os dois formatos de levantamento que existem: o da referência *levantamento* e o antigo (seções
numeradas, story points em tópicos, dúvidas `D1.`).

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
- **Orçamento:** a demanda passou de 80% e de 100% do orçamento de tokens do nível (trivial 300 mil, simples 800 mil,
  padrao 2 milhões, complexa 4 milhões, critica 6 milhões). O aviso não trava nada.
- **Contexto:** o contexto do orquestrador passou de 80%.

## Economia do orquestrador

A regra mais cara de quebrar é o orquestrador ler código no próprio chat, porque esse texto fica no contexto até o
fim da demanda.
- **Aviso:** quando o orquestrador lê um arquivo de código fora da pasta do AiDW, o mod conta a leitura e acrescenta ao
  resultado um aviso para delegar ao explorador. Uma verificação pontual de premissa (skill `verificar-premissa`)
  continua valendo.
- **Na faixa:** a contagem de leituras e o uso do contexto do orquestrador.

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
| `hooks/aidw.ts` | prompt da delegação, `metricas.md`, `routing.toml`, orçamento |
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
