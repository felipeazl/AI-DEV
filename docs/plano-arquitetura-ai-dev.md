# Arquitetura de Desenvolvimento Multi-Agente com IA

## Objetivo

Evoluir o workflow atual, baseado em conversas separadas no Claude e arquivos `CLAUDE.md`, para uma arquitetura definitiva de desenvolvimento multi-agente, mantendo o que já funciona e adicionando:

- Orquestração automática;
- múltiplos modelos especializados;
- Skills reutilizáveis;
- especificações e tickets como fonte de verdade;
- revisão automática;
- QA/testes;
- agente especializado em API/DB;
- documentação;
- camada de decisão com JEV;
- interface visual para acompanhar e controlar os agentes;
- observabilidade, logs e métricas;
- possibilidade de intervenção humana em pontos críticos.

---

# 1. Arquitetura proposta

```text
                           ┌─────────────────────────┐
                           │        VOCÊ / UI        │
                           │                         │
                           │  Agent Canvas / Web UI  │
                           └────────────┬────────────┘
                                        │
                                        ▼
                    ┌────────────────────────────────────┐
                    │          ORCHESTRATOR              │
                    │                                    │
                    │      Claude Opus 5.5 High         │
                    │                                    │
                    │  • entende objetivo                │
                    │  • planeja                         │
                    │  • cria especificação              │
                    │  • delega                          │
                    │  • acompanha execução              │
                    │  • decide quando terminar          │
                    └─────────────────┬──────────────────┘
                                      │
                                      ▼
                           ┌────────────────────┐
                           │    JEV / ROUTER    │
                           │                    │
                           │  Decision Engine   │
                           └─────────┬──────────┘
                                     │
             ┌───────────────────────┼───────────────────────┐
             │                       │                       │
             ▼                       ▼                       ▼
       ┌────────────┐         ┌────────────┐         ┌────────────┐
       │   PLANNER  │         │   CODER    │         │  REVIEWER  │
       │            │         │            │         │            │
       │ Opus High  │         │ Opus Medium│         │ GPT Sol    │
       └─────┬──────┘         └──────┬─────┘         └─────┬──────┘
             │                       │                     │
             ▼                       ▼                     ▼
          to-spec              implement-ticket       code-review
             │                       │                     │
             ▼                       │                     │
        to-tickets                    │                     │
             │                        │                     │
             └────────────┬───────────┘                     │
                          │                                 │
                          ▼                                 │
                  ┌───────────────┐                         │
                  │   TEST / QA   │◄────────────────────────┘
                  │               │
                  │   GPT Luna    │
                  └───────┬───────┘
                          │
                          ▼
                    ┌───────────┐
                    │   JEV     │
                    │ DECISION  │
                    └─────┬─────┘
                          │
                ┌─────────┴─────────┐
                │                   │
                ▼                   ▼
             CORRIGIR              OK
                │                   │
                ▼                   ▼
              CODER               DOCS
                                  │
                                  ▼
                              GPT Luna
```

---

# 2. Princípio central: separar Agent, Model, Skill, Tool e Policy

O sistema deve evitar colocar toda a lógica dentro dos `CLAUDE.md`.

## Agent

Representa o papel:

- Orchestrator
- Coder
- Reviewer
- API/DB Agent
- QA
- Documenter

## Model

Representa o modelo usado pelo agente:

- Claude Opus 5.5 High
- Claude Opus 5.5 Medium
- GPT Sol
- GPT Luna
- JEV

O modelo pode mudar sem mudar necessariamente o papel do agente.

## Skill

Representa um procedimento reutilizável:

- `to-spec`
- `to-tickets`
- `implement-ticket`
- `code-review`
- `debug`
- `testing`
- `documentation`

## Tool

Representa aquilo que o agente pode acessar:

- filesystem
- terminal
- Git
- GitHub
- Azure DevOps
- banco de dados
- APIs
- browser
- MCP

