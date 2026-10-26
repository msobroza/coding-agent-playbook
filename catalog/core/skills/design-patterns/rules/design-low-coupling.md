---
id: design-low-coupling
name: Low coupling
description: "Minimize what one unit must know about another: pick the loosest form of coupling that stays readable, and replace shared globals with values passed in."
scope: scoped
globs:
  - "**/*.py"
section: abstractions
priority: 44
tags: [python, design, coupling]
---

# Low coupling

## Description

Coupling is how much one unit must know about another to work. The less it knows, the less a change in one place ripples through the others. From tightest to loosest:

1. **Content:** writing another object's internals (`account._balance -= fee`).
2. **Global:** several functions read and rebind the same module state.
3. **External:** a third-party API's types and calls spread through business code.
4. **Control:** a flag argument steers which branch the callee runs.
5. **Stamp:** a whole record is passed when one field is used.
6. **Data:** plain values passed as parameters, normal and expected.
7. **Message:** a published event the sender does not track.

Removing one form often introduces another, so aim for the least harmful form, not for zero coupling.

## Bad Example

```python
API_URL = os.environ["API_URL"]  # global coupling: every function reads module state
TOKEN = os.environ["API_TOKEN"]


def post_reading(path: str, reading: Reading) -> None:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    send(f"{API_URL}/{path}", headers=headers, body=reading.to_json())
```

## Good Example

```python
@dataclass(frozen=True)
class ApiSettings:
    base_url: str
    token: str
    account_id: int


class ApiClient:
    def __init__(self, settings: ApiSettings, send: SendRequest) -> None:
        self._settings = settings
        self._send = send

    def post_reading(self, path: str, reading: Reading) -> None:
        headers = {"Authorization": f"Bearer {self._settings.token}"}
        self._send(f"{self._settings.base_url}/{path}", headers, reading.to_json())


def main() -> None:
    settings = load_api_settings()  # loaded once, at the entry point
    client = ApiClient(settings, send=http_send)
    run_station(client)
```

## Notes

- The trade-off chain: three config globals replaced by six parameters trade global coupling for a noisy signature; grouping those values into a small settings dataclass built by the entry point is usually the balanced end point.
- Stamp coupling is often the clearer choice when the callee is conceptually "about" the record. Do not shred a cohesive record into loose arguments just to rank lower; when a function uses one nested field of a complex object, pass that field.
- Content coupling's fix is to move the behavior to the owner (`account.withdraw(fee)`): `design-tell-dont-ask`.
- External coupling's fix is a wrapper or adapter that keeps the vendor's types out of business code.
- Let the owner compute its part instead of testing its kind: a payment method that provides `net_price(amount: Decimal) -> Decimal` spares the sale an `isinstance` ladder over payment methods, and adding a method needs no change to the sale.
- Decoupling moves: put the method on the class that owns the data, return values instead of causing side effects, pass only what a function needs, and introduce an intermediate record when two subsystems know too much of each other.
- Hard-wired collaborators (a client built inside `__init__`) are `python-dependency-injection` in the python-coding skill.
