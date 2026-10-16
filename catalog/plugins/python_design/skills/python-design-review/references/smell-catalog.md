# Smell catalog

Each entry gives a default severity, how to spot the smell, why it hurts, the usual fix, and a small before/after. Every heading is a smell id. The ids printed in the `smell` field by scripts/detect_smells.py are marked "(scanner)"; find the rest by reading.

A smell is a reason to look closer, not a verdict. Confirm it in context and skip it when the code states a reason for its shape.

## Data shapes

### dict-as-record

Severity: design. Spot: a function reads fixed string keys from a dict parameter, or returns `dict[str, Any]` across a module boundary. Why: typos become runtime `KeyError`s, the type checker sees nothing, and readers cannot learn the shape without a debugger. Fix: a dataclass, `NamedTuple` or `TypedDict` (the last only at JSON edges).

```python
def exposure_for(obs: dict[str, Any]) -> float:  # before
    return obs["exposure_s"] * obs["frames"]

@dataclass(frozen=True)
class Observation:  # after
    target: str
    exposure_s: float
    frames: int
```

### parallel-collections

Severity: design. Spot: two or more lists or dicts indexed by the same position or key and updated together, often joined with `zip`. Why: one insert or sort that forgets a sibling silently misaligns every later read. Fix: one list of records.

```python
dock_ids = ["D1", "D2"]  # before
bikes_free = [4, 0]

docks = [Dock("D1", bikes_free=4), Dock("D2", bikes_free=0)]  # after
```

### prefixed-field-group

Severity: design. Spot: several fields sharing a prefix (`sender_name`, `sender_street`, `sender_postcode`). Why: the prefix is a missing type, and every function that needs "the sender" takes three arguments. Fix: extract the group.

```python
class Parcel:  # before
    sender_name: str
    sender_street: str
    sender_postcode: str

class Parcel:  # after
    sender: Address  # Address(name, street, postcode), reused for the recipient
```

### stored-derived-value

Severity: correctness when another code path can change the inputs, otherwise design. Spot: a field that is always recomputed from other fields. Why: every writer must remember to update it, and one that forgets leaves a stale value. Fix: a `@property`, or `functools.cached_property` on an immutable object.

```python
@dataclass
class Recipe:
    prep_minutes: int
    cook_minutes: int

    @property
    def total_minutes(self) -> int:  # was a stored field updated by hand
        return self.prep_minutes + self.cook_minutes
```

### string-option-set

Severity: design. Spot: a `str` parameter compared against literals (`if mode == "drip"`). Why: typos pass silently and readers must grep for the allowed values. Fix: `Enum`, `StrEnum` or `Literal[...]`.

```python
def irrigate(zone: Zone, mode: str) -> None: ...  # before: "drip"? "Drip"?

class WateringMode(StrEnum):  # after
    DRIP = "drip"
    SPRAY = "spray"
```

### float-money

Severity: correctness. Spot: prices, balances or fares typed or computed as `float`. Why: binary floats cannot represent most decimal fractions, so sums drift by cents and equality checks fail. Fix: `decimal.Decimal` built from strings, or integer minor units.

```python
fare = 2.35 * 3  # before: 7.050000000000001
fare = Decimal("2.35") * 3  # after: Decimal('7.05')
```

### shallow-frozen-dataclass

Severity: correctness. Spot: `@dataclass(frozen=True)` with `list`, `dict` or `set` fields. Why: the instance is unhashable (it fails as a dict key or set member), and its contents can still change through `route.stops.append(...)`. Fix: `tuple` and `frozenset` fields, converted from the caller's input.

```python
@dataclass(frozen=True)
class Route:
    stops: tuple[str, ...]  # was list[str]

route = Route(stops=tuple(stop_names))
```

### leaked-mutable-internals

Severity: correctness. Spot: a method or property returns the object's own list or dict. Why: callers can mutate state the class believes it guards. Fix: return a tuple, a copy or a read-only view.

```python
def readings(self) -> tuple[float, ...]:
    return tuple(self._readings)  # was: return self._readings
```

