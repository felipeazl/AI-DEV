---
name: contexto-criar
description: Cria um contexto de trabalho novo do AiDW (contexts/<nome>, repositório Git privado) a partir de uma análise criteriosa dos repositórios indicados e de no mínimo 10 perguntas ao usuário — sistemas, build e teste, convenções, políticas, aprovações e MCPs. Use quando o usuário pedir para criar ou montar um contexto.
aidw: admin
---

# contexto-criar

Um contexto é o pacote de regras de uma empresa ou squad: sistemas, comandos, convenções e políticas que o
orquestrador e os agentes seguem. Ele fica em `{{root}}/contexts/<nome>/`, num **repositório Git próprio e
privado**, ignorado pelo Git do AiDW. `aidw.py` está em `{{root}}`.

**Regras:** base tudo em arquivos e commits reais dos repositórios analisados — nunca invente exemplo nem copie
conteúdo de outro contexto (o contexto ativo só serve de exemplo de *estrutura*). Não leia `.env`, arquivos de
segredo nem connection strings; segredo entra no contexto só pelo **nome** da variável. Economia: o que o agente
usa sempre vai no prompt (`include`); o resto vira referência lida sob demanda (`reference` com `when`).

## 1. Escopo (antes de analisar)

Pergunte, numa pergunta só: nome do contexto (minúsculas, dígitos, hífen), descrição (empresa — squad) e **quais
repositórios** entram (caminhos locais). Confira que cada caminho existe e é um repositório Git
(`python "{{root}}/aidw.py" project detect --path <repo> --json`).

## 2. Análise criteriosa (só leitura)

Um subagente `Explore` por repositório, **em paralelo**, pedindo `arquivo:linha` e trechos curtos (não o
arquivo inteiro). Para cada repositório, levante com evidência:

1. **Stack e estrutura:** linguagens, frameworks e versões (csproj/package.json/pom…), solução e projetos,
   camadas (API/Application/Domain/Infrastructure…), front e back.
2. **Build e teste:** o comando real que compila e o que testa (scripts do package.json, `dotnet build/test`,
   MSBuild, pipelines `azure-pipelines*.yml`/`.github/workflows`), framework de teste e onde ficam os testes.
   Proponha a versão **com saída filtrada** (só erros e o resumo).
3. **Dependências de build fora do Git:** `packages/`, `node_modules/`, configs locais — vira `[worktree] link`.
4. **Convenções de código:** `.editorconfig`, analyzers, lint/prettier, `CLAUDE.md`/`AGENTS.md`/`CONTRIBUTING`/
   README do repositório, idioma do código, nomenclatura observada no código vizinho.
5. **Git e fluxo:** branch padrão e de desenvolvimento (`git branch -r`), padrão de nome das branches e das
   mensagens de commit (`git log --oneline -50`), onde vivem os PRs (Azure DevOps, GitHub…).
6. **Integração entre sistemas:** clientes HTTP/SOAP, pacotes compartilhados, filas, enums/contratos que um
   sistema consome do outro — vira `depends_on` e as notas de contrato.
7. **Configuração e ambientes:** appsettings por ambiente, serviço de configuração, nomes de variáveis (nunca
   valores), quais ambientes existem (dev, qa, hml, prod).
8. **Banco:** ORM/acesso a dados, pasta de scripts `.sql`, migrations, como o time versiona script.
9. **Riscos:** código legado frágil, UI thread, concorrência, dados pessoais (CPF, e-mail…) circulando.

Grave o resultado em `contexts/<nome>/reference/analise-inicial.md` (depois do passo 4) com as evidências.

## 3. Perguntas (no mínimo 10)

Faça **no mínimo 10 perguntas**, em blocos de até 4 (ferramenta de pergunta), cada uma com opções tiradas da
análise, a **recomendação** e o porquê. Pergunte mais sempre que a análise deixar dúvida real. Cubra pelo menos:

1. **Sistemas:** nome de cada sistema, repositórios de cada um e a descrição curta (confirme o que a análise achou).
2. **Build e teste:** confirme o comando filtrado de cada sistema; o que fazer quando não há teste automatizado.
3. **Branch e PR:** prefixo da branch (`feature/<id>-<slug>`?), base de desenvolvimento e alvo do PR.
4. **Gestão das demandas:** onde ficam (Azure DevOps, Jira, GitHub), org/projeto, tipos de item e o que o AiDW
   pode fazer sozinho no board (ler, criar tarefa, mudar estado, comentar).
5. **Ações travadas:** quais sempre pedem OK (commit, push, merge, SQL de escrita, chamadas que mudam dado,
   comentários) e quais rodam sozinhas.
6. **Ambientes:** em quais os agentes podem atuar (dev/qa), quais só com autorização, e produção (nunca?).
7. **Banco:** acesso só leitura por validador? Em quais ambientes? Como um script de banco entra na demanda?
8. **Padrão de código:** a fonte de verdade (repositório de guideline, documento, o próprio código) e o que o
   revisor deve bloquear.
9. **Segredos e dados pessoais:** o que nunca vai para arquivo, log ou card; regras de LGPD do time.
10. **MCPs:** quais o time precisa (board, design, navegador…) e quais variáveis de ambiente eles exigem.
11. **Quem decide:** Tech Lead, PO — e onde as decisões ficam registradas (comentários do card?).
12. **Repositório privado do contexto:** URL do remoto privado (ou ficar só local por enquanto).

## 4. Gerar o contexto

1. `python "{{root}}/aidw.py" context create <nome> --description "<descrição>" [--mcp a,b] [--env X,Y]` — cria a
   estrutura mínima e o `git init`.
2. Preencha, a partir da análise e das respostas:
   - `context.toml`: `[systems.<chave>]` (name, repos, stack, depends_on, build, test, notes), `[worktree]`,
     `[permissions]` (allow, git_ask, ask, deny — o mínimo que a rotina precisa), `required_env`, `required_mcp`
     e `[mcp.<nome>]` com o comando de registro, `[agents.<papel>]` com `include` e `reference`.
   - `policies/*.md`: uma por tema das respostas 4 a 9 (curtas, com a regra e o porquê).
   - `agents/orchestrator.md`: o fluxo do time (passos, quando parar para o usuário, o que vai no card) — sem
     repetir o núcleo do AiDW.
   - `agents/<papel>.md` e `shared/guia-*.md`: só o que cada papel usa sempre; o resto em `reference/` com `when`.
3. `python "{{root}}/aidw.py" context check <nome>` — corrija até não haver erro.

## 5. Entregar

Mostre ao usuário: o que foi criado (arquivos), os sistemas e comandos, as políticas, o que ficou como
referência e os avisos do `check`. Proponha, sem executar:
- ativar: skill `contexto-usar` (`context use <nome>`);
- commit no repositório do contexto e, se houver remoto privado, `git remote add origin <url>` e o push —
  **commit e push pedem OK**; confirme que o remoto é **privado** antes do push.
