---
id: sensitive-data-read-guard
name: Sensitive data read guard
description: Ask before the agent reads raw customer data or notebook outputs (regulated overlay activation).
tier: default
enabled: true
priority: 17
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [read, search, notebook_edit, shell]
handler:
  builtin: sensitive_read_guard
  config:
    mode: ask
    deny_globs: ["data/raw/**", "exports/**", "*.parquet", "*.sqlite", "*.db", "*.xlsx"]
    csv_max_sample_bytes: 65536
    allow_globs: ["data/fixtures/**", "data/synthetic/**", "tests/**"]
decisions: [ask, deny, none]
timeout: 3
on_error: ask
supports: [claude_code, opencode]
tags: [safety, data, overlay]
---
Never read raw customer data: no `data/raw/` or `exports/` files, parquet, SQLite or Excel
exports, and no notebook outputs. Work from `data/fixtures/` or `data/synthetic/` samples.
