---
id: validate-then-sync-on-canonical-edit
name: Validate canonical edits
description: Report playbook validate failures for an edited canonical source in-turn; sync only when [hooks] auto_sync allows.
summary: After editing a canonical playbook source, run `playbook validate` and fix its failures; ask the user to sync.
tier: default
priority: 40
events: [post_tool_use]
matcher:
  post_tool_use:
    tools: [edit, write]
    paths:
      - playbook/rules/**
      - playbook/prompts/**
      - playbook/skills/**
      - playbook/hooks/**
      - .coding-agent-playbook.toml
      - src/*/resources/rules/**
      - src/*/resources/prompts/**
      - src/*/resources/skills/**
      - src/*/resources/hooks/**
      - catalog/core/rules/**
      - catalog/core/prompts/**
      - catalog/core/skills/**
      - catalog/core/hooks/**
      - catalog/plugins/*/rules/**
      - catalog/plugins/*/prompts/**
      - catalog/plugins/*/skills/**
      - catalog/plugins/*/hooks/**
handler:
  builtin: validate_then_sync_on_canonical_edit
decisions: [context, none]
timeout: 10
on_error: open
supports: [claude_code, opencode]
tags: [protect, validate]
---
After editing a canonical playbook source (`playbook/rules`, `playbook/prompts`,
`playbook/skills`, `playbook/hooks` or `.coding-agent-playbook.toml`), run
`playbook validate` and resolve every failure it reports for that file before finishing.
Generated outputs change only through `playbook sync`; ask the user to run it.
