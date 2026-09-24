# Permissions policy

Policies are not only instructions to the model. Where possible they are enforced by software:

- `aidev.py apply` writes the `[policies].deny` rules from `aidev.config.toml` into each
  agent's `.claude/settings.local.json`, so Claude Code blocks those commands regardless
  of what the model decides.
- Each agent gets only the tools its role needs (e.g. the Reviewer reports, it does not edit).
- Operations that require approval return `next_action: "HUMAN_APPROVAL"` and wait.
