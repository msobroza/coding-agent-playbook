---
id: commit-message-convention
name: Commit message convention
description: Deny a git commit whose message, or a git push whose commits after the cut-over date, fail this repo's commitizen convention (cz check).
version: 1
tier: default
priority: 24
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [shell]
handler:
  builtin: commit_message_convention
  config:
    check_push: true
decisions: [deny, none]
timeout: 10
on_error: open
supports: [claude_code, opencode]
tags: [safety, git, commitizen]
---
Commit messages follow this repo's commitizen convention (`cz check`); run it before committing.
