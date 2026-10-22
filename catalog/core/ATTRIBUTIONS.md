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
principles. The same article, credited the same way, gave the rationale of the
python-coding rules on small units, shallow nesting and error messages that
carry the offending value.

## python-best-practices

Source: the "python-best-practices" agent skills by Ludo Technologies LLC, tag v0.8.0.
Commit: `fa0d3f58afb8bf56c028bb559e0e7bc1538e079a`
License: MIT License. Copyright (c) 2026 Ludo Technologies LLC.

Its impact ratings inform each rule's section and priority. Ideas from it also
shaped the python-typing, python-docstrings,
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
| `skills/coding-standards/rules/error-no-silent-exceptions.md` | `rules/python-error-handling.md`, `rules/python-error-boundaries.md` | Engine frontmatter (kept id, lint codes and hook link); impact tag rendered from the section; References list dropped. Examples read text with `encoding="utf-8"` and `SettingsError` derives from the project base error. Notes absorb the engine's "what to catch", chaining, `assert` and logging points. The fixed "enable BLE001 and check-typed-exception" settings become "the repo's ruff settings decide". The boundary and documented-fallback notes (lines 45, 47) also feed `python-error-boundaries`. |
| `skills/coding-standards/rules/design-early-return.md` | `rules/python-early-return.md` | Retitled around shallow nesting (about two levels, one level of abstraction per function). The `Result(status=...)` strings become raised domain errors, and money totals use `Decimal`. The engine's named-predicate loop example joins the Good Example. "Order guards by likelihood for minor performance gains" (line 73) and the References list are dropped. |

Distilled (credited by name only, no vendored text):

- `rules/python-performance-idioms.md`
- `rules/python-async.md`
- `rules/python-classes-and-protocols.md`
- `rules/python-typing.md.j2`
- `rules/python-docstrings.md`
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
| `skills/clean-architecture/references/error-handling.md` | `rules/python-error-handling.md`, `rules/python-error-boundaries.md`, `rules/python-custom-exceptions.md` | Split by topic. Lines 5-44: the custom exceptions inherit the project base error instead of `Exception`, and the unclosed sqlite connection becomes a `with closing(...)` block. Lines 45-92 and 280-324: one `except` clause per failure mode and the "a broad catch hides real bugs" note; "simple subclasses of `Exception`" becomes "subclasses of the project base", and the broad-catch exception follows the engine's surfacing-recovery rule. Lines 104-128, 218-242 and 263-279: fail fast, catch only at entry points, let unknown errors propagate, kept stack-neutral (the FastAPI handler and status mapping belong to the web-application skill). The "acceptable retry decorator catching `Exception`" example (lines 93-103) is dropped. |
| `skills/clean-architecture/references/code-quality.md` | `rules/python-error-handling.md`, `rules/python-early-return.md` | Rule 12's blanket "never `except Exception`" is relaxed to the engine's surfacing-recovery rule (lines 160-178); rule 4's deep-nesting example becomes guard clauses and a per-item helper (lines 46-71). |
| `skills/clean-architecture/references/code-smells.md` | `rules/python-early-return.md` | Lines 253-275: only the detection line (more than two levels of nested `if`/`for`/`while`) is kept, as a Note. |
| `skills/clean-architecture/references/refactoring-case-studies.md` | `rules/python-error-handling.md`, `rules/python-error-boundaries.md`, `rules/python-early-return.md` | Move 8 (lines 210-231): the specific catch now chains with `raise ... from exc`. Move 14 (lines 352-373): "return one type from every path" becomes one Note under the engine's absence convention. Moves 1-2 (lines 15-62): guard clauses with `continue` and a named predicate. |
| `skills/clean-architecture/references/function-design.md` | `rules/python-error-boundaries.md` | Lines 63-99: "validate at entry points, trust validated values inside" kept; the return conventions are rewritten to the engine's absence convention, and no example uses `float` for a price. |

Distilled (credited by name only, no vendored text):

- `rules/python-dependency-injection.md`
- `rules/python-pure-core.md`
- `rules/python-data-shapes.md`
- `rules/python-idioms.md`
- `rules/python-classes-and-protocols.md`
- `rules/python-context-managers.md`
- `rules/python-retries-and-timeouts.md`
- `rules/python-typing.md.j2`

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
- `rules/python-error-messages-with-context.md`
- `rules/python-small-units.md`

### python-documentation

### python-testing

- `SKILL.md`

### python-tooling

- `SKILL.md`

### web-application

- `SKILL.md`
