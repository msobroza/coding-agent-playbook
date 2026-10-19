---
id: gate-weakening-guard
name: Do not weaken the gates
description: The gate-integrity Stop stage plus an edit companion; flag new suppressions, skipped or deleted tests and loosened checker config.
summary: 'Fix the root cause instead of silencing a check: no bare `# noqa`, skipped tests or loosened tool configuration.'
version: 1
tier: default
priority: 30
events: [stop, pre_tool_use]
matcher:
  pre_tool_use:
    tools: [edit, write, shell]
handlers:
  stop:
    builtin: gate_weakening_guard
    config:
      stage: gate-integrity
  pre_tool_use:
    builtin: gate_weakening_guard:pre_edit
decisions: [deny, ask, none]
timeout: 3
on_error: ask
supports: [claude_code, opencode]
tags: [verify, gates, stop-gate]
---
Fix the root cause instead of silencing a check. Do not add `# type: ignore`, `# noqa`,
`# pragma: no cover` or `# nosec` without a trailing reason, do not skip, xfail or delete
tests, and do not loosen mypy, ruff, pytest or pre-commit configuration to get green.
