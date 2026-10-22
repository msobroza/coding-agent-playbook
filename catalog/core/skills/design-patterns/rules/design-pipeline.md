---
id: design-pipeline
name: Pipeline
description: "When a value passes through a configurable series of transformations, list named step functions of one typed alias and apply them in order, wrapping a failure with the step's name; keep three fixed steps inline."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: specialized-patterns
priority: 88
tags: [python, design, patterns]
---

# Pipeline

## Description

Nested calls such as `truncate(collapse(strip(text)))` read inside out, and adding, removing or reordering a step means editing the nesting. A pipeline turns the steps into data: a sequence of functions that share one signature, applied left to right. The order reads as written, the sequence can be built from configuration or inspected, and each step is a small function tested on its own. Steps return new values rather than mutating their input.

## Bad Example

```python
def clean_title(raw: str) -> str:
    # Inside out, and every new step adds another layer of parentheses.
    return truncate(collapse_whitespace(strip_markup(raw.strip())), max_length=80)
```

## Good Example

```python
TextStep = Callable[[str], str]


class StepFailedError(PipelineError):
    def __init__(self, step_name: str, value: str) -> None:
        super().__init__(f"pipeline step {step_name!r} failed on {value!r}")
        self.step_name = step_name
        self.value = value


def compose(*steps: TextStep) -> TextStep:
    """Apply the steps left to right; a step's ValueError names the step and its input."""

    def run(value: str) -> str:
        for step in steps:
            try:
                value = step(value)
            except ValueError as exc:
                name = getattr(step, "__name__", repr(step))
                raise StepFailedError(name, value) from exc
        return value

    return run


clean_title = compose(
    str.strip,
    strip_markup,
    collapse_whitespace,
    partial(truncate, max_length=80),
)
```

`functools.partial` fills in configuration so every step matches `TextStep`; adding a step is one more line in the list.

## Notes

- `functools.reduce` can build the same composition; hide it inside `compose` so callers never read it, and use named functions, not lambdas assigned to names.
- Wrap a failure with the failing step's name (`raise StepFailedError(name, value) from exc`); otherwise the traceback does not say which stage broke.
- Heavier form: a chain of handlers, each holding its own state and deciding whether to pass the value on, for when a step may stop the flow early (middleware, event handling).
- For streams, chain generator expressions or `itertools` so each item flows through the steps without building full lists.
- Restraint: three fixed steps read clearly as plain sequential calls with named intermediate values. The same variable reassigned step after step suggests a pipeline only when the steps vary or keep growing.
- Data-frame pipelines are the ml-data skill's.
