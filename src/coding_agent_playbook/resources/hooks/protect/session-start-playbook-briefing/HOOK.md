---
id: session-start-playbook-briefing
name: Session-start playbook briefing
description: Prove the guards answer (one heartbeat line) and report playbook anomalies at session start, resume and compaction.
version: 1
tier: default
priority: 10
events: [session_start]
matcher:
  session_start:
    sources: [startup, resume, clear, compact, fork]
handler:
  builtin: session_start_playbook_briefing
decisions: [context, none]
timeout: 5
on_error: open
supports: [claude_code, opencode]
tags: [protect, heartbeat]
---
