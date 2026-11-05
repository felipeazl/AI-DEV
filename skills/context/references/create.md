# context create

A context is the rule package of a company or squad: the systems, commands, conventions and policies the orchestrator
and the agents follow. It lives in `{{root}}/contexts/<name>/`, in its **own private Git repository**, ignored by the
AiDW's Git. `aidw.py` is in `{{root}}`.

**Rules:** base everything on real files and commits of the analyzed repositories — never invent an example or copy
content from another context (the active context only serves as an example of *structure*). Do not read `.env`,
secret files or connection strings; a secret enters the context only by the variable's **name**. Economy: what the
agent always uses goes into the prompt (`include`); the rest becomes a reference read on demand (`reference` with
`when`).

**Language:** the context has its own language (a BCP-47 tag, e.g. `en`, `pt-BR`), decided in step 1. Write **all**
the context content in it — agents, policies, references, knowledge notes — and ask the questions of step 3 in it.
File and folder names stay in English.

## 1. Scope (before analyzing)

Ask, in a single question: the context's name (lowercase, digits, hyphen), the description (company — squad), the
**language** of the context (default: the AiDW UI language, `[ui] language`, shown by `python "{{root}}/aidw.py" show`)
and **which repositories** go in (local paths). Check that each path exists and is a Git repository
(`python "{{root}}/aidw.py" project detect --path <repo> --json`).

## 2. Careful analysis (read-only)

One `Explore` subagent per repository, **in parallel**, asking for `file:line` and short excerpts (not the whole
file). For each repository, gather with evidence:

1. **Stack and structure:** languages, frameworks and versions (csproj/package.json/pom…), solution and projects,
   layers (API/Application/Domain/Infrastructure…), front and back end.
2. **Build and test:** the real command that compiles and the one that tests (package.json scripts,
   `dotnet build/test`, MSBuild, `azure-pipelines*.yml`/`.github/workflows` pipelines), test framework and where the
   tests live. Propose the version **with filtered output** (only errors and the summary).
3. **Build dependencies outside Git:** `packages/`, `node_modules/`, local configs — they become `[worktree] link`.
4. **Code conventions:** `.editorconfig`, analyzers, lint/prettier, the repository's `CLAUDE.md`/`AGENTS.md`/
   `CONTRIBUTING`/README, the language of the code, the naming observed in the neighboring code.
5. **Git and flow:** default and development branch (`git branch -r`), the naming pattern of branches and commit
   messages (`git log --oneline -50`), where the PRs live (Azure DevOps, GitHub…).
6. **Integration between systems:** HTTP/SOAP clients, shared packages, queues, enums/contracts one system consumes
   from another — they become `depends_on` and the contract notes.
7. **Configuration and environments:** appsettings per environment, configuration service, variable names (never
   values), which environments exist (dev, qa, hml, prod).
8. **Database:** ORM/data access, `.sql` scripts folder, migrations, how the team versions scripts.
9. **Risks:** fragile legacy code, UI thread, concurrency, personal data (national ids, e-mail…) flowing around.

Write the result to `contexts/<name>/reference/initial-analysis.md` (after step 4) with the evidence.

## 3. Questions (at least 10)

Ask **at least 10 questions**, in blocks of up to 4 (question tool), each with options taken from the analysis, the
**recommendation** and why. Ask more whenever the analysis leaves a real doubt. Cover at least:

1. **Systems:** the name of each system, the repositories of each and a short description (confirm what the analysis
   found).
2. **Build and test:** confirm each system's filtered command; what to do when there is no automated test.
3. **Branch and PR:** branch prefix (`feature/<id>-<slug>`?), development base and PR target.
4. **Demand management:** where demands live (Azure DevOps, Jira, GitHub), org/project, item types and what the AiDW
   may do on its own on the board (read, create a task, change state, comment).
5. **Locked actions:** which always ask for an OK (commit, push, merge, write SQL, calls that change data, comments)
   and which run on their own.
6. **Environments:** where the agents may act (dev/qa), which only with authorization, and production (never?).
7. **Database:** read-only access through a validator? In which environments? How does a database script enter the
   demand?
8. **Code standard:** the source of truth (guideline repository, a document, the code itself) and what the reviewer
   must block.
9. **Secrets and personal data:** what never goes into a file, log or card; the team's data-protection rules.
10. **MCPs:** which ones the team needs (board, design, browser…) and which environment variables they require.
11. **Who decides:** Tech Lead, PO — and where the decisions are recorded (card comments?).
12. **The context's private repository:** URL of the private remote (or stay local for now).

## 4. Generate the context

1. `python "{{root}}/aidw.py" context create <name> --description "<description>" --language <tag> [--mcp a,b]
   [--env X,Y]` — creates the minimal structure (with `language = "<tag>"` in `context.toml`) and runs `git init`.
2. Fill in, from the analysis and the answers, in the context's language:
   - `context.toml`: `[systems.<key>]` (name, repos, stack, depends_on, build, test, notes), `[worktree]`,
     `[permissions]` (allow, git_ask, ask, deny — the minimum the routine needs), `required_env`, `required_mcp`
     and `[mcp.<name>]` with the registration command, `[agents.<role>]` with `include` and `reference`.
   - `policies/*.md`: one per topic of answers 4 to 9 (short, with the rule and why).
   - `agents/orchestrator.md`: the team's flow (steps, when to stop for the user, what goes on the card) — without
     repeating the AiDW core.
   - `agents/<role>.md` and `shared/guide-*.md`: only what each role always uses; the rest in `reference/` with `when`.
   - The knowledge base (the `[knowledge] dir` folder, already created with the conventions `README.md`): one note per
     system in `sistemas/<key>.md` with what the analysis found about how it works, where each thing lives, the
     repository's documentation (cited, not copied) and the integrations (`integracoes/`, one per contract between
     systems, linked to both sides). Domain terms that came up in the answers become `conceitos/`. Each fact in one
     note only; build and test stay in `context.toml`. Then, `python "{{root}}/aidw.py" kb index`.
3. `python "{{root}}/aidw.py" context check <name>` — fix until there is no error (it also runs `kb check`).

## 5. Deliver

Show the user: what was created (files), the systems and commands, the policies, what became a reference and the
`check` warnings. Propose, without running:
- activate: `/aidw:context use <name>` (`context use <name>`);
- a commit in the context's repository and, if there is a private remote, `git remote add origin <url>` and the push —
  **commit and push need an OK**; confirm that the remote is **private** before the push.
