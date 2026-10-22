# Abstract factory: from factory classes to a frozen bundle

A step-by-step walk from the class-based abstract factory to the frozen bundle of callables that `design-abstract-factory` recommends. The example is a tax system whose income tax and capital tax must always come from the same family, progressive or flat. Amounts are integer cents; rates are `Decimal` percentages with explicit rounding.

## Contents

- The shared helpers
- Classic form: factory classes
- Step 1: Protocols instead of ABCs
- Step 2: functions instead of single-method products
- Step 3: a tuple of functions instead of the factory class
- Step 4: functools.partial removes the duplicates
- Step 5: builder functions take the configuration
- Final form: a frozen dataclass bundle
- When to use an abstract factory
- Trade-offs
- Progression summary
- Decision guide

## The shared helpers

```python
def percent_of(amount_cents: int, percent: Decimal) -> int:
    share = Decimal(amount_cents) * percent / 100
    return int(share.quantize(Decimal(1), rounding=ROUND_HALF_UP))


#: (upper bound of the bracket in cents, or None for the top bracket; rate in percent)
Bracket = tuple[int | None, Decimal]
BRACKETS: Final[tuple[Bracket, ...]] = ((50_000_00, Decimal(20)), (None, Decimal(40)))


def bracketed_tax(taxable_cents: int, brackets: Sequence[Bracket]) -> int:
    tax, lower = 0, 0
    for upper, rate in brackets:
        top = taxable_cents if upper is None else min(taxable_cents, upper)
        if top <= lower:
            break
        tax += percent_of(top - lower, rate)
        lower = top
    return tax
```

## Classic form: factory classes

Two product interfaces, two products per family, one factory interface and one factory per family.

```python
class IncomeTax(ABC):
    @abstractmethod
    def compute(self, income_cents: int) -> int: ...


class CapitalTax(ABC):
    @abstractmethod
    def compute(self, capital_cents: int) -> int: ...


class ProgressiveIncomeTax(IncomeTax):
    def compute(self, income_cents: int) -> int:
        return bracketed_tax(max(0, income_cents - 10_000_00), BRACKETS)


class FlatIncomeTax(IncomeTax):
    def compute(self, income_cents: int) -> int:
        return percent_of(income_cents, Decimal(10))


class PercentageCapitalTax(CapitalTax):
    def compute(self, capital_cents: int) -> int:
        return percent_of(capital_cents, Decimal(5))


class ZeroCapitalTax(CapitalTax):
    def compute(self, capital_cents: int) -> int:
        return 0


class TaxFactory(ABC):
    @abstractmethod
    def income_tax(self) -> IncomeTax: ...

    @abstractmethod
    def capital_tax(self) -> CapitalTax: ...


class ProgressiveTaxFactory(TaxFactory):
    def income_tax(self) -> IncomeTax:
        return ProgressiveIncomeTax()

    def capital_tax(self) -> CapitalTax:
        return PercentageCapitalTax()


class FlatTaxFactory(TaxFactory):
    def income_tax(self) -> IncomeTax:
        return FlatIncomeTax()

    def capital_tax(self) -> CapitalTax:
        return ZeroCapitalTax()


def compute_tax(factory: TaxFactory, income_cents: int, capital_cents: int) -> int:
    income = factory.income_tax().compute(income_cents)
    capital = factory.capital_tax().compute(capital_cents)
    return income + capital
```

Switching `ProgressiveTaxFactory()` for `FlatTaxFactory()` changes the whole system without touching `compute_tax`, and no caller can mix a progressive income tax with a flat capital tax. The cost: nine classes for two families of two one-method products, and the rates are buried inside them.

## Step 1: Protocols instead of ABCs

```python
class IncomeTax(Protocol):
    def compute(self, income_cents: int) -> int: ...


class TaxFactory(Protocol):
    def income_tax(self) -> IncomeTax: ...
    def capital_tax(self) -> CapitalTax: ...
```

The concrete classes stay and drop their base classes; they satisfy the Protocols structurally, so the products no longer import the interfaces. There are still as many classes.

## Step 2: functions instead of single-method products

Each product has one method, so each becomes a function under a role-named alias:

```python
TaxRule = Callable[[int], int]  # amount in cents -> tax in cents


def progressive_income_tax(income_cents: int) -> int:
    return bracketed_tax(max(0, income_cents - 10_000_00), BRACKETS)


def flat_income_tax(income_cents: int) -> int:
    return percent_of(income_cents, Decimal(10))


def capital_gains_tax(capital_cents: int) -> int:
    return percent_of(capital_cents, Decimal(5))


def no_tax(amount_cents: int) -> int:
    return 0
```

This works only because each product had one method and no state. Products with several methods or state stay objects.

## Step 3: a tuple of functions instead of the factory class

The factory existed to group the members of a family. A typed tuple groups them with no class:

```python
TaxFamily = tuple[TaxRule, TaxRule]  # (income tax, capital tax)

PROGRESSIVE: Final[TaxFamily] = (progressive_income_tax, capital_gains_tax)
FLAT: Final[TaxFamily] = (flat_income_tax, no_tax)


def compute_tax(family: TaxFamily, income_cents: int, capital_cents: int) -> int:
    income_tax, capital_tax = family
    return income_tax(income_cents) + capital_tax(capital_cents)
```

