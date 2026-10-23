# Refactoring moves

A catalog of recurring refactoring transformations, not a gallery of projects. Each move gives the before shape to look for, the after shape, the principle that drives it and the rule that holds its detail. When a review finding needs a code change, find its move here, then apply the moves in the order the process at the end gives.

## Contents

- Smell to move
- 1. Guard clauses to reduce indentation
- 2. Extract named helper functions
- 3. Replace raw data structures with domain classes
- 4. Separate I/O from business logic
- 5. Replace magic numbers with named constants
- 6. Replace string comparisons with enums
- 7. Consolidate rules into data
- 8. Replace catch-all exception handling
- 9. Encapsulate data-structure access
- 10. Remove unnecessary class wrappers
- 11. Keep `__init__` to storing ready-made dependencies
- 12. Use comprehensions over loop-and-append
- 13. Replace recursion with a loop for retries
- 14. Return one type from every path
- Refactoring process

## Smell to move

| Smell in legacy code | Move |
| --- | --- |
| Deep nesting | 1 |
| A complex inline condition with a comment | 2 |
| Raw dicts, lists or tuples carrying domain data | 3 |
| `print` or `input` inside logic classes | 4 |
| Magic numbers | 5 |
| String comparisons | 6 |
| Scattered if/elif rejection or validation chains | 7 |
| Catch-all exception handling | 8 |
| Callers editing another object's collections | 9 |
| A class that only wraps a function | 10 |
| Complex `__init__` methods with setup logic | 11 |
| Loop-and-append | 12 |
| Recursion used to retry | 13 |
| Functions with inconsistent return types | 14 |

## 1. Guard clauses to reduce indentation

Handle the error and edge cases first with early returns, leaving the main path at shallow indentation. Principle: lower cognitive load; readers skip the guards and follow the main path. Rule: python-coding's python-early-return.

```python
def ship_order(order: Order | None) -> None:  # before: the real work sits four levels deep
    if order:
        if order.items:
            for item in order.items:
                if item.price_cents > 0:
                    reserve(item)


def ship_order(order: Order | None) -> None:  # after
    if order is None or not order.items:
        return
    for item in order.items:
        if item.price_cents <= 0:
            continue
        reserve(item)
```

## 2. Extract named helper functions

Move a complex condition into a function whose name says what it checks; the name replaces the comment. Principle: self-documenting code. Rule: python-coding's python-small-units.

```python
if order.total_cents > 100_000 and order.kind is OrderKind.BULK and not user.is_trial:  # before
    approve(order)


def needs_manual_approval(order: Order, user: User) -> bool:  # after
    return order.total_cents > 100_000 and order.kind is OrderKind.BULK and not user.is_trial


if needs_manual_approval(order, user):
    approve(order)
```

## 3. Replace raw data structures with domain classes

Move data and the operations on it from dicts, lists and tuples into a class or dataclass. Principle: data and its operations belong together. Rule: `design-start-with-the-data`.

```python
board = [["O"] * 5 for _ in range(5)]  # before: a raw grid edited from anywhere


def place_ship(board: list[list[str]], row: int, col: int) -> None:
    board[row][col] = "S"


class Board:  # after: the grid and its operations in one place
    def __init__(self, size: int) -> None:
        self._cells = [[Cell.WATER] * size for _ in range(size)]

    def place_ship(self, row: int, col: int) -> None:
        self._cells[row][col] = Cell.SHIP
```

## 4. Separate I/O from business logic

Business logic never reads input or prints. It receives what it needs and returns a result; a thin outer layer talks to the console, the network or the files. Principle: separation of concerns; logic tested without a console. Rule: python-coding's python-pure-core; passing the I/O collaborator in is python-coding's python-dependency-injection.

```python
class Game:  # before: prompts and prints inside the rules
    def play_round(self) -> None:
        guess = input("Enter guess: ")
        print(f"Result: {self._check(guess)}")


class Game:  # after: the rules take a guess and return a result
    def play_round(self, guess: Guess) -> RoundResult:
        return self._check(guess)


def run_round(game: Game, read_guess: Callable[[], Guess]) -> RoundResult:
    return game.play_round(read_guess())  # the entry point shows the result
```

## 5. Replace magic numbers with named constants

Extract hard-coded values into module-level constants with descriptive names, and semantic markers into an enum. Principle: one source of truth; change one constant, not twenty scattered literals. Rule: python-coding's python-data-shapes.

```python
if guesses_left == 5:
    ...  # before

MAX_GUESSES: Final = 5  # after

if guesses_left == MAX_GUESSES:
    ...
```

## 6. Replace string comparisons with enums

