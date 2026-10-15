---
id: stop-diff-sweep
name: Stop-time secret sweep
description: The secrets Stop stage; block when the turn's working tree adds a secret token or an untracked credential file, and warn on untracked model or data artifacts and large files.
version: 1
tier: default
priority: 35
events: [stop]
handler:
  builtin: stop_secret_sweep
  config:
    stage: secrets
    mode: block
    max_scan_bytes: 2097152
    large_file_mb: 10
    extra_patterns: []
decisions: [deny, none]
timeout: 3
on_error: open
supports: [claude_code, opencode]
tags: [safety, secrets, stop-gate]
---
Before finishing, make sure the working tree adds no secret token and no credential
file (`.env*`, keys, `credentials.json`): move values to the environment or the secret
manager and gitignore credential files. Keep model weights, pickles and large data out of
the repository.
