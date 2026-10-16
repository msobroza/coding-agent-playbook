---
id: python-architecture
name: python-architecture
description: "Guides the module-level structure of a Python application: which layer each package belongs to, which way imports may point, where concrete sessions and clients are built, when a Protocol port is worth adding, and how far persistence should go (injected session, repository, unit of work, read models, event sourcing). Use when laying out or reviewing the package structure or import graph of a Python service, web API, worker or CLI, when business logic is entangled with a web framework, ORM or vendor SDK, when adding a database or an external integration, or when a repository, unit of work, CQRS or event-sourced design is proposed."
---

# Python application architecture

Architecture here is one question asked many times: which modules may know about which. With the direction right, business rules run in tests without a database, swapping a vendor touches one module, and a second entry point (a CLI next to the API) reuses the same use cases. Size the structure to the code: a single-file tool or a notebook needs none of this, and a three-module service can stop at `main.py`, `domain.py` and `db.py`.

## When to load

- Planning the package layout of a new service, API, worker or CLI, or adding its first database or external integration.
- Reviewing an import graph: a route that queries the ORM, business code that imports `fastapi` or builds its own client, an import cycle, an ORM row returned in a response.
- Deciding whether a Protocol port, a repository, a unit of work, a read model or an event store is justified.

This skill covers boundaries between modules, not function-level style such as naming or long functions.

## The layer model

| Layer | Holds | May import | Package or module names recognized by default |
|---|---|---|---|
| interface | HTTP routes, CLI commands, queue consumers, request and response schemas | application, domain | `api`, `routers`, `routes`, `endpoints`, `views`, `cli` |
| application | use cases: load, let the domain decide, save, commit | domain | `services`, `operations`, `use_cases`, `usecases`, `application` |
| domain | typed records, value objects, rules, domain errors | none of the other layers | `domain`, `models`, `entities` |
| infrastructure | ORM tables, repository and client implementations, file and object stores | domain, application | `db`, `repositories`, `adapters`, `infrastructure`, `infra`, `persistence`, `storage` |
| composition root | builds the concrete objects and connects them | every layer | files named `main.py`, `app.py`, `__main__.py`, `deps.py`, `dependencies.py`, `container.py`, `bootstrap.py`, `wiring.py` |

What the table implies:

- An interface module parses input, calls one use case, and maps the result or the domain error to a response. It never runs a query, opens a session or decides a business rule. Its collaborators come from the composition root; in FastAPI, through `Depends` providers in `deps.py`.
- Application code never imports the web framework or the module that creates the engine. It receives data access as a parameter: an ORM `Session` at step 1 of the persistence flow below, or a port it declares itself from step 2 on.
- Infrastructure may import the application layer only for the ports it implements. It never calls a use case.
- The domain performs no I/O and reads no clock, randomness or environment variable. Those values arrive as arguments.
- Layers below the interface exchange typed records (dataclasses or value objects), never `dict[str, Any]`. Request and response schemas stay in the interface layer.
- Domain errors are raised in domain or application code and translated once per entry point. A domain error with no HTTP mapping is a 500, never a guessed 400.
- Imports under `if TYPE_CHECKING:` create no runtime edge and are never violations.

## When a port earns its keep

| Situation | Inject | Why |
|---|---|---|
| CRUD over a few tables, no rules beyond validation | the ORM `Session`, with queries in the use case | the session already tracks changes and commits; a port would restate it |
| Business rules you want to test without a database | a narrow repository Protocol declared beside its consumer | an in-memory fake makes rule tests fast and literal |
| A remote system: payments, mail, SMS, object storage, a vendor SDK | a Protocol or `Callable` alias, implemented by an adapter in infrastructure | vendor types, credentials, timeouts and retries stay out of business code; a fake replaces the network |
| A single behavior: send a message, read the clock, make an id | a role-named `Callable` alias such as `Clock = Callable[[], datetime]` | a one-method Protocol is ceremony |
| Two or more real implementations chosen by configuration | a Protocol | the variation already exists |
| An in-process helper with no I/O | the concrete function or class, imported directly | there is nothing to fake or swap |
| A working ABC that shares implementation or is a documented extension point | keep the ABC | replacing it buys nothing |
| A reporting or analytics query | a dedicated query function that takes the session | CRUD-shaped repository methods fit aggregates badly |

