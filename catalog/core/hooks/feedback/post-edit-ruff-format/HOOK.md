---
id: post-edit-ruff-format
name: Post-edit ruff format
description: Format already-clean Python files after an edit (safe import and pyupgrade fixes only) and report the ruff findings CI fails on for the changed lines.
summary: After editing a Python file, run `ruff check` and `ruff format` on it as CI does, and fix what they report.
tier: default
priority: 50
events: [post_tool_use]
matcher:
  post_tool_use:
    tools: [edit, write]
    paths: ["*.py", "*.pyi"]
handler:
  builtin: ruff_post_edit
  config:
    safe_fix_allowlist: [I, UP]
    max_project_lines: 5
decisions: [context, none]
timeout: 10
on_error: open
supports: [claude_code, opencode]
tags: [feedback, ruff, python]
---
After editing a Python file, run `ruff check` and `ruff format` on it the way the project's CI
does, and resolve what they report on the lines you changed. Do not reformat files you did not
edit, and do not remove an import you are about to use.