## Policy

Representa regras que não devem depender de decisão do LLM:

- não apagar produção;
- não alterar secrets;
- não executar migration destrutiva sem aprovação;
- não fazer merge sem review;
- não fazer push para determinadas branches;
- exigir aprovação humana para operações críticas.

---

# 3. Estrutura de diretórios proposta

```text
AI-DEV/
│
├── orchestrator/
│   ├── CLAUDE.md
│   ├── prompts/
│   ├── policies/
│   └── config/
│
├── agents/
│   │
│   ├── coder/
│   │   ├── CLAUDE.md
│   │   ├── skills/
│   │   └── config/
│   │
│   ├── reviewer/
│   │   ├── CLAUDE.md
│   │   └── skills/
│   │
│   ├── api-db/
│   │   ├── CLAUDE.md
│   │   └── skills/
│   │
│   ├── qa/
│   │   ├── CLAUDE.md
│   │   └── skills/
│   │
│   └── documenter/
│       ├── CLAUDE.md
│       └── skills/
│
├── skills/
│   ├── to-spec/
│   ├── to-tickets/
│   ├── implement-ticket/
│   ├── code-review/
│   ├── debug/
│   ├── testing/
│   └── documentation/
│
├── workflows/
│   ├── feature.yaml
│   ├── bugfix.yaml
│   ├── refactor.yaml
│   └── hotfix.yaml
│
└── state/
    ├── specs/
    ├── tickets/
    ├── reviews/
    └── runs/
```

A estrutura de agentes deve ficar separada dos projetos para permitir reutilização.

Exemplo:

```text
~/AI-DEV/
~/projects/projeto-a/
~/projects/projeto-b/
```

---

# 4. Orchestrator

O Orchestrator será o principal agente de raciocínio e coordenação.

## Modelo

**Claude Opus 5.5 High**

## Responsabilidades

1. Entender o pedido.
2. Inspecionar o repositório.
3. Determinar escopo.
4. Criar ou atualizar a especificação.
5. Quebrar a especificação em tickets.
6. Delegar tickets.
7. Avaliar resultados.
8. Solicitar revisão.
9. Tratar falhas.
10. Decidir quando a tarefa está concluída.

O Orchestrator não deve implementar código diretamente, salvo quando explicitamente necessário.

## Exemplo conceitual do `CLAUDE.md`

```text
# ROLE

You are the Lead Software Architect and Orchestrator.

You do NOT implement code unless explicitly instructed.

Your responsibilities:

1. Understand the request.
2. Inspect the repository.
3. Determine scope.
4. Create or update the specification.
5. Break the specification into tickets.
6. Delegate tickets.
7. Evaluate agent results.
8. Request review.
9. Handle failures.
10. Decide when the task is complete.

# AGENTS

Coder:
    Claude Opus 5.5 Medium

Reviewer:
    GPT-5.6 Sol

API/DB:
    GPT-5.6 Luna

QA:
    GPT-5.6 Luna

Documentation:
    GPT-5.6 Luna

# WORKFLOW

Request
→ Understand
→ Spec
→ Tickets
→ Implementation
→ Tests
→ Review
→ Fix
→ Final validation
→ Documentation
→ Complete

# RULES

Never assume implementation details.

Never bypass review for non-trivial changes.

Never execute destructive database operations without explicit authorization.
```

O `CLAUDE.md` deve ser relativamente pequeno. Conhecimento procedural deve ficar nas Skills e regras críticas devem ficar em Policies.

---

# 5. Skill `to-spec`

A primeira etapa importante deve transformar um pedido em uma especificação persistente.

Exemplo:

```text
Pedido:
"Adicionar reconnect automático ao WebSocket"

        ↓

to-spec

        ↓

specs/websocket-reconnect.md
```

A especificação pode conter:

