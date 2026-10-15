# Layers and the composition root

Long-form notes on the layer model in SKILL.md: what belongs in each layer, where concrete objects get built for each kind of entry point, how to lay out packages, and how to break import cycles.

## What each layer owns

**Interface.** Translates between a delivery mechanism and the use cases. A handler parses and validates input, calls exactly one use case, and maps the outcome to a response or an exit code. When a screen needs the results of two use cases, add a use case that orchestrates them instead of orchestrating in the handler. Warning signs: `select(` or `session.` in a route, branching on business values, a status code chosen in service code.

**Application.** One function per use case, or a small class when several use cases share collaborators. A use case loads what it needs, lets the domain decide, persists the outcome and commits, so it owns the transaction boundary. It takes collaborators as parameters and returns typed records. Warning signs: `import fastapi`, `import click`, `HTTPException`, a call to a session factory, reading `os.environ`.

**Domain.** Frozen dataclasses, value objects, enums, rules written as pure functions or methods, and the project's error hierarchy. Warning signs: a session attribute on an entity, `datetime.now()` inside a rule, an entity method that saves itself, logging configuration.

**Infrastructure.** Everything that touches the outside world: ORM mapped classes, repository implementations, clients for other services, file and object stores. It converts between external shapes and domain records, translates driver errors into domain errors (a unique-constraint failure on a barcode becomes `DuplicateBarcodeError`, raised `from` the original), and gives every remote call a timeout and, for idempotent calls, a small retry on transient failures only. Warning signs: ORM rows returned to callers, `KeyError` escaping as "not found", importing a use case.

## One composition root per entry point

The composition root is the single place per entry point that picks the concrete classes and connects them. Everything else receives what it needs.

| Entry point | Its composition root |
|---|---|
| FastAPI app | the app factory and its lifespan for long-lived resources, plus the provider module (`deps.py`) for per-request sessions, repositories, clocks and id factories |
| Click or Typer CLI | the root group callback, which builds services once and stores them on the context object for subcommands |
| Worker or scheduled job | `main()`, which builds everything and then starts the loop |
| Library | none of its own: the caller is the root, so the library takes collaborators as parameters and never reads configuration |

Rules for the root:

- Load settings once here, and fail at startup when a required value is missing. Hand callees the few values they use (a base URL, a timeout), not the settings object.
- Creating an engine, a session factory or the app object at import time is fine, because none of them connects. Opening a connection or calling the network at import time is not.
- Interface modules may import the provider module, but only for its `Annotated` aliases. Application, domain and infrastructure code never imports the root; reaching into it for a session turns it into a service locator. The layer checker reports such an import as a violation, including one made inside a function body.

A Click root that builds everything once and hands subcommands ready-to-call use cases through the context object:

```python
@dataclass(frozen=True)
class Services:
    remind_overdue: Callable[[], int]


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    settings = Settings()  # read once; a missing value stops the CLI here
    sessions = sessionmaker(create_engine(settings.database_url))
    gateway = HttpSmsGateway(settings.sms_api_base, timeout=settings.sms_timeout_seconds)

    def remind_overdue() -> int:
        with sessions() as session:  # one session per run, closed on every path
            return send_overdue_reminders(SqlOverdueLoans(session), gateway.send, utc_now)

    ctx.obj = Services(remind_overdue=remind_overdue)


@cli.command()
@click.pass_obj
def remind(services: Services) -> None:
    click.echo(f"{services.remind_overdue()} reminders sent")
```

The subcommand constructs nothing. Its test calls `CliRunner().invoke(remind, obj=Services(remind_overdue=lambda: 3))` and checks the output; the use case itself is tested separately with fakes.

## Layer-first or feature-first

```text
layer-first                          feature-first
  api/loans.py                         loans/api/routes.py
  api/members.py                       loans/services/lending.py
  services/lending.py                  loans/domain/records.py
  services/membership.py               loans/db/repositories.py
  domain/loans.py                      members/api/routes.py
  db/repositories.py                   members/services/membership.py
  main.py, deps.py                     main.py, deps.py
```

| | Layer-first | Feature-first |
|---|---|---|
| Strength | the architecture is visible from the top level | a feature reads, and can be deleted, as one folder |
| Cost | one feature change touches four directories | each feature repeats the same inner structure |
| Extra rule | none | features talk through each other's application layer, never through each other's `db` |

Pick one axis per repository and keep it. Both layouts work with the layer checker's defaults, because a layer name is matched anywhere in a module's dotted path, including the file name itself: `loans/api/routes.py`, `loans/routes.py` and `routes/loans.py` are all interface code. Singular names such as `loans/service.py` match nothing until they are added with `--layer`.

A project packaged under one package that happens to carry a layer name, such as `api/` holding `api/routers/`, `api/services/` and `api/db/`, works too. The checker reads such a container package as the project's name, not as the interface layer, when the names inside it cover at least two other layers and no package beside it names another layer, and it lists every container in its report. A `db/` holding only `db/models.py` and `db/repositories.py` stays infrastructure.

## Breaking import cycles

A cycle means neither module can be understood, tested or loaded without the other. Fix the dependency instead of hiding it.

1. Find the edge that points the wrong way (a lower layer importing a higher one) and invert it. The lower module declares a Protocol or takes a `Callable`, and the composition root passes the higher-level implementation in.
2. When both modules need the same type, move that type down into the domain.
3. Two modules that always change together and import each other are one module in two files. Merge them.
4. Moving an import into a function body to dodge the cycle only hides it. Function-local imports are fine when they keep an optional or heavy dependency lazy.
5. A cycle that exists only for annotations is legitimately broken with an import under `if TYPE_CHECKING:`, together with `from __future__ import annotations` or quoted annotations.

A cycle inside one package is usually a module that wants splitting or merging. A cycle across layers is always a wrong-direction edge and the first thing to fix.
