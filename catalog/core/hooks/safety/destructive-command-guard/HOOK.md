---
id: destructive-command-guard
name: Destructive command guard
description: Deny catastrophic shell commands (rm -r of /, home or the repo, force-pushing a protected branch, a download piped into a shell, mkfs, dd onto a disk); ask before a command that would lose uncommitted work.
summary: Never run destructive commands (`rm -rf`, force-push, `git reset --hard`, `curl … | sh`) on your own; ask first.
tier: default
priority: 18
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [shell]
handler:
  builtin: destructive_command_guard
  config:
    protected_branches: [main, master, "release/*"]
    safe_rm_dirs: [dist, build, __pycache__, .pytest_cache, .mypy_cache, .ruff_cache, htmlcov, node_modules]
    extra_rows: []
decisions: [deny, ask, none]
timeout: 3
on_error: ask
supports: [claude_code, opencode]
tags: [safety, shell, git]
---
Never run destructive commands on your own: no `rm -rf` outside build or cache
directories, no force-push to a protected branch (push a feature branch; the user merges),
no `git reset --hard`, `git clean -f` or `git checkout -- .` over uncommitted work, and no
`curl ... | sh`. When something must be deleted or rewritten, ask the user first.
