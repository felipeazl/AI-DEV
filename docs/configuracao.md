# Configuração e perfis de usuário

Cada pessoa usa o AiDW de um jeito: um provedor ou outro, um plano de assinatura maior ou menor, back-end ou front-end,
mais ou menos controle. Este documento mostra onde cada coisa se configura e traz perfis prontos.

## As três camadas

| Camada | Onde | Versionado | Quem muda | O que define |
|---|---|---|---|---|
| **Núcleo** | repositório do AiDW | sim | quem mantém o AiDW | agentes, skills, fluxo, regras de `state`, tabela de níveis, catálogos de modelos e MCPs, políticas genéricas |
| **Contexto** | `contexts/<nome>/` | sim, repositório do time | o time | sistemas, regras por agente, políticas, permissões, MCPs obrigatórios, prefixo de branch ([contextos.md](contextos.md)) |
| **Máquina** | `aidw.config.toml` | **não** | você | provedor, pastas, contexto ativo, MCPs ligados, bloqueios extras, nome, modelo, effort e status de cada agente |

A regra prática: **o que é só seu vai no `aidw.config.toml`; o que o time inteiro deve seguir vai no contexto; o que
vale para qualquer time vai no núcleo**, por PR no AiDW.

Depois de mudar qualquer camada:

```powershell
python aidw.py apply      # modo projeto (chat na raiz do AiDW)
python aidw.py install    # plugin global do Claude (e --provider codex, se usa o Codex)
```

E abra um chat novo. Para refazer o arquivo pelo wizard: `python aidw.py configure` (reescreve o arquivo; comentários
próprios se perdem).

## `aidw.config.toml` campo a campo

O modelo é o `aidw.config.example.toml`. O `setup` cria o seu pelo wizard.

### `[provider]`

```toml
[provider]
name = "claude"           # "claude" = tudo no Claude Code · "codex" = tudo no Codex CLI
```

Um provedor por instalação no modo projeto. O plugin do Claude e a instalação do Codex podem coexistir
(`install --provider all`).

### `[delegation]`

```toml
[delegation]
mode = "native"           # subagentes do provedor (recomendado) · "headless" = um processo por tarefa
```

