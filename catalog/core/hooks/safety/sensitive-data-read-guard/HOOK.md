---
id: sensitive-data-read-guard
name: Sensitive data read guard
description: Ask before the agent reads raw data (overlay-configured data globs, CSVs above a sample size) or notebooks whose outputs may embed customer rows; deny instead in enforce mode. Path-based, never reads data content. Inert in the engine (mode off); a regulated overlay activates it.
summary: Do not read raw data exports or notebook outputs; work from fixtures or synthetic samples.
tier: overlay
enabled: true
priority: 17
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [read, search, notebook_edit, shell]
handler:
  builtin: sensitive_read_guard
  config:
    mode: "off"
    deny_globs: []
    allow_globs: []
    csv_max_sample_bytes: 65536
decisions: [ask, deny, none]
timeout: 3
on_error: ask
supports: [claude_code, opencode]
tags: [safety, data, overlay]
---
Do not read raw data exports (customer CSVs, parquet files, databases) or notebook
outputs: work from fixtures or synthetic samples, and read notebooks with outputs stripped.