### list-scan-lookup

Severity: design. Spot: `next(x for x in items if x.code == code)` or a loop with `break` used for keyed lookup, especially inside another loop. Why: quadratic time, and each scan site re-implements "not found". Fix: build a dict keyed by the lookup field once.

```python
bins_by_code = {b.code: b for b in bins}  # once
target = bins_by_code[code]  # instead of a scan per order line
```

## Functions and signatures

### mutable-default-argument

(scanner) Severity: correctness. Spot: a default of `[]`, `{}`, `set()` or another mutable value. Why: the default is created once when `def` runs and shared by every call. Fix: an immutable default for read-only input, or `None` plus an explicit copy.

```python
def tag(item: Item, tags: list[str] = []) -> list[str]: ...  # before

def tag(item: Item, tags: Sequence[str] = ()) -> list[str]:  # after
    return [*tags, item.kind]
```

### long-parameter-list

(scanner: more than five parameters, not counting `self` or `cls`) Severity: design. Spot: long signatures, especially where neighbors belong together. Why: call sites pass arguments in the wrong order, and every new option widens every caller. Fix: group related values into a record and make options keyword-only.

```python
def create_shipment(sender_name, sender_city, recipient_name, recipient_city, weight_kg, insured): ...

def create_shipment(sender: Contact, recipient: Contact, weight_kg: Decimal, *, insured: bool = False): ...
```

### boolean-flag-parameter

(scanner) Severity: design. Spot: a `bool` parameter whose value chooses between two blocks of the body. Why: the function does two jobs, and call sites such as `export(readings, True)` hide which one. Fix: two functions when the flag picks an algorithm. Keep a keyword-only flag that tweaks one detail (`*, include_header: bool = True`); the scanner flags those too, so confirm before reporting.

```python
def export_readings(readings: Sequence[Reading], as_csv: bool) -> str: ...  # before

def export_readings_csv(readings: Sequence[Reading]) -> str: ...  # after
def export_readings_json(readings: Sequence[Reading]) -> str: ...
```

### long-function

(scanner: more than 50 statement lines) Severity: design. Spot: a function that scrolls, usually with comments marking its phases. Why: no single read holds it, and its phases cannot be tested alone. Fix: extract each phase into a named function and keep the original as a short coordinator; split gathering inputs, computing and presenting.

```python
def nightly_report(station: Station, now: datetime) -> str:  # was 80 lines doing all three
    readings = load_readings(station, since=now - DAY)
    summary = summarize(readings)
    return render_summary(station, summary)
```

### deep-nesting

(scanner: more than three nested blocks in a function) Severity: design. Spot: the logic that matters sits four indents deep. Why: each level is a condition the reader must hold in mind. Fix: guard clauses, `continue` for skipped items, and extracting the inner body.

```python
for order in orders:  # before
    if order.paid:
        if order.lines:
            for line in order.lines:
                if line.quantity > 0:
                    reserve(line)

for order in orders:  # after
    if not order.paid:
        continue
    reserve_lines(order.lines)  # skips zero quantities itself
```

### misleading-verb

Severity: clarity, or design when callers rely on the wrong reading. Spot: `get_` that hits the network or writes a cache, `create_` that appends to a list and returns nothing, `is_` that mutates. Why: callers reason from the name and get the wrong cost or effect. Fix: rename to the behavior (`fetch_`, `load_`, `add_`, `ensure_`) or change the behavior to match.

```python
def get_forecast(city: str) -> Forecast: ...  # before: makes an HTTP call
def fetch_forecast(client: WeatherClient, city: str) -> Forecast: ...  # after
```

## Naming

### type-in-name

(scanner: identifiers ending `_str`, `_int`, `_list`, `_dict`, `_set`, `_tuple`, `_bool`, or starting `str_`, `list_`, `dict_`) Severity: clarity. Spot: parameters and assignments named for their type. Why: the annotation already states the type, and the name lies once the type changes. Fix: name the role.

```python
def notify(email_str: str, retries_int: int) -> None: ...  # before
def notify(recipient: str, max_attempts: int) -> None: ...  # after
```

