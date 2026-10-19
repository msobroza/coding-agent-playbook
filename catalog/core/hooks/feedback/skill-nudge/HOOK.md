---
id: skill-nudge
name: Skill nudge
description: Name the skill that covers a file the first time a session edits it, one line per skill (warn only).
version: 1
tier: default
priority: 30
events: [post_tool_use]
matcher:
  post_tool_use:
    tools: [edit, write]
handler:
  builtin: skill_nudge
decisions: [context, none]
timeout: 2
on_error: open
supports: [claude_code, opencode]
tags: [feedback, skills]
---
