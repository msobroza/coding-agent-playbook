# Smell catalog

A code smell is a surface sign of a deeper design problem. The code may work perfectly; the smell says the next change will cost more than it should. Each entry below gives a default severity, how to spot the smell, why it hurts, the usual fix, the rule that owns the fix, and a small before/after. Every heading is a smell id. The ids that detect_smells.py prints in its `smell` field are marked "(scanner)"; find the rest by reading, in the order quality-checklist.md gives.

A smell is a reason to look closer, not a verdict. Confirm it in context, skip it when the code states a reason for its shape, and rank what remains with `design-review-by-severity`.

## Contents

- Smell to first fix
- Data shapes: dict-as-record, parallel-collections, prefixed-field-group, stored-derived-value, string-option-set, bare-primitive, float-money, shallow-frozen-dataclass, leaked-mutable-internals, list-scan-lookup
- Functions and signatures: mutable-default-argument, long-parameter-list, boolean-flag-parameter, long-function, deep-nesting, magic-number, misleading-verb
- Naming: type-in-name, vague-name, shadowed-builtin, asymmetric-names, junk-drawer-package
- Classes: low-cohesion-class, namespace-class, method-could-be-function, single-method-class, feature-envy, value-only-subclass, inheritance-for-reuse, isinstance-ladder
- Coupling and construction: hard-wired-collaborator, attribute-chain, private-access, module-level-mutable-global-rebound, two-step-initialization, polymorphic-new
- Errors and idioms: bare-except, swallowed-exception, missing-with, missing-wraps, match-without-fallback, method-cache, naive-datetime, wildcard-import
- Restraint: speculative-abstraction

## Smell to first fix

| Smell id | Severity | First fix to try | Owning rule |
| --- | --- | --- | --- |
| dict-as-record, parallel-collections, prefixed-field-group | design | one record type | `design-start-with-the-data` |
| stored-derived-value | design | `@property`, or compute on demand | python-coding's python-data-shapes |
| string-option-set | design | `Enum`, `StrEnum` or `Literal[...]` | python-coding's python-enums |
| bare-primitive, float-money | design, correctness | a frozen value type; money in `Decimal` or integer minor units | `design-value-objects` |
| mutable-default-argument | correctness | default to `None` and copy, or to an immutable `()`; `field(default_factory=list)` in a dataclass | python-coding's python-typing |
| long-parameter-list | design | group values that travel together into a record; make options keyword-only | `design-start-with-the-data` |
| boolean-flag-parameter | design | two named functions when the flag picks an algorithm; keyword-only when it tweaks one detail | python-coding's python-function-signatures |
| long-function, deep-nesting | design | extract named steps; guard clauses and early returns | python-coding's python-small-units and python-early-return |
| type-in-name, vague-name, misleading-verb, asymmetric-names | clarity | name the role and match the verb to the behavior | `design-name-for-intent` |
| low-cohesion-class | design | split along the attribute clusters, then compose the parts | `design-split-god-class` |
| namespace-class, method-could-be-function, single-method-class | clarity, restraint | a module of plain functions | `design-lightest-construct` |
| feature-envy, attribute-chain, private-access | design | move the computation to the object that owns the data | `design-tell-dont-ask` |
| value-only-subclass, inheritance-for-reuse | restraint, design | configured instances; a composed collaborator | `design-composition-over-inheritance` |
| isinstance-ladder | design | behavior on the types, or a mapping from type or enum to handler | `design-open-closed` |
| hard-wired-collaborator | design | a constructor parameter typed as a `Protocol` or `Callable`, wired in the composition root | python-coding's python-dependency-injection |
| module-level-mutable-global-rebound | design | pass the state in and return the new state | `design-low-coupling` |
| two-step-initialization, polymorphic-new | design | a classmethod constructor; a factory function | `design-complete-construction` |
| bare-except, swallowed-exception | correctness | catch the specific error you can handle; otherwise let it propagate | python-coding's python-error-handling |
| speculative-abstraction | restraint | inline to the concrete form | `design-pattern-from-smell` |