A port belongs to the code that consumes it. Declare it in the application or domain package that calls it, name it after the role (`LoanRepository`, `SendReceipt`), and list only the methods that consumer uses. Implementations satisfy it structurally and do not need to import it.

## How far to take persistence

Climb one step at a time, and only when the signal for the next step is present in the code or in a stated requirement, never in anticipation.

1. **Injected session, queries in the use case.** The default for CRUD. The use case takes a `Session`, runs `select(...)`, converts rows to records before returning, and commits once. Cost: rule tests need a database, though an in-memory SQLite engine is often enough.
2. **Typed repository.** Signal: rules worth testing without a database, the same query repeated across use cases, or ORM objects leaking into domain code. Write one Protocol per aggregate that returns typed records, raises a domain not-found error, and adds and flushes but never commits. Pair it with an in-memory fake kept honest by one shared contract test. Cost: a module per aggregate, and query methods that multiply.
3. **Unit of work.** Signal: one use case writes through two or more repositories that must succeed or fail together, or checks one repository and then writes another. Repositories share one session and the use case calls a single `commit()`. Cost: another seam to fake, and every write must go through it. A SQLAlchemy session already is a unit of work, so this step is a thin wrapper.
4. **CQRS read models.** Signal: list or dashboard views compute derived fields on every request, need to filter or sort by them, or read shapes keep drifting from write shapes. First split command functions from query functions that select only the columns a view needs. Add a projection table, updated in the same transaction as the write, only if that is still too slow. Cost: duplicated data, a projector to keep correct, and a rebuild path whenever the view changes.
5. **Event sourcing.** Signal: history is the product, for example a mandated audit of every change, questions such as "what was true on date X", or new views that must be rebuilt from the past. Cost: events are a schema you can never drop, long streams need snapshots, erasing personal data gets hard, and most developers find the model unfamiliar. An audit table written beside ordinary rows answers "who changed what" far more cheaply.

Stepping back down is a valid finding too: a repository with one implementation and no fake in the tests, or a read model that mirrors its write table column for column, is cost without the benefit.

## Checking layers with scripts/layer_map.py

If scripts/layer_map.py exists next to this file, run it before reading the code in detail, calling it by its path inside this skill's directory and passing the project directory as ROOT. Otherwise trace imports by hand: search for lines that start with `import` or `from`, including inside functions. The script needs only Python 3.10 or later and the standard library.

```text
python3 scripts/layer_map.py [ROOT] [--layer NAME=dir1,dir2 ...] [--allow NAME=DEP1,DEP2 ...] [--root-module NAME ...] [--json]
```

- ROOT is the project directory, the current directory when omitted; when ROOT/src holds Python files, that is what gets scanned, and otherwise ROOT itself is (so a Rust or JavaScript `src/` is passed over). Nothing is imported or executed. Test code (`tests/`, `test_*.py`, `conftest.py`) is skipped, because tests wire their own fakes the way a composition root does. Files that cannot be parsed are reported on stderr and skipped. Finding no module to scan is a usage error.
- A module's layer is the outermost part of its dotted name, a directory or the file name itself, that matches a name from the layer table, so `routes/loans.py` and `loans/routes.py` are both interface code. A module that matches nothing is unlayered and never checked. Absolute and relative imports are resolved to scanned modules; every other import is ignored.
- One exception keeps a project's own package name from swallowing its layers. A package named like a layer is a container, not a layer, when the names below it cover at least two other layers and no package beside it names another layer: a service packaged as `api/` with `api/services/` and `api/db/` inside, or the `services/` package that encloses ROOT `services/billing` when that holds `domain/` and `db/`. Its own name is skipped, so `api/db/session.py` is infrastructure and `api/config.py` is unlayered. Layer-first packages side by side (`api/`, `services/`, `db/`) stay layers, and so does a `db/` holding only `db/models.py` and `db/repositories.py`, so ORM tables there are still infrastructure. Containers are listed in the report. To overrule one for part of its tree, add a name with `/` to a layer, such as `api/models` to the interface names when `api/models/` holds request schemas; a name with `/` is never treated as a container.
- `--layer NAME=dir1,dir2` replaces that layer's whole list of names, or adds a new layer. `--allow NAME=DEP1,DEP2` replaces the list of layers NAME may import. `--root-module NAME` marks one more composition root, given as a dotted module, its trailing part, or the path of a scanned file, absolute or relative to the current directory, ROOT or the scanned directory, so the `file` the report prints works. A value that matches no scanned module is a usage error. Repeat each flag once per value.
- Only interface modules may import a composition root, for the provider module's `Annotated` aliases. Any other layered module that imports one, at module level or inside a function, is a violation: a service locator. A root inside a layered directory also keeps that layer for the layer rules.
- The default is a text report. `--json` prints one object with `layers` (module to layer), `flows` (`[from_layer, to_layer, count]`, counting distinct module pairs and leaving composition roots out), `violations` (each with `importer`, `imported`, `from_layer`, `to_layer`, `file`, `line`; `to_layer` is null when the imported module is a composition root with no layer), `cycles` (lists of modules), `type_only` (rule-breaking edges under `if TYPE_CHECKING:`, which never fail the run), plus `unlayered`, `composition_roots` and `container_packages`.
- Imports inside a function body count against the layer rules but not toward cycles, which include only imports that run at import time. A cycle hidden by a function-local import therefore has to be found by reading the code.
- Exit code 0 means no violation and no import cycle, 1 means at least one of either, and 2 means a usage error, including a `--root-module` that matches nothing and a ROOT with no module to scan.

