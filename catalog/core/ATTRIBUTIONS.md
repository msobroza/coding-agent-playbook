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

The domino-apps skill (its SKILL.md and every rule under its rules/
directory, listed under "Engine-written files") distills facts from the
Domino Data Lab 6.2 user and admin documentation, which carries no open
license; it is credited by name only and not vendored. No sentences or
examples from the documentation are copied, its unsafe example settings are
not reproduced, and the facts are restated in the engine's own words. The
`domino-docs` section below records, per documentation page, the files that
use its facts or why it was dropped; a distilled source has no pin and no
license copy.

The domino-jobs skill distills facts from the Domino Data Lab 6.2 user guide
and its python-domino API guide in the same way: credited by name only, no
sentences, code or shell snippets copied, its files listed under
"Engine-written files" and its pages recorded in the `domino-docs` section.

## python-best-practices

Source: the "python-best-practices" agent skills by Ludo Technologies LLC, tag v0.8.0.
Commit: `fa0d3f58afb8bf56c028bb559e0e7bc1538e079a`
License: MIT License. Copyright (c) 2026 Ludo Technologies LLC.

Its impact ratings inform each rule's section and priority. Ideas from it also
shaped the python-error-handling, python-typing, python-docstrings,
python-data-shapes, python-idioms and pytest rules.

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

Distilled (credited by name only, no vendored text):

