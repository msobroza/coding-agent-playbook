---
id: design-patterns
name: design-patterns
description: "Shapes the code inside Python modules."
playbook:
  use_when: "designing or refactoring classes and modules, hunting design smells or weighing a pattern"
  files: "Python classes and modules under design or refactoring"
  sections:
    - id: responsibilities
      title: "Responsibilities"
      impact: HIGH
      summary: "Give each unit one reason to change and put behavior beside the data it uses."
      open_when: "A class or module takes on a second job, callers pull its fields to decide for it, or code must pick who creates an object."
    - id: abstractions
      title: "Abstractions and coupling"
      impact: HIGH
      summary: "Depend on narrow, consumer-owned abstractions at real seams; extend by adding, not editing; compose before inheriting."
      open_when: "A class is subclassed or gets a mixin, an interface or an injected collaborator, or each new kind forces edits in several places."
    - id: simplicity
      title: "Simplicity and restraint"
      impact: HIGH
      summary: "Build only the structure today's code needs, in the lightest construct, and add a pattern only for a present smell."
      open_when: "Code adds a class, factory, option or layer with one caller and no second variant, or copies logic that exists elsewhere."
    - id: smells
      title: "Smells and review"
      impact: MEDIUM
      summary: "Review data first, rank findings by severity, and fix naming, construction and data-shape smells."
      open_when: "A design review or cleanup is requested, detect_smells.py reports a hit, or fields share a prefix, names are vague or objects need setup calls."
    - id: common-patterns
      title: "Common patterns"
      impact: MEDIUM
      summary: "Pythonic forms of the patterns most Python code needs: plugins, dispatch tables, strategies, adapters, value objects, events, lazy values."
      open_when: "Code grows an if/elif on a key, loads plugins, wraps a vendor SDK, notifies other parts after an action, caches a costly value or passes raw amounts."
    - id: specialized-patterns
      title: "Specialized patterns"
      impact: LOW
      summary: "Patterns to reach for only when their signal is present and a lighter form has failed."
      open_when: "Code hard-codes its caller's reaction, copies one algorithm, needs a class per combination, undo, modes, chained steps or many options."
---

# Design patterns

Design guidance for the shape of code inside Python modules, for people and coding agents alike: who owns each responsibility, which abstractions and couplings a unit may have, how much structure today's code needs, how to review a module for smells, and the Pythonic form of each classic pattern. Line- and function-level idioms live in the python-coding skill, and relations between modules (layers, import direction, the composition root, persistence) in the python-architecture skill.

## Quick reference

Extend by adding a variant, not by editing a ladder:

```python
class JsonFormat:
    def export(self, invoice: Invoice) -> str: ...


class CsvFormat:
    def export(self, invoice: Invoice) -> str: ...
```

Consumers declare small Protocols with only the methods they call:

```python
class Workable(Protocol):
    def work(self) -> None: ...
```

### Seven principles

