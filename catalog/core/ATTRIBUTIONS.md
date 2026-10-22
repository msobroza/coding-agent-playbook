# Attributions

This file is the only place in the shipped resources that credits outside
sources for the engine's own rules, references, scripts and prompts. Artifact
bodies carry no attribution. Attributions for the `find-injected-vuln-*` eval
fixtures live in `eval_samples/ATTRIBUTIONS.md`.

Core's Python guidance is vendored from the two MIT-licensed sources below: the
upstream text is copied and adapted (engine frontmatter, one topic per rule
file, the repository's own toolchain, no URLs, and every point where an engine
decision disagrees rewritten to that decision). Each table records, per core
skill, which core files every upstream file became and what changed, or `DROP`
with the reason it was left out. A file listed as distilled reuses ideas only,
with no upstream text, and is credited here by name.

Each core skill that holds a source's text ships that source's license notice,
byte-identical, as `references/LICENSE.<source>` (for example
`references/LICENSE.python-best-practices`). The Continue adapter writes no
skill directories, so its output carries no license copy.

Core paths in the tables are relative to the skill directory
(`catalog/core/skills/<skill>/`); a path ending in `/` covers every file under
that directory. Files the engine wrote with no upstream text are listed per
skill under "Engine-written files" at the end.

The code-legibility always rule (the eight principles it names, each pointing
at the skill rule that holds its detail) distills ideas from Akita, "Clean Code
para Agentes de IA" (2026-04-20), as reformulated by the engine's owner; it is
credited by name only. No sentences or examples from the article are copied;
the ideas are restated in the engine's own words as general clean-code
principles. The rationale of python-coding's `rules/python-meaningful-names.md`
(names that a search finds, the grep test) distills the same article the same
way.

python-coding's `rules/python-comments-why.md` distills one idea from the
matforge article on documentation best practices (comments that give the
reason), together with the engine owner's standing instruction to comment why,
not what; it is credited by name only and copies no text.

## python-best-practices

Source: the "python-best-practices" agent skills by Ludo Technologies LLC, tag v0.8.0.
Commit: `fa0d3f58afb8bf56c028bb559e0e7bc1538e079a`
License: MIT License. Copyright (c) 2026 Ludo Technologies LLC.

Its impact ratings inform each rule's section and priority. Ideas from it also
shaped the python-error-handling, python-typing, python-docstrings,
python-dependency-injection, python-data-shapes, python-idioms and pytest rules.

### design-patterns

| Upstream file | Core files | Changes |
| --- | --- | --- |

### ml-data

| Upstream file | Core files | Changes |
| --- | --- | --- |

Distilled (credited by name only, no vendored text):

- `rules/ml-vectorization.md.j2`
- `rules/ml-data-transforms.md.j2`
- `rules/ml-dtypes-and-typing.md.j2`
- `rules/ml-reproducibility-and-testing.md.j2`

### python-coding

| Upstream file | Core files | Changes |
| --- | --- | --- |
| `skills/coding-standards/rules/doc-type-hints.md` | `rules/python-typing.md.j2`, `rules/python-abstract-inputs.md`, `rules/python-type-aliases.md` | python-typing: the skeleton (Description, Bad/Good, Notes), widened from public APIs to every signature, `include_disabled` made keyword-only, the Bad/Good cut to `find_user`; engine frontmatter and lint codes, the generics and `Self` template branches (D40), the Any ladder, mutable defaults with `ClassVar` and named ignore codes added. python-abstract-inputs: the abstract-collections Note (54). python-type-aliases: the domain-alias Note (55), as NewType ids. The References list is dropped. |
| `skills/coding-standards/rules/doc-docstring.md` | `rules/python-docstrings.md` | The skeleton (Description, Bad/Good, Notes); the Good Example gains the required usage example, keeps Google sections as optional, makes `capture` keyword-only and is trimmed to one function plus a class line; engine frontmatter and lint codes, the definition of public, the four accepted example forms and units and limits added. The References list is dropped. |

Distilled (credited by name only, no vendored text):

- `rules/python-performance-idioms.md`
- `rules/python-async.md`
- `rules/python-classes-and-protocols.md`
- `rules/python-error-handling.md`
- `rules/python-dependency-injection.md`
- `rules/python-data-shapes.md`
- `rules/python-idioms.md`
- `rules/pydantic-boundaries.md`

### python-testing

| Upstream file | Core files | Changes |
| --- | --- | --- |

Distilled (credited by name only, no vendored text):

- `rules/pytest-test-doubles.md`
- `rules/pytest-fixtures.md`
- `rules/pytest.md.j2`

