# Configuração

Onde cada coisa se configura, o idioma e perfis prontos.

## As três camadas

| Camada | Onde | Versionado | Quem muda | O que define |
|---|---|---|---|---|
| **Núcleo** | este repositório | sim | quem mantém o AiDW | agentes, skills, fluxo, regras de `state`, exceções de effort, catálogos de modelos e MCPs, políticas genéricas |
| **Contexto** | `contexts/<nome>/` | sim, repositório do time | o time | sistemas, regras por agente, políticas, permissões, MCPs obrigatórios, prefixo de branch, o idioma do contexto ([contexts.md](contexts.md)) |
| **Máquina** | `aidw.config.toml` | **não** | você | provedor, pastas, contexto ativo, MCPs ligados, bloqueios extras, idioma da interface, nome, modelo, effort e status de cada agente |

Regra prática: o que é só seu vai no `aidw.config.toml`; o que o time inteiro deve seguir vai no contexto; o que vale
para qualquer time vai no núcleo.

Depois de mudar qualquer camada:

```powershell
python aidw.py install    # o plugin global do Claude (e o Codex, se você instalou)
python aidw.py apply      # o modo projeto (chat aberto na raiz do AiDW)
```

E abra um chat novo. Para refazer o arquivo pelo wizard: `python aidw.py configure` (reescreve o arquivo; comentários
próprios se perdem). `python aidw.py configure --defaults [--provider codex] [--language pt-BR]` grava a configuração
padrão sem perguntar.

## `aidw.config.toml` campo a campo

O modelo é o `aidw.config.example.toml`; o `setup` cria o seu pelo wizard.

### `[provider]`

```toml
[provider]
name = "claude"           # "claude" = tudo no Claude Code · "codex" = tudo no Codex CLI
```

`claude` é o padrão e o recomendado. Com `codex`, o AiDW é só agentes e skills ([claude-and-codex.md](claude-and-codex.md)).
O plugin do Claude e a instalação do Codex podem coexistir (`install --provider all`); depois disso, o `install` sem
`--provider` atualiza os dois.

### `[delegation]`

```toml
[delegation]
mode = "native"           # subagentes do provedor (recomendado) · "headless" = um processo por tarefa
```

O plugin (`install`) exige `native`. O `headless` roda cada agente com `aidw.py delegate` (`claude -p` ou `codex exec`),
só no modo projeto — útil para automação.

### `[workspace]` e `[worktree]`

```toml
[workspace]
project_dirs = ["C:/Repos", "C:/Legado"]   # os seus repositórios; liberados para o orquestrador e todos os agentes

[worktree]
root = "C:/wt"            # <root>/<demanda>/<repo>; curta e fora de qualquer repositório
```

A raiz padrão é `C:/wt` no Windows e `~/wt` nos outros sistemas. Um caminho curto evita o limite de 260 caracteres do
Windows em projetos .NET e Node.

### `[context]` e `[mcp]`

```toml
[context]
active = "meu-time"       # pasta em contexts/ ("" = nenhum). Troque com /aidw:context use <nome>

[mcp]
enabled = ["playwright", "chrome-devtools", "figma", "context7"]   # chaves do config/mcp.toml (este é o padrão)
```

Os MCPs que o contexto exige (`required_mcp`) são conferidos pelo `doctor` independentemente desta lista.

### `[ui]` — idioma

```toml
[ui]
language = "pt-BR"        # tag BCP-47: "en", "pt-BR", "es"... Padrão "en"
```

### Idioma

Duas configurações, uma herdando da outra:

| Configuração | Onde | Padrão | Controla |
|---|---|---|---|
| `[ui] language` | `aidw.config.toml` | `en` | o idioma em que o orquestrador fala com você, e a faixa e os painéis do `aidw-mods` (qualquer tag `pt*` mostra em português; o resto, em inglês) |
| `language` | no topo do `contexts/<nome>/context.toml` | o `[ui] language` | o conteúdo do contexto e dos artefatos da demanda (planos, relatórios, revisões, tarefas) |

- **Os nomes de arquivo são sempre em inglês** (`plan-<id>.md`, `metrics.md`…), qualquer que seja o idioma.
- O wizard pergunta o idioma da interface (passo 6, antes do contexto, para que um contexto criado ali herde);
  `python aidw.py context create <nome> --language <tag>` define o idioma de um contexto.
- `python aidw.py show` mostra os dois, por exemplo ``Language: UI Portuguese (Brazil) (`pt-BR`); demand artifacts Portuguese (Brazil) (`pt-BR`) (inherited from the UI)``.
- Depois de mudar qualquer um: `install` (e `apply`) e um chat novo.

### `[policies]`

```toml
[policies]
deny = ["Bash(git push --force *)", "Read(**/.env)"]   # bloqueado sempre
ask = ["Bash(npm publish *)"]                           # sempre pede OK (vence qualquer allow)
```

