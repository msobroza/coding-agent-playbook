---
id: typing-lint-feedback
name: Typing lint feedback
description: Report missing annotations on public signatures, `Any`, mutable defaults, blanket type ignores and pre-PEP 604/695 typing on the lines a Python edit changed (warn only).
tier: default
priority: 60
events: [post_tool_use]
linked_rule: python-typing
matcher:
  post_tool_use:
    tools: [edit, write]
handler:
  builtin: ruff_lint_feedback
decisions: [context, none]
timeout: 10
on_error: open
supports: [claude_code, opencode]
tags: [feedback, ruff, python, typing]
---
