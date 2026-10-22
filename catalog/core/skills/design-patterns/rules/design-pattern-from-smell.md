---
id: design-pattern-from-smell
name: A pattern only for a present smell
description: "Start from a smell visible in today's code, stop at the lightest form that removes it, and remove a pattern that no longer earns its keep."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: simplicity
priority: 52
tags: [python, design, patterns]
---

# A pattern only for a present smell

## Description

Do not start from a pattern catalog and look for places to apply it. Start from a problem the code has today (a growing if/elif, a hard-wired collaborator, side effects mixed into core logic), remove the coupling behind it, and let the pattern emerge: a `Callable` alias passed in is a strategy, a mapping of constructors is a factory, a dependency passed from outside is injection. Stop at the first form that removes the smell. A Protocol, factory, registry or strategy with one implementation, no test double and no planned second variant (smell id speculative-abstraction) makes every reader pay for indirection that buys nothing yet.

## Bad Example

```python
class GreetingStrategy(Protocol):
    def greet(self, name: str) -> str: ...


class DefaultGreeting:  # the only implementation, never swapped
    def greet(self, name: str) -> str:
        return f"Welcome back, {name}"


def make_greeting_strategy() -> GreetingStrategy:  # a factory with one product
    return DefaultGreeting()


def build_greeting(name: str) -> str:
    return make_greeting_strategy().greet(name)
```

## Good Example

```python
def greeting(name: str) -> str:
    return f"Welcome back, {name}"
```

When a second variant arrives, or a test needs to swap the behavior, reintroduce the seam in its lightest form:

```python
Greet = Callable[[str], str]


def welcome_message(name: str, *, greet: Greet = greeting) -> str:
    return greet(name)
```

## Notes

- Default preferences for every pattern are design-lightest-construct's promotion ladder and its limit (do not convert when the lighter form reads worse); an `ABC` beats a `Protocol` only when the base must hold shared state or enforce overrides.
- Move from the lightest form to a heavier one only when the lighter form fails; the pattern table in this skill's SKILL.md gives the signal, the lightest form, the heavier form and when to stop, per pattern.
- Not speculative: a port at an I/O boundary that tests fake, and documented extension points (entry-point groups, plugin base classes).
- Removing a pattern that no longer earns its keep is as valid a recommendation as adding one.
- When suggesting a pattern, show where the smell is, the before and after, and the trade-off; rank suggestions by impact (one that simplifies fifty lines beats one that saves three), and say so when the simple version is fine as it is.
