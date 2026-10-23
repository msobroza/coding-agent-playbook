# Where code goes

One question comes back with every change: which package does this code belong in, and where does its test go. This guide routes each kind of code to its layer, the package names that hold it and the rules that govern it. It is a routing table only: open the named rules for the detail.

## How to use this guide

Find the row for the code you are about to write and open the rules it names, usually one to three. A row naming a gated rule says when that rule applies. Package names follow the skill's layer table; when the repo already uses other names for a layer, keep the repo's names.

## Kind of code

| Kind of code | Layer | Package or module names | Rules |
| --- | --- | --- | --- |
| A business rule or invariant | domain | `domain`, `models`, `entities` | arch-rich-domain-model, arch-ubiquitous-language |
| A value object (money, an email, a date range) | domain | `domain` | arch-rich-domain-model |
| A domain error | domain | `domain` (an errors module beside the types it guards) | arch-rich-domain-model, arch-use-case-functions |
| A use case: load, let the domain decide, save, commit | application | `services`, `operations`, `use_cases`, `application` | arch-use-case-functions, arch-dependency-direction |
| A port for a store or a remote system | application, beside the use case that calls it | the consumer's module or a `ports` module next to it | arch-ports, arch-repository-port |
| A record passed between layers | domain, or application when only use cases share it | `domain`, `services` | arch-typed-records-across-layers |
| An ORM table or mapped class | infrastructure (domain at persistence step 1 when it lives in `models`) | `db`, `persistence` | arch-persistence-steps; with SQLAlchemy, sqlalchemy-repositories |
| A repository or client adapter | infrastructure | `db`, `repositories`, `adapters`, `infrastructure` | arch-repository-port, arch-ports; with SQLAlchemy, sqlalchemy-repositories |
| The engine, the session factory, one transaction | infrastructure builds them, the composition root owns their lifetime, the use case commits | `db`, `main.py`, `deps.py` | arch-unit-of-work; with SQLAlchemy, sqlalchemy-engine-and-session-scope |
| A message, email or webhook sent after a write | application, after the commit | `services`, with the sender behind a port | arch-effects-after-commit |
| A read query for a list or dashboard | application, as a query function | `services`, `queries` | arch-cqrs, arch-read-model-projections |
| An event, the event store, a projection | domain for the events, infrastructure for the store | `domain`, `events`, `projections` | arch-event-sourcing, arch-event-store |
| Wiring: build the concrete objects and connect them | composition root | `main.py`, `app.py`, `__main__.py`, `deps.py`, `container.py`, `wiring.py` | arch-composition-root |
| An entry-point handler: route, CLI command, queue consumer | interface | `api`, `routers`, `cli`, `views` | arch-use-case-functions, arch-dependency-direction |
| A helper with no home | the package of the concept it serves | never `utils`, `helpers` or `common` | arch-no-junk-drawer-packages |
| A new package or a moved module | the repo's existing layout axis | layer-first or feature-first, not both | arch-one-layout-axis, arch-predictable-project-tree |

Imports point inward: interface to application to domain, with infrastructure implementing the application's ports (arch-dependency-direction). A module that seems to need both directions usually holds two kinds of code from the table: split it. When two modules end up importing each other, follow arch-break-import-cycles.

## Symptoms of code in the wrong place

| Symptom | Where it belongs | Rule |
| --- | --- | --- |
| `select(` or `session.` in a route or CLI command | a use case or a repository | arch-use-case-functions |
| `import fastapi` or `HTTPException` in a use case | the entry point maps the domain error | arch-dependency-direction |
| `datetime.now()`, `uuid4()` or `os.environ` in a domain rule | an argument from the use case or the composition root | arch-rich-domain-model |
| A client or session built inside a use case | the composition root, passed in | arch-composition-root |
| `commit()` inside a repository method | the use case, once per unit of work | arch-repository-port, arch-unit-of-work |
| `dict[str, Any]` or an ORM row returned from a port | a typed record | arch-typed-records-across-layers |
| A message sent before the transaction commits | after the commit, or an outbox row in the same transaction | arch-effects-after-commit |
| A `utils`, `helpers` or `common` module | the package of the concept it serves | arch-no-junk-drawer-packages |
| A port with one implementation and no fake in the tests | the concrete class, imported directly | arch-ports, arch-persistence-steps |

Coupling across the whole import graph (cycles, hidden globals, god modules imported by nearly everything) is not one misplaced module: run the checklist in architecture-review.md.

## Where its test goes

| Code under test | Test it | Rule |
| --- | --- | --- |
| A domain rule or value object | directly, with plain values, no fakes | arch-tests-by-layer |
| A use case | through its ports, with typed in-memory fakes, a fixed clock and an id factory | arch-test-use-cases-with-fakes |
| A fake of a port | in one contract suite with the real implementation; applies with pytest | arch-contract-tests-for-fakes |
| An adapter or repository | through that contract suite, on the real engine in a rolled-back transaction | arch-tests-by-layer, arch-contract-tests-for-fakes |
| An entry point | only what the edge adds (parsing, status or exit codes, wiring), on the real engine | arch-tests-by-layer |
| Legacy code with no seam | characterize it first, then cut a seam | arch-make-legacy-testable |

## Placed by other skills

- Function-level idioms (names, signatures, error handling, typing): the python-coding skill. Translating domain errors at an entry point is python-coding's python-error-boundaries.
- Code shape inside one module (patterns, principles, smells): the design-patterns skill.
- HTTP routes and per-request database wiring: the web-application skill.
- Test doubles, fixtures and test structure inside a test file: the python-testing skill.