- `rules/python-performance-idioms.md`
- `rules/python-async.md`
- `rules/python-classes-and-protocols.md`
- `rules/python-error-handling.md`
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
| `skills/clean-architecture/references/code-smells.md` | `rules/python-dependency-injection.md` | Lines 382-399 (hardwired dependency): the Bad Example shape and the `self.x = ConcreteClass()` detection line, with the vendor class name made neutral. |
| `skills/clean-architecture/references/function-design.md` | `rules/python-pure-core.md` | Lines 100-209 (pure functions, side effects): the argument-mutation Bad case, returning new values and the repository-parameter shell become the Bad Example and Notes; float amounts dropped. |
| `skills/clean-architecture/references/testable-api.md` | `rules/python-pure-core.md` | Lines 385-403: injecting today's date instead of reading the clock becomes the date parameter and the fixed-dates testing Note. |
| `skills/clean-architecture/references/design-principles.md` | `rules/python-pure-core.md` | Lines 36-53 (separate I/O from domain models): folded into the __str__-or-presenter and input()-in-the-entry-point Note; no example copied. |
| `skills/clean-architecture/references/context-managers.md` | `rules/python-context-managers.md`, `rules/python-custom-context-managers.md` | python-context-managers: lines 1-37 and 120-143 (manual cleanup, file handling; the except-Exception rollback replaced by the engine's committed-flag transaction), 181-235 (nesting, ExitStack, async managers) and 236-251 (Do/Don't, suppressing in __exit__ replaced by contextlib.suppress) become the sync Bad/Good pair and Notes. python-custom-context-managers: lines 38-119 (class-based manager, __exit__ parameters, @contextmanager, class vs decorator) and 144-180 (temporary state, timing logged through logging instead of print) become its Good Example and Notes. |
| `skills/clean-architecture/references/patterns/retry.md` | `rules/python-retries-and-timeouts.md` | Lines 1-38 (simple retry) become the Bad Example, annotated with what is wrong; lines 189-222 (when to retry, when not, idempotency) become Notes, the idempotency-key example rewritten without dict rows. Dropped: exponential backoff, the except-Exception decorator, fallback defaults, the tenacity advice, the LLM case, the circuit breaker and the cross-file links (39-188, 223-278), because engine retries are fixed-delay, transient-only and re-raise the original, and add backoff or fallbacks only when asked (pca-F2, pbp-B#54). |
| `skills/clean-architecture/references/decorators.md` | `rules/python-retries-and-timeouts.md` | Lines 64-136 (retry decorator and its async version): the decorator form, re-raising the original and awaiting asyncio.sleep become Notes. Dropped: 'catching Exception broadly is acceptable in retry decorators' and exponential backoff by default (102-103) and 'use tenacity in production' (251), because engine retries catch only transient errors at a fixed delay (pca-F2); the re-raise point (104) is kept. |
| `skills/clean-architecture/references/async-patterns.md` | `rules/python-custom-context-managers.md` | Lines 110-155 (__aenter__/__aexit__, @asynccontextmanager) become the async Note; the unguarded close and the commit inside the session manager are not vendored. |
| `skills/clean-architecture/references/error-handling.md` | `rules/python-custom-context-managers.md` | Lines 129-217 (the finally block, context managers preferred): the try/finally repeated across fetch functions becomes the Bad Example and the 'why a context manager beats try/finally' list the Description; print calls dropped. Dropped: the 'ACCEPTABLE: retry decorator catches Exception' example (93-103), because a retry catches only transient errors (pca-F2) and the unit-of-work rollback form is python-context-managers' committed-flag transaction (pca-F8). |
| `commands/make-pythonic.md` | `rules/python-custom-context-managers.md` | Line 26 ('try/finally for resource cleanup' -> context manager) becomes a Note. |
| `skills/clean-architecture/references/code-quality.md` | `rules/python-custom-context-managers.md` | Lines 180-201 (rule 13's SQLite class whose __exit__ reads a connection never assigned when connect() fails) become the partial-setup Bad case, rewritten with ExitStack and pop_all in the Good Example. |

Distilled (credited by name only, no vendored text):

- `rules/python-data-shapes.md`
- `rules/python-idioms.md`
- `rules/python-classes-and-protocols.md`
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

## domino-docs

Source: the Domino Data Lab 6.2 user and admin documentation, cited by page id.
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
| `user_guide/de4abb` | `SKILL.md` | Facts restated in the Quick Reference: the DFS working directory and what a DFS run syncs back. |
| `user_guide/ccaee6` | `SKILL.md` | Facts restated in the Quick Reference: the Git-based layout (/mnt/code, /mnt/data, /mnt/artifacts). |
| `user_guide/910370` | `SKILL.md`, `rules/domino-datasets-for-large-data.md` | Facts restated: a Git-based job syncs only artifacts back and pushes no code; Git LFS is not supported. |
| `user_guide/55fc89` | `SKILL.md` | Facts restated in the Quick Reference: the variables that tell the project type and a Flow task apart. |
| `user_guide/af97b7` | `rules/domino-job-exit-codes.md` | Facts restated: every non-zero exit fails the job; 'Publish after complete' republishes only after success. Not reproduced: the status mapping shell snippet (it exits before its test). Not used: tagging, renaming, stopping from the Active tab, volume sizing, tier grouping and cluster attachment (UI-only). |
| `user_guide/b4cb04` | `rules/domino-job-exit-codes.md`, `rules/domino-datasets-for-large-data.md`, `rules/domino-run-scoped-writes.md` | Facts restated: Failed versus Error; Preparing copies project files; Stopping still syncs new and changed files. |
| `user_guide/5dce1f` | `rules/domino-job-exit-codes.md`, `rules/domino-run-scoped-writes.md` | Facts restated: 'Update Domino endpoint' runs after completion with success unstated; without 'Run sequentially' runs overlap. |
| `user_guide/5b84c5` | `rules/domino-job-exit-codes.md` | Fact restated: failure emails are sent by default. |
| `user_guide/e09156` | `SKILL.md`, `rules/domino-job-exit-codes.md`, `rules/domino-dataset-snapshots.md` | Facts restated: a missing declared output fails a Flow task; Flows mount one snapshot per dataset at the plain path and refuse version 0. |
| `api_guide/c5ef26` | `rules/domino-job-exit-codes.md`, `rules/domino-run-scoped-writes.md` | Facts restated: callers poll job status; stopping a job commits its results by default. Not used: budgets, billing tags, files and blobs, App publishing and the dataset upload helpers. |
| `user_guide/942549` | `rules/domino-job-entry-point.md`, `rules/domino-run-scoped-writes.md` | Facts restated: a job is a headless run of one file from the UI, a schedule, the CLI or the API; parallel runs get separate containers. |
| `user_guide/a068c1` | `rules/domino-job-entry-point.md` | Facts restated: the interpreter follows the extension (.py with python -u, .sh with bash, .ipynb executed and saved over itself); custom handlers need an admin flag and two handler paths are given. Not used: the R, R Markdown, MATLAB, Perl, Julia, F#, SAS and Stata handlers and the custom-handler Dockerfile recipe (not Python job code). |
| `user_guide/f4e1e3` | `rules/domino-job-entry-point.md`, `rules/domino-launcher-arguments.md`, `rules/domino-launcher-uploads.md` | Facts restated: a Launcher fills a command template and runs a job; values arrive single-quoted and unexpanded, files as paths, multi-selects comma-separated; uploads and every touched file become results; an email.html becomes the notification body. Not used: the JSON edit mode (private deployments only), the R parsing examples and the knitr, nbconvert and explainability tips. |
| `user_guide/fda6d8` | `rules/domino-job-entry-point.md` | Fact restated: jobs, not workspaces, give the strongest reproducibility. |
| `user_guide/56938d` | `rules/domino-datasets-for-large-data.md`, `rules/domino-materialize-external-data.md` | Facts restated: the per-project file and per-file transfer limits; Datasets are mounted, not copied; cluster workers cannot see project files; TrainingSets persist versioned data frames. |
| `user_guide/b4f02f` | `rules/domino-datasets-for-large-data.md` | Fact restated: sync is not designed for more than about 10 GB or 100,000 files. |
| `user_guide/e6e601` | `rules/domino-datasets-for-large-data.md` | Fact restated: every execution copies all project files at start, Datasets excepted. |
| `user_guide/305721` | `rules/domino-datasets-for-large-data.md` | Fact restated: keep big data in Datasets. |
| `user_guide/f7292e` | `rules/domino-datasets-for-large-data.md`, `rules/domino-run-scoped-writes.md` | Facts restated: .noLock skips file locking during sync, and files must not change while a sync runs. |
| `user_guide/9355a5` | `rules/domino-datasets-for-large-data.md` | Facts restated: the project upload may time out above about 1,000 files; the dataset upload overwrites unless --fileUploadSetting (case-sensitive) says otherwise. |
| `admin_guide/71d6ad` | `rules/domino-datasets-for-large-data.md` | Fact restated: copying project files into a run times out after 15 minutes by default. |
| `user_guide/b99d5d` | `rules/domino-run-scoped-writes.md` | Fact restated: Domino does not serialize concurrent access to shared storage. |
| `user_guide/6942ab` | `SKILL.md`, `rules/domino-dataset-snapshots.md` | Facts restated: snapshot paths by number for local, shared and imported datasets in DFS and Git-based projects; mount mode by role. |
| `user_guide/dbdbff` | `rules/domino-dataset-snapshots.md` | Facts restated: snapshots are immutable copies whose creation time grows with size; no file may change while one is taken; a reassigned tag mounts only the most recently added. Not used: the UI and CLI snapshot and tagging workflows. |
| `user_guide/0264e0` | `rules/domino-dataset-snapshots.md`, `rules/domino-materialize-external-data.md` | Facts restated: what the reproducibility engine records per run, including the snapshot used. |
| `user_guide/e568d7` | `rules/domino-materialize-external-data.md` | Facts restated: databases, APIs, network drives and data sources are invisible to the reproducibility engine; materialize extracts; keep project-file results under 10 GB. |
| `user_guide/ac5c29` | DROP | MATLAB Launcher wrapper: nothing for Python repos beyond the Launcher argument rule. |

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
- `rules/domino-job-exit-codes.md`
- `rules/domino-job-entry-point.md`
- `rules/domino-launcher-arguments.md`
- `rules/domino-launcher-uploads.md`
- `rules/domino-datasets-for-large-data.md`
- `rules/domino-run-scoped-writes.md`
- `rules/domino-dataset-snapshots.md`
- `rules/domino-materialize-external-data.md`

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