## Data shapes

### dict-as-record

Severity: design. Spot: a function reads fixed string keys from a dict parameter, or returns `dict[str, Any]` across a module boundary. Why: typos become runtime `KeyError`s, the type checker sees nothing, and readers cannot learn the shape without a debugger. Fix: a dataclass, `NamedTuple` or `TypedDict` (the last only at JSON edges). Rule: `design-start-with-the-data`; the record's own shape is python-coding's python-data-shapes.

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

Severity: design. Spot: two or more lists or dicts indexed by the same position or key and updated together, often joined with `zip`. Why: one insert or sort that forgets a sibling silently misaligns every later read. Fix: one list of records. Rule: `design-start-with-the-data`.

```python
names = ["Widget", "Gadget"]  # before
quantities = [3, 5]
prices_cents = [100, 200]


@dataclass(frozen=True)
class LineItem:  # after
    name: str
    quantity: int
    price_cents: int


items = [LineItem("Widget", 3, 100), LineItem("Gadget", 5, 200)]
```

### prefixed-field-group

Severity: design. Spot: several fields sharing a prefix (`customer_name`, `customer_address`, `customer_email`), or a class with so many fields that they fall into groups. Why: the prefix is a missing type, and every function that needs "the customer" takes three arguments. Fix: extract the group into its own record. Rule: `design-start-with-the-data`.

```python
@dataclass
class Order:  # before
    customer_name: str
    customer_address: str
    customer_email: str
    items: list[LineItem]


@dataclass
class Order:  # after: Customer(name, address, email) is reused wherever a customer travels
    customer: Customer
    items: list[LineItem]
```

### stored-derived-value

Severity: correctness when another code path can change the inputs, otherwise design. Spot: a field that is always recomputed from other fields and updated everywhere they change. Why: every writer must remember to update it, and one that forgets leaves a stale value. Fix: a `@property`, or `functools.cached_property` on an immutable object. Rule: python-coding's python-data-shapes.

```python
class BankAccount:
    def __init__(self, checking_cents: int, savings_cents: int) -> None:
        self.checking_cents = checking_cents
        self.savings_cents = savings_cents

    @property
    def total_cents(self) -> int:  # was a third field updated by hand
        return self.checking_cents + self.savings_cents
```

### string-option-set

Severity: design. Spot: a `str` parameter compared against literals (`if role == "manager"`), or an if/elif chain over string constants. Why: typos pass silently and readers must search for the allowed values. Fix: `Enum`, `StrEnum` or `Literal[...]`. Rule: python-coding's python-enums.

```python
user = User("Ada", role="slacker")  # before: any string is accepted


class Role(Enum):  # after
    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"


user = User("Ada", role=Role.MEMBER)  # a wrong value fails the type check
```

### bare-primitive

Severity: design. Spot: a domain value with rules (an email address, a rate, a quantity with a unit, a code) passed around as a bare `str`, `int` or `float`. Why: every function re-validates it or trusts it blindly, and two values of the same primitive type are easy to swap. Fix: a small frozen value type that validates on construction. Rule: `design-value-objects`.

```python
def send_receipt(to: str) -> None: ...  # before: an address, a path or a name?


@dataclass(frozen=True)
class EmailAddress:  # after
    value: str

    def __post_init__(self) -> None:
        if "@" not in self.value:
            raise ValueError(f"not an email address: {self.value!r}")
```

### float-money

Severity: correctness. Spot: prices, balances or fares typed or computed as `float`. Why: binary floats cannot represent most decimal fractions, so sums drift by cents and equality checks fail. Fix: `decimal.Decimal` built from strings, or integer minor units. Rule: `design-value-objects`.

```python
fare = 2.35 * 3  # before: 7.050000000000001
fare = Decimal("2.35") * 3  # after: Decimal('7.05')
```

### shallow-frozen-dataclass

