# Patterns, lightest form first

Recommend a pattern only for a problem visible in the code today. Start from the smell, not the catalog, and stop at the first form that removes it. Each entry lists the signals that call for the pattern, the progression from lightest to heaviest form, when not to use it, the built-in that often replaces it, and pitfalls to check in existing implementations. Removing a pattern that no longer earns its keep is as valid a recommendation as adding one.

## Strategy

- **Signals:** an if/elif chain where each branch is a variant of one computation; a `mode` or `kind` parameter; options that only one variant uses.
- **Progression:** pass a function typed with a role-named `Callable` alias; then a callable dataclass when the variant needs named configuration; then a Protocol with several methods; then an ABC when implementations share code.
- **Not when:** two branches that will not grow. Keep the `if`.
- **Built-in:** first-class functions and `key=` parameters (`sorted`, `max`, `min`), `re.sub` with a function replacement.
- **Pitfalls:** `functools.partial` blurs the signature: some type checkers see only `partial[R]`, so a mismatch with your alias can slip through, and reprs and tracebacks hide what was bound. Prefer a closure or a callable dataclass where typing matters. Do not widen the shared signature with parameters only one variant needs; configure that variant at construction.

```python
PriceRule = Callable[[Decimal], Decimal]

@dataclass(frozen=True)
class OffPeakDiscount:
    percent: Decimal

    def __call__(self, fare: Decimal) -> Decimal:
        return fare * (1 - self.percent / 100)
```

## Dispatch table and registry

- **Signals:** an if/elif mapping a string or enum to a constructor or handler; objects built from config or JSON by a type field.
- **Progression:** a module-level dict from key to callable; then a `Registry` object filled by `register` calls from the composition root; then entry-point discovery (see Plugin loading).
- **Not when:** the keys are a closed enum used in one place, where an exhaustive `match` reads better.
- **Built-in:** `dict`; `functools.singledispatch` when the key is the argument's type.
- **Pitfalls:** a raw lookup raises a bare `KeyError` that reads like a bug. Raise a domain error that names the unknown key and lists the known ones. Unpacking config with `**options` ties JSON keys to parameter names, so a renamed parameter becomes a runtime `TypeError`. Validate config into a typed record first, then call the handler with explicit arguments.

```python
def parser_for(fmt: str) -> Parser:
    try:
        return PARSERS[fmt]
    except KeyError:
        raise UnknownFormatError(f"unknown format {fmt!r}; known: {sorted(PARSERS)}") from None
```

## Command (undo, queue, replay)

- **Signals:** undo or redo, queued or scheduled actions, an audit trail, all-or-nothing batches, macros.
- **Progression:** a function that performs the action and returns an undo closure; then command dataclasses with `execute` and `undo` when commands must be inspected, serialized or stored.
- **Not when:** nothing is ever reversed, deferred or replayed.
- **Built-in:** closures; `contextlib.ExitStack.callback`, whose callbacks run in reverse registration order.
- **Pitfalls:** capture the state to restore (a snapshot) before executing, rather than recomputing an inverse that may not exist. Undo a batch in reverse order, and when step N fails, undo steps N-1 down to 1 before re-raising.

```python
Undo = Callable[[], None]

def apply_batch(actions: Sequence[Callable[[], Undo]]) -> list[Undo]:
    undos: list[Undo] = []
    try:
        for action in actions:
            undos.append(action())
    except Exception:
        for undo in reversed(undos):
            undo()
        raise
    return undos
```

## Template method

- **Signals:** two or more classes or functions run the same sequence of steps and differ in one or two of them.
- **Progression:** one function that takes the varying steps as parameters (callables or a small Protocol); then an ABC whose template method calls abstract hooks, when the base holds shared state or overrides must be enforced.
- **Not when:** only one variant exists.
- **Built-in:** higher-order functions; `contextlib.contextmanager` for setup and teardown around a varying body.
- **Pitfalls:** mark the template method `typing.final` so type checkers stop subclasses from overriding the sequence instead of the hooks. Avoid hooks that only work if the subclass remembers to call `super()`.

## Pipeline

- **Signals:** a value passed through a series of transformations; the same variable reassigned step after step; a configurable sequence of processing stages.
- **Progression:** a plain sequence of calls; then a list of step functions applied in a loop or with `functools.reduce`; then a handler chain when steps may stop the flow.
- **Not when:** three fixed steps read clearly inline.
- **Built-in:** generator expressions and `itertools` for streaming; `functools.reduce`.
- **Pitfalls:** steps must return new values, not mutate their input. Wrap a failure with the name of the failing step (`raise StepFailed(step.__name__) from exc`), or the traceback will not say which stage broke.

