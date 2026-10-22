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

The domino-apps skill (its SKILL.md and every rule under its rules/
directory, listed under "Engine-written files") distills facts from the
Domino Data Lab 6.2 user and admin documentation, which carries no open
license; it is credited by name only and not vendored. No sentences or
examples from the documentation are copied, its unsafe example settings are
not reproduced, and the facts are restated in the engine's own words. The
`domino-docs` section below records, per documentation page, the files that
use its facts or why it was dropped; a distilled source has no pin and no
license copy.

The domino-jobs skill (its SKILL.md and every rule under its rules/
directory, listed under "Engine-written files") distills facts from the same
documentation's user guide and its API guide in the same way (D50): no
sentences or examples are copied, every example is new, and where the
documentation contradicts itself the rules state the safe behavior. Its pages
are recorded in the `domino-docs` section below as well.

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

Distilled (credited by name only, no vendored text):

- `rules/python-performance-idioms.md`
- `rules/python-async.md`
- `rules/python-classes-and-protocols.md`
- `rules/python-typing.md.j2`
- `rules/python-docstrings.md`
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
| `skills/clean-architecture/references/dependency-injection.md` | `rules/python-dependency-injection.md`, `rules/python-no-global-singletons.md` | python-dependency-injection: lines 9-31, 51-122 (constructor, Callable and consumer-owned Protocol injection) and 178-191, 222-248 (a fake or lambda through the same parameter, injecting too much, creating dependencies in __init__ and its detection line) become Description and Notes, without print calls or int money. python-no-global-singletons: lines 209-221 (service locator) become its Description bullet. Not vendored: the composition-root and DataInterface sections (owned by python-architecture) and the inspiration line. |
| `skills/clean-architecture/references/code-smells.md` | `rules/python-dependency-injection.md`, `rules/python-early-return.md` | Lines 382-399 (hardwired dependency): the Bad Example shape and the `self.x = ConcreteClass()` detection line, with the vendor class name made neutral. Lines 253-275: only the detection line (more than two levels of nested `if`/`for`/`while`) is kept, as a Note. |
| `skills/clean-architecture/references/function-design.md` | `rules/python-pure-core.md`, `rules/python-error-boundaries.md` | Lines 100-209 (pure functions, side effects): the argument-mutation Bad case, returning new values and the repository-parameter shell become the Bad Example and Notes; float amounts dropped. Lines 63-99: "validate at entry points, trust validated values inside" kept; the return conventions are rewritten to the engine's absence convention, and no example uses `float` for a price. |
| `skills/clean-architecture/references/testable-api.md` | `rules/python-pure-core.md` | Lines 385-403: injecting today's date instead of reading the clock becomes the date parameter and the fixed-dates testing Note. |
| `skills/clean-architecture/references/design-principles.md` | `rules/python-pure-core.md` | Lines 36-53 (separate I/O from domain models): folded into the __str__-or-presenter and input()-in-the-entry-point Note; no example copied. |
| `skills/clean-architecture/references/context-managers.md` | `rules/python-context-managers.md`, `rules/python-custom-context-managers.md` | python-context-managers: lines 1-37 and 120-143 (manual cleanup, file handling; the except-Exception rollback replaced by the engine's committed-flag transaction), 181-235 (nesting, ExitStack, async managers) and 236-251 (Do/Don't, suppressing in __exit__ replaced by contextlib.suppress) become the sync Bad/Good pair and Notes. python-custom-context-managers: lines 38-119 (class-based manager, __exit__ parameters, @contextmanager, class vs decorator) and 144-180 (temporary state, timing logged through logging instead of print) become its Good Example and Notes. |
| `skills/clean-architecture/references/patterns/retry.md` | `rules/python-retries-and-timeouts.md` | Lines 1-38 (simple retry) become the Bad Example, annotated with what is wrong; lines 189-222 (when to retry, when not, idempotency) become Notes, the idempotency-key example rewritten without dict rows. Dropped: exponential backoff, the except-Exception decorator, fallback defaults, the tenacity advice, the LLM case, the circuit breaker and the cross-file links (39-188, 223-278), because engine retries are fixed-delay, transient-only and re-raise the original, and add backoff or fallbacks only when asked (pca-F2, pbp-B#54). |
| `skills/clean-architecture/references/decorators.md` | `rules/python-retries-and-timeouts.md` | Lines 64-136 (retry decorator and its async version): the decorator form, re-raising the original and awaiting asyncio.sleep become Notes. Dropped: 'catching Exception broadly is acceptable in retry decorators' and exponential backoff by default (102-103) and 'use tenacity in production' (251), because engine retries catch only transient errors at a fixed delay (pca-F2); the re-raise point (104) is kept. |
| `skills/clean-architecture/references/async-patterns.md` | `rules/python-custom-context-managers.md` | Lines 110-155 (__aenter__/__aexit__, @asynccontextmanager) become the async Note; the unguarded close and the commit inside the session manager are not vendored. |
| `skills/clean-architecture/references/error-handling.md` | `rules/python-custom-context-managers.md`, `rules/python-error-handling.md`, `rules/python-error-boundaries.md`, `rules/python-custom-exceptions.md` | Lines 129-217 (the finally block, context managers preferred): the try/finally repeated across fetch functions becomes the Bad Example and the 'why a context manager beats try/finally' list the Description; print calls dropped. Dropped: the 'ACCEPTABLE: retry decorator catches Exception' example (93-103), because a retry catches only transient errors (pca-F2) and the unit-of-work rollback form is python-context-managers' committed-flag transaction (pca-F8). Split by topic. Lines 5-44: the custom exceptions inherit the project base error instead of `Exception`, and the unclosed sqlite connection becomes a `with closing(...)` block. Lines 45-92 and 280-324: one `except` clause per failure mode and the "a broad catch hides real bugs" note; "simple subclasses of `Exception`" becomes "subclasses of the project base", and the broad-catch exception follows the engine's surfacing-recovery rule. Lines 104-128, 218-242 and 263-279: fail fast, catch only at entry points, let unknown errors propagate, kept stack-neutral (the FastAPI handler and status mapping belong to the web-application skill). The "acceptable retry decorator catching `Exception`" example (lines 93-103) is dropped. |
| `commands/make-pythonic.md` | `rules/python-custom-context-managers.md` | Line 26 ('try/finally for resource cleanup' -> context manager) becomes a Note. |
| `skills/clean-architecture/references/code-quality.md` | `rules/python-custom-context-managers.md`, `rules/python-error-handling.md`, `rules/python-early-return.md` | Lines 180-201 (rule 13's SQLite class whose __exit__ reads a connection never assigned when connect() fails) become the partial-setup Bad case, rewritten with ExitStack and pop_all in the Good Example. Rule 12's blanket "never `except Exception`" is relaxed to the engine's surfacing-recovery rule (lines 160-178); rule 4's deep-nesting example becomes guard clauses and a per-item helper (lines 46-71). |
| `skills/clean-architecture/references/refactoring-case-studies.md` | `rules/python-error-handling.md`, `rules/python-error-boundaries.md`, `rules/python-early-return.md` | Move 8 (lines 210-231): the specific catch now chains with `raise ... from exc`. Move 14 (lines 352-373): "return one type from every path" becomes one Note under the engine's absence convention. Moves 1-2 (lines 15-62): guard clauses with `continue` and a named predicate. |

Distilled (credited by name only, no vendored text):

- `rules/python-data-shapes.md`
- `rules/python-idioms.md`
- `rules/python-classes-and-protocols.md`
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

## domino-docs

Source: the Domino Data Lab 6.2 user, admin and API documentation, cited by page id.
Form: distilled (credited by name only, not vendored; no open license).

Each row names the files that restate a page's facts in the engine's own
words; those files stay under "Engine-written files". Pages a later lane
uses gain its files in their row.

### domino-apps

| Upstream file | Core files | Changes |
| --- | --- | --- |
| `user_guide/9d3c12` | `SKILL.md`, `rules/domino-app-bind-host-port.md`, `rules/domino-app-launch-script.md` | Facts restated: the launch contract (one launch file, a process on 0.0.0.0:8888 that Domino watches). |
| `user_guide/6a2215` | `SKILL.md`, `rules/domino-app-url-prefix.md`, `rules/domino-app-viewer-identity.md`, `rules/domino-app-verify-viewer-jwt.md`, `rules/domino-app-starter-settings.md` | Facts restated: the injected headers and DOMINO_RUN_HOST_PATH; user-level variables follow the starter. |
| `user_guide/b99d5d` | `SKILL.md` | Facts restated in the Quick Reference: runtime file writes do not persist. |
| `admin_guide/71d6ad` | `SKILL.md`, `rules/domino-app-viewer-identity.md` | Facts restated: the default proxy limits; anonymous access to public products. |
| `user_guide/a537c2` | `rules/domino-app-bind-host-port.md` | Fact restated: every framework serves TCP 8888. Not reproduced: the Dash stub's debug-on run line and the R Shiny runApp lines (unsafe / R-only). |
| `user_guide/2039f2` | `rules/domino-app-bind-host-port.md` | Fact restated: host 0.0.0.0, port 8888. Not reproduced: the debug-on launch script, the DFS layout tree and the publish click-path. |
| `user_guide/cb9195` | `rules/domino-app-bind-host-port.md`, `rules/domino-app-url-prefix.md`, `rules/domino-app-relative-urls.md`, `rules/domino-app-viewer-identity.md`, `rules/domino-app-verify-viewer-jwt.md`, `rules/domino-app-viewer-token.md` | Facts restated: the base path variable, the three identity levels, RS256 with audience apps, extended-identity consent. Not reproduced (unsafe): the basic identity launch script (debug on, no port), the JWT snippet fetching the key set over plain HTTP on every call with no timeout, and the decoded-payload sample. |
| `user_guide/9b11ea` | `rules/domino-app-bind-host-port.md` | Fact restated: an empty host binds every interface. Not reproduced: the example serving the whole working directory (unsafe). |
| `user_guide/2c3a33` | `rules/domino-app-bind-host-port.md`, `rules/domino-app-launch-script.md`, `rules/domino-app-starter-settings.md`, `rules/domino-app-endpoint-auth.md` | Facts restated: Streamlit's 8501 default, an executable launch script at the project root, a publisher's user-level key. Not reproduced (unsafe): CORS and XSRF protection off, usage statistics on, endpoint URL and token in the code file, unpinned installs; the dead example-repo pointer and model names are dropped. |
| `user_guide/de2589` | `rules/domino-app-url-prefix.md`, `rules/domino-app-launch-script.md` | Facts restated: the prefix variable read for the browser side; a one-command launch script. Not reproduced: the environment and publish click-paths and the debug-on run line (unsafe). |
| `support_kb/SecureIdentityPropagationToAppsEnabled` | `rules/domino-app-url-prefix.md` | Fact restated: hand-built prefixes break after a restart under the secure flag. |
| `user_guide/cfc79e` | `rules/domino-app-url-prefix.md`, `rules/domino-app-publisher-data-rights.md` | Facts restated: the secure flag changes the host path; a configuration record decides dataset mounting. |
| `admin_guide/6469bf` | `rules/domino-app-url-prefix.md`, `rules/domino-app-viewer-identity.md`, `rules/domino-app-verify-viewer-jwt.md` | Facts restated: the secure flag defaults on in 6.2; anonymous viewers are possible. |
| `user_guide/55fc89` | `rules/domino-app-url-prefix.md`, `rules/domino-app-starter-settings.md` | Facts restated: the run variables of the broken prefix and DOMINO_STARTING_USERNAME. Not used: the variable glossary and deprecated variables (domino-jobs' shared basics). |
| `user_guide/b04682` | `rules/domino-app-launch-script.md`, `rules/domino-app-relative-urls.md`, `rules/domino-app-endpoint-auth.md` | Practices restated: a minimal launch script, no hard-coded URLs, paths or tokens. |
| `user_guide/f3cc84` | `rules/domino-app-launch-script.md` | Fact restated: launch-file names are free-form. Not used: the audit App's sizing and unsupported-forks notes (product-specific). |
| `user_guide/cd0095` | `rules/domino-app-relative-urls.md`, `rules/domino-app-publisher-data-rights.md`, `rules/domino-app-viewer-token.md` | Facts restated: custom URL paths; the App acts as its publisher; acting for viewers is admin-only and grants full access. |
| `user_guide/5bef19` | `rules/domino-app-publisher-data-rights.md` | Facts restated: mounts use the creator's access; per-viewer access goes through the Data API SDK. |
| `user_guide/e3ec27` | `rules/domino-app-publisher-data-rights.md`, `rules/domino-app-starter-settings.md` | Facts restated: mounts and data sources use the starter's permissions and credentials. |
| `admin_guide/a9e507` | `rules/domino-app-viewer-token.md` | Fact restated: App execution logs are kept indefinitely and go into support bundles. |
| `user_guide/bb4b24` | `rules/domino-app-viewer-token.md` | Fact restated: App stdout and stderr are part of the support bundle. |
| `user_guide/6ac5a1` | `rules/domino-app-starter-settings.md` | Fact restated: the user value wins over project and environment values. Not used: the reserved names and naming syntax (domino-jobs' shared basics). |
| `user_guide/e038f2` | `rules/domino-app-endpoint-auth.md` | Facts restated: restricted endpoints, basic auth for sync and Bearer for async, per-endpoint tokens. |
| `user_guide/71635d` | DROP | Section landing page: one-line pointers to child pages, nothing actionable. |
| `user_guide/e92082` | DROP | R-only Shiny walkthrough; its 0.0.0.0:8888 fact is restated from a537c2. |
| `user_guide/a29497` | DROP | Partial: the claim that Apps never scale horizontally is stale; the sizing arithmetic and the R Shiny single-process paragraph are not rule material. |
| `user_guide/5aedde` | DROP | Agent deployment, tracing and runs belong to the domino-agents skill. |
| `user_guide/d95a3c` | DROP | Reserved project files are detector markers and domino-jobs results material, not App guidance. |
| `user_guide/ccaee6` | DROP | The Git-based /mnt layout is domino-jobs' shared basics. |
| `support_kb/docs-lifecycle` | DROP | Docs lifecycle and the client compatibility matrix: provenance facts, not rule text. |

### domino-jobs

| Upstream file | Core files | Changes |
| --- | --- | --- |
| `user_guide/5dce1f` | `SKILL.md`, `rules/domino-job-schedules.md`, `rules/domino-idempotent-jobs.md` | Facts restated: the schedule fields (branch or commit, command, tier, environment revision, datasets), Quartz expressions, Run sequentially and overlapping runs, the notify and endpoint-update actions. D65 Note: the page calls `0 5 * ? * *` daily; the rule states that it fires at minute 5 of every hour. |
| `user_guide/d2b098` | `rules/domino-job-schedules.md` | Fact restated: copying a project does not copy its schedules. |
| `user_guide/e4f67f` | `rules/domino-job-schedules.md`, `rules/domino-launch-jobs-from-code.md` | Facts restated: bigger pipelines go to external orchestrators, which only start Domino jobs; Airflow workers install the `dominodatalab[airflow]` extra. |
| `user_guide/af97b7` | `rules/domino-idempotent-jobs.md` | Facts restated: re-runs with the original or the current code keep the original arguments; jobs started from a commit never pick up new commits. Not used: tagging, renaming and stopping from the Active tab, volume sizes, tier grouping and cluster attachment (UI-only, no effect on job code). |
| `user_guide/e09156` | `SKILL.md`, `rules/domino-idempotent-jobs.md`, `rules/domino-flow-task-io.md`, `rules/domino-flow-task-purity.md` | Facts restated: inputs as files under /workflow/inputs, every declared output under /workflow/outputs or the task fails, DOMINO_IS_WORKFLOW_JOB, read-only snapshot mounts (one per dataset, never version 0), retries, timeout, cache and cache_version, use_latest=False with IDs. |
| `user_guide/2629d4` | `rules/domino-idempotent-jobs.md`, `rules/domino-spot-checkpoints.md` | Facts restated: spot reclaims fail and retry jobs; checkpoints under the artifacts directory are mounted at the next start, not after it; rank in file names; retry after 30 minutes, then a non-spot tier. D65 Note: the page names only the Git-based path and AWS spot capacity, so DFS behavior is left to verify. |
| `api_guide/c5ef26` | `rules/domino-idempotent-jobs.md`, `rules/domino-launch-jobs-from-code.md` | Facts restated: job_start and its defaults, job_start_blocking's max_poll_time, job_status, job_stop(commit_results), job_restart, the 2.0 client floor for 6.2. D65 Note: the undocumented failure behavior of job_start_blocking becomes an explicit state check. Not used: budgets, billing tags, files and blobs, App publishing and dataset upload helpers (not needed by job code). |
| `api_guide/8c929e` | `rules/domino-launch-jobs-from-code.md` | Facts restated: POST /api/jobs/v1/jobs starts a job and there is no v1 stop endpoint. |
| `user_guide/866fae` | `rules/domino-launch-jobs-from-code.md` | Fact restated in the orchestrator Note: Kubeflow uses the same client library. Not reproduced: the page's misnamed package. |
| `user_guide/752b35` | `rules/domino-launch-jobs-from-code.md` | Index of external orchestrators: informs the orchestrator Note only. |
| `user_guide/9355a5` | `rules/domino-launch-jobs-from-code.md` | Fact restated: `domino run --wait` blocks until the job ends. |
| `user_guide/e21e55` | `rules/domino-launch-jobs-from-code.md` | Fact restated: CLI versions before 6.2.3 cannot log in. |
| `user_guide/b4cb04` | `rules/domino-launch-jobs-from-code.md` | Fact restated: the final state names (Succeeded, Failed, Error, Stopped). |
| `user_guide/78acf5` | `rules/domino-flow-task-io.md`, `rules/domino-flow-task-purity.md` | Facts restated: tasks are Domino jobs on Flyte with typed inputs and outputs; a task reads versioned inputs and writes defined outputs; tasks writing read-write datasets cannot run in Flows; many tiny computations fit poorly. |
| `user_guide/55fc89` | `rules/domino-flow-task-io.md` | Fact restated: DOMINO_IS_WORKFLOW_JOB arrives as a text flag in the environment. |
| `user_guide/5b84c5` | `SKILL.md`, `rules/domino-job-results.md`, `rules/domino-job-logging.md`, `rules/domino-job-stats-file.md`, `rules/domino-job-email-report.md` | Facts restated: .dominoresults and .dominoignore syntax, dominostats.json at the root (deleted before each run, keys become dashboard columns), the success email with the stdout tail and up to ten result files, email.html placement, its title as the subject. D65 Note: the tip naming the file `emails.html` is a slip; the rule uses `email.html`. |
| `user_guide/bfeeae` | `rules/domino-job-results.md` | Facts restated: .dominoignore at the project root applies to CLI and end-of-run sync, the Git directory is always ignored, isolated results branches. |
| `user_guide/31abd5` | `rules/domino-job-results.md` | Fact restated: results on an isolated branch are fetched with the download-results command. |
| `user_guide/de4abb` | `rules/domino-job-results.md`, `rules/domino-job-logging.md` | Facts restated: .dominokeep keeps empty directories; results/stdout.txt holds the console tail in DFS projects. |
| `user_guide/fda6d8` | `rules/domino-job-results.md` | Fact restated: comparisons match files by name, so result names carry no version. |
| `user_guide/ee0a08` | `rules/domino-job-results.md` | Fact restated: the example admin caps of 250 compared files and about 1 MB of diffs. |
| `user_guide/e1c37a` | `rules/domino-job-results.md`, `rules/domino-job-logging.md`, `rules/domino-job-stats-file.md` | Facts restated: results are the files a run adds or changes; Setup Output and User Output logs; resource usage kept about 15 days; MLflow recommended for metrics. Not used: dashboard filtering, commenting and archiving (UI workflows). |
| `user_guide/5b3b05` | `rules/domino-job-results.md` | Fact restated: in Git-based projects the results are the artifacts. |
| `user_guide/a068c1` | `rules/domino-job-logging.md` | Fact restated: .py files run with python -u, so prints are unbuffered. |
| `admin_guide/a9e507` | `rules/domino-job-logging.md` | Fact restated: execution logs are kept indefinitely and go into support bundles. |
| `user_guide/0264e0` | `rules/domino-job-stats-file.md` | Contradiction resolved: the page calls the file `domino.json`; the rule keeps `dominostats.json` and says so. |
| `user_guide/f4e1e3` | `rules/domino-job-email-report.md` | Fact restated: a Launcher's email.html becomes the body mailed to its notification list. |
| `user_guide/db2820` | DROP | Long-running job notifications are a per-user UI preference; nothing for code to do. |
| `report/domino-jobs R6` | DROP | Report candidate 'persist anything needed beyond 15 days': the limit covers resource-usage details only, not logs or metrics, so it shrinks to one Note in domino-job-logging. |

## Engine-written files

Files written for the engine with no upstream text, per core skill. A file
that comes to hold vendored text moves from here into its source's table.

### design-patterns

### domino-agents

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

### domino-jobs

- `SKILL.md`
- `rules/domino-job-schedules.md`
- `rules/domino-idempotent-jobs.md`
- `rules/domino-spot-checkpoints.md`
- `rules/domino-launch-jobs-from-code.md`
- `rules/domino-flow-task-io.md`
- `rules/domino-flow-task-purity.md`
- `rules/domino-job-results.md`
- `rules/domino-job-logging.md`
- `rules/domino-job-stats-file.md`
- `rules/domino-job-email-report.md`

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