```markdown
# WebSocket Reconnect

## Objective

...

## Current behavior

...

## Desired behavior

...

## Constraints

...

## Acceptance criteria

- ...
- ...
- ...

## Out of scope

...

## Technical considerations

...
```

A especificação deve ser a fonte de verdade da tarefa.

---

# 6. Skill `to-tickets`

Depois da especificação:

```text
SPEC
 ↓
to-tickets
```

Resultado:

```text
tickets/
├── WS-001-client-reconnect.md
├── WS-002-backoff.md
├── WS-003-connection-state.md
├── WS-004-tests.md
└── WS-005-documentation.md
```

Cada ticket deve ser pequeno o suficiente para um agente executar sem precisar conhecer toda a conversa original.

---

# 7. Uso do JEV

O JEV não deve ser tratado simplesmente como outro agente.

Ele deve funcionar como uma **camada de decisão**.

## Modelo conceitual

```text
Opus High
   │
   │ planejamento complexo
   ▼
JEV
   │
   │ decisão rápida
   ├── escolher agente
   ├── escolher modelo
   ├── retry
   ├── continuar
   ├── revisar
   ├── finalizar
   └── pedir intervenção humana
```

O JEV deve receber estado estruturado, e não uma conversa inteira.

Exemplo:

```json
{
  "task": "WS-002",
  "status": "implementation_complete",
  "tests": {
    "passed": true
  },
  "review": {
    "status": "not_started"
  },
  "changed_files": 4,
  "risk": "medium"
}
```

Possíveis decisões:

```text
REVIEW
TEST
CODER_FIX
DONE
HUMAN_APPROVAL
```

O software de orquestração executa a decisão.

## Regra importante

O JEV não deve ter acesso irrestrito ao computador.

A arquitetura deve ser:

```text
JEV
 ↓
decisão estruturada
 ↓
application code
 ↓
validação de policy
 ↓
execução
```

O LLM decide; o software controla a execução e as permissões.

---

# 8. Coder

## Modelo

**Claude Opus 5.5 Medium**

## Responsabilidades

- implementar;
- alterar arquivos;
- refatorar;
- criar testes;
- executar build;
- corrigir erros;
- executar lint;
- executar typecheck.

O Coder deve receber:

```text
SPEC
+
TICKET
+
RELEVANT CONTEXT
+
PROJECT RULES
+
TOOLS
```

Não deve receber automaticamente toda a conversa do Orchestrator.

## Resultado estruturado

```json
{
  "status": "completed",
  "files_changed": [
    "src/WebSocketClient.ts"
  ],
  "tests": [
    "websocket-reconnect.spec.ts"
  ],
  "validation": {
    "typecheck": "passed",
    "tests": "passed",
    "lint": "passed"
  }
}
```

---

# 9. Reviewer

## Modelo

**GPT-5.6 Sol**

O Reviewer recebe:

```text
SPEC
+
TICKET
+
DIFF
+
TEST RESULTS
```

Em vez de simplesmente receber uma pergunta genérica como "revise o código".

## Resultado

```json
{
  "status": "changes_requested",
  "issues": [
    {
      "severity": "high",
      "file": "...",
      "line": 142,
      "problem": "...",
      "recommendation": "..."
    }
  ]
}
```

Fluxo:

```text
Reviewer
   │
   ├── APPROVED
   │
   └── CHANGES REQUESTED
            ↓
          Coder
```

---

# 10. QA separado do Reviewer

Reviewer e QA devem ter responsabilidades diferentes.

## Reviewer

Pergunta:

> O código está correto, sustentável e aderente à especificação?

## QA

Pergunta:

> O software funciona?

Fluxo:

```text
Coder
 ↓
Tests
 ↓
Reviewer
 ↓
Fix
 ↓
Tests
 ↓
Reviewer
```

O QA pode usar GPT Luna por ser uma tarefa mais determinística e de menor complexidade.

---

# 11. API/DB Agent

## Modelo

