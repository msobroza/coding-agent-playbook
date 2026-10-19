---
id: guard-eval-fixtures
name: Guard eval fixtures
description: Ask before editing or reformatting a committed eval task's frozen setup/ fixtures.
summary: Do not edit, reformat or lint-fix an eval task's frozen `setup/` files unless you are authoring that task.
version: 1
tier: opt-in
priority: 60
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [edit, write, notebook_edit, shell]
handler:
  builtin: guard_eval_fixtures
decisions: [ask, none]
timeout: 2
on_error: open
supports: [claude_code, opencode]
tags: [protect, evals]
---
Files under an eval task's `setup/` directory (`eval_tasks/<id>/setup/`) are the frozen
starting state of that task: find-injected-vuln fixtures are intentionally vulnerable and
`file_unchanged` gates compare against them. Do not edit, reformat or lint-fix them
(`ruff format`, `ruff --fix`, `black`, `isort`, `sed -i`) unless you are authoring that task.
