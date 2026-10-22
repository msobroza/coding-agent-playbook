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
principles.

## python-best-practices

Source: the "python-best-practices" agent skills by Ludo Technologies LLC, tag v0.8.0.
Commit: `fa0d3f58afb8bf56c028bb559e0e7bc1538e079a`
License: MIT License. Copyright (c) 2026 Ludo Technologies LLC.

Its impact ratings inform each rule's section and priority. Ideas from it also
shaped the python-error-handling, python-typing, python-docstrings,
python-dependency-injection, python-idioms and pytest rules.

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
| `skills/coding-standards/rules/oop-dataclass.md` | `rules/python-data-shapes.md`, `rules/python-frozen-dataclasses.md` | python-data-shapes: lines 8-79 are the skeleton (title, Description, Bad Example of a hand-written `__init__`/`__repr__`/`__eq__`/`__hash__`, Good Example with `default_factory` and slots): engine frontmatter; the Order's stored `_total` becomes a `@property` and its float discount a Decimal; the frozen Point moves to python-frozen-dataclasses; Notes merge the engine's record rules (no string dicts, no parallel lists, at most three tuple values, slots, Final constants vs the settings object) and a TypedDict-at-the-edge line. python-frozen-dataclasses: line 76 (frozen generates `__hash__`) joins its Description. Dropped: the derived `_total` stored in `__post_init__` and the float discount (54-59), because derived values are properties and money is never float (pbp-B#61, pbp-B#56), and 'consider attrs' (80), a new dependency (pbp-B19). |
| `skills/coding-standards/rules/oop-protocol.md` | `rules/python-protocols.md` | Lines 8-116 are the skeleton: engine frontmatter; the f-string JSON becomes `json.dumps`; the three-method Repository Protocol with `id` parameters becomes a two-method role-named InvoiceSender (repository ports are python-architecture's, pbp-B#60); a Callable alias is added for one behavior; the ABC Exporter shrinks to typed rows instead of `list[dict]`; 'When ABC is the right choice' and the Notes collapse into one ABC-vs-Protocol Note plus the engine's seam-only line. |
| `skills/coding-standards/rules/oop-property.md` | `rules/python-properties.md` | Lines 8-104 are the skeleton: engine frontmatter; trimmed to the Circle class and one cached_property example returning a typed record instead of `dict[str, float]`; error messages carry the offending value; the User example is dropped to fit; the cached_property note is reworded around the instance `__dict__`; the engine's 'keep properties cheap' and 'never functools.lru_cache on a method' points and a design-lazy-loading pointer are added. |

Distilled (credited by name only, no vendored text):

- `rules/python-performance-idioms.md`
- `rules/python-async.md`
- `rules/python-classes-and-protocols.md`
- `rules/python-error-handling.md`
- `rules/python-typing.md.j2`
- `rules/python-docstrings.md`
- `rules/python-dependency-injection.md`
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
| `skills/clean-architecture/references/classes-and-dataclasses.md` | `rules/python-data-shapes.md`, `rules/python-frozen-dataclasses.md`, `rules/python-dataclass-post-init.md`, `rules/python-hide-internal-state.md` | python-data-shapes: lines 96-226 (dataclass basics, simple and mutable defaults with the ValueError on a list literal, named default factories) become its Good Example's Cart and Notes, without reserve()'s print. python-frozen-dataclasses: lines 330-395 (when to freeze, the `__post_init__` limitation, default_factory before `object.__setattr__`) become Notes; the generated licence plate becomes a value derived from fields. python-dataclass-post-init: lines 257-329 (`field(init=False)`, validation in `__post_init__`, the default_factory vs `__post_init__` table) are the skeleton; the random plate becomes a search key computed from fields, a derived display name becomes a `@property`, and errors name the offending value. python-hide-internal-state: lines 396-464 (the underscore convention, `repr=False`, expose behavior and hide data) are the skeleton; accessories become a set, and find_by_plate gains a raising get_by_plate per the engine's absence convention. Dropped: the random licence plate as a default_factory (227-256), because randomness inside a record default breaks the pure core (pca-F13). Not vendored: the inspiration line (5). |
| `skills/clean-architecture/references/data-structures.md` | `rules/python-data-shapes.md`, `rules/python-enums.md` | python-data-shapes: lines 141-205 (tuples for two or three values, upgrading a long tuple to a dataclass) become a Note. python-enums: lines 257-340 (the problem with strings, the Enum solution, when to use, practical patterns) are the skeleton; the match gains a raising `case _`. Dropped: lines 405-454 (int vs float numerics), because money-never-float is the always-loaded house style, Decimal fields are pydantic-special-types' and numeric arrays belong to the ml-data skill. Not vendored: the inspiration line (5). |
| `skills/clean-architecture/references/code-quality.md` | `rules/python-data-shapes.md`, `rules/python-enums.md` | python-data-shapes: rule 6 (86-105, parallel data structures -> a record) and rule 11 (135-159, named constants including semantic ones, annotated Final) become Notes. python-enums: rule 1 (7-20, strings for fixed option sets) becomes its Description; its 'integers for money' half stays with the house style. |
| `skills/clean-architecture/references/code-smells.md` | `rules/python-data-shapes.md`, `rules/python-enums.md` | python-data-shapes: 2.3 and 2.4 (152-198, redundant instance variables -> a property, parallel data structures and the zip detection line) become Notes. python-enums: 1.1 (17-35, type abuse and its detection line) becomes a Note; `class Role(str, Enum)` becomes the version Note. |
| `skills/clean-architecture/references/refactoring-case-studies.md` | `rules/python-data-shapes.md`, `rules/python-enums.md` | python-data-shapes: move 5 (129-152, magic numbers -> module constants) becomes the constants Note, without its print calls. python-enums: move 6 (153-179, string comparisons with the 'scisssors' typo) becomes the Bad Example. |
| `skills/clean-architecture/references/types-and-type-hints.md` | `rules/python-protocols.md` | Lines 315-440 and 626-668 (nominal vs structural typing, the Protocol vs ABC table, Protocol as the default) condense into the Description and the ABC-vs-Protocol Note; the dict-based Repository example is not vendored (repository ports are python-architecture's). Not vendored: the inspiration line. |
| `skills/clean-architecture/references/design-principles.md` | `rules/python-protocols.md` | Lines 256-263 (the ABC vs Protocol table) merge with the types-and-type-hints table into one Note. |
| `commands/make-pythonic.md` | `rules/python-protocols.md`, `rules/python-data-shapes.md`, `rules/python-enums.md` | Line 17 (ABC hierarchy -> Protocol) is applied only within the engine's seam rule (pca-F1b); line 27 (manual `__init__` for data holders -> dataclass) and line 28 (bare string constants -> Enum or StrEnum) become Notes. |

Distilled (credited by name only, no vendored text):

- `rules/python-dependency-injection.md`
- `rules/python-pure-core.md`
- `rules/python-idioms.md`
- `rules/python-classes-and-protocols.md`
- `rules/python-context-managers.md`
- `rules/python-retries-and-timeouts.md`
- `rules/python-typing.md.j2`
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

### python-documentation

### python-testing

- `SKILL.md`

### python-tooling

- `SKILL.md`

### web-application

- `SKILL.md`
