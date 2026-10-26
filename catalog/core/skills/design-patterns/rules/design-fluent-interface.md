---
id: design-fluent-interface
name: Fluent interface
description: "When a sequence of calls on one object reads as noise or keeps parallel lists in step, give it domain verbs that each return a new frozen instance, so the chain reads as the sequence and two chains from a shared base cannot interfere."
scope: scoped
globs:
  - "**/*.py"
section: specialized-patterns
priority: 86
tags: [python, design, patterns]
---

# Fluent interface

## Description

A fluent interface lets calls chain, so code that builds a sequence, a configuration or a pipeline reads in order, like a small domain language. Use it when order matters and separate statements on one object are verbose or easy to get out of sync. Name the methods after domain actions, hold each step as one record so related values cannot drift apart, and return a new instance from each method. A fluent API that mutates and returns `self` lets two chains started from a shared base change each other.

## Bad Example

```python
@dataclass
class Animation:
    steps: list[Step] = field(default_factory=list)
    durations: list[float] = field(default_factory=list)  # must stay aligned with steps

    def add(self, step: Step, duration: float = 1.0) -> None:
        self.steps.append(step)
        self.durations.append(duration)


animation = Animation()
animation.add(Rotate(60))
animation.add(Move(200, 0))
animation.add(FadeTo(0.0), duration=0.5)
```

## Good Example

```python
@dataclass(frozen=True)
class TimedStep:
    step: Step
    duration: float


@dataclass(frozen=True)
class Animation:
    steps: tuple[TimedStep, ...] = ()

    def _then(self, step: Step, duration: float) -> "Animation":
        return replace(self, steps=(*self.steps, TimedStep(step, duration)))

    def rotate(self, degrees: float, duration: float = 1.0) -> "Animation":
        return self._then(Rotate(degrees), duration)

    def move(self, dx: float, dy: float, duration: float = 1.0) -> "Animation":
        return self._then(Move(dx, dy), duration)

    def fade_to(self, opacity: float, duration: float = 1.0) -> "Animation":
        return self._then(FadeTo(opacity), duration)


intro = Animation().rotate(60).move(200, 0)
fade_out = intro.fade_to(0.0, duration=0.5)  # intro is unchanged
slide_back = intro.move(-200, 0)
```

## Notes

- Wrap long chains in parentheses, one call per line, rather than backslashes.
- On Python 3.11 and later, annotate the chaining methods with `typing.Self` so a subclass's chain keeps its own type; the string forward reference works on every version.
- Good fit: ordered operations (animations, validation chains, configuration flows, query or pipeline construction) and APIs that should read as a sequence of actions.
- Bad fit: a one-off call (call a function), operations with no natural order, steps applied out of order, or chains so long that they hide what happens.
- A builder collects parts in a mutable builder and returns a separate frozen product from `build()`; a fluent interface returns the object itself or a new copy of it: design-builder.
- Stop when two or three plain calls read fine.
