# Prompt template

A prompt is a task the user starts by name, as a slash command; guidance the agent should apply unprompted is a rule instead. Copy the skeleton, replace the placeholders and run `playbook validate`. Keys: `playbook-prompt-frontmatter`; samples: `playbook-eval-samples`. The example is the fictional prompt release-review.

## Frontmatter

`prompts/release-review.md`:

```yaml
---
id: release-review
name: Release review
description: Review a release branch for billing regressions before it ships.
slash: release-review            # unique among prompts, skills and harness commands
applies_if:                      # optional; the rule gate language
  any_dependency: [sqlalchemy]
input_variables:                 # optional
  - name: branch
    description: The release branch to review
    required: true
includes_rules:                  # rule ids, in the order the task needs them
  - acme-decimal-amounts
  - acme-invoice-ids
write_scope:
  read_only: true
output_contract:                 # regexes the final answer must match
  - '(?im)^\W*verdict\W*(ship|hold)\W*$'
---
```

## Body skeleton

```markdown
# Release review

## Priorities

1. <What to check first, and why.>
2. <What to check next.>

## Output format

Findings as a list of `path:line: problem`, then one line exactly:
`Verdict: ship` or `Verdict: hold`.
```

The Output format asks for the exact line the output contract matches. Never paste a rule's bullets into the body: list the rule in `includes_rules`.

## What the engine adds per harness

- Claude Code and OpenCode: a "Before you start" block naming each skill and rule file to load.
- Continue, agent_harness and the eval runner: the included rules' text in a closing `## Reference rules` section.
- An included rule whose gate fails in the repo drops silently.

## Output-contract patterns

| Need | Pattern |
| --- | --- |
| A verdict line | `'(?im)^\W*verdict\W*(ship\|hold)\W*$'` |
| A cited location | `'(?m)^\S+\.py:\d+:'` |
| Case-insensitive, multiline | Inline flags at the start: `(?i)`, `(?m)`, `(?im)` |

Write each regex in single-quoted YAML, where a backslash stays literal; a double-quoted string turns `\W` into an invalid escape.

## Read-only and scoped writes

- `write_scope: {read_only: true}` for a review or an explanation: it also renders natively restricted on Claude Code and OpenCode.
- `write_scope: {globs: ["tests/**/*.py"]}` when the task may edit only some files.

## Checklist

- The slash name is unique.
- Rules are listed by id in `includes_rules`, as a YAML list, never pasted.
- Each eval sample of this prompt names it in its `prompt_id`; the prompt does not list them.
- Each output-contract regex compiles, and the body asks for what it matches.
- In the engine's core layer, prompts' includes_rules stay frozen until the pilot ends.
