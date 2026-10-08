# Mods (só Claude Code)

Mods são plugins de *function hooks* do Claude Code: código que roda dentro da sessão e pode desenhar na tela (faixa
acima do prompt, painéis, status, toasts) e reagir a eventos (uma ferramenta chamada, um prompt enviado, um subagente
que terminou). O AiDW traz os dele no plugin **`aidw-mods`**, que o `install` instala junto com o plugin `aidw`.

**Só existem no Claude Code.** O Codex não tem mods ([claude-e-codex.md](claude-e-codex.md)).

## Quando ficam ligados

Os mods do AiDW ficam ligados **só no modo orquestrador**: quando você chama `/aidw:orquestrar` ou `/aidw:levantamento`,
o guard do AiDW registra a sessão em `state/sessions.json`, e o `aidw-mods` confere esse registro a cada mensagem. Com
`/aidw:sair` ou `/aidw:done`, a sessão sai do registro e os mods se desligam. Fora do modo orquestrador eles não gravam
nem mostram nada.

## O que fazem hoje

### Métricas gravadas sozinhas

Toda delegação do AiDW (um `Agent` cujo prompt traz `Pasta da demanda:`) vira uma linha no `metricas.md` quando o
agente termina, pelo próprio `aidw.py record`, com os números medidos pelo Claude Code: tokens, chamadas de ferramenta,
duração e o `state` lido do JSON final do agente. O nível vem do `Nível:` do prompt, e o rótulo vem do nome da tarefa
(`tarefa-codificador-rota.md` → `rota`).

- O resultado do agente volta ao orquestrador com a linha `AiDW: delegação registrada…` e o `header` e o `resumo` para
  mostrar. Com ela, o orquestrador **não** roda o `record`. Sem ela, ou se o mod disser que não conseguiu, ele roda à
  mão. Assim não há linha duplicada nem delegação sem registro.
- **Agente em segundo plano:** a linha é gravada quando ele termina, e o aviso chega ao orquestrador como uma nota na
  conversa.

### Faixa da demanda

Uma linha acima do prompt:

```text
AiDW us-131190 · CODER_FIX · revisão r4/3 ⚠ · padrao · 12 delegações · 1,2M tokens · ▶ codificador (rota)
```

| Parte | De onde vem |
|---|---|
| demanda e etapa | `demand.json` (atualiza a cada `aidw.py demand set`) |
| rodada | o maior `review-*-r<N>.md` (ou `revisao-plano-*-r<N>.md` nas etapas do plano) contra o `max_retries` do `routing.toml`; passou do limite, ⚠ |
| nível, delegações e tokens | `metricas.md` |
| ▶ | os agentes do AiDW rodando agora |

A demanda é a da pasta da sessão (o worktree ou a pasta da demanda) ou a da última delegação. A faixa some quando a
demanda chega em `DONE`. **`/aidw-faixa`** esconde e mostra a faixa.

## Configuração

O `install` grava a raiz do AiDW desta máquina no plugin. Dois campos podem ser trocados no menu de configuração do
Claude Code (`pluginConfigs`): `aidwRoot` (a pasta do `aidw.py`) e `python` (o comando do Python, padrão `python`).

## Desenvolver um mod

- **Fonte:** `mods/aidw-mods/` (o plugin, a fonte da verdade). O `install` copia tudo, menos `tests/`, para
  `.aidw/marketplace/plugins/aidw-mods/`, onde o Claude Code o lê. Depois de mudar a fonte: `python aidw.py install` e
  `/reload-plugins` (ou um chat novo).
- **Um módulo só:** o `hooks/hooks.json` aponta um módulo (`hooks/register.tsx`), que importa os outros arquivos do
  plugin. Um mod novo entra como mais hooks nesse módulo, ou num arquivo que ele importa, e também liga só no modo
  orquestrador (o atom `active`).
- **Estado:** o que a tela lê fica em `$.state`, declarado em `types/index.d.ts` (`PluginState['aidw-mods']`).
- **Lógica sem `$`** (ler o prompt, o `metricas.md`, o `routing.toml`) fica em `hooks/aidw.ts`, testável sem o engine.
- **Conferir:**

```powershell
claude plugin validate mods/aidw-mods
claude plugin test mods/aidw-mods
```

O primeiro lê o manifesto e o módulo como o engine vai ler; o segundo roda `tests/*.test.ts` contra o engine (os hooks
do teste fazem o papel do disco, do `aidw.py` e das ferramentas).
