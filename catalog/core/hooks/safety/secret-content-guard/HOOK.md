---
id: secret-content-guard
name: Secret content guard
description: Deny a write that would persist a secret token (cloud, VCS, chat, payment and LLM API keys, private keys, JWTs, URL passwords) and a git push whose unpushed commits add one.
summary: Never write a secret value into a file or a commit; read it from the environment or the secret manager.
version: 1
tier: default
priority: 16
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [edit, write, notebook_edit, shell]
handler:
  builtin: secret_content_guard
  config:
    extra_patterns: []
    max_scan_bytes: 1048576
decisions: [deny, ask, none]
timeout: 3
on_error: ask
supports: [claude_code, opencode]
tags: [safety, secrets]
---
Never write a secret value (API key, token, private key, password in a URL) into a file
or a commit. Read it from an environment variable or the secret manager and reference it
by name. An `# playbook: allow-secret <rule-id>` waiver counts only once a reviewer has
committed it.
