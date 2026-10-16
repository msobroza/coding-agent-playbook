---
id: resync-on-detector-input-change
name: Resync on detector input change
description: Name the rules and prompts a dependency, Dockerfile, CI or notebook change newly activates; never auto-removes guidance.
version: 1
tier: default
priority: 45
events: [post_tool_use]
matcher:
  post_tool_use:
    tools: [edit, write, shell]
handler:
  builtin: resync_on_detector_input_change
decisions: [context, none]
timeout: 10
on_error: open
supports: [claude_code, opencode]
tags: [protect, detector]
---
Changing the project's dependencies (`pyproject.toml`, `uv add`, `poetry add`), adding a
`Dockerfile`, CI workflow or notebook can make more playbook rules and prompts apply. After
such a change, ask the user to run `playbook validate && playbook sync` so the new guidance
is rendered before you write the code it covers.
