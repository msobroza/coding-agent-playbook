---
id: stop-ci-parity-gate
name: Stop until the checks pass
description: The Stop coordinator; run the Stop stages once per working tree and block with one combined reason while any is red.
summary: Before claiming done, run `ruff check .`, `ruff format --check .`, the type checker and the tests; report the results.
version: 1
tier: default
priority: 10
events: [stop]
handler:
  builtin: stop_ci_parity_gate
  config:
    budget_s: 3.0
    max_blocks: 2
decisions: [deny, none]
timeout: 5
on_error: open
supports: [claude_code, opencode]
tags: [verify, stop-gate]
---
Before claiming the work is done, run the repository's checks (`ruff check .`,
`ruff format --check .`, the type checker and the tests) and report their result.
A red check is not done: fix it, or say plainly that it is still failing.