**GPT-5.6 Luna**

Responsabilidades:

- consultar schema;
- trabalhar com migrations;
- criar queries;
- analisar APIs;
- consultar logs;
- validar integrações.

Esse agente deve ter permissões próprias e diferentes do Coder.

## Segurança

Nunca deixar um LLM ser a última barreira de segurança.

Fluxo:

```text
LLM
 ↓
SQL
 ↓
Parser / Validator
 ↓
Permission Check
 ↓
Human Approval (quando necessário)
 ↓
Database
```

Exemplo de operações que podem exigir aprovação:

- `DROP`;
- `TRUNCATE`;
- migrations destrutivas;
- alterações em produção;
- updates massivos;
- alterações de permissões.

---

# 12. Documenter

## Modelo

**GPT-5.6 Luna**

Responsabilidades:

- README;
- documentação de API;
- changelog;
- documentação arquitetural;
- JSDoc;
- OpenAPI;
- documentação de alterações.

A documentação deve ser gerada depois da implementação, QA e review.

Fluxo:

```text
Implementation
 ↓
QA
 ↓
Review
 ↓
Approved
 ↓
Documentation
```

Assim a documentação representa o código realmente implementado.

---

# 13. Skills recomendadas

Além de `to-spec` e `to-tickets`, criar:

## `codebase-context`

Responsável por reunir:

- arquitetura;
- stack;
- convenções;
- aliases;
- padrões;
- dependências;
- restrições.

## `implement-ticket`

Fluxo:

```text
entender
↓
planejar
↓
implementar
↓
testar
↓
lint
↓
typecheck
↓
diff
```

## `review-code`

Entrada:

```text
SPEC
+
TICKET
+
DIFF
+
TEST RESULTS
```

## `debug-failure`

Fluxo:

```text
erro
 ↓
JEV
 ↓
retry coder / reviewer / human
```

## `database-safe`

Responsável por aplicar políticas antes de executar operações de banco.

## `testing`

Padronizar execução de:

- unit tests;
- integration tests;
- lint;
- typecheck;
- build;
- testes específicos.

## `documentation`

Padronizar geração e atualização de documentação.

---

# 14. Interface

A interface deve funcionar como painel de controle e observabilidade.

Exemplo:

```text
╔════════════════════════════════════════════╗
║             FEATURE #124                   ║
╠════════════════════════════════════════════╣
║                                            ║
║ ● Specification              ✓             ║
║                                            ║
║ ● Tickets                    ✓             ║
║                                            ║
║ ● WS-001                     ✓             ║
║                                            ║
║ ● WS-002                     ███████ 78%   ║
║      └─ Coder               running        ║
║                                            ║
║ ● WS-003                     waiting       ║
║                                            ║
║ ● Review                     waiting       ║
║                                            ║
╠════════════════════════════════════════════╣
║ Model usage                                ║
║ Opus High       42k tokens                 ║
║ Opus Medium     81k tokens                 ║
║ GPT Sol         21k tokens                 ║
║ GPT Luna        17k tokens                 ║
║ JEV              3k decisions              ║
╚════════════════════════════════════════════╝
```

Controles importantes:

- pause;
- resume;
- approve;
- reject;
- retry;
- cancelar;
- visualizar diff;
- visualizar logs;
- visualizar decisões;
- assumir controle manualmente.

OpenHands / Agent Canvas pode ser avaliado como a interface dessa camada.

---

# 15. Fluxo completo

Uma feature deve seguir aproximadamente:

