---
id: python-comments-why
name: Comments that say why
description: "A comment explains what the code cannot say itself, such as a constraint, a workaround or a trade-off, and never restates the code."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: types
priority: 45
tags: [python, docs]
---

# Comments that say why

## Description

Code already says what it does; a comment earns its place by saying why. Write one where a reader would otherwise have to rediscover the reason: an outside constraint, a workaround for a bug elsewhere (with its issue or commit), or a trade-off that looks wrong until you know what it buys. A comment that narrates the next line adds reading time and nothing else, and once the code changes it turns into a wrong statement that the next reader, person or agent, may trust over the code.

## Bad Example

```python
# increment i
i += 1

# retry three times
for attempt in range(5):
    send(batch)

# loop over the pages
for page in range(1, total_pages + 1):
    rows.extend(fetch_page(page - 1))
```

The first comment restates the line, the second contradicts the code below it, and the third hides the one fact that matters: why the page number is shifted.

## Good Example

```python
# The billing API numbers pages from 0 (issue 412): convert here, once.
for page in range(1, total_pages + 1):
    rows.extend(fetch_page(page - 1))

# Five attempts cover the provider's documented 2-second failover window.
for attempt in range(5):
    send(batch)
```

## Notes

- Keep rationale comments through refactors: when you move or rewrite the code a comment explains, move or update the comment with it, and delete it only when the reason is gone.
- Delete comments that only narrate what the code does; if the code needs narration, rename or extract it until it does not.
- A comment that names a workaround names where it is tracked (an issue number or a commit), so the next reader can check whether it still applies.
- Commented-out code is not a comment: delete it, version control keeps it.
- Docstrings, which describe the contract of a public name, are `python-docstrings`; a decision that spans modules belongs in a decision record (`docs-record-why`, python-documentation skill).
