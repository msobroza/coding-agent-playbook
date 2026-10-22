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
para Agentes de IA" (2026-04-20), as reformulated by the engine's owner, and
so does the opening rationale of design-patterns' design-single-responsibility
rule; both are credited by name only. No sentences or examples from the article are copied;
the ideas are restated in the engine's own words as general clean-code
principles.

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
| `skills/coding-standards/SKILL.md` | `SKILL.md` | Lines 13 and 154-160 only: the intro, rewritten for the skill's scope, and the open/closed and interface-segregation snippets of the Design Patterns quick reference; the dependency-injection and early-return snippets belong to python-coding. |
| `skills/coding-standards/rules/design-single-responsibility.md` | `rules/design-single-responsibility.md` | Engine frontmatter; title without the impact tag; the password-hashing step and its notes (25, 49-55, 94) replaced by a neutral collaborator (web-application owns password hashing); collaborators are plain classes, not dataclasses; Description opens with why one responsibility helps every reader, people and agents (distilled, see above); Notes gain the core warning signs, function-level splits and the coordinator and script exceptions; References list (96-97) dropped. |
| `skills/coding-standards/rules/solid-ocp.md` | `rules/design-open-closed.md` | Engine frontmatter; `format: str` renamed and typed as an Enum; Good Example leads with an Enum-keyed mapping of Callables and keeps the Protocol classes for multi-method variants; Notes add isinstance ladders, rules as data, singledispatch and the restraint lines; References list (61-63) dropped. |
| `skills/coding-standards/rules/oop-composition-over-inheritance.md` | `rules/design-composition-over-inheritance.md` | Engine frontmatter; behaviors return strings instead of printing; the Employee hierarchy pair (27-38, 74-84) cut for size; 'mixins ... use sparingly' (91) replaced by the engine's mixin and framework-base lines; Bad and Good Examples gain the inherit-for-reuse store and the value-only subclass; References list (93-94) dropped. |
| `skills/coding-standards/rules/solid-lsp.md` | `rules/design-liskov-substitution.md` | Engine frontmatter; the missing Sparrow defined in both examples; Notes restated as the engine's three-part contract and warning signs, plus substitution as a test, not a ban; References list (64-66) dropped. |
| `skills/coding-standards/rules/solid-isp.md` | `rules/design-interface-segregation.md` | Engine frontmatter; Notes gain the engine's split trigger, the no-symmetry-split line and Protocol segregation; the oop-protocol cross-reference points to python-coding; References list (76-78) dropped. |

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

Distilled (credited by name only, no vendored text):

