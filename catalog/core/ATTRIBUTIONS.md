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
python-data-shapes, python-idioms and pytest rules.

### design-patterns

| Upstream file | Core files | Changes |
| --- | --- | --- |

### ml-data

| Upstream file | Core files | Changes |
| --- | --- | --- |
| `skills/data-science/rules/vec-no-python-loops.md` | `rules/ml-vectorization.md.j2` | Lines 8-79 are the skeleton: engine frontmatter; the mixed NumPy/pandas examples split into per-library `{% if %}` lines inside one Bad and one Good fence, with a polars pair (map_elements vs pl.when expressions) added; the add_discount money example (`price * 0.2`) becomes a parcel handling tier chosen by np.select over weights; arrays are annotated `npt.NDArray[np.float64]`; the numba/Cython rung becomes the engine's 'compiled extension only after the user agrees'; the perf-list-comprehension cross-reference becomes python-comprehensions and the group-by note a pointer to ml-named-aggregation; Notes merge the engine's library-neutral ladder, the per-item-effect loop and the per-library ladders, and name library-equivalents.md. Dropped: the '10-1000x' impact line and the '~10x faster' itertuples claim (77), unmeasured speed figures (pbp-D.2), keeping 'itertuples is still a row loop'. |
| `skills/data-science/rules/vec-no-incremental-growth.md` | `rules/ml-build-once.md.j2` | Lines 8-61 are the skeleton: engine frontmatter; per-library lines with a polars pair (vstack in a loop vs one concat); the preallocated array gets `dtype=np.float64` and is filled by a per-file effect, while random values come from the injected generator in one call instead of a per-element draw_sample() loop; the read_csv calls name their dtypes and the dtype-explicit-io cross-reference becomes ml-dtypes-at-load; 'DataFrame.append was removed in pandas 2.0' (61) is reworded version-neutrally; Parquet batches only where the repo already has a Parquet engine. Dropped: the O(n^2) impact line. |
| `skills/data-science/rules/mut-no-inplace.md` | `rules/ml-data-transforms.md.j2` | Lines 8-55 are the pandas branch's skeleton (the inplace=True description, the clean() Bad/Good pair, the take-a-frame-return-a-frame, rebinding and commented top-level memory-exception Notes): engine frontmatter; the description opens with the engine's library-neutral 'inputs are values' and NumPy (a slice written through vs np.minimum) and polars (insert_column vs with_columns) Bad/Good lines are added; pandas-3.0 statements are reworded version-neutrally; the design-pure-functions reference becomes python-pure-core and style-method-chaining becomes ml-method-chaining; Notes name review-signals.md. Dropped: the PDEP-8 roadmap sentence (11), a dated claim (version-neutral default). |
| `skills/data-science/rules/mut-loc-not-chained.md` | `rules/ml-loc-assignment.md` | Lines 8-50 nearly verbatim: engine frontmatter; copy-on-write behavior stated without pandas version numbers; the 'amount > 1000' money filter becomes a weight filter; the style-method-chaining reference becomes ml-method-chaining; a Note points to ml-data-transforms for frames a function received. Dropped: the 'enable CoW in pandas 2.x before 3.0' migration tip (51), a version-specific tip with no version predicate. |
| `skills/data-science/rules/dtype-explicit-io.md` | `rules/ml-dtypes-at-load.md.j2`, `rules/ml-check-after-load.md.j2` | ml-dtypes-at-load: lines 8-58 are the skeleton, opened with the engine's library-neutral 'decide types where data enters' bullets, with a polars pair (schema_overrides=, strict str.to_datetime) and an engine-written NumPy pair (np.loadtxt with dtype= and usecols=, serials as str); the float 'amount' becomes integer cents ('Int64'), 'region' a shared categorical constant, the date format a constant and the loader takes a Path; dtype_backend='pyarrow' and the Parquet round trip are worded 'where the repo already has it' (propose, never add); line 60 becomes a pointer to ml-numpy-dtypes and line 59 to ml-check-after-load. ml-check-after-load: line 59 (a drift fails fast instead of corrupting downstream numbers) becomes a Note. Dropped: the '2-10x' memory claim (pbp-D.2), the pandas-3.0 str-dtype sentence (57, version-neutral default) and the downcasting note (58), cut to fit the size cap. |
| `skills/data-science/rules/dtype-numpy-explicit.md` | `rules/ml-numpy-dtypes.md`, `rules/ml-check-after-load.md.j2` | ml-numpy-dtypes: lines 8-41 and 44-51 nearly verbatim: engine frontmatter; the engine's int64 headroom for counts and cents added; the 'Since NumPy 2.0, NEP 50' note (51) reworded as version-neutral promotion behavior; a Note points to ml-check-after-load. ml-check-after-load: the boundary `assert embeddings.dtype == np.float32` (42-43) becomes the NumPy Bad case and a check that raises an error naming the actual and expected dtype and shape (pbp-B#46). |
| `skills/data-science/rules/dtype-categorical.md` | `rules/ml-categorical-labels.md.j2` | Lines 8-50 are the pandas branch's skeleton: engine frontmatter; the engine's 'one shared constant applied to every source' becomes part of the description; the inline 'category' strings of the Good Example become shared CategoricalDtype constants, and the per-source astype('category') becomes a Bad case; a polars pair (pl.Categorical vs a pl.Enum constant) added; 'the default since pandas 3.0' (47) becomes 'pass observed=True explicitly'. Dropped: the '5-20x' impact line and the '~1.2 GB', '~20 MB' and 'slow hashing' comments (pbp-D.2). |
| `skills/data-science/rules/schema-pandera.md` | `rules/ml-frame-validation.md.j2`, `rules/ml-check-after-load.md.j2` | ml-frame-validation: lines 8-65 are the skeleton, gated on the repo already depending on pandera (pbp-B#65): engine frontmatter; the loader takes a Path and parses dates with to_datetime and a format instead of parse_dates; float prices and the float revenue become integer gram weights (pbp-B#56); validation is lazy; the polars form renders when polars is declared without pandas, else as one Note; the validation-pydantic reference becomes pydantic-boundaries. ml-check-after-load: line 11 (first two sentences, worded for arrays and frames) becomes its Description and line 59 (validate once at the boundary) a Note. |
| `skills/data-science/rules/type-array-annotations.md` | `rules/ml-frame-validation.md.j2` | Lines 35-37, 53-54 and 68 (DataFrame[Schema] hints; the model doubles as type hint and validator, no separate TypedDict of columns) become ml-frame-validation's Good Example hints and first Note. |
| `skills/data-science/rules/*.md` | DROP | Every rule's `## References` block (13 sections, 24 URLs) is dropped (D7), and so are the unmeasured speed and memory multipliers of the `impactDescription` lines (vec-no-python-loops:4, vec-no-incremental-growth:4, dtype-categorical:4, dtype-explicit-io:4; pbp-D.2). The rest of each rule maps in its own row. |
| `skills/data-science/README.md` | DROP | D32: upstream README.md files are dropped. |
| `skills/data-science/metadata.json` | DROP | D32: metadata.json is dropped; sections come from SKILL.md (D17). |
| `skills/data-science/rules/_template.md` | DROP | D32: the rule template becomes the 'Writing a rule' section of catalog/README.md, not ml-data content. |

Distilled (credited by name only, no vendored text):

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
| `skills/clean-architecture/references/patterns/pipeline.md` | DROP | Lines 185-222 (pandas .pipe()): pipe with arguments is already covered by the pbp chaining guidance and the engine's convert_to_eur chain, and the example mutates its argument (`df.columns = ...`) and prints from main, contradicting ml-data-transforms; ml-data vendors no text from this source. |

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
