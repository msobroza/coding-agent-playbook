# Hook template

One directory per hook: `hooks/<category>/<id>/HOOK.md`, where the directory name is the id and the category folder means nothing. Copy the skeleton for your layer, replace the placeholders and run `playbook validate` after every edit. Keys and handlers: `playbook-hook-definition`; summary, body and twin: `playbook-hook-guardrails`.

## Contents

- Builtin-handler hook
- External-handler hook
- Event table
- Matcher vocabulary
- Guardrail text
- Guard twin and pre-commit wiring
- Overriding a hook
- Checklist

## Builtin-handler hook

The engine layer runs only registered handlers and ships no `scripts/`.

```markdown
---
id: <hook-id>
name: <Hook name>
description: <What it decides, in one sentence.>
summary: <One line of 1-120 characters: what to do instead.>
tier: default                 # default or opt-in
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [edit, write]
    paths: ["<glob>"]
handler:
  builtin: <registered_name>
  config: {}                  # validated by the handler's schema
decisions: [deny, none]       # never allow
timeout: 5                    # seconds
on_error: open
supports: [claude_code, opencode]
---
<Imperative guardrail text with the fix: what to do, what to run.>
```

## External-handler hook

An overlay or `playbook/` hook may run its own script, kept in the hook's `scripts/`:

```yaml
handler:
  command: python                     # a launcher name, never a shell string
  script: scripts/<check>.py          # inside this hook's scripts/
  args: ["--flag", "<static value>"]  # static, no URL
```

It runs only when the source is trusted and the user approves the script's hash in an interactive `playbook sync`:

```toml
[hooks]
enabled = true
allow_code_from = ["<repo-local>"]  # or the overlay's package name
```

## Event table

| Event | Decisions allowed | `on_error` allowed | Matcher fields | Timeout cap |
| --- | --- | --- | --- | --- |
| `session_start` | `context`, `none` | `open` | `sources` | 600 |
| `user_prompt_submit` | `deny`, `context`, `none` | `deny`, `open` | none | 30 |
| `pre_tool_use` | `deny`, `ask`, `context`, `none` | `ask`, `deny`, `open` | `command`, `paths`, `tool_names`, `tools` | 30 |
| `post_tool_use` | `context`, `none` | `open` | `command`, `paths`, `tool_names`, `tools` | 30 |
| `post_tool_use_failure` | `context`, `none` | `open` | `command`, `paths`, `tool_names`, `tools` | 30 |
| `stop` | `deny`, `context`, `none` | `open` | none | 600 |
| `subagent_stop` | `deny`, `context`, `none` | `open` | `agent_types` | 600 |
| `pre_compact` | `none` | `open` | `triggers` | 600 |
| `session_end` | `none` | `open` | none | 600 |

## Matcher vocabulary

| Field | Takes |
| --- | --- |
| `tools` | Tool classes: `shell`, `edit`, `write`, `notebook_edit`, `read`, `search`, `web`, `subagent`, `mcp` |
| `paths` | Repo-relative globs, without `..` |
| `command` | Regexes over the shell command, compiled by validate |
| `tool_names` | Regexes over the Claude Code tool names |

## Guardrail text

- `summary`: one line, 1-120 characters, no template syntax. It is the hook's line in `AGENTS.md`, and in the Claude Code rules file where Claude Code cannot run the hook.
- Body: imperative guidance with the fix. It becomes the hook's section of the playbook-guardrails skill, Continue's guardrail rule and the agent_harness guardrail text.

## Guard twin and pre-commit wiring

A hook that blocks something reproducible gets a twin running the same judge: a playbook subcommand in the engine, a console script in an overlay, a script in `playbook/`.

```yaml
- repo: local
  hooks:
    - id: <twin-id>
      name: <what it checks>
      entry: python tools/<check>.py
      language: system
      files: ^src/
```

## Overriding a hook

- An overlay hook with an existing id may only add: events, tool classes, stricter config (`playbook-override-by-id`).
- A `playbook/` hook may replace a hook that is not mandatory.
- `[hooks] disable = ["<hook-id>"]` switches a hook off with no file.

## Checklist

- The id matches the directory, is unique, and equals no rule or prompt id.
- Required keys are present; there is exactly one of `handler` or `handlers`.
- Every decision is valid for a declared event, and `allow` never appears.
- The timeout respects the cap; `on_error` is valid for each event, and `deny` only on an overlay hook.
- Every adapter in `supports` reaches at least one declared event.
- An external script sits in the hook's `scripts/`, and its source is in `allow_code_from`.
- `applies_if` uses known facts; `linked_rule` names an existing rule; the summary is one line, and the body tells the agent what to do.
