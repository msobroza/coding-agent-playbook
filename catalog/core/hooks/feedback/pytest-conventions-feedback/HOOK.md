---
id: pytest-conventions-feedback
name: pytest conventions feedback
description: Report unittest-style asserts, parametrize shape, broad pytest.raises and composite asserts on the lines a test edit changed (warn only; AST heuristics opt-in).
version: 1
tier: default
priority: 60
events: [post_tool_use]
linked_rule: pytest
matcher:
  post_tool_use:
    tools: [edit, write]
handler:
  builtin: ruff_lint_feedback
  config:
    ast_heuristics: false
decisions: [context, none]
timeout: 10
on_error: open
supports: [claude_code, opencode]
tags: [feedback, ruff, python, testing]
---
