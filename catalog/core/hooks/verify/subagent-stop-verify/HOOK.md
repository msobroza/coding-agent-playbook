---
id: subagent-stop-verify
name: Verify a subagent before it stops
description: Run the Stop gate's scoped stages on the files an editing subagent changed and block its stop while they are red.
summary: A subagent that edits files leaves them passing `ruff check .` and `ruff format --check .` before it reports back.
version: 1
tier: opt-in
priority: 20
events: [subagent_stop]
handler:
  builtin: subagent_stop_verify
  config:
    stages: [lint]
decisions: [deny, none]
timeout: 5
on_error: open
supports: [claude_code]
tags: [verify, subagents, stop-gate]
---
A subagent that edits files must leave them passing the repository's checks (at least
`ruff check .` and `ruff format --check .`) before it reports back. Do not claim success
while a check is red; say what is still failing.
