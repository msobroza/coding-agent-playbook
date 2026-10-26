---
id: secrets-path-guard
name: Secrets path guard
description: Deny agent reads and writes of credential files (.env, keys, cloud and SSH credentials) and commands that print a forge token (gh auth token, glab config get token, echo $GH_TOKEN); ask before creating a new .env or opening a hard link to a credential file.
summary: Never read, print or write credential files (`.env*`, keys, `~/.ssh`) or forge tokens; ask the user for the values.
tier: default
priority: 15
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [read, search, edit, write, notebook_edit, shell, mcp]
handler:
  builtin: secret_path_guard
  config:
    extra_globs: []
    allow_paths: []
decisions: [deny, ask, context, none]
timeout: 2
on_error: ask
supports: [claude_code, opencode]
tags: [safety, secrets]
---
Never read, print or write credential files: `.env*`, `*.pem`, `*.key`, key stores,
SSH keys and cloud credentials under `~/.aws`, `~/.ssh` and similar. Keep only variable
NAMES in `.env.example`, ask the user to supply the values, and read them from the
environment at run time. Never print a forge token (`gh auth token`, `glab auth status -t`,
`glab config get token`, `echo $GH_TOKEN`): `gh`, `glab` and `playbook forge` use their own login.