- `rules/python-performance-idioms.md`
- `rules/python-async.md`
- `rules/python-classes-and-protocols.md`
- `rules/python-error-handling.md`
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
| `skills/clean-architecture/SKILL.md` | `SKILL.md` | Lines 73-83 and 85-122 only: the seven principles one line each, mapped to this skill's sections (the mixin ban, 80, dropped: engine wins, F1), and the smell-to-pattern table merged with the engine's lightest-form table ('signal, lightest form, heavier form, stop when, pattern'); the singleton, value-object, registry, notification and plugin rows rewritten to the engine decisions (F9, F14, F10); repository, unit of work, CQRS, event sourcing and retry rows name their owning skills; the default preferences as bullets. |
| `skills/clean-architecture/references/design-principles.md` | `rules/design-single-responsibility.md`, `rules/design-tell-dont-ask.md`, `rules/design-low-coupling.md`, `rules/design-dependency-inversion.md`, `rules/design-open-closed.md`, `rules/design-composition-over-inheritance.md` | Lines 5-35 and 55-87 become function-level split notes; the Law of Demeter and Information Expert (164-175, 429-447) the tell-don't-ask examples; the coupling ladder, global-coupling example and trade-off chain (90-163, 176-215) the low-coupling rule, with no literal token and no real host, settings built once by the entry point, and the stamp-coupling Protocol shrunk to one note; 'Depend on Abstractions' (216-255) the dependency-inversion skeleton with a Callable alias owned by the consumer; dictionary mapping as OCP (419-421) a note; configuration vs subclass and the composition pattern (276-345) the composition rule, pay in int cents, the mixin ban (342) dropped (engine wins, F1). |
| `skills/clean-architecture/references/grasp-principles.md` | `rules/design-tell-dont-ask.md`, `rules/design-split-god-class.md`, `rules/design-grasp-responsibilities.md`, `rules/design-low-coupling.md`, `rules/design-dependency-inversion.md`, `rules/design-open-closed.md` | Creator, Controller, Indirection and Pure Fabrication (17-38, 70-97, 173-202, 228-249) become the GRASP rule: an injected date instead of date.today(), Decimal rates instead of float, a thin handler without a web framework; Information Expert and its caveat (44-69) go to tell-don't-ask; low-cohesion signs (128-140) to the god-class rule without fixed counts (F30); the net-price example (102-127) to a low-coupling note in Decimal; Polymorphism (144-172) to open-closed; Protected Variations (206-227) to a dependency-inversion note. Course attribution and the three-layer and DBInterface asides (5, 40, 98, 124, 224, 250) dropped (python-architecture owns layering). |
| `skills/clean-architecture/references/code-quality.md` | `rules/design-tell-dont-ask.md`, `rules/design-split-god-class.md`, `rules/design-open-closed.md` | Tell-don't-ask and feature envy (72-85, 110-113) the tell-don't-ask skeleton, with an Enum status and a domain error; no god classes (106-109) the god-class rule; isinstance dispatch (266-284) an open-closed note. |
| `skills/clean-architecture/references/code-smells.md` | `rules/design-tell-dont-ask.md`, `rules/design-split-god-class.md`, `rules/design-liskov-substitution.md` | Tell-don't-ask violations (276-298) the feature-envy example; too many instance variables (112-151) a note on splitting a record, without the fixed count (F30); subclasses that break substitution (334) a Liskov warning sign. |
| `skills/clean-architecture/references/refactoring-case-studies.md` | `rules/design-tell-dont-ask.md`, `rules/design-open-closed.md` | Encapsulate data-structure access (232-249) a tell-don't-ask note; rules consolidated into a list of predicates (180-209) an open-closed note, as a role-named Callable alias. |
| `skills/clean-architecture/references/dependency-injection.md` | `rules/design-dependency-inversion.md` | The DI-vs-DIP framing (3) and table (32-50) restated in prose; the Bad Example is DI without DIP, a vendor class imported by the consumer. Title and attribution lines (1, 5, 250) dropped. |
| `skills/clean-architecture/references/patterns/template-method.md` | `rules/design-interface-segregation.md` | Protocol segregation (251-321) and the 4-5 method heuristic (342) as notes, without endorsing or banning mixins. |
| `commands/decouple.md` | `rules/design-tell-dont-ask.md`, `rules/design-low-coupling.md` | Checklist items only (15-17): global mutable state, content coupling and Law of Demeter violations, as notes; command frontmatter, $ARGUMENTS and plugin paths dropped (D9). |
| `commands/extract-god-class.md` | `rules/design-split-god-class.md` | Steps 13-34 as a non-interactive procedure: propose the split, apply it only when asked; AskUserQuestion and auto-apply (35-39, F28), frontmatter and plugin paths (1-11) dropped. |
| `commands/make-pythonic.md` | `rules/design-composition-over-inheritance.md` | Smell row 19 (deep inheritance or mixins -> composition with a Protocol) as the rule's premise, with mixins per the engine line (F1). |

### ml-data

| Upstream file | Core files | Changes |
| --- | --- | --- |

### python-architecture

| Upstream file | Core files | Changes |
| --- | --- | --- |

### python-coding

| Upstream file | Core files | Changes |
| --- | --- | --- |

Distilled (credited by name only, no vendored text):

- `rules/python-dependency-injection.md`
- `rules/python-pure-core.md`
- `rules/python-data-shapes.md`
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

- `scripts/detect_smells.py`
- `scripts/lcom4_clusters.py`

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
