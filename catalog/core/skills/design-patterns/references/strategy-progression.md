# Strategy: from classes to functions

A step-by-step walk from the class-based strategy pattern to its Pythonic forms, for `design-strategy`. Every step keeps the same job: an order computes its total with a discount it receives, and never learns which discount it got. Amounts are integer cents; percentages are `Decimal` with explicit rounding. Stop at the first step that reads well for your code: later is not better.

## Contents

- The shared helper
- Classic form: an abstract base class
- Step 1: a Protocol instead of the ABC
- Step 2: a Callable alias with callable classes
- Step 3: callable dataclasses carry the configuration
- Step 4: plain functions
- Step 5: closures build configured functions
- Step 6: functools.partial
- When to use a strategy
- Trade-offs
- Gotchas
- Related rules

## The shared helper

Every step below rounds a percentage of an amount the same way:

```python
def percent_of(amount_cents: int, percent: Decimal) -> int:
    share = Decimal(amount_cents) * percent / 100
    return int(share.quantize(Decimal(1), rounding=ROUND_HALF_UP))
```

## Classic form: an abstract base class

Each branch of the old if/elif becomes a subclass; `Order` depends only on the abstraction.

```python
class DiscountStrategy(ABC):
    @abstractmethod
    def compute(self, subtotal_cents: int) -> int:
        """The discount, in cents, for a subtotal in cents."""


class PercentageDiscount(DiscountStrategy):
    def compute(self, subtotal_cents: int) -> int:
        return percent_of(subtotal_cents, Decimal(20))


class FixedDiscount(DiscountStrategy):
    def compute(self, subtotal_cents: int) -> int:
        return 10_00


@dataclass(frozen=True)
class Order:
    price_cents: int
    quantity: int
    discount: DiscountStrategy

    def total_cents(self) -> int:
        subtotal = self.price_cents * self.quantity
        return max(0, subtotal - self.discount.compute(subtotal))
```

This already raises cohesion (`Order` holds price and quantity and delegates the discount), lowers coupling (`Order` never imports a concrete discount) and makes the order open for extension. Two problems remain: the rates are magic numbers inside each class, and every variant pays for a class.

## Step 1: a Protocol instead of the ABC

Drop the inheritance: any class with a matching `compute` method fits.

```python
class DiscountStrategy(Protocol):
    def compute(self, subtotal_cents: int) -> int: ...


class FixedDiscount:  # no base class
    def compute(self, subtotal_cents: int) -> int:
        return 10_00
```

Keep the ABC instead when the strategies share state or helper methods in the base, or when a missing method should fail at instantiation.

## Step 2: a Callable alias with callable classes

Each strategy has one method, and a class with one method is a function waiting to get out. The abstraction becomes a type, not a hierarchy:

```python
DiscountFunction = Callable[[int], int]  # subtotal in cents -> discount in cents


class FixedDiscount:
    def __call__(self, subtotal_cents: int) -> int:
        return 10_00


@dataclass(frozen=True)
class Order:
    price_cents: int
    quantity: int
    discount: DiscountFunction

    def total_cents(self) -> int:
        subtotal = self.price_cents * self.quantity
        return max(0, subtotal - self.discount(subtotal))
```

Any callable with that signature now works: a class with `__call__`, a function, a bound method.

## Step 3: callable dataclasses carry the configuration

The magic numbers go: each strategy receives its configuration when it is built.

```python
@dataclass(frozen=True)
class PercentageDiscount:
    percent: Decimal

    def __call__(self, subtotal_cents: int) -> int:
        return percent_of(subtotal_cents, self.percent)


@dataclass(frozen=True)
class FixedDiscount:
    amount_cents: int

    def __call__(self, subtotal_cents: int) -> int:
        return min(self.amount_cents, subtotal_cents)


order = Order(price_cents=100_00, quantity=2, discount=PercentageDiscount(Decimal(30)))
# order.total_cents() == 140_00
```

This step is often the practical sweet spot: named, inspectable configuration (`PercentageDiscount(percent=Decimal(15))`) and a value that still matches `DiscountFunction`.

