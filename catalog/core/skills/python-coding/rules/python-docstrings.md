---
id: python-docstrings
name: Docstrings
description: "Every public module, class and function gets a docstring: an intent line, then one usage example."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: types
priority: 44
tags: [python, docs]
lint_codes:
  warn: [D100, D101, D102, D103, D104, D105, D106, D107]
---

# Python docstrings

Give every new public module, class, function and method a docstring, and keep the ones that exist. A name is public when no part of its dotted path starts with `_`; a module is public when its file name does not.

## Layout

- The first line is one sentence that states the intent: what the caller gets, not how the body works.
- After a blank line, show one usage example.
- Document the error a caller must handle, and any non-obvious argument.
- Google-style `Args:`, `Returns:` and `Raises:` sections are optional: use them where the module already does. The intent line and the usage example are the required parts.
- Don't repeat in prose a type the annotation already states. Say what the value means, its units and its limits (`timeout_s`: seconds, at most 30).
- Update the docstring in the same change that alters the behavior, the parameters or the errors raised.

## Example forms

Any one of these counts as a usage example:

- a doctest line: `>>> load("config.toml")`;
- an `Example:`, `Examples:` or `Usage:` header followed by the call;
- a numpy-style `Examples` header underlined with `--------`;
- a reST literal block introduced by `::`, such as `Usage::`.

```python
def load(path: Path) -> Config:
    """Read the committed config at ``path``; raises ``ConfigError`` when it is malformed.

    Example::

        >>> load(Path(".coding-agent-playbook.toml")).project.name
        'demo'
    """
```

Do not add docstrings to private helpers to satisfy a count: a clear name is enough there.