```text
VOCÊ
 │
 │ "Implementar reconnect do WebSocket"
 ▼
ORCHESTRATOR
 │
 ├── inspect repo
 │
 ▼
to-spec
 │
 ▼
SPEC
 │
 ▼
to-tickets
 │
 ▼
┌──────────────────────────────┐
│ WS-001 │ WS-002 │ WS-003 │  │
└───┬────────┬────────┬───────┘
    │        │        │
    ▼        ▼        ▼
  CODER    CODER    CODER
    │        │        │
    └────────┼────────┘
             ▼
            QA
             │
             ▼
           JEV
             │
             ▼
          REVIEW
             │
       ┌─────┴─────┐
       ▼           ▼
    APPROVE      REJECT
       │           │
       │           ▼
       │         CODER
       │           │
       │           └───────┐
       │                   │
       └───────────────────┘
               │
               ▼
          DOCUMENTATION
               │
               ▼
              DONE
```

---

# 16. Observabilidade

Cada execução deve gerar estado persistente.

Exemplo:

```text
state/
└── runs/
    └── 2026-09-24-001/
        ├── task.json
        ├── decisions.json
        ├── spec.md
        ├── tickets/
        ├── agent-results/
        ├── reviews/
        └── metrics.json
```

Registrar:

- modelo usado;
- tokens;
- custo;
- duração;
- agente;
- ticket;
- número de retries;
- testes;
- resultado de review;
- decisões do JEV;
- intervenção humana;
- arquivos alterados.

Isso permitirá descobrir:

- qual agente falha mais;
- qual modelo custa mais;
- quais tarefas precisam de modelos caros;
- quais tarefas podem usar Luna;
- quantos retries são necessários;
- onde o workflow fica lento.

---

# 17. Políticas de segurança

Criar uma camada explícita de policies.

Exemplo:

```text
policies/
├── git.md
├── database.md
├── secrets.md
├── production.md
└── permissions.md
```

## Git

Exemplos:

- não fazer force push;
- não apagar branches protegidas;
- não fazer merge sem aprovação;
- não alterar histórico sem autorização.

## Database

Exemplos:

- produção é somente leitura por padrão;
- operações destrutivas exigem aprovação;
- migration deve ser validada;
- SQL gerado por LLM passa por validator.

## Secrets

- nunca imprimir secrets;
- nunca enviar `.env` ao modelo;
- nunca incluir credenciais em commits.

---

# 18. Fases de implementação

Não implementar tudo de uma vez.

## Fase 1 — Organizar o sistema atual

Não mudar modelos nem ferramentas inicialmente.

Organizar:

```text
CLAUDE.md
↓
Agents
↓
Skills
↓
Specs
↓
Tickets
```

Implementar primeiro:

- `to-spec`;
- `to-tickets`;
- `implement-ticket`;
- `code-review`.

---

## Fase 2 — Comunicação estruturada

Fazer todos os agentes retornarem resultados estruturados.

Exemplo:

```text
status
files
tests
errors
next_action
```

Isso permite automatização.

---

## Fase 3 — Automatizar Orchestrator

O Orchestrator passa a:

```text
criar spec
↓
criar tickets
↓
chamar agentes
↓
interpretar resultados
```

Objetivo: reduzir a necessidade de abrir manualmente cada conversa.

---

## Fase 4 — Introduzir JEV

Primeiro fazer o workflow funcionar com decisões determinísticas:

```text
if review_failed
    → coder
```

Depois substituir decisões simples por JEV:

```text
JEV
→ next_action
```

Assim é possível medir se o JEV realmente melhora o sistema.

---

## Fase 5 — Interface

Adicionar OpenHands / Agent Canvas ou interface própria para:

- acompanhar tarefas;
- visualizar agentes;
- controlar execução;
- visualizar logs;
- aprovar operações;
- pausar;
- retomar;
- cancelar;
- fazer retry.

---

## Fase 6 — Observabilidade

Adicionar:

- logs;
- métricas;
- custos;
- tokens;
- tempo;
- retries;
- taxa de aprovação;
- taxa de falhas.

---

# 19. Evolução do workflow atual

O workflow atual é um excelente MVP do sistema futuro.

Hoje:

```text
VOCÊ
 ↓
abre Claude
 ↓
Orchestrator
 ↓
abre Codificador
 ↓
abre Revisor
 ↓
volta ao Orchestrator
```

