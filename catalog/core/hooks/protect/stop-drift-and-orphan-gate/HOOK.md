---
id: stop-drift-and-orphan-gate
name: Stop on generated-output drift
description: Block the end of a turn while generated outputs differ from the lockfile or orphans remain; run validate and sync first.
version: 1
tier: default
priority: 30
events: [stop]
handler:
  builtin: stop_drift_and_orphan_gate
  config:
    stage: drift
decisions: [deny, none]
timeout: 5
on_error: open
supports: [claude_code, opencode]
tags: [protect, drift]
---
Before finishing a turn that changed `playbook/` sources, detector inputs or generated
files, run `playbook sync --check`. If it reports drift, run
`playbook validate && playbook sync` (or ask the user to) before you stop.