Configure the run to match the project rather than arguing with its output:

- The default directions describe step 2 and up. At step 1, use cases legitimately import the mapped classes. If those live in `db/`, run with `--allow application=domain,infrastructure` instead of reporting every query as a violation. If they live in `models/`, the defaults already treat them as domain.
- From step 2 on, a `models/` package that holds ORM tables is infrastructure, and a use case importing it is a leak. Pass `--layer domain=domain,entities --layer infrastructure=db,models,repositories,adapters,infrastructure,infra,persistence,storage` so those imports show up.
- Singular module names (`service.py`, `repository.py`) match nothing by default. Add them with `--layer`, repeating the default names you keep.
- A worker entry point under another file name needs `--root-module worker`, or its wiring imports will show up as violations.

Every hit is a candidate, not a verdict. Open the importing line and decide whether the module is an unrecognized composition root, a misclassified directory, or a real leak. For each cycle, check whether it crosses layers, which is critical, or stays inside one package, where it usually means a module should be split or merged.

## Review output

1. **Layer map**: one line per layer listing its modules, then one line each for composition roots, container packages (when there are any) and unlayered modules.
2. **Flows**: layer-to-layer edges with counts, each marked ok or violation.
3. **Violations and cycles**: `path:line`, importer and imported module, and the rule broken, each confirmed by reading the code. Cycles are written as full paths, such as `a.py -> b.py -> a.py`.
4. **Persistence step**: the step the code is at, and whether the signal for the next step, or for stepping back, is present.
5. **Findings by severity.** Critical: wrong-direction imports, business code that cannot run without real infrastructure, cycles that cross layers. Important: hidden globals and service locators, ORM rows or driver errors crossing a boundary, commits inside data-access code. Suggestion: speculative ports, a handler doing light domain work, a module whose layer is unclear. Each finding gives `path:line`, its concrete cost (what it makes hard to test, swap or change), and a minimal before and after.
6. **Fix plan**: small, safe steps ordered by blast radius, each naming the files it touches.

## Optional depth

These notes ship beside this file when the skill is installed with its supporting files. Everything above stands on its own without them.

- references/layers-and-composition-root.md: what each layer owns, composition roots for FastAPI, Click and workers, layer-first versus feature-first layouts, and breaking import cycles.
- references/dependency-injection.md: injection versus inversion, injection forms from lightest to heaviest, two independent axes of variation, and anti-patterns.
- references/testability.md: fakes and failure fakes, clock and id injection, a recipe for making existing code testable, and an edge-case checklist.
- references/persistence.md: session lifetime, typed repositories, the unit of work, contract tests and query shape.
- references/cqrs-and-event-sourcing.md: splitting commands from queries, projections, events, event stores and snapshots.
- references/worked-example.md: a small FastAPI tool-lending service written out module by module, with its tests.
