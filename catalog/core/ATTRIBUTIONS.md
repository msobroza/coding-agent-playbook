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
principles. The same article, credited the same way, gave the rationale of the
python-coding rules on small units, shallow nesting and error messages that
carry the offending value.
The rationale of python-coding's `rules/python-meaningful-names.md`
(names that a search finds, the grep test) distills the same article the same
way.

python-coding's `rules/python-comments-why.md` distills one idea from the
matforge article on documentation best practices (comments that give the
reason), together with the engine owner's standing instruction to comment why,
not what; it is credited by name only and copies no text.

The domino-apps skill (its SKILL.md and every rule under its rules/
directory, listed under "Engine-written files") distills facts from the
Domino Data Lab 6.2 user and admin documentation, which carries no open
license; it is credited by name only and not vendored. No sentences or
examples from the documentation are copied, its unsafe example settings are
not reproduced, and the facts are restated in the engine's own words. The
`domino-docs` section below records, per documentation page, the files that
use its facts or why it was dropped; a distilled source has no pin and no
license copy.

The domino-agents skill's SKILL.md and rules draw on two sources, each
credited by name only. The Domino Data Lab 6.2 documentation (the
agentic-systems user guide pages, the Apps pages, the python-domino agents API
guide and the environment variable reference) carries no open license, so its
facts are distilled (D50): restated in the engine's own words, with no sentence
or code copied. Domino Data Lab's `simple_agent_api_only` example agent is
Apache-2.0 licensed (commit `eee728252c42fa660e65c2dccbea6ae4f679c04c`); the
rules take only ideas from it, with no sentence or code copied, so they hold no
upstream text. Neither source has a pinned section above, so the rules are
listed under "Engine-written files", with the upstream files the secrets and
service rules draw on and the upstream text they leave out; the adapted example
app, which does hold that repository's code, is credited with its license copy
and change list when it is vendored.

The domino-jobs skill (its SKILL.md and every rule under its rules/
directory, listed under "Engine-written files") distills facts from the
Domino Data Lab 6.2 user, admin and API documentation, which carries no open
license; it is credited by name only and not vendored. No sentences or
examples from the documentation are copied, and the facts are restated in the
engine's own words. The `domino-docs` section below records, per
documentation page, the files that use its facts or why it was dropped; a
distilled source has no pin and no license copy.

## python-best-practices

Source: the "python-best-practices" agent skills by Ludo Technologies LLC, tag v0.8.0.
Commit: `fa0d3f58afb8bf56c028bb559e0e7bc1538e079a`
License: MIT License. Copyright (c) 2026 Ludo Technologies LLC.

