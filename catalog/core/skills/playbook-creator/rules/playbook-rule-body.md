---
id: playbook-rule-body
name: Rule body
description: "Write one topic per rule: an imperative title, then Description, Bad Example, Good Example and Notes, within 100 lines."
version: 1
scope: scoped
globs:
  - "catalog/**/rules/**/*.md"
  - "catalog/**/rules/**/*.md.j2"
  - "playbook/**/rules/**/*.md"
  - "playbook/**/rules/**/*.md.j2"
  - "src/*/resources/**/rules/**/*.md"
  - "src/*/resources/**/rules/**/*.md.j2"
applies_if:
  playbook_layer: true
section: rules
priority: 27
tags: [playbook, rules]
---

# Write one self-contained topic per rule body

## Description

A rule body holds one topic: an imperative `# Title` without an impact tag (the engine renders the tag from the rule's section), then `## Description`, `## Bad Example`, `## Good Example` and `## Notes`. Every branch renders to at most 100 lines and 750 words; longer material becomes a reference of the same skill.

Code examples are complete enough to read alone. They pass ruff format and parse (docs-check parses Python blocks), and follow the always rules: type hints on every signature, `encoding="utf-8"` on file I/O, typed records between layers, no float money, keyword-only flags. When two rules need the same example, each repeats or replaces it rather than depending on the other's.

## Bad Example

```markdown
# Retry Budgets [HIGH]

Retries must be bounded.

(a paragraph pasted from another rule)

## Notes

- See the async rule in the other skill's own file for timeouts.

## References

- A list of links to blog posts
```

An authored impact tag, a pasted paragraph that drifts from its owner, a pointer into another skill's files, and a links list that every harness renders as dead text.

## Good Example

````markdown
# Bound every retry loop

## Description

Retry only transient failures, at most three times, with a timeout on each call.

## Bad Example

```python
while True:
    response = client.get(path)
```

## Good Example

```python
for _attempt in range(3):
    response = client.get(path, timeout=5.0)
```

## Notes

- Timeouts per call: `acme-http-timeouts`.
````

## Notes

- Name other rules by id in backticks. Name a rule of another skill only when this rule's gate guarantees that rule renders too; otherwise the name dangles.
- Name a reference of the same skill by its bare file name, and an example file as examples/<app>/<file>, in plain text in Notes: Continue receives rules without references.
- In core, plugin and overlay content, write document-layout paths in their default form (docs/specs/, docs/plans/, docs/adr/); sync rewrites them for a repo with its own `[layout]`. `playbook/` content is not rewritten, so it uses this repo's configured paths.
- No URL in prose; in core skills only reserved example hosts, and only inside code blocks. Describe a banned URL form in words, never with its literal scheme separator.
- No upstream source or author name outside ATTRIBUTIONS and the license copies.
- No dropped-recommendation token anywhere, not even inside a prohibition: the engine's scan is a literal substring match.
- A rule never includes another rule.
- rule-template.md has the body skeleton and a checklist.
