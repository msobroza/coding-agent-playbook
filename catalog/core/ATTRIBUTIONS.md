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
| `skills/web-application/rules/api-bounded-lists.md` | `rules/web-api-pagination.md` | Engine frontmatter; impact tag and References dropped; one comment names the shared shapes and aliases (self-contained rule); the eager-loading option dropped from the Good example; Notes add one page envelope for every list endpoint and bound the offset form; query-parameter constraints named as `fastapi-query-parameters`'. |
| `skills/web-application/rules/api-error-responses.md` | `rules/fastapi-error-boundaries.md`, `rules/web-http-methods.md` | Merged into the engine's FastAPI error-boundaries rule, whose decisions all win: one exception-type-to-status table on the project base exception looked up along the MRO, unmapped errors re-raised to the default 500, never a handler on `Exception`, router `except` blocks as the one alternative style; per-class handlers replaced by the table; the debug-flag advice reworded as "never run production in debug mode"; cross-skill references in plain text; the success-status list moved to web-http-methods; the account-enumeration note left to the security rules. |
| `skills/web-application/rules/api-separate-schemas.md` | `rules/web-api-schemas.md.j2` | Engine frontmatter; gated on any web framework; one comment names the shared service and aliases; Notes add the update-model rule (`exclude_unset`, never `exclude_none`), secrets out of every Read model, `EmailStr`'s extra as a proposal, validator scope, SQLModel and other stacks, each owned elsewhere named in plain text; the example pointer renders only under FastAPI. |
| `skills/web-application/rules/app-factory-lifespan.md` | `rules/fastapi-app-wiring.md` | Kept id `fastapi-app-wiring` (split): the engine's lifespan, `app.state` provider and no-module-globals points lead the Description; the Good factory drops the CORS and middleware lines, reads the client timeout from settings, keeps the lifespan at module level and flat with `AsyncExitStack`, and adds the settings provider; Notes add the D27(1) sentence, liveness and readiness routes, and names the rules that own migrations, tests, router prefixes, providers and blocking calls; the router-prefix note moves to web-api-resource-naming. |
| `skills/web-application/rules/app-thin-routes.md` | `rules/fastapi-thin-routes.md`, `rules/fastapi-dependency-providers.md` | Split: the thin-route skeleton becomes fastapi-thin-routes (aliases shown only as a comment, keyword-only service parameters, `timezone.utc` for the Python 3.10 floor, the `/pay` path made a noun); the alias block and the `Annotated` preference move to fastapi-dependency-providers; "routes do not catch them" becomes the app's one mapping style; a no-derived-values clause added; cross-skill references in plain text. |
| `skills/web-application/rules/config-typed-settings.md` | `rules/fastapi-app-wiring.md` | Only the FastAPI wiring of settings (the `SettingsDep` provider, `create_app(Settings())` in the ASGI entrypoint, tests passing settings, the cached-getter remark) is kept; the settings class itself is left to the python-coding skill. |
| `skills/web-application/rules/obs-request-id-logging.md` | `rules/fastapi-request-id-logging.md` | Engine frontmatter; the service example trimmed to one structured log call; the middleware logs unhandled errors itself; a Note adds the D27(5) sentence and limits who sets the context variable; logging libraries and tracing become proposals, never added unasked. |
| `skills/web-application/rules/sec-object-authorization.md` | `rules/fastapi-dependency-providers.md` | Notes only (router-level auth dependency, per-request caching, roles as dependencies, tenant from the principal) for the provider rule; the rest of the file is left to the security rules. |
| `skills/web-application/rules/test-db-rollback.md` | `rules/sqlalchemy-test-rollback.md.j2` | Engine frontmatter; the event-loop setup and decorators branch on the repo's async test plugin (D27(4)); the test database URL read inside the fixture; one keyword-only factory with a precomputed hash; the in-memory SQLite stand-in rebuilt per test added as a counter-example; the D27(3) sentence added; testcontainers as a proposal; the example pointer renders only under FastAPI. |
| `skills/web-application/rules/test-dependency-overrides.md` | `rules/fastapi-dependency-overrides.md.j2` | Engine frontmatter; the async markers and fixture decorators branch on the repo's async test plugin (D27(4)); the settings fixture compressed into a comment; the Bad example keeps the no-effect patch and adds a global app, an import-time override and a global client; the login uses the password whose hash sqlalchemy-test-rollback's factory stores; overrides cleared in the fixture teardown (engine text); the D27(3) sentence added; asgi-lifespan and respx as proposals. |

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
| `commands/review-api-design.md` | `rules/web-api-schemas.md.j2`, `rules/web-api-pagination.md`, `rules/web-http-methods.md`, `rules/fastapi-dependency-providers.md` | The checklist only (D9): method semantics and status codes become web-http-methods, request and response checks web-api-schemas' Notes, list pagination web-api-pagination's, dependency injection for auth and sessions fastapi-dependency-providers'; the command frame, `$ARGUMENTS`, report format and plugin paths are dropped. |
| `skills/clean-architecture/SKILL.md` | `rules/web-api-schemas.md.j2` | Lines 56-71 only: separate Create and Read models per entity, with `exclude_none` replaced by `exclude_unset`. |
| `skills/clean-architecture/references/async-patterns.md` | `rules/fastapi-app-wiring.md` | Lines 156-172 only: the lifespan shape (acquire before `yield`, release after); its create-tables startup step is the migration rule's counter-example. |
| `skills/clean-architecture/references/error-handling.md` | `rules/fastapi-error-boundaries.md` | Lines 243-276 only: router `except` blocks as the accepted alternative style (never mixed with the table), and the route-level catch-all answering a hand-built 500 as the rule it forbids. |
| `skills/clean-architecture/references/layered-architecture.md` | `rules/web-api-schemas.md.j2`, `rules/fastapi-app-wiring.md`, `rules/fastapi-dependency-providers.md` | The Create/Read/Update trio (with `exclude_unset`) and the SQLModel trade-off go to web-api-schemas' Notes; the module-level app and engine to fastapi-app-wiring's Bad example (D27(1)); manual injection with `SessionLocal()` per endpoint to fastapi-dependency-providers' Bad example, provider functions as the composition root to its Good example. |
| `skills/clean-architecture/references/pydantic-validation.md` | `rules/web-api-schemas.md.j2` | Lines 336-386 and the one-model anti-pattern row: Create and Read models with validation, partial-update models, FastAPI's own 422; `exclude_none` replaced by `exclude_unset`. |
| `skills/clean-architecture/references/rest-api-design.md` | `rules/web-http-methods.md`, `rules/web-api-pagination.md`, `rules/fastapi-error-boundaries.md`, `rules/fastapi-app-wiring.md`, `rules/fastapi-thin-routes.md` | The CRUD route table and status codes become web-http-methods; one pagination shape web-api-pagination's Note; the duplicate answered with 400 becomes 409 in fastapi-error-boundaries; the health route fastapi-app-wiring's Note; router versus operations responsibilities fastapi-thin-routes' Description. |
| `skills/clean-architecture/references/testable-api.md` | `rules/fastapi-error-boundaries.md` | Lines 176-189 only: a router catching a domain error into `HTTPException`, as the alternative style; its `SessionLocal()` per endpoint is not kept. |
| `skills/clean-architecture/references/testing-advanced.md` | `rules/fastapi-dependency-overrides.md.j2`, `rules/sqlalchemy-test-rollback.md.j2` | The module-level override and global client become fastapi-dependency-overrides' Bad example and the in-memory SQLite schema rebuilt per test sqlalchemy-test-rollback's; endpoint tests cover HTTP only, business rules are tested without HTTP (plain text). |

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
