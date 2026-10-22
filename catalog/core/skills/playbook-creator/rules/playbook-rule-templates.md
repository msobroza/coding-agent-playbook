---
id: playbook-rule-templates
name: Rule templates
description: "Make a rule a .md.j2 template only when a detector fact changes part of its text, and branch through the helpers."
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
priority: 26
tags: [playbook, rules]
---

# Template a rule only where a fact changes its text

## Description

A `.md` body is used verbatim. A `.md.j2` body renders in a sandboxed Jinja environment where an undefined name fails loudly. Choose `.md.j2` only when a detector fact changes part of the text; when the whole rule applies or not, gate it instead (`playbook-rule-gates`).

The helpers take one name and return a bool:

- `has_framework('x')`, `has_ml_dep('x')`, `has_dependency('x')` (any runtime or dev dependency);
- `python_at_least('3.11')`: compares numerically, and is false when the version is unknown, so the `else` branch carries the Python 3.10 form.

Variables: every detector fact (`python_version`, `frameworks`, `dependencies` and so on), `project_name`, `project_description`, the init answers, `engine_version` and `layout` (the repo's document-layout directories). The frontmatter is never templated.

## Bad Example

Template source that compares versions as text and wraps a whole topic in a branch:

```markdown
{% if python_version >= "3.11" %}
Use `typing.Self` for fluent methods.
{% endif %}
{% if has_framework("fastapi") %}
## FastAPI dependencies
... the whole rule ...
{% endif %}
```

As text, "3.9" sorts after "3.11". The FastAPI rule renders empty everywhere else; gate it with `applies_if` instead.

## Good Example

A branch on the idiom the rule is about, with the 3.10 form in `else`:

```markdown
{% if python_at_least("3.11") %}
from typing import Self

def with_name(self, name: str) -> Self: ...
{% else %}
from typing import TypeVar

T = TypeVar("T", bound="Builder")

def with_name(self: T, name: str) -> T: ...
{% endif %}
```

## Notes

- A fact the detector did not set is undefined and fails the render: branch on the helpers, which never fail, or guard a raw fact with `is defined`.
- Branch only where the idiom is the rule's topic; an incidental newer form gets a 3.10 example plus a Note.
- Every branch stays within 100 lines and 750 words; in the engine every core template is rendered across a fact matrix.
- A pointer to another skill's file sits inside a branch that tests the same fact as that file's gate.
- Read `layout` only where the text must name this repo's configured directory; elsewhere write the default path, which sync rewrites (`playbook-rule-body`).
- Prompts list the rules they need in `includes_rules`; no template places another rule's text. The old inclusion helper is gone and validate rejects a body that calls it.
