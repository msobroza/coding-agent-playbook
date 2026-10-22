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
| `skills/web-application/rules/db-parameterized-queries.md` | `rules/sqlalchemy-bound-parameters.md` | Engine frontmatter (database section); title without the impact tag; References dropped; the `StrEnum` sort key became a `Literal` plus a column map (no Python version gate); one comment names `SessionDep`, `User` and `UserRead`; new Note on DB-API placeholders. |
| `skills/web-application/rules/db-session-per-request.md` | `rules/sqlalchemy-session-per-request.md` | Engine frontmatter (database section); References dropped; the Good example builds the engine in a real lifespan inside `create_app` (D27(1)) instead of pointing at another rule; the per-request report engine trimmed from the Bad example; Notes add the D27(1) and D27(2) sentences, provider chaining and the hotel example's files; cross-references became rule ids. |
| `skills/web-application/rules/db-transaction-boundary.md` | `rules/sqlalchemy-transaction-boundary.md.j2` | Engine frontmatter (database section); References dropped; the Good example loads the invoice with its own owner-scoped `select` and keyword-only ids, and one comment names its aliases; the FastAPI version claim became version-neutral; FastAPI-only teardown points phrased as such; the rollback Note says translate with `raise ... from`, never log and continue; Notes name python-context-managers, arch-unit-of-work and arch-effects-after-commit; one Note on the hotel example renders only for FastAPI. |
| `skills/web-application/rules/db-eager-loading.md` | `rules/sqlalchemy-eager-loading.md` | Engine frontmatter (database section); References dropped; the Good example declares the `Invoice` relationships it needs instead of pointing at another rule's model; Notes merge the upstream architecture guide's `back_populates`, cascade and loader rule of thumb; no hand-built nested dict serialization. |
| `skills/web-application/rules/db-migrations-alembic.md` | `rules/alembic-migrations.md` | Engine frontmatter (database section); References dropped; `Base` with the naming convention is defined here instead of in another rule; Notes add the D27(1) sentence for `env.py` and a proposal-only Note for repos without Alembic; cross-references became rule ids. |
| `skills/web-application/rules/db-sqlalchemy-2-style.md` | `rules/sqlalchemy-2-style.md.j2` | Engine frontmatter (database section); References dropped; the shared-model sentence dropped and the Good example trimmed to `Base`, `User` and `Invoice` (naming convention left to alembic-migrations); the mypy plugin Note became version-neutral; new SQLModel Note; one Note on the hotel example renders only for FastAPI. |
| `skills/web-application/rules/async-no-blocking-calls.md` | `rules/fastapi-no-blocking-calls.md` | Engine frontmatter (async-io section); References dropped; Description merges the engine's async-def-or-def guidance; `rates: dict[str, float]` became a frozen record of `Decimal` rates; thread-pool sizes became "both pools are bounded"; task queues only as proposals; Notes add `asyncio.run` inside a route, sync drivers and file I/O through `asyncio.to_thread` or `anyio.Path`, and name python-async. |
| `skills/web-application/rules/async-shared-http-client.md` | `rules/httpx-shared-client.md` | Engine frontmatter (async-io section); References dropped; the lifespan snippet is self-contained inside `create_app`; timeout, limits and key come from settings; `PaymentGatewayError` inherits the project base exception; the default-timeout Note became version-neutral; the backoff-library sentence became a pointer to python-retries-and-timeouts; Notes add the D27(2) sentence; cross-references became rule ids. |

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
| `skills/clean-architecture/references/async-patterns.md` | `rules/sqlalchemy-session-per-request.md`, `rules/fastapi-no-blocking-calls.md` | Lines 206-221 (`async_sessionmaker` with `expire_on_commit=False` and the yield provider) merged into sqlalchemy-session-per-request without the module-level engine and its inline DSN (D27(1)); lines 23, 35-60 (no `asyncio.run` in a route, `async def` versus `def`) and the route rows 374 and 377 of the common-mistakes table merged into fastapi-no-blocking-calls; `aiofiles` is not proposed. |
| `skills/clean-architecture/references/layered-architecture.md` | `rules/sqlalchemy-eager-loading.md`, `rules/alembic-migrations.md`, `rules/sqlalchemy-2-style.md.j2` | Lines 308-373 (relationships, cascade delete, eager-loading rule of thumb) merged into sqlalchemy-eager-loading's example and Notes, its nested `to_dict` (342-357) not vendored; lines 286-304 (`create_all` in the lifespan) confirm alembic-migrations' Bad example; lines 430-451 (SQLModel) became one sqlalchemy-2-style Note: table classes are not request or response schemas. |

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
