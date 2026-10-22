---
id: playbook-validate-and-sync
name: Validate and sync
description: "Run playbook validate after every source edit, fix each FAIL line, and change generated files only through sync."
version: 1
scope: scoped
globs:
  - "catalog/**"
  - "playbook/**"
  - "src/*/resources/**"
  - ".coding-agent-playbook.toml"
applies_if:
  playbook_layer: true
section: validation
priority: 28
tags: [playbook, validation]
---

# Validate every source change, then sync

## Description

`playbook validate` checks every layer's sources without rendering: frontmatter, ids and layout, sections and priority bands, gates, Jinja syntax, `includes_rules`, eval sample links in both directions, markdown links, Agent Skills names and the hook contract. It prints `OK <N> artifacts validated`, or one `FAIL <path>: <message>` line per error; sync refuses to write while any error stands.

Run it after each edit and fix every FAIL line that names your file. Read the warnings too: a rule joining a sectioned skill without `section:`, or a `playbook:` block no rule joins, means content is misplaced. For a repo with its own `[layout]`, validate also lists each document-layout rewrite (file, from, to, count); those are expected, not failures.

Then the user runs `playbook sync`: ask for it, unless `[hooks] auto_sync` is on. `playbook sync --check` confirms the working copy after a sync, or the committed output under `[output] commit = true`; on a fresh CI clone under `commit = false`, CI runs validate instead.

## Bad Example

Previewing a change by editing the output, then committing it:

```bash
$EDITOR .claude/skills/acme-billing/SKILL.md   # generated: the next sync overwrites it
git add .claude/
git commit -m "docs: tweak billing skill"
```

## Good Example

```bash
playbook validate                              # fix every FAIL line naming your file
playbook render acme-invoice-ids               # the rule as written, impact tag included
playbook render acme-invoice-ids --show-source # which layer and file it came from
playbook render acme-release-review --show-rules
playbook check                                 # facts, and why an artifact is skipped
playbook sync                                  # asked of the user
playbook sync --check
playbook docs-check                            # before committing Markdown
```

## Notes

- In an engine or overlay checkout without `.coding-agent-playbook.toml`, validate covers the engine's catalog, the checkout's `src/*/resources/` and `playbook/`, and names the consumer checks it skips.
- Content files are Markdown, so the docs-check pre-commit hook also checks their relative links and Python code blocks; `docs-check-in-ci` in python-documentation owns that practice.
- Under `commit = false`, `playbook sync --check-staged` refuses staged generated output.
- The validate-then-sync-on-canonical-edit and eval-sample-authoring-lint hooks remind you after an edit.