Severity: correctness. Spot: `@dataclass(frozen=True)` with `list`, `dict` or `set` fields. Why: the instance is unhashable, and its contents can still change through `route.stops.append(...)`. Fix: `tuple` and `frozenset` fields, converted from the caller's input. Rule: python-coding's python-frozen-dataclasses.

```python
@dataclass(frozen=True)
class Route:
    stops: tuple[str, ...]  # was list[str]


route = Route(stops=tuple(stop_names))
```

### leaked-mutable-internals

Severity: correctness. Spot: a method or property returns the object's own list or dict. Why: callers can mutate state the class believes it guards. Fix: return a tuple, a copy or a read-only view. Rule: python-coding's python-hide-internal-state.

```python
def readings(self) -> tuple[float, ...]:
    return tuple(self._readings)  # was: return self._readings
```

### list-scan-lookup

Severity: design. Spot: a loop with `break`, or `next(x for x in items if ...)`, used for keyed lookup, especially inside another loop; frequent re-sorting for the same reason. Why: each lookup is linear, quadratic inside a loop, and every scan site re-implements "not found". Fix: build a dict keyed by the lookup field once. Rule: python-coding's python-collection-choice.

```python
class ModelRegistry:
    def __init__(self, models: Iterable[ModelInfo]) -> None:
        # was: a list scanned on every lookup
        self._by_key = {(m.brand, m.model): m for m in models}

    def find(self, brand: str, model: str) -> ModelInfo | None:
        return self._by_key.get((brand, model))
```

## Functions and signatures

### mutable-default-argument

(scanner) Severity: correctness. Spot: a default of `[]`, `{}`, `set()` or another mutable value. Why: the default is created once, when `def` runs, and shared by every call. Fix: an immutable default for read-only input, or `None` plus an explicit copy; `field(default_factory=list)` in a dataclass. Rule: python-coding's python-typing.

```python
def tag(item: Item, tags: list[str] = []) -> list[str]: ...  # before


def tag(item: Item, tags: Sequence[str] = ()) -> list[str]:  # after
    return [*tags, item.kind]
```

### long-parameter-list

(scanner: more than five parameters, not counting `self` or `cls`) Severity: design. Spot: long signatures, especially where neighbors belong together (first name, last name and email are a customer). Why: call sites pass arguments in the wrong order, and every new option widens every caller. Fix: group related values into a record and make options keyword-only. Rule: `design-start-with-the-data`; keyword-only options are python-coding's python-function-signatures.

```python
def reserve_room(room_number, first_name, last_name, email, from_date, to_date): ...


def reserve_room(room_id: RoomId, guest: Guest, stay: DateRange) -> Reservation: ...
```

### boolean-flag-parameter

(scanner) Severity: design. Spot: a `bool` parameter whose value chooses between two blocks of the body. Why: the function does two jobs, and a call such as `place_order(amount, True)` hides which one. Fix: two functions when the flag picks an algorithm. Keep a keyword-only flag that tweaks one detail (`*, include_header: bool = True`); the scanner flags those too, so confirm before reporting. Rule: python-coding's python-function-signatures.

```python
class Wallet:
    def place_order(self, amount_cents: int, is_buying: bool) -> None: ...  # before

    def buy(self, amount_cents: int) -> None: ...  # after

    def sell(self, amount_cents: int) -> None: ...
```

### long-function

(scanner: more than 50 statement lines) Severity: design. Spot: a function that scrolls, usually with comments marking its phases. Why: no single read holds it, and its phases cannot be tested alone. Fix: extract each phase into a named function and keep the original as a short coordinator; split gathering inputs, computing and presenting. Rule: python-coding's python-small-units.

```python
def nightly_report(station: Station, now: datetime) -> str:  # was 80 lines doing all three
    readings = load_readings(station, since=now - DAY)
    summary = summarize(readings)
    return render_summary(station, summary)
```

### deep-nesting

(scanner: more than three nested blocks in a function) Severity: design. Spot: the logic that matters sits four indents deep. Why: each level is a condition the reader must hold in mind. Fix: guard clauses, `continue` for skipped items, and extracting the inner body. Rule: python-coding's python-early-return.

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

