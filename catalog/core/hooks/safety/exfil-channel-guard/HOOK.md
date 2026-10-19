---
id: exfil-channel-guard
name: Exfiltration channel guard
description: Ask before repository data leaves the machine through ordinary tools (a new git remote, a push to an unconfigured target, a gist, curl or wget uploads, scp, rsync or sftp to a remote host); deny when the file sent is a credential file.
summary: Do not send repository data off the machine (new remotes, gists, uploads, `scp`) unless the user asked for it.
version: 1
tier: default
priority: 22
events: [pre_tool_use, session_start]
matcher:
  pre_tool_use:
    tools: [shell]
handlers:
  pre_tool_use:
    builtin: exfil_guard
    config:
      allowed_hosts: []
      extra_rows: []
  session_start:
    builtin: "exfil_guard:session_start"
decisions: [deny, ask, none]
timeout: 3
on_error: ask
supports: [claude_code, opencode]
tags: [safety, shell, network]
---
Do not send repository data off the machine on your own: no new git remotes, no pushes
to targets other than the configured remotes, no gists, and no `curl`/`wget` uploads or
`scp`/`rsync`/`sftp` copies to remote hosts unless the user asked for them. Never upload a
credential file.
