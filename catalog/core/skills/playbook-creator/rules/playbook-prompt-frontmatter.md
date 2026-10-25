---
id: playbook-prompt-frontmatter
name: Prompt frontmatter
description: "Make a prompt a slash-command task that names its rules by id in includes_rules and states its write scope and output contract."
version: 1
scope: scoped
globs:
  - "catalog/**/prompts/*.md"
  - "catalog/**/prompts/*.md.j2"
  - "playbook/prompts/*"
  - "src/*/resources/prompts/*"
applies_if:
  playbook_layer: true
section: prompts
priority: 45
tags: [playbook, prompts]
---

# Name a prompt's rules by id and declare its scope and contract

## Description

A prompt is a task the user starts by name, as a slash command. Guidance the agent should apply unprompted belongs in a rule or a skill instead.

A prompt is `prompts/<id>.md` or `.md.j2` with:

- **Required:** `id`, `name`, `description`, `version`, and `slash`: pick a name no other prompt or skill uses and no harness reserves (nothing checks it).
- `applies_if`: the rule gate language; the prompt is written only where it holds.
- `input_variables`: each with `name`, `description` and `required`.
- `includes_rules`: rule ids, in the order the task needs them.
- `eval_samples`: the ids of the samples that test the prompt.
- `write_scope`: `{read_only: true}` or `{globs: [...]}`.
- `output_contract`: regexes the final answer must match.

Delivery differs by harness. On Claude Code and OpenCode, `includes_rules` becomes a "Before you start" block naming each skill and rule file to load. On Continue, agent_harness and the eval runner, the rules' text is appended as a "Reference rules" section. An included rule whose gate fails in the repo drops silently.

## Bad Example

```yaml
id: release-review
slash: release-review
includes_rules: acme-decimal-amounts
output_contract:
  - "(?im)^verdict:\s*(ship|hold)$"
```

```markdown
# Release review

Amounts are decimals with a currency, never floats. Round once, at the invoice line.
```

A bare string for `includes_rules`, a regex in a double-quoted YAML string (where a backslash escape fails), and a rule's bullets pasted into the body, where they drift from the rule.

## Good Example

```yaml
id: release-review
name: Release review
description: Review a release branch for billing regressions before it ships.
version: 1
slash: release-review
includes_rules:
  - acme-decimal-amounts
  - acme-invoice-ids
eval_samples:
  - release-review-happy-path
write_scope:
  read_only: true
output_contract:
  - '(?im)^\W*verdict\W*(ship|hold)\W*$'
```

The body's `## Output format` section asks for exactly that line: `Verdict: ship` or `Verdict: hold`.

## Notes

- Validate fails on an unknown included id (with a did-you-mean), an `includes_rules` that is not a list, an output contract that does not compile and an eval sample that does not point back to the prompt.
- The opt-in output-contract stop hook checks the final answer against `output_contract`.
- A read-only prompt also renders natively restricted on Claude Code and OpenCode.
- In the engine's core layer, prompts' includes_rules stay frozen until the pilot ends.
- Harnesses reserve their commands, command aliases and shipped skills, and a synced prompt with such a slash shadows the harness's own. Avoid, among others: on Claude Code `review`, `code-review`, `security-review`, `init`, `simplify`, `run`, `verify`, `debug`, `doctor`, `loop`, `batch`; on OpenCode `init`, `review`, `compact`, `undo` and `customize-opencode`; on Codex `review`, `init`, `diff`, `plan`, `agents`, `skills`, `compact` and `undo`. On a collision add a suffix, as core does with `review-core`.
- prompt-template.md has the full skeleton.