### magic-number

Severity: clarity. Spot: a bare literal whose meaning lives in the author's head (`if km > 100`), or a marker string repeated across a module (`grid[row][col] = "O"`). Why: the reader must guess what it stands for, and changing it means finding every copy. Fix: a named module constant, or a setting when it varies by deployment. Rule: python-coding's python-data-shapes.

```python
FREE_KM: Final = 100

paid_km = max(0, km - FREE_KM)  # was: km - 100 behind if km > 100
```

### misleading-verb

Severity: clarity, or design when callers rely on the wrong reading. Spot: `get_` that hits the network or writes a cache, `create_` that appends to a list and returns nothing, `is_` that mutates. Why: callers reason from the name and get the wrong cost or effect. Fix: rename to the behavior (`fetch_`, `load_`, `add_`, `ensure_`) or change the behavior to match. Rule: `design-name-for-intent`.

```python
def create_line_item(self, name: str, quantity: int) -> None: ...  # before: appends, returns None


def add_line_item(self, item: LineItem) -> None: ...  # after
```

## Naming

### type-in-name

(scanner: identifiers ending `_str`, `_int`, `_list`, `_dict`, `_set`, `_tuple`, `_bool`, or starting `str_`, `list_`, `dict_`) Severity: clarity. Spot: parameters and assignments named for their type. Why: the annotation already states the type, and the name lies once the type changes. Fix: name the role. Rule: `design-name-for-intent`.

```python
def notify(email_str: str, retries_int: int) -> None: ...  # before


def notify(recipient: str, max_attempts: int) -> None: ...  # after
```

### vague-name

Severity: clarity. Spot: public names such as `data`, `info`, `item`, `tmp`, `result`, `process`, `handle`, `manager`; abbreviations such as `cfg`, `mgr`, `cnt`; single letters outside comprehensions, short lambdas and math. If a comment is needed to say what a variable holds, the name is too vague. Why: the reader has to trace the value to learn what it is. Fix: name what it holds or does. Rule: `design-name-for-intent`; general naming is python-coding's python-meaningful-names.

```python
def process(data: list[Reading]) -> float: ...  # before


def mean_soil_moisture(readings: list[Reading]) -> float: ...  # after
```

### shadowed-builtin

Severity: clarity, correctness when the builtin is called later in the same scope. Spot: locals or parameters named `id`, `type`, `list`, `filter`, `input`, `format`, `sum`. Why: later code in that scope calling the builtin gets the local instead. Fix: a domain name. Rule: python-coding's python-idioms.

```python
def archive(id: str, type: str) -> None: ...  # before


def archive(episode_id: str, media_type: str) -> None: ...  # after
```

### asymmetric-names

Severity: clarity. Spot: sibling classes doing the same job under different names or signatures (`compute_rent(days)` beside `compute_rental_price(from_date, to_date)`), or custom string methods where a dunder exists. Why: callers need a branch per class, and a shared Protocol is impossible. Fix: one name and signature, or the matching dunder (`__str__`, `__len__`, `__iter__`). Rule: `design-name-for-intent`.

```python
class PowerDrill:
    def compute_rent(self, days: int) -> int: ...


class CementMixer:
    def compute_rent(self, days: int) -> int: ...  # was compute_rental_price(from_date, to_date)
```

### junk-drawer-package

Severity: design. Spot: packages or modules named `utils`, `helpers`, `misc`, `common` or `managers`. Why: they attract everything that has no obvious home, so they grow without a theme and everything imports them. Fix: name the package for its domain concept (`pricing/`, `importers/`) and move each function next to its callers. Rule: python-architecture's arch-no-junk-drawer-packages.

## Classes

### low-cohesion-class

(found with lcom4_clusters.py) Severity: design. Spot: methods split into groups that share no attributes and never call each other (LCOM4 above 1), a class name joined with "and", or a god class that does everything. Why: unrelated reasons to change collide in one file and one test fixture. Fix: one class per cluster; the original either disappears or composes the parts. The script skips Protocol classes and classes with fewer than two methods, leaves stub-only methods, classmethods, staticmethods and dunders such as `__init__` out of the graph, and counts a property read as an attribute access. Rule: `design-split-god-class`.