### vague-name

Severity: clarity. Spot: public names such as `data`, `info`, `item`, `tmp`, `result`, `process`, `handle`; abbreviations such as `cfg`, `mgr`, `cnt`; single letters outside comprehensions, short lambdas and math. Why: the reader has to trace the value to learn what it is. Fix: name what it holds or does.

```python
def process(data: list[Reading]) -> float: ...  # before
def mean_soil_moisture(readings: list[Reading]) -> float: ...  # after
```

### shadowed-builtin

Severity: clarity, correctness when the builtin is called later in the same scope. Spot: locals or parameters named `id`, `type`, `list`, `filter`, `input`, `format`, `sum`. Why: later code in that scope calling the builtin gets the local instead. Fix: a domain name.

```python
def archive(id: str, type: str) -> None: ...  # before
def archive(episode_id: str, media_type: str) -> None: ...  # after
```

### asymmetric-names

Severity: clarity. Spot: sibling classes doing the same job under different names or signatures (`to_text()`, `render_summary()`, `describe(verbose)`). Why: callers need a branch per class, and a shared Protocol is impossible. Fix: one name and signature, or the matching dunder (`__str__`, `__len__`, `__iter__`).

```python
class TideReport:
    def __str__(self) -> str: ...  # was to_text()

class SwellReport:
    def __str__(self) -> str: ...  # was render_summary()
```

## Classes

### low-cohesion-class

(found with scripts/lcom4_clusters.py) Severity: design. Spot: methods split into groups that share no attributes and never call each other (LCOM4 above 1), or a class name joined with "and". Why: unrelated reasons to change collide in one file and one test fixture. Fix: one class per cluster; the original either disappears or composes the parts. The script skips Protocol classes and classes with fewer than two methods, leaves stub-only methods, classmethods, staticmethods and dunders such as `__init__` out of the graph, and counts a property read as an attribute access.

```python
class TelescopeController:  # before: slew()/track() use mount; notify_*() use smtp
    ...

class Mount: ...  # after: one class per cluster
class ObservationNotifier: ...
```

### namespace-class

(scanner: a class whose methods are all staticmethods) Severity: clarity. Spot: a class used only as a prefix for functions. Why: it adds a level of indirection and suggests state that does not exist. Fix: move the functions to a module; the module name becomes the namespace.

```python
class FareMath:  # before
    @staticmethod
    def peak_fare(base: Decimal) -> Decimal: ...

# after, in fares.py
def peak_fare(base: Decimal) -> Decimal: ...
```

### method-could-be-function

(scanner) Severity: clarity. Spot: an instance method that never reads `self`. The scanner skips overrides of a base-class method, `@override`, `@abstractmethod`, properties and setters, class and static methods, dunders and Protocol classes; still confirm, because a method may exist to satisfy a structural interface. Why: it implies a dependency on instance state that is not there, and it cannot be called without an instance. Fix: a module-level function.

```python
class Playlist:
    def format_duration(self, seconds: int) -> str: ...  # before: self unused

def format_duration(seconds: int) -> str: ...  # after
```

### single-method-class

Severity: restraint. Spot: a class with `__init__` and one other method, often named `run` or `execute`, or no state at all. Why: the class is ceremony around a function. Fix: a function, or a closure when configuration is fixed early. A callable dataclass holding named configuration is fine.

```python
class SlugMaker:  # before
    def make(self, title: str) -> str: ...

def make_slug(title: str) -> str: ...  # after
```

### feature-envy

Severity: design. Spot: a function or method that reads several attributes of one other object to compute something about it. Why: the logic lives away from its data, so changes to the data scatter. Fix: move the computation to the object that owns the data (tell, do not ask).

```python
volume = crate.width * crate.depth * crate.height  # before, repeated by callers
volume = crate.volume_cm3()  # after: Crate owns the formula
```

### value-only-subclass

Severity: restraint. Spot: a subclass whose only change is passing different constants to `super().__init__`. Why: a class per configuration multiplies types without new behavior. Fix: instances or a factory function with those values.

