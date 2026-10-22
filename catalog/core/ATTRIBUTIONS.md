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
| `skills/coding-standards/rules/async-gather.md` | `rules/python-async.md.j2` | Lines 8-65 are the skeleton (Description, Bad Example of sequential awaits, Good Example, Notes): engine frontmatter, now a template with no version gate (D40); the Good Example leads with the engine's TaskGroup and except* on Python 3.11 and later and renders gather under wait_for below; the return_exceptions=True example keeps the CancelledError re-raise but logs each failure with exc_info instead of logger.error then continue; tuple[dict, dict, dict] and dict[str, dict] results become typed records (Dashboard, Quote). Notes keep CancelledError as a BaseException, siblings left running by plain gather and one deadline per group. The References list is dropped. |
| `skills/coding-standards/rules/async-create-task.md` | `rules/python-async-tasks.md.j2` | Lines 8-77 are the skeleton: engine frontmatter, a template on python_at_least('3.11'); the discarded create_task Bad Example is kept with typed collaborators; the engine's BackgroundJobs supervisor, built and closed by the composition root, replaces the module-level background_tasks set; TaskGroup ownership on 3.11 and later, a task list cancelled in finally below. Notes keep the done-callback boundary, awaiting a task directly, cancellable tasks and the set[asyncio.Task[None]] annotation; set_debug becomes the PYTHONASYNCIODEBUG=1 debug mode. Dropped: the module-level background_tasks set (34-35), because nothing closes it and tests share it (pbp-B#49). The References list is dropped. |
| `skills/coding-standards/rules/async-semaphore.md` | `rules/python-async-fanout.md.j2` | Lines 8-36 and 63-69 are the skeleton: engine frontmatter, a template on python_at_least('3.11'); the 10,000-request Bad Example becomes the engine's quote_parcels case; the function-scoped semaphore is sized from settings instead of a literal default of 10; Notes keep the wrong-loop RuntimeError, BoundedSemaphore, release on raise, Queue workers and client connection limits (httpx added beside aiohttp). Dropped: the per-loop WeakKeyDictionary semaphore cache and its import (26, 37-61), replaced by building the semaphore on the loop that uses it. The References list is dropped. |
| `skills/coding-standards/rules/validation-pydantic.md` | `rules/pydantic-boundaries.md`, `rules/pydantic-field-constraints.md`, `rules/pydantic-typed-settings.md`, `rules/pydantic-special-types.md` | pydantic-boundaries: lines 8-57 and 70-77 are the skeleton; the FastAPI endpoint becomes a stack-neutral queue consumer parsing with model_validate_json and translating ValidationError once; the untyped dict Bad Example is kept; EmailStr carries the email-validator extra note; the FastAPI note becomes a plain-text pointer to the web-application skill. pydantic-field-constraints: lines 74-75 (Field limits over hand-written ifs, after vs before validator order) become Notes. pydantic-typed-settings: the settings block (58-67) joins its Good Example with SecretStr secrets and no debug flag. pydantic-special-types: line 37's EmailStr becomes the email-validator Note. The References list is dropped. |
| `skills/web-application/rules/config-typed-settings.md` | `rules/pydantic-typed-settings.md` | Lines 8-51, 59-66, 68 and 70-71 are the skeleton, made stack-neutral: engine frontmatter; one BaseSettings class built once in main() and passed in; Field(default_factory=list) instead of `= []`; signing and payments keys stay SecretStr; tests build Settings(...) instead of patching the environment; .env and nested-settings Notes kept. Not vendored here: the FastAPI SettingsDep, app.state and create_app(Settings()) wiring (52-58, 68's create_app half) and the lru_cache get_settings note (69), which belong to the web-application skill's fastapi-app-wiring, and the mypy plugin note (67), which is the python-tooling skill's mypy-type-checking; each is one plain-text pointer. The References list is dropped. |

Distilled (credited by name only, no vendored text):

- `rules/python-performance-idioms.md`
- `rules/python-classes-and-protocols.md`
- `rules/python-error-handling.md`
- `rules/python-typing.md.j2`
- `rules/python-docstrings.md`
- `rules/python-dependency-injection.md`
- `rules/python-data-shapes.md`
- `rules/python-idioms.md`

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
| `skills/clean-architecture/references/async-patterns.md` | `rules/python-async.md.j2`, `rules/python-async-generators.md` | python-async: lines 9-33 (asyncio.run only at the entry point), 64-109 (gather vs TaskGroup, its 'partial success' row rewritten to require return_exceptions=True, pca-F12) and the general rows of 370-382 (time.sleep, sequential awaits, a forgotten await, sync I/O moved off the loop with asyncio.to_thread instead of aiofiles) become Notes and the Good Example; the asyncio.run-in-a-route and sync-driver-in-a-handler rows stay with the web-application skill's fastapi-no-blocking-calls, named in plain text. python-async-generators: lines 176-205 are the skeleton; pages and items become typed records, the return type is AsyncIterator[OrderPage], and the Bad Example (every page collected first), the contextlib.aclosing Note and the per-request timeout pointer are added (pca-F16). The inspiration line is not vendored. |
| `skills/clean-architecture/references/pydantic-validation.md` | `rules/pydantic-boundaries.md`, `rules/pydantic-field-constraints.md`, `rules/pydantic-model-validators.md`, `rules/pydantic-serializers.md`, `rules/pydantic-special-types.md`, `rules/pydantic-typed-settings.md` | pydantic-field-constraints: lines 11-144 (numeric, string and collection constraints, field metadata, after and before field validators, one validator for several fields) and 252-280 (ConfigDict options; from_attributes left to the web-application skill) become Notes beside the engine's ShipmentRequest; float tax_percent is not carried. pydantic-model-validators: lines 1-10 and 145-199 are the skeleton (the DateRange example becomes StayRequest; the before validator only reshapes input; 'business rule validation' becomes input invariants only, pca-F5; the Self note becomes version-neutral). pydantic-serializers: lines 200-251 are the skeleton; untyped serializer and info parameters get pydantic types; the password-dropping model_serializer is replaced by a reshaping one, since SecretStr already masks and response models are the web-application skill's web-api-schemas. pydantic-special-types: lines 297-335 are the skeleton; PositiveFloat balance becomes Decimal (pca-F14); `pip install pydantic[email]` becomes 'propose the extra' (pbp-B#2). pydantic-typed-settings: lines 281-296 join the Bad Example, fixed to SettingsConfigDict without empty-string secrets (pca-F19). pydantic-boundaries: anti-pattern rows 393 and 395 become a Note; row 394 is web-api-schemas'. Not vendored: the inspiration lines (7, 332), the 'Arjan's preferred convention' sentence and the three-layer patterns (336-385), owned by the web-application skill. |
| `skills/clean-architecture/references/layered-architecture.md` | `rules/pydantic-typed-settings.md` | Lines 409-421 (the BaseSettings class with ConfigDict(env_file) and a default database URL for a per-environment value) become the Bad Example's settings class, annotated with what is wrong (pca-F19). Lines 422-426 (a module-level settings instance imported by db/database.py) are the python-architecture skill's sqlalchemy-engine-and-session-scope Bad Example; this rule states only the stack-neutral ban. |

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
