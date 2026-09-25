# Permissions policy

Policies are not only instructions to the model. Where possible they are enforced by software:

- `aidw.py apply` turns the `[policies]` rules of `aidw.config.toml` and the context permissions
  into provider rules: `.claude/settings.local.json` (Claude Code) or `.codex/rules/aidw.rules`
  (Codex). The CLI blocks those commands regardless of what the model decides.
- Each agent gets only the tools, MCP servers and writable folders its role needs (e.g. the
  Reviewer reports, it does not edit code).
- Agents run headless: what would need approval is refused and comes back as a denial. The
  agent proposes it (exact command/text) and returns `policy_requires_approval`; only the user
  approves, through the orchestrator.
