# Bridge: from two class hierarchies to functions

A step-by-step walk from the class-based bridge to its Pythonic forms, for `design-bridge`. The example has two independent axes: where prices come from and trades go (an exchange), and how to decide (a trading rule). Without a bridge, every combination is its own class (`PaperAverageBot`, `PaperThresholdBot`, `LiveAverageBot`, ...): one new exchange needs a class per rule, one new rule a class per exchange. The bridge joins the two axes once, through an abstraction. Prices are `Decimal`; the exchanges are illustrative.

## Contents

- Classic form: an ABC bridge
- When an ABC is the right bridge
- Step 1: Protocols instead of ABCs
- Step 2: functions that take the object
- Step 3: functions that take a function
- Step 4: bound methods as the bridge
- Step 5: functools.partial for full configuration
- When to stop
- Trade-offs
- Bridge, strategy, adapter and injection

## Classic form: an ABC bridge

One hierarchy per axis. The abstract bot holds a reference to the abstract exchange, and that reference is the bridge.

```python
class Exchange(ABC):
    @abstractmethod
    def prices(self, symbol: str) -> Sequence[Decimal]: ...

    @abstractmethod
    def buy(self, symbol: str, quantity: int) -> None: ...

    @abstractmethod
    def sell(self, symbol: str, quantity: int) -> None: ...


class PaperExchange(Exchange):  # a simulated exchange for dry runs
    def __init__(self, history: Mapping[str, Sequence[Decimal]], ledger: Ledger) -> None:
        self._history = history
        self._ledger = ledger

    def prices(self, symbol: str) -> Sequence[Decimal]:
        return self._history[symbol]

    def buy(self, symbol: str, quantity: int) -> None:
        self._ledger.record(Side.BUY, symbol, quantity)

    def sell(self, symbol: str, quantity: int) -> None:
        self._ledger.record(Side.SELL, symbol, quantity)


class TradingBot(ABC):
    def __init__(self, exchange: Exchange) -> None:
        self.exchange = exchange  # the bridge: typed as the abstraction

    @abstractmethod
    def should_buy(self, symbol: str) -> bool: ...

    @abstractmethod
    def should_sell(self, symbol: str) -> bool: ...


class AverageBot(TradingBot):
    def should_buy(self, symbol: str) -> bool:
        prices = self.exchange.prices(symbol)
        return prices[-1] < statistics.mean(prices[-3:])

    def should_sell(self, symbol: str) -> bool:
        prices = self.exchange.prices(symbol)
        return prices[-1] > statistics.mean(prices[-3:])


def trade_once(bot: TradingBot, exchange: Exchange, symbol: str, quantity: int) -> None:
    if bot.should_buy(symbol):
        exchange.buy(symbol, quantity)
    elif bot.should_sell(symbol):
        exchange.sell(symbol, quantity)
```

Swap `AverageBot` for another rule and no exchange code changes; swap the exchange and no bot changes. The bot imports `Exchange`, never a concrete exchange, and the exchange knows nothing of bots: the link is one-way and abstract, the depend-on-abstractions principle applied to two class trees.

## When an ABC is the right bridge

An abstract base can hold shared state and helpers that every concrete bot inherits:

```python
class TradingBot(ABC):
    def __init__(self, exchange: Exchange, *, max_quantity: int) -> None:
        self.exchange = exchange
        self.max_quantity = max_quantity

    def within_limit(self, quantity: int) -> bool:  # shared by every concrete bot
        return quantity <= self.max_quantity

    @abstractmethod
    def should_buy(self, symbol: str) -> bool: ...
```

A Protocol cannot hold that implementation. Keep the ABC when the bridge side is more than an interface.

## Step 1: Protocols instead of ABCs

Both axes become Protocols. Since nothing inherits a Protocol, each concrete bot declares its own `exchange` field: the bridge moves from the base class into each bot.

```python
class Exchange(Protocol):
    def prices(self, symbol: str) -> Sequence[Decimal]: ...
    def buy(self, symbol: str, quantity: int) -> None: ...
    def sell(self, symbol: str, quantity: int) -> None: ...


class TradingBot(Protocol):
    def should_buy(self, symbol: str) -> bool: ...
    def should_sell(self, symbol: str) -> bool: ...


@dataclass(frozen=True)
class AverageBot:
    exchange: Exchange

    def should_buy(self, symbol: str) -> bool:
        prices = self.exchange.prices(symbol)
        return prices[-1] < statistics.mean(prices[-3:])

    def should_sell(self, symbol: str) -> bool:
        prices = self.exchange.prices(symbol)
        return prices[-1] > statistics.mean(prices[-3:])
```