Its impact ratings inform each rule's section and priority. Ideas from it also
shaped the python-typing, python-docstrings, python-data-shapes, python-idioms and
pytest rules.

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
| `skills/coding-standards/rules/design-dependency-injection.md` | `rules/python-dependency-injection.md` | Lines 8-62 are the skeleton (title, Description, Bad and Good Example): engine frontmatter; vendor names become neutral (CardGateway, SqlOrderStore); the three Protocols shrink to a consumer-owned Protocol plus Callable parameters; the Mock(spec=...) test becomes a named-fake test. Notes merge the engine's seam-only, few-values and named-fake points and the D27(2) route-edge sentence; the engine's Checkout/LegacyCheckout pair is carried by the OrderProcessor Bad/Good pair (a hard-wired mailer vs role-named Callable aliases). Dropped: the Mock(spec=...) and assert_called_once_with test (64-73) and 'consider DI containers' (79), because tests pass named fakes and an existing container stays in the composition root (pbp-B#28, pbp-B#31). |
| `skills/coding-standards/rules/design-pure-functions.md` | `rules/python-pure-core.md` | Lines 8-79 are the skeleton: engine frontmatter; float prices become Decimal; the status string becomes an Enum member; mark_processed uses dataclasses.replace; the shell reads the date once. Notes merge the engine's inputs-as-arguments, no I/O in domain classes, naming in-place mutators and freeze-time points, and the D27(5) ContextVar sentence; the legacy clock read uses timezone.utc (Python 3.10 floor). |
| `skills/coding-standards/rules/design-no-global-singleton.md` | `rules/python-no-global-singletons.md` | Lines 8-114 are the skeleton: engine frontmatter; trimmed to fit (no Settings dataclass, no Protocol stubs, no fake-based test, which python-dependency-injection shows); the engine's metaclass, caching __new__ and registry ban added; the last Note reworded to 'patching module globals'; the D27(1) and D27(5) sentences added; the composition-root mechanics become a pointer to arch-composition-root. |
| `skills/coding-standards/rules/async-context-manager.md` | `rules/python-context-managers.md`, `rules/python-custom-context-managers.md` | Lines 8-62 are python-context-managers' skeleton: engine frontmatter; a sync Bad/Good pair added; dict returns become typed records; the Good example receives the aiohttp session, opened with a timeout from settings in the entry point, instead of opening an untimed one per call; Notes merge the engine's closing(), ExitStack, narrow-block, suppress and commit-only-on-success points. Lines 59-60 (__aenter__/__aexit__, asynccontextmanager) become a python-custom-context-managers Note. |
| `skills/web-application/rules/db-parameterized-queries.md` | `rules/python-parameterized-queries.md` | Description, Bad/Good structure and Notes copied and generalized from SQLAlchemy to DB-API drivers: sqlite3 '?' placeholders in the examples, psycopg and asyncpg placeholders in a Note, sort columns from an allow-list mapping, LIKE wildcards and IN lists rewritten for drivers; the FastAPI route, StrEnum and SQLAlchemy specifics are left to sqlalchemy-bound-parameters; the References list is dropped. |
| `skills/coding-standards/rules/error-no-silent-exceptions.md` | `rules/python-error-handling.md`, `rules/python-error-boundaries.md` | Engine frontmatter (kept id, lint codes and hook link); impact tag rendered from the section; References list dropped. Examples read text with `encoding="utf-8"` and `SettingsError` derives from the project base error. Notes absorb the engine's "what to catch", chaining, `assert` and logging points. The fixed "enable BLE001 and check-typed-exception" settings (line 48) are dropped for "the repo's ruff settings decide". The boundary and documented-fallback notes (lines 45, 47) also feed `python-error-boundaries`. |
| `skills/coding-standards/rules/design-early-return.md` | `rules/python-early-return.md` | Retitled around shallow nesting (about two levels, one level of abstraction per function). The `Result(status=...)` strings become raised domain errors, and money totals use `Decimal`. The engine's named-predicate loop example joins the Good Example. "Order guards by likelihood for minor performance gains" (line 73) and the References list are dropped. |
| `skills/coding-standards/rules/doc-type-hints.md` | `rules/python-typing.md.j2`, `rules/python-abstract-inputs.md`, `rules/python-type-aliases.md` | python-typing: the skeleton (Description, Bad/Good, Notes), widened from public APIs to every signature, `include_disabled` made keyword-only, the Bad/Good cut to `find_user`; engine frontmatter and lint codes, the generics and `Self` template branches (D40), the Any ladder, mutable defaults with `ClassVar` and named ignore codes added. python-abstract-inputs: the abstract-collections Note (54). python-type-aliases: the domain-alias Note (55), as NewType ids. The References list is dropped. |
| `skills/coding-standards/rules/doc-docstring.md` | `rules/python-docstrings.md` | The skeleton (Description, Bad/Good, Notes); the Good Example gains the required usage example, keeps Google sections as optional, makes `capture` keyword-only and is trimmed to one function plus a class line; engine frontmatter and lint codes, the definition of public, the four accepted example forms and units and limits added. The References list is dropped. |
| `skills/coding-standards/rules/async-gather.md` | `rules/python-async.md.j2` | Lines 8-65 are the skeleton (Description, Bad Example of sequential awaits, Good Example, Notes): engine frontmatter, now a template with no version gate (D40); the Good Example leads with the engine's TaskGroup and except* on Python 3.11 and later and renders gather under wait_for below; the return_exceptions=True example keeps the CancelledError re-raise but logs each failure with exc_info instead of logger.error then continue; tuple[dict, dict, dict] and dict[str, dict] results become typed records (Dashboard, Quote). Notes keep CancelledError as a BaseException, siblings left running by plain gather (a version-neutral Note) and one deadline per group, read from settings. The References list is dropped. |
| `skills/coding-standards/rules/async-create-task.md` | `rules/python-async-tasks.md.j2` | Lines 8-77 are the skeleton: engine frontmatter, a template on python_at_least('3.11'); the discarded create_task Bad Example is kept with typed collaborators; the engine's BackgroundJobs supervisor, built and closed by the composition root, replaces the module-level background_tasks set; TaskGroup ownership on 3.11 and later, a task set cancelled in finally below, beside the supervisor's done callback. Notes keep the done-callback boundary, awaiting a task directly, cancellable tasks and the set[asyncio.Task[None]] annotation; set_debug becomes the PYTHONASYNCIODEBUG=1 debug mode. Dropped: the module-level background_tasks set (34-35), because nothing closes it and tests share it (pbp-B#49). The References list is dropped. |
| `skills/coding-standards/rules/async-semaphore.md` | `rules/python-async-fanout.md.j2` | Lines 8-36 and 63-69 are the skeleton: engine frontmatter, a template on python_at_least('3.11'); the 10,000-request Bad Example becomes the engine's quote_parcels case; the function-scoped semaphore is sized from settings instead of a literal default of 10, and the batch deadline comes from settings too; Notes keep the wrong-loop RuntimeError, BoundedSemaphore, release on raise, Queue workers and client connection limits (httpx added beside aiohttp). Dropped: the per-loop WeakKeyDictionary semaphore cache and its import (26, 37-61), replaced by building the semaphore on the loop that uses it. The References list is dropped. |
| `skills/coding-standards/rules/validation-pydantic.md` | `rules/pydantic-boundaries.md`, `rules/pydantic-field-constraints.md`, `rules/pydantic-typed-settings.md`, `rules/pydantic-special-types.md` | pydantic-boundaries: lines 8-57 and 70-77 are the skeleton; the FastAPI endpoint becomes a stack-neutral queue consumer parsing with model_validate_json and translating ValidationError once into an error naming each failing field; the untyped dict Bad Example is kept; EmailStr carries the email-validator extra note as a pointer to pydantic-special-types; the FastAPI note becomes a plain-text pointer to the web-application skill. pydantic-field-constraints: lines 74-75 (Field limits over hand-written ifs, after vs before validator order) become Notes. pydantic-typed-settings: the settings block (58-67) joins its Good Example with SecretStr secrets and no debug flag. pydantic-special-types: line 37's EmailStr becomes the email-validator Note. The References list is dropped. |
| `skills/web-application/rules/config-typed-settings.md` | `rules/pydantic-typed-settings.md` | Lines 8-51, 59-66, 68 and 70-71 are the skeleton, made stack-neutral: engine frontmatter; one BaseSettings class built once in main() and passed in; Field(default_factory=list) instead of `= []`; signing and payments keys stay SecretStr; tests build Settings(...) instead of patching the environment; .env and nested-settings Notes kept. Not vendored here: the FastAPI SettingsDep, app.state and create_app(Settings()) wiring (52-58, 68's create_app half) and the lru_cache get_settings note (69), which belong to the web-application skill's fastapi-app-wiring, and the mypy plugin note (67), which is the python-tooling skill's mypy-type-checking; each is one plain-text pointer. The References list is dropped. |

Distilled (credited by name only, no vendored text):

- `rules/python-performance-idioms.md`
- `rules/python-classes-and-protocols.md`
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
| `skills/web-application/rules/sec-object-authorization.md` | `rules/web-object-authorization.md`, `rules/fastapi-dependency-providers.md` | Engine frontmatter (security section, any web framework gate); title without the impact tag; References dropped; the dated Top 10 ranking dropped; the Good example names its own aliases, model and schema and defines `NotFoundError` on the project base exception, carrying the resource id, mapped to 404 through `fastapi-error-boundaries`; cross-references become rule ids; a Note for the owner or tenant filter in any framework. fastapi-dependency-providers takes Notes only (router-level auth dependency, per-request caching, roles as dependencies, tenant from the principal). |
| `skills/web-application/rules/sec-jwt-validation.md` | `rules/web-jwt-validation.md` | Engine frontmatter (security section, any web framework gate); title without the impact tag; References dropped; the Good example names the Settings fields and aliases it uses; the install command and the library-history sentence become "propose adding PyJWT through the project's package manager, never unasked"; a sentence for other JWT libraries; the secret one-liner shortened; the string-`sub` Note becomes a comment on the claim; cross-references become rule ids (pydantic-typed-settings, in another skill, in plain text). |
| `skills/web-application/rules/sec-password-hashing.md` | `rules/web-password-hashing.md` | Engine frontmatter (security section, any web framework gate); title without the impact tag; References dropped; the module-level hasher and import-time dummy hash become a `PasswordHasher` built by the composition root and passed to `authenticate`, taking `SecretStr` and returning a frozen `PasswordCheck` instead of a bare tuple; the install line becomes a version-neutral proposal through the project's package manager; Notes on throttling, sign-up enumeration and Django's hasher setting; cross-references become rule ids. |
| `skills/web-application/rules/sec-secure-tokens.md` | `rules/web-secure-tokens.md` | Engine frontmatter (security section, any web framework gate); title without the impact tag; References dropped; a comment names the two `User` columns the example writes; a Note for the same conditional update without SQLAlchemy; the S311 point stays Note text, with no `lint_codes` entry (D16); cross-references become rule ids. |
| `skills/web-application/rules/sec-cors-origins.md` | `rules/web-cors-origins.md` | Engine frontmatter (security section, any web framework gate); title without the impact tag; References dropped; the Good example shows the settings field and the middleware inside `create_app(settings)` instead of pointing at other rules; origin examples with a scheme stay only inside the code block, the Notes describe them in prose; a Note for Django and Flask CORS extensions. |
| `skills/web-application/SKILL.md` | `SKILL.md` | Lines 12, 16, 92, 131-190 and 223-227 only so far (the app-factory and testing blocks come with their rules): the intro joins the engine's summary, its one-stack sentence keeps the libraries and says the security and database rules hold for Flask, Django and Starlette, and "takes precedence" becomes "this skill's rule wins where python-coding or python-testing overlap"; the Quick Reference has the authorized query (the lazy-loading comment waits for the database rules), passwords and tokens, and settings and CORS blocks (the module-level hasher becomes an injected `PasswordHasher`, `NotFoundError` carries the id, `cors_origins` uses `Field(default_factory=list)`, settings fields only for those blocks); See Also becomes plain-text skill names, with python-architecture added. Dropped: the frontmatter `paths:` (the engine uses globs), the publisher sentence (14), the shared-example paragraph (18) and the Categories tables (20-90, replaced by the generated section index). |
| `skills/web-application/rules/api-error-responses.md` | `rules/web-password-hashing.md`, `rules/fastapi-error-boundaries.md`, `rules/web-http-methods.md` | Line 90: the sign-up account-enumeration point joins the password rule's "same error" Note, moved there from the error-boundary rule for size. The rest is merged into the engine's FastAPI error-boundaries rule, whose decisions all win: one exception-type-to-status table on the project base exception looked up along the MRO, unmapped errors re-raised to the default 500, never a handler on `Exception`, router `except` blocks as the one alternative style; per-class handlers replaced by the table; the debug-flag advice reworded as "never run production in debug mode"; cross-skill references in plain text; the success-status list moved to web-http-methods; the account-enumeration note left to the security rules. |
| `skills/web-application/rules/db-parameterized-queries.md` | `rules/sqlalchemy-bound-parameters.md` | Engine frontmatter (database section); title without the impact tag; References dropped; the `StrEnum` sort key became a `Literal` plus a column map (no Python version gate); one comment names `SessionDep`, `User` and `UserRead`; new Note on DB-API placeholders. |
| `skills/web-application/rules/db-session-per-request.md` | `rules/sqlalchemy-session-per-request.md` | Engine frontmatter (database section); References dropped; the Good example builds the engine in a real lifespan inside `create_app` (D27(1)) instead of pointing at another rule; the per-request report engine trimmed from the Bad example; Notes add the D27(1) and D27(2) sentences, provider chaining and the hotel example's files; cross-references became rule ids. |
| `skills/web-application/rules/db-transaction-boundary.md` | `rules/sqlalchemy-transaction-boundary.md.j2` | Engine frontmatter (database section); References dropped; the Good example loads the invoice with its own owner-scoped `select` and keyword-only ids, and one comment names its aliases; the FastAPI version claim became version-neutral; FastAPI-only teardown points phrased as such; the rollback Note says translate with `raise ... from`, never log and continue; Notes name python-context-managers, arch-unit-of-work and arch-effects-after-commit; one Note on the hotel example renders only for FastAPI. |
| `skills/web-application/rules/db-eager-loading.md` | `rules/sqlalchemy-eager-loading.md` | Engine frontmatter (database section); References dropped; the Good example declares the `Invoice` relationships it needs instead of pointing at another rule's model; Notes merge the upstream architecture guide's `back_populates`, cascade and loader rule of thumb; no hand-built nested dict serialization. |
| `skills/web-application/rules/db-migrations-alembic.md` | `rules/alembic-migrations.md` | Engine frontmatter (database section); References dropped; `Base` with the naming convention is defined here instead of in another rule; Notes add the D27(1) sentence for `env.py` and a proposal-only Note for repos without Alembic; cross-references became rule ids. |
| `skills/web-application/rules/db-sqlalchemy-2-style.md` | `rules/sqlalchemy-2-style.md.j2` | Engine frontmatter (database section); References dropped; the shared-model sentence dropped and the Good example trimmed to `Base`, `User` and `Invoice` (naming convention left to alembic-migrations); the mypy plugin Note became version-neutral; new SQLModel Note; one Note on the hotel example renders only for FastAPI. |
| `skills/web-application/rules/async-no-blocking-calls.md` | `rules/fastapi-no-blocking-calls.md` | Engine frontmatter (async-io section); References dropped; Description merges the engine's async-def-or-def guidance; `rates: dict[str, float]` became a frozen record of `Decimal` rates; thread-pool sizes became "both pools are bounded"; task queues only as proposals; Notes add `asyncio.run` inside a route, sync drivers and file I/O through `asyncio.to_thread` or `anyio.Path`, and name python-async. |
| `skills/web-application/rules/async-shared-http-client.md` | `rules/httpx-shared-client.md` | Engine frontmatter (async-io section); References dropped; the lifespan snippet is self-contained inside `create_app`; timeout, limits and key come from settings; `PaymentGatewayError` inherits the project base exception; the default-timeout Note became version-neutral; the backoff-library sentence became a pointer to python-retries-and-timeouts; Notes add the D27(2) sentence; cross-references became rule ids. |
| `skills/web-application/rules/api-bounded-lists.md` | `rules/web-api-pagination.md` | Engine frontmatter; impact tag and References dropped; one comment names the shared shapes and aliases (self-contained rule); the eager-loading option dropped from the Good example; Notes add one page envelope for every list endpoint and bound the offset form; query-parameter constraints named as `fastapi-query-parameters`'. |
| `skills/web-application/rules/api-separate-schemas.md` | `rules/web-api-schemas.md.j2` | Engine frontmatter; gated on any web framework; one comment names the shared service and aliases; Notes add the update-model rule (`exclude_unset`, never `exclude_none`), secrets out of every Read model, `EmailStr`'s extra as a proposal, validator scope, SQLModel and other stacks, each owned elsewhere named in plain text; the example pointer renders only under FastAPI. |
| `skills/web-application/rules/app-factory-lifespan.md` | `rules/fastapi-app-wiring.md`, `rules/web-api-resource-naming.md` | Kept id `fastapi-app-wiring` (split): the engine's lifespan, `app.state` provider and no-module-globals points lead the Description; the Good factory drops the CORS and middleware lines, reads the client timeout from settings, keeps the lifespan at module level and flat with `AsyncExitStack`, and adds the settings provider; Notes add the D27(1) sentence, liveness and readiness routes, and names the rules that own migrations, tests, router prefixes, providers and blocking calls; the router-prefix note moves to web-api-resource-naming. Line 101 (routers in feature modules with a prefix per resource; the factory only includes them) becomes a web-api-resource-naming Note; its `tags=[...]` point is left to fastapi-openapi-metadata, and the Note adds that the layout follows the repo's existing axis (pbp-B#68). |
| `skills/web-application/rules/app-thin-routes.md` | `rules/fastapi-thin-routes.md`, `rules/fastapi-dependency-providers.md` | Split: the thin-route skeleton becomes fastapi-thin-routes (aliases shown only as a comment, keyword-only service parameters, `timezone.utc` for the Python 3.10 floor, the `/pay` path made a noun); the alias block and the `Annotated` preference move to fastapi-dependency-providers; "routes do not catch them" becomes the app's one mapping style; a no-derived-values clause added; cross-skill references in plain text. |
| `skills/web-application/rules/config-typed-settings.md` | `rules/fastapi-app-wiring.md` | Only the FastAPI wiring of settings (the `SettingsDep` provider, `create_app(Settings())` in the ASGI entrypoint, tests passing settings, the cached-getter remark) is kept; the settings class itself is left to the python-coding skill. |
| `skills/web-application/rules/obs-request-id-logging.md` | `rules/fastapi-request-id-logging.md` | Engine frontmatter; the service example trimmed to one structured log call; the middleware logs unhandled errors itself; a Note adds the D27(5) sentence and limits who sets the context variable; logging libraries and tracing become proposals, never added unasked. |
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
| `skills/clean-architecture/references/pythonic-patterns.md` | `SKILL.md` | Lines 15-605 only as one row each of the pattern table ('signal, lightest form, heavier form, stop when, pattern'). DROP: the per-pattern summaries and their code (15-605), which the pattern rules duplicate; the retry (535-566), repository (498-514), unit-of-work (375-398), CQRS (337-354) and event-sourcing (317-336) summaries are covered by their owners' full files and become rows naming python-coding and python-architecture. |
| `commands/suggest-patterns.md` | `SKILL.md` | Lines 13-41: the smell-to-pattern rows, merged into the same pattern table; the singleton, value-object, registry and notification rows rewritten to the engine decisions (F9, F14, F10). DROP: command frontmatter, $ARGUMENTS and plugin paths (1-11, 53; D9). |
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
| `skills/clean-architecture/references/dependency-injection.md` | `rules/python-dependency-injection.md`, `rules/python-no-global-singletons.md` | python-dependency-injection: lines 9-31, 51-122 (constructor, Callable and consumer-owned Protocol injection) and 178-191, 222-248 (a fake or lambda through the same parameter, injecting too much, creating dependencies in __init__ and its detection line) become Description and Notes, without print calls or int money. python-no-global-singletons: lines 209-221 (service locator) become its Description bullet. Not vendored: the composition-root and DataInterface sections (owned by python-architecture) and the inspiration line. |
| `skills/clean-architecture/references/code-smells.md` | `rules/python-dependency-injection.md`, `rules/python-early-return.md` | Lines 382-399 (hardwired dependency): the Bad Example shape and the `self.x = ConcreteClass()` detection line, with the vendor class name made neutral. Lines 253-275: only the detection line (more than two levels of nested `if`/`for`/`while`) is kept, as a Note. |
| `skills/clean-architecture/references/function-design.md` | `rules/python-pure-core.md`, `rules/python-error-boundaries.md` | Lines 100-209 (pure functions, side effects): the argument-mutation Bad case, returning new values and the repository-parameter shell become the Bad Example and Notes; float amounts dropped. Lines 63-99: "validate at entry points, trust validated values inside" kept; the return conventions are rewritten to the engine's absence convention, and no example uses `float` for a price. |
| `skills/clean-architecture/references/testable-api.md` | `rules/python-pure-core.md` | Lines 385-403: injecting today's date instead of reading the clock becomes the date parameter and the fixed-dates testing Note. |
| `skills/clean-architecture/references/design-principles.md` | `rules/python-pure-core.md` | Lines 36-53 (separate I/O from domain models): folded into the __str__-or-presenter and input()-in-the-entry-point Note; no example copied. |
| `skills/clean-architecture/references/context-managers.md` | `rules/python-context-managers.md`, `rules/python-custom-context-managers.md` | python-context-managers: lines 1-37 and 120-143 (manual cleanup, file handling; the except-Exception rollback replaced by the engine's committed-flag transaction), 181-235 (nesting, ExitStack, async managers) and 236-251 (Do/Don't, suppressing in __exit__ replaced by contextlib.suppress) become the sync Bad/Good pair and Notes. python-custom-context-managers: lines 38-119 (class-based manager, __exit__ parameters, @contextmanager, class vs decorator) and 144-180 (temporary state, timing logged through logging instead of print) become its Good Example and Notes. |
| `skills/clean-architecture/references/patterns/retry.md` | `rules/python-retries-and-timeouts.md` | Lines 1-38 (simple retry) become the Bad Example, annotated with what is wrong; lines 189-222 (when to retry, when not, idempotency) become Notes, the idempotency-key example rewritten without dict rows. Dropped: exponential backoff, the except-Exception decorator, fallback defaults, the tenacity advice, the LLM case, the circuit breaker and the cross-file links (39-188, 223-278), because engine retries are fixed-delay, transient-only and re-raise the original, and add backoff or fallbacks only when asked (pca-F2, pbp-B#54). |
| `skills/clean-architecture/references/decorators.md` | `rules/python-retries-and-timeouts.md` | Lines 64-136 (retry decorator and its async version): the decorator form, re-raising the original and awaiting asyncio.sleep become Notes. Dropped: 'catching Exception broadly is acceptable in retry decorators' and exponential backoff by default (102-103) and 'use tenacity in production' (251), because engine retries catch only transient errors at a fixed delay (pca-F2); the re-raise point (104) is kept. |
| `skills/clean-architecture/references/async-patterns.md` | `rules/python-async.md.j2`, `rules/python-async-generators.md`, `rules/python-custom-context-managers.md` | python-async: lines 9-33 (asyncio.run only at the entry point), 64-109 (gather vs TaskGroup, its 'partial success' row rewritten to require return_exceptions=True, pca-F12) and the general rows of 370-382 (time.sleep, sequential awaits, a forgotten await, sync I/O moved off the loop with asyncio.to_thread instead of aiofiles) become Notes and the Good Example; the asyncio.run-in-a-route and sync-driver-in-a-handler rows stay with the web-application skill's fastapi-no-blocking-calls, named in plain text. python-async-generators: lines 176-205 are the skeleton; pages and items become typed records, the return type is AsyncIterator[OrderPage], and the Bad Example (every page collected first), the contextlib.aclosing Note and the per-request timeout pointer are added (pca-F16). The inspiration line is not vendored. python-custom-context-managers: lines 110-155 (__aenter__/__aexit__, @asynccontextmanager) become the async Note; the unguarded close and the commit inside the session manager are not vendored. |
| `skills/clean-architecture/references/error-handling.md` | `rules/python-custom-context-managers.md`, `rules/python-error-handling.md`, `rules/python-error-boundaries.md`, `rules/python-custom-exceptions.md` | Lines 129-217 (the finally block, context managers preferred): the try/finally repeated across fetch functions becomes the Bad Example and the 'why a context manager beats try/finally' list the Description; print calls dropped. Dropped: the 'ACCEPTABLE: retry decorator catches Exception' example (93-103), because a retry catches only transient errors (pca-F2) and the unit-of-work rollback form is python-context-managers' committed-flag transaction (pca-F8). Split by topic. Lines 5-44: the custom exceptions inherit the project base error instead of `Exception`, and the unclosed sqlite connection becomes a `with closing(...)` block. Lines 45-92 and 280-324: one `except` clause per failure mode and the "a broad catch hides real bugs" note; "simple subclasses of `Exception`" becomes "subclasses of the project base", and the broad-catch exception follows the engine's surfacing-recovery rule. Lines 104-128, 218-242 and 263-279: fail fast, catch only at entry points, let unknown errors propagate, kept stack-neutral (the FastAPI handler and status mapping belong to the web-application skill). The "acceptable retry decorator catching `Exception`" example (lines 93-103) is dropped. |
| `commands/make-pythonic.md` | `rules/python-custom-context-managers.md`, `rules/python-type-aliases.md` | python-custom-context-managers: line 26 ('try/finally for resource cleanup' -> context manager) becomes a Note. python-type-aliases: the "single-method abstract class -> Callable alias" row (18) became one Note, limited to a real seam; the command's process and argument text are not carried. |
| `skills/clean-architecture/references/code-quality.md` | `rules/python-custom-context-managers.md`, `rules/python-error-handling.md`, `rules/python-early-return.md`, `rules/python-meaningful-names.md`, `rules/python-typing.md.j2` | python-custom-context-managers, python-error-handling, python-early-return: lines 180-201 (rule 13's SQLite class whose __exit__ reads a connection never assigned when connect() fails) become the partial-setup Bad case, rewritten with ExitStack and pop_all in the Good Example. Rule 12's blanket "never `except Exception`" is relaxed to the engine's surfacing-recovery rule (lines 160-178); rule 4's deep-nesting example becomes guard clauses and a per-item helper (lines 46-71). python-meaningful-names: rule 2 "no vague identifiers" (21-32) became the Bad/Good names and the generic-words Note, rule 21 "no misleading method names" (330-346) the verb Note and the `add_line_item` example; rule 20's review angle (313-329) is left to design-name-for-intent. python-typing: rule 14 "no mutable default arguments" (202-217) confirms the mutable-default paragraph, its untyped `items: list` typed and its fix written as an explicit copy. |
| `skills/clean-architecture/references/refactoring-case-studies.md` | `rules/python-error-handling.md`, `rules/python-error-boundaries.md`, `rules/python-early-return.md` | Move 8 (lines 210-231): the specific catch now chains with `raise ... from exc`. Move 14 (lines 352-373): "return one type from every path" becomes one Note under the engine's absence convention. Moves 1-2 (lines 15-62): guard clauses with `continue` and a named predicate. |
| `skills/clean-architecture/references/types-and-type-hints.md` | `rules/python-typing.md.j2`, `rules/python-abstract-inputs.md`, `rules/python-type-aliases.md` | python-typing: the Optional section (155-181) became two Notes (the pipe form instead of Optional, `-> None` for side-effect functions); the 3.12 generic-alias section (441-528) became the template's 3.12 branch with one generic `type` alias, without the float `PriceMap` money alias and the float generic-strategy `Order`; "annotate every function" (608-625) became the Description, its `list[dict[str, float]]` invoice replaced by pbp's typed `find_user`. python-abstract-inputs: the "overly specific types" trade-off (559-562, 579-594) became the Description and the Bad/Good pair, with string ids instead of float prices; the "broadest appropriate type" table (722-732) became the Notes table. python-type-aliases: the Callable section (201-314) became the skeleton, its int discount strategies rewritten as Decimal fee rules (no float money) and joined by NewType ids; "keep type definitions readable" (669-696) became the nested-type Note. Dropped: the type-system theory and hint tutorial (1-154), the float side-by-side (182-200), the cryptic-errors trade-off (529-558) and the int-vs-float `compute_pay` example (563-578), which shows money as float; every course-credit line. |
| `skills/clean-architecture/references/pydantic-validation.md` | `rules/pydantic-boundaries.md`, `rules/pydantic-field-constraints.md`, `rules/pydantic-model-validators.md`, `rules/pydantic-serializers.md`, `rules/pydantic-special-types.md`, `rules/pydantic-typed-settings.md` | pydantic-field-constraints: lines 11-144 (numeric, string and collection constraints, field metadata, after and before field validators, one validator for several fields) and 252-280 (ConfigDict options; from_attributes left to the web-application skill) become Notes beside the engine's ShipmentRequest; float tax_percent is not carried. pydantic-model-validators: lines 1-10 and 145-199 are the skeleton (the DateRange example becomes StayRequest; the before validator only reshapes input; 'business rule validation' becomes input invariants only, pca-F5; the Self note becomes version-neutral). pydantic-serializers: lines 200-251 are the skeleton; untyped serializer and info parameters get pydantic types; the password-dropping model_serializer is replaced by a reshaping one, since SecretStr already masks and response models are the web-application skill's web-api-schemas. pydantic-special-types: lines 297-335 are the skeleton; PositiveFloat balance becomes Decimal (pca-F14); `pip install pydantic[email]` becomes 'propose the extra' (pbp-B#2). pydantic-typed-settings: lines 281-296 join the Bad Example, fixed to SettingsConfigDict without empty-string secrets (pca-F19). pydantic-boundaries: anti-pattern rows 393 and 395 become a Note; row 394 is web-api-schemas'. Not vendored: the inspiration lines (7, 332), the 'Arjan's preferred convention' sentence and the three-layer patterns (336-385), owned by the web-application skill. |
| `skills/clean-architecture/references/layered-architecture.md` | `rules/pydantic-typed-settings.md` | Lines 409-421 (the BaseSettings class with ConfigDict(env_file) and a default database URL for a per-environment value) become the Bad Example's settings class, annotated with what is wrong (pca-F19). Lines 422-426 (a module-level settings instance imported by db/database.py) are the python-architecture skill's sqlalchemy-engine-and-session-scope Bad Example; this rule states only the stack-neutral ban. |

Distilled (credited by name only, no vendored text):

- `rules/python-data-shapes.md`
- `rules/python-idioms.md`
- `rules/python-classes-and-protocols.md`

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
| `skills/clean-architecture/references/rest-api-design.md` | `rules/web-password-hashing.md`, `rules/web-http-methods.md`, `rules/web-api-pagination.md`, `rules/fastapi-error-boundaries.md`, `rules/fastapi-app-wiring.md`, `rules/fastapi-thin-routes.md`, `rules/fastapi-query-parameters.md`, `rules/web-api-resource-naming.md`, `rules/fastapi-openapi-metadata.md` | Lines 179-181 and 250-257: the rate-limiting idea becomes a Note (throttle login and reset endpoints at the proxy or with the project's limiter, limits read from settings and shared across instances); lines 182-249 (the third-party limiter and shared-store recipe) are dropped: a dependency the engine does not adopt, and a reference cannot be gated (D5). The CRUD route table and status codes become web-http-methods; one pagination shape web-api-pagination's Note; the duplicate answered with 400 becomes 409 in fastapi-error-boundaries; the health route fastapi-app-wiring's Note; router versus operations responsibilities fastapi-thin-routes' Description. fastapi-query-parameters: lines 45-73 (sensible defaults, `Query()` constraints) are the skeleton in the engine rule format; the naive `datetime.now()` defaults become `None` resolved from an injected clock (pca-F13); constraints move into `Annotated[..., Query(...)]`; a `Literal` closed set and `Decimal` amounts added. web-api-resource-naming: lines 7-12 (plural nouns, ids in the path, nesting), 37-41 (one format everywhere) and 130-139 (path versioning, version only for breaking changes) become the Description, Good Example and Notes, with invoice resources and a non-CRUD action as a sub-resource. fastapi-openapi-metadata: lines 90-126 (`response_model`, `summary`, docstring, router tags, `responses=`) are the skeleton; the duplicate-email 400 becomes 409 (pca-F3b) and the return annotation replaces `response_model=`. Not vendored here: the route table and status codes (web-http-methods) and pagination (web-api-pagination). |
| `skills/clean-architecture/references/async-patterns.md` | `rules/sqlalchemy-session-per-request.md`, `rules/fastapi-no-blocking-calls.md`, `rules/fastapi-app-wiring.md` | Lines 206-221 (`async_sessionmaker` with `expire_on_commit=False` and the yield provider) merged into sqlalchemy-session-per-request without the module-level engine and its inline DSN (D27(1)); lines 23, 35-60 (no `asyncio.run` in a route, `async def` versus `def`) and the route rows 374 and 377 of the common-mistakes table merged into fastapi-no-blocking-calls; `aiofiles` is not proposed. Lines 156-172 (the lifespan shape: acquire before `yield`, release after) go to fastapi-app-wiring; its create-tables startup step is the migration rule's counter-example. |
| `skills/clean-architecture/references/layered-architecture.md` | `rules/sqlalchemy-eager-loading.md`, `rules/alembic-migrations.md`, `rules/sqlalchemy-2-style.md.j2`, `rules/web-api-schemas.md.j2`, `rules/fastapi-app-wiring.md`, `rules/fastapi-dependency-providers.md` | Lines 308-373 (relationships, cascade delete, eager-loading rule of thumb) merged into sqlalchemy-eager-loading's example and Notes, its nested `to_dict` (342-357) not vendored; lines 286-304 (`create_all` in the lifespan) confirm alembic-migrations' Bad example; lines 430-451 (SQLModel) became one sqlalchemy-2-style Note: table classes are not request or response schemas. The Create/Read/Update trio (with `exclude_unset`) and the SQLModel trade-off go to web-api-schemas' Notes; the module-level app and engine to fastapi-app-wiring's Bad example (D27(1)); manual injection with `SessionLocal()` per endpoint to fastapi-dependency-providers' Bad example, provider functions as the composition root to its Good example. |
| `commands/review-api-design.md` | `rules/web-api-schemas.md.j2`, `rules/web-api-pagination.md`, `rules/web-http-methods.md`, `rules/fastapi-dependency-providers.md`, `rules/web-api-resource-naming.md`, `rules/fastapi-openapi-metadata.md` | The checklist only (D9): method semantics and status codes become web-http-methods, request and response checks web-api-schemas' Notes, list pagination web-api-pagination's, dependency injection for auth and sessions fastapi-dependency-providers'; the command frame, `$ARGUMENTS`, report format and plugin paths are dropped. web-api-resource-naming: lines 20-25 (plural nouns, nesting, no verbs in URLs, one case style, ids in the path) and 46 (router prefix matches the resource) become the Bad/Good pair and Notes. fastapi-openapi-metadata: lines 47-48 (tags and response models on every endpoint) become a Note. |
| `skills/clean-architecture/SKILL.md` | `rules/web-api-schemas.md.j2` | Lines 56-71 only: separate Create and Read models per entity, with `exclude_none` replaced by `exclude_unset`. |
| `skills/clean-architecture/references/error-handling.md` | `rules/fastapi-error-boundaries.md` | Lines 243-276 only: router `except` blocks as the accepted alternative style (never mixed with the table), and the route-level catch-all answering a hand-built 500 as the rule it forbids. |
| `skills/clean-architecture/references/pydantic-validation.md` | `rules/web-api-schemas.md.j2` | Lines 336-386 and the one-model anti-pattern row: Create and Read models with validation, partial-update models, FastAPI's own 422; `exclude_none` replaced by `exclude_unset`. |
| `skills/clean-architecture/references/testable-api.md` | `rules/fastapi-error-boundaries.md` | Lines 176-189 only: a router catching a domain error into `HTTPException`, as the alternative style; its `SessionLocal()` per endpoint is not kept. |
| `skills/clean-architecture/references/testing-advanced.md` | `rules/fastapi-dependency-overrides.md.j2`, `rules/sqlalchemy-test-rollback.md.j2` | The module-level override and global client become fastapi-dependency-overrides' Bad example and the in-memory SQLite schema rebuilt per test sqlalchemy-test-rollback's; endpoint tests cover HTTP only, business rules are tested without HTTP (plain text). |

## domino-docs

Source: the Domino Data Lab 6.2 user, admin and API documentation, cited by page id.
Form: distilled (credited by name only, not vendored; no open license).

Each row names the files that restate a page's facts in the engine's own
words; those files stay under "Engine-written files". Pages a later lane
uses gain its files in their row.

### domino-apps

| Upstream file | Core files | Changes |
| --- | --- | --- |
| `user_guide/9d3c12` | `SKILL.md`, `rules/domino-app-bind-host-port.md`, `rules/domino-app-launch-script.md`, `rules/domino-app-external-persistence.md`, `rules/domino-app-publish-from-commit.md`, `rules/domino-app-deployment-record.md` | Facts restated: the launch contract (one launch file, a process on 0.0.0.0:8888 that Domino watches); stopping an App deletes its pod and every unsaved file change; launch file, environment, hardware tier and code branch define an App, each App pinning its own environment version and tier. |
| `user_guide/6a2215` | `SKILL.md`, `rules/domino-app-url-prefix.md`, `rules/domino-app-viewer-identity.md`, `rules/domino-app-verify-viewer-jwt.md`, `rules/domino-app-starter-settings.md` | Facts restated: the injected headers and DOMINO_RUN_HOST_PATH; user-level variables follow the starter. |
| `user_guide/b99d5d` | `SKILL.md`, `rules/domino-app-external-persistence.md`, `rules/domino-app-concurrent-writes.md`, `rules/domino-app-proxy-limits.md`, `rules/domino-app-logging.md` | Facts restated: Apps never save file changes (the Quick Reference's runtime writes do not persist), so durable data goes to a Dataset, a database or an object store, and so do large data and durable outputs such as logs; Domino does not serialize writes across viewers. |
| `admin_guide/71d6ad` | `SKILL.md`, `rules/domino-app-viewer-identity.md`, `rules/domino-app-concurrent-writes.md`, `rules/domino-app-proxy-limits.md` | Facts restated: the default proxy limits (the run pod proxy's 300 s connect and read timeouts and the 25 MiB body-size default, all admin-configurable; the body cap applying to Apps is marked as inferred); anonymous access to public products; autoscaled replicas share one volume for code and temporary files. |
| `user_guide/a537c2` | `rules/domino-app-bind-host-port.md`, `rules/domino-app-dash.md`, `rules/domino-app-streamlit.md`, `rules/domino-app-shiny.md` | Facts restated: every framework serves TCP 8888; Streamlit's launch flags; Shiny serves 0.0.0.0:8888. Not reproduced: the Dash stub that omits the browser-side prefix and runs with debug on, and the R Shiny runApp lines (unsafe / R-only). |
| `user_guide/2039f2` | `rules/domino-app-bind-host-port.md`, `rules/domino-app-flask.md` | Facts restated: host 0.0.0.0, port 8888; the WSGI middleware that sets the mount point and scheme; the package layout. Not reproduced: the debug-on launch script, the DFS layout tree and the publish click-path. |
| `user_guide/cb9195` | `rules/domino-app-bind-host-port.md`, `rules/domino-app-url-prefix.md`, `rules/domino-app-relative-urls.md`, `rules/domino-app-viewer-identity.md`, `rules/domino-app-verify-viewer-jwt.md`, `rules/domino-app-viewer-token.md`, `rules/domino-app-flask.md`, `rules/domino-app-sharing-mode.md` | Facts restated: the base path variable (the prefix comes from DOMINO_RUN_HOST_PATH, not a request header), the three identity levels, RS256 with audience apps, extended-identity consent; edit rights come from project collaboration; view rights are Restricted or open to anyone in Domino, with discoverable Restricted Apps and access requests. Not reproduced (unsafe): the basic identity launch script (debug on, no port), the JWT snippet fetching the key set over plain HTTP on every call with no timeout, and the decoded-payload sample. |
| `user_guide/9b11ea` | `rules/domino-app-bind-host-port.md`, `rules/domino-app-static-site.md` | Facts restated: an empty host binds every interface; a standard-library HTTP server on 8888 can serve static pages from a Python launch file. Not reproduced: the example serving the whole working directory (unsafe). |
| `user_guide/2c3a33` | `rules/domino-app-bind-host-port.md`, `rules/domino-app-launch-script.md`, `rules/domino-app-starter-settings.md`, `rules/domino-app-endpoint-auth.md`, `rules/domino-app-streamlit.md`, `rules/domino-app-external-resources.md`, `rules/domino-app-publish-from-commit.md`, `rules/domino-app-workspace-preview.md` | Facts restated: Streamlit's 8501 default, an executable launch script at the project root that writes the server settings, a publisher's user-level key; file-system projects sync files only after the workspace saves and stops; preview through the workspace proxy, publish on 8888. Not reproduced (unsafe): CORS and XSRF protection off, usage statistics on, endpoint URL and token in the code file, unpinned installs; the dead example-repo pointer and model names are dropped. |
| `user_guide/de2589` | `rules/domino-app-url-prefix.md`, `rules/domino-app-launch-script.md`, `rules/domino-app-dash.md` | Facts restated: Dash's two path prefixes; the prefix variable read for the browser side; a one-command launch script. Not reproduced: the environment and publish click-paths and the debug-on run line (unsafe). |
| `support_kb/SecureIdentityPropagationToAppsEnabled` | `rules/domino-app-url-prefix.md` | Fact restated: hand-built prefixes break after a restart under the secure flag. |
| `user_guide/cfc79e` | `rules/domino-app-url-prefix.md`, `rules/domino-app-publisher-data-rights.md` | Facts restated: the secure flag changes the host path; a configuration record decides dataset mounting. |
| `admin_guide/6469bf` | `rules/domino-app-url-prefix.md`, `rules/domino-app-viewer-identity.md`, `rules/domino-app-verify-viewer-jwt.md`, `rules/domino-app-external-resources.md`, `rules/domino-app-sharing-mode.md` | Facts restated: the secure flag defaults on in 6.2; anonymous viewers are possible when an admin permission admits them; the App CSP flag defaults off, the iframe flag on, and flag changes need no restart. |
| `user_guide/55fc89` | `rules/domino-app-url-prefix.md`, `rules/domino-app-starter-settings.md` | Facts restated: the run variables of the broken prefix and DOMINO_STARTING_USERNAME. Not used: the variable glossary and deprecated variables (domino-jobs' shared basics). |
| `user_guide/b04682` | `rules/domino-app-launch-script.md`, `rules/domino-app-relative-urls.md`, `rules/domino-app-endpoint-auth.md`, `rules/domino-app-concurrent-writes.md`, `rules/domino-app-deployment-record.md`, `rules/domino-app-sharing-mode.md` | Practices restated: a minimal launch script, no hard-coded URLs, paths or tokens; replicas share one disk, so concurrent writes to one file can corrupt it; one branch and environment per stage, clone environments instead of editing them, tag versions; review permissions on publish, describe audience, data and limits, give a team contact. |
| `user_guide/f3cc84` | `rules/domino-app-launch-script.md` | Fact restated: launch-file names are free-form. Not used: the audit App's sizing and unsupported-forks notes (product-specific). |
| `user_guide/cd0095` | `rules/domino-app-relative-urls.md`, `rules/domino-app-publisher-data-rights.md`, `rules/domino-app-viewer-token.md`, `rules/domino-app-publish-from-commit.md`, `rules/domino-app-deployment-record.md`, `rules/domino-app-sharing-mode.md` | Facts restated: custom URL paths; the App acts as its publisher; acting for viewers is admin-only and grants full access; a Git-based App runs the branch or revision chosen at publish time; the per-App settings of the publish dialog; sharing modes and access requests, collaborators as editors. |
| `user_guide/5bef19` | `rules/domino-app-publisher-data-rights.md` | Facts restated: mounts use the creator's access; per-viewer access goes through the Data API SDK. |
| `user_guide/e3ec27` | `rules/domino-app-publisher-data-rights.md`, `rules/domino-app-starter-settings.md`, `rules/domino-app-external-persistence.md` | Facts restated: mounts and data sources use the starter's permissions and credentials; project files are writable inside an App but never saved. |
| `admin_guide/a9e507` | `rules/domino-app-viewer-token.md`, `rules/domino-app-logging.md` | Fact restated: App execution logs are kept indefinitely and go into support bundles. |
| `user_guide/bb4b24` | `rules/domino-app-viewer-token.md`, `rules/domino-app-publish-from-commit.md`, `rules/domino-app-logging.md` | Facts restated: each publish snapshots environment, file references and code paths with no rollback or diff; App stdout and stderr go into the execution logs and are part of the support bundle. |
| `user_guide/6ac5a1` | `rules/domino-app-starter-settings.md` | Fact restated: the user value wins over project and environment values. Not used: the reserved names and naming syntax (domino-jobs' shared basics). |
| `user_guide/e038f2` | `rules/domino-app-endpoint-auth.md` | Facts restated: restricted endpoints, basic auth for sync and Bearer for async, per-endpoint tokens. |
| `user_guide/f46bdc` | `rules/domino-app-replica-state.md`, `rules/domino-app-shiny.md`, `rules/domino-app-deployment-record.md`, `rules/domino-app-logging.md` | Facts restated: autoscaled replicas, session affinity and its secure-flag requirement, small pods for Shiny; autoscaling settings persist across launches; the logs of all pods are interleaved into one log. |
| `user_guide/a29497` | `rules/domino-app-external-persistence.md`, `rules/domino-app-replica-state.md`, `rules/domino-app-dash.md`, `rules/domino-app-flask.md`, `rules/domino-app-shiny.md`, `rules/domino-app-production-server.md` | Facts restated: Apps never sync file changes; the Flask and Dash development servers are single-threaded and not meant for more than about ten concurrent users, so they serve with gunicorn workers; one R Shiny process computes for one session at a time (the Python consequence is the engine's inference). Not reproduced: the debug-on launch scripts (unsafe). Not used: the stale claim that Apps never scale horizontally and the worked sizing arithmetic. |
| `user_guide/aec000` | `rules/domino-app-external-resources.md` | Facts restated: a content security policy or iframe restriction blocks outside fonts, APIs and pages unless allowlisted; diagnose in the browser console and restart the App after the allowlist changes. |
| `user_guide/910370` | `rules/domino-app-publish-from-commit.md` | Facts restated: code must be pushed to be seen; no Git LFS. |
| `user_guide/2c01ae` | `rules/domino-app-workspace-preview.md` | Facts restated: a workspace exposes one port, 80 and 9000 are reserved; the server proxy path is built from the project owner, project name and run id. |
| `user_guide/71635d` | DROP | Section landing page: one-line pointers to child pages, nothing actionable. |
| `user_guide/e92082` | DROP | R-only Shiny walkthrough; its 0.0.0.0:8888 fact is restated from a537c2. |
| `user_guide/5aedde` | DROP | Agent deployment, tracing and runs belong to the domino-agents skill. |
| `user_guide/d95a3c` | DROP | Reserved project files are detector markers and domino-jobs results material, not App guidance. |
| `user_guide/ccaee6` | DROP | The Git-based /mnt layout is domino-jobs' shared basics. |
| `support_kb/docs-lifecycle` | DROP | Docs lifecycle and the client compatibility matrix: provenance facts, not rule text. |

### domino-jobs

| Upstream file | Core files | Changes |
| --- | --- | --- |
| `user_guide/910370` | `SKILL.md`, `rules/domino-project-types.md` | Fact restated: a job in a Git-based project syncs only artifacts back; code edits are neither saved nor pushed. |
| `user_guide/ccaee6` | `SKILL.md`, `rules/domino-project-types.md`, `rules/domino-paths-from-env.md` | Facts restated: the Git-based layout (code checkout as working directory, data, artifacts, imported folders). Not reproduced: the prose's /mnt/local dataset path, which contradicts the tree (code reads the variable instead). |
| `user_guide/de4abb` | `SKILL.md`, `rules/domino-project-types.md`, `rules/domino-paths-from-env.md` | Facts restated: the DFS layout, its working directory and how importing a project moves it. |
| `user_guide/b4f02f` | `rules/domino-project-types.md`, `rules/domino-secrets-in-env-vars.md` | Facts restated: what each project type tracks, a new revision per completed job, the store keeps every version, Apps and endpoints persist nothing. |
| `user_guide/b4cb04` | `rules/domino-project-types.md` | Facts restated: the Finishing and Stopping states copy new and changed files back; Error means a platform failure. |
| `user_guide/5b3b05` | `rules/domino-project-types.md` | Fact restated: changes are captured at completion whether the job succeeded or failed. |
| `user_guide/56938d` | `rules/domino-project-types.md`, `rules/domino-paths-from-env.md` | Facts restated: where artifacts live per project type; variables instead of /mnt literals. Not reproduced: the tip to replace /mnt with DOMINO_WORKING_DIR, which breaks for Git-based artifacts. |
| `user_guide/d8dde6` | `rules/domino-secrets-in-env-vars.md` | Facts restated: no secrets in source; project variables live in a secure store, are passed verbatim up to 64K and are readable by every collaborator. |
| `user_guide/d7bac0` | `rules/domino-secrets-in-env-vars.md` | Contradiction noted: who may edit project variables; the rule validates values at startup instead of trusting either version. |
| `user_guide/910b3a` | `rules/domino-secrets-in-env-vars.md` | Facts restated: user variables are visible only to their owner and injected only into that user's runs, never into models. |
| `user_guide/9c4f82` | `rules/domino-secrets-in-env-vars.md`, `rules/domino-pinned-environments.md` | Facts restated: requirements.txt location and reinstall on every execution; private Git dependencies use the Git integration. |
| `user_guide/aa15a8` | `rules/domino-secrets-in-env-vars.md` | Fact restated: removing a file from the store needs an administrator's full delete across all projects. |
| `admin_guide/a9e507` | `rules/domino-secrets-in-env-vars.md` | Fact restated: execution logs are kept indefinitely. |
| `user_guide/55fc89` | `rules/domino-paths-from-env.md`, `rules/domino-api-proxy-auth.md`, `rules/domino-env-var-names.md` | Facts restated: the injected path and identity variables, the deprecated API key and removed token file, no injected defaults in Model Manager. |
| `user_guide/6942ab` | `SKILL.md`, `rules/domino-paths-from-env.md` | Fact restated: dataset mount paths per project type. |
| `user_guide/e09156` | `SKILL.md`, `rules/domino-paths-from-env.md`, `rules/domino-environment-revisions.md` | Facts restated: DOMINO_IS_WORKFLOW_JOB, Flow task outputs and snapshot mounts, Flow environment and tier IDs and the revision specification with use_latest off. |
| `user_guide/40b91f` | `rules/domino-api-proxy-auth.md` | Facts restated: service-account Bearer tokens from an environment variable, short-lived personal tokens, deprecated API keys, the in-run API proxy. |
| `api_guide/c5ef26` | `rules/domino-api-proxy-auth.md`, `rules/domino-env-var-names.md`, `rules/domino-environment-revisions.md` | Facts restated: python-domino's authentication order, the proxy's HTTPS limitation, DOMINO_MAX_RETRIES and the other tuning variables, job_start's environment and tier arguments, the minimum client version. Not used: budgets, billing tags, files and blobs, App publishing and dataset upload helpers. |
| `api_guide/d9cc25` | `rules/domino-api-proxy-auth.md` | Fact restated: with no authentication arguments the client detects the proxy. Not reproduced: its outdated token-file and API-key description. |
| `user_guide/af97b7` | `rules/domino-api-proxy-auth.md`, `rules/domino-environment-revisions.md` | Facts restated: the job's default revision and the re-run options; the SDK example's API key is noted as outdated. Not used: UI-only parts (tagging, renaming, stopping from the Active tab, volume sizes, tier grouping, cluster attachment). |
| `user_guide/e4f67f` | `rules/domino-api-proxy-auth.md` | Contradiction noted: the Airflow setup stores a user API key; the rule follows the authentication page. |
| `user_guide/6ac5a1` | `rules/domino-env-var-names.md` | Facts restated: four variable levels and their precedence, name syntax, reserved names and prefixes, the advice to use a company prefix. |
| `user_guide/b60bf6` | `rules/domino-env-var-names.md` | Fact restated: compute-environment variables need ARG and ENV lines and a rebuild. |
| `user_guide/813d89` | `rules/domino-env-var-names.md`, `rules/domino-pinned-environments.md` | Facts restated: Dockerfile instructions without FROM, install as root then back to ubuntu, exact pins, one pip install, the 127-layer limit, ARG versus ENV. |
| `user_guide/0e4da9` | `rules/domino-pinned-environments.md`, `rules/domino-environment-revisions.md` | Facts restated: dependency files reinstall over the network on every execution; test new revisions before making them Active. |
| `user_guide/5dd2c1` | `rules/domino-pinned-environments.md` | Facts restated: setup-script order and scope, the build cannot see project files or user variables; the two post-run script definitions are noted. |
| `user_guide/fda6d8` | `rules/domino-pinned-environments.md` | Fact restated: explicit versions in one place. |
| `user_guide/f51038` | `rules/domino-environment-revisions.md` | Facts restated: each save adds a revision, the latest successful build becomes Active unless auto-assign is off, build propagation. |
| `user_guide/5dce1f` | `rules/domino-environment-revisions.md` | Facts restated: a schedule uses the latest revision unless one is chosen; restricted projects. |
| `user_guide/e53646` | `rules/domino-environment-revisions.md` | Contradiction noted: whether re-running with the original version reuses the original environment. |
| `user_guide/dba65c` | `rules/domino-environment-revisions.md` | Fact restated: the project's default tier and environment apply unless overridden. |
| `user_guide/e6e601` | `rules/domino-environment-revisions.md` | Fact restated: a smaller hardware tier provisions faster. |
| `user_guide/e46d54` | DROP | Index page (environments); no fact beyond its children. |
| `user_guide/db2820` | DROP | Long-running job notifications are a per-user UI preference; nothing for code to do. |
| `user_guide/63ac71` | DROP | Saving artifacts through the workspace File Changes panel is an interactive workflow; the job persistence fact comes from user_guide/910370. |
| `user_guide/ca786d` | DROP | Index page (Manage a DFS project); no fact beyond its children. |
| `user_guide/a8e081` | DROP | Index page (Work with Projects). |
| `user_guide/716281` | DROP | Index page (Configure a Project). |
| `user_guide/1c333d` | DROP | Index page (Reference). |
| `user_guide/30b067` | DROP | Index page (Domino CLI). |
| `user_guide/85722a` | DROP | Troubleshooting index; its import-path advice concerns workspaces. |
| `user_guide/5d0521` | DROP | Restates the Git-based layout already taken from user_guide/ccaee6 and user_guide/910370. |
| `user_guide/b9d997` | DROP | Docs lifecycle: informs the 6.2 target and this credit only; no rule. |
| `legal/terms` | DROP | Terms of use: the basis for distilling instead of vendoring; no rule content. |
| `user_guide/66b789` | DROP | Model variables apply to deployed models, which no Domino skill covers. |
| `admin_guide/ed1c08` | DROP | Registry credentials for external images: an administrator task. |
| `admin_guide/de48cc` | DROP | User management index: an administrator topic with no job-code fact. |
| `user_guide/0002fb` | DROP | Workspace management, linked from the job monitoring page by mistake; nothing for jobs. |
| `user_guide/ac5c29` | DROP | MATLAB Launcher wrapper: nothing for Python repos. |

## Engine-written files

Files written for the engine with no upstream text, per core skill. A file
that comes to hold vendored text moves from here into its source's table.

### design-patterns

- `scripts/_pyscan_common.py`
- `scripts/_smell_detectors.py`
- `scripts/_smell_model.py`
- `scripts/detect_smells.py`
- `scripts/lcom4_clusters.py`

### domino-agents

- `SKILL.md`
- `rules/domino-agent-llm-keys.md`
- `rules/domino-agent-access-token.md`
- `rules/domino-agent-endpoint-auth.md`
- `rules/domino-agent-redact-traces.md`
- `rules/domino-agent-app-factory.md`
- `rules/domino-agent-chat-endpoint.md`
- `rules/domino-agent-run-limits.md`
- `rules/domino-agent-conversation-state.md`
- `rules/domino-agent-logging.md`
- `rules/domino-agent-settings.md`
- `rules/domino-agent-config-file.md`
- `rules/domino-agent-trace-entrypoint.md`
- `rules/domino-agent-manual-spans.md`
- `rules/domino-agent-sdk-names.md`
- `rules/domino-agent-dev-eval-job.md`
- `rules/domino-agent-evaluators.md`
- `rules/domino-agent-eval-out-of-band.md`
- `rules/domino-agent-prod-eval-watermark.md`
- `rules/a2a-agent-card.md`
- `rules/a2a-client-deadlines.md`
- `rules/a2a-mount-lifespan.md`
- `rules/domino-agent-fake-domino-tests.md`
- `rules/domino-agent-fake-llm-tests.md`

Upstream files each secrets and service rule draws on (example-agent files by
path and lines, 6.2 documentation pages by guide and page id):

- domino-agent-llm-keys: `ai_system_config.yaml` 1-33, `README.md` 289-296,
  `dev_eval_simplest_agent.py` 154-164; api_guide/c5ef26, user_guide/baab29.
- domino-agent-access-token: `README.md` 51-77, 366-370, 420-425,
  `simplest_agent.py` 84-98, `chat_app.py` 136-137; admin_guide/71d6ad,
  user_guide/40b91f, api_guide/c5ef26.
- domino-agent-endpoint-auth: `simplest_agent.py` 80-109, `ai_system_config.yaml`
  15-33 (the endpoint shape only); user_guide/e038f2, user_guide/5aedde.
- domino-agent-redact-traces: `chat_app.py` 99-102; api_guide/c5ef26,
  user_guide/da707d.
- domino-agent-app-factory: `chat_app.py` 1-84, 121-133, 180-211,
  `simplest_agent.py` 13-20, 112-128, `app.sh` 1-11, `static/app.js` 4-11;
  user_guide/5aedde, user_guide/9d3c12.
- domino-agent-chat-endpoint: `chat_app.py` 87-118, `README.md` 40-49, 81-103;
  user_guide/5aedde, admin_guide/71d6ad.
- domino-agent-run-limits: `simplest_agent.py` 116-121, `ai_system_config.yaml`
  35-38; admin_guide/71d6ad.
- domino-agent-conversation-state: `chat_app.py` 87-96, 110,
  `ai_system_config.yaml` 38; user_guide/f46bdc, user_guide/b99d5d.
- domino-agent-logging: `chat_app.py` 20-21, 115-118, 203-210,
  `simplest_agent.py` 38, 65, `app.sh` 11, `dev_eval_simplest_agent.py` 31-38;
  admin_guide/a9e507, user_guide/bb4b24.

Upstream text these rules leave out (DROP, with the reason):

- `ai_system_config.yaml` 15-33, 46-61: commented provider blocks with an
  internal host and endpoint id, not reproduced (the endpoint URL moves to
  settings), and unused alternative prompts.
- `chat_app.py` 27-29, 136-146, 153-177: the static directory constants, the
  UI-only platform-info route and the static catch-all go with the playground
  UI; the catch-all's prefix-match check and its 200 for unknown paths are not
  reproduced.
- `static/app.js` 1-3, 12-103, 140-217, 234-625: playground UI code; only its
  relative base-path idea (4-11) is used, as a Note of domino-agent-app-factory.
- user_guide/5aedde: the page's FastAPI sample is not copied; it builds the
  agent inside the traced function on every call, and domino-agent-app-factory
  and domino-agent-endpoint-auth state the safe behavior instead.

### domino-apps

- `SKILL.md`
- `rules/domino-app-bind-host-port.md`
- `rules/domino-app-url-prefix.md`
- `rules/domino-app-launch-script.md`
- `rules/domino-app-relative-urls.md`
- `rules/domino-app-publisher-data-rights.md`
- `rules/domino-app-viewer-identity.md`
- `rules/domino-app-verify-viewer-jwt.md`
- `rules/domino-app-viewer-token.md`
- `rules/domino-app-starter-settings.md`
- `rules/domino-app-endpoint-auth.md`
- `rules/domino-app-external-persistence.md`
- `rules/domino-app-concurrent-writes.md`
- `rules/domino-app-replica-state.md`
- `rules/domino-app-dash.md`
- `rules/domino-app-flask.md`
- `rules/domino-app-streamlit.md`
- `rules/domino-app-shiny.md`
- `rules/domino-app-static-site.md`
- `rules/domino-app-production-server.md`
- `rules/domino-app-proxy-limits.md`
- `rules/domino-app-external-resources.md`
- `rules/domino-app-publish-from-commit.md`
- `rules/domino-app-deployment-record.md`
- `rules/domino-app-sharing-mode.md`
- `rules/domino-app-workspace-preview.md`
- `rules/domino-app-logging.md`

### domino-jobs

- `SKILL.md`
- `rules/domino-project-types.md`
- `rules/domino-secrets-in-env-vars.md`
- `rules/domino-paths-from-env.md`
- `rules/domino-api-proxy-auth.md`
- `rules/domino-env-var-names.md`
- `rules/domino-pinned-environments.md`
- `rules/domino-environment-revisions.md`

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
- `rules/python-error-messages-with-context.md`
- `rules/python-small-units.md`

### python-documentation

### python-testing

- `SKILL.md`

### python-tooling

- `SKILL.md`

### web-application

