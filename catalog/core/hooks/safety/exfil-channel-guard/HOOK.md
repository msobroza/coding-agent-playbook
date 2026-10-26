---
id: exfil-channel-guard
name: Exfiltration channel guard
description: Ask before repository data leaves the machine through ordinary tools (a new git remote, a push to an unconfigured target, a gist or snippet, curl or wget uploads, scp, rsync or sftp to a remote host, mail through git send-email, git imap-send, sendmail or msmtp); deny when the file sent is a credential file, including a body, attachment or asset file sent through gh, glab or playbook forge.
summary: Do not send repository data off the machine (new remotes, gists, uploads, `scp`, mail) unless the user asked for it.
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
to targets other than the configured remotes, no gists or snippets (`gh gist create`,
`glab snippet create`), no `curl`/`wget` uploads or `scp`/`rsync`/`sftp` copies to
remote hosts, and no mail (`git send-email`, `git imap-send`, `sendmail`, `msmtp`) unless
the user asked for them. Never upload a credential file, nor send one
as a body, description, attachment or release asset through `gh`, `glab` or `playbook forge`.
