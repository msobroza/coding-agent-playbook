---
id: eval-task-authoring-lint
name: Eval task authoring lint
description: Parse and trial-compile an edited eval task and show how the engine reads it; never runs it.
summary: After editing an eval task, run `playbook validate` and `playbook eval --show <id>`; never `playbook eval --run`.
version: 1
tier: default
priority: 50
events: [post_tool_use]
matcher:
  post_tool_use:
    tools: [edit, write]
    paths:
      - "**/eval_tasks/*/task.toml"
      - "**/eval_tasks/*/setup/pyproject.toml"
handler:
  builtin: eval_task_authoring_lint
decisions: [context, none]
timeout: 10
on_error: open
supports: [claude_code, opencode]
tags: [protect, evals]
---
After editing an eval task (`eval_tasks/<id>/task.toml` or its `setup/pyproject.toml`), run
`playbook validate` and `playbook eval --show <id>` and fix every compile error before
finishing. Write regex patterns as TOML literal strings (single quotes): `\s` is an
invalid escape in a basic string. Never run `playbook eval --run` to check a task.
