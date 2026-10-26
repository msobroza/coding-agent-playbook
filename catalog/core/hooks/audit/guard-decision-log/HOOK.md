---
id: guard-decision-log
name: Guard decision log
description: Log every guard deny, ask, override, escape and degraded event locally, as ids and flags only (never command text, paths, prompts or file contents).
tier: default
priority: 90
events: [session_start, user_prompt_submit, pre_tool_use, post_tool_use, post_tool_use_failure, stop, subagent_stop, pre_compact, session_end]
handler:
  builtin: decision_log
decisions: [none]
timeout: 1
on_error: open
supports: [claude_code, opencode]
tags: [audit]
---
