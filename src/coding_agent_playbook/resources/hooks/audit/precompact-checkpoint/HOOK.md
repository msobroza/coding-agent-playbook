---
id: precompact-checkpoint
name: Pre-compaction checkpoint
description: Before compaction, remember where the user's own prompts are in the transcript (entry ids and offsets, never their text); after it, re-inject them as quoted, masked excerpts with the files edited so far.
version: 1
tier: opt-in
priority: 92
events: [pre_compact, session_start]
matcher:
  pre_compact:
    triggers: [manual, auto]
  session_start:
    sources: [compact]
handlers:
  pre_compact:
    builtin: precompact_checkpoint
    config:
      max_prompts: 10
  session_start:
    builtin: "precompact_checkpoint:reinject"
    config:
      max_prompts: 10
      pii: []
decisions: [context, none]
timeout: 3
on_error: open
supports: [claude_code]
tags: [audit, compaction]
---