```python
class TelescopeController:  # before: slew()/track() use mount; notify_*() use mailer
    ...


class Mount: ...  # after: one class per cluster


class ObservationNotifier: ...
```

### namespace-class

(scanner: a class whose methods are all staticmethods) Severity: clarity. Spot: a class used only as a prefix for functions. Why: it adds a level of indirection and suggests state that does not exist. Fix: move the functions to a module; the module name becomes the namespace. Rule: `design-lightest-construct`.

```python
class FareMath:  # before
    @staticmethod
    def peak_fare(base: Decimal) -> Decimal: ...


# after, in fares.py
def peak_fare(base: Decimal) -> Decimal: ...
```

### method-could-be-function

(scanner) Severity: clarity. Spot: an instance method that never reads `self`. The scanner skips overrides of a base-class method, `@override`, `@abstractmethod`, properties and setters, class and static methods, dunders and Protocol classes; still confirm, because a method may exist to satisfy a structural interface. Why: it implies a dependency on instance state that is not there, and it cannot be called without an instance. Fix: a module-level function. Rule: `design-lightest-construct`.

```python
class Hotel:
    def generate_room_id(self) -> str:  # before: self unused
        return str(uuid.uuid4())


def generate_room_id() -> str:  # after
    return str(uuid.uuid4())
```

### single-method-class

Severity: restraint. Spot: a class with `__init__` and one other method, often named `run` or `execute`, or no state at all. Why: the class is ceremony around a function. Fix: a function, or a closure when configuration is fixed early. A callable dataclass holding named configuration is fine. Rule: `design-lightest-construct`.

```python
class SlugMaker:  # before
    def make(self, title: str) -> str: ...


def make_slug(title: str) -> str: ...  # after
```

### feature-envy

Severity: design. Spot: a function or method that reads several attributes of one other object to compute or change something about it (ask, then act). Why: the logic lives away from its data, so changes to the data scatter. Fix: move the computation to the object that owns the data (tell, do not ask). Rule: `design-tell-dont-ask`.

```python
def normalize(vector: Vector) -> None:  # before: reads and writes another object's fields
    length = math.hypot(vector.x, vector.y)
    vector.x, vector.y = vector.x / length, vector.y / length


vector.normalize()  # after: Vector owns the formula
```

### value-only-subclass

Severity: restraint. Spot: a subclass whose only change is passing different constants to `super().__init__`. Why: a class per configuration multiplies types without new behavior. Fix: instances or a factory function with those values. Rule: `design-composition-over-inheritance`.

```python
class ExpressParcel(Parcel):  # before
    def __init__(self) -> None:
        super().__init__(max_days=1)


express = Parcel(max_days=1)  # after
```

### inheritance-for-reuse

Severity: design. Spot: hierarchies three or more levels deep, or mixins that read attributes the host class must provide. Why: behavior is spread over files, and a change to the base ripples to subclasses that never asked for it. Fix: compose a collaborator and delegate. Not this smell: framework base classes, framework-required mixins, exception trees, and ABCs that document an extension point. Rule: `design-composition-over-inheritance`.

```python
class AuditedCsvExportMixin:  # before: reads self.rows and self.user set by the host
    ...


class CsvExport:  # after: collaborators are explicit
    def __init__(self, rows: Sequence[Row], audit: AuditLog) -> None: ...
```

### isinstance-ladder

(scanner: three or more `isinstance` tests in one if/elif chain) Severity: design. Spot: dispatch on the type of an argument. Why: each added type forces another edit to the ladder, and a forgotten branch silently falls through. Fix: put the behavior on the types behind a method or Protocol; use `functools.singledispatch` for types you do not own; a `match` on classes is acceptable when it ends in `case _: raise`. Rule: `design-open-closed`.

