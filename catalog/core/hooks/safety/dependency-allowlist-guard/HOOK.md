---
id: dependency-allowlist-guard
name: Dependency allowlist guard
description: Deny the wrong package manager and hand edits of uv.lock or poetry.lock; ask before a new direct dependency (once per package per session) or a second package index.
version: 1
tier: default
priority: 20
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [shell, edit, write]
handler:
  builtin: dependency_guard
  config:
    index_mode: ask
    allowlist: []
    required_index: ""
decisions: [deny, ask, none]
timeout: 3
on_error: ask
supports: [claude_code, opencode]
tags: [safety, dependencies, supply-chain]
---
Do not add a new dependency without asking the user first. Install through the project's
package manager (`uv add`, `poetry add`, or `requirements.in` plus `pip-compile`), never edit
`uv.lock` or `poetry.lock` by hand (regenerate them), and do not add a second package index
(`--extra-index-url`) unless the user confirms it.