### python-tooling

| Upstream file | Core files | Changes |
| --- | --- | --- |

Distilled (credited by name only, no vendored text):

- `rules/python-static-checks.md`
- `rules/pytest-configuration.md`
- `rules/python-uv-workflow.md`

### web-application

| Upstream file | Core files | Changes |
| --- | --- | --- |

## python-clean-architecture

Source: the "python-clean-architecture" Claude Code plugin by MKToronto, 16 commits after version 0.8.1.
Commit: `9d627ca7bedbe0bb9e2fcf3c83d81814a6133dce`
License: MIT License. Copyright (c) 2025 MKToronto.
The plugin describes its concepts as inspired by Arjan Codes' courses.

Ideas from it also shaped the python-house-style always rule and the
review-architecture, make-testable, characterize, review and refactor prompts.

### design-patterns

| Upstream file | Core files | Changes |
| --- | --- | --- |

### ml-data

| Upstream file | Core files | Changes |
| --- | --- | --- |

### python-architecture

| Upstream file | Core files | Changes |
| --- | --- | --- |

### python-coding

| Upstream file | Core files | Changes |
| --- | --- | --- |
| `skills/clean-architecture/references/types-and-type-hints.md` | `rules/python-typing.md.j2`, `rules/python-abstract-inputs.md`, `rules/python-type-aliases.md` | python-typing: the Optional section (155-181) became two Notes (the pipe form instead of Optional, `-> None` for side-effect functions); the 3.12 generic-alias section (441-528) became the template's 3.12 branch with one generic `type` alias, without the float `PriceMap` money alias and the float generic-strategy `Order`; "annotate every function" (608-625) became the Description, its `list[dict[str, float]]` invoice replaced by pbp's typed `find_user`. python-abstract-inputs: the "overly specific types" trade-off (559-562, 579-594) became the Description and the Bad/Good pair, with string ids instead of float prices; the "broadest appropriate type" table (722-732) became the Notes table. python-type-aliases: the Callable section (201-314) became the skeleton, its int discount strategies rewritten as Decimal fee rules (no float money) and joined by NewType ids; "keep type definitions readable" (669-696) became the nested-type Note. Dropped: the type-system theory and hint tutorial (1-154), the float side-by-side (182-200), the cryptic-errors trade-off (529-558) and the int-vs-float `compute_pay` example (563-578), which shows money as float; every course-credit line. |
| `skills/clean-architecture/references/code-quality.md` | `rules/python-meaningful-names.md`, `rules/python-typing.md.j2` | python-meaningful-names: rule 2 "no vague identifiers" (21-32) became the Bad/Good names and the generic-words Note, rule 21 "no misleading method names" (330-346) the verb Note and the `add_line_item` example; rule 20's review angle (313-329) is left to design-name-for-intent. python-typing: rule 14 "no mutable default arguments" (202-217) confirms the mutable-default paragraph, its untyped `items: list` typed and its fix written as an explicit copy. |
| `commands/make-pythonic.md` | `rules/python-type-aliases.md` | The "single-method abstract class -> Callable alias" row (18) became one Note, limited to a real seam; the command's process and argument text are not carried. |

Distilled (credited by name only, no vendored text):

- `rules/python-dependency-injection.md`
- `rules/python-pure-core.md`
- `rules/python-data-shapes.md`
- `rules/python-idioms.md`
- `rules/python-classes-and-protocols.md`
- `rules/python-context-managers.md`
- `rules/python-retries-and-timeouts.md`
- `rules/python-error-handling.md`

### python-testing

| Upstream file | Core files | Changes |
| --- | --- | --- |

Distilled (credited by name only, no vendored text):

- `rules/pytest.md.j2`

### python-tooling

| Upstream file | Core files | Changes |
| --- | --- | --- |

### web-application

| Upstream file | Core files | Changes |
| --- | --- | --- |

Distilled (credited by name only, no vendored text):

- `rules/fastapi-app-wiring.md`
- `rules/fastapi-error-boundaries.md`

## Engine-written files

Files written for the engine with no upstream text, per core skill. A file
that comes to hold vendored text moves from here into its source's table.

### design-patterns

### domino-agents

### domino-apps

### domino-jobs

### ml-data

- `SKILL.md`
- `rules/ml-serialization-security.md.j2`

### playbook-creator

### playbook-guardrails

- `SKILL.md`

### python-architecture

### python-coding

- `SKILL.md`
- `rules/python-comments-why.md`

### python-documentation

### python-testing

- `SKILL.md`

### python-tooling

- `SKILL.md`

### web-application

- `SKILL.md`