The cost is one repeated field per bot; the gain is structural typing, so an exchange class from another package fits without inheriting anything.

## Step 2: functions that take the object

`AverageBot` holds nothing but the exchange, so its two methods are really two functions:

```python
def should_buy_on_average(exchange: Exchange, symbol: str) -> bool:
    prices = exchange.prices(symbol)
    return prices[-1] < statistics.mean(prices[-3:])


def should_sell_on_average(exchange: Exchange, symbol: str) -> bool:
    prices = exchange.prices(symbol)
    return prices[-1] > statistics.mean(prices[-3:])
```

The bot class and its Protocol are gone; the bridge is the `Exchange` parameter.

## Step 3: functions that take a function

The rules call only `prices` on the exchange. Depend on that one function instead of the whole object:

```python
PriceHistory = Callable[[str], Sequence[Decimal]]


def should_buy_on_average(prices_for: PriceHistory, symbol: str) -> bool:
    prices = prices_for(symbol)
    return prices[-1] < statistics.mean(prices[-3:])
```

The rule no longer knows an `Exchange` exists: any callable from a symbol to a price history works, including a lambda over a list in a test.

## Step 4: bound methods as the bridge

The entry point passes the exchange's bound method, which already matches the alias:

```python
exchange = PaperExchange(history, ledger)
if should_buy_on_average(exchange.prices, symbol):
    exchange.buy(symbol, quantity)
```

`exchange.prices` is a callable bound to its object. The bridge is now a `Callable` alias: new price sources and new rules meet only through `PriceHistory`.

## Step 5: functools.partial for full configuration

Every collaborator can become a function, with an orchestrator that takes them all:

```python
Decide = Callable[[PriceHistory, str], bool]
Trade = Callable[[str, int], None]


def run_bot(
    prices_for: PriceHistory,
    *,
    should_buy: Decide,
    should_sell: Decide,
    buy: Trade,
    sell: Trade,
    symbol: str,
    quantity: int,
) -> None:
    if should_buy(prices_for, symbol):
        buy(symbol, quantity)
    elif should_sell(prices_for, symbol):
        sell(symbol, quantity)
```

Pushed further, `partial` pre-binds the symbol and quantity into zero-argument callables:

```python
buy_now = partial(exchange.buy, symbol, quantity)
sell_now = partial(exchange.sell, symbol, quantity)
buy_signal = partial(should_buy_on_average, exchange.prices, symbol)
sell_signal = partial(should_sell_on_average, exchange.prices, symbol)

if buy_signal():
    buy_now()
elif sell_signal():
    sell_now()
```

## When to stop

The fully functional version is possible, not automatically better. At the extreme the orchestrator does almost nothing: it calls pre-configured functions in sequence, and the complexity has moved into the `partial` calls at the entry point, where it is harder to read and to debug. An object, a group of functions with shared context, would say the same more clearly. Going fully functional can obscure intent as badly as a deep hierarchy.

- Default to steps 3 and 4: higher-order functions with `Callable` aliases, and bound methods.
- Reach for step 5 only when the dependencies must really be composed at startup.
- Fall back to step 1 when the two sides carry meaningful state or more than two or three methods each.
- Keep an ABC only when the base must share implementation.

## Trade-offs

| Form | Strengths | Weaknesses |
| --- | --- | --- |
| ABC bridge | the base holds shared state; enforced abstract methods | coupling through inheritance; boilerplate; harder to test in isolation |
| Protocol bridge | structural typing; third-party classes fit | the bridge field repeated in each class; no shared implementation |
| Functions taking the object | simple; easy to test; no class for stateless rules | still depends on the object's type |
| Functions taking a function | maximum decoupling; the bridge is a type alias | related functions lose their grouping; names must compensate |
| Bound methods | natural idiom; the object stays coherent | the caller must pass `obj.method`, not `obj` |
| `functools.partial` | everything configured at the entry point | hides what runs; partial chains are hard to debug |

Start with the simplest form that keeps the two axes independent, and escalate only for a concrete problem, not because a more functional version exists.

## Bridge, strategy, adapter and injection

- Strategy makes one axis interchangeable; a bridge connects two axes that vary independently. A bridge is two strategies joined by an abstract link (`design-strategy`).
- An adapter fits an existing interface after the fact; a bridge separates the axes by design, before the classes multiply (`design-adapter`).
- The classic bridge is constructor injection, and the functional bridge is parameter injection: the bridge uses dependency injection as its mechanism, and the entry point that wires it is the composition root.
