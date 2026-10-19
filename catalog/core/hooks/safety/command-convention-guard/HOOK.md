---
id: command-convention-guard
name: Command convention guard
description: Apply this repository's Bash convention rows (a deny row names the corrected command, a warn row adds a reminder once per session); the engine ships no rows.
summary: Run commands the way this repository documents them; when one is refused, use the corrected form it names.
version: 1
tier: opt-in
priority: 60
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [shell]
handler:
  builtin: command_convention_guard
  config:
    rules: []
decisions: [deny, context, none]
timeout: 2
on_error: open
supports: [claude_code, opencode]
tags: [safety, shell, conventions]
---
Run commands the way this repository documents them; when a command is refused, use the
corrected form the message names.
