---
id: block-precommit-bypass
name: Do not bypass the pre-commit hooks
description: Deny skipping the repo's playbook pre-commit hooks (--no-verify, SKIP=, core.hooksPath, .git/hooks edits); ask on plumbing commits.
version: 1
tier: default
priority: 20
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [shell, edit, write]
handler:
  builtin: block_precommit_bypass
  config:
    strict_skip: false
decisions: [deny, ask, none]
timeout: 2
on_error: ask
supports: [claude_code, opencode]
tags: [verify, git, pre-commit]
---
This repository's pre-commit hooks must run on every commit. Never pass `--no-verify`
(or `git commit -n`), set `SKIP=` for a playbook hook, change `core.hooksPath`, or edit
`.git/hooks/`. When a hook fails, fix what it reported (`playbook validate && playbook sync`,
or the metrics regression), or stop and tell the user.
