# context list

1. Rode `python "{{root}}/aidw.py" context list` ({{root}} é a raiz do AiDW) — exatamente nessa forma, com as aspas: é a que as regras de permissão liberam sem pedir aprovação.
2. Mostre ao usuário, numa tabela curta: nome, descrição, se está **ativo** (`*`), repositório (git próprio,
   remoto só pelo host — nunca mostre URL completa), sistemas e plugin instalado.
3. Aponte o que merece atenção, se houver: contexto sem repositório git próprio, contexto sem remoto (o
   conteúdo só existe nesta máquina), erro no `context.toml`.
4. Termine com o próximo passo possível: `/aidw:context use <nome>` para trocar, `/aidw:context create` para um novo.

Não altere nada: esta skill só lê.
