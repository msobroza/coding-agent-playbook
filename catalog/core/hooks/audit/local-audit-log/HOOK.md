---
id: local-audit-log
name: Local audit log
description: Record each tool call, prompt and session boundary as a structure-only local audit line (command names and flag names, masked paths, prompt digests; never values, prompt text or file contents).
tier: opt-in
priority: 91
events: [session_start, user_prompt_submit, post_tool_use, post_tool_use_failure, session_end]
handler:
  builtin: activity_log
  config:
    retain_days: 90
    chain: false
    full_commands: false
    pii: []
decisions: [none]
timeout: 2
on_error: open
supports: [claude_code, opencode]
tags: [audit]
---