## Callbacks, wrappers and function builders

- **Signals:** a caller needs to be told when something happens; an existing function's parameters do not fit a seam; a function is configured once and then called many times.
- **Progression:** pass a callback; write a small wrapper function that translates arguments; write a builder that returns a configured closure; move to a callable dataclass when the configuration should be inspectable.
- **Built-in:** closures, `functools.partial`, `functools.wraps` for wrappers.
- **Pitfalls:** closures created in a loop capture the variable, not its value: every `lambda: notify(zone)` sees the last `zone`. Bind it with a default argument or a builder function.

## Notification and domain events

- **Signals:** core logic ends by calling several unrelated side-effect systems (mail, metrics, cache invalidation); adding a channel means editing every caller.
- **Progression:** return event objects from the core and let the caller act on them; then a small dispatcher object, built in the composition root, that maps event classes to handler lists; then an external queue when handlers must outlive the process.
- **Not when:** there is one side effect with one caller. Call it directly.
- **Built-in:** none in the standard library; a dict of lists is enough. A framework's own signal mechanism may already exist.
- **Pitfalls:** key subscriptions by event class, never by string, so a typo fails at import rather than silently notifying nobody. Running setup a second time subscribes each handler again and every event is handled twice, so register once in the composition root or make `subscribe` ignore a handler it already has. Events are frozen dataclasses named in the past tense with an aware UTC `occurred_at` taken from an injected clock. Decide the failure policy explicitly: let handler errors propagate, or isolate each handler and log with `logger.exception`, never silently.

```python
@dataclass(frozen=True)
class IrrigationSkipped:
    zone_id: str
    reason: str
    occurred_at: datetime  # aware UTC, from the injected clock

E = TypeVar("E")

class EventDispatcher:  # built once in the composition root, passed to publishers
    def __init__(self) -> None:
        self._handlers: defaultdict[type, list[Callable[[Any], None]]] = defaultdict(list)

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        if handler not in self._handlers[event_type]:  # a second setup run must not double-notify
            self._handlers[event_type].append(handler)

    def publish(self, event: object) -> None:
        for handler in self._handlers.get(type(event), ()):
            handler(event)
```

## State

- **Signals:** behavior depends on a mode that changes over the object's life; the same `if self.status == ...` guard repeats in many methods; some transitions are illegal.
- **Progression:** an enum plus a transition table `dict[tuple[Status, Action], Status]` that raises on missing pairs; then state objects behind a Protocol when each state carries substantial behavior.
- **Not when:** two states that barely differ in behavior. A boolean or a two-member enum is enough.
- **Built-in:** `enum.Enum`, `dict`, `match`.
- **Pitfalls:** transitions scattered across methods drift apart. Keep them in one table or one place, and make an illegal transition raise a domain error that names both states.

## Builder and fluent interface

- **Signals:** many optional parts that must be validated together; construction in stages where later parts depend on earlier ones; tests building large fixtures.
- **Progression:** a dataclass with defaults and keyword-only fields; a classmethod constructor per common shape; `dataclasses.replace` for variations; then a builder whose `build()` validates and returns a frozen product.
- **Not when:** every field is known at once. Keyword arguments already are a builder.
- **Built-in:** keyword arguments with defaults, `dataclasses.replace`.
- **Pitfalls:** `build()` must copy collections into the product (`tuple(self._stops)`), or later builder calls mutate a product that claims to be frozen. A fluent API whose methods mutate and return `self` lets two chains from a shared base interfere; return new instances when callers branch. Annotate chaining methods with `Self` (3.11+, or a bound `TypeVar` on older versions).

```python
def build(self) -> Route:
    if len(self._stops) < 2:
        raise ValueError(f"a route needs at least two stops, got {self._stops!r}")
    return Route(name=self._name, stops=tuple(self._stops))
```

## Adapter

- **Signals:** a third-party API whose shape differs from what your code wants; vendor types and exceptions leaking into business code.
- **Progression:** a wrapper function for one call; then an adapter class that implements your Protocol by delegating to the vendor client.
- **Not when:** both sides are your own code; change one of them instead.
- **Built-in:** plain functions, `functools.partial` for fixed arguments.
- **Pitfalls:** wrap, do not subclass the vendor class. Translate vendor exceptions into your own at the adapter. Outbound calls there get explicit timeouts, and only idempotent calls get a small, bounded retry on transient errors. Add backoff or circuit breakers only when the project asks for them.

