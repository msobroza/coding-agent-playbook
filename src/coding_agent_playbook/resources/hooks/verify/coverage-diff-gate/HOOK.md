---
id: coverage-diff-gate
name: Cover the changed lines
description: The coverage Stop stage; when completion is claimed, run the suite once with coverage and block while the changed lines are under-covered or total coverage dropped since the last green run of HEAD.
version: 1
tier: opt-in
priority: 80
events: [stop]
applies_if:
  has_dev_dependency: [pytest-cov]
handler:
  builtin: coverage_diff_gate
  config:
    stage: coverage
    timeout_s: 300
    diff_base: HEAD
    decision: deny
decisions: [deny, none]
timeout: 300
on_error: open
supports: [claude_code, opencode]
tags: [verify, coverage, stop-gate]
---
Before claiming done, run the suite with coverage and cover every changed line (≥80%).