1. High cohesion: each class, function and module has one job; extract a class or a function when it does two (Responsibilities).
2. Low coupling: move behavior to the unit that owns the data and pass only what a function needs (Responsibilities; Abstractions and coupling).
3. Depend on abstractions: a role-named `Callable` alias or a small `Protocol` at a real seam; patterns follow from removing coupling (Abstractions and coupling).
4. Composition over inheritance: hold a collaborator and delegate; inherit only where every subclass substitutes (Abstractions and coupling).
5. Separate creation from use: one place builds the objects, a mapping replaces an if/elif that picks a constructor (Responsibilities; Common patterns; the composition root itself is the python-architecture skill's).
6. Start with the data: fix the record shapes first, then the functions and classes around them (Smells and review).
7. Keep things simple: one home per piece of knowledge, the lightest construct that works, nothing built for a need nobody stated (Simplicity and restraint).

### Patterns: lightest form first

Move right only when the lighter form fails; the "stop when" column says when to stay lighter or skip the pattern.

| Signal in the code | Lightest Pythonic form | Heavier form | Stop when | Pattern |
| --- | --- | --- | --- | --- |
| Other packages add variants | explicit `register(registry)` functions called by the entry point | entry-point discovery | every variant lives in this repo | plugin loading |
| if/elif maps a key from config or data to a constructor | a `Final` mapping that raises a domain error naming the known keys | a registry object filled by register calls | the keys are a closed enum matched once | dispatch table |
| if/elif chooses among algorithms | pass a function typed with a `Callable` alias | callable dataclass, then Protocol classes | two fixed branches that will not grow | strategy |
| A third-party API has the wrong shape | a wrapper function | an adapter class implementing your Protocol | both sides are your own code | adapter |
| Bare `str`, `int` or `float` for a domain value | a frozen dataclass that validates | a richer value type with operations | the value has no rules | value object |
| Core logic calls several side-effect systems | return event objects; one dispatcher calls handlers | in-process pub/sub keyed by event class | one side effect with one caller | domain events |
| An expensive value is needed only sometimes | a cached module function or `functools.cached_property` | a lazy proxy object | it is always needed at startup | lazy loading |
| A class hard-codes how its caller reacts | pass a callback with a named no-op default | a list of handlers | one fixed reaction | callback |
| An existing function's parameters do not fit a seam | a small function that translates and delegates | an adapter class | the caller can pass the values directly | function wrapper |
| Configuration and runtime arguments arrive together | a function that returns a configured closure | a callable frozen dataclass | the configuration is used once | function builder |
| Same steps, different details across classes | one function taking the varying steps as parameters | an ABC template method | only one variant exists | template method |
| Behavior depends on a mode that changes | an enum plus a transition table | state objects behind a Protocol | two states that barely differ | state |
| Many optional parts, validated together | a dataclass with defaults and keyword-only fields | a builder whose `build()` returns a frozen product | every field is known at once | builder |
| Sequential calls on one object read as noise | methods that return a new instance for chaining | a fluent builder | two or three calls read fine | fluent interface |
| Callers coordinate many subsystem calls | one function that runs the sequence | a facade class | the subsystem is already simple | facade |
| Nested calls transform data step by step | a list of functions applied in order | a handler chain with early exit | three steps read fine inline | pipeline |
| Undo, redo, queued or logged actions | functions returning an undo closure | command dataclasses with `execute` and `undo` | nobody reverses or replays | command |
| One shared instance | build it in the entry point and pass it down | a module-level instance for stateless process-wide services | tests need separate instances | singleton |
| Families of objects must match | a frozen dataclass bundling the callables | one factory class per family | there is only one family | abstract factory |
| Two independent axes vary, one class per combination | inject one axis as a `Callable` or Protocol | two class hierarchies joined by a reference | one axis never varies | bridge |
| Data access mixed into domain classes | see the python-architecture skill | | | repository, unit of work |
| Reads and writes diverge, or history must be replayed | see the python-architecture skill | | | CQRS, event sourcing |
| Transient failures on outbound calls | see the python-coding skill | | | retries and timeouts |

Default preferences for every pattern:

- A Protocol before an ABC, unless the base must hold shared state or enforce overrides.
- `functools.partial` and closures to configure a generic function, rather than wrapper classes.
- A closure to separate configuration-time arguments from runtime arguments.
- Do not go fully functional: readability decides, and a small class with named fields often reads best.

## Scripts

Two stdlib scripts sit in this skill's `scripts/` directory and run on Python 3.10 or later:

```bash
python3 <this skill's directory>/scripts/detect_smells.py src/
python3 <this skill's directory>/scripts/lcom4_clusters.py src/
```

- `detect_smells.py` takes files or directories (default: the current directory) and prints a JSON array of `{"smell", "file", "line", "evidence"}` objects; it exits 0 with or without hits and 2 on a usage error.
- `lcom4_clusters.py` prints `{"class", "file", "line", "lcom4", "clusters"}` for each class whose methods fall into more than one group (`--all` lists every class); each cluster is a candidate class after a split.

Both print candidates, not verdicts: open the code at every hit and confirm it before reporting it.

## See also

python-coding, python-architecture, python-testing, python-tooling.