```python
def pay(employee: Employee) -> Payslip:  # before
    if isinstance(employee, SalariedEmployee):
        ...
    elif isinstance(employee, HourlyEmployee):
        ...
    elif isinstance(employee, Contractor):
        ...


payslip = employee.pay()  # after: each employee type implements pay()
```

## Coupling and construction

### hard-wired-collaborator

Severity: design. Spot: `__init__` or a business function constructs a client, session, mailer or file handle itself (`self.processor = CardGateway()`). Why: tests can only patch, and swapping the implementation means editing the class. Fix: take it as a parameter typed as a `Protocol` or `Callable`, and build it in the composition root. Rule: python-coding's python-dependency-injection; typing it as an abstraction the consumer owns is `design-dependency-inversion`.

```python
class PointOfSale:
    def __init__(self, charge: ChargeCard) -> None:  # was CardGateway() built inside
        self._charge = charge
```

### attribute-chain

Severity: design. Spot: `a.b.c.d` reaching through objects the code does not own, or writing through them (`game.scoreboard.points[name] += 1`); method chains on fluent APIs and value objects are fine. Why: the caller depends on the structure of every object along the chain. Fix: ask the nearest object for what you need, or pass that value in directly. Rule: `design-tell-dont-ask`.

```python
email = parcel.route.hub.manager.email  # before
email = parcel.hub_contact_email()  # after, or pass the email in
```

### private-access

Severity: design. Spot: code reading or writing another object's `_attribute` outside its class or module. Why: the owner can no longer change its internals safely. Fix: add the method the caller needs, or move the logic into the owner. Rule: `design-tell-dont-ask`.

```python
if feed._episodes:
    ...  # before
if feed.has_episodes():
    ...  # after
```

### module-level-mutable-global-rebound

(scanner: any `global` statement) Severity: correctness when threads or async tasks touch it, otherwise design. Spot: functions that rebind module state. Why: hidden coupling between callers, order-dependent tests and races. Fix: pass the state in and return the new state, or hold it in an object the entry point creates. Rule: `design-low-coupling`.

```python
_last_sync: float | None = None  # before


def sync() -> None:
    global _last_sync
    _last_sync = time.time()


def sync(state: SyncState, now: float) -> SyncState:  # after
    return replace(state, last_sync=now)
```

### two-step-initialization

Severity: design. Spot: an object unusable until the caller remembers `connect()`, `load()` or `init()`; documentation that says "call X before using Y". Why: forgetting the second call fails later and far away. Fix: do the work in a classmethod constructor that returns a ready instance, or require the inputs in `__init__`. Rule: `design-complete-construction`.

```python
feed = PodcastFeed()  # before
feed.load(path)

feed = PodcastFeed.from_file(path)  # after
```

### polymorphic-new

Severity: design. Spot: `__new__` that returns an instance of some other class depending on its arguments. Why: `Cls(...)` no longer means "a Cls", and type checkers and readers are misled. Fix: a factory function, or a mapping from key to constructor. Rule: `design-complete-construction`.

```python
def make_reader(fmt: LogFormat) -> LogReader:  # was Reader.__new__ switching on fmt
    reader_class = READER_CLASSES[fmt]
    return reader_class()
```

## Errors and idioms

### bare-except

(scanner) Severity: correctness. Spot: `except:` with no type. Why: it also catches `KeyboardInterrupt` and `SystemExit`, so Ctrl-C and shutdown are swallowed. Fix: the specific exception; at most `except Exception` when the handler cleans up and re-raises. Rule: python-coding's python-error-handling.

```python
def parse_amount(text: str) -> int:
    try:
        return int(text)
    except ValueError as exc:  # was: except: return "error"
        raise InvalidAmountError(f"expected a whole number, got {text!r}") from exc
```

### swallowed-exception