O plugin exige `native`. O `headless` roda cada agente com `aidw.py delegate` (`claude -p` ou `codex exec`), útil para
automação ([claude-e-codex.md](claude-e-codex.md#modo-headless)).

### `[workspace]` e `[worktree]`

```toml
[workspace]
project_dirs = ["C:/Projetos", "C:/Legado"]   # onde ficam os seus repositórios; liberadas para todos os agentes

[worktree]
root = "C:/wt"            # raiz das pastas das demandas: <root>/<demanda>/<repo>. Curta e fora de qualquer repositório
```

Um caminho curto evita o limite de 260 caracteres do Windows em projetos .NET e Node.

### `[context]` e `[mcp]`

```toml
[context]
active = "meu-time"       # pasta em contexts/ ("" = nenhum). Troque com /aidw:contexto-usar

[mcp]
enabled = ["playwright", "chrome-devtools", "figma", "context7"]   # do catálogo config/mcp.toml
```

Os MCPs que o contexto exige (`required_mcp`) são conferidos pelo `doctor` independentemente desta lista.

### `[policies]`

```toml
[policies]
deny = ["Bash(git push --force *)", "Read(**/.env)"]   # bloqueado sempre
ask = ["Bash(npm publish *)"]                           # sempre pede OK (vence qualquer allow)
```

Somam às regras do contexto. Use para um bloqueio que vale só na sua máquina.

### `[agents.<papel>]`

```toml
[agents.reviewer]
name = "revisor"          # nome que aparece no chat (aceita acento e espaço); sem ele, o padrão
enabled = true            # false = o orquestrador nunca delega a ele
model = "opus"            # chave de config/models.toml do provedor; sem ele, o tier padrão do papel
effort = "medium"         # effort padrão; o orquestrador escolhe o de cada tarefa pela tabela de níveis
skills = ["code-review", "verificar-premissa"]
preload = ["code-review"]
```

| Papel | Nome padrão | Tier padrão |
|---|---|---|
| `orchestrator` | orquestrador | o modelo do chat |
| `planner` | planejador | top |
| `explorer` | explorador | fast |
| `coder` | codificador | top |
| `reviewer` | revisor | top |
| `api-db` | api | mid |
| `documenter` | documentador | fast |
| `bug-hunter` | bugs | mid |
| `security` | seguranca | mid |
| `qa` | qa | mid |

- **`model` troca o modelo base do papel.** Os níveis em que a tabela de `routing.toml` dá outro modelo ao papel
  (ex.: Sonnet no codificador em trivial e simples) continuam com o da tabela.
- Um modelo de outro provedor é ignorado com aviso.
- Uma config antiga, sem os agentes mais novos, recebe os novos com o padrão.
- Nomes que colidem com agentes do CLI (`plan`, `explore`, `default`…) são recusados.

## Perfis de exemplo

### Padrão (Claude, plano da empresa)

O que o wizard gera. Nada a mudar: a tabela de níveis já equilibra custo e qualidade.

### Economizar a sessão (plano menor)

```toml
[agents.coder]
model = "sonnet"          # Sonnet no lugar de Opus onde a tabela não indica outro
effort = "medium"

[agents.planner]
model = "sonnet"

[agents.bug-hunter]
enabled = false           # sem passadas extras automáticas; peça quando quiser

[agents.security]
enabled = false
```

E no dia a dia: "esse ticket é simples, use effort low". O `metricas.md` mostra onde o consumo está.

### Só Codex

```toml
[provider]
name = "codex"
```

```powershell
python aidw.py install --provider codex
codex --profile aidw      # uma vez: "Trust all and continue" para aprovar os hooks
```

A tabela de níveis vale pelo tier equivalente de cada modelo, entre os liberados para a conta
([agentes.md](agentes.md#equivalência-no-codex)).

### Front-end

```toml
[mcp]
enabled = ["playwright", "chrome-devtools", "figma", "context7"]

[agents.qa]
enabled = true            # testes de ponta a ponta com o Playwright
```

O Figma precisa de autenticação uma vez (Claude: `/mcp` → figma → Authenticate; Codex: `codex mcp login figma`).

### Mais controle

Não é configuração: chame `/aidw:orquestrar <demanda> interativo`. O orquestrador para antes dos tickets e antes de
cada delegação.

### Nomes próprios

```toml
[agents.coder]
name = "Dev"

[agents.reviewer]
name = "Zé Revisor"
```

Os textos do contexto usam `{{agent:<papel>}}` e acompanham o nome novo.

## Os outros arquivos de configuração (núcleo)

Mudanças aqui valem para todos que usam o AiDW: faça por PR.

| Arquivo | O que define |
|---|---|
| `config/models.toml` | Catálogo de modelos por provedor: `model_id` (no Claude, o apelido que sempre aponta para a versão mais nova), `label` (como aparece), `tiers` (`top`/`mid`/`fast`), `efforts` aceitos, `min_cli` |
| `orchestrator/config/routing.toml` | `[rules]` (`state` → ação), `max_retries`, `[effort] default_level`, `[effort.levels.<nível>]` (effort por papel, `"none"` = não roda) e `.models` (modelo por papel no nível), `[effort.escalate]` |
| `config/mcp.toml` | Catálogo de MCPs: comando ou URL, `auth`, `allow`, os papéis que podem usar (`agents`), `use_when` e `triggers` (quando o orquestrador manda usar) |
| `orchestrator/ORCHESTRATOR.md` | O núcleo do orquestrador |
| `orchestrator/reference/` | O que o orquestrador lê sob demanda (com `when:`) |
| `orchestrator/policies/` | Políticas genéricas: git, banco, produção, segredos, permissões |
| `agents/`, `skills/`, `workflows/` | Agentes, skills e fluxos por tipo de demanda |

### Mudar a tabela de níveis

```toml
[effort.levels.padrao]
coder = "medium"
reviewer = "medium"

[effort.levels.complexa]
coder = "high"

[effort.levels.complexa.models]
bug-hunter = "opus"       # chave do Claude; no Codex vale o equivalente pelo tier
```

Os testes (`python -m unittest discover -s tests`) conferem a tabela inteira; atualize o teste junto.

## O que fica fora do AiDW

O AiDW acrescenta ao `~/.claude/settings.json` só os itens dele (regras de permissão, pastas, variáveis) e remove só
o que ele mesmo gravou. Ele **não** grava `model` nem `effortLevel`: o modelo do chat é o que você escolhe no app. O
seu `~/.claude/CLAUDE.md` e as suas configurações pessoais do CLI continuam seus.
