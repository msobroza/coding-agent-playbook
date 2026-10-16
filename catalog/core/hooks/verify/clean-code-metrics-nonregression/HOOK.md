---
id: clean-code-metrics-nonregression
name: No metrics regressions at Stop
description: The quality-metrics Stop stage; measure touched Python files against HEAD with the repo's static metrics gate and ruff's complexity budgets, plus a post-edit companion on changed lines.
version: 1
tier: default
priority: 60
events: [stop, post_tool_use]
matcher:
  post_tool_use:
    tools: [edit, write]
    paths: ["*.py"]
handlers:
  stop:
    builtin: clean_code_metrics_nonregression
    config:
      stage: quality-metrics
  post_tool_use:
    builtin: clean_code_metrics_nonregression:post_edit
    config:
      lint_feedback: true
decisions: [deny, context, none]
timeout: 3
on_error: open
supports: [claude_code, opencode]
tags: [verify, metrics, stop-gate]
---
Do not make a function, class or module you touched more complex than it is at `HEAD`
(cyclomatic complexity, nesting, coupling, cohesion). Before finishing, run
`playbook metrics --baseline git:HEAD` on the files you changed and fix each regression.