```python
class ExpressParcel(Parcel):  # before
    def __init__(self) -> None:
        super().__init__(max_days=1)

express = Parcel(max_days=1)  # after
```

### inheritance-for-reuse

Severity: design. Spot: hierarchies three or more levels deep, or mixins that read attributes the host class must provide. Why: behavior is spread over files, and a change to the base ripples to subclasses that never asked for it. Fix: compose a collaborator and delegate. Not this smell: framework base classes, framework-required mixins, exception trees, and ABCs that document an extension point.

```python
class AuditedCsvExportMixin:  # before: reads self.rows and self.user set by the host
    ...

class CsvExport:  # after: collaborators are explicit
    def __init__(self, rows: Sequence[Row], audit: AuditLog) -> None: ...
```

### isinstance-ladder

(scanner: three or more `isinstance` tests in one if/elif chain) Severity: design. Spot: dispatch on the type of an argument. Why: each added type forces another edit to the ladder, and a forgotten branch silently falls through. Fix: put the behavior on the types behind a method or Protocol; use `functools.singledispatch` for types you do not own; a `match` on classes is acceptable when it ends in `case _: raise`.

```python
def calibrate(sensor: Sensor) -> None:  # before
    if isinstance(sensor, Thermometer): ...
    elif isinstance(sensor, Hygrometer): ...
    elif isinstance(sensor, Anemometer): ...

sensor.calibrate()  # after: each sensor type implements calibrate()
```

## Coupling and construction

### hard-wired-collaborator

Severity: design. Spot: `__init__` or a business function constructs a client, session, mailer or file handle itself. Why: tests can only patch, and swapping the implementation means editing the class. Fix: take it as a parameter typed as a `Protocol` or `Callable`, and build it in the composition root.

```python
class Forecaster:
    def __init__(self, fetch: Callable[[str], Forecast]) -> None:  # was httpx.Client() inside
        self._fetch = fetch
```

### attribute-chain

Severity: design. Spot: `a.b.c.d` reaching through objects the code does not own (method chains on fluent APIs and value objects are fine). Why: the caller depends on the structure of every object along the chain. Fix: ask the nearest object for what you need, or pass that value in directly.

```python
email = parcel.route.hub.manager.email  # before
email = parcel.hub_contact_email()  # after, or pass the email in
```

### private-access

Severity: design. Spot: code reading or writing another object's `_attribute` outside its class or module. Why: the owner can no longer change its internals safely. Fix: add the method the caller needs, or move the logic into the owner.

```python
if feed._episodes: ...  # before
if feed.has_episodes(): ...  # after
```

### module-level-mutable-global-rebound

(scanner: any `global` statement) Severity: correctness when threads or async tasks touch it, otherwise design. Spot: functions that rebind module state. Why: hidden coupling between callers, order-dependent tests and races. Fix: pass the state in and return the new state, or hold it in an object created by the entry point.

```python
_last_sync = None  # before

def sync() -> None:
    global _last_sync
    _last_sync = time.time()

def sync(state: SyncState, now: float) -> SyncState:  # after
    return replace(state, last_sync=now)
```

### two-step-initialization

Severity: design. Spot: an object unusable until the caller remembers `connect()`, `load()` or `init()`. Why: forgetting the second call fails later and far away. Fix: do the work in a classmethod constructor that returns a ready instance, or require the inputs in `__init__`.

```python
feed = PodcastFeed()  # before
feed.load(path)

feed = PodcastFeed.from_file(path)  # after
```

### polymorphic-new

Severity: design. Spot: `__new__` that returns an instance of some other class depending on its arguments. Why: `Cls(...)` no longer means "a Cls", and type checkers and readers are misled. Fix: a factory function or a dict from key to constructor.

```python
def make_reader(fmt: LogFormat) -> LogReader:  # was Reader.__new__ switching on fmt
    reader_class = READER_CLASSES[fmt]
    return reader_class()
```

## Errors and idioms

### bare-except