Somam às regras do contexto. A lista `deny` padrão bloqueia force push, `reset --hard`, `clean -f` e a leitura de
arquivos `.env`, no Bash e no PowerShell.

### `[agents.<papel>]`

```toml
[agents.reviewer]
name = "revisor"          # nome que aparece no chat (aceita acento e espaço); sem ele, o papel
enabled = true            # false = o orquestrador nunca delega a ele
model = "sonnet"          # chave do config/models.toml; sem ela, o tier padrão do papel
effort = "high"           # effort padrão; as exceções ficam em [effort.variants] do routing.toml
skills = ["code-review", "verify-premise"]
preload = ["code-review"]
```

| Papel | Tier padrão (modelo no Claude) | Effort padrão |
|---|---|---|
| `orchestrator` | `top` (Opus) — só recomendação: valem o modelo e o effort do chat | medium |
| `planner` | `mid` (Sonnet) | high |
| `explorer` | `fast` (Haiku) | low (ignorado pelo Haiku) |
| `coder` | `mid` (Sonnet) | high |
| `reviewer` | `mid` (Sonnet) | high |
| `qa` | `mid` (Sonnet) | medium |
| `documenter` | `fast` (Haiku) | medium (ignorado pelo Haiku) |

Vêm do `DEFAULT_AGENTS` do `aidw.py` e do `config/models.toml` ([agents.md](agents.md#onde-ficam-os-padrões)).

- Uma config sem um papel mais novo recebe o papel com o padrão; um papel que saiu (`api-db`, `bug-hunter`, `security`)
  é ignorado com aviso.
- Os nomes antigos das skills do núcleo (`verificar-premissa`, `preparar-worktree`) continuam aceitos e viram os novos.
- Nomes que colidem com agentes do CLI (`plan`, `explore`, `default`…) são recusados.

## Perfis

### Padrão

O que o wizard grava. Nada a mudar: o padrão de cada agente e as exceções já equilibram custo e qualidade.

### Economizar a sessão (plano menor)

```toml
[agents.coder]
effort = "medium"

[agents.reviewer]
effort = "medium"
```

E no dia a dia: "essa correção é pequena, use o coder medium". O `metrics.md` e o `orchestrator-metrics.md` mostram
onde o consumo está — em geral no chat do orquestrador; um modelo mais barato no chat é a maior economia.

### Só Codex

```toml
[provider]
name = "codex"
```

```powershell
python aidw.py install --provider codex              # agentes e skills aidw-*
python aidw.py open --provider codex --demand 1234   # liga o multi_agent_v2 (o spawn_agent precisa dele)
```

Só agentes e skills: sem regras de permissão, hooks, guard, perfil, MCP por agente, painel de diff, pastas da sessão nem
mods ([claude-and-codex.md](claude-and-codex.md)).

### Front-end

```toml
[mcp]
enabled = ["playwright", "chrome-devtools", "figma", "context7"]
```

O Figma precisa de autenticação uma vez (Claude: `/mcp` → figma → Authenticate; Codex: `codex mcp login figma`).

### Nomes e idioma próprios

```toml
[ui]
language = "pt-BR"

[agents.coder]
name = "Dev"

[agents.reviewer]
name = "Revisor de Código"
```

Os textos do contexto usam `{{agent:<papel>}}` e acompanham o nome novo.

## Os arquivos de configuração do núcleo

Mudanças aqui valem para todos que usam o AiDW: faça por PR.

| Arquivo | O que define |
|---|---|
| `config/models.toml` | Catálogo de modelos por provedor: `model_id` (no Claude, o apelido), `label`, `tiers` (`top`/`mid`/`fast`), `efforts` aceitos, `min_cli`, `alias` |
| `orchestrator/config/routing.toml` | `[rules]` (`state` → ação) e `[[effort.variants.<papel>]]` (as exceções: `effort`, `model` opcional, `when`) |
| `config/mcp.toml` | Catálogo de MCPs: comando ou URL, `auth`, `allow`, os papéis que podem usar (`agents`), `use_when` e `triggers` |
| `orchestrator/ORCHESTRATOR.md` · `orchestrator/SURVEY.md` | O núcleo do orquestrador e o orquestrador enxuto do levantamento |
| `orchestrator/reference/` | O que o orquestrador lê sob demanda (`short-path`, `testing`, `pr-review`, `pr-triage`, `survey`) |
| `orchestrator/policies/` | Políticas genéricas: git, banco, produção, segredos, permissões |
| `agents/`, `skills/`, `workflows/` | Agentes, skills e workflows |

## O que fica fora do AiDW

O `install` acrescenta ao `~/.claude/settings.json` só os itens do AiDW (regras de permissão, pastas liberadas,
variáveis de ambiente) e remove só o que ele mesmo gravou. Ele **não** grava `model` nem `effortLevel`: o modelo do chat
é o que você escolhe. O seu `~/.claude/CLAUDE.md` e as suas configurações pessoais do CLI continuam seus.
