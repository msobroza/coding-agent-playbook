---
id: network-egress-guard
name: Network egress guard
description: Restrict agent network egress to the organization allowlist.
version: 1
tier: default
mandatory: true
priority: 21
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [shell, web]
handler:
  builtin: network_egress_guard
  config:
    mode: enforce
    allowed_hosts: [artifactory.bank.example, git.bank.example]
    gateway_hosts: [litellm.bank.example]
    webfetch_max_query_chars: 256
decisions: [deny, ask, none]
timeout: 5
on_error: ask
supports: [claude_code, opencode]
tags: [safety, network, overlay]
---
Network access is limited to approved internal hosts. Install packages from the
internal index only; do not call public APIs or search the web from this repo.
