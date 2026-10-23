# Configuração e perfis de usuário

Cada pessoa usa o AiDW de um jeito: Claude Code (a plataforma principal) ou Codex (limitado a agentes e skills), um plano de assinatura maior ou menor, back-end ou front-end,
mais ou menos controle. Este documento mostra onde cada coisa se configura e traz perfis prontos.

## As três camadas

| Camada | Onde | Versionado | Quem muda | O que define |
|---|---|---|---|---|
| **Núcleo** | repositório do AiDW | sim | quem mantém o AiDW | agentes, skills, fluxo, regras de `state`, exceções de effort, catálogos de modelos e MCPs, políticas genéricas |
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

O padrão e o recomendado é `claude`. **Com `codex`, o AiDW é só agentes e skills:** o `install --provider codex` não
instala regras, hooks, perfil nem mods, e o que é exclusivo do Claude Code fica de fora
([claude-e-codex.md](claude-e-codex.md#o-que-é-exclusivo-do-claude-code)).

Um provedor por instalação no modo projeto. O plugin do Claude e a instalação do Codex podem coexistir
(`install --provider all`); depois disso, o `install` sem `--provider` atualiza os dois, e o `doctor` avisa se o Codex
ficar desatualizado.

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
model = "sonnet"          # chave de config/models.toml do provedor; sem ele, o tier padrão do papel
effort = "high"           # effort padrão; as exceções ficam em [effort.variants] do routing.toml
skills = ["code-review", "verificar-premissa"]
preload = ["code-review"]
```

| Papel | Nome padrão | Tier padrão |
|---|---|---|
| `orchestrator` | orquestrador | o modelo do chat |
| `planner` | planejador | mid (high) |
| `explorer` | explorador | fast |
| `coder` | codificador | mid (high) |
| `reviewer` | revisor | mid (high) |
| `qa` | qa | mid (medium) |
| `documenter` | documentador | fast |

- **`model` troca o modelo do papel.** As exceções de `[effort.variants]` que dão outro modelo (ex.: o explorador em
  Sonnet no levantamento) continuam com o delas.
- Um modelo de outro provedor vira o equivalente pelo tier.
- Uma config antiga, sem os agentes mais novos, recebe os novos com o padrão; com `api-db`, `bug-hunter` ou
  `security` (que saíram no fluxo v3), recebe um aviso e eles não são gerados.
- Nomes que colidem com agentes do CLI (`plan`, `explore`, `default`…) são recusados.

## Perfis de exemplo

### Padrão (Claude, plano da empresa)

O que o wizard gera. Nada a mudar: o padrão de cada agente e as exceções já equilibram custo e qualidade.

### Economizar a sessão (plano menor)

```toml
[agents.coder]
effort = "medium"         # medium como padrão; a correção pequena continua na exceção

[agents.reviewer]
effort = "medium"
```

E no dia a dia: "essa correção é pequena, use o codificador medium". O `metricas.md` e o `metricas-orquestrador.md`
mostram onde o consumo está — em geral, no chat do orquestrador.

### Só Codex

Só agentes e skills: sem regras de permissão, hooks (guard), perfil, MCP por agente, painel de diff, pastas da sessão
nem mods ([claude-e-codex.md](claude-e-codex.md#usar-o-aidw-no-codex)). As proteções ficam com as aprovações do seu Codex.

```toml
[provider]
name = "codex"
```

```powershell
python aidw.py install --provider codex              # agentes e skills aidw-*
python aidw.py open --provider codex --demand 1234   # já liga multi_agent_v2 (o spawn_agent precisa dele)
```

A tabela de agentes e effort vale pelo tier equivalente de cada modelo, entre os liberados para a conta
([agentes.md](agentes.md#equivalência-no-codex)).

### Front-end

```toml
[mcp]
enabled = ["playwright", "chrome-devtools", "figma", "context7"]

[agents.qa]
enabled = true            # padrão: o qa testa a tela pelo Claude in Chrome ou pelo Playwright
```

O Figma precisa de autenticação uma vez (Claude: `/mcp` → figma → Authenticate; Codex: `codex mcp login figma`).

### Mais controle

Não é configuração: chame `/aidw:orquestrar <demanda> interativo`. Além dos pontos fixos (plano, achados, sua revisão,
passos manuais, PR), o orquestrador para antes de cada delegação.

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
| `orchestrator/config/routing.toml` | `[rules]` (`state` → ação), `max_retries` e `[[effort.variants.<papel>]]` (as exceções ao padrão de cada agente: `effort`, `model` opcional e `when`, o motivo que permite usá-la) |
| `config/mcp.toml` | Catálogo de MCPs: comando ou URL, `auth`, `allow`, os papéis que podem usar (`agents`), `use_when` e `triggers` (quando o orquestrador manda usar) |
| `orchestrator/ORCHESTRATOR.md` | O núcleo do orquestrador |
| `orchestrator/reference/` | O que o orquestrador lê sob demanda (com `when:`) |
| `orchestrator/policies/` | Políticas genéricas: git, banco, produção, segredos, permissões |
| `agents/`, `skills/`, `workflows/` | Agentes, skills e fluxos por tipo de demanda |

### Mudar as exceções de effort

```toml
[[effort.variants.coder]]
effort = "medium"
when = "correção pequena (achado mantido, teste que falhou, ajuste do usuário) ou ajuste temporário de teste"

[[effort.variants.explorer]]
model = "sonnet"          # chave do Claude; no Codex vale o equivalente pelo tier
effort = "high"
when = "levantamento: o mapa do fluxo de ponta a ponta é a entrega"
```

Cada exceção vira uma variante (`codificador-medium`, `explorador-sonnet-high`) e entra na tabela *Agents and effort*
do orquestrador com o `when`; o mod recusa uma variante fora dela. Um contexto pode trocar a lista de um papel no
`contexts/<nome>/routing.toml`. Os testes (`python -m unittest discover -s tests`) conferem as variantes; atualize o
teste junto.

## O que fica fora do AiDW

O AiDW acrescenta ao `~/.claude/settings.json` só os itens dele (regras de permissão, pastas, variáveis) e remove só
o que ele mesmo gravou. Ele **não** grava `model` nem `effortLevel`: o modelo do chat é o que você escolhe no app. O
seu `~/.claude/CLAUDE.md` e as suas configurações pessoais do CLI continuam seus.
