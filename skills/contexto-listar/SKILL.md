---
name: contexto-listar
description: Lista os contextos de trabalho do AiDW (contexts/<nome>) — descrição, qual está ativo, repositório Git privado, sistemas e se o plugin está instalado. Use quando o usuário pedir para ver, listar ou conferir os contextos.
aidw: admin
---

# contexto-listar

1. Rode `python "{{root}}/aidw.py" context list` ({{root}} é a raiz do AiDW) — exatamente nessa forma, com as aspas: é a que as regras de permissão liberam sem pedir aprovação.
2. Mostre ao usuário, numa tabela curta: nome, descrição, se está **ativo** (`*`), repositório (git próprio,
   remoto só pelo host — nunca mostre URL completa), sistemas e plugin instalado.
3. Aponte o que merece atenção, se houver: contexto sem repositório git próprio, contexto sem remoto (o
   conteúdo só existe nesta máquina), erro no `context.toml`.
4. Termine com o próximo passo possível: `contexto-usar` para trocar, `contexto-criar` para um novo.

Não altere nada: esta skill só lê.