Turn scattered string literals into an enum, so a typo fails at once instead of falling through. Principle: type safety. Rule: python-coding's python-enums.

```python
if choice == "rock":
    ...  # before
elif choice == "scisssors":
    ...  # the typo goes unnoticed


class Move(Enum):  # after
    ROCK = "rock"
    PAPER = "paper"
    SCISSORS = "scissors"


if choice is Move.ROCK:
    ...
```

## 7. Consolidate rules into data

Replace a run of separate if-statements that each reject a request with one list of named predicates under a role-named alias. Principle: open/closed; a new rule is one more entry, not an edit to the chain. Rule: `design-open-closed`.

```python
RejectionRule = Callable[[Order, User], bool]


def not_premium(order: Order, user: User) -> bool:
    return not user.is_premium


def over_limit(order: Order, user: User) -> bool:
    return order.total_cents > user.limit_cents


REJECTION_RULES: Final[tuple[RejectionRule, ...]] = (not_premium, over_limit)


def is_rejected(order: Order, user: User) -> bool:
    return any(rule(order, user) for rule in REJECTION_RULES)
```

## 8. Replace catch-all exception handling

Replace a bare `except:` or `except Exception:` with the specific exception, translated into a domain error that names the offending value and keeps the cause. Principle: fail explicitly; generic catches hide real bugs. Rule: python-coding's python-error-handling.

```python
try:  # before
    amount = int(text)
except:
    return "error"

try:  # after
    amount = int(text)
except ValueError as exc:
    raise InvalidAmountError(f"expected a whole number, got {text!r}") from exc
```

## 9. Encapsulate data-structure access

Do not let callers change another object's internal collections; give the owner a method that names the operation. Principle: Law of Demeter; each object controls its own data. Rule: `design-tell-dont-ask`.

```python
game.scoreboard.points[player] += 1  # before
game.scoreboard.add_point(player)  # after
```

## 10. Remove unnecessary class wrappers

Replace a class that only wraps a function, with an empty `__init__` and one method, by the function itself. Principle: keep it simple; a class must earn its place by guarding state. Rule: `design-lightest-construct`.

```python
class AmountParser:  # before
    def __init__(self) -> None:
        pass

    def parse(self, text: str) -> int:
        return int(text)


def parse_amount(text: str, *, minimum: int, maximum: int) -> int:  # after
    amount = int(text)
    if not minimum <= amount <= maximum:
        raise InvalidAmountError(f"expected {minimum}..{maximum}, got {amount}")
    return amount
```

## 11. Keep `__init__` to storing ready-made dependencies

Move setup steps, printing and other work out of `__init__`; it receives what the object needs, already built. Principle: separate creation from use. Rule: `design-complete-construction`.

```python
class Game:  # before: __init__ builds, registers and starts
    def __init__(self, player_name: str) -> None:
        self.board = self._create_board()
        self._register_player(player_name)
        self._start()


class Game:  # after
    def __init__(self, board: Board, player: Player) -> None:
        self.board = board
        self.player = player
```

## 12. Use comprehensions over loop-and-append

Replace an empty list filled in a loop with a comprehension when each element is one simple transform or filter. Principle: the expression states the intent. Rule: python-coding's python-comprehensions.

```python
alive = [cell for row in grid for cell in row if cell.is_alive]  # was a nested loop with append
```

## 13. Replace recursion with a loop for retries

A function that calls itself to ask again grows the stack with every bad answer. Loop instead, and take the reader and the validator as parameters so the logic stays testable without a console. Principle: recursion is for recursive problems, not loops. Rule: python-coding's python-pure-core.

```python
def read_valid(read: Callable[[], str], is_valid: Callable[[str], bool]) -> str:
    while True:  # was: if not is_valid(value): return self.read_input()
        value = read()
        if is_valid(value):
            return value
```

## 14. Return one type from every path

A function that returns `Command` on one path and `False` on another forces every caller to check types. Return `Command | None` where absence is normal, or raise. Principle: type safety. Rule: python-coding's python-error-boundaries.

```python
def parse_command(text: str) -> Command | bool: ...  # before: False on failure


def parse_command(text: str) -> Command | None: ...  # after
```

## Refactoring process

1. Read and understand: change nothing until you know what the code does and who calls it.
2. Add characterization tests that pin the current behavior before changing it (python-architecture's arch-make-legacy-testable).
3. Pick the worst smell: start with the move that removes the most complexity, data shapes first.
4. Apply one move at a time; do not refactor everything at once.
5. Run the tests after each move to confirm the behavior is unchanged.
6. Repeat with the next smell.