## Facade

- **Signals:** callers repeat the same sequence of calls into a subsystem; many modules import the subsystem's internals.
- **Progression:** one function that runs the sequence; then a facade class holding the subsystem collaborators it was given.
- **Not when:** the subsystem is already simple, or callers genuinely need fine control.
- **Built-in:** a module exposing a few functions is a facade.
- **Pitfalls:** a facade that grows a method for every subsystem feature becomes a god class. Keep it to the operations callers actually use, and do not return subsystem types through it.

## Matching object families (abstract factory) and bridge

- **Signals:** several objects must be swapped together (a regional formatter, validator and tax rule); or two independent axes of variation produce a subclass for every combination.
- **Progression:** a frozen dataclass bundling the matching callables per family; then one factory class per family when the products have several methods or state. For two axes, inject one axis into the other as a `Callable` or Protocol instead of subclassing the matrix.
- **Not when:** only one family exists, or the objects vary independently (use separate strategies).
- **Built-in:** classes are callables, so a class object can stand in as a factory.
- **Pitfalls:** a bare tuple of callables is positional, so swapping two members type-checks. Use named, typed fields. `partial` chains wired at startup become unreadable; once the wiring needs more than a few, use objects.

## Plugin loading

- **Signals:** other packages or deployments add variants without editing this code.
- **Progression:** each plugin module exposes `register(registry)` and the composition root calls it explicitly; then discovery through `importlib.metadata.entry_points(group=...)` for installed distributions.
- **Not when:** every variant lives in this repository. A dispatch table is enough.
- **Built-in:** `importlib.metadata.entry_points`.
- **Pitfalls:** never pass a module name taken from config or user input to `importlib.import_module` unless it is on an allowlist, because importing runs arbitrary code. Prefer explicit `register(registry)` calls over registration as an import side effect into a global. `@runtime_checkable` Protocol checks confirm only that the method names exist, so a plugin with the wrong signatures passes. A plugin that fails to load should produce an error naming it, not vanish silently.

```python
ALLOWED_EXPORTERS = {"csv": "exporters.csv_exporter", "parquet": "exporters.parquet_exporter"}

def load_exporter(name: str, registry: ExporterRegistry) -> None:
    module_name = ALLOWED_EXPORTERS.get(name)
    if module_name is None:
        raise UnknownExporterError(f"exporter {name!r} not allowed; known: {sorted(ALLOWED_EXPORTERS)}")
    importlib.import_module(module_name).register(registry)
```

## Single shared instance

- **Signals:** one connection pool, client or cache is needed for the whole process.
- **Progression:** build it in the entry point and pass it down; a module-level instance for process-wide services such as loggers.
- **Not when:** the object is cheap and holds no shared resource; create it where it is used.
- **Built-in:** modules are imported once, so a module attribute is already single.
- **Pitfalls:** class-level machinery (a metaclass instance cache, a caching `__new__`) hides the dependency and makes tests share state. Skip it; one instance in the composition root achieves the same. A module-level instance that holds state must be reset between tests, so keep that form for stateless services.

## Value objects

- **Signals:** bare `str`, `int` or `float` for quantities with units, identifiers that get mixed up, validated codes; the same validation repeated at call sites.
- **Progression:** `typing.NewType` to separate identifiers statically; a frozen dataclass that validates in `__post_init__`; operators and methods on it as rules accumulate.
- **Not when:** the value has no rules and no risk of confusion.
- **Built-in:** `Decimal`, `datetime`, `enum`, `NewType`, frozen dataclasses.
- **Pitfalls:** `NewType` performs no runtime check. Subclassing `int` or `str` for a value type loses the type on arithmetic and string methods (`Meters(3) + 1` is a plain `int`), so prefer a dataclass once operations matter.

## Lazy loading and caching

- **Signals:** an expensive value (a model, a large file, a remote catalog) that only some paths need; slow startup.
- **Progression:** `functools.cached_property` for per-instance values; a cached module-level function for process-wide values; a generator to load data incrementally.
- **Not when:** the value is always needed, or failing at startup is preferable to failing on first use.
- **Built-in:** `functools.cached_property`, `functools.cache`, generators, module-level `__getattr__`.
- **Pitfalls:** `@cache` or `@lru_cache` on a method keeps every instance alive and shares one cache across instances. Cached mutable values are shared by every caller, so return tuples, frozensets or frozen dataclasses. `functools.cache` is unbounded; prefer `lru_cache(maxsize=...)` for inputs with many distinct values. Lazy initialization reached from several threads needs a lock.
