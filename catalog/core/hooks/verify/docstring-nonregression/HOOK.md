---
id: docstring-nonregression
name: No docstring regressions
description: The docstrings Stop stage plus a post-edit bucket; flag removed docstrings and new undocumented public symbols in touched Python files.
summary: Give every new public function, class and module a docstring with an intent line and one usage example.
tier: default
priority: 60
events: [stop, post_tool_use]
linked_rule: python-docstrings
matcher:
  post_tool_use:
    tools: [edit, write]
handlers:
  stop:
    builtin: docstring_nonregression
    config:
      stage: docstrings
  post_tool_use:
    builtin: docstring_nonregression:post_edit
    config:
      lint_feedback: true
decisions: [deny, context, none]
timeout: 3
on_error: open
supports: [claude_code, opencode]
tags: [verify, docstrings, ruff, stop-gate]
---
Give every new public function, class and module a docstring: an intent line, then one usage
example.
