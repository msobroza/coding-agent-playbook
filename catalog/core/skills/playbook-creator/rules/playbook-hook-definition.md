---
id: playbook-hook-definition
name: Hook definition
description: "Declare a hook's events, decisions, timeout and one registered or trusted handler in its own HOOK.md directory."
version: 1
scope: scoped
globs:
  - "catalog/**/hooks/**/HOOK.md"
  - "catalog/**/hooks/**/HOOK.md.j2"
  - "playbook/hooks/**"
  - "src/*/resources/hooks/**"
applies_if:
  playbook_layer: true
section: hooks
priority: 43
tags: [playbook, hooks]
---

# Declare what a hook may decide and which handler runs it

## Description

A hook is a directory `hooks/<category>/<id>/` holding `HOOK.md` (or `HOOK.md.j2`). The directory name is the id (`^[a-z0-9][a-z0-9-]{0,62}$`); the category folder means nothing, and no hook nests inside another.

- **Required keys:** `id`, `name`, `description`, `tier` (`default` or `opt-in`; `overlay` is reserved for engine mechanisms an overlay activates), `events`, `decisions`, `timeout`, `on_error`, `supports`, and exactly one of `handler` or `handlers` (one per event).
- **Optional keys:** `version`, `enabled`, `mandatory` (overlay hooks only), `priority` (fan-out order), `matcher`, `applies_if`, `linked_rule`, `tags`, `summary`.
- **Events:** `session_start`, `user_prompt_submit`, `pre_tool_use`, `post_tool_use`, `post_tool_use_failure`, `stop`, `subagent_stop`, `pre_compact`, `session_end`. Deny is possible on `user_prompt_submit`, `pre_tool_use`, `stop` and `subagent_stop`; ask only on `pre_tool_use`; `pre_compact` and `session_end` decide nothing.
- **Constraints:** `decisions` never include `allow`; `timeout` is at most 30 seconds on tool and prompt events (600 otherwise); `on_error: deny` only on an overlay hook. Matcher `tools` use the classes shell, edit, write, notebook_edit, read, search, web, subagent and mcp, plus path globs and command regexes.

Handlers come in two kinds. A **builtin** names a registered handler and a `config` its schema validates. Engine hooks are builtin-only and ship no `scripts/`; an overlay package may register its own builtin through the `coding_agent_playbook.hook_handlers` entry point, which runs only when `[hooks] allow_code_from` lists the package. An **external** handler (overlay or `playbook/` only) names a launcher (python, bash, sh or node), a script inside the hook's own `scripts/` and static `args`. It runs only when `[hooks] allow_code_from` lists its source and the user approves the script's hash in an interactive sync.

## Bad Example

```yaml
id: acme-freeze-guard
events: [pre_tool_use]
decisions: [allow, deny]
timeout: 60
handler:
  command: "python scripts/check.py && echo ok"
```

`allow` is never a decision, 60 seconds exceeds the cap on a tool event, and a command is a launcher name, not a shell string.

## Good Example

`playbook/hooks/release/acme-freeze-guard/HOOK.md`:

```yaml
id: acme-freeze-guard
name: Release freeze guard
description: Deny edits under src/ while the release freeze file exists.
summary: During a release freeze, change only release notes; ask the release owner first.
tier: default
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [edit, write]
    paths: ["src/**"]
handler:
  command: python
  script: scripts/freeze_check.py
  args: ["--freeze-file", "RELEASE_FREEZE"]
decisions: [deny, none]
timeout: 5
on_error: open
supports: [claude_code, opencode]
```

```toml
[hooks]
enabled = true
allow_code_from = ["<repo-local>"]
```

## Notes

- No HTTP, prompt, agent or input-rewriting handler keys exist.
- A hook must reach at least one declared event on every adapter listed in `supports`.
- An overlay's same-id hook may only add (`playbook-override-by-id`).
- hook-template.md has both skeletons and the full event table.
