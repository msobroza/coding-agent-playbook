---
id: control-plane-guard
name: Control-plane guard
description: Stop the agent disabling or rewriting its own guardrails; that configuration is user-owned.
summary: Never edit guard configuration (`.claude/settings*.json`, `[hooks]`, `playbook/hooks/`) to loosen a guard; ask the user.
tier: default
priority: 20
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [edit, write, shell]
handler:
  builtin: control_plane_guard
  config:
    extra_paths: []
decisions: [deny, ask, none]
timeout: 2
on_error: ask
supports: [claude_code, opencode]
tags: [protect, guardrails]
---
Guardrail configuration is user-owned. Do not edit `.claude/settings*.json`, `.mcp.json`,
the `mcp`/`plugin` keys of `opencode.json`, the `[hooks]` and `[guardrails]` tables (or
other policy keys) of `.coding-agent-playbook.toml` and `.coding-agent-playbook.local.toml`,
`playbook/hooks/`, the playbook hook state under the git dir or the user's trust store to
disable or loosen a guard, and never wrap `playbook sync` in a pty or pipe input into it.
Ask the user to change the configuration instead.
