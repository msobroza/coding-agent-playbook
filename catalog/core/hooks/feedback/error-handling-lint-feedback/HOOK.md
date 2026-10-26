---
id: error-handling-lint-feedback
name: Error-handling lint feedback
description: Report bare or blind excepts, silent pass/continue, a missing `raise ... from` and assert-as-check on the lines a Python edit changed (warn only).
tier: default
priority: 60
events: [post_tool_use]
linked_rule: python-error-handling
matcher:
  post_tool_use:
    tools: [edit, write]
handler:
  builtin: ruff_lint_feedback
decisions: [context, none]
timeout: 10
on_error: open
supports: [claude_code, opencode]
tags: [feedback, ruff, python]
---
