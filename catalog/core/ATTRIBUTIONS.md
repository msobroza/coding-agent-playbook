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

The domino-apps skill (its SKILL.md and every rule under its rules/
directory, listed under "Engine-written files") distills facts from the
Domino Data Lab 6.2 user and admin documentation, which carries no open
license; it is credited by name only and not vendored. No sentences or
examples from the documentation are copied, its unsafe example settings are
not reproduced, and the facts are restated in the engine's own words. The
`domino-docs` section below records, per documentation page, the files that
use its facts or why it was dropped; a distilled source has no pin and no
license copy.

The domino-agents skill's SKILL.md and rules distill facts from the Domino
Data Lab 6.2 documentation (the agentic-systems, Apps, python-domino and
environment variable pages), which carries no open license, and ideas from the
`simple_agent_api_only` example agent by Domino Data Lab (Apache-2.0, commit
`eee728252c42fa660e65c2dccbea6ae4f679c04c`). The rules restate those facts and
ideas in the engine's own words, with no sentences or code copied, so they are
listed under "Engine-written files", with the upstream files each one draws on
and the upstream text they leave out.

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
| `skills/clean-architecture/SKILL.md` | `SKILL.md` | Lines 73-83 and 85-122 only: the seven principles one line each, mapped to this skill's sections (the mixin ban, 80, dropped: engine wins, F1), and the smell-to-pattern table merged with the engine's lightest-form table ('signal, lightest form, heavier form, stop when, pattern'); the singleton, value-object, registry, notification and plugin rows rewritten to the engine decisions (F9, F14, F10); repository, unit of work, CQRS, event sourcing and retry rows name their owning skills; the default preferences as bullets. |
| `skills/clean-architecture/references/design-principles.md` | `rules/design-single-responsibility.md`, `rules/design-tell-dont-ask.md`, `rules/design-low-coupling.md`, `rules/design-dependency-inversion.md`, `rules/design-open-closed.md`, `rules/design-composition-over-inheritance.md` | Lines 5-35 and 55-87 become function-level split notes; the Law of Demeter and Information Expert (164-175, 429-447) the tell-don't-ask examples; the coupling ladder, global-coupling example and trade-off chain (90-163, 176-215) the low-coupling rule, with no literal token and no real host, settings built once by the entry point, and the stamp-coupling Protocol shrunk to one note; 'Depend on Abstractions' (216-255) the dependency-inversion skeleton with a Callable alias owned by the consumer; dictionary mapping as OCP (419-421) a note; configuration vs subclass and the composition pattern (276-345) the composition rule, pay in int cents, the mixin ban (342) dropped (engine wins, F1). |
| `skills/clean-architecture/references/grasp-principles.md` | `rules/design-tell-dont-ask.md`, `rules/design-split-god-class.md`, `rules/design-grasp-responsibilities.md`, `rules/design-low-coupling.md`, `rules/design-dependency-inversion.md`, `rules/design-open-closed.md` | Creator, Controller, Indirection and Pure Fabrication (17-38, 70-97, 173-202, 228-249) become the GRASP rule: an injected date instead of date.today(), Decimal rates instead of float, a thin handler without a web framework; Information Expert and its caveat (44-69) go to tell-don't-ask; low-cohesion signs (128-140) to the god-class rule without fixed counts (F30); the net-price example (102-127) to a low-coupling note in Decimal; Polymorphism (144-172) to open-closed; Protected Variations (206-227) to a dependency-inversion note. Course attribution and the three-layer and DBInterface asides (5, 40, 98, 124, 224, 250) dropped (python-architecture owns layering). |
| `skills/clean-architecture/references/code-quality.md` | `rules/design-tell-dont-ask.md`, `rules/design-split-god-class.md`, `rules/design-open-closed.md` | Tell-don't-ask and feature envy (72-85, 110-113) the tell-don't-ask skeleton, with an Enum status and a domain error; no god classes (106-109) the god-class rule; isinstance dispatch (266-284) an open-closed note. |
| `skills/clean-architecture/references/code-smells.md` | `rules/design-tell-dont-ask.md`, `rules/design-split-god-class.md`, `rules/design-liskov-substitution.md`, `rules/design-pipeline.md` | Tell-don't-ask violations (276-298) the feature-envy example; too many instance variables (112-151) a note on splitting a record, without the fixed count (F30); subclasses that break substitution (334) a Liskov warning sign; missing function composition (336-363) only as the pipeline's restraint note. DROP: its reduce-and-named-lambdas example for three reassignments (336-360; F22). |
| `skills/clean-architecture/references/refactoring-case-studies.md` | `rules/design-tell-dont-ask.md`, `rules/design-open-closed.md` | Encapsulate data-structure access (232-249) a tell-don't-ask note; rules consolidated into a list of predicates (180-209) an open-closed note, as a role-named Callable alias. |
| `skills/clean-architecture/references/dependency-injection.md` | `rules/design-dependency-inversion.md`, `rules/design-bridge.md` | The DI-vs-DIP framing (3) and table (32-50) restated in prose; the Bad Example is DI without DIP, a vendor class imported by the consumer. The two-axes section (152-177) becomes the bridge's Protocol note (payment method by authorization method). Title and attribution lines (1, 5, 250) dropped. |
| `skills/clean-architecture/references/patterns/template-method.md` | `rules/design-interface-segregation.md`, `rules/design-template-method.md` | Protocol segregation (251-321) and the 4-5 method heuristic (342) as notes, without endorsing or banning mixins. The duplicated-algorithm problem, why Protocols alone hold no behavior, the free function over a Protocol and the ABC criteria (1-69, 155-250, 322-343) become the template-method rule: the trading bots rewritten as restockers with Decimal prices and no print, the ABC form summarized in Notes with `typing.final`. DROP: course attribution (3) and the full ABC trading-bot code (70-153), summarized in Notes. |
| `skills/clean-architecture/references/function-design.md` | `rules/design-callback.md`, `rules/design-function-builder.md` | Functions as values (5-11) open the callback rule; a tuple of post-processing functions passed as an `Iterable` (281-324) becomes a callback note with amounts in int cents and no print; returning a function (`make_multiplier`, 263-279) the function builder's smallest form. DROP: the 'everything is an object' trivia printing `type()` results (27-39). |
| `skills/clean-architecture/references/patterns/functional.md` | `rules/design-callback.md`, `rules/design-function-wrapper.md`, `rules/design-function-builder.md` | Callback (1-2, 4-101): a job that hard-codes its reactions as the Bad Example, a role-named alias with a named no-op default (not a lambda-returning-lambda `default_factory`) and a handler list as the Good Example, reactions logging instead of printing. Function wrapper (103-170): amounts in int cents with Decimal rates and explicit rounding, the loyalty table a `Final` mapping keyed by the Enum, no print. Function builder (172-282): the mail sender takes a settings object and an injected send function, no literal password and no real mail host. The summary table and decision guide (284-300) split across the three rules. DROP: course attribution (3). |
| `skills/clean-architecture/references/patterns/state.md` | `rules/design-state.md` | Recognize, problem, when and when not, and the relation to strategy (1-128, 150-167): the document workflow becomes the Bad Example with repeated status checks; the Good Example is an Enum plus a transition table that raises a domain error naming the state and the action; Protocol state objects become the heavier form in Notes, without print. DROP: module-based states (129-146), which lose type checking. |
| `skills/clean-architecture/references/patterns/builder.md` | `rules/design-builder.md` | Problem, fluent builder with a frozen product, when to use, design notes and validation in `build()` (1-114, 139-194): the HTML page replaced by a route with no markup and no author metadata, product fields as tuples, `build()` validating and copying; chaining methods use a string forward reference with `Self` named for 3.11+; the builder-versus-fluent contrast (153-171) one note naming design-fluent-interface. DROP: the library 'real-world builders' trivia (115-135). |
| `skills/clean-architecture/references/patterns/fluent-interface.md` | `rules/design-fluent-interface.md` | Recognize, problem, return-self chaining, domain verbs, parenthesized chains, the `Self` hint, when and when not, and fluent versus builder (1-6, 8-141, 150-155): the parallel steps and durations lists become the Bad Example; the Good Example returns a new frozen instance per verb via `dataclasses.replace`, holding one tuple of timed-step records. DROP: course attribution (7) and the library trivia list (142-149). |
| `skills/clean-architecture/references/patterns/facade.md` | `rules/design-facade.md` | Client coupled to a subsystem, the facade class, binding controllers, when and when not, and trade-offs (1-130, 148-172): the facade receives its collaborators and device registration moves to the entry point; no subsystem types returned. DROP: the MVC and three-layer mapping (131-145; python-architecture owns layering). |
| `skills/clean-architecture/references/patterns/pipeline.md` | `rules/design-pipeline.md` | The nested-call problem, composition and when to use (1-25, 118-184, 243-260): a typed step alias with named functions and failure wrapping that names the step; chain of responsibility kept as the one-line heavier form; data-frame pipelines named as the ml-data skill's. DROP: course attribution (3), the chain-of-responsibility class code (26-117) and the workflow-tool section (223-242). |
| `skills/clean-architecture/references/patterns/command.md` | `rules/design-command.md` | Problem, the functional form with undo closures and batches, when to use, and trade-offs (1-54, 271-320, 341-360, 390-432): example titles neutral, the batch undoes the done steps in reverse and re-raises when one fails, and the class form becomes a note pointing to command-progression.md. DROP: course attribution (5). |
| `skills/clean-architecture/references/patterns/singleton.md` | `rules/design-singleton.md` | Historical context, injection as the preferred approach, why class-based singletons hurt, and the object pool (1-40, 160-225): the Bad Example is a class-level `get_instance()` cache, the pool takes an injected factory and returns connections through a context manager; the bans stay with python-no-global-singletons. DROP: module-level config as an 'acceptable fallback', and the metaclass, thread-safe metaclass and caching `__new__` recipes (41-67, 71-158; F9). |
| `skills/clean-architecture/references/patterns/abstract-factory.md` | `rules/design-abstract-factory.md` | Problem, when to use and not, trade-offs and the decision guide (1-42, 440-525): flags selecting related calculators as the Bad Example, a frozen `TaxSystem` dataclass bundling matching callables (amounts in int cents, neutral family names) as the Good Example; the walkthrough is named as abstract-factory-progression.md. DROP: course attribution (5) and the `# type: ignore` mitigation (460-473), which conflicts with mandatory ignore codes. |
| `skills/clean-architecture/references/patterns/bridge.md` | `rules/design-bridge.md` | The Cartesian-product problem, when to stop, trade-offs and bridge versus strategy, adapter and injection (1-26, 458-508): real exchange names replaced by a stock-take report rendered and delivered through two `Callable` aliases; the walkthrough is named as bridge-progression.md. DROP: course attribution (5). |
| `commands/decouple.md` | `rules/design-tell-dont-ask.md`, `rules/design-low-coupling.md` | Checklist items only (15-17): global mutable state, content coupling and Law of Demeter violations, as notes; command frontmatter, $ARGUMENTS and plugin paths dropped (D9). |
| `commands/extract-god-class.md` | `rules/design-split-god-class.md` | Steps 13-34 as a non-interactive procedure: propose the split, apply it only when asked; AskUserQuestion and auto-apply (35-39, F28), frontmatter and plugin paths (1-11) dropped. |
| `skills/clean-architecture/references/pythonic-patterns.md` | `SKILL.md` | Lines 15-605 only as one row each of the pattern table ('signal, lightest form, heavier form, stop when, pattern'). DROP: the per-pattern summaries and their code (15-605), which the pattern rules duplicate; the retry (535-566), repository (498-514), unit-of-work (375-398), CQRS (337-354) and event-sourcing (317-336) summaries are covered by their owners' full files and become rows naming python-coding and python-architecture. |
| `commands/suggest-patterns.md` | `SKILL.md` | Lines 13-41: the smell-to-pattern rows, merged into the same pattern table; the singleton, value-object, registry and notification rows rewritten to the engine decisions (F9, F14, F10). DROP: command frontmatter, $ARGUMENTS and plugin paths (1-11, 53; D9). |
| `commands/make-pythonic.md` | `rules/design-composition-over-inheritance.md`, `rules/design-template-method.md`, `rules/design-abstract-factory.md` | Smell row 19 (deep inheritance or mixins -> composition with a Protocol) as the rule's premise, with mixins per the engine line (F1); row 25 (duplicated algorithm -> free function with a Protocol parameter) the template-method premise; row 21 (factory class hierarchies -> bundled functions) the abstract-factory premise, as a frozen dataclass instead of a tuple. |

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

Upstream files each rule draws on (example-agent files by path and lines, 6.2
documentation pages by guide and page id):

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
