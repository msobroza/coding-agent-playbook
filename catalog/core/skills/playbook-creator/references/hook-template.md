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
| `session_start` | `context`, `none` | `open` | `sources` | 15 |
| `user_prompt_submit` | `deny`, `context`, `none` | `deny`, `open` | none | 30 |
| `pre_tool_use` | `deny`, `ask`, `context`, `none` | `ask`, `deny`, `open` | `command`, `paths`, `tool_names`, `tools` | 30 |
| `post_tool_use` | `context`, `none` | `open` | `command`, `paths`, `tool_names`, `tools` | 30 |
| `post_tool_use_failure` | `context`, `none` | `open` | `command`, `paths`, `tool_names`, `tools` | 30 |
| `stop` | `deny`, `context`, `none` | `open` | none | 595 |
| `subagent_stop` | `deny`, `context`, `none` | `open` | `agent_types` | 595 |
| `pre_compact` | `none` | `open` | `triggers` | 30 |
| `session_end` | `none` | `open` | none | 8 |

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
```

## Overriding a hook

- An overlay hook with an existing id may only add: events, tool classes, stricter config (`playbook-override-by-id`).
- A `playbook/` hook may replace a hook that is not mandatory; `[hooks] disable = ["<hook-id>"]` switches a hook off with no file.

## Checklist

- H1-H2: `HOOK.md` parses, with schema keys only and every required key. The id matches `^[a-z0-9][a-z0-9-]{0,62}$`, equals its directory and is unique in the layer; a directory holds `HOOK.md` or `HOOK.md.j2`, never both, and no hook directory nests in another.
- H3-H4: `events` is non-empty, unique and canonical. Each `matcher` key is a declared event and uses only that event's fields from the event table; regexes compile, and globs are relative, without `..`.
- H5: every decision is valid for a declared event, and `allow` never appears.
- H6-H8: exactly one of `handler` or `handlers`, whose keys equal `events`. A builtin is registered and its `config` validates. An external `command` is `python`, `bash`, `sh` or `node`, never a shell string; its script is a regular file in the hook's `scripts/`; `args` carry no URL. No `type`, `url`, `headers`, `async`, `updated_input`, `prompt` or `model` key.
- H9-H10: `0 < timeout <= 600`, and the timeout stays within the smallest cap of its events in the event table: above 30 on a tool or prompt event is an error, above any other cap a warning and a clamp. `on_error` is valid for each event, and `deny` only on an overlay hook.
- H11: every adapter in `supports` reaches at least one declared event.
- H12-H13: `tier` is `default`, `opt-in` or `overlay`, and `overlay` only on an engine hook or an overlay's override of one; `mandatory: true` only on an overlay hook with `enabled: true`. An engine hook is builtin-only and ships no `scripts/`.
- H14-H16: an override only adds; nothing overrides or disables a `mandatory` hook; an external handler's source is in `allow_code_from`.
- H17-H20: `applies_if` uses known facts; `linked_rule` names an existing rule; a `HOOK.md.j2` body compiles and includes no rule; the id equals no rule or prompt id. The summary is one line of 1-120 characters, and the body tells the agent what to do.
- H21: `[hooks]` and `[guardrails]` parse; `enable` and `disable` name existing hooks and never the same one; `allow_code_from` names enabled overlays or `<repo-local>`.
