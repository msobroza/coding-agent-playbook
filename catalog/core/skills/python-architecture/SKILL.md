---
id: python-architecture
name: python-architecture
description: "Shapes how Python modules depend on each other."
playbook:
  use_when: "laying out packages, reviewing imports between modules, or adding a database"
  files: "Package layout, entry points and imports between layers"
  sections:
    - id: layers
      title: "Layers and imports"
      impact: CRITICAL
      summary: "Which layer owns what, which way imports point, where concrete objects are built, and how import cycles are broken."
      open_when: "A package starts importing another package, an entry point (main, CLI, worker) is added, or concrete objects are wired together."
    - id: boundaries
      title: "Ports and boundaries"
      impact: HIGH
      summary: "Use cases that receive their ports, typed records across every boundary, and ports added only at real seams."
      open_when: "A handler gains business logic, a use case gains a collaborator that may need a port, or rows or dicts cross a layer."
    - id: domain
      title: "Domain model"
      impact: HIGH
      summary: "Domain types that hold the rules in the business's own words, free of frameworks, I/O, clocks and randomness."
      open_when: "Code adds or changes an entity or a business rule in the domain package, or names a concept the business experts use."
    - id: persistence
      title: "Persistence"
      impact: HIGH
      summary: "How far data access goes, from an injected session to repositories and a unit of work, and where commits and outside effects happen."
      open_when: "A repository or unit of work is added, a use case writes through several repositories, a job or CLI opens a DB session, or a message follows a write."
    - id: testing
      title: "Layer tests"
      impact: HIGH
      summary: "Fakes for owned ports, contract tests that keep them honest, the right layer for each test, and seams cut into legacy code."
      open_when: "Choosing the layer a test runs at: a use case on fakes of its ports, an adapter on the real store, or legacy code with no seam."
    - id: layout
      title: "Project layout"
      impact: MEDIUM
      summary: "One layout axis that makes the architecture visible, and packages named for what they hold."
      open_when: "A change creates or renames a package, moves modules between packages, or adds a utils, helpers or common module."
    - id: read-models
      title: "CQRS and event sourcing"
      impact: LOW
      summary: "Splitting reads from writes and storing history as events, only when the signal justifies the cost."
      open_when: "A list or dashboard view computes derived fields per request, or a design proposes read models, projections or events."
  references:
    - path: references/architecture-review.md
      open_when: "Reviewing a service's whole module structure or import graph, or running layer_map.py and reading its report."
    - path: references/where-code-goes.md
      open_when: "Writing new code and unsure which package or layer it belongs in, or where its test goes."
---

# Python application architecture

Architecture guidance for Python services, APIs, workers and CLIs, for people and coding agents alike. Architecture here is one question asked many times: which modules may know about which. With the direction right, business rules run in tests without a database, swapping a vendor touches one module, and a second entry point (a CLI next to the API) reuses the same use cases. Size the structure to the code: a single-file tool or a notebook needs none of this, and a three-module service can stop at `main.py`, `domain.py` and `db.py`.

Apply it when planning the package layout of a new service or adding its first database or external integration; when reviewing an import graph (a handler that queries the ORM, business code that imports a web framework or builds its own client, an import cycle, an ORM row returned to a caller); when deciding whether a port, a repository, a unit of work, a read model or an event store is justified; and when making existing code testable through injected collaborators.

This skill covers relations between modules. Function-level idioms live in the python-coding skill, the shape of code inside one module (patterns, principles, smells) in the design-patterns skill, and HTTP and per-request database wiring in the web-application skill.

## Quick reference

### The layer model

Imports point inward: the interface calls the application, the application calls the domain, and infrastructure implements the ports the application declares. The composition root is the one place that knows every concrete class.

| Layer | Holds | May import | Package or module names |
| --- | --- | --- | --- |
| interface | HTTP routes, CLI commands, queue consumers, request and response schemas | application, domain | `api`, `routers`, `routes`, `endpoints`, `views`, `cli` |
| application | use cases: load, let the domain decide, save, commit | domain | `services`, `operations`, `use_cases`, `usecases`, `application` |
| domain | typed records, value objects, rules, domain errors | none of the other layers | `domain`, `models`, `entities` |
| infrastructure | ORM tables, repository and client implementations, file and object stores | domain, application (for the ports it implements) | `db`, `repositories`, `adapters`, `infrastructure`, `infra`, `persistence`, `storage` |
| composition root | builds the concrete objects and connects them | every layer | `main.py`, `app.py`, `__main__.py`, `deps.py`, `dependencies.py`, `container.py`, `bootstrap.py`, `wiring.py` |

What the table implies:

- An interface module parses input, calls one use case, and maps the result or the domain error to a response. It never runs a query, opens a session or decides a business rule.
- Application code never imports the web framework or the module that creates the engine. It receives data access as a parameter.
- The domain performs no I/O and reads no clock, randomness or environment variable. Those values arrive as arguments.
- Layers below the interface exchange typed records, never `dict[str, Any]`. Request and response schemas stay in the interface layer.
- Imports under `if TYPE_CHECKING:` create no runtime edge.

### When a port earns its keep

| Situation | Inject |
| --- | --- |
| CRUD over a few tables, no rules beyond validation | the ORM session, with queries in the use case |
| Business rules you want to test without a database | a narrow repository Protocol declared beside its consumer |
| A remote system: payments, mail, SMS, object storage, a vendor SDK | a Protocol or `Callable` alias, implemented by an adapter in infrastructure |
| A single behavior: send a message, read the clock, make an id | a role-named `Callable` alias such as `Clock = Callable[[], datetime]` |
| An in-process helper with no I/O | the concrete function or class, imported directly |

A port belongs to the code that consumes it: declare it where it is called, name it after the role, and list only the methods that consumer uses.

### How far to take persistence

Climb one step at a time, and only when the signal for the next step is present:

1. Injected session, queries in the use case: the default for CRUD.
2. Typed repository: rules worth testing without a database, or ORM objects leaking into domain code.
3. Unit of work: one use case writes through two or more repositories that must succeed or fail together.
4. CQRS read models: list or dashboard views compute derived fields on every request.
5. Event sourcing: history is the product, such as a mandated audit of every change.

Stepping back down is a valid finding too: a repository with one implementation and no fake, or a read model that mirrors its write table, is cost without the benefit.

### Checking the layers

The skill's layer_map.py script sorts a project's modules into these layers and reports imports that point the wrong way and import cycles. Every hit is a candidate: open the importing line and confirm it before reporting it.

## See also

python-coding, design-patterns, web-application, python-testing.
