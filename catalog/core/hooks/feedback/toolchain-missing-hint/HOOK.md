---
id: toolchain-missing-hint
name: Toolchain missing hint
description: When a shell command shows ruff, mypy, pytest or commitizen is not installed, name the project's install command once per session and ask the user before installing.
version: 1
tier: default
priority: 50
events: [post_tool_use, post_tool_use_failure]
matcher:
  post_tool_use:
    tools: [shell]
  post_tool_use_failure:
    tools: [shell]
handler:
  builtin: toolchain_hint
decisions: [context, none]
timeout: 5
on_error: open
supports: [claude_code, opencode]
tags: [feedback, toolchain]
---
If a check fails because ruff, mypy, pytest or commitizen is not installed, tell the user the
project's install command and ask before installing anything: an install may contact the
package index.