Both members share one type, so a family written in the wrong order still type-checks; the final form fixes that.

## Step 4: functools.partial removes the duplicates

`flat_income_tax` and `capital_gains_tax` both take a percentage of an amount. One generic function, configured per use, replaces them:

```python
def rate_tax(amount_cents: int, *, percent: Decimal, allowance_cents: int = 0) -> int:
    return percent_of(max(0, amount_cents - allowance_cents), percent)


FLAT: Final[TaxFamily] = (partial(rate_tax, percent=Decimal(10)), no_tax)
PROGRESSIVE: Final[TaxFamily] = (progressive_income_tax, partial(rate_tax, percent=Decimal(5)))
```

## Step 5: builder functions take the configuration

Rates and allowances are configuration, not part of the `TaxRule` signature. A builder function takes them once and returns the configured family, so the entry point can build a family from settings:

```python
def progressive_family(*, allowance_cents: int, capital_percent: Decimal) -> TaxFamily:
    def income_tax(income_cents: int) -> int:
        return bracketed_tax(max(0, income_cents - allowance_cents), BRACKETS)

    return income_tax, partial(rate_tax, percent=capital_percent)


def flat_family(*, percent: Decimal) -> TaxFamily:
    return partial(rate_tax, percent=percent), no_tax
```

This is `design-function-builder` applied to a whole family. Moving the configured parameters into the builder keeps the alias down to the runtime argument, which is also what lets a type checker match the returned callables against `TaxRule`.

## Final form: a frozen dataclass bundle

Replace the positional tuple with a frozen dataclass whose fields name each member. The builders return it, the entry point picks one family once, and `compute_tax` reads the members by name:

```python
@dataclass(frozen=True)
class TaxSystem:
    income_tax: TaxRule
    capital_tax: TaxRule


def progressive_system(*, allowance_cents: int, capital_percent: Decimal) -> TaxSystem:
    def income_tax(income_cents: int) -> int:
        return bracketed_tax(max(0, income_cents - allowance_cents), BRACKETS)

    def capital_tax(capital_cents: int) -> int:
        return rate_tax(capital_cents, percent=capital_percent)

    return TaxSystem(income_tax=income_tax, capital_tax=capital_tax)


def flat_system(*, percent: Decimal) -> TaxSystem:
    def income_tax(income_cents: int) -> int:
        return rate_tax(income_cents, percent=percent)

    return TaxSystem(income_tax=income_tax, capital_tax=no_tax)


def compute_tax(system: TaxSystem, income_cents: int, capital_cents: int) -> int:
    return system.income_tax(income_cents) + system.capital_tax(capital_cents)


# The entry point builds the family once, from settings.
system = progressive_system(allowance_cents=10_000_00, capital_percent=Decimal(5))
tax = compute_tax(system, income_cents=100_000_00, capital_cents=100_000_00)
```

Named inner functions instead of `partial` keep every member's signature exact for the type checker and readable in a traceback.

## When to use an abstract factory

Signals:

- several boolean flags select related variants (`progressive: bool`, `tax_capital: bool`);
- objects vary together as a family: switching the tax system changes both calculators at once;
- new families are expected, each bringing a matching set of members;
- the consumer should not know which concrete members it got;
- several call sites build the same family on their own.

Not when there is one product (pass one function: `design-strategy`), when the members vary independently, or when there are exactly two variants that will not grow (an `if` is clearer).

## Trade-offs

`functools.partial` does not carry full type information. A function with extra keyword parameters assigned to `Callable[[int], int]`, or a `partial` object, may not be matched exactly against the alias. Do not silence that with a bare ignore; instead:

1. move configured parameters into a builder function, so the alias describes only the runtime arguments;
2. return named inner functions from the builder, as in the final form;
3. keep the Protocol-based factory when full static typing of every member is required.

Keep the class-based factory when the products have several methods (`calculate()`, `validate()` and `summary()` cannot be one function), when they keep state between calls, or when the team reads class-based factories more easily than bundles of callables. Classes are callables too, so a class object can stand in as a bundle field.

## Progression summary

| Form | Classes | Type safety | Best for |
| --- | --- | --- | --- |
| ABC hierarchy | many | full | multi-method products, shared state |
| Protocol hierarchy | many | full | the same, with structural typing |
| Callable aliases | none | good | single-method products |
| Tuple of functions | none | good, but order is unchecked | grouping related callables |
| `partial` and tuple | none | partial | configurable single-method products |
| Builder function | none | good with named inner functions | configuring a family at the entry point |
| Frozen dataclass bundle | one | good | the default: named members chosen once |

## Decision guide

```text
Must several objects or functions be swapped together as a family?
  No  -> one behavioral swap: design-strategy
  Yes -> Is each member a single method without state?
           No  -> factory classes behind a Protocol (step 1)
           Yes -> Does a family need configuration (rates, thresholds)?
                    No  -> a frozen dataclass bundle of functions
                    Yes -> builder functions that return the bundle
```