(scanner) Severity: correctness. Spot: `except:` with no type. Why: it also catches `KeyboardInterrupt` and `SystemExit`, so Ctrl-C and shutdown are swallowed. Fix: the specific exception; at most `except Exception` when the handler cleans up and re-raises.

```python
def import_manifest(path: Path) -> Manifest:
    try:
        return parse_manifest(path)
    except ManifestError as exc:  # was: except:
        raise ImportFailed(path) from exc
```

### swallowed-exception

(scanner: `except Exception` or `except BaseException` whose body is only `pass`, `...` or `continue`) Severity: correctness. Spot: failures disappear without a trace. Why: bugs become wrong data far from their cause. Fix: catch the specific expected error and handle it; otherwise let it propagate. Logging and moving on is acceptable only at an isolation boundary such as a per-item batch loop, and only with `logger.exception`.

```python
for path in uploads:
    try:
        ingest(path)
    except CorruptUpload:  # was: except Exception: continue
        logger.exception("skipping corrupt upload", extra={"path": str(path)})
```

### missing-with

Severity: correctness. Spot: `open()`, connections, locks or temporary directories released by hand, or not at all. Why: an exception between acquire and release leaks the resource. Fix: `with`, `ExitStack` for a dynamic set, or a context manager for repeated setup and teardown.

```python
with path.open(encoding="utf-8") as fh:  # was: fh = open(path); ...; fh.close()
    header = fh.readline()
```

### missing-wraps

Severity: clarity, correctness when tools rely on metadata. Spot: a decorator's inner function lacks `functools.wraps`. Why: the wrapped function loses its name, docstring and signature, which breaks introspection, framework routing and debugging. Fix: `@functools.wraps(func)`, plus `ParamSpec` to keep the signature typed.

```python
def timed(func: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R: ...
    return wrapper
```

### match-without-fallback

Severity: correctness. Spot: a `match` over an enum, string or class set with no `case _:`. Why: an unhandled value falls through silently and the function returns `None`. Fix: end with `case _:` that raises, or `assert_never(value)` so the type checker proves exhaustiveness.

```python
match mode:
    case WateringMode.DRIP: ...
    case WateringMode.SPRAY: ...
    case _:
        assert_never(mode)
```

### method-cache

Severity: correctness. Spot: `@functools.cache` or `@lru_cache` on an instance method. Why: one cache keyed on `self` serves every instance, so it keeps instances alive long after their last use and, when bounded, evicts one instance's entries to make room for another's. Fix: `functools.cached_property` for per-instance values, or a cached module-level function keyed on plain values.

```python
@cached_property
def star_catalog(self) -> Catalog:  # was @lru_cache on a method
    return load_catalog(self._catalog_path)
```

### naive-datetime

Severity: correctness. Spot: `datetime.now()` or `datetime.utcnow()` without a timezone, or naive timestamps stored and compared with aware ones. Why: comparisons fail or shift by hours across machines and DST. Fix: `datetime.now(UTC)` (`timezone.utc` before Python 3.11), injected as a clock in domain code.

```python
def permit_expired(expires_at: datetime, now: datetime) -> bool:  # caller passes datetime.now(UTC)
    return expires_at <= now
```

### wildcard-import

Severity: clarity. Spot: `from module import *`. Why: readers and linters cannot tell where a name came from, and later imports silently shadow earlier ones. Fix: import the names you use, or the module.

```python
from tides.models import TidePrediction, TideStation  # was: from tides.models import *
```

## Restraint

### speculative-abstraction

Severity: restraint. Spot: a Protocol, ABC, factory, registry or strategy with exactly one implementation, no test double and no planned second variant; pass-through layers that only forward calls. Why: every reader pays for indirection that buys nothing yet. Fix: inline to the concrete form, and reintroduce the seam when a second implementation or a test needs it. Not this smell: a port at an I/O boundary that tests fake, and documented extension points.

```python
class GreetingStrategy(Protocol): ...  # before: one implementation, never swapped
class DefaultGreeting: ...
def build_greeting(strategy: GreetingStrategy) -> str: ...

def greeting(name: str) -> str:  # after
    return f"Welcome back, {name}"
```