## Step 4: plain functions

When a strategy needs no configuration, drop the class entirely. `Order` now receives a function: a strategy, at its core, is a higher-order function.

```python
def no_discount(subtotal_cents: int) -> int:
    return 0


def staff_discount(subtotal_cents: int) -> int:
    return percent_of(subtotal_cents, Decimal(20))


order = Order(price_cents=100_00, quantity=2, discount=staff_discount)
```

The magic number is back in `staff_discount`, and the `(int) -> int` signature leaves no room for a configuration parameter.

## Step 5: closures build configured functions

A builder function takes the configuration and returns a function that matches the alias. Configuration-time arguments (the percent) and runtime arguments (the subtotal) are now separate, and they can differ completely in kind.

```python
def percentage_discount(percent: Decimal) -> DiscountFunction:
    def discount(subtotal_cents: int) -> int:
        return percent_of(subtotal_cents, percent)

    return discount


order = Order(price_cents=100_00, quantity=2, discount=percentage_discount(Decimal(15)))
# order.total_cents() == 170_00
```

`percentage_discount(Decimal(15))` computes nothing: it builds the function that does. This is `design-function-builder`.

## Step 6: functools.partial

When the configuration is simply some of the function's own parameters, pre-apply them:

```python
def percentage_discount(subtotal_cents: int, *, percent: Decimal) -> int:
    return percent_of(subtotal_cents, percent)


discount = partial(percentage_discount, percent=Decimal(12))
order = Order(price_cents=100_00, quantity=2, discount=discount)
# order.total_cents() == 176_00
```

## When to use a strategy

Signals in existing code:

- a long if/elif where each branch is a variant of one computation (a discount, a sort order, a validation rule);
- a method with a `type` or `mode` parameter that selects a logic path;
- parameter lists that grow with each variant, holding values only one variant uses;
- methods duplicated except for one behavioral step;
- the caller needs to choose the behavior at run time.

Confirm with one question: does this function do different things depending on a flag, and will there be more options? If yes, extract a strategy. A two-branch if/else that will not grow keeps its `if`.

## Trade-offs

| Form | Use when | Avoid when |
| --- | --- | --- |
| Mapping lookup | Branches map keys to values or to handlers named in config | Each branch has different logic or needs runtime state |
| ABC | Strategies share state or helper methods in the base | The strategy is one method with no shared state |
| Protocol | Several cooperating methods, or the method name carries meaning | A shared base implementation is needed |
| Callable alias | The strategy is one function | It needs several cooperating methods |
| Callable dataclass | Named configuration or state between calls | No configuration at all |
| Closure (function builder) | Configuration differs in kind from the runtime arguments | Plain pre-binding is enough |
| `functools.partial` | The configuration is a subset of the function's parameters | Typing precision matters |

## Gotchas

- `functools.partial` blurs the signature: some type checkers infer only `partial[int]`, so a mismatch with `DiscountFunction` can slip through, and reprs and tracebacks hide what was bound. Prefer a closure or a callable dataclass where typing matters.
- A one-line lambda is fine for a throwaway; logic that needs a name belongs in a named inner function, as in step 5.
- Callable classes keep their place: configuration stored as fields or state between calls (a counter, a cache) reads better in a dataclass with `__call__` than in a closure with `nonlocal`.
- Do not widen the shared signature with parameters only one variant needs: a percent and a fixed amount are construction-time concerns of their own strategies, not part of `DiscountFunction`.
- A single-method Protocol and a `Callable` alias are equivalent; prefer the alias for brevity, and the Protocol when the method name carries meaning.

## Related rules

- `design-function-builder`: the closure of step 5, generalized; the builder's parameters can be unrelated to the returned function's.
- `design-dispatch-table`: when each branch only maps a key from data to a value or a handler.
- `design-abstract-factory`: several strategies that must be swapped together as a family.
- `design-command`: also replaces behavior with a callable, but to store, sequence and undo actions rather than to select an algorithm.
- `design-bridge`: two independent axes, each injected like a strategy.
- `design-pipeline`: strategies applied one after another.