Objetivo:

```text
VOCÊ
 ↓
ORCHESTRATOR
 ↓
to-spec
 ↓
to-tickets
 ↓
JEV
 ↓
AGENTS
 ↓
QA
 ↓
REVIEW
 ↓
JEV
 ↓
DOCUMENTATION
 ↓
DONE
```

A ideia não é jogar fora o sistema atual.

É transformar o processo manual que já funciona em uma infraestrutura automatizada.

---

# 20. Arquitetura final resumida

```text
                     ┌─────────────────────┐
                     │        USER         │
                     └──────────┬──────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │        UI           │
                     │  Agent Canvas/Web   │
                     └──────────┬──────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │    ORCHESTRATOR     │
                     │   Claude Opus H     │
                     └──────────┬──────────┘
                                │
                         Planning Layer
                                │
                         ┌──────▼──────┐
                         │   to-spec   │
                         └──────┬──────┘
                                │
                         ┌──────▼──────┐
                         │ to-tickets  │
                         └──────┬──────┘
                                │
                                ▼
                         ┌─────────────┐
                         │     JEV     │
                         │ Decision    │
                         └──────┬──────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
          ▼                     ▼                     ▼
       CODER                 API/DB                 QA
     Opus Medium              Luna                  Luna
          │                     │                     │
          └─────────────────────┼─────────────────────┘
                                │
                                ▼
                            REVIEWER
                            GPT Sol
                                │
                         ┌──────┴──────┐
                         │             │
                         ▼             ▼
                       FIX           APPROVED
                         │             │
                         ▼             ▼
                       CODER        DOCS
                                      │
                                      ▼
                                     DONE
```

---

# 21. Princípios que devem guiar a implementação

1. **Não substituir o workflow atual antes de entender o que funciona nele.**
2. **Não colocar todo o conhecimento dentro dos `CLAUDE.md`.**
3. **Usar Skills para procedimentos reutilizáveis.**
4. **Usar Specs como fonte de verdade.**
5. **Usar Tickets como unidades de execução.**
6. **Usar modelos caros para raciocínio que realmente exige capacidade.**
7. **Usar modelos baratos para tarefas determinísticas.**
8. **Usar JEV para decisões rápidas e repetitivas, não como cérebro principal.**
9. **Nunca permitir que um LLM seja a única camada de segurança.**
10. **Separar execução de decisão.**
11. **Manter intervenção humana para operações críticas.**
12. **Registrar todas as decisões importantes.**
13. **Começar manual/híbrido e automatizar progressivamente.**
14. **Medir antes de substituir um modelo ou agente.**
15. **Preservar o workflow atual como fallback durante a migração.**

---

# 22. Próxima etapa: adaptar ao setup existente

Antes de implementar essa arquitetura, coletar o setup atual:

1. `CLAUDE.md` do Orchestrator;
2. `CLAUDE.md` do Coder;
3. `CLAUDE.md` do Reviewer;
4. estrutura das pastas;
5. prompts/comandos usados para passar tarefas entre agentes;
6. como Claude Code e o aplicativo Claude são utilizados;
7. onde o código está hospedado;
8. projeto/repositório escolhido para o primeiro teste.

Depois disso, criar uma **versão 2 específica do sistema existente**, classificando:

```text
SEU ATUAL
   ↓
┌───────────────────────────────────┐
│ MANTER                            │
│ MODIFICAR                         │
│ REMOVER                           │
│ AUTOMATIZAR                       │
│ TRANSFORMAR EM SKILL              │
│ TRANSFORMAR EM POLICY             │
│ TRANSFORMAR EM AGENT              │
└───────────────────────────────────┘
   ↓
ARQUITETURA DEFINITIVA
```

A prioridade deve ser evoluir o que já funciona, e não reconstruir tudo do zero.