(scanner: `except Exception` or `except BaseException` whose body is only `pass`, `...` or `continue`) Severity: correctness. Spot: failures disappear without a trace, or a broad catch maps every failure to one answer. Why: bugs become wrong data far from their cause. Fix: catch the specific expected error and handle it; otherwise let it propagate. Logging and moving on is acceptable only at an isolation boundary such as a per-item batch loop, and only with `logger.exception`. Rule: python-coding's python-error-handling.

```python
for path in uploads:
    try:
        ingest(path)
    except CorruptUpload:  # was: except Exception: continue
        logger.exception("skipping corrupt upload", extra={"path": str(path)})
```

### missing-with

Severity: correctness. Spot: `open()`, connections, locks or temporary directories released by hand, or not at all. Why: an exception between acquire and release leaks the resource. Fix: `with`, `ExitStack` for a dynamic set, or a context manager for repeated setup and teardown. Rule: python-coding's python-context-managers.

```python
with path.open(encoding="utf-8") as fh:  # was: fh = open(path); ...; fh.close()
    header = fh.readline()
```

### missing-wraps

Severity: clarity, correctness when tools rely on metadata. Spot: a decorator's inner function lacks `functools.wraps`. Why: the wrapped function loses its name, docstring and signature, which breaks introspection, framework routing and debugging. Fix: `@functools.wraps(func)`, plus `ParamSpec` to keep the signature typed. Rule: python-coding's python-decorators.

```python
def timed(func: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R: ...

    return wrapper
```

### match-without-fallback

Severity: correctness. Spot: a `match` over an enum, string or class set with no `case _:`. Why: an unhandled value falls through silently and the function returns `None`. Fix: end with `case _:` that raises, or `assert_never(value)` so the type checker proves exhaustiveness. Rule: python-coding's python-match-fallback.

```python
match mode:
    case WateringMode.DRIP:
        ...
    case WateringMode.SPRAY:
        ...
    case _:
        assert_never(mode)
```

### method-cache

Severity: correctness. Spot: `@functools.cache` or `@lru_cache` on an instance method. Why: one cache keyed on `self` serves every instance, so it keeps instances alive long after their last use and, when bounded, evicts one instance's entries to make room for another's. Fix: `functools.cached_property` for per-instance values, or a cached module-level function keyed on plain values. Rule: python-coding's python-properties.

```python
@cached_property
def star_catalog(self) -> Catalog:  # was @lru_cache on a method
    return load_catalog(self._catalog_path)
```

### naive-datetime

Severity: correctness. Spot: `datetime.now()` or `datetime.utcnow()` without a timezone, or naive timestamps stored and compared with aware ones. Why: comparisons fail or shift by hours across machines and daylight-saving changes. Fix: `datetime.now(timezone.utc)`, injected as a clock in domain code. Rule: python-coding's python-pure-core.

```python
def permit_expired(
    expires_at: datetime, now: datetime
) -> bool:  # the caller passes the clock's now
    return expires_at <= now
```

### wildcard-import

Severity: clarity. Spot: `from module import *`. Why: readers and linters cannot tell where a name came from, and later imports silently shadow earlier ones. Fix: import the names you use, or the module. Rule: python-coding's python-imports.

```python
from tides.models import TidePrediction, TideStation  # was: from tides.models import *
```

## Restraint

### speculative-abstraction

Severity: restraint. Spot: a Protocol, ABC, factory, registry or strategy with exactly one implementation, no test double and no planned second variant; pass-through layers that only forward calls. Why: every reader pays for indirection that buys nothing yet. Fix: inline to the concrete form, and reintroduce the seam when a second implementation or a test needs it. Not this smell: a port at an I/O boundary that tests fake, and documented extension points. Rule: `design-pattern-from-smell`.

```python
class GreetingStrategy(Protocol): ...  # before: one implementation, never swapped


class DefaultGreeting: ...


def build_greeting(strategy: GreetingStrategy) -> str: ...


def greeting(name: str) -> str:  # after
    return f"Welcome back, {name}"
```

A variable reassigned through three or four fixed steps is not a smell by itself: the steps read fine inline. A list of named step functions (`design-pipeline`) pays off only once the steps are configurable or reused.
