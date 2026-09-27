---
name: contexto-usar
description: Troca o contexto de trabalho ativo do AiDW — valida o contexto, grava no aidw.config.toml, regenera o ambiente e, se o AiDW estiver instalado, regenera o plugin aidw com as regras do novo contexto. Use quando o usuário pedir para usar, ativar ou trocar de contexto.
aidw: admin
---

# contexto-usar

`aidw.py` fica em `{{root}}` (raiz do AiDW). Rode os comandos exatamente na forma `python "{{root}}/aidw.py" ...`, com as aspas: é a que as regras de permissão liberam.

1. **Qual contexto:** o que o usuário pediu. Se ele não disse ou o nome não bate, rode
   `python "{{root}}/aidw.py" context list` e pergunte com as opções (vazio = nenhum contexto).
2. **Demanda aberta:** rode `python "{{root}}/aidw.py" demand list --active`. Se houver demanda ativa no contexto
   atual, avise que ela fica pausada (as regras e os agentes mudam) e pergunte se quer trocar mesmo assim.
3. **Validar:** `python "{{root}}/aidw.py" context check <nome>`. Com erro, mostre os erros e pare — não troque para
   um contexto quebrado. Avisos: mostre e siga.
4. **Trocar:** `python "{{root}}/aidw.py" context use <nome>`. Ele grava só a linha `active` do `aidw.config.toml`
   (os comentários ficam), roda o `apply` e, se o AiDW estiver instalado, o `install`: o plugin `aidw` (mesmo nome,
   mesmos comandos) passa a ter os agentes, sistemas e políticas do novo contexto, e as regras globais do contexto
   antigo saem, as do novo entram.
5. **Resultado:** diga o contexto ativo e que é preciso **abrir um chat novo** para
   valer. Em caso de erro, mostre a mensagem do comando; não tente contornar.
