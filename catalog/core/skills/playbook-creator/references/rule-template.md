# Rule template

Copy the block that matches the rule you are starting, replace every `<placeholder>`, delete the comments, then run `playbook validate`. Each block names the rule of this skill that explains its keys; read that rule when a choice is unclear.

## Contents

- Member rule inside a skill
- Rule joining another layer's skill
- Always rule
- Template variant
- Priority bands
- Predicate keys
- Checklist before validate

## Member rule inside a skill

`<layer>/skills/<skill>/rules/<id>.md`. Keys: `playbook-rule-frontmatter`; id: `playbook-rule-ids`; gate: `playbook-rule-gates`; body: `playbook-rule-body`. A member never declares `skill:`: its directory makes it one.

```markdown
---
id: <prefix>-<topic>          # equals the file stem; kebab case, at most 64 characters
name: <Topic label>           # short; the index row is "<name>: <description>"
description: "<One actionable sentence ending with a period.>"
version: 1                    # bump on a breaking change
scope: scoped                 # lowercase
section: <section-id>         # declared in the skill's playbook: block
priority: <band floor + rank> # inside the section's band (table below)
globs: ["src/**/*.py"]       # the skill nudge and Continue's attachment, never a gate
applies_if:                   # optional; ANDed keys on detector facts, tags optional too
  any_dependency: [<name>]
---

# <Imperative title, no impact tag>

## Description
<What to do and why, for one topic.>

## Bad Example
<A complete, formatted snippet, then one sentence on what goes wrong.>

## Good Example
<The same snippet, fixed.>

## Notes
- <Edge cases; other rules by id in backticks; a guide of this skill by its bare file name.>
```

## Rule joining another layer's skill

`<layer>/rules/<file>.md` (`playbook-layer-placement`). The same frontmatter, plus the skill it joins:

```yaml
skill: <skill-id>     # a skill with a playbook: block, in any layer
section: <section-id> # one of that skill's section ids (`playbook-skill-sections`)
priority: <n>         # inside that section's band
```

## Always rule

`<layer>/rules/<file>.md`; core keeps them as `rules/always/NN-<id>.md`. It is in every turn's context, so keep it to a few bullets, with no `skill`, `section` or `globs`:

```markdown
---
id: <prefix>-<topic>
name: <Topic label>
description: "<One sentence.>"
scope: always
priority: <n>
---
- <One short instruction per bullet.>
```

## Template variant

Name the file `<id>.md.j2` only when a fact changes part of the text (`playbook-rule-templates`). The frontmatter stays static; the body branches:

```markdown
{% if python_at_least("3.11") %}
Use `typing.Self` as the return type of a fluent method.
{% else %}
Bind a `TypeVar` to the class and return it.
{% endif %}
{% if has_framework("fastapi") %}
In a route, take the value through a dependency.
{% endif %}
```

Helpers, one name each: `has_framework`, `has_ml_dep`, `has_dependency`, `python_at_least`. Variables: every detector fact, `project_name`, `project_description`, the init answers, `engine_version`, `layout`.

## Priority bands

| Impact | Band | Ranks |
| --- | --- | --- |
| CRITICAL | 20-39 | Band floor plus the rule's rank among the skill's rules of this impact, in index order |
| HIGH | 40-59 | The same; inserting a rule renumbers the rest of the band |
| MEDIUM | 60-79 | The same; validate checks only that the priority lies in the band |
| LOW | 80-99 | The same; a band holds 20 ranks |

## Predicate keys

| Key | Value shape | Example |
| --- | --- | --- |
| `python_version` | A comparison string | `">=3.10"` |
| `has_framework`, `any_framework` | A list of detector frameworks: `fastapi`, `flask`, `django`, `starlette`, `pydantic`, `sqlalchemy`, `alembic`, `httpx`, `requests`, `aiohttp`, `click`, `typer`, `pytest`, `pytest-asyncio`, `pytest-mock`, `unittest` | `[fastapi]` |
| `has_ml_stack`, `any_ml_stack` | A list: `numpy`, `pandas`, `polars`, `torch`, `tensorflow`, `jax`, `transformers`, `scikit-learn`, `xgboost`, `lightgbm`, `matplotlib`, `seaborn`, `duckdb` | `[numpy, pandas]` |
| `has_dependency`, `any_dependency` | A list of normalized dependency names | `[sqlalchemy]` |
| `has_dev_dependency` | A list of dev dependency names | `[ruff]` |
| `has_file`, `any_file` | A list of repo-relative paths | `[catalog/core]` |
| `package_manager` | A name, or a list meaning any | `uv` |
| `has_notebooks`, `has_dockerfile`, `has_ci`, `domino_project`, `playbook_layer` | `true` | `true` |

The trap: a list key written as a bare string (`any_framework: fastapi`) fails validate; write `[fastapi]`.

## Checklist before validate

- The id equals the file stem, is unique in the layer and is never a retired id.
- The section is declared by the skill, and the priority lies in its band. Every gate key is known, list keys hold lists, and booleans gate on `true`.
- Each branch renders to at most 100 lines and 750 words; code blocks are formatted and parse.
- No URL, link or upstream source name; other rules are named by id; a guide is named by file name in Notes.
