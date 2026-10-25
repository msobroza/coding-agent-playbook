---
id: network-egress-guard
name: Network egress guard
description: Restrict agent network egress (shell clients, git remotes, package installs, WebFetch and WebSearch) to the organization's approved hosts. Inert in the engine (mode off); an air-gapped overlay activates it.
summary: 'Reach only the organization''s approved hosts: install from the internal index, call no public API, search no web.'
tier: overlay
enabled: true
priority: 21
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [shell, web]
handler:
  builtin: network_egress_guard
  config:
    mode: "off"
    allowed_hosts: []
    gateway_hosts: []
    webfetch_max_query_chars: 256
decisions: [deny, ask, none]
timeout: 5
on_error: ask
supports: [claude_code, opencode]
tags: [safety, network, overlay]
---
Network access is limited to the organization's approved hosts. Install packages from
the internal index only, and do not call public APIs or search the web from this repo.
